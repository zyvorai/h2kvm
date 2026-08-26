# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/fixers/windows/route_cleanup.py
"""
Windows duplicate persistent route cleanup for VMware -> KVM migration.

When the NIC driver changes from vmxnet3/e1000 to virtio-net, Windows may
create duplicate default routes on the new adapter while keeping stale
routes from the old adapter. This causes routing failures (packets go to
the wrong gateway or are dropped).

This module stages a PowerShell firstboot script that:
  1) Removes duplicate persistent routes
  2) Preserves the correct default gateway
  3) Configures per-NIC gateway settings
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
    return _safe_logger_base(self, "hyper2kvm.route_cleanup")


def _build_route_cleanup_ps1() -> str:
    r"""
    PowerShell script that runs at first boot to clean up duplicate routes.

    Logic:
      - Enumerate all IPv4 routes
      - Find duplicate default gateways (0.0.0.0/0)
      - Keep the route on the active (Up) adapter, remove duplicates
      - Remove persistent routes pointing to adapters that no longer exist
      - Set correct interface-level default gateway via netsh
    """
    return r"""
$ErrorActionPreference = "Continue"

$LogPath = "C:\hyper2kvm\route_cleanup\route-cleanup.log"
New-Item -ItemType Directory -Force -Path (Split-Path $LogPath) | Out-Null

function Log($msg) {
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Add-Content -Path $LogPath -Value "$ts $msg"
}

Log "=== hyper2kvm route cleanup starting ==="

# Step 1: Get all IPv4 routes
$allRoutes = Get-NetRoute -AddressFamily IPv4 -ErrorAction SilentlyContinue
if (-not $allRoutes) {
  Log "No IPv4 routes found. Nothing to do."
  exit 0
}

# Step 2: Find default routes (0.0.0.0/0)
$defaultRoutes = $allRoutes | Where-Object {
  $_.DestinationPrefix -eq "0.0.0.0/0"
}

Log ("Found {0} total routes, {1} default routes" -f $allRoutes.Count, @($defaultRoutes).Count)

if (@($defaultRoutes).Count -le 1) {
  Log "No duplicate default routes. Skipping cleanup."
} else {
  # Step 3: Find the best adapter (Up, physical, non-virtual)
  $adapters = Get-NetAdapter -ErrorAction SilentlyContinue
  $upAdapters = $adapters | Where-Object {
    $_.Status -eq "Up" -and $_.Name -notmatch "vEthernet|Hyper-V|Loopback|Virtual"
  }

  $bestIfIndex = $null
  if ($upAdapters) {
    $bestIfIndex = ($upAdapters | Select-Object -First 1).ifIndex
  } else {
    $bestIfIndex = ($adapters | Where-Object { $_.Status -eq "Up" } | Select-Object -First 1).ifIndex
  }

  Log "Best adapter ifIndex=$bestIfIndex"

  # Step 4: Remove duplicate default routes (keep the one on best adapter)
  $kept = $false
  foreach ($route in $defaultRoutes) {
    if ($route.InterfaceIndex -eq $bestIfIndex -and -not $kept) {
      Log ("KEEP default route: GW={0} ifIndex={1}" -f $route.NextHop, $route.InterfaceIndex)
      $kept = $true
    } else {
      try {
        Remove-NetRoute -DestinationPrefix "0.0.0.0/0" -InterfaceIndex $route.InterfaceIndex `
          -NextHop $route.NextHop -Confirm:$false -ErrorAction SilentlyContinue
        Log ("REMOVED duplicate default route: GW={0} ifIndex={1}" -f $route.NextHop, $route.InterfaceIndex)
      } catch {
        Log ("Failed to remove route GW={0} ifIndex={1}: {2}" -f $route.NextHop, $route.InterfaceIndex, $_.Exception.Message)
      }
    }
  }
}

# Step 5: Clean up persistent routes pointing to non-existent adapters
$existingIfIndices = @((Get-NetAdapter -ErrorAction SilentlyContinue).ifIndex)
$persistentRoutes = Get-NetRoute -AddressFamily IPv4 -PolicyStore PersistentStore -ErrorAction SilentlyContinue

if ($persistentRoutes) {
  foreach ($pr in $persistentRoutes) {
    if ($pr.InterfaceIndex -and $pr.InterfaceIndex -notin $existingIfIndices) {
      try {
        Remove-NetRoute -DestinationPrefix $pr.DestinationPrefix -InterfaceIndex $pr.InterfaceIndex `
          -NextHop $pr.NextHop -PolicyStore PersistentStore -Confirm:$false -ErrorAction SilentlyContinue
        Log ("REMOVED stale persistent route: dest={0} GW={1} ifIndex={2}" -f `
          $pr.DestinationPrefix, $pr.NextHop, $pr.InterfaceIndex)
      } catch {
        Log ("Failed to remove stale route: {0}" -f $_.Exception.Message)
      }
    }
  }
}

# Step 6: Ensure the active adapter has a proper metric
if ($bestIfIndex) {
  try {
    Set-NetIPInterface -InterfaceIndex $bestIfIndex -InterfaceMetric 10 `
      -AddressFamily IPv4 -ErrorAction SilentlyContinue
    Log "Set active adapter metric to 10 (preferred)"
  } catch {
    Log ("Failed to set metric: {0}" -f $_.Exception.Message)
  }
}

Log "=== Route cleanup complete ==="
""".lstrip()


def stage_route_cleanup(self, g: guestfs.GuestFS) -> dict[str, Any]:
    """
    Stage a firstboot PowerShell script to clean up duplicate routes.

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

    base_dir = "/hyper2kvm/route_cleanup"
    ps1_path = f"{base_dir}/cleanup-routes.ps1"

    try:
        with _step(logger, "🛤️ Stage duplicate route cleanup script"):
            _guest_mkdir_p(g, "/hyper2kvm", dry_run=dry_run)
            _guest_mkdir_p(g, base_dir, dry_run=dry_run)
            _guest_write_text(g, ps1_path, _build_route_cleanup_ps1(), dry_run=dry_run)

        result["staged"] = True
        result["artifacts"].append(
            {
                "kind": "route_cleanup_ps1",
                "dst": ps1_path,
                "action": "written" if not dry_run else "dry_run",
            }
        )
        result["notes"].append(
            r"Route cleanup script staged at C:\hyper2kvm\route_cleanup\cleanup-routes.ps1"
        )

        _log(logger, logging.INFO, "Route cleanup script staged: %s", ps1_path)

    except Exception as e:  # pylint: disable=broad-exception-caught
        # best-effort firstboot staging: any failure must not abort the whole migration
        msg = f"Route cleanup staging failed: {e}"
        result["warnings"].append(msg)
        _log(logger, logging.WARNING, "%s", msg)

    return result


__all__ = ["stage_route_cleanup"]
