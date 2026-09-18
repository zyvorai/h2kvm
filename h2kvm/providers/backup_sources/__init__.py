# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
# https://zyvor.dev · info@zyvor.dev

# h2kvm/backup_sources/__init__.py
"""
Backup integration for VM import from backup solutions.

Enables VM migration from enterprise backup formats:
- Veeam Backup & Replication (VBK/VIB)
- Commvault (MediaAgent exports)
- Proxmox Backup Server (PBS)
- Acronis Backup (TIB)
- Restic/Borg archives

Use cases:
- DR testing (restore backups to KVM for validation)
- Backup-based migrations (when live migration not feasible)
- Archive recovery (restore legacy backups)
- Compliance testing (verify backup integrity)
"""

from .base import BackupSource, BackupVMInfo, RestoreProgress
from .generic import GenericBackupSource
from .orchestrator import BackupRestoreOrchestrator
from .proxmox import ProxmoxBackupSource
from .veeam import VeeamBackupSource

__all__ = [
    "BackupRestoreOrchestrator",
    "BackupSource",
    "BackupVMInfo",
    "GenericBackupSource",
    "ProxmoxBackupSource",
    "RestoreProgress",
    "VeeamBackupSource",
]
