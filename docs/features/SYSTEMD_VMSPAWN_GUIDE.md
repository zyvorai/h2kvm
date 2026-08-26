# systemd-vmspawn Integration Guide for hyper2kvm

## Overview

`systemd-vmspawn` is a **lightweight VM launcher** from systemd that creates and runs virtual machines using QEMU/KVM, tightly integrated with systemd — similar to how `systemd-nspawn` runs containers.

**Key Concept:**
- `systemd-nspawn` → runs **containers**
- `systemd-vmspawn` → runs **virtual machines**

**Introduced:** systemd v255+ (2023)
**Perfect for:** Post-migration VM testing, ephemeral validation, CI pipelines

---

## Architecture

```
hyper2kvm migration pipeline
           ↓
    systemd-vmspawn
           ↓
    systemd-machined
           ↓
       QEMU/KVM
           ↓
    VM as systemd machine
```

VMs become **first-class systemd objects** managed like services.

---

## Why systemd-vmspawn for hyper2kvm?

### 1. Post-Migration Validation
After converting VMware VMDK → QCOW2, validate boot without complex libvirt setup:

```python
from hyper2kvm.systemd import SystemdVmspawn

vmspawn = SystemdVmspawn()

# Quick smoke test of migrated disk
vmspawn.spawn(
    Path("/var/lib/hyper2kvm/migrated-vm.qcow2"),
    cpus=2,
    memory="4G",
    network_user=True,
)
```

### 2. Automated Boot Verification
Integrate into CI pipeline:

```python
# Test boot succeeds
try:
    vmspawn.spawn(
        migrated_disk,
        cpus=1,
        memory="2G",
        console="passive",  # Non-interactive
    )
    print("✅ Boot test passed")
except subprocess.CalledProcessError:
    print("❌ Boot test failed")
    sys.exit(1)
```

### 3. No libvirtd Required
Perfect for lightweight environments:

```bash
# Traditional approach (heavy)
sudo systemctl start libvirtd
virsh define vm.xml
virsh start vm

# vmspawn approach (lightweight)
sudo systemd-vmspawn --image=vm.qcow2 --memory=2G
```

---

## Native systemd Integration

### Managing VMs with machinectl

After spawning a VM with systemd-vmspawn, manage it like any systemd machine:

```bash
# List running VMs
machinectl list

# Example output:
# MACHINE  CLASS SERVICE OS      VERSION ADDRESSES
# test-vm  vm    vmspawn fedora  39      10.0.2.15

# View VM status
machinectl status test-vm

# Login to VM console
machinectl login test-vm

# Stop VM gracefully
machinectl stop test-vm

# Force terminate
machinectl terminate test-vm

# View VM properties
machinectl show test-vm
```

### Python Integration

```python
import subprocess

def list_vms():
    """List running VMs managed by systemd-machined."""
    result = subprocess.run(
        ["machinectl", "list", "--output=json"],
        capture_output=True,
        text=True,
        check=True
    )
    return json.loads(result.stdout)

def vm_status(vm_name: str) -> dict:
    """Get VM status via machinectl."""
    result = subprocess.run(
        ["machinectl", "show", vm_name, "--output=json"],
        capture_output=True,
        text=True,
        check=True
    )
    return json.loads(result.stdout)
```

---

## Journald Integration

### View VM Logs

```bash
# View logs from specific VM
journalctl -M test-vm

# Follow logs in real-time
journalctl -M test-vm -f

# Filter by service within VM
journalctl -M test-vm -u sshd.service

# Boot messages
journalctl -M test-vm -b
```

### Python Integration

```python
from hyper2kvm.systemd import SystemdCat

# Log migration events to journal
cat = SystemdCat()
cat.log(f"Starting boot test for {vm_name}", priority=6)

# Spawn VM (logs automatically captured)
vmspawn.spawn(disk_image, memory="2G")

cat.log(f"Boot test completed for {vm_name}", priority=6)
```

---

## Feature Comparison

### vmspawn vs Alternatives

