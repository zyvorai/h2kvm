# VMCraft - Modular Disk Image Manipulation Library

VMCraft is a pure Python library for VM disk image manipulation, providing enterprise-grade guest filesystem access with native Linux tools.

## Performance Highlights (v2.2.0+)

**Enterprise LVM Improvements:**
- ✅ **7x Faster LVM Activation** - 0.71s (enterprise-grade performance)
- ✅ **100% Host Protection** - Device-filtered VG activation prevents corruption
- ✅ **Production Validated** - RHEL 8.8 and openSUSE Leap 15.4 tested
- ✅ **Safe Deactivation** - Automatic cleanup with VG tracking

See [LVM Enterprise Improvements](../../../../docs/LVM_AND_ENTERPRISE_IMPROVEMENTS.md) for technical details.

## Architecture

The VMCraft library is organized into focused modules, each with a specific responsibility:

```
h2kvm/core/vmcraft/
├── __init__.py              # Public API exports
├── main.py                  # Main VMCraft class (orchestrator)
├── _utils.py                # Shared utilities
│
├── nbd.py                   # NBD device management
├── storage.py               # Storage stack (LVM, LUKS, RAID, ZFS)
├── mount.py                 # Filesystem mounting
├── file_ops.py              # File operations (read, write, find, etc.)
│
├── inspection.py            # OS detection orchestration
├── linux_detection.py       # Linux distribution detection
├── windows_detection.py     # Windows version detection
│
├── windows_registry.py      # Windows registry operations
├── windows_drivers.py       # Windows driver injection
│
├── backup.py                # Backup and restore
├── security.py              # Security auditing
└── optimization.py          # Disk optimization and forensics
```

## Module Overview

### Core Infrastructure

#### `main.py` - VMCraft Class
The main orchestrator that coordinates all other modules. Provides the high-level API for:
- Disk image lifecycle (add, launch, shutdown, close)
- Context manager support
- Performance metrics
- Backend information

#### `nbd.py` - NBD Device Management
Manages Network Block Device (NBD) connections to disk images:
- Find free NBD devices
- Connect/disconnect disk images via qemu-nbd
- Partition discovery
- Safe cleanup

**Class**: `NBDDeviceManager`

#### `storage.py` - Storage Stack Activation
Activates storage technologies for disk access:
- LVM (Volume Groups, Logical Volumes)
- LUKS encryption
- MD RAID
- ZFS pools

**Classes**: `StorageStackActivator`, `LVMActivator`, `LUKSUnlocker`, `MDRaidAssembler`, `ZFSImporter`

#### `mount.py` - Filesystem Mounting
Handles filesystem mounting with intelligent fallbacks:
- Read-only and read-write mounts
- NTFS support (via ntfs-3g)
- FAT32/exFAT support
- Mount ladders (retry with different options)
- Mount point tracking

**Class**: `MountManager`

#### `file_ops.py` - File Operations
Complete file operation API:
- Basic: `is_file()`, `is_dir()`, `exists()`, `read_file()`, `cat()`, `write()`
- Transfer: `upload()`, `download()`
- Directory: `ls()`, `find()`, `find_files()`
- Manipulation: `mkdir_p()`, `chmod()`, `ln_sf()`, `cp()`, `rm_f()`, `touch()`
- Advanced: `checksum()`, `file_age()`, `set_permissions()`, `set_owner()`
- Filesystem: `list_filesystems()`, `list_partitions()`, `vfs_type()`, `vfs_uuid()`, `vfs_label()`

**Class**: `FileOperations`

### OS Detection

#### `inspection.py` - OS Inspection Orchestration
Coordinates OS detection across partitions:
- Scan partitions for root filesystems
- Detect Linux vs Windows
- Cache inspection results
- Comprehensive logging

**Class**: `OSInspector`

