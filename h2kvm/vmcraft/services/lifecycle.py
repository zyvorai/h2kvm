# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Lifecycle orchestration helpers for VMCraft."""

from __future__ import annotations

import contextlib
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from h2kvm.core.structured_log import (
    PhaseTimer,
    TraceContext,
    log_event,
    log_execution_summary,
)
from h2kvm.vmcraft.nbd import NBDDeviceManager, NBDSecurity
from h2kvm.vmcraft.storage import StorageStackActivator

# pylint: disable=protected-access
# This module implements the VMCraft manager's launch/shutdown internals as free
# functions (split out of main.py to keep that class' size manageable). `vm` is
# always the VMCraft instance itself, so these are not third-party internals being
# reached into -- they are this subsystem's own private state, accessed by design.


def _best_effort_step(vm, action, success_message: str, warning_template: str) -> None:
    """Execute a cleanup action and convert errors to warnings."""
    try:
        action()
        vm.logger.info(success_message)
    except Exception as e:  # pylint: disable=broad-exception-caught  # action is an arbitrary cleanup callable; must not abort shutdown over one step's failure
        vm.logger.warning(warning_template, e)


def _reset_runtime_fields(vm) -> None:
    """Clear runtime manager/object references on the VM instance."""
    for attr in [
        "_nbd_manager",
        "_storage_activator",
        "_mount_manager",
        "_file_ops",
        "_linux_detector",
        "_windows_detector",
        "_os_inspector",
        "_win_registry",
        "_win_drivers",
        "_win_users",
        "_linux_services",
        "_backup_mgr",
        "_security_auditor",
        "_disk_optimizer",
    ]:
        setattr(vm, attr, None)
    # Multi-drive per-drive state lists
    vm._nbd_managers = []
    vm._nbd_devices = []
    vm._storage_activators = []


def _build_security(vm, drive: dict) -> NBDSecurity:
    """Build an NBDSecurity instance for *drive*, including user-specified dirs."""
    security = NBDSecurity(vm.logger)

    # Always allow the parent directory of the input image (graceful default)
    try:
        image_parent = Path(drive["path"]).resolve().parent
        security.add_allowed_directory(image_parent)
        vm.logger.debug("Auto-allowed image parent directory: %s", image_parent)
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort default; add_allowed_directory's validation errors vary
        vm.logger.debug("Could not auto-allow image parent directory: %s", e)

    # Add user-specified allowed directories if provided
    if hasattr(vm, "_allowed_dirs") and vm._allowed_dirs:
        for dir_path in vm._allowed_dirs:
            try:
                security.add_allowed_directory(Path(dir_path))
                vm.logger.debug("Added allowed directory: %s", dir_path)
            except Exception as e:  # pylint: disable=broad-exception-caught  # one bad dir must not abort the rest; validation errors vary
                vm.logger.warning("Failed to add allowed directory %s: %s", dir_path, e)

    return security


def _connect_drive(vm, idx: int, drive: dict, security: NBDSecurity) -> tuple[str, float]:
    """Connect a single drive via NBD and return (nbd_device, elapsed_seconds)."""
    image_name = Path(drive["path"]).name
    phase_label = f"nbd_drive{idx}"

    with PhaseTimer(
        f"nbd_connect_start_drive{idx}",
        f"nbd_connect_complete_drive{idx}",
        phase=phase_label,
    ):
        nbd_start = time.time()
        manager = NBDDeviceManager(
            vm.logger,
            readonly=drive["readonly"],
            conversion_dir=vm._conversion_dir,
            security=security,
        )
        nbd_device = manager.connect(
            drive["path"],
            format=drive.get("format"),
            readonly=drive["readonly"],
        )
        elapsed = time.time() - nbd_start

    vm._nbd_managers.append(manager)
    vm._nbd_devices.append(nbd_device)
    vm.logger.info(
        "   Drive %d NBD connected: %s -> %s (%.2fs)",
        idx,
        image_name,
        nbd_device,
        elapsed,
    )
    return nbd_device, elapsed