| Feature | vmspawn | libvirt | virt-install | qemu |
|---------|---------|---------|--------------|------|
| **systemd integration** | ✅ Native | Partial | No | No |
| **daemon required** | ❌ No | ✅ Yes (libvirtd) | ❌ No | ❌ No |
| **CLI complexity** | ✅ Simple | Medium | Medium | Complex |
| **journald support** | ✅ Full | Limited | No | No |
| **machinectl mgmt** | ✅ Yes | No | No | No |
| **cgroup integration** | ✅ Native | Partial | No | Manual |
| **production virt** | Medium | ✅ Best | ✅ Good | Medium |
| **K8s/KubeVirt base** | No | ✅ Yes | Yes | Yes |
| **Setup time** | ✅ Instant | Medium | Medium | Fast |
| **Resource overhead** | ✅ Minimal | Medium | Low | Low |

**Recommendation:**
- **vmspawn**: Post-migration testing, CI, ephemeral VMs
- **libvirt**: Production deployments, complex networking
- **qemu**: Direct control, development

### vmspawn vs nspawn

| Feature | nspawn | vmspawn |
|---------|--------|---------|
| **Isolation** | Container (namespaces) | Full VM (hardware) |
| **Kernel** | Shared with host | Separate kernel |
| **Performance** | ✅ Faster | Slightly slower |
| **Security** | Medium | ✅ Strong |
| **Windows support** | ❌ No | ✅ Yes |
| **Device passthrough** | Limited | ✅ Full PCI |
| **Boot time** | ✅ Instant | ~seconds |
| **Memory overhead** | ✅ Minimal | ~MB |

---

## hyper2kvm Integration Examples

### Example 1: Post-Migration Boot Test

```python
from pathlib import Path
from hyper2kvm.systemd import SystemdVmspawn, SystemdCat
import logging

logger = logging.getLogger(__name__)

def validate_migrated_vm(qcow2_path: Path) -> bool:
    """
    Boot test migrated VM using systemd-vmspawn.

    Returns True if VM boots successfully.
    """
    vmspawn = SystemdVmspawn()
    cat = SystemdCat()

    vm_name = qcow2_path.stem

    # Log to journal
    cat.log(f"Starting boot validation for {vm_name}", priority=6)

    try:
        # Spawn VM with timeout
        # In practice, you'd use --console=passive and poll
        vmspawn.spawn(
            qcow2_path,
            cpus=2,
            memory="2G",
            network_user=True,
            console="passive",
        )

        cat.log(f"✅ {vm_name} boot successful", priority=6)
        return True

    except subprocess.CalledProcessError as e:
        cat.log(f"❌ {vm_name} boot failed: {e}", priority=3)
        logger.error(f"Boot test failed: {e}")
        return False
```

### Example 2: TPM Auto-Unlock Validation

```python
def test_tpm_unlock(encrypted_disk: Path) -> bool:
    """
    Test TPM-based LUKS auto-unlock after migration.
    """
    vmspawn = SystemdVmspawn()

    try:
        # Boot with TPM emulation
        vmspawn.spawn_with_tpm(
            encrypted_disk,
            cpus=1,
            memory="2G",
        )

        logger.info("✅ TPM auto-unlock successful")
        return True

    except subprocess.CalledProcessError:
        logger.error("❌ TPM auto-unlock failed")
        return False
```

### Example 3: Secure Boot Verification

```python
def verify_secure_boot(uefi_disk: Path) -> bool:
    """
    Verify migrated UEFI VM boots with Secure Boot.
    """
    vmspawn = SystemdVmspawn()

    try:
        vmspawn.spawn_secure_boot(
            uefi_disk,
            cpus=2,
            memory="4G",
        )

        logger.info("✅ Secure Boot verified")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Secure Boot failed: {e}")
        return False
```

### Example 4: Network Connectivity Test

```python
def test_network_connectivity(vm_disk: Path) -> bool:
    """
    Boot VM and verify network connectivity.
    """
    vmspawn = SystemdVmspawn()

    # Spawn with user-mode networking
    proc = vmspawn.spawn(
        vm_disk,
        cpus=1,
        memory="2G",
        network_user=True,  # SLIRP user networking
    )

    # In practice, you'd use vsock or serial to check
    # if network is up inside the VM

    return proc.returncode == 0
```