#### `linux_detection.py` - Linux Distribution Detection
Detects all major Linux distributions:
- **Detection methods** (priority order):
  1. `/etc/os-release` (systemd standard)
  2. `/etc/lsb-release` (LSB standard)
  3. Distribution-specific files
  4. `/etc/issue` (fallback)

- **Supported distributions**:
  - Red Hat family: RHEL, Fedora, CentOS, Rocky, AlmaLinux, Oracle Linux
  - SUSE family: SLES, openSUSE (Leap, Tumbleweed)
  - Debian family: Debian, Ubuntu
  - Others: Arch, Gentoo, Alpine, Slackware, Photon OS

**Class**: `LinuxDetector`

#### `windows_detection.py` - Windows Version Detection
Detects all Windows versions via registry parsing:
- **Detection methods** (priority order):
  1. ProductName matching (most reliable)
  2. Build number (Windows 10/11 split: >=22000 = Win11)
  3. Major/minor version (legacy Windows)

- **Supported versions**:
  - Client: Windows 12, 11, 10, 8.1, 8, 7, Vista, XP, 2000, NT
  - Server: Server 2025, 2022, 2019, 2016, 2012 R2, 2012, 2008 R2, 2008, 2003

- **Registry parsing**: Uses `hivexget` to read SOFTWARE hive offline

**Class**: `WindowsDetector`

### Windows-Specific Operations

#### `windows_registry.py` - Windows Registry Operations
Provides offline Windows registry access:
- Read registry values
- Write registry values
- List keys and subkeys
- List values
- Case-insensitive path resolution

**Class**: `WindowsRegistryManager`

**Registry support**:
- SOFTWARE hive
- SYSTEM hive
- SAM hive (future)

#### `windows_drivers.py` - Windows Driver Injection
Injects drivers into Windows DriverStore:
- Locate DriverStore path (case-insensitive)
- Find INF files
- Copy driver packages
- Prepare for installation

**Class**: `WindowsDriverInjector`

### Operational Tools

#### `backup.py` - Backup and Restore
Archive-based backup and restore operations:
- Tar-based backups with compression (gzip, bzip2, xz)
- Selective file backup
- Full restore
- Template creation

**Class**: `BackupManager`

#### `security.py` - Security Auditing
Security analysis and package detection:
- Find world-writable files
- Find setuid/setgid files
- Detect package managers (rpm, deb, apk, pacman)
- Extract network configuration
- Windows service management

**Class**: `SecurityAuditor`

#### `optimization.py` - Disk Optimization
Disk forensics and cleanup:
- Analyze disk usage
- Find large files
- Find duplicates (by checksum)
- Find recently modified files
- Find empty directories
- Cleanup temp files

**Class**: `DiskOptimizer`

## Usage Examples

### Basic Workflow

```python
from h2kvm.core.vmcraft import VMCraft

# Create instance
g = VMCraft(python_return_dict=True)

# Add disk image
g.add_drive_opts("/path/to/disk.vmdk", readonly=True, format="vmdk")

# Launch (connect NBD, activate storage)
g.launch()

# Inspect operating systems
roots = g.inspect_os()
for root in roots:
    print(f"Type: {g.inspect_get_type(root)}")
    print(f"Product: {g.inspect_get_product_name(root)}")

# Mount root filesystem
mounts = g.inspect_get_mountpoints(roots[0])
for mp, dev in mounts.items():
    g.mount(dev, mp)

# Read files
content = g.cat("/etc/hostname")
print(f"Hostname: {content}")

# Write files
g.write("/etc/motd", "Welcome to VMCraft!\n")

# Cleanup
g.umount_all()
g.shutdown()
g.close()
```

### Context Manager

```python
from h2kvm.core.vmcraft import VMCraft

with VMCraft() as g:
    g.add_drive_opts("/path/to/disk.vmdk", readonly=True)
    g.launch()

    roots = g.inspect_os()
    for root in roots:
        os_type = g.inspect_get_type(root)
        product = g.inspect_get_product_name(root)
        print(f"{os_type}: {product}")

    # Automatic cleanup on exit
```

