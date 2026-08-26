# H2KVM vmspawn SDK

Production-grade Python SDK for VM validation using systemd-vmspawn.

## Overview

The vmspawn SDK provides a complete solution for validating migrated VMs at scale, supporting everything from single VM testing to massive parallel validation of 1000+ VMs.

## Features

- ✅ **Synchronous and Async APIs** - Choose based on your needs
- ✅ **Massive Scale** - Validate 1000+ VMs in parallel with rate limiting
- ✅ **TPM Emulation** - Test LUKS auto-unlock and secure boot
- ✅ **vsock Communication** - Host-guest communication without network
- ✅ **cloud-init Injection** - Configure VMs on first boot
- ✅ **Kubernetes Validation** - Validate K8s nodes before joining cluster
- ✅ **Automatic Cleanup** - Resource cleanup on success or failure
- ✅ **Production-Ready** - Exception handling, logging, timeouts

## Quick Start

### Installation

```bash
# Install systemd-vmspawn (systemd >= 255)
sudo apt install systemd-container  # Debian/Ubuntu
sudo dnf install systemd-container  # Fedora

# Verify installation
systemd-vmspawn --version
```

### Simple Example

```python
from pathlib import Path
from h2kvm.vmspawn import VMSpawnManager, VMValidator

# Create manager
manager = VMSpawnManager()

# Create and start VM
machine = manager.create(
    name="test-vm",
    image=Path("/var/lib/h2kvm/migrated-vm.qcow2"),
    memory_mb=2048,
    cpus=2,
)

manager.start("test-vm")

# Validate
validator = VMValidator(machine)
if validator.validate():
    print("✅ VM validation passed!")

# Cleanup
manager.stop("test-vm")
```

## Async API for Scale

### Single VM (Async)

```python
import asyncio
from pathlib import Path
from h2kvm.vmspawn.async_machine import AsyncMachine
from h2kvm.vmspawn.async_validator import AsyncValidator

async def validate_vm():
    machine = AsyncMachine(
        name="test-vm",
        image=Path("/var/lib/h2kvm/vm.qcow2"),
        memory_mb=2048,
        cpus=2,
    )

    await machine.start()
    await machine.wait_running()

    validator = AsyncValidator(machine)
    result = await validator.validate()

    await machine.stop()
    return result

asyncio.run(validate_vm())
```

### Batch Validation (100 VMs)

```python
from h2kvm.vmspawn.async_machine import AsyncMachine
from h2kvm.vmspawn.async_manager import AsyncVMManager
from h2kvm.vmspawn.async_validator import AsyncValidator

async def validate_batch():
    # Create 100 VMs
    machines = [
        AsyncMachine(f"vm-{i}", Path(f"/images/vm-{i}.qcow2"))
        for i in range(100)
    ]

    # Manager with rate limiting (max 20 concurrent)
    manager = AsyncVMManager(max_parallel=20)

    # Start all VMs
    await manager.start_all(machines)

    # Validate all VMs
    results = await manager.validate_batch(machines, AsyncValidator)

    # Cleanup
    from h2kvm.vmspawn.cleanup import CleanupEngine
    cleanup = CleanupEngine(machines)
    await cleanup.cleanup_all()

    return results

asyncio.run(validate_batch())
```

### Massive Scale (1000 VMs)

```python
async def validate_1000_vms():
    machines = [
        AsyncMachine(f"vm-{i}", Path("/images/base.qcow2"),
                    memory_mb=512, cpus=1)
        for i in range(1000)
    ]

    manager = AsyncVMManager(max_parallel=100)
    await manager.start_all(machines)

    results = await manager.validate_batch(machines, AsyncValidator)

    # Cleanup
    cleanup = CleanupEngine(machines)
    await cleanup.cleanup_all(graceful=False)  # Force for speed

    passed = sum(1 for r in results.values() if r)
    print(f"Results: {passed}/1000 passed")
```

## Advanced Features

### TPM Support

```python
machine = AsyncMachine(
    name="secure-vm",
    image=Path("/images/encrypted.qcow2"),
    tpm=True,  # Enable TPM emulation
)
```

### cloud-init Injection

```python
from h2kvm.vmspawn.cloudinit import create_cloud_init_config

cloud_init = create_cloud_init_config(
    hostname="web-server",
    users=["admin"],
    ssh_authorized_keys=["ssh-rsa AAAAB3..."],
    packages=["nginx", "curl"],
    runcmd=["systemctl enable nginx"],
)

machine = AsyncMachine(
    name="web-server",
    image=Path("/images/base.qcow2"),
    cloud_init=cloud_init,
)
```

### vsock Communication

