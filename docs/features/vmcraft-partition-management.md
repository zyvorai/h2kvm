# VMCraft Partition Management Guide

Complete guide to partition table manipulation with VMCraft for advanced VM customization.

## Overview

VMCraft v9.1+ provides comprehensive partition management APIs for:
- Creating and deleting partitions
- Initializing partition tables (GPT, MBR/msdos)
- Setting GPT metadata (names, type GUIDs)
- Querying partition table information

These APIs enable advanced migration scenarios like:
- Repartitioning VMs during migration
- Converting MBR to GPT
- Creating additional partitions for KVM-specific data
- Customizing partition layouts for cloud environments

## Partition Management APIs

### Core APIs (7 methods)

| Method | Purpose | Complexity |
|--------|---------|------------|
| `part_init()` | Initialize empty partition table | Low |
| `part_disk()` | Initialize table + create single partition | Low |
| `part_add()` | Add partition to device | Medium |
| `part_del()` | Delete partition by number | Low |
| `part_set_name()` | Set GPT partition name | Low |
| `part_set_gpt_type()` | Set GPT partition type GUID | Low |
| `part_get_parttype()` | Get partition table type | Low |

---

## Quick Start Examples

### 1. Create GPT Partition Table

```python
from h2kvm.vmcraft import VMCraft

g = VMCraft("ubuntu-server.vmdk")
g.launch()

# Initialize GPT partition table (empty, no partitions)
g.part_init("/dev/nbd0", "gpt")

# Verify
parttype = g.part_get_parttype("/dev/nbd0")
print(f"Partition table type: {parttype}")  # Output: gpt
```

### 2. Create Partition Table with Single Partition

```python
# Initialize GPT and create single partition covering entire disk
g.part_disk("/dev/nbd0", "gpt")

# Verify partition created
parts = g.list_partitions()
print(f"Partitions: {parts}")  # Output: ['/dev/nbd0p1']
```

### 3. Add Multiple Partitions

```python
# Initialize empty GPT table
g.part_init("/dev/nbd0", "gpt")

# Add boot partition (1GiB)
# Sectors: 2048 (1MiB offset) to 2097152 (1GiB)
g.part_add("/dev/nbd0", "primary", 2048, 2099200)

# Add root partition (remaining space)
# Sectors: 2099200 to end of disk (-1)
g.part_add("/dev/nbd0", "primary", 2099200, -1)

# Verify
parts = g.list_partitions()
print(f"Created partitions: {parts}")
# Output: ['/dev/nbd0p1', '/dev/nbd0p2']
```

### 4. Set GPT Partition Metadata

```python
# Set partition name (GPT only)
g.part_set_name("/dev/nbd0", 1, "EFI System")
g.part_set_name("/dev/nbd0", 2, "Linux Root")

# Set partition type GUID (GPT only)
# EFI System Partition GUID
g.part_set_gpt_type("/dev/nbd0", 1, "C12A7328-F81F-11D2-BA4B-00A0C93EC93B")

# Linux filesystem GUID
g.part_set_gpt_type("/dev/nbd0", 2, "0FC63DAF-8483-4772-8E79-3D69D8477DE4")
```

---

## API Reference

### part_init()

Initialize empty partition table (no partitions created).

**Signature:**
```python
def part_init(device: str, parttype: str) -> None
```

**Parameters:**
- `device` (str): Device path (e.g., `/dev/nbd0`)
- `parttype` (str): Partition table type (`"gpt"`, `"msdos"`, or `"mbr"`)

**Notes:**
- `"mbr"` is normalized to `"msdos"` internally
- Destroys existing partition table and data
- Does not create any partitions (use `part_add()` or `part_disk()`)

**Example:**
```python
# GPT partition table
g.part_init("/dev/nbd0", "gpt")

# MBR/msdos partition table
g.part_init("/dev/nbd0", "msdos")

# Also accepts "mbr" (normalized to "msdos")
g.part_init("/dev/nbd0", "mbr")
```

---

### part_disk()

Initialize partition table and create single partition covering entire disk.

**Signature:**
```python
def part_disk(device: str, parttype: str) -> None
```

**Parameters:**
- `device` (str): Device path
- `parttype` (str): Partition table type (`"gpt"`, `"msdos"`, or `"mbr"`)

**Notes:**
- Convenience wrapper for `part_init()` + `part_add()`
- Creates one primary partition from 1MiB to 100% of disk
- 1MiB offset ensures proper alignment

