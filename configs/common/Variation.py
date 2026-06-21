# Copyright (2026) Google, Inc.
# All rights reserved.

import random

def perturb_fu_latencies(cpu, sigma=0.1):
    """
    Perturb the latencies of functional units in the CPU using a Gaussian distribution.
    
    :param cpu: The CPU SimObject to perturb.
    :param sigma: The standard deviation as a fraction of the baseline latency.
    """
    if not hasattr(cpu, 'fuPool'):
        return

    # Iterate through all functional units in the pool
    for fu in cpu.fuPool.FUList:
        for op in fu.opList:
            baseline = int(op.opLat)
            # Perturb and round to nearest integer (minimum 1 cycle)
            variation = random.gauss(0, sigma * baseline)
            new_lat = max(1, round(baseline + variation))
            op.opLat = new_lat

def perturb_cache_parameters(cache, sigma_lat=0.1, sigma_size=0.0):
    """
    Perturb cache parameters like latency.
    
    :param cache: The Cache SimObject to perturb.
    :param sigma_lat: Standard deviation for latency variation.
    :param sigma_size: Standard deviation for size variation (rarely used).
    """
    if hasattr(cache, 'tag_latency'):
        baseline_tag = int(cache.tag_latency)
        cache.tag_latency = max(1, round(random.gauss(baseline_tag, sigma_lat * baseline_tag)))
    
    if hasattr(cache, 'data_latency'):
        baseline_data = int(cache.data_latency)
        cache.data_latency = max(1, round(random.gauss(baseline_data, sigma_lat * baseline_data)))
    
    if hasattr(cache, 'response_latency'):
        baseline_resp = int(cache.response_latency)
        cache.response_latency = max(1, round(random.gauss(baseline_resp, sigma_lat * baseline_resp)))

def apply_variation_model(system, cpu_sigma=0.1, cache_sigma=0.05):
    """
    Apply silicon variation model to the entire system.
    """
    cpus = system.cpu if isinstance(system.cpu, list) else [system.cpu]
    for cpu in cpus:
        perturb_fu_latencies(cpu, cpu_sigma)
        if hasattr(cpu, 'icache'):
            perturb_cache_parameters(cpu.icache, cache_sigma)
        if hasattr(cpu, 'dcache'):
            perturb_cache_parameters(cpu.dcache, cache_sigma)
    
    if hasattr(system, 'l2'):
        perturb_cache_parameters(system.l2, cache_sigma)
