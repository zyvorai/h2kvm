# Migration Pipeline Test Guide

Complete guide for testing the h2kvm migration pipeline with vmspawn validation.

## Quick Start

### Method 1: Using YAML Configuration (Recommended)

```bash
# Run with the provided config
./test_migration_cli.py migration-config.yaml
```

### Method 2: Using Command-Line Arguments

```bash
# Basic conversion + validation
./test_migration_cli.py \
    --vmdk ./esx8.0-rhel8.8-with-thin-provision-disk1.vmdk \
    --output-dir ./output \
    --flatten \
    --compress \
    --fstab-mode stabilize-all \
    --regen-initramfs
```

### Method 3: Using Python API Directly

```bash
# Run the pipeline test script
./test_migration_pipeline.py
```

## Configuration

### YAML Configuration File

Edit `migration-config.yaml`:

```yaml
input:
  vmdk: ./esx8.0-rhel8.8-with-thin-provision-disk1.vmdk

output:
  dir: ./output
  filename: rhel8.8-fixed.qcow2
  format: qcow2
  compress: true

conversion:
  flatten: true
  fstab_mode: stabilize-all
  regen_initramfs: true

validation:
  enabled: true
  memory: 2048
  cpus: 2
  timeout: 300
  tpm: false
```

## Pipeline Stages

The migration pipeline runs these stages:

### 1. Disk Conversion (VMDK → QCOW2)

**Operations:**
- ✅ Flatten thin-provisioned disks
- ✅ Convert to QCOW2 format
- ✅ Apply compression

**Expected Duration:** 2-10 minutes (depends on disk size)

### 2. Offline Fixes

**Operations:**
- ✅ Stabilize /etc/fstab (UUID → /dev/sdX)
- ✅ Regenerate initramfs with KVM drivers
- ✅ Fix bootloader configuration
- ✅ Update network configuration

**Expected Duration:** 30-60 seconds

### 3. VM Validation with vmspawn

**Operations:**
- ✅ Boot VM with systemd-vmspawn
- ✅ Verify systemd is running
- ✅ Check network configuration
- ✅ Confirm boot completed

**Expected Duration:** 30-300 seconds (depends on image)

### 4. Reporting

**Outputs:**
- ✅ Console summary with timeline
- ✅ JSON report: `output/migration-report.json`
- ✅ Exit code (0 = success, 1 = failure)

## Command-Line Options

### Input/Output Options

```bash
--vmdk FILE              # Input VMDK file (required)
--output-dir DIR         # Output directory (default: ./output)
--output-file NAME       # Output filename (default: converted.qcow2)
--format FORMAT          # Output format: qcow2, raw, vmdk (default: qcow2)
```

### Conversion Options

```bash
--flatten                # Flatten disk chain (recommended)
--no-flatten            # Keep disk chain
--compress              # Compress output (qcow2 only)
--fstab-mode MODE       # preserve, uuid, label, stabilize-all
--regen-initramfs       # Regenerate initramfs (default: true)
```

### Validation Options

```bash
--no-validation         # Skip validation (conversion only)
--validation-memory MB  # VM memory (default: 2048)
--validation-cpus N     # VM CPUs (default: 2)
--validation-timeout S  # Timeout in seconds (default: 300)
--validation-tpm        # Enable TPM emulation
```

## Example Usage

### Basic Test

```bash
# Full pipeline with defaults
./test_migration_cli.py \
    --vmdk esx8.0-rhel8.8-with-thin-provision-disk1.vmdk
```

Expected output:
```
======================================================================
H2KVM MIGRATION PIPELINE TEST
======================================================================

Input:  ./esx8.0-rhel8.8-with-thin-provision-disk1.vmdk
Output: ./output/rhel8.8-fixed.qcow2
Format: qcow2
Compress: True
Fstab Mode: stabilize-all
Regen Initramfs: True
======================================================================

🔄 [2026-02-18T23:00:00] Disk Conversion: start
✅ [2026-02-18T23:05:30] Disk Conversion: Converted in 330.5s → ./output/rhel8.8-fixed.qcow2
🔄 [2026-02-18T23:05:30] VM Validation: start
ℹ️  [2026-02-18T23:05:30] VM Validation: Booting VM (timeout: 300s)
✅ [2026-02-18T23:06:15] VM Validation: Passed in 45.2s (systemd: True, network: True, boot: True)
✅ [2026-02-18T23:06:15] Migration Pipeline: All steps completed successfully

======================================================================
MIGRATION PIPELINE REPORT
======================================================================

Overall Status: ✅ SUCCESS
Total Duration: 375.7s

📦 Disk Conversion:
  Status: ✅ Success
  Duration: 330.5s
  Output: ./output/rhel8.8-fixed.qcow2
  Flatten: True
  Fstab Mode: stabilize-all
  Initramfs Regen: True

🔍 VM Validation:
  Status: ✅ Success
  Duration: 45.2s
  Checks:
    Systemd:       ✅
    Network:       ✅
    Boot Complete: ✅

📄 Report saved to: ./output/migration-report.json
```

