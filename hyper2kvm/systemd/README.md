# Systemd Tools Integration

Integration of systemd command-line tools into hyper2kvm for enhanced VM
migration functionality.

## 🎯 Overview

This module provides Python wrappers around systemd tools to leverage their capabilities:

- **systemd-dissect**: Disk image inspection and mounting
- **systemd-detect-virt**: Virtualization platform detection
- **systemd-escape**: String escaping for systemd units
- **systemd-creds**: Secure credential encryption
- **systemd-cryptenroll**: LUKS/TPM2 encryption management
- **systemd-run**: Resource-limited command execution

## 📦 Available Tools

### 1. SystemdAnalyze

Analyze system boot performance and verify unit files.

```python
from hyper2kvm.systemd import SystemdAnalyze

analyze = SystemdAnalyze()

# Get boot time breakdown
boot_time = analyze.time()
print(f"Total boot: {boot_time.total}s")
print(f"Userspace: {boot_time.userspace}s")

# Find slow units
slow_units = analyze.blame(limit=10)
for unit in slow_units:
    print(f"{unit.unit}: {unit.time}s")

# Show critical chain
chain = analyze.critical_chain()
print(chain)

# Verify unit files
errors = analyze.verify()
if errors:
    for unit, msgs in errors.items():
        print(f"{unit}: {msgs}")
```

### 2. SystemdCat

Send logs to systemd journal.

```python
from hyper2kvm.systemd import SystemdCat

cat = SystemdCat()

# Log a message
cat.log("Migration started", priority=6)  # Info
cat.log("Migration failed", priority=3)   # Error

# Run command and log output
result = cat.run(
    ["qemu-img", "info", "disk.img"],
    identifier="vm-migration",
)
```

### 3. SystemdInhibit

Prevent system sleep/shutdown during migrations.

```python
from hyper2kvm.systemd import SystemdInhibit

inhibit = SystemdInhibit()

# Run conversion with sleep/shutdown inhibited
result = inhibit.run(
    ["qemu-img", "convert", "input.vmdk", "output.qcow2"],
    what="idle:sleep:shutdown",
    why="VM disk conversion in progress",
)

# List active locks
locks = inhibit.list()
print(locks)
```

### 4. SystemdNotify

Send service status notifications to systemd.

```python
from hyper2kvm.systemd import SystemdNotify

notify = SystemdNotify()

# Notify ready
notify.ready()

# Update status
notify.status("Migrating VM: web-server-01 (25%)")
notify.status("Migrating VM: web-server-01 (50%)")

# Send watchdog ping
notify.watchdog()

# Notify stopping
notify.stopping()
```

### 5. SystemdTmpfiles

Manage temporary files and directories.

```python
from hyper2kvm.systemd import SystemdTmpfiles

tmpfiles = SystemdTmpfiles()

# Create temporary directories
tmpfiles.create(prefix="/run/hyper2kvm")

# Clean up temporary files
tmpfiles.clean(prefix="/tmp/hyper2kvm")

# Remove directories
tmpfiles.remove(prefix="/var/lib/hyper2kvm")
```

### 6. SystemdDissect

Inspect and manipulate disk images using systemd-dissect.

```python
from hyper2kvm.systemd import SystemdDissect

dissect = SystemdDissect()

# Inspect image
info = dissect.inspect(Path("disk.img"))
print(f"OS: {info.os_release.get('NAME')}")
print(f"Partitions: {len(info.partitions)}")

# Mount image
dissect.mount(Path("disk.img"), Path("/mnt/disk"))

# Extract file
dissect.copy_from(Path("disk.img"), "/etc/hostname", Path("/tmp/hostname"))

# Execute command
result = dissect.with_image(Path("disk.img"), ["cat", "/etc/os-release"])

# Unmount
dissect.umount(Path("/mnt/disk"))
```

### 7. SystemdDetectVirt

Detect virtualization environment.

