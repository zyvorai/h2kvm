# Manifest Workflow Daemon - 3-Directory Processing

The manifest workflow daemon provides declarative, observable VM conversion processing using manifest files.

## Features

- **Declarative Pipeline**: Define entire conversion workflow in JSON/YAML
- **Clear State Tracking**: Manifests move through well-defined directories
- **Batch Processing**: Process multiple VMs with a single manifest
- **Detailed Reports**: JSON reports with artifact tracking
- **Error Handling**: Failed manifests with detailed error context

## Directory Structure

```
manifest_workflow_dir/
├── to_be_processed/   # Drop zone for manifest files (.json, .yaml)
├── processing/        # Active manifests being processed
├── processed/         # Completed manifests with reports
│   └── 2026-01-24/
│       ├── my-vm.json
│       └── my-vm.json.report.json
└── failed/            # Failed manifests with error details
    └── 2026-01-24/
        ├── bad-vm.json
        └── bad-vm.json.error.json
```

## Quick Start

### 1. Start the Manifest Workflow Daemon

```bash
# Using config file
sudo h2kvm --config manifest-daemon.yaml

# Or via command line
sudo h2kvm daemon \
  --manifest-workflow-mode \
  --manifest-workflow-dir /var/lib/h2kvm/manifest-workflow \
  --output-dir /var/lib/h2kvm/output \
  --max-concurrent-jobs 2
```

### 2. Drop Manifest Files

Create a manifest file describing your conversion:

```json
{
  "manifest_version": "1.0",
  "source": {"provider": "vsphere", "vm_name": "my-vm", "export_timestamp": "2026-03-24T10:00:00Z"},
  "vm": {"cpu": 2, "mem_gb": 4, "firmware": "bios", "os_hint": "linux"},
  "disks": [
    {"id": "disk-0", "source_format": "vmdk", "bytes": 10737418240, "local_path": "/data/my-vm.vmdk", "disk_type": "boot"}
  ],
  "pipeline": {"inspect": {"enabled": true}, "fix": {"enabled": true, "fstab_mode": "stabilize-all"}, "convert": {"enabled": true, "compress": true}, "validate": {"enabled": true}},
  "output": {"directory": "/output", "format": "qcow2"}
}
```

Drop it into the queue:

```bash
cp my-vm-manifest.json /var/lib/h2kvm/manifest-workflow/to_be_processed/
```

### 3. Monitor Progress

```bash
# Watch directories
watch ls -lh /var/lib/h2kvm/manifest-workflow/*/

# Check logs
tail -f /var/log/h2kvm/manifest-daemon.log

# View completed reports
cat /var/lib/h2kvm/manifest-workflow/processed/2026-01-24/my-vm.json.report.json
```

## Manifest Format

> **Important:** The daemon workflow only accepts Artifact Manifest v1.0 (`"manifest_version": "1.0"`). Legacy manifest formats are no longer supported.

### Artifact Manifest v1.0

```json
{
  "manifest_version": "1.0",
  "source": {"provider": "vsphere", "vm_name": "my-vm", "export_timestamp": "2026-03-24T10:00:00Z"},
  "vm": {"cpu": 2, "mem_gb": 4, "firmware": "bios", "os_hint": "linux"},
  "disks": [
    {"id": "disk-0", "source_format": "vmdk", "bytes": 10737418240, "local_path": "/path/to/disk.vmdk", "disk_type": "boot"}
  ],
  "pipeline": {
    "inspect": {"enabled": true},
    "fix": {"enabled": true, "fstab_mode": "stabilize-all"},
    "convert": {"enabled": true, "compress": true},
    "validate": {"enabled": true}
  },
  "output": {"directory": "/output", "format": "qcow2"}
}
```

### Batch Processing

For batch migrations, use one manifest file per VM and drop them all into the watch directory. Each manifest follows the same Artifact Manifest v1.0 format:

```bash
# vm1-manifest.json
cp vm1-manifest.json /var/lib/h2kvm/manifest-workflow/to_be_processed/

# vm2-manifest.json
cp vm2-manifest.json /var/lib/h2kvm/manifest-workflow/to_be_processed/
```

Example manifest for vm1:

```json
{
  "manifest_version": "1.0",
  "source": {"provider": "vsphere", "vm_name": "vm1", "export_timestamp": "2026-03-24T10:00:00Z"},
  "vm": {"cpu": 2, "mem_gb": 4, "firmware": "bios", "os_hint": "linux"},
  "disks": [
    {"id": "disk-0", "source_format": "vmdk", "bytes": 10737418240, "local_path": "/data/vm1.vmdk", "disk_type": "boot"}
  ],
  "pipeline": {"inspect": {"enabled": true}, "fix": {"enabled": true, "fstab_mode": "stabilize-all"}, "convert": {"enabled": true, "compress": true}, "validate": {"enabled": true}},
  "output": {"directory": "/output", "format": "qcow2"}
}
```

## Pipeline Stages

### 1. DISKS
Source disks are defined in the top-level `disks` array:
- `id`: Unique disk identifier (e.g., `disk-0`)
- `source_format`: vmdk, ova, ovf, vhd, vhdx, raw, ami
- `local_path`: Path to source disk
- `disk_type`: boot or data
- `bytes`: Disk size in bytes

### 2. INSPECT
Detect guest OS and configuration:
- `enabled`: Enable inspection
- `detect_os`: Detect operating system

