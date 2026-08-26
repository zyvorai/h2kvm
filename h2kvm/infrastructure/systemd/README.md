# Systemd Integration for H2KVM

Comprehensive systemd integration providing advanced service management, logging, resource control, and boot-time optimization for VM migration and preparation.

## Features

### Core Components

#### 1. **Service Management** (`systemd_core.py`)
- Systemd service lifecycle control
- D-Bus integration for service management
- Transient scope creation for resource isolation
- Service unit generation with security hardening
- Watchdog support for service monitoring

#### 2. **Journal Logging** (`journal_integration.py`)
- Structured logging to systemd journal
- Real-time log monitoring and analysis
- Operation tracking with metadata
- Performance metrics logging
- Historical analysis and reporting

#### 3. **Resource Control** (`resource_control.py`)
- CPU, memory, and I/O limits via cgroups v2
- Real-time resource monitoring
- Process isolation with systemd slices
- Resource usage reporting
- Adaptive resource allocation

#### 4. **Socket Activation** (`socket_activation.py`)
- On-demand VM repair via socket activation
- REST API for repair operations
- Concurrent request handling
- Automatic service start/stop
- Integration with systemd socket units

#### 5. **Path Monitoring** (`path_monitor.py`)
- Automatic VMDK detection and repair
- File system event monitoring
- Batch processing of VMs
- Integration with systemd path units
- Configurable monitoring patterns

### Boot Integration Features

#### 6. **Boot Path Integration** (`boot_integration.py`)

Comprehensive systemd boot-time tools integration:

##### Partition Management
- **systemd-repart**: Automatic partition creation and management
  - GPT partition type support (ESP, XBOOTLDR, ROOT, HOME, VAR, TMP, SWAP, DATA, LVM, RAID)
  - Declarative partition definitions
  - Automatic partition growth
  - Standard layouts for BIOS and UEFI systems

##### Filesystem Management
- **systemd-growfs**: Automatic filesystem growth at boot
  - Ext4, XFS, Btrfs support
  - Grows filesystems to partition size
  - Integrated with mount units

- **systemd-makefs**: On-demand filesystem creation
  - Creates filesystems if they don't exist
  - Supports all major Linux filesystems
  - Integration with mount units

##### Mount Management
- **systemd-mount**: Systemd mount unit generation
  - Declarative mount configuration
  - Dependency management
  - Timeout and retry configuration
  - Integration with fstab

##### System Configuration
- **systemd-firstboot**: First boot system setup
  - Hostname configuration
  - Timezone and locale setup
  - Machine ID generation
  - Root password and shell configuration

- **systemd-tmpfiles**: Temporary file management
  - Runtime directory creation
  - File and directory cleanup
  - Symbolic link management
  - Age-based cleanup policies

- **systemd-remount-fs**: Root filesystem remount
  - Early boot root remount
  - Mount option updates
  - fstab integration

##### Boot Analysis
- **systemd-analyze**: Boot performance analysis
  - Boot time breakdown
  - Critical path identification
  - Service blame analysis
  - Performance optimization

##### Recovery Tools
- **Emergency Recovery Configuration**
  - Rescue target customization
  - Emergency shell access
  - Boot environment verification
  - Recovery mode setup

## Installation

### Requirements

```bash
# System packages (Fedora/RHEL/CentOS)
sudo dnf install systemd-devel python3-systemd python3-dbus

# System packages (Ubuntu/Debian)
sudo apt install libsystemd-dev python3-systemd python3-dbus

# Python packages
pip install 'h2kvm[systemd]'
```

### Optional Dependencies

```bash
# For socket activation
pip install aiohttp

# For resource monitoring
pip install psutil
```

## Quick Start

### Basic Usage

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

# Configure auto-grow for root filesystem
integration.configure_auto_grow_filesystems(["/"])
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

## Usage Examples

### 1. Partition Management

```python
from h2kvm.systemd import (
    SystemdRepartManager,
    PartitionDefinition,
    PartitionType,
    FilesystemType,
)

repart = SystemdRepartManager()

# Create standard partition layout
configs = repart.create_standard_layout(
    boot_type=BootType.UEFI,
    disk_size_gb=50
)

# Custom partition
data_partition = PartitionDefinition(
    type=PartitionType.DATA,
    size_min="10G",
    filesystem=FilesystemType.XFS,
    label="data",
    grow=True
)

repart.create_partition_config(data_partition)
```

