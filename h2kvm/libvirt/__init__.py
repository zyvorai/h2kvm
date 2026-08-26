# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Libvirt integration for h2kvm.

This package provides libvirt domain and storage pool management capabilities
for automatic VM import and lifecycle operations after conversion.
"""

from __future__ import annotations

# Import utilities
from .libvirt_utils import (
    default_libvirt_images_dir,
    default_libvirt_nvram_dir,
    sanitize_name,
)

# Import managers (may not be available if libvirt not installed)
try:
    from .libvirt_manager import LIBVIRT_AVAILABLE, LibvirtManager
    from .pool_manager import PoolManager
except ImportError:
    LIBVIRT_AVAILABLE = False  # type: ignore
    LibvirtManager = None  # type: ignore
    PoolManager = None  # type: ignore

__all__ = [
    "LIBVIRT_AVAILABLE",
    # Managers
    "LibvirtManager",
    "PoolManager",
    "default_libvirt_images_dir",
    "default_libvirt_nvram_dir",
    # Utilities
    "sanitize_name",
]
