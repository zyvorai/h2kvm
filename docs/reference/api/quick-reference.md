# hyper2kvm API Quick Reference

Quick reference guide for the most commonly used APIs in hyper2kvm.

## VMCraft - Disk Image Analysis

### Basic Usage
```python
from hyper2kvm.vmcraft.main import VMCraft

g = VMCraft()
g.add_drive_opts('/path/to/disk.vmdk', readonly=True)
g.launch()

# ... use APIs ...

g.shutdown()
```

### OS Detection (8 APIs)
```python
# Detect operating systems
roots = g.inspect_os()  # ['/dev/sda2', ...]

# Get OS details
os_type = g.inspect_get_type(root)           # 'linux' or 'windows'
distro = g.inspect_get_distro(root)          # 'ubuntu', 'opensuse-leap', etc.
product = g.inspect_get_product_name(root)   # 'Ubuntu 22.04 LTS'
version_major = g.inspect_get_major_version(root)  # 22
version_minor = g.inspect_get_minor_version(root)  # 4
arch = g.inspect_get_arch(root)              # 'x86_64'

# Get mount structure
mountpoints = g.inspect_get_mountpoints(root)
# {'/': '/dev/sda2', '/boot': '/dev/sda1', ...}
```

### Filesystem Detection (4 APIs)
```python
# List all filesystems
filesystems = g.list_filesystems()
# {'/dev/sda1': 'ext4', '/dev/sda2': 'btrfs', '/dev/sda3': 'swap'}

# Get filesystem metadata
fs_type = g.vfs_type('/dev/sda1')      # 'ext4'
fs_uuid = g.vfs_uuid('/dev/sda1')      # 'abc-123-def-456'
fs_label = g.vfs_label('/dev/sda1')    # 'boot'
```

### Partition Operations (2 APIs)
```python
# Extract partition number
partnum = g.part_to_partnum('/dev/sda1')     # 1
partnum = g.part_to_partnum('/dev/nvme0n1p2') # 2

# Get parent device
parent = g.part_to_dev('/dev/sda1')          # '/dev/sda'
parent = g.part_to_dev('/dev/nvme0n1p2')     # '/dev/nvme0n1'
```

### Block Device Info (5 APIs)
```python
device = '/dev/sda'

# Get device size and geometry
size_bytes = g.blockdev_getsize64(device)    # 512000000000 (512 GB)
sector_size = g.blockdev_getss(device)       # 512
sector_count = g.blockdev_getsz(device)      # 1000000000
block_size = g.blockdev_getbsz(device)       # 4096

# Check read-only status
is_readonly = g.blockdev_getro(device)       # True/False
```

### Block Device Management (4 APIs)
```python
# Set device mode
g.blockdev_setrw(device)      # Set read-write
g.blockdev_setro(device)      # Set read-only

# Maintenance operations
g.blockdev_flushbufs(device)  # Flush buffers
g.blockdev_rereadpt(device)   # Re-read partition table
```

### Extended Attributes - ext2/3/4 (2 APIs)
```python
# Get file attributes
attrs = g.get_e2attrs('/etc/passwd')   # '-------------e--'

# Set file attributes
g.set_e2attrs('/tmp/file', 'i')            # Make immutable
g.set_e2attrs('/tmp/file', 'a')            # Make append-only
g.set_e2attrs('/tmp/file', 'i', clear=True) # Remove immutable
```

### Btrfs Operations (2 APIs)
```python
# Show Btrfs filesystem info
info = g.btrfs_filesystem_show('/dev/sda2')
# [{'label': '', 'uuid': 'abc-123', 'total_devices': '1'}]

# List Btrfs subvolumes
subvols = g.btrfs_subvolume_list('/dev/sda2')
# [{'id': '256', 'path': '@'}, {'id': '257', 'path': '@home'}]
```

