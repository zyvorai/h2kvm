# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/tui/migration_tracker.py
"""
Migration state and history tracking for the TUI.

Tracks active and completed migrations to provide statistics and status updates.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any


class MigrationStatus(str, Enum):
    """Migration status enumeration."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class MigrationRecord:  # pylint: disable=too-many-instance-attributes
    # Each field records a distinct piece of migration state/audit info;
    # that's the point of this tracking record.
    """
    Record of a migration operation.

    Attributes:
        id: Unique migration ID
        vm_name: Name of the VM being migrated
        source_type: Source type (vsphere, local, hyperv, ova)
        status: Current migration status
        start_time: ISO format start time
        end_time: ISO format end time (None if not finished)
        progress: Progress percentage (0-100)
        error_message: Error message if failed
        output_path: Path to output file/directory
        source_path: Path to source VM/file
        size_mb: Size in MB
        metadata: Additional metadata dict
    """

    id: str
    vm_name: str
    source_type: str
    status: MigrationStatus
    start_time: str
    end_time: str | None = None
    progress: float = 0.0
    error_message: str | None = None
    output_path: str | None = None
    source_path: str | None = None
    size_mb: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MigrationRecord:
        """Create from dictionary."""
        # Convert status string to enum
        if "status" in data and isinstance(data["status"], str):
            data["status"] = MigrationStatus(data["status"])
        return cls(**data)

    def is_active(self) -> bool:
        """Check if migration is currently active."""
        return self.status in [MigrationStatus.PENDING, MigrationStatus.RUNNING, MigrationStatus.PAUSED]

    def is_completed(self) -> bool:
        """Check if migration completed successfully."""
        return self.status == MigrationStatus.COMPLETED

    def is_failed(self) -> bool:
        """Check if migration failed."""
        return self.status == MigrationStatus.FAILED

    def duration_seconds(self) -> float | None:
        """Calculate duration in seconds."""
        if not self.end_time:
            return None
        start = datetime.fromisoformat(self.start_time)
        end = datetime.fromisoformat(self.end_time)
        return (end - start).total_seconds()


