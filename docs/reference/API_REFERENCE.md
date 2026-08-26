# API Reference

Complete API documentation for hyper2kvm vmspawn SDK.

## Core Classes

### MachineConfig

Configuration for a VM instance.

```python
from hyper2kvm.vmspawn import MachineConfig

config = MachineConfig(
    name="my-vm",
    image="/path/to/image.qcow2",
    memory=2048,        # MB
    cpus=2,
    tpm=False,          # Enable TPM emulation
    vsock=True,         # Enable vsock communication
    vsock_cid=None,     # Auto-assign vsock CID
)
```

#### Parameters

- **name** (str, required): Unique VM name
- **image** (str, required): Path to disk image
- **memory** (int): Memory in MB (default: 2048)
- **cpus** (int): CPU count (default: 2)
- **tpm** (bool): Enable TPM emulation (default: False)
- **vsock** (bool): Enable vsock (default: True)
- **vsock_cid** (int, optional): vsock CID (auto-assigned if None)

### Machine

Synchronous VM management.

```python
from hyper2kvm.vmspawn import Machine, MachineConfig

config = MachineConfig(name="test-vm", image="/path/to/image.qcow2")
machine = Machine(config)

# Start VM
machine.start()

# Check if running
if machine.is_running():
    print("VM is running")

# Execute command in VM
output = machine.exec("systemctl status")

# Get journal logs
logs = machine.get_journal()

# Stop VM
machine.stop()
```

#### Methods

##### start()

Start the VM.

```python
machine.start()
```

**Raises:**
- `VMStartError`: If VM fails to start
- `SystemdError`: If systemd-vmspawn not found

##### stop(force=False)

Stop the VM.

```python
machine.stop(force=True)  # Force stop
```

**Parameters:**
- **force** (bool): Force termination (default: False)

**Raises:**
- `VMStopError`: If VM fails to stop

##### is_running() → bool

Check if VM is running.

```python
if machine.is_running():
    print("Running")
```

**Returns:**
- bool: True if VM is running

##### exec(command: str) → str

Execute command in VM.

```python
output = machine.exec("ls -la /")
```

**Parameters:**
- **command** (str): Command to execute

**Returns:**
- str: Command output

**Raises:**
- `VMNotRunningError`: If VM is not running
- `VMExecError`: If command fails

##### get_journal(lines=100) → str

Get VM journal logs.

```python
logs = machine.get_journal(lines=50)
```

**Parameters:**
- **lines** (int): Number of lines (default: 100)

**Returns:**
- str: Journal logs

### AsyncMachine

Asynchronous VM management for parallel operations.

```python
from hyper2kvm.vmspawn import AsyncMachine, MachineConfig
import asyncio

async def main():
    config = MachineConfig(name="async-vm", image="/path/to/image.qcow2")
    machine = AsyncMachine(config)
    
    await machine.start()
    
    if await machine.is_running():
        output = await machine.exec("uptime")
        print(output)
    
    await machine.stop()

asyncio.run(main())
```

#### Methods

All methods are async versions of `Machine` methods:

- `async start()`
- `async stop(force=False)`
- `async is_running() → bool`
- `async exec(command: str) → str`
- `async get_journal(lines=100) → str`

### AsyncVMManager

Manage multiple VMs with rate limiting.

```python
from hyper2kvm.vmspawn import AsyncVMManager, MachineConfig
import asyncio

async def main():
    manager = AsyncVMManager(max_parallel=10)
    
    configs = [
        MachineConfig(name=f"vm-{i}", image=f"/images/vm-{i}.qcow2")
        for i in range(100)
    ]
    
    # Validate all VMs
    results = await manager.validate_batch(configs, timeout=300)
    
    for result in results:
        print(f"{result.config.name}: {result.success}")

asyncio.run(main())
```

#### Constructor

```python
AsyncVMManager(max_parallel=100)
```

**Parameters:**
- **max_parallel** (int): Maximum concurrent VMs (default: 100)

#### Methods

##### validate_vm(config, timeout=300) → dict

Validate a single VM.

```python
result = await manager.validate_vm(config, timeout=300)
```

**Parameters:**
- **config** (MachineConfig): VM configuration
- **timeout** (int): Validation timeout in seconds

**Returns:**
- dict: Validation result with success, checks, error

##### validate_batch(configs, timeout=300) → List[dict]

Validate multiple VMs in parallel.

```python
results = await manager.validate_batch(configs, timeout=300)
```

**Parameters:**
- **configs** (List[MachineConfig]): List of configurations
- **timeout** (int): Per-VM timeout

**Returns:**
- List[dict]: List of validation results

## Validators

### VMValidator

Basic VM validation.