**Example:**
```python
# Create GPT with single partition
g.part_disk("/dev/nbd0", "gpt")

# Equivalent to:
# g.part_init("/dev/nbd0", "gpt")
# g.part_add("/dev/nbd0", "primary", 2048, -1)
```

---

### part_add()

Add partition to device.

**Signature:**
```python
def part_add(device: str, prlogex: str, startsect: int, endsect: int) -> None
```

**Parameters:**
- `device` (str): Device path (e.g., `/dev/nbd0`)
- `prlogex` (str): Partition type (`"primary"`, `"logical"`, or `"extended"`)
- `startsect` (int): Start sector (usually 2048 for 1MiB alignment)
- `endsect` (int): End sector (`-1` for end of disk)

**Notes:**
- Partition cache automatically invalidated
- Partition table re-read automatically (`blockdev_rereadpt()`)
- Sector size is typically 512 bytes

**Example:**
```python
# Boot partition: 1MiB to 1GiB
# Start: sector 2048 (1MiB / 512 bytes)
# End: sector 2099200 ((1GiB + 1MiB) / 512 bytes)
g.part_add("/dev/nbd0", "primary", 2048, 2099200)

# Root partition: 1GiB to end of disk
g.part_add("/dev/nbd0", "primary", 2099200, -1)
```

**Sector Calculation:**
```python
# Convert MiB to sectors (512-byte sectors)
def mib_to_sectors(mib):
    return (mib * 1024 * 1024) // 512

# Example: 100 MiB offset, 500 MiB size
start_sect = mib_to_sectors(100)  # 204800
end_sect = mib_to_sectors(600)    # 1228800

g.part_add("/dev/nbd0", "primary", start_sect, end_sect)
```

---

### part_del()

Delete partition from device.

**Signature:**
```python
def part_del(device: str, partnum: int) -> None
```

**Parameters:**
- `device` (str): Device path
- `partnum` (int): Partition number to delete (1-based indexing)

**Notes:**
- Partition data is NOT securely wiped
- Partition table updated immediately
- Cache invalidated and partition table re-read

**Example:**
```python
# Delete first partition
g.part_del("/dev/nbd0", 1)

# Delete third partition
g.part_del("/dev/nbd0", 3)

# Verify deletion
parts = g.list_partitions()
print(f"Remaining partitions: {parts}")
```

**Warning:**
```python
# ✗ DANGEROUS: Deletes boot partition
g.part_del("/dev/nbd0", 1)

# Always verify partition contents before deletion
metadata = g.blkid("/dev/nbd0p1")
print(f"Partition 1 label: {metadata.get('LABEL', 'N/A')}")

if metadata.get("LABEL") != "Important Data":
    g.part_del("/dev/nbd0", 1)  # Safe to delete
```

---

### part_set_name()

Set GPT partition name.

**Signature:**
```python
def part_set_name(device: str, partnum: int, name: str) -> None
```

**Parameters:**
- `device` (str): Device path
- `partnum` (int): Partition number (1-based)
- `name` (str): Partition name (up to 36 characters)

**Notes:**
- **GPT only** (not supported on MBR/msdos)
- Name is purely metadata (not used for mounting)
- Visible in `lsblk`, `parted print`, `gdisk -l`

**Example:**
```python
# Set descriptive names for GPT partitions
g.part_set_name("/dev/nbd0", 1, "EFI System")
g.part_set_name("/dev/nbd0", 2, "Linux Root x86-64")
g.part_set_name("/dev/nbd0", 3, "Linux /home")
g.part_set_name("/dev/nbd0", 4, "Linux Swap")

# Verify with lsblk
# /dev/nbd0p1  "EFI System"
# /dev/nbd0p2  "Linux Root x86-64"
# /dev/nbd0p3  "Linux /home"
# /dev/nbd0p4  "Linux Swap"
```

---

### part_set_gpt_type()

Set GPT partition type GUID.

**Signature:**
```python
def part_set_gpt_type(device: str, partnum: int, guid: str) -> None
```

**Parameters:**
- `device` (str): Device path
- `partnum` (int): Partition number (1-based)
- `guid` (str): Partition type GUID (UUID format)

**Common GUIDs:**

