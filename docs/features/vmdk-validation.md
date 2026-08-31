# VMDK and Disk Image Validation

**Comprehensive validation tools for ensuring disk image integrity before migration**

---

## Overview

H2KVM provides built-in validation capabilities to check disk image integrity at multiple levels before attempting migration. This helps catch corruption, format issues, and filesystem problems early in the migration process.

### Validation Levels

| Level | Speed | Requires Root | Description |
|-------|-------|---------------|-------------|
| **Basic** | Fast | No | qemu-img metadata + structure check |
| **Deep** | Medium | Yes | Basic + partition table inspection via NBD |
| **Full** | Slow | Yes | Deep + read-only filesystem checks (fsck -n) |

---

## Quick Start

### Command-Line Validation

```bash
# Basic validation (fast, no root required)
python scripts/validate_vmdk.py /path/to/disk.vmdk

# Deep validation with partition table check
sudo python scripts/validate_vmdk.py --deep /path/to/disk.vmdk

# Full validation with filesystem integrity checks
sudo python scripts/validate_vmdk.py --full /path/to/disk.vmdk
```

### Python API

```python
from h2kvm.guestkit.nbd import NBDDeviceManager
import logging

logger = logging.getLogger(__name__)
nbd = NBDDeviceManager(logger, readonly=True)

# Basic validation (fast)
metadata = nbd._validate_image('/path/to/disk.vmdk')
print(f"Format: {metadata['format']}")
print(f"Size: {metadata['virtual-size'] / (1024**3):.2f} GiB")

# Deep validation (requires sudo)
report = nbd.validate_filesystems(
    '/path/to/disk.vmdk',
    check_partitions=True,
    run_fsck=False
)
print(f"Partitions: {len(report['partitions'])}")

# Full validation with fsck (requires sudo, slower)
report = nbd.validate_filesystems(
    '/path/to/disk.vmdk',
    check_partitions=True,
    run_fsck=True
)
for fsck in report['fsck_results']:
    print(f"{fsck['partition']}: {fsck['status']}")

# Comprehensive disk inspection with LVM (requires sudo)
report = nbd.inspect_disk(
    '/path/to/disk.vmdk',
    check_lvm=True,
    activate_lvm=True,
    run_fsck=False
)
print(f"LVM PVs: {len(report['lvm']['physical_volumes'])}")
print(f"LVM VGs: {len(report['lvm']['volume_groups'])}")
print(f"LVM LVs: {len(report['lvm']['logical_volumes'])}")
print(f"Filesystems: {len(report['filesystems'])}")
```

---

## Validation and Inspection Methods

### 1. Basic Validation (`_validate_image()`)

**Fast structural validation using qemu-img**

```python
metadata = nbd._validate_image(image_path)
```

**What it checks:**
- ✅ Image format validity (VMDK, QCOW2, VHD, etc.)
- ✅ Structural integrity (qemu-img check)
- ✅ Metadata extraction (size, format, backing files)
- ✅ Corruption detection (leaked clusters, corrupted sectors)
- ✅ Snapshot/backing file warnings

**Advantages:**
- No root privileges required
- Fast execution (~1-2 seconds)
- No NBD device needed
- Safe for all environments

**Returns:**
- Image metadata dictionary from qemu-img info

**Raises:**
- `RuntimeError` if image is invalid or corrupted

---

### 2. Deep Filesystem Validation (`validate_filesystems()`)

**Comprehensive validation with partition table inspection**

```python
report = nbd.validate_filesystems(
    image_path,
    format='vmdk',           # Optional format hint
    check_partitions=True,   # Inspect partition table
    run_fsck=False          # Skip filesystem checks
)
```

**What it checks:**
- ✅ Everything from basic validation
- ✅ Partition table structure (via NBD + lsblk)
- ✅ Partition device creation
- ✅ Filesystem type detection
- ✅ Optionally: Read-only filesystem checks (fsck -n)

**Advantages:**
- Detects partition table corruption
- Verifies partitions are mountable
- Identifies filesystem types
- Optional filesystem integrity checks

**Requirements:**
- Root/sudo privileges
- NBD kernel module
- qemu-nbd command

**Returns:**
- Validation report dictionary:
  ```python
  {
      "image": "/path/to/disk.vmdk",
      "format": "vmdk",
      "virtual_size_gb": 100.0,
      "actual_size_gb": 25.5,
      "partitions": [
          {"device": "nbd0p1", "info": "nbd0p1 ext4 1G ..."},
          {"device": "nbd0p2", "info": "nbd0p2 swap 4G ..."}
      ],
      "partition_table": "lsblk output...",
      "fsck_results": [
          {"partition": "/dev/nbd0p1", "status": "clean", "exit_code": 0},
          {"partition": "/dev/nbd0p2", "status": "clean", "exit_code": 0}
      ],
      "status": "validated"
  }
  ```

**Raises:**
- `RuntimeError` if validation fails
- `FileNotFoundError` if image doesn't exist

---

### 3. Comprehensive Disk Inspection (`inspect_disk()`)

