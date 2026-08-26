# YAML Configuration vs Manifests: Understanding the Difference

**When to use YAML configs vs manifest files in Hyper2KVM**

---

## Quick Answer

- **YAML Config Files** → Direct CLI execution for interactive work (`h2kvmctl --config migration.yaml`)
- **Manifest Files** → Daemon-mode workflow processing for automation (`hyper2kvm daemon --manifest-workflow-mode`)

Both are YAML or JSON files, but serve fundamentally different purposes with different execution models.

---

## YAML Configuration Files

### Purpose
Direct command-line execution of a single migration task. You run the command, it executes immediately, and completes synchronously.

### Execution Model
```bash
# You trigger execution directly
h2kvmctl --config migration.yaml
# Command runs and completes before returning
```

### File Structure

Flat configuration with direct parameters:

```yaml
# centos10-test.yaml - Standard YAML Config
cmd: local

# Source VMDK
vmdk: /home/user/VMs/centos10.vmdk

# Output Configuration
output_dir: out/centos10-test
to_output: centos10.qcow2
out_format: qcow2
compress: true

# Core Linux Fixes
fstab_fixes_enable: true
fstab_mode: stabilize-all
grub_fixes_enable: true
initramfs_regen_enable: true
initramfs_regen_force: true

# VirtIO modules
initramfs_modules:
  - virtio_blk
  - virtio_scsi
  - virtio_net
  - virtio_pci

# Network fixes
network_fixes_enable: true

# Libvirt XML generation
libvirt_xml_generate: true
libvirt_vm_name: centos10-test
libvirt_memory_mb: 4096
libvirt_vcpus: 2
libvirt_import: true

# Reporting
report: out/centos10-test/migration-report.md
log_file: out/centos10-test/migration.log
verbose: 2
dry_run: false
```

### Characteristics

- ✅ **Simple syntax**: Flat key-value structure
- ✅ **Direct execution**: Runs when you execute the command
- ✅ **Synchronous**: Blocks until completion
- ✅ **Single VM**: One migration per config file
- ✅ **No state tracking**: No pipeline stages or state management
- ✅ **Immediate feedback**: See results in terminal immediately
- ✅ **Best for**: Interactive CLI usage, testing, development

### Usage Examples

```bash
# Basic migration
h2kvmctl --config migration.yaml

# Using command-line flags instead
h2kvmctl --cmd local \
    --vmdk /vms/centos10.vmdk \
    --output-dir ./out \
    --to-output centos10.qcow2 \
    --compress

# Dry run to preview
h2kvmctl --config migration.yaml --dry-run -vv

# Different commands
h2kvmctl --config fetch-from-esxi.yaml
h2kvmctl --config windows-migration.yaml
```

### When to Use YAML Configs

✅ **Use YAML configs when:**
- Doing one-off migrations
- Interactive testing and development
- Quick conversions with immediate feedback
- Learning and experimenting
- Running from command line manually
- Need simple, straightforward syntax

---

## Manifest Files

### Purpose
Daemon-mode workflow processing with explicit pipeline stages, state tracking, and asynchronous execution. Drop manifests into a watch directory for automatic processing.

### Execution Model
```bash
# Start daemon (runs continuously)
hyper2kvm daemon --manifest-workflow-mode \
  --manifest-workflow-dir /var/lib/hyper2kvm/manifest-workflow

# Drop manifest files for processing
cp vm-manifest.json /var/lib/hyper2kvm/manifest-workflow/to_be_processed/
# Daemon picks it up automatically and processes asynchronously
```

### File Structure

Artifact Manifest v1.0 format with source metadata, disk inventory, and pipeline stages:

```json
{
  "manifest_version": "1.0",
  "source": {"provider": "vsphere", "vm_name": "my-vm", "export_timestamp": "2026-03-24T10:00:00Z"},
  "vm": {"cpu": 2, "mem_gb": 4, "firmware": "bios", "os_hint": "linux"},
  "disks": [
    {"id": "disk-0", "source_format": "vmdk", "bytes": 10737418240, "local_path": "/data/vms/my-vm.vmdk", "disk_type": "boot"}
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

### Directory-Based State Tracking

Manifests move through well-defined directories:

```
manifest_workflow_dir/
├── to_be_processed/   # Drop zone for new manifest files
├── processing/        # Active manifests being processed
├── processed/         # Completed manifests with reports
│   └── 2026-01-28/
│       ├── my-vm.json
│       └── my-vm.json.report.json
└── failed/            # Failed manifests with error details
    └── 2026-01-28/
        ├── bad-vm.json
        └── bad-vm.json.error.json
