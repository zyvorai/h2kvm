# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Security Operations.

Provides security-related and disaster recovery operations for VMCraft
via composition. Merges SecurityOpsMixin + DisasterRecoveryMixin.
"""

from __future__ import annotations

from typing import Any


# This class is a thin delegating facade over `host`'s internal dispatch
# helper (composition pattern merging SecurityOpsMixin + DisasterRecoveryMixin
# into one API surface); accessing host._dispatch_manager_attr_call is tight,
# deliberate coupling rather than reaching into an unrelated class, and the
# large method count mirrors the breadth of operations it exposes.
# pylint: disable=protected-access
# pylint: disable-next=too-many-public-methods
class SecurityOps:
    """Security operations via composition."""

    def __init__(self, host) -> None:
        self._host = host

    # === Container and Bootloader Detection (from SecurityOpsMixin) ===

    def detect_containers(self) -> dict[str, Any]:
        """Detect container runtime installations (Docker, Podman, LXC, systemd-nspawn)."""
        return self._host._dispatch_manager_attr_call("_os_inspector", "detect_containers")

    def is_inside_container(self) -> dict[str, Any]:
        """Check if the inspected OS is running inside a container."""
        return self._host._dispatch_manager_attr_call("_os_inspector", "is_inside_container")

    def detect_bootloader(self) -> dict[str, Any]:
        """Detect bootloader configuration (GRUB2, systemd-boot, UEFI, LILO)."""
        return self._host._dispatch_manager_attr_call("_os_inspector", "detect_bootloader")

    def get_bootloader_entries(self) -> list[dict[str, Any]]:
        """Get boot loader menu entries."""
        return self._host._dispatch_manager_attr_call("_os_inspector", "get_bootloader_entries")

    # === Security Module Detection (from SecurityOpsMixin) ===

    def detect_selinux(self) -> dict[str, Any]:
        """Detect SELinux configuration and status."""
        return self._host._dispatch_manager_attr_call("_security_auditor", "detect_selinux")

    def detect_apparmor(self) -> dict[str, Any]:
        """Detect AppArmor configuration and status."""
        return self._host._dispatch_manager_attr_call("_security_auditor", "detect_apparmor")

    def get_security_modules(self) -> dict[str, Any]:
        """Get comprehensive security module information (SELinux, AppArmor)."""
        return self._host._dispatch_manager_attr_call("_security_auditor", "get_security_modules")

    # === Package Manager Operations (from SecurityOpsMixin) ===

    def query_package(self, package_name: str, manager: str = "auto") -> dict[str, Any]:
        """Query installed package information (RPM, APT, Pacman)."""
        return self._host._dispatch_manager_attr_call(
            "_security_auditor", "query_package", package_name, manager
        )

    def list_installed_packages(self, manager: str = "auto", limit: int = 0) -> list[dict[str, str]]:
        """List all installed packages."""
        return self._host._dispatch_manager_attr_call(
            "_security_auditor", "list_installed_packages", manager, limit
        )

    # === Cloud Optimization (from SecurityOpsMixin) ===

    def analyze_cloud_readiness(self, system_info: dict[str, Any]) -> dict[str, Any]:
        """Analyze system readiness for cloud migration."""
        return self._host._dispatch_manager_attr_call(
            "_cloud_optimizer", "analyze_cloud_readiness", system_info
        )

    def recommend_instance_type(
        self, requirements: dict[str, Any], cloud_provider: str = "aws"
    ) -> dict[str, Any]:
        """Recommend optimal cloud instance type."""
        return self._host._dispatch_manager_attr_call(
            "_cloud_optimizer", "recommend_instance_type", requirements, cloud_provider
        )

    def calculate_cloud_costs(
        self, usage_profile: dict[str, Any], cloud_provider: str = "aws"
    ) -> dict[str, Any]:
        """Calculate projected cloud costs."""
        return self._host._dispatch_manager_attr_call(
            "_cloud_optimizer", "calculate_cloud_costs", usage_profile, cloud_provider
        )

    def compare_cloud_providers(self, requirements: dict[str, Any]) -> dict[str, Any]:
        """Compare costs across multiple cloud providers."""
        return self._host._dispatch_manager_attr_call(
            "_cloud_optimizer", "compare_cloud_providers", requirements
        )

    def generate_migration_plan(
        self, system_info: dict[str, Any], target_cloud: str = "aws"
    ) -> dict[str, Any]:
        """Generate comprehensive cloud migration plan."""
        return self._host._dispatch_manager_attr_call(
            "_cloud_optimizer", "generate_migration_plan", system_info, target_cloud
        )

    def optimize_for_cloud(self, configuration: dict[str, Any]) -> dict[str, Any]:
        """Optimize system configuration for cloud environment."""
        return self._host._dispatch_manager_attr_call(
            "_cloud_optimizer", "optimize_for_cloud", configuration
        )

    # === Disaster Recovery (from DisasterRecoveryMixin) ===

    def assess_recovery_requirements(self, system_info: dict[str, Any]) -> dict[str, Any]:
        """Assess disaster recovery requirements."""
        return self._host._dispatch_manager_attr_call(
            "_disaster_recovery", "assess_recovery_requirements", system_info
        )

    def create_backup_strategy(self, requirements: dict[str, Any]) -> dict[str, Any]:
        """Create comprehensive backup strategy."""
        return self._host._dispatch_manager_attr_call(
            "_disaster_recovery", "create_backup_strategy", requirements
        )

    def calculate_rto_rpo(self, backup_config: dict[str, Any]) -> dict[str, Any]:
        """Calculate achievable RTO and RPO."""
        return self._host._dispatch_manager_attr_call(
            "_disaster_recovery", "calculate_rto_rpo", backup_config
        )

    def create_failover_procedure(self, system_config: dict[str, Any]) -> dict[str, Any]:
        """Create failover procedure documentation."""
        return self._host._dispatch_manager_attr_call(
            "_disaster_recovery", "create_failover_procedure", system_config
        )

    def test_dr_plan(self, dr_config: dict[str, Any]) -> dict[str, Any]:
        """Simulate DR plan testing."""
        return self._host._dispatch_manager_attr_call("_disaster_recovery", "test_dr_plan", dr_config)

    def generate_dr_report(self, system_info: dict[str, Any]) -> dict[str, Any]:
        """Generate comprehensive DR report."""
        return self._host._dispatch_manager_attr_call(
            "_disaster_recovery", "generate_dr_report", system_info
        )
