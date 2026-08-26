# VMCraft Inspector - Comprehensive Guest Image Analysis

## Overview

The VMCraft Inspector (`vmcraft_inspect.py`) is a powerful CLI tool that showcases all the enhanced features of VMCraft, including comprehensive OS detection, container and bootloader detection, security analysis, and performance metrics.

## Features

### ✅ Enhanced OS Detection
- **Windows**: All versions from NT 4.0 through Windows 12
  - All Windows Server editions (2003-2025)
  - Registry-based detection with build number mapping
  - Accurate version, edition, and architecture detection

- **Linux**: All major distributions
  - Red Hat family: RHEL, Fedora, CentOS, Rocky, AlmaLinux, Oracle Linux
  - SUSE family: SLES, openSUSE (Leap, Tumbleweed)
  - Debian family: Debian, Ubuntu, Linux Mint
  - Others: Arch, Gentoo, Alpine, Slackware, Photon OS, Amazon Linux

### 🐳 Container Detection
Detects container runtime installations:
- Docker (/.dockerenv, /var/lib/docker)
- Podman (/run/podman, containers/storage)
- LXC (/var/lib/lxc)
- systemd-nspawn (/var/lib/machines)

### 🥾 Bootloader Detection
Identifies bootloader configuration:
- GRUB2 (detects config path and boot entries)
- systemd-boot
- UEFI firmware
- LILO (legacy)

### 🔒 Security Analysis
- **SELinux**: Mode (enforcing, permissive, disabled), policy type
- **AppArmor**: Status, loaded profiles, enforcement modes

### 📦 Package Management
Auto-detects package manager and lists installed packages:
- **RPM-based**: RHEL, Fedora, CentOS, Rocky, Alma, SUSE
- **APT-based**: Debian, Ubuntu, Mint
- **Pacman-based**: Arch, Manjaro

### 🪟 Windows-Specific Features
- **Registry Operations**: Read Windows registry values offline
  - ProductName, CurrentBuild, EditionID
  - Uses hivexget for offline registry parsing

- **User Management**: SAM registry parsing
  - List all Windows users
  - Identify administrators
  - Check disabled accounts
  - User statistics

### ⚙️ Linux-Specific Features
- **Systemd Service Management**:
  - List all services
  - Identify boot-time services
  - Get service dependencies
  - Show enabled/disabled services

### ⚡ Performance Metrics
- Launch timing (NBD connection, storage activation)
- Operation counters (mounts, file reads/writes, registry reads)
- Memory usage estimates
- Cache statistics (LRU cache hit rates)

## Installation

### System Requirements

**Required**:
```bash
# Fedora/RHEL
sudo dnf install qemu-utils ntfs-3g hivex

# Ubuntu/Debian
sudo apt install qemu-utils ntfs-3g libhivex-bin
```

**Optional** (for specific features):
```bash
# For Linux package management
sudo dnf install rpm dpkg pacman  # Install as needed

# For LUKS encryption support
sudo dnf install cryptsetup

# For software RAID support
sudo dnf install mdadm
```

### Python Dependencies

VMCraft is included in the h2kvm project:
```bash
cd h2kvm
pip install -e .
```

## Usage

### Basic Usage

```bash
# Inspect a disk image (requires sudo for NBD access)
sudo python3 scripts/vmcraft_inspect.py /path/to/disk.qcow2

# VMDK format
sudo python3 scripts/vmcraft_inspect.py /path/to/disk.vmdk --format vmdk

# Show all available information
sudo python3 scripts/vmcraft_inspect.py /path/to/disk.qcow2 --show-all
```

### Selective Information Display

