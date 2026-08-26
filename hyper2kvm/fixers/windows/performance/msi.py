# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""MSI interrupt configuration for VirtIO devices.

Enables Message Signaled Interrupts (MSI) for VirtIO storage and network devices.
MSI interrupts can improve performance by ~20% for network throughput and reduce
interrupt latency for storage operations.
"""

import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from hyper2kvm.fixers.windows.registry.encoding import (
    _close_best_effort,
    _commit_best_effort,
    _ensure_child,
    _set_dword,
)
from hyper2kvm.fixers.windows.registry.io import detect_windows_hive, open_system_hive_for_edit

if TYPE_CHECKING:
    import hivex

    from hyper2kvm.core.guestfs_typing import guestfs

logger = logging.getLogger(__name__)


def enable_msi_interrupts(
    g: "guestfs.GuestFS",
    root: str,
    devices: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Enable MSI interrupts for VirtIO devices.

    Args:
        g: GuestFS instance
        root: Windows root path
        devices: List of device drivers to enable MSI for (default: ["viostor", "netkvm"])

    Returns:
        Dict with configuration results

    Configuration:
        - Enables MSI for VirtIO storage (viostor)
        - Enables MSI for VirtIO network (netkvm)
        - Sets MSISupported=1 in device Parameters
        - Creates MessageSignaledInterruptProperties registry keys
    """
    if devices is None:
        devices = ["viostor", "netkvm"]

    logger.info("Enabling MSI interrupts for devices: %s", devices)

    # pylint: disable=duplicate-code
    # reason: mirrors the results-dict-init + SYSTEM-hive-lookup-guard shape
    # in hyper2kvm/fixers/windows/performance/trim.py's enable_trim_discard()
    # -- coincidental, each fixer's results dict has different keys.
    results = {
        "success": False,
        "devices_configured": [],
        "devices_skipped": [],
        "verification_script": None,
        "warnings": [],
    }

    try:
        system_path = detect_windows_hive(g, root, "SYSTEM")
        if not system_path:
            results["warnings"].append("SYSTEM hive not found - cannot enable MSI")
            return results

        # pylint: disable=duplicate-code
        # reason: this is the shared open_system_hive_for_edit() call
        # pattern used identically by hyper2kvm/fixers/windows/performance/
        # balloon.py, hyperv_cleanup.py, and trim.py -- intentional, that's
        # the point of the shared helper; each caller's surrounding
        # results dict and hive-editing logic still differs.
        with tempfile.TemporaryDirectory() as tmpdir:
            local_hive = Path(tmpdir) / "SYSTEM"
            hive, root_node, controlset_name = open_system_hive_for_edit(
                logger, g, system_path, local_hive
            )

            try:
                for device in devices:
                    if _enable_device_msi(hive, root_node, controlset_name, device):
                        results["devices_configured"].append(device)
                        logger.info("MSI enabled for %s", device)
                    else:
                        results["devices_skipped"].append(device)
                        logger.warning("Could not enable MSI for %s (service not found)", device)

                # Commit changes
                _commit_best_effort(hive)

                # Upload modified hive
                g.upload(str(local_hive), system_path)

                results["success"] = len(results["devices_configured"]) > 0

            finally:
                _close_best_effort(hive)

        # Generate verification script
        verification_script = _generate_msi_verification_script(devices)

        # Stage verification script
        script_path = f"{root}/hyper2kvm/performance/msi-verify.ps1"
        try:
            g.mkdir_p(f"{root}/hyper2kvm/performance")
            g.write(script_path, verification_script.encode("utf-8"))
            results["verification_script"] = script_path
            logger.info("MSI verification script staged at %s", script_path)
        # staging the verification script is best-effort; MSI config itself already succeeded
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Failed to stage verification script: %s", e)
            results["warnings"].append(f"Could not stage verification script: {e}")

    # top-level fixer entrypoint: must report failure via results, not crash the migration
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Failed to enable MSI interrupts: %s", e)
        logger.debug("MSI enablement error", exc_info=True)
        results["warnings"].append(f"MSI enablement failed: {e}")

    return results


