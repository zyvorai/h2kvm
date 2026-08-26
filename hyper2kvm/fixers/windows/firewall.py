# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/fixers/windows/firewall.py

"""
Windows Firewall rule migration for preserving network security configuration.

Exports firewall rules before migration and stages import scripts for first boot.
This preserves custom firewall rules that protect applications and services.
"""

from __future__ import annotations

import contextlib
import logging
import os
import tempfile
from typing import TYPE_CHECKING, Any

from hyper2kvm.fixers.windows._hivex_compat import HIVEX_AVAILABLE, hivex

if TYPE_CHECKING:
    from hyper2kvm.core.guestfs_typing import guestfs


def stage_firewall_export_script(  # pylint: disable=unused-argument
    g: guestfs.GuestFS, root: str = ""
) -> dict[str, Any]:
    # reason: `root` is unused here but kept for API compat -- callers across the
    # fixer module invoke this with the same (g, root) positional signature.
    """
    Stage a PowerShell script to export Windows Firewall rules.

    The script will run on first boot BEFORE migration to capture current rules,
    then import them after hardware change is complete.

    Args:
        g: GuestFS instance with Windows disk mounted
        root: Unused (kept for API compat). Guest paths are always absolute from /.

    Returns:
        Dict with staging results:
            {
                "staged": bool,
                "script_path": str,
                "error": str
            }
    """
    result = {
        "staged": False,
        "script_path": None,
        "error": None,
    }

    try:
        # Create firewall backup/restore script
        script_content = _generate_firewall_migration_script()

        # Stage script in Windows directory (absolute guest path)
        script_dir = "/Windows/Temp"
        script_path = f"{script_dir}/hyper2kvm-firewall-migrate.ps1"

        # Ensure Temp dir exists
        try:
            if not g.is_dir(script_dir):
                g.mkdir_p(script_dir)
        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort mkdir -- g.write() below will surface any real problem.
            pass

        g.write(script_path, script_content.encode("utf-8"))
        result["staged"] = True
        result["script_path"] = script_path

        logging.info("✅ Staged firewall migration script: %s", script_path)

        # Also create a scheduled task to run it
        task_result = _stage_firewall_migration_task(g)
        result["task_staged"] = task_result.get("staged", False)

    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort fixer step -- must not abort the whole migration over
        # one guest's firewall-script staging quirk.
        result["error"] = str(e)
        logging.exception("Failed to stage firewall migration script: %s", e)

    return result


def _generate_firewall_migration_script() -> str:
    """
    Generate PowerShell script for firewall rule migration.

    The script:
        1. Exports current firewall rules to XML
        2. Stores them in a safe location
        3. After migration, imports them back
    """
    return r"""# hyper2kvm Firewall Migration Script
# Preserves Windows Firewall rules during VM migration

$ErrorActionPreference = "Stop"
$LogFile = "C:\Windows\Temp\hyper2kvm-firewall-migration.log"

function Write-Log {
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -Append -FilePath $LogFile
    Write-Host $Message
}

Write-Log "=== Windows Firewall Migration Started ==="

try {
    # Export location
    $BackupPath = "C:\Windows\Temp\hyper2kvm-firewall-backup.wfw"
    $RulesPath = "C:\Windows\Temp\hyper2kvm-firewall-rules.xml"

    # Check if this is pre-migration or post-migration
    if (-not (Test-Path $BackupPath)) {
        # PRE-MIGRATION: Export current rules
        Write-Log "Exporting firewall configuration..."

        # Export all firewall rules
        try {
            netsh advfirewall export $BackupPath | Out-Null
            Write-Log "✓ Exported firewall policy to: $BackupPath"
        } catch {
            Write-Log "⚠ Failed to export firewall policy: $_"
        }

        # Also export individual rules as XML for inspection
        try {
            $Rules = Get-NetFirewallRule | Where-Object { $_.Enabled -eq $true }
            $Rules | Export-Clixml -Path $RulesPath
            Write-Log "✓ Exported $($Rules.Count) enabled firewall rules"
        } catch {
            Write-Log "⚠ Failed to export firewall rules: $_"
        }

    } else {
        # POST-MIGRATION: Import rules back
        Write-Log "Importing firewall configuration..."

        try {
            # Import firewall policy
            netsh advfirewall import $BackupPath | Out-Null
            Write-Log "✓ Imported firewall policy from: $BackupPath"

            # Verify critical rules are present
            $RdpRule = Get-NetFirewallRule -DisplayGroup "Remote Desktop" -ErrorAction SilentlyContinue
            if ($RdpRule) {
                Write-Log "✓ Remote Desktop firewall rules verified"
            } else {
                Write-Log "⚠ Remote Desktop rules not found - enabling..."
                Enable-NetFirewallRule -DisplayGroup "Remote Desktop" -ErrorAction SilentlyContinue
            }

        } catch {
            Write-Log "⚠ Failed to import firewall policy: $_"
        }

        # Clean up backup files
        Remove-Item $BackupPath -Force -ErrorAction SilentlyContinue
        Remove-Item $RulesPath -Force -ErrorAction SilentlyContinue
    }

    Write-Log "=== Firewall Migration Completed ==="

} catch {
    Write-Log "ERROR: Firewall migration failed: $_"
    Write-Log $_.ScriptStackTrace
    exit 1
}

exit 0
"""


