# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""VirtIO balloon driver auto-configuration.

Configures the VirtIO balloon driver for optimal memory management on KVM.
The balloon driver allows the hypervisor to reclaim unused memory from the guest.
"""

import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

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


# opens/navigates/patches the SYSTEM hive and stages a verification script in one pass
def configure_balloon_driver(  # pylint: disable=too-many-locals
    g: "guestfs.GuestFS",
    root: str,
    memory_stats_interval: int = 10,
    enable_free_page_reporting: bool = True,
) -> dict[str, Any]:
    """Configure VirtIO balloon driver for optimal performance.

    Args:
        g: GuestFS instance
        root: Windows root path
        memory_stats_interval: Memory statistics reporting interval in seconds (default: 10)
        enable_free_page_reporting: Enable free page reporting for memory reclaim (default: True)

    Returns:
        Dict with configuration results

    Configuration:
        - Sets memory stats interval for balloon statistics
        - Enables free page reporting (Windows Server 2019+)
        - Configures balloon service parameters
        - Generates verification script for first boot
    """
    logger.info("Configuring VirtIO balloon driver")

    results = {
        "success": False,
        "balloon_configured": False,
        "memory_stats_interval": memory_stats_interval,
        "free_page_reporting": enable_free_page_reporting,
        "verification_script": None,
        "warnings": [],
    }

    try:
        # Check if balloon driver is installed
        system_path = detect_windows_hive(g, root, "SYSTEM")
        if not system_path:
            results["warnings"].append("SYSTEM hive not found - cannot configure balloon")
            return results

        # pylint: disable=duplicate-code
        # reason: this is the shared open_system_hive_for_edit() call
        # pattern used identically by hyper2kvm/fixers/windows/performance/
        # hyperv_cleanup.py, msi.py, and trim.py -- intentional, that's the
        # point of the shared helper; each caller's surrounding results
        # dict and hive-editing logic still differs.
        with tempfile.TemporaryDirectory() as tmpdir:
            local_hive = Path(tmpdir) / "SYSTEM"
            hive, root_node, controlset_name = open_system_hive_for_edit(
                logger, g, system_path, local_hive
            )

            try:
                # Check if balloon service exists
                services_path = f"{controlset_name}\\Services\\balloon"
                balloon_service = hive.node_get_child(root_node, services_path)

                if not balloon_service:
                    results["warnings"].append(
                        "Balloon driver service not found - driver may not be installed"
                    )
                    logger.warning("Balloon service not found in registry")
                    return results

                # Configure balloon parameters
                params_path = f"{services_path}\\Parameters"
                params_node = hive.node_get_child(root_node, params_path)

                # Create Parameters key if it doesn't exist
                if not params_node:
                    params_node = _ensure_child(hive, balloon_service, "Parameters")

                # Set memory stats interval
                _set_balloon_parameter(
                    hive,
                    params_node,
                    "MemoryStatsInterval",
                    memory_stats_interval,
                )

                # Enable free page reporting (if supported)
                if enable_free_page_reporting:
                    _set_balloon_parameter(
                        hive,
                        params_node,
                        "FreePageReporting",
                        1,
                    )

                # Commit changes
                _commit_best_effort(hive)

                # Upload modified hive

                g.upload(str(local_hive), system_path)

                results["balloon_configured"] = True
                results["success"] = True

                logger.info(
                    "Balloon driver configured: stats_interval=%ss, free_page_reporting=%s",
                    memory_stats_interval,
                    enable_free_page_reporting,
                )

            finally:
                _close_best_effort(hive)

        # Generate verification script
        verification_script = _generate_balloon_verification_script(
            memory_stats_interval, enable_free_page_reporting
        )

        # Stage verification script
        script_path = f"{root}/hyper2kvm/performance/balloon-verify.ps1"
        try:
            g.mkdir_p(f"{root}/hyper2kvm/performance")
            g.write(script_path, verification_script.encode("utf-8"))
            results["verification_script"] = script_path
            logger.info("Balloon verification script staged at %s", script_path)
        # best-effort staging step, must not abort the whole migration
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Failed to stage verification script: %s", e)
            results["warnings"].append(f"Could not stage verification script: {e}")

    # top-level workflow guard: must not crash the whole migration over one guest's quirk
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Failed to configure balloon driver: %s", e)
        logger.debug("Balloon configuration error", exc_info=True)
        results["warnings"].append(f"Configuration failed: {e}")

    return results


def _set_balloon_parameter(
    hive: "hivex.Hivex",
    params_node: int,
    name: str,
    value: int,
) -> None:
    """Set a balloon driver parameter in the registry.

    Args:
        hive: Hivex instance
        params_node: Parameters node
        name: Parameter name
        value: Parameter value (DWORD)
    """
    _set_dword(hive, params_node, name, value)


def _generate_balloon_verification_script(
    memory_stats_interval: int,
    enable_free_page_reporting: bool,
) -> str:
    """Generate PowerShell script to verify balloon configuration.

    Args:
        memory_stats_interval: Expected memory stats interval
        enable_free_page_reporting: Expected free page reporting state

    Returns:
        PowerShell script content
    """
    # pylint: disable=line-too-long
    return f"""# VirtIO Balloon Driver Verification Script
