# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/ai/health.py
"""
Post-migration health check engine.

Analyses the fixer report to flag potential boot issues without performing
any additional disk I/O.
"""

from __future__ import annotations

from typing import Any

from .models import HealthCheck, HealthReport, HealthStatus

# ---------------------------------------------------------------------------
# Health check definitions
# ---------------------------------------------------------------------------

_HealthCheckDef = dict[str, Any]

HEALTH_CHECKS: list[_HealthCheckDef] = [
    {
        "name": "boot_config",
        "label": "Bootloader configuration",
        "check": "_check_boot_config",
    },
    {
        "name": "fstab_valid",
        "label": "fstab validity",
        "check": "_check_fstab",
    },
    {
        "name": "virtio_drivers",
        "label": "Virtio driver presence",
        "check": "_check_virtio_drivers",
    },
    {
        "name": "no_vmware_remnants",
        "label": "VMware remnant removal",
        "check": "_check_vmware_remnants",
    },
    {
        "name": "network_config",
        "label": "Network configuration",
        "check": "_check_network",
    },
]


class HealthEngine:  # pylint: disable=too-few-public-methods  # single-purpose engine, private methods are individual checks
    """Run post-migration health checks against the fixer report."""

    def check(self, fixer_report: dict[str, Any] | None) -> HealthReport:
        """Evaluate all health checks and return a :class:`HealthReport`."""
        if not fixer_report:
            return HealthReport(
                checks=[
                    HealthCheck(
                        name="no_report", status=HealthStatus.SKIP, message="No fixer report available"
                    )
                ],
                overall_status=HealthStatus.SKIP,
            )

        checks: list[HealthCheck] = []
        for hdef in HEALTH_CHECKS:
            method = getattr(self, hdef["check"], None)
            if method is None:
                checks.append(
                    HealthCheck(
                        name=hdef["name"],
                        status=HealthStatus.SKIP,
                        message=f"Check {hdef['name']} not implemented",
                    )
                )
                continue
            try:
                result = method(fixer_report)
                checks.append(result)
            except Exception as exc:  # pylint: disable=broad-exception-caught  # one check must not abort the rest
                checks.append(
                    HealthCheck(
                        name=hdef["name"],
                        status=HealthStatus.WARN,
                        message=f"Check raised exception: {exc}",
                    )
                )

        overall = self._aggregate_status(checks)
        return HealthReport(checks=checks, overall_status=overall)

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_boot_config(report: dict[str, Any]) -> HealthCheck:
        analysis = report.get("analysis", {}) or {}
        boot_mode = analysis.get("boot_mode", "")
        grub_ok = analysis.get("grub_installed", None)
        actions = report.get("actions", []) or []
        grub_actions = [a for a in actions if "grub" in str(a).lower()]

        if grub_ok is False:
            return HealthCheck(
                name="boot_config",
                status=HealthStatus.FAIL,
                message="GRUB not detected after fixes",
                details={"boot_mode": boot_mode, "grub_actions": grub_actions},
            )
        if grub_actions:
            return HealthCheck(
                name="boot_config",
                status=HealthStatus.PASS,
                message=f"Bootloader configured ({boot_mode or 'bios'})",
                details={"boot_mode": boot_mode, "grub_actions": grub_actions},
            )
        return HealthCheck(
            name="boot_config",
            status=HealthStatus.PASS,
            message=f"Boot configuration present ({boot_mode or 'bios'})",
            details={"boot_mode": boot_mode},
        )

    @staticmethod
    def _check_fstab(report: dict[str, Any]) -> HealthCheck:
        actions = report.get("actions", []) or []
        fstab_actions = [a for a in actions if "fstab" in str(a).lower()]
        warnings = report.get("warnings", []) or []
        fstab_warnings = [w for w in warnings if "fstab" in str(w).lower()]

        if fstab_warnings:
            return HealthCheck(
                name="fstab_valid",
                status=HealthStatus.WARN,
                message=f"fstab warnings detected: {len(fstab_warnings)}",
                details={"warnings": fstab_warnings, "actions": fstab_actions},
            )
        if fstab_actions:
            return HealthCheck(
                name="fstab_valid",
                status=HealthStatus.PASS,
                message="fstab stabilised successfully",
                details={"actions": fstab_actions},
            )
        return HealthCheck(
            name="fstab_valid",
            status=HealthStatus.PASS,
            message="fstab appears valid (no changes needed)",
        )

    @staticmethod
    def _check_virtio_drivers(report: dict[str, Any]) -> HealthCheck:
        analysis = report.get("analysis", {}) or {}
        actions = report.get("actions", []) or []
        initramfs_actions = [
            a for a in actions if "initramfs" in str(a).lower() or "dracut" in str(a).lower()
        ]
        drivers = analysis.get("initramfs_drivers", []) or []

        virtio_found = any("virtio" in str(d).lower() for d in drivers)
        virtio_injected = any("virtio" in str(a).lower() for a in initramfs_actions)

        if virtio_found or virtio_injected:
            return HealthCheck(
                name="virtio_drivers",
                status=HealthStatus.PASS,
                message="Virtio drivers present in initramfs",
                details={"drivers": drivers, "actions": initramfs_actions},
            )
        # Not necessarily a failure -- some guests don't need virtio
        return HealthCheck(
            name="virtio_drivers",
            status=HealthStatus.WARN,
            message="Virtio drivers not confirmed in initramfs",
            details={"drivers": drivers},
        )

    @staticmethod
    def _check_vmware_remnants(report: dict[str, Any]) -> HealthCheck:
        actions = report.get("actions", []) or []
        vmware_actions = [a for a in actions if "vmware" in str(a).lower()]
        warnings = report.get("warnings", []) or []
        vmware_warnings = [w for w in warnings if "vmware" in str(w).lower()]

        if vmware_warnings:
            return HealthCheck(
                name="no_vmware_remnants",
                status=HealthStatus.WARN,
                message="VMware remnants may still be present",
                details={"warnings": vmware_warnings},
            )
        if vmware_actions:
            return HealthCheck(
                name="no_vmware_remnants",
                status=HealthStatus.PASS,
                message="VMware components cleaned up",
                details={"actions": vmware_actions},
            )
        return HealthCheck(
            name="no_vmware_remnants",
            status=HealthStatus.PASS,
            message="No VMware remnants detected",
        )

    @staticmethod
    def _check_network(report: dict[str, Any]) -> HealthCheck:
        actions = report.get("actions", []) or []
        net_actions = [
            a for a in actions if any(k in str(a).lower() for k in ("network", "eth", "ens", "ifcfg"))
        ]
        warnings = report.get("warnings", []) or []
        net_warnings = [w for w in warnings if "network" in str(w).lower()]

        if net_warnings:
            return HealthCheck(
                name="network_config",
                status=HealthStatus.WARN,
                message="Network configuration warnings present",
                details={"warnings": net_warnings},
            )
        return HealthCheck(
            name="network_config",
            status=HealthStatus.PASS,
            message="Network configuration appears intact",
            details={"actions": net_actions},
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_status(checks: list[HealthCheck]) -> HealthStatus:
        """Compute overall status from individual checks."""
        has_fail = any(c.status == HealthStatus.FAIL for c in checks)
        has_warn = any(c.status == HealthStatus.WARN for c in checks)
        if has_fail:
            return HealthStatus.FAIL
        if has_warn:
            return HealthStatus.WARN
        if all(c.status == HealthStatus.SKIP for c in checks):
            return HealthStatus.SKIP
        return HealthStatus.PASS
