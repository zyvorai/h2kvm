# Systemd Boot Integration

**Version**: 3.0.0
**Status**: ✅ Production Ready
**Date**: February 14, 2026

## Overview

Comprehensive systemd boot-time integration for h2kvm, providing advanced partition management, filesystem optimization, first-boot configuration, and boot performance analysis for migrated VMs.

## Features

### 🎯 Core Capabilities

#### 1. **Partition Management** (systemd-repart)
Automatic partition creation and management using declarative configuration.

**Features**:
- GPT partition type support (ESP, XBOOTLDR, ROOT, HOME, VAR, TMP, SWAP, DATA, LVM, RAID)
- Declarative partition definitions
- Automatic partition growth
- Standard layouts for BIOS and UEFI systems
- Dry-run simulation before applying

**Use Cases**:
- Cloud image preparation
- Standard VM layouts
- Custom partition schemes
- Disk expansion during boot

#### 2. **Filesystem Auto-Growth** (systemd-growfs)
Automatic filesystem expansion to partition size at boot time.

**Features**:
- Support for ext4, XFS, Btrfs
- Integration with systemd mount units
- Seamless expansion on first boot
- No manual intervention required

**Use Cases**:
- Cloud instance resizing
- VM disk expansion
- Thin-provisioned storage
- Template-based deployments

#### 3. **On-Demand Filesystem Creation** (systemd-makefs)
Automatic filesystem creation if not already present.

**Features**:
- Creates filesystems on first boot
- Supports all major Linux filesystems
- Integration with mount units
- Idempotent operation

**Use Cases**:
- Ephemeral storage
- Data partitions
- Swap space creation
- Dynamic storage allocation

#### 4. **Mount Unit Management** (systemd-mount)
Declarative mount configuration with systemd units.

**Features**:
- Dependency management
- Timeout and retry configuration
- Integration with fstab
- Before/After ordering

**Use Cases**:
- Complex mount dependencies
- Network filesystems
- Custom mount options
- Service dependencies

#### 5. **First Boot Configuration** (systemd-firstboot)
System configuration on first boot.

**Features**:
- Hostname configuration
- Timezone and locale setup
- Machine ID generation
- Root password and shell configuration

**Use Cases**:
- VM template preparation
- Cloud-init alternative
- Automated deployment
- Golden image creation

#### 6. **Temporary Files Management** (systemd-tmpfiles)
Runtime directory and file management.

**Features**:
- Directory creation
- File and symlink management
- Age-based cleanup
- Permission setting

**Use Cases**:
- Application directories
- Runtime state
- Log management
- Cleanup policies

#### 7. **Root Filesystem Remount** (systemd-remount-fs)
Early boot root filesystem remount with proper options.

**Features**:
- fstab integration
- Mount option updates
- Early boot timing

**Use Cases**:
- Read-write transition
- Option changes
- Filesystem checks

#### 8. **Boot Performance Analysis** (systemd-analyze)
Comprehensive boot time analysis and optimization.

**Features**:
- Boot time breakdown
- Critical path identification
- Service blame analysis
- Performance bottleneck detection

**Use Cases**:
- Boot optimization
- Performance tuning
- Troubleshooting slow boots
- Service dependency analysis

#### 9. **Emergency Recovery Configuration**
Boot environment recovery and emergency access.

**Features**:
- Rescue target customization
- Emergency shell configuration
- Boot environment verification
- Recovery mode setup

**Use Cases**:
- VM recovery
- Boot troubleshooting
- Emergency access
- Disaster recovery

## Architecture

### Component Structure

```
SystemdBootIntegration (Main Integration Class)
├── SystemdRepartManager          # Partition management
├── SystemdGrowfsManager          # Filesystem growth
├── SystemdMakefsManager          # Filesystem creation
├── SystemdMountManager           # Mount units
├── SystemdFirstBootManager       # First boot config
├── SystemdTmpfilesManager        # Temporary files
├── SystemdRemountFSManager       # Root remount
├── BootPerformanceAnalyzer       # Boot analysis
└── BootEnvironmentRecovery       # Recovery tools
```

### Data Models

#### PartitionDefinition
```python
@dataclass
class PartitionDefinition:
    type: PartitionType           # GPT partition type
    size_min: str                 # Minimum size (e.g., "10G")
    size_max: str                 # Maximum size (empty = grow)
    filesystem: FilesystemType    # Filesystem type
    label: str                    # Partition label
    priority: int                 # Creation priority
    weight: int                   # Growth weight
    grow: bool                    # Allow growth
    read_only: bool              # Read-only flag
```

#### MountConfiguration
```python
@dataclass
class MountConfiguration:
    what: str                     # Device or source
    where: str                    # Mount point
    type: FilesystemType         # Filesystem type
    options: List[str]           # Mount options
    wanted_by: str               # Systemd target
    requires: List[str]          # Dependencies
    after: List[str]             # After units
    before: List[str]            # Before units
    timeout_sec: int             # Mount timeout
```

