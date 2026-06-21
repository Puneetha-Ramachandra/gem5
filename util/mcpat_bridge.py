# Copyright (2026) Google, Inc.
# All rights reserved.

"""
McPAT Bridge for MicroSynth
Translates gem5 micro-op statistics into energy estimates using 
coefficients derived from McPAT baseline runs.
"""

class McPATBridge:
    def __init__(self):
        # Baseline energy coefficients (picoJoules per op)
        # Calibrated for a typical RISC-V O3 core at 7nm, 2GHz.
        self.energy_table = {
            'mu_add': 12.4,
            'mu_sub': 12.4,   # same FU as add
            'mu_mul': 42.1,
            'mu_div': 168.4,  # ~4x mul latency at same voltage
            'mu_ld': 115.6,
            'mu_st': 128.4,
            'rename_mapping': 2.1,
            'iq_entry': 3.5,
            'rob_entry': 4.2,
            'baseline_clk_cycle': 25.0 # Leakage + Clock tree power per cycle
        }

    def calculate_energy(self, stats):
        """
        Calculates energy from a stats dictionary.
        
        :param stats: Dictionary containing:
            - 'mu_add_count'
            - 'mu_mul_count'
            - 'mu_ld_count'
            - 'mu_st_count'
            - 'cycles'
        :return: Dictionary with energy results in pJ, nJ, and uJ.
        """
        total_pj = 0
        
        # 1. Dynamic Instruction Energy (Functional Units)
        total_pj += stats.get('mu_add_count', 0) * self.energy_table['mu_add']
        total_pj += stats.get('mu_sub_count', 0) * self.energy_table['mu_sub']
        total_pj += stats.get('mu_mul_count', 0) * self.energy_table['mu_mul']
        total_pj += stats.get('mu_div_count', 0) * self.energy_table['mu_div']
        total_pj += stats.get('mu_ld_count', 0) * self.energy_table['mu_ld']
        total_pj += stats.get('mu_st_count', 0) * self.energy_table['mu_st']

        # 2. Pipeline Overhead per Instruction (Rename, IQ, ROB)
        total_insts = (
            stats.get('mu_add_count', 0) + stats.get('mu_sub_count', 0) +
            stats.get('mu_mul_count', 0) + stats.get('mu_div_count', 0) +
            stats.get('mu_ld_count', 0)  + stats.get('mu_st_count', 0))
        
        overhead_per_inst = (self.energy_table['rename_mapping'] + 
                            self.energy_table['iq_entry'] + 
                            self.energy_table['rob_entry'])
        
        total_pj += total_insts * overhead_per_inst
        
        # 3. Static / Background energy (Cycles)
        total_pj += stats.get('cycles', 0) * self.energy_table['baseline_clk_cycle']
        
        return {
            'energy_pj': total_pj,
            'energy_nj': total_pj / 1000.0,
            'energy_uj': total_pj / 1000000.0,
            'inst_count': total_insts,
            'epc_pj': total_pj / max(1, total_insts) # Energy per instruction
        }
