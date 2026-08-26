# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/fixers/windows/disk_online.py
"""
Windows VirtIO disk online script for VMware -> KVM migration.

After migrating a Windows VM, VirtIO disks may appear as "Offline" or
"Read-Only" because Windows doesn't recognise the new disk controller.
This is especially common with data disks (non-boot volumes).

This module stages a firstboot PowerShell script that:
  1) Clears the SAN policy to OnlineAll (prevents future offline disks)
  2) Finds all offline disks and brings them online
  3) Clears readonly attributes on all writable disks
  4) Re-assigns drive letters if they were lost
"""

from __future__ import annotations

import logging
from typing import Any

try:
    import guestfs  # type: ignore
except ImportError:
    guestfs = None  # type: ignore

from hyper2kvm.core.guest_utils import (
    guest_mkdir_p as _guest_mkdir_p,
    guest_write_text as _guest_write_text,
)
from hyper2kvm.core.logging_utils import (
    log_step as _step,
    log_with_emoji as _log,
    safe_logger as _safe_logger_base,
)


def _safe_logger(self) -> logging.Logger:
    return _safe_logger_base(self, "hyper2kvm.disk_online")


def _build_disk_online_ps1() -> str:
    r"""
    PowerShell script that ensures all VirtIO disks are online and writable.

    Uses both diskpart (legacy compat) and PowerShell cmdlets (modern).
    """
    return r"""
$ErrorActionPreference = "Continue"

$LogPath = "C:\hyper2kvm\disk_online\disk-online.log"
New-Item -ItemType Directory -Force -Path (Split-Path $LogPath) | Out-Null

function Log($msg) {
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Add-Content -Path $LogPath -Value "$ts $msg"
}

Log "=== hyper2kvm disk online starting ==="

# Step 1: Set SAN policy to OnlineAll (prevents future offline disks)
try {
  $diskpartScript = @"
san policy=OnlineAll
exit
"@
  $tmpFile = [System.IO.Path]::GetTempFileName()
  Set-Content -Path $tmpFile -Value $diskpartScript -Encoding ASCII
  $dpResult = & diskpart /s $tmpFile 2>&1
  Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
  Log "SAN policy set to OnlineAll"
  Log "diskpart output: $dpResult"
} catch {
  Log ("Failed to set SAN policy: {0}" -f $_.Exception.Message)
}

# Step 2: Try PowerShell Storage cmdlets first (Server 2012+, Win8+)
$usePowerShell = $false
try {
  $null = Get-Command Get-Disk -ErrorAction Stop
  $usePowerShell = $true
} catch {
  Log "Get-Disk cmdlet not available, falling back to diskpart"
}

if ($usePowerShell) {
  # PowerShell approach (preferred)
  try {
    $offlineDisks = Get-Disk | Where-Object { $_.OperationalStatus -eq "Offline" }
    foreach ($disk in $offlineDisks) {
      try {
        Set-Disk -Number $disk.Number -IsOffline $false
        Log ("Brought disk {0} online (Size={1}GB)" -f $disk.Number, [math]::Round($disk.Size/1GB, 2))
      } catch {
        Log ("Failed to online disk {0}: {1}" -f $disk.Number, $_.Exception.Message)
      }
    }

    $readonlyDisks = Get-Disk | Where-Object { $_.IsReadOnly -eq $true -and $_.Number -ne 0 }
    foreach ($disk in $readonlyDisks) {
      try {
        Set-Disk -Number $disk.Number -IsReadOnly $false
        Log ("Cleared readonly on disk {0}" -f $disk.Number)
      } catch {
        Log ("Failed to clear readonly on disk {0}: {1}" -f $disk.Number, $_.Exception.Message)
      }
    }
  } catch {
    Log ("PowerShell disk operations failed: {0}" -f $_.Exception.Message)
  }

} else {
  # Diskpart fallback (Windows 7, Server 2008 R2 and earlier)
  try {
    $listScript = "list disk`r`nexit"
    $tmpFile = [System.IO.Path]::GetTempFileName()
    Set-Content -Path $tmpFile -Value $listScript -Encoding ASCII
    $listOutput = & diskpart /s $tmpFile 2>&1
    Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue

    $diskNumbers = @()
    foreach ($line in $listOutput) {
      if ($line -match "Disk\s+(\d+)\s+Offline") {
        $diskNumbers += [int]$Matches[1]
      }
    }

    foreach ($diskNum in $diskNumbers) {
      $onlineScript = @"
select disk $diskNum
attributes disk clear readonly
online disk
exit
"@
      $tmpFile = [System.IO.Path]::GetTempFileName()
      Set-Content -Path $tmpFile -Value $onlineScript -Encoding ASCII
      $onlineOutput = & diskpart /s $tmpFile 2>&1
      Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
      Log ("diskpart: online disk {0}: {1}" -f $diskNum, ($onlineOutput -join " "))
    }
  } catch {
    Log ("diskpart fallback failed: {0}" -f $_.Exception.Message)
  }
}

# Step 3: Check for volumes without drive letters and try to assign
if ($usePowerShell) {
  try {
    $partitions = Get-Partition | Where-Object {
      -not $_.DriveLetter -and
      $_.Type -ne "Reserved" -and
      $_.Type -ne "System" -and
      $_.Type -ne "Recovery" -and
      $_.Size -gt 100MB
    }

    foreach ($part in $partitions) {
      try {
        $part | Add-PartitionAccessPath -AssignDriveLetter -ErrorAction SilentlyContinue
        $newLetter = (Get-Partition -DiskNumber $part.DiskNumber -PartitionNumber $part.PartitionNumber).DriveLetter
        if ($newLetter) {
          Log ("Assigned drive letter {0}: to disk {1} partition {2}" -f $newLetter, $part.DiskNumber, $part.PartitionNumber)
        }
      } catch {
        Log ("Could not assign letter to disk {0} part {1}: {2}" -f $part.DiskNumber, $part.PartitionNumber, $_.Exception.Message)
      }
    }
  } catch {
    Log ("Drive letter assignment failed: {0}" -f $_.Exception.Message)
  }
}

# Step 4: Summary
if ($usePowerShell) {
  $finalDisks = Get-Disk -ErrorAction SilentlyContinue
  $online = @($finalDisks | Where-Object { $_.OperationalStatus -eq "Online" }).Count
  $offline = @($finalDisks | Where-Object { $_.OperationalStatus -eq "Offline" }).Count
  Log ("Final state: {0} online, {1} offline" -f $online, $offline)
} else {
  Log "Final state check skipped (no PowerShell storage cmdlets)"
}

Log "=== Disk online complete ==="
""".lstrip()


