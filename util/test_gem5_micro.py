import m5
from m5.objects import *
from m5.objects.MicroCPU import MicroCPU
import os
import sys

# 1. Setup a minimal system for gem5-micro verification
system = System()
system.clk_domain = SrcClockDomain(clock='1GHz', voltage_domain=VoltageDomain())
system.mem_mode = 'timing'
system.mem_ranges = [AddrRange('512MB')]

# 2. CPU configuration (MicroCPU)
# Specifically using 1 thread for micro-op injection testing
system.cpu = MicroCPU(numThreads=1)
system.cpu.clk_domain = system.clk_domain
system.cpu.isa = [RiscvISA()]
system.cpu.decoder = [RiscvDecoder(isa=system.cpu.isa[0])]

# Explicitly override BP to avoid proxy issues with Vector2d stats
system.cpu.branchPred = BranchPredictor(numThreads=1)
system.cpu.branchPred.conditionalBranchPred = TournamentBP(numThreads=1)

# Essential for RiscvO3CPU
system.cpu.createInterruptController()

# Set up a dummy process so the CPU has something to "fetch" if it wants
# but we will mainly focus on the injected instructions.
system.cpu.workload = [Process(executable='tests/test-progs/hello/bin/riscv/linux/hello', cmd=['hello'])]
system.workload = RiscvEmuLinux()

# 3. Memory & Bus
system.membus = SystemXBar()
system.cpu.icache_port = system.membus.cpu_side_ports
system.cpu.dcache_port = system.membus.cpu_side_ports
system.system_port = system.membus.cpu_side_ports

system.mem_ctrl = MemCtrl()
system.mem_ctrl.dram = DDR3_1600_8x8(range=system.mem_ranges[0])
system.mem_ctrl.port = system.membus.mem_side_ports

# Root object
root = Root(full_system=False, system=system)

# Instantiate the simulation
print("--- [Gem5Micro] Instantiating simulation ---", flush=True)
m5.instantiate()

# 4. Phase 1: Injection & Damping
trace_file = "micro_trace.bin"
print(f"--- [Gem5Micro] Phase 1: MicroInjection & MicroDump to {trace_file} ---", flush=True)

# Enable trace dumping
system.cpu.enableDump(trace_file)

# Inject a test sequence:
# x3 = x1 + x2
# x5 = x3 * x4
print("Injected Add(rs1=1, rs2=2, rd=3)", flush=True)
system.cpu.injectAdd(1, 2, 3)
print("Injected Mul(rs1=3, rs2=4, rd=5)", flush=True)
system.cpu.injectMul(3, 4, 5)

print("Simulating sequence for 10000 ticks...", flush=True)
exit_event = m5.simulate(10000)
print(f"Exited at tick {m5.curTick()} because {exit_event.getCause()}")

# Close the dump stream
system.cpu.disableDump()

# 5. Phase 2: Verification of Trace File
if os.path.exists(os.path.join("m5out", trace_file)):
    full_path = os.path.join("m5out", trace_file)
    size = os.path.getsize(full_path)
    print(f"--- [Gem5Micro] Verification: Trace file {full_path} created ({size} bytes) ---", flush=True)
    
    if size == 18:
        print("SUCCESS: Trace file size is correct (2 instructions @ 9 bytes each).")
    else:
        print(f"WARNING: Unexpected trace file size ({size} bytes). Expected 18.")
else:
    print(f"ERROR: Trace file {trace_file} not found in m5out!")

print("--- [Gem5Micro] Verification script finished ---")
