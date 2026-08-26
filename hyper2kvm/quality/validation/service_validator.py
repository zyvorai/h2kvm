# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/validation/service_validator.py
"""
Service validation for post-migration checks.

Validates that critical services are configured correctly after migration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .health_checker import HealthCheckResult, HealthCheckStatus, HealthCheckType

logger = logging.getLogger(__name__)


@dataclass
class ServiceCheckResult:
    """Result of service validation check."""

    service_name: str
    enabled: bool
    status: HealthCheckStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)


class ServiceValidator:
    """
    Service validator.

    Validates that critical services are enabled and configured.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize service validator.

        Args:
            logger: Logger instance
        """
        self.logger = logger

    def check_service_enabled(self, vmcraft_instance, service_name: str) -> ServiceCheckResult:
        """
        Check if service is enabled.

        Args:
            vmcraft_instance: VMCraft instance
            service_name: Service name (without .service extension)

        Returns:
            Service check result
        """
        try:
            # Check systemd service files
            service_paths = [
                f"/etc/systemd/system/{service_name}.service",
                f"/lib/systemd/system/{service_name}.service",
                f"/usr/lib/systemd/system/{service_name}.service",
            ]

            service_exists = False
            service_path = None

            for path in service_paths:
                if vmcraft_instance.exists(path):
                    service_exists = True
                    service_path = path
                    break

            if not service_exists:
                return ServiceCheckResult(
                    service_name=service_name,
                    enabled=False,
                    status=HealthCheckStatus.WARN,
                    message=f"Service {service_name} not found",
                    details={"paths_checked": service_paths},
                )

            # Check if enabled via symlink in multi-user.target.wants
            wants_path = f"/etc/systemd/system/multi-user.target.wants/{service_name}.service"
            enabled = vmcraft_instance.exists(wants_path)

            if enabled:
                return ServiceCheckResult(
                    service_name=service_name,
                    enabled=True,
                    status=HealthCheckStatus.PASS,
                    message=f"Service {service_name} is enabled",
                    details={"service_path": service_path, "wants_path": wants_path},
                )
            return ServiceCheckResult(
                service_name=service_name,
                enabled=False,
                status=HealthCheckStatus.WARN,
                message=f"Service {service_name} exists but is not enabled",
                details={"service_path": service_path},
            )

        except Exception as e:
            return ServiceCheckResult(
                service_name=service_name,
                enabled=False,
                status=HealthCheckStatus.ERROR,
                message=f"Check failed: {e}",
            )

    def validate_critical_services(
        self, vmcraft_instance, services: list[str] | None = None
    ) -> HealthCheckResult:
        """
        Validate critical services.

        Args:
            vmcraft_instance: VMCraft instance
            services: List of service names to check (default: common critical services)

        Returns:
            Health check result
        """
        import time

        start = time.time()

        if services is None:
            services = [
                "sshd",
                "systemd-networkd",
                "NetworkManager",
                "firewalld",
                "chronyd",
            ]

        try:
            results = []
            for service in services:
                result = self.check_service_enabled(vmcraft_instance, service)
                results.append(result)

            enabled_count = sum(1 for r in results if r.enabled)
            total = len(results)

            duration = (time.time() - start) * 1000

            if enabled_count == total:
                status = HealthCheckStatus.PASS
                message = f"All {total} critical services are enabled"
            elif enabled_count > 0:
                status = HealthCheckStatus.WARN
                message = f"{enabled_count}/{total} critical services are enabled"
            else:
                status = HealthCheckStatus.WARN
                message = "No critical services are enabled"

            return HealthCheckResult(
                check_id="critical_services",
                check_type=HealthCheckType.SERVICE,
                name="Critical Services Validation",
                status=status,
                message=message,
                details={
                    "total_services": total,
                    "enabled_count": enabled_count,
                    "services": [
                        {
                            "name": r.service_name,
                            "enabled": r.enabled,
                            "status": r.status.value,
                        }
                        for r in results
                    ],
                },
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return HealthCheckResult(
                check_id="critical_services",
                check_type=HealthCheckType.SERVICE,
                name="Critical Services Validation",
                status=HealthCheckStatus.ERROR,
                message=f"Validation failed: {e}",
                duration_ms=duration,
            )