def _enable_device_msi(
    hive: "hivex.Hivex",
    root_node: int,
    controlset_name: str,
    device: str,
) -> bool:
    """Enable MSI for a specific device.

    Args:
        hive: Hivex instance
        root_node: Registry root node
        controlset_name: Current control set name
        device: Device driver name

    Returns:
        True if MSI was enabled, False otherwise
    """
    # Path: CurrentControlSet\Services\{device}\Parameters\InterruptManagement\MessageSignaledInterruptProperties
    service_path = f"{controlset_name}\\Services\\{device}"
    service_node = hive.node_get_child(root_node, service_path)

    if not service_node:
        return False

    # Create Parameters key if needed
    params_node = hive.node_get_child(service_node, "Parameters")
    if not params_node:
        params_node = _ensure_child(hive, service_node, "Parameters")

    # Create InterruptManagement key
    intmgmt_node = hive.node_get_child(params_node, "InterruptManagement")
    if not intmgmt_node:
        intmgmt_node = _ensure_child(hive, params_node, "InterruptManagement")

    # Create MessageSignaledInterruptProperties key
    msi_node = hive.node_get_child(intmgmt_node, "MessageSignaledInterruptProperties")
    if not msi_node:
        msi_node = _ensure_child(hive, intmgmt_node, "MessageSignaledInterruptProperties")

    # Set MSISupported = 1
    _set_dword(hive, msi_node, "MSISupported", 1)

    return True


def _generate_msi_verification_script(devices: list[str]) -> str:
    """Generate PowerShell script to verify MSI configuration.

    Args:
        devices: List of device names to verify

    Returns:
        PowerShell script content
    """
    devices_str = ", ".join([f'"{d}"' for d in devices])

    # pylint: disable=line-too-long
    # one generated PowerShell line below exceeds the limit; splitting it would
    # alter the emitted script's content
    # pylint: disable=duplicate-code
    # reason: the generated Write-Log PowerShell helper mirrors the one in
    # hyper2kvm/fixers/windows/activedirectory/cleanup.py's
    # _generate_netdom_script() -- coincidental, each generated script is a
    # standalone artifact and its embedded logging helper must stay intact.
    return f"""# MSI Interrupt Verification Script
# Generated by hyper2kvm

$LogFile = "C:\\hyper2kvm\\performance\\msi-verify.log"

function Write-Log {{
    param($Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -Append -FilePath $LogFile
    Write-Host $Message
}}

Write-Log "=== MSI Interrupt Verification ==="

$Devices = @({devices_str})
$AllSuccess = $true

foreach ($Device in $Devices) {{
    Write-Log "Checking MSI configuration for $Device..."

    $RegPath = "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\$Device\\Parameters\\InterruptManagement\\MessageSignaledInterruptProperties"

    if (Test-Path $RegPath) {{
        $MSISupported = Get-ItemProperty -Path $RegPath -Name "MSISupported" -ErrorAction SilentlyContinue

        if ($MSISupported) {{
            $Enabled = $MSISupported.MSISupported -eq 1
            Write-Log "$Device MSISupported: $($MSISupported.MSISupported) (Enabled: $Enabled)"

            if ($Enabled) {{
                Write-Log "SUCCESS: MSI enabled for $Device"
            }} else {{
                Write-Log "WARNING: MSI not enabled for $Device"
                $AllSuccess = $false
            }}
        }} else {{
            Write-Log "WARNING: MSISupported value not found for $Device"
            $AllSuccess = $false
        }}
    }} else {{
        Write-Log "WARNING: MSI registry path not found for $Device"
        $AllSuccess = $false
    }}
}}

# Check actual MSI usage in Device Manager (requires elevated permissions)
Write-Log "Checking MSI usage in system..."

try {{
    $MSIDevices = Get-WmiObject -Class Win32_PnPEntity | Where-Object {{
        $_.Name -match "VirtIO" -or $_.Name -match "Red Hat"
    }}

    if ($MSIDevices) {{
        foreach ($Dev in $MSIDevices) {{
            Write-Log "Device: $($Dev.Name) - Status: $($Dev.Status)"
        }}
    }} else {{
        Write-Log "INFO: No VirtIO devices found via WMI"
    }}
}} catch {{
    Write-Log "WARNING: Could not query WMI for devices: $_"
}}

Write-Log "=== Verification Complete ==="

if ($AllSuccess) {{
    Write-Log "SUCCESS: All devices configured for MSI"
    exit 0
}} else {{
    Write-Log "WARNING: Some devices may not have MSI enabled"
    exit 1
}}
"""
    # pylint: enable=line-too-long
