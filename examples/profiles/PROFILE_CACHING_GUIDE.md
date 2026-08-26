# Profile Caching Guide

## Overview

Profile caching improves performance for batch conversions by avoiding redundant file I/O and YAML parsing when the same profiles are used across multiple VMs.

## Features

- **Built-in Profile Caching**: Loaded once, reused indefinitely
- **Custom Profile Caching**: Cached with automatic invalidation on file modification
- **Thread-Safe**: Safe for parallel batch processing
- **Cache Statistics**: Monitor hits, misses, and hit rates
- **Automatic Invalidation**: Custom profiles automatically invalidated when files change
- **Optional Disabling**: Can be disabled for testing or debugging

## How It Works

### 1. Global Cache

By default, all `ProfileLoader` instances share a global cache:

```python
from hyper2kvm.profiles import ProfileLoader

# Both loaders share the same global cache
loader1 = ProfileLoader()
loader2 = ProfileLoader()

assert loader1.cache is loader2.cache  # True
```

### 2. Cache Keys

Profiles are cached using keys:
- Built-in profiles: `profile_name` (e.g., "production")
- Custom profiles: `custom_path:profile_name` (e.g., "/profiles:custom")

### 3. Cache Validation

**Built-in profiles**: Never expire (cached indefinitely)

**Custom profiles**: Automatically invalidated when:
- File modification time (mtime) changes
- File is deleted

Example:
```python
loader = ProfileLoader()

# First load - reads from disk
profile1 = loader.load_profile("custom", custom_profile_path="/profiles")

# Second load - uses cache
profile2 = loader.load_profile("custom", custom_profile_path="/profiles")

# Modify /profiles/custom.yaml
# ...

# Third load - cache invalidated, reads from disk again
profile3 = loader.load_profile("custom", custom_profile_path="/profiles")
```

## Usage

### Basic Usage

```python
from hyper2kvm.profiles import ProfileLoader

# Create loader with caching enabled (default)
loader = ProfileLoader()

# Load profiles multiple times
for i in range(100):
    profile = loader.load_profile("production")
    # Only first load hits disk, rest use cache

# Check statistics
stats = loader.get_cache_statistics()
print(f"Hit rate: {stats['hit_rate_percent']:.1f}%")
print(f"Hits: {stats['hits']}, Misses: {stats['misses']}")
```

### Disable Caching

```python
from hyper2kvm.profiles import ProfileLoader

# Disable caching for testing or debugging
loader = ProfileLoader(enable_cache=False)

# Each load reads from disk
profile1 = loader.load_profile("production")
profile2 = loader.load_profile("production")  # Re-reads from disk
```

### Custom Cache Instance

```python
from hyper2kvm.profiles import ProfileLoader, ProfileCache

# Create custom cache with specific configuration
custom_cache = ProfileCache(enabled=True)

# Use custom cache
loader = ProfileLoader(cache=custom_cache)
```

### Cache Statistics

```python
from hyper2kvm.profiles import ProfileLoader

loader = ProfileLoader()

# Load profiles
for profile_name in ["production", "testing", "minimal"]:
    loader.load_profile(profile_name)
    loader.load_profile(profile_name)  # Cache hit

# Get detailed statistics
stats = loader.get_cache_statistics()

print(f"Cache enabled: {stats['enabled']}")
print(f"Cache size: {stats['size']}")
print(f"Total requests: {stats['total_requests']}")
print(f"Hits: {stats['hits']}")
print(f"Misses: {stats['misses']}")
print(f"Invalidations: {stats['invalidations']}")
print(f"Hit rate: {stats['hit_rate_percent']:.1f}%")

# Per-profile statistics
for profile_name, entry_stats in stats['entries'].items():
    print(f"\n{profile_name}:")
    print(f"  Accesses: {entry_stats['accesses']}")
    print(f"  Age: {entry_stats['age_seconds']:.1f}s")
    print(f"  Source: {entry_stats['source']}")
```

### Log Statistics

```python
from hyper2kvm.profiles import ProfileLoader

loader = ProfileLoader()

# Load profiles...

# Log cache statistics
loader.log_cache_statistics()
# Output:
# INFO: Profile cache statistics: 5 hits, 3 misses, 62.5% hit rate, 3 cached profiles
# DEBUG:   - production: 2 accesses, 12.3s old, source=builtin
# DEBUG:   - testing: 2 accesses, 11.8s old, source=builtin
# DEBUG:   - custom: 1 accesses, 8.5s old, source=custom.yaml
```

## Batch Conversion Performance

For batch conversions with many VMs using the same profile, caching provides significant performance improvements:

```python
from hyper2kvm.manifest.batch_orchestrator import BatchOrchestrator
from hyper2kvm.profiles import ProfileLoader

# Create loader with caching enabled
loader = ProfileLoader(enable_cache=True)

# Run batch conversion
# All VMs using the same profile will benefit from caching
orchestrator = BatchOrchestrator("batch.json")
orchestrator.run()

# Check how much caching helped
loader.log_cache_statistics()
```

### Performance Comparison

**Without caching** (100 VMs, same profile):
- Profile loads: 100
- Disk reads: 100
- YAML parsing: 100
- Time: ~1000ms (10ms per load)

**With caching** (100 VMs, same profile):
- Profile loads: 100
- Disk reads: 1 (first load)
- YAML parsing: 1 (first load)
- Cache hits: 99
- Time: ~20ms (10ms first load + 0.1ms×99 cache hits)

**Speedup**: ~50x faster for profile loading

## Cache Invalidation

### Automatic Invalidation

Custom profiles are automatically invalidated when files change:

