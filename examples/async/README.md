# Async Examples

This directory contains examples demonstrating asynchronous/parallel VM migration for improved performance.

## Available Examples

- **`async_batch_migration_example.py`** - Parallel VM migrations with async/await
  - Export multiple VMs concurrently (3-5x speedup)
  - Automatic concurrency limiting (default: 5 parallel VMs)
  - Progress tracking for each VM
  - Automatic retry on failures
  - Real-time statistics

- **`async_with_tui_example.py`** - Async migrations with TUI integration
  - Combines async performance with interactive dashboard
  - Real-time progress visualization
  - Multi-VM status monitoring

## Features

- **3-5x speedup** for batch migrations
- Automatic concurrency control
- Per-VM progress tracking
- Failure isolation (one VM failure doesn't stop others)
- Resource management (automatic rate limiting)

## Requirements

```bash
pip install 'hyper2kvm[async]'
```

## Usage

```bash
# Basic async batch migration
python async_batch_migration_example.py

# With TUI dashboard
python async_with_tui_example.py
```

## Performance Tips

- Default concurrency: 5 VMs in parallel
- Adjust based on network/storage: set `max_concurrent_vms`
- Monitor resource usage during large batches
- Use SSD storage for best performance

## Documentation

- [docs/guides/Batch-Migration-Features-Guide.md](../../docs/guides/Batch-Migration-Features-Guide.md)
- [docs/guides/Batch-Migration-Quick-Reference.md](../../docs/guides/Batch-Migration-Quick-Reference.md)
