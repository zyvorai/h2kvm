# Workflow Daemon - 3-Directory Processing

The workflow daemon provides a production-ready, observable VM conversion pipeline with clear state separation.

## Features

- **Clear State Tracking**: Jobs move through well-defined directories
- **Config File Support**: Drop `.yaml` or `.json` configs for custom conversion settings
- **Batch Processing**: Process multiple VMs with a single config file
- **Error Handling**: Failed jobs moved to `failed/` with detailed error context
- **Concurrent Processing**: Configurable worker pool for parallel conversions

## Directory Structure

```
workflow_dir/
├── to_be_processed/   # Drop zone - place VM disk files or job configs here
├── processing/        # Active jobs being converted
├── processed/         # Successfully completed jobs (organized by date)
│   └── 2026-01-24/   # Dated subdirectories
│       ├── vm1.vmdk
│       └── vm1.vmdk.meta.json
└── failed/            # Failed jobs with error details
    └── 2026-01-24/
        ├── vm2.vhd
        └── vm2.vhd.error.json
```

## Quick Start

### 1. Start the Workflow Daemon

```bash
# Using config file
sudo hyper2kvm --config workflow-daemon.yaml

# Or via command line
sudo hyper2kvm daemon \
  --workflow-mode \
  --workflow-dir /var/lib/hyper2kvm/workflow \
  --output-dir /var/lib/hyper2kvm/output \
  --max-concurrent-jobs 3
```

### 2. Drop VM Disk Files

Simply copy VM disk files into `to_be_processed/`:

```bash
# VMware
cp my-vm.vmdk /var/lib/hyper2kvm/workflow/to_be_processed/

# Hyper-V
cp my-vm.vhdx /var/lib/hyper2kvm/workflow/to_be_processed/

# OVA
cp my-vm.ova /var/lib/hyper2kvm/workflow/to_be_processed/
```

The daemon will:
1. Detect the file
2. Move it to `processing/`
3. Convert it using default settings
4. Move to `processed/` on success or `failed/` on error

### 3. Monitor Progress

```bash
# Watch the processing directory
watch ls -lh /var/lib/hyper2kvm/workflow/processing/

# Check daemon logs
tail -f /var/log/hyper2kvm/workflow-daemon.log

# View completed jobs
ls -lh /var/lib/hyper2kvm/workflow/processed/$(date +%Y-%m-%d)/
```

## Using Job Config Files

For custom conversion settings, create a job config file:

### Simple Job

```yaml
# my-vm-job.yaml
input: my-vm.vmdk
output_format: qcow2
compress: true
fstab_mode: stabilize-all
regen_initramfs: true
# grub is auto-handled
```

Drop both the VMDK and the config file:

```bash
cp my-vm.vmdk /var/lib/hyper2kvm/workflow/to_be_processed/
cp my-vm-job.yaml /var/lib/hyper2kvm/workflow/to_be_processed/
```

### Batch Job

Process multiple VMs with one config:

```yaml
# batch-job.yaml
jobs:
  - input: vm1.vmdk
    output_format: qcow2
    compress: true

  - input: vm2.vhd
    output_format: raw
    compress: false

  - input: vm3.ova
    output_format: qcow2
    flatten: true
```

```bash
cp batch-job.yaml /var/lib/hyper2kvm/workflow/to_be_processed/
```

## Supported File Types

**VM Disk Files:**
- `.vmdk` (VMware)
- `.ova` (OVF archive)
- `.ovf` (OVF)
- `.vhd`, `.vhdx` (Hyper-V)
- `.raw`, `.img` (Raw disk)
- `.ami` (AWS AMI)

**Config Files:**
- `.yaml`, `.yml` (YAML job configs)
- `.json` (JSON job configs)

## Job Metadata

### Success Metadata

For successful jobs, metadata is saved as `<filename>.meta.json`:

```json
{
  "job_id": "my-vm",
  "original_name": "my-vm.vmdk",
  "completed_at": "2026-01-24T10:30:45",
  "status": "success"
}
```

### Error Metadata

For failed jobs, error details are saved as `<filename>.error.json`:

```json
{
  "job_id": "my-vm",
  "original_name": "my-vm.vhd",
  "failed_at": "2026-01-24T10:45:30",
  "error": "File not found: /path/to/vm",
  "exception": "Traceback...",
  "status": "failed"
}
```

## Systemd Integration

### Service File

```bash
# /etc/systemd/system/hyper2kvm-workflow.service
[Unit]
Description=hyper2kvm Workflow Daemon
After=network.target

[Service]
Type=simple
User=hyper2kvm
Group=hyper2kvm
ExecStart=/usr/bin/python3 -m hyper2kvm --config /etc/hyper2kvm/workflow-daemon.yaml
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
```

### Start Service

```bash
sudo systemctl enable --now hyper2kvm-workflow.service
sudo systemctl status hyper2kvm-workflow.service
```

## Advanced Configuration

### Custom Output Paths

```yaml
# Organize output by date and VM name
output_dir: /var/lib/hyper2kvm/output

# Results will be in:
# /var/lib/hyper2kvm/output/2026-01-24/vm-name/
```

### Worker Pool Tuning

```yaml
# Adjust based on CPU cores and disk I/O capacity
max_concurrent_jobs: 5  # Default: 3
```

### Conversion Settings

```yaml
# Apply to all disk files (can be overridden per job)
out_format: qcow2        # or: raw, vdi
compress: true           # qcow2 only
flatten: true            # Flatten snapshot chains
fstab_mode: stabilize-all  # or: bypath-only, noop
regen_initramfs: true    # Rebuild initramfs
```

## Troubleshooting

### Check Failed Jobs

```bash
# List failed jobs
ls -lh /var/lib/hyper2kvm/workflow/failed/$(date +%Y-%m-%d)/

# View error details
cat /var/lib/hyper2kvm/workflow/failed/2026-01-24/my-vm.vhd.error.json
```

### Monitor Active Jobs

```bash
# Check what's currently processing
ls -lh /var/lib/hyper2kvm/workflow/processing/

# Daemon logs
journalctl -u hyper2kvm-workflow.service -f
```

### Reprocess Failed Jobs

```bash
# Move failed job back to to_be_processed
mv /var/lib/hyper2kvm/workflow/failed/2026-01-24/my-vm.vmdk \
   /var/lib/hyper2kvm/workflow/to_be_processed/
```

## Examples

See the example files in this directory:
- `workflow-daemon.yaml` - Main daemon configuration
- `job-config-simple.yaml` - Simple single-VM job
- `job-config-batch.yaml` - Batch processing example

## Comparison: Workflow vs Standard Daemon

| Feature | Standard Daemon | Workflow Daemon |
|---------|----------------|-----------------|
| **Input** | Disk files only | Disk files + config files |
| **State Tracking** | Single watch dir | 3-directory workflow |
| **Observability** | Less clear | Very clear (dir = state) |
| **Config per Job** | No | Yes (.yaml/.json) |
| **Batch Jobs** | No | Yes |
| **Error Handling** | `.errors/` subdir | `failed/` top-level with metadata |

## Best Practices

1. **Use dated subdirectories**: Workflow daemon auto-creates them in `processed/` and `failed/`
2. **Monitor processing/**: If jobs stay here too long, check logs
3. **Archive old jobs**: Periodically clean up `processed/` and `failed/` dated dirs
4. **Config per VM type**: Create job configs for different VM types (Linux, Windows, etc.)
5. **Test first**: Start with `max_concurrent_jobs: 1` and increase based on resources

## See Also

- [Daemon Mode Documentation](../../docs/Daemon-Mode.md)
- [YAML Configuration Examples](../yaml/)
- [Systemd Service Setup](../../systemd/)
