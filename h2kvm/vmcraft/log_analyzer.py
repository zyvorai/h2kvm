# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/log_analyzer.py
"""
System log analysis for Linux systems.

Provides comprehensive log file analysis:
- System logs (syslog, messages, dmesg)
- Authentication logs (auth.log, secure)
- Application logs (apache, nginx, mysql)
- Journal logs (systemd journal)
- Log pattern matching and error detection
- Security event detection

Features:
- Parse various log formats
- Identify errors and warnings
- Security event analysis (failed logins, sudo usage)
- Application crash detection
- Log statistics and summaries
- Recent events extraction
"""

from __future__ import annotations

import re
from typing import Any

from .base_analyzer import BaseAnalyzer


class LogAnalyzer(BaseAnalyzer):
    """
    System log analyzer.

    Analyzes system and application logs on Linux systems.
    """

    def analyze_logs(self) -> dict[str, Any]:
        """
        Analyze system logs comprehensively.

        Returns:
            Log analysis summary
        """
        analysis: dict[str, Any] = {
            "system_logs": {},
            "auth_logs": {},
            "application_logs": {},
            "errors": [],
            "warnings": [],
            "security_events": [],
            "statistics": {},
        }

        # Analyze system logs
        analysis["system_logs"] = self._analyze_system_logs()

        # Analyze authentication logs
        analysis["auth_logs"] = self._analyze_auth_logs()

        # Analyze application logs
        analysis["application_logs"] = self._analyze_application_logs()

        # Extract errors and warnings
        analysis["errors"] = self._find_errors()
        analysis["warnings"] = self._find_warnings()

        # Security event analysis
        analysis["security_events"] = self._analyze_security_events()

        # Statistics
        analysis["statistics"] = self._calculate_statistics(analysis)

        return analysis

    def _analyze_system_logs(self) -> dict[str, Any]:
        """Analyze system logs (syslog, messages, dmesg)."""
        logs: dict[str, Any] = {
            "syslog": None,
            "messages": None,
            "dmesg": None,
            "kern": None,
        }

        # Check various system log locations
        log_paths = {
            "syslog": ["/var/log/syslog", "/var/log/syslog.1"],
            "messages": ["/var/log/messages", "/var/log/messages.1"],
            "dmesg": ["/var/log/dmesg"],
            "kern": ["/var/log/kern.log", "/var/log/kern.log.1"],
        }

        for log_type, paths in log_paths.items():
            for path in paths:
                if self.file_ops.exists(path):
                    logs[log_type] = self._parse_log_file(path, limit=100)
                    break

        return logs

    def _analyze_auth_logs(self) -> dict[str, Any]:
        """Analyze authentication logs."""
        logs: dict[str, Any] = {
            "auth_log": None,
            "secure": None,
            "failed_logins": [],
            "successful_logins": [],
            "sudo_usage": [],
        }

        # Check auth log locations (Debian/Ubuntu)
        if self.file_ops.exists("/var/log/auth.log"):
            logs["auth_log"] = self._parse_log_file("/var/log/auth.log", limit=100)
            logs["failed_logins"] = self._find_failed_logins("/var/log/auth.log")
            logs["successful_logins"] = self._find_successful_logins("/var/log/auth.log")
            logs["sudo_usage"] = self._find_sudo_usage("/var/log/auth.log")
        # Check secure log (Red Hat/CentOS/Fedora)
        elif self.file_ops.exists("/var/log/secure"):
            logs["secure"] = self._parse_log_file("/var/log/secure", limit=100)
            logs["failed_logins"] = self._find_failed_logins("/var/log/secure")
            logs["successful_logins"] = self._find_successful_logins("/var/log/secure")
            logs["sudo_usage"] = self._find_sudo_usage("/var/log/secure")

        return logs

    def _analyze_application_logs(self) -> dict[str, Any]:
        """Analyze common application logs."""
        logs: dict[str, Any] = {
            "apache": [],
            "nginx": [],
            "mysql": [],
            "postgresql": [],
        }

        # Apache logs
        apache_paths = ["/var/log/apache2/error.log", "/var/log/httpd/error_log"]
        for path in apache_paths:
            if self.file_ops.exists(path):
                logs["apache"] = self._parse_log_file(path, limit=50)
                break

        # Nginx logs
        if self.file_ops.exists("/var/log/nginx/error.log"):
            logs["nginx"] = self._parse_log_file("/var/log/nginx/error.log", limit=50)

        # MySQL logs
        mysql_paths = ["/var/log/mysql/error.log", "/var/log/mysqld.log"]
        for path in mysql_paths:
            if self.file_ops.exists(path):
                logs["mysql"] = self._parse_log_file(path, limit=50)
                break

        # PostgreSQL logs
        if self.file_ops.is_dir("/var/log/postgresql"):
            # Get latest log file
            pg_files = self.file_ops.ls("/var/log/postgresql")
            if pg_files:
                latest_pg = sorted(pg_files)[-1]
                logs["postgresql"] = self._parse_log_file(f"/var/log/postgresql/{latest_pg}", limit=50)

        return logs

    def _parse_log_file(self, filepath: str, limit: int = 100) -> dict[str, Any]:
        """
        Parse a log file and extract recent entries.

        Args:
            filepath: Path to log file
            limit: Maximum number of entries to return

        Returns:
            Parsed log data
        """
        log_data: dict[str, Any] = {
            "path": filepath,
            "entries": [],
            "total_lines": 0,
            "error_count": 0,
            "warning_count": 0,
        }

        try:
            content = self.file_ops.cat(filepath)
            lines = content.splitlines()
            log_data["total_lines"] = len(lines)

            # Get last N lines
            recent_lines = lines[-limit:] if len(lines) > limit else lines

            for line in recent_lines:
                entry = self._parse_log_line(line)
                if entry:
                    log_data["entries"].append(entry)

                    # Count errors and warnings
                    if "ERROR" in line or "error" in line.lower():
                        log_data["error_count"] += 1
                    if "WARNING" in line or "warning" in line.lower() or "WARN" in line:
                        log_data["warning_count"] += 1

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort scan
            self.logger.debug(f"Failed to parse log file {filepath}: {e}")

        return log_data

    def _parse_log_line(self, line: str) -> dict[str, Any] | None:
        """Parse a single log line."""
        # Common syslog format: timestamp hostname process[pid]: message
        # Example: Jan 15 10:30:45 hostname sshd[1234]: message

        # Try to extract timestamp
        timestamp_match = re.match(r"^(\w+\s+\d+\s+\d+:\d+:\d+)\s+(\S+)\s+([^:]+):\s*(.*)$", line)

        if timestamp_match:
            return {
                "timestamp": timestamp_match.group(1),
                "hostname": timestamp_match.group(2),
                "process": timestamp_match.group(3),
                "message": timestamp_match.group(4),
                "raw": line,
            }

        # If parsing failed, just return raw line
        return {"raw": line}

    def _find_errors(self, limit: int = 50) -> list[dict[str, Any]]:
        """Find error messages in system logs."""
        errors = []

        # Search in syslog/messages
        for log_path in ["/var/log/syslog", "/var/log/messages"]:
            if self.file_ops.exists(log_path):
                try:
                    content = self.file_ops.cat(log_path)
                    lines = content.splitlines()

                    # Search last 1000 lines for errors
                    recent_lines = lines[-1000:] if len(lines) > 1000 else lines

                    for line in recent_lines:
                        if re.search(r"\b(ERROR|error|Error|failed|Failed|FAILED)\b", line):
                            errors.append(self._parse_log_line(line) or {"raw": line})

                        if len(errors) >= limit:
                            break

                except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort scan
                    self.logger.debug(f"Failed to search errors in {log_path}: {e}")

                if len(errors) >= limit:
                    break

        return errors[-limit:]

    def _find_warnings(self, limit: int = 50) -> list[dict[str, Any]]:
        """Find warning messages in system logs."""
        warnings = []

        for log_path in ["/var/log/syslog", "/var/log/messages"]:
            if self.file_ops.exists(log_path):
                try:
                    content = self.file_ops.cat(log_path)
                    lines = content.splitlines()

                    recent_lines = lines[-1000:] if len(lines) > 1000 else lines

                    for line in recent_lines:
                        if re.search(r"\b(WARNING|warning|Warning|WARN|Warn)\b", line):
                            warnings.append(self._parse_log_line(line) or {"raw": line})

                        if len(warnings) >= limit:
                            break

                except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort scan
                    self.logger.debug(f"Failed to search warnings in {log_path}: {e}")

                if len(warnings) >= limit:
                    break

        return warnings[-limit:]

    def _find_failed_logins(self, log_path: str, limit: int = 50) -> list[dict[str, Any]]:
        """Find failed login attempts."""
        failed_logins = []

        try:
            content = self.file_ops.cat(log_path)
            lines = content.splitlines()

            for line in lines:
                if "Failed password" in line or "authentication failure" in line:
                    entry = self._parse_log_line(line)
                    if entry:
                        failed_logins.append(entry)

                if len(failed_logins) >= limit:
                    break

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort scan
            self.logger.debug(f"Failed to find failed logins: {e}")

        return failed_logins[-limit:]

    def _find_successful_logins(self, log_path: str, limit: int = 50) -> list[dict[str, Any]]:
        """Find successful login attempts."""
        successful_logins = []

        try:
            content = self.file_ops.cat(log_path)
            lines = content.splitlines()

            for line in lines:
                if "Accepted password" in line or "Accepted publickey" in line or "session opened" in line:
                    entry = self._parse_log_line(line)
                    if entry:
                        successful_logins.append(entry)

                if len(successful_logins) >= limit:
                    break

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort scan
            self.logger.debug(f"Failed to find successful logins: {e}")

        return successful_logins[-limit:]

    def _find_sudo_usage(self, log_path: str, limit: int = 50) -> list[dict[str, Any]]:
        """Find sudo usage events."""
        sudo_events = []

        try:
            content = self.file_ops.cat(log_path)
            lines = content.splitlines()

            for line in lines:
                if "sudo:" in line or "COMMAND=" in line:
                    entry = self._parse_log_line(line)
                    if entry:
                        sudo_events.append(entry)

                if len(sudo_events) >= limit:
                    break

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort scan
            self.logger.debug(f"Failed to find sudo usage: {e}")

        return sudo_events[-limit:]

    def _analyze_security_events(self) -> list[dict[str, Any]]:
        """Analyze security-related events."""
        events = []

        # Add failed login summary
        auth_logs = self._analyze_auth_logs()
        if auth_logs.get("failed_logins"):
            events.append(
                {
                    "type": "failed_logins",
                    "count": len(auth_logs["failed_logins"]),
                    "description": f"Found {len(auth_logs['failed_logins'])} failed login attempts",
                }
            )

        # Add sudo usage summary
        if auth_logs.get("sudo_usage"):
            events.append(
                {
                    "type": "sudo_usage",
                    "count": len(auth_logs["sudo_usage"]),
                    "description": f"Found {len(auth_logs['sudo_usage'])} sudo command executions",
                }
            )

        return events

    def _calculate_statistics(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Calculate log statistics."""
        stats: dict[str, Any] = {
            "total_errors": len(analysis.get("errors", [])),
            "total_warnings": len(analysis.get("warnings", [])),
            "failed_logins": len(analysis.get("auth_logs", {}).get("failed_logins", [])),
            "successful_logins": len(analysis.get("auth_logs", {}).get("successful_logins", [])),
            "sudo_usage": len(analysis.get("auth_logs", {}).get("sudo_usage", [])),
            "security_events": len(analysis.get("security_events", [])),
        }

        return stats

    def get_recent_errors(  # pylint: disable=unused-argument  # 'hours' is public API; no parsed timestamps to filter by yet
        self, hours: int = 24, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Get errors from the last N hours."""
        # Note: Without timestamps, we just return recent errors
        return self._find_errors(limit=limit)

    def get_critical_events(self) -> list[dict[str, Any]]:
        """Get critical events (kernel panics, OOM, crashes)."""
        critical = []

        for log_path in ["/var/log/syslog", "/var/log/messages", "/var/log/kern.log"]:
            if self.file_ops.exists(log_path):
                try:
                    content = self.file_ops.cat(log_path)
                    lines = content.splitlines()

                    for line in lines:
                        if any(
                            keyword in line
                            for keyword in [
                                "kernel panic",
                                "Out of memory",
                                "segfault",
                                "kernel BUG",
                                "Call Trace:",
                            ]
                        ):
                            critical.append(self._parse_log_line(line) or {"raw": line})

                except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort scan
                    self.logger.debug(f"Failed to search critical events: {e}")

        return critical
