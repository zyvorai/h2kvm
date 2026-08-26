# VMCraft LVM Management Guide

Complete guide to Logical Volume Manager (LVM) creation and management with VMCraft for dynamic storage configuration.

## Overview

VMCraft v9.1+ provides comprehensive LVM APIs for creating and managing Linux logical volumes:
- Physical volume (PV) creation
- Volume group (VG) creation and removal
- Logical volume (LV) creation, resizing, and removal
- Full LVM stack lifecycle management

These APIs enable enterprise migration scenarios like:
- Creating flexible storage layouts during migration
- Consolidating multiple partitions into LVM volumes
- Setting up volume snapshots for backup
- Preparing VMs for cloud deployment with dynamic storage

## LVM Concepts

### LVM Stack Hierarchy

```
┌─────────────────────────────────────┐
│  Logical Volumes (LVs)              │  ← User-visible volumes
│  /dev/vg_data/lv_root               │     (mounted as filesystems)
│  /dev/vg_data/lv_home               │
│  /dev/vg_data/lv_var                │
└─────────────────────────────────────┘
               ↑
┌─────────────────────────────────────┐
│  Volume Groups (VGs)                │  ← Pool of storage
│  vg_data (combines PVs)             │     (allocates space to LVs)
└─────────────────────────────────────┘
               ↑
┌──────────────┬──────────────────────┐
│ Physical     │ Physical             │  ← Physical devices
│ Volume (PV)  │ Volume (PV)          │     (partitions or disks)
│ /dev/sda2    │ /dev/sdb1            │
└──────────────┴──────────────────────┘
               ↑
┌──────────────┬──────────────────────┐
│ Partition    │ Partition            │  ← Underlying storage
│ /dev/sda2    │ /dev/sdb1            │
└──────────────┴──────────────────────┘
```

### Key Terms

| Term | Description |
|------|-------------|
| **Physical Volume (PV)** | Partition or disk initialized for LVM use |
| **Volume Group (VG)** | Pool of storage combining one or more PVs |
| **Logical Volume (LV)** | Virtual partition carved from VG space |
| **Physical Extent (PE)** | Smallest allocation unit (default 4MiB) |

---

## LVM Management APIs

### Core APIs (6 methods)

| Method | Purpose | Complexity |
|--------|---------|------------|
| `pvcreate()` | Create physical volumes | Low |
| `vgcreate()` | Create volume group | Low |
| `lvcreate()` | Create logical volume | Medium |
| `lvresize()` | Resize logical volume | Medium |
| `lvremove()` | Remove logical volume | Low |
| `vgremove()` | Remove volume group | Low |

All methods return audit dicts with `{attempted, ok, error}` pattern.

---

## Quick Start Examples

### 1. Create Simple LVM Setup

```python
from h2kvm.vmcraft import VMCraft

g = VMCraft("ubuntu-server.vmdk")
g.launch()

# Create partition for LVM
g.part_init("/dev/nbd0", "gpt")
g.part_add("/dev/nbd0", "primary", 2048, -1)

# Initialize physical volume
result = g.pvcreate(["/dev/nbd0p1"])
print(f"PV created: {result['ok']}")

# Create volume group
result = g.vgcreate("vg_data", ["/dev/nbd0p1"])
print(f"VG created: {result['ok']}")

# Create logical volume (use all available space)
result = g.lvcreate("lv_root", "vg_data", extents="100%FREE")
print(f"LV path: {result['lv']}")  # /dev/vg_data/lv_root

# Format and mount
g.mkfs("ext4", "/dev/vg_data/lv_root", label="root")
g.mount("/dev/vg_data/lv_root", "/")
```

### 2. Create Multi-Volume Setup