```python
from hyper2kvm.systemd import SystemdDetectVirt, VirtType

detector = SystemdDetectVirt()

# Detect environment
if detector.is_virtualized():
    virt_type = detector.detect()
    print(f"Running in: {detector.get_hypervisor_name()}")

# Check specific types
if detector.is_vm():
    print("Full VM")
elif detector.is_container():
    print("Container")

# Get all supported types
types = detector.list_types()
```

### 8. SystemdCreds

Encrypt and manage credentials securely.

```python
from hyper2kvm.systemd import SystemdCreds

creds = SystemdCreds()

# Encrypt credential
encrypted_path = creds.encrypt(
    "my-password",
    "vcenter-password",
    output=Path("/etc/credentials/vcenter.cred")
)

# Decrypt credential
password = creds.decrypt(Path("/etc/credentials/vcenter.cred"))

# Check TPM2 support
if creds.has_tpm2():
    print("TPM2 available for secure storage")
```

### 9. SystemdCryptenroll

Manage LUKS encryption and TPM2 enrollment.

```python
from hyper2kvm.systemd import SystemdCryptenroll

enroll = SystemdCryptenroll()

# Enroll TPM2 for auto-unlock
enroll.enroll_tpm2(
    Path("/dev/sda1"),
    tpm2_pcrs="7+14"  # Bind to PCR banks
)

# Generate recovery key
recovery_key = enroll.enroll_recovery(Path("/dev/sda1"))
print(f"Recovery key: {recovery_key}")

# Enroll password
enroll.enroll_password(Path("/dev/sda1"), "new-password")

# Remove enrollment
enroll.wipe_slot(Path("/dev/sda1"), "tpm2")
```

### 10. SystemdRun

Execute commands with resource limits.

```python
from hyper2kvm.systemd import SystemdRun

runner = SystemdRun()

# Run with resource limits
result = runner.run(
    ["qemu-img", "convert", "input.vmdk", "output.qcow2"],
    description="VM disk conversion",
    memory_max="4G",      # Max 4GB RAM
    cpu_quota="200%",     # 2 CPUs
    io_weight=500,        # I/O priority
)
```

### 11. systemd_escape / systemd_unescape

Escape strings for systemd unit names.

```python
from hyper2kvm.systemd import systemd_escape, systemd_unescape

# Escape service name
escaped = systemd_escape("my service name")
# Output: "my\\x20service\\x20name"

# Escape path
path = systemd_escape("/mnt/vm disks", path=True)
# Output: "mnt-vm\\x20disks"

# Unescape
original = systemd_unescape(escaped)
```

### 12. SystemdMount

Mount filesystems with automatic unit file generation.

```python
from hyper2kvm.systemd import SystemdMount

mount = SystemdMount()

# Mount disk image
mountpoint = mount.mount(
    Path("/dev/sdb1"),
    options="ro"
)
print(f"Mounted at: {mountpoint}")

# Mount with specific location
mount.mount(
    Path("/path/to/disk.img"),
    Path("/mnt/vm-disk"),
    type="ext4",
)

# List mounts
mounts = mount.list()
for m in mounts:
    print(f"{m['what']} -> {m['where']}")

# Unmount
mount.umount(Path("/mnt/vm-disk"))
```

### 13. SystemdPath

Get systemd path locations.

```python
from hyper2kvm.systemd import SystemdPath

path = SystemdPath()

# Get specific paths
temp_dir = path.get_temporary_directory()
state_dir = path.get_state_directory()
cache_dir = path.get_cache_directory()

# Get all paths
all_paths = path.get_all()
for name, value in all_paths.items():
    print(f"{name}: {value}")

# Use for migration directories
import os
migration_tmp = os.path.join(temp_dir, "hyper2kvm")
os.makedirs(migration_tmp, exist_ok=True)
```

### 14. SystemdRepart

Automatically resize and repartition disks.

```python
from hyper2kvm.systemd import SystemdRepart

repart = SystemdRepart()

# Dry run first
repart.apply(
    Path("/dev/sda"),
    definitions=Path("/etc/repart.d"),
    dry_run=True
)

# Actually repartition
repart.apply(Path("/dev/sda"))

# Calculate minimum size
sizes = repart.size(Path("/dev/sda"))
min_size = sum(sizes.values())
print(f"Minimum disk size: {min_size / 1e9:.1f} GB")

# Verify definitions
errors = repart.verify(definitions=Path("/etc/repart.d"))
if errors:
    print(f"Found {len(errors)} errors")
```