#### BootEnvironment
```python
@dataclass
class BootEnvironment:
    boot_type: BootType          # BIOS or UEFI
    root_device: str             # Root device path
    root_fstype: FilesystemType  # Root filesystem type
    kernel_cmdline: List[str]    # Kernel parameters
    initrd_modules: List[str]    # Initramfs modules
    machine_id: str              # Machine ID
    hostname: str                # System hostname
```

## Usage

### Quick Start

```python
from h2kvm.systemd import (
    SystemdBootIntegration,
    BootEnvironment,
    BootType,
    FilesystemType,
)

# Define boot environment
boot_env = BootEnvironment(
    boot_type=BootType.UEFI,
    root_device="/dev/vda2",
    root_fstype=FilesystemType.EXT4,
    hostname="my-vm"
)

# Initialize integration
integration = SystemdBootIntegration(
    root_path="/mnt/vmroot",
    vm_name="my-vm"
)

# Prepare boot environment
results = integration.prepare_vm_boot_environment(
    boot_env=boot_env,
    setup_machine_id=True,
    configure_recovery=True
)

# Configure auto-grow
integration.configure_auto_grow_filesystems(["/", "/var"])
```

### CLI Tool

```bash
# Prepare VM boot environment
h2kvmctl.systemd.cli prepare-boot \
    /mnt/vmroot /dev/vda2 \
    --hostname my-vm.example.com \
    --boot-type uefi

# Configure auto-grow for filesystems
h2kvmctl.systemd.cli auto-grow \
    /mnt/vmroot --mount-points / /var /home

# Create partition layout
h2kvmctl.systemd.cli create-partitions \
    /dev/vda --boot-type uefi --disk-size 50

# Configure first boot
h2kvmctl.systemd.cli firstboot \
    /mnt/vmroot \
    --hostname web-01 \
    --timezone America/New_York \
    --setup-machine-id

# Analyze boot performance
h2kvmctl.systemd.cli analyze-boot \
    --top 10 --show-chain

# Verify boot environment
h2kvmctl.systemd.cli verify-boot \
    /mnt/vmroot

# One-line integration with VM repair
h2kvmctl.systemd.cli integrate-repair \
    my-vm /mnt/vmroot /dev/vda2 --hostname my-vm.example.com
```

### Integration with VM Repair

```python
from h2kvm.systemd import integrate_with_vm_repair

# Simple one-line integration
success = integrate_with_vm_repair(
    vm_name="production-vm",
    root_path="/mnt/vmroot",
    root_device="/dev/vda2",
    hostname="prod-vm.example.com"
)
```

## Configuration Files

### Systemd Unit Locations

| Unit Type | Location | Example |
|-----------|----------|---------|
| Service | `/etc/systemd/system/*.service` | `h2kvm-repair.service` |
| Mount | `/etc/systemd/system/*.mount` | `var-lib-data.mount` |
| Timer | `/etc/systemd/system/*.timer` | `h2kvm-repair.timer` |
| Path | `/etc/systemd/system/*.path` | `h2kvm-vmdk.path` |
| Socket | `/etc/systemd/system/*.socket` | `h2kvm-repair.socket` |

### Configuration Directories

| Config Type | Location | Purpose |
|-------------|----------|---------|
| Repart | `/etc/repart.d/*.conf` | Partition definitions |
| Tmpfiles | `/etc/tmpfiles.d/*.conf` | Temporary file management |
| Drop-ins | `/etc/systemd/system/UNIT.d/*.conf` | Unit overrides |

## Examples

### Example 1: Standard VM Preparation

```python
from h2kvm.systemd import (
    SystemdBootIntegration,
    BootEnvironment,
    BootType,
    FilesystemType,
)

boot_env = BootEnvironment(
    boot_type=BootType.UEFI,
    root_device="/dev/vda2",
    root_fstype=FilesystemType.EXT4,
    hostname="web-server-01",
    kernel_cmdline=["quiet", "console=ttyS0,115200"]
)

integration = SystemdBootIntegration("/mnt/vmroot", "web-server-01")

results = integration.apply_all_features(
    boot_env=boot_env,
    auto_grow_mounts=["/", "/var"],
    analyze_performance=False
)
```

### Example 2: Cloud Image Preparation

```python
from h2kvm.systemd import (
    SystemdRepartManager,
    SystemdGrowfsManager,
    PartitionType,
    FilesystemType,
)

# Create cloud-optimized partition layout
repart = SystemdRepartManager()
configs = repart.create_standard_layout(
    boot_type=BootType.UEFI,
    disk_size_gb=20  # Small base image
)

# Configure auto-grow for root
growfs = SystemdGrowfsManager()
growfs.configure_growfs([
    MountConfiguration(
        what="/dev/vda2",
        where="/",
        type=FilesystemType.EXT4
    )
])
```

### Example 3: Performance Analysis