```bash
# Show only container detection
sudo python3 scripts/vmcraft_inspect.py disk.qcow2 --show-containers

# Show only bootloader information
sudo python3 scripts/vmcraft_inspect.py disk.qcow2 --show-bootloader

# Show security modules (SELinux, AppArmor)
sudo python3 scripts/vmcraft_inspect.py disk.qcow2 --show-security

# Show installed packages
sudo python3 scripts/vmcraft_inspect.py disk.qcow2 --show-packages

# Windows-specific information (registry, users)
sudo python3 scripts/vmcraft_inspect.py windows.vmdk --format vmdk --show-windows

# Linux systemd services
sudo python3 scripts/vmcraft_inspect.py linux.qcow2 --show-services

# Filesystems and partitions
sudo python3 scripts/vmcraft_inspect.py disk.qcow2 --show-filesystems

# Performance metrics and cache statistics
sudo python3 scripts/vmcraft_inspect.py disk.qcow2 --show-performance
```

### Combined Options

```bash
# Windows VM: Show OS info, registry, and users
sudo python3 scripts/vmcraft_inspect.py win10.vmdk --format vmdk \
  --show-windows --show-security --show-performance

# Linux VM: Show OS info, containers, bootloader, and services
sudo python3 scripts/vmcraft_inspect.py ubuntu.qcow2 \
  --show-containers --show-bootloader --show-services --show-packages
```

## Examples

### Example 1: Windows 10 VM Inspection

```bash
$ sudo python3 scripts/vmcraft_inspect.py win10/win10.vmdk --format vmdk --show-all

================================================================================
  🚀 VMCraft Comprehensive Inspector
================================================================================

Phase 1: Launching VMCraft
  ✓ Launched successfully

Phase 2: OS Detection & Inspection
  ✓ Found 1 operating system(s)

--- Operating System #1 ---
  Root device: /dev/nbd5p3
  Type: 🪟 windows
  Product: Windows 10 EnterpriseS
  Distribution: windows
  Version: 10.0
  Architecture: x86_64

================================================================================
  🐳 Container Detection
================================================================================
  Is Container: False
  Container Type: None

  Indicators:
    ✗ docker: False
    ✗ podman: False
    ✗ lxc: False
    ✗ systemd_nspawn: False

================================================================================
  🪟 Windows Analysis
================================================================================

Registry Information:
  ProductName: Windows 10 Enterprise LTSC 2021
  CurrentBuild: 19044
  EditionID: EnterpriseS

User Accounts:
  Found 3 user(s):
    - Administrator (ENABLED)
      RID: 500
    - Guest (DISABLED)
      RID: 501
    - User1 (ENABLED)
      RID: 1001

  Administrators (2):
    - Administrator
    - User1

User Statistics:
  Total: 3
  Enabled: 2
  Disabled: 1
  Administrators: 2

================================================================================
  ⚡ Performance Metrics
================================================================================

Timing:
  Launch Time: 1.85s
  NBD Connect Time: 1.42s
  Storage Activation Time: 0.28s

Operations:
  Mounts: 1
  File Reads: 15
  Registry Reads: 3

Memory:
  Estimate: 12.3 MB
```

### Example 2: Linux VM with Container Detection

```bash
$ sudo python3 scripts/vmcraft_inspect.py fedora.qcow2 --show-containers --show-bootloader

================================================================================
  🐳 Container Detection
================================================================================
  Is Container: False
  Container Type: docker

  Indicators:
    ✓ docker: True
    ✗ podman: False
    ✗ lxc: False
    ✗ systemd_nspawn: False

================================================================================
  🥾 Bootloader Detection
================================================================================
  Bootloader: grub2
  Is UEFI: True
  Config Path: /boot/efi/EFI/fedora/grub.cfg

  Boot Entries (3):
    - Fedora Linux (6.18.5-200.fc43.x86_64)
      Kernel: /vmlinuz-6.18.5-200.fc43.x86_64
    - Fedora Linux (6.18.4-200.fc43.x86_64)
      Kernel: /vmlinuz-6.18.4-200.fc43.x86_64
    - Fedora Linux (Rescue)
      Kernel: /vmlinuz-0-rescue
```

## Performance

VMCraft delivers high-performance guest image analysis:

