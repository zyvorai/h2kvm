# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: LicenseRef-Zyvor-Production-1.0
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/offline/__init__.py
"""
Offline fixer helper modules for VMware -> KVM migration.

This package provides helper modules for offline guest modifications:
- config_rewriter: Configuration file rewriting operations
- spec_converter: Spec conversion utilities
- validation: Post-modification validation and health checks
- mount: GuestFS mounting and filesystem operations
"""

from .config_rewriter import FstabCrypttabRewriter
from .spec_converter import SpecConverter
from .validation import OfflineValidationManager

__all__ = [
    "FstabCrypttabRewriter",
    "OfflineValidationManager",
    "SpecConverter",
]
