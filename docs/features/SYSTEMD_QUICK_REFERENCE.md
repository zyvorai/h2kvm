# Systemd Tools Quick Reference

Quick reference guide for using systemd tools in VM migration workflows.

## 🎯 Common Migration Tasks

### Detect Source Platform

```python
from h2kvm.systemd import SystemdDetectVirt

detector = SystemdDetectVirt()
if detector.is_virtualized():
    print(f"Source: {detector.get_hypervisor_name()}")
    # Output: VMware, Hyper-V, KVM, etc.
```

### Inspect Disk Image

```python
from h2kvm.systemd import SystemdDissect

dissect = SystemdDissect()
info = dissect.inspect(Path("vm.qcow2"))

print(f"OS: {info.os_release['NAME']}")
print(f"Size: {info.size / 1e9:.2f} GB")
print(f"Partitions: {len(info.partitions)}")
```

### Prevent Sleep During Migration

```python
from h2kvm.systemd import SystemdInhibit

inhibit = SystemdInhibit()
inhibit.run(
    ["qemu-img", "convert", "source.vmdk", "target.qcow2"],
    why="VM migration in progress"
)
```

### Convert with Resource Limits

```python
from h2kvm.systemd import SystemdRun

run = SystemdRun()
run.run(
    ["qemu-img", "convert", "-O", "qcow2", "input.vmdk", "output.qcow2"],
    memory_max="4G",
    cpu_quota="200%"
)
```

### Test in Container (Fast)

```python
from h2kvm.systemd import SystemdNspawn

nspawn = SystemdNspawn()
nspawn.spawn_image(
    Path("migrated-vm.qcow2"),
    ephemeral=True,  # No persistent changes
    boot=True
)
```

### Test in Full VM (Comprehensive)

```python
from h2kvm.systemd import SystemdVmspawn

vmspawn = SystemdVmspawn()
vmspawn.spawn(
    Path("migrated-vm.qcow2"),
    cpus=2,
    memory="4G",
    network_user=True
)
```

### Secure Credential Storage

```python
from h2kvm.systemd import SystemdCreds

creds = SystemdCreds()

# Encrypt
creds.encrypt(
    vcenter_password,
    "vcenter-password",
    output=Path("/var/lib/h2kvm/vcenter.cred")
)

# Decrypt
password = creds.decrypt(Path("/var/lib/h2kvm/vcenter.cred"))
```

### Setup LUKS Auto-Unlock

```python
from h2kvm.systemd import SystemdCryptenroll

enroll = SystemdCryptenroll()

# Enroll TPM2
enroll.enroll_tpm2(Path("/dev/sda1"), tpm2_pcrs="7+14")

# Generate recovery key
recovery_key = enroll.enroll_recovery(Path("/dev/sda1"))
```

### Ensure Unique Machine ID

```python
from h2kvm.systemd import SystemdMachineId

machine_id = SystemdMachineId()

# Clear before cloning
machine_id.clear(root=Path("/mnt/source-vm"))

# Generate new ID
new_id = machine_id.setup(root=Path("/mnt/migrated-vm"))
```

### Monitor Resource Usage

```python
from h2kvm.systemd import SystemdCgtop

cgtop = SystemdCgtop()
stats = cgtop.snapshot()

for cg in stats[:5]:  # Top 5 cgroups
    print(f"{cg.path}: CPU {cg.cpu_percent:.1f}%, "
          f"MEM {cg.memory_bytes / 1e6:.1f}MB")
```

### Analyze Boot Performance

```python
from h2kvm.systemd import SystemdAnalyze

analyze = SystemdAnalyze()

# Boot time breakdown
boot_time = analyze.time()
print(f"Total: {boot_time.total}s")
print(f"Userspace: {boot_time.userspace}s")

# Find slow units
slow_units = analyze.blame(limit=10)
for unit in slow_units:
    print(f"{unit.unit}: {unit.time}s")
```

## 🔄 Complete Workflow

```python
from pathlib import Path
from h2kvm.systemd import (
    SystemdDetectVirt,
    SystemdDissect,
    SystemdInhibit,
    SystemdNspawn,
    SystemdVmspawn,
    SystemdMachineId,
    SystemdAnalyze,
)

# 1. Detect source
detector = SystemdDetectVirt()
print(f"Source: {detector.get_hypervisor_name()}")

# 2. Inspect disk
dissect = SystemdDissect()
info = dissect.inspect(Path("source.vmdk"))
print(f"OS: {info.os_release['NAME']}")

# 3. Convert with sleep prevention
inhibit = SystemdInhibit()
inhibit.run(
    ["qemu-img", "convert", "source.vmdk", "target.qcow2"],
    why="Migration"
)

# 4. Test in container (fast)
nspawn = SystemdNspawn()
nspawn.spawn_image(Path("target.qcow2"), ephemeral=True, boot=True)

# 5. Test in VM (comprehensive)
vmspawn = SystemdVmspawn()
vmspawn.spawn(Path("target.qcow2"), cpus=2, memory="4G")

# 6. Setup unique ID
machine_id = SystemdMachineId()
machine_id.setup(root=Path("/mnt/vm"))

# 7. Verify boot performance
analyze = SystemdAnalyze()
boot_time = analyze.time()
print(f"Boot time: {boot_time.total}s")
```

