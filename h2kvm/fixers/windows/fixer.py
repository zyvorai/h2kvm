# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/windows/fixer.py
"""
Thin façade for Windows fixing.

This module intentionally stays small and delegates the heavy lifting to:
  - virtio/core.py (driver discovery + injection + staging + BCD backup hints)
  - registry_core.py (offline hive edits: SYSTEM services/CDD + SOFTWARE DevicePath)
  - network_fixer.py (best-effort network config retention via firstboot PowerShell)
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    import guestfs  # type: ignore
except ImportError:
    guestfs = None  # type: ignore

from h2kvm.core.exceptions import WindowsFixerError
from h2kvm.core.logging_utils import safe_logger as _safe_logger_base

from .activedirectory.cleanup import (
    CleanupMethod,
    stage_cleanup_script,
)
from .activedirectory.extractor import extract_domain_info
from .activedirectory.rejoin import (
    DomainRejoinMethod,
    stage_domain_rejoin_script,
)
from .appcompat.detector import (
    detect_dongle_drivers,
    detect_hardware_dependent_apps,
    detect_license_services,
)
from .appcompat.reporter import generate_compatibility_report
from .appcompat.sqlserver import (
    detect_sql_server_instances,
    generate_sql_reconfiguration_script,
)
from .bitlocker import check_bitlocker_before_migration, detect_bitlocker
from .disk_online import stage_disk_online
from .firewall import get_firewall_migration_instructions, stage_firewall_export_script
from .license.extractor import extract_license_info
from .license.reactivator import stage_reactivation_script
from .network_fixer import retain_windows_network_config
from .performance.balloon import configure_balloon_driver
from .performance.hyperv_cleanup import cleanup_hyperv_enlightenments
from .performance.msi import enable_msi_interrupts
from .performance.trim import enable_trim_discard
from .rdp import enable_rdp_if_disabled, verify_rdp_enabled
from .registry.encoding import _close_best_effort, _detect_current_controlset
from .registry.io import detect_windows_hive, download_and_open_hive
from .route_cleanup import stage_route_cleanup
from .virtio.core import (
    inject_virtio_drivers,
    is_windows,
    windows_bcd_actual_fix,
)
from .virtio_warning import get_virtio_download_url, warn_no_virtio_drivers

if TYPE_CHECKING:
    import logging


def _safe_logger(self) -> logging.Logger:
    """Wrapper for backward compatibility - calls shared safe_logger."""
    return _safe_logger_base(self, "h2kvm.windows_fixer")


class WindowsFixer:
    """
    Optional OO wrapper for callers that expect a fixer object.

    This class is intentionally minimal: it forwards to module-level functions
    implemented elsewhere.
    """

    def __init__(self, **kwargs: Any):
        # Allow ad-hoc construction in tests; callers can also set attributes after init.
        # Typical attributes used:
        #   logger, dry_run, virtio_drivers_dir, force_virtio_overwrite, export_report,
        #   enable_virtio_gpu, enable_virtio_input, enable_virtio_fs, enable_virtio_serial, enable_virtio_rng,
        #   virtio_config_path, virtio_config,
        #   inspect_root
        for k, v in kwargs.items():
            setattr(self, k, v)

    def is_windows(self, g: guestfs.GuestFS) -> bool:
        """Check whether the mounted guest filesystem is a Windows install."""
        return is_windows(self, g)

    def windows_bcd_actual_fix(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Repair the Windows Boot Configuration Data (BCD) store for KVM boot."""
        return windows_bcd_actual_fix(self, g)

    def inject_virtio_drivers(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Discover, stage, and inject VirtIO drivers into the Windows guest."""
        return inject_virtio_drivers(self, g)

    def retain_windows_network_config(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Stage a first-boot script to retain the guest's network configuration."""
        return retain_windows_network_config(self, g)

    def stage_route_cleanup(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Stage duplicate route cleanup script for first boot."""
        return stage_route_cleanup(self, g)

    def stage_disk_online(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Stage VirtIO disk online script for first boot."""
        return stage_disk_online(self, g)

    def extract_license_info(self, g: guestfs.GuestFS, root: str):
        """Extract Windows license information from offline registry."""
        return extract_license_info(g, root)

    def stage_license_reactivation(
        self,
        g: guestfs.GuestFS,
        root: str,
        license_info,
        kms_server_override=None,
        kms_port_override=None,
    ):
        """Stage license reactivation script for first boot."""
        return stage_reactivation_script(g, root, license_info, kms_server_override, kms_port_override)

    def extract_domain_info(self, g: guestfs.GuestFS, root: str):
        """Extract Active Directory domain membership information."""
        return extract_domain_info(g, root)

    def stage_domain_rejoin(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        g: guestfs.GuestFS,
        root: str,
        domain_info,
        method=DomainRejoinMethod.MANUAL,
        domain_override=None,
        ou_path=None,
        unattended_join_file=None,
    ):
        # reason: thin facade forwarding all of stage_domain_rejoin_script()'s options.
        """Stage domain rejoin script for first boot."""
        return stage_domain_rejoin_script(
            g, root, domain_info, method, domain_override, ou_path, unattended_join_file
        )

    def stage_ad_cleanup(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        g: guestfs.GuestFS,
        root: str,
        old_computer_name: str,
        domain: str,
        method=CleanupMethod.POWERSHELL_SCRIPT,
        ou_path=None,
    ):
        # reason: thin facade forwarding all of stage_cleanup_script()'s options.
        """Stage Active Directory computer object cleanup script.

        Args:
            g: GuestFS instance
            root: Windows root path
            old_computer_name: Old computer name to remove from AD
            domain: Domain name
            method: Cleanup method (default: PowerShell)
            ou_path: Organizational Unit path (optional)

        Returns:
            Dict with staging results
        """
        return stage_cleanup_script(g, root, old_computer_name, domain, method, ou_path)

    def detect_application_compatibility(self, g: guestfs.GuestFS, root: str) -> dict[str, Any]:
        """Detect application compatibility issues for migration.

        Scans for:
        - Hardware-dependent applications
        - License manager services
        - Hardware dongle drivers
        - SQL Server instances

        Returns:
            Dict with findings and compatibility report
        """
        logger = _safe_logger(self)
        logger.info("Running application compatibility detection")

        results = {
            "hardware_apps": [],
            "license_services": [],
            "dongle_drivers": [],
            "sql_instances": [],
            "report_json": None,
            "report_markdown": None,
        }

        try:
            # Detect hardware-dependent applications
            results["hardware_apps"] = detect_hardware_dependent_apps(g, root)

            # Detect license services
            results["license_services"] = detect_license_services(g, root)

            # Detect dongle drivers
            results["dongle_drivers"] = detect_dongle_drivers(g, root)

            # Detect SQL Server instances
            results["sql_instances"] = detect_sql_server_instances(g, root)

            # Generate compatibility report
            hostname = self._extract_hostname(g, root)

            report = generate_compatibility_report(
                hardware_apps=results["hardware_apps"],
                license_services=results["license_services"],
                dongle_drivers=results["dongle_drivers"],
                sql_instances=results["sql_instances"],
                hostname=hostname,
            )

            results["report_json"] = report.to_json()
            results["report_markdown"] = report.to_markdown()

            logger.info(
                "Compatibility scan complete: %d findings (%d critical, %d high)",
                report.total_findings,
                report.critical_findings,
                report.high_findings,
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort fixer step -- must not abort the whole migration over
            # one guest's compatibility-scan quirk.
            logger.exception(
                "Application compatibility detection failed while scanning Windows registry: %s. "
                "Some hardware-dependent apps or license services may need manual attention after migration.",
                e,
            )
            logger.debug("Compatibility detection error", exc_info=True)

        return results

    def generate_sql_reconfiguration_script(
        self,
        g: guestfs.GuestFS,
        root: str,
        old_hostname: str | None = None,
        new_hostname: str | None = None,
    ) -> str:
        """Generate SQL Server reconfiguration script.

        Args:
            g: GuestFS instance
            root: Windows root path
            old_hostname: Old server hostname (optional)
            new_hostname: New server hostname (optional)

        Returns:
            T-SQL script as string
        """
        instances = detect_sql_server_instances(g, root)
        return generate_sql_reconfiguration_script(instances, old_hostname, new_hostname)

    def _extract_hostname(self, g: guestfs.GuestFS, root: str) -> str:
        """Extract Windows hostname from registry.

        Args:
            g: GuestFS instance
            root: Windows root path

        Returns:
            Hostname string or "Unknown"
        """
        try:
            system_path = detect_windows_hive(g, root, "SYSTEM")
            if not system_path:
                return "Unknown"

            with tempfile.TemporaryDirectory() as tmpdir:
                local_hive = Path(tmpdir) / "SYSTEM"
                hive = download_and_open_hive(_safe_logger(self), g, system_path, local_hive, write=False)

                try:
                    root_node = hive.root()
                    controlset_name = _detect_current_controlset(hive, root_node)
                    hostname_path = f"{controlset_name}\\Control\\ComputerName\\ComputerName"

                    hostname_node = hive.node_get_child(root_node, hostname_path)
                    if not hostname_node:
                        return "Unknown"

                    value = hive.node_get_value(hostname_node, "ComputerName")
                    if value:
                        hostname_bytes = hive.value_value(value)
                        return hostname_bytes.decode("utf-16le", errors="ignore").rstrip("\x00")

                finally:
                    _close_best_effort(hive)

        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort informational lookup -- caller treats "Unknown" as
            # "couldn't determine hostname" rather than failing the whole operation.
            pass

        return "Unknown"

    def optimize_performance(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
        self,
        g: guestfs.GuestFS,
        root: str,
        enable_balloon: bool = True,
        enable_trim: bool = True,
        enable_msi: bool = True,
        cleanup_hyperv: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        # reason: single entry point toggling four independent, orthogonal performance
        # optimizations, each with its own kwargs-sourced option.
        """Apply performance optimizations for Windows on KVM.

        Args:
            g: GuestFS instance
            root: Windows root path
            enable_balloon: Configure VirtIO balloon driver (default: True)
            enable_trim: Enable TRIM/discard for SSDs (default: True)
            enable_msi: Enable MSI interrupts for VirtIO devices (default: True)
            cleanup_hyperv: Remove Hyper-V enlightenments (default: False, auto-detect)
            **kwargs: Additional options for specific optimizations

        Returns:
            Dict with optimization results
        """
        logger = _safe_logger(self)
        logger.info("Applying performance optimizations")

        results = {
            "balloon": None,
            "trim": None,
            "msi": None,
            "hyperv_cleanup": None,
            "warnings": [],
        }

        try:
            # Configure balloon driver
            if enable_balloon:
                balloon_interval = kwargs.get("balloon_memory_stats_interval", 10)
                balloon_free_page = kwargs.get("balloon_free_page_reporting", True)

                results["balloon"] = configure_balloon_driver(g, root, balloon_interval, balloon_free_page)

            # Enable TRIM/discard
            if enable_trim:
                trim_schedule = kwargs.get("trim_schedule_optimization", True)
                results["trim"] = enable_trim_discard(g, root, trim_schedule)

            # Enable MSI interrupts
            if enable_msi:
                msi_devices = kwargs.get("msi_devices", ["viostor", "netkvm"])
                results["msi"] = enable_msi_interrupts(g, root, msi_devices)

            # Cleanup Hyper-V enlightenments
            if cleanup_hyperv:
                hyperv_force = kwargs.get("hyperv_force_cleanup", False)
                results["hyperv_cleanup"] = cleanup_hyperv_enlightenments(g, root, hyperv_force)

            logger.info("Performance optimization complete")

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort fixer step -- must not abort the whole migration over
            # a non-critical performance-optimization quirk.
            logger.exception(
                "Windows performance optimization failed: %s. "
                "VirtIO balloon, TRIM, or MSI optimizations were not applied. "
                "These are non-critical but affect performance. "
                "After boot, install virtio-win guest tools from https://fedorapeople.org/groups/virt/virtio-win/",
                e,
            )
            results["warnings"].append(f"Optimization failed: {e}")

        return results

    def check_bitlocker(self, g: guestfs.GuestFS, root: str) -> dict[str, Any]:
        """
        Check for BitLocker encryption on Windows VM.

        CRITICAL: BitLocker-encrypted disks CANNOT be migrated offline.
        This method detects encryption and raises an error to block migration.

        Args:
            g: GuestFS instance
            root: Windows root path

        Returns:
            Dict with detection results (only if not encrypted)

        Raises:
            WindowsFixerError: If BitLocker is detected
        """
        logger = _safe_logger(self)
        return check_bitlocker_before_migration(g, root, logger)

    def verify_rdp(self, g: guestfs.GuestFS, root: str) -> dict[str, Any]:
        """
        Verify Remote Desktop Protocol is enabled in Windows.

        Checks RDP configuration and warns if disabled, preventing
        admin lockout on headless VMs after migration.

        Args:
            g: GuestFS instance
            root: Windows root path

        Returns:
            Dict with RDP configuration status:
                {
                    "rdp_enabled": bool,
                    "nla_enabled": bool,
                    "rdp_port": int,
                    "warnings": List[str],
                    "recommendations": List[str]
                }
        """
        return verify_rdp_enabled(g, root)

    def enable_rdp(self, g: guestfs.GuestFS, root: str) -> dict[str, Any]:
        """
        Enable Remote Desktop if currently disabled.

        Modifies Windows registry to enable RDP access, preventing
        admin lockout after migration.

        Args:
            g: GuestFS instance
            root: Windows root path

        Returns:
            Dict with modification results:
                {
                    "modified": bool,
                    "previous_state": bool,
                    "current_state": bool
                }
        """
        logger = _safe_logger(self)
        return enable_rdp_if_disabled(g, root, logger)

    def stage_firewall_migration(self, g: guestfs.GuestFS, root: str) -> dict[str, Any]:
        """
        Stage Windows Firewall rule migration.

        Creates PowerShell script and scheduled task to preserve
        firewall rules during migration.

        Args:
            g: GuestFS instance
            root: Windows root path

        Returns:
            Dict with staging results:
                {
                    "staged": bool,
                    "script_path": str,
                    "task_staged": bool
                }
        """
        return stage_firewall_export_script(g, root)

    def warn_virtio_drivers_missing(self, windows_info: dict[str, Any] | None = None) -> None:
        """
        Emit warning about missing VirtIO drivers.

        Explains performance impact and provides download/installation
        instructions when VirtIO drivers are not available.

        Args:
            windows_info: Optional Windows version info for specific recommendations
        """
        logger = _safe_logger(self)
        virtio_dir = getattr(self, "virtio_drivers_dir", None)

        if not virtio_dir:
            warn_no_virtio_drivers(logger, windows_info)


__all__ = [
    "CleanupMethod",
    "DomainRejoinMethod",
    "WindowsFixer",
    "WindowsFixerError",
    "check_bitlocker_before_migration",
    "cleanup_hyperv_enlightenments",
    "configure_balloon_driver",
    # New critical features
    "detect_bitlocker",
    "detect_dongle_drivers",
    "detect_hardware_dependent_apps",
    "detect_license_services",
    "detect_sql_server_instances",
    "enable_msi_interrupts",
    "enable_rdp_if_disabled",
    "enable_trim_discard",
    "extract_domain_info",
    "extract_license_info",
    "generate_compatibility_report",
    "generate_sql_reconfiguration_script",
    "get_firewall_migration_instructions",
    "get_virtio_download_url",
    "inject_virtio_drivers",
    "is_windows",
    "retain_windows_network_config",
    "stage_cleanup_script",
    "stage_disk_online",
    "stage_domain_rejoin_script",
    "stage_firewall_export_script",
    "stage_reactivation_script",
    "stage_route_cleanup",
    "verify_rdp_enabled",
    "warn_no_virtio_drivers",
    "windows_bcd_actual_fix",
]
