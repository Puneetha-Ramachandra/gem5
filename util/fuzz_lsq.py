# fuzz_lsq.py: gem5-micro Case Study
# Agent-driven LSQ stress testing using MicroInjection.
# Validates the paper's claim (§4) that lsq_forw_loads and lsq_full_events
# are reachable via MicroInjection but not through compiled binaries.

import os
import struct
import sys
import tempfile
import m5
from m5.objects import *
from m5.objects.MicroCPU import MicroCPU

# Include util dir to import shared micro_elf library
sys.path.append(os.path.dirname(__file__))
from micro_elf import make_spin_elf


def parse_stat(stats_path, stat_name, block_index=0):
    """Return the integer value of a stat from the N-th stats block, or 0."""
    try:
        with open(stats_path) as f:
            current_block = -1
            for line in f:
                if "Begin Simulation Statistics" in line:
                    current_block += 1
                elif current_block == block_index:
                    if line.startswith(stat_name):
                        parts = line.split()
                        if len(parts) >= 2:
                            return int(float(parts[1]))
    except FileNotFoundError:
        pass
    return 0

print("--- [fuzz_lsq] Starting LSQ Stress Test ---", flush=True)

# 1. System Setup
system = System()
system.clk_domain = SrcClockDomain(clock='1GHz', voltage_domain=VoltageDomain())
system.mem_mode = 'timing'
system.mem_ranges = [AddrRange('512MB')]

_spin_elf = tempfile.mktemp(suffix='.elf')
spin_addr, nop_addr = make_spin_elf(_spin_elf, arch='riscv')

# 2. MicroCPU Configuration
system.cpu = MicroCPU(numThreads=1, LQEntries=16, SQEntries=8, synth_pc_base=nop_addr)
system.cpu.clk_domain = system.clk_domain
system.cpu.isa = [RiscvISA()]
system.cpu.decoder = [RiscvDecoder(isa=system.cpu.isa[0])]
system.cpu.branchPred = BranchPredictor(numThreads=1)
system.cpu.branchPred.conditionalBranchPred = TournamentBP(numThreads=1)
system.cpu.createInterruptController()

# Spin-loop binary: jal x0,0 forever.  No branch mispredictions after the
# first iteration, so the hello binary's squash interference is avoided.
system.cpu.workload = [Process(executable=_spin_elf, cmd=['spin'])]
system.workload = RiscvEmuLinux()

# 3. Memory Hierarchy — L1 caches are essential.
# Without them, every instruction fetch goes directly to DRAM (~83000 ticks).
# This causes the branch predictor to retrain after every misprediction squash
# (new DRAM fetch needed each time), creating periodic squash events that kill
# injected ops indefinitely regardless of warmup time.
# With L1 caches, the spin loop's icache miss only occurs once; all subsequent
# iterations hit L1 in ~4 cycles, training the predictor to steady state fast.
system.membus = SystemXBar()
system.cpu.icache = Cache(
    size='32kB', assoc=8,
    tag_latency=2, data_latency=2, response_latency=2,
    mshrs=4, tgts_per_mshr=20)
system.cpu.dcache = Cache(
    size='32kB', assoc=8,
    tag_latency=2, data_latency=2, response_latency=2,
    mshrs=4, tgts_per_mshr=20)
system.cpu.icache.cpu_side = system.cpu.icache_port
system.cpu.icache.mem_side = system.membus.cpu_side_ports
system.cpu.dcache.cpu_side = system.cpu.dcache_port
system.cpu.dcache.mem_side = system.membus.cpu_side_ports
system.system_port = system.membus.cpu_side_ports
# SimpleMemory avoids DDR3's ~200k-tick initialization overhead.
# DDR3 init was delaying the first instruction fetch past our warmup window,
# causing periodic DRAM-miss-driven mispredictions that squashed injected ops.
system.mem_ctrl = SimpleMemory(range=system.mem_ranges[0], latency='10ns')
system.mem_ctrl.port = system.membus.mem_side_ports

root = Root(full_system=False, system=system)

print(flush=True)
print("=" * 62, flush=True)
print("  gem5-micro: LSQ Fuzzing Case Study  (paper section 4)", flush=True)
print("=" * 62, flush=True)
m5.instantiate()

