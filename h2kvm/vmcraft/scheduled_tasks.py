# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/scheduled_tasks.py
"""
Scheduled task and cron job analysis for both Windows and Linux.

Provides comprehensive scheduled task detection:
- Linux cron jobs (system and user crontabs)
- Linux systemd timers
- anacron jobs
- at jobs
- Windows Task Scheduler (via registry and XML files)

Features:
- Parse cron syntax
- List scheduled tasks
- Identify task frequency
- Detect disabled/enabled tasks
- Task dependencies and triggers
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging

    from .file_ops import FileOperations


class ScheduledTaskAnalyzer:
    """
    Scheduled task and cron job analyzer.

    Analyzes scheduled tasks for both Windows and Linux systems.
    """

    def __init__(self, logger: logging.Logger, file_ops: FileOperations):
        """
        Initialize scheduled task analyzer.

        Args:
            logger: Logger instance
            file_ops: FileOperations instance
        """
        self.logger = logger
        self.file_ops = file_ops

    def analyze_scheduled_tasks(self, os_type: str) -> dict[str, Any]:
        """
        Analyze scheduled tasks based on OS type.

        Args:
            os_type: Operating system type ("windows" or "linux")

        Returns:
            Scheduled tasks configuration dictionary
        """
        if os_type == "windows":
            return self._analyze_windows_tasks()
        if os_type == "linux":
            return self._analyze_linux_tasks()
        return {"error": f"Unsupported OS type: {os_type}"}

    def _analyze_linux_tasks(self) -> dict[str, Any]:
        """
        Analyze Linux scheduled tasks.

        Detects and parses:
        - System crontab (/etc/crontab)
        - Cron.d files (/etc/cron.d/*)
        - User crontabs (/var/spool/cron/*)
        - Systemd timers (/etc/systemd/system/*.timer)
        - Anacron (/etc/anacrontab)

        Returns:
            Scheduled tasks configuration
        """
        config: dict[str, Any] = {
            "system_cron": [],
            "user_cron": [],
            "cron_d": [],
            "systemd_timers": [],
            "anacron": [],
            "total_count": 0,
        }

        # Parse system crontab
        if self.file_ops.exists("/etc/crontab"):
            system_jobs = self._parse_crontab("/etc/crontab")
            config["system_cron"] = system_jobs
            config["total_count"] += len(system_jobs)

        # Parse cron.d directory
        if self.file_ops.is_dir("/etc/cron.d"):
            files = self.file_ops.ls("/etc/cron.d")
            for file in files:
                if not file.startswith("."):
                    jobs = self._parse_crontab(f"/etc/cron.d/{file}")
                    config["cron_d"].extend([{"file": file, **job} for job in jobs])
            config["total_count"] += len(config["cron_d"])

        # Parse user crontabs
        if self.file_ops.is_dir("/var/spool/cron"):
            files = self.file_ops.ls("/var/spool/cron")
            for file in files:
                if not file.startswith("."):
                    jobs = self._parse_crontab(f"/var/spool/cron/{file}")
                    config["user_cron"].extend([{"user": file, **job} for job in jobs])
            config["total_count"] += len(config["user_cron"])

        # Parse systemd timers
        if self.file_ops.is_dir("/etc/systemd/system"):
            timers = self._parse_systemd_timers()
            config["systemd_timers"] = timers
            config["total_count"] += len(timers)

        # Parse anacron
        if self.file_ops.exists("/etc/anacrontab"):
            anacron_jobs = self._parse_anacrontab("/etc/anacrontab")
            config["anacron"] = anacron_jobs
            config["total_count"] += len(anacron_jobs)

        return config

    def _parse_crontab(self, filepath: str) -> list[dict[str, Any]]:
        """Parse a crontab file."""
        jobs = []

        # pylint: disable=duplicate-code
        # reason: mirrors the equivalent cron-line parsing loop in
        # core/inspectors/linux_extractor.py (extract_cron_jobs) --
        # structurally similar by coincidence, not shared logic; keeping
        # independent avoids coupling unrelated cron-parsing code paths.
        try:
            content = self.file_ops.cat(filepath)

            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Parse cron line: minute hour day month weekday user command
                # System crontabs have user field, user crontabs don't
                parts = line.split(None, 6)
                if len(parts) < 6:
                    continue

                # Check if this is a system crontab (has user field)
                has_user = not self._is_cron_time_field(parts[5])

                if has_user and len(parts) >= 7:
                    job = {
                        "minute": parts[0],
                        "hour": parts[1],
                        "day": parts[2],
                        "month": parts[3],
                        "weekday": parts[4],
                        "user": parts[5],
                        "command": parts[6],
                        "schedule": self._describe_cron_schedule(parts[0:5]),
                    }
                else:
                    job = {
                        "minute": parts[0],
                        "hour": parts[1],
                        "day": parts[2],
                        "month": parts[3],
                        "weekday": parts[4],
                        "command": " ".join(parts[5:]),
                        "schedule": self._describe_cron_schedule(parts[0:5]),
                    }

                jobs.append(job)

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Best-effort crontab parse; a malformed guest file must not abort the scan.
            self.logger.debug(f"Failed to parse crontab {filepath}: {e}")

        return jobs

    def _is_cron_time_field(self, field: str) -> bool:
        """Check if a field looks like a cron time specification."""
        # Cron time fields contain digits, *, /, -, or ,
        return bool(re.match(r"^[\d*/,-]+$", field))

    # Each branch below is a distinct, mutually-exclusive named schedule pattern
    # (hourly/daily/weekly/monthly); expressing them as early returns is clearer
    # than nesting into a single generic description.
    # pylint: disable-next=too-many-return-statements
    def _describe_cron_schedule(self, fields: list[str]) -> str:
        """Convert cron time fields to human-readable description."""
        minute, hour, day, month, weekday = fields

        # Common patterns
        if all(f == "*" for f in fields):
            return "Every minute"
        if minute == "0" and hour == "*" and day == "*" and month == "*" and weekday == "*":
            return "Every hour"
        if minute == "0" and hour == "0" and day == "*" and month == "*" and weekday == "*":
            return "Daily at midnight"
        if minute == "0" and hour != "*" and day == "*" and month == "*" and weekday == "*":
            return f"Daily at {hour}:00"
        if minute == "0" and hour == "0" and day == "1" and month == "*" and weekday == "*":
            return "Monthly on the 1st"
        if minute == "0" and hour == "0" and day == "*" and month == "*" and weekday == "0":
            return "Weekly on Sunday"
        if minute == "0" and hour == "0" and day == "*" and month == "*" and weekday == "1":
            return "Weekly on Monday"

        # Generic description
        parts = []
        if minute != "*":
            parts.append(f"minute={minute}")
        if hour != "*":
            parts.append(f"hour={hour}")
        if day != "*":
            parts.append(f"day={day}")
        if month != "*":
            parts.append(f"month={month}")
        if weekday != "*":
            parts.append(f"weekday={weekday}")

        return " ".join(parts) if parts else "Custom schedule"

    def _parse_systemd_timers(self) -> list[dict[str, Any]]:
        """Parse systemd timer units."""
        timers = []

        # Directory-exists guard + file-type filter + per-line field parse naturally
        # nests one level deeper than the default limit; splitting further would
        # obscure the straightforward top-to-bottom timer-file parse.
        try:  # pylint: disable=too-many-nested-blocks
            if self.file_ops.is_dir("/etc/systemd/system"):
                files = self.file_ops.ls("/etc/systemd/system")
                for file in files:
                    if file.endswith(".timer"):
                        timer_path = f"/etc/systemd/system/{file}"
                        content = self.file_ops.cat(timer_path)

                        timer = {
                            "name": file,
                            "unit": file.replace(".timer", ".service"),
                            "on_calendar": None,
                            "on_boot_sec": None,
                            "on_unit_active_sec": None,
                        }

                        # Parse timer configuration
                        for line in content.splitlines():
                            line = line.strip()
                            if line.startswith("OnCalendar="):
                                timer["on_calendar"] = line.split("=", 1)[1]
                            elif line.startswith("OnBootSec="):
                                timer["on_boot_sec"] = line.split("=", 1)[1]
                            elif line.startswith("OnUnitActiveSec="):
                                timer["on_unit_active_sec"] = line.split("=", 1)[1]

                        timers.append(timer)

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Best-effort systemd timer parse; a malformed guest file must not abort the scan.
            self.logger.debug(f"Failed to parse systemd timers: {e}")

        return timers

    def _parse_anacrontab(self, filepath: str) -> list[dict[str, Any]]:
        """Parse anacrontab file."""
        jobs = []

        try:
            content = self.file_ops.cat(filepath)

            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # anacron format: period delay job-identifier command
                parts = line.split(None, 3)
                if len(parts) >= 4:
                    job = {
                        "period": parts[0],
                        "delay": parts[1],
                        "identifier": parts[2],
                        "command": parts[3],
                    }
                    jobs.append(job)

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Best-effort anacrontab parse; a malformed guest file must not abort the scan.
            self.logger.debug(f"Failed to parse anacrontab: {e}")

        return jobs

    def _analyze_windows_tasks(self) -> dict[str, Any]:
        """
        Analyze Windows Task Scheduler tasks.

        Windows scheduled tasks are stored in:
        - C:\\Windows\\System32\\Tasks\\* (XML files)
        - Registry: HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Schedule\\TaskCache

        Returns:
            Windows scheduled tasks configuration
        """
        config = {
            "note": "Windows Task Scheduler requires XML parsing and registry access",
            "tasks": [],
            "total_count": 0,
        }

        # Would need XML parsing for full implementation
        # Task XML files are in C:\Windows\System32\Tasks\
        try:
            if self.file_ops.is_dir("/Windows/System32/Tasks"):
                tasks = self._scan_windows_tasks("/Windows/System32/Tasks")
                config["tasks"] = tasks
                config["total_count"] = len(tasks)
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Best-effort Windows task scan; guest FS quirks must not abort the analysis.
            self.logger.debug(f"Failed to scan Windows tasks: {e}")

        return config

    def _scan_windows_tasks(self, base_path: str) -> list[dict[str, Any]]:
        """Scan Windows Task Scheduler directory."""
        tasks = []

        try:
            files = self.file_ops.ls(base_path)
            for file in files:
                file_path = f"{base_path}/{file}"
                if self.file_ops.is_dir(file_path):
                    # Recurse into subdirectories
                    tasks.extend(self._scan_windows_tasks(file_path))
                elif self.file_ops.is_file(file_path):
                    # Basic task info (full parsing would require XML)
                    task = {
                        "name": file,
                        "path": file_path.replace("/Windows/System32/Tasks/", ""),
                        "note": "Full details require XML parsing",
                    }
                    tasks.append(task)

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Best-effort recursive scan; guest FS quirks must not abort the analysis.
            self.logger.debug(f"Failed to scan {base_path}: {e}")

        return tasks

    def get_task_count(self, config: dict[str, Any]) -> int:
        """Get total count of scheduled tasks."""
        return config.get("total_count", 0)

    def find_daily_tasks(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        """Find tasks that run daily."""
        daily_tasks = []

        # Check system cron
        for job in config.get("system_cron", []):
            if "Daily" in job.get("schedule", ""):
                daily_tasks.append(job)

        # Check user cron
        for job in config.get("user_cron", []):
            if "Daily" in job.get("schedule", ""):
                daily_tasks.append(job)

        # Check cron.d
        for job in config.get("cron_d", []):
            if "Daily" in job.get("schedule", ""):
                daily_tasks.append(job)

        return daily_tasks

    def find_tasks_by_user(self, config: dict[str, Any], user: str) -> list[dict[str, Any]]:
        """Find tasks scheduled for a specific user."""
        user_tasks = []

        # System cron jobs with user field
        for job in config.get("system_cron", []):
            if job.get("user") == user:
                user_tasks.append(job)

        # Cron.d jobs with user field
        for job in config.get("cron_d", []):
            if job.get("user") == user:
                user_tasks.append(job)

        return user_tasks