### 15. SystemdNspawn

Container spawning for testing migrated VMs.

```python
from hyper2kvm.systemd import SystemdNspawn

nspawn = SystemdNspawn()

# Test migrated VM in ephemeral container
nspawn.spawn(
    Path("/var/lib/machines/migrated-vm"),
    boot=True,
    ephemeral=True,
    network_veth=True,
)

# Test from disk image
nspawn.spawn_image(
    Path("/var/lib/hyper2kvm/vm.raw"),
    ephemeral=True,
    boot=True,
)

# Open interactive shell
nspawn.shell(Path("/var/lib/machines/vm"), user="root")
```

### 16. SystemdCgtop

Real-time cgroup resource monitoring.

```python
from hyper2kvm.systemd import SystemdCgtop

cgtop = SystemdCgtop()

# Get resource usage snapshot
stats = cgtop.snapshot()
for cg in stats:
    print(f"{cg.path}: CPU {cg.cpu_percent}%, MEM {cg.memory_bytes / 1e6:.1f}MB")

# Monitor specific service
migration_stats = cgtop.monitor_service(
    "hyper2kvm-migration.service",
    duration=30
)

# Calculate average CPU usage
avg_cpu = sum(s.cpu_percent for s in migration_stats) / len(migration_stats)
print(f"Average CPU during migration: {avg_cpu:.1f}%")
```

### 17. SystemdMachineId

Machine ID management for migrated VMs.

```python
from hyper2kvm.systemd import SystemdMachineId

machine_id = SystemdMachineId()

# Read current machine ID
current_id = machine_id.read(root=Path("/mnt/vm"))
print(f"Current ID: {current_id}")

# Clear ID before cloning (will regenerate on boot)
machine_id.clear(root=Path("/mnt/source-vm"))

# Generate new ID for migrated VM
new_id = machine_id.setup(root=Path("/mnt/migrated-vm"))
print(f"New machine ID: {new_id}")
```

### 18. SystemdVmspawn

VM spawning with QEMU/KVM for full virtualization testing.

```python
from hyper2kvm.systemd import SystemdVmspawn

vmspawn = SystemdVmspawn()

# Test migrated disk image in QEMU/KVM
vmspawn.spawn(
    Path("/var/lib/hyper2kvm/migrated-vm.qcow2"),
    cpus=2,
    memory="4G",
    network_user=True,
)

# Test with TPM emulation
vmspawn.spawn_with_tpm(
    Path("/var/lib/hyper2kvm/encrypted-vm.qcow2"),
    memory="4G",
)

# Test secure boot
vmspawn.spawn_secure_boot(
    Path("/var/lib/hyper2kvm/uefi-vm.qcow2"),
    memory="2G",
)

# Test with vsock for host-guest communication
vmspawn.spawn_with_vsock(
    Path("/var/lib/hyper2kvm/vm.qcow2"),
    cid=3,
    memory="2G",
)
```

### 19. SystemdDelta

Configuration file override detection.

```python
from hyper2kvm.systemd import SystemdDelta

delta = SystemdDelta()

# Find all configuration overrides
overrides = delta.find_overrides()
for override in overrides:
    print(f"{override.type}: {override.original} -> {override.override}")

# Find masked files
masked = delta.find_masked()
print(f"Found {len(masked)} masked files")

# Find overridden files
overridden = delta.find_overridden()
for o in overridden:
    print(f"Override: {o.original} -> {o.override}")

# Check for equivalent overrides (duplicates)
equivalent = delta.check_equivalent()
print(f"Found {len(equivalent)} unnecessary overrides")
```

### 20. SystemdId128

Generate 128-bit unique identifiers.