| Operation | VMCraft |
|-----------|---------|
| Launch | ~1.9s |
| NBD Connect | ~1.4s |
| Inspection | ~0.3s |
| File Operations | Optimized with LRU cache |

## Architecture

VMCraft uses a modern NBD-based architecture:

1. **NBD Connection**: Uses `qemu-nbd` to expose disk images as `/dev/nbdX` devices
2. **Storage Stack**: Activates LVM, LUKS, mdraid, ZFS automatically
3. **Native Tools**: Uses standard Linux tools (mount, blkid, lsblk, etc.)
4. **Registry Parsing**: Uses `hivexget` for offline Windows registry access
5. **LRU Caching**: Caches file metadata and directory listings for performance

## Troubleshooting

### NBD Device Busy
```
Error: No free NBD devices
```
**Solution**: Load NBD kernel module with more devices
```bash
sudo modprobe nbd max_part=16 nbds_max=32
```

### Permission Denied
```
Error: Permission denied accessing NBD device
```
**Solution**: Run with sudo
```bash
sudo python3 scripts/vmcraft_inspect.py disk.qcow2
```

### NTFS Mount Failed
```
Error: Mount failed: Device or resource busy
```
**Solution**: Ensure ntfs-3g is installed
```bash
sudo dnf install ntfs-3g  # Fedora/RHEL
sudo apt install ntfs-3g  # Ubuntu/Debian
```

### Registry Read Failed
```
Error: hivexget: command not found
```
**Solution**: Install hivex package
```bash
sudo dnf install hivex           # Fedora/RHEL
sudo apt install libhivex-bin    # Ubuntu/Debian
```

### Windows User Enumeration Failed
```
SAM registry hive not found
```
**Solution**: Ensure filesystem is mounted before calling user management APIs.
The filesystem needs to be mounted for SAM registry access.

## Comparison: vmcraft_inspect.py vs inspect_guest.py

| Feature | inspect_guest.py | vmcraft_inspect.py |
|---------|------------------|-------------------|
| **Backend** | Legacy Inspector | VMCraft (NBD-based) |
| **Performance** | ~10-13s launch | **~1.9s launch** |
| **Windows Detection** | Basic | **Enhanced** (NT-12, all Server editions) |
| **Linux Detection** | Basic | **Enhanced** (all major distros) |
| **Container Detection** | ❌ No | ✅ **Docker, Podman, LXC, systemd-nspawn** |
| **Bootloader Detection** | ❌ No | ✅ **GRUB2, systemd-boot, UEFI, LILO** |
| **Security Modules** | Basic | ✅ **SELinux, AppArmor with details** |
| **Package Management** | Basic | ✅ **RPM, APT, Pacman with query** |
| **Windows Users** | ❌ No | ✅ **SAM registry parsing** |
| **Linux Services** | Basic | ✅ **systemd service management** |
| **Performance Metrics** | ❌ No | ✅ **Timing, operations, cache stats** |
| **LRU Caching** | ❌ No | ✅ **File metadata and directories** |

## Contributing

To add new features to VMCraft Inspector:

1. Add new methods to VMCraft modules in `h2kvm/core/vmcraft/`
2. Update `vmcraft_inspect.py` to showcase the new features
3. Add command-line arguments for selective display
4. Update this documentation

## License

SPDX-License-Identifier: Apache-2.0

## See Also

- [VMCraft OS Detection](../VMCRAFT_OS_DETECTION.md) - Comprehensive OS detection capabilities
- [VMCraft Enhancements](../VMCRAFT_ENHANCEMENTS.md) - All 28 new methods with examples
- [VMCraft Testing Results](../VMCRAFT_TESTING_RESULTS.md) - Test results with Windows 10 VM
- [VMCraft Module README](../h2kvm/core/vmcraft/README.md) - Module architecture

## References

- VMCraft: Native Python disk image manipulation library
- guestfs: Guest filesystem manipulation interface
- qemu-nbd: QEMU Network Block Device server
- hivex: Windows Registry hive extraction library