def stage_disk_online(self, g: guestfs.GuestFS) -> dict[str, Any]:
    """
    Stage a firstboot PowerShell script to bring VirtIO disks online.

    Attributes consumed from ``self``:
      - dry_run: bool
      - logger: optional

    Returns:
        Result dict with success/artifacts/warnings.
    """
    logger = _safe_logger(self)
    dry_run = bool(getattr(self, "dry_run", False))

    result: dict[str, Any] = {
        "staged": False,
        "dry_run": dry_run,
        "artifacts": [],
        "warnings": [],
        "notes": [],
    }

    base_dir = "/hyper2kvm/disk_online"
    ps1_path = f"{base_dir}/online-disks.ps1"

    try:
        with _step(logger, "💾 Stage VirtIO disk online script"):
            _guest_mkdir_p(g, "/hyper2kvm", dry_run=dry_run)
            _guest_mkdir_p(g, base_dir, dry_run=dry_run)
            _guest_write_text(g, ps1_path, _build_disk_online_ps1(), dry_run=dry_run)

        result["staged"] = True
        result["artifacts"].append(
            {
                "kind": "disk_online_ps1",
                "dst": ps1_path,
                "action": "written" if not dry_run else "dry_run",
            }
        )
        result["notes"].append(r"Disk online script staged at C:\hyper2kvm\disk_online\online-disks.ps1")

        _log(logger, logging.INFO, "Disk online script staged: %s", ps1_path)

    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort firstboot script staging, must not abort the whole migration
        msg = f"Disk online staging failed: {e}"
        result["warnings"].append(msg)
        _log(logger, logging.WARNING, "%s", msg)

    return result


__all__ = ["stage_disk_online"]