```python
from hyper2kvm.systemd import SystemdId128

id128 = SystemdId128()

# Generate new random ID
vm_id = id128.new()
print(f"New VM ID: {vm_id}")

# Generate volume ID
vol_id = id128.generate_volume_id()
print(f"Volume ID: {vol_id}")

# Get machine ID
machine_id = id128.machine_id()
print(f"Machine ID: {machine_id}")

# Get boot ID
boot_id = id128.boot_id()
print(f"Boot ID: {boot_id}")

# Get invocation ID (if running in systemd service)
try:
    inv_id = id128.invocation_id()
    print(f"Invocation ID: {inv_id}")
except subprocess.CalledProcessError:
    print("Not running in systemd service")
```

## 🔄 Pipeline Integration

Use systemd tools in migration pipeline:

```python
from hyper2kvm.pipeline.systemd_integration import SystemdPipelineIntegration

integration = SystemdPipelineIntegration()

# Detect source platform
platform = integration.detect_source_platform()
print(f"Migrating from: {platform['hypervisor']}")

# Inspect disk
disk_info = integration.inspect_disk_image(Path("source.vmdk"))
print(f"OS: {disk_info['os_release']['NAME']}")

# Encrypt credentials
cred_path = integration.encrypt_credential("vcenter-pass", "secret123")

# Setup LUKS TPM2
integration.setup_luks_tpm2(Path("/dev/sda1"))

# Convert with limits
integration.run_conversion_with_limits(
    Path("source.vmdk"),
    Path("target.qcow2"),
    memory_max="8G",
    cpu_quota="300%"
)
```

## 🎯 Use Cases

### 1. Long-Running Migration Protection

```python
# Prevent system sleep/shutdown during long migration
from hyper2kvm.systemd import SystemdInhibit

inhibit = SystemdInhibit()

# Inhibit sleep/shutdown for the entire migration
inhibit.run(
    ["hyper2kvm", "migrate", "--vm", "production-db"],
    what="idle:sleep:shutdown",
    why="Critical database migration in progress",
)
```

### 2. Boot Performance Analysis

```python
# Analyze migrated VM boot performance
from hyper2kvm.systemd import SystemdAnalyze

analyze = SystemdAnalyze()

# Check boot time
boot_time = analyze.time()
if boot_time.total > 60:
    print("Warning: Slow boot detected")

    # Find slow units
    slow_units = analyze.blame(limit=5)
    for unit in slow_units:
        print(f"Slow: {unit.unit} ({unit.time}s)")
```

### 3. Journal Logging Integration

```python
# Log migration progress to systemd journal
from hyper2kvm.systemd import SystemdCat

cat = SystemdCat()

cat.log("Starting migration batch", priority=6)
cat.log(f"VM {vm_name} migrated successfully", priority=6)
cat.log(f"Migration failed: {error}", priority=3)
```

### 4. Service Status Updates

```python
# Update systemd service status during migration
from hyper2kvm.systemd import SystemdNotify

notify = SystemdNotify()

notify.ready()  # Service initialized

for i, vm in enumerate(vms):
    progress = (i + 1) / len(vms) * 100
    notify.status(f"Migrating {vm.name} ({progress:.0f}%)")
    # ... migrate VM ...
    notify.watchdog()  # Keep watchdog alive

notify.stopping()
```

### 5. Secure Credential Storage

```python
# Store vCenter password encrypted
creds = SystemdCreds()
creds.encrypt(
    vcenter_password,
    "vcenter-password",
    output=Path("/var/lib/hyper2kvm/vcenter.cred")
)

# Later, retrieve it
password = creds.decrypt(Path("/var/lib/hyper2kvm/vcenter.cred"))
```

### 6. Pre-Migration Validation

```python
# Validate disk image before migration
dissect = SystemdDissect()

if not dissect.validate(source_disk):
    raise ValueError("Invalid disk image")

# Extract OS info
info = dissect.inspect(source_disk)
if info.os_release:
    print(f"Migrating: {info.os_release['NAME']} {info.os_release['VERSION']}")
```

### 7. Resource-Limited Conversions