def _activate_storage_for_drive(
    vm,
    idx: int,
    nbd_device: str,
) -> tuple[dict, float]:
    """Activate the storage stack for a single NBD device and return (audit, elapsed)."""
    with PhaseTimer(
        f"storage_activate_start_drive{idx}",
        f"storage_activate_complete_drive{idx}",
        phase=f"lvm_drive{idx}",
    ):
        storage_start = time.time()
        activator = StorageStackActivator(
            vm.logger,
            container_isolation=getattr(vm, "_container_isolation", True),
        )
        activator.nbd_device = nbd_device
        audit = activator.activate_all()
        elapsed = time.time() - storage_start

    vm._storage_activators.append(activator)
    vm.logger.info("   Drive %d storage stack activated (%.2fs)", idx, elapsed)
    return audit, elapsed


def _merge_storage_audits(audits: list[dict]) -> dict:
    """Merge per-drive storage audits into a single combined audit dict."""
    merged: dict = {"mdraid": None, "zfs": None, "lvm": None, "luks": None}
    for audit in audits:
        for key, current in merged.items():
            entry = audit.get(key)
            if entry is None:
                continue
            if current is None:
                merged[key] = entry
            elif isinstance(current, dict) and isinstance(entry, dict):
                # Merge list-valued keys (e.g. "vgs", "arrays", "pools") by extending
                for k, v in entry.items():
                    if isinstance(v, list) and isinstance(current.get(k), list):
                        current[k].extend(v)
                    else:
                        # For scalar values keep the first non-None value
                        current.setdefault(k, v)
    return merged


def launch_backend(vm) -> None:
    """Launch backend resources and initialize runtime managers."""
    start_time = time.time()

    if vm._launched:
        raise RuntimeError("VMCraft backend is already running. Call shutdown() before launching again.")

    if not vm._drives:
        raise RuntimeError(
            "No disk drives configured. Add at least one drive with add_drive() before launching."
        )

    # Initialise per-drive tracking lists
    vm._nbd_managers = []
    vm._nbd_devices = []
    vm._storage_activators = []

    # Use the first drive's image name as the primary identifier for tracing
    primary_image = Path(vm._drives[0]["path"]).name

    vm.logger.info("Launching VMCraft backend...")
    vm.logger.info("   Backend: VMCraft (Python + qemu-nbd + Linux tools)")
    vm.logger.info("   Drives: %d", len(vm._drives))
    for idx, drive in enumerate(vm._drives):
        image_name = Path(drive["path"]).name
        vm.logger.info(
            "   Drive %d: %s  format=%s  mode=%s",
            idx,
            image_name,
            drive.get("format", "auto-detect"),
            "read-only" if drive["readonly"] else "read-write",
        )

    with TraceContext(vm_id=primary_image, workflow="vm_activation", component="lifecycle"):
        # ------------------------------------------------------------------
        # Phase 1: Connect each drive to its own NBD device
        # ------------------------------------------------------------------
        total_nbd_time = 0.0
        for idx, drive in enumerate(vm._drives):
            security = _build_security(vm, drive)
            _nbd_dev, elapsed = _connect_drive(vm, idx, drive, security)
            total_nbd_time += elapsed
        vm._perf_metrics["nbd_connect"] = total_nbd_time

        # ------------------------------------------------------------------
        # Phase 2: Activate storage stack for each NBD device
        # ------------------------------------------------------------------
        total_storage_time = 0.0
        storage_audits: list[dict] = []
        for idx, nbd_device in enumerate(vm._nbd_devices):
            audit, elapsed = _activate_storage_for_drive(vm, idx, nbd_device)
            storage_audits.append(audit)
            total_storage_time += elapsed
        vm._perf_metrics["storage_activation"] = total_storage_time

        # Merge per-drive audits into a single combined audit
        vm._storage_audit = _merge_storage_audits(storage_audits)

        # ------------------------------------------------------------------
        # Backward-compatible aliases (first drive)
        # ------------------------------------------------------------------
        vm._nbd_manager = vm._nbd_managers[0]
        vm._nbd_device = vm._nbd_devices[0]
        vm._storage_activator = vm._storage_activators[0]

        # ------------------------------------------------------------------
        # Finalize
        # ------------------------------------------------------------------
        vm._mount_root = Path(tempfile.mkdtemp(prefix="h2kvm-guestfs-"))
        vm._initialize_runtime_managers()

        total_time = time.time() - start_time
        vm._perf_metrics["total_launch"] = total_time
        vm._launched = True

        log_event(
            "vm_activation_complete",
            status="success",
            drive_count=len(vm._drives),
            total_duration_ms=round(total_time * 1000, 1),
        )
        log_execution_summary(
            vm_id=primary_image,
            workflow="vm_activation",
            phases={"nbd": round(total_nbd_time * 1000, 1), "lvm": round(total_storage_time * 1000, 1)},
            total_duration_ms=round(total_time * 1000, 1),
            status="success",
        )

    vm.logger.info("VMCraft ready in %.2fs (%d drive(s))", total_time, len(vm._drives))
    vm.logger.debug("   Mount root: %s", vm._mount_root)


