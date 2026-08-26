# Enhanced Features with RHEL 10 Compatibility

This guide covers the enhanced features added to hyper2kvm with full RHEL 10 compatibility through optional dependencies and stdlib fallbacks.

## Overview

hyper2kvm now includes enhanced features that provide better developer experience when optional dependencies are available, while maintaining **100% compatibility with RHEL 10** and other minimal environments through stdlib fallbacks.

### Design Philosophy

- **Optional by Default**: Enhanced features use optional dependencies
- **Graceful Degradation**: Falls back to stdlib implementations when dependencies unavailable
- **Zero Breaking Changes**: All existing code continues to work
- **Production Ready**: Works in RHEL 10, Fedora, Ubuntu, and all target platforms

## Feature Matrix

| Feature | With Optional Deps | RHEL 10 (stdlib only) | Implementation |
|---------|-------------------|----------------------|----------------|
| **Configuration Validation** | Pydantic (type-safe) | Manual validation | `hyper2kvm.config.validation` |
| **Retry Logic** | Tenacity (advanced) | Exponential backoff | `hyper2kvm.core.retry_enhanced` |
| **Logging** | Built-in (excellent!) | Built-in (excellent!) | `hyper2kvm.core.logger` ✅ |

## Installation Options

### Full Installation (Recommended for Development)

```bash
# All enhancements
pip install hyper2kvm[enhanced]

# Or install full (includes all optional deps)
pip install hyper2kvm[full]
```

### Selective Installation

```bash
# Just validation enhancements
pip install hyper2kvm[validation]

# Just retry enhancements
pip install hyper2kvm[retry]

# Just daemon mode
pip install hyper2kvm[daemon]
```

### Minimal Installation (RHEL 10 Compatible)

```bash
# Core only - everything still works!
pip install hyper2kvm
```

## 1. Configuration Validation

### Overview

Type-safe configuration validation with helpful error messages. Uses pydantic when available, falls back to manual validation on RHEL 10.

### Usage

```python
from hyper2kvm.config.validation import (
    NetworkConfig,
    VMwareSourceConfig,
    DiskConfig,
    ConfigValidationError,
)

# Create validated configuration
try:
    network = NetworkConfig(
        interface_name="eth0",
        mac_address="52:54:00:12:34:56",
        ip_address="192.168.1.10",
        dns_servers=["8.8.8.8"]
    )
    print(f"Network: {network.interface_name}")

except ConfigValidationError as e:
    print("Validation failed:")
    for error in e.errors:
        print(f"  {error['field']}: {error['message']}")
```

### Available Validators

#### NetworkConfig

Validates network interface configuration:

```python
NetworkConfig(
    interface_name: str,          # Must start with letter, lowercase alphanumeric
    mac_address: str = None,      # Format: XX:XX:XX:XX:XX:XX
    ip_address: str = None,       # IPv4 format
    gateway: str = None,          # IPv4 format
    dns_servers: List[str] = []   # Max 3 servers
)
```

#### VMwareSourceConfig

Validates VMware vSphere connection:

```python
VMwareSourceConfig(
    host: str,                    # vCenter/ESXi hostname
    username: str,
    password: str,
    vm_name: str = None,          # Either vm_name OR vm_uuid required
    vm_uuid: str = None,
    datacenter: str = None,
    datastore: str = None,
    port: int = 443,              # 1-65535
    verify_ssl: bool = True
)
```

#### DiskConfig

Validates disk configuration:

```python
DiskConfig(
    source_path: Path,            # Must exist and be a file
    output_format: str = "qcow2", # qcow2, raw, vmdk, vhd
    compression: bool = True,
    size_gb: int = None           # 1-16384 if specified
)
```

### Error Handling

```python
try:
    config = NetworkConfig(interface_name="0invalid")  # Starts with digit
except ConfigValidationError as e:
    # Uniform error interface works with or without pydantic
    for error in e.errors:
        print(f"{error['field']}: {error['message']}")
```

### Checking Availability

```python
from hyper2kvm.core.optional_imports import PYDANTIC_AVAILABLE

if PYDANTIC_AVAILABLE:
    print("Using pydantic for validation")
else:
    print("Using stdlib fallback validation")
```

## 2. Enhanced Retry Logic

### Overview

Robust retry logic with exponential backoff. Uses tenacity when available for advanced features, falls back to existing `core.retry` module on RHEL 10.

### Decorators

#### retry_network_operation

For network operations (HTTP, SSH, etc.):

```python
from hyper2kvm.core.retry_enhanced import retry_network_operation

@retry_network_operation(max_attempts=5, min_wait=2.0, max_wait=30.0)
def download_vmdk(url: str) -> bytes:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.content

# Automatically retries on network errors with exponential backoff
disk_data = download_vmdk("https://vcenter.example.com/disk.vmdk")
```

#### retry_vmware_api

For VMware vSphere API calls:

```python
from hyper2kvm.core.retry_enhanced import retry_vmware_api

@retry_vmware_api(max_attempts=3, min_wait=4.0, max_wait=10.0)
def get_vm_info(vmware_client, vm_name: str):
    return vmware_client.get_vm_by_name(vm_name)

# Automatically retries on authentication failures and network errors
vm = get_vm_info(client, "web-server-01")
```