| Partition Type | GUID |
|----------------|------|
| EFI System Partition | `C12A7328-F81F-11D2-BA4B-00A0C93EC93B` |
| Linux filesystem | `0FC63DAF-8483-4772-8E79-3D69D8477DE4` |
| Linux swap | `0657FD6D-A4AB-43C4-84E5-0933C84B4F4F` |
| Linux /home | `933AC7E1-2EB4-4F13-B844-0E14E2AEF915` |
| Linux LVM | `E6D6D379-F507-44C2-A23C-238F2A3DF928` |
| Microsoft Basic Data | `EBD0A0A2-B9E5-4433-87C0-68B6B72699C7` |
| Microsoft Reserved | `E3C9E316-0B5C-4DB8-817D-F92DF00215AE` |

**Example:**
```python
# Set partition types for typical Linux system
g.part_set_gpt_type("/dev/nbd0", 1, "C12A7328-F81F-11D2-BA4B-00A0C93EC93B")  # EFI
g.part_set_gpt_type("/dev/nbd0", 2, "0FC63DAF-8483-4772-8E79-3D69D8477DE4")  # Root
g.part_set_gpt_type("/dev/nbd0", 3, "933AC7E1-2EB4-4F13-B844-0E14E2AEF915")  # /home
g.part_set_gpt_type("/dev/nbd0", 4, "0657FD6D-A4AB-43C4-84E5-0933C84B4F4F")  # Swap
```

---

### part_get_parttype()

Get partition table type.

**Signature:**
```python
def part_get_parttype(device: str) -> str
```

**Parameters:**
- `device` (str): Device path

**Returns:**
- `str`: Partition table type (`"gpt"`, `"msdos"`, or `"unknown"`)

**Example:**
```python
parttype = g.part_get_parttype("/dev/nbd0")

if parttype == "gpt":
    print("GPT partition table")
    # Can use part_set_name(), part_set_gpt_type()
elif parttype == "msdos":
    print("MBR/msdos partition table")
    # Cannot use GPT-specific features
else:
    print("Unknown or no partition table")
```

---

## Advanced Use Cases

### 1. Convert MBR to GPT During Migration

```python
from h2kvm.vmcraft import VMCraft

g = VMCraft("legacy-vm.vmdk")
g.launch()

# Check current partition table type
current_type = g.part_get_parttype("/dev/nbd0")
print(f"Current: {current_type}")  # Output: msdos

if current_type == "msdos":
    # Backup partition layout
    parts_before = g.list_partitions()
    print(f"Partitions before: {parts_before}")

    # WARNING: This destroys data! Backup first!
    # Copy all partition data to temporary location

    # Re-initialize as GPT
    g.part_init("/dev/nbd0", "gpt")

    # Recreate partitions with same layout
    # (Restore data from backup after recreation)
```

**Note:** MBR→GPT conversion requires data backup and restoration. Consider using `gdisk` or `sgdisk` for in-place conversion instead.

### 2. Create Multi-Partition Layout for Enterprise Linux

```python
# Create enterprise RHEL/Ubuntu partition layout
# Layout: EFI (512M), /boot (1G), / (50G), /home (remaining)

g = VMCraft("enterprise-linux.vmdk")
g.launch()

# Initialize GPT
g.part_init("/dev/nbd0", "gpt")

# Calculate sectors (512 bytes per sector)
# 1 MiB = 2048 sectors
# 512 MiB = 1048576 sectors
# 1 GiB = 2097152 sectors
# 50 GiB = 104857600 sectors

# Partition 1: EFI (1MiB - 513MiB)
g.part_add("/dev/nbd0", "primary", 2048, 1050624)
g.part_set_name("/dev/nbd0", 1, "EFI System")
g.part_set_gpt_type("/dev/nbd0", 1, "C12A7328-F81F-11D2-BA4B-00A0C93EC93B")

# Partition 2: /boot (513MiB - 1.5GiB)
g.part_add("/dev/nbd0", "primary", 1050624, 3147776)
g.part_set_name("/dev/nbd0", 2, "Linux /boot")
g.part_set_gpt_type("/dev/nbd0", 2, "0FC63DAF-8483-4772-8E79-3D69D8477DE4")

# Partition 3: / (1.5GiB - 51.5GiB)
g.part_add("/dev/nbd0", "primary", 3147776, 107005952)
g.part_set_name("/dev/nbd0", 3, "Linux Root")
g.part_set_gpt_type("/dev/nbd0", 3, "0FC63DAF-8483-4772-8E79-3D69D8477DE4")

# Partition 4: /home (51.5GiB - end)
g.part_add("/dev/nbd0", "primary", 107005952, -1)
g.part_set_name("/dev/nbd0", 4, "Linux /home")
g.part_set_gpt_type("/dev/nbd0", 4, "933AC7E1-2EB4-4F13-B844-0E14E2AEF915")

# Format partitions
g.mkfs("ext4", "/dev/nbd0p2", label="boot")
g.mkfs("ext4", "/dev/nbd0p3", label="root")
g.mkfs("ext4", "/dev/nbd0p4", label="home")
g.mkfs("vfat", "/dev/nbd0p1", label="EFI")

# Mount and verify
g.mount("/dev/nbd0p3", "/")
g.mount("/dev/nbd0p2", "/boot")
g.mount("/dev/nbd0p4", "/home")
g.mount("/dev/nbd0p1", "/boot/efi")
```

