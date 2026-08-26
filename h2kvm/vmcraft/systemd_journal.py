# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd journal integration for VMCraft.

This module provides APIs for accessing and analyzing systemd journal logs
within guest VMs. Useful for debugging boot issues, analyzing service failures,
and investigating system events during migration.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ._utils import run_sudo


class SystemdJournalManager:
    """
    Systemd journal log access and analysis.

    Provides APIs for querying journal entries, filtering by service/priority,
    analyzing boot logs, and managing journal disk usage.
    """

    def __init__(self, logger: logging.Logger, guest_root: str):
        """
        Initialize SystemdJournalManager.

        Args:
            logger: Logger instance for output
            guest_root: Path to guest filesystem root
        """
        self.logger = logger
        self.guest_root = Path(guest_root)
        self._journalctl_available: bool | None = None

    def is_journalctl_available(self) -> bool:
        """
        Check if journalctl is available in guest.

        Returns:
            True if journalctl is present, False otherwise
        """
        if self._journalctl_available is not None:
            return self._journalctl_available

        # Check for journalctl binary
        journalctl_paths = [
            self.guest_root / "usr/bin/journalctl",
            self.guest_root / "bin/journalctl",
        ]

        self._journalctl_available = any(p.exists() for p in journalctl_paths)

        if self._journalctl_available:
            self.logger.debug("journalctl detected in guest")
        else:
            self.logger.debug("journalctl not found in guest")

        return self._journalctl_available

    def _run_journalctl(self, args: list[str]) -> dict[str, Any]:
        """
        Run journalctl command in guest context.

        Args:
            args: journalctl arguments

        Returns:
            Audit dict with command results
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "stdout": "", "stderr": ""}

        if not self.is_journalctl_available():
            audit["error"] = "journalctl_not_available"
            return audit

        audit["attempted"] = True

        # pylint: disable=duplicate-code
        # reason: this chroot-exec + audit-dict try/except shape mirrors
        # the equivalent block in vmcraft/systemd_mgr.py (systemctl runner)
        # -- structurally similar by coincidence (both wrap a chroot/nspawn
        # command with the same audit dict), not shared logic; keeping
        # independent avoids coupling unrelated journalctl/systemctl
        # execution code paths.
        try:
            # Use chroot to access guest journal
            cmd = ["chroot", str(self.guest_root), "journalctl", *args]

            result = run_sudo(self.logger, cmd, check=True, capture=True, failure_log_level=logging.DEBUG)

            audit["ok"] = True
            audit["stdout"] = result.stdout
            audit["stderr"] = result.stderr
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort journal operation; must return an audit dict, not raise
            audit["error"] = str(e)
            if hasattr(e, "stderr"):
                audit["stderr"] = e.stderr
            return audit

    # ==================================================================================
    # Journal Query Methods (5 methods)
    # ==================================================================================

    def get(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # each param maps 1:1 to a journalctl filter flag
        self,
        lines: int | None = None,
        unit: str | None = None,
        priority: str | None = None,
        since: str | None = None,
        until: str | None = None,
        grep: str | None = None,
    ) -> dict[str, Any]:
        """
        Get journal entries with filtering.

        Args:
            lines: Number of lines to return (default: all)
            unit: Filter by systemd unit (e.g., "sshd.service")
            priority: Filter by priority (emerg, alert, crit, err, warning, notice, info, debug)
            since: Start time (e.g., "2024-01-01", "yesterday", "-1h")
            until: End time
            grep: Filter output by pattern

        Returns:
            Dict with journal entries

        Example:
            >>> # Get last 100 log entries
            >>> logs = g.journal_get(lines=100)
            >>>
            >>> # Get SSH service logs from last hour
            >>> logs = g.journal_get(unit="sshd.service", since="-1h")
            >>>
            >>> # Get critical errors
            >>> logs = g.journal_get(priority="crit")
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "entries": [], "count": 0}

        if not self.is_journalctl_available():
            audit["error"] = "journalctl_not_available"
            return audit

        audit["attempted"] = True

        try:
            args = ["--no-pager", "--output=json"]

            if lines:
                args.extend(["-n", str(lines)])

            if unit:
                args.extend(["-u", unit])

            if priority:
                args.extend(["-p", priority])

            if since:
                args.extend(["--since", since])

            if until:
                args.extend(["--until", until])

            if grep:
                args.extend(["-g", grep])

            result = self._run_journalctl(args)

            if not result["ok"]:
                audit["error"] = result.get("error")
                return audit

            # Parse JSON output (each line is a JSON object)
            entries = []
            for line in result["stdout"].strip().split("\n"):
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

            audit["ok"] = True
            audit["entries"] = entries
            audit["count"] = len(entries)
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort journal operation; must return an audit dict, not raise
            audit["error"] = str(e)
            self.logger.debug(f"Failed to get journal entries: {e}")
            return audit

    def get_service(self, service: str, lines: int = 100) -> dict[str, Any]:
        """
        Get journal entries for specific service.

        Args:
            service: Service name (e.g., "sshd", "NetworkManager")
            lines: Number of lines to return

        Returns:
            Dict with service log entries

        Example:
            >>> # Debug SSH service issues
            >>> logs = g.journal_get_service("sshd", lines=50)
            >>> for entry in logs["entries"]:
            ...     print(entry.get("MESSAGE"))
        """
        # Ensure .service suffix
        if not service.endswith(".service"):
            service = f"{service}.service"

        return self.get(unit=service, lines=lines)

    def get_since_boot(self, boot_offset: int = 0) -> dict[str, Any]:
        """
        Get journal entries since specified boot.

        Args:
            boot_offset: Boot offset (0 = current, -1 = previous, etc.)

        Returns:
            Dict with boot log entries

        Example:
            >>> # Get logs from current boot
            >>> logs = g.journal_get_since_boot()
            >>>
            >>> # Get logs from previous boot
            >>> logs = g.journal_get_since_boot(boot_offset=-1)
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "entries": [], "count": 0}

        if not self.is_journalctl_available():
            audit["error"] = "journalctl_not_available"
            return audit

        audit["attempted"] = True

        try:
            args = ["--no-pager", "--output=json", "-b", str(boot_offset)]

            result = self._run_journalctl(args)

            if not result["ok"]:
                audit["error"] = result.get("error")
                return audit

            # Parse JSON output
            entries = []
            for line in result["stdout"].strip().split("\n"):
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

            audit["ok"] = True
            audit["entries"] = entries
            audit["count"] = len(entries)
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort journal operation; must return an audit dict, not raise
            audit["error"] = str(e)
            self.logger.debug(f"Failed to get boot logs: {e}")
            return audit

    def get_priority(self, priority: str, lines: int = 100) -> dict[str, Any]:
        """
        Get journal entries by priority level.

        Args:
            priority: Priority level (emerg, alert, crit, err, warning, notice, info, debug)
            lines: Number of lines to return

        Returns:
            Dict with filtered entries

        Example:
            >>> # Get all errors and critical messages
            >>> errors = g.journal_get_priority("err", lines=50)
        """
        return self.get(priority=priority, lines=lines)

    def get_tail(self, lines: int = 100) -> dict[str, Any]:
        """
        Get last N journal entries.

        Args:
            lines: Number of lines to return

        Returns:
            Dict with recent entries

        Example:
            >>> # Get last 50 log entries
            >>> recent = g.journal_get_tail(lines=50)
        """
        return self.get(lines=lines)

    # ==================================================================================
    # Boot Analysis Methods (2 methods)
    # ==================================================================================

    def list_boots(self) -> dict[str, Any]:
        """
        List available boot sessions.

        Returns:
            Dict with list of boots

        Example:
            >>> boots = g.journal_list_boots()
            >>> for boot in boots["boots"]:
            ...     print(f"Boot ID: {boot['boot_id']}, First: {boot['first_entry']}")
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "boots": [], "count": 0}

        if not self.is_journalctl_available():
            audit["error"] = "journalctl_not_available"
            return audit

        audit["attempted"] = True

        try:
            result = self._run_journalctl(["--list-boots", "--no-pager"])

            if not result["ok"]:
                audit["error"] = result.get("error")
                return audit

            # pylint: disable=duplicate-code
            # reason: this "-1 abc123... time_range" boot-list line parser
            # mirrors the equivalent parser in
            # vmcraft/systemd/journalctl.py -- structurally similar by
            # coincidence (both parse the same journalctl --list-boots
            # format), not shared logic; keeping independent avoids
            # coupling two unrelated journalctl wrapper code paths.
            boots = []
            for line in result["stdout"].strip().split("\n"):
                if line:
                    # Parse boot list output
                    # Format: -1 abc123... Mon 2024-01-01 10:00:00 UTC—Mon 2024-01-01 18:00:00 UTC
                    parts = line.split(None, 2)
                    if len(parts) >= 3:
                        boots.append(
                            {
                                "offset": parts[0],
                                "boot_id": parts[1],
                                "time_range": parts[2] if len(parts) > 2 else "",
                            }
                        )

            audit["ok"] = True
            audit["boots"] = boots
            audit["count"] = len(boots)
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort journal operation; must return an audit dict, not raise
            audit["error"] = str(e)
            self.logger.debug(f"Failed to list boots: {e}")
            return audit

    def get_boot_id(self) -> str | None:
        """
        Get current boot ID.

        Returns:
            Boot ID string or None if unavailable

        Example:
            >>> boot_id = g.journal_get_boot_id()
            >>> print(f"Current boot: {boot_id}")
        """
        try:
            result = self._run_journalctl(["-b", "0", "--output=json", "-n", "1"])

            if not result["ok"]:
                return None

            # Parse first entry to get boot ID
            for line in result["stdout"].strip().split("\n"):
                if line:
                    try:
                        entry = json.loads(line)
                        return entry.get("_BOOT_ID")
                    except json.JSONDecodeError:
                        continue

            return None

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort journal operation; must return an audit dict, not raise
            self.logger.debug(f"Failed to get boot ID: {e}")
            return None

    # ==================================================================================
    # Journal Management Methods (3 methods)
    # ==================================================================================

    def get_disk_usage(self) -> dict[str, Any]:
        """
        Get journal disk usage statistics.

        Returns:
            Dict with disk usage information

        Example:
            >>> usage = g.journal_get_disk_usage()
            >>> print(f"Journal size: {usage['size']}")
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "size": None, "usage": None}

        if not self.is_journalctl_available():
            audit["error"] = "journalctl_not_available"
            return audit

        audit["attempted"] = True

        try:
            result = self._run_journalctl(["--disk-usage", "--no-pager"])

            if not result["ok"]:
                audit["error"] = result.get("error")
                return audit

            # Parse disk usage output
            # Format: "Archived and active journals take up 1.2G in the file system."
            output = result["stdout"].strip()
            audit["ok"] = True
            audit["usage"] = output

            # Try to extract size
            if "take up" in output:
                parts = output.split("take up")
                if len(parts) > 1:
                    size_part = parts[1].split("in")[0].strip()
                    audit["size"] = size_part

            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort journal operation; must return an audit dict, not raise
            audit["error"] = str(e)
            self.logger.debug(f"Failed to get disk usage: {e}")
            return audit

    def vacuum(
        self, size: str | None = None, time: str | None = None, files: int | None = None
    ) -> dict[str, Any]:
        """
        Clean up old journal entries.

        Args:
            size: Maximum disk usage (e.g., "100M", "1G")
            time: Maximum age (e.g., "1week", "1month")
            files: Maximum number of journal files to keep

        Returns:
            Audit dict with cleanup results

        Example:
            >>> # Keep only last 100MB of logs
            >>> g.journal_vacuum(size="100M")
            >>>
            >>> # Keep only last week of logs
            >>> g.journal_vacuum(time="1week")
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None}

        if not self.is_journalctl_available():
            audit["error"] = "journalctl_not_available"
            return audit

        if not size and not time and not files:
            audit["error"] = "size, time, or files parameter required"
            return audit

        audit["attempted"] = True

        try:
            args = ["--vacuum-size=" + size] if size else []
            if time:
                args.append("--vacuum-time=" + time)
            if files:
                args.append("--vacuum-files=" + str(files))

            result = self._run_journalctl(args)

            if not result["ok"]:
                audit["error"] = result.get("error")
                return audit

            audit["ok"] = True
            self.logger.info(f"Journal vacuum completed: {result['stdout']}")
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort journal operation; must return an audit dict, not raise
            audit["error"] = str(e)
            self.logger.warning(f"Failed to vacuum journal: {e}")
            return audit

    def verify(self) -> dict[str, Any]:
        """
        Verify journal file consistency.

        Returns:
            Audit dict with verification results

        Example:
            >>> result = g.journal_verify()
            >>> if result["ok"]:
            ...     print("Journal is consistent")
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "verified": False}

        if not self.is_journalctl_available():
            audit["error"] = "journalctl_not_available"
            return audit

        audit["attempted"] = True

        try:
            result = self._run_journalctl(["--verify", "--no-pager"])

            # journalctl --verify returns non-zero on corruption
            # but we catch that in _run_journalctl
            audit["ok"] = result["ok"]
            audit["verified"] = result["ok"]

            if not result["ok"]:
                audit["error"] = "journal_verification_failed"

            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort journal operation; must return an audit dict, not raise
            audit["error"] = str(e)
            audit["verified"] = False
            self.logger.warning(f"Journal verification failed: {e}")
            return audit