#### retry_file_operation

For file system operations:

```python
from hyper2kvm.core.retry_enhanced import retry_file_operation

@retry_file_operation(max_attempts=3, wait_time=1.0)
def write_config(path: Path, content: str):
    with open(path, 'w') as f:
        f.write(content)

# Automatically retries on OSError, IOError
write_config(Path("/tmp/config.yaml"), yaml_content)
```

### Context Manager

For manual retry control:

```python
from hyper2kvm.core.retry_enhanced import RetryContext

with RetryContext(max_attempts=3, wait_time=2.0) as retry:
    for attempt in retry:
        try:
            result = risky_operation()
            break  # Success - exit loop
        except Exception as e:
            if attempt.is_last:
                raise  # Final attempt - give up
            logger.warning(f"Attempt {attempt.number} failed: {e}")
            # Will automatically retry
```

### Integration Example

```python
from hyper2kvm.vmware.clients.client import VMwareClient
from hyper2kvm.core.retry_enhanced import retry_vmware_api, retry_network_operation

class EnhancedVMwareClient(VMwareClient):
    """VMware client with automatic retry."""

    @retry_vmware_api(max_attempts=3)
    def connect(self):
        """Connect with automatic retry on auth failures."""
        return super().connect()

    @retry_vmware_api(max_attempts=5)
    def get_vm_by_name(self, vm_name: str):
        """Get VM with automatic retry."""
        return super().get_vm_by_name(vm_name)

    @retry_network_operation(max_attempts=5)
    def download_disk(self, url: str, output_path: Path):
        """Download disk with automatic retry and resume."""
        return super().download_disk(url, output_path)
```

### Checking Availability

```python
from hyper2kvm.core.optional_imports import TENACITY_AVAILABLE

if TENACITY_AVAILABLE:
    print("Using tenacity for retry")
else:
    print("Using stdlib fallback retry")
```

## 3. Logging (Built-in - No Optional Deps!)

### Overview

hyper2kvm already has an **excellent logging system** in `core.logger` that provides:

- ✅ JSON structured logging (like structlog!)
- ✅ Context-aware logging
- ✅ Beautiful console output with colors and emoji
- ✅ Process-aware logging for multiprocessing
- ✅ Rate-limited warnings
- ✅ File and console output

**No structlog needed!** The existing system works great on all platforms including RHEL 10.

### Basic Usage

```python
from hyper2kvm.core.logger import Log

# Setup logger
logger = Log.setup(
    verbose=2,           # 0=INFO, 1=INFO, 2=DEBUG, 3=TRACE
    json_logs=False,     # Set True for NDJSON output
    show_proc=True,      # Show process name (multiprocessing)
    show_pid=True,       # Show process ID
    log_file="/var/log/hyper2kvm/migration.log"
)

# Basic logging
logger.info("Migration started")
logger.debug("Detailed debug info")
logger.warning("Disk is large")
logger.error("Migration failed")
```

### Context-Aware Logging

Like structlog, but built-in:

```python
# Bind context that persists across log calls
log = Log.bind(logger, vm="web-server-01", hypervisor="vmware")

log.info("Starting export")
log.info("Export complete", extra={"ctx": {"duration_s": 45.2}})

# Output includes vm= and hypervisor= in every log line
```

### Helper Methods

```python
# Styled logging helpers
Log.step(logger, "Processing VM", vm="web-01")     # ➡️
Log.ok(logger, "Export completed", duration_s=45)   # ✅
Log.warn(logger, "Disk is large", size_gb=500)      # ⚠️
Log.fail(logger, "Export failed", error="timeout")  # 💥

# Rate-limited warnings
Log.warn_once(logger, "disk_warning", "Disk format is deprecated")
Log.warn_rl(logger, "slow_api", "API is slow", every_s=60.0)
```

### JSON Logging (Production)

Perfect for log aggregation, ELK, Loki, CloudWatch:

```python
logger = Log.setup(
    verbose=1,
    json_logs=True,     # NDJSON output
    show_proc=True,
    show_pid=True,
)

logger.info("Migration started", extra={
    "ctx": {
        "vm": "web-01",
        "hypervisor": "vmware",
        "disk_count": 3
    }
})

# Output (one JSON object per line):
# {"ts": "2026-01-23T17:30:45.123Z", "level": "INFO", "msg": "Migration started",
#  "ctx": {"vm": "web-01", "hypervisor": "vmware", "disk_count": 3}, ...}
```

### File Logging

```python
logger = Log.setup(
    verbose=2,
    log_file="/var/log/hyper2kvm/migration.log",  # Also writes to file
    json_logs=True,     # JSON format in file too
)

# Logs go to both stderr (console) and file
logger.info("Logged to both console and file")
```

## Complete Example

