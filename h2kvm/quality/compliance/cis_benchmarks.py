# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/compliance/cis_benchmarks.py
"""
CIS Benchmark compliance validator.

Validates VMs against CIS Benchmarks for Linux distributions.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .base import (
    ComplianceCheck,
    ComplianceFramework,
    ComplianceLevel,
    ComplianceResult,
    ComplianceValidator,
)

logger = logging.getLogger(__name__)


class CISBenchmarkValidator(ComplianceValidator):
    """
    CIS Benchmark compliance validator.

    Validates common CIS Benchmark controls for Linux systems.
    """

    def get_framework(self) -> ComplianceFramework:
        """Get compliance framework type."""
        return ComplianceFramework.CIS_BENCHMARK

    def get_checks(self) -> list[dict[str, Any]]:
        """Get list of available CIS checks."""
        return [
            {
                "check_id": "CIS-1.1.1.1",
                "title": "Ensure mounting of cramfs filesystems is disabled",
                "description": "The cramfs filesystem should be disabled",
                "level": ComplianceLevel.MEDIUM,
                "references": ["CIS Benchmark 1.1.1.1"],
            },
            {
                "check_id": "CIS-1.4.1",
                "title": "Ensure permissions on bootloader config are configured",
                "description": "Bootloader config should be 0600 (rw-------)",
                "level": ComplianceLevel.CRITICAL,
                "references": ["CIS Benchmark 1.4.1"],
            },
            {
                "check_id": "CIS-1.5.1",
                "title": "Ensure core dumps are restricted",
                "description": "Core dumps should be disabled for security",
                "level": ComplianceLevel.HIGH,
                "references": ["CIS Benchmark 1.5.1"],
            },
            {
                "check_id": "CIS-3.3.3",
                "title": "Ensure IPv6 router advertisements are not accepted",
                "description": "IPv6 router advertisements should be disabled",
                "level": ComplianceLevel.MEDIUM,
                "references": ["CIS Benchmark 3.3.3"],
            },
            {
                "check_id": "CIS-4.1.1.1",
                "title": "Ensure auditd is installed",
                "description": "Audit daemon should be installed for logging",
                "level": ComplianceLevel.HIGH,
                "references": ["CIS Benchmark 4.1.1.1"],
            },
            {
                "check_id": "CIS-5.2.1",
                "title": "Ensure permissions on /etc/ssh/sshd_config are configured",
                "description": "SSH config should be 0600 (rw-------)",
                "level": ComplianceLevel.CRITICAL,
                "references": ["CIS Benchmark 5.2.1"],
            },
            {
                "check_id": "CIS-5.2.2",
                "title": "Ensure SSH Protocol is set to 2",
                "description": "SSH should use protocol 2 only",
                "level": ComplianceLevel.HIGH,
                "references": ["CIS Benchmark 5.2.2"],
            },
            {
                "check_id": "CIS-5.2.5",
                "title": "Ensure SSH PermitRootLogin is disabled",
                "description": "Root SSH login should be disabled",
                "level": ComplianceLevel.HIGH,
                "references": ["CIS Benchmark 5.2.5"],
            },
            {
                "check_id": "CIS-5.4.1.1",
                "title": "Ensure password expiration is configured",
                "description": "Password expiration should be 365 days or less",
                "level": ComplianceLevel.MEDIUM,
                "references": ["CIS Benchmark 5.4.1.1"],
            },
            {
                "check_id": "CIS-6.1.2",
                "title": "Ensure permissions on /etc/passwd are configured",
                "description": "/etc/passwd should be 0644 (rw-r--r--)",
                "level": ComplianceLevel.CRITICAL,
                "references": ["CIS Benchmark 6.1.2"],
            },
            {
                "check_id": "CIS-6.1.3",
                "title": "Ensure permissions on /etc/shadow are configured",
                "description": "/etc/shadow should be 0000 or 0400",
                "level": ComplianceLevel.CRITICAL,
                "references": ["CIS Benchmark 6.1.3"],
            },
        ]

    def validate(self, vmcraft_instance, os_info: dict[str, Any]) -> ComplianceResult:
        """
        Validate VM against CIS Benchmarks.

        Args:
            vmcraft_instance: Launched VMCraft instance
            os_info: OS information dict

        Returns:
            ComplianceResult with all check results
        """
        result = ComplianceResult(
            vm_name=vmcraft_instance.disk_path.stem if hasattr(vmcraft_instance, "disk_path") else "unknown",
            framework=ComplianceFramework.CIS_BENCHMARK,
            os_type=os_info.get("os_type"),
            os_version=os_info.get("os_version"),
        )

        self.logger.info("Running CIS Benchmark compliance checks...")

        # Run all checks
        checks = [
            self._check_bootloader_permissions(vmcraft_instance),
            self._check_core_dumps(vmcraft_instance),
            self._check_ssh_config_permissions(vmcraft_instance),
            self._check_ssh_protocol(vmcraft_instance),
            self._check_ssh_root_login(vmcraft_instance),
            self._check_passwd_permissions(vmcraft_instance),
            self._check_shadow_permissions(vmcraft_instance),
            self._check_auditd_installed(vmcraft_instance),
        ]

        # Add checks to result
        result.checks = checks
        result.total_checks = len(checks)

        # Count results
        for check in checks:
            if check.passed:
                result.passed_checks += 1
            else:
                result.failed_checks += 1

                # Count by level
                if check.level == ComplianceLevel.CRITICAL:
                    result.critical_failures += 1
                elif check.level == ComplianceLevel.HIGH:
                    result.high_failures += 1
                elif check.level == ComplianceLevel.MEDIUM:
                    result.medium_failures += 1
                elif check.level == ComplianceLevel.LOW:
                    result.low_failures += 1

        # Calculate score and compliance
        result.compliance_score = self.calculate_compliance_score(result)
        result.overall_compliant = self.is_compliant(result)

        # Mark scan complete
        result.scan_end = __import__("datetime").datetime.now()
        result.duration_seconds = (result.scan_end - result.scan_start).total_seconds()

        self.logger.info(
            f"CIS Benchmark scan complete: {result.passed_checks}/{result.total_checks} passed, "
            f"score: {result.compliance_score:.1f}%"
        )

        return result

    def _check_bootloader_permissions(self, g) -> ComplianceCheck:
        """Check bootloader config permissions."""
        grub_configs = ["/boot/grub/grub.cfg", "/boot/grub2/grub.cfg", "/boot/efi/EFI/*/grub.cfg"]

        for config_path in grub_configs:
            if g.exists(config_path):
                try:
                    stat = g.stat(config_path)
                    mode = stat.get("mode", 0) & 0o777

                    if mode == 0o600:
                        return ComplianceCheck(
                            check_id="CIS-1.4.1",
                            framework=ComplianceFramework.CIS_BENCHMARK,
                            title="Ensure permissions on bootloader config are configured",
                            description="Bootloader config permissions should be 0600",
                            passed=True,
                            level=ComplianceLevel.CRITICAL,
                            finding=f"{config_path} has correct permissions (0600)",
                        )
                    return ComplianceCheck(
                        check_id="CIS-1.4.1",
                        framework=ComplianceFramework.CIS_BENCHMARK,
                        title="Ensure permissions on bootloader config are configured",
                        description="Bootloader config permissions should be 0600",
                        passed=False,
                        level=ComplianceLevel.CRITICAL,
                        finding=f"{config_path} has incorrect permissions ({oct(mode)})",
                        remediation=f"chmod 0600 {config_path}",
                        references=["CIS Benchmark 1.4.1"],
                    )
                except Exception:
                    pass

        # Bootloader config not found
        return ComplianceCheck(
            check_id="CIS-1.4.1",
            framework=ComplianceFramework.CIS_BENCHMARK,
            title="Ensure permissions on bootloader config are configured",
            description="Bootloader config permissions should be 0600",
            passed=False,
            level=ComplianceLevel.CRITICAL,
            finding="Bootloader config not found",
            remediation="Ensure bootloader config exists with 0600 permissions",
        )

    def _check_core_dumps(self, g) -> ComplianceCheck:
        """Check if core dumps are restricted."""
        limits_conf = "/etc/security/limits.conf"

        if g.exists(limits_conf):
            try:
                content = g.read_file(limits_conf)
                if "* hard core 0" in content:
                    return ComplianceCheck(
                        check_id="CIS-1.5.1",
                        framework=ComplianceFramework.CIS_BENCHMARK,
                        title="Ensure core dumps are restricted",
                        description="Core dumps should be disabled",
                        passed=True,
                        level=ComplianceLevel.HIGH,
                        finding="Core dumps are restricted in limits.conf",
                    )
            except Exception:
                pass

        return ComplianceCheck(
            check_id="CIS-1.5.1",
            framework=ComplianceFramework.CIS_BENCHMARK,
            title="Ensure core dumps are restricted",
            description="Core dumps should be disabled",
            passed=False,
            level=ComplianceLevel.HIGH,
            finding="Core dumps are not restricted",
            remediation=f"Add '* hard core 0' to {limits_conf}",
            references=["CIS Benchmark 1.5.1"],
        )

    def _check_ssh_config_permissions(self, g) -> ComplianceCheck:
        """Check SSH config file permissions."""
        sshd_config = "/etc/ssh/sshd_config"

        if g.exists(sshd_config):
            try:
                stat = g.stat(sshd_config)
                mode = stat.get("mode", 0) & 0o777

                if mode == 0o600:
                    return ComplianceCheck(
                        check_id="CIS-5.2.1",
                        framework=ComplianceFramework.CIS_BENCHMARK,
                        title="Ensure permissions on /etc/ssh/sshd_config are configured",
                        description="SSH config should be 0600",
                        passed=True,
                        level=ComplianceLevel.CRITICAL,
                        finding=f"{sshd_config} has correct permissions (0600)",
                    )
                return ComplianceCheck(
                    check_id="CIS-5.2.1",
                    framework=ComplianceFramework.CIS_BENCHMARK,
                    title="Ensure permissions on /etc/ssh/sshd_config are configured",
                    description="SSH config should be 0600",
                    passed=False,
                    level=ComplianceLevel.CRITICAL,
                    finding=f"{sshd_config} has incorrect permissions ({oct(mode)})",
                    remediation=f"chmod 0600 {sshd_config}",
                    references=["CIS Benchmark 5.2.1"],
                )
            except Exception:
                pass

        return ComplianceCheck(
            check_id="CIS-5.2.1",
            framework=ComplianceFramework.CIS_BENCHMARK,
            title="Ensure permissions on /etc/ssh/sshd_config are configured",
            description="SSH config should be 0600",
            passed=False,
            level=ComplianceLevel.CRITICAL,
            finding="SSH config not found",
        )

    def _check_ssh_protocol(self, g) -> ComplianceCheck:
        """Check SSH protocol version."""
        sshd_config = "/etc/ssh/sshd_config"

        if g.exists(sshd_config):
            try:
                content = g.read_file(sshd_config)

                # Check for Protocol 2 (or absence of Protocol line, which defaults to 2)
                if re.search(r"^Protocol\s+1", content, re.MULTILINE):
                    return ComplianceCheck(
                        check_id="CIS-5.2.2",
                        framework=ComplianceFramework.CIS_BENCHMARK,
                        title="Ensure SSH Protocol is set to 2",
                        description="SSH should use protocol 2 only",
                        passed=False,
                        level=ComplianceLevel.HIGH,
                        finding="SSH Protocol 1 is enabled",
                        remediation="Set 'Protocol 2' in /etc/ssh/sshd_config",
                        references=["CIS Benchmark 5.2.2"],
                    )

                # Protocol 2 or not specified (defaults to 2)
                return ComplianceCheck(
                    check_id="CIS-5.2.2",
                    framework=ComplianceFramework.CIS_BENCHMARK,
                    title="Ensure SSH Protocol is set to 2",
                    description="SSH should use protocol 2 only",
                    passed=True,
                    level=ComplianceLevel.HIGH,
                    finding="SSH Protocol 2 is configured",
                )
            except Exception:
                pass

        return ComplianceCheck(
            check_id="CIS-5.2.2",
            framework=ComplianceFramework.CIS_BENCHMARK,
            title="Ensure SSH Protocol is set to 2",
            description="SSH should use protocol 2 only",
            passed=False,
            level=ComplianceLevel.HIGH,
            finding="Could not verify SSH protocol",
        )

    def _check_ssh_root_login(self, g) -> ComplianceCheck:
        """Check if SSH root login is disabled."""
        sshd_config = "/etc/ssh/sshd_config"

        if g.exists(sshd_config):
            try:
                content = g.read_file(sshd_config)

                # Check for PermitRootLogin no
                if re.search(r"^PermitRootLogin\s+no", content, re.MULTILINE | re.IGNORECASE):
                    return ComplianceCheck(
                        check_id="CIS-5.2.5",
                        framework=ComplianceFramework.CIS_BENCHMARK,
                        title="Ensure SSH PermitRootLogin is disabled",
                        description="Root SSH login should be disabled",
                        passed=True,
                        level=ComplianceLevel.HIGH,
                        finding="PermitRootLogin is disabled",
                    )

                return ComplianceCheck(
                    check_id="CIS-5.2.5",
                    framework=ComplianceFramework.CIS_BENCHMARK,
                    title="Ensure SSH PermitRootLogin is disabled",
                    description="Root SSH login should be disabled",
                    passed=False,
                    level=ComplianceLevel.HIGH,
                    finding="PermitRootLogin is not disabled",
                    remediation="Set 'PermitRootLogin no' in /etc/ssh/sshd_config",
                    references=["CIS Benchmark 5.2.5"],
                )
            except Exception:
                pass

        return ComplianceCheck(
            check_id="CIS-5.2.5",
            framework=ComplianceFramework.CIS_BENCHMARK,
            title="Ensure SSH PermitRootLogin is disabled",
            description="Root SSH login should be disabled",
            passed=False,
            level=ComplianceLevel.HIGH,
            finding="Could not verify SSH root login setting",
        )

    def _check_passwd_permissions(self, g) -> ComplianceCheck:
        """Check /etc/passwd permissions."""
        passwd_file = "/etc/passwd"

        if g.exists(passwd_file):
            try:
                stat = g.stat(passwd_file)
                mode = stat.get("mode", 0) & 0o777

                if mode == 0o644:
                    return ComplianceCheck(
                        check_id="CIS-6.1.2",
                        framework=ComplianceFramework.CIS_BENCHMARK,
                        title="Ensure permissions on /etc/passwd are configured",
                        description="/etc/passwd should be 0644",
                        passed=True,
                        level=ComplianceLevel.CRITICAL,
                        finding="/etc/passwd has correct permissions (0644)",
                    )
                return ComplianceCheck(
                    check_id="CIS-6.1.2",
                    framework=ComplianceFramework.CIS_BENCHMARK,
                    title="Ensure permissions on /etc/passwd are configured",
                    description="/etc/passwd should be 0644",
                    passed=False,
                    level=ComplianceLevel.CRITICAL,
                    finding=f"/etc/passwd has incorrect permissions ({oct(mode)})",
                    remediation="chmod 0644 /etc/passwd",
                    references=["CIS Benchmark 6.1.2"],
                )
            except Exception:
                pass

        return ComplianceCheck(
            check_id="CIS-6.1.2",
            framework=ComplianceFramework.CIS_BENCHMARK,
            title="Ensure permissions on /etc/passwd are configured",
            description="/etc/passwd should be 0644",
            passed=False,
            level=ComplianceLevel.CRITICAL,
            finding="/etc/passwd not found",
        )

    def _check_shadow_permissions(self, g) -> ComplianceCheck:
        """Check /etc/shadow permissions."""
        shadow_file = "/etc/shadow"

        if g.exists(shadow_file):
            try:
                stat = g.stat(shadow_file)
                mode = stat.get("mode", 0) & 0o777

                if mode in [0o000, 0o400]:
                    return ComplianceCheck(
                        check_id="CIS-6.1.3",
                        framework=ComplianceFramework.CIS_BENCHMARK,
                        title="Ensure permissions on /etc/shadow are configured",
                        description="/etc/shadow should be 0000 or 0400",
                        passed=True,
                        level=ComplianceLevel.CRITICAL,
                        finding=f"/etc/shadow has correct permissions ({oct(mode)})",
                    )
                return ComplianceCheck(
                    check_id="CIS-6.1.3",
                    framework=ComplianceFramework.CIS_BENCHMARK,
                    title="Ensure permissions on /etc/shadow are configured",
                    description="/etc/shadow should be 0000 or 0400",
                    passed=False,
                    level=ComplianceLevel.CRITICAL,
                    finding=f"/etc/shadow has incorrect permissions ({oct(mode)})",
                    remediation="chmod 0000 /etc/shadow",
                    references=["CIS Benchmark 6.1.3"],
                )
            except Exception:
                pass

        return ComplianceCheck(
            check_id="CIS-6.1.3",
            framework=ComplianceFramework.CIS_BENCHMARK,
            title="Ensure permissions on /etc/shadow are configured",
            description="/etc/shadow should be 0000 or 0400",
            passed=False,
            level=ComplianceLevel.CRITICAL,
            finding="/etc/shadow not found",
        )

    def _check_auditd_installed(self, g) -> ComplianceCheck:
        """Check if auditd is installed."""
        auditd_paths = ["/sbin/auditd", "/usr/sbin/auditd", "/bin/auditd"]

        for path in auditd_paths:
            if g.exists(path):
                return ComplianceCheck(
                    check_id="CIS-4.1.1.1",
                    framework=ComplianceFramework.CIS_BENCHMARK,
                    title="Ensure auditd is installed",
                    description="Audit daemon should be installed",
                    passed=True,
                    level=ComplianceLevel.HIGH,
                    finding="auditd is installed",
                )

        return ComplianceCheck(
            check_id="CIS-4.1.1.1",
            framework=ComplianceFramework.CIS_BENCHMARK,
            title="Ensure auditd is installed",
            description="Audit daemon should be installed",
            passed=False,
            level=ComplianceLevel.HIGH,
            finding="auditd is not installed",
            remediation="Install auditd package",
            references=["CIS Benchmark 4.1.1.1"],
        )
