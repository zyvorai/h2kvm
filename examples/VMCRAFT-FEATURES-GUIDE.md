# VMCraft Complete Features Guide

This guide provides a comprehensive overview of all VMCraft features and how to use them through the provided examples.

## Table of Contents

1. [VMCraft Overview](#vmcraft-overview)
2. [Feature Categories](#feature-categories)
3. [Example Scripts Map](#example-scripts-map)
4. [Quick Start Guide](#quick-start-guide)
5. [Advanced Workflows](#advanced-workflows)

---

## VMCraft Overview

**VMCraft** is a pure Python VM disk manipulation library with **395+ methods** covering:
- Filesystem operations
- Storage management (partitions, LVM)
- Configuration management (Augeas)
- Systemd integration
- Performance optimizations
- Archive and backup operations

### Version History
- **v9.1** (Dec 2024): Core filesystem and storage operations
- **v9.2** (Jan 2025): Systemd integration (52 new APIs)
- **Current**: 395+ methods, 62 modules, 30,000+ lines of code

---

## Feature Categories

### 1. Performance & Robustness 🚀

**Features:**
- Parallel mount operations (2-3x faster)
- Partition list caching
- Blkid metadata caching (120s TTL)
- NBD connection retry logic (3 attempts with backoff)
- Mount fallback strategies (4 strategies)

**Example:** `advanced_vmcraft/01_parallel_mount_performance.py`

**Key APIs:**
```python
# Parallel mounting (2-3x faster)
g.mount_all_parallel(devices, max_workers=4)

# Caching for performance
partitions = g.list_partitions(use_cache=True)
metadata = g.blkid(device, use_cache=True)

# Fallback for damaged filesystems
g.mount_with_fallback(device, mountpoint)

# Cache management
g.invalidate_partition_cache(device)
```

**Use Cases:**
- Multi-partition VM migrations
- Performance-critical operations
- Handling problematic filesystems

---

### 2. Partition Management 💾

**Features:**
- Create partition tables (GPT, MBR/MSDOS)
- Add/delete partitions
- Set partition names (GPT)
- Set GPT type GUIDs
- Query partition information
- Quick disk initialization

**Example:** `advanced_vmcraft/02_partition_management.py`

**Key APIs:**
```python
# Initialize partition table
g.part_init(device, "gpt")

# Add partition (sectors)
g.part_add(device, "primary", start_sect, end_sect)

# Delete partition
g.part_del(device, partnum)

# Set GPT metadata
g.part_set_name(device, partnum, "EFI System")
g.part_set_gpt_type(device, partnum, guid)

# Quick full-disk partition
g.part_disk(device, "gpt")

# Query
parttype = g.part_get_parttype(device)
```

**Common GPT Type GUIDs:**
- EFI System: `C12A7328-F81F-11D2-BA4B-00A0C93EC93B`
- Linux filesystem: `0FC63DAF-8483-4772-8E79-3D69D8477DE4`
- Linux swap: `0657FD6D-A4AB-43C4-84E5-0933C84B4F4F`
- Linux LVM: `E6D6D379-F507-44C2-A23C-238F2A3DF928`

**Use Cases:**
- VM disk customization
- Disk expansion
- Multi-boot setup
- Disk conversion (MBR ↔ GPT)

---

### 3. LVM Management 📦

**Features:**
- Create physical volumes (PV)
- Create volume groups (VG)
- Create logical volumes (LV)
- Resize logical volumes
- Remove LVM components
- List LVM components

**Requirements:** `lvm2` package must be installed

**Example:** `advanced_vmcraft/03_lvm_management.py`

**Key APIs:**
```python
# LVM stack: PV → VG → LV

# Create physical volume
g.pvcreate(["/dev/sda1"])

# Create volume group
g.vgcreate("vg_data", ["/dev/sda1"])

# Create logical volume (size or percentage)
g.lvcreate("lv_root", "vg_data", size_mb=10240)
g.lvcreate("lv_home", "vg_data", extents="50%FREE")

# Resize logical volume
g.lvresize("/dev/vg_data/lv_home", size_mb=20480)

# List components
pvs = g.pvs()
vgs = g.vgs()
lvs = g.lvs()

# Cleanup
g.lvremove("/dev/vg_data/lv_home", force=True)
g.vgremove("vg_data", force=True)
```

**Use Cases:**
- Flexible storage management
- Volume snapshots (with lvs_snapshot)
- Dynamic volume sizing
- Storage pooling

---

### 4. Systemd Integration ⚙️

**Version:** v9.2 (52 new APIs)

**Features:**
- Service management (enable/disable/start/stop)
- systemd-networkd configuration
- Journal log access and analysis
- Unit file creation and management
- Boot performance analysis

**Examples:**
- `systemd_migration/01_vmware_to_kvm_services.py` - Service migration
- `systemd_migration/02_network_config_migration.py` - Network migration
- `systemd_migration/03_boot_issue_debugging.py` - Boot debugging

#### 4.1 Service Management

**Key APIs:**
```python
# Check if systemd is available
if g.systemd_is_available():
    # Enable/disable services
    g.systemd_service_enable("qemu-guest-agent")
    g.systemd_service_disable("vmtoolsd")

    # Bulk operations
    g.systemd_services_disable_multiple(["svc1", "svc2"])
    g.systemd_services_mask(["vmware-tools", "vmtoolsd"])

    # Query services
    services = g.systemd_list_services(state="active")
    failed = g.systemd_list_failed_services()

    # Reload daemon
    g.systemd_daemon_reload()
```

#### 4.2 Network Configuration

**Key APIs:**
```python
# Migrate from ifcfg to networkd
result = g.networkd_migrate_from_ifcfg("eth0")

# Create network file
g.networkd_create_network_file(
    name="10-eth0",
    match={"Name": "eth0"},
    network={"Address": "192.168.1.100/24"}
)

# Create bridge for KVM
g.networkd_create_bridge_network("br0", ["eth0"])

# Enable systemd-networkd
g.networkd_enable_networkd()

# List and parse network files
files = g.networkd_list_network_files()
parsed = g.networkd_parse_network_file("10-eth0.network")
```

#### 4.3 Journal Analysis

**Key APIs:**
```python
# Get journal entries
logs = g.journal_get(lines=100, priority="err")

# Service-specific logs
svc_logs = g.journal_get_service("sshd", lines=50)

# Boot logs
boot_logs = g.journal_get_since_boot(boot_offset=0)

# List boots
boots = g.journal_list_boots()

# Get boot ID
boot_id = g.journal_get_boot_id()

# Disk usage
usage = g.journal_get_disk_usage()
```

#### 4.4 Boot Performance

**Key APIs:**
```python
# Boot performance metrics
perf = g.units_analyze_boot_performance()
# Returns: kernel_time, userspace_time, boot_time

# Critical boot path
chain = g.units_analyze_critical_chain()

# Slowest services
blame = g.units_analyze_blame()
# Returns: list of {time, name} for each service
```

**Use Cases:**
- VMware to KVM service migration
- Network configuration modernization
- Boot issue diagnostics
- Performance optimization
- Security hardening

---

### 5. Configuration Management (Augeas) 📝

**Features:**
- Edit configuration files consistently
- Support for 100+ file formats
- Pattern matching and bulk updates
- Atomic saves
- Preserve file structure and comments

**Requirements:** `python-augeas` and `augeas` packages

**Example:** `advanced_vmcraft/04_config_management_augeas.py`

**Key APIs:**
```python
# Initialize Augeas
g.aug_init()

# Read configuration
value = g.aug_get("/files/etc/fstab/*/file")

# Set configuration
g.aug_set("/files/etc/ssh/sshd_config/PermitRootLogin", "no")

# Pattern matching
entries = g.aug_match("/files/etc/fstab/*")

# Insert new entry
g.aug_insert(path, label, before=True)

# Remove entries
count = g.aug_rm("/files/etc/fstab/*[file='/old']")

# Save changes (atomic)
g.aug_save()

# Close Augeas
g.aug_close()
```

**Supported Files:**
- `/etc/fstab` - Filesystem mounts
- `/etc/ssh/sshd_config` - SSH daemon
- `/etc/hosts` - Host entries
- `/etc/resolv.conf` - DNS configuration
- `/etc/systemd/system/*.service` - Systemd units
- And 100+ more formats

**Use Cases:**
- Consistent config editing across distributions
- Automated security hardening
- Network reconfiguration during migration
- Bulk configuration updates

---

### 6. Archive & Backup Operations 📦

**Features:**
- Create tar archives from VM directories
- Extract tar archives to VM
- Multiple compression formats (gzip, bzip2, xz)
- Block device information queries
- dd-based block copying

**Example:** `advanced_vmcraft/05_archive_backup_operations.py`

**Key APIs:**
```python
# Create archive with compression
g.tar_out("/etc", "etc-backup.tar.xz", compress="xz")

# Extract archive
g.tar_in("backup.tar.gz", "/restore", compress="gzip")

# Convenience wrappers
g.tgz_out("/var/log", "logs.tgz")
g.tgz_in("data.tgz", "/data")

# Block device info
size_bytes = g.blockdev_getsize64(device)
size_sectors = g.blockdev_getsz(device)

# Block-level copy
g.dd_copy(src, dest, blocksize=512, count=None)
```

**Compression Options:**
- `None` - No compression (fastest, largest)
- `"gzip"` - Good balance of speed and size
- `"bzip2"` - Better compression, slower
- `"xz"` - Best compression, slowest

**Use Cases:**
- VM backup and restore
- Configuration migration
- Log collection
- Block-level disk cloning

---

## Example Scripts Map

### Basic Examples

| Example | Features | Use Case |
|---------|----------|----------|
| `vmcraft_filesystem_apis.py` | Basic filesystem operations | Learning VMCraft basics |

### Systemd Integration Examples

| Example | Features | Use Case |
|---------|----------|----------|
| `systemd_migration/01_vmware_to_kvm_services.py` | Service migration | VMware→KVM conversion |
| `systemd_migration/02_network_config_migration.py` | Network migration | Networkd setup |
| `systemd_migration/03_boot_issue_debugging.py` | Boot debugging | Troubleshooting |

### Advanced Feature Examples

| Example | Features | Use Case |
|---------|----------|----------|
| `advanced_vmcraft/01_parallel_mount_performance.py` | Performance optimization | Fast migrations |
| `advanced_vmcraft/02_partition_management.py` | Partition operations | Disk customization |
| `advanced_vmcraft/03_lvm_management.py` | LVM operations | Flexible storage |
| `advanced_vmcraft/04_config_management_augeas.py` | Config editing | Consistent configs |
| `advanced_vmcraft/05_archive_backup_operations.py` | Backup/restore | Disaster recovery |

### Master Example

| Example | Features | Use Case |
|---------|----------|----------|
| `enterprise_migration_master.py` | **ALL features** | Complete enterprise migration |

---

## Quick Start Guide

### 1. Basic VM Inspection

```python
from hyper2kvm.core.vmcraft.main import VMCraft

with VMCraft("/path/to/vm.qcow2") as g:
    # Detect OS
    roots = g.inspect_os()
    root = roots[0]

    # Get OS info
    os_type = g.inspect_get_type(root)
    distro = g.inspect_get_distro(root)

    # List partitions
    partitions = g.list_partitions()

    # Mount and inspect
    mountpoints = g.inspect_get_mountpoints(root)
    for mp, device in mountpoints.items():
        g.mount(device, mp)

    # List files
    files = g.ls("/etc")
```

### 2. VMware to KVM Migration

```python
with VMCraft("/vmware/vm.vmdk") as g:
    # Mount filesystem
    roots = g.inspect_os()
    mountpoints = g.inspect_get_mountpoints(roots[0])
    for mp, device in mountpoints.items():
        g.mount(device, mp)

    # Disable VMware services
    vmware_services = ["vmtoolsd", "vmware-tools"]
    g.systemd_services_disable_multiple(vmware_services)
    g.systemd_services_mask(vmware_services)

    # Enable KVM services
    g.systemd_service_enable("qemu-guest-agent")

    # Reload systemd
    g.systemd_daemon_reload()
```

### 3. Performance-Optimized Migration

```python
with VMCraft("/path/to/vm.qcow2") as g:
    # Use cached partition listing
    partitions = g.list_partitions(use_cache=True)

    # Prepare mount targets
    mount_targets = [
        (partitions[0], "/boot"),
        (partitions[1], "/"),
        (partitions[2], "/home"),
    ]

    # Mount in parallel (2-3x faster)
    results = g.mount_all_parallel(mount_targets, max_workers=4)
```

---

## Advanced Workflows

### Complete Enterprise Migration

See `enterprise_migration_master.py` for a comprehensive example that integrates:

1. **Pre-migration inspection** with caching
2. **Parallel mounting** for performance
3. **Service migration** (VMware → KVM)
4. **Network configuration** migration
5. **Security hardening** with Augeas
6. **Boot validation** and performance analysis
7. **Backup creation** with compression
8. **Comprehensive reporting**

**Run it:**
```bash
python enterprise_migration_master.py /vmware/rhel9.vmdk /output/kvm
```

### Custom Workflows

Build your own workflows by combining features:

```python
with VMCraft("/path/to/vm.qcow2") as g:
    # 1. Performance: Use caching
    partitions = g.list_partitions(use_cache=True)

    # 2. Storage: Manage partitions
    g.part_init(device, "gpt")
    g.part_add(device, "primary", 2048, -1)

    # 3. LVM: Create volumes
    g.pvcreate(["/dev/sda1"])
    g.vgcreate("vg_data", ["/dev/sda1"])
    g.lvcreate("lv_root", "vg_data", extents="100%FREE")

    # 4. Filesystem: Create and mount
    g.mkfs("ext4", "/dev/vg_data/lv_root")
    g.mount("/dev/vg_data/lv_root", "/")

    # 5. Config: Edit with Augeas
    g.aug_init()
    g.aug_set("/files/etc/fstab/*/passno", "1")
    g.aug_save()
    g.aug_close()

    # 6. Systemd: Manage services
    g.systemd_service_enable("my-app")

    # 7. Backup: Create archive
    g.tar_out("/etc", "etc-backup.tar.xz", compress="xz")
```

---

## Best Practices

### 1. Always Use Context Managers

```python
# Good
with VMCraft(disk_path) as g:
    # Work with VM
    pass

# Bad
g = VMCraft(disk_path)
g.launch()
# ... (might leak resources if exception occurs)
```

### 2. Enable Caching for Performance

```python
# Enable caching for repeated operations
partitions = g.list_partitions(use_cache=True)
metadata = g.blkid(device, use_cache=True)

# Invalidate cache after modifications
g.invalidate_partition_cache()
```

### 3. Use Parallel Operations When Possible

```python
# Parallel mounting (2-3x faster)
results = g.mount_all_parallel(mount_targets, max_workers=4)
```

### 4. Handle Errors Gracefully

```python
try:
    g.mount(device, mountpoint)
except RuntimeError:
    # Try fallback strategies
    success = g.mount_with_fallback(device, mountpoint)
```

### 5. Use Audit Dicts for Validation

```python
result = g.systemd_service_enable("myservice")
if result["ok"]:
    print(f"Service enabled: {result['service']}")
else:
    print(f"Failed: {result['error']}")
```

---

## Learning Path

1. **Start here:** `vmcraft_filesystem_apis.py`
   - Learn basic filesystem operations

2. **Performance:** `advanced_vmcraft/01_parallel_mount_performance.py`
   - Understand caching and parallel operations

3. **Storage:** `advanced_vmcraft/02_partition_management.py` → `03_lvm_management.py`
   - Master partition and LVM management

4. **Configuration:** `advanced_vmcraft/04_config_management_augeas.py`
   - Learn Augeas configuration editing

5. **Systemd:** `systemd_migration/` examples
   - Master systemd integration

6. **Integration:** `enterprise_migration_master.py`
   - See everything working together

---

## Additional Resources

- **API Documentation:** `docs/09-VMCraft.md`
- **Migration Quick Reference:** `docs/21-Migration-Quick-Reference.md`
- **CHANGELOG:** `CHANGELOG.md` (VMCraft v9.2 release notes)

---

## Summary

VMCraft provides **395+ methods** across these categories:

- ✅ **Performance** - Parallel ops, caching, retry logic
- ✅ **Storage** - Partitions, LVM, filesystems
- ✅ **Configuration** - Augeas for consistent editing
- ✅ **Systemd** - Services, networkd, journal, units
- ✅ **Backup** - Archives, compression, block ops
- ✅ **Security** - SSH hardening, service management

All features work together seamlessly for enterprise-grade VM migrations!
