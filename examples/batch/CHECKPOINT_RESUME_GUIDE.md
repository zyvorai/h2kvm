# Batch Checkpoint/Resume Guide

## Overview

The checkpoint/resume feature enables long-running batch conversions to recover from interruptions, crashes, or manual stops. When enabled, the batch orchestrator automatically saves progress after each VM completes, allowing you to resume exactly where you left off.

## Features

- **Automatic Checkpoint Saves**: Progress saved after each VM completion
- **Transparent Resume**: Simply re-run the same command to resume
- **Per-VM Granularity**: Skip already-completed or failed VMs
- **Atomic Writes**: Checkpoint files use temp + replace for safety
- **Progress Tracking**: See how many VMs completed vs. total
- **Automatic Cleanup**: Checkpoints removed on successful completion

## How It Works

### 1. Automatic Checkpoint Creation

When you run a batch conversion with checkpointing enabled (default):

```bash
sudo hyper2kvm --config batch-manifest.json batch
```

The orchestrator automatically:
- Creates a checkpoint directory: `{output_directory}/.checkpoints/`
- Saves checkpoint after each VM: `checkpoint-{batch_id}.json`
- Updates checkpoint with completion status

### 2. Resume from Interruption

If the batch is interrupted (Ctrl+C, crash, power loss, etc.), simply re-run the **same command**:

```bash
sudo hyper2kvm --config batch-manifest.json batch
```

The orchestrator will:
- Detect existing checkpoint
- Load completed and failed VM lists
- Skip already-processed VMs
- Continue with remaining VMs
- Generate final report including all VMs

### 3. Checkpoint File Structure

Checkpoint files are JSON and stored at:

```
{output_directory}/.checkpoints/checkpoint-{batch_id}.json
```

Example checkpoint contents:

```json
{
  "batch_id": "migration-2026-01-22",
  "timestamp": 1737561600.123,
  "timestamp_iso": "2026-01-22T12:00:00Z",
  "completed_vms": [
    "web-server-01",
    "web-server-02",
    "app-server-01"
  ],
  "failed_vms": [
    {
      "vm_id": "database-primary",
      "error": "DiskExtractionError: Failed to extract disk"
    }
  ],
  "total_vms": 5,
  "resume_from": 4,
  "metadata": {}
}
```

## Configuration

### Enable/Disable Checkpointing

Checkpointing is **enabled by default**. To disable:

```python
from hyper2kvm.manifest.batch_orchestrator import BatchOrchestrator

orchestrator = BatchOrchestrator(
    batch_manifest_path="batch.json",
    enable_checkpoint=False,  # Disable checkpointing
)
```

### Custom Checkpoint Directory

By default, checkpoints are stored in `{output_directory}/.checkpoints/`. To customize:

```json
{
  "batch_version": "1.0",
  "shared_config": {
    "output_directory": "/var/lib/hyper2kvm/converted"
  }
}
```

Checkpoint will be saved to:
```
/var/lib/hyper2kvm/converted/.checkpoints/checkpoint-{batch_id}.json
```

### Unique Batch IDs

Each batch must have a unique `batch_id` to avoid checkpoint conflicts:

```json
{
  "batch_metadata": {
    "batch_id": "migration-2026-01-22-production",
    "parallel_limit": 4
  }
}
```

## Usage Examples

### Example 1: Simple Resume

Start batch conversion:
```bash
sudo hyper2kvm --config batch.json batch
```

After processing 3 out of 10 VMs, press Ctrl+C to interrupt.

Resume from checkpoint:
```bash
sudo hyper2kvm --config batch.json batch
```

Output:
```
🚀 Batch Conversion Pipeline
================================================================================
📋 Batch ID: migration-2026-01-22
📦 VMs to process: 10
📂 Resuming from checkpoint: 3 completed, 0 failed
⏩ Skipping 3 already-processed VMs
🔄 Processing VMs sequentially
...
```

### Example 2: Continue on Error with Checkpoint

Batch manifest with `continue_on_error`:

```json
{
  "batch_metadata": {
    "batch_id": "resilient-migration",
    "continue_on_error": true
  },
  "vms": [...]
}
```

If VM 3 fails during conversion:
- VM 3 marked as failed in checkpoint
- Processing continues with VMs 4-10
- If interrupted at VM 7, resume skips VMs 1-7 (3 completed, 1 failed, 3 already done)

### Example 3: Force Restart from Beginning

To ignore checkpoint and restart from scratch:

```bash
# Remove checkpoint file
rm -rf /var/lib/hyper2kvm/converted/.checkpoints/checkpoint-migration-2026-01-22.json

# Re-run batch (will start from VM 1)
sudo hyper2kvm --config batch.json batch
```

Or programmatically:

```python
from hyper2kvm.manifest.checkpoint_manager import CheckpointManager

manager = CheckpointManager(
    checkpoint_dir="/var/lib/hyper2kvm/converted/.checkpoints",
    batch_id="migration-2026-01-22",
)
manager.reset()  # Delete checkpoint
```

## Monitoring Progress

### Check Progress Percentage

```python
from hyper2kvm.manifest.checkpoint_manager import CheckpointManager

manager = CheckpointManager(
    checkpoint_dir="/var/lib/hyper2kvm/converted/.checkpoints",
    batch_id="migration-2026-01-22",
)

if manager.has_checkpoint():
    progress = manager.get_progress_percentage()
    print(f"Progress: {progress:.1f}%")
```

