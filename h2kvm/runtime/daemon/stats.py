# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/daemon/stats.py
"""
Statistics tracking for daemon mode.
Tracks processing metrics, success rates, and performance data.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging
    from pathlib import Path


@dataclass
class JobStats:
    """Statistics for a single job."""

    filename: str
    file_type: str
    file_size_mb: float
    start_time: str
    end_time: str | None
    duration_seconds: float | None
    status: str  # 'processing', 'success', 'failed', 'retrying'
    error: str | None = None
    retry_count: int = 0


class DaemonStatistics:
    """
    Tracks daemon statistics and performance metrics.

    Thread-safe implementation for concurrent access.
    """

    def __init__(self, logger: logging.Logger, stats_file: Path):
        self.logger = logger
        self.stats_file = stats_file
        self.lock = threading.Lock()

        # Current state
        self.start_time = datetime.now()
        self.total_processed = 0
        self.total_failed = 0
        self.total_retried = 0
        self.current_jobs: dict[str, JobStats] = {}
        self.completed_jobs: list[JobStats] = []

        # Performance tracking
        self.total_processing_time = 0.0
        self.by_file_type: dict[str, dict[str, int]] = {}

        # Periodic save
        self._last_save = time.time()
        self._save_interval = 60  # Save every 60 seconds

        # Load existing stats if available
        self._load()

    def _load(self) -> None:
        """Load existing statistics from file."""
        if not self.stats_file.exists():
            return

        try:
            with open(self.stats_file) as f:
                data = json.load(f)

            self.total_processed = data.get("total_processed", 0)
            self.total_failed = data.get("total_failed", 0)
            self.total_retried = data.get("total_retried", 0)
            self.total_processing_time = data.get("total_processing_time", 0.0)
            self.by_file_type = data.get("by_file_type", {})

            self.logger.info(
                f"📊 Loaded stats: {self.total_processed} processed, {self.total_failed} failed"
            )
        except Exception as e:
            self.logger.warning(f"Failed to load stats: {e}")

    def job_started(self, filename: str, file_type: str, file_size_mb: float) -> None:
        """Record job start."""
        with self.lock:
            job = JobStats(
                filename=filename,
                file_type=file_type,
                file_size_mb=file_size_mb,
                start_time=datetime.now().isoformat(),
                end_time=None,
                duration_seconds=None,
                status="processing",
            )
            self.current_jobs[filename] = job
            self.logger.debug(f"📊 Job started: {filename}")

    def job_completed(self, filename: str, success: bool, error: str | None = None) -> None:
        """Record job completion."""
        with self.lock:
            if filename not in self.current_jobs:
                self.logger.warning(f"Job {filename} not found in current jobs")
                return

            job = self.current_jobs[filename]
            job.end_time = datetime.now().isoformat()
            job.status = "success" if success else "failed"
            job.error = error

            # Calculate duration
            start = datetime.fromisoformat(job.start_time)
            end = datetime.fromisoformat(job.end_time)
            job.duration_seconds = (end - start).total_seconds()

            # Update counters
            if success:
                self.total_processed += 1
                self.total_processing_time += job.duration_seconds
            else:
                self.total_failed += 1

            # Track by file type
            if job.file_type not in self.by_file_type:
                self.by_file_type[job.file_type] = {"processed": 0, "failed": 0, "total_time": 0}

            if success:
                self.by_file_type[job.file_type]["processed"] += 1
                self.by_file_type[job.file_type]["total_time"] += job.duration_seconds
            else:
                self.by_file_type[job.file_type]["failed"] += 1

            # Move to completed
            self.completed_jobs.append(job)
            del self.current_jobs[filename]

            # Keep only last 100 completed jobs
            if len(self.completed_jobs) > 100:
                self.completed_jobs = self.completed_jobs[-100:]

            self.logger.info(
                f"📊 Job {'completed' if success else 'failed'}: {filename} ({job.duration_seconds:.1f}s)"
            )

            # Periodic save
            if time.time() - self._last_save > self._save_interval:
                self.save()

    def job_retried(self, filename: str) -> None:
        """Record job retry."""
        with self.lock:
            self.total_retried += 1
            if filename in self.current_jobs:
                self.current_jobs[filename].retry_count += 1
                self.current_jobs[filename].status = "retrying"

    def get_summary(self) -> dict:
        """Get statistics summary."""
        with self.lock:
            uptime_seconds = (datetime.now() - self.start_time).total_seconds()
            total_jobs = self.total_processed + self.total_failed
            success_rate = (self.total_processed / total_jobs * 100) if total_jobs > 0 else 0
            avg_time = (self.total_processing_time / self.total_processed) if self.total_processed > 0 else 0

            return {
                "daemon_start_time": self.start_time.isoformat(),
                "uptime_seconds": uptime_seconds,
                "uptime_hours": uptime_seconds / 3600,
                "total_processed": self.total_processed,
                "total_failed": self.total_failed,
                "total_retried": self.total_retried,
                "success_rate_percent": round(success_rate, 2),
                "average_processing_time_seconds": round(avg_time, 2),
                "current_queue_depth": len(self.current_jobs),
                "current_jobs": [asdict(job) for job in self.current_jobs.values()],
                "by_file_type": self._get_type_summary(),
                "recent_completed": [asdict(job) for job in self.completed_jobs[-10:]],
            }

    def _get_type_summary(self) -> dict:
        """Get summary by file type."""
        summary = {}
        for file_type, stats in self.by_file_type.items():
            total = stats["processed"] + stats["failed"]
            avg_time = stats["total_time"] / stats["processed"] if stats["processed"] > 0 else 0
            success_rate = (stats["processed"] / total * 100) if total > 0 else 0

            summary[file_type] = {
                "processed": stats["processed"],
                "failed": stats["failed"],
                "success_rate_percent": round(success_rate, 2),
                "average_time_seconds": round(avg_time, 2),
            }
        return summary

    def save(self, force: bool = False) -> None:
        """Save statistics to file."""
        with self.lock:
            try:
                summary = self.get_summary()
                summary["last_updated"] = datetime.now().isoformat()

                # Ensure parent directory exists
                self.stats_file.parent.mkdir(parents=True, exist_ok=True)

                # Write to temp file first, then atomic rename
                temp_file = self.stats_file.with_suffix(".tmp")
                with open(temp_file, "w") as f:
                    json.dump(summary, f, indent=2)

                temp_file.replace(self.stats_file)
                self._last_save = time.time()

                if force:
                    self.logger.info(f"📊 Stats saved: {self.stats_file}")
            except Exception as e:
                self.logger.exception(f"Failed to save stats: {e}")

    def print_summary(self) -> None:
        """Print statistics summary to log."""
        summary = self.get_summary()

        self.logger.info("━" * 60)
        self.logger.info("📊 DAEMON STATISTICS")
        self.logger.info("━" * 60)
        self.logger.info(f"Uptime: {summary['uptime_hours']:.1f} hours")
        self.logger.info(f"Total Processed: {summary['total_processed']}")
        self.logger.info(f"Total Failed: {summary['total_failed']}")
        self.logger.info(f"Total Retried: {summary['total_retried']}")
        self.logger.info(f"Success Rate: {summary['success_rate_percent']}%")
        self.logger.info(f"Avg Processing Time: {summary['average_processing_time_seconds']:.1f}s")
        self.logger.info(f"Current Queue: {summary['current_queue_depth']} jobs")

        if summary["by_file_type"]:
            self.logger.info("━" * 60)
            self.logger.info("By File Type:")
            for file_type, stats in summary["by_file_type"].items():
                self.logger.info(
                    f"  {file_type}: {stats['processed']} ok, {stats['failed']} failed, "
                    f"{stats['success_rate_percent']}% success, "
                    f"{stats['average_time_seconds']:.1f}s avg"
                )

        self.logger.info("━" * 60)