### 3. Add KVM-Specific Partition During Migration

```python
# Add partition for cloud-init config or KVM guest agent data

g = VMCraft("vmware-vm.vmdk")
g.launch()

# Get current partition count
parts = g.list_partitions()
print(f"Existing partitions: {len(parts)}")

# Shrink last partition to make space (requires filesystem resize)
# (Use resize2fs, xfs_growfs, etc. before shrinking partition)

# Add new partition for KVM data (1 GiB)
last_part_num = len(parts)
new_start = 107005952  # After shrinking last partition
new_end = 109103104    # +1 GiB

g.part_add("/dev/nbd0", "primary", new_start, new_end)
g.part_set_name("/dev/nbd0", last_part_num + 1, "KVM Cloud Config")

# Format and populate
g.mkfs("ext4", f"/dev/nbd0p{last_part_num + 1}", label="kvm-config")
g.mount(f"/dev/nbd0p{last_part_num + 1}", "/tmp/kvm-config")

# Write cloud-init config
cloud_init_cfg = """#cloud-config
users:
  - name: admin
    sudo: ALL=(ALL) NOPASSWD:ALL
    ssh_authorized_keys:
      - ssh-rsa AAAA...
"""
g.write("/tmp/kvm-config/cloud-init.yaml", cloud_init_cfg)
```

### 4. Align Partitions for SSD/NVMe Performance

```python
# Ensure partitions are aligned to 1MiB boundaries for optimal SSD performance

def align_to_mib(sector, alignment=2048):
    """Align sector to 1MiB boundary (2048 sectors)."""
    return ((sector + alignment - 1) // alignment) * alignment

# Create aligned partitions
g.part_init("/dev/nbd0", "gpt")

# Partition 1: Start at 1MiB, size 10GiB
p1_start = align_to_mib(2048)       # 2048 (1MiB)
p1_end = align_to_mib(20973568)     # 20971520 (10GiB aligned)

# Partition 2: Start after p1, size 20GiB
p2_start = align_to_mib(p1_end + 1)  # 20973568 (aligned)
p2_end = align_to_mib(62916608)      # 62914560 (20GiB aligned)

g.part_add("/dev/nbd0", "primary", p1_start, p1_end)
g.part_add("/dev/nbd0", "primary", p2_start, p2_end)

print(f"Partition 1: {p1_start} - {p1_end} (aligned: {p1_start % 2048 == 0})")
print(f"Partition 2: {p2_start} - {p2_end} (aligned: {p2_start % 2048 == 0})")
```

---

## Integration with LVM

Partition management is essential for setting up LVM during migration:

```python
# Create partitions for LVM physical volumes

g = VMCraft("database-server.vmdk")
g.launch()

# Initialize GPT
g.part_init("/dev/nbd0", "gpt")

# Create boot partition (non-LVM)
g.part_add("/dev/nbd0", "primary", 2048, 2099200)  # 1GiB

# Create LVM partition (remaining space)
g.part_add("/dev/nbd0", "primary", 2099200, -1)
g.part_set_name("/dev/nbd0", 2, "Linux LVM")
g.part_set_gpt_type("/dev/nbd0", 2, "E6D6D379-F507-44C2-A23C-238F2A3DF928")

# Create LVM stack on partition 2
result = g.pvcreate(["/dev/nbd0p2"])
print(f"PV created: {result['ok']}")

result = g.vgcreate("vg_data", ["/dev/nbd0p2"])
print(f"VG created: {result['ok']}")

result = g.lvcreate("lv_root", "vg_data", extents="100%FREE")
print(f"LV created: {result['lv']}")  # /dev/vg_data/lv_root

# Format and use LVM volume
g.mkfs("ext4", "/dev/vg_data/lv_root", label="root")
```

