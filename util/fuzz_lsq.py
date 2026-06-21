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


SYNTH_PC_BASE = 0x20000  # must match SYNTH_PC_BASE in src/cpu/o3/rename.cc

def make_riscv_spin_elf(path):
    """Write a minimal ELF64 RISC-V binary with two PT_LOAD segments:
      0x10000: spin loop  — jal x0,0 × 1024 (the CPU workload)
      0x20000: NOP page   — addi x0,x0,0 × 1024 (synthetic PC landing zone)

    Injected ops use PCs from the NOP page (SYNTH_PC_BASE + seq*4) rather
    than the spin loop.  The spin loop's jal x0,0 at 0x10000 creates a BTB
    entry; if injected stores share that PC the commit stage detects a
    false 'branch misprediction' (non-branch committed where BTB expected a
    taken branch).  The NOP page has no BTB entries, so injected ops and
    any squash-recovery fetches to 0x20000+ commit cleanly without squashes.
    """
    SPIN_ADDR = 0x10000
    NOP_ADDR  = SYNTH_PC_BASE   # 0x20000
    ENTRY     = SPIN_ADDR
    SPIN_CODE = struct.pack('<I', 0x0000006f) * 1024  # jal x0,0  × 1024 = 4KB
    NOP_CODE  = struct.pack('<I', 0x00000013) * 1024  # addi x0,x0,0 × 1024 = 4KB

    e_ident = b'\x7fELF' + b'\x02\x01\x01\x00' + b'\x00'*8
    # Two program headers — update e_phnum=2
    elf_hdr = struct.pack('<HHIQQQIHHHHHH',
        2, 0xF3, 1, ENTRY,
        64,       # e_phoff
        0, 0,
        64,       # e_ehsize
        56,       # e_phentsize
        2,        # e_phnum  ← two segments
        64, 0, 0,
    )

    # Segment 0: spin loop at SPIN_ADDR
    spin_off = 64 + 56 * 2           # file offset: after elf_hdr + 2×phdr
    ph0 = struct.pack('<IIQQQQQQ',
        1, 5,                         # PT_LOAD, PF_R|PF_X
        spin_off, SPIN_ADDR, SPIN_ADDR,
        len(SPIN_CODE), len(SPIN_CODE), 0x1000,
    )

    # Segment 1: NOP page at NOP_ADDR
    nop_off = spin_off + len(SPIN_CODE)
    ph1 = struct.pack('<IIQQQQQQ',
        1, 5,                         # PT_LOAD, PF_R|PF_X
        nop_off, NOP_ADDR, NOP_ADDR,
        len(NOP_CODE), len(NOP_CODE), 0x1000,
    )

    with open(path, 'wb') as f:
        f.write(e_ident + elf_hdr + ph0 + ph1 + SPIN_CODE + NOP_CODE)
    os.chmod(path, 0o755)


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

# 2. MicroCPU Configuration
system.cpu = MicroCPU(numThreads=1, LQEntries=16, SQEntries=8)
system.cpu.clk_domain = system.clk_domain
system.cpu.isa = [RiscvISA()]
system.cpu.decoder = [RiscvDecoder(isa=system.cpu.isa[0])]
system.cpu.branchPred = BranchPredictor(numThreads=1)
system.cpu.branchPred.conditionalBranchPred = TournamentBP(numThreads=1)
system.cpu.createInterruptController()

# Spin-loop binary: jal x0,0 forever.  No branch mispredictions after the
# first iteration, so the hello binary's squash interference is avoided.
_spin_elf = tempfile.mktemp(suffix='.elf')
make_riscv_spin_elf(_spin_elf)
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

print("--- [fuzz_lsq] Instantiating Simulation ---", flush=True)
m5.instantiate()

addr_reg = 2   # x2 = sp, valid mapped stack address in SE mode
data_reg = 1   # x1 (store data — value doesn't matter for forwarding/lsqFull)
SQ_SIZE  = 8   # matches SQEntries above

# Wait for the initial squashFromTC (CPU init) to clear.  At tick 0 the TC
# squash fires and kills any ops already in the pipeline; by tick 2000 the
# squash has fully propagated and the spin loop is running cleanly.
print("--- [fuzz_lsq] Waiting for TC squash to clear ---", flush=True)
m5.simulate(100000)  # clears TC squash (tick 0) + first jal mispred with SimpleMemory
m5.stats.reset()

# --- Baseline Phase: Run without instruction injection ---
print("--- [fuzz_lsq] Running Baseline Phase (No Injection) ---", flush=True)
exit_event = m5.simulate(500000)
print(f"--- [fuzz_lsq] Baseline Simulation Finished: {exit_event.getCause()} ---", flush=True)
m5.stats.dump()

# Reset stats for the injection run
m5.stats.reset()

# --- Injection Phase ---
# Phase 1: inject exactly SQ_SIZE stores and simulate 3 cycles (3000 ticks) — enough for
# dispatch (SQ fills to SQ_SIZE/SQ_SIZE) but not enough to commit
# (commit requires execute + writeback + cache-write ≥ ~8 cycles from dispatch).
print("--- [fuzz_lsq] Injection Phase 1: Fill SQ ---", flush=True)
for i in range(SQ_SIZE):
    system.cpu.injectSt(addr_reg, data_reg, -8 - i * 8)

m5.simulate(3000)

# Phase 2: inject aliasing loads first (so they rename/dispatch and forward
# from the Phase 1 stores still in the SQ), followed by more stores to
# fill the SQ and trigger SQFullEvents.
print("--- [fuzz_lsq] Injection Phase 2: Trigger lsqFull + forwarding ---", flush=True)
for i in range(SQ_SIZE):
    system.cpu.injectLd(addr_reg, (i % 6) + 4, -8 - i * 8)

for i in range(SQ_SIZE, SQ_SIZE + 4):
    system.cpu.injectSt(addr_reg, data_reg, -8 - i * 8)

print("--- [fuzz_lsq] Simulating Injection Phase ---", flush=True)
exit_event = m5.simulate(500000)
print(f"--- [fuzz_lsq] Injection Simulation Finished: {exit_event.getCause()} ---", flush=True)
m5.stats.dump()

# --- Validation & Comparison (paper §4) ---
stats_path = os.path.join("m5out", "stats.txt")

# Parse baseline stats (first stats block, index 0)
base_forw_loads = parse_stat(stats_path, "system.cpu.lsq0.forwLoads", 0)
base_lsq_full = parse_stat(stats_path, "system.cpu.rename.SQFullEvents", 0)

# Parse injected stats (second stats block, index 1)
inj_forw_loads = parse_stat(stats_path, "system.cpu.lsq0.forwLoads", 1)
inj_lsq_full = parse_stat(stats_path, "system.cpu.rename.SQFullEvents", 1)

# Print comparison table
print("", flush=True)
print("                     baseline    injected", flush=True)
print(f" lsq0.forwLoads           {base_forw_loads}          {inj_forw_loads}", flush=True)
print(f" rename.SQFullEvents       {base_lsq_full}         {inj_lsq_full}", flush=True)
print("", flush=True)

failures = []
if inj_forw_loads == 0:
    failures.append(f"forwLoads == 0 in injected run; expected > 0")
if inj_lsq_full == 0:
    failures.append(f"SQFullEvents == 0 in injected run; expected > 0")

if failures:
    for msg in failures:
        print(f"FAIL: {msg}")
    sys.exit(1)
else:
    print("--- [fuzz_lsq] Validation: PASS ---")
