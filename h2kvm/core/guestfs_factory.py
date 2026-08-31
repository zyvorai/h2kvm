# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/guestfs_factory.py
"""
Factory for creating GuestFS instances with backend selection.

Supports:
- 'guestkit': GuestKit Rust Guestfs via PyO3 (default)
- 'guestfs': Native libguestfs (python3-guestfs)
- 'auto': Try GuestKit first, fall back to libguestfs
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
    GUESTKIT = "guestkit"


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


def _guestkit_available() -> bool:
    """Return True if the GuestKit Python module is importable."""
    try:
        import guestkit  # type: ignore  # pylint: disable=import-outside-toplevel,unused-import

        return True
    except ImportError:
        return False


GUESTKIT_AVAILABLE = _guestkit_available()


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


def _create_guestkit() -> Any:
    """Instantiate GuestKit Guestfs (PyO3 bindings)."""
    try:
        from guestkit import Guestfs  # type: ignore  # pylint: disable=import-outside-toplevel
    except ImportError as e:
        raise ImportError(
            "GuestKit backend requested but the 'guestkit' Python module is not installed.\n"
            "    Install from the GuestKit checkout:\n"
            "      pip install -e /path/to/guestkit\n"
            "    Or from PyPI:\n"
            "      pip install hypersdk-guestkit\n"
            "    Host tools required: qemu-nbd, qemu-img.\n"
            "    Or switch to libguestfs: backend: guestfs / --backend guestfs"
        ) from e
    return Guestfs()


def _normalize_backend(backend: str) -> str:
    """Map legacy backend names to supported values."""
    legacy = {
        "vmcraft": "guestkit",
        "namespace": "guestkit",
    }
    return legacy.get(backend, backend)


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
        python_return_dict: Return dicts instead of tuples (libguestfs only; ignored by GuestKit).
        backend: Backend to use:
            - 'guestkit': GuestKit Rust Guestfs via PyO3 (default)
            - 'guestfs': Force native libguestfs backend
            - 'auto': Try GuestKit first, fall back to libguestfs
            - None: Defaults to 'guestkit'
            Legacy aliases 'vmcraft' and 'namespace' map to 'guestkit'.
        conversion_dir: Unused (kept for call-site compatibility).
        allowed_dirs: Unused (kept for call-site compatibility).
        container_isolation: Unused (kept for call-site compatibility).

    Returns:
        GuestFS-compatible instance (guestkit.Guestfs or guestfs.GuestFS)

    Raises:
        RuntimeError: If requested backend is unavailable
        ImportError: If backend requested but not installed

    Environment Variables:
        H2KVM_GUESTFS_BACKEND: Override backend selection (auto, guestfs, guestkit)

    Examples:
        # Use GuestKit (default)
        g = create_guestfs()

        # Force native guestfs backend
        g = create_guestfs(backend='guestfs')

        # Auto-select (GuestKit, then libguestfs)
        g = create_guestfs(backend='auto')
    """
    del conversion_dir, allowed_dirs, container_isolation  # API compatibility only

    # Check environment variable override
    env_backend = os.environ.get("H2KVM_GUESTFS_BACKEND")
    if env_backend:
        backend = env_backend.lower()
        if backend in ("vmcraft", "namespace"):
            import warnings

            warnings.warn(
                f"backend '{backend}' is deprecated; use 'guestkit'",
                DeprecationWarning,
                stacklevel=2,
            )

    # Default to GuestKit
    if backend is None:
        backend = "guestkit"

    backend = _normalize_backend(backend.lower())

    # Validate backend
    if backend not in ("auto", "guestfs", "guestkit"):
        raise ValueError(
            f"Invalid backend '{backend}'. Must be 'auto', 'guestfs', or 'guestkit'.\n"
            f"    Set via: backend: guestkit (in YAML) or --backend guestkit (CLI)\n"
            f"    Or set environment variable: H2KVM_GUESTFS_BACKEND=guestkit"
        )

    if backend == "guestfs":
        if not GUESTFS_AVAILABLE:
            raise ImportError(
                "Native guestfs backend requested but python3-guestfs is not installed.\n"
                "    Install: dnf install python3-libguestfs  (Fedora/RHEL)\n"
                "             apt install python3-guestfs     (Debian/Ubuntu)\n"
                "    Or switch to GuestKit: backend: guestkit"
            )
        return guestfs.GuestFS(python_return_dict=python_return_dict)

    if backend == "auto":
        if GUESTKIT_AVAILABLE or _guestkit_available():
            return _create_guestkit()
        if _guestfs_appliance_available():
            return guestfs.GuestFS(python_return_dict=python_return_dict)
        raise RuntimeError(
            "No guest disk backend available.\n"
            "    Install GuestKit: pip install hypersdk-guestkit  (or pip install -e ~/tt/guestkit)\n"
            "    Or install libguestfs: dnf install python3-libguestfs"
        )

    if backend == "guestkit":
        return _create_guestkit()

    raise RuntimeError(
        f"Unknown disk inspection backend '{backend}'. "
        f"Supported backends: 'guestkit' (default), 'guestfs', 'auto'. "
        f"Set via --backend or the 'backend:' YAML key."
    )