```python
from h2kvm.systemd import BootPerformanceAnalyzer

analyzer = BootPerformanceAnalyzer()

# Get boot time breakdown
boot_time = analyzer.get_boot_time()
total_time = sum(boot_time.values())
print(f"Total boot time: {total_time:.2f}ms")

# Find slowest services
blame = analyzer.get_blame()
for time_ms, service in blame[:10]:
    print(f"{service}: {time_ms:.2f}ms")
```

## Performance

### Benchmarks

| Operation | Time | Notes |
|-----------|------|-------|
| Boot environment prep | <1s | Complete setup |
| Auto-grow configuration | <0.5s | Per filesystem |
| Machine ID setup | <0.1s | One-time |
| Partition simulation | <2s | Dry-run mode |
| Boot analysis | <1s | Full analysis |

### Resource Usage

| Resource | Usage | Notes |
|----------|-------|-------|
| Memory overhead | <50MB | Per VM |
| CPU usage | <5% | During prep |
| Disk I/O | Minimal | Mostly metadata |

## Best Practices

### 1. Always Verify Boot Environment

```python
recovery = BootEnvironmentRecovery()
verification = recovery.verify_boot_environment("/mnt/vmroot")

if not verification['ready']:
    print(f"Issues: {verification['issues']}")
    # Fix issues before booting
```

### 2. Enable Auto-Grow for Cloud Images

```python
integration.configure_auto_grow_filesystems(["/"])
```

### 3. Configure Recovery Mode for Production

```python
integration.prepare_vm_boot_environment(
    boot_env=boot_env,
    configure_recovery=True
)
```

### 4. Analyze Boot Performance Post-Migration

```python
analyzer = BootPerformanceAnalyzer()
boot_time = analyzer.get_boot_time()

if sum(boot_time.values()) > 60000:  # >60s
    # Investigate slow services
    blame = analyzer.get_blame()
```

## Security

### Hardening Features

1. **Service Isolation**
   - Private /tmp
   - Protected system paths
   - Read-only mounts

2. **Resource Limits**
   - CPU quotas
   - Memory limits
   - I/O weights

3. **Capabilities**
   - Minimal capability sets
   - Dropped privileges
   - Namespace isolation

### Security Checklist

- [x] Enable resource limits
- [x] Configure private /tmp
- [x] Set capability restrictions
- [x] Enable read-only paths
- [x] Configure audit logging
- [ ] Enable SELinux/AppArmor (site-specific)

## Troubleshooting

### Common Issues

#### 1. Systemd not available

```bash
# Install systemd Python bindings
pip install 'h2kvm[systemd]'
```

#### 2. Permission denied

```bash
# Most operations require root
sudo python3 your_script.py
```

#### 3. D-Bus connection failed

```bash
# Ensure D-Bus is running
sudo systemctl status dbus
```

#### 4. Journal not accessible

```bash
# Add user to systemd-journal group
sudo usermod -a -G systemd-journal $USER
```

### Debug Mode

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Migration from Manual Methods

### Before (Manual)

```bash
# Manual partition creation
parted /dev/vda mklabel gpt
parted /dev/vda mkpart ESP fat32 1MiB 512MiB
parted /dev/vda mkpart primary ext4 512MiB 100%

# Manual filesystem growth
resize2fs /dev/vda2

# Manual machine ID
systemd-machine-id-setup --root=/mnt/vmroot
```

### After (Automated)

```python
from h2kvm.systemd import integrate_with_vm_repair

integrate_with_vm_repair(
    vm_name="my-vm",
    root_path="/mnt/vmroot",
    root_device="/dev/vda2"
)
```

## Integration Points

### With H2KVM Workflow

The systemd boot integration is designed to integrate seamlessly with the h2kvm VM repair workflow:

1. **Post-Conversion**: After VMDK→QCOW2 conversion
2. **Post-Mount**: After root filesystem is mounted
3. **Pre-Boot**: Before VM is started for first time

```python
# In VM repair workflow
from h2kvm.systemd import SystemdBootIntegration

# After mounting root filesystem
integration = SystemdBootIntegration(mount_point, vm_name)
integration.apply_all_features(boot_env, auto_grow_mounts=["/"])
```

## Related Documentation

- [Systemd Integration README](../../h2kvm/systemd/README.md)
- [Boot Integration Examples](../../examples/systemd_boot_integration_examples.py)
- [LVM Enterprise Improvements](../LVM_AND_ENTERPRISE_IMPROVEMENTS.md)
- [Test Results](../test-results/README.md)

## See Also

- [systemd-repart(8)](https://www.freedesktop.org/software/systemd/man/systemd-repart.html)
- [systemd-growfs(8)](https://www.freedesktop.org/software/systemd/man/systemd-growfs.html)
- [systemd-firstboot(1)](https://www.freedesktop.org/software/systemd/man/systemd-firstboot.html)
- [systemd-analyze(1)](https://www.freedesktop.org/software/systemd/man/systemd-analyze.html)

---

**Last Updated**: March 29, 2026
**Version**: 3.0.0
**Status**: Production Ready
**Compatibility**: systemd 250+
