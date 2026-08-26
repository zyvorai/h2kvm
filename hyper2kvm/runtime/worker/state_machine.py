# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/worker/state_machine.py
"""
Job State Machine.

Implements job lifecycle state transitions with validation and persistence.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path

from .schemas import JobSpec, JobState

logger = logging.getLogger(__name__)


class InvalidStateTransition(Exception):
    """Raised when attempting an invalid state transition."""

    def __init__(self, from_state: JobState, to_state: JobState, reason: str = ""):
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason
        super().__init__(
            f"Invalid transition from {from_state.value} to {to_state.value}"
            + (f": {reason}" if reason else "")
        )


class JobStateMachine:
    """
    Job state machine with transition validation.

    Valid transitions:
        CREATED → VALIDATED
        VALIDATED → QUEUED
        QUEUED → ASSIGNED
        ASSIGNED → RUNNING
        RUNNING → PROGRESSING
        PROGRESSING → PROGRESSING (self-transition for updates)
        PROGRESSING → COMPLETED | FAILED | RETRYING
        RUNNING → COMPLETED | FAILED | RETRYING
        RETRYING → QUEUED | FAILED
        Any → CANCELLED

    Terminal states: COMPLETED, FAILED, CANCELLED
    """

    # Valid state transitions
    TRANSITIONS: dict[JobState, set[JobState]] = {
        JobState.CREATED: {JobState.VALIDATED, JobState.CANCELLED},
        JobState.VALIDATED: {JobState.QUEUED, JobState.CANCELLED},
        JobState.QUEUED: {JobState.ASSIGNED, JobState.CANCELLED},
        JobState.ASSIGNED: {JobState.RUNNING, JobState.CANCELLED},
        JobState.RUNNING: {
            JobState.PROGRESSING,
            JobState.COMPLETED,
            JobState.FAILED,
            JobState.RETRYING,
            JobState.CANCELLED,
        },
        JobState.PROGRESSING: {
            JobState.PROGRESSING,  # Self-transition for progress updates
            JobState.COMPLETED,
            JobState.FAILED,
            JobState.RETRYING,
            JobState.CANCELLED,
        },
        JobState.RETRYING: {JobState.QUEUED, JobState.FAILED, JobState.CANCELLED},
        # Terminal states can only transition to themselves (idempotent updates)
        JobState.COMPLETED: {JobState.COMPLETED},
        JobState.FAILED: {JobState.FAILED},
        JobState.CANCELLED: {JobState.CANCELLED},
    }

    # Terminal states (no further transitions except to self)
    TERMINAL_STATES = {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}

    def __init__(self, job_id: str, initial_state: JobState = JobState.CREATED):
        """
        Initialize state machine for a job.

        Args:
            job_id: Job identifier
            initial_state: Initial state (default: CREATED)
        """
        self.job_id = job_id
        self._lock = threading.Lock()
        self.current_state = initial_state
        self.state_history: list[dict] = [
            {
                "state": initial_state.value,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": "Job created",
            }
        ]
        self.logger = logging.getLogger(f"{__name__}.{job_id}")

    def can_transition(self, to_state: JobState) -> bool:
        """
        Check if transition to target state is valid.

        Args:
            to_state: Target state

        Returns:
            True if transition is valid
        """
        if self.current_state == to_state:
            # Self-transition always allowed
            return True

        allowed_states = self.TRANSITIONS.get(self.current_state, set())
        return to_state in allowed_states

    def transition(self, to_state: JobState, reason: str = "") -> None:
        """
        Transition to new state with validation.

        Args:
            to_state: Target state
            reason: Reason for transition (for audit trail)

        Raises:
            InvalidStateTransition: If transition is not valid
        """
        with self._lock:
            if not self.can_transition(to_state):
                raise InvalidStateTransition(
                    self.current_state, to_state, reason or "Transition not allowed"
                )

            # Log transition
            self.logger.info(
                f"Job {self.job_id}: {self.current_state.value} → {to_state.value}"
                + (f" ({reason})" if reason else "")
            )

            # Record in history
            self.state_history.append(
                {
                    "from_state": self.current_state.value,
                    "to_state": to_state.value,
                    "timestamp": datetime.utcnow().isoformat(),
                    "reason": reason,
                }
            )

            # Update current state
            self.current_state = to_state

    def is_terminal(self) -> bool:
        """Check if current state is terminal (job finished)."""
        return self.current_state in self.TERMINAL_STATES

    def get_state_duration(self, state: JobState) -> float | None:
        """
        Get time spent in a specific state (in seconds).

        Args:
            state: State to measure

        Returns:
            Duration in seconds, or None if never in that state
        """
        entries = [h for h in self.state_history if h.get("to_state") == state.value]
        if not entries:
            return None

        # Find first entry and exit
        entry_time = datetime.fromisoformat(entries[0]["timestamp"])

        # Find when we left this state
        entry_idx = self.state_history.index(entries[0])
        if entry_idx + 1 < len(self.state_history):
            exit_time = datetime.fromisoformat(self.state_history[entry_idx + 1]["timestamp"])
        else:
            # Still in this state
            exit_time = datetime.utcnow()

        return (exit_time - entry_time).total_seconds()

    def to_dict(self) -> dict:
        """Serialize state machine to dictionary."""
        return {
            "job_id": self.job_id,
            "current_state": self.current_state.value,
            "state_history": self.state_history,
            "is_terminal": self.is_terminal(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> JobStateMachine:
        """Deserialize state machine from dictionary."""
        sm = cls(job_id=data["job_id"], initial_state=JobState(data["current_state"]))
        sm.state_history = data.get("state_history", [])
        return sm

    def save(self, state_dir: Path) -> None:
        """
        Save state machine to disk.

        Args:
            state_dir: Directory to save state files
        """
        state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        state_file = state_dir / f"{self.job_id}.state.json"

        with open(state_file, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

        self.logger.debug(f"Saved state to {state_file}")

    @classmethod
    def load(cls, job_id: str, state_dir: Path) -> JobStateMachine | None:
        """
        Load state machine from disk.

        Args:
            job_id: Job identifier
            state_dir: Directory containing state files

        Returns:
            JobStateMachine if found, None otherwise
        """
        state_file = state_dir / f"{job_id}.state.json"

        if not state_file.exists():
            return None

        try:
            with open(state_file) as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            logger.exception(f"Failed to load state for job {job_id}: {e}")
            return None


class JobRegistry:
    """
    Registry for managing multiple job state machines.

    Provides persistence and lookup for job states.
    """

    def __init__(self, state_dir: Path | None = None):
        """
        Initialize job registry.

        Args:
            state_dir: Directory for state persistence (default: /tmp/hyper2kvm/jobs)
        """
        self.state_dir = state_dir or Path("/tmp/hyper2kvm/jobs")
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        self.jobs: dict[str, JobStateMachine] = {}
        self.logger = logging.getLogger(__name__)

    def register(self, job_spec: JobSpec) -> JobStateMachine:
        """
        Register a new job.

        Args:
            job_spec: Job specification

        Returns:
            JobStateMachine for the job
        """
        sm = JobStateMachine(job_spec.job_id, JobState.CREATED)
        self.jobs[job_spec.job_id] = sm
        sm.save(self.state_dir)

        self.logger.info(f"Registered job {job_spec.job_id}")
        return sm

    def get(self, job_id: str) -> JobStateMachine | None:
        """
        Get job state machine.

        Args:
            job_id: Job identifier

        Returns:
            JobStateMachine if found, None otherwise
        """
        # Check in-memory cache
        if job_id in self.jobs:
            return self.jobs[job_id]

        # Try to load from disk
        sm = JobStateMachine.load(job_id, self.state_dir)
        if sm:
            self.jobs[job_id] = sm

        return sm

    def update_state(self, job_id: str, new_state: JobState, reason: str = "") -> None:
        """
        Update job state.

        Args:
            job_id: Job identifier
            new_state: New state
            reason: Reason for state change

        Raises:
            ValueError: If job not found
            InvalidStateTransition: If transition not valid
        """
        sm = self.get(job_id)
        if not sm:
            raise ValueError(
                f"Job '{job_id}' not found. It may have completed or been removed. "
                f"Check active jobs with the job listing endpoint."
            )

        sm.transition(new_state, reason)
        sm.save(self.state_dir)

    def list_jobs(self, state_filter: JobState | None = None) -> list[str]:
        """
        List job IDs, optionally filtered by state.

        Args:
            state_filter: Only return jobs in this state

        Returns:
            List of job IDs
        """
        # Load all job states from disk
        job_ids = []
        for state_file in self.state_dir.glob("*.state.json"):
            job_id = state_file.stem.replace(".state", "")
            sm = self.get(job_id)

            if sm and (state_filter is None or sm.current_state == state_filter):
                job_ids.append(job_id)

        return job_ids

    def cleanup_terminal_jobs(self, max_age_hours: int = 24) -> int:
        """
        Remove terminal jobs older than specified age.

        Args:
            max_age_hours: Maximum age in hours

        Returns:
            Number of jobs removed
        """
        removed = 0
        cutoff = datetime.utcnow().timestamp() - (max_age_hours * 3600)

        for state_file in self.state_dir.glob("*.state.json"):
            if state_file.stat().st_mtime < cutoff:
                job_id = state_file.stem.replace(".state", "")
                sm = self.get(job_id)

                if sm and sm.is_terminal():
                    state_file.unlink()
                    self.jobs.pop(job_id, None)
                    removed += 1
                    self.logger.info(f"Cleaned up terminal job: {job_id}")

        return removed
