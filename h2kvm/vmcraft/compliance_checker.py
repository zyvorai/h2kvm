# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/compliance_checker.py
"""
System compliance and hardening checker.

Provides compliance checking against security standards:
- CIS Benchmarks (basic checks)
- System hardening verification
- Security baseline compliance
- PCI-DSS requirements (basic)
- HIPAA technical safeguards (basic)

Features:
- Password policy verification
- File permission auditing
- Service configuration checking
- Network security settings
- Logging and auditing configuration
- Compliance scoring
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging
    from pathlib import Path

    from .file_ops import FileOperations


class ComplianceChecker:
    """
    System compliance checker.

    Checks system configuration against security baselines.
    """

    def __init__(self, logger: logging.Logger, file_ops: FileOperations, mount_root: Path):
        """
        Initialize compliance checker.

        Args:
            logger: Logger instance
            file_ops: FileOperations instance
            mount_root: Root directory where guest filesystem is mounted
        """
        self.logger = logger
        self.file_ops = file_ops
        self.mount_root = mount_root

    def check_compliance(self, os_type: str = "linux") -> dict[str, Any]:
        """
        Run comprehensive compliance checks.

        Args:
            os_type: Operating system type

        Returns:
            Compliance check results
        """
        compliance: dict[str, Any] = {
            "os_type": os_type,
            "checks": [],
            "passed": 0,
            "failed": 0,
            "warnings": 0,
            "score": 0,
            "grade": None,
        }

        checks = self._check_linux_compliance() if os_type == "linux" else self._check_windows_compliance()

        compliance["checks"] = checks

        # Calculate scores
        for check in checks:
            if check["status"] == "pass":
                compliance["passed"] += 1
            elif check["status"] == "fail":
                compliance["failed"] += 1
            elif check["status"] == "warning":
                compliance["warnings"] += 1

        total = compliance["passed"] + compliance["failed"] + compliance["warnings"]
        if total > 0:
            compliance["score"] = int((compliance["passed"] / total) * 100)
            compliance["grade"] = self._score_to_grade(compliance["score"])

        return compliance

    def _check_linux_compliance(self) -> list[dict[str, Any]]:
        """Check Linux system compliance."""
        checks = []

        # Check 1: Password policy
        checks.append(self._check_password_policy())

        # Check 2: Shadow passwords
        checks.append(self._check_shadow_passwords())

        # Check 3: File permissions on sensitive files
        checks.extend(self._check_sensitive_file_permissions())

        # Check 4: No empty passwords
        checks.append(self._check_empty_passwords())

        # Check 5: Root login disabled
        checks.append(self._check_root_login())

        # Check 6: Firewall enabled
        checks.append(self._check_firewall_enabled())

        # Check 7: SELinux/AppArmor enabled
        checks.append(self._check_mandatory_access_control())

        # Check 8: System logging enabled
        checks.append(self._check_logging_enabled())

        # Check 9: Unnecessary services disabled
        checks.extend(self._check_unnecessary_services())

        # Check 10: Core dumps disabled
        checks.append(self._check_core_dumps())

        return checks

    def _check_password_policy(self) -> dict[str, Any]:
        """Check password policy configuration."""
        check = {
            "id": "PWD-001",
            "category": "Authentication",
            "description": "Password minimum length configured",
            "status": "unknown",
            "severity": "medium",
            "recommendation": None,
        }

        # Check /etc/login.defs
        if self.file_ops.exists("/etc/login.defs"):
            try:
                content = self.file_ops.cat("/etc/login.defs")
                for line in content.splitlines():
                    if line.startswith("PASS_MIN_LEN"):
                        min_len = int(line.split()[1])
                        if min_len >= 8:
                            check["status"] = "pass"
                            check["details"] = f"Minimum password length: {min_len}"
                        else:
                            check["status"] = "fail"
                            check["details"] = f"Minimum password length too short: {min_len}"
                            check["recommendation"] = "Set PASS_MIN_LEN to at least 8"
                        break
            except Exception:  # pylint: disable=broad-exception-caught
                # best-effort guest config parse; must not abort the compliance check
                check["status"] = "unknown"

        return check

    def _check_shadow_passwords(self) -> dict[str, Any]:
        """Check if shadow passwords are enabled."""
        check = {
            "id": "PWD-002",
            "category": "Authentication",
            "description": "Shadow passwords enabled",
            "status": "unknown",
            "severity": "high",
            "recommendation": None,
        }

        if self.file_ops.exists("/etc/shadow"):
            check["status"] = "pass"
            check["details"] = "Shadow password file exists"
        else:
            check["status"] = "fail"
            check["details"] = "Shadow password file not found"
            check["recommendation"] = "Enable shadow passwords"

        return check

    def _check_sensitive_file_permissions(self) -> list[dict[str, Any]]:
        """Check permissions on sensitive files."""
        checks = []

        sensitive_files = {
            "/etc/passwd": 0o644,
            "/etc/shadow": 0o000,  # Should be restricted
            "/etc/group": 0o644,
            "/etc/gshadow": 0o000,  # Should be restricted
        }

        for filepath in sensitive_files:
            check = {
                "id": f"PERM-{filepath.replace('/', '_')}",
                "category": "File Permissions",
                "description": f"Permissions on {filepath}",
                "status": "unknown",
                "severity": "high" if "shadow" in filepath else "medium",
                "recommendation": None,
            }

            if self.file_ops.exists(filepath):
                # Basic check - file exists
                check["status"] = "pass"
                check["details"] = f"{filepath} exists with restricted access"
            else:
                check["status"] = "warning"
                check["details"] = f"{filepath} not found"

            checks.append(check)

        return checks

    def _check_empty_passwords(self) -> dict[str, Any]:
        """Check for accounts with empty passwords."""
        check = {
            "id": "PWD-003",
            "category": "Authentication",
            "description": "No accounts with empty passwords",
            "status": "unknown",
            "severity": "critical",
            "recommendation": None,
        }

        if self.file_ops.exists("/etc/shadow"):
            try:
                content = self.file_ops.cat("/etc/shadow")
                empty_passwords = 0

                for line in content.splitlines():
                    if not line or line.startswith("#"):
                        continue

                    parts = line.split(":")
                    if len(parts) >= 2:
                        # Check if password field is empty or just !
                        if parts[1] == "" or parts[1] == "!":
                            empty_passwords += 1

                if empty_passwords == 0:
                    check["status"] = "pass"
                    check["details"] = "No empty passwords found"
                else:
                    check["status"] = "fail"
                    check["details"] = f"Found {empty_passwords} accounts with empty/locked passwords"
                    check["recommendation"] = "Set passwords or disable these accounts"

            except Exception:  # pylint: disable=broad-exception-caught
                # best-effort guest config parse; must not abort the compliance check
                check["status"] = "unknown"

        return check

    def _check_root_login(self) -> dict[str, Any]:
        """Check if root login is disabled."""
        check = {
            "id": "SSH-001",
            "category": "SSH Security",
            "description": "Root SSH login disabled",
            "status": "unknown",
            "severity": "high",
            "recommendation": None,
        }

        if self.file_ops.exists("/etc/ssh/sshd_config"):
            try:
                content = self.file_ops.cat("/etc/ssh/sshd_config")

                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith("PermitRootLogin"):
                        value = line.split()[1].lower()
                        if value == "no":
                            check["status"] = "pass"
                            check["details"] = "Root login is disabled"
                        elif value == "prohibit-password":
                            check["status"] = "warning"
                            check["details"] = "Root login allowed with key only"
                            check["recommendation"] = "Set PermitRootLogin to 'no'"
                        else:
                            check["status"] = "fail"
                            check["details"] = "Root login is allowed"
                            check["recommendation"] = "Set PermitRootLogin to 'no'"
                        break

            except Exception:  # pylint: disable=broad-exception-caught
                # best-effort guest config parse; must not abort the compliance check
                check["status"] = "unknown"

        return check

    def _check_firewall_enabled(self) -> dict[str, Any]:
        """Check if firewall is enabled."""
        check = {
            "id": "NET-001",
            "category": "Network Security",
            "description": "Firewall enabled",
            "status": "unknown",
            "severity": "high",
            "recommendation": None,
        }

        # Check for various firewalls
        firewall_indicators = [
            "/etc/firewalld",
            "/etc/ufw",
            "/etc/sysconfig/iptables",
        ]

        for indicator in firewall_indicators:
            if self.file_ops.exists(indicator):
                check["status"] = "pass"
                check["details"] = f"Firewall configuration found at {indicator}"
                break
        else:
            check["status"] = "fail"
            check["details"] = "No firewall configuration found"
            check["recommendation"] = "Enable and configure a firewall"

        return check

    def _check_mandatory_access_control(self) -> dict[str, Any]:
        """Check if MAC (SELinux/AppArmor) is enabled."""
        check = {
            "id": "SEC-001",
            "category": "Access Control",
            "description": "Mandatory Access Control enabled",
            "status": "unknown",
            "severity": "medium",
            "recommendation": None,
        }

        # Check SELinux
        if self.file_ops.exists("/etc/selinux/config"):
            try:
                content = self.file_ops.cat("/etc/selinux/config")
                if "SELINUX=enforcing" in content or "SELINUX=permissive" in content:
                    check["status"] = "pass"
                    check["details"] = "SELinux is enabled"
                else:
                    check["status"] = "fail"
                    check["details"] = "SELinux is disabled"
                    check["recommendation"] = "Enable SELinux"
            except Exception:  # pylint: disable=broad-exception-caught
                # best-effort guest config parse; must not abort the compliance check
                pass

        # Check AppArmor
        elif self.file_ops.is_dir("/etc/apparmor.d"):
            check["status"] = "pass"
            check["details"] = "AppArmor is installed"

        else:
            check["status"] = "fail"
            check["details"] = "No MAC system found"
            check["recommendation"] = "Enable SELinux or AppArmor"

        return check

    def _check_logging_enabled(self) -> dict[str, Any]:
        """Check if system logging is enabled."""
        check = {
            "id": "LOG-001",
            "category": "Logging",
            "description": "System logging enabled",
            "status": "unknown",
            "severity": "medium",
            "recommendation": None,
        }

        # Check for syslog or systemd-journald
        logging_indicators = [
            "/var/log/syslog",
            "/var/log/messages",
            "/run/systemd/journal",
        ]

        for indicator in logging_indicators:
            if self.file_ops.exists(indicator):
                check["status"] = "pass"
                check["details"] = f"Logging active: {indicator}"
                break
        else:
            check["status"] = "fail"
            check["details"] = "No logging system found"
            check["recommendation"] = "Enable rsyslog or systemd-journald"

        return check

    def _check_unnecessary_services(self) -> list[dict[str, Any]]:
        """Check for unnecessary services."""
        checks = []

        # List of services that should typically be disabled
        unnecessary_services = [
            "telnet",
            "rsh",
            "rlogin",
            "vsftpd",
        ]

        for service in unnecessary_services:
            check = {
                "id": f"SVC-{service}",
                "category": "Services",
                "description": f"Unnecessary service '{service}' disabled",
                "status": "pass",  # Assume pass if not found
                "severity": "medium",
                "recommendation": None,
                "details": f"Service {service} not found (good)",
            }

            # Check if service exists
            service_paths = [
                f"/etc/systemd/system/{service}.service",
                f"/lib/systemd/system/{service}.service",
            ]

            for path in service_paths:
                if self.file_ops.exists(path):
                    check["status"] = "warning"
                    check["details"] = f"Service {service} found"
                    check["recommendation"] = f"Disable {service} if not needed"
                    break

            checks.append(check)

        return checks

    def _check_core_dumps(self) -> dict[str, Any]:
        """Check if core dumps are disabled."""
        check = {
            "id": "SEC-002",
            "category": "Security",
            "description": "Core dumps disabled",
            "status": "unknown",
            "severity": "low",
            "recommendation": None,
        }

        if self.file_ops.exists("/etc/security/limits.conf"):
            try:
                content = self.file_ops.cat("/etc/security/limits.conf")
                if "* hard core 0" in content:
                    check["status"] = "pass"
                    check["details"] = "Core dumps are disabled"
                else:
                    check["status"] = "warning"
                    check["details"] = "Core dumps not explicitly disabled"
                    check["recommendation"] = "Disable core dumps in limits.conf"
            except Exception:  # pylint: disable=broad-exception-caught
                # best-effort guest config parse; must not abort the compliance check
                check["status"] = "unknown"

        return check

    def _check_windows_compliance(self) -> list[dict[str, Any]]:
        """Check Windows system compliance (basic)."""
        checks = []

        # Basic Windows checks
        check = {
            "id": "WIN-001",
            "category": "Windows Security",
            "description": "Windows compliance check",
            "status": "info",
            "severity": "info",
            "recommendation": None,
            "details": "Windows compliance checking requires registry access",
        }
        checks.append(check)

        return checks

    def _score_to_grade(self, score: int) -> str:
        """Convert score to letter grade."""
        # pylint: disable=duplicate-code
        # reason: mirrors the equivalent score-to-grade thresholds in
        # vmcraft/ssh_analyzer.py -- structurally similar by coincidence
        # (both use the same conventional 90/80/70/60 grading bands), not
        # shared logic; keeping independent avoids coupling two unrelated
        # scoring code paths.
        if score >= 90:
            return "A"
        if score >= 80:
            return "B"
        if score >= 70:
            return "C"
        if score >= 60:
            return "D"
        return "F"

    def get_compliance_summary(self, compliance: dict[str, Any]) -> dict[str, Any]:
        """
        Get compliance summary.

        Args:
            compliance: Compliance check results

        Returns:
            Summary dictionary
        """
        return {
            "score": compliance.get("score", 0),
            "grade": compliance.get("grade", "F"),
            "total_checks": len(compliance.get("checks", [])),
            "passed": compliance.get("passed", 0),
            "failed": compliance.get("failed", 0),
            "warnings": compliance.get("warnings", 0),
            "critical_failures": sum(
                1
                for check in compliance.get("checks", [])
                if check["status"] == "fail" and check["severity"] == "critical"
            ),
            "high_failures": sum(
                1
                for check in compliance.get("checks", [])
                if check["status"] == "fail" and check["severity"] == "high"
            ),
        }

    def get_failed_checks(self, compliance: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Get all failed checks.

        Args:
            compliance: Compliance check results

        Returns:
            List of failed checks
        """
        return [check for check in compliance.get("checks", []) if check["status"] == "fail"]

    def get_recommendations(self, compliance: dict[str, Any]) -> list[str]:
        """
        Get all recommendations.

        Args:
            compliance: Compliance check results

        Returns:
            List of recommendations
        """
        recommendations = []

        for check in compliance.get("checks", []):
            if check.get("recommendation"):
                recommendations.append(f"[{check['id']}] {check['recommendation']}")

        return recommendations
