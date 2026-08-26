# Coding Style Guide

**Version**: 1.0
**Last Updated**: 2026-03-29
**Based on**: systemd CODING_STYLE.md, PEP 8, PEP 257

---

## Table of Contents

1. [Python Version](#python-version)
2. [Formatting](#formatting)
3. [Type Hints](#type-hints)
4. [Docstrings](#docstrings)
5. [Naming Conventions](#naming-conventions)
6. [Functions](#functions)
7. [Classes](#classes)
8. [Error Handling](#error-handling)
9. [Imports](#imports)
10. [Comments](#comments)
11. [Testing](#testing)
12. [Logging](#logging)
13. [File Organization](#file-organization)
14. [Tooling](#tooling)

---

## Python Version

**Minimum**: Python 3.9
**Target**: Python 3.12+
**Compatibility**: Use features available in Python 3.9+

Use modern Python syntax when possible:

- Type hints with `list[str]`, not `List[str]` (PEP 585)
- Union types with `str | None`, not `Optional[str]` (PEP 604, Python 3.10+)
- Match statements for complex conditionals (Python 3.10+)

---

## Formatting

### Automated Formatting

**All code is formatted with Ruff**. Run before committing:

```bash
ruff format .
ruff check --fix .
```

Pre-commit hooks will automatically enforce this.

### Line Length

**Maximum: 109 characters** (matching systemd)

Exceptions:

- Long URLs in comments
- Test data strings
- Import statements (use parentheses for multiline)

### Indentation

- **4 spaces** per level (no tabs)
- Continuation lines: align with opening delimiter

```python
# Good
result = some_function(
    arg1,
    arg2,
    arg3,
)

# Also good
result = some_function(arg1, arg2, arg3)

# Bad - inconsistent alignment
result = some_function(arg1,
    arg2, arg3)
```

### Quotes

**Double quotes** for strings (enforced by ruff):

```python
# Good
message = "Hello, world"
error = "Failed to process disk"

# Bad
message = 'Hello, world'
```

**Triple double-quotes** for docstrings:

```python
def function():
    """This is a docstring."""
    pass
```

### Blank Lines

- **2 blank lines** between top-level definitions
- **1 blank line** between methods in a class
- **1 blank line** to separate logical sections in functions

```python
import os


class MyClass:
    """A class."""

    def method1(self):
        """First method."""
        pass

    def method2(self):
        """Second method."""
        pass


def standalone_function():
    """A function."""
    pass
```

---

## Type Hints

**Required** on all public functions and methods.

### Basic Types

```python
def process_disk(
    path: str,
    size: int,
    readonly: bool = False,
) -> dict[str, str | int]:
    """Process a disk image."""
    return {"path": path, "size": size}
```

### Modern Syntax (Python 3.9+)

```python
# Use built-in generics
list[str]           # not List[str]
dict[str, int]      # not Dict[str, int]
tuple[int, ...]     # not Tuple[int, ...]
set[str]            # not Set[str]

# Use union operator (Python 3.10+)
str | None          # not Optional[str]
int | str           # not Union[int, str]

# For Python 3.9 compatibility, use Union
from __future__ import annotations
```

### Complex Types

```python
from typing import TYPE_CHECKING, TypeAlias
from pathlib import Path

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

# Type aliases
PathLike: TypeAlias = str | Path
ResultDict: TypeAlias = dict[str, str | int | bool]

def walk_directory(
    root: PathLike,
    callback: Callable[[Path], None],
) -> Iterator[Path]:
    """Walk directory and call callback."""
    ...
```

### Type Annotations in Libraries

For modules with optional dependencies:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import libvirt  # Only imported for type checking

def connect_libvirt() -> "libvirt.virConnect":
    """Connect to libvirt."""
    import libvirt  # Runtime import
    return libvirt.open()
```

---

## Docstrings

**Required** on all public classes, functions, and methods.

### Format: NumPy/Google Style

```python
def activate_lvm(
    device: str, vg_name: str, *, readonly: bool = False
) -> dict[str, list[str]]:
    """
    Activate LVM volume group from device.

    Scans the specified device for LVM physical volumes and activates
    any volume groups found. Uses isolated LVM metadata directory to
    prevent host cache pollution.

    Parameters
    ----------
    device : str
        Block device path (e.g., "/dev/nbd0")
    vg_name : str
        Volume group name to activate
    readonly : bool, default=False
        Activate in read-only mode

    Returns
    -------
    dict[str, list[str]]
        Dictionary with keys:
        - "logical_volumes": List of activated LV paths
        - "status": Activation status

    Raises
    ------
    LVMError
        If activation fails
    DeviceNotFoundError
        If device doesn't exist

    Examples
    --------
    >>> result = activate_lvm("/dev/nbd0", "vg-root")
    >>> print(result["logical_volumes"])
    ['/dev/vg-root/root', '/dev/vg-root/swap']

    Notes
    -----
    This function uses PID-based isolated LVM directories for concurrent
    safety. See vmcraft/storage.py for implementation details.
    """
    ...
```

### Short Docstrings

For simple functions, one-line docstrings are acceptable:

```python
def is_block_device(path: str) -> bool:
    """Check if path is a block device."""
    return Path(path).is_block_device()
```

### Module Docstrings

Every module should have a docstring:

```python
"""
LVM volume group activation with isolation.

This module provides safe LVM activation for guest disk images with:
- Isolated metadata directories (prevents host cache pollution)
- Explicit device filtering (prevents accidental host VG activation)
- Enhanced device settlement (prevents race conditions)
"""
```

---

## Naming Conventions

### General Rules

- **snake_case** for functions, methods, variables
- **PascalCase** for classes
- **SCREAMING_SNAKE_CASE** for constants
- **_leading_underscore** for private/internal
- **__double_leading** for name mangling (rare)

```python
# Good
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30.0

class DiskConverter:
    """Converts disk images."""

    def convert_disk(self, source: str, target: str) -> None:
        """Convert disk image."""
        self._validate_source(source)

    def _validate_source(self, source: str) -> None:
        """Validate source path (private)."""
        ...
```

### Specific Conventions

**Functions/Methods**: Verb-noun pattern

```python
activate_lvm()         # not lvm_activate()
convert_disk()         # not disk_convert()
validate_config()      # not config_validate()
```

**Boolean Variables/Functions**: Use positive names

```python
# Good
is_ready: bool
has_error: bool
can_retry: bool

# Bad
not_ready: bool        # Double negatives confusing
no_error: bool         # Ambiguous
```

**Collections**: Plural names

```python
devices: list[str]
volume_groups: list[str]
results: dict[str, int]
```

---

## Functions

### Size and Complexity

- **Target**: <50 lines per function
- **Maximum**: 100 lines (rare exceptions)
- **Cyclomatic complexity**: <15 (enforced by ruff)

Extract helper functions for clarity:

```python
# Bad - too long
def process_vm(config):
    # ... 200 lines of code

# Good - extracted helpers
def process_vm(config: VMConfig) -> Result:
    """Process VM migration."""
    disk = _prepare_disk(config)
    vm = _convert_vm(disk, config)
    return _finalize_migration(vm)

def _prepare_disk(config: VMConfig) -> Disk:
    """Prepare disk for migration (helper)."""
    ...
```

### Parameters

- **Maximum**: 5 parameters
- Use keyword-only args for optional parameters
- Use config objects for complex functions

```python
# Bad - too many parameters
def convert(source, target, format, compression, sparse,
            buffer_size, threads, callback):
    ...

# Good - config object
@dataclass
class ConversionConfig:
    """Configuration for disk conversion."""
    source: Path
    target: Path
    format: str
    compression: bool = False
    sparse: bool = True
    buffer_size: int = 1024 * 1024
    threads: int = 1
    progress_callback: Callable[[int], None] | None = None

def convert_disk(config: ConversionConfig) -> ConversionResult:
    """Convert disk image."""
    ...
```

### Return Values

Prefer dataclasses or typed dicts over tuples:

```python
# Bad - tuple return
def activate_lvm(device):
    ...
    return success, error_msg, logical_volumes

# Good - dataclass return
@dataclass
class ActivationResult:
    """Result of LVM activation."""
    success: bool
    error: str | None = None
    logical_volumes: list[str] = field(default_factory=list)

def activate_lvm(device: str) -> ActivationResult:
    """Activate LVM."""
    ...
    return ActivationResult(success=True, logical_volumes=lvs)
```

---

## Classes

### Dataclasses

Prefer dataclasses over regular classes for data containers:

```python
from dataclasses import dataclass, field

@dataclass
class DiskInfo:
    """Information about a disk image."""
    path: Path
    format: str
    size: int
    virtual_size: int
    backing_file: Path | None = None
    snapshots: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate after initialization."""
        if self.size <= 0:
            raise ValueError("Size must be positive")
```

### Regular Classes

Use when behavior is more important than data:

```python
class VMCraft:
    """VM disk image manipulation."""

    def __init__(self, disk_path: Path):
        """Initialize VMCraft instance."""
        self.disk_path = disk_path
        self._device: str | None = None

    def __enter__(self) -> "VMCraft":
        """Context manager entry."""
        self.launch()
        return self

    def __exit__(self, *args) -> None:
        """Context manager exit."""
        self.shutdown()

    def launch(self) -> None:
        """Launch VM access."""
        self._device = self._attach_device()

    def _attach_device(self) -> str:
        """Attach block device (private helper)."""
        ...
```

---

## Error Handling

### Exception Hierarchy

Use specific exception types:

```python
# Good - specific exceptions
try:
    result = activate_lvm(device, vg_name)
except DeviceNotFoundError:
    logger.error(f"Device {device} not found")
    return None
except LVMError as e:
    logger.error(f"LVM activation failed: {e}")
    raise

# Bad - catch everything
try:
    result = activate_lvm(device, vg_name)
except Exception:  # Too broad
    return None
```

### Custom Exceptions

All custom exceptions inherit from base exception:

```python
from dataclasses import dataclass

@dataclass
class Hyper2KvmError(Exception):
    """Base exception for hyper2kvm."""
    msg: str

@dataclass
class LVMError(Hyper2KvmError):
    """LVM operation failed."""
    device: str
    vg_name: str
    command_output: str = ""

    def __str__(self) -> str:
        return f"{self.msg}: device={self.device}, vg={self.vg_name}"

# Usage
raise LVMError(
    msg="Failed to activate volume group",
    device="/dev/nbd0",
    vg_name="vg-root",
    command_output=result.stderr,
)
```

### Exception Chaining

Preserve exception context with `from`:

```python
# Good - preserves stack trace
try:
    result = subprocess.run(cmd, check=True)
except subprocess.CalledProcessError as e:
    raise LVMError(
        msg="vgchange command failed",
        device=device,
        vg_name=vg_name,
    ) from e  # Preserves original exception

# Bad - loses context
except subprocess.CalledProcessError as e:
    raise LVMError(...)  # Original exception lost
```

---

## Imports

### Order

Enforced by ruff (isort):

1. Standard library
2. Third-party libraries
3. Local imports

```python
# Standard library
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

# Third-party
import libvirt
from guestfs import GuestFS

# Local
from hyper2kvm.core import exceptions
from hyper2kvm.vmcraft import VMCraft
```

### Import Style

```python
# Good - specific imports
from pathlib import Path
from typing import TYPE_CHECKING

# Good - module import for clarity
import subprocess

# Avoid - wildcard imports
from module import *  # Never use
```

### Conditional Imports

For optional dependencies:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import libvirt  # Only for type checking

def connect() -> "libvirt.virConnect":
    import libvirt  # Runtime import
    return libvirt.open()
```

---

## Comments

### When to Comment

- **Why**, not what: Explain reasoning, not code translation
- Complex algorithms
- Workarounds for bugs
- Performance-critical sections
- Non-obvious behavior

### Good Comments

```python
# Use isolated LVM directory to prevent host cache pollution.
# This is critical for concurrent VM operations - each process
# gets its own metadata directory to avoid conflicts.
lvm_env["LVM_SYSTEM_DIR"] = str(temp_dir)

# Sleep 200ms after udevadm settle to prevent race conditions.
# Some kernel versions need extra time for device node creation.
# See: https://github.com/systemd/systemd/issues/12345
time.sleep(0.2)
```

### Bad Comments

```python
# Set variable to 5
max_retries = 5  # Obvious from code

# Call function
result = activate_lvm(device, vg)  # Just repeating code
```

### TODO Comments

Use specific format for tracking:

```python
# TODO(username): Add support for BTRFS subvolumes
# TODO: Optimize for large files (>100GB)
# FIXME: Race condition when multiple processes access same VG
```

---

## Testing

### Test Organization

```python
class TestLVMActivation:
    """Tests for LVM activation functionality."""

    def test_activate_success(self):
        """Should activate VG successfully."""
        result = activate_lvm("/dev/nbd0", "vg-root")
        assert result.success
        assert len(result.logical_volumes) > 0

    def test_activate_device_not_found(self):
        """Should raise DeviceNotFoundError if device missing."""
        with pytest.raises(DeviceNotFoundError):
            activate_lvm("/dev/nonexistent", "vg-root")

    def test_activate_vg_not_found(self):
        """Should raise LVMError if VG not found."""
        with pytest.raises(LVMError, match="not found"):
            activate_lvm("/dev/nbd0", "nonexistent-vg")
```

### Naming

- `test_<function>_<scenario>`: `test_activate_lvm_success`
- Docstring describes expected behavior: "Should ..."

### Mocking

```python
from unittest.mock import Mock, patch

@patch("hyper2kvm.vmcraft.storage.run_sudo")
def test_activate_lvm_success(mock_run_sudo):
    """Should activate VG successfully."""
    # Arrange
    mock_run_sudo.return_value = Mock(
        returncode=0,
        stdout="",
        stderr="",
    )

    # Act
    result = activate_lvm("/dev/nbd0", "vg-root")

    # Assert
    assert result.success
    mock_run_sudo.assert_called_once()
```

---

## Logging

### Levels

- `DEBUG`: Detailed diagnostic info
- `INFO`: Confirmation of expected behavior
- `WARNING`: Something unexpected but handled
- `ERROR`: Serious problem, operation failed
- `CRITICAL`: Program may crash

### Format

```python
logger.debug(f"Scanning device {device} for LVM PVs")
logger.info(f"Activated VG {vg_name} with {len(lvs)} LVs")
logger.warning(f"Device {device} not found, retrying...")
logger.error(f"Failed to activate VG {vg_name}: {error}")
```

### Avoid

```python
# Bad - string concatenation in production
logger.debug("Scanning " + device + " for LVM")

# Good - f-strings for readability
logger.debug(f"Scanning {device} for LVM")

# Good - lazy % formatting for performance-critical code
logger.debug("Scanning %s for LVM", device)
```

---

## File Organization

### Module Structure

```python
"""Module docstring describing purpose."""

# Future imports
from __future__ import annotations

# Imports (stdlib, third-party, local)
import os
from pathlib import Path
from typing import TYPE_CHECKING

import libvirt

from hyper2kvm.core import exceptions

# TYPE_CHECKING imports
if TYPE_CHECKING:
    from collections.abc import Callable

# Constants
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30.0

# Type aliases
PathLike: TypeAlias = str | Path

# Classes
class MyClass:
    """A class."""
    ...

# Functions
def my_function():
    """A function."""
    ...

# Main guard
if __name__ == "__main__":
    main()
```

---

## Tooling

### Required Tools

Install and configure:

```bash
# Install development tools
pip install ruff mypy pre-commit pytest pytest-cov

# Install pre-commit hooks
pre-commit install

# Run before committing
ruff format .
ruff check .
mypy hyper2kvm/
pytest tests/unit/
```

### Editor Integration

**VS Code** (`settings.json`):

```json
{
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.organizeImports": "explicit"
    }
  },
  "python.linting.mypyEnabled": true
}
```

**PyCharm**: Enable "Ruff" formatter in Settings → Tools → Ruff

---

## Summary

**Key Principles**:

1. ✅ **Consistency**: Use ruff for all formatting
2. ✅ **Type Safety**: Add type hints to all functions
3. ✅ **Documentation**: Write clear docstrings
4. ✅ **Simplicity**: Keep functions small (<50 lines)
5. ✅ **Clarity**: Prefer explicit over clever
6. ✅ **Testing**: Write tests for all new code
7. ✅ **Automation**: Let tools enforce style

**Before Committing**:

```bash
ruff format .           # Format code
ruff check .            # Check linting
mypy hyper2kvm/         # Type check
pytest tests/unit/      # Run tests
git commit              # Pre-commit hooks run automatically
```

---

**Questions?** See [CONTRIBUTING.md](CONTRIBUTING.md) or open a discussion.
