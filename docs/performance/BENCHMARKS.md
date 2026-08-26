# Performance Benchmarks

This document contains performance benchmarks and optimization guidelines for h2kvm.

## Benchmarking Tools

### Load Testing

The load testing tool measures throughput and latency for parallel VM validation:

```bash
# Basic load test - 100 VMs with 10 parallel
h2kvmctl.vmspawn.benchmarks.load_test \
    --vms 100 \
    --parallel 10 \
    --runs 5 \
    --output results.json

# Scaling test - test different VM counts
h2kvmctl.vmspawn.benchmarks.load_test \
    --mode scaling \
    --parallel 50

# Concurrency test - find optimal parallelism
h2kvmctl.vmspawn.benchmarks.load_test \
    --mode concurrency \
    --vms 100
```

### Profiling

Profile code to identify bottlenecks:

```bash
# Profile async validation
h2kvmctl.vmspawn.benchmarks.profiler async

# Profile sync operations
h2kvmctl.vmspawn.benchmarks.profiler sync

# Compare implementations
h2kvmctl.vmspawn.benchmarks.profiler compare
```

## Performance Metrics

### vmspawn SDK

#### Single VM Validation
- **Start time**: < 2 seconds (systemd-vmspawn initialization)
- **Boot time**: 5-30 seconds (depends on image)
- **Validation checks**: < 1 second per check
- **Total time**: Typically 10-60 seconds per VM

#### Parallel Validation
- **10 VMs (10 parallel)**: ~15-60 seconds total
- **100 VMs (50 parallel)**: ~60-180 seconds total
- **1000 VMs (100 parallel)**: ~300-900 seconds total
- **Throughput**: 5-20 VMs/second (hardware dependent)

## Optimization Guidelines

### Use Async API for Parallel Validation

```python
# Good - Async for parallel
from h2kvm.vmspawn.async_manager import AsyncVMManager

manager = AsyncVMManager(max_parallel=50)
results = await manager.validate_batch(configs)
```

## Best Practices

1. **Use async API** for parallel operations
2. **Tune parallelism** based on hardware
3. **Monitor metrics** to identify bottlenecks
4. **Set timeouts** appropriately for your images
5. **Profile regularly** to catch regressions