```python
from hyper2kvm.vmspawn import VMValidator, MachineConfig

config = MachineConfig(name="test", image="/path/to/image.qcow2")
validator = VMValidator(config)

result = validator.validate(timeout=300)

if result.success:
    print("Validation passed")
    print(f"Systemd: {result.checks.systemd}")
    print(f"Network: {result.checks.network}")
    print(f"Boot: {result.checks.boot_complete}")
else:
    print(f"Failed: {result.error}")
```

#### Methods

##### validate(timeout=300) → ValidationResult

Run validation.

**Parameters:**
- **timeout** (int): Validation timeout

**Returns:**
- ValidationResult: Validation result object

**ValidationResult attributes:**
- **success** (bool): Overall success
- **checks** (object): Individual checks
  - **systemd** (bool): Systemd running
  - **network** (bool): Network configured
  - **boot_complete** (bool): Boot completed
- **error** (str, optional): Error message if failed

### KubernetesNodeValidator

Kubernetes node validation.

```python
from hyper2kvm.vmspawn import KubernetesNodeValidator, MachineConfig

config = MachineConfig(name="k8s-node", image="/path/to/k8s-node.qcow2")
validator = KubernetesNodeValidator(config)

result = validator.validate(timeout=600)

if result.success:
    print("K8s node validation passed")
    print(f"Kubelet: {result.checks.kubelet}")
    print(f"Container Runtime: {result.checks.container_runtime}")
    print(f"CNI: {result.checks.cni}")
```

#### Methods

Same as `VMValidator.validate()`, with additional checks:

**ValidationResult.checks attributes:**
- All VMValidator checks, plus:
- **kubelet** (bool): Kubelet running
- **container_runtime** (bool): Container runtime active
- **cni** (bool): CNI configured

## Exceptions

### VMStartError

Raised when VM fails to start.

```python
from hyper2kvm.vmspawn.exceptions import VMStartError

try:
    machine.start()
except VMStartError as e:
    print(f"Failed to start: {e}")
```

### VMStopError

Raised when VM fails to stop.

### VMNotRunningError

Raised when operation requires running VM.

### VMExecError

Raised when command execution fails.

### SystemdError

Raised for systemd-related errors.

## Utilities

### CleanupEngine

Automatic resource cleanup.

```python
from hyper2kvm.vmspawn.cleanup import CleanupEngine

cleanup = CleanupEngine()

# Register cleanup handlers
cleanup.register(machine.stop)

# Or use as context manager
with CleanupEngine() as cleanup:
    machine.start()
    cleanup.register(machine.stop)
    # Automatically cleaned up on exit
```

### VsockClient / VsockServer

Host-guest communication via vsock.

```python
from hyper2kvm.vmspawn.vsock import VsockClient, VsockServer

# In host
client = VsockClient(cid=3, port=9000)
client.send(b"Hello VM")
response = client.receive()

# In guest
server = VsockServer(port=9000)
data = server.receive()
server.send(b"Hello Host")
```

## Configuration

### Cloud-init Support

```python
from hyper2kvm.vmspawn.cloudinit import create_cloud_init_config

cloud_init = create_cloud_init_config(
    hostname="my-vm",
    users=[{
        "name": "admin",
        "ssh_authorized_keys": ["ssh-rsa ..."],
        "sudo": "ALL=(ALL) NOPASSWD:ALL"
    }]
)

config = MachineConfig(
    name="vm",
    image="image.qcow2",
    cloud_init=cloud_init
)
```

## Best Practices

### 1. Use Async for Parallel Operations

```python
# Good
manager = AsyncVMManager(max_parallel=50)
results = await manager.validate_batch(configs)

# Bad - synchronous in loop
for config in configs:
    machine = Machine(config)
    machine.start()  # Blocks!
```

### 2. Always Clean Up Resources

```python
# Good - cleanup guaranteed
with CleanupEngine() as cleanup:
    machine.start()
    cleanup.register(machine.stop)

# Bad - may leak resources
machine.start()
machine.stop()  # May not be called if error
```

### 3. Handle Errors Appropriately

```python
# Good
try:
    machine.start()
except VMStartError as e:
    logger.error(f"Failed to start {machine.name}: {e}")
    # Cleanup and retry
except SystemdError as e:
    logger.error(f"systemd-vmspawn not available: {e}")
    # Guide user to install

# Bad
machine.start()  # Uncaught exceptions crash program
```

### 4. Set Appropriate Timeouts

```python
# Good - based on expected boot time
validator.validate(timeout=300)  # 5 minutes for typical VM

# Better - based on image type
if config.kubernetes:
    timeout = 600  # K8s nodes need more time
else:
    timeout = 300

validator.validate(timeout=timeout)
```

## See Also

- [Quick Start Guide](QUICKSTART.md)
- [User Guide](USER_GUIDE.md)
- [Examples](../examples/)
- [Performance Guide](performance/BENCHMARKS.md)
