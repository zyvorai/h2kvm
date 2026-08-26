# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""TRIM/discard enablement for SSD-backed storage.

Enables TRIM (also known as discard) support for Windows VMs running on
SSD-backed KVM storage. TRIM improves SSD performance and lifespan by allowing
the OS to inform the storage layer which blocks are no longer in use.
"""

import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from h2kvm.core.guestfs_typing import guestfs

logger = logging.getLogger(__name__)


def enable_trim_discard(
    g: "guestfs.GuestFS",
    root: str,
    schedule_optimization: bool = True,
) -> dict[str, Any]:
    # pylint: disable=too-many-locals,too-many-statements,import-outside-toplevel,broad-exception-caught
    # too-many-locals/statements: this walks the full TRIM enablement flow (hive open, registry
    # edit, script staging) as one cohesive fault-tolerant step; splitting it would obscure the
    # sequence. import-outside-toplevel: registry helpers are imported lazily to avoid a circular
    # import between fixer submodules. broad-exception-caught: best-effort fixer step, must not
    # abort the whole migration over one guest's quirk.
    """Enable TRIM/discard support for SSD-backed storage.

    Args:
        g: GuestFS instance
        root: Windows root path
        schedule_optimization: Schedule automatic TRIM optimization (default: True)

    Returns:
        Dict with configuration results

    Configuration:
        - Enables TRIM via DisableDeleteNotification registry key
        - Schedules automatic TRIM optimization
        - Generates verification script
        - Supports Windows 7 and later
    """
    logger.info("Enabling TRIM/discard support")

    # pylint: disable=duplicate-code
    # reason: mirrors the results-dict-init + SYSTEM-hive-lookup-guard shape
    # in h2kvm/fixers/windows/performance/msi.py's enable_msi_interrupts()
    # -- coincidental, each fixer's results dict has different keys.
    results = {
        "success": False,
        "trim_enabled": False,
        "optimization_scheduled": False,
        "verification_script": None,
        "warnings": [],
    }

    try:
        from h2kvm.fixers.windows.registry.encoding import _close_best_effort
        from h2kvm.fixers.windows.registry.io import detect_windows_hive, open_system_hive_for_edit

        # Configure TRIM in SYSTEM registry
        system_path = detect_windows_hive(g, root, "SYSTEM")
        if not system_path:
            results["warnings"].append("SYSTEM hive not found - cannot enable TRIM")
            return results

        # pylint: disable=duplicate-code
        # reason: this is the shared open_system_hive_for_edit() call
        # pattern used identically by h2kvm/fixers/windows/performance/
        # balloon.py, hyperv_cleanup.py, and msi.py -- intentional, that's
        # the point of the shared helper; each caller's surrounding
        # results dict and hive-editing logic still differs.
        with tempfile.TemporaryDirectory() as tmpdir:
            local_hive = Path(tmpdir) / "SYSTEM"
            hive, root_node, controlset_name = open_system_hive_for_edit(
                logger, g, system_path, local_hive
            )

            try:
                # Enable TRIM by setting DisableDeleteNotification = 0
                filesystem_path = f"{controlset_name}\\Control\\FileSystem"
                filesystem_node = hive.node_get_child(root_node, filesystem_path)

                if not filesystem_node:
                    from h2kvm.fixers.windows.registry.encoding import _ensure_child

                    control_node = hive.node_get_child(root_node, f"{controlset_name}\\Control")
                    if control_node:
                        filesystem_node = _ensure_child(hive, control_node, "FileSystem")

                if filesystem_node:
                    from h2kvm.fixers.windows.registry.encoding import _set_dword

                    # DisableDeleteNotification = 0 means TRIM is ENABLED
                    # DisableDeleteNotification = 1 means TRIM is DISABLED
                    _set_dword(hive, filesystem_node, "DisableDeleteNotification", 0)

                    results["trim_enabled"] = True
                    logger.info("TRIM enabled via DisableDeleteNotification registry key")
                else:
                    results["warnings"].append("FileSystem registry key not found")
                    logger.warning("Could not locate FileSystem registry key")

                # Commit changes
                from h2kvm.fixers.windows.registry.encoding import _commit_best_effort

                _commit_best_effort(hive)

                # Upload modified hive
                g.upload(str(local_hive), system_path)

                results["success"] = results["trim_enabled"]

            finally:
                _close_best_effort(hive)

        # Generate TRIM optimization script
        if schedule_optimization:
            optimization_script = _generate_trim_optimization_script()

            # Stage optimization script
            script_path = f"{root}/h2kvm/performance/trim-optimize.ps1"
            try:
                g.mkdir_p(f"{root}/h2kvm/performance")
                g.write(script_path, optimization_script.encode("utf-8"))
                results["optimization_scheduled"] = True
                logger.info("TRIM optimization script staged at %s", script_path)
            except Exception as e:
                logger.warning("Failed to stage optimization script: %s", e)
                results["warnings"].append(f"Could not stage optimization script: {e}")

        # Generate verification script
        verification_script = _generate_trim_verification_script()

        # Stage verification script
        verify_path = f"{root}/h2kvm/performance/trim-verify.ps1"
        try:
            g.mkdir_p(f"{root}/h2kvm/performance")
            g.write(verify_path, verification_script.encode("utf-8"))
            results["verification_script"] = verify_path
            logger.info("TRIM verification script staged at %s", verify_path)
        except Exception as e:
            logger.warning("Failed to stage verification script: %s", e)
            results["warnings"].append(f"Could not stage verification script: {e}")

    except Exception as e:
        logger.exception("Failed to enable TRIM/discard: %s", e)
        logger.debug("TRIM enablement error", exc_info=True)
        results["warnings"].append(f"TRIM enablement failed: {e}")

    return results


def _generate_trim_optimization_script() -> str:
    """Generate PowerShell script to schedule TRIM optimization.

    Returns:
        PowerShell script content
    """
    return """# TRIM/Discard Optimization Scheduler
