# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/validation/network_validator.py
"""
Network validation for post-migration checks.

Validates network configuration after migration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .health_checker import HealthCheckResult, HealthCheckStatus, HealthCheckType

logger = logging.getLogger(__name__)


@dataclass
class NetworkCheckResult:
    """Result of network validation check."""

    check_name: str
    status: HealthCheckStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)


class NetworkValidator:
    """
    Network validator.

    Validates network configuration and connectivity.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize network validator.

        Args:
            logger: Logger instance
        """
        self.logger = logger

    def check_network_interfaces(self, vmcraft_instance) -> HealthCheckResult:
        """
        Check network interface configuration.

        Args:
            vmcraft_instance: VMCraft instance

        Returns:
            Health check result
        """
        import time

        start = time.time()

        try:
            # Check for network configuration files
            config_files = [
                "/etc/sysconfig/network-scripts/ifcfg-*",
                "/etc/network/interfaces",
                "/etc/systemd/network/*.network",
                "/etc/NetworkManager/system-connections/*",
            ]

            found_configs = []
            for pattern in config_files:
                # Simple check for config file existence
                if "*" not in pattern and vmcraft_instance.exists(pattern):
                    found_configs.append(pattern)

            duration = (time.time() - start) * 1000

            if found_configs:
                return HealthCheckResult(
                    check_id="network_interfaces",
                    check_type=HealthCheckType.NETWORK,
                    name="Network Interface Configuration",
                    status=HealthCheckStatus.PASS,
                    message=f"Found {len(found_configs)} network configuration(s)",
                    details={"configs": found_configs},
                    duration_ms=duration,
                )
            return HealthCheckResult(
                check_id="network_interfaces",
                check_type=HealthCheckType.NETWORK,
                name="Network Interface Configuration",
                status=HealthCheckStatus.WARN,
                message="No network configuration files found",
                remediation="Configure network interfaces",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return HealthCheckResult(
                check_id="network_interfaces",
                check_type=HealthCheckType.NETWORK,
                name="Network Interface Configuration",
                status=HealthCheckStatus.ERROR,
                message=f"Check failed: {e}",
                duration_ms=duration,
            )

    def check_dns_configuration(self, vmcraft_instance) -> HealthCheckResult:
        """
        Check DNS configuration.

        Args:
            vmcraft_instance: VMCraft instance

        Returns:
            Health check result
        """
        import time

        start = time.time()

        try:
            resolv_conf = "/etc/resolv.conf"

            if not vmcraft_instance.exists(resolv_conf):
                duration = (time.time() - start) * 1000
                return HealthCheckResult(
                    check_id="dns_config",
                    check_type=HealthCheckType.NETWORK,
                    name="DNS Configuration",
                    status=HealthCheckStatus.WARN,
                    message="/etc/resolv.conf not found",
                    remediation="Configure DNS nameservers",
                    duration_ms=duration,
                )

            content = vmcraft_instance.read_file(resolv_conf)
            nameservers = [line for line in content.splitlines() if line.strip().startswith("nameserver")]

            duration = (time.time() - start) * 1000

            if nameservers:
                return HealthCheckResult(
                    check_id="dns_config",
                    check_type=HealthCheckType.NETWORK,
                    name="DNS Configuration",
                    status=HealthCheckStatus.PASS,
                    message=f"Found {len(nameservers)} nameserver(s)",
                    details={"nameservers": nameservers},
                    duration_ms=duration,
                )
            return HealthCheckResult(
                check_id="dns_config",
                check_type=HealthCheckType.NETWORK,
                name="DNS Configuration",
                status=HealthCheckStatus.WARN,
                message="No nameservers configured in /etc/resolv.conf",
                remediation="Add nameserver entries to /etc/resolv.conf",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return HealthCheckResult(
                check_id="dns_config",
                check_type=HealthCheckType.NETWORK,
                name="DNS Configuration",
                status=HealthCheckStatus.ERROR,
                message=f"Check failed: {e}",
                duration_ms=duration,
            )

    def validate_network(self, vmcraft_instance) -> list[HealthCheckResult]:
        """
        Run all network validation checks.

        Args:
            vmcraft_instance: VMCraft instance

        Returns:
            List of health check results
        """
        return [
            self.check_network_interfaces(vmcraft_instance),
            self.check_dns_configuration(vmcraft_instance),
        ]