```python
#!/usr/bin/env python3
"""Complete example using all enhanced features."""

from pathlib import Path
from hyper2kvm.config.validation import VMwareSourceConfig, ConfigValidationError
from hyper2kvm.core.retry_enhanced import retry_vmware_api, retry_network_operation
from hyper2kvm.core.logger import Log

# Check what's available
from hyper2kvm.core.optional_imports import PYDANTIC_AVAILABLE, TENACITY_AVAILABLE

print(f"Pydantic: {PYDANTIC_AVAILABLE}, Tenacity: {TENACITY_AVAILABLE}")
print("Note: Everything works even if both are False!")

# 1. Validate configuration
try:
    vmware_config = VMwareSourceConfig(
        host="vcenter.example.com",
        username="admin",
        password="secret",
        vm_name="web-server-01"
    )
except ConfigValidationError as e:
    print(f"Config validation failed:")
    for error in e.errors:
        print(f"  {error['field']}: {error['message']}")
    exit(1)

# 2. Setup logging
logger = Log.setup(
    verbose=2,
    json_logs=False,
    show_proc=True,
)

log = Log.bind(logger,
    vm=vmware_config.vm_name,
    host=vmware_config.host
)

# 3. Define operations with retry
@retry_vmware_api(max_attempts=3)
def connect_to_vmware():
    log.info("Connecting to vSphere")
    # ... connection logic ...
    return True

@retry_network_operation(max_attempts=5)
def download_vm_disk(url: str):
    log.info("Downloading VM disk", url=url)
    # ... download logic ...
    return "/tmp/disk.vmdk"

# 4. Run migration
Log.step(logger, "Starting migration")

try:
    connect_to_vmware()
    Log.ok(logger, "Connected to vSphere")

    disk_path = download_vm_disk("https://vcenter.example.com/disk.vmdk")
    Log.ok(logger, "Downloaded VM disk", path=disk_path)

    Log.ok(logger, "Migration completed successfully")

except Exception as e:
    Log.fail(logger, "Migration failed", error=str(e))
    raise
```

## Testing

### Running Tests

```bash
# Run all tests (works with or without optional deps)
pytest tests/unit/test_config/test_validation_compat.py
pytest tests/unit/test_core/test_retry_compat.py

# Run with coverage
pytest --cov=hyper2kvm tests/

# Test RHEL 10 compatibility (uninstall optional deps)
pip uninstall pydantic tenacity -y
pytest tests/  # Should still pass!
```

### Test Both Code Paths

```python
# tests/unit/test_config/test_validation_compat.py
import pytest
from hyper2kvm.core.optional_imports import PYDANTIC_AVAILABLE

@pytest.mark.skipif(not PYDANTIC_AVAILABLE, reason="pydantic not available")
def test_pydantic_specific_feature():
    """Test that only runs when pydantic is available."""
    # Test pydantic-specific behavior
    pass

def test_works_with_or_without_pydantic():
    """Test that works regardless of pydantic availability."""
    # Test common behavior
    pass
```

## Migration Guide

### From Existing Code

No migration needed! All existing code continues to work. To adopt enhanced features:

1. **Add optional dependencies** (or don't for RHEL 10):
   ```bash
   pip install hyper2kvm[enhanced]
   ```

2. **Use enhanced imports**:
   ```python
   # Old (still works)
   from hyper2kvm.core.retry import retry_with_backoff

   # New (enhanced, but falls back automatically)
   from hyper2kvm.core.retry_enhanced import retry_network_operation
   ```

3. **Add configuration validation**:
   ```python
   # Old
   vmware_config = config_dict['vmware']

   # New (validated)
   from hyper2kvm.config.validation import VMwareSourceConfig
   vmware_config = VMwareSourceConfig(**config_dict['vmware'])
   ```

## FAQ

### Q: Do I need to install optional dependencies?

**A:** No! Everything works without them. Optional dependencies provide enhanced features but fall back to stdlib implementations automatically.

### Q: Will this work on RHEL 10?

**A:** Yes! All features have stdlib fallbacks that work on RHEL 10 and other minimal environments.

### Q: Is logging better with structlog?

**A:** No need for structlog! The built-in `hyper2kvm.core.logger` already provides JSON logging, context binding, and all features you'd want from structlog.

### Q: What if pydantic/tenacity become available later?

**A:** The code automatically detects and uses them! No code changes needed. Just install and restart.

### Q: Can I check what's available at runtime?

**A:** Yes:
```python
from hyper2kvm.core.optional_imports import (
    PYDANTIC_AVAILABLE,
    TENACITY_AVAILABLE,
    WATCHDOG_AVAILABLE,
)

print(f"Pydantic: {PYDANTIC_AVAILABLE}")
print(f"Tenacity: {TENACITY_AVAILABLE}")
print(f"Watchdog: {WATCHDOG_AVAILABLE}")
```

## Summary

✅ **Configuration Validation**: Type-safe with pydantic, manual fallback on RHEL 10
✅ **Enhanced Retry**: Advanced with tenacity, stdlib fallback on RHEL 10
✅ **Logging**: Already excellent with built-in system - no structlog needed!
✅ **RHEL 10 Compatible**: 100% compatible with or without optional deps
✅ **Zero Breaking Changes**: All existing code continues to work

For more examples, see `examples/enhanced_features_example.py`.
