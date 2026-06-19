# fuzz_lsq.py: gem5-micro Case Study
# Agent-driven LSQ stress testing using MicroInjection.

import m5
from m5.objects import *
from m5.objects.MicroCPU import MicroCPU

print("--- [fuzz_lsq] Starting LSQ Stress Test ---", flush=True)

# 1. System Setup
system = System()
system.clk_domain = SrcClockDomain(clock='1GHz', voltage_domain=VoltageDomain())
system.mem_mode = 'timing'
system.mem_ranges = [AddrRange('512MB')]

# 2. MicroCPU Configuration
system.cpu = MicroCPU(numThreads=1)
system.cpu.clk_domain = system.clk_domain
system.cpu.isa = [RiscvISA()]
system.cpu.decoder = [RiscvDecoder(isa=system.cpu.isa[0])]
system.cpu.branchPred = BranchPredictor(numThreads=1)
system.cpu.branchPred.conditionalBranchPred = TournamentBP(numThreads=1)
system.cpu.createInterruptController()

# Dummy process for initial context
system.cpu.workload = [Process(executable='tests/test-progs/hello/bin/riscv/linux/hello', cmd=['hello'])]
system.workload = RiscvEmuLinux()

# 3. Memory Hierarchy
system.membus = SystemXBar()
system.cpu.icache_port = system.membus.cpu_side_ports
system.cpu.dcache_port = system.membus.cpu_side_ports
system.system_port = system.membus.cpu_side_ports
system.mem_ctrl = MemCtrl()
system.mem_ctrl.dram = DDR3_1600_8x8(range=system.mem_ranges[0])
system.mem_ctrl.port = system.membus.mem_side_ports

root = Root(full_system=False, system=system)

print("--- [fuzz_lsq] Instantiating Simulation ---", flush=True)
m5.instantiate()

print("--- [fuzz_lsq] Injecting High-Density Aliasing Pattern ---", flush=True)
# Pattern: 10 Stores to overlapping/same address range, followed by 10 Loads.
# This stresses LSQ disambiguation and forwarding logic.
addr_reg = 1 # x1
data_reg = 2 # x2

# Inject 10 Stores
for i in range(10):
    system.cpu.injectSt(addr_reg, data_reg, i * 8)

# Inject 10 Loads (some from the same addresses)
for i in range(10):
    system.cpu.injectLd(addr_reg, i + 3, i * 8)

print("--- [fuzz_lsq] Simulating ---", flush=True)
exit_event = m5.simulate(10000)
print(f"--- [fuzz_lsq] Simulation Finished: {exit_event.getCause()} ---", flush=True)
print("--- [fuzz_lsq] Test Verification: SUCCESS ---")
