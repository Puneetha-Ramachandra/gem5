# test_gem5_micro.py — gem5-micro Live Demo
# MicroDump  — inject 2 ops, dump to binary trace
# MicroPlayback — stream trace back through rename

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

RECORD_SIZE   = 12  # 1B opcode + 8B offset + 1B rd + 1B rs1 + 1B rs2


def parse_trace(trace_path):
    """Return (total_records, active_records) from a MicroISA trace file."""
    total, active = 0, 0
    try:
        with open(trace_path, 'rb') as f:
            while True:
                rec = f.read(RECORD_SIZE)
                if len(rec) < RECORD_SIZE:
                    break
                total += 1
                if rec[0] != 0:   # opcode 0 = native ISA sentinel
                    active += 1
    except FileNotFoundError:
        pass
    return total, active


# ---- System setup ----------------------------------------------------------
system = System()
system.clk_domain = SrcClockDomain(clock='1GHz', voltage_domain=VoltageDomain())
system.mem_mode   = 'timing'
system.mem_ranges = [AddrRange('512MB')]

_spin_elf = tempfile.mktemp(suffix='.elf')
spin_addr, nop_addr = make_spin_elf(_spin_elf, arch='riscv')

system.cpu = MicroCPU(numThreads=1, synth_pc_base=nop_addr)
system.cpu.clk_domain = system.clk_domain
system.cpu.isa     = [RiscvISA()]
system.cpu.decoder = [RiscvDecoder(isa=system.cpu.isa[0])]
system.cpu.branchPred = BranchPredictor(numThreads=1)
system.cpu.branchPred.conditionalBranchPred = TournamentBP(numThreads=1)
system.cpu.createInterruptController()

system.cpu.workload  = [Process(executable=_spin_elf, cmd=['spin'])]
system.workload      = RiscvEmuLinux()

# L1 caches: avoids DRAM-miss-driven pipeline stalls that could squash
# injected ops before they reach commit.
system.membus = SystemXBar()
system.cpu.icache = Cache(size='32kB', assoc=8,
    tag_latency=2, data_latency=2, response_latency=2, mshrs=4, tgts_per_mshr=20)
system.cpu.dcache = Cache(size='32kB', assoc=8,
    tag_latency=2, data_latency=2, response_latency=2, mshrs=4, tgts_per_mshr=20)
system.cpu.icache.cpu_side = system.cpu.icache_port
system.cpu.icache.mem_side = system.membus.cpu_side_ports
system.cpu.dcache.cpu_side = system.cpu.dcache_port
system.cpu.dcache.mem_side = system.membus.cpu_side_ports
system.system_port   = system.membus.cpu_side_ports
system.mem_ctrl      = SimpleMemory(range=system.mem_ranges[0], latency='10ns')
system.mem_ctrl.port = system.membus.mem_side_ports

root = Root(full_system=False, system=system)
m5.instantiate()

# Warm up: clear TC squash + spin-loop branch predictor training
m5.simulate(100000)
m5.stats.reset()

trace_file = "micro_trace.bin"

# ---- MicroDump -------------------------------------------------------------
print(flush=True)
print("=" * 62, flush=True)
print("  MicroDump: inject ops, serialize to trace", flush=True)
print("=" * 62, flush=True)

system.cpu.enableDump(trace_file)
print(f"  Trace output: m5out/{trace_file}", flush=True)
print(flush=True)

print(f"  [enqueue] MuAdd  x3 = x1 + x2", flush=True)
system.cpu.injectAdd(1, 2, 3)
print(f"  [enqueue] MuMul  x5 = x3 * x4", flush=True)
system.cpu.injectMul(3, 4, 5)

print(flush=True)
print("  Simulating ... (ops drain through rename -> IEW -> commit)", flush=True)
m5.simulate(10000)
system.cpu.disableDump()

trace_path    = os.path.join("m5out", trace_file)
total, active = parse_trace(trace_path)
trace_size    = os.path.getsize(trace_path) if os.path.exists(trace_path) else 0

print(f"  Trace written: {trace_size} bytes  "
      f"({total} records: {active} MicroISA + {total - active} ISA sentinels)", flush=True)

if active == 0:
    print("ERROR: no active records in trace -- injected ops never reached rename", flush=True)
    sys.exit(1)

# ---- MicroPlayback ----------------------------------------------------------
print(flush=True)
print("=" * 62, flush=True)
print("  MicroPlayback: stream trace back through rename", flush=True)
print("=" * 62, flush=True)

if not os.path.exists(trace_path):
    print(f"ERROR: trace file not found at {trace_path}", flush=True)
    sys.exit(1)

print(f"  Replaying {active} MicroISA op(s) from {trace_path}", flush=True)
print(f"  Mode: streaming -- drains at rename-width ops/tick", flush=True)
print(flush=True)

system.cpu.startStreamingPlayback(trace_path)
print("  Simulating ... (trace drains into rename each tick)", flush=True)
m5.simulate(10000)
system.cpu.stopStreamingPlayback()

print(f"  Playback complete.", flush=True)

# ---- Summary ----------------------------------------------------------------
print(flush=True)
print("=" * 62, flush=True)
print("  Summary", flush=True)
print("=" * 62, flush=True)
print(f"  Ops injected & dumped : 2  (MuAdd, MuMul)", flush=True)
print(f"  Trace file            : {trace_size} bytes  "
      f"({active} active + {total - active} sentinel records)", flush=True)
print(f"  Ops replayed          : {active}", flush=True)
print("=" * 62, flush=True)
print(flush=True)