```python
# Create multiple logical volumes from single volume group

# Create VG (assuming PV already created)
g.vgcreate("vg_system", ["/dev/nbd0p2"])

# Create root volume (20 GiB)
result = g.lvcreate("lv_root", "vg_system", size_mb=20480)
print(f"Root LV: {result['lv']}")

# Create home volume (30 GiB)
result = g.lvcreate("lv_home", "vg_system", size_mb=30720)
print(f"Home LV: {result['lv']}")

# Create var volume (10 GiB)
result = g.lvcreate("lv_var", "vg_system", size_mb=10240)
print(f"Var LV: {result['lv']}")

# Use remaining space for tmp
result = g.lvcreate("lv_tmp", "vg_system", extents="100%FREE")
print(f"Tmp LV: {result['lv']}")

# Format all volumes
g.mkfs("ext4", "/dev/vg_system/lv_root", label="root")
g.mkfs("ext4", "/dev/vg_system/lv_home", label="home")
g.mkfs("ext4", "/dev/vg_system/lv_var", label="var")
g.mkfs("ext4", "/dev/vg_system/lv_tmp", label="tmp")
```

### 3. Extend Logical Volume

```python
# Resize logical volume (requires filesystem resize after)

# Check current size
result = g.lvs()  # Hypothetical method (not yet implemented)
current_size_mb = 20480  # 20 GiB

# Extend to 30 GiB
new_size_mb = 30720
result = g.lvresize("/dev/vg_system/lv_root", new_size_mb)

if result['ok']:
    # Extend filesystem to use new space
    # For ext4:
    g.resize2fs("/dev/vg_system/lv_root")
    # For XFS:
    # g.xfs_growfs("/dev/vg_system/lv_root")
```

---

## API Reference

### pvcreate()

Create physical volumes for LVM use.

**Signature:**
```python
def pvcreate(devices: list[str]) -> dict[str, Any]
```

**Parameters:**
- `devices` (list[str]): List of device paths to initialize as PVs

**Returns:**
- `dict`: Audit dict with keys:
  - `attempted` (bool): Whether operation was attempted
  - `ok` (bool): Whether operation succeeded
  - `error` (str | None): Error message if failed
  - `pvs` (list[str]): List of created PV paths

**Example:**
```python
# Create single PV
result = g.pvcreate(["/dev/nbd0p2"])
if result['ok']:
    print(f"Created PVs: {result['pvs']}")
else:
    print(f"Failed: {result['error']}")

# Create multiple PVs
result = g.pvcreate(["/dev/nbd0p2", "/dev/nbd0p3"])
if result['ok']:
    print(f"Created {len(result['pvs'])} PVs")
```

**Notes:**
- Destroys existing data on device
- Device must be partition or whole disk (not mounted)
- Requires `lvm2` tools (`pvcreate` command)

---

### vgcreate()

Create volume group from physical volumes.

**Signature:**
```python
def vgcreate(vgname: str, pvs: list[str]) -> dict[str, Any]
```

**Parameters:**
- `vgname` (str): Volume group name
- `pvs` (list[str]): List of physical volume paths

**Returns:**
- `dict`: Audit dict with keys:
  - `attempted` (bool): Whether operation was attempted
  - `ok` (bool): Whether operation succeeded
  - `error` (str | None): Error message if failed
  - `vg` (str | None): Volume group name

**Example:**
```python
# Create VG from single PV
result = g.vgcreate("vg_data", ["/dev/nbd0p2"])
if result['ok']:
    print(f"VG created: {result['vg']}")

# Create VG from multiple PVs (spanning disks)
result = g.vgcreate("vg_large", ["/dev/nbd0p2", "/dev/nbd0p3"])
if result['ok']:
    print(f"VG '{result['vg']}' created from multiple PVs")
```

**Notes:**
- VG name must be unique on system
- All PVs must already exist (`pvcreate` first)
- Combines PV space into single pool

---

### lvcreate()

Create logical volume within volume group.

**Signature:**
```python
def lvcreate(
    lvname: str,
    vgname: str,
    size_mb: int | None = None,
    extents: str | None = None
) -> dict[str, Any]
```

**Parameters:**
- `lvname` (str): Logical volume name
- `vgname` (str): Volume group name
- `size_mb` (int | None): Size in megabytes (mutually exclusive with `extents`)
- `extents` (str | None): Size in extents (e.g., `"100%FREE"`, `"50%VG"`)