### ZFS Operations (2 APIs)
```python
# List ZFS pools
pools = g.zfs_pool_list()
# ['tank', 'backup']

# List ZFS datasets
datasets = g.zfs_dataset_list('tank')
# [{'name': 'tank/home', 'used': '10G', 'avail': '90G', ...}]
```

### XFS Operations (5 APIs)
```python
device = '/dev/sda1'

# Get XFS filesystem info
info = g.xfs_info(device)
# {'blocksize': 4096, 'agcount': 4, 'inodesize': 512, ...}

# Modify XFS parameters
g.xfs_admin(device, label='mydata')

# Grow XFS filesystem
g.xfs_growfs('/mnt/xfs')

# Repair XFS filesystem
g.xfs_repair(device)

# Debug XFS filesystem
output = g.xfs_db(device, commands=['-c', 'sb 0', '-c', 'p'])
```

### NTFS Operations (1 API)
```python
# Probe NTFS filesystem
result = g.ntfs_3g_probe('/dev/sda1')       # 0 = OK, non-zero = issues
result = g.ntfs_3g_probe('/dev/sda1', rw=True)  # Test R/W capability
```

### Filesystem Statistics (1 API)
```python
# Get filesystem usage
stats = g.statvfs('/')
# {
#   'bsize': 4096,           # Block size
#   'blocks': 1000000,       # Total blocks
#   'bfree': 500000,         # Free blocks
#   'bavail': 450000,        # Available blocks
#   'files': 200000,         # Total inodes
#   'ffree': 150000,         # Free inodes
# }

# Calculate usage
total_gb = stats['blocks'] * stats['bsize'] / (1024**3)
free_gb = stats['bfree'] * stats['bsize'] / (1024**3)
used_gb = total_gb - free_gb
usage_percent = (used_gb / total_gb) * 100
```

## VMCraft - Systemd Integration

### Service Management (15 APIs)

```python
# List services
services = g.systemctl_list_units('service', state='active')
# [{'unit': 'sshd.service', 'active': 'active', 'sub': 'running', ...}]

# Check service status
is_active = g.systemctl_is_active('sshd.service')    # True/False
is_enabled = g.systemctl_is_enabled('sshd.service')  # 'enabled'/'disabled'
is_failed = g.systemctl_is_failed('sshd.service')    # True/False

# Get detailed status
status = g.systemctl_status('sshd.service')
# {'active': 'active', 'sub': 'running', 'description': '...', ...}

# Show service properties
props = g.systemctl_show('sshd.service')
# {'Type': 'notify', 'ExecStart': '/usr/sbin/sshd', ...}

# List failed services
failed = g.systemctl_list_failed()
# [{'unit': 'fail.service', 'active': 'failed', ...}]

# List timers
timers = g.systemctl_list_timers()
# [{'unit': 'backup.timer', 'next': '2026-01-27 00:00:00', ...}]

# List dependencies
deps = g.systemctl_list_dependencies('multi-user.target')
# ['basic.target', 'network.target', ...]

# Get default boot target
target = g.systemctl_get_default_target()  # 'multi-user.target'
```

### Log Analysis (8 APIs)

```python
# Query journal logs
logs = g.journalctl_query(unit='sshd.service', lines=100)

# Get boot history
boots = g.journalctl_list_boots()
# [{'offset': '0', 'boot_id': 'abc123...', 'time_range': '...'}]

# Get errors and warnings
errors = g.journalctl_get_errors(since='1 hour ago', lines=50)
warnings = g.journalctl_get_warnings(since='today', lines=50)

# Get journal disk usage
usage = g.journalctl_disk_usage()
# {'current_use': '512M', 'max_use': '4G'}

# Verify journal integrity
result = g.journalctl_verify()
```

### Performance Analysis (10 APIs)

