# Developer Guide - New Patterns and Best Practices

This guide covers new abstractions and patterns introduced to improve code quality and consistency in h2kvm.

## Table of Contents

1. [CommandRunner - Standardized Command Execution](#commandrunner)
2. [Exception Hierarchy - Consistent Error Handling](#exception-hierarchy)
3. [Migration Examples](#migration-examples)
4. [Best Practices](#best-practices)

---

## CommandRunner - Standardized Command Execution

### Overview

The `CommandRunner` class (`h2kvm/core/command_runner.py`) provides a standardized way to execute shell commands with:
- Automatic retry with exponential backoff
- Timeout enforcement
- Structured logging
- Error capture with context
- Sudo support
- Dry-run mode

### Basic Usage

```python
from h2kvm.core.command_runner import CommandRunner

# Create runner (typically in __init__)
runner = CommandRunner(logger=self.logger, dry_run=False)

# Simple execution
result = runner.run("ls -la /tmp")
if result.success:
    logger.info(f"Command completed in {result.duration:.2f}s")
    logger.info(f"Output: {result.stdout}")
```

### With Retry Logic

```python
# Retry up to 3 times on failure
result = runner.run(
    "mount /dev/sda1 /mnt",
    retries=3,
    use_sudo=True
)
```

### With Timeout

```python
# Timeout after 60 seconds
result = runner.run(
    "rsync -av /source/ /dest/",
    timeout=60.0
)
```

### Error Handling

```python
# Manual error checking
result = runner.run("somecommand")
if result.failed:
    logger.error(f"Command failed: {result.stderr}")
    # Handle error...

# Automatic error raising
try:
    result = runner.run_checked("somecommand")  # Raises on failure
    # Success handling...
except CommandError as e:
    logger.error(f"Command failed: {e.user_message()}")
```

### Migration Example

**Before (old pattern):**

```python
import subprocess

try:
    result = subprocess.run(
        ["mount", "/dev/sda1", "/mnt"],
        capture_output=True,
        text=True,
        timeout=300,
        check=True
    )
    self.logger.info(f"Mount succeeded: {result.stdout}")
except subprocess.CalledProcessError as e:
    self.logger.error(f"Mount failed: {e.stderr}")
    raise
except subprocess.TimeoutExpired:
    self.logger.error("Mount timed out")
    raise
```

**After (new pattern):**

```python
from h2kvm.core.command_runner import CommandRunner

runner = CommandRunner(logger=self.logger)
result = runner.run(
    "mount /dev/sda1 /mnt",
    timeout=300,
    use_sudo=True,
    retries=2
)

if result.success:
    self.logger.info(f"Mount succeeded in {result.duration:.2f}s")
else:
    self.logger.error(f"Mount failed after {result.retries} retries: {result.stderr}")
    raise CommandError(
        code=result.exit_code,
        msg="Failed to mount partition",
        context={"device": "/dev/sda1", "mount_point": "/mnt"}
    )
```

### Advanced Features

#### Dry-Run Mode

```python
# Initialize with dry_run=True
runner = CommandRunner(logger=logger, dry_run=True)

# Commands are logged but not executed
result = runner.run("rm -rf /dangerous/path")
# Output: [DRY RUN] Would execute: rm -rf /dangerous/path
```

#### Custom Retry Parameters

```python
runner = CommandRunner(
    logger=logger,
    default_retries=3,      # Default retry count
    retry_delay=2.0,        # Initial delay (seconds)
    retry_backoff=2.0,      # Backoff multiplier
)

# This command will retry with delays: 2s, 4s, 8s
result = runner.run("flaky-command")
```

#### Legacy Compatibility

```python
# Returns tuple instead of CommandResult (for gradual migration)
exit_code, stdout, stderr = runner.run_silent("command")
```

---

## Exception Hierarchy - Consistent Error Handling

### Overview

A comprehensive exception hierarchy (`h2kvm/core/exceptions.py`) provides:
- Subsystem-specific exceptions
- Consistent error context and redaction
- User-friendly error messages
- Solutions and documentation links

### Exception Tree

```
H2KvmError (base)
├── Fatal (user-facing fatal errors)
├── ProviderError
│   ├── VMwareError
│   ├── AzureError
│   └── BackupSourceError
├── FixerError
│   ├── BootloaderFixerError
│   ├── FilesystemFixerError
│   ├── NetworkFixerError
│   └── WindowsFixerError
├── StorageError
│   ├── DiskConversionError
│   ├── LVMError
│   ├── LUKSError
│   ├── PartitionError
│   └── NBDError
├── ConfigurationError
│   ├── ManifestError
│   ├── ProfileError
│   └── MappingError
├── ValidationError
│   ├── ComplianceError
│   └── SanityCheckError
├── RuntimeError
│   ├── DaemonError
│   ├── WorkerError
│   ├── OperatorError
│   └── HookExecutionError
├── GuestBackendError (alias: VMCraftError, deprecated)
│   ├── MountError
│   └── InspectionError
├── InfrastructureError
│   ├── SystemdError
│   ├── SSHError
│   ├── RollbackError
│   └── LibvirtError
└── CommandError
```

### Basic Usage

```python
from h2kvm.core.exceptions import FixerError, BootloaderFixerError

# Raise with code and message
raise FixerError(
    code=1,
    msg="Failed to fix filesystem"
)

# With context
raise BootloaderFixerError(
    code=1,
    msg="GRUB configuration not found",
    context={
        "searched_paths": ["/boot/grub", "/boot/grub2"],
        "os_type": "ubuntu-22.04"
    }
)

# With cause (chained exception)
try:
    perform_risky_operation()
except Exception as e:
    raise FixerError(
        code=1,
        msg="Operation failed",
        cause=e
    )
```

### Enhanced Errors with Solutions

```python
from h2kvm.core.exceptions import create_helpful_error, VMwareError

error = create_helpful_error(
    VMwareError,
    "VM not found: web-server-01",
    code=404,
    solutions=[
        "Verify VM name with: govc ls /DC/vm/",
        "Check datacenter and folder path",
        "Ensure you have permissions to view the VM"
    ],
    causes=[
        "VM was renamed or deleted",
        "Insufficient permissions",
        "Incorrect datacenter specified"
    ],
    doc_link="30-vSphere-Export.md#troubleshooting"
)

raise error
```

### Error Message Formatting

```python
# Simple string representation
str(error)  # "VM not found: web-server-01"

# With context
error.user_message(include_context=True)
# Output:
# VM not found: web-server-01
#
# Solutions:
#   1. Verify VM name with: govc ls /DC/vm/
#   2. Check datacenter and folder path
#   3. Ensure you have permissions to view the VM
#
# Common causes:
#   1. VM was renamed or deleted
#   2. Insufficient permissions
#   3. Incorrect datacenter specified
#
# Documentation: https://github.com/ssahani/h2kvm/blob/main/docs/30-vSphere-Export.md#troubleshooting

# With cause
error.user_message(include_cause=True)
# (cause: ConnectionError: Failed to connect to vCenter)

# As dictionary (for JSON/logging)
error.to_dict()
# {
#   "type": "VMwareError",
#   "code": 404,
#   "message": "VM not found: web-server-01",
#   "context": { ... }
# }
```

### Catching Exceptions by Subsystem

```python
from h2kvm.core.exceptions import FixerError, StorageError

try:
    perform_migration()
except FixerError as e:
    # Catch all fixer-related errors
    logger.error(f"Fixing failed: {e.user_message(include_context=True)}")
    rollback_fixes()
except StorageError as e:
    # Catch all storage-related errors
    logger.error(f"Storage operation failed: {e.user_message()}")
    cleanup_devices()
except H2KvmError as e:
    # Catch all project errors
    logger.error(f"Migration failed: {e.user_message()}")
```

### Secret Redaction

The exception hierarchy automatically redacts secrets from context:

```python
error = FixerError(
    code=1,
    msg="Authentication failed",
    context={
        "username": "admin",
        "password": "secret123",  # Will be redacted
        "api_key": "xyz",         # Will be redacted
        "server": "vcenter.local" # Not redacted
    }
)

error.to_dict()
# {
#   "context": {
#     "username": "admin",
#     "password": "***REDACTED***",
#     "api_key": "***REDACTED***",
#     "server": "vcenter.local"
#   }
# }
```

---

## Migration Examples

### Example 1: Fixer Module

**Before:**

```python
import subprocess

class MyFixer:
    def fix_bootloader(self, device):
        try:
            subprocess.run(
                ["grub-install", device],
                check=True,
                capture_output=True
            )
        except subprocess.CalledProcessError as e:
            self.logger.error(f"GRUB install failed: {e.stderr}")
            raise Exception(f"Bootloader fixing failed")
```

**After:**

```python
from h2kvm.core.command_runner import CommandRunner
from h2kvm.core.exceptions import BootloaderFixerError

class MyFixer:
    def __init__(self, logger):
        self.logger = logger
        self.runner = CommandRunner(logger=logger)

    def fix_bootloader(self, device):
        result = self.runner.run(
            f"grub-install {device}",
            use_sudo=True,
            retries=2
        )

        if result.failed:
            raise BootloaderFixerError(
                code=result.exit_code,
                msg=f"GRUB installation failed on {device}",
                context={
                    "device": device,
                    "stderr": result.stderr,
                    "exit_code": result.exit_code
                }
            ).with_context(
                solutions=[
                    "Verify device is accessible",
                    "Check if UEFI or Legacy BIOS",
                    "Ensure /boot partition is mounted"
                ]
            )
```

### Example 2: Provider Module

**Before:**

```python
def download_vm(self, vm_name):
    try:
        # Download logic...
        if not os.path.exists(output_path):
            raise Exception(f"Download failed for {vm_name}")
    except Exception as e:
        self.logger.error(f"Error: {e}")
        raise
```

**After:**

```python
from h2kvm.core.exceptions import ProviderError, VMwareError

def download_vm(self, vm_name):
    try:
        # Download logic...
        if not os.path.exists(output_path):
            raise VMwareError(
                code=1,
                msg=f"VM download failed: {vm_name}",
                context={
                    "vm_name": vm_name,
                    "expected_path": output_path,
                    "vcenter": self.vcenter_host
                }
            ).with_context(
                solutions=[
                    "Check network connectivity to vCenter",
                    "Verify VM export permissions",
                    "Ensure sufficient disk space"
                ],
                doc_link="providers/vmware.md#download-issues"
            )
    except Exception as e:
        raise ProviderError(
            code=1,
            msg=f"Download failed: {vm_name}",
            cause=e
        )
```

### Example 3: Storage Operations

**Before:**

```python
def mount_partition(self, device, mount_point):
    cmd = f"mount {device} {mount_point}"
    try:
        subprocess.check_call(cmd, shell=True)
        return True
    except subprocess.CalledProcessError:
        return False
```

**After:**

```python
from h2kvm.core.command_runner import CommandRunner
from h2kvm.core.exceptions import StorageError, MountError

def mount_partition(self, device, mount_point):
    result = self.runner.run(
        f"mount {device} {mount_point}",
        use_sudo=True,
        retries=3,
        timeout=30
    )

    if result.failed:
        raise MountError(
            code=result.exit_code,
            msg=f"Failed to mount {device}",
            context={
                "device": device,
                "mount_point": mount_point,
                "stderr": result.stderr,
                "retries": result.retries
            }
        )

    self.logger.info(f"Mounted {device} in {result.duration:.2f}s")
    return result
```

---

## Best Practices

### 1. Always Use CommandRunner for Subprocess Calls

❌ **Don't:**
```python
subprocess.run(["ls", "-la"], check=True)
```

✅ **Do:**
```python
runner.run("ls -la", check=True)
```

### 2. Use Specific Exception Types

❌ **Don't:**
```python
raise Exception("Something went wrong")
```

✅ **Do:**
```python
raise FixerError(code=1, msg="Bootloader configuration failed")
```

### 3. Provide Context and Solutions

❌ **Don't:**
```python
raise FixerError(code=1, msg="Failed")
```

✅ **Do:**
```python
raise FixerError(
    code=1,
    msg="GRUB configuration not found",
    context={
        "searched_paths": ["/boot/grub", "/boot/grub2"],
        "os_type": "ubuntu-22.04"
    }
).with_context(
    solutions=["Verify /boot is mounted", "Check OS type"]
)
```

### 4. Use Dry-Run Mode in Fixtures

```python
class TestMyFixer:
    def setup_method(self):
        self.runner = CommandRunner(logger=mock_logger, dry_run=True)

    def test_fix_bootloader(self):
        # Commands won't actually execute
        result = self.runner.run("grub-install /dev/sda")
        assert result.exit_code == 0
```

### 5. Chain Exceptions with Cause

```python
try:
    low_level_operation()
except LowLevelError as e:
    raise HighLevelError(
        code=1,
        msg="High-level operation failed",
        cause=e  # Preserve the original exception
    )
```

### 6. Use CommandResult Properties

```python
result = runner.run("somecommand")

if result.success:
    # Handle success
elif result.failed:
    # Handle failure
```

### 7. Log Structured Context

```python
self.logger.error(
    "Migration failed",
    extra={
        "vm_name": vm_name,
        "error_code": error.code,
        "context": error.context
    }
)
```

---

## Testing with New Patterns

### Unit Testing CommandRunner

```python
from unittest.mock import patch, MagicMock
from h2kvm.core.command_runner import CommandRunner

def test_command_success():
    runner = CommandRunner(logger=mock_logger, dry_run=True)
    result = runner.run("echo 'test'")
    assert result.success
    assert result.exit_code == 0

def test_command_retry():
    runner = CommandRunner(logger=mock_logger)
    with patch('subprocess.run') as mock_run:
        # Fail twice, succeed third time
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, 'cmd'),
            subprocess.CalledProcessError(1, 'cmd'),
            MagicMock(returncode=0, stdout="OK", stderr="")
        ]

        result = runner.run("flaky-command", retries=2)
        assert result.success
        assert result.retries == 2
```

### Unit Testing Exceptions

```python
from h2kvm.core.exceptions import FixerError

def test_error_context():
    error = FixerError(
        code=1,
        msg="Test error",
        context={"key": "value"}
    )

    assert error.code == 1
    assert "Test error" in str(error)
    assert error.context["key"] == "value"

def test_helpful_error():
    error = create_helpful_error(
        FixerError,
        "Something failed",
        solutions=["Try this"]
    )

    msg = error.user_message(include_context=True)
    assert "Solutions:" in msg
    assert "Try this" in msg
```

---

## Gradual Migration Strategy

1. **New code:** Always use CommandRunner and exception hierarchy
2. **Bug fixes:** Convert to new patterns when fixing bugs in old code
3. **Refactoring:** Convert entire modules when refactoring
4. **No breaking changes:** Keep backward compatibility with wrapper functions if needed

### Compatibility Wrapper Example

```python
# Old function (deprecated)
def run_command_old(cmd):
    """Deprecated: Use CommandRunner instead."""
    runner = CommandRunner(logger=default_logger)
    result = runner.run(cmd)
    return result.exit_code, result.stdout, result.stderr

# New code calls CommandRunner directly
```

---

## Additional Resources

- [CommandRunner API Reference](../h2kvm/core/command_runner.py)
- [Exception Hierarchy](../h2kvm/core/exceptions.py)
- [Configuration README](../h2kvm/config/README.md)
- [Fixer Documentation](../h2kvm/fixers/README.md)