```

### Manifest Sections

1. **source** - Provider and VM metadata (provider, vm_name, export_timestamp)
2. **vm** - VM hardware specs (cpu, mem_gb, firmware, os_hint)
3. **disks** - Disk inventory (id, source_format, bytes, local_path, disk_type)
4. **pipeline** - Processing stages (inspect, fix, convert, validate, kubevirt)
5. **output** - Output directory and format

> **Note:** The daemon workflow only accepts Artifact Manifest v1.0 (`"manifest_version": "1.0"`). Legacy manifest formats are no longer supported.

### Characteristics

- ✅ **Explicit pipeline**: Declarative stage-by-stage workflow
- ✅ **State tracking**: Observable directory-based state machine
- ✅ **Asynchronous**: Non-blocking, daemon processes in background
- ✅ **Batch processing**: One manifest per VM, drop multiple into watch directory
- ✅ **Detailed reports**: Stage-by-stage JSON reports with artifact tracking
- ✅ **Error handling**: Failed manifests with detailed error context
- ✅ **Observable**: Watch directories to monitor progress
- ✅ **Best for**: Production automation, CI/CD pipelines, batch processing

### Batch Processing

For batch migrations, create one Artifact Manifest v1.0 file per VM and drop them all into the watch directory:

```json
{
  "manifest_version": "1.0",
  "source": {"provider": "vsphere", "vm_name": "web-server", "export_timestamp": "2026-03-24T10:00:00Z"},
  "vm": {"cpu": 4, "mem_gb": 8, "firmware": "bios", "os_hint": "linux"},
  "disks": [
    {"id": "disk-0", "source_format": "vmdk", "bytes": 10737418240, "local_path": "/data/web-server.vmdk", "disk_type": "boot"}
  ],
  "pipeline": {"inspect": {"enabled": true}, "fix": {"enabled": true, "fstab_mode": "stabilize-all"}, "convert": {"enabled": true, "compress": true}, "validate": {"enabled": true}},
  "output": {"directory": "/output", "format": "qcow2"}
}
```

Drop each VM's manifest into the queue:

```bash
cp web-server-manifest.json /var/lib/hyper2kvm/manifest-workflow/to_be_processed/
cp database-manifest.json /var/lib/hyper2kvm/manifest-workflow/to_be_processed/
```

### Output Reports

For successful conversions:

```json
{
  "manifest": "my-vm",
  "status": "completed",
  "completed_at": "2026-01-28T14:30:45",
  "stages": {
    "load": {"status": "success", "artifacts": [...]},
    "inspect": {"status": "success", "os_detected": "CentOS 10"},
    "fix": {"status": "success", "fixes_applied": ["fstab", "grub", "initramfs"]},
    "convert": {"status": "success", "output_file": "/output/my-vm.qcow2"},
    "validate": {"status": "success", "checks": ["format", "size"]}
  },
  "artifacts": {
    "input": "/data/my-vm.vmdk",
    "output": "/output/my-vm-converted.qcow2"
  }
}
```

For failed conversions:

```json
{
  "job_id": "my-vm",
  "original_name": "my-vm.json",
  "failed_at": "2026-01-28T14:30:45",
  "error": "File not found: /data/my-vm.vmdk",
  "exception": "Traceback...",
  "status": "failed"
}
```

### When to Use Manifests

✅ **Use manifests when:**
- Running daemon mode for continuous processing
- Need asynchronous, non-blocking execution
- Batch processing multiple VMs
- Production automation and CI/CD pipelines
- Want detailed stage-by-stage reports
- Need observable workflow state (directory-based)
- Processing VMs from a queue
- Require precise control over pipeline stages

---

## Comparison Table

| Feature | YAML Config | Manifest |
|---------|-------------|----------|
| **Execution** | Synchronous (CLI) | Asynchronous (daemon) |
| **Trigger** | Manual command execution | Drop file in watch directory |
| **Structure** | Flat key-value | Artifact Manifest v1.0 (source, vm, disks, pipeline, output) |
| **State Tracking** | None | Directory-based state machine |
| **Progress Monitoring** | Terminal output | Directory movement + JSON reports |
| **Reporting** | Basic logs | Stage-by-stage JSON reports |
| **Batch Support** | One VM per file | One manifest per VM, drop multiple into watch dir |
| **Error Handling** | Exit code + logs | Failed directory + error JSON |
| **Format** | YAML (or CLI flags) | JSON or YAML |
| **Pipeline Control** | Implicit | Explicit (inspect → fix → convert → validate → kubevirt) |
| **Use Case** | Interactive migrations | Automated workflows |
| **Command** | `h2kvmctl --config config.yaml` | `hyper2kvm daemon --manifest-workflow-mode` |
| **Best For** | Quick one-off migrations | Production automation |
| **Complexity** | Simple | Advanced |

---

## Example Scenarios

### Scenario 1: Quick Interactive Migration

**Use YAML Config**

```bash
# Create simple config
cat > migration.yaml <<EOF
cmd: local
vmdk: /vms/test-vm.vmdk
output_dir: ./out
to_output: test-vm.qcow2
compress: true
fstab_fixes_enable: true
grub_fixes_enable: true
EOF