**Complete disk structure analysis including LVM**

```python
report = nbd.inspect_disk(
    image_path,
    format='vmdk',           # Optional format hint
    check_lvm=True,          # Detect LVM structures
    activate_lvm=True,       # Activate VGs to see LVs
    run_fsck=False          # Skip fsck for faster inspection
)
```

**What it checks:**
- ✅ Everything from basic validation
- ✅ Partition table structure
- ✅ LVM physical volumes (pvs)
- ✅ LVM volume groups (vgs)
- ✅ LVM logical volumes (lvs) when activated
- ✅ Filesystems on partitions and LVs
- ✅ Optionally: Filesystem integrity checks

**Advantages:**
- Complete LVM topology analysis
- Shows full storage stack
- Detects filesystems on logical volumes
- Automatic NBD device allocation
- Safe automatic cleanup

**Requirements:**
- Root/sudo privileges
- NBD kernel module
- LVM tools (pvs, vgs, lvs)

**Returns:**
- Comprehensive inspection report:
  ```python
  {
      "image": "/path/to/disk.vmdk",
      "format": "vmdk",
      "virtual_size_gb": 100.0,
      "actual_size_gb": 25.5,
      "partitions": [
          {"device": "nbd0p1", "info": "..."}
      ],
      "lvm": {
          "physical_volumes": [
              {"pv": "/dev/nbd0p2", "vg": "rhel_centos", "size": "95G"}
          ],
          "volume_groups": [
              {"vg": "rhel_centos", "pv_count": "1", "lv_count": "2", "size": "95G"}
          ],
          "logical_volumes": [
              {"lv": "root", "path": "/dev/rhel_centos/root", "size": "91G", "vg": "rhel_centos"},
              {"lv": "swap", "path": "/dev/rhel_centos/swap", "size": "4G", "vg": "rhel_centos"}
          ]
      },
      "filesystems": [
          {"device": "/dev/mapper/rhel_centos-root", "fstype": "xfs"},
          {"device": "/dev/mapper/rhel_centos-swap", "fstype": "swap"}
      ],
      "fsck_results": [],  # Populated if run_fsck=True
      "status": "inspected"
  }
  ```

**Use cases:**
- Pre-migration analysis of LVM setups
- Understanding complex storage layouts
- Planning LVM to LVM migrations
- Troubleshooting storage issues

---

## Use Cases

### Pre-Migration Validation

Validate images before starting migration:

```python
from h2kvm.guestkit.nbd import NBDDeviceManager
import logging

logger = logging.getLogger(__name__)
nbd = NBDDeviceManager(logger, readonly=True)

def validate_before_migration(image_path):
    """Validate image before migration."""
    print(f"Validating: {image_path}")

    # Step 1: Quick structure check
    try:
        metadata = nbd._validate_image(image_path)
        print(f"✓ Format: {metadata['format']}")
    except RuntimeError as e:
        print(f"✗ Invalid image: {e}")
        return False

    # Step 2: Partition table check (if root)
    try:
        report = nbd.validate_filesystems(
            image_path,
            check_partitions=True,
            run_fsck=False
        )
        print(f"✓ Partitions: {len(report['partitions'])}")
    except RuntimeError as e:
        print(f"⚠ Partition check failed: {e}")

    print("✓ Image is ready for migration")
    return True
```

### Batch Validation

Validate multiple images before batch migration:

```bash
#!/bin/bash
# Validate all VMDKs in a directory

for vmdk in /vms/*.vmdk; do
    echo "Validating: $vmdk"
    python scripts/validate_vmdk.py "$vmdk" || echo "Failed: $vmdk"
done
```

### CI/CD Integration

Integrate validation into CI/CD pipelines:

```yaml
# .github/workflows/validate-images.yml
name: Validate VM Images

on: [push]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Install dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y qemu-utils

      - name: Validate images
        run: |
          for img in test-images/*.vmdk; do
            python scripts/validate_vmdk.py "$img"
          done
```

---

## Command-Line Tool

### `scripts/validate_vmdk.py`

Standalone validation script with multiple modes.

#### Basic Validation

```bash
python scripts/validate_vmdk.py /path/to/disk.vmdk
```

**Output:**
```
======================================================================
Basic Validation: disk.vmdk
======================================================================

✓ Image Structure: VALID

Image Metadata:
  Format: vmdk
  Virtual Size: 100.00 GiB
  Actual Size: 25.50 GiB

======================================================================
Basic validation completed successfully
======================================================================
```

#### Deep Validation

```bash
sudo python scripts/validate_vmdk.py --deep /path/to/disk.vmdk
```

**Output:**
```
======================================================================
Deep Validation: disk.vmdk
======================================================================

✓ Deep Validation: PASSED

Image: /path/to/disk.vmdk
Format: vmdk
Virtual Size: 100.00 GiB
Actual Size: 25.50 GiB

Partition Table:
NAME    FSTYPE SIZE  LABEL UUID                                 MOUNTPOINT
nbd0           100G
├─nbd0p1 ext4   96G   root  a1b2c3d4-...
└─nbd0p2 swap   4G          e5f6g7h8-...

Found 2 partitions:
  - nbd0p1: nbd0p1 ext4 96G root a1b2c3d4-...
  - nbd0p2: nbd0p2 swap 4G e5f6g7h8-...

======================================================================
Deep validation completed successfully
======================================================================
```