### Windows Registry Operations

```python
with VMCraft() as g:
    g.add_drive_opts("/path/to/windows.vmdk", readonly=False)
    g.launch()

    # Read registry value
    product = g.win_registry_read(
        "SOFTWARE",
        r"Microsoft\Windows NT\CurrentVersion",
        "ProductName"
    )
    print(f"Windows: {product}")

    # Write registry value
    g.win_registry_write(
        "SOFTWARE",
        r"Microsoft\MyApp",
        "Version",
        "1.0.0"
    )
```

### Driver Injection

```python
with VMCraft() as g:
    g.add_drive_opts("/path/to/windows.vmdk", readonly=False)
    g.launch()

    # Inject VirtIO driver
    result = g.win_inject_driver("/path/to/virtio-win/viostor/w11/amd64")

    if result["ok"]:
        print(f"Driver injected: {result['destination']}")
        print(f"Files copied: {result['files_copied']}")
    else:
        print(f"Error: {result['error']}")
```

### Backup and Restore

```python
with VMCraft() as g:
    g.add_drive_opts("/path/to/disk.vmdk", readonly=True)
    g.launch()

    # Backup critical files
    result = g.backup_files(
        paths=["/etc", "/var/log"],
        dest_archive="/tmp/backup.tar.gz",
        compression="gzip"
    )
    print(f"Backed up {result['files_archived']} files ({result['size_bytes']} bytes)")

    # Restore from backup
    result = g.restore_files("/tmp/backup.tar.gz", dest_path="/restore")
    print(f"Restored {result['files_extracted']} files")
```

### Security Audit

```python
with VMCraft() as g:
    g.add_drive_opts("/path/to/disk.vmdk", readonly=True)
    g.launch()

    # Audit permissions
    audit = g.audit_permissions("/")

    print(f"World-writable files: {audit['world_writable_count']}")
    print(f"Setuid files: {audit['setuid_count']}")
    print(f"Setgid files: {audit['setgid_count']}")

    for file in audit['world_writable'][:10]:
        print(f"  {file}")
```

### Disk Optimization

```python
with VMCraft() as g:
    g.add_drive_opts("/path/to/disk.vmdk", readonly=True)
    g.launch()

    # Analyze disk usage
    usage = g.analyze_disk_usage("/", top_n=20)
    print(f"Total size: {usage['total_bytes']} bytes")
    print(f"Total files: {usage['file_count']}")

    # Find large files
    large = g.find_large_files(min_size_mb=100)
    for file in large[:10]:
        print(f"{file['size_mb']:.1f} MB: {file['path']}")

    # Find duplicates
    dupes = g.find_duplicates(min_size_mb=1)
    print(f"Found {len(dupes)} sets of duplicate files")
```

## API Compatibility

VMCraft maintains API compatibility with the standard guestfs interface:
- Standard guestfs method signatures
- `python_return_dict=True` semantics preserved
- Factory pattern for backend selection

```python
from h2kvm.core.guestfs_factory import create_guestfs

# Use VMCraft backend (default)
g = create_guestfs(backend='vmcraft')

# Or auto-select
g = create_guestfs(backend='auto')
```

## Performance

VMCraft delivers high performance for guest filesystem operations:
- **NBD connection**: ~0.77s
- **LVM activation**: ~0.71s
- **Inspection**: ~0.3s
- **Total launch time**: ~1.5s

**LVM Performance** (RHEL 8.8 test):
```
Operation          VMCraft
NBD Connection     0.77s
LVM Activation     0.71s
Total Ready Time   1.49s
```

Performance metrics available via:
```python
metrics = g.get_performance_metrics()
print(f"Launch time: {metrics['launch_time_s']:.2f}s")
print(f"NBD connect: {metrics['nbd_connect_time_s']:.2f}s")
print(f"LVM activate: {metrics['lvm_activate_time_s']:.2f}s")
```