def _stage_firewall_migration_task(  # pylint: disable=unused-argument
    g: guestfs.GuestFS, root: str = ""
) -> dict[str, Any]:
    # reason: `root` is unused here but kept for API compat with the module's other
    # (g, root) fixer-function signatures.
    """
    Create a scheduled task to run firewall migration on first boot.

    Uses Windows Task Scheduler XML format.
    """
    result = {"staged": False, "error": None}

    try:
        task_xml = r"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>hyper2kvm - Preserve Windows Firewall rules during migration</Description>
    <Author>hyper2kvm</Author>
  </RegistrationInfo>
  <Triggers>
    <BootTrigger>
      <Enabled>true</Enabled>
    </BootTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-18</UserId>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT1H</ExecutionTimeLimit>
    <Priority>4</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-ExecutionPolicy Bypass -File "C:\Windows\Temp\hyper2kvm-firewall-migrate.ps1"</Arguments>
    </Exec>
  </Actions>
</Task>"""

        # Write task XML (absolute guest path)
        task_path = "/Windows/System32/Tasks/hyper2kvm-firewall-migration"

        # Ensure Tasks directory exists
        tasks_dir = "/Windows/System32/Tasks"
        if not g.is_dir(tasks_dir):
            g.mkdir_p(tasks_dir)

        g.write(task_path, task_xml.encode("utf-8"))
        result["staged"] = True
        logging.info("✅ Staged firewall migration scheduled task")

    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort fixer step -- must not abort the whole migration over
        # one guest's scheduled-task staging quirk.
        result["error"] = str(e)
        logging.debug("Failed to stage firewall task: %s", e)

    return result


def extract_firewall_rules_for_report(  # pylint: disable=unused-argument
    g: guestfs.GuestFS, root: str
) -> list[dict[str, Any]]:
    # reason: `g`/`root` unused -- kept for API compat with the module's other
    # (g, root) fixer-function signatures; this function is currently informational-only.
    """
    Extract Windows Firewall rules for documentation/reporting.

    This is informational only - actual rules are migrated via scheduled task.

    Returns:
        List of firewall rule summaries for migration report
    """
    rules = []

    try:
        # Windows Firewall rules are stored in:
        # Registry: HKLM\SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy
        # Files: %SystemRoot%\System32\LogFiles\Firewall\

        # For now, just log that firewall migration will occur
        rules.append(
            {
                "name": "Windows Firewall Migration",
                "description": "Firewall rules will be exported and re-imported on first boot",
                "status": "Scheduled",
            }
        )

    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort informational lookup -- failures shouldn't block the report.
        logging.debug("Could not extract firewall rules: %s", e)

    return rules


def _read_service_start_type(  # pylint: disable=too-many-locals,too-many-return-statements,too-many-branches,unused-argument
    g: guestfs.GuestFS, root: str, service_name: str
) -> int | None:
    # reason: `root` unused -- kept for API compat with the module's other (g, root, ...)
    # fixer-function signatures. Navigating the SYSTEM hive (Select -> ControlSetNNN ->
    # Services -> <name> -> Start) needs an early return at each missing node, and a
    # handful of locals to hold the intermediate hive nodes/values.
    """
    Read service Start registry value from SYSTEM hive.

    Args:
        g: GuestFS instance
        root: Windows root path
        service_name: Service name (e.g., "MpsSvc")

    Returns:
        Start value (2=Automatic, 3=Manual, 4=Disabled) or None if unavailable
    """
    if not HIVEX_AVAILABLE:
        logging.debug("hivex not available, cannot read registry")
        return None

    # pylint: disable=duplicate-code
    # reason: the hive-download/open/ControlSet-detection steps mirror
    # hyper2kvm/fixers/windows/bitlocker.py's _read_bitlocker_service_info()
    # -- coincidental. This routine takes a parameterized service_name and
    # a root-agnostic hive path, while bitlocker.py's hardcodes BDESVC and
    # also reads DisplayName; keeping them independent avoids coupling two
    # functions with different data shapes.
    system_hive_path = "/Windows/System32/config/SYSTEM"
    if not g.exists(system_hive_path):
        return None

    h: hivex.Hivex | None = None
    try:
        # Download hive to temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=".hiv") as tmp:
            tmp_path = tmp.name

        g.download(system_hive_path, tmp_path)

        # Open hive with hivex (read-only)
        h = hivex.Hivex(tmp_path, write=False)
        root_node = h.root()

        # Detect current ControlSet (usually ControlSet001)
        select_node = h.node_get_child(root_node, "Select")
        if not select_node:
            return None

        current_val = h.node_get_value(select_node, "Current")
        if not current_val:
            return None

        _, current_data = h.value_value(current_val)
        current_cs_num = int.from_bytes(current_data[:4], "little", signed=False)
        controlset_name = f"ControlSet{current_cs_num:03d}"

        # Navigate to CurrentControlSet\Services\{service_name}
        controlset_node = h.node_get_child(root_node, controlset_name)
        if not controlset_node:
            return None

        services_node = h.node_get_child(controlset_node, "Services")
        if not services_node:
            return None

        service_node = h.node_get_child(services_node, service_name)
        if not service_node:
            return None

        # Read Start value (DWORD)
        start_val = h.node_get_value(service_node, "Start")
        if not start_val:
            return None

        _, start_bytes = h.value_value(start_val)
        if len(start_bytes) >= 4:
            return int.from_bytes(start_bytes[:4], "little", signed=False)

        return None

    # pylint: disable=duplicate-code
    # reason: the except/finally hive-close-and-tempfile-cleanup shape
    # mirrors hyper2kvm/fixers/windows/bitlocker.py's
    # _read_bitlocker_service_info() -- coincidental, both are the standard
    # best-effort cleanup for a temporarily downloaded hive.
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort registry probe -- caller treats None as "unknown".
        logging.debug("Failed to read service start type for %s: %s", service_name, e)
        return None
    finally:
        if h:
            with contextlib.suppress(Exception):
                h.close()
        # Clean up temporary file
        try:
            if "tmp_path" in locals():
                os.unlink(tmp_path)
        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort temp file cleanup must not raise.
            pass


def verify_firewall_service_enabled(g: guestfs.GuestFS, root: str) -> dict[str, Any]:
    """
    Verify Windows Firewall service is enabled.

    If firewall is disabled, rules don't matter - document this.
    """
    result = {
        "firewall_service_enabled": None,
        "warnings": [],
    }

    try:
        # Check registry for MpsSvc (Windows Firewall service)
        # HKLM\SYSTEM\CurrentControlSet\Services\MpsSvc\Start
        # 2 = Automatic, 3 = Manual, 4 = Disabled

        start_type = _read_service_start_type(g, root, "MpsSvc")

        if start_type is not None:
            # Map start type to human-readable name
            start_type_names = {0: "Boot", 1: "System", 2: "Automatic", 3: "Manual", 4: "Disabled"}
            start_type_name = start_type_names.get(start_type, f"Unknown({start_type})")

            result["firewall_service_enabled"] = start_type <= 3  # Not disabled
            result["start_type"] = start_type
            result["start_type_name"] = start_type_name

            logging.info("Windows Firewall service (MpsSvc) Start type: %s", start_type_name)

            if start_type == 4:
                result["warnings"].append(
                    "⚠️  Windows Firewall service is DISABLED\n"
                    "  Firewall rules will not be active after migration\n"
                    "  Consider enabling: Set-Service -Name 'MpsSvc' -StartupType Automatic"
                )
            else:
                logging.debug("Windows Firewall enabled (Start=%s)", start_type)
        else:
            # Could not read registry
            result["warnings"].append(
                "ℹ️  Verify Windows Firewall service after migration:\n"
                "  PowerShell: Get-Service -Name 'MpsSvc' | Select-Object Status, StartType"
            )

    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort informational check -- failures shouldn't block migration.
        logging.debug("Could not check firewall service: %s", e)

    return result


def get_firewall_migration_instructions() -> str:
    """
    Return instructions for manual firewall rule migration.

    Used if automated migration fails or for documentation.
    """
    return """
Windows Firewall Rule Migration Instructions:

BEFORE MIGRATION (in VMware):
  1. Export firewall rules:
       netsh advfirewall export C:\\firewall-backup.wfw

  2. Document custom rules:
       Get-NetFirewallRule | Where-Object {$_.Direction -eq 'Inbound' -and $_.Enabled -eq $true} | Format-Table

  3. Save to external location (USB, network share)

AFTER MIGRATION (in KVM):
  1. Import firewall rules:
       netsh advfirewall import C:\\firewall-backup.wfw

  2. Verify critical rules:
       Get-NetFirewallRule -DisplayGroup "Remote Desktop"
       Get-NetFirewallRule -DisplayGroup "File and Printer Sharing"

  3. Enable RDP rule if needed:
       Enable-NetFirewallRule -DisplayGroup "Remote Desktop"

  4. Test connectivity:
       Test-NetConnection -ComputerName localhost -Port 3389

TROUBLESHOOTING:
  - If import fails, rules may need manual recreation
  - Check Windows Event Viewer: Applications and Services Logs → Microsoft → Windows → Windows Firewall With Advanced Security
  - Reset to defaults: netsh advfirewall reset
"""