**Returns:**
- `dict`: Audit dict with keys:
  - `attempted` (bool): Whether operation was attempted
  - `ok` (bool): Whether operation succeeded
  - `error` (str | None): Error message if failed
  - `lv` (str | None): Logical volume path (e.g., `/dev/vg_data/lv_root`)

**Example:**
```python
# Create LV with absolute size
result = g.lvcreate("lv_root", "vg_system", size_mb=20480)  # 20 GiB
if result['ok']:
    print(f"LV created at: {result['lv']}")

# Create LV using all free space
result = g.lvcreate("lv_data", "vg_system", extents="100%FREE")

# Create LV using 50% of VG space
result = g.lvcreate("lv_half", "vg_system", extents="50%VG")

# Create LV using specific extent count
result = g.lvcreate("lv_exact", "vg_system", extents="1000")  # 1000 extents
```

**Extent Formats:**
- `"100%FREE"` - Use all free space in VG
- `"50%FREE"` - Use 50% of free space
- `"100%VG"` - Use entire VG (warning: leaves no free space)
- `"50%VG"` - Use 50% of total VG space
- `"1000"` - Use exactly 1000 extents (default extent: 4MiB = 4000 MiB)

**Notes:**
- Must specify either `size_mb` OR `extents` (not both)
- LV name must be unique within VG
- VG must have sufficient free space

---

### lvresize()

Resize logical volume.

**Signature:**
```python
def lvresize(lvpath: str, size_mb: int) -> dict[str, Any]
```

**Parameters:**
- `lvpath` (str): Logical volume path (e.g., `/dev/vg_data/lv_root`)
- `size_mb` (int): New size in megabytes

**Returns:**
- `dict`: Audit dict with `attempted`, `ok`, `error` keys

**Example:**
```python
# Extend LV from 20 GiB to 30 GiB
result = g.lvresize("/dev/vg_system/lv_root", 30720)  # 30 GiB

if result['ok']:
    print("LV extended successfully")

    # IMPORTANT: Resize filesystem after extending LV
    # For ext4:
    g.resize2fs("/dev/vg_system/lv_root")
    # For XFS:
    # g.xfs_growfs("/dev/vg_system/lv_root")
else:
    print(f"Resize failed: {result['error']}")
```

**Important Notes:**
- **Extending**: Safe to extend LV, then resize filesystem
- **Shrinking**: MUST shrink filesystem BEFORE shrinking LV (data loss risk!)
- Filesystem resize is separate operation (not automatic)
- VG must have sufficient free space for extension

**Shrinking Workflow (ext4):**
```python
# 1. Unmount filesystem
g.umount("/dev/vg_system/lv_data")

# 2. Check filesystem
g.e2fsck("/dev/vg_system/lv_data", force=True)

# 3. Shrink filesystem first
g.resize2fs("/dev/vg_system/lv_data", "15G")  # Shrink to 15 GiB

# 4. Shrink LV to match
result = g.lvresize("/dev/vg_system/lv_data", 15360)  # 15 GiB

# 5. Remount
g.mount("/dev/vg_system/lv_data", "/data")
```

---

### lvremove()

Remove logical volume.

**Signature:**
```python
def lvremove(lvpath: str, force: bool = False) -> dict[str, Any]
```

**Parameters:**
- `lvpath` (str): Logical volume path
- `force` (bool): Force removal without confirmation

**Returns:**
- `dict`: Audit dict with `attempted`, `ok`, `error` keys

**Example:**
```python
# Remove LV with confirmation (default)
result = g.lvremove("/dev/vg_system/lv_old")

# Force removal (no confirmation prompt)
result = g.lvremove("/dev/vg_system/lv_tmp", force=True)

if result['ok']:
    print("LV removed successfully")
else:
    print(f"Removal failed: {result['error']}")
```

**Important:**
- Data is destroyed permanently
- LV must be unmounted before removal
- Cannot be undone (backup important data first)

---

### vgremove()

Remove volume group.