### 2. Filesystem Auto-Grow

```python
from h2kvm.systemd import (
    SystemdGrowfsManager,
    MountConfiguration,
    FilesystemType,
)

growfs = SystemdGrowfsManager()

# Configure auto-grow for multiple mounts
mounts = [
    MountConfiguration(
        what="/dev/vda2",
        where="/",
        type=FilesystemType.EXT4
    ),
    MountConfiguration(
        what="/dev/vda3",
        where="/var",
        type=FilesystemType.XFS
    ),
]

growfs.configure_growfs(mounts)
```

### 3. First Boot Configuration

```python
from h2kvm.systemd import SystemdFirstBootManager

firstboot = SystemdFirstBootManager()

# Configure system for first boot
firstboot.configure_firstboot(
    root_path="/mnt/vmroot",
    hostname="web-server-01",
    timezone="America/New_York",
    locale="en_US.UTF-8",
    keymap="us"
)

# Setup machine ID
machine_id = firstboot.setup_machine_id("/mnt/vmroot")
```

### 4. Boot Performance Analysis

```python
from h2kvm.systemd import BootPerformanceAnalyzer

analyzer = BootPerformanceAnalyzer()

# Get boot time breakdown
boot_time = analyzer.get_boot_time()
print(f"Total boot time: {sum(boot_time.values()):.2f}ms")

# Find slow services
blame = analyzer.get_blame()
for time_ms, service in blame[:5]:
    print(f"{service}: {time_ms:.2f}ms")
```

### 5. Journal Logging

```python
from h2kvm.systemd import JournalLogger

logger = JournalLogger(vm_name="web-01", operation="migration")

logger.log_start()
logger.log_step("conversion", "in_progress", "Converting VMDK to QCOW2")
logger.log_progress(50, 100, "50% complete")
logger.log_metric("conversion_speed", 125.5, "MB/s")
logger.log_success(duration=45.3)
```

### 6. Resource Control

```python
from h2kvm.systemd import SystemdResourceControl

resource_ctl = SystemdResourceControl()

# Set resource limits for a process
resource_ctl.set_process_limits(
    pid=12345,
    cpu_quota=50,      # 50% CPU
    memory_limit_mb=2048,
    io_weight=100
)

# Monitor resource usage
usage = resource_ctl.get_resource_usage(pid=12345)
print(f"CPU: {usage['cpu_percent']}%")
print(f"Memory: {usage['memory_mb']}MB")
```

### 7. Socket Activation

```python
from h2kvm.systemd import RepairSocketServer

# Create socket server for on-demand repairs
server = RepairSocketServer(
    socket_path="/run/h2kvm-repair.sock",
    max_workers=4
)

# Start server (systemd will activate on connection)
server.start()
```

### 8. Path Monitoring

```python
from h2kvm.systemd import VMPathMonitor

# Monitor directory for new VMDKs
monitor = VMPathMonitor(
    watch_path="/var/lib/vmware/vmdks",
    output_dir="/var/lib/libvirt/images"
)

# Process detected VMs
monitor.process_detected_vms()
```

## Architecture

### Component Relationships

```
SystemdBootIntegration (Main Integration)
├── SystemdRepartManager (Partition management)
├── SystemdGrowfsManager (Filesystem growth)
├── SystemdMakefsManager (Filesystem creation)
├── SystemdMountManager (Mount units)
├── SystemdFirstBootManager (First boot config)
├── SystemdTmpfilesManager (Temporary files)
├── SystemdRemountFSManager (Root remount)
├── BootPerformanceAnalyzer (Boot analysis)
└── BootEnvironmentRecovery (Recovery tools)

SystemdIntegration (Service management)
├── SystemdResourceControl (Resource limits)
├── JournalLogger (Structured logging)
├── JournalMonitor (Log analysis)
├── RepairSocketServer (Socket activation)
└── VMPathMonitor (Path monitoring)
```

### Data Flow