```python
from hyper2kvm.profiles import ProfileLoader
from pathlib import Path
import time

loader = ProfileLoader()

# Load custom profile
profile1 = loader.load_profile("custom", custom_profile_path="/profiles")

# Modify the file
custom_file = Path("/profiles/custom.yaml")
time.sleep(0.1)  # Ensure mtime changes
custom_file.write_text("...")  # File modified

# Next load detects change and reloads
profile2 = loader.load_profile("custom", custom_profile_path="/profiles")
# Cache was invalidated and profile reloaded from disk
```

### Manual Invalidation

```python
from hyper2kvm.profiles import get_global_cache

# Get global cache
cache = get_global_cache()

# Invalidate specific profile
cache.invalidate("production")

# Clear entire cache
cache.clear()
```

### Reset Global Cache

```python
from hyper2kvm.profiles import reset_global_cache

# Reset global cache (useful for testing)
reset_global_cache()
```

## Advanced Usage

### Thread Safety

The cache is thread-safe for parallel batch processing:

```python
from hyper2kvm.profiles import ProfileLoader
import concurrent.futures

loader = ProfileLoader()

def load_profile_multiple_times():
    for _ in range(100):
        loader.load_profile("production")

# Multiple threads can safely use the same loader
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
    futures = [executor.submit(load_profile_multiple_times) for _ in range(4)]
    concurrent.futures.wait(futures)

# Cache handles concurrent access safely
stats = loader.get_cache_statistics()
print(f"Total requests: {stats['total_requests']}")
```

### Cache Statistics API

```python
stats = loader.get_cache_statistics()

# Available fields:
# - enabled (bool): Whether caching is enabled
# - size (int): Number of cached profiles
# - hits (int): Number of cache hits
# - misses (int): Number of cache misses
# - invalidations (int): Number of invalidations
# - total_requests (int): Total cache requests
# - hit_rate_percent (float): Cache hit rate percentage
# - entries (dict): Per-profile statistics
#   - accesses (int): Number of times accessed
#   - age_seconds (float): Age in seconds
#   - source (str): "builtin" or filename
```

## Best Practices

1. **Enable caching for production**: Always use caching in production batch conversions
   ```python
   loader = ProfileLoader(enable_cache=True)  # Default
   ```

2. **Disable caching for tests**: Disable caching in tests to avoid side effects
   ```python
   loader = ProfileLoader(enable_cache=False)
   # Or reset global cache between tests
   reset_global_cache()
   ```

3. **Monitor cache performance**: Log statistics after large batches
   ```python
   loader.log_cache_statistics()
   ```

4. **Use global cache for batch**: Share cache across all VMs in a batch
   ```python
   # All VMs will share the same global cache
   loader = ProfileLoader()  # Uses global cache
   ```

5. **Custom cache for isolation**: Use custom cache when you need isolation
   ```python
   custom_cache = ProfileCache()
   loader = ProfileLoader(cache=custom_cache)
   ```

## Troubleshooting

### Cache Not Working

Check if caching is enabled:
```python
stats = loader.get_cache_statistics()
if not stats['enabled']:
    print("Caching is disabled!")
```

### Low Hit Rate

Check cache statistics to diagnose:
```python
stats = loader.get_cache_statistics()
print(f"Hit rate: {stats['hit_rate_percent']:.1f}%")

if stats['invalidations'] > 0:
    print(f"Cache invalidations: {stats['invalidations']}")
    print("Custom profile files may be changing frequently")
```

### Stale Cache

If you suspect stale cache entries:
```python
# Manually invalidate specific profile
get_global_cache().invalidate("production")

# Or clear entire cache
get_global_cache().clear()

# Or reset global cache completely
reset_global_cache()
```

## Performance Metrics

### Overhead

**Cache hit**: ~0.1ms (in-memory lookup + dict copy)

**Cache miss + store**: ~10ms (disk I/O + YAML parsing + cache store)

**Invalidation check**: ~0.05ms (mtime comparison)

### Memory Usage

**Per cached profile**: ~1-5KB (depending on profile complexity)

**Cache metadata**: ~500 bytes per entry

**Total**: ~2-6KB per cached profile

### Scalability

The cache scales well for typical workloads:
- **100 profiles**: ~200-600KB memory
- **1000 profiles**: ~2-6MB memory (unlikely scenario)

## Example: Batch with Caching

```python
from hyper2kvm.manifest.batch_orchestrator import BatchOrchestrator
from hyper2kvm.profiles import ProfileLoader, get_global_cache

# Enable caching (default)
loader = ProfileLoader(enable_cache=True)

# Run batch conversion
orchestrator = BatchOrchestrator("batch-with-profiles.json")
report = orchestrator.run()

# Check cache effectiveness
cache_stats = get_global_cache().get_statistics()

print(f"\nProfile Cache Performance:")
print(f"  Total profile loads: {cache_stats['total_requests']}")
print(f"  Cache hits: {cache_stats['hits']}")
print(f"  Cache misses: {cache_stats['misses']}")
print(f"  Hit rate: {cache_stats['hit_rate_percent']:.1f}%")
print(f"  Cached profiles: {cache_stats['size']}")

# Log detailed statistics
get_global_cache().log_statistics()
```

## Related Documentation

- [Migration Profiles Guide](../../hyper2kvm/profiles/README.md)
- [Batch Migration Guide](../../docs/Batch-Migration-Features-Guide.md)
- [ProfileCache API Reference](../../hyper2kvm/profiles/profile_cache.py)

## Conclusion

Profile caching provides significant performance improvements for batch conversions with minimal overhead. By default, caching is enabled and shared globally across all ProfileLoader instances, providing optimal performance out of the box.

For most use cases, no configuration is needed - caching works automatically. For advanced scenarios, the cache can be customized, monitored, and controlled as needed.