```python
# Analyze boot time
timing = g.systemd_analyze_time()
# {'total': 15.5, 'kernel': 3.2, 'initrd': 2.1, 'userspace': 10.2}

# Show slowest services
blame = g.systemd_analyze_blame(lines=10)
# [{'time': '5.2s', 'unit': 'NetworkManager.service'}, ...]

# Show critical boot path
chain = g.systemd_analyze_critical_chain()

# Security analysis
security = g.systemd_analyze_security('sshd.service')
# [{'description': 'PrivateDevices=yes', 'exposure': '0.1'}, ...]

# Verify unit files
verify = g.systemd_analyze_verify('myapp.service')
```

### System Configuration (13 APIs)

```python
# Time/Date (timedatectl)
time_status = g.timedatectl_status()
# {'timezone': 'America/New_York', 'ntp': 'yes', ...}

timezones = g.timedatectl_list_timezones()
# ['America/New_York', 'Europe/London', ...]

# Hostname (hostnamectl)
hostname_info = g.hostnamectl_status()
# {'static_hostname': 'myserver', 'operating_system': 'Ubuntu 22.04', ...}

# Locale (localectl)
locale_status = g.localectl_status()
# {'system_locale': 'en_US.UTF-8', 'vc_keymap': 'us', ...}

locales = g.localectl_list_locales()
# ['en_US.UTF-8', 'de_DE.UTF-8', ...]

keymaps = g.localectl_list_keymaps()
# ['us', 'uk', 'de', ...]

# Sessions (loginctl)
sessions = g.loginctl_list_sessions()
# [{'session': '1', 'user': 'root', 'tty': 'tty1'}]

users = g.loginctl_list_users()
# [{'uid': '1000', 'user': 'ubuntu'}]
```

## Guest Inspector - VM Metadata

### Basic Usage
```python
from hyper2kvm.core.guest_inspector import GuestInspector

inspector = GuestInspector()
vm_info = inspector.inspect_vm('/path/to/disk.vmdk')
```

### VM Information Structure
```python
{
    'os_type': 'linux',                    # linux, windows, unknown
    'distro': 'ubuntu',                    # ubuntu, fedora, windows, etc.
    'product_name': 'Ubuntu 22.04 LTS',
    'version': '22.04',
    'architecture': 'x86_64',
    'hostname': 'myserver',
    'domain': 'example.com',

    'network_interfaces': [
        {
            'interface_name': 'eth0',
            'mac_address': '00:11:22:33:44:55',
            'ip_addresses': ['192.168.1.100'],
            'subnet_mask': '255.255.255.0',
            'gateway': '192.168.1.1',
        }
    ],

    'packages': [
        {
            'name': 'openssh-server',
            'version': '1:8.9p1-3ubuntu0.1',
            'architecture': 'amd64',
            'package_format': 'deb',
        }
    ],

    'users': [
        {
            'username': 'ubuntu',
            'uid': '1000',
            'gid': '1000',
            'home': '/home/ubuntu',
            'shell': '/bin/bash',
        }
    ],

    'applications': [
        {
            'name': 'Google Chrome',
            'version': '119.0.6045.105',
            'vendor': 'Google LLC',
            'install_location': '/opt/google/chrome',
        }
    ],
}
```

### Windows-Specific Fields
```python
# Windows registry data automatically extracted
{
    'product_name': 'Windows 10 Pro',
    'build_number': '19044',
    'install_date': '2024-01-15T10:30:00',

    'firewall_rules': [
        {
            'name': 'StandardProfile Firewall',
            'enabled': True,
            'direction': 'both',
        }
    ],

    'environment': {
        'PATH': 'C:\\Windows\\System32;...',
        'PROCESSOR_ARCHITECTURE': 'AMD64',
        'SystemRoot': 'C:\\Windows',
    },
}
```

## Async VMware Operations