# Generated by h2kvm

$LogFile = "C:\\h2kvm\\performance\\trim-optimize.log"

function Write-Log {
    param($Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -Append -FilePath $LogFile
    Write-Host $Message
}

Write-Log "=== TRIM Optimization Scheduler ==="

# Check Windows version (Windows 8/Server 2012 and later support automatic TRIM)
$OSVersion = [System.Environment]::OSVersion.Version

if ($OSVersion.Major -ge 6 -and $OSVersion.Minor -ge 2) {
    Write-Log "Windows version supports automatic TRIM optimization"

    # Create scheduled task for weekly TRIM optimization
    $TaskName = "H2KVM TRIM Optimization"
    $TaskPath = "\\Microsoft\\Windows\\Defrag\\"

    # Check if task already exists
    $ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

    if ($null -ne $ExistingTask) {
        Write-Log "TRIM optimization task already exists"
    } else {
        Write-Log "Creating TRIM optimization scheduled task..."

        $Action = New-ScheduledTaskAction -Execute "defrag.exe" -Argument "/C /H /L /O"
        $Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 2am
        $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

        try {
            Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -TaskPath $TaskPath -Description "Weekly TRIM optimization for SSD drives" -ErrorAction Stop
            Write-Log "SUCCESS: TRIM optimization task created"
        } catch {
            Write-Log "ERROR: Failed to create scheduled task: $_"
            exit 1
        }
    }

    # Run immediate optimization
    Write-Log "Running immediate TRIM optimization..."

    try {
        defrag.exe /C /L /O
        Write-Log "SUCCESS: TRIM optimization completed"
    } catch {
        Write-Log "WARNING: TRIM optimization failed: $_"
    }
} else {
    Write-Log "WARNING: Windows version does not support automatic TRIM"
    Write-Log "Manual TRIM optimization recommended"
}

Write-Log "=== TRIM Optimization Complete ==="
"""


def _generate_trim_verification_script() -> str:
    """Generate PowerShell script to verify TRIM configuration.

    Returns:
        PowerShell script content
    """
    return """# TRIM/Discard Verification Script
# Generated by h2kvm

$LogFile = "C:\\h2kvm\\performance\\trim-verify.log"

function Write-Log {
    param($Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -Append -FilePath $LogFile
    Write-Host $Message
}

Write-Log "=== TRIM/Discard Verification ==="

# Check if TRIM is enabled via registry
$RegPath = "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\FileSystem"
$DisableDeleteNotification = Get-ItemProperty -Path $RegPath -Name "DisableDeleteNotification" -ErrorAction SilentlyContinue

if ($DisableDeleteNotification) {
    $TrimEnabled = $DisableDeleteNotification.DisableDeleteNotification -eq 0
    Write-Log "DisableDeleteNotification registry value: $($DisableDeleteNotification.DisableDeleteNotification)"
    Write-Log "TRIM Enabled: $TrimEnabled"

    if ($TrimEnabled) {
        Write-Log "SUCCESS: TRIM is enabled in registry"
    } else {
        Write-Log "WARNING: TRIM is disabled in registry"
    }
} else {
    Write-Log "ERROR: DisableDeleteNotification registry key not found"
    exit 1
}

# Query TRIM support using fsutil
Write-Log "Querying TRIM support via fsutil..."

try {
    $FsutilOutput = fsutil behavior query DisableDeleteNotify

    if ($FsutilOutput -match "DisableDeleteNotify = 0") {
        Write-Log "SUCCESS: TRIM is enabled (fsutil confirms)"
    } elseif ($FsutilOutput -match "DisableDeleteNotify = 1") {
        Write-Log "WARNING: TRIM is disabled (fsutil confirms)"
    } else {
        Write-Log "INFO: fsutil output: $FsutilOutput"
    }
} catch {
    Write-Log "WARNING: Failed to query fsutil: $_"
}

# List physical drives and check for SSD
Write-Log "Checking for SSD drives..."

try {
    $PhysicalDisks = Get-PhysicalDisk -ErrorAction SilentlyContinue

    if ($PhysicalDisks) {
        foreach ($Disk in $PhysicalDisks) {
            Write-Log "Drive $($Disk.DeviceId): $($Disk.FriendlyName) - MediaType: $($Disk.MediaType)"

            if ($Disk.MediaType -eq "SSD") {
                Write-Log "SUCCESS: SSD detected - TRIM will improve performance and lifespan"
            }
        }
    } else {
        Write-Log "INFO: Could not query physical disks (requires Windows 8/Server 2012+)"
    }
} catch {
    Write-Log "WARNING: Failed to query physical disks: $_"
}

Write-Log "=== Verification Complete ==="

# Return success if TRIM is enabled
if ($TrimEnabled) {
    exit 0
} else {
    exit 1
}
"""
