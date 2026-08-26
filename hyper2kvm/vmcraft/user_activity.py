# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/vmcraft/user_activity.py
"""
User activity and access pattern analysis.

Provides comprehensive user activity tracking:
- Login history (wtmp, lastlog)
- Sudo usage (auth.log, secure)
- Command history (bash_history, zsh_history)
- SSH key usage (authorized_keys, known_hosts)
- Failed login attempts
- User sessions and active users

Features:
- Parse login history
- Analyze sudo usage patterns
- Extract command history
- Track SSH access
- Detect suspicious activity
- Generate user activity reports
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging
    from pathlib import Path

    from .file_ops import FileOperations


class UserActivityAnalyzer:
    """
    User activity and access pattern analyzer.

    Analyzes user login history, sudo usage, and command patterns.
    """

    def __init__(self, logger: logging.Logger, file_ops: FileOperations, mount_root: Path):
        """
        Initialize user activity analyzer.

        Args:
            logger: Logger instance
            file_ops: FileOperations instance
            mount_root: Root directory where guest filesystem is mounted
        """
        self.logger = logger
        self.file_ops = file_ops
        self.mount_root = mount_root

    def analyze_user_activity(self) -> dict[str, Any]:
        """
        Analyze user activity comprehensively.

        Returns:
            User activity analysis results
        """
        activity: dict[str, Any] = {
            "login_history": [],
            "sudo_usage": [],
            "command_history": [],
            "ssh_keys": [],
            "failed_logins": [],
            "total_logins": 0,
            "total_sudo_commands": 0,
            "total_users_with_history": 0,
        }

        # Analyze login history
        login_history = self._analyze_login_history()
        activity["login_history"] = login_history[:50]  # Limit to 50 recent
        activity["total_logins"] = len(login_history)

        # Analyze sudo usage
        sudo_usage = self._analyze_sudo_usage()
        activity["sudo_usage"] = sudo_usage[:50]
        activity["total_sudo_commands"] = len(sudo_usage)

        # Analyze command history
        command_history = self._analyze_command_history()
        activity["command_history"] = command_history
        activity["total_users_with_history"] = len(command_history)

        # Analyze SSH keys
        ssh_keys = self._analyze_ssh_keys()
        activity["ssh_keys"] = ssh_keys

        # Analyze failed logins
        failed_logins = self._analyze_failed_logins()
        activity["failed_logins"] = failed_logins[:50]

        return activity

    def _analyze_login_history(self) -> list[dict[str, Any]]:
        """Analyze login history from lastlog."""
        logins = []

        # Try to parse /var/log/lastlog (binary format - skip for now)
        # Instead, look for text-based alternatives

        # Parse /var/log/auth.log or /var/log/secure for login events
        log_paths = [
            "/var/log/auth.log",
            "/var/log/secure",
        ]

        for log_path in log_paths:
            if not self.file_ops.exists(log_path):
                continue

            try:
                content = self.file_ops.cat(log_path)
                for line in content.splitlines():
                    # Look for successful logins
                    if "Accepted password" in line or "Accepted publickey" in line:
                        login_info = self._parse_login_line(line)
                        if login_info:
                            logins.append(login_info)
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort scan
                self.logger.debug(f"Failed to parse {log_path}: {e}")

        return logins

    def _parse_login_line(self, line: str) -> dict[str, Any] | None:
        """Parse a login log line."""
        # Example: Jan 15 10:23:45 host sshd[1234]: Accepted password for user from 192.168.1.100 port 12345 ssh2
        try:
            if "Accepted password" in line:
                match = re.search(r"Accepted password for (\w+) from ([\d.]+)", line)
                if match:
                    return {
                        "user": match.group(1),
                        "ip": match.group(2),
                        "method": "password",
                        "service": "ssh",
                    }
            elif "Accepted publickey" in line:
                match = re.search(r"Accepted publickey for (\w+) from ([\d.]+)", line)
                if match:
                    return {
                        "user": match.group(1),
                        "ip": match.group(2),
                        "method": "publickey",
                        "service": "ssh",
                    }
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort scan
            pass

        return None

    def _analyze_sudo_usage(self) -> list[dict[str, Any]]:
        """Analyze sudo command usage."""
        sudo_commands = []

        log_paths = [
            "/var/log/auth.log",
            "/var/log/secure",
        ]

        for log_path in log_paths:
            if not self.file_ops.exists(log_path):
                continue

            try:
                content = self.file_ops.cat(log_path)
                for line in content.splitlines():
                    if "sudo:" in line and "COMMAND=" in line:
                        sudo_info = self._parse_sudo_line(line)
                        if sudo_info:
                            sudo_commands.append(sudo_info)
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort scan
                self.logger.debug(f"Failed to parse {log_path}: {e}")

        return sudo_commands

    def _parse_sudo_line(self, line: str) -> dict[str, Any] | None:
        """Parse a sudo log line."""
        # Example: Jan 15 10:23:45 host sudo: user : TTY=pts/0 ; PWD=/home/user ;
        # USER=root ; COMMAND=/usr/bin/apt update
        try:
            match = re.search(r"sudo:\s+(\w+)\s+:.*COMMAND=(.+)$", line)
            if match:
                return {
                    "user": match.group(1),
                    "command": match.group(2).strip(),
                }
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort scan
            pass

        return None

    def _analyze_command_history(self) -> list[dict[str, Any]]:
        """Analyze command history for users."""
        users_history = []

        # Get list of users
        if not self.file_ops.exists("/etc/passwd"):
            return users_history

        try:
            passwd_content = self.file_ops.cat("/etc/passwd")
            for line in passwd_content.splitlines():
                if not line or line.startswith("#"):
                    continue

                parts = line.split(":")
                if len(parts) < 6:
                    continue

                username = parts[0]
                home_dir = parts[5]

                # Skip system users
                if not home_dir.startswith("/home") and home_dir != "/root":
                    continue

                # Check for bash history
                bash_history = f"{home_dir}/.bash_history"
                if self.file_ops.exists(bash_history):
                    try:
                        content = self.file_ops.cat(bash_history)
                        commands = content.splitlines()

                        # Get top commands (unique)
                        list(set(commands[:100]))  # First 100 unique

                        users_history.append(
                            {
                                "user": username,
                                "shell": "bash",
                                "command_count": len(commands),
                                "recent_commands": commands[-10:],  # Last 10 commands
                                "unique_count": len(set(commands)),
                            }
                        )
                    except Exception:  # pylint: disable=broad-exception-caught  # best-effort scan
                        pass

                # Check for zsh history
                zsh_history = f"{home_dir}/.zsh_history"
                if self.file_ops.exists(zsh_history):
                    try:
                        content = self.file_ops.cat(zsh_history)
                        commands = content.splitlines()

                        users_history.append(
                            {
                                "user": username,
                                "shell": "zsh",
                                "command_count": len(commands),
                                "recent_commands": commands[-10:],
                                "unique_count": len(set(commands)),
                            }
                        )
                    except Exception:  # pylint: disable=broad-exception-caught  # best-effort scan
                        pass

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort scan
            self.logger.debug(f"Failed to analyze command history: {e}")

        return users_history

    def _analyze_ssh_keys(self) -> list[dict[str, Any]]:
        """Analyze SSH keys for users."""
        ssh_keys = []

        # Get list of users
        if not self.file_ops.exists("/etc/passwd"):
            return ssh_keys

        try:
            passwd_content = self.file_ops.cat("/etc/passwd")
            for line in passwd_content.splitlines():
                if not line or line.startswith("#"):
                    continue

                parts = line.split(":")
                if len(parts) < 6:
                    continue

                username = parts[0]
                home_dir = parts[5]

                # Check for authorized_keys
                auth_keys_path = f"{home_dir}/.ssh/authorized_keys"
                if self.file_ops.exists(auth_keys_path):
                    try:
                        content = self.file_ops.cat(auth_keys_path)
                        keys = [line for line in content.splitlines() if line and not line.startswith("#")]

                        ssh_keys.append(
                            {
                                "user": username,
                                "authorized_keys": len(keys),
                                "key_types": self._extract_key_types(keys),
                            }
                        )
                    except Exception:  # pylint: disable=broad-exception-caught  # best-effort scan
                        pass

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort scan
            self.logger.debug(f"Failed to analyze SSH keys: {e}")

        return ssh_keys

    def _extract_key_types(self, keys: list[str]) -> list[str]:
        """Extract SSH key types."""
        types = []
        for key in keys:
            if key.startswith("ssh-rsa"):
                types.append("rsa")
            elif key.startswith("ssh-ed25519"):
                types.append("ed25519")
            elif key.startswith("ecdsa"):
                types.append("ecdsa")
        return list(set(types))

    def _analyze_failed_logins(self) -> list[dict[str, Any]]:
        """Analyze failed login attempts."""
        failed = []

        log_paths = [
            "/var/log/auth.log",
            "/var/log/secure",
        ]

        for log_path in log_paths:
            if not self.file_ops.exists(log_path):
                continue

            try:
                content = self.file_ops.cat(log_path)
                for line in content.splitlines():
                    if "Failed password" in line:
                        failed_info = self._parse_failed_login(line)
                        if failed_info:
                            failed.append(failed_info)
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort scan
                self.logger.debug(f"Failed to parse {log_path}: {e}")

        return failed

    def _parse_failed_login(self, line: str) -> dict[str, Any] | None:
        """Parse a failed login line."""
        # Example: Jan 15 10:23:45 host sshd[1234]: Failed password for invalid user
        # admin from 192.168.1.100 port 12345 ssh2
        try:
            match = re.search(r"Failed password for (?:invalid user )?(\w+) from ([\d.]+)", line)
            if match:
                return {
                    "user": match.group(1),
                    "ip": match.group(2),
                    "service": "ssh",
                }
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort scan
            pass

        return None

    def get_activity_summary(self, activity: dict[str, Any]) -> dict[str, Any]:
        """
        Get user activity summary.

        Args:
            activity: User activity analysis results

        Returns:
            Summary dictionary
        """
        return {
            "total_logins": activity.get("total_logins", 0),
            "total_sudo_commands": activity.get("total_sudo_commands", 0),
            "users_with_command_history": activity.get("total_users_with_history", 0),
            "users_with_ssh_keys": len(activity.get("ssh_keys", [])),
            "failed_login_attempts": len(activity.get("failed_logins", [])),
            "unique_login_ips": len({login.get("ip", "") for login in activity.get("login_history", [])}),
        }

    def detect_suspicious_activity(self, activity: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Detect suspicious user activity.

        Args:
            activity: User activity analysis results

        Returns:
            List of suspicious activities
        """
        suspicious = []

        # Check for excessive failed logins
        failed_logins = activity.get("failed_logins", [])
        if len(failed_logins) > 100:
            suspicious.append(
                {
                    "severity": "high",
                    "type": "brute_force_attempt",
                    "issue": f"{len(failed_logins)} failed login attempts detected",
                    "recommendation": "Review auth logs and consider IP blocking",
                }
            )

        # Check for sudo usage by suspicious users
        sudo_usage = activity.get("sudo_usage", [])
        for sudo_cmd in sudo_usage:
            if "passwd" in sudo_cmd.get("command", "").lower():
                suspicious.append(
                    {
                        "severity": "medium",
                        "type": "password_change",
                        "issue": f"Password change via sudo by {sudo_cmd.get('user')}",
                        "recommendation": "Verify this was an authorized action",
                    }
                )

        return suspicious

    def get_top_sudo_users(self, activity: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
        """
        Get users with most sudo usage.

        Args:
            activity: User activity analysis results
            limit: Maximum number of users to return

        Returns:
            List of users with sudo usage counts
        """
        sudo_usage = activity.get("sudo_usage", [])
        user_counts: dict[str, int] = {}

        for sudo_cmd in sudo_usage:
            user = sudo_cmd.get("user", "unknown")
            user_counts[user] = user_counts.get(user, 0) + 1

        # Sort by count
        sorted_users = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)

        return [{"user": user, "sudo_count": count} for user, count in sorted_users[:limit]]

    def get_login_sources(self, activity: dict[str, Any]) -> dict[str, int]:
        """
        Get login source IPs and their counts.

        Args:
            activity: User activity analysis results

        Returns:
            Dictionary of IP addresses and login counts
        """
        login_history = activity.get("login_history", [])
        ip_counts: dict[str, int] = {}

        for login in login_history:
            ip = login.get("ip", "unknown")
            ip_counts[ip] = ip_counts.get(ip, 0) + 1

        return ip_counts
