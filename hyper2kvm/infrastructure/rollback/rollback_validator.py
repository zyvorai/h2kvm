# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/rollback/rollback_validator.py
"""
Rollback validation.

Validates that rollback operations succeeded and system is in expected state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ValidationStatus(Enum):
    """Validation status."""

    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"


@dataclass
class ValidationResult:
    """
    Validation result.

    Attributes:
        check_name: Validation check name
        status: Validation status
        message: Result message
        details: Additional details
        timestamp: Validation timestamp
    """

    check_name: str
    status: ValidationStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "check_name": self.check_name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


class RollbackValidator:
    """
    Rollback validator.

    Validates that rollback operations succeeded.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize rollback validator.

        Args:
            logger: Logger instance
        """
        self.logger = logger
        self._results: list[ValidationResult] = []

    def validate_snapshot_restored(self, snapshot_manager, snapshot_id: str) -> ValidationResult:
        """
        Validate that snapshot was restored successfully.

        Args:
            snapshot_manager: SnapshotManager instance
            snapshot_id: Snapshot ID

        Returns:
            Validation result
        """
        try:
            snapshot = snapshot_manager.get_snapshot(snapshot_id)

            if not snapshot:
                result = ValidationResult(
                    check_name="snapshot_restored",
                    status=ValidationStatus.FAIL,
                    message=f"Snapshot not found: {snapshot_id}",
                    details={"snapshot_id": snapshot_id},
                )
                self._results.append(result)
                return result

            # Check that source file exists
            source_path = Path(snapshot.source_path)
            if not source_path.exists():
                result = ValidationResult(
                    check_name="snapshot_restored",
                    status=ValidationStatus.FAIL,
                    message=f"Source file not found: {source_path}",
                    details={"source_path": str(source_path)},
                )
                self._results.append(result)
                return result

            # Verify file size matches original snapshot size (for full snapshots)
            if snapshot.snapshot_type.value == "full":
                current_size = source_path.stat().st_size
                if current_size != snapshot.size_bytes:
                    result = ValidationResult(
                        check_name="snapshot_restored",
                        status=ValidationStatus.WARN,
                        message=f"File size mismatch: expected {snapshot.size_bytes}, got {current_size}",
                        details={
                            "expected_size": snapshot.size_bytes,
                            "actual_size": current_size,
                        },
                    )
                    self._results.append(result)
                    return result

            result = ValidationResult(
                check_name="snapshot_restored",
                status=ValidationStatus.PASS,
                message=f"Snapshot {snapshot_id} restored successfully",
                details={"snapshot_id": snapshot_id},
            )
            self._results.append(result)
            return result

        except Exception as e:
            result = ValidationResult(
                check_name="snapshot_restored",
                status=ValidationStatus.FAIL,
                message=f"Validation failed: {e}",
                details={"error": str(e)},
            )
            self._results.append(result)
            return result

    def validate_file_restored(
        self, file_path: str | Path, expected_exists: bool = True
    ) -> ValidationResult:
        """
        Validate that file is in expected state.

        Args:
            file_path: File path
            expected_exists: Whether file should exist

        Returns:
            Validation result
        """
        file_path = Path(file_path)

        try:
            exists = file_path.exists()

            if exists == expected_exists:
                result = ValidationResult(
                    check_name="file_restored",
                    status=ValidationStatus.PASS,
                    message=f"File state correct: {file_path}",
                    details={
                        "file_path": str(file_path),
                        "expected_exists": expected_exists,
                        "exists": exists,
                    },
                )
            else:
                result = ValidationResult(
                    check_name="file_restored",
                    status=ValidationStatus.FAIL,
                    message=f"File state incorrect: expected exists={expected_exists}, got exists={exists}",
                    details={
                        "file_path": str(file_path),
                        "expected_exists": expected_exists,
                        "exists": exists,
                    },
                )

            self._results.append(result)
            return result

        except Exception as e:
            result = ValidationResult(
                check_name="file_restored",
                status=ValidationStatus.FAIL,
                message=f"Validation failed: {e}",
                details={"file_path": str(file_path), "error": str(e)},
            )
            self._results.append(result)
            return result

    def validate_state(self, state_tracker, expected_state: Any) -> ValidationResult:
        """
        Validate migration state.

        Args:
            state_tracker: StateTracker instance
            expected_state: Expected migration state

        Returns:
            Validation result
        """
        try:
            current_state = state_tracker.get_current_state()

            if current_state == expected_state:
                result = ValidationResult(
                    check_name="state_validated",
                    status=ValidationStatus.PASS,
                    message=f"State correct: {current_state.value}",
                    details={
                        "expected": expected_state.value,
                        "actual": current_state.value,
                    },
                )
            else:
                result = ValidationResult(
                    check_name="state_validated",
                    status=ValidationStatus.FAIL,
                    message=f"State incorrect: expected {expected_state.value}, got {current_state.value}",
                    details={
                        "expected": expected_state.value,
                        "actual": current_state.value,
                    },
                )

            self._results.append(result)
            return result

        except Exception as e:
            result = ValidationResult(
                check_name="state_validated",
                status=ValidationStatus.FAIL,
                message=f"Validation failed: {e}",
                details={"error": str(e)},
            )
            self._results.append(result)
            return result

    def get_results(self) -> list[ValidationResult]:
        """Get all validation results."""
        return self._results.copy()

    def get_summary(self) -> dict[str, Any]:
        """
        Get validation summary.

        Returns:
            Summary dict with pass/fail counts
        """
        total = len(self._results)
        passed = sum(1 for r in self._results if r.status == ValidationStatus.PASS)
        failed = sum(1 for r in self._results if r.status == ValidationStatus.FAIL)
        warnings = sum(1 for r in self._results if r.status == ValidationStatus.WARN)

        return {
            "total_checks": total,
            "passed": passed,
            "failed": failed,
            "warnings": warnings,
            "success": failed == 0,
        }