### Conversion Only (No Validation)

```bash
# Skip validation for faster testing
./test_migration_cli.py \
    --vmdk image.vmdk \
    --no-validation
```

### Custom Validation Settings

```bash
# More memory and timeout for large VMs
./test_migration_cli.py \
    --vmdk image.vmdk \
    --validation-memory 4096 \
    --validation-cpus 4 \
    --validation-timeout 600
```

### With TPM for Secure Boot

```bash
# Enable TPM emulation
./test_migration_cli.py \
    --vmdk image.vmdk \
    --validation-tpm
```

## Troubleshooting

### Issue: Conversion Fails

**Check:**
```bash
# Verify input file exists
ls -lh esx8.0-rhel8.8-with-thin-provision-disk1.vmdk

# Check qemu-img is available
qemu-img --version

# Check disk space
df -h ./output
```

**Solution:**
- Ensure input file is readable
- Install qemu-utils: `sudo apt install qemu-utils`
- Free up disk space (need 2x source size)

### Issue: Validation Timeout

**Check:**
```bash
# Test image boots manually
qemu-system-x86_64 \
    -m 2G \
    -smp 2 \
    -drive file=./output/rhel8.8-fixed.qcow2 \
    -nographic
```

**Solution:**
- Increase timeout: `--validation-timeout 600`
- Check initramfs was regenerated correctly
- Verify fstab uses correct device names

### Issue: systemd-vmspawn Not Found

**Check:**
```bash
which systemd-vmspawn
systemd-vmspawn --version
```

**Solution:**
```bash
# Debian/Ubuntu
sudo apt install systemd-container

# RHEL/Fedora
sudo dnf install systemd-container
```

### Issue: Permission Denied on /dev/kvm

**Check:**
```bash
ls -la /dev/kvm
groups
```

**Solution:**
```bash
# Add user to kvm group
sudo usermod -a -G kvm $USER

# Log out and back in, or:
newgrp kvm
```

## Output Files

After successful migration:

```
output/
├── rhel8.8-fixed.qcow2       # Converted and fixed VM image
├── migration-report.json     # Detailed JSON report
└── temp/                     # Temporary files (if debug enabled)
    ├── fstab.orig
    ├── initramfs.log
    └── conversion.log
```

## Report Format

The JSON report contains:

```json
{
  "conversion": {
    "success": true,
    "output_path": "./output/rhel8.8-fixed.qcow2",
    "duration": 330.5,
    "flatten": true,
    "fstab_mode": "stabilize-all",
    "initramfs_regen": true
  },
  "validation": {
    "success": true,
    "duration": 45.2,
    "checks": {
      "systemd": true,
      "network": true,
      "boot_complete": true
    }
  },
  "timeline": [
    {
      "timestamp": "2026-02-18T23:00:00",
      "step": "Disk Conversion",
      "status": "start"
    },
    ...
  ],
  "success": true
}
```

## Integration with CI/CD

### GitHub Actions

```yaml
- name: Test Migration
  run: |
    pip install h2kvm
    ./test_migration_cli.py migration-config.yaml

- name: Upload Result
  uses: actions/upload-artifact@v4
  with:
    name: migrated-vm
    path: output/rhel8.8-fixed.qcow2
```

### GitLab CI

```yaml
test-migration:
  script:
    - pip install h2kvm
    - ./test_migration_cli.py migration-config.yaml
  artifacts:
    paths:
      - output/
    reports:
      junit: output/migration-report.json
```

## Advanced Usage

### Custom Pipeline

Create your own pipeline:

```python
from test_migration_pipeline import MigrationPipeline

config = {
    "vmdk": "my-vm.vmdk",
    "output_dir": "./output",
    "to_output": "my-vm.qcow2",
    "flatten": True,
    "fstab_mode": "stabilize-all",
    "regen_initramfs": True,
}

pipeline = MigrationPipeline(config)
success = pipeline.run()
```

### Skip Specific Stages

```python
# Conversion only
pipeline = MigrationPipeline(config)
success = pipeline.run_conversion()

# Validation only (if image already exists)
pipeline = MigrationPipeline(config)
pipeline.results["conversion"]["output_path"] = "existing.qcow2"
success = pipeline.run_validation()
```

## Performance Tips

1. **Use SSD storage** for 2-3x faster conversion
2. **Increase CPU cores** for parallel processing
3. **Pre-allocate disk space** for qcow2:
   ```bash
   qemu-img create -f qcow2 -o preallocation=metadata output.qcow2 50G
   ```
4. **Disable compression** for faster conversion (use for final output only)

## Next Steps

After successful migration:

1. **Test thoroughly** in development environment
2. **Verify all services** start correctly
3. **Check performance** compared to original
4. **Deploy to production** using KubeVirt or standalone KVM

## Getting Help

- Issues: https://github.com/ssahani/h2kvm/issues
- Discussions: https://github.com/ssahani/h2kvm/discussions
- Docs: https://h2kvm.io/docs
