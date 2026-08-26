# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/fixers/windows/virtio/install.py
"""
VirtIO driver installation pipeline stages.

This module contains the installation pipeline functions that handle
the sequential stages of VirtIO driver injection into Windows guests.
"""

# pylint: disable=too-many-lines
# too-many-lines: cohesive VirtIO installation pipeline broken into many small, single-purpose
# stage functions; splitting across files would scatter a tightly-coupled sequential pipeline.

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

try:
    import guestfs  # type: ignore
except ImportError:
    guestfs = None  # type: ignore

from hyper2kvm.fixers.windows.registry.firstboot import (
    log_firstboot_provision_summary,
    provision_firstboot_payload_and_service,
)
from hyper2kvm.fixers.windows.registry.mount import _ensure_windows_root
from hyper2kvm.fixers.windows.registry.software import append_devicepath_software_hive
from hyper2kvm.fixers.windows.registry.system import edit_system_hive

from .detection import DriverFile, WindowsVirtioPlan, _plan_to_dict
from .windows_virtio_config import DriverStartType, DriverType
from .windows_virtio_paths import WindowsSystemPaths, _guestfs_to_windows_path
from .windows_virtio_utils import (
    _guest_mkdir_p,
    _guest_sha256,
    _guest_write_text,
    _is_probably_driver_payload,
    _log,
    _safe_logger,
)


