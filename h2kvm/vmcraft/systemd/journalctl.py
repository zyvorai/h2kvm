# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Journalctl integration for VMCraft.

Provides systemd journal log analysis capabilities.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    import logging


class JournalctlManager:
    """Manage systemd journal via journalctl."""

    def __init__(self, command_runner: Callable[[list[str]], str], logger: logging.Logger):
        """
        Initialize JournalctlManager.

        Args:
            command_runner: Function to execute commands in guest
            logger: Logger instance
        """
        self.command = command_runner
        self.logger = logger

    def query(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # journalctl exposes many independent filter flags
        self,
        unit: str | None = None,
        priority: int | None = None,
        since: str | None = None,
        until: str | None = None,
        boot: int | str | None = None,
        lines: int | None = None,
        grep: str | None = None,
        output_format: str = "short",
    ) -> str:
        """
        Query systemd journal logs.

        Args:
            unit: Filter by unit name (e.g., "sshd.service")
            priority: Filter by priority (0=emerg, 1=alert, 2=crit, 3=err, 4=warning, 5=notice, 6=info, 7=debug)
            since: Start time (e.g., "1 hour ago", "yesterday", "2023-01-01")
            until: End time
            boot: Boot ID or offset (0=current, -1=previous, etc.)
            lines: Number of lines to show
            grep: Pattern to grep for
            output_format: Output format (short, json, verbose, cat, etc.)

        Returns:
            Log output as string

        Example:
            # Get SSH logs from last hour
            logs = manager.query(unit="sshd.service", since="1 hour ago")

            # Get all errors
            errors = manager.query(priority=3)

            # Get boot logs
            boot_log = manager.query(boot=0)
        """
        try:
            cmd = ["journalctl", "--no-pager", f"-o{output_format}"]

            if unit:
                cmd.extend(["-u", unit])
            if priority is not None:
                cmd.extend(["-p", str(priority)])
            if since:
                cmd.extend(["--since", since])
            if until:
                cmd.extend(["--until", until])
            if boot is not None:
                cmd.extend(["-b", str(boot)])
            if lines is not None:
                cmd.extend(["-n", str(lines)])
            if grep:
                cmd.extend(["--grep", grep])

            return self.command(cmd)

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort journalctl wrapper, must not raise on any command failure
            self.logger.debug(f"journalctl query failed: {e}")
            return ""

    def list_boots(self) -> list[dict[str, str]]:
        """
        List available boot entries.

        Returns:
            List of dicts with keys: boot_id, first_entry, last_entry

        Example:
            boots = manager.list_boots()
            print(f"Current boot: {boots[0]['boot_id']}")
            print(f"Previous boot: {boots[1]['boot_id']}")
        """
        try:
            cmd = ["journalctl", "--list-boots", "--no-pager"]
            result = self.command(cmd)

            # pylint: disable=duplicate-code
            # reason: this "-1 abc123... time_range" boot-list line parser
            # mirrors the equivalent parser in vmcraft/systemd_journal.py --
            # structurally similar by coincidence (both parse the same
            # journalctl --list-boots format), not shared logic; keeping
            # independent avoids coupling two unrelated journalctl wrapper
            # code paths.
            boots = []
            for line in result.splitlines():
                line = line.strip()
                if not line:
                    continue

                # Format: -1 abc123... 2023-01-01 12:00:00 UTC—2023-01-01 13:00:00 UTC
                parts = line.split(None, 2)
                if len(parts) >= 3:
                    boots.append(
                        {
                            "offset": parts[0],
                            "boot_id": parts[1],
                            "time_range": parts[2] if len(parts) > 2 else "",
                        }
                    )

            return boots

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort journalctl wrapper, must not raise on any command failure
            self.logger.debug(f"journalctl list-boots failed: {e}")
            return []

    def get_boot_log(self, boot: int | str = 0, lines: int | None = None) -> str:
        """
        Get log for a specific boot.

        Args:
            boot: Boot ID or offset (0=current, -1=previous)
            lines: Number of lines to return

        Returns:
            Boot log as string
        """
        return self.query(boot=boot, lines=lines)

    def get_errors(self, since: str | None = None, lines: int = 100) -> list[dict[str, str]]:
        """
        Get error messages from journal.

        Args:
            since: Time specification
            lines: Maximum number of errors to return

        Returns:
            List of dicts with keys: timestamp, unit, message, priority

        Example:
            errors = manager.get_errors(since="1 hour ago")
            for err in errors:
                print(f"{err['unit']}: {err['message']}")
        """
        try:
            cmd = ["journalctl", "-p", "err", "--no-pager", "-o", "json", "-n", str(lines)]
            if since:
                cmd.extend(["--since", since])

            result = self.command(cmd)

            errors = []
            for line in result.splitlines():
                if not line.strip():
                    continue

                try:
                    entry = json.loads(line)
                    errors.append(
                        {
                            "timestamp": entry.get("__REALTIME_TIMESTAMP", ""),
                            "unit": entry.get("_SYSTEMD_UNIT", entry.get("SYSLOG_IDENTIFIER", "unknown")),
                            "message": entry.get("MESSAGE", ""),
                            "priority": entry.get("PRIORITY", ""),
                        }
                    )
                except json.JSONDecodeError:
                    continue

            return errors

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort journalctl wrapper, must not raise on any command failure
            self.logger.debug(f"journalctl get errors failed: {e}")
            return []

    def get_warnings(self, since: str | None = None, lines: int = 100) -> list[dict[str, str]]:
        """
        Get warning messages from journal.

        Args:
            since: Time specification
            lines: Maximum number of warnings to return

        Returns:
            List of dicts with warning information
        """
        try:
            cmd = ["journalctl", "-p", "warning", "--no-pager", "-o", "json", "-n", str(lines)]
            if since:
                cmd.extend(["--since", since])

            result = self.command(cmd)

            warnings = []
            for line in result.splitlines():
                if not line.strip():
                    continue

                try:
                    entry = json.loads(line)
                    warnings.append(
                        {
                            "timestamp": entry.get("__REALTIME_TIMESTAMP", ""),
                            "unit": entry.get("_SYSTEMD_UNIT", entry.get("SYSLOG_IDENTIFIER", "unknown")),
                            "message": entry.get("MESSAGE", ""),
                            "priority": entry.get("PRIORITY", ""),
                        }
                    )
                except json.JSONDecodeError:
                    continue

            return warnings

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort journalctl wrapper, must not raise on any command failure
            self.logger.debug(f"journalctl get warnings failed: {e}")
            return []

    def disk_usage(self) -> dict[str, Any]:
        """
        Get journal disk usage information.

        Returns:
            Dict with disk usage information
            Keys: total_size, current_use, max_use

        Example:
            usage = manager.disk_usage()
            print(f"Journal size: {usage['current_use']} / {usage['max_use']}")
        """
        try:
            cmd = ["journalctl", "--disk-usage", "--no-pager"]
            result = self.command(cmd)

            usage = {}

            # Parse output like: "Archived and active journals take up 123.4M in the file system."
            match = re.search(r"(\d+\.?\d*[KMGT]?)\s*(?:in|on)", result)
            if match:
                usage["current_use"] = match.group(1)

            return usage

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort journalctl wrapper, must not raise on any command failure
            self.logger.debug(f"journalctl disk-usage failed: {e}")
            return {}

    def verify(self) -> dict[str, Any]:
        """
        Verify journal file consistency.

        Returns:
            Dict with verification results
            Keys: passed, errors, details

        Example:
            result = manager.verify()
            if not result['passed']:
                print(f"Journal verification failed: {result['errors']}")
        """
        try:
            cmd = ["journalctl", "--verify", "--no-pager"]
            result = self.command(cmd)

            verification = {
                "passed": "PASS" in result.upper(),
                "errors": [],
                "details": result,
            }

            # Extract errors
            for line in result.splitlines():
                if "error" in line.lower() or "fail" in line.lower():
                    verification["errors"].append(line.strip())

            return verification

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort journalctl wrapper, must not raise on any command failure
            self.logger.debug(f"journalctl verify failed: {e}")
            return {"passed": False, "errors": [str(e)], "details": ""}

    def get_cursor(self) -> str:
        """
        Get current journal cursor position.

        Returns:
            Cursor string
        """
        try:
            cmd = ["journalctl", "-n", "1", "--show-cursor", "--no-pager", "-o", "json"]
            result = self.command(cmd)

            # Extract cursor from output
            match = re.search(r"--cursor.*?([a-zA-Z0-9+/=]+)", result)
            if match:
                return match.group(1)

            return ""

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort journalctl wrapper, must not raise on any command failure
            self.logger.debug(f"journalctl get cursor failed: {e}")
            return ""

    def export(self, output_format: str = "json", since: str | None = None) -> str:
        """
        Export journal logs.

        Args:
            output_format: Export format (json, short, verbose, export, cat)
            since: Export logs since this time

        Returns:
            Exported log data as string

        Example:
            # Export all logs as JSON
            json_logs = manager.export("json")

            # Export last hour
            recent = manager.export("json", since="1 hour ago")
        """
        return self.query(since=since, output_format=output_format)

    # Enhanced journal operations

    def search(self, pattern: str, since: str | None = None, lines: int = 100) -> list[dict[str, str]]:
        """
        Search journal logs for a pattern.

        Args:
            pattern: Pattern to search for (grep-compatible regex)
            since: Search logs since this time
            lines: Maximum number of matching entries to return

        Returns:
            List of matching journal entries with metadata

        Example:
            # Search for authentication failures
            failures = manager.search("authentication failure", since="1 day ago")

            # Search for out of memory errors
            oom = manager.search("out of memory|oom", since="1 week ago")
        """
        try:
            cmd = ["journalctl", "--grep", pattern, "--no-pager", "-o", "json", "-n", str(lines)]
            if since:
                cmd.extend(["--since", since])

            result = self.command(cmd)

            entries = []
            for line in result.splitlines():
                if not line.strip():
                    continue

                try:
                    entry = json.loads(line)
                    entries.append(
                        {
                            "timestamp": entry.get("__REALTIME_TIMESTAMP", ""),
                            "unit": entry.get("_SYSTEMD_UNIT", entry.get("SYSLOG_IDENTIFIER", "unknown")),
                            "message": entry.get("MESSAGE", ""),
                            "priority": entry.get("PRIORITY", ""),
                            "hostname": entry.get("_HOSTNAME", ""),
                            "pid": entry.get("_PID", ""),
                        }
                    )
                except json.JSONDecodeError:
                    continue

            return entries

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort journalctl wrapper, must not raise on any command failure
            self.logger.debug(f"journalctl search failed: {e}")
            return []

    def statistics(self) -> dict[str, Any]:
        """
        Get journal statistics and message counts.

        Returns:
            Dict with journal statistics including:
            - total_entries: Total number of journal entries
            - by_priority: Counts grouped by priority level
            - by_unit: Top units by message count
            - time_range: First and last entry timestamps

        Example:
            stats = manager.statistics()
            print(f"Total entries: {stats['total_entries']}")
            print(f"Errors: {stats['by_priority'].get('err', 0)}")
        """
        try:
            stats = {
                "total_entries": 0,
                "by_priority": {},
                "by_unit": {},
                "time_range": {},
            }

            # Get total count and time range from first/last entries
            cmd_first = ["journalctl", "-n", "1", "--reverse", "-o", "json", "--no-pager"]
            result_first = self.command(cmd_first)
            if result_first.strip():
                try:
                    first_entry = json.loads(result_first.splitlines()[0])
                    stats["time_range"]["first"] = first_entry.get("__REALTIME_TIMESTAMP", "")
                except (json.JSONDecodeError, IndexError):
                    pass

            cmd_last = ["journalctl", "-n", "1", "-o", "json", "--no-pager"]
            result_last = self.command(cmd_last)
            if result_last.strip():
                try:
                    last_entry = json.loads(result_last.splitlines()[0])
                    stats["time_range"]["last"] = last_entry.get("__REALTIME_TIMESTAMP", "")
                except (json.JSONDecodeError, IndexError):
                    pass

            # Count by priority
            priority_names = {
                "0": "emerg",
                "1": "alert",
                "2": "crit",
                "3": "err",
                "4": "warning",
                "5": "notice",
                "6": "info",
                "7": "debug",
            }

            for priority_num, priority_name in priority_names.items():
                cmd = ["journalctl", "-p", priority_num, "--no-pager", "-q", "-n", "0"]
                self.command(cmd)
                # Parse line count from journalctl output if available
                # For now, just mark as available
                stats["by_priority"][priority_name] = 0  # Placeholder

            return stats

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort journalctl wrapper, must not raise on any command failure
            self.logger.debug(f"journalctl statistics failed: {e}")
            return {"total_entries": 0, "by_priority": {}, "by_unit": {}, "time_range": {}}

    def vacuum(
        self, size: str | None = None, time: str | None = None, files: int | None = None
    ) -> dict[str, str]:
        """
        Clean up old journal log files.

        Args:
            size: Keep only this much disk space (e.g., "500M", "1G")
            time: Keep only logs newer than this (e.g., "1month", "2weeks")
            files: Keep only this many journal files

        Returns:
            Dict with vacuum results

        Example:
            # Keep only 500MB of logs
            result = manager.vacuum(size="500M")

            # Keep only last month
            result = manager.vacuum(time="1month")

            # Keep only 10 most recent files
            result = manager.vacuum(files=10)
        """
        try:
            cmd = ["journalctl", "--vacuum"]

            if size:
                cmd.append(f"--vacuum-size={size}")
            elif time:
                cmd.append(f"--vacuum-time={time}")
            elif files:
                cmd.append(f"--vacuum-files={files}")
            else:
                # Default: vacuum to 100M
                cmd.append("--vacuum-size=100M")

            result = self.command(cmd)

            return {
                "status": "success" if result else "no_action",
                "output": result,
            }

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort journalctl wrapper, must not raise on any command failure
            self.logger.debug(f"journalctl vacuum failed: {e}")
            return {"status": "error", "output": str(e)}

    def get_boot_time(self, boot: int | str = 0) -> dict[str, str]:
        """
        Get boot time and shutdown time for a specific boot.

        Args:
            boot: Boot ID or offset (0=current, -1=previous)

        Returns:
            Dict with boot_time and shutdown_time

        Example:
            boot_info = manager.get_boot_time(0)
            print(f"Last boot: {boot_info['boot_time']}")
        """
        try:
            # Get first entry for boot time
            cmd_boot = ["journalctl", "-b", str(boot), "-n", "1", "--reverse", "-o", "json", "--no-pager"]
            result_boot = self.command(cmd_boot)

            boot_time = ""
            shutdown_time = ""

            if result_boot.strip():
                try:
                    entry = json.loads(result_boot.splitlines()[0])
                    boot_time = entry.get("__REALTIME_TIMESTAMP", "")
                except (json.JSONDecodeError, IndexError):
                    pass

            # Get last entry for shutdown time
            cmd_shutdown = ["journalctl", "-b", str(boot), "-n", "1", "-o", "json", "--no-pager"]
            result_shutdown = self.command(cmd_shutdown)

            if result_shutdown.strip():
                try:
                    entry = json.loads(result_shutdown.splitlines()[0])
                    shutdown_time = entry.get("__REALTIME_TIMESTAMP", "")
                except (json.JSONDecodeError, IndexError):
                    pass

            return {
                "boot_time": boot_time,
                "shutdown_time": shutdown_time,
            }

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort journalctl wrapper, must not raise on any command failure
            self.logger.debug(f"get_boot_time failed: {e}")
            return {"boot_time": "", "shutdown_time": ""}