Host side:
```python
from h2kvm.vmspawn.vsock import VsockClient

client = VsockClient(cid=3, port=9000)

# Health check
if client.health_check():
    print("✅ VM is healthy")

# Send custom message
response = client.send(b"GET /status")
```

Guest side (inside VM):
```python
from h2kvm.vmspawn.vsock import VsockServer

server = VsockServer(port=9000)

def handler(message):
    if message == b"PING":
        return b"PONG"
    return b"OK"

server.handle(handler)
```

### Kubernetes Node Validation

```python
from h2kvm.vmspawn.async_machine import AsyncMachine
from h2kvm.vmspawn.validator import KubernetesNodeValidator

async def validate_k8s_node():
    machine = AsyncMachine(
        name="k8s-node-1",
        image=Path("/images/k8s-node.qcow2"),
        memory_mb=4096,
        cpus=4,
    )

    await machine.start()
    await machine.wait_running()

    # Validate K8s components
    validator = KubernetesNodeValidator(machine)

    if await validator.validate():
        print("✅ Kubernetes node ready!")
        # Node can now join cluster

    await machine.stop()
```

## Integration with H2KVM Pipeline

```python
from pathlib import Path
from h2kvm.converters import convert_vmdk_to_qcow2
from h2kvm.vmspawn import VMSpawnManager, VMValidator

def migrate_and_validate(vmdk_path: Path) -> Path:
    """
    Complete migration pipeline with automatic validation.
    """
    # Step 1: Convert
    qcow2 = convert_vmdk_to_qcow2(vmdk_path)

    # Step 2: Validate with vmspawn
    manager = VMSpawnManager()
    machine = manager.create(
        name="validation-test",
        image=qcow2,
        memory_mb=2048,
        cpus=2,
    )

    try:
        manager.start("validation-test")

        validator = VMValidator(machine)

        if not validator.validate():
            raise ValueError("VM validation failed - boot test unsuccessful")

        print("✅ Migration validated successfully")
        return qcow2

    finally:
        manager.stop("validation-test")
```

## API Reference

### Sync API

**VMSpawnManager** - High-level manager
- `create(name, image, **kwargs)` - Create VM configuration
- `start(name)` - Start and wait for boot
- `stop(name)` - Graceful shutdown
- `destroy(name)` - Stop and remove

**Machine** - Low-level operations
- `start()` - Start VM
- `stop()` - Graceful shutdown
- `terminate()` - Force terminate
- `status()` - Get VM status
- `exec(command)` - Execute command in VM
- `journal(lines)` - Get logs

**VMValidator** - Validation checks
- `validate()` - Run all checks
- `check_systemd()` - systemd status
- `check_network()` - Network up
- `check_boot_complete()` - Boot finished

### Async API

**AsyncVMManager** - Async manager
- `create_machine()` - Create async machine
- `start_machine(machine)` - Start with rate limiting
- `start_all(machines)` - Parallel start
- `validate_batch(machines, validator_class)` - Parallel validation

**AsyncMachine** - Async operations
- `async start()` - Start VM
- `async wait_running()` - Wait for boot
- `async exec(command)` - Execute command
- `async is_running()` - Check status

**AsyncValidator** - Async validation
- `async validate()` - Run checks
- `async check_systemd()` - systemd check
- `async check_network()` - Network check

**CleanupEngine** - Resource cleanup
- `async cleanup_all(graceful)` - Cleanup all VMs
- `async cleanup_failed()` - Cleanup failed VMs
- `async cleanup_by_pattern(pattern)` - Pattern matching

## Performance

On modern server hardware:

| Scale | VMs | Time | Concurrent |
|-------|-----|------|------------|
| Small | 10 | ~15s | 5 |
| Medium | 100 | ~60s | 20 |
| Large | 1000 | ~120s | 100 |

Factors:
- Disk I/O speed
- CPU cores
- Available RAM
- VM image size

## Requirements

- systemd >= 255 (Ubuntu 24.04+, Fedora 39+)
- QEMU/KVM >= 7.0
- Python >= 3.10
- `/dev/kvm` access
- Sufficient RAM for concurrent VMs

## Troubleshooting

### Permission denied on /dev/kvm

```bash
sudo usermod -aG kvm $USER
# Or run with sudo
```

### VM doesn't boot

```bash
# Check VM console
systemd-vmspawn --image=vm.qcow2 --console=interactive

# Verify disk image
qemu-img check vm.qcow2
```

### Rate limiting errors

Reduce `max_parallel` in AsyncVMManager:

```python
manager = AsyncVMManager(max_parallel=20)  # Reduce from 100
```

## Examples

See `examples/vmspawn_validation_example.py` for complete working examples.

## License

Apache-2.0

---

**Last Updated:** 2026-03-29
**Status:** Production-ready
**Maintainer:** h2kvm team