def shutdown_backend(vm) -> None:
    """Shutdown backend resources."""
    if not vm._launched:
        return

    vm.logger.info("Shutting down VMCraft backend...")

    with (
        TraceContext(vm_id="shutdown", workflow="vm_shutdown", component="lifecycle"),
        PhaseTimer("shutdown_start", "shutdown_complete", phase="shutdown"),
    ):
        _best_effort_step(
            vm,
            vm.umount_all,
            "   All filesystems unmounted",
            "   Error during umount_all: %s",
        )

        # Deactivate storage stacks in reverse drive order
        activators = getattr(vm, "_storage_activators", [])
        if activators:
            for idx in reversed(range(len(activators))):
                activator = activators[idx]
                if activator:
                    _best_effort_step(
                        vm,
                        activator.deactivate_all,
                        f"   Drive {idx} storage stack deactivated",
                        f"   Error deactivating drive {idx} storage: %s",
                    )
        elif vm._storage_activator:
            # Fallback for legacy single-drive path
            _best_effort_step(
                vm,
                vm._storage_activator.deactivate_all,
                "   Storage stack deactivated",
                "   Error deactivating storage: %s",
            )

        # Disconnect NBD devices in reverse drive order
        managers = getattr(vm, "_nbd_managers", [])
        devices = getattr(vm, "_nbd_devices", [])
        if managers:
            for idx in reversed(range(len(managers))):
                mgr = managers[idx]
                dev = devices[idx] if idx < len(devices) else None
                if mgr:
                    _best_effort_step(
                        vm,
                        mgr.disconnect,
                        f"   Drive {idx} NBD device disconnected: {dev}",
                        f"   Error disconnecting drive {idx} NBD: %s",
                    )
        elif vm._nbd_manager:
            # Fallback for legacy single-drive path
            _best_effort_step(
                vm,
                vm._nbd_manager.disconnect,
                f"   NBD device disconnected: {vm._nbd_device}",
                "   Error disconnecting NBD: %s",
            )

    vm._launched = False
    vm.logger.info("VMCraft shut down successfully")


def _force_umount_tree(vm, mount_root: Path) -> None:
    """Force-unmount anything still mounted under mount_root (deepest first)."""
    try:
        result = subprocess.run(
            ["findmnt", "-rn", "-o", "TARGET", "--submounts", str(mount_root)],
            capture_output=True,
            text=True,
            check=False,
        )
        targets = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        # Unmount deepest first
        for target in sorted(targets, reverse=True):
            try:
                subprocess.run(["umount", "-l", target], capture_output=True, check=False)
                vm.logger.debug("   Force-unmounted stale: %s", target)
            except OSError:
                pass
    except OSError:
        pass


def close_backend(vm) -> None:
    """Close backend and cleanup temporary state."""
    with contextlib.suppress(Exception):
        shutdown_backend(vm)

    if vm._mount_root and vm._mount_root.exists():
        # Force-unmount anything still mounted before removing the tree
        _force_umount_tree(vm, vm._mount_root)
        try:
            shutil.rmtree(vm._mount_root)
        except OSError as e:
            vm.logger.warning("Error removing mount root: %s", e)
        vm._mount_root = None

    _reset_runtime_fields(vm)
