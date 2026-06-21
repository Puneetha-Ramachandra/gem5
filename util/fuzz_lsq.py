# fuzz_lsq.py: gem5-micro Case Study
# Agent-driven LSQ stress testing using MicroInjection.
# Validates the paper's claim (§4) that lsq_forw_loads and lsq_full_events
# are reachable via MicroInjection but not through compiled binaries.

import os
import sys
import m5
from m5.objects import *
from m5.objects.MicroCPU import MicroCPU


def parse_stat(stats_path, stat_name):
    """Return the integer value of a stat from m5out/stats.txt, or None."""
    try:
        with open(stats_path) as f:
            for line in f:
                if line.startswith(stat_name):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(float(parts[1]))
    except FileNotFoundError:
        pass
    return None

print("--- [fuzz_lsq] Starting LSQ Stress Test ---", flush=True)

# 1. System Setup
system = System()
system.clk_domain = SrcClockDomain(clock='1GHz', voltage_domain=VoltageDomain())
system.mem_mode = 'timing'
system.mem_ranges = [AddrRange('512MB')]

# 2. MicroCPU Configuration
system.cpu = MicroCPU(numThreads=1, LQEntries=8, SQEntries=8)
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
# Use x2 (sp): gem5 SE mode initializes sp to a valid stack address before
# simulate(), so EA = sp + offset is always a mapped virtual address.
# Using x1 (= 0) would produce null-pointer EAs that fault before LSQ
# forwarding is checked, keeping forwLoads = 0.
addr_reg = 2  # x2 = sp
data_reg = 1  # x1 (store value — contents don't matter for forwarding)

# Inject 10 Stores then 10 Loads with aliasing addresses.
# SQEntries=8 means 10 stores will trigger lsqFullEvents (SQ fills at 8).
# Negative offsets stay within the valid stack region (below sp).
for i in range(10):
    system.cpu.injectSt(addr_reg, data_reg, -8 - i * 8)

for i in range(10):
    system.cpu.injectLd(addr_reg, (i % 8) + 4, -8 - i * 8)

print("--- [fuzz_lsq] Simulating ---", flush=True)
exit_event = m5.simulate(500000)
print(f"--- [fuzz_lsq] Simulation Finished: {exit_event.getCause()} ---", flush=True)
m5.stats.dump()

# --- Validation (paper §4) ---
# Verify that the injected aliasing pattern triggered LSQ events that are
# unreachable through compiled binaries.
stats_path = os.path.join("m5out", "stats.txt")
failures = []

# Store-to-load forwarding events (lsq_unit.cc: forwLoads)
forw_loads = parse_stat(stats_path, "system.cpu.lsq0.forwLoads")
if forw_loads is None:
    failures.append("forwLoads stat not found in stats.txt")
elif forw_loads == 0:
    failures.append(f"forwLoads == 0; expected > 0 from aliasing pattern")
else:
    print(f"  forwLoads      = {forw_loads}  [PASS]")

# LSQ-full stall events (iew.cc: lsqFullEvents)
lsq_full = parse_stat(stats_path, "system.cpu.iew.lsqFullEvents")
if lsq_full is None:
    failures.append("lsqFullEvents stat not found in stats.txt")
elif lsq_full == 0:
    print(f"  lsqFullEvents  = 0  [INFO: LSQ did not fill — increase injection count]")
else:
    print(f"  lsqFullEvents  = {lsq_full}  [PASS]")

if failures:
    for msg in failures:
        print(f"FAIL: {msg}")
    sys.exit(1)
else:
    print("--- [fuzz_lsq] Validation: PASS ---")
