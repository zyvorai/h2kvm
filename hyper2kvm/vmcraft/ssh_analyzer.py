# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/vmcraft/ssh_analyzer.py
"""
SSH configuration analysis for Linux systems.

Provides comprehensive SSH configuration detection:
- sshd_config parsing
- SSH server settings (port, protocol, authentication methods)
- SSH security analysis (root login, password auth, key types)
- Authorized keys detection
- Known hosts analysis
- SSH client configuration

Features:
- Parse sshd_config directives
- Identify security issues
- List authorized keys per user
- Detect SSH key types and algorithms
- Configuration recommendations
"""

# pylint: disable=duplicate-code
# reason: this module has 4+ small blocks (score-to-grade conversion,
# authorized_keys parsing, ssh-config-style key=value loops) that are
# structurally similar to blocks in several sibling vmcraft modules (e.g.
# compliance_checker.py, scheduled_tasks.py, enhanced_inspection.py,
# services/inspection.py) by coincidence, not shared logic; keeping each
# independently editable avoids coupling unrelated inspection code paths.
# See git history for the pylint pass that reviewed each instance.

from __future__ import annotations

from typing import Any

from .base_analyzer import BaseAnalyzer


class SSHAnalyzer(BaseAnalyzer):
    """
    SSH configuration analyzer.

    Analyzes SSH server and client configuration on Linux systems.
    """

    def analyze_ssh_config(self) -> dict[str, Any]:
        """
        Analyze SSH server and client configuration.

        Returns:
            SSH configuration dictionary
        """
        config: dict[str, Any] = {
            "server_config": {},
            "authorized_keys": [],
            "known_hosts": [],
            "client_config": {},
            "security_issues": [],
        }

        # Parse sshd_config
        if self.file_ops.exists("/etc/ssh/sshd_config"):
            config["server_config"] = self._parse_sshd_config("/etc/ssh/sshd_config")
            config["security_issues"] = self._analyze_security(config["server_config"])

        # Parse authorized_keys
        config["authorized_keys"] = self._find_authorized_keys()

        # Parse ssh_config (client)
        if self.file_ops.exists("/etc/ssh/ssh_config"):
            config["client_config"] = self._parse_ssh_config("/etc/ssh/ssh_config")

        return config

    def _parse_sshd_config(self, filepath: str) -> dict[str, Any]:
        """
        Parse sshd_config file.

        Returns:
            Parsed configuration directives
        """
        config: dict[str, Any] = {
            "Port": "22",  # Default
            "Protocol": "2",  # Default
            "PermitRootLogin": "prohibit-password",  # Default in modern SSH
            "PasswordAuthentication": "yes",  # Default
            "PubkeyAuthentication": "yes",  # Default
            "ChallengeResponseAuthentication": "no",  # Default
            "UsePAM": "yes",  # Default on most systems
            "X11Forwarding": "yes",  # Default on some systems
            "AllowUsers": None,
            "DenyUsers": None,
            "AllowGroups": None,
            "DenyGroups": None,
            "raw_directives": [],
        }

        try:
            content = self.file_ops.cat(filepath)

            for line in content.splitlines():
                original_line = line
                line = line.strip()

                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue

                # Parse directive
                parts = line.split(None, 1)
                if len(parts) >= 2:
                    directive = parts[0]
                    value = parts[1]

                    # Store in config
                    config[directive] = value
                    config["raw_directives"].append(original_line)

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort parse, must not abort
            self.logger.debug("Failed to parse sshd_config: %s", e)

        return config

    def _parse_ssh_config(self, filepath: str) -> dict[str, Any]:
        """
        Parse ssh_config (client configuration).

        Returns:
            Parsed client configuration
        """
        config: dict[str, Any] = {
            "hosts": [],
            "global_settings": {},
        }

        try:
            content = self.file_ops.cat(filepath)
            current_host = None

            for line in content.splitlines():
                line = line.strip()

                if not line or line.startswith("#"):
                    continue

                parts = line.split(None, 1)
                if len(parts) < 2:
                    continue

                directive = parts[0]
                value = parts[1]

                if directive == "Host":
                    if current_host:
                        config["hosts"].append(current_host)
                    current_host = {"pattern": value, "settings": {}}
                elif current_host:
                    current_host["settings"][directive] = value
                else:
                    config["global_settings"][directive] = value

            if current_host:
                config["hosts"].append(current_host)

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort parse, must not abort
            self.logger.debug("Failed to parse ssh_config: %s", e)

        return config

    def _find_authorized_keys(self) -> list[dict[str, Any]]:
        """
        Find authorized_keys files for all users.

        Returns:
            List of authorized keys by user
        """
        authorized_keys = []

        try:  # pylint: disable=too-many-nested-blocks  # scans /etc/passwd for every user's authorized_keys
            # Check /etc/passwd for user home directories
            if self.file_ops.exists("/etc/passwd"):
                passwd_content = self.file_ops.cat("/etc/passwd")

                for line in passwd_content.splitlines():
                    parts = line.split(":")
                    if len(parts) >= 6:
                        username = parts[0]
                        home_dir = parts[5]

                        # Check for .ssh/authorized_keys
                        auth_keys_path = f"{home_dir}/.ssh/authorized_keys"
                        if self.file_ops.exists(auth_keys_path):
                            keys = self._parse_authorized_keys(auth_keys_path)
                            if keys:
                                authorized_keys.append(
                                    {
                                        "user": username,
                                        "path": auth_keys_path,
                                        "keys": keys,
                                        "key_count": len(keys),
                                    }
                                )

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort scan, must not abort
            self.logger.debug("Failed to find authorized_keys: %s", e)

        return authorized_keys

    def _parse_authorized_keys(self, filepath: str) -> list[dict[str, Any]]:
        """Parse an authorized_keys file."""
        keys = []

        try:
            content = self.file_ops.cat(filepath)

            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Parse SSH key format: [options] keytype key [comment]
                parts = line.split()
                if len(parts) >= 2:
                    # Check if first part is key type (ssh-rsa, ssh-ed25519, etc.)
                    if parts[0].startswith("ssh-") or parts[0].startswith("ecdsa-"):
                        key = {
                            "type": parts[0],
                            "key": parts[1][:32] + "...",  # Truncate for brevity
                            "comment": " ".join(parts[2:]) if len(parts) > 2 else None,
                            "options": None,
                        }
                    # First part might be options
                    elif len(parts) >= 3:
                        key = {
                            "type": parts[1],
                            "key": parts[2][:32] + "...",
                            "comment": " ".join(parts[3:]) if len(parts) > 3 else None,
                            "options": parts[0],
                        }
                    else:
                        continue

                    keys.append(key)

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort parse, must not abort
            self.logger.debug("Failed to parse authorized_keys %s: %s", filepath, e)

        return keys

    def _analyze_security(self, sshd_config: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Analyze SSH configuration for security issues.

        Returns:
            List of security issues and recommendations
        """
        issues = []

        # Check PermitRootLogin
        if sshd_config.get("PermitRootLogin") == "yes":
            issues.append(
                {
                    "severity": "high",
                    "directive": "PermitRootLogin",
                    "value": "yes",
                    "issue": "Root login is permitted",
                    "recommendation": "Set PermitRootLogin to 'prohibit-password' or 'no'",
                }
            )

        # Check PasswordAuthentication
        if sshd_config.get("PasswordAuthentication") == "yes":
            issues.append(
                {
                    "severity": "medium",
                    "directive": "PasswordAuthentication",
                    "value": "yes",
                    "issue": "Password authentication is enabled",
                    "recommendation": "Consider using key-based authentication only",
                }
            )

        # Check for old protocol
        if sshd_config.get("Protocol") == "1":
            issues.append(
                {
                    "severity": "critical",
                    "directive": "Protocol",
                    "value": "1",
                    "issue": "SSH Protocol 1 is enabled (deprecated and insecure)",
                    "recommendation": "Use Protocol 2 only",
                }
            )

        # Check X11Forwarding
        if sshd_config.get("X11Forwarding") == "yes":
            issues.append(
                {
                    "severity": "low",
                    "directive": "X11Forwarding",
                    "value": "yes",
                    "issue": "X11 forwarding is enabled",
                    "recommendation": "Disable if not needed for security",
                }
            )

        # Check if PermitEmptyPasswords is enabled
        if sshd_config.get("PermitEmptyPasswords") == "yes":
            issues.append(
                {
                    "severity": "critical",
                    "directive": "PermitEmptyPasswords",
                    "value": "yes",
                    "issue": "Empty passwords are permitted",
                    "recommendation": "Set PermitEmptyPasswords to 'no'",
                }
            )

        return issues

    def get_ssh_port(self, config: dict[str, Any]) -> int:
        """Get SSH server port."""
        port_str = config.get("server_config", {}).get("Port", "22")
        try:
            return int(port_str)
        except ValueError:
            return 22

    def is_root_login_allowed(self, config: dict[str, Any]) -> bool:
        """Check if root login is allowed."""
        permit_root = config.get("server_config", {}).get("PermitRootLogin", "prohibit-password")
        return permit_root.lower() == "yes"

    def is_password_auth_enabled(self, config: dict[str, Any]) -> bool:
        """Check if password authentication is enabled."""
        password_auth = config.get("server_config", {}).get("PasswordAuthentication", "yes")
        return password_auth.lower() == "yes"

    def get_authorized_key_count(self, config: dict[str, Any]) -> int:
        """Get total count of authorized keys."""
        total = 0
        for user_keys in config.get("authorized_keys", []):
            total += user_keys.get("key_count", 0)
        return total

    def get_security_score(self, config: dict[str, Any]) -> dict[str, Any]:
        """
        Calculate SSH security score.

        Returns:
            Security score and breakdown
        """
        issues = config.get("security_issues", [])

        score = 100
        critical_count = sum(1 for i in issues if i["severity"] == "critical")
        high_count = sum(1 for i in issues if i["severity"] == "high")
        medium_count = sum(1 for i in issues if i["severity"] == "medium")
        low_count = sum(1 for i in issues if i["severity"] == "low")

        # Deduct points based on severity
        score -= critical_count * 30
        score -= high_count * 20
        score -= medium_count * 10
        score -= low_count * 5

        score = max(0, score)

        return {
            "score": score,
            "grade": self._score_to_grade(score),
            "critical_issues": critical_count,
            "high_issues": high_count,
            "medium_issues": medium_count,
            "low_issues": low_count,
        }

    def _score_to_grade(self, score: int) -> str:
        """Convert numeric score to letter grade."""
        if score >= 90:
            return "A"
        if score >= 80:
            return "B"
        if score >= 70:
            return "C"
        if score >= 60:
            return "D"
        return "F"
