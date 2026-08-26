# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/rollback/orchestrator.py
"""
Rollback orchestrator.

Coordinates complete rollback workflow with snapshot restoration,
state tracking, execution, and validation.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from .rollback_executor import RollbackExecutor
from .rollback_validator import RollbackValidator
from .snapshot_manager import SnapshotManager
from .state_tracker import MigrationState, StateTracker

logger = logging.getLogger(__name__)


class RollbackStrategy(Enum):
    """Rollback strategies."""

    FULL = "full"  # Full rollback (restore snapshot)
    PARTIAL = "partial"  # Partial rollback (revert specific changes)
    INCREMENTAL = "incremental"  # Incremental rollback (step-by-step)


@dataclass
class RollbackReport:
    """
    Rollback operation report.

    Attributes:
        rollback_id: Unique rollback identifier
        strategy: Rollback strategy used
        started_at: Rollback start time
        completed_at: Rollback completion time
        success: Overall rollback success
        snapshot_restored: Snapshot ID that was restored (if any)
        actions_executed: Number of rollback actions executed
        actions_successful: Number of successful actions
        validations_passed: Number of validations passed
        validations_failed: Number of validations failed
        execution_results: List of execution results
        validation_results: List of validation results
        duration_ms: Total rollback duration
    """

    rollback_id: str
    strategy: RollbackStrategy
    started_at: datetime
    completed_at: datetime
    success: bool
    snapshot_restored: str | None = None
    actions_executed: int = 0
    actions_successful: int = 0
    validations_passed: int = 0
    validations_failed: int = 0
    execution_results: list[dict[str, Any]] = field(default_factory=list)
    validation_results: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "rollback_id": self.rollback_id,
            "strategy": self.strategy.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "success": self.success,
            "snapshot_restored": self.snapshot_restored,
            "actions_executed": self.actions_executed,
            "actions_successful": self.actions_successful,
            "validations_passed": self.validations_passed,
            "validations_failed": self.validations_failed,
            "execution_results": self.execution_results,
            "validation_results": self.validation_results,
            "duration_ms": self.duration_ms,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class RollbackOrchestrator:
    """
    Rollback orchestrator.

    Coordinates complete rollback workflow.
    """

    def __init__(
        self,
        logger: logging.Logger,
        *,
        snapshot_dir: Path | None = None,
        state_file: Path | None = None,
    ):
        """
        Initialize rollback orchestrator.

        Args:
            logger: Logger instance
            snapshot_dir: Directory for snapshots
            state_file: Path to state file
        """
        self.logger = logger
        self.snapshot_manager = SnapshotManager(logger, snapshot_dir)
        self.state_tracker = StateTracker(logger, state_file)
        self.executor = RollbackExecutor(logger)
        self.validator = RollbackValidator(logger)

    def execute_full_rollback(
        self,
        snapshot_id: str,
        *,
        verify_checksum: bool = False,
        validate: bool = True,
    ) -> RollbackReport:
        """
        Execute full rollback by restoring snapshot.

        Args:
            snapshot_id: Snapshot to restore
            verify_checksum: Verify snapshot checksum before restore
            validate: Run validation checks after rollback

        Returns:
            Rollback report
        """
        import time

        start_time = datetime.now()
        rollback_id = f"rollback_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.logger.info(f"Starting full rollback: {rollback_id}")
        self.logger.info(f"Restoring snapshot: {snapshot_id}")

        start = time.time()

        # Execute snapshot restoration
        result = self.executor.execute_rollback_snapshot(
            self.snapshot_manager,
            snapshot_id,
            verify_checksum=verify_checksum,
        )

        # Update state
        if result.success:
            self.state_tracker.checkpoint(
                MigrationState.ROLLED_BACK,
                f"Rolled back to snapshot {snapshot_id}",
                snapshot_id=snapshot_id,
            )

        # Validate if requested
        if validate and result.success:
            self.logger.info("Validating rollback...")
            self.validator.validate_snapshot_restored(
                self.snapshot_manager,
                snapshot_id,
            )

        end_time = datetime.now()
        duration = (time.time() - start) * 1000

        # Generate report
        exec_summary = self.executor.get_summary()
        val_summary = self.validator.get_summary()

        report = RollbackReport(
            rollback_id=rollback_id,
            strategy=RollbackStrategy.FULL,
            started_at=start_time,
            completed_at=end_time,
            success=result.success and (not validate or val_summary["success"]),
            snapshot_restored=snapshot_id if result.success else None,
            actions_executed=exec_summary["total_actions"],
            actions_successful=exec_summary["successful"],
            validations_passed=val_summary["passed"],
            validations_failed=val_summary["failed"],
            execution_results=[r.to_dict() for r in self.executor.get_results()],
            validation_results=[v.to_dict() for v in self.validator.get_results()],
            duration_ms=duration,
        )

        self.logger.info(
            f"Rollback complete: {rollback_id} (success={report.success}, duration={duration:.2f}ms)"
        )

        return report

    def execute_partial_rollback(
        self,
        *,
        revert_files: list[tuple[str, str]] | None = None,
        remove_files: list[str] | None = None,
        validate: bool = True,
    ) -> RollbackReport:
        """
        Execute partial rollback by reverting specific changes.

        Args:
            revert_files: List of (file_path, backup_path) tuples to revert
            remove_files: List of file paths to remove
            validate: Run validation checks after rollback

        Returns:
            Rollback report
        """
        import time

        start_time = datetime.now()
        rollback_id = f"rollback_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.logger.info(f"Starting partial rollback: {rollback_id}")

        start = time.time()

        # Revert files
        if revert_files:
            for file_path, backup_path in revert_files:
                result = self.executor.execute_revert_file(file_path, backup_path)
                if validate and result.success:
                    self.validator.validate_file_restored(file_path, expected_exists=True)

        # Remove files
        if remove_files:
            for file_path in remove_files:
                result = self.executor.execute_remove_file(file_path)
                if validate and result.success:
                    self.validator.validate_file_restored(file_path, expected_exists=False)

        # Update state
        self.state_tracker.checkpoint(
            MigrationState.ROLLED_BACK,
            "Partial rollback completed",
            revert_count=len(revert_files or []),
            remove_count=len(remove_files or []),
        )

        end_time = datetime.now()
        duration = (time.time() - start) * 1000

        # Generate report
        exec_summary = self.executor.get_summary()
        val_summary = self.validator.get_summary()

        report = RollbackReport(
            rollback_id=rollback_id,
            strategy=RollbackStrategy.PARTIAL,
            started_at=start_time,
            completed_at=end_time,
            success=exec_summary["failed"] == 0 and (not validate or val_summary["success"]),
            actions_executed=exec_summary["total_actions"],
            actions_successful=exec_summary["successful"],
            validations_passed=val_summary["passed"],
            validations_failed=val_summary["failed"],
            execution_results=[r.to_dict() for r in self.executor.get_results()],
            validation_results=[v.to_dict() for v in self.validator.get_results()],
            duration_ms=duration,
        )

        self.logger.info(
            f"Partial rollback complete: {rollback_id} (success={report.success}, duration={duration:.2f}ms)"
        )

        return report

    def generate_markdown_report(self, report: RollbackReport) -> str:
        """
        Generate Markdown rollback report.

        Args:
            report: Rollback report

        Returns:
            Markdown-formatted report
        """
        lines = [
            "# Rollback Report",
            "",
            "## Summary",
            "",
            f"**Rollback ID**: {report.rollback_id}",
            f"**Strategy**: {report.strategy.value.title()}",
            f"**Status**: {'✅ SUCCESS' if report.success else '❌ FAILED'}",
            f"**Started**: {report.started_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Completed**: {report.completed_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Duration**: {report.duration_ms:.2f}ms",
            "",
        ]

        if report.snapshot_restored:
            lines.extend(
                [
                    f"**Snapshot Restored**: {report.snapshot_restored}",
                    "",
                ]
            )

        lines.extend(
            [
                "## Execution Summary",
                "",
                f"- **Total Actions**: {report.actions_executed}",
                f"- **Successful**: {report.actions_successful}",
                f"- **Failed**: {report.actions_executed - report.actions_successful}",
                "",
            ]
        )

        if report.execution_results:
            lines.extend(
                [
                    "## Execution Details",
                    "",
                ]
            )

            for result in report.execution_results:
                status_emoji = "✅" if result["success"] else "❌"
                lines.extend(
                    [
                        f"### {status_emoji} {result['action'].replace('_', ' ').title()}",
                        "",
                        f"**Message**: {result['message']}",
                        f"**Duration**: {result['duration_ms']:.2f}ms",
                        "",
                    ]
                )

        lines.extend(
            [
                "## Validation Summary",
                "",
                f"- **Total Checks**: {report.validations_passed + report.validations_failed}",
                f"- **Passed**: {report.validations_passed}",
                f"- **Failed**: {report.validations_failed}",
                "",
            ]
        )

        if report.validation_results:
            lines.extend(
                [
                    "## Validation Details",
                    "",
                ]
            )

            for result in report.validation_results:
                status_emoji = {
                    "pass": "✅",
                    "fail": "❌",
                    "warn": "⚠️",
                }[result["status"]]

                lines.extend(
                    [
                        f"### {status_emoji} {result['check_name'].replace('_', ' ').title()}",
                        "",
                        f"**Message**: {result['message']}",
                        "",
                    ]
                )

        return "\n".join(lines)

    def save_report(
        self,
        report: RollbackReport,
        output_dir: Path,
        *,
        json_report: bool = True,
        markdown_report: bool = True,
    ) -> dict[str, str]:
        """
        Save rollback report to files.

        Args:
            report: Rollback report
            output_dir: Output directory
            json_report: Generate JSON report
            markdown_report: Generate Markdown report

        Returns:
            Dict mapping format to file path
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        saved_files = {}

        # JSON report
        if json_report:
            json_file = output_dir / f"{report.rollback_id}-report.json"
            json_file.write_text(report.to_json())
            saved_files["json"] = str(json_file)
            self.logger.info(f"Saved JSON report: {json_file}")

        # Markdown report
        if markdown_report:
            md_file = output_dir / f"{report.rollback_id}-report.md"
            md_file.write_text(self.generate_markdown_report(report))
            saved_files["markdown"] = str(md_file)
            self.logger.info(f"Saved Markdown report: {md_file}")

        return saved_files