See [VMCraft LVM Guide](vmcraft-lvm-guide.md) for more LVM examples.

---

## Best Practices

### 1. Always Start at 1MiB Offset

**Reason:** Modern disks (SSD, NVMe, advanced format HDD) require 1MiB alignment for optimal performance.

```python
# ✓ GOOD: 1MiB offset (sector 2048)
g.part_add("/dev/nbd0", "primary", 2048, -1)

# ✗ BAD: No offset (sector 0 or 1)
g.part_add("/dev/nbd0", "primary", 0, -1)  # Poor performance
```

### 2. Use GPT for Modern Systems

**Reason:** GPT supports disks >2TB, unlimited partitions, partition names, and is UEFI-compatible.

```python
# ✓ GOOD: GPT for new VMs
g.part_init("/dev/nbd0", "gpt")

# ✗ BAD: MBR for disks >2TB or UEFI systems
g.part_init("/dev/nbd0", "msdos")  # Limited to 2TB, 4 primary partitions
```

### 3. Set Partition Names and Types

**Reason:** Improves manageability and compatibility with automation tools.

```python
# ✓ GOOD: Descriptive metadata
g.part_set_name("/dev/nbd0", 1, "EFI System")
g.part_set_gpt_type("/dev/nbd0", 1, "C12A7328-F81F-11D2-BA4B-00A0C93EC93B")

# ✗ BAD: No metadata
# (Partitions have generic names like "primary1", no type info)
```

### 4. Invalidate Cache After Modifications

**Reason:** Ensure partition list is up-to-date after changes.

```python
# Cache is automatically invalidated by part_add(), part_del()
g.part_add("/dev/nbd0", "primary", 2048, -1)
# Cache cleared automatically

# Manual invalidation if needed
g.invalidate_partition_cache("/dev/nbd0")
```

### 5. Verify Partition Table After Modifications

```python
# Always verify after partition operations
g.part_add("/dev/nbd0", "primary", 2048, -1)

# Verify partition created
parts = g.list_partitions()
assert len(parts) > 0, "Partition creation failed"

# Verify partition table type
parttype = g.part_get_parttype("/dev/nbd0")
assert parttype == "gpt", "Partition table type mismatch"
```

---

## Troubleshooting

### Issue: "Partition table re-read failed"

**Cause:** Kernel couldn't re-read partition table (disk in use, mounted partitions)

**Solution:**
```python
# Ensure no partitions are mounted
g.umount_all()

# Manually trigger re-read
g.blockdev_rereadpt("/dev/nbd0")

# Verify kernel recognized partitions
import time
time.sleep(1)  # Give kernel time to update
parts = g.list_partitions()
```

### Issue: "Invalid partition table type"

**Cause:** Disk has no partition table or corrupted table

**Solution:**
```python
# Check current state
parttype = g.part_get_parttype("/dev/nbd0")

if parttype == "unknown":
    # Initialize fresh partition table
    g.part_init("/dev/nbd0", "gpt")
```

### Issue: "Partition number out of range"

**Cause:** Attempting to delete non-existent partition

**Solution:**
```python
# Always check partition count first
parts = g.list_partitions()
max_partnum = len(parts)

if partnum <= max_partnum:
    g.part_del("/dev/nbd0", partnum)
else:
    print(f"Partition {partnum} doesn't exist (max: {max_partnum})")
```

### Issue: GPT commands fail on MBR disk

**Cause:** GPT-specific operations (`part_set_name`, `part_set_gpt_type`) not supported on MBR

**Solution:**
```python
# Check partition table type before GPT operations
parttype = g.part_get_parttype("/dev/nbd0")

if parttype == "gpt":
    g.part_set_name("/dev/nbd0", 1, "EFI System")
    g.part_set_gpt_type("/dev/nbd0", 1, "C12A7328-F81F-11D2-BA4B-00A0C93EC93B")
else:
    print(f"GPT operations not supported on {parttype} partition table")
```

---

## See Also

- [VMCraft Complete Guide](vmcraft/complete-guide.md) - Full VMCraft API reference
- [VMCraft LVM Guide](vmcraft-lvm-guide.md) - LVM creation and management
- [VMCraft Performance Guide](vmcraft-performance-guide.md) - Performance optimizations
- [Advanced Features](vmcraft/advanced-features.md) - Advanced usage patterns

---

**Last Updated**: March 2026
**VMCraft Version**: v9.1+
