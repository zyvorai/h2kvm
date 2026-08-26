# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Offline VM Fix Operations

Portable repair scripts that run inside offline-fix VMs or on bare metal.
These operations require full NBD partition access and guest filesystem mounting.

All fixers are:
- Idempotent: Safe to re-run multiple times
- Portable: Work in VM, bare metal, or online mode
- OS-aware: Detect and adapt to different distros
- Testable: Can be validated on real disk images
"""

from .fix_fstab import FstabFixer
from .fix_grub import GrubFixer
from .fix_initramfs import InitramfsFixer
from .fix_selinux import SELinuxFixer
from .utils import detect_os_from_root, get_block_device_label, get_block_device_uuid, is_lvm_device

__all__ = [
    "FstabFixer",
    "GrubFixer",
    "InitramfsFixer",
    "SELinuxFixer",
    "detect_os_from_root",
    "get_block_device_label",
    "get_block_device_uuid",
    "is_lvm_device",
]