See [LVM Test Results](../../../../docs/test-results/LVM_ENTERPRISE_IMPROVEMENTS_TEST_RESULTS.md) for detailed benchmarks.

## System Dependencies

**Required**:
- `qemu-utils` - Provides qemu-nbd
- `util-linux` - Provides mount, umount, lsblk, blkid
- `lvm2` - LVM support
- `cryptsetup` - LUKS encryption support

**For Windows support**:
- `ntfs-3g` - NTFS write support
- `libhivex-bin` - Windows registry tools (hivexget, hivexregedit)

**Optional**:
- `mdadm` - Software RAID support
- `zfsutils-linux` - ZFS support
- `exfat-fuse` - exFAT support
- `kpartx` - Partition mapping (alternative to partprobe)

## Development

### Adding New Modules

To add new functionality:

1. Create new module in `h2kvm/core/vmcraft/`
2. Create class with focused responsibility
3. Use dependency injection for other managers
4. Add to `main.py` initialization
5. Export from `__init__.py` if public API
6. Add tests in `tests/unit/test_core/test_vmcraft/`
7. Update documentation

### Module Guidelines

- **Single Responsibility**: Each module should have one clear purpose
- **Dependency Injection**: Pass dependencies via constructor
- **Logging**: Use `self.logger` for all logging
- **Error Handling**: Use descriptive exceptions
- **Documentation**: Comprehensive docstrings with examples
- **Type Hints**: Full type annotations
- **SPDX Headers**: Include license headers

## Testing

```bash
# Unit tests
pytest tests/unit/test_core/test_vmcraft/ -v

# Integration tests
pytest tests/integration/test_core/test_vmcraft/ -v

# Specific module
pytest tests/unit/test_core/test_vmcraft/test_linux_detection.py -v
```

## Migration from Monolithic vmcraft.py

The original `vmcraft.py` has been refactored into this modular structure. The public API remains identical, ensuring backward compatibility.

**Old import** (still works):
```python
from h2kvm.core.vmcraft import VMCraft
```

**New structure** (transparent):
```python
from h2kvm.core.vmcraft import VMCraft  # Actually imports from __init__.py
```

All functionality has been preserved. The refactoring improves:
- **Maintainability**: Easier to find and modify code
- **Testability**: Modules can be tested in isolation
- **Extensibility**: Simple to add new features
- **Team Development**: Multiple developers can work simultaneously

## What's Next?

### 🚀 I want to use VMCraft
→ See usage examples above and [API Reference](../../../../docs/reference/api/README.md)

### 📊 I want performance details
→ Read [LVM Enterprise Improvements](../../../../docs/LVM_AND_ENTERPRISE_IMPROVEMENTS.md)

### 🧪 I want test results
→ Check [LVM Test Results](../../../../docs/test-results/LVM_ENTERPRISE_IMPROVEMENTS_TEST_RESULTS.md)

### 🔧 I want to contribute
→ See [Module Guidelines](#module-guidelines) and [Contributing Guide](../../../../docs/development/contributing.md)

## License

SPDX-License-Identifier: Proprietary (Zyvor AI Labs)

## References

- [VMCraft OS Detection](../../../VMCRAFT_OS_DETECTION.md) - Comprehensive OS detection capabilities
- [LVM Enterprise Improvements](../../../../docs/LVM_AND_ENTERPRISE_IMPROVEMENTS.md) - Performance and safety features
- [LVM Test Results](../../../../docs/test-results/LVM_ENTERPRISE_IMPROVEMENTS_TEST_RESULTS.md) - Production validation
- [qemu-nbd](https://www.qemu.org/docs/master/tools/qemu-nbd.html) - NBD server documentation

---

**Last Updated**: February 14, 2026
**Version**: 0.2.2
**LVM Performance**: 7x faster with 100% host protection
