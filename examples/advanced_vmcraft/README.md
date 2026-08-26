# Advanced VMCraft Examples

This directory contains comprehensive examples demonstrating VMCraft's advanced capabilities including performance optimizations, partition management, LVM, configuration management, and backup operations.

## Examples Overview

### 01_parallel_mount_performance.py
**Demonstrates:** Performance optimizations and robustness features

- Partition list caching (reduces redundant scans)
- Blkid metadata caching (reduces system calls, 120s TTL)
- Parallel mount operations (2-3x faster than sequential)
- Mount fallback strategies (handles damaged filesystems)
- NBD connection retry logic (handles transient failures)

**Usage:**
```bash
python 01_parallel_mount_performance.py /path/to/vm.qcow2
```

**Key APIs:**
- `list_partitions(use_cache=True)` - Cached partition listing
- `blkid(device, use_cache=True)` - Cached filesystem metadata
- `mount_all_parallel(devices, max_workers=4)` - Parallel mounting
- `mount_with_fallback(device, mountpoint)` - Fallback strategies
- `invalidate_partition_cache()` - Manual cache invalidation

### 02_partition_management.py
**Demonstrates:** Partition table and partition management

- Creating partition tables (GPT, MBR/MSDOS)
- Adding and deleting partitions
- Setting partition names (GPT only)
- Setting GPT partition type GUIDs
- Querying partition information
- Quick disk initialization with `part_disk()`

**Usage:**
```bash
# Create test image first
qemu-img create -f qcow2 test-partition.qcow2 1G
python 02_partition_management.py test-partition.qcow2
```

**Key APIs:**
- `part_init(device, 'gpt'|'msdos')` - Initialize partition table
- `part_add(device, type, start_sect, end_sect)` - Add partition
- `part_del(device, partnum)` - Delete partition
- `part_set_name(device, partnum, name)` - Set partition name (GPT)
- `part_set_gpt_type(device, partnum, guid)` - Set type GUID (GPT)
- `part_get_parttype(device)` - Query partition table type
- `part_disk(device, 'gpt'|'msdos')` - Quick full-disk partition

**Common GPT Type GUIDs:**
- EFI System: `C12A7328-F81F-11D2-BA4B-00A0C93EC93B`
- Linux filesystem: `0FC63DAF-8483-4772-8E79-3D69D8477DE4`
- Linux swap: `0657FD6D-A4AB-43C4-84E5-0933C84B4F4F`
- Linux LVM: `E6D6D379-F507-44C2-A23C-238F2A3DF928`

### 03_lvm_management.py
**Demonstrates:** LVM (Logical Volume Manager) operations

- Creating physical volumes (PV)
- Creating volume groups (VG)
- Creating logical volumes (LV)
- Resizing logical volumes
- Creating filesystems on LVs
- Cleaning up LVM stack

**Requirements:**
- LVM tools (lvm2) must be installed: `sudo dnf install lvm2`

**Usage:**
```bash
# Create test image (recommend at least 2GB)
qemu-img create -f qcow2 test-lvm.qcow2 2G
python 03_lvm_management.py test-lvm.qcow2
```

**Key APIs:**
- `pvcreate([devices])` - Initialize physical volumes
- `vgcreate(name, pvs)` - Create volume group
- `lvcreate(name, vg, size_mb=N)` - Create LV with size in MB
- `lvcreate(name, vg, extents='50%FREE')` - Create LV with percentage
- `lvresize(lv_path, size_mb)` - Resize logical volume
- `lvremove(lv_path, force=True)` - Remove logical volume
- `vgremove(vg_name, force=True)` - Remove volume group
- `pvs()`, `vgs()`, `lvs()` - List LVM components

**LVM Hierarchy:**
```
Physical Volumes (PV) → Volume Groups (VG) → Logical Volumes (LV)
```

### 04_config_management_augeas.py
**Demonstrates:** Configuration file editing with Augeas