**Signature:**
```python
def vgremove(vgname: str, force: bool = False) -> dict[str, Any]
```

**Parameters:**
- `vgname` (str): Volume group name
- `force` (bool): Force removal without confirmation

**Returns:**
- `dict`: Audit dict with `attempted`, `ok`, `error` keys

**Example:**
```python
# Remove VG (must remove all LVs first)
result = g.lvremove("/dev/vg_old/lv_data", force=True)
result = g.lvremove("/dev/vg_old/lv_home", force=True)
result = g.vgremove("vg_old", force=True)

if result['ok']:
    print("VG removed successfully")
```

**Important:**
- All logical volumes must be removed first
- PVs are not removed (use `pvremove` to clean up PVs)

---

## Advanced Use Cases

### 1. Enterprise RHEL/Ubuntu LVM Setup

```python
# Create production LVM layout for RHEL/Ubuntu

g = VMCraft("rhel9-server.vmdk")
g.launch()

# Create partitions
g.part_init("/dev/nbd0", "gpt")

# Boot partition (non-LVM, 1 GiB)
g.part_add("/dev/nbd0", "primary", 2048, 2099200)
g.mkfs("ext4", "/dev/nbd0p1", label="boot")

# LVM partition (remaining space)
g.part_add("/dev/nbd0", "primary", 2099200, -1)
g.part_set_gpt_type("/dev/nbd0", 2, "E6D6D379-F507-44C2-A23C-238F2A3DF928")  # Linux LVM

# Create LVM stack
g.pvcreate(["/dev/nbd0p2"])
g.vgcreate("rhel", ["/dev/nbd0p2"])

# Create logical volumes
g.lvcreate("root", "rhel", size_mb=10240)     # 10 GiB for /
g.lvcreate("home", "rhel", size_mb=20480)     # 20 GiB for /home
g.lvcreate("var", "rhel", size_mb=10240)      # 10 GiB for /var
g.lvcreate("tmp", "rhel", size_mb=5120)       # 5 GiB for /tmp
g.lvcreate("swap", "rhel", size_mb=4096)      # 4 GiB swap

# Format volumes
g.mkfs("ext4", "/dev/rhel/root", label="root")
g.mkfs("ext4", "/dev/rhel/home", label="home")
g.mkfs("ext4", "/dev/rhel/var", label="var")
g.mkfs("ext4", "/dev/rhel/tmp", label="tmp")
g.mkswap("/dev/rhel/swap")

# Mount hierarchy
g.mount("/dev/rhel/root", "/")
g.mount("/dev/nbd0p1", "/boot")
g.mount("/dev/rhel/home", "/home")
g.mount("/dev/rhel/var", "/var")
g.mount("/dev/rhel/tmp", "/tmp")
```

### 2. Multi-Disk LVM Setup (Spanning)

```python
# Create VG spanning multiple physical disks

g = VMCraft("multi-disk-vm.vmdk")
g.launch()

# Initialize multiple disks with LVM partitions
devices = ["/dev/nbd0", "/dev/nbd1", "/dev/nbd2"]

pvs = []
for device in devices:
    g.part_init(device, "gpt")
    g.part_add(device, "primary", 2048, -1)
    partition = f"{device}p1"

    result = g.pvcreate([partition])
    if result['ok']:
        pvs.append(partition)

# Create VG spanning all disks
result = g.vgcreate("vg_large", pvs)
print(f"VG spans {len(pvs)} physical volumes")

# Create large LV using all space
result = g.lvcreate("lv_data", "vg_large", extents="100%FREE")
print(f"Large LV created: {result['lv']}")

# Format and mount
g.mkfs("xfs", "/dev/vg_large/lv_data", label="large-data")
g.mount("/dev/vg_large/lv_data", "/data")
```

### 3. Convert Existing Partitions to LVM During Migration

