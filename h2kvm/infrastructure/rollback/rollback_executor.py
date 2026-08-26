# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/rollback/rollback_executor.py
"""
Rollback execution engine.

Executes rollback operations to revert failed migrations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class RollbackAction(Enum):
    """Rollback action types."""

    RESTORE_SNAPSHOT = "restore_snapshot"
    REVERT_FILE = "revert_file"
    REVERT_CONFIG = "revert_config"
    REMOVE_FILE = "remove_file"
    RESTORE_BACKUP = "restore_backup"
    CUSTOM = "custom"


@dataclass
class RollbackResult:
    """
    Rollback operation result.

    Attributes:
        action: Rollback action type
        success: Whether action succeeded
        message: Result message
        details: Additional result details
        duration_ms: Action duration in milliseconds
        timestamp: Action timestamp
    """

    action: RollbackAction
    success: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "action": self.action.value,
            "success": self.success,
            "message": self.message,
            "details": self.details,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
        }


class RollbackExecutor:
    """
    Rollback executor.

    Executes rollback operations to revert migrations.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize rollback executor.

        Args:
            logger: Logger instance
        """
        self.logger = logger
        self._results: list[RollbackResult] = []

    def execute_rollback_snapshot(
        self, snapshot_manager, snapshot_id: str, *, verify_checksum: bool = False
    ) -> RollbackResult:
        """
        Execute snapshot restoration.

        Args:
            snapshot_manager: SnapshotManager instance
            snapshot_id: Snapshot to restore
            verify_checksum: Verify snapshot checksum before restore

        Returns:
            Rollback result
        """
        import time

        start = time.time()

        try:
            self.logger.info(f"Restoring snapshot: {snapshot_id}")

            snapshot_manager.restore_snapshot(snapshot_id, verify_checksum=verify_checksum)

            duration = (time.time() - start) * 1000

            result = RollbackResult(
                action=RollbackAction.RESTORE_SNAPSHOT,
                success=True,
                message=f"Snapshot {snapshot_id} restored successfully",
                details={"snapshot_id": snapshot_id},
                duration_ms=duration,
            )

            self._results.append(result)
            return result

        except Exception as e:
            duration = (time.time() - start) * 1000

            result = RollbackResult(
                action=RollbackAction.RESTORE_SNAPSHOT,
                success=False,
                message=f"Failed to restore snapshot: {e}",
                details={"snapshot_id": snapshot_id, "error": str(e)},
                duration_ms=duration,
            )

            self._results.append(result)
            return result

    def execute_revert_file(self, file_path: str | Path, backup_path: str | Path) -> RollbackResult:
        """
        Revert file from backup.

        Args:
            file_path: File to revert
            backup_path: Backup file path

        Returns:
            Rollback result
        """
        import shutil
        import time

        start = time.time()

        file_path = Path(file_path)
        backup_path = Path(backup_path)

        try:
            if not backup_path.exists():
                raise FileNotFoundError(f"Backup file not found: {backup_path}")

            self.logger.info(f"Reverting {file_path} from {backup_path}")

            # Remove current file if exists
            if file_path.exists():
                file_path.unlink()

            # Restore from backup
            shutil.copy2(backup_path, file_path)

            duration = (time.time() - start) * 1000

            result = RollbackResult(
                action=RollbackAction.REVERT_FILE,
                success=True,
                message=f"File reverted: {file_path}",
                details={
                    "file_path": str(file_path),
                    "backup_path": str(backup_path),
                },
                duration_ms=duration,
            )

            self._results.append(result)
            return result

        except Exception as e:
            duration = (time.time() - start) * 1000

            result = RollbackResult(
                action=RollbackAction.REVERT_FILE,
                success=False,
                message=f"Failed to revert file: {e}",
                details={
                    "file_path": str(file_path),
                    "backup_path": str(backup_path),
                    "error": str(e),
                },
                duration_ms=duration,
            )

            self._results.append(result)
            return result

    def execute_remove_file(self, file_path: str | Path) -> RollbackResult:
        """
        Remove file (rollback file creation).

        Args:
            file_path: File to remove

        Returns:
            Rollback result
        """
        import time

        start = time.time()
        file_path = Path(file_path)

        try:
            if file_path.exists():
                self.logger.info(f"Removing file: {file_path}")
                file_path.unlink()

                duration = (time.time() - start) * 1000

                result = RollbackResult(
                    action=RollbackAction.REMOVE_FILE,
                    success=True,
                    message=f"File removed: {file_path}",
                    details={"file_path": str(file_path)},
                    duration_ms=duration,
                )
            else:
                duration = (time.time() - start) * 1000

                result = RollbackResult(
                    action=RollbackAction.REMOVE_FILE,
                    success=True,
                    message=f"File already removed: {file_path}",
                    details={"file_path": str(file_path)},
                    duration_ms=duration,
                )

            self._results.append(result)
            return result

        except Exception as e:
            duration = (time.time() - start) * 1000

            result = RollbackResult(
                action=RollbackAction.REMOVE_FILE,
                success=False,
                message=f"Failed to remove file: {e}",
                details={"file_path": str(file_path), "error": str(e)},
                duration_ms=duration,
            )

            self._results.append(result)
            return result

    def execute_custom_action(
        self, action_func: Callable[[], None], action_name: str = "custom_action"
    ) -> RollbackResult:
        """
        Execute custom rollback action.

        Args:
            action_func: Function to execute
            action_name: Action name for logging

        Returns:
            Rollback result
        """
        import time

        start = time.time()

        try:
            self.logger.info(f"Executing custom action: {action_name}")

            action_func()

            duration = (time.time() - start) * 1000

            result = RollbackResult(
                action=RollbackAction.CUSTOM,
                success=True,
                message=f"Custom action completed: {action_name}",
                details={"action_name": action_name},
                duration_ms=duration,
            )

            self._results.append(result)
            return result

        except Exception as e:
            duration = (time.time() - start) * 1000

            result = RollbackResult(
                action=RollbackAction.CUSTOM,
                success=False,
                message=f"Custom action failed: {e}",
                details={"action_name": action_name, "error": str(e)},
                duration_ms=duration,
            )

            self._results.append(result)
            return result

    def get_results(self) -> list[RollbackResult]:
        """Get all rollback results."""
        return self._results.copy()

    def get_summary(self) -> dict[str, Any]:
        """
        Get rollback summary.

        Returns:
            Summary dict with success/failure counts
        """
        total = len(self._results)
        successful = sum(1 for r in self._results if r.success)
        failed = total - successful

        return {
            "total_actions": total,
            "successful": successful,
            "failed": failed,
            "success_rate": (successful / total * 100) if total > 0 else 0.0,
        }