- Modifying /etc/fstab entries
- Editing SSH daemon configuration
- Pattern matching for bulk operations
- Inserting and removing configuration entries
- Using Augeas variables for complex queries

**Requirements:**
- python-augeas library: `pip install python-augeas`
- augeas system packages: `sudo dnf install augeas augeas-libs`

**Usage:**
```bash
python 04_config_management_augeas.py /path/to/vm.qcow2
```

**Key APIs:**
- `aug_init()` - Initialize Augeas with guest filesystem
- `aug_get(path)` - Get configuration value
- `aug_set(path, value)` - Set configuration value
- `aug_match(pattern)` - Find paths matching pattern
- `aug_insert(path, label, before)` - Insert new entry
- `aug_rm(path)` - Remove entry/entries
- `aug_save()` - Save all changes to disk
- `aug_close()` - Close Augeas
- `aug_defvar(name, expr)` - Define variable
- `aug_defnode(name, expr, value)` - Define node variable

**Supported Configuration Files:**
- /etc/fstab - Filesystem mounts
- /etc/ssh/sshd_config - SSH daemon
- /etc/hosts - Host entries
- /etc/resolv.conf - DNS configuration
- /etc/systemd/system/*.service - Systemd units
- And 100+ more formats

### 05_archive_backup_operations.py
**Demonstrates:** Archive creation and block device operations

- Creating tar archives from VM directories
- Extracting tar archives to VM
- Using compression (gzip, bzip2, xz)
- Querying block device information
- Block-level copying with dd
- Complete backup/restore workflows

**Usage:**
```bash
python 05_archive_backup_operations.py /path/to/vm.qcow2
```

**Key APIs:**
- `tar_out(directory, tarfile, compress=None)` - Create archive from VM
- `tar_in(tarfile, directory, compress=None)` - Extract archive to VM
- `tgz_out(directory, tarfile)` - Create gzipped tar (convenience)
- `tgz_in(tarfile, directory)` - Extract gzipped tar (convenience)
- `blockdev_getsize64(device)` - Get device size in bytes
- `blockdev_getsz(device)` - Get device size in 512-byte sectors
- `dd_copy(src, dest, blocksize=512, count=None)` - Block-level copy

**Compression Options:**
- `None` - No compression (fastest, largest)
- `'gzip'` - Good balance of speed and size
- `'bzip2'` - Better compression, slower
- `'xz'` - Best compression, slowest

## Running the Examples

All examples follow a similar pattern:

1. **Check requirements** - Ensure necessary tools are installed
2. **Provide VM image path** - Use existing VM or create test image
3. **Read warnings** - Some examples modify the disk image
4. **Review output** - Each example provides detailed logging

## Common Patterns

### Error Handling
All examples use proper error handling and provide clear error messages when operations fail.

### Logging
Examples use Python's logging module with INFO level for normal operations and DEBUG for detailed troubleshooting.

### Context Managers
All examples use VMCraft with context managers (`with VMCraft(...) as g:`) to ensure proper resource cleanup.

### Caching
Examples demonstrate caching features where applicable (`use_cache=True` parameter).

## Use Cases

These examples demonstrate real-world VM management scenarios:

1. **Performance Optimization** - Parallel operations and caching
2. **Disk Management** - Partition and LVM operations
3. **Configuration Management** - Consistent config file editing
4. **Backup and Restore** - Archive and block-level operations
5. **VM Customization** - Partition layouts, LVM volumes, configurations

## Contributing

When adding new examples:

1. Follow the existing structure (numbered files, clear descriptions)
2. Include comprehensive docstrings
3. Provide usage examples in comments
4. Handle errors gracefully
5. Include a summary section at the end
6. Update this README

## Related Documentation

- [VMCraft API Documentation](../../docs/09-VMCraft.md)
- [Migration Quick Reference](../../docs/21-Migration-Quick-Reference.md)
- [Systemd Integration Examples](../systemd_migration/)

## License

All examples are licensed under Apache-2.0.
