# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Hyper-V enlightenments removal for Hyper-V to KVM migrations.

Removes Hyper-V-specific enlightenments and synthetic devices when migrating
FROM Hyper-V TO KVM. This prevents conflicts and ensures optimal performance
on the KVM hypervisor.
"""

import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hyper2kvm.fixers.windows.registry.encoding import (
    _close_best_effort,
    _commit_best_effort,
    _detect_current_controlset,
    _set_dword,
)
from hyper2kvm.fixers.windows.registry.io import (
    detect_windows_hive,
    download_and_open_hive,
    open_system_hive_for_edit,
)

if TYPE_CHECKING:
    import hivex

    from hyper2kvm.core.guestfs_typing import guestfs

logger = logging.getLogger(__name__)

# Hyper-V services to disable/remove
HYPERV_SERVICES = [
    "hv_fcopy",  # Hyper-V File Copy
    "hv_kvp_daemon",  # Hyper-V KVP Daemon
    "hv_vss_daemon",  # Hyper-V VSS Daemon
    "hvservice",  # Hyper-V Service
    "vmbus",  # Hyper-V Virtual Machine Bus
    "vmicheartbeat",  # Hyper-V Heartbeat Service
    "vmickvpexchange",  # Hyper-V Data Exchange Service
    "vmicrdv",  # Hyper-V Remote Desktop Virtualization Service
    "vmicshutdown",  # Hyper-V Guest Shutdown Service
    "vmictimesync",  # Hyper-V Time Synchronization Service
    "vmicvmsession",  # Hyper-V PowerShell Direct Service
    "vmicvss",  # Hyper-V Volume Shadow Copy Requestor
]


# Coordinates hive lookup, download, per-service disable, commit, and upload; the local
# count reflects the distinct pieces of state needed across that full offline-hive workflow.
# pylint: disable-next=too-many-locals
def cleanup_hyperv_enlightenments(
    g: "guestfs.GuestFS",
    root: str,
    force: bool = False,
) -> dict[str, Any]:
    """Remove Hyper-V enlightenments and synthetic devices.

    Args:
        g: GuestFS instance
        root: Windows root path
        force: Force cleanup even if Hyper-V detection uncertain (default: False)

    Returns:
        Dict with cleanup results

    Configuration:
        - Detects if VM was running on Hyper-V
        - Disables Hyper-V integration services
        - Removes Hyper-V synthetic device drivers
        - Only executes for Hyper-V → KVM migrations
    """
    logger.info("Checking for Hyper-V enlightenments")

    results = {
        "success": False,
        "hyperv_detected": False,
        "services_disabled": [],
        "services_skipped": [],
        "warnings": [],
    }

    try:
        # Detect if this is a Hyper-V VM
        is_hyperv = _detect_hyperv_vm(g, root)

        if not is_hyperv and not force:
            logger.info("Hyper-V not detected - skipping enlightenment cleanup")
            results["warnings"].append("Hyper-V not detected - cleanup skipped (use force=True to override)")
            results["success"] = True
            return results

        results["hyperv_detected"] = is_hyperv or force

        if force and not is_hyperv:
            logger.warning("Force cleanup enabled - proceeding without Hyper-V detection")
            results["warnings"].append("Forced cleanup without Hyper-V detection")

        system_path = detect_windows_hive(g, root, "SYSTEM")
        if not system_path:
            results["warnings"].append("SYSTEM hive not found - cannot cleanup")
            return results

        # pylint: disable=duplicate-code
        # reason: this is the shared open_system_hive_for_edit() call
        # pattern used identically by hyper2kvm/fixers/windows/performance/
        # balloon.py, msi.py, and trim.py -- intentional, that's the point
        # of the shared helper; each caller's surrounding results dict and
        # hive-editing logic still differs.
        with tempfile.TemporaryDirectory() as tmpdir:
            local_hive = Path(tmpdir) / "SYSTEM"
            hive, root_node, controlset_name = open_system_hive_for_edit(
                logger, g, system_path, local_hive
            )

            try:
                # Disable Hyper-V services
                for service in HYPERV_SERVICES:
                    if _disable_service(hive, root_node, controlset_name, service):
                        results["services_disabled"].append(service)
                        logger.info("Disabled Hyper-V service: %s", service)
                    else:
                        results["services_skipped"].append(service)

                # Commit changes
                _commit_best_effort(hive)

                # Upload modified hive
                g.upload(str(local_hive), system_path)

                results["success"] = True
                logger.info(
                    "Hyper-V cleanup complete: %d services disabled",
                    len(results["services_disabled"]),
                )

            finally:
                _close_best_effort(hive)

    except Exception as e:  # pylint: disable=broad-exception-caught
        # best-effort fixer step: registry/hive operations can fail in many ways and must
        # not abort the whole migration over one guest's Hyper-V cleanup quirk
        logger.exception("Failed to cleanup Hyper-V enlightenments: %s", e)
        logger.debug("Hyper-V cleanup error", exc_info=True)
        results["warnings"].append(f"Cleanup failed: {e}")

    return results


# pylint: disable-next=too-many-locals
def _detect_hyperv_vm(g: "guestfs.GuestFS", root: str) -> bool:
    """Detect if VM was running on Hyper-V.

    Args:
        g: GuestFS instance
        root: Windows root path

    Returns:
        True if Hyper-V detected, False otherwise
    """
    try:
        system_path = detect_windows_hive(g, root, "SYSTEM")
        if not system_path:
            return False

        with tempfile.TemporaryDirectory() as tmpdir:
            local_hive = Path(tmpdir) / "SYSTEM"
            hive = download_and_open_hive(logger, g, system_path, local_hive, write=False)

            try:
                root_node = hive.root()
                controlset_name = _detect_current_controlset(hive, root_node)

                # Check for Hyper-V services
                for service in HYPERV_SERVICES[:3]:  # Check first 3 services
                    service_path = f"{controlset_name}\\Services\\{service}"
                    service_node = hive.node_get_child(root_node, service_path)

                    if service_node:
                        logger.info("Hyper-V service detected: %s", service)
                        return True

            finally:
                _close_best_effort(hive)

    except Exception as e:  # pylint: disable=broad-exception-caught
        # best-effort detection: any hive/registry access failure just means "not detected"
        logger.debug("Error detecting Hyper-V: %s", e)

    return False


def _disable_service(
    hive: "hivex.Hivex",
    root_node: int,
    controlset_name: str,
    service: str,
) -> bool:
    """Disable a Windows service by setting Start=4 (disabled).

    Args:
        hive: Hivex instance
        root_node: Registry root node
        controlset_name: Current control set name
        service: Service name

    Returns:
        True if service was disabled, False if not found
    """
    service_path = f"{controlset_name}\\Services\\{service}"
    service_node = hive.node_get_child(root_node, service_path)

    if not service_node:
        return False

    # Set Start = 4 (SERVICE_DISABLED)
    _set_dword(hive, service_node, "Start", 4)

    return True
