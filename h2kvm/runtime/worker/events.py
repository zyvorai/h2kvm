# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/worker/events.py
"""
Progress Event Streaming and Persistence.

Provides real-time event emission, storage, and retrieval for job progress tracking.
Supports multiple backends: file-based, in-memory, and extensible to WebSocket/SSE.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from .schemas import ProgressEvent

if TYPE_CHECKING:
    from datetime import datetime

logger = logging.getLogger(__name__)


class EventStore:
    """
    Event storage backend.

    Stores progress events for later retrieval and analysis.
    """

    def __init__(self, storage_dir: Path | None = None):
        """
        Initialize event store.

        Args:
            storage_dir: Directory for event storage (default: /tmp/h2kvm/events)
        """
        self.storage_dir = storage_dir or Path("/tmp/h2kvm/events")
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # In-memory cache for fast access
        self._cache: dict[str, list[ProgressEvent]] = {}
        self._lock = threading.Lock()

        self.logger = logging.getLogger(__name__)

    def store(self, event: ProgressEvent) -> None:
        """
        Store a progress event.

        Args:
            event: Progress event to store
        """
        with self._lock:
            # Add to in-memory cache
            if event.job_id not in self._cache:
                self._cache[event.job_id] = []
            self._cache[event.job_id].append(event)

            # Persist to disk
            event_file = self.storage_dir / f"{event.job_id}.events.jsonl"

            try:
                with open(event_file, "a") as f:
                    # Write as JSON Lines (one event per line)
                    f.write(event.model_dump_json() + "\n")
            except Exception as e:
                self.logger.exception(f"Failed to persist event for job {event.job_id}: {e}")

    def get_events(
        self, job_id: str, since: datetime | None = None, phase_filter: str | None = None
    ) -> list[ProgressEvent]:
        """
        Retrieve events for a job.

        Args:
            job_id: Job identifier
            since: Only return events after this timestamp
            phase_filter: Only return events from this phase

        Returns:
            List of progress events
        """
        with self._lock:
            # Try cache first
            if job_id in self._cache:
                events = self._cache[job_id]
            else:
                # Load from disk
                events = self._load_from_disk(job_id)
                self._cache[job_id] = events

            # Apply filters
            filtered = events

            if since:
                filtered = [e for e in filtered if e.timestamp > since]

            if phase_filter:
                filtered = [e for e in filtered if e.phase == phase_filter]

            return filtered

    def _load_from_disk(self, job_id: str) -> list[ProgressEvent]:
        """Load events from disk."""
        event_file = self.storage_dir / f"{job_id}.events.jsonl"

        if not event_file.exists():
            return []

        events = []
        try:
            with open(event_file) as f:
                for line in f:
                    if line.strip():
                        event_data = json.loads(line)
                        events.append(ProgressEvent(**event_data))
        except Exception as e:
            self.logger.exception(f"Failed to load events for job {job_id}: {e}")

        return events

    def get_latest_event(self, job_id: str) -> ProgressEvent | None:
        """Get the most recent event for a job."""
        events = self.get_events(job_id)
        return events[-1] if events else None

    def clear_job_events(self, job_id: str) -> None:
        """Clear all events for a job."""
        with self._lock:
            # Remove from cache
            self._cache.pop(job_id, None)

            # Remove from disk
            event_file = self.storage_dir / f"{job_id}.events.jsonl"
            if event_file.exists():
                event_file.unlink()

    def list_job_ids(self) -> list[str]:
        """List all job IDs with stored events."""
        job_ids = []
        for event_file in self.storage_dir.glob("*.events.jsonl"):
            job_id = event_file.stem.replace(".events", "")
            job_ids.append(job_id)
        return job_ids


class EventEmitter:
    """
    Event emitter for progress tracking.

    Supports multiple listeners (callbacks, storage, streaming).
    """

    def __init__(self, job_id: str, event_store: EventStore | None = None):
        """
        Initialize event emitter.

        Args:
            job_id: Job identifier
            event_store: Event store for persistence
        """
        self.job_id = job_id
        self.event_store = event_store or EventStore()

        # Registered listeners
        self._listeners: list[Callable[[ProgressEvent], None]] = []
        self._lock = threading.Lock()

        self.logger = logging.getLogger(f"{__name__}.{job_id}")

    def register_listener(self, callback: Callable[[ProgressEvent], None]) -> None:
        """
        Register a listener for events.

        Args:
            callback: Function to call with each event
        """
        with self._lock:
            self._listeners.append(callback)

    def unregister_listener(self, callback: Callable[[ProgressEvent], None]) -> None:
        """Unregister a listener."""
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def emit(
        self, phase: str, progress_percent: int, message: str, details: dict | None = None
    ) -> ProgressEvent:
        """
        Emit a progress event.

        Args:
            phase: Execution phase
            progress_percent: Progress percentage (0-100)
            message: Human-readable message
            details: Additional phase-specific details

        Returns:
            The emitted event
        """
        event = ProgressEvent(
            job_id=self.job_id,
            phase=phase,
            progress_percent=progress_percent,
            message=message,
            details=details,
        )

        # Store event
        self.event_store.store(event)

        # Notify listeners
        with self._lock:
            for listener in self._listeners:
                try:
                    listener(event)
                except Exception as e:
                    self.logger.exception(f"Listener failed: {e}")

        return event

    def get_progress(self) -> int | None:
        """Get current progress percentage."""
        latest = self.event_store.get_latest_event(self.job_id)
        return latest.progress_percent if latest else None


class EventStream:
    """
    Event stream for real-time updates.

    Provides iterator-based access to events as they arrive.
    Can be used for WebSocket/SSE streaming.
    """

    def __init__(
        self, job_id: str, event_store: EventStore, follow: bool = True, since: datetime | None = None
    ):
        """
        Initialize event stream.

        Args:
            job_id: Job identifier
            event_store: Event store to stream from
            follow: Continue streaming new events as they arrive
            since: Only stream events after this timestamp
        """
        self.job_id = job_id
        self.event_store = event_store
        self.follow = follow
        self.since = since

        self._position = 0
        self._stop = threading.Event()

    def __iter__(self):
        """Iterate over events."""
        # Get initial events
        events = self.event_store.get_events(self.job_id, since=self.since)
        for event in events:
            yield event
            self._position += 1

        # Follow mode: wait for new events
        if self.follow:
            while not self._stop.is_set():
                # Check for new events
                all_events = self.event_store.get_events(self.job_id)
                if len(all_events) > self._position:
                    for event in all_events[self._position :]:
                        yield event
                        self._position += 1
                else:
                    # Wait a bit before checking again
                    self._stop.wait(timeout=0.5)

    def stop(self):
        """Stop streaming."""
        self._stop.set()


class ProgressTracker:
    """
    High-level progress tracker for multi-phase operations.

    Simplifies progress reporting with automatic percentage calculation.
    """

    def __init__(self, job_id: str, phases: list[str], event_emitter: EventEmitter | None = None):
        """
        Initialize progress tracker.

        Args:
            job_id: Job identifier
            phases: List of phase names in execution order
            event_emitter: Event emitter (default: creates new one)
        """
        self.job_id = job_id
        self.phases = phases
        self.emitter = event_emitter or EventEmitter(job_id)

        self._current_phase_idx = 0
        self._phase_progress: dict[str, int] = dict.fromkeys(phases, 0)

    def start_phase(self, phase: str, message: str = "") -> None:
        """
        Start a new phase.

        Args:
            phase: Phase name
            message: Optional message
        """
        if phase not in self.phases:
            raise ValueError(f"Unknown migration phase '{phase}'. Valid phases: {', '.join(self.phases)}.")

        self._current_phase_idx = self.phases.index(phase)

        msg = message or f"Starting {phase}"
        overall_progress = self._calculate_overall_progress()

        self.emitter.emit(phase, overall_progress, msg)

    def update_phase(
        self, phase: str, progress_percent: int, message: str, details: dict | None = None
    ) -> None:
        """
        Update progress within a phase.

        Args:
            phase: Phase name
            progress_percent: Progress within this phase (0-100)
            message: Progress message
            details: Additional details
        """
        if phase not in self.phases:
            raise ValueError(f"Unknown migration phase '{phase}'. Valid phases: {', '.join(self.phases)}.")

        self._phase_progress[phase] = progress_percent
        overall_progress = self._calculate_overall_progress()

        self.emitter.emit(phase, overall_progress, message, details)

    def complete_phase(self, phase: str, message: str = "") -> None:
        """
        Mark a phase as complete.

        Args:
            phase: Phase name
            message: Optional completion message
        """
        self._phase_progress[phase] = 100
        overall_progress = self._calculate_overall_progress()

        msg = message or f"Completed {phase}"
        self.emitter.emit(phase, overall_progress, msg)

    def _calculate_overall_progress(self) -> int:
        """Calculate overall progress across all phases."""
        if not self.phases:
            return 0

        # Weight each phase equally
        phase_weight = 100.0 / len(self.phases)

        total_progress = 0.0
        for phase in self.phases:
            phase_progress = self._phase_progress.get(phase, 0)
            total_progress += (phase_progress / 100.0) * phase_weight

        return int(total_progress)

    def get_overall_progress(self) -> int:
        """Get current overall progress percentage."""
        return self._calculate_overall_progress()


# Global event store instance
_event_store: EventStore | None = None


def get_event_store() -> EventStore:
    """Get global event store instance."""
    global _event_store
    if _event_store is None:
        _event_store = EventStore()
    return _event_store