def _sha256_path(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# Injection pipeline (split into smaller functions)


VIRTIO_WIN_DIR = "/var/lib/hyper2kvm"
VIRTIO_WIN_ISO = f"{VIRTIO_WIN_DIR}/virtio-win.iso"


def _virtio_preflight(self, g: guestfs.GuestFS) -> tuple[Path | None, dict[str, Any] | None]:
    # pylint: disable=too-many-locals,too-many-branches,too-many-statements,import-outside-toplevel,broad-exception-caught
    # too-many-*: this preflight covers many independent, provider-specific pre-migration checks
    # (VirtIO discovery, BitLocker, RDP, firewall staging) as one cohesive gate function.
    # import-outside-toplevel: lazy imports avoid circular imports between fixer submodules and
    # keep optional checks from adding hard import-time dependencies.
    # broad-exception-caught: best-effort/fatal-decision fixer steps; each is deliberately scoped
    # (some re-raise, some log-and-continue) and must not crash on an unexpected exception type.
    logger = _safe_logger(self)
    virtio_dir = getattr(self, "virtio_drivers_dir", None)

    # If not explicitly set, auto-discover from standard locations
    if not virtio_dir:
        from hyper2kvm.fixers.windows.virtio_warning import VIRTIO_WIN_RPM_ISO

        for candidate in (VIRTIO_WIN_ISO, VIRTIO_WIN_RPM_ISO):
            std = Path(candidate)
            if std.exists():
                virtio_dir = str(std)
                _log(logger, logging.INFO, "VirtIO inject: using %s", virtio_dir)
                break

    if not virtio_dir:
        _log(logger, logging.INFO, "VirtIO inject: virtio_drivers_dir not set -> skip")

        # Even without VirtIO drivers, run critical Windows migration checks
        result = {"injected": False, "reason": "virtio_drivers_dir_not_set"}

        # Get root path for critical checks
        root = "/" if not hasattr(self, "inspect_root") else getattr(self, "inspect_root", "/")

        # CRITICAL: Check for BitLocker encryption
        try:
            from hyper2kvm.fixers.windows.bitlocker import check_bitlocker_before_migration

            _log(logger, logging.INFO, "🔒 Checking for BitLocker encryption...")
            check_bitlocker_before_migration(g, root, logger)
            result["bitlocker_check"] = {"passed": True}
        except Exception as e:
            # BitLocker detection errors are fatal - re-raise
            _log(logger, logging.ERROR, f"BitLocker check failed: {e}")
            raise

        # RDP Verification
        try:
            from hyper2kvm.fixers.windows.rdp import log_rdp_precheck_summary, verify_rdp_enabled

            _log(logger, logging.INFO, "🖥️  Verifying Remote Desktop configuration...")
            rdp_result = verify_rdp_enabled(g, root)
            result["rdp_check"] = rdp_result
            log_rdp_precheck_summary(logger, rdp_result, firstboot_planned=True)
        except Exception as e:
            _log(logger, logging.WARNING, f"RDP verification failed (non-fatal): {e}")
            result["rdp_check"] = {"error": str(e)}

        # Firewall Migration Staging
        try:
            from hyper2kvm.fixers.windows.firewall import stage_firewall_export_script

            _log(logger, logging.INFO, "🛡️  Staging firewall migration script...")
            firewall_result = stage_firewall_export_script(g, root)
            result["firewall_staging"] = firewall_result
            if firewall_result.get("staged"):
                _log(logger, logging.INFO, "✅ Firewall migration script staged")
            else:
                _log(logger, logging.WARNING, f"⚠️  Firewall staging failed: {firewall_result.get('error')}")
        except Exception as e:
            _log(logger, logging.WARNING, f"Firewall staging failed (non-fatal): {e}")
            result["firewall_staging"] = {"staged": False, "error": str(e)}

        # Emit detailed warning about performance impact
        try:
            from hyper2kvm.fixers.windows.virtio_warning import warn_no_virtio_drivers

            # Try to get Windows version info for specific recommendations
            try:
                from .detection import _windows_version_info
                from .windows_virtio_paths import _resolve_windows_system_paths

                paths = _resolve_windows_system_paths(self, g)
                win_info = _windows_version_info(self, g, paths=paths)
            except (ImportError, RuntimeError, KeyError, OSError) as version_err:
                logger.debug("Could not get Windows version info: %s", version_err)
                win_info = None

            warn_no_virtio_drivers(logger, win_info)
        except Exception as e:
            # Don't fail if warning fails
            _log(logger, logging.DEBUG, f"Could not emit VirtIO warning: {e}")

        return None, result

    virtio_src = Path(str(virtio_dir))
    if not virtio_src.exists():
        return None, {"injected": False, "reason": "virtio_drivers_dir_not_found", "path": str(virtio_src)}
    if not (virtio_src.is_dir() or virtio_src.suffix.lower() == ".iso"):
        return None, {"injected": False, "reason": "virtio_drivers_dir_invalid", "path": str(virtio_src)}

    # Import here to avoid circular dependency
    from .core import is_windows  # pylint: disable=cyclic-import

    if not is_windows(self, g):
        return None, {"injected": False, "reason": "not_windows"}
    if not getattr(self, "inspect_root", None):
        return None, {"injected": False, "reason": "no_inspect_root"}

    return virtio_src, None


def _virtio_ensure_system_volume(self, g: guestfs.GuestFS) -> WindowsSystemPaths:
    # pylint: disable=import-outside-toplevel  # avoid circular import between fixer submodules
    from .windows_virtio_paths import _resolve_windows_system_paths
    from .windows_virtio_utils import _step

    logger = _safe_logger(self)
    with _step(logger, "🧭 Ensure Windows system volume mounted (C: -> /)"):
        _ensure_windows_root(logger, g, hint_hive_path="/Windows/System32/config/SYSTEM")
    return _resolve_windows_system_paths(self, g)


def _virtio_ensure_temp_dir(self, g: guestfs.GuestFS, paths: WindowsSystemPaths, *, dry_run: bool) -> None:
    # pylint: disable=import-outside-toplevel,broad-exception-caught
    # import-outside-toplevel: avoid circular import between fixer submodules.
    # broad-exception-caught: best-effort fixer step, must not abort the whole migration.
    from .windows_virtio_utils import _step

    logger = _safe_logger(self)
    with _step(logger, "📁 Ensure Windows Temp dir exists"):
        try:
            _guest_mkdir_p(g, paths.temp_dir, dry_run=dry_run)
        except Exception as e:
            _log(logger, logging.WARNING, "Temp dir ensure failed (%s): %s", paths.temp_dir, e)


def _virtio_init_result(
    self, virtio_src: Path, win_info: dict[str, Any], plan: WindowsVirtioPlan, paths: WindowsSystemPaths
) -> dict[str, Any]:
    dry_run = bool(getattr(self, "dry_run", False))
    force_overwrite = bool(getattr(self, "force_virtio_overwrite", False))
    return {
        "injected": False,
        "success": False,
        "dry_run": bool(dry_run),
        "force_overwrite": bool(force_overwrite),
        "windows": win_info,
        "plan": _plan_to_dict(plan),
        "virtio_dir": str(virtio_src),
        "windows_paths": {
            "windows_dir": paths.windows_dir,
            "system32_dir": paths.system32_dir,
            "drivers_dir": paths.drivers_dir,
            "config_dir": paths.config_dir,
            "temp_dir": paths.temp_dir,
            "system_hive": paths.system_hive,
            "software_hive": paths.software_hive,
        },
        "drivers_found": [],
        "files_copied": [],
        "packages_staged": [],
        "registry_changes": {},
        "devicepath_changes": {},
        "bcd_changes": {},
        "firstboot": {},
        "artifacts": [],
        "warnings": [],
        "notes": [],
    }


def _virtio_copy_sys_binaries(
    self, g: guestfs.GuestFS, result: dict[str, Any], paths: WindowsSystemPaths, drivers: list[DriverFile]
) -> None:
    # pylint: disable=too-many-locals,import-outside-toplevel,broad-exception-caught
    # too-many-locals: per-driver upload/verify/report bookkeeping for a fault-tolerant copy loop.
    # import-outside-toplevel: avoid circular import between fixer submodules.
    # broad-exception-caught: best-effort per-driver copy step, must not abort the whole migration
    # over one driver's failure.
    from .windows_virtio_utils import _step

    logger = _safe_logger(self)
    dry_run = bool(result.get("dry_run"))
    force_overwrite = bool(result.get("force_overwrite"))

    with _step(logger, "🧱 Ensure System32\\drivers exists"):
        if not g.is_dir(paths.drivers_dir) and not dry_run:
            g.mkdir_p(paths.drivers_dir)

    logger.debug(
        "virtio_copy_sys_binaries: %d drivers to copy, dry_run=%s, force_overwrite=%s",
        len(drivers),
        dry_run,
        force_overwrite,
    )
    with _step(logger, "📦 Upload .sys driver binaries"):
        for drv in drivers:
            dest_path = f"{paths.drivers_dir}/{drv.dest_name}"
            try:
                src_size = drv.src_path.stat().st_size
                host_hash = _sha256_path(drv.src_path)
                logger.debug(
                    "Processing driver: %s -> %s (size=%d, sha256=%s, type=%s, service=%s)",
                    drv.src_path.name,
                    dest_path,
                    src_size,
                    host_hash[:12],
                    drv.type.value,
                    drv.service_name,
                )

                if g.is_file(dest_path) and not force_overwrite:
                    try:
                        guest_hash = _guest_sha256(g, dest_path)
                        if guest_hash and guest_hash == host_hash:
                            result["files_copied"].append(
                                {
                                    "name": drv.dest_name,
                                    "action": "skipped",
                                    "reason": "already_exists_same_hash",
                                    "source": str(drv.src_path),
                                    "destination": dest_path,
                                    "size": src_size,
                                    "sha256": host_hash,
                                    "type": drv.type.value,
                                    "service": drv.service_name,
                                }
                            )
                            result["artifacts"].append(
                                {
                                    "kind": "driver_sys",
                                    "service": drv.service_name,
                                    "type": drv.type.value,
                                    "src": str(drv.src_path),
                                    "dst": dest_path,
                                    "size": src_size,
                                    "sha256": host_hash,
                                    "action": "skipped",
                                }
                            )
                            _log(logger, logging.INFO, "Skip (same hash): %s -> %s", drv.src_path, dest_path)
                            continue
                    except Exception as hash_err:
                        _log(
                            logger,
                            logging.DEBUG,
                            "Could not verify hash of existing %s (will overwrite): %s",
                            dest_path,
                            hash_err,
                        )

                if not dry_run:
                    g.upload(str(drv.src_path), dest_path)

                verify = None
                if drv.type == DriverType.STORAGE and not dry_run:
                    try:
                        verify = _guest_sha256(g, dest_path)
                    except Exception as verify_err:
                        _log(
                            logger,
                            logging.DEBUG,
                            "Could not verify uploaded storage driver %s: %s",
                            dest_path,
                            verify_err,
                        )
                        verify = None

                action = "copied" if not dry_run else "dry_run"
                result["files_copied"].append(
                    {
                        "name": drv.dest_name,
                        "action": action,
                        "source": str(drv.src_path),
                        "destination": dest_path,
                        "size": src_size,
                        "sha256": host_hash,
                        "guest_sha256": verify,
                        "type": drv.type.value,
                        "service": drv.service_name,
                        "bucket_used": drv.bucket_used,
                        "match_pattern": drv.match_pattern,
                    }
                )
                result["artifacts"].append(
                    {
                        "kind": "driver_sys",
                        "service": drv.service_name,
                        "type": drv.type.value,
                        "src": str(drv.src_path),
                        "dst": dest_path,
                        "size": src_size,
                        "sha256": host_hash,
                        "guest_sha256": verify,
                        "action": action,
                        "bucket_used": drv.bucket_used,
                        "match_pattern": drv.match_pattern,
                    }
                )
                _log(logger, logging.INFO, "Upload: %s -> %s", drv.src_path, dest_path)
            except Exception as e:
                driver_purpose = {
                    "storage": "disk access (without this driver, Windows cannot boot from VirtIO disk)",
                    "network": "network connectivity (Windows will have no network after migration)",
                }.get(drv.type.value, f"{drv.type.value} device support")
                msg = (
                    f"Failed to copy VirtIO driver '{drv.dest_name}' ({drv.service_name}) "
                    f"to Windows guest: {e}. "
                    f"This driver provides {driver_purpose}. "
                    f"Ensure the VirtIO drivers directory is accessible and the guest disk is writable."
                )
                result["warnings"].append(msg)
                _log(logger, logging.WARNING, "%s", msg)


def _virtio_stage_packages(
    self, g: guestfs.GuestFS, result: dict[str, Any], drivers: list[DriverFile]
) -> tuple[str, str]:
    """
    Stage INF/CAT/DLL payloads so firstboot can pnputil /install them.

    Returns (staging_root_guestfs_path, devicepath_append_string)
    """
    # pylint: disable=too-many-locals,import-outside-toplevel,broad-exception-caught
    # too-many-locals: staging bookkeeping across multiple driver packages in one pass.
    # import-outside-toplevel: avoid circular import between fixer submodules.
    # broad-exception-caught: best-effort per-package staging step, must not abort the whole
    # migration over one package's failure.
    from .windows_virtio_utils import _step

    logger = _safe_logger(self)
    dry_run = bool(result.get("dry_run"))

    staging_root = "/hyper2kvm/drivers/virtio"
    devicepath_append = r"%SystemDrive%\hyper2kvm\drivers\virtio"

    with _step(logger, "📁 Stage driver packages (INF/CAT/DLL) for PnP"):
        try:
            _guest_mkdir_p(g, staging_root, dry_run=dry_run)
        except Exception as e:
            msg = f"VirtIO stage: failed to create staging root {staging_root}: {e}"
            result["warnings"].append(msg)
            _log(logger, logging.WARNING, "%s", msg)

        for drv in drivers:
            if not drv.package_dir or not drv.package_dir.exists() or not drv.inf_path:
                continue

            guest_pkg_dir = f"{staging_root}/{drv.service_name}"
            try:
                _guest_mkdir_p(g, guest_pkg_dir, dry_run=dry_run)
            except Exception as e:
                msg = f"VirtIO stage: cannot create {guest_pkg_dir}: {e}"
                result["warnings"].append(msg)
                _log(logger, logging.WARNING, "%s", msg)
                continue

            staged_files: list[dict[str, Any]] = []
            try:
                payload = sorted(
                    [p for p in drv.package_dir.iterdir() if p.is_file() and _is_probably_driver_payload(p)]
                )
                for p in payload:
                    gp = f"{guest_pkg_dir}/{p.name}"
                    try:
                        if not dry_run:
                            g.upload(str(p), gp)
                        staged_files.append(
                            {"name": p.name, "source": str(p), "dest": gp, "size": p.stat().st_size}
                        )
                        result["artifacts"].append(
                            {
                                "kind": "staged_payload",
                                "service": drv.service_name,
                                "type": drv.type.value,
                                "src": str(p),
                                "dst": gp,
                                "size": p.stat().st_size,
                                "action": "copied" if not dry_run else "dry_run",
                            }
                        )
                    except Exception as e:
                        msg = (
                            f"Failed to stage VirtIO driver package file '{p.name}' "
                            f"for {drv.service_name} driver: {e}. "
                            f"The driver INF/CAT files may not be available for PnP installation at first boot."
                        )
                        result["warnings"].append(msg)
                        _log(logger, logging.WARNING, "%s", msg)

                if staged_files:
                    result["packages_staged"].append(
                        {
                            "service": drv.service_name,
                            "type": drv.type.value,
                            "package_dir": str(drv.package_dir),
                            "inf": str(drv.inf_path),
                            "guest_dir": guest_pkg_dir,
                            "files": staged_files,
                        }
                    )
                    _log(
                        logger,
                        logging.INFO,
                        "Staged package: %s -> %s (%d files)",
                        drv.service_name,
                        guest_pkg_dir,
                        len(staged_files),
                    )
            except Exception as e:
                msg = (
                    f"Failed to stage VirtIO driver package for '{drv.service_name}': {e}. "
                    f"Without staged INF/CAT files, Windows PnP cannot install the {drv.service_name} driver "
                    f"at first boot. The driver .sys file was still copied to System32\\drivers."
                )
                result["warnings"].append(msg)
                _log(logger, logging.WARNING, "%s", msg)

    return staging_root, devicepath_append


def _virtio_stage_manual_setup_cmd(self, g: guestfs.GuestFS, result: dict[str, Any]) -> None:
    # pylint: disable=import-outside-toplevel,broad-exception-caught
    # import-outside-toplevel: avoid circular import between fixer submodules.
    # broad-exception-caught: best-effort fixer step, must not abort the whole migration.
    from .windows_virtio_utils import _step

    logger = _safe_logger(self)
    dry_run = bool(result.get("dry_run"))

    if not result.get("packages_staged"):
        return

    setup_script = "/hyper2kvm/setup.cmd"
    script_content = "@echo off\r\n"
    script_content += "echo Installing staged VirtIO drivers...\r\n"
    for staged in result["packages_staged"]:
        inf = staged.get("inf")
        if inf:
            inf_name = Path(str(inf)).name
            service_name = staged["service"]
            script_content += (
                f'pnputil /add-driver "C:\\hyper2kvm\\drivers\\virtio\\{service_name}\\{inf_name}" '
                "/install\r\n"
            )
    script_content += "echo Done.\r\n"

    try:
        with _step(logger, "🧾 Stage manual setup.cmd (optional)"):
            _guest_write_text(g, setup_script, script_content, dry_run=dry_run)
        result["setup_script"] = {"path": setup_script, "content": script_content}
        result["artifacts"].append(
            {"kind": "setup_cmd", "dst": setup_script, "action": "written" if not dry_run else "dry_run"}
        )
    except Exception as e:
        msg = f"Failed to stage setup.cmd: {e}"
        result["warnings"].append(msg)
        _log(logger, logging.WARNING, "%s", msg)


def _virtio_stage_guest_tools_installers(
    self,
    g: guestfs.GuestFS,
    result: dict[str, Any],
    virtio_src: Path,
    staging_root: str,
) -> None:
    """Stage VirtIO guest tools installers for Windows firstboot.

    Driver package staging copies INF/CAT/SYS payloads near discovered driver
    packages. The full guest tools installer and QEMU Guest Agent MSI live
    elsewhere on virtio-win media, so copy them explicitly to paths consumed by
    firstboot:
    C:\\hyper2kvm\\drivers\\virtio\\guest-agent\\virtio-win-guest-tools.exe.
    C:\\hyper2kvm\\drivers\\virtio\\guest-agent\\virtio-win-gt-x64.msi.
    C:\\hyper2kvm\\drivers\\virtio\\guest-agent\\virtio-win-gt-x86.msi.
    C:\\hyper2kvm\\drivers\\virtio\\guest-agent\\qemu-ga-x86_64.msi.
    """
    # pylint: disable=too-many-locals,too-many-branches,too-many-statements,import-outside-toplevel
    # pylint: disable=broad-exception-caught
    # too-many-*: staging bookkeeping across several installer candidates (guest tools exe, per-
    # arch MSIs, qemu-ga MSI) with fallback glob search for each, as one cohesive staging step.
    # import-outside-toplevel, cyclic-import: avoid circular import between fixer submodules.
    # broad-exception-caught: best-effort staging step, must not abort the whole migration.
    from .core import _materialize_virtio_source  # pylint: disable=cyclic-import
    from .windows_virtio_utils import _step

    logger = _safe_logger(self)
    dry_run = bool(result.get("dry_run"))
    guest_dir = f"{staging_root}/guest-agent"
    qemu_guest_path = f"{guest_dir}/qemu-ga-x86_64.msi"
    guest_tools_path = f"{guest_dir}/virtio-win-guest-tools.exe"
    virtio_driver_msi_paths = {
        "x64": f"{guest_dir}/virtio-win-gt-x64.msi",
        "x86": f"{guest_dir}/virtio-win-gt-x86.msi",
    }
    qemu_ga_candidates = [
        "guest-agent/qemu-ga-x86_64.msi",
        "guest-agent/qemu-ga-x64.msi",
        "qemu-ga-x86_64.msi",
        "qemu-ga-x64.msi",
    ]
    guest_tools_candidates = [
        "virtio-win-guest-tools.exe",
        "guest-agent/virtio-win-guest-tools.exe",
    ]
    virtio_driver_msi_candidates = {
        "x64": ["virtio-win-gt-x64.msi", "guest-agent/virtio-win-gt-x64.msi"],
        "x86": ["virtio-win-gt-x86.msi", "guest-agent/virtio-win-gt-x86.msi"],
    }

    with _step(logger, "📦 Stage VirtIO guest tools installers for firstboot"):
        try:
            with _materialize_virtio_source(self, virtio_src) as base:
                qemu_ga: Path | None = None
                for rel in qemu_ga_candidates:
                    p = base / rel
                    if p.exists() and p.is_file():
                        qemu_ga = p
                        break
                if qemu_ga is None:
                    matches = sorted(base.glob("**/qemu-ga*x64*.msi")) + sorted(
                        base.glob("**/qemu-ga*x86_64*.msi")
                    )
                    qemu_ga = matches[0] if matches else None

                guest_tools: Path | None = None
                for rel in guest_tools_candidates:
                    p = base / rel
                    if p.exists() and p.is_file():
                        guest_tools = p
                        break
                if guest_tools is None:
                    matches = sorted(base.glob("**/virtio-win-guest-tools.exe"))
                    guest_tools = matches[0] if matches else None

                virtio_driver_msis: dict[str, Path] = {}
                for arch, candidates in virtio_driver_msi_candidates.items():
                    for rel in candidates:
                        p = base / rel
                        if p.exists() and p.is_file():
                            virtio_driver_msis[arch] = p
                            break
                    if arch not in virtio_driver_msis:
                        matches = sorted(base.glob(f"**/virtio-win-gt-{arch}.msi"))
                        if matches:
                            virtio_driver_msis[arch] = matches[0]

                staged: list[dict[str, Any]] = []
                _guest_mkdir_p(g, guest_dir, dry_run=dry_run)

                def _stage_file(src: Path, dst: str, service: str, payload_type: str) -> None:
                    if not dry_run:
                        g.upload(str(src), dst)
                    item = {
                        "source": str(src),
                        "guest_path": dst,
                        "size": src.stat().st_size,
                        "action": "copied" if not dry_run else "dry_run",
                    }
                    staged.append({"service": service, "type": payload_type, **item})
                    result["artifacts"].append(
                        {
                            "kind": "staged_payload",
                            "service": service,
                            "type": payload_type,
                            "src": str(src),
                            "dst": dst,
                            "size": src.stat().st_size,
                            "action": "copied" if not dry_run else "dry_run",
                        }
                    )

                if guest_tools is not None:
                    _stage_file(guest_tools, guest_tools_path, "virtio-win-guest-tools", "guest-tools")
                    _log(
                        logger,
                        logging.INFO,
                        "Staged VirtIO guest tools installer: %s -> %s",
                        guest_tools,
                        guest_tools_path,
                    )
                else:
                    msg = (
                        "virtio-win-guest-tools.exe not found in VirtIO source; "
                        "firstboot will fall back to INF/MSI installs"
                    )
                    result.setdefault("warnings", []).append(msg)
                    _log(logger, logging.INFO, "%s", msg)

                for arch in ("x64", "x86"):
                    msi = virtio_driver_msis.get(arch)
                    if msi is not None:
                        _stage_file(
                            msi, virtio_driver_msi_paths[arch], f"virtio-win-gt-{arch}", "driver-msi"
                        )
                        _log(
                            logger,
                            logging.INFO,
                            "Staged VirtIO driver MSI (%s): %s -> %s",
                            arch,
                            msi,
                            virtio_driver_msi_paths[arch],
                        )
                    else:
                        _log(
                            logger, logging.INFO, "VirtIO driver MSI for %s not found in VirtIO source", arch
                        )

                if qemu_ga is not None:
                    _stage_file(qemu_ga, qemu_guest_path, "qemu-ga", "guest-agent")
                    _log(
                        logger,
                        logging.INFO,
                        "Staged QEMU Guest Agent MSI: %s -> %s",
                        qemu_ga,
                        qemu_guest_path,
                    )
                else:
                    msg = (
                        "QEMU Guest Agent MSI not found in VirtIO source; "
                        "firstboot may rely on virtio-win guest tools"
                    )
                    result.setdefault("warnings", []).append(msg)
                    _log(logger, logging.WARNING, "%s", msg)

                result["guest_tools_staging"] = {
                    "staged": len(staged) > 0,
                    "guest_dir": guest_dir,
                    "files": staged,
                }
        except Exception as e:
            msg = f"VirtIO guest tools installer staging failed: {e}"
            result["guest_tools_staging"] = {"staged": False, "error": str(e)}
            result.setdefault("warnings", []).append(msg)
            _log(logger, logging.WARNING, "%s", msg)


def _virtio_edit_registry_system(
    self, g: guestfs.GuestFS, result: dict[str, Any], paths: WindowsSystemPaths, drivers: list[DriverFile]
) -> None:
    # pylint: disable=import-outside-toplevel,broad-exception-caught
    # import-outside-toplevel: avoid circular import between fixer submodules.
    # broad-exception-caught: best-effort fixer step, must not abort the whole migration.
    from .windows_virtio_utils import _step

    logger = _safe_logger(self)
    with _step(logger, "🧬 Edit SYSTEM hive (Services + CDD + StartOverride + Remove VMware)"):
        try:
            reg_res = edit_system_hive(
                self,
                g,
                paths.system_hive,
                drivers,
                driver_type_storage_value=DriverType.STORAGE.value,
                boot_start_value=DriverStartType.BOOT.value,
            )
            result["registry_changes"] = reg_res
            if not reg_res.get("success"):
                _log(logger, logging.WARNING, "SYSTEM hive edit reported errors: %s", reg_res.get("errors"))

            # Report VMware removal stats
            vmware_removed = reg_res.get("vmware_services_removed", [])
            if vmware_removed:
                _log(
                    logger,
                    logging.INFO,
                    "Removed %d VMware services from registry: %s",
                    len(vmware_removed),
                    ", ".join(vmware_removed[:5]),
                )
        except Exception as e:
            result["registry_changes"] = {"success": False, "error": str(e)}
            msg = (
                f"Windows SYSTEM registry hive edit failed: {e}. "
                f"VirtIO driver services were NOT registered. Without registry entries, "
                f"the storage driver (viostor) will not load and Windows will BSOD on VirtIO boot. "
                f"Verify the SYSTEM hive at {paths.system_hive} is accessible and not corrupted."
            )
            result["warnings"].append(msg)
            _log(logger, logging.WARNING, "%s", msg)


def _virtio_remove_vmware_sys_files(
    self, g: guestfs.GuestFS, result: dict[str, Any], paths: WindowsSystemPaths
) -> None:
    """
    Delete VMware .sys driver files from System32\\drivers to prevent boot errors.
    """
    # pylint: disable=import-outside-toplevel,broad-exception-caught
    # import-outside-toplevel: avoid circular import between fixer submodules.
    # broad-exception-caught: best-effort per-file delete step, must not abort the whole migration.
    from .windows_virtio_utils import _step

    logger = _safe_logger(self)
    dry_run = bool(result.get("dry_run"))

    vmware_sys_files = [
        "vm3dmp.sys",
        "vmmouse.sys",
        "vmusbmouse.sys",
        "vmxnet3.sys",
        "vmxnet.sys",
        "vmhgfs.sys",
        "vmci.sys",
        "vmscsi.sys",
        "pvscsi.sys",
        "vmmemctl.sys",
        "vsock.sys",
        "vmrawdsk.sys",
    ]

    deleted = []
    with _step(logger, "🗑️ Remove VMware driver files from System32\\drivers"):
        for sys_file in vmware_sys_files:
            sys_path = f"{paths.drivers_dir}/{sys_file}"
            try:
                if g.is_file(sys_path):
                    if not dry_run:
                        g.rm(sys_path)
                    deleted.append(sys_file)
                    _log(logger, logging.INFO, "Deleted VMware driver: %s", sys_path)
            except Exception as e:
                _log(logger, logging.DEBUG, "VMware driver %s not found or cannot delete: %s", sys_file, e)

    result["vmware_sys_files_deleted"] = deleted
    if deleted:
        _log(logger, logging.INFO, "Removed %d VMware .sys files from System32\\drivers", len(deleted))


def _virtio_update_devicepath(
    self, g: guestfs.GuestFS, result: dict[str, Any], paths: WindowsSystemPaths, devicepath_append: str
) -> None:
    # pylint: disable=import-outside-toplevel,broad-exception-caught
    # import-outside-toplevel: avoid circular import between fixer submodules.
    # broad-exception-caught: best-effort fixer step, must not abort the whole migration.
    from .windows_virtio_utils import _step

    logger = _safe_logger(self)
    with _step(logger, "🧩 Update SOFTWARE DevicePath (PnP discovery)"):
        try:
            if result.get("packages_staged"):
                dp_res = append_devicepath_software_hive(self, g, paths.software_hive, devicepath_append)
                result["devicepath_changes"] = dp_res
                if not dp_res.get("success", True):
                    _log(
                        logger,
                        logging.WARNING,
                        "DevicePath update reported errors: %s",
                        dp_res.get("errors"),
                    )
            else:
                result["devicepath_changes"] = {"skipped": True, "reason": "no_packages_staged"}
                _log(logger, logging.INFO, "DevicePath: skipped (no packages staged)")
        except Exception as e:
            result["devicepath_changes"] = {"success": False, "error": str(e)}
            msg = (
                f"Windows SOFTWARE registry DevicePath update failed: {e}. "
                f"Windows PnP may not discover staged VirtIO drivers at first boot. "
                f"After boot, manually run: pnputil /add-driver C:\\hyper2kvm\\drivers\\virtio\\*\\*.inf /install"
            )
            result["warnings"].append(msg)
            _log(logger, logging.WARNING, "%s", msg)


def _virtio_provision_firstboot(
    self, g: guestfs.GuestFS, result: dict[str, Any], paths: WindowsSystemPaths, staging_root: str
) -> None:
    # pylint: disable=import-outside-toplevel,broad-exception-caught
    # import-outside-toplevel: avoid circular import between fixer submodules.
    # broad-exception-caught: best-effort fixer step, must not abort the whole migration.
    from .windows_virtio_utils import _step

    logger = _safe_logger(self)
    packages_staged = result.get("packages_staged") or []
    has_virtio_packages = len(packages_staged) > 0
    enable_rdp = getattr(self, "enable_rdp", None)
    if enable_rdp is None:
        enable_rdp = True
    if not has_virtio_packages:
        _log(
            logger,
            logging.INFO,
            "No VirtIO packages staged — provisioning firstboot for RDP, guest-agent, and cleanup",
        )
        staging_root = staging_root or "/hyper2kvm/drivers/virtio"

    log_path_guestfs = f"{paths.temp_dir}/hyper2kvm-firstboot.log"
    logger.debug(
        "Provisioning firstboot: packages_staged=%d, service=hyper2kvm-firstboot, "
        "log_path=%s, staging_root=%s, enhanced_virtio=%s",
        len(packages_staged),
        log_path_guestfs,
        staging_root,
        has_virtio_packages,
    )

    with _step(logger, "🛠️ Provision firstboot service (pnputil /install + logging)"):
        try:
            fb = provision_firstboot_payload_and_service(
                self,
                g,
                system_hive_path=paths.system_hive,
                service_name="hyper2kvm-firstboot",
                guest_dir="/hyper2kvm",
                log_path=log_path_guestfs,
                driver_stage_dir=staging_root,
                extra_cmd=None,
                remove_vmware_tools=True,
                # Enterprise features (matching Linux systemd firstboot)
                install_qemu_guest_agent=True,
                enhanced_virtio_install=has_virtio_packages,
                network_reconfiguration=True,
                enable_rdp=bool(enable_rdp),
                event_log_integration=True,
                health_verification=True,
                create_metadata=True,
            )
            result["firstboot"] = fb
            if not fb.get("success", True):
                msg = f"Firstboot provisioning failed: {fb.get('errors')}"
                result["warnings"].append(msg)
            log_firstboot_provision_summary(
                logger,
                fb,
                guest_log_windows_path=_guestfs_to_windows_path(log_path_guestfs),
                virtio_packages=len(packages_staged),
            )
            if not enable_rdp:
                logger.info(
                    "Firstboot RDP step skipped (enable_rdp=false) — enable Remote Desktop manually if needed"
                )
        except Exception as e:
            result["firstboot"] = {"success": False, "error": str(e)}
            msg = (
                f"Windows firstboot service provisioning failed: {e}. "
                f"The VirtIO driver .sys files are installed but the automatic "
                f"PnP installation (pnputil) will not run at first boot. "
                f"After boot, manually run: C:\\hyper2kvm\\setup.cmd"
            )
            result["warnings"].append(msg)
            _log(logger, logging.WARNING, "%s", msg)


def _virtio_provision_setup_complete(self, g: guestfs.GuestFS, result: dict[str, Any]) -> None:
    """Stage SetupComplete.cmd for automatic VirtIO driver installation.

    Windows runs C:\\Windows\\Setup\\Scripts\\SetupComplete.cmd automatically
    after setup/first boot. This script finds the virtio-win CD-ROM and
    runs virtio-win-guest-tools.exe /S (silent install of all drivers +
    guest agent) — no pnputil, no registry hacking, no user interaction.
    """
    # pylint: disable=import-outside-toplevel,broad-exception-caught
    # import-outside-toplevel: avoid circular import between fixer submodules.
    # broad-exception-caught: best-effort fixer step, must not abort the whole migration.
    from .windows_virtio_utils import _step

    logger = _safe_logger(self)

    setup_complete_script = (
        "@echo off\r\n"
        "setlocal enabledelayedexpansion\r\n"
        "\r\n"
        "set LOGFILE=C:\\Windows\\Logs\\virtio-install.log\r\n"
        "echo %DATE% %TIME% - VirtIO Driver Installation Started >> %LOGFILE%\r\n"
        "\r\n"
        "set DRIVE=\r\n"
        "for %%i in (D E F G H I J K L M N O P Q R S T U V W X Y Z) do (\r\n"
        "    if exist %%i:\\virtio-win-guest-tools.exe (\r\n"
        "        set DRIVE=%%i:\r\n"
        "        echo %DATE% %TIME% - Found VirtIO at !DRIVE! >> %LOGFILE%\r\n"
        "        goto :install\r\n"
        "    )\r\n"
        "    if exist %%i:\\guest-agent\\virtio-win-guest-tools.exe (\r\n"
        "        set DRIVE=%%i:\r\n"
        "        echo %DATE% %TIME% - Found VirtIO at !DRIVE!\\guest-agent >> %LOGFILE%\r\n"
        "        goto :install\r\n"
        "    )\r\n"
        ")\r\n"
        "echo %DATE% %TIME% - ERROR: VirtIO CD-ROM not found >> %LOGFILE%\r\n"
        "exit /b 1\r\n"
        "\r\n"
        ":install\r\n"
        "if exist %DRIVE%\\virtio-win-guest-tools.exe (\r\n"
        "    echo %DATE% %TIME% - Running: %DRIVE%\\virtio-win-guest-tools.exe /S >> %LOGFILE%\r\n"
        "    start /wait %DRIVE%\\virtio-win-guest-tools.exe /S /norestart\r\n"
        "    echo %DATE% %TIME% - Exit code: !ERRORLEVEL! >> %LOGFILE%\r\n"
        "    goto :complete\r\n"
        ")\r\n"
        "if exist %DRIVE%\\guest-agent\\virtio-win-guest-tools.exe (\r\n"
        "    echo %DATE% %TIME% - Running: %DRIVE%\\guest-agent\\virtio-win-guest-tools.exe /S >> %LOGFILE%\r\n"
        "    start /wait %DRIVE%\\guest-agent\\virtio-win-guest-tools.exe /S /norestart\r\n"
        "    echo %DATE% %TIME% - Exit code: !ERRORLEVEL! >> %LOGFILE%\r\n"
        "    goto :complete\r\n"
        ")\r\n"
        "\r\n"
        "echo %DATE% %TIME% - Fallback: pnputil INF install >> %LOGFILE%\r\n"
        "for /d %%d in (%DRIVE%\\*) do (\r\n"
        "    if exist %%d\\*.inf (\r\n"
        "        echo %DATE% %TIME% - Installing from %%~nd >> %LOGFILE%\r\n"
        '        pnputil /add-driver "%%d\\*.inf" /install >> %LOGFILE% 2>&1\r\n'
        "    )\r\n"
        ")\r\n"
        "\r\n"
        ":complete\r\n"
        "echo %DATE% %TIME% - VirtIO Driver Installation Complete >> %LOGFILE%\r\n"
        'pnputil /enum-drivers | findstr /i "virtio red hat" >> %LOGFILE% 2>&1\r\n'
        "exit /b 0\r\n"
    )

    script_size = len(setup_complete_script.encode("utf-8"))
    logger.debug("SetupComplete.cmd script size: %d bytes", script_size)

    with _step(logger, "📝 Stage SetupComplete.cmd (auto VirtIO install on first boot)"):
        try:
            scripts_dir = "/Windows/Setup/Scripts"
            g.mkdir_p(scripts_dir)
            guest_path = f"{scripts_dir}/SetupComplete.cmd"
            logger.debug("Writing SetupComplete.cmd to guest_path=%s", guest_path)
            g.write(guest_path, setup_complete_script.encode("utf-8"))
            result["setup_complete"] = {"staged": True, "guest_path": guest_path}
            _log(logger, logging.INFO, "SetupComplete.cmd staged: %s", guest_path)
        except Exception as e:
            result["setup_complete"] = {"staged": False, "error": str(e)}
            _log(logger, logging.WARNING, "SetupComplete.cmd staging failed (non-fatal): %s", e)


def _virtio_bcd_backup(self, g: guestfs.GuestFS, result: dict[str, Any]) -> None:
    # pylint: disable=import-outside-toplevel,broad-exception-caught,cyclic-import
    # import-outside-toplevel: avoid circular import between fixer submodules.
    # broad-exception-caught: best-effort fixer step, must not abort the whole migration.
    from .core import windows_bcd_actual_fix
    from .windows_virtio_utils import _step

    logger = _safe_logger(self)
    with _step(logger, "🧷 BCD store discovery + backup"):
        try:
            result["bcd_changes"] = windows_bcd_actual_fix(self, g)
        except Exception as e:
            result["bcd_changes"] = {"windows": True, "bcd": "error", "error": str(e)}
            msg = (
                f"Windows BCD (Boot Configuration Data) backup/check failed: {e}. "
                f"The BCD store controls Windows boot manager settings. "
                f"This is non-fatal but means no BCD backup was created. "
                f"If boot issues occur, use Windows recovery: bootrec /rebuildbcd"
            )
            result["warnings"].append(msg)
            _log(logger, logging.WARNING, "%s", msg)