```python
# Run conversion with memory/CPU limits to avoid overload
runner = SystemdRun()

runner.run(
    ["qemu-img", "convert", "-O", "qcow2", "input.vmdk", "output.qcow2"],
    description="VM disk conversion",
    memory_max="4G",  # Limit to 4GB
    cpu_quota="150%",  # Use 1.5 CPUs
    io_weight=100,     # Low I/O priority
)
```

### 8. LUKS Auto-Unlock Setup

```python
# Enroll TPM2 for automatic LUKS unlock after migration
enroll = SystemdCryptenroll()

# Enroll TPM2
enroll.enroll_tpm2(
    Path("/dev/mapper/luks-root"),
    tpm2_pcrs="7+14"
)

# Generate recovery key
recovery = enroll.enroll_recovery(Path("/dev/mapper/luks-root"))
print(f"Save this recovery key: {recovery}")
```

### 9. Container-Based VM Testing

```python
# Test migrated VM in lightweight container before full KVM deployment
from hyper2kvm.systemd import SystemdNspawn

nspawn = SystemdNspawn()

# Quick smoke test in ephemeral container
nspawn.spawn(
    Path("/var/lib/machines/migrated-vm"),
    boot=True,
    ephemeral=True,  # No persistent changes
    network_veth=True,
)
```

### 10. Resource Monitoring

```python
# Monitor migration process resource usage
from hyper2kvm.systemd import SystemdCgtop

cgtop = SystemdCgtop()

# Real-time monitoring
stats = cgtop.monitor_service("hyper2kvm.service", duration=60)

# Alert if excessive resource use
for s in stats:
    if s.cpu_percent > 90:
        print(f"High CPU usage: {s.cpu_percent}%")
    if s.memory_bytes > 8 * 1024**3:  # 8GB
        print(f"High memory usage: {s.memory_bytes / 1e9:.1f}GB")
```

### 11. Machine ID Uniqueness

```python
# Ensure migrated VMs have unique machine IDs
from hyper2kvm.systemd import SystemdMachineId

machine_id = SystemdMachineId()

# Clear source VM's machine ID before cloning
machine_id.clear(root=Path("/mnt/source-vm"))

# Generate new IDs for each cloned VM
for vm_root in cloned_vms:
    new_id = machine_id.setup(root=vm_root)
    print(f"VM {vm_root.name}: {new_id}")
```

### 12. Full VM Testing with QEMU/KVM

```python
# Test migrated disk in full virtualization
from hyper2kvm.systemd import SystemdVmspawn

vmspawn = SystemdVmspawn()

# Quick smoke test with user-mode networking
vmspawn.spawn(
    Path("/var/lib/hyper2kvm/migrated-vm.qcow2"),
    cpus=2,
    memory="4G",
    network_user=True,
    console="interactive",
)

# Test TPM auto-unlock
vmspawn.spawn_with_tpm(
    Path("/var/lib/hyper2kvm/encrypted-vm.qcow2"),
    memory="4G",
)
```

### 13. Configuration Management

```python
# Detect configuration overrides after migration
from hyper2kvm.systemd import SystemdDelta

delta = SystemdDelta()

# Find what was changed
overrides = delta.find_overrides()
for override in overrides:
    if override.type == "masked":
        print(f"Service masked: {override.original}")
    elif override.type == "overridden":
        print(f"Config overridden: {override.original}")
```

### 14. Unique ID Generation

```python
# Generate unique IDs for VMs and volumes
from hyper2kvm.systemd import SystemdId128

id128 = SystemdId128()

# Unique VM identifiers
vm_ids = {}
for vm in migrated_vms:
    vm_ids[vm.name] = id128.generate_vm_id()

# Volume UUIDs
for volume in vm.volumes:
    volume.uuid = id128.generate_volume_id()
```

## 📚 Benefits

