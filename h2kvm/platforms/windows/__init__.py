# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
# https://zyvor.dev · info@zyvor.dev

"""
Windows migration support module.

This module provides specialized functionality for Windows VM migrations including:
- Automated license reactivation (KMS, MAK, OEM)
- Active Directory integration and domain rejoin
- SQL Server migration support
- Windows Update integration for VirtIO drivers
"""

from .active_directory import ActiveDirectoryManager
from .license import WindowsLicenseManager
from .sql_server import SQLServerManager
from .windows_update import WindowsUpdateManager

__all__ = [
    "ActiveDirectoryManager",
    "SQLServerManager",
    "WindowsLicenseManager",
    "WindowsUpdateManager",
]
