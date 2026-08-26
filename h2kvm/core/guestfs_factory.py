# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/guestfs_factory.py
"""
Factory for creating GuestFS instances with backend selection.

Supports:
- 'auto': Try native guestfs first, fall back to VMCraft
- 'guestfs': Force native guestfs backend (raise if unavailable)
- 'vmcraft': Force VMCraft implementation (default)
"""

from __future__ import annotations

import logging
import os
import shutil
from enum import Enum
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


class BackendType(str, Enum):
    """GuestFS backend selection."""

    AUTO = "auto"
    GUESTFS = "guestfs"
    VMCRAFT = "vmcraft"


def _auto_detect_libguestfs_path() -> None:
    """Auto-detect and set LIBGUESTFS_PATH if not already set.

    libguestfs searches for the supermin appliance in LIBGUESTFS_PATH.
    Different distros install it in different locations:
      - Fedora/RHEL/Alma: /usr/lib64/guestfs
      - Debian/Ubuntu:     /usr/lib/x86_64-linux-gnu/guestfs
      - openSUSE:          /usr/lib64/guestfs
      - Manual builds:     /usr/local/lib/guestfs
    Auto-detect by finding where supermin.d actually lives.
    """
    if os.environ.get("LIBGUESTFS_PATH"):
        return  # User already set it — respect that

    search_dirs = [
        "/usr/lib64/guestfs",
        "/usr/lib/x86_64-linux-gnu/guestfs",
        "/usr/lib/guestfs",
        "/usr/local/lib64/guestfs",
        "/usr/local/lib/guestfs",
    ]

    # Also check near the supermin binary
    supermin_bin = shutil.which("supermin")
    if supermin_bin:
        # e.g. /usr/bin/supermin → check /usr/lib64/guestfs, /usr/lib/guestfs
        prefix = Path(supermin_bin).resolve().parent.parent
        for lib in ("lib64", "lib"):
            candidate = prefix / lib / "guestfs"
            if candidate not in [Path(d) for d in search_dirs]:
                search_dirs.insert(0, str(candidate))

    for d in search_dirs:
        if Path(d, "supermin.d").is_dir():
            os.environ["LIBGUESTFS_PATH"] = d
            return


_auto_detect_libguestfs_path()


def _auto_detect_libguestfs_hv() -> None:
    """Auto-detect and set LIBGUESTFS_HV (QEMU binary) if not already set.

    libguestfs defaults to qemu-system-x86_64 which doesn't exist on
    RHEL/AlmaLinux/CentOS where the binary is /usr/libexec/qemu-kvm.
    """
    if os.environ.get("LIBGUESTFS_HV"):
        return  # User already set it — respect that

    # If the default exists, nothing to do
    if shutil.which("qemu-system-x86_64"):
        return

    # RHEL/Alma/CentOS use /usr/libexec/qemu-kvm
    for candidate in ("/usr/libexec/qemu-kvm", "/usr/bin/qemu-kvm"):
        if Path(candidate).is_file():
            os.environ["LIBGUESTFS_HV"] = candidate
            return


_auto_detect_libguestfs_hv()

# Check native guestfs availability (import + supermin appliance)
try:
    import guestfs  # type: ignore

    GUESTFS_AVAILABLE = True
except ImportError:
    GUESTFS_AVAILABLE = False


def _guestfs_appliance_available() -> bool:
    """Check that libguestfs supermin appliance is usable, not just importable."""
    if not GUESTFS_AVAILABLE:
        _log.debug("guestfs Python module not importable")
        return False
    try:
        g = guestfs.GuestFS(python_return_dict=True)
        g.set_backend("direct")
        g.close()
        return True
    except Exception as e:  # pylint: disable=broad-exception-caught  # probing an optional native backend; any failure just means "unavailable"
        _log.debug("libguestfs appliance probe failed: %s", e)
        return False


