# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Windows performance optimization modules.

This module provides performance tuning for Windows VMs migrating to KVM:

- VirtIO balloon driver auto-configuration
- TRIM/discard enablement for SSD-backed storage
- MSI interrupt configuration for VirtIO devices
- Hyper-V enlightenments removal
"""

from .balloon import configure_balloon_driver
from .hyperv_cleanup import cleanup_hyperv_enlightenments
from .msi import enable_msi_interrupts
from .trim import enable_trim_discard

__all__ = [
    "cleanup_hyperv_enlightenments",
    "configure_balloon_driver",
    "enable_msi_interrupts",
    "enable_trim_discard",
]
