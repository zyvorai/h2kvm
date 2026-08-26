# hyper2kvm API Reference

Complete API documentation for using hyper2kvm as a Python library.

## Table of Contents

1. [Core API](#core-api)
2. [Converters](#converters)
3. [Fixers](#fixers)
4. [Orchestrator](#orchestrator)
5. [Manifest API](#manifest-api)
6. [VMware Integration](#vmware-integration)
7. [Configuration](#configuration)
8. [Error Handling](#error-handling)

---

## Core API

### `hyper2kvm.core`

Main entry point for programmatic VM conversion.

#### `convert_vm()`

Convert a VM image from VMware format to KVM-compatible format.

```python
from hyper2kvm.core import convert_vm

result = convert_vm(
    input_path="/path/to/vm.vmdk",
    output_path="/path/to/output.qcow2",
    os_type="linux",
    config=None
)
```

**Parameters:**
- `input_path` (str): Path to input VMDK file
- `output_path` (str): Path for output QCOW2 file
- `os_type` (str): Operating system type (`"linux"`, `"windows"`)
- `config` (dict, optional): Configuration options

**Returns:**
- `dict`: Conversion result with status and metadata

**Example:**
```python
result = {
    "success": True,
    "input_file": "/path/to/vm.vmdk",
    "output_file": "/path/to/output.qcow2",
    "duration_seconds": 125.4,
    "original_size_mb": 10240,
    "converted_size_mb": 8192,
    "drivers_injected": ["virtio_blk", "virtio_net"],
}
```

#### `inspect_image()`

Inspect a VM image to determine OS type and configuration.

```python
from hyper2kvm.core import inspect_image

info = inspect_image("/path/to/vm.vmdk")
```

**Returns:**
```python
{
    "os_type": "linux",
    "distro": "rhel",
    "major_version": 9,
    "kernel_version": "5.14.0",
    "filesystems": ["/dev/sda1", "/dev/sda2"],
    "boot_loader": "grub2",
}
```

---

## Converters

### `hyper2kvm.converters.qemu`

QEMU-based image conversion.

#### `QEMUConverter`

```python
from hyper2kvm.converters.qemu import QEMUConverter

converter = QEMUConverter(
    input_format="vmdk",
    output_format="qcow2",
    compression=True
)

converter.convert(
    source="/path/to/input.vmdk",
    destination="/path/to/output.qcow2"
)
```

**Methods:**

##### `convert(source, destination, **options)`

Convert image format.

**Options:**
- `compression` (bool): Enable compression (default: True)
- `cache` (str): Cache mode (`"none"`, `"writeback"`, `"writethrough"`)
- `sparse` (bool): Create sparse image (default: True)

**Returns:** `ConversionResult` object

##### `get_info(image_path)`

Get image information.

```python
info = converter.get_info("/path/to/image.qcow2")
# {
#   "format": "qcow2",
#   "virtual_size_gb": 20,
#   "actual_size_gb": 8,
#   "backing_file": None
# }
```

---

## Fixers

### `hyper2kvm.fixers.bootloader`

Bootloader configuration fixers.

#### `GRUBFixer`

```python
from hyper2kvm.fixers.bootloader.grub import GRUBFixer
import guestfs

g = guestfs.GuestFS(python_return_dict=True)
g.add_drive("/path/to/image.qcow2")
g.launch()

fixer = GRUBFixer(root="/dev/sda1", g=g)
result = fixer.regenerate()
```

**Methods:**

##### `regenerate()`

Regenerate GRUB configuration for KVM compatibility.

**Returns:**
```python
{
    "success": True,
    "grub_config": "/boot/grub2/grub.cfg",
    "initramfs_regenerated": True,
    "drivers_added": ["virtio_blk", "virtio_scsi"],
}
```

##### `detect_grub_version()`

Detect installed GRUB version.

**Returns:** `str` - GRUB version ("grub2", "grub-legacy")

#### `SystemdBootFixer`

For systemd-boot systems.

```python
from hyper2kvm.fixers.bootloader.systemdboot import SystemdBootFixer

fixer = SystemdBootFixer(root="/dev/sda1", g=g)
result = fixer.fix()
```

### `hyper2kvm.fixers.network`

Network configuration fixers.

#### `NetworkFixer`

```python
from hyper2kvm.fixers.network import NetworkFixer

fixer = NetworkFixer(root="/dev/sda1", g=g, distro="rhel")
result = fixer.fix_network_config()
```

**Methods:**

##### `fix_network_config()`

Update network configuration for virtio_net.

**Returns:**
```python
{
    "interfaces_updated": ["eth0", "ens33"],
    "driver_changed_from": "vmxnet3",
    "driver_changed_to": "virtio_net",
    "config_files_modified": [
        "/etc/sysconfig/network-scripts/ifcfg-eth0"
    ],
}
```

##### `detect_network_manager()`

Detect network management system.

**Returns:** `str` - (`"NetworkManager"`, `"systemd-networkd"`, `"netplan"`, `"ifupdown"`)

---

## Orchestrator

### `hyper2kvm.orchestrator`

High-level orchestration for complete VM migrations.

#### `MigrationOrchestrator`

```python
from hyper2kvm.orchestrator import MigrationOrchestrator

orchestrator = MigrationOrchestrator(
    config_file="/etc/hyper2kvm/config.yaml"
)

result = orchestrator.migrate_vm(
    vm_name="web-server-01",
    source="vsphere://vcenter.example.com/vm/web-server-01",
    destination="/var/lib/libvirt/images/web-server-01.qcow2"
)
```

**Methods:**

##### `migrate_vm(**kwargs)`

Perform complete VM migration.

**Parameters:**
- `vm_name` (str): VM name
- `source` (str): Source location (vSphere, AWS, disk path)
- `destination` (str): Destination path
- `auto_detect_os` (bool): Auto-detect OS type (default: True)
- `inject_drivers` (bool): Inject virtio drivers (default: True)
- `validate_boot` (bool): Validate boot configuration (default: True)

**Returns:** `MigrationResult`

##### `migrate_batch(vms, parallel=False, max_workers=4)`

Migrate multiple VMs.

```python
vms = [
    {"name": "vm-1", "source": "...", "destination": "..."},
    {"name": "vm-2", "source": "...", "destination": "..."},
]

results = orchestrator.migrate_batch(vms, parallel=True, max_workers=4)
```

**Returns:** `list[MigrationResult]`

#### `MigrationResult`

Result object from migration operations.

**Attributes:**
```python
class MigrationResult:
    success: bool
    vm_name: str
    duration_seconds: float
    stages: dict[str, StageResult]
    errors: list[str]
    warnings: list[str]
    artifacts: dict[str, str]  # Generated files
```

**Methods:**

##### `to_dict()`

Convert to dictionary.

##### `to_json()`

Export as JSON string.

##### `save_report(path)`

Save detailed report to file.

---

## Manifest API

### `hyper2kvm.manifest`

Artifact Manifest v1.0 API for declarative workflows.

#### `ManifestLoader`

```python
from hyper2kvm.manifest import ManifestLoader

loader = ManifestLoader()
manifest = loader.load_from_file("/path/to/manifest.json")
```

**Methods:**

##### `load_from_file(path)`

Load manifest from JSON file.

**Returns:** `ArtifactManifest` object

##### `load_from_dict(data)`

Load manifest from dictionary.

##### `validate(manifest)`

Validate manifest against JSON schema.

**Returns:** `ValidationResult`

#### `ArtifactManifest`

Manifest object representing VM metadata.

**Attributes:**
```python
class ArtifactManifest:
    version: str  # "1.0"
    source: SourceInfo
    vm: VMInfo
    disks: list[DiskInfo]
    network: NetworkInfo
    metadata: dict
```

**Methods:**

##### `get_primary_disk()`

Get primary boot disk.

**Returns:** `DiskInfo`

##### `get_network_adapters()`

Get all network adapters.

**Returns:** `list[NetworkAdapter]`

##### `to_dict()`

Convert to dictionary.

#### `ManifestExecutor`

Execute conversion based on manifest.

```python
from hyper2kvm.manifest import ManifestExecutor

executor = ManifestExecutor(manifest)
result = executor.execute(
    output_dir="/var/lib/libvirt/images",
    dry_run=False
)
```

**Methods:**

##### `execute(output_dir, dry_run=False, stages=None)`

Execute manifest-driven conversion.

**Parameters:**
- `output_dir` (str): Output directory
- `dry_run` (bool): Preview without executing
- `stages` (list, optional): Specific stages to run

**Returns:** `ExecutionResult`

---

## VMware Integration

### `hyper2kvm.vmware`

vSphere integration for direct VM exports.

#### `VSphereClient`

```python
from hyper2kvm.vmware import VSphereClient

client = VSphereClient(
    host="vcenter.example.com",
    username="administrator@vsphere.local",
    password="password",
    verify_ssl=False
)

client.connect()
```

**Methods:**

##### `list_vms(folder=None, datacenter=None)`

List available VMs.

**Returns:** `list[VMInfo]`

##### `export_vm(vm_name, destination, format="ova")`

Export VM from vSphere.

**Parameters:**
- `vm_name` (str): VM name or MoRef
- `destination` (str): Export destination path
- `format` (str): Export format (`"ova"`, `"ovf"`, `"vmdk"`)

**Returns:** `ExportResult`

##### `get_vm_info(vm_name)`

Get VM information.

**Returns:**
```python
{
    "name": "web-server-01",
    "power_state": "poweredOn",
    "guest_os": "rhel9_64Guest",
    "memory_mb": 8192,
    "num_cpu": 4,
    "disks": [...],
    "networks": [...],
}
```

---

## Configuration

### `hyper2kvm.config`

Configuration management.

#### `Config`

```python
from hyper2kvm.config import Config

config = Config.load_from_file("/etc/hyper2kvm/config.yaml")

# Or create programmatically
config = Config(
    default_output_format="qcow2",
    compression=True,
    inject_drivers=True,
    log_level="INFO"
)
```

**Attributes:**
```python
class Config:
    default_output_format: str
    compression: bool
    inject_drivers: bool
    log_level: str
    cache_dir: str
    temp_dir: str
    parallel_conversions: int
    vsphere: VSphereConfig
    storage: StorageConfig
```

**Methods:**

##### `save_to_file(path)`

Save configuration to YAML file.

##### `validate()`

Validate configuration.

**Returns:** `bool`

---

## Error Handling

### Exception Classes

```python
from hyper2kvm.exceptions import (
    ConversionError,
    ImageInspectionError,
    DriverInjectionError,
    ManifestValidationError,
    VSphereConnectionError,
)
```

#### `ConversionError`

Base exception for conversion errors.

```python
try:
    convert_vm(...)
except ConversionError as e:
    print(f"Conversion failed: {e}")
    print(f"Stage: {e.stage}")
    print(f"Details: {e.details}")
```

**Attributes:**
- `message` (str): Error message
- `stage` (str): Stage where error occurred
- `details` (dict): Additional error details

#### `ImageInspectionError`

Raised when image inspection fails.

#### `DriverInjectionError`

Raised when driver injection fails.

#### `ManifestValidationError`

Raised when manifest validation fails.

**Attributes:**
- `errors` (list): List of validation errors

---

## Advanced Usage Examples

### Example 1: Programmatic Conversion with Custom Options

```python
from hyper2kvm.core import convert_vm
from hyper2kvm.config import Config

# Create custom configuration
config = Config(
    default_output_format="qcow2",
    compression=True,
    inject_drivers=True,
    log_level="DEBUG",
    temp_dir="/tmp/hyper2kvm"
)

# Convert VM
result = convert_vm(
    input_path="/mnt/vmware/vm-template.vmdk",
    output_path="/var/lib/libvirt/images/vm-template.qcow2",
    os_type="linux",
    config=config
)

if result["success"]:
    print(f"✓ Conversion completed in {result['duration_seconds']}s")
    print(f"✓ Size reduced from {result['original_size_mb']}MB to {result['converted_size_mb']}MB")
else:
    print(f"✗ Conversion failed: {result['error']}")
```

### Example 2: Manifest-Driven Workflow

```python
from hyper2kvm.manifest import ManifestLoader, ManifestExecutor

# Load manifest
loader = ManifestLoader()
manifest = loader.load_from_file("/exports/web-server-01/manifest.json")

# Validate manifest
validation = loader.validate(manifest)
if not validation.is_valid:
    print(f"Invalid manifest: {validation.errors}")
    exit(1)

# Execute conversion
executor = ManifestExecutor(manifest)
result = executor.execute(
    output_dir="/var/lib/libvirt/images",
    dry_run=False,
    stages=["INSPECT", "CONVERT", "FIX_DRIVERS"]
)

# Save detailed report
result.save_report("/var/log/hyper2kvm/report.json")
```

### Example 3: Batch Migration from vSphere

```python
from hyper2kvm.vmware import VSphereClient
from hyper2kvm.orchestrator import MigrationOrchestrator

# Connect to vSphere
client = VSphereClient(
    host="vcenter.example.com",
    username="admin@vsphere.local",
    password="password"
)
client.connect()

# List VMs in folder
vms = client.list_vms(folder="Production/Web Servers")

# Create orchestrator
orchestrator = MigrationOrchestrator()

# Prepare migration list
migrations = []
for vm in vms:
    migrations.append({
        "name": vm.name,
        "source": f"vsphere://{client.host}/vm/{vm.moref}",
        "destination": f"/var/lib/libvirt/images/{vm.name}.qcow2"
    })

# Execute batch migration (4 parallel)
results = orchestrator.migrate_batch(
    migrations,
    parallel=True,
    max_workers=4
)

# Report results
successful = sum(1 for r in results if r.success)
print(f"Migrated {successful}/{len(results)} VMs successfully")
```

### Example 4: Custom Fixer Pipeline

```python
import guestfs
from hyper2kvm.fixers.bootloader.grub import GRUBFixer
from hyper2kvm.fixers.network import NetworkFixer

# Open image
g = guestfs.GuestFS(python_return_dict=True)
g.add_drive("/var/lib/libvirt/images/vm.qcow2")
g.launch()

# Inspect OS
roots = g.inspect_os()
root = roots[0]

# Apply fixers
grub_fixer = GRUBFixer(root=root, g=g)
grub_result = grub_fixer.regenerate()

network_fixer = NetworkFixer(root=root, g=g, distro="rhel")
network_result = network_fixer.fix_network_config()

# Cleanup
g.sync()
g.umount_all()
g.close()

print(f"GRUB: {grub_result['success']}")
print(f"Network: {network_result['interfaces_updated']}")
```

---

## Type Hints

hyper2kvm includes comprehensive type hints for IDE auto-completion:

```python
from typing import List, Dict, Optional
from hyper2kvm.core import convert_vm
from hyper2kvm.types import ConversionResult, VMInfo

def batch_convert(vms: List[VMInfo]) -> List[ConversionResult]:
    results = []
    for vm in vms:
        result: ConversionResult = convert_vm(
            input_path=vm.disk_path,
            output_path=f"/output/{vm.name}.qcow2",
            os_type=vm.os_type
        )
        results.append(result)
    return results
```

---

## Logging

Configure logging for library usage:

```python
import logging
from hyper2kvm import set_log_level

# Set log level
set_log_level("DEBUG")

# Or configure directly
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger('hyper2kvm')
logger.setLevel(logging.DEBUG)
```

---

## See Also

- [Quick Start Guide](./03-Quick-Start.md)
- [CLI Reference](./04-CLI-Reference.md)
- [YAML Configuration](./05-YAML-Examples.md)
- [Library API Examples](./08-Library-API.md)
- [Manifest Workflow](./Manifest-Workflow.md)