```
VM Repair Workflow
    ↓
integrate_with_vm_repair()
    ↓
SystemdBootIntegration.prepare_vm_boot_environment()
    ├─→ Machine ID setup
    ├─→ Tmpfiles creation
    ├─→ Recovery configuration
    └─→ Boot environment verification
    ↓
Auto-grow configuration
    ├─→ Root filesystem
    ├─→ /var filesystem
    └─→ /home filesystem
    ↓
Boot-ready VM
```

## Configuration Files

### Systemd Unit Locations

- **Service units**: `/etc/systemd/system/*.service`
- **Mount units**: `/etc/systemd/system/*.mount`
- **Timer units**: `/etc/systemd/system/*.timer`
- **Path units**: `/etc/systemd/system/*.path`
- **Socket units**: `/etc/systemd/system/*.socket`

### Configuration Directories

- **Repart configs**: `/etc/repart.d/*.conf`
- **Tmpfiles configs**: `/etc/tmpfiles.d/*.conf`
- **Drop-ins**: `/etc/systemd/system/UNIT.d/*.conf`

## Best Practices

### 1. Always Verify Boot Environment

```python
recovery = BootEnvironmentRecovery()
verification = recovery.verify_boot_environment("/mnt/vmroot")

if not verification['ready']:
    print(f"Issues: {verification['issues']}")
    # Fix issues before booting VM
```

### 2. Use Auto-Grow for Cloud Images

```python
# Enable auto-grow for root filesystem
integration.configure_auto_grow_filesystems(["/"])
```

### 3. Configure Recovery Mode

```python
# Always configure rescue mode for production VMs
integration.prepare_vm_boot_environment(
    boot_env=boot_env,
    configure_recovery=True
)
```

### 4. Monitor Boot Performance

```python
# After first boot, analyze performance
analyzer = BootPerformanceAnalyzer()
boot_time = analyzer.get_boot_time()

if sum(boot_time.values()) > 60000:  # >60 seconds
    # Investigate slow services
    blame = analyzer.get_blame()
```

### 5. Use Structured Logging

```python
# Always use JournalLogger for VM operations
logger = JournalLogger(vm_name=vm_name, operation="migration")
logger.log_start()
try:
    # ... migration steps ...
    logger.log_success()
except Exception as e:
    logger.log_failure(str(e))
```

## Troubleshooting

### Common Issues

#### 1. Systemd not available

```python
from h2kvm.systemd import check_systemd_available

if not check_systemd_available():
    print("Systemd integration not available")
    print("Install: pip install 'h2kvm[systemd]'")
```

#### 2. Permission denied

Most systemd operations require root privileges:

```bash
sudo python3 your_script.py
```

#### 3. D-Bus connection failed

Ensure D-Bus is running:

```bash
sudo systemctl status dbus
```

#### 4. Journal not accessible

Add user to systemd-journal group:

```bash
sudo usermod -a -G systemd-journal $USER
```

## Performance

### Benchmarks

- **LVM activation**: 7x faster (0.71s vs 5-10s)
- **Boot environment prep**: <1 second
- **Auto-grow configuration**: <0.5 seconds
- **Machine ID setup**: <0.1 seconds

### Resource Usage

- **Memory overhead**: <50MB per VM
- **CPU usage**: <5% during preparation
- **Disk I/O**: Minimal (mostly metadata)

## Security

### Hardening Features

1. **Service isolation**: Private /tmp, protected system paths
2. **Resource limits**: CPU, memory, I/O quotas
3. **Capabilities**: Minimal capability sets
4. **Namespace isolation**: Private namespaces where applicable
5. **Read-only paths**: System directories mounted read-only

### Security Checklist

- [ ] Enable resource limits
- [ ] Configure private /tmp
- [ ] Set up capability restrictions
- [ ] Enable SELinux/AppArmor
- [ ] Configure filesystem permissions
- [ ] Enable audit logging

## Contributing

See [Development Guide](../../docs/development/contributing.md) for contribution guidelines.

## License

Apache-2.0

## Related Documentation

- [Systemd Boot Integration Examples](../../examples/systemd_boot_integration_examples.py)
- [LVM Enterprise Improvements](../../docs/LVM_AND_ENTERPRISE_IMPROVEMENTS.md)
- [Test Results](../../docs/test-results/README.md)
- [API Documentation](../../docs/api/README.md)

---

**Version**: 3.0.0
**Last Updated**: February 14, 2026
**Status**: Production Ready