# Run immediately
h2kvmctl --config migration.yaml
# Waits and shows progress in terminal
```

**Why**: Simple, immediate, direct feedback.

---

### Scenario 2: Production Batch Processing

**Use Manifests**

```bash
# Start daemon (runs continuously)
hyper2kvm daemon --manifest-workflow-mode \
  --manifest-workflow-dir /var/lib/hyper2kvm/manifest-workflow \
  --output-dir /var/lib/hyper2kvm/output \
  --max-concurrent-jobs 4

# Create one manifest per VM (Artifact Manifest v1.0)
cat > vm1-manifest.json <<EOF
{
  "manifest_version": "1.0",
  "source": {"provider": "vsphere", "vm_name": "vm1", "export_timestamp": "2026-03-24T10:00:00Z"},
  "vm": {"cpu": 2, "mem_gb": 4, "firmware": "bios", "os_hint": "linux"},
  "disks": [{"id": "disk-0", "source_format": "vmdk", "bytes": 10737418240, "local_path": "/data/vm1.vmdk", "disk_type": "boot"}],
  "pipeline": {"inspect": {"enabled": true}, "fix": {"enabled": true, "fstab_mode": "stabilize-all"}, "convert": {"enabled": true, "compress": true}, "validate": {"enabled": true}},
  "output": {"directory": "/output", "format": "qcow2"}
}
EOF

cat > vm2-manifest.json <<EOF
{
  "manifest_version": "1.0",
  "source": {"provider": "vsphere", "vm_name": "vm2", "export_timestamp": "2026-03-24T10:00:00Z"},
  "vm": {"cpu": 2, "mem_gb": 4, "firmware": "bios", "os_hint": "linux"},
  "disks": [{"id": "disk-0", "source_format": "vhd", "bytes": 10737418240, "local_path": "/data/vm2.vhd", "disk_type": "boot"}],
  "pipeline": {"inspect": {"enabled": true}, "fix": {"enabled": true, "fstab_mode": "stabilize-all"}, "convert": {"enabled": true, "compress": false}, "validate": {"enabled": true}},
  "output": {"directory": "/output", "format": "raw"}
}
EOF

# Drop each manifest for processing
cp vm1-manifest.json vm2-manifest.json /var/lib/hyper2kvm/manifest-workflow/to_be_processed/

# Monitor progress
watch -n 5 'ls -lh /var/lib/hyper2kvm/manifest-workflow/*/'

# Check results
cat /var/lib/hyper2kvm/manifest-workflow/processed/2026-03-24/vm1-manifest.json.report.json
```

**Why**: Automated, observable, detailed reporting, batch processing.

---

### Scenario 3: CI/CD Pipeline Integration

**Use Manifests**

```bash
# CI/CD job creates manifest from template
envsubst < vm-template.json > "${VM_NAME}-manifest.json"

# Drop into daemon's watch directory
scp "${VM_NAME}-manifest.json" \
    migration-server:/var/lib/hyper2kvm/manifest-workflow/to_be_processed/

# Poll for completion
while [ ! -f "/var/lib/hyper2kvm/manifest-workflow/processed/*/${VM_NAME}-manifest.json" ]; do
  sleep 10
done