# Generated by hyper2kvm

$LogFile = "C:\\hyper2kvm\\performance\\balloon-verify.log"

function Write-Log {{
    param($Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -Append -FilePath $LogFile
    Write-Host $Message
}}

Write-Log "=== VirtIO Balloon Driver Verification ==="

# Check if balloon driver service exists
$BalloonService = Get-Service -Name "balloon" -ErrorAction SilentlyContinue

if ($null -eq $BalloonService) {{
    Write-Log "ERROR: Balloon driver service not found"
    Write-Log "Ensure VirtIO balloon driver is installed"
    exit 1
}}

Write-Log "Balloon driver service status: $($BalloonService.Status)"

if ($BalloonService.Status -ne "Running") {{
    Write-Log "WARNING: Balloon service is not running"
    Write-Log "Attempting to start balloon service..."

    try {{
        Start-Service -Name "balloon"
        Write-Log "SUCCESS: Balloon service started"
    }} catch {{
        Write-Log "ERROR: Failed to start balloon service: $_"
        exit 1
    }}
}}

# Verify balloon driver configuration
$RegPath = "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\balloon\\Parameters"

if (Test-Path $RegPath) {{
    $MemStatsInterval = Get-ItemProperty -Path $RegPath -Name "MemoryStatsInterval" -ErrorAction SilentlyContinue
    $FreePageReporting = Get-ItemProperty -Path $RegPath -Name "FreePageReporting" -ErrorAction SilentlyContinue

    if ($MemStatsInterval) {{
        Write-Log "Memory Stats Interval: $($MemStatsInterval.MemoryStatsInterval) seconds (expected: {memory_stats_interval})"

        if ($MemStatsInterval.MemoryStatsInterval -eq {memory_stats_interval}) {{
            Write-Log "SUCCESS: Memory stats interval configured correctly"
        }} else {{
            Write-Log "WARNING: Memory stats interval mismatch"
        }}
    }} else {{
        Write-Log "WARNING: Memory stats interval not configured"
    }}

    if ($FreePageReporting) {{
        $enabled = $FreePageReporting.FreePageReporting -eq 1
        Write-Log "Free Page Reporting: $enabled (expected: {str(enable_free_page_reporting).lower()})"

        if ($enabled -eq {str(enable_free_page_reporting).lower()}) {{
            Write-Log "SUCCESS: Free page reporting configured correctly"
        }} else {{
            Write-Log "WARNING: Free page reporting mismatch"
        }}
    }} else {{
        Write-Log "INFO: Free page reporting not configured (may not be supported on this Windows version)"
    }}
}} else {{
    Write-Log "WARNING: Balloon Parameters registry key not found"
}}

# Check balloon device in Device Manager
$BalloonDevice = Get-PnpDevice -FriendlyName "*Balloon*" -ErrorAction SilentlyContinue

if ($BalloonDevice) {{
    Write-Log "Balloon device found: $($BalloonDevice.FriendlyName)"
    Write-Log "Device status: $($BalloonDevice.Status)"

    if ($BalloonDevice.Status -eq "OK") {{
        Write-Log "SUCCESS: Balloon device is working properly"
    }} else {{
        Write-Log "WARNING: Balloon device status is not OK"
    }}
}} else {{
    Write-Log "WARNING: Balloon device not found in Device Manager"
}}

Write-Log "=== Verification Complete ==="

# Return success if service is running
if ($BalloonService.Status -eq "Running") {{
    exit 0
}} else {{
    exit 1
}}
"""