1. **Leverage Systemd Ecosystem**: Use battle-tested systemd tools
2. **Resource Management**: Limit CPU/memory/IO for migration tasks
3. **Secure Credentials**: TPM2-backed credential encryption
4. **LUKS Integration**: Automated encryption handling
5. **Platform Detection**: Accurate source hypervisor detection
6. **Disk Inspection**: Rich disk image analysis without mounting
7. **Sleep Protection**: Prevent system sleep during long migrations
8. **Boot Analysis**: Verify migrated VM boot performance
9. **Journal Logging**: Integrate with systemd logging infrastructure
10. **Service Integration**: Full systemd service lifecycle support
11. **Container Testing**: Test VMs in lightweight containers before deployment
12. **Resource Monitoring**: Real-time cgroup resource tracking
13. **Machine ID Management**: Ensure VM uniqueness after cloning
14. **Automatic Partitioning**: Resize disks during migration
15. **Full VM Testing**: Test with QEMU/KVM including TPM and secure boot
16. **Configuration Tracking**: Detect and manage configuration overrides
17. **UUID Generation**: Generate unique identifiers for VMs and volumes

## 🔧 Requirements

- systemd >= 250 (Ubuntu 22.04+, Fedora 36+)
- systemd >= 254 for systemd-repart, systemd-vmspawn
- Python 3.9+
- QEMU/KVM for systemd-vmspawn
- Tools must be available in PATH:
  - systemd-analyze
  - systemd-cat
  - systemd-cgtop
  - systemd-creds
  - systemd-cryptenroll
  - systemd-delta
  - systemd-detect-virt
  - systemd-dissect
  - systemd-escape
  - systemd-id128
  - systemd-inhibit
  - systemd-machine-id-setup
  - systemd-mount
  - systemd-notify
  - systemd-nspawn
  - systemd-path
  - systemd-repart
  - systemd-run
  - systemd-tmpfiles
  - systemd-vmspawn

## 🧪 Testing

```bash
# Run systemd integration tests
pytest tests/unit/test_systemd/ -v

# Check if tools are available
python -c "
from hyper2kvm.systemd import *
print('✅ All systemd tools available')
"
```

## 📖 Examples

See `examples/systemd_integration_example.py` for complete working examples.

```bash
# Run example
python examples/systemd_integration_example.py
```

## 🔗 References

- [systemd-analyze(1)](https://www.freedesktop.org/software/systemd/man/systemd-analyze.html)
- [systemd-cat(1)](https://www.freedesktop.org/software/systemd/man/systemd-cat.html)
- [systemd-cgtop(1)](https://www.freedesktop.org/software/systemd/man/systemd-cgtop.html)
- [systemd-creds(1)](https://www.freedesktop.org/software/systemd/man/systemd-creds.html)
- [systemd-cryptenroll(1)](https://www.freedesktop.org/software/systemd/man/systemd-cryptenroll.html)
- [systemd-delta(1)](https://www.freedesktop.org/software/systemd/man/systemd-delta.html)
- [systemd-detect-virt(1)](https://www.freedesktop.org/software/systemd/man/systemd-detect-virt.html)
- [systemd-dissect(1)](https://www.freedesktop.org/software/systemd/man/systemd-dissect.html)
- [systemd-id128(1)](https://www.freedesktop.org/software/systemd/man/systemd-id128.html)
- [systemd-inhibit(1)](https://www.freedesktop.org/software/systemd/man/systemd-inhibit.html)
- [systemd-machine-id-setup(1)](https://www.freedesktop.org/software/systemd/man/systemd-machine-id-setup.html)
- [systemd-mount(1)](https://www.freedesktop.org/software/systemd/man/systemd-mount.html)
- [systemd-notify(1)](https://www.freedesktop.org/software/systemd/man/systemd-notify.html)
- [systemd-nspawn(1)](https://www.freedesktop.org/software/systemd/man/systemd-nspawn.html)
- [systemd-path(1)](https://www.freedesktop.org/software/systemd/man/systemd-path.html)
- [systemd-repart(1)](https://www.freedesktop.org/software/systemd/man/systemd-repart.html)
- [systemd-run(1)](https://www.freedesktop.org/software/systemd/man/systemd-run.html)
- [systemd-tmpfiles(1)](https://www.freedesktop.org/software/systemd/man/systemd-tmpfiles.html)
- [systemd-vmspawn(1)](https://www.freedesktop.org/software/systemd/man/systemd-vmspawn.html)
