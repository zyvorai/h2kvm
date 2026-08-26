# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/compliance/stig_validator.py
"""
STIG (Security Technical Implementation Guide) compliance validator.

Validates VMs against DISA STIG requirements.
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


class STIGValidator(ComplianceValidator):
    """
    STIG compliance validator.

    Validates common DISA STIG controls for Linux systems.
    """

    def get_framework(self) -> ComplianceFramework:
        """Get compliance framework type."""
        return ComplianceFramework.STIG

    def get_checks(self) -> list[dict[str, Any]]:
        """Get list of available STIG checks."""
        return [
            {
                "check_id": "RHEL-07-010010",
                "title": "File permissions for /etc/passwd must be 0644",
                "description": "File permissions for /etc/passwd must be 0644",
                "level": ComplianceLevel.HIGH,
                "references": ["STIG ID: RHEL-07-010010"],
            },
            {
                "check_id": "RHEL-07-010020",
                "title": "File permissions for /etc/shadow must be 0000",
                "description": "File permissions for /etc/shadow must be 0000",
                "level": ComplianceLevel.HIGH,
                "references": ["STIG ID: RHEL-07-010020"],
            },
            {
                "check_id": "RHEL-07-040110",
                "title": "SSH must be configured to use only FIPS 140-2 approved algorithms",
                "description": "SSH must use FIPS-approved ciphers",
                "level": ComplianceLevel.MEDIUM,
                "references": ["STIG ID: RHEL-07-040110"],
            },
            {
                "check_id": "RHEL-07-040310",
                "title": "SSH daemon must not permit root login",
                "description": "PermitRootLogin must be disabled",
                "level": ComplianceLevel.HIGH,
                "references": ["STIG ID: RHEL-07-040310"],
            },
            {
                "check_id": "RHEL-07-040320",
                "title": "SSH daemon must not allow authentication using an empty password",
                "description": "PermitEmptyPasswords must be disabled",
                "level": ComplianceLevel.HIGH,
                "references": ["STIG ID: RHEL-07-040320"],
            },
        ]

    def validate(self, vmcraft_instance, os_info: dict[str, Any]) -> ComplianceResult:
        """
        Validate VM against STIG requirements.

        Args:
            vmcraft_instance: Launched VMCraft instance
            os_info: OS information dict

        Returns:
            ComplianceResult with all check results
        """
        result = ComplianceResult(
            vm_name=vmcraft_instance.disk_path.stem if hasattr(vmcraft_instance, "disk_path") else "unknown",
            framework=ComplianceFramework.STIG,
            os_type=os_info.get("os_type"),
            os_version=os_info.get("os_version"),
        )

        self.logger.info("Running STIG compliance checks...")

        # Run all checks
        checks = [
            self._check_passwd_permissions(vmcraft_instance),
            self._check_shadow_permissions(vmcraft_instance),
            self._check_ssh_root_login(vmcraft_instance),
            self._check_ssh_empty_passwords(vmcraft_instance),
            self._check_ssh_fips_ciphers(vmcraft_instance),
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
            f"STIG scan complete: {result.passed_checks}/{result.total_checks} passed, "
            f"score: {result.compliance_score:.1f}%"
        )

        return result

    def _check_passwd_permissions(self, g) -> ComplianceCheck:
        """Check /etc/passwd permissions (RHEL-07-010010)."""
        passwd_file = "/etc/passwd"

        if g.exists(passwd_file):
            try:
                stat = g.stat(passwd_file)
                mode = stat.get("mode", 0) & 0o777

                if mode == 0o644:
                    return ComplianceCheck(
                        check_id="RHEL-07-010010",
                        framework=ComplianceFramework.STIG,
                        title="File permissions for /etc/passwd must be 0644",
                        description="File permissions for /etc/passwd must be 0644",
                        passed=True,
                        level=ComplianceLevel.HIGH,
                        finding="/etc/passwd has correct permissions (0644)",
                    )
                return ComplianceCheck(
                    check_id="RHEL-07-010010",
                    framework=ComplianceFramework.STIG,
                    title="File permissions for /etc/passwd must be 0644",
                    description="File permissions for /etc/passwd must be 0644",
                    passed=False,
                    level=ComplianceLevel.HIGH,
                    finding=f"/etc/passwd has incorrect permissions ({oct(mode)})",
                    remediation="chmod 0644 /etc/passwd",
                    references=["STIG ID: RHEL-07-010010"],
                )
            except Exception:
                pass

        return ComplianceCheck(
            check_id="RHEL-07-010010",
            framework=ComplianceFramework.STIG,
            title="File permissions for /etc/passwd must be 0644",
            description="File permissions for /etc/passwd must be 0644",
            passed=False,
            level=ComplianceLevel.HIGH,
            finding="/etc/passwd not found",
        )

    def _check_shadow_permissions(self, g) -> ComplianceCheck:
        """Check /etc/shadow permissions (RHEL-07-010020)."""
        shadow_file = "/etc/shadow"

        if g.exists(shadow_file):
            try:
                stat = g.stat(shadow_file)
                mode = stat.get("mode", 0) & 0o777

                if mode == 0o000:
                    return ComplianceCheck(
                        check_id="RHEL-07-010020",
                        framework=ComplianceFramework.STIG,
                        title="File permissions for /etc/shadow must be 0000",
                        description="File permissions for /etc/shadow must be 0000",
                        passed=True,
                        level=ComplianceLevel.HIGH,
                        finding="/etc/shadow has correct permissions (0000)",
                    )
                return ComplianceCheck(
                    check_id="RHEL-07-010020",
                    framework=ComplianceFramework.STIG,
                    title="File permissions for /etc/shadow must be 0000",
                    description="File permissions for /etc/shadow must be 0000",
                    passed=False,
                    level=ComplianceLevel.HIGH,
                    finding=f"/etc/shadow has incorrect permissions ({oct(mode)})",
                    remediation="chmod 0000 /etc/shadow",
                    references=["STIG ID: RHEL-07-010020"],
                )
            except Exception:
                pass

        return ComplianceCheck(
            check_id="RHEL-07-010020",
            framework=ComplianceFramework.STIG,
            title="File permissions for /etc/shadow must be 0000",
            description="File permissions for /etc/shadow must be 0000",
            passed=False,
            level=ComplianceLevel.HIGH,
            finding="/etc/shadow not found",
        )

    def _check_ssh_root_login(self, g) -> ComplianceCheck:
        """Check SSH root login (RHEL-07-040310)."""
        sshd_config = "/etc/ssh/sshd_config"

        if g.exists(sshd_config):
            try:
                content = g.read_file(sshd_config)

                if re.search(r"^PermitRootLogin\s+no", content, re.MULTILINE | re.IGNORECASE):
                    return ComplianceCheck(
                        check_id="RHEL-07-040310",
                        framework=ComplianceFramework.STIG,
                        title="SSH daemon must not permit root login",
                        description="PermitRootLogin must be disabled",
                        passed=True,
                        level=ComplianceLevel.HIGH,
                        finding="PermitRootLogin is disabled",
                    )

                return ComplianceCheck(
                    check_id="RHEL-07-040310",
                    framework=ComplianceFramework.STIG,
                    title="SSH daemon must not permit root login",
                    description="PermitRootLogin must be disabled",
                    passed=False,
                    level=ComplianceLevel.HIGH,
                    finding="PermitRootLogin is not disabled",
                    remediation="Set 'PermitRootLogin no' in /etc/ssh/sshd_config",
                    references=["STIG ID: RHEL-07-040310"],
                )
            except Exception:
                pass

        return ComplianceCheck(
            check_id="RHEL-07-040310",
            framework=ComplianceFramework.STIG,
            title="SSH daemon must not permit root login",
            description="PermitRootLogin must be disabled",
            passed=False,
            level=ComplianceLevel.HIGH,
            finding="Could not verify SSH configuration",
        )

    def _check_ssh_empty_passwords(self, g) -> ComplianceCheck:
        """Check SSH empty passwords (RHEL-07-040320)."""
        sshd_config = "/etc/ssh/sshd_config"

        if g.exists(sshd_config):
            try:
                content = g.read_file(sshd_config)

                if re.search(r"^PermitEmptyPasswords\s+no", content, re.MULTILINE | re.IGNORECASE):
                    return ComplianceCheck(
                        check_id="RHEL-07-040320",
                        framework=ComplianceFramework.STIG,
                        title="SSH daemon must not allow authentication using an empty password",
                        description="PermitEmptyPasswords must be disabled",
                        passed=True,
                        level=ComplianceLevel.HIGH,
                        finding="PermitEmptyPasswords is disabled",
                    )

                return ComplianceCheck(
                    check_id="RHEL-07-040320",
                    framework=ComplianceFramework.STIG,
                    title="SSH daemon must not allow authentication using an empty password",
                    description="PermitEmptyPasswords must be disabled",
                    passed=False,
                    level=ComplianceLevel.HIGH,
                    finding="PermitEmptyPasswords is not explicitly disabled",
                    remediation="Set 'PermitEmptyPasswords no' in /etc/ssh/sshd_config",
                    references=["STIG ID: RHEL-07-040320"],
                )
            except Exception:
                pass

        return ComplianceCheck(
            check_id="RHEL-07-040320",
            framework=ComplianceFramework.STIG,
            title="SSH daemon must not allow authentication using an empty password",
            description="PermitEmptyPasswords must be disabled",
            passed=False,
            level=ComplianceLevel.HIGH,
            finding="Could not verify SSH configuration",
        )

    def _check_ssh_fips_ciphers(self, g) -> ComplianceCheck:
        """Check SSH FIPS-approved ciphers (RHEL-07-040110)."""
        sshd_config = "/etc/ssh/sshd_config"

        # FIPS-approved ciphers
        fips_ciphers = [
            "aes128-ctr",
            "aes192-ctr",
            "aes256-ctr",
            "aes128-gcm@openssh.com",
            "aes256-gcm@openssh.com",
        ]

        if g.exists(sshd_config):
            try:
                content = g.read_file(sshd_config)

                # Look for Ciphers directive
                cipher_match = re.search(r"^Ciphers\s+(.+)$", content, re.MULTILINE | re.IGNORECASE)
                if cipher_match:
                    configured_ciphers = cipher_match.group(1).split(",")
                    configured_ciphers = [c.strip() for c in configured_ciphers]

                    # Check if all configured ciphers are FIPS-approved
                    non_fips = [c for c in configured_ciphers if c not in fips_ciphers]

                    if not non_fips:
                        return ComplianceCheck(
                            check_id="RHEL-07-040110",
                            framework=ComplianceFramework.STIG,
                            title="SSH must be configured to use only FIPS 140-2 approved algorithms",
                            description="SSH must use FIPS-approved ciphers",
                            passed=True,
                            level=ComplianceLevel.MEDIUM,
                            finding="SSH is configured with FIPS-approved ciphers only",
                        )
                    return ComplianceCheck(
                        check_id="RHEL-07-040110",
                        framework=ComplianceFramework.STIG,
                        title="SSH must be configured to use only FIPS 140-2 approved algorithms",
                        description="SSH must use FIPS-approved ciphers",
                        passed=False,
                        level=ComplianceLevel.MEDIUM,
                        finding=f"Non-FIPS ciphers detected: {', '.join(non_fips)}",
                        remediation=f"Set 'Ciphers {','.join(fips_ciphers)}' in /etc/ssh/sshd_config",
                        references=["STIG ID: RHEL-07-040110"],
                    )

                # No Ciphers directive found - using defaults (may not be FIPS)
                return ComplianceCheck(
                    check_id="RHEL-07-040110",
                    framework=ComplianceFramework.STIG,
                    title="SSH must be configured to use only FIPS 140-2 approved algorithms",
                    description="SSH must use FIPS-approved ciphers",
                    passed=False,
                    level=ComplianceLevel.MEDIUM,
                    finding="SSH ciphers not explicitly configured",
                    remediation=f"Set 'Ciphers {','.join(fips_ciphers)}' in /etc/ssh/sshd_config",
                    references=["STIG ID: RHEL-07-040110"],
                )
            except Exception:
                pass

        return ComplianceCheck(
            check_id="RHEL-07-040110",
            framework=ComplianceFramework.STIG,
            title="SSH must be configured to use only FIPS 140-2 approved algorithms",
            description="SSH must use FIPS-approved ciphers",
            passed=False,
            level=ComplianceLevel.MEDIUM,
            finding="Could not verify SSH configuration",
        )
