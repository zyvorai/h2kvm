# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/rollback/state_tracker.py
"""
Migration state tracking for rollback support.

Tracks migration state changes and provides rollback points.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class MigrationState(Enum):
    """Migration states."""

    NOT_STARTED = "not_started"
    SNAPSHOT_CREATED = "snapshot_created"
    PRE_MIGRATION_CHECKS = "pre_migration_checks"
    STORAGE_ACTIVATED = "storage_activated"
    FILESYSTEM_MOUNTED = "filesystem_mounted"
    BOOTLOADER_FIXED = "bootloader_fixed"
    DRIVERS_INSTALLED = "drivers_installed"
    NETWORK_CONFIGURED = "network_configured"
    FSTAB_STABILIZED = "fstab_stabilized"
    VALIDATION_PASSED = "validation_passed"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class StateCheckpoint:
    """
    Migration state checkpoint.

    Attributes:
        state: Migration state
        timestamp: Checkpoint timestamp
        description: Human-readable description
        reversible: Whether this state can be rolled back
        data: State-specific data
    """

    state: MigrationState
    timestamp: datetime
    description: str
    reversible: bool = True
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "state": self.state.value,
            "timestamp": self.timestamp.isoformat(),
            "description": self.description,
            "reversible": self.reversible,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StateCheckpoint:
        """Create from dictionary."""
        return cls(
            state=MigrationState(data["state"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            description=data["description"],
            reversible=data.get("reversible", True),
            data=data.get("data", {}),
        )


class StateTracker:
    """
    Migration state tracker.

    Tracks migration progress and provides rollback checkpoints.
    """

    def __init__(self, logger: logging.Logger, state_file: Path | None = None):
        """
        Initialize state tracker.

        Args:
            logger: Logger instance
            state_file: Path to state file (default: temporary file)
        """
        self.logger = logger
        self.state_file = state_file

        self._current_state = MigrationState.NOT_STARTED
        self._checkpoints: list[StateCheckpoint] = []
        self._metadata: dict[str, Any] = {}

        if self.state_file and self.state_file.exists():
            self._load_state()

    def _load_state(self) -> None:
        """Load state from file."""
        if not self.state_file or not self.state_file.exists():
            return

        try:
            data = json.loads(self.state_file.read_text())

            self._current_state = MigrationState(data["current_state"])
            self._metadata = data.get("metadata", {})

            self._checkpoints = [StateCheckpoint.from_dict(cp) for cp in data.get("checkpoints", [])]

            self.logger.debug(f"Loaded state: {self._current_state.value}")

        except Exception as e:
            self.logger.warning(f"Failed to load state from {self.state_file}: {e}")

    def _save_state(self) -> None:
        """Save state to file."""
        if not self.state_file:
            return

        try:
            data = {
                "current_state": self._current_state.value,
                "metadata": self._metadata,
                "checkpoints": [cp.to_dict() for cp in self._checkpoints],
            }

            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(data, indent=2))

        except Exception as e:
            self.logger.warning(f"Failed to save state to {self.state_file}: {e}")

    def checkpoint(
        self, state: MigrationState, description: str, *, reversible: bool = True, **data: Any
    ) -> None:
        """
        Create state checkpoint.

        Args:
            state: New migration state
            description: Checkpoint description
            reversible: Whether this checkpoint can be rolled back
            **data: Additional state data
        """
        checkpoint = StateCheckpoint(
            state=state,
            timestamp=datetime.now(),
            description=description,
            reversible=reversible,
            data=data,
        )

        self._checkpoints.append(checkpoint)
        self._current_state = state

        self.logger.info(f"Checkpoint: {state.value} - {description}")

        self._save_state()

    def get_current_state(self) -> MigrationState:
        """Get current migration state."""
        return self._current_state

    def get_checkpoints(self) -> list[StateCheckpoint]:
        """Get all checkpoints."""
        return self._checkpoints.copy()

    def get_last_reversible_checkpoint(self) -> StateCheckpoint | None:
        """Get last reversible checkpoint."""
        for checkpoint in reversed(self._checkpoints):
            if checkpoint.reversible:
                return checkpoint
        return None

    def get_rollback_plan(self) -> list[StateCheckpoint]:
        """
        Get rollback plan (checkpoints in reverse order).

        Returns:
            List of checkpoints to rollback, in reverse order
        """
        # Find last irreversible checkpoint
        last_irreversible_idx = -1
        for i, checkpoint in enumerate(self._checkpoints):
            if not checkpoint.reversible:
                last_irreversible_idx = i

        # Rollback plan starts after last irreversible checkpoint
        rollback_checkpoints = self._checkpoints[last_irreversible_idx + 1 :]
        return list(reversed(rollback_checkpoints))

    def set_metadata(self, key: str, value: Any) -> None:
        """Set metadata value."""
        self._metadata[key] = value
        self._save_state()

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get metadata value."""
        return self._metadata.get(key, default)

    def clear(self) -> None:
        """Clear all state."""
        self._current_state = MigrationState.NOT_STARTED
        self._checkpoints.clear()
        self._metadata.clear()
        self._save_state()