class MigrationTracker:
    """
    Tracks migration history and provides statistics.

    Stores migration records in ~/.config/h2kvm/migration_history.json
    """

    def __init__(
        self, history_path: Path | None = None, logger: logging.Logger | None = None, max_history: int = 1000
    ):
        """
        Initialize migration tracker.

        Args:
            history_path: Optional custom path to history file
            logger: Optional logger for debug output
            max_history: Maximum number of records to keep
        """
        if history_path is None:
            config_dir = Path.home() / ".config" / "h2kvm"
            history_path = config_dir / "migration_history.json"

        self.history_path = history_path
        self.logger = logger or logging.getLogger(__name__)
        self.max_history = max_history
        self.migrations: dict[str, MigrationRecord] = {}

    def load(self) -> dict[str, MigrationRecord]:
        """
        Load migration history from file.

        Returns:
            Dict of migration records by ID
        """
        if not self.history_path.exists():
            self.logger.debug(f"History file not found: {self.history_path}")
            return {}

        try:
            with open(self.history_path, encoding="utf-8") as f:
                data = json.load(f)

            self.migrations = {}
            for migration_id, record_data in data.items():
                try:
                    self.migrations[migration_id] = MigrationRecord.from_dict(record_data)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    # One malformed history record must not block loading
                    # the rest of the migration history.
                    self.logger.warning("Failed to load migration record %s: %s", migration_id, e)

            self.logger.debug("Loaded %d migration records", len(self.migrations))
            return self.migrations

        except json.JSONDecodeError as e:
            self.logger.warning("Invalid JSON in history file: %s", e)
            return {}
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Best-effort history load; any unexpected failure should
            # degrade to an empty history rather than crash the caller.
            self.logger.warning("Failed to load history: %s", e)
            return {}

    def save(self) -> bool:
        """
        Save migration history to file.

        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure directory exists
            self.history_path.parent.mkdir(parents=True, exist_ok=True)

            # Trim to max_history if needed
            if len(self.migrations) > self.max_history:
                # Keep most recent records
                sorted_migrations = sorted(
                    self.migrations.items(), key=lambda x: x[1].start_time, reverse=True
                )
                self.migrations = dict(sorted_migrations[: self.max_history])

            # Convert to dict for JSON
            data = {migration_id: record.to_dict() for migration_id, record in self.migrations.items()}

            # Write to file
            with open(self.history_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True, default=str)

            self.logger.debug("Saved %d migration records", len(self.migrations))
            return True

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Best-effort history save; any unexpected failure should
            # be reported and return False rather than crash the caller.
            self.logger.exception("Failed to save history: %s", e)
            return False

    def add_migration(self, record: MigrationRecord) -> bool:
        """
        Add a new migration record.

        Args:
            record: Migration record to add

        Returns:
            True if successful
        """
        self.migrations[record.id] = record
        return self.save()

    def update_migration(
        self,
        migration_id: str,
        status: MigrationStatus | None = None,
        progress: float | None = None,
        error_message: str | None = None,
        end_time: str | None = None,
    ) -> bool:
        """
        Update an existing migration record.

        Args:
            migration_id: Migration ID
            status: Optional new status
            progress: Optional new progress percentage
            error_message: Optional error message
            end_time: Optional end time (ISO format)

        Returns:
            True if successful
        """
        if migration_id not in self.migrations:
            self.logger.warning(f"Migration {migration_id} not found")
            return False

        record = self.migrations[migration_id]

        if status is not None:
            record.status = status
        if progress is not None:
            record.progress = progress
        if error_message is not None:
            record.error_message = error_message
        if end_time is not None:
            record.end_time = end_time

        return self.save()

    def get_migration(self, migration_id: str) -> MigrationRecord | None:
        """
        Get a migration record by ID.

        Args:
            migration_id: Migration ID

        Returns:
            Migration record or None if not found
        """
        return self.migrations.get(migration_id)

    def get_active_migrations(self) -> list[MigrationRecord]:
        """
        Get all active migrations.

        Returns:
            List of active migration records
        """
        return [record for record in self.migrations.values() if record.is_active()]

    def get_completed_today(self) -> list[MigrationRecord]:
        """
        Get migrations completed today.

        Returns:
            List of migration records completed today
        """
        today = datetime.now().date()
        completed_today = []

        for record in self.migrations.values():
            if record.is_completed() and record.end_time:
                try:
                    end_date = datetime.fromisoformat(record.end_time).date()
                    if end_date == today:
                        completed_today.append(record)
                except (ValueError, TypeError) as e:
                    self.logger.debug(f"Skipping migration with invalid end_time: {e}")

        return completed_today

    def get_statistics(self) -> dict[str, Any]:
        """
        Calculate migration statistics.

        Returns:
            Dict with statistics:
            - total_migrations: Total number of migrations
            - active_migrations: Number of active migrations
            - completed_today: Number completed today
            - success_rate: Success rate percentage
            - total_completed: Total completed migrations
            - total_failed: Total failed migrations
            - avg_duration_seconds: Average duration for completed migrations
        """
        total = len(self.migrations)
        active = len(self.get_active_migrations())
        completed_today = len(self.get_completed_today())

        completed = [r for r in self.migrations.values() if r.is_completed()]
        failed = [r for r in self.migrations.values() if r.is_failed()]

        total_finished = len(completed) + len(failed)
        success_rate = (len(completed) / total_finished * 100) if total_finished > 0 else 100.0

        # Calculate average duration
        durations = [r.duration_seconds() for r in completed if r.duration_seconds() is not None]
        avg_duration = sum(durations) / len(durations) if durations else 0.0

        return {
            "total_migrations": total,
            "active_migrations": active,
            "completed_today": completed_today,
            "success_rate": success_rate,
            "total_completed": len(completed),
            "total_failed": len(failed),
            "avg_duration_seconds": avg_duration,
        }

    def cleanup_old_records(self, days: int = 30) -> int:
        """
        Remove migration records older than specified days.

        Args:
            days: Number of days to keep

        Returns:
            Number of records removed
        """
        cutoff = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff.isoformat()

        original_count = len(self.migrations)

        # Keep records newer than cutoff or still active
        self.migrations = {
            migration_id: record
            for migration_id, record in self.migrations.items()
            if record.start_time >= cutoff_str or record.is_active()
        }

        removed = original_count - len(self.migrations)

        if removed > 0:
            self.save()
            self.logger.info(f"Cleaned up {removed} old migration records")

        return removed


def create_migration_id(vm_name: str) -> str:
    """
    Create a unique migration ID.

    Args:
        vm_name: VM name

    Returns:
        Unique migration ID combining timestamp and VM name
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in vm_name)
    return f"mig_{timestamp}_{safe_name}"
