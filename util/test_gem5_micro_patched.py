# test_gem5_micro_patched.py — gem5-micro hello world demo with patched ELF
# Demonstrates patch_elf_for_microisa by patching a pre-compiled RISC-V hello
# program to add the NOP page, and executing micro-ops on top of it.

import os
import struct
import sys
import tempfile
import m5
from m5.objects import *
from m5.objects.MicroCPU import MicroCPU

# Include util dir to import shared micro_elf library
sys.path.append(os.path.dirname(__file__))
from micro_elf import patch_elf_for_microisa

RECORD_SIZE = 12  # 1B opcode + 8B offset + 1B rd + 1B rs1 + 1B rs2


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


# ---- ELF Patching Phase ----------------------------------------------------
print(flush=True)
print("==============================================================", flush=True)
# Locate and patch the pre-compiled hello binary
src_hello = 'tests/test-progs/hello/bin/riscv/linux/hello'
dst_hello = tempfile.mktemp(suffix='_hello_patched.elf')

print(f"  Patching source binary: {src_hello}", flush=True)
entry_addr, nop_addr = patch_elf_for_microisa(src_hello, dst_hello, arch='riscv')
print(f"  Patched executable written to: {dst_hello}", flush=True)
print(f"  Entry Point Address: {hex(entry_addr)}", flush=True)
print(f"  NOP Landing Page:    {hex(nop_addr)}", flush=True)
print("==============================================================", flush=True)
print(flush=True)


# ---- System setup ----------------------------------------------------------
system = System()
system.clk_domain = SrcClockDomain(clock='1GHz', voltage_domain=VoltageDomain())
system.mem_mode   = 'timing'
system.mem_ranges = [AddrRange('512MB')]

# Initialize MicroCPU with the dynamically resolved nop_addr
system.cpu = MicroCPU(numThreads=1, synth_pc_base=nop_addr)
system.cpu.clk_domain = system.clk_domain
system.cpu.isa     = [RiscvISA()]
system.cpu.decoder = [RiscvDecoder(isa=system.cpu.isa[0])]
system.cpu.branchPred = BranchPredictor(numThreads=1)
system.cpu.branchPred.conditionalBranchPred = TournamentBP(numThreads=1)
system.cpu.createInterruptController()

# Set workload to our patched hello executable
system.cpu.workload  = [Process(executable=dst_hello, cmd=['hello'])]
system.workload      = RiscvEmuLinux()

# Memory and L1 Caches setup
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

# ---- Execution phase selection ---------------------------------------------
import argparse
parser = argparse.ArgumentParser(description="gem5-micro hello world demo with patched ELF")
parser.add_argument('--playback', action='store_true', help="Run playback only using existing trace")
args, unknown = parser.parse_known_args()

trace_file = "micro_patched_trace.bin"
trace_path = os.path.join("m5out", trace_file)

if args.playback:
    # ---- Playback Mode (Rerun program and stream recorded trace) -----------
    if not os.path.exists(trace_path):
        print(f"Error: Trace file not found at {trace_path}. Run dump phase first.", flush=True)
        if os.path.exists(dst_hello):
            os.remove(dst_hello)
        sys.exit(1)

    total, active = parse_trace(trace_path)
    print("==============================================================", flush=True)
    print("  MicroPlayback: Replaying from Patched Hello Trace (Fresh Run)", flush=True)
    print("==============================================================", flush=True)
    print(f"  Replaying {active} MicroISA op(s) from {trace_path}", flush=True)
    print(flush=True)

    # Warm up: run the binary's initial startup logic for 100,000 ticks,
    # matching the dump phase timing.
    print("  Warming up pipeline...", flush=True)
    m5.simulate(100000)

    system.cpu.startStreamingPlayback(trace_path)
    print("  Simulating program execution with playback...", flush=True)
    exit_event = m5.simulate()
    system.cpu.stopStreamingPlayback()
    print(f"  Simulation exited: {exit_event.getCause()}", flush=True)
    print("  Playback complete.", flush=True)
    print("==============================================================", flush=True)
else:
    # ---- Dump Mode (Run program, inject micro-ops, and dump trace) ---------
    print("==============================================================", flush=True)
    print("  Running Simulation & Injecting Ops Over Patched Hello Binary", flush=True)
    print("==============================================================", flush=True)

    # Warm up: run the binary's initial startup logic for 100,000 ticks
    print("  Warming up pipeline...", flush=True)
    m5.simulate(100000)

    # Enable trace dumping
    system.cpu.enableDump(trace_file)

    # Inject micro-ops: x0 = x0 + x0, x0 = x0 * x0
    print("  [enqueue] Injected MuAdd(rs1=0, rs2=0, rd=0)", flush=True)
    system.cpu.injectAdd(0, 0, 0)
    print("  [enqueue] Injected MuMul(rs1=0, rs2=0, rd=0)", flush=True)
    system.cpu.injectMul(0, 0, 0)

    # Simulate to let the injected instructions run and let the program execute print
    print("  Simulating program execution...", flush=True)
    exit_event = m5.simulate()
    print(f"  Simulation exited: {exit_event.getCause()}", flush=True)

    # Close dump
    system.cpu.disableDump()
    print("==============================================================", flush=True)
    print(flush=True)

    total, active = parse_trace(trace_path)
    trace_size    = os.path.getsize(trace_path) if os.path.exists(trace_path) else 0
    print(f"  Trace file written: {trace_size} bytes ({active} active records)", flush=True)
    print("==============================================================", flush=True)

# Clean up temporary patched executable
if os.path.exists(dst_hello):
    os.remove(dst_hello)