# Parse results
jq '.stages.convert.status' /var/lib/hyper2kvm/manifest-workflow/processed/*/${VM_NAME}-manifest.json.report.json
```

**Why**: Automated, non-blocking, machine-parseable results.

---

## Converting Between Formats

### YAML Config → Manifest

**Before (YAML Config):**
```yaml
cmd: local
vmdk: /vms/my-vm.vmdk
output_dir: ./out
to_output: my-vm.qcow2
fstab_fixes_enable: true
grub_fixes_enable: true
compress: true
```

**After (Artifact Manifest v1.0):**
```json
{
  "manifest_version": "1.0",
  "source": {"provider": "vsphere", "vm_name": "my-vm", "export_timestamp": "2026-03-24T10:00:00Z"},
  "vm": {"cpu": 2, "mem_gb": 4, "firmware": "bios", "os_hint": "linux"},
  "disks": [
    {"id": "disk-0", "source_format": "vmdk", "bytes": 10737418240, "local_path": "/vms/my-vm.vmdk", "disk_type": "boot"}
  ],
  "pipeline": {"inspect": {"enabled": true}, "fix": {"enabled": true, "fstab_mode": "stabilize-all"}, "convert": {"enabled": true, "compress": true}, "validate": {"enabled": true}},
  "output": {"directory": "/output", "format": "qcow2"}
}
```

---

## Best Practices

### For YAML Configs

1. ✅ Use for interactive CLI work and testing
2. ✅ Keep configs simple and focused
3. ✅ Use `--dry-run` to preview changes
4. ✅ Version control your configs
5. ✅ Use descriptive output directory names

### For Manifests

1. ✅ Use for production automation
2. ✅ Define all pipeline stages explicitly
3. ✅ Enable validation stage for quality assurance
4. ✅ Monitor processed/ directory for reports
5. ✅ Archive old manifests periodically
6. ✅ Use separate manifest files per VM for batch processing
7. ✅ Version your manifest schema

---

## Commands Reference

### YAML Config Commands

```bash
# Interactive migration
h2kvmctl --config migration.yaml

# Dry run
h2kvmctl --config migration.yaml --dry-run

# Verbose output
h2kvmctl --config migration.yaml -vv

# Override config values
h2kvmctl --config migration.yaml --compress --verbose 3
```

### Manifest Workflow Commands

```bash
# Start daemon
hyper2kvm daemon --manifest-workflow-mode \
  --manifest-workflow-dir /var/lib/hyper2kvm/manifest-workflow \
  --output-dir /var/lib/hyper2kvm/output \
  --max-concurrent-jobs 2

# Drop manifest for processing
cp my-manifest.json /var/lib/hyper2kvm/manifest-workflow/to_be_processed/

# Monitor directories
watch ls -lh /var/lib/hyper2kvm/manifest-workflow/*/

# View report
cat /var/lib/hyper2kvm/manifest-workflow/processed/*/my-manifest.json.report.json

# Reprocess failed manifest
mv /var/lib/hyper2kvm/manifest-workflow/failed/*/my-manifest.json \
   /var/lib/hyper2kvm/manifest-workflow/to_be_processed/
```

---

## Summary

### YAML Configuration Files
- **Nature**: Direct CLI execution configuration
- **Model**: Synchronous, blocking
- **Use**: Interactive work, testing, one-off migrations
- **Command**: `h2kvmctl --config config.yaml`

### Manifest Files
- **Nature**: Declarative pipeline workflow
- **Model**: Asynchronous, daemon-processed
- **Use**: Production automation, batch processing, CI/CD
- **Command**: `hyper2kvm daemon --manifest-workflow-mode` (then drop manifests)

**Both are valid** - choose based on your use case:
- Quick migration? → YAML config
- Production automation? → Manifest

---

## KubeVirt Deployment Stage

When `pipeline.kubevirt.enabled` is true in a manifest, the pipeline adds a **KUBEVIRT_DEPLOY** stage (Stage 7) after validation. This stage generates a KubeVirt `VirtualMachine` custom resource and applies it via `kubectl`.

### Manifest Example with KubeVirt

```json
{
  "manifest_version": "1.0",
  "source": {"provider": "vsphere", "vm_name": "web-app", "export_timestamp": "2026-03-24T10:00:00Z"},
  "vm": {"cpu": 4, "mem_gb": 8, "firmware": "bios", "os_hint": "linux"},
  "disks": [
    {"id": "disk-0", "source_format": "vmdk", "bytes": 21474836480, "local_path": "/data/web-app.vmdk", "disk_type": "boot"}
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

When the kubevirt stage runs, the daemon:

1. Generates a `VirtualMachine` CR from the manifest's `vm` and `disks` metadata
2. Applies the CR via `kubectl apply`
3. Optionally starts the VM if `auto_start` is true

---

## See Also

- [h2kvmctl CLI Guide](cli/h2kvmctl-guide.md)
- [Manifest Workflow Documentation](../examples/manifest-workflow/README.md)
- [YAML Configuration Examples](../examples/yaml/)
- [CLI Reference](cli/reference.md)

---

**Last Updated**: March 2026
**Status**: Production Ready