```python
# Migrate from traditional partitions to LVM layout

g = VMCraft("legacy-vm.vmdk")
g.launch()

# Backup existing data from /home and /var
# (Copy files to temporary location)

# Delete old partitions (after backup!)
g.part_del("/dev/nbd0", 3)  # /home
g.part_del("/dev/nbd0", 4)  # /var

# Create single LVM partition in freed space
g.part_add("/dev/nbd0", "primary", 20971520, -1)  # From 10GiB to end

# Setup LVM
g.pvcreate(["/dev/nbd0p3"])
g.vgcreate("vg_data", ["/dev/nbd0p3"])
g.lvcreate("lv_home", "vg_data", size_mb=30720)  # 30 GiB
g.lvcreate("lv_var", "vg_data", extents="100%FREE")

# Format
g.mkfs("ext4", "/dev/vg_data/lv_home", label="home")
g.mkfs("ext4", "/dev/vg_data/lv_var", label="var")

# Restore data
# (Copy files back from temporary location)
```

### 4. LVM Thin Provisioning (Advanced)

```python
# Create thin provisioning pool for efficient storage use
# Note: Requires thin provisioning support in LVM

# Create VG
g.vgcreate("vg_thin", ["/dev/nbd0p2"])

# Create thin pool (uses lvcreate with thin pool flags)
# This requires extending VMCraft with thin pool support
# For now, use shell commands:

from h2kvm.core.utils import run_sudo

# Create thin pool (50 GiB)
cmd = ["lvcreate", "-L", "50G", "-T", "vg_thin/thin_pool"]
run_sudo(g.logger, cmd, check=True)

# Create thin volumes (can overcommit)
cmd = ["lvcreate", "-V", "100G", "-T", "vg_thin/thin_pool", "-n", "thin_vol1"]
run_sudo(g.logger, cmd, check=True)

cmd = ["lvcreate", "-V", "100G", "-T", "vg_thin/thin_pool", "-n", "thin_vol2"]
run_sudo(g.logger, cmd, check=True)

# Total allocated: 200 GiB
# Actual pool size: 50 GiB (thin provisioning)
```

---

## Integration with Migration Workflows

### Complete Migration with LVM Conversion

```python
#!/usr/bin/env python3
"""Migrate VMware VM to KVM with LVM conversion."""

from h2kvm.vmcraft import VMCraft
import logging

logging.basicConfig(level=logging.INFO)

def migrate_to_lvm(source_vmdk: str, target_qcow2: str):
    """Convert traditional partition layout to LVM during migration."""

    g = VMCraft(source_vmdk)
    g.launch()

    try:
        # 1. Inspect source VM
        os_info = g.inspect_os()
        print(f"Migrating: {os_info}")

        # 2. Create new disk with LVM layout
        # (Simplified - in practice, copy data partition by partition)

        # 3. Setup LVM structure
        g.pvcreate(["/dev/nbd0p2"])
        g.vgcreate("vg_system", ["/dev/nbd0p2"])

        # 4. Create logical volumes
        lvs = {
            "root": 20480,   # 20 GiB
            "home": 30720,   # 30 GiB
            "var": 10240,    # 10 GiB
        }

        for lv_name, size_mb in lvs.items():
            result = g.lvcreate(lv_name, "vg_system", size_mb=size_mb)
            if result['ok']:
                # Format
                g.mkfs("ext4", result['lv'], label=lv_name)
                print(f"✓ Created and formatted {lv_name}")

        # 5. Mount and copy data
        g.mount("/dev/vg_system/root", "/")
        g.mount("/dev/vg_system/home", "/home")
        g.mount("/dev/vg_system/var", "/var")

        # 6. Update fstab for LVM paths
        fstab_content = """
# /etc/fstab - LVM layout
/dev/vg_system/root  /       ext4  defaults  0  1
/dev/vg_system/home  /home   ext4  defaults  0  2
/dev/vg_system/var   /var    ext4  defaults  0  2
"""
        g.write("/etc/fstab", fstab_content)

        # 7. Update GRUB for LVM boot
        # (Regenerate initramfs with LVM support)

        print("✓ Migration to LVM complete")

    finally:
        g.shutdown()

if __name__ == "__main__":
    migrate_to_lvm("vmware-vm.vmdk", "kvm-vm.qcow2")
```

