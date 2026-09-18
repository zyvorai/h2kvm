# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
# https://zyvor.dev · info@zyvor.dev

# h2kvm/rollback/__init__.py
"""
Rollback framework for migration recovery.

Provides comprehensive rollback capabilities for failed migrations.
"""

from .orchestrator import (
    RollbackOrchestrator,
    RollbackReport,
    RollbackStrategy,
)
from .rollback_executor import (
    RollbackAction,
    RollbackExecutor,
    RollbackResult,
)
from .rollback_validator import (
    RollbackValidator,
    ValidationResult,
    ValidationStatus,
)
from .snapshot_manager import (
    Snapshot,
    SnapshotManager,
    SnapshotType,
)
from .state_tracker import (
    MigrationState,
    StateCheckpoint,
    StateTracker,
)

__all__ = [
    "MigrationState",
    "RollbackAction",
    "RollbackExecutor",
    "RollbackOrchestrator",
    "RollbackReport",
    "RollbackResult",
    "RollbackStrategy",
    "RollbackValidator",
    "Snapshot",
    "SnapshotManager",
    "SnapshotType",
    "StateCheckpoint",
    "StateTracker",
    "ValidationResult",
    "ValidationStatus",
]
