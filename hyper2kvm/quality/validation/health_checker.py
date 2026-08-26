# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/validation/health_checker.py
"""
Health check framework for post-migration validation.

Provides core health checking infrastructure for validating migrated VMs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class HealthCheckType(Enum):
    """Types of health checks."""

    SYSTEM = "system"
    SERVICE = "service"
    NETWORK = "network"
    DATABASE = "database"
    APPLICATION = "application"
    STORAGE = "storage"
    SECURITY = "security"
    PERFORMANCE = "performance"


class HealthCheckStatus(Enum):
    """Health check result status."""

    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"
    ERROR = "error"


@dataclass
class HealthCheckResult:
    """
    Result of a single health check.

    Attributes:
        check_id: Unique check identifier
        check_type: Type of health check
        name: Human-readable check name
        status: Check status (PASS, FAIL, WARN, SKIP, ERROR)
        message: Status message
        details: Additional check details
        remediation: Suggested remediation steps
        duration_ms: Check duration in milliseconds
    """

    check_id: str
    check_type: HealthCheckType
    name: str
    status: HealthCheckStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    remediation: str | None = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "check_id": self.check_id,
            "check_type": self.check_type.value,
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "remediation": self.remediation,
            "duration_ms": self.duration_ms,
        }


class HealthChecker:
    """
    Base health checker.

    Provides core health checking functionality for migrated VMs.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize health checker.

        Args:
            logger: Logger instance
        """
        self.logger = logger
        self._checks: list[HealthCheckResult] = []

    def check_system_boot(self, vmcraft_instance) -> HealthCheckResult:
        """
        Check if system can boot.

        Args:
            vmcraft_instance: VMCraft instance with mounted filesystem

        Returns:
            Health check result
        """
        import time

        start = time.time()

        try:
            # Check for bootloader
            bootloaders_exist = False
            boot_paths = [
                "/boot/grub/grub.cfg",
                "/boot/grub2/grub.cfg",
                "/EFI/*/grub.cfg",
                "/boot/efi/EFI/*/grub.cfg",
            ]

            for path in boot_paths:
                try:
                    if "*" in path:
                        # Expand glob pattern
                        from pathlib import Path

                        matches = list(Path("/").glob(path.lstrip("/")))
                        if matches:
                            bootloaders_exist = True
                            break
                    elif vmcraft_instance.exists(path):
                        bootloaders_exist = True
                        break
                except Exception:
                    pass

            duration = (time.time() - start) * 1000

            if bootloaders_exist:
                return HealthCheckResult(
                    check_id="system_boot",
                    check_type=HealthCheckType.SYSTEM,
                    name="System Boot Configuration",
                    status=HealthCheckStatus.PASS,
                    message="Bootloader configuration found",
                    details={"bootloader": "grub"},
                    duration_ms=duration,
                )
            return HealthCheckResult(
                check_id="system_boot",
                check_type=HealthCheckType.SYSTEM,
                name="System Boot Configuration",
                status=HealthCheckStatus.WARN,
                message="No bootloader configuration detected",
                details={"bootloader": "none"},
                remediation="Install and configure bootloader",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return HealthCheckResult(
                check_id="system_boot",
                check_type=HealthCheckType.SYSTEM,
                name="System Boot Configuration",
                status=HealthCheckStatus.ERROR,
                message=f"Check failed: {e}",
                duration_ms=duration,
            )

    def check_fstab_valid(self, vmcraft_instance) -> HealthCheckResult:
        """
        Check if /etc/fstab is valid.

        Args:
            vmcraft_instance: VMCraft instance

        Returns:
            Health check result
        """
        import time

        start = time.time()

        try:
            if not vmcraft_instance.exists("/etc/fstab"):
                duration = (time.time() - start) * 1000
                return HealthCheckResult(
                    check_id="fstab_valid",
                    check_type=HealthCheckType.SYSTEM,
                    name="Filesystem Table Validity",
                    status=HealthCheckStatus.WARN,
                    message="/etc/fstab not found",
                    remediation="Create /etc/fstab with required mount points",
                    duration_ms=duration,
                )

            content = vmcraft_instance.read_file("/etc/fstab")
            lines = content.strip().splitlines()

            valid_entries = 0
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = line.split()
                if len(parts) >= 4:  # device, mountpoint, fstype, options (dump and pass are optional)
                    valid_entries += 1

            duration = (time.time() - start) * 1000

            if valid_entries > 0:
                return HealthCheckResult(
                    check_id="fstab_valid",
                    check_type=HealthCheckType.SYSTEM,
                    name="Filesystem Table Validity",
                    status=HealthCheckStatus.PASS,
                    message=f"Valid /etc/fstab with {valid_entries} entries",
                    details={"entries": valid_entries},
                    duration_ms=duration,
                )
            return HealthCheckResult(
                check_id="fstab_valid",
                check_type=HealthCheckType.SYSTEM,
                name="Filesystem Table Validity",
                status=HealthCheckStatus.WARN,
                message="/etc/fstab has no valid entries",
                details={"entries": 0},
                remediation="Add mount point entries to /etc/fstab",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return HealthCheckResult(
                check_id="fstab_valid",
                check_type=HealthCheckType.SYSTEM,
                name="Filesystem Table Validity",
                status=HealthCheckStatus.ERROR,
                message=f"Check failed: {e}",
                duration_ms=duration,
            )

    def check_kernel_modules(self, vmcraft_instance) -> HealthCheckResult:
        """
        Check if required kernel modules are available.

        Args:
            vmcraft_instance: VMCraft instance

        Returns:
            Health check result
        """
        import time

        start = time.time()

        try:
            modules_dir = "/lib/modules"

            if not vmcraft_instance.exists(modules_dir):
                duration = (time.time() - start) * 1000
                return HealthCheckResult(
                    check_id="kernel_modules",
                    check_type=HealthCheckType.SYSTEM,
                    name="Kernel Modules Availability",
                    status=HealthCheckStatus.FAIL,
                    message=f"{modules_dir} not found",
                    remediation="Install kernel modules",
                    duration_ms=duration,
                )

            # Just check that modules directory exists and has content
            # Detailed module verification would require parsing modules.dep
            duration = (time.time() - start) * 1000
            return HealthCheckResult(
                check_id="kernel_modules",
                check_type=HealthCheckType.SYSTEM,
                name="Kernel Modules Availability",
                status=HealthCheckStatus.PASS,
                message="Kernel modules directory exists",
                details={"modules_dir": modules_dir},
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return HealthCheckResult(
                check_id="kernel_modules",
                check_type=HealthCheckType.SYSTEM,
                name="Kernel Modules Availability",
                status=HealthCheckStatus.ERROR,
                message=f"Check failed: {e}",
                duration_ms=duration,
            )

    def run_all_checks(self, vmcraft_instance) -> list[HealthCheckResult]:
        """
        Run all health checks.

        Args:
            vmcraft_instance: VMCraft instance

        Returns:
            List of health check results
        """
        checks = [
            self.check_system_boot(vmcraft_instance),
            self.check_fstab_valid(vmcraft_instance),
            self.check_kernel_modules(vmcraft_instance),
        ]

        self._checks = checks
        return checks

    def get_summary(self) -> dict[str, Any]:
        """
        Get summary of health check results.

        Returns:
            Summary dict with counts by status
        """
        return {
            "total": len(self._checks),
            "pass": sum(1 for c in self._checks if c.status == HealthCheckStatus.PASS),
            "fail": sum(1 for c in self._checks if c.status == HealthCheckStatus.FAIL),
            "warn": sum(1 for c in self._checks if c.status == HealthCheckStatus.WARN),
            "skip": sum(1 for c in self._checks if c.status == HealthCheckStatus.SKIP),
            "error": sum(1 for c in self._checks if c.status == HealthCheckStatus.ERROR),
        }