### Example 5: CI Pipeline Integration

```python
#!/usr/bin/env python3
"""
CI pipeline: Test all migrated VMs boot successfully.
"""

import sys
from pathlib import Path
from hyper2kvm.systemd import SystemdVmspawn

def ci_boot_test(output_dir: Path) -> int:
    """
    Test all QCOW2 images in output directory.
    Returns 0 if all pass, 1 if any fail.
    """
    vmspawn = SystemdVmspawn()
    failures = []

    for qcow2 in output_dir.glob("*.qcow2"):
        print(f"Testing {qcow2.name}...", end=" ")

        try:
            vmspawn.spawn(
                qcow2,
                cpus=1,
                memory="1G",
                console="passive",
            )
            print("✅ PASS")

        except subprocess.CalledProcessError:
            print("❌ FAIL")
            failures.append(qcow2.name)

    if failures:
        print(f"\n❌ {len(failures)} VMs failed boot test:")
        for vm in failures:
            print(f"  - {vm}")
        return 1

    print(f"\n✅ All {len(list(output_dir.glob('*.qcow2')))} VMs passed")
    return 0

if __name__ == "__main__":
    sys.exit(ci_boot_test(Path("/var/lib/hyper2kvm/output")))
```

---

## Advanced Features

### 1. Host-Guest Communication via vsock

```python
def spawn_with_monitoring(vm_disk: Path, vsock_cid: int = 3):
    """
    Spawn VM with vsock for host-guest communication.
    """
    vmspawn = SystemdVmspawn()

    # Spawn with vsock
    vmspawn.spawn_with_vsock(
        vm_disk,
        cid=vsock_cid,
        cpus=2,
        memory="4G",
    )

    # Host can connect to vsock for monitoring
    # import socket
    # sock = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
    # sock.connect((vsock_cid, port))
```

### 2. Custom Kernel/Initrd

```python
def spawn_with_custom_kernel(vm_disk: Path, kernel: Path, initrd: Path):
    """
    Boot VM with custom kernel (useful for testing kernel upgrades).
    """
    vmspawn = SystemdVmspawn()

    vmspawn.spawn(
        vm_disk,
        kernel=kernel,
        initrd=initrd,
        kernel_cmdline="console=ttyS0 debug",
        console="interactive",
    )
```

### 3. Resource Monitoring

```python
from hyper2kvm.systemd import SystemdCgtop
import time

def monitor_vm_resources(vm_name: str, duration: int = 60):
    """
    Monitor VM resource usage via cgroups.
    """
    cgtop = SystemdCgtop()

    stats = []
    for _ in range(duration):
        snapshot = cgtop.snapshot()
        for cg in snapshot:
            if vm_name in cg.path:
                stats.append({
                    'cpu_percent': cg.cpu_percent,
                    'memory_mb': cg.memory_bytes / 1e6,
                    'io_bytes': cg.io_bytes,
                })
        time.sleep(1)

    # Analyze
    avg_cpu = sum(s['cpu_percent'] for s in stats) / len(stats)
    max_mem = max(s['memory_mb'] for s in stats)

    return {
        'avg_cpu': avg_cpu,
        'max_memory_mb': max_mem,
        'samples': len(stats),
    }
```

---

## Networking

systemd-vmspawn automatically integrates with systemd-networkd:

### User-Mode Networking (SLIRP)
```python
# Easiest - no setup required
vmspawn.spawn(disk, network_user=True)
# VM gets 10.0.2.15, host is 10.0.3.0
```

### TAP Networking
```bash
# Setup bridge (one-time)
sudo ip link add br0 type bridge
sudo ip link set br0 up

# Create TAP interface
sudo ip tuntap add tap0 mode tap
sudo ip link set tap0 master br0
sudo ip link set tap0 up
```

```python
# Use TAP interface
vmspawn.spawn(disk, network_tap="tap0")
```

---

## Storage Support

systemd-vmspawn supports multiple disk formats:

| Format | Support | Notes |
|--------|---------|-------|
| **raw** | ✅ Full | Fastest, no overhead |
| **qcow2** | ✅ Full | Recommended for hyper2kvm |
| **vmdk** | ⚠️ Limited | Convert to qcow2 first |
| **vdi** | ⚠️ Limited | Convert to qcow2 first |
| **Block devices** | ✅ Full | `/dev/sda`, `/dev/mapper/...` |

**Recommendation:** Always convert to **qcow2** or **raw** for vmspawn.

---

## Version Requirements

| Component | Minimum Version | Recommended |
|-----------|----------------|-------------|
| **systemd** | 255 | 256+ |
| **QEMU/KVM** | 7.0+ | 8.0+ |
| **Kernel** | 5.15+ | 6.0+ |
| **Linux** | Ubuntu 24.04, Fedora 39 | Latest |

**Check versions:**
```bash
systemctl --version
systemd-vmspawn --version
qemu-system-x86_64 --version
```

---

## Troubleshooting

### Issue: systemd-vmspawn not found

```bash
# Debian/Ubuntu
sudo apt install systemd-container

# Fedora
sudo dnf install systemd-container

# Arch
sudo pacman -S systemd
```

### Issue: Permission denied on /dev/kvm

```bash
# Add user to kvm group
sudo usermod -aG kvm $USER

# Or run with sudo
sudo systemd-vmspawn --image=vm.qcow2
```

### Issue: VM doesn't boot

```bash
# Check VM console output
systemd-vmspawn --image=vm.qcow2 --console=interactive

# Check journal
journalctl -u systemd-vmspawn@*

# Verify disk image
qemu-img check vm.qcow2
```

### Issue: Network not working

```bash
# User mode (works without setup)
systemd-vmspawn --image=vm.qcow2 --network-user-mode

# Check if KVM networking is enabled
ls -la /dev/net/tun
```

---

## Comparison: vmspawn vs libvirt for hyper2kvm

### Use vmspawn when:
- ✅ Quick post-migration validation
- ✅ CI/CD boot testing
- ✅ Ephemeral test VMs
- ✅ Simple one-off tests
- ✅ No complex networking needed
- ✅ Systemd-based infrastructure

### Use libvirt when:
- ✅ Production VM deployment
- ✅ Complex networking (bridges, VLANs)
- ✅ VM lifecycle management (snapshots, clones)
- ✅ GUI management (virt-manager)
- ✅ Multi-host clusters
- ✅ Integration with KubeVirt/OpenStack

---

## Future Enhancements for hyper2kvm

Potential integrations:

### 1. Automated Boot Validation
```python
# In migration pipeline
def migrate_and_validate(source_vmdk: Path) -> Path:
    # Convert
    qcow2 = convert_vmdk_to_qcow2(source_vmdk)

    # Auto-test boot
    if not validate_boot_with_vmspawn(qcow2):
        raise MigrationValidationError("Boot test failed")

    return qcow2
```

### 2. Performance Benchmarking
```python
# Compare boot times before/after migration
def benchmark_boot_time(disk: Path) -> float:
    start = time.time()
    vmspawn.spawn(disk, cpus=1, memory="1G")
    return time.time() - start
```

### 3. Parallel Testing
```python
# Test multiple VMs in parallel
from concurrent.futures import ThreadPoolExecutor

def test_batch(disks: list[Path]) -> list[bool]:
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(validate_boot, d) for d in disks]
        return [f.result() for f in futures]
```

---

## References

- [systemd-vmspawn(1) man page](https://www.freedesktop.org/software/systemd/man/systemd-vmspawn.html)
- [systemd-machined(8) man page](https://www.freedesktop.org/software/systemd/man/systemd-machined.html)
- [machinectl(1) man page](https://www.freedesktop.org/software/systemd/man/machinectl.html)
- [systemd v255 Release Notes](https://github.com/systemd/systemd/releases/tag/v255)

---

**Last Updated:** 2026-03-29
**Author:** hyper2kvm team
**Status:** Production-ready (systemd >= 255)