## 📚 Tool Categories

### Disk & Storage

- `SystemdDissect` - Inspect, mount, extract from disk images
- `SystemdMount` - Mount filesystems with auto-generated units
- `SystemdRepart` - Automatically resize partitions
- `SystemdTmpfiles` - Manage temporary files
- `SystemdPath` - Get system directory paths
- `systemd_escape` - Escape strings for unit names

### Security & Encryption

- `SystemdCreds` - TPM2-backed credential encryption
- `SystemdCryptenroll` - LUKS encryption and auto-unlock

### System Analysis

- `SystemdAnalyze` - Boot performance and unit verification
- `SystemdDetectVirt` - Detect virtualization platform
- `SystemdDelta` - Find configuration overrides

### Process & Resources

- `SystemdRun` - Execute with CPU/memory/IO limits
- `SystemdInhibit` - Prevent sleep/shutdown
- `SystemdCgtop` - Monitor resource usage
- `SystemdNotify` - Send service status updates
- `SystemdCat` - Log to systemd journal

### Testing

- `SystemdNspawn` - Lightweight container testing
- `SystemdVmspawn` - Full VM testing with QEMU/KVM

### Identity

- `SystemdMachineId` - Manage machine IDs
- `SystemdId128` - Generate unique identifiers

## 🎯 Use Case Examples

### High-Security Migration

```python
# Encrypt all credentials with TPM2
creds = SystemdCreds()
if creds.has_tpm2():
    for name, value in credentials.items():
        creds.encrypt(value, name, output=Path(f"/var/lib/creds/{name}.cred"))

# Setup LUKS auto-unlock
enroll = SystemdCryptenroll()
enroll.enroll_tpm2(Path("/dev/sda1"), tpm2_pcrs="7+14")
```

### Performance-Optimized Migration

```python
# Resource-controlled conversion
run = SystemdRun()
run.run(
    ["qemu-img", "convert", "-O", "qcow2", "input.vmdk", "output.qcow2"],
    memory_max="8G",
    cpu_quota="300%",
    io_weight=1000
)

# Monitor in real-time
cgtop = SystemdCgtop()
stats = cgtop.monitor_service("qemu-img.service", duration=300)
```

### Multi-Stage Testing

```python
# Stage 1: Quick container test (< 1 min)
nspawn = SystemdNspawn()
nspawn.spawn_image(Path("vm.qcow2"), ephemeral=True, boot=True)

# Stage 2: Full VM test (5-10 min)
vmspawn = SystemdVmspawn()
vmspawn.spawn(Path("vm.qcow2"), cpus=2, memory="4G")

# Stage 3: Secure Boot test
vmspawn.spawn_secure_boot(Path("vm.qcow2"), memory="2G")

# Stage 4: TPM test
vmspawn.spawn_with_tpm(Path("vm.qcow2"), memory="4G")
```

### Batch Migration with Monitoring

```python
inhibit = SystemdInhibit()
cgtop = SystemdCgtop()
notify = SystemdNotify()

for vm in vm_list:
    # Notify start
    notify.status(f"Migrating {vm.name}")

    # Convert with protection
    inhibit.run(
        ["qemu-img", "convert", vm.source, vm.target],
        why=f"Migrating {vm.name}"
    )

    # Monitor
    stats = cgtop.snapshot()

    # Update progress
    notify.status(f"Completed {vm.name}")
```

## 📖 Documentation

- **Full Documentation**: [SYSTEMD_INTEGRATION_SUMMARY.md](SYSTEMD_INTEGRATION_SUMMARY.md)
- **Complete Example**: [systemd_complete_migration.py](../examples/systemd_complete_migration.py)
- **Tool README**: [systemd/README.md](../h2kvm/systemd/README.md)

## 💡 Tips

1. **Always test in container first** - Faster than full VM
2. **Use ephemeral mode for testing** - No persistent changes
3. **Monitor resource usage** - Prevent overload
4. **Prevent sleep on long migrations** - Use systemd-inhibit
5. **Encrypt sensitive credentials** - Use TPM2 when available
6. **Ensure unique machine IDs** - Clear before cloning
7. **Verify boot performance** - Check after migration
8. **Use resource limits** - Prevent runaway processes

## 🔗 References

- [systemd Tools Documentation](https://www.freedesktop.org/software/systemd/man/)
- [h2kvm Documentation](../README.md)