---

## Best Practices

### 1. Always Use Partition Type GUID for LVM

```python
# ✓ GOOD: Set LVM partition type
g.part_set_gpt_type("/dev/nbd0", 2, "E6D6D379-F507-44C2-A23C-238F2A3DF928")

# ✗ BAD: Generic partition type
# (Works but less clear in tools like parted, gdisk)
```

### 2. Leave Free Space in VG for Snapshots

```python
# ✓ GOOD: Reserve 20% for snapshots
g.lvcreate("lv_data", "vg_system", extents="80%VG")

# ✗ BAD: Use entire VG (no room for snapshots)
g.lvcreate("lv_data", "vg_system", extents="100%VG")
```

### 3. Use Descriptive VG/LV Names

```python
# ✓ GOOD: Descriptive names
g.vgcreate("vg_database", pvs)
g.lvcreate("lv_mysql_data", "vg_database", size_mb=102400)

# ✗ BAD: Generic names
g.vgcreate("vg0", pvs)
g.lvcreate("lv0", "vg0", size_mb=102400)
```

### 4. Check VG Free Space Before Creating LVs

```python
# ✓ GOOD: Check available space
# (Hypothetical vgs() method - not yet implemented)
# vg_info = g.vgs("vg_system")
# free_mb = vg_info['free_mb']
# if free_mb >= 20480:
#     g.lvcreate("lv_new", "vg_system", size_mb=20480)

# Current workaround: Use extents
result = g.lvcreate("lv_new", "vg_system", extents="50%FREE")
```

### 5. Always Remove LVs Before Removing VG

```python
# ✓ GOOD: Remove LVs first
g.lvremove("/dev/vg_old/lv_data", force=True)
g.lvremove("/dev/vg_old/lv_home", force=True)
g.vgremove("vg_old", force=True)

# ✗ BAD: Try to remove VG with active LVs (will fail)
# g.vgremove("vg_old")  # Error: VG contains active LVs
```

---

## Troubleshooting

### Issue: "LVM tools not available"

**Cause:** `lvm2` package not installed on host

**Solution:**
```bash
# Fedora/RHEL
sudo dnf install lvm2

# Ubuntu/Debian
sudo apt install lvm2

# Verify
which pvcreate vgcreate lvcreate
```

### Issue: "Device not found" during pvcreate

**Cause:** Partition doesn't exist or NBD not connected

**Solution:**
```python
# Verify partition exists
parts = g.list_partitions()
print(f"Available partitions: {parts}")

# Ensure partition table re-read
g.blockdev_rereadpt("/dev/nbd0")

# Try again
result = g.pvcreate(["/dev/nbd0p2"])
```

### Issue: "Insufficient free space" during lvcreate

**Cause:** VG doesn't have enough space for requested LV size

**Solution:**
```python
# Use extents to allocate available space
result = g.lvcreate("lv_data", "vg_system", extents="100%FREE")

# Or check VG capacity first
# vg_info = g.vgs("vg_system")  # Not yet implemented
# free_mb = vg_info['free_mb']
```

### Issue: LV path doesn't appear after lvcreate

**Cause:** udev rules not triggered or LV inactive

**Solution:**
```python
# Activate LV manually
from h2kvm.core.utils import run_sudo
run_sudo(g.logger, ["lvchange", "-ay", "/dev/vg_system/lv_data"], check=True)

# Wait for udev
import time
time.sleep(1)

# Verify LV exists
import os
assert os.path.exists("/dev/vg_system/lv_data"), "LV path doesn't exist"
```

---

## See Also

- [VMCraft Complete Guide](vmcraft/complete-guide.md) - Full VMCraft API reference
- [VMCraft Partition Management](vmcraft-partition-management.md) - Partition manipulation
- [VMCraft Performance Guide](vmcraft-performance-guide.md) - Performance optimizations
- [Migration Playbooks](../../guides/migration/playbooks.md) - Complete migration workflows

---

**Last Updated**: March 2026
**VMCraft Version**: v9.1+
