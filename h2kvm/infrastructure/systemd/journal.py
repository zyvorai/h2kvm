# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd Journal Integration
============================

Advanced journal logging with structured data and monitoring.
"""

import contextlib
import logging
import time
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Optional

try:
    # This imports the third-party python-systemd package (systemd.journal),
    # not this local module — ruff's PLW0406 false-positives here because this
    # package directory (h2kvm/infrastructure/systemd/) happens to share
    # the "systemd" name with the external top-level package.
    import systemd.journal  # noqa: PLW0406

    JOURNAL_AVAILABLE = True
except ImportError:
    JOURNAL_AVAILABLE = False


class JournalLogger:
    """Enhanced journal logging with structured data"""

    def __init__(self, vm_name: str, operation: str = "migration"):
        self.vm_name = vm_name
        self.operation = operation
        self.start_time = time.time()
        self.logger = logging.getLogger(__name__)

    def log_start(self):
        """Log operation start"""
        if JOURNAL_AVAILABLE:
            systemd.journal.send(
                f"Starting {self.operation} for {self.vm_name}",
                PRIORITY=systemd.journal.LOG_INFO,
                VM_NAME=self.vm_name,
                OPERATION=self.operation,
                STATUS="start",
                TIMESTAMP=str(time.time()),
            )
        self.logger.info(f"Started {self.operation} for {self.vm_name}")

    def log_success(self, duration: Optional[float] = None):
        """Log successful operation"""
        if duration is None:
            duration = time.time() - self.start_time

        if JOURNAL_AVAILABLE:
            systemd.journal.send(
                f"Successfully completed {self.operation} for {self.vm_name}",
                PRIORITY=systemd.journal.LOG_INFO,
                VM_NAME=self.vm_name,
                OPERATION=self.operation,
                STATUS="success",
                DURATION=str(duration),
                EXIT_CODE="0",
            )
        self.logger.info(f"Completed {self.operation} for {self.vm_name} in {duration:.2f}s")

    def log_failure(self, error: str, exit_code: int = 1):
        """Log operation failure"""
        if JOURNAL_AVAILABLE:
            systemd.journal.send(
                f"Failed {self.operation} for {self.vm_name}: {error}",
                PRIORITY=systemd.journal.LOG_ERR,
                VM_NAME=self.vm_name,
                OPERATION=self.operation,
                STATUS="failure",
                ERROR=error,
                EXIT_CODE=str(exit_code),
            )
        self.logger.error(f"Failed {self.operation} for {self.vm_name}: {error}")

    def log_step(self, step: str, status: str, details: str = ""):
        """Log individual operation step"""
        if JOURNAL_AVAILABLE:
            systemd.journal.send(
                f"{self.operation} step {step}: {status}",
                PRIORITY=systemd.journal.LOG_INFO,
                VM_NAME=self.vm_name,
                OPERATION=self.operation,
                STEP=step,
                STEP_STATUS=status,
                DETAILS=details,
                TIMESTAMP=str(time.time()),
            )
        self.logger.info(f"Step {step}: {status}")

    def log_progress(self, current: int, total: int, message: str = ""):
        """Log progress update"""
        percent = (current / total * 100) if total > 0 else 0

        if JOURNAL_AVAILABLE:
            systemd.journal.send(
                f"{self.operation} progress: {percent:.1f}%",
                PRIORITY=systemd.journal.LOG_INFO,
                VM_NAME=self.vm_name,
                OPERATION=self.operation,
                PROGRESS_CURRENT=str(current),
                PROGRESS_TOTAL=str(total),
                PROGRESS_PERCENT=f"{percent:.1f}",
                MESSAGE=message,
            )
        self.logger.info(f"Progress: {percent:.1f}% ({current}/{total}) {message}")

    def log_metric(self, metric_name: str, value: float, unit: str = ""):
        """Log performance metric"""
        if JOURNAL_AVAILABLE:
            systemd.journal.send(
                f"Metric {metric_name}: {value} {unit}",
                PRIORITY=systemd.journal.LOG_DEBUG,
                VM_NAME=self.vm_name,
                OPERATION=self.operation,
                METRIC_NAME=metric_name,
                METRIC_VALUE=str(value),
                METRIC_UNIT=unit,
            )


class JournalMonitor:
    """Monitor and analyze journal entries for VM operations"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        if not JOURNAL_AVAILABLE:
            self.logger.warning(
                "Journal monitoring not available.\n"
                "    Install with: pip install systemd-python  (or: dnf install python3-systemd)"
            )
            self.reader = None
            return

        self.reader = systemd.journal.Reader()
        self.reader.this_boot()
        self.reader.add_match(_SYSTEMD_UNIT__startswith="h2kvm")

    def get_recent_failures(self, hours: int = 24) -> list[dict]:
        """Get recent operation failures

        Args:
            hours: Look back this many hours

        Returns:
            List of failure entries
        """
        if not self.reader:
            return []

        failures = []
        since = datetime.now() - timedelta(hours=hours)

        self.reader.seek_realtime(since)
        self.reader.add_match(PRIORITY=systemd.journal.LOG_ERR)

        for entry in self.reader:
            failures.append(
                {
                    "timestamp": entry.get("__REALTIME_TIMESTAMP"),
                    "message": entry.get("MESSAGE", ""),
                    "vm": entry.get("VM_NAME", "unknown"),
                    "operation": entry.get("OPERATION", "unknown"),
                    "exit_code": entry.get("EXIT_CODE", "unknown"),
                    "error": entry.get("ERROR", ""),
                }
            )

        return failures

    def get_recent_successes(self, hours: int = 24) -> list[dict]:
        """Get recent successful operations"""
        if not self.reader:
            return []

        successes = []
        since = datetime.now() - timedelta(hours=hours)

        self.reader.seek_realtime(since)
        self.reader.add_match(STATUS="success")

        for entry in self.reader:
            successes.append(
                {
                    "timestamp": entry.get("__REALTIME_TIMESTAMP"),
                    "vm": entry.get("VM_NAME", "unknown"),
                    "operation": entry.get("OPERATION", "unknown"),
                    "duration": entry.get("DURATION", "unknown"),
                }
            )

        return successes

    def stream_logs(self, vm_name: Optional[str] = None, operation: Optional[str] = None) -> Iterator[dict]:
        """Stream logs in real-time

        Args:
            vm_name: Filter by VM name
            operation: Filter by operation type

        Yields:
            Log entries as they arrive
        """
        if not self.reader:
            return

        self.reader.seek_tail()
        self.reader.get_previous()

        if vm_name:
            self.reader.add_match(VM_NAME=vm_name)
        if operation:
            self.reader.add_match(OPERATION=operation)

        while True:
            entry = self.reader.get_next()
            if entry:
                yield self._format_entry(entry)
            else:
                time.sleep(0.5)

    def generate_report(self, days: int = 7) -> dict:
        """Generate operation report for last N days

        Args:
            days: Number of days to analyze

        Returns:
            Report dictionary with statistics
        """
        if not self.reader:
            return {}

        report = {
            "total_operations": 0,
            "successful": 0,
            "failed": 0,
            "avg_duration": 0,
            "vms": {},
            "operations": {},
        }

        since = datetime.now() - timedelta(days=days)
        self.reader.seek_realtime(since)

        durations = []
        for entry in self.reader:
            if "EXIT_CODE" not in entry:
                continue

            vm = entry.get("VM_NAME", "unknown")
            operation = entry.get("OPERATION", "unknown")
            report["total_operations"] += 1

            # Track per-VM stats
            if vm not in report["vms"]:
                report["vms"][vm] = {"success": 0, "fail": 0}

            # Track per-operation stats
            if operation not in report["operations"]:
                report["operations"][operation] = {"success": 0, "fail": 0}

            # Count success/failure
            if entry["EXIT_CODE"] == "0":
                report["successful"] += 1
                report["vms"][vm]["success"] += 1
                report["operations"][operation]["success"] += 1
            else:
                report["failed"] += 1
                report["vms"][vm]["fail"] += 1
                report["operations"][operation]["fail"] += 1

            # Track duration
            if "DURATION" in entry:
                with contextlib.suppress(ValueError):
                    durations.append(float(entry["DURATION"]))

        # Calculate average duration
        if durations:
            report["avg_duration"] = sum(durations) / len(durations)
            report["min_duration"] = min(durations)
            report["max_duration"] = max(durations)

        return report

    def _format_entry(self, entry) -> dict:
        """Format journal entry to dictionary"""
        return {
            "timestamp": str(entry.get("__REALTIME_TIMESTAMP", "")),
            "priority": entry.get("PRIORITY", 6),
            "message": entry.get("MESSAGE", ""),
            "vm": entry.get("VM_NAME", "unknown"),
            "operation": entry.get("OPERATION", "unknown"),
            "unit": entry.get("_SYSTEMD_UNIT", "unknown"),
            "status": entry.get("STATUS", ""),
            "step": entry.get("STEP", ""),
            "details": entry.get("DETAILS", ""),
        }

    def get_vm_history(self, vm_name: str, days: int = 30) -> list[dict]:
        """Get complete history for a specific VM

        Args:
            vm_name: Name of the VM
            days: Days of history to retrieve

        Returns:
            List of all operations for the VM
        """
        if not self.reader:
            return []

        history = []
        since = datetime.now() - timedelta(days=days)

        self.reader.seek_realtime(since)
        self.reader.add_match(VM_NAME=vm_name)

        for entry in self.reader:
            if "OPERATION" in entry:
                history.append(self._format_entry(entry))

        return history


def setup_journal_handler(logger: logging.Logger):
    """Setup systemd journal handler for Python logging

    Args:
        logger: Logger to configure
    """
    if not JOURNAL_AVAILABLE:
        return

    # Create journal handler
    journal_handler = systemd.journal.JournalHandler(SYSLOG_IDENTIFIER="h2kvm")

    # Set format
    formatter = logging.Formatter("%(levelname)s: %(message)s")
    journal_handler.setFormatter(formatter)

    # Add to logger
    logger.addHandler(journal_handler)
