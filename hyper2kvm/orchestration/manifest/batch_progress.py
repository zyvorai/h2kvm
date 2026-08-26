# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Batch progress tracking and persistence for monitoring ongoing conversions.

This module provides real-time progress tracking for batch conversions,
enabling monitoring via CLI tools, web UI, or external systems.
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class VMStatus(Enum):
    """Status of a VM in batch conversion."""

    PENDING = "pending"  # Not started yet
    IN_PROGRESS = "in_progress"  # Currently processing
    COMPLETED = "completed"  # Successfully completed
    FAILED = "failed"  # Failed with error
    SKIPPED = "skipped"  # Skipped (from checkpoint)


@dataclass
class VMProgress:  # pylint: disable=too-many-instance-attributes
    # reason: dataclass models the independent progress fields tracked per VM
    # (timing, status, stage, error); splitting would fragment one progress record.
    """Progress information for a single VM."""

    vm_id: str
    status: VMStatus
    started_at: float | None = None
    completed_at: float | None = None
    duration: float = 0.0
    error: str | None = None
    current_stage: str | None = None
    stages_completed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "vm_id": self.vm_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration": self.duration,
            "error": self.error,
            "current_stage": self.current_stage,
            "stages_completed": self.stages_completed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VMProgress:
        """Create from dictionary."""
        return cls(
            vm_id=data["vm_id"],
            status=VMStatus(data["status"]),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            duration=data.get("duration", 0.0),
            error=data.get("error"),
            current_stage=data.get("current_stage"),
            stages_completed=data.get("stages_completed", []),
        )