#### Full Validation

```bash
sudo python scripts/validate_vmdk.py --full /path/to/disk.vmdk
```

**Output:**
```
[... deep validation output ...]

Filesystem Checks:
  ✓ /dev/nbd0p1: clean
  ✓ /dev/nbd0p2: clean

======================================================================
Full validation completed successfully
======================================================================
```

### Options

```
usage: validate_vmdk.py [-h] [--deep] [--full] [-v] [--json] image

Validate VMDK and disk images for integrity

positional arguments:
  image          Path to disk image (VMDK, QCOW2, VHD, etc.)

optional arguments:
  -h, --help     show this help message and exit
  --deep         Enable deep validation (partition table check via NBD)
  --full         Enable full validation (includes read-only fsck)
  -v, --verbose  Verbose output (debug logging)
  --json         Output results as JSON (for --deep/--full only)
```

---

## Examples

### Example Scripts

#### 1. `examples/vmdk_validation_example.py`

Demonstrates all validation methods:

```bash
# Basic validation
python examples/vmdk_validation_example.py /path/to/disk.vmdk

# Deep/full validation (requires sudo)
sudo python examples/vmdk_validation_example.py /path/to/disk.vmdk
```

**What it demonstrates:**
- Basic metadata check
- Partition table validation
- Filesystem integrity check
- Complete pre-migration workflow

---

## Technical Details

### How Validation Works

#### Basic Validation Flow

1. Run `qemu-img check` to detect corruption
2. Run `qemu-img info --output=json` for metadata
3. Parse results and log warnings
4. Return metadata dictionary

#### Deep Validation Flow

1. Perform basic validation first
2. Find free NBD device
3. Connect image via `qemu-nbd --read-only`
4. Run `partprobe` to scan partitions
5. Run `lsblk -f` to inspect partition table
6. Optionally run `fsck -n` (read-only) on each partition
7. Disconnect NBD device
8. Return validation report

### Error Handling

The validation methods handle various error conditions:

- **Invalid format**: Raises `RuntimeError` immediately
- **Corruption detected**: Warns but continues (may fail later)
- **Missing backing file**: Warns about snapshot dependencies
- **Partition errors**: Logged as warnings, included in report
- **fsck failures**: Logged with exit code and output

### Performance

| Validation Level | Time (typical) | Disk Access |
|-----------------|----------------|-------------|
| Basic | 1-2 seconds | Metadata only |
| Deep | 5-10 seconds | Partition scan |
| Full | 30-300 seconds | Full read scan |

**Note**: Full validation time depends on disk size and filesystem complexity.

---

## Best Practices

### When to Use Each Level

**Use Basic Validation:**
- ✅ Quick pre-flight checks
- ✅ CI/CD pipeline validation
- ✅ Validating many images quickly
- ✅ No root access available

**Use Deep Validation:**
- ✅ Pre-migration verification
- ✅ Troubleshooting mount failures
- ✅ Verifying partition table integrity
- ✅ After format conversions

**Use Full Validation:**
- ✅ Suspected filesystem corruption
- ✅ Before critical migrations
- ✅ After manual disk repairs
- ✅ Forensic analysis

### Recommendations

1. **Always validate** before batch migrations
2. **Use basic validation** in automated workflows
3. **Use deep validation** for production VMs
4. **Use full validation** only when troubleshooting
5. **Version control** validation scripts for repeatability

---

## Troubleshooting

### Common Issues

#### Permission Denied

```
Error: Permission denied
```

**Solution:** Deep and full validation require sudo:
```bash
sudo python scripts/validate_vmdk.py --deep disk.vmdk
```

#### NBD Module Not Loaded

```
Error: Failed to load NBD module
```

**Solution:** Load NBD module manually:
```bash
sudo modprobe nbd max_part=16
```

#### qemu-img Not Found

```
Error: qemu-img: command not found
```

**Solution:** Install qemu-img:
```bash
# Fedora/RHEL/CentOS
sudo dnf install qemu-img

# Ubuntu/Debian
sudo apt-get install qemu-utils
```

#### Invalid VMDK Descriptor

```
Error: invalid VMDK image descriptor
```

**Common causes:**
- Using `-flat.vmdk` file instead of descriptor `.vmdk`
- Corrupted descriptor file
- Unsupported VMDK variant

**Solution:** Use the descriptor file (without -flat suffix)

---

## See Also

- [NBD Device Management](../reference/nbd-management.md)
- [Pre-Migration Checklist](../guides/migration/pre-migration.md)
- [Troubleshooting Guide](../guides/troubleshooting.md)

---

**Last Updated**: March 2026
**Status**: Production Ready
**Requirements**: qemu-img (basic), qemu-nbd + NBD kernel module (deep/full)
