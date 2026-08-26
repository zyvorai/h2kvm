# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/worker/scheduler.py
"""
Job Scheduler and Queue.

Implements job scheduling, queuing, and worker assignment with capability matching.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import deque
from datetime import datetime
from pathlib import Path

from .schemas import JobSpec, JobState, WorkerCapabilities
from .state_machine import JobRegistry

logger = logging.getLogger(__name__)


class JobQueue:
    """
    Priority job queue with persistence.

    Maintains jobs in priority order and persists to disk.
    """

    def __init__(self, queue_dir: Path | None = None):
        """
        Initialize job queue.

        Args:
            queue_dir: Directory for queue persistence (default: /tmp/hyper2kvm/queue)
        """
        self.queue_dir = queue_dir or Path("/tmp/hyper2kvm/queue")
        self.queue_dir.mkdir(parents=True, exist_ok=True)

        # Priority queues (higher priority = lower number, 1 = highest)
        self._queues: dict[int, deque[JobSpec]] = {i: deque() for i in range(1, 11)}
        self._lock = threading.Lock()

        self.logger = logging.getLogger(__name__)

        # Load existing queue from disk
        self._load_from_disk()

    def enqueue(self, job_spec: JobSpec) -> None:
        """
        Add job to queue.

        Args:
            job_spec: Job specification
        """
        priority = job_spec.execution_policy.priority

        with self._lock:
            self._queues[priority].append(job_spec)
            self._persist_to_disk(job_spec)

        self.logger.info(f"Enqueued job {job_spec.job_id} with priority {priority}")

    def dequeue(self, worker_capabilities: dict[str, bool] | None = None) -> JobSpec | None:
        """
        Remove and return highest priority job that matches worker capabilities.

        Args:
            worker_capabilities: Worker capabilities for matching

        Returns:
            JobSpec if available, None otherwise
        """
        with self._lock:
            # Check queues in priority order (1 to 10)
            for priority in sorted(self._queues.keys()):
                queue = self._queues[priority]

                # Find first job that matches capabilities
                for _i, job_spec in enumerate(queue):
                    if self._job_matches_worker(job_spec, worker_capabilities):
                        # Remove from queue
                        queue.remove(job_spec)
                        self._remove_from_disk(job_spec.job_id)

                        self.logger.info(f"Dequeued job {job_spec.job_id}")
                        return job_spec

        return None

    def _job_matches_worker(self, job_spec: JobSpec, worker_capabilities: dict[str, bool] | None) -> bool:
        """Check if job requirements match worker capabilities."""
        if worker_capabilities is None:
            # No capabilities specified, match any job
            return True

        requirements = {
            "nbd": job_spec.capability_requirements.needs_nbd,
            "lvm": job_spec.capability_requirements.needs_lvm,
            "mount": job_spec.capability_requirements.needs_mount,
            "selinux": job_spec.capability_requirements.needs_selinux_tools,
        }

        for cap, required in requirements.items():
            if required and not worker_capabilities.get(cap, False):
                return False

        return True

    def peek(self) -> JobSpec | None:
        """Peek at next job without removing it."""
        with self._lock:
            for priority in sorted(self._queues.keys()):
                queue = self._queues[priority]
                if queue:
                    return queue[0]
        return None

    def size(self) -> int:
        """Get total number of jobs in queue."""
        with self._lock:
            return sum(len(q) for q in self._queues.values())

    def list_jobs(self) -> list[JobSpec]:
        """List all jobs in queue (in priority order)."""
        jobs = []
        with self._lock:
            for priority in sorted(self._queues.keys()):
                jobs.extend(self._queues[priority])
        return jobs

    def _persist_to_disk(self, job_spec: JobSpec) -> None:
        """Persist job to disk."""
        job_file = self.queue_dir / f"{job_spec.job_id}.job.json"
        try:
            with open(job_file, "w") as f:
                f.write(job_spec.model_dump_json(indent=2))
        except Exception as e:
            self.logger.exception(f"Failed to persist job {job_spec.job_id}: {e}")

    def _remove_from_disk(self, job_id: str) -> None:
        """Remove job from disk."""
        job_file = self.queue_dir / f"{job_id}.job.json"
        if job_file.exists():
            job_file.unlink()

    def _load_from_disk(self) -> None:
        """Load existing jobs from disk."""
        for job_file in self.queue_dir.glob("*.job.json"):
            try:
                with open(job_file) as f:
                    job_data = json.load(f)
                job_spec = JobSpec(**job_data)

                priority = job_spec.execution_policy.priority
                self._queues[priority].append(job_spec)

                self.logger.debug(f"Loaded queued job: {job_spec.job_id}")
            except Exception as e:
                self.logger.exception(f"Failed to load job from {job_file}: {e}")


class WorkerRegistry:
    """
    Registry of available workers.

    Tracks worker capabilities and availability for job matching.
    """

    def __init__(self, heartbeat_timeout: int = 300):
        """
        Initialize worker registry.

        Args:
            heartbeat_timeout: Timeout in seconds for worker heartbeat
        """
        self.heartbeat_timeout = heartbeat_timeout
        self._workers: dict[str, WorkerCapabilities] = {}
        self._lock = threading.Lock()

        self.logger = logging.getLogger(__name__)

    def register(self, worker_caps: WorkerCapabilities) -> None:
        """
        Register a worker.

        Args:
            worker_caps: Worker capabilities
        """
        with self._lock:
            self._workers[worker_caps.worker_id] = worker_caps

        self.logger.info(f"Registered worker: {worker_caps.worker_id}")

    def heartbeat(self, worker_id: str) -> bool:
        """
        Update worker heartbeat.

        Args:
            worker_id: Worker identifier

        Returns:
            True if worker exists and heartbeat was updated, False otherwise
        """
        with self._lock:
            if worker_id in self._workers:
                self._workers[worker_id].last_heartbeat = datetime.utcnow()
                return True
            return False

    def unregister(self, worker_id: str) -> None:
        """Unregister a worker."""
        with self._lock:
            if worker_id in self._workers:
                del self._workers[worker_id]
        self.logger.info(f"Unregistered worker: {worker_id}")

    def get_worker(self, worker_id: str) -> WorkerCapabilities | None:
        """Get worker capabilities by ID."""
        with self._lock:
            return self._workers.get(worker_id)

    def list_workers(self, only_alive: bool = True) -> list[WorkerCapabilities]:
        """
        List registered workers.

        Args:
            only_alive: Only return workers with recent heartbeat

        Returns:
            List of worker capabilities
        """
        workers = []
        cutoff = datetime.utcnow().timestamp() - self.heartbeat_timeout

        with self._lock:
            for worker in self._workers.values():
                if only_alive:
                    if worker.last_heartbeat.timestamp() > cutoff:
                        workers.append(worker)
                else:
                    workers.append(worker)

        return workers

    def find_capable_worker(self, requirements: dict[str, bool]) -> WorkerCapabilities | None:
        """
        Find a worker that can execute job with given requirements.

        Args:
            requirements: Required capabilities

        Returns:
            WorkerCapabilities if found, None otherwise
        """
        workers = self.list_workers(only_alive=True)

        for worker in workers:
            if self._worker_matches_requirements(worker, requirements):
                return worker

        return None

    def _worker_matches_requirements(
        self, worker: WorkerCapabilities, requirements: dict[str, bool]
    ) -> bool:
        """Check if worker matches requirements."""
        for cap, required in requirements.items():
            if required and not worker.capabilities.get(cap, False):
                return False
        return True


class JobScheduler:
    """
    Job scheduler with capability-based worker matching.

    Coordinates job queue and worker registry to assign jobs to capable workers.
    """

    def __init__(
        self,
        job_queue: JobQueue | None = None,
        worker_registry: WorkerRegistry | None = None,
        job_registry: JobRegistry | None = None,
    ):
        """
        Initialize scheduler.

        Args:
            job_queue: Job queue
            worker_registry: Worker registry
            job_registry: Job state registry
        """
        self.job_queue = job_queue or JobQueue()
        self.worker_registry = worker_registry or WorkerRegistry()
        self.job_registry = job_registry or JobRegistry()

        # Track assigned jobs
        self._assigned_jobs: dict[str, str] = {}  # job_id -> worker_id
        self._lock = threading.Lock()

        self.logger = logging.getLogger(__name__)

    def submit_job(self, job_spec: JobSpec) -> None:
        """
        Submit a job for execution.

        Args:
            job_spec: Job specification
        """
        # Register job
        sm = self.job_registry.register(job_spec)

        # Validate job
        # (In a real implementation, would validate against available workers)

        # Queue job
        sm.transition(JobState.VALIDATED, "Job validated")
        sm.transition(JobState.QUEUED, "Job queued for execution")
        self.job_queue.enqueue(job_spec)

        self.logger.info(f"Submitted job {job_spec.job_id}")

    def assign_job(self, worker_id: str) -> JobSpec | None:
        """
        Assign next available job to worker.

        Args:
            worker_id: Worker requesting job

        Returns:
            JobSpec if job assigned, None if no suitable jobs
        """
        # Get worker capabilities
        worker = self.worker_registry.get_worker(worker_id)
        if not worker:
            self.logger.warning(f"Unknown worker: {worker_id}")
            return None

        # Find matching job
        job_spec = self.job_queue.dequeue(worker.capabilities)
        if not job_spec:
            return None

        # Assign job
        with self._lock:
            self._assigned_jobs[job_spec.job_id] = worker_id

        # Update state
        sm = self.job_registry.get(job_spec.job_id)
        if sm:
            sm.transition(JobState.ASSIGNED, f"Assigned to worker {worker_id}")

        self.logger.info(f"Assigned job {job_spec.job_id} to worker {worker_id}")
        return job_spec

    def complete_job(self, job_id: str, success: bool, reason: str = "") -> None:
        """
        Mark job as completed.

        Args:
            job_id: Job identifier
            success: Whether job completed successfully
            reason: Completion reason
        """
        with self._lock:
            self._assigned_jobs.pop(job_id, None)

        # Update state
        sm = self.job_registry.get(job_id)
        if sm:
            if success:
                sm.transition(JobState.COMPLETED, reason or "Job completed")
            else:
                # Check if retry needed
                # (In real implementation, would check retry policy)
                sm.transition(JobState.FAILED, reason or "Job failed")

    def get_queue_size(self) -> int:
        """Get number of jobs in queue."""
        return self.job_queue.size()

    def get_assigned_jobs(self) -> dict[str, str]:
        """Get currently assigned jobs (job_id -> worker_id)."""
        with self._lock:
            return self._assigned_jobs.copy()


# Global scheduler instance
_scheduler: JobScheduler | None = None


def get_scheduler() -> JobScheduler:
    """Get global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = JobScheduler()
    return _scheduler