@dataclass
class BatchProgress:
    """Overall batch conversion progress."""

    batch_id: str
    total_vms: int
    started_at: float
    updated_at: float
    completed_at: float | None = None
    vms: dict[str, VMProgress] = field(default_factory=dict)

    def get_counts(self) -> dict[str, int]:
        """Get VM counts by status."""
        counts = {status.value: 0 for status in VMStatus}
        for vm_progress in self.vms.values():
            counts[vm_progress.status.value] += 1
        return counts

    def get_completion_percentage(self) -> float:
        """Get completion percentage."""
        if self.total_vms == 0:
            return 0.0

        counts = self.get_counts()
        completed = counts[VMStatus.COMPLETED.value] + counts[VMStatus.FAILED.value]
        return (completed / self.total_vms) * 100.0

    def get_estimated_time_remaining(self) -> float | None:
        """
        Estimate time remaining based on current progress.

        Returns:
            Estimated seconds remaining, or None if cannot estimate
        """
        counts = self.get_counts()
        completed = counts[VMStatus.COMPLETED.value]

        if completed == 0:
            return None  # No data yet

        # Calculate average time per VM
        total_duration = sum(vm.duration for vm in self.vms.values() if vm.status == VMStatus.COMPLETED)
        avg_duration = total_duration / completed if completed > 0 else 0

        # Estimate remaining time
        # Calculate remaining as total - completed - failed
        failed = counts[VMStatus.FAILED.value]
        remaining_vms = self.total_vms - completed - failed
        return avg_duration * remaining_vms

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "batch_id": self.batch_id,
            "total_vms": self.total_vms,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "counts": self.get_counts(),
            "completion_percentage": self.get_completion_percentage(),
            "estimated_time_remaining": self.get_estimated_time_remaining(),
            "vms": {vm_id: vm.to_dict() for vm_id, vm in self.vms.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BatchProgress:
        """Create from dictionary."""
        vms = {vm_id: VMProgress.from_dict(vm_data) for vm_id, vm_data in data.get("vms", {}).items()}

        return cls(
            batch_id=data["batch_id"],
            total_vms=data["total_vms"],
            started_at=data["started_at"],
            updated_at=data["updated_at"],
            completed_at=data.get("completed_at"),
            vms=vms,
        )


class ProgressTracker:
    """
    Tracks and persists batch conversion progress.

    Features:
    - Real-time progress tracking
    - Atomic file writes
    - Thread-safe updates
    - JSON format for easy parsing
    """

    def __init__(
        self,
        progress_file: Path | str,
        batch_id: str,
        total_vms: int,
        logger: logging.Logger | None = None,
    ):
        """
        Initialize progress tracker.

        Args:
            progress_file: Path to progress file
            batch_id: Unique batch identifier
            total_vms: Total number of VMs in batch
            logger: Logger instance
        """
        self.progress_file = Path(progress_file)
        self.logger = logger or logging.getLogger(__name__)
        self._lock = threading.RLock()

        # Ensure directory exists
        self.progress_file.parent.mkdir(parents=True, exist_ok=True)

        # Initialize progress
        self.progress = BatchProgress(
            batch_id=batch_id,
            total_vms=total_vms,
            started_at=time.time(),
            updated_at=time.time(),
        )

        # Write initial progress
        self._write_progress()

    def start_vm(self, vm_id: str) -> None:
        """
        Mark VM as started.

        Args:
            vm_id: VM identifier
        """
        with self._lock:
            self.progress.vms[vm_id] = VMProgress(
                vm_id=vm_id,
                status=VMStatus.IN_PROGRESS,
                started_at=time.time(),
            )
            self.progress.updated_at = time.time()
            self._write_progress()

        self.logger.debug(f"Progress: VM {vm_id} started")

    def update_vm_stage(self, vm_id: str, stage: str) -> None:
        """
        Update current stage for a VM.

        Args:
            vm_id: VM identifier
            stage: Current stage name
        """
        with self._lock:
            if vm_id in self.progress.vms:
                vm_progress = self.progress.vms[vm_id]
                vm_progress.current_stage = stage
                if stage not in vm_progress.stages_completed:
                    vm_progress.stages_completed.append(stage)
                self.progress.updated_at = time.time()
                self._write_progress()

        self.logger.debug(f"Progress: VM {vm_id} stage: {stage}")

    def complete_vm(self, vm_id: str, success: bool, error: str | None = None) -> None:
        """
        Mark VM as completed.

        Args:
            vm_id: VM identifier
            success: Whether conversion succeeded
            error: Error message if failed
        """
        with self._lock:
            if vm_id in self.progress.vms:
                vm_progress = self.progress.vms[vm_id]
                vm_progress.status = VMStatus.COMPLETED if success else VMStatus.FAILED
                vm_progress.completed_at = time.time()
                vm_progress.error = error

                # Calculate duration
                if vm_progress.started_at:
                    vm_progress.duration = time.time() - vm_progress.started_at

                self.progress.updated_at = time.time()
                self._write_progress()

        status = "completed" if success else "failed"
        self.logger.debug(f"Progress: VM {vm_id} {status}")

    def skip_vm(self, vm_id: str, reason: str = "skipped from checkpoint") -> None:
        """
        Mark VM as skipped.

        Args:
            vm_id: VM identifier
            reason: Reason for skipping
        """
        with self._lock:
            self.progress.vms[vm_id] = VMProgress(
                vm_id=vm_id,
                status=VMStatus.SKIPPED,
                error=reason,
            )
            self.progress.updated_at = time.time()
            self._write_progress()

        self.logger.debug(f"Progress: VM {vm_id} skipped ({reason})")

    def complete_batch(self) -> None:
        """Mark batch as completed."""
        with self._lock:
            self.progress.completed_at = time.time()
            self.progress.updated_at = time.time()
            self._write_progress()

        self.logger.info("Progress: Batch completed")

    def get_progress(self) -> BatchProgress:
        """
        Get current progress.

        Returns:
            BatchProgress object
        """
        with self._lock:
            return self.progress

    def _write_progress(self) -> None:
        """Write progress to disk atomically."""
        # Atomic write: temp file + replace
        temp_file = self.progress_file.with_suffix(".json.tmp")

        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.progress.to_dict(), f, indent=2, sort_keys=False)
                f.write("\n")

            # Atomic replace
            temp_file.replace(self.progress_file)

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort progress persistence, must not abort the batch run
            self.logger.exception("Failed to write progress file: %s", e)
            # Clean up temp file
            with contextlib.suppress(Exception):
                temp_file.unlink()

    @classmethod
    def load_progress(
        cls, progress_file: Path | str, logger: logging.Logger | None = None
    ) -> BatchProgress | None:
        """
        Load progress from file.

        Args:
            progress_file: Path to progress file
            logger: Logger instance

        Returns:
            BatchProgress if file exists, else None
        """
        progress_path = Path(progress_file)

        if not progress_path.exists():
            return None

        try:
            with open(progress_path, encoding="utf-8") as f:
                data = json.load(f)

            return BatchProgress.from_dict(data)

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort progress load, must not abort the caller
            if logger:
                logger.exception("Failed to load progress file: %s", e)
            return None

    def cleanup(self) -> None:
        """Remove progress file (call on successful completion)."""
        try:
            if self.progress_file.exists():
                self.progress_file.unlink()
                self.logger.debug("Progress file cleaned up")
        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort cleanup, must not abort the caller
            self.logger.warning("Failed to cleanup progress file: %s", e)


__all__ = [
    "BatchProgress",
    "ProgressTracker",
    "VMProgress",
    "VMStatus",
]