### List Completed VMs

```python
completed = manager.get_completed_vm_ids()
print(f"Completed VMs: {completed}")

failed = manager.get_failed_vm_ids()
print(f"Failed VMs: {failed}")
```

## Advanced Features

### Checkpoint Metadata

Add custom metadata to checkpoints:

```python
orchestrator = BatchOrchestrator("batch.json")

# Custom metadata saved with checkpoint
metadata = {
    "operator": "admin@example.com",
    "migration_phase": "testing",
}

# Metadata automatically included in checkpoint saves
```

### Manual Checkpoint Management

```python
from hyper2kvm.manifest.checkpoint_manager import CheckpointManager

manager = CheckpointManager(
    checkpoint_dir="/checkpoints",
    batch_id="my-batch",
)

# Check if VM should be skipped
if manager.should_skip_vm("web-server-01"):
    print("VM already processed, skipping")

# Get checkpoint data
if manager.has_checkpoint():
    data = manager.load_checkpoint()
    print(f"Resume from index: {data['resume_from']}")

# Cleanup checkpoint
manager.cleanup()
```

## Error Handling

### Checkpoint Load Failures

If checkpoint is corrupted:
- Error logged: `CheckpointError: Invalid checkpoint JSON`
- Batch continues as if no checkpoint exists
- Fresh checkpoint created

### Batch ID Mismatch

If checkpoint batch_id doesn't match manifest:
- Warning logged
- Checkpoint data still loaded (for debugging)
- Proceed with caution or reset checkpoint

### Checkpoint Directory Errors

If checkpoint directory cannot be created:
- `CheckpointError` raised
- Batch conversion stops
- Fix directory permissions or specify valid path

## Best Practices

1. **Use Descriptive Batch IDs**: Include date, environment, or purpose
   ```json
   "batch_id": "prod-migration-2026-01-22"
   ```

2. **Enable continue_on_error**: For large batches, continue despite failures
   ```json
   "continue_on_error": true
   ```

3. **Monitor Checkpoints**: Check `.checkpoints/` directory periodically

4. **Backup Checkpoints**: For critical migrations, backup checkpoint files

5. **Clean Up Old Checkpoints**: Remove checkpoints from completed batches
   ```bash
   find /var/lib/hyper2kvm/converted/.checkpoints -mtime +30 -delete
   ```

## Security Considerations

- **Atomic Writes**: Checkpoints use temp file + replace to prevent corruption
- **Safe Paths**: Batch IDs sanitized to prevent path traversal
- **Permissions**: Checkpoint directory inherits output directory permissions
- **No Sensitive Data**: Checkpoints contain only VM IDs and status

## Troubleshooting

### Checkpoint Not Created

Check:
- Output directory is writable
- Checkpointing enabled (default: true)
- Batch ID is valid (alphanumeric, hyphens, underscores)

### Resume Not Working

Verify:
- Using same batch manifest file
- Same `batch_id` in manifest
- Checkpoint file exists in expected location

### Unexpected VM Skips

Check checkpoint file:
```bash
cat /var/lib/hyper2kvm/converted/.checkpoints/checkpoint-{batch_id}.json
```

Look for VM ID in `completed_vms` or `failed_vms` arrays.

## Performance Impact

- **Overhead**: ~10-50ms per checkpoint save (negligible)
- **Disk Usage**: ~1-2KB per checkpoint file
- **Memory**: Minimal (checkpoint data cached in memory)
- **Atomicity**: Guaranteed via temp file + replace pattern

## Related Documentation

- [Batch Migration Guide](../../docs/Batch-Migration-Features-Guide.md)
- [Batch Manifest Schema](./batch-simple.json)
- [Error Handling](./batch-with-profiles.yaml)

## Example Files

- [batch-with-checkpoint.json](./batch-with-checkpoint.json) - Complete example with annotations
- [batch-simple.json](./batch-simple.json) - Basic batch without checkpointing

## API Reference

### CheckpointManager

```python
class CheckpointManager:
    def __init__(
        self,
        checkpoint_dir: Path | str,
        batch_id: str,
        logger: logging.Logger | None = None,
    ):
        """Initialize checkpoint manager."""

    def has_checkpoint(self) -> bool:
        """Check if checkpoint exists."""

    def load_checkpoint(self) -> dict[str, Any]:
        """Load checkpoint data."""

    def save_checkpoint(
        self,
        completed_vms: list[str],
        failed_vms: list[dict[str, Any]] | None = None,
        total_vms: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Save checkpoint state."""

    def get_completed_vm_ids(self) -> set[str]:
        """Get set of completed VM IDs."""

    def get_failed_vm_ids(self) -> set[str]:
        """Get set of failed VM IDs."""

    def should_skip_vm(self, vm_id: str) -> bool:
        """Check if VM should be skipped."""

    def cleanup(self) -> None:
        """Remove checkpoint file."""

    def reset(self) -> None:
        """Force restart from beginning."""

    def get_progress_percentage(self) -> float:
        """Calculate progress percentage."""
```

## Conclusion

The checkpoint/resume feature makes batch migrations resilient to interruptions, enabling reliable long-running conversions without manual state tracking. Simply re-run the same command to resume from the last completed VM.

For questions or issues, see the [main documentation](../../docs/Batch-Migration-Features-Guide.md) or file an issue at https://github.com/anthropics/hyper2kvm/issues.
