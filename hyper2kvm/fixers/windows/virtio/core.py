# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/fixers/windows/virtio/core.py
# pylint: disable=duplicate-code  # optional guestfs/hivex fallback block is repeated per-module boilerplate
"""
Windows VirtIO driver injection for VMware to KVM migration.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time as _time
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

try:
    import guestfs  # type: ignore
except ImportError:
    guestfs = None  # type: ignore

from hyper2kvm.core.utils import U
from hyper2kvm.fixers.windows.bitlocker import check_bitlocker_before_migration
from hyper2kvm.fixers.windows.firewall import stage_firewall_export_script
from hyper2kvm.fixers.windows.rdp import log_rdp_precheck_summary, verify_rdp_enabled

# Import from split modules - detection
from .detection import (
    DriverFile,
    WindowsVirtioPlan,
    _bucket_candidates,
    _choose_driver_plan,
    _plan_to_dict,
    _windows_version_info,
    is_windows,
)

# Import from split modules - discovery
from .discovery import _discover_virtio_drivers, _warn_if_driver_defs_suspicious

# Import from split modules - installation
from .install import (
    _virtio_bcd_backup,
    _virtio_copy_sys_binaries,
    _virtio_edit_registry_system,
    _virtio_ensure_system_volume,
    _virtio_ensure_temp_dir,
    _virtio_init_result,
    _virtio_preflight,
    _virtio_provision_firstboot,
    _virtio_provision_setup_complete,
    _virtio_remove_vmware_sys_files,
    _virtio_stage_guest_tools_installers,
    _virtio_stage_manual_setup_cmd,
    _virtio_stage_packages,
    _virtio_update_devicepath,
)

# Import from split modules - configuration
from .windows_virtio_config import (
    DEFAULT_VIRTIO_CONFIG,
    DriverStartType,
    DriverType,
    WindowsRelease,
    _load_virtio_config,
)

# Import from split modules - paths
from .windows_virtio_paths import (
    WindowsSystemPaths,
    _find_windows_root,
)

# Import from split modules - utilities
from .windows_virtio_utils import (
    _log,
    _log_mountpoints_best_effort,
    _safe_logger,
    _step,
)

# Optional ISO extractor
try:
    import pycdlib  # type: ignore
except ImportError:  # pragma: no cover
    pycdlib = None


# Public API exports
__all__ = [
    # Configuration
    "DEFAULT_VIRTIO_CONFIG",
    "DriverFile",
    "DriverStartType",
    # Enums and types
    "DriverType",
    "WindowsRelease",
    "WindowsSystemPaths",
    "WindowsVirtioPlan",
    "inject_virtio_drivers",
    # Public API functions
    "is_windows",
    "windows_bcd_actual_fix",
]


# VirtIO source materialization (dir OR ISO)


_VIRTIO_CACHE_DIR = Path("/var/lib/hyper2kvm/virtio-win-extracted")


def _iso_cache_is_valid(cache_dir: Path, iso_path: Path) -> bool:
    """Check if cached extraction is still valid by comparing ISO mtime."""
    stamp = cache_dir / ".iso_mtime"
    if not stamp.exists() or not (cache_dir / "viostor").is_dir():
        return False
    try:
        cached_mtime = float(stamp.read_text().strip())
        return cached_mtime == iso_path.stat().st_mtime
    except (OSError, ValueError):
        return False


def _write_cache_stamp(cache_dir: Path, iso_path: Path) -> None:
    """Write ISO mtime stamp so we know when to re-extract."""
    stamp = cache_dir / ".iso_mtime"
    try:
        stamp.write_text(str(iso_path.stat().st_mtime))
    except OSError:
        pass


def _extract_iso_bsdtar(iso_path: Path, dest: Path, logger: logging.Logger) -> bool:
    """Extract ISO using bsdtar (handles Rock Ridge names correctly)."""
    bsdtar = shutil.which("bsdtar")
    if not bsdtar:
        return False
    try:
        result = subprocess.run(
            [bsdtar, "xf", str(iso_path), "-C", str(dest)],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        # bsdtar may warn about hardlinks but still extract successfully
        if result.returncode != 0 and not (dest / "viostor").is_dir():
            _log(logger, logging.DEBUG, "bsdtar failed: %s", result.stderr[:500])
            return False
        return True
    except (OSError, subprocess.SubprocessError) as e:
        _log(logger, logging.DEBUG, "bsdtar extraction error: %s", e)
        return False


def _extract_iso_pycdlib_rr(iso_path: Path, dest: Path, logger: logging.Logger) -> bool:
    """Extract ISO using pycdlib with Rock Ridge name support."""
    if pycdlib is None:
        return False
    try:
        iso = pycdlib.PyCdlib()
        iso.open(str(iso_path))
        extracted = 0

        def _walk_rr(iso_dir: str, real_dir: str):
            """Walk ISO tree, using Rock Ridge names for output paths."""
            nonlocal extracted
            try:
                kids = iso.list_children(iso_path=iso_dir)
            except Exception:  # pylint: disable=broad-exception-caught  # pycdlib (dynamic/optional library) can raise its own error types
                return
            for c in kids:
                try:
                    iso_name = c.file_identifier().decode("utf-8", errors="ignore").rstrip(";1")
                except Exception:  # pylint: disable=broad-exception-caught  # pycdlib (dynamic/optional library) can raise its own error types
                    continue
                if iso_name in (".", "..") or not iso_name:
                    continue

                # Prefer Rock Ridge name (preserves case and long names like w11, w8.1)
                rr_name = None
                if c.rock_ridge is not None:
                    try:
                        rr_name = c.rock_ridge.name().decode("utf-8", errors="ignore")
                    except Exception:  # pylint: disable=broad-exception-caught  # pycdlib (dynamic/optional library) can raise its own error types
                        pass
                out_name = rr_name or iso_name

                child_iso = iso_dir.rstrip("/") + "/" + iso_name
                child_real = real_dir.rstrip("/") + "/" + out_name

                if c.is_dir():
                    _walk_rr(child_iso, child_real)
                else:
                    out = dest / child_real.lstrip("/")
                    out.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        iso.get_file_from_iso(str(out), iso_path=child_iso)
                        extracted += 1
                    except Exception as e:  # pylint: disable=broad-exception-caught  # pycdlib is a dynamic library; skip this file, keep extracting
                        _log(logger, logging.DEBUG, "pycdlib extract failed for %s: %s", child_iso, e)

        _walk_rr("/", "/")

        with suppress(Exception):
            iso.close()

        _log(logger, logging.DEBUG, "pycdlib Rock Ridge extraction: %d files", extracted)
        return extracted > 0
    except Exception as e:  # pylint: disable=broad-exception-caught  # pycdlib (dynamic/optional library) can raise its own error types
        _log(logger, logging.DEBUG, "pycdlib extraction error: %s", e)
        return False


@contextmanager
def _materialize_virtio_source(self, virtio_path: Path):
    """
    Context manager to materialize VirtIO driver source.

    Accepts either:
    - Directory: yields as-is
    - ISO file: extracts once to persistent cache, reuses on subsequent runs

    The cache is stored at /var/lib/hyper2kvm/virtio-win-extracted/ and is
    invalidated when the ISO file changes (mtime check).

    Extraction prefers bsdtar (handles Rock Ridge long names like w11, w8.1
    correctly) and falls back to pycdlib with Rock Ridge support.
    """
    logger = _safe_logger(self)

    if virtio_path.is_dir():
        yield virtio_path
        return

    if virtio_path.suffix.lower() != ".iso":
        raise RuntimeError(f"virtio_drivers_dir must be a directory or .iso, got: {virtio_path}")

    cache_dir = _VIRTIO_CACHE_DIR

    # Reuse cached extraction if ISO hasn't changed
    if _iso_cache_is_valid(cache_dir, virtio_path):
        _log(logger, logging.INFO, "📀 Using cached VirtIO extraction: %s", cache_dir)
        yield cache_dir
        return

    # Extract fresh
    _log(
        logger, logging.INFO, "📀 Extracting VirtIO ISO -> %s (one-time, cached for future runs)", cache_dir
    )

    # Clean stale cache
    if cache_dir.exists():
        shutil.rmtree(cache_dir, ignore_errors=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Try bsdtar first (Rock Ridge aware), fall back to pycdlib
    ok = _extract_iso_bsdtar(virtio_path, cache_dir, logger)
    if not ok:
        _log(logger, logging.INFO, "📀 bsdtar not available, falling back to pycdlib")
        ok = _extract_iso_pycdlib_rr(virtio_path, cache_dir, logger)

    if not ok:
        shutil.rmtree(cache_dir, ignore_errors=True)
        raise RuntimeError(
            "Failed to extract VirtIO ISO. Install bsdtar (libarchive) or pycdlib, "
            "or provide an already-extracted virtio-win directory."
        )

    _write_cache_stamp(cache_dir, virtio_path)
    _log(logger, logging.INFO, "📀 VirtIO ISO extracted and cached successfully")
    yield cache_dir


# Public: BCD backup + hints (offline-safe)


def windows_bcd_actual_fix(  # pylint: disable=too-many-locals  # probes/backs up several independent BCD store locations (BIOS + multiple UEFI paths)
    self, g: guestfs.GuestFS
) -> dict[str, Any]:
    """
    Discover and back up Windows BCD stores (Boot Configuration Data).

    This is an offline-safe operation that:
    1. Locates BCD stores (BIOS and UEFI locations)
    2. Creates backups with timestamps
    3. Provides boot mode hints based on discovered stores

    NOTE: Deep BCD edits (e.g., boot device changes) require Windows tools
    (bcdedit/bootrec) run inside Windows Recovery Environment.

    Args:
        self: Context object with logger and optional dry_run flag
        g: GuestFS handle with Windows system volume mounted at /

    Returns:
        Dict with:
        - windows: bool - Whether this is a Windows system
        - bcd: str - Status: "found", "no_bcd_store", "no_windows_directory", "error"
        - stores: Dict of discovered BCD stores (path, size, exists status)
        - backups: Dict of created backups (backup_path, timestamp, size)
        - notes: List of hints about boot mode (UEFI vs BIOS)
        - reason: str (only if windows=False)
    """
    _safe_logger(self)

    if not is_windows(self, g):
        return {"windows": False, "reason": "not_windows"}

    windows_root = _find_windows_root(self, g)
    if not windows_root:
        return {"windows": True, "bcd": "no_windows_directory"}

    bcd_stores = {
        "bios": f"{windows_root}/Boot/BCD",
        "uefi_standard": "/boot/efi/EFI/Microsoft/Boot/BCD",
        "uefi_alternative": "/boot/EFI/Microsoft/Boot/BCD",
        "uefi_fallback": "/efi/EFI/Microsoft/Boot/BCD",
        "uefi_root": "/EFI/Microsoft/Boot/BCD",
    }

    found: dict[str, Any] = {}
    backups: dict[str, Any] = {}
    dry_run = getattr(self, "dry_run", False)

    for store_type, store_path in bcd_stores.items():
        try:
            if g.is_file(store_path):
                size = g.filesize(store_path)
                found[store_type] = {"path": store_path, "size": size, "exists": True}
                if not dry_run:
                    ts = U.now_ts()
                    backup_path = f"{store_path}.backup.hyper2kvm.{ts}"
                    try:
                        g.cp(store_path, backup_path)
                        backups[store_type] = {"backup_path": backup_path, "timestamp": ts, "size": size}
                    except Exception as be:  # pylint: disable=broad-exception-caught  # guestfs is a dynamic library; backup is best-effort per store
                        backups[store_type] = {"error": str(be), "path": store_path}
            else:
                found[store_type] = {"path": store_path, "exists": False}
        except Exception as e:  # pylint: disable=broad-exception-caught  # guestfs is a dynamic library; probing one store must not abort the others
            found[store_type] = {"path": store_path, "exists": False, "error": str(e)}

    if not any(v.get("exists") for v in found.values()):
        return {"windows": True, "bcd": "no_bcd_store", "stores": found}

    notes: list[str] = [
        "Offline-safe: backups created where possible.",
        "Deep BCD edits need Windows tools (bcdedit/bootrec) inside Windows RE.",
    ]

    has_uefi = any(
        found.get(k, {}).get("exists")
        for k in ("uefi_standard", "uefi_alternative", "uefi_fallback", "uefi_root")
    )
    has_bios = found.get("bios", {}).get("exists")

    if has_uefi and not has_bios:
        notes.append("Hint: UEFI-style BCD present; boot the converted VM in UEFI mode.")
    if has_bios and not has_uefi:
        notes.append("Hint: BIOS-style BCD present; boot the converted VM in legacy BIOS mode.")
    if has_bios and has_uefi:
        notes.append("Hint: Both BIOS+UEFI BCD stores found; boot mode must match installed Windows mode.")

    return {"windows": True, "bcd": "found", "stores": found, "backups": backups, "notes": notes}


# Finalization + reporting


def _virtio_finalize(
    self, result: dict[str, Any], drivers: list[DriverFile], *, plan: WindowsVirtioPlan, cfg: dict[str, Any]
) -> dict[str, Any]:
    """
    Finalize VirtIO injection result.

    Updates result dict with:
    - drivers_found: List of discovered driver details
    - injected/success: Overall success status
    - notes: Detailed information about detection, discovery, installation
    - warnings: Critical issues (missing storage drivers)
    - report_exported: Path to JSON report (if export_report=True)

    Args:
        self: Context object with logger and optional export_report flag
        result: Accumulating result dict
        drivers: List of discovered driver files
        plan: Windows driver plan (release, arch, bucket)
        cfg: VirtIO configuration dict

    Returns:
        Updated result dict
    """
    logger = _safe_logger(self)

    result["drivers_found"] = [d.to_dict() for d in drivers]

    sys_ok = any(x.get("action") in ("copied", "dry_run", "skipped") for x in result.get("files_copied", []))
    reg_ok = bool(result.get("registry_changes", {}).get("success"))
    result["injected"] = bool(sys_ok and reg_ok)
    result["success"] = result["injected"]
    if not result["success"]:
        result["reason"] = "registry_update_failed" if not reg_ok else "sys_copy_failed"

    storage_found = sorted({d.service_name for d in drivers if d.type == DriverType.STORAGE})
    storage_missing: list[str] = []
    if "viostor" not in storage_found:
        storage_missing.append("viostor")
    if "vioscsi" not in storage_found:
        storage_missing.append("vioscsi")

    result["notes"] += [
        "Release detection: prefers ProductName + build number (CurrentBuildNumber/CurrentBuild) over major/minor.",
        "Config-driven: driver definitions + OS(bucket) mapping can come from "
        "YAML/JSON config (self.config) or an override file.",
        "Config merge: dicts deep-merge; lists are replaced (override wins).",
        "Default release fallback: Windows 11.",
        "Driver discovery: canonical pattern first; fallback globs warn on multiple matches and pick a best candidate.",
        "Storage: injects viostor + vioscsi when present and forces BOOT start in SYSTEM hive.",
        "Registry: StartOverride removed when found (can silently disable boot drivers).",
        "CDD: CriticalDeviceDatabase populated for virtio storage PCI IDs to ensure early binding.",
        f"Driver discovery buckets: {_bucket_candidates(plan.release, cfg)}",
        f"Storage drivers found: {storage_found} missing: {storage_missing}",
        r"Staging: payload staged under C:\hyper2kvm\drivers\virtio and installed via firstboot service (pnputil).",
        r"Logs: see the 'firstboot' section for the exact log path.",
    ]

    if storage_missing:
        msg = (
            f"Missing critical storage drivers: {storage_missing} (guest may BSOD INACCESSIBLE_BOOT_DEVICE)"
        )
        result["warnings"].append(msg)
        _log(logger, logging.WARNING, "%s", msg)

    export_report = bool(getattr(self, "export_report", False))
    if export_report:
        report_path = "virtio_inject_report.json"
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)
            result["report_exported"] = report_path
            _log(logger, logging.INFO, "Report exported: %s", report_path)
        except OSError as e:
            msg = f"Failed to export report: {e}"
            result["warnings"].append(msg)
            _log(logger, logging.WARNING, "%s", msg)

    return result


# Public: VirtIO injection orchestration


def inject_virtio_drivers(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements  # orchestrates the full multi-stage VirtIO injection pipeline (see docstring)
    self, g: guestfs.GuestFS
) -> dict[str, Any]:
    """
    Inject VirtIO drivers into a Windows guest image (main entry point).

    This orchestrates the complete VirtIO injection pipeline:
    1. Preflight checks (Windows detection, virtio_drivers_dir validation)
    2. **CRITICAL: BitLocker encryption detection (blocks migration if encrypted)**
    3. Configuration loading and driver plan creation
    4. Driver discovery from source directory/ISO
    5. System volume mounting and path resolution
    6. Driver binary (.sys) upload to System32\\drivers
    7. Driver package staging (INF/CAT/DLL) for PnP installation
    8. Registry edits (SYSTEM hive: Services, CDD, StartOverride)
    9. **NEW: RDP verification (warns if disabled)**
    10. **NEW: Firewall migration staging (preserves firewall rules)**
    11. DevicePath update (SOFTWARE hive) for PnP discovery
    12. Firstboot service provisioning (pnputil /install on first boot)
    13. BCD backup and boot mode detection

    Args:
        self: Context object with configuration attributes:
            - virtio_drivers_dir: Path - VirtIO source (directory or .iso)
            - inspect_root: str - GuestFS inspect root
            - dry_run: bool (optional) - Skip actual writes
            - force_virtio_overwrite: bool (optional) - Overwrite existing drivers
            - enable_virtio_gpu/input/fs/serial/rng: bool (optional) - Enable extra drivers
            - virtio_config/virtio_config_path/virtio_config_inline_json: (optional) - Config overrides
            - config: Dict (optional) - Merged app config
            - export_report: bool (optional) - Export JSON report
            - logger: logging.Logger (optional)
        g: GuestFS handle (should be launched but not mounted)

    Returns:
        Dict with comprehensive injection status:
        - injected: bool - Overall success
        - success: bool - Same as injected
        - dry_run: bool - Whether this was a dry run
        - windows: Dict - Windows version info (build, product_name, arch, major, minor)
        - plan: Dict - Driver plan (release, arch_dir, bucket_hint, drivers_needed)
        - drivers_found: List[Dict] - Discovered drivers with metadata
        - files_copied: List[Dict] - Uploaded .sys files
        - packages_staged: List[Dict] - Staged INF/CAT/DLL packages
        - registry_changes: Dict - SYSTEM hive edit results
        - devicepath_changes: Dict - SOFTWARE hive DevicePath update results
        - firstboot: Dict - Firstboot service provisioning results
        - bcd_changes: Dict - BCD discovery and backup results
        - bitlocker_check: Dict - BitLocker detection results (NEW)
        - rdp_check: Dict - RDP verification results (NEW)
        - firewall_staging: Dict - Firewall migration staging results (NEW)
        - artifacts: List[Dict] - All created artifacts
        - warnings: List[str] - Non-fatal issues
        - notes: List[str] - Detailed information about the injection
        - reason: str (only if injected=False) - Failure reason

    Raises:
        BitLockerDetectionError: If BitLocker encryption detected (blocks migration)
        Exception: Critical failures during injection (logged and returned in result)
    """
    logger = _safe_logger(self)

    _t0 = _time.monotonic()

    logger.debug("inject_virtio_drivers: starting VirtIO injection pipeline")
    logger.debug(
        "inject_virtio_drivers: dry_run=%s, force_overwrite=%s, virtio_drivers_dir=%s",
        getattr(self, "dry_run", False),
        getattr(self, "force_virtio_overwrite", False),
        getattr(self, "virtio_drivers_dir", None),
    )

    virtio_src, early = _virtio_preflight(self, g)
    if early is not None:
        logger.debug(
            "inject_virtio_drivers: preflight returned early result: %s", early.get("reason", "N/A")
        )
        return early
    if virtio_src is None:
        logger.debug("inject_virtio_drivers: virtio_src is None after preflight")
        return {"injected": False, "reason": "virtio_src_missing"}

    logger.debug("inject_virtio_drivers: virtio source resolved to %s", virtio_src)

    cfg = _load_virtio_config(self)
    _warn_if_driver_defs_suspicious(self, cfg)

    _log_mountpoints_best_effort(logger, g)

    paths = _virtio_ensure_system_volume(self, g)
    if not paths.windows_dir or not g.is_dir(paths.windows_dir):
        logger.debug("inject_virtio_drivers: no Windows root found at %s", paths.windows_dir)
        return {"injected": False, "reason": "no_windows_root", "windows_dir": paths.windows_dir}

    # CRITICAL: Check for BitLocker encryption before making any modifications
    # This prevents BSOD/data corruption from attempting to modify encrypted volumes
    root = "/" if not hasattr(self, "inspect_root") else getattr(self, "inspect_root", "/")

    _log(logger, logging.INFO, "🔒 Checking for BitLocker encryption...")
    # BitLockerDetectionError will be raised and propagated to caller.
    # This blocks migration, which is the correct behavior.
    check_bitlocker_before_migration(g, root, logger)

    dry_run = bool(getattr(self, "dry_run", False))
    _virtio_ensure_temp_dir(self, g, paths, dry_run=dry_run)

    win_info = _windows_version_info(self, g, paths=paths)
    logger.debug(
        "inject_virtio_drivers: Windows version info: build=%s, product=%s, arch=%s",
        win_info.get("build"),
        win_info.get("product_name"),
        win_info.get("arch"),
    )
    plan = _choose_driver_plan(self, win_info, cfg)
    logger.debug(
        "inject_virtio_drivers: driver plan: release=%s, arch_dir=%s, bucket=%s",
        plan.release,
        plan.arch_dir,
        plan.bucket_hint,
    )

    with _step(logger, "🔎 Discover VirtIO drivers"):
        drivers = _discover_virtio_drivers(self, virtio_src, plan, cfg)

    logger.debug("inject_virtio_drivers: discovered %d drivers", len(drivers) if drivers else 0)
    if not drivers:
        return {
            "injected": False,
            "reason": "no_drivers_found",
            "virtio_dir": str(virtio_src),
            "windows_info": win_info,
            "plan": _plan_to_dict(plan),
            "buckets_tried": _bucket_candidates(plan.release, cfg),
            "windows_paths": {
                "windows_dir": paths.windows_dir,
                "system32_dir": paths.system32_dir,
                "drivers_dir": paths.drivers_dir,
                "config_dir": paths.config_dir,
                "temp_dir": paths.temp_dir,
            },
        }

    result = _virtio_init_result(self, virtio_src, win_info, plan, paths)

    try:
        _virtio_copy_sys_binaries(self, g, result, paths, drivers)
    except Exception as e:  # pylint: disable=broad-exception-caught  # guestfs is a dynamic library; any binary-copy failure must abort injection cleanly
        return {**result, "reason": f"sys_copy_failed: {e}"}

    staging_root, devicepath_append = _virtio_stage_packages(self, g, result, drivers)

    _virtio_stage_manual_setup_cmd(self, g, result)
    _virtio_stage_guest_tools_installers(self, g, result, virtio_src, staging_root)
    _virtio_edit_registry_system(self, g, result, paths, drivers)
    _virtio_remove_vmware_sys_files(self, g, result, paths)

    # NEW: Critical Windows migration features (after registry edits)
    # These run regardless of whether VirtIO drivers are being injected

    # RDP Verification: Warn if Remote Desktop is disabled (prevents admin lockout)
    try:
        _log(logger, logging.INFO, "🖥️  Verifying Remote Desktop configuration...")
        rdp_result = verify_rdp_enabled(g, root)
        result["rdp_check"] = rdp_result
        rdp_at_boot = getattr(self, "enable_rdp", None)
        if rdp_at_boot is None:
            rdp_at_boot = True
        log_rdp_precheck_summary(logger, rdp_result, firstboot_planned=bool(rdp_at_boot))

        if not rdp_result.get("rdp_enabled"):
            msg = "Remote Desktop may be disabled - admin access may be limited after migration"
            result["warnings"].append(msg)
    except Exception as e:  # pylint: disable=broad-exception-caught  # non-fatal best-effort check; must not abort VirtIO injection over RDP verification
        _log(logger, logging.WARNING, "RDP verification failed (non-fatal): %s", e)
        result["rdp_check"] = {"error": str(e)}

    # Firewall Migration: Stage PowerShell script to preserve firewall rules
    try:
        _log(logger, logging.INFO, "🛡️  Staging firewall migration script...")
        firewall_result = stage_firewall_export_script(g, root)
        result["firewall_staging"] = firewall_result

        if firewall_result.get("staged"):
            _log(
                logger,
                logging.INFO,
                "✅ Firewall migration script staged: %s",
                firewall_result.get("script_path", "unknown"),
            )
            if firewall_result.get("task_staged"):
                _log(logger, logging.INFO, "✅ Scheduled task created for first boot")
        else:
            msg = "Firewall migration staging failed - rules may need manual migration"
            result["warnings"].append(msg)
            _log(logger, logging.WARNING, "⚠️  %s", msg)
            if firewall_result.get("error"):
                _log(logger, logging.WARNING, "   Error: %s", firewall_result["error"])
    except Exception as e:  # pylint: disable=broad-exception-caught  # non-fatal best-effort staging; must not abort VirtIO injection over firewall export
        _log(logger, logging.WARNING, "Firewall staging failed (non-fatal): %s", e)
        result["firewall_staging"] = {"staged": False, "error": str(e)}

    _virtio_update_devicepath(self, g, result, paths, devicepath_append)
    _virtio_provision_setup_complete(self, g, result)
    _virtio_provision_firstboot(self, g, result, paths, staging_root)
    _virtio_bcd_backup(self, g, result)

    _elapsed = _time.monotonic() - _t0
    logger.debug(
        "inject_virtio_drivers: pipeline completed in %.1fs, files_copied=%d, "
        "packages_staged=%d, warnings=%d",
        _elapsed,
        len(result.get("files_copied", [])),
        len(result.get("packages_staged", [])),
        len(result.get("warnings", [])),
    )
    return _virtio_finalize(self, result, drivers, plan=plan, cfg=cfg)
