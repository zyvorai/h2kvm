# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/libvirt/libvirt_utils.py
"""Shared libvirt utility functions

Provides common helpers for libvirt operations to avoid duplication across modules.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

_logger = logging.getLogger(__name__)

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._+-]+")
_DEFAULT_IMAGES_DIR = Path("/var/lib/libvirt/images")
_DEFAULT_NVRAM_DIR = Path("/var/lib/libvirt/qemu/nvram")


def sanitize_name(s: str) -> str:
    """Sanitize name for libvirt-friendly identifiers and filenames.

    Args:
        s: String to sanitize

    Returns:
        Sanitized string safe for libvirt names and filenames

    Behavior:
        - Keeps: A-Za-z0-9._+-
        - Replaces everything else with '-'
        - Strips '-' from edges
        - Returns 'vm' if result is empty

    Example:
        >>> sanitize_name("My VM (test)")
        'My-VM--test-'
        >>> sanitize_name(" ")
        'vm'
        >>> sanitize_name("linux-server-01.example.com")
        'linux-server-01.example.com'
    """
    s = (s or "").strip()
    s = _SAFE_NAME_RE.sub("-", s).strip("-")
    return s or "vm"


def default_libvirt_images_dir() -> Path:
    """Return the default libvirt images directory.

    Returns:
        Path to /var/lib/libvirt/images
    """
    return _DEFAULT_IMAGES_DIR


def default_libvirt_nvram_dir() -> Path:
    """Return the default libvirt NVRAM directory.

    Returns:
        Path to /var/lib/libvirt/qemu/nvram
    """
    return _DEFAULT_NVRAM_DIR


_QEMU_BINARY_CANDIDATES = [
    "/usr/bin/qemu-system-x86_64",
    "/usr/libexec/qemu-kvm",
    "/usr/bin/qemu-kvm",
]


def find_qemu_binary() -> str:
    """Find the QEMU binary on this system.

    Checks well-known paths first, then falls back to PATH lookup.
    Returns the first binary found, or '/usr/bin/qemu-system-x86_64' as default.
    """
    for candidate in _QEMU_BINARY_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    # Fall back to PATH search
    for name in ("qemu-system-x86_64", "qemu-kvm"):
        found = shutil.which(name)
        if found:
            return found
    return "/usr/bin/qemu-system-x86_64"


_SPICE_LIB_DIRS = ("/usr/lib64", "/usr/lib/x86_64-linux-gnu", "/usr/lib")


def has_spice() -> bool:
    """Check if SPICE is available by looking for the shared library."""
    for lib_dir in _SPICE_LIB_DIRS:
        spice_lib = Path(lib_dir)
        if spice_lib.is_dir() and any(spice_lib.glob("libspice-server.so*")):
            _logger.debug("has_spice: found libspice-server.so in %s", lib_dir)
            return True
        _logger.debug("has_spice: not found in %s (is_dir=%s)", lib_dir, spice_lib.is_dir())
    _logger.debug("has_spice: SPICE not available in any searched directory")
    return False


def default_graphics() -> str:
    """Return 'spice' if supported by the QEMU/libvirt stack, otherwise 'vnc'."""
    result = "spice" if has_spice() else "vnc"
    _logger.debug("default_graphics: chose %s", result)
    return result


def default_video() -> str:
    """Return 'qxl' if SPICE is available (QXL is SPICE's video driver), otherwise 'virtio'."""
    result = "qxl" if has_spice() else "virtio"
    _logger.debug("default_video: chose %s", result)
    return result


__all__ = [
    "default_graphics",
    "default_libvirt_images_dir",
    "default_libvirt_nvram_dir",
    "default_video",
    "find_qemu_binary",
    "has_spice",
    "sanitize_name",
]