### Basic Usage
```python
from hyper2kvm.vmware.async_client.client import AsyncVMwareClient

async with AsyncVMwareClient(
    host='vcenter.example.com',
    username='admin',
    password='secret',
    max_concurrent_vms=5,
) as client:
    # List VMs
    vms = await client.list_vms()

    # Get VM info
    vm_info = await client.get_vm_info('my-vm')

    # Export VM
    await client.export_vm_async('my-vm', '/output/dir')
```

### Batch Operations
```python
from hyper2kvm.vmware.async_client.operations import AsyncVMwareOperations

ops = AsyncVMwareOperations(client)

def progress_callback(p):
    print(f"{p.vm_name}: {p.progress*100:.1f}% - {p.stage}")
    print(f"  Throughput: {p.throughput_mbps:.1f} MB/s")
    print(f"  Elapsed: {p.elapsed_seconds:.0f}s")
    if p.eta_seconds:
        print(f"  ETA: {p.eta_seconds:.0f}s")

results = await ops.batch_export(
    ['vm1', 'vm2', 'vm3'],
    Path('/output'),
    on_progress=progress_callback,
)
```

## Common Patterns

### Iterate Through All Filesystems
```python
filesystems = g.list_filesystems()
for device, fstype in filesystems.items():
    print(f"\nFilesystem: {device} ({fstype})")

    # Get metadata
    uuid = g.vfs_uuid(device)
    label = g.vfs_label(device)
    print(f"  UUID: {uuid}")
    print(f"  Label: {label}")

    # Get size if it's a block device
    if device.startswith('/dev/'):
        try:
            size = g.blockdev_getsize64(device)
            print(f"  Size: {size / (1024**3):.2f} GiB")
        except:
            pass
```

### Analyze All Services
```python
# Get all services
services = g.systemctl_list_units('service', all_units=True)

# Group by state
active = [s for s in services if s['active'] == 'active']
failed = [s for s in services if s['active'] == 'failed']
inactive = [s for s in services if s['active'] == 'inactive']

print(f"Active: {len(active)}")
print(f"Failed: {len(failed)}")
print(f"Inactive: {len(inactive)}")

# Check critical services
for service_name in ['sshd.service', 'cron.service', 'systemd-journald.service']:
    is_active = g.systemctl_is_active(service_name)
    status = "✓" if is_active else "✗"
    print(f"{status} {service_name}")
```

### Find Slow Boot Services
```python
# Get boot time breakdown
timing = g.systemd_analyze_time()
total_boot = timing.get('total', 0)

if total_boot > 60:
    print(f"⚠️ Slow boot detected: {total_boot:.1f}s")

    # Find culprits
    blame = g.systemd_analyze_blame(lines=10)
    print("\nTop 10 slowest services:")
    for svc in blame:
        print(f"  {svc['time']:>8s}  {svc['unit']}")
```

### Comprehensive OS Detection
```python
# Detect all OS roots
roots = g.inspect_os()

for root in roots:
    print(f"\n=== OS Root: {root} ===")

    # Get OS details
    print(f"Type: {g.inspect_get_type(root)}")
    print(f"Distro: {g.inspect_get_distro(root)}")
    print(f"Product: {g.inspect_get_product_name(root)}")
    print(f"Version: {g.inspect_get_major_version(root)}.{g.inspect_get_minor_version(root)}")
    print(f"Arch: {g.inspect_get_arch(root)}")

    # Get filesystems
    filesystems = g.inspect_get_filesystems(root)
    print(f"\nFilesystems ({len(filesystems)}):")
    for fs in filesystems:
        print(f"  - {fs}")

    # Get mount structure
    mounts = g.inspect_get_mountpoints(root)
    print(f"\nMount points:")
    for mp, dev in sorted(mounts.items()):
        print(f"  {mp:20s} -> {dev}")
```

---

For complete API documentation, see:
- `docs/IMPLEMENTATION_COMPLETE.md` - Full implementation summary
- `examples/vmcraft_filesystem_apis.py` - Filesystem API examples
- `examples/demo_systemd_apis.py` - Systemd API examples