addr_reg = 2   # x2 = sp, valid mapped stack address in SE mode
data_reg = 1   # x1 (store data — value doesn't matter for forwarding/lsqFull)
SQ_SIZE  = 8   # matches SQEntries above

# Warm up: clear TC squash + spin-loop branch predictor training
print(flush=True)
print("  Warming up pipeline ...", flush=True)
m5.simulate(100000)
m5.stats.reset()

# ---- Baseline: spin loop only, no injection --------------------------------
print(flush=True)
print("  Baseline (no injection) — running spin loop ...", flush=True)
exit_event = m5.simulate(500000)
print(f"  Done: {exit_event.getCause()}", flush=True)
m5.stats.dump()

# Reset stats for the injection run
m5.stats.reset()

# ---- Phase 1: fill SQ with SQ_SIZE stores ----------------------------------
# Simulate just 3 cycles after injection so the stores dispatch (SQ fills to
# SQ_SIZE/SQ_SIZE) but haven't committed yet.  The SQ stays full when Phase 2
# stores arrive, triggering SQFullEvents.
print(flush=True)
print("  Phase 1 — fill SQ with stores:", flush=True)
for i in range(SQ_SIZE):
    offset = -8 - i * 8
    print(f"    [ST] Mem[sp + {offset}] = x1  ->  SQ[{i}]", flush=True)
    system.cpu.injectSt(addr_reg, data_reg, offset)
print(f"  SQ is now {SQ_SIZE}/{SQ_SIZE} full — dispatching ...", flush=True)

m5.simulate(3000)

# ---- Phase 2: aliasing loads + overflow stores -----------------------------
# Loads first: they alias with Phase 1 stores still in the SQ and get
# forwarded directly (forwLoads events).  Extra stores overflow the full SQ
# (SQFullEvents).
print(flush=True)
print("  Phase 2 — aliasing loads (forwarding) + overflow stores (SQ full):", flush=True)

for i in range(SQ_SIZE):
    offset = -8 - i * 8
    dest   = (i % 6) + 4
    print(f"    [LD] x{dest} = Mem[sp + {offset}]  (aliases ST above -> forward)", flush=True)
    system.cpu.injectLd(addr_reg, dest, offset)

for i in range(SQ_SIZE, SQ_SIZE + 4):
    offset = -8 - i * 8
    print(f"    [ST] Mem[sp + {offset}] = x1  ->  SQ FULL -> SQFullEvent", flush=True)
    system.cpu.injectSt(addr_reg, data_reg, offset)

print(flush=True)
print("  Simulating ...", flush=True)
exit_event = m5.simulate(500000)
print(f"  Done: {exit_event.getCause()}", flush=True)
m5.stats.dump()

# ---- Validation & comparison table (paper §4) ------------------------------
stats_path = os.path.join("m5out", "stats.txt")

base_forw = parse_stat(stats_path, "system.cpu.lsq0.forwLoads",         0)
base_full = parse_stat(stats_path, "system.cpu.rename.SQFullEvents",    0)
inj_forw  = parse_stat(stats_path, "system.cpu.lsq0.forwLoads",         1)
inj_full  = parse_stat(stats_path, "system.cpu.rename.SQFullEvents",    1)

W = max(len(str(base_forw)), len(str(inj_forw)),
        len(str(base_full)), len(str(inj_full)), 8)

print(flush=True)
print(f"  {'stat':<26}  {'baseline':>{W}}  {'injected':>{W}}", flush=True)
print(f"  {'-'*26}  {'-'*W}  {'-'*W}", flush=True)
print(f"  {'lsq0.forwLoads':<26}  {base_forw:>{W}}  {inj_forw:>{W}}", flush=True)
print(f"  {'rename.SQFullEvents':<26}  {base_full:>{W}}  {inj_full:>{W}}", flush=True)
print(flush=True)

failures = []
if inj_forw == 0:
    failures.append("forwLoads == 0 in injected run; expected > 0")
if inj_full == 0:
    failures.append("SQFullEvents == 0 in injected run; expected > 0")

if failures:
    for msg in failures:
        print(f"FAIL: {msg}")
    sys.exit(1)
else:
    print("--- [fuzz_lsq] Validation: PASS ---")