### 3. FIX
Apply offline fixes:
- **fstab**: Rewrite `/etc/fstab` entries
  - `mode`: stabilize-all, bypath-only, noop
- **grub**: Repair GRUB bootloader
- **initramfs**: Regenerate initramfs
- **network**: Fix network configuration
  - `fix_level`: full, basic, none

### 4. CONVERT
Convert to target format:
- `output_format`: qcow2, raw, vdi
- `compress`: Enable compression (qcow2 only)
- `output_path`: Optional custom output name

### 5. VALIDATE
Validate conversion:
- `enabled`: Enable validation
- `boot_test`: Test boot (requires QEMU)

### 6. LIBVIRT_XML
Generate libvirt domain XML (implicit when output format is qcow2/raw and libvirt options are set).

### 7. KUBEVIRT_DEPLOY
Deploy to KubeVirt (when `pipeline.kubevirt.enabled` is true):
- `enabled`: Enable KubeVirt deployment
- `namespace`: Target Kubernetes namespace
- `auto_start`: Start the VM after CR creation

Generates a KubeVirt `VirtualMachine` CR from manifest metadata and applies it via `kubectl`.

Example:
```json
{
  "manifest_version": "1.0",
  "source": {"provider": "vsphere", "vm_name": "app-server", "export_timestamp": "2026-03-24T10:00:00Z"},
  "vm": {"cpu": 4, "mem_gb": 8, "firmware": "bios", "os_hint": "linux"},
  "disks": [
    {"id": "disk-0", "source_format": "vmdk", "bytes": 21474836480, "local_path": "/data/app-server.vmdk", "disk_type": "boot"}
  ],
  "pipeline": {
    "inspect": {"enabled": true},
    "fix": {"enabled": true, "fstab_mode": "stabilize-all"},
    "convert": {"enabled": true, "compress": true},
    "validate": {"enabled": true},
    "kubevirt": {"enabled": true, "namespace": "production", "auto_start": true}
  },
  "output": {"directory": "/output", "format": "qcow2"}
}
```

## Output Reports

For successful conversions, a report is generated:

```json
{
  "manifest": "my-vm",
  "status": "completed",
  "completed_at": "2026-01-24T14:30:45",
  "stages": {
    "load": {"status": "success", "artifacts": [...]},
    "inspect": {"status": "success", "os_detected": "..."},
    "fix": {"status": "success", "fixes_applied": [...]},
    "convert": {"status": "success", "output_file": "..."},
    "validate": {"status": "success", "checks": [...]}
  },
  "artifacts": {
    "input": "/data/my-vm.vmdk",
    "output": "/output/my-vm-converted.qcow2"
  }
}
```

## Error Reports

For failed conversions:

```json
{
  "job_id": "my-vm",
  "original_name": "my-vm.json",
  "failed_at": "2026-01-24T14:30:45",
  "error": "File not found: /data/my-vm.vmdk",
  "exception": "Traceback...",
  "status": "failed"
}
```

## Examples

This directory contains:

- `manifest-daemon.yaml` - Daemon configuration
- `simple-vm-manifest.json` - Single VM example
- `batch-manifest.json` - Batch processing example
- `photon-manifest.json` - Real Photon OS example

## Systemd Integration

```bash
# /etc/systemd/system/h2kvm-manifest.service
[Unit]
Description=h2kvm Manifest Workflow Daemon
After=network.target

[Service]
Type=simple
User=h2kvm
Group=h2kvm
ExecStart=/usr/bin/python3 -m h2kvm --config /etc/h2kvm/manifest-daemon.yaml
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
```

## Comparison: Disk Workflow vs Manifest Workflow

| Feature | Disk Workflow | Manifest Workflow |
|---------|--------------|-------------------|
| **Input** | Disk files (.vmdk, .vhd, etc.) | Manifest files (.json, .yaml) |
| **Configuration** | Job configs (optional) | Pipeline definition (required) |
| **Pipeline** | Implicit | Explicit/declarative |
| **Reporting** | Basic metadata | Detailed stage-by-stage reports |
| **Batch** | Config file with jobs | One manifest per VM, drop multiple into watch dir |
| **Use Case** | Quick disk conversions | Complex workflows with validation |

## Best Practices

1. **Use manifests for complex workflows**: When you need precise control over each pipeline stage
2. **Version your manifests**: Commit manifest files to version control
3. **Test with dry-run first**: Validate manifest syntax before production
4. **Monitor processed/ directory**: Review reports for conversion quality
5. **Archive old manifests**: Periodically clean up dated subdirectories

## Troubleshooting

### Manifest Validation Errors

```bash
# Check manifest syntax
python -m json.tool my-manifest.json

# Or for YAML
python -c "import yaml; yaml.safe_load(open('my-manifest.yaml'))"
```

### Check Processing State

```bash
# List active manifests
ls -lh /var/lib/h2kvm/manifest-workflow/processing/

# View error details
cat /var/lib/h2kvm/manifest-workflow/failed/2026-01-24/my-vm.json.error.json
```

### Reprocess Failed Manifest

```bash
# Move back to to_be_processed
mv /var/lib/h2kvm/manifest-workflow/failed/2026-01-24/my-vm.json \
   /var/lib/h2kvm/manifest-workflow/to_be_processed/
```

## See Also

- [Disk Workflow Documentation](../workflow-daemon/README.md)
- [Manifest Format Specification](../../docs/Manifest-Format.md)
- [YAML Configuration Examples](../yaml/)