def create_guestfs(
    *,
    python_return_dict: bool = True,
    backend: str | None = None,
    conversion_dir: str | None = None,
    allowed_dirs: list[str] | None = None,
    container_isolation: bool = True,
) -> Any:
    """
    Create a GuestFS instance with backend selection.

    Args:
        python_return_dict: Return dicts instead of tuples (default: True)
        backend: Backend to use:
            - 'auto': Try native guestfs, fall back to VMCraft
            - 'guestfs': Force native guestfs backend (raise if unavailable)
            - 'vmcraft': Force VMCraft implementation (default)
            - None: Defaults to 'vmcraft'
        conversion_dir: Directory for VMDK conversion temp files (VMCraft only).
                       Defaults to ~/.cache/h2kvm/conversions
        allowed_dirs: Additional directories allowed for VM image access (security).
                     Only applies to VMCraft backend.

    Returns:
        GuestFS instance (either guestfs.GuestFS or VMCraft)

    Raises:
        RuntimeError: If requested backend is unavailable
        ImportError: If guestfs backend requested but not available

    Environment Variables:
        H2KVM_GUESTFS_BACKEND: Override backend selection (auto, guestfs, vmcraft)

    Examples:
        # Use VMCraft (default)
        g = create_guestfs()

        # Explicit VMCraft
        g = create_guestfs(backend='vmcraft')

        # Force native guestfs backend
        g = create_guestfs(backend='guestfs')

        # Auto-select (tries native guestfs, falls back to VMCraft)
        g = create_guestfs(backend='auto')
    """
    # Check environment variable override
    env_backend = os.environ.get("H2KVM_GUESTFS_BACKEND")
    if env_backend:
        backend = env_backend.lower()

    # Default to 'vmcraft'
    if backend is None:
        backend = "vmcraft"

    backend = backend.lower()

    # Validate backend
    if backend not in ("auto", "guestfs", "vmcraft"):
        raise ValueError(
            f"Invalid backend '{backend}'. Must be 'auto', 'guestfs', or 'vmcraft'.\n"
            f"    Set via: backend: vmcraft (in YAML) or --backend vmcraft (CLI)\n"
            f"    Or set environment variable: H2KVM_GUESTFS_BACKEND=vmcraft"
        )

    # Try native guestfs backend
    if backend == "guestfs":
        if not GUESTFS_AVAILABLE:
            raise ImportError(
                "Native guestfs backend requested but python3-guestfs is not installed.\n"
                "    Install: dnf install python3-libguestfs  (Fedora/RHEL)\n"
                "             apt install python3-guestfs     (Debian/Ubuntu)\n"
                "    Or switch to VMCraft (no native dependencies): backend: vmcraft"
            )
        return guestfs.GuestFS(python_return_dict=python_return_dict)

    # Try auto (native guestfs first, then VMCraft)
    if backend == "auto":
        if _guestfs_appliance_available():
            return guestfs.GuestFS(python_return_dict=python_return_dict)
        # Fall back to VMCraft
        # VMCraft is heavy (480+ methods); keep lazy to avoid the cost when native guestfs is used
        from h2kvm.vmcraft import VMCraft  # pylint: disable=import-outside-toplevel

        return VMCraft(
            python_return_dict=python_return_dict,
            conversion_dir=conversion_dir,
            allowed_dirs=allowed_dirs,
            container_isolation=container_isolation,
        )

    # VMCraft backend
    if backend == "vmcraft":
        # VMCraft is heavy (480+ methods); keep lazy to avoid the cost when native guestfs is used
        from h2kvm.vmcraft import VMCraft  # pylint: disable=import-outside-toplevel

        return VMCraft(
            python_return_dict=python_return_dict,
            conversion_dir=conversion_dir,
            allowed_dirs=allowed_dirs,
            container_isolation=container_isolation,
        )

    # Should not reach here
    raise RuntimeError(
        f"Unknown disk inspection backend '{backend}'. "
        f"Supported backends: 'vmcraft' (default), 'guestfs'. "
        f"Set via --backend or the 'backend:' YAML key."
    )
