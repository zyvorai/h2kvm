# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/vmcraft/storage.py
# pylint: disable=too-many-lines
# Cohesive storage-stack implementation (LVM/LUKS/mdraid/ZFS activation and teardown);
# splitting it across files would hurt readability more than the line count helps.
"""
Storage stack activation for LVM, LUKS, mdraid, and ZFS.

Uses native Linux tools for comprehensive storage management.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from hyper2kvm.core.constants import DELAY_DEVICE_SETTLE
from hyper2kvm.core.structured_log import PhaseTimer, log_event

from ._utils import run_sudo
from .lvm import LVM
from .lvm_executor import _PodmanWorker

# Optional: namespace-based isolation (requires unshare)
try:
    from .namespace_lvm import Hyper2KVM, Hyper2KVMError

    NAMESPACE_AVAILABLE = True
except ImportError:
    NAMESPACE_AVAILABLE = False


def _has_command(cmd: str) -> bool:
    """Check if command is available in PATH."""
    return shutil.which(cmd) is not None


class LVMActivator:
    """
    LVM (Logical Volume Manager) activation.

    Scans for volume groups and activates logical volumes.
    """

    @staticmethod
    def _create_isolated_lvm_env(logger: logging.Logger) -> tuple[dict[str, str], Path]:
        """
        Create isolated LVM environment with dedicated system directory.

        Creates a temporary directory for LVM metadata to prevent:
        - Host LVM cache pollution
        - Concurrent operation conflicts
        - Stale cache issues

        Returns:
            Tuple of (environment dict, temp directory path)

        Example:
            env, temp_dir = _create_isolated_lvm_env(logger)
            run_sudo(logger, ["vgscan"], env=env)
        """
        # Create isolated LVM system directory
        # Uses PID to ensure uniqueness across concurrent operations
        lvm_system_dir = Path(tempfile.gettempdir()) / f"hyper2kvm-lvm-{os.getpid()}"
        lvm_system_dir.mkdir(parents=True, exist_ok=True)

        # Build environment with LVM isolation
        lvm_env = os.environ.copy()
        lvm_env["LVM_SYSTEM_DIR"] = str(lvm_system_dir)
        lvm_env["LVM_SUPPRESS_FD_WARNINGS"] = "1"

        logger.debug(f"Created isolated LVM environment: {lvm_system_dir}")

        return lvm_env, lvm_system_dir

    @staticmethod
    def _settle_devices(logger: logging.Logger) -> None:
        """
        Ensure device nodes are fully created and visible.

        Uses a three-step approach for maximum reliability:
        1. dmsetup mknodes - Create device-mapper nodes
        2. udevadm settle - Wait for udev events to complete
        3. 200ms sleep - Additional buffer for device visibility

        This combination prevents race conditions where newly-created LVM devices
        aren't immediately visible to tools like blkid/lsblk/mount.

        The 200ms sleep after udevadm settle is necessary because:
        - udevadm settle only waits for event processing to complete
        - Device nodes may not be immediately visible in /dev/mapper/
        - Some systems need extra time for full propagation
        - 200ms is empirically determined to be reliable across systems

        Args:
            logger: Logger instance

        Example:
            LVMActivator._settle_devices(logger)
            # Now safe to use newly created LVM devices
        """
        # Step 1: Create device-mapper nodes
        if _has_command("dmsetup"):
            result = run_sudo(
                logger, ["dmsetup", "mknodes"], check=False, capture=True, failure_log_level=logging.DEBUG
            )
            if result and result.returncode != 0:
                logger.debug(f"dmsetup mknodes warning: {result.stderr}")

        # Step 2: Wait for udev to settle
        if _has_command("udevadm"):
            result = run_sudo(
                logger, ["udevadm", "settle"], check=False, capture=True, failure_log_level=logging.DEBUG
            )
            if result and result.returncode != 0:
                logger.debug(f"udevadm settle warning: {result.stderr}")

        # Step 3: Additional sleep for device visibility
        # Some systems need extra time after udev settle for device nodes
        # to be fully propagated to /dev/mapper/ and visible to userspace tools
        time.sleep(DELAY_DEVICE_SETTLE)

        logger.debug("Device settlement complete (dmsetup + udevadm + 200ms)")

    @staticmethod
    def _get_lvm_device_filter(nbd_device: str) -> str:
        """
        Generate LVM device filter configuration string.

        Creates an explicit regex-based filter that:
        - Accepts ONLY the specified NBD device and its partitions
          (anchored start AND end to prevent overmatch, e.g. nbd1 vs nbd10)
        - Rejects ALL other devices (r|.*|)
        - Sets both ``filter`` and ``global_filter`` for full isolation
        - Disables locking for isolation (locking_type=0)
        - Disables udev auto-activation and thin pool autoextend

        Args:
            nbd_device: NBD device path (e.g., "/dev/nbd0")

        Returns:
            LVM config string with device filter

        Example:
            filter = _get_lvm_device_filter("/dev/nbd0")
            run_sudo(logger, ["vgscan", "--config", filter])
        """
        # pylint: disable=duplicate-code
        # reason: mirrors the equivalent LVM device-filter builder in
        # hyper2kvm/vmcraft/lvm_executor.py -- structurally similar by
        # coincidence (both build the same lvm.conf filter string shape for
        # an NBD device), not shared logic; keeping independent avoids
        # coupling two unrelated LVM activation code paths.
        escaped = nbd_device.replace("/", r"\/")

        return (
            f"devices {{ "
            f'filter=["a|^{escaped}($|p[0-9]+$)|","r|.*|"] '
            f'global_filter=["a|^{escaped}($|p[0-9]+$)|","r|.*|"] '
            f"}} "
            f"activation {{ "
            f"auto_activation_volume_list=[] "
            f"thin_pool_autoextend_threshold=0 "
            f"}} "
            f"global {{ locking_type=0 }}"
        )

    @staticmethod
    # Two-phase container scan + host activation with per-VG bookkeeping; the local
    # variables are inherent to tracking that handoff, not accidental complexity.
    # pylint: disable-next=too-many-locals
    def _activate_via_container(
        logger: logging.Logger,
        nbd_device: str,
    ) -> dict[str, Any]:
        """
        Discover LVM VGs inside a container, then activate on the host.

        Uses a two-phase approach:
          1. **Scan** — run pvscan + vgs inside a hardened container
             (podman or docker, auto-detected) with a strict device
             filter.  This isolates the scan from host LVM metadata.
          2. **Activate** — run vgchange -ay on the **host** with the
             same device filter so device-mapper tables and udev events
             are processed natively, avoiding cross-namespace DM issues.

        Args:
            logger: Logger instance
            nbd_device: NBD device path (e.g., "/dev/nbd0")

        Returns:
            Audit dict: {"attempted": bool, "ok": bool, "error": str | None, "vgs": list}
        """
        audit: dict[str, Any] = {"attempted": True, "ok": False, "error": None, "vgs": []}

        _t0 = time.monotonic()

        try:
            # --- Phase 1: container-isolated VG discovery ---
            worker = _PodmanWorker(image="auto", log=logger)

            scan_script = "vgscan --cache >/dev/null 2>&1 || true\nvgs --noheadings -o vg_name 2>/dev/null\n"

            # _PodmanWorker is a private helper in this same vmcraft package;
            # no public accessor exists for the detected runtime.
            logger.info(
                "Scanning LVM via container (%s) on %s",
                worker._runtime,  # pylint: disable=protected-access
                nbd_device,
                extra={
                    "ctx": {
                        "event": "lvm_scan_start",
                        "runtime": worker._runtime,  # pylint: disable=protected-access
                        "nbd_device": nbd_device,
                    }
                },
            )
            result = worker.run(nbd_device, scan_script)

            # Parse VG names from stdout (vgs --noheadings output)
            vg_names: list[str] = []
            for line in result.stdout.strip().splitlines():
                name = line.strip()
                if name:
                    vg_names.append(name)

            if not vg_names:
                logger.info(
                    "Container scan: no volume groups found on %s",
                    nbd_device,
                )
                audit["ok"] = True
                return audit

            logger.info(
                "Container scan found %d VG(s): %s",
                len(vg_names),
                ", ".join(vg_names),
                extra={
                    "ctx": {
                        "event": "vg_discovered",
                        "vg_names": vg_names,
                        "count": len(vg_names),
                    }
                },
            )

            # --- Phase 2: host-side activation ---
            lvm_env, lvm_system_dir = LVMActivator._create_isolated_lvm_env(logger)
            lvm_filter = LVMActivator._get_lvm_device_filter(nbd_device)

            # Prime host-side LVM cache with the device filter
            if _has_command("pvscan"):
                run_sudo(
                    logger,
                    ["pvscan", "--cache", "--config", lvm_filter],
                    check=False,
                    capture=True,
                    env=lvm_env,
                )

            # Deactivate stale VGs first (may point to a disconnected NBD
            # device from a previous run), then re-activate with the
            # current device filter so DM tables map to the right device.
            for vg in vg_names:
                run_sudo(
                    logger,
                    ["vgchange", "-an", vg],
                    check=False,
                    capture=True,
                    failure_log_level=logging.DEBUG,
                    env=lvm_env,
                )

            # Activate each VG on the host so DM tables + udev are native
            for vg in vg_names:
                try:
                    run_sudo(
                        logger,
                        ["vgchange", "-ay", "--config", lvm_filter, vg],
                        check=True,
                        capture=True,
                        env=lvm_env,
                    )
                    logger.info(
                        "Activated VG on host: %s",
                        vg,
                        extra={"ctx": {"event": "vg_activated", "vg": vg}},
                    )
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    logger.warning(
                        "Failed to activate VG %s on host: %s\n"
                        "    Try manually: vgchange -ay %s\n"
                        "    If VG names conflict with host, use: --container-isolation",
                        vg,
                        exc,
                        vg,
                    )

            LVMActivator._settle_devices(logger)

            audit["vgs"] = vg_names
            audit["ok"] = True

            _elapsed_ms = int((time.monotonic() - _t0) * 1000)
            logger.info(
                "LVM activation complete (%d VG(s), %dms)",
                len(vg_names),
                _elapsed_ms,
                extra={
                    "ctx": {
                        "event": "lvm_activation_complete",
                        "vg_names": vg_names,
                        "count": len(vg_names),
                        "duration_ms": _elapsed_ms,
                    }
                },
            )

            # Cleanup isolated LVM directory
            try:
                if lvm_system_dir and lvm_system_dir.exists():
                    shutil.rmtree(lvm_system_dir)
            except Exception:  # pylint: disable=broad-exception-caught
                # Best-effort temp-dir cleanup; must not fail the LVM activation over this.
                pass

            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught
            audit["error"] = str(e)
            logger.warning(
                "Container LVM activation failed: %s\n"
                "    Ensure podman/docker is installed and running.\n"
                "    Or disable with: --no-container-isolation",
                e,
            )
            return audit

    @staticmethod
    # pylint: disable-next=too-many-locals,too-many-return-statements,too-many-branches,too-many-statements
    def activate(
        # This method covers many independent NBD/LVM activation paths (container isolation,
        # direct scan, fallback activation, opt-in host-wide activation) with early returns for
        # each; splitting it risks subtly changing the fault-tolerant fallback behavior.
        logger: logging.Logger,
        nbd_device: str | None = None,
        container_isolation: bool = True,
    ) -> dict[str, Any]:
        """
        Activate LVM volumes from NBD device with isolated metadata.

        Uses LVM_SYSTEM_DIR to create isolated LVM metadata directory,
        preventing host cache pollution and enabling safe concurrent operations.

        When *container_isolation* is ``True`` and an *nbd_device* is set,
        LVM operations are dispatched to a container (podman or docker)
        via ``_activate_via_container``.

        Args:
            nbd_device: Optional NBD device path (e.g., "/dev/nbd0") to scan only NBD-related PVs
            container_isolation: Route LVM activation through a Podman container

        Returns:
            Audit dict: {"attempted": bool, "ok": bool, "error": str | None, "vgs": list}
        """
        if container_isolation and nbd_device:
            return LVMActivator._activate_via_container(logger, nbd_device)

        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "vgs": []}

        if not _has_command("vgscan") or not _has_command("vgchange"):
            audit["error"] = "lvm_tools_not_available"
            return audit

        audit["attempted"] = True

        # Create isolated LVM environment to prevent host cache pollution
        lvm_env, lvm_system_dir = LVMActivator._create_isolated_lvm_env(logger)

        # Generate device filter if NBD device is specified
        lvm_filter = None
        if nbd_device:
            lvm_filter = LVMActivator._get_lvm_device_filter(nbd_device)
            logger.debug(f"Using LVM device filter: {lvm_filter}")

        # Create LVM instance with isolated env and device filter
        # This ensures ALL LVM operations (scan, activate, list) only
        # see the NBD device and never touch host LVM.
        lvm = LVM(logger=logger, env=lvm_env, device_filter=lvm_filter)

        try:
            # Gather NBD partitions for explicit device specification
            nbd_partitions = []
            if nbd_device and _has_command("pvscan"):
                nbd_dev_path = Path(nbd_device)
                nbd_partitions = [str(p) for p in nbd_dev_path.parent.glob(f"{nbd_dev_path.name}p*")]
                logger.info(
                    f"Scanning NBD partitions for LVM: {nbd_partitions}",
                    extra={
                        "ctx": {
                            "event": "lvm_scan_start",
                            "nbd_device": nbd_device,
                            "partitions": nbd_partitions,
                            "partition_count": len(nbd_partitions),
                            "isolation_mode": "direct",
                        }
                    },
                )

                # Scan with isolated env + device filter
                try:
                    lvm.scan(activate=False)
                    logger.debug("LVM scan complete")
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.warning(f"LVM scan failed: {e}")
                    # Fallback to manual pvscan/vgscan if needed
                    if _has_command("pvscan"):
                        run_sudo(logger, ["pvscan", "--cache"], check=False, capture=True, env=lvm_env)
                    if _has_command("vgscan"):
                        run_sudo(logger, ["vgscan", "--cache"], check=False, capture=True, env=lvm_env)

            # Find VGs using explicit device filter (only NBD partitions)
            vgs_to_activate = []
            if nbd_partitions and lvm_filter and _has_command("pvs"):
                try:
                    # Query VGs on NBD device using filter
                    # The filter ensures only NBD devices are scanned
                    result = run_sudo(
                        logger,
                        ["pvs", "--config", lvm_filter, "--noheadings", "-o", "vg_name"],
                        check=True,
                        capture=True,
                        failure_log_level=logging.DEBUG,
                        env=lvm_env,
                    )

                    vg_set = set()
                    for line in result.stdout.strip().split("\n"):
                        vg_name = line.strip()
                        if vg_name:
                            vg_set.add(vg_name)
                            logger.info(f"  Found VG '{vg_name}' on {nbd_device}")

                    vgs_to_activate = list(vg_set)
                    logger.info(
                        f"Found {len(vgs_to_activate)} VG(s) on {nbd_device}: {vgs_to_activate}",
                        extra={
                            "ctx": {
                                "event": "vg_discovered",
                                "nbd_device": nbd_device,
                                "vg_names": vgs_to_activate,
                                "count": len(vgs_to_activate),
                                "isolation_mode": "direct",
                            }
                        },
                    )
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.warning(f"Could not determine VGs from {nbd_device}: {e}")

            # Activate only NBD-related VGs
            if vgs_to_activate:
                try:
                    # Activate VGs with automatic udev settling
                    lvm.vg_activate(True, vgs_to_activate)
                    logger.info(
                        f"Activated VG(s): {', '.join(vgs_to_activate)} (from {nbd_device})",
                        extra={
                            "ctx": {
                                "event": "vg_activated",
                                "vg_names": vgs_to_activate,
                                "nbd_device": nbd_device,
                                "method": "lvm_api",
                            }
                        },
                    )
                    audit["vgs"] = vgs_to_activate
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.warning(f"Failed to activate VGs {vgs_to_activate}: {e}")
                    # Fallback to manual activation with device filter
                    for vg in vgs_to_activate:
                        try:
                            cmd = ["vgchange", "-ay"]
                            if lvm_filter:
                                cmd.extend(["--config", lvm_filter])
                            cmd.append(vg)
                            run_sudo(logger, cmd, check=True, capture=True, env=lvm_env)
                            logger.info(f"Activated VG: {vg} (fallback method)")
                            LVMActivator._settle_devices(logger)
                        except Exception as exc:  # pylint: disable=broad-exception-caught
                            # Best-effort per-VG fallback activation; one VG's failure
                            # must not abort activation of the remaining VGs.
                            logger.warning(f"Failed to activate VG {vg}: {exc}")
                    audit["vgs"] = vgs_to_activate
            else:
                # No VGs found on this NBD device — this is normal for
                # non-LVM disks (e.g. plain partitions, Photon OS, etc.)
                if nbd_device and nbd_partitions:
                    # We scanned the NBD partitions and found no LVM — just skip
                    logger.info(
                        f"No LVM volume groups found on {nbd_device} — disk does not use LVM",
                        extra={
                            "ctx": {
                                "event": "lvm_scan_no_vgs",
                                "nbd_device": nbd_device,
                                "partition_count": len(nbd_partitions),
                            }
                        },
                    )
                    audit["ok"] = True
                    return audit

                if nbd_device and not nbd_partitions:
                    # NBD device exists but no partition nodes — likely max_part issue
                    logger.warning(
                        f"No partition devices found for {nbd_device}. "
                        f"NBD module may need max_part=16: "
                        f"rmmod nbd && modprobe nbd max_part=16"
                    )
                    audit["ok"] = True
                    return audit

                # No nbd_device specified at all — refuse to blindly activate
                allow_host_activation = os.getenv(
                    "HYPER2KVM_ALLOW_HOST_VG_ACTIVATION", ""
                ).strip().lower() in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }

                if not allow_host_activation:
                    logger.warning(
                        "No NBD device specified for LVM activation. "
                        "Skipping to prevent accidental host VG activation."
                    )
                    audit["ok"] = True
                    return audit

                # User explicitly opted in - proceed with warning
                logger.warning("⚠️  DANGER: Activating ALL volume groups (host VGs may be affected)")
                logger.warning("⚠️  HYPER2KVM_ALLOW_HOST_VG_ACTIVATION=1 detected - safety override enabled")
                logger.warning("⚠️  Ensure no VG name collisions between host and guest")

                # Activate all VGs with automatic udev settling
                try:
                    lvm.vg_activate_all(True)
                    logger.warning("⚠️  Activated all volume groups (UNSAFE fallback mode)")
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.exception(f"Failed to activate all VGs: {e}")
                    # Fallback to manual activation
                    run_sudo(logger, ["vgchange", "-ay"], check=True, capture=True, env=lvm_env)
                    LVMActivator._settle_devices(logger)

            audit["ok"] = True
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught
            audit["error"] = str(e)
            logger.warning(f"LVM activation failed: {e}")
            log_event("lvm_activation_failed", level="warning", nbd_device=nbd_device, error=str(e))
            return audit

        finally:
            # Cleanup isolated LVM directory
            try:
                if lvm_system_dir and lvm_system_dir.exists():
                    shutil.rmtree(lvm_system_dir)
                    logger.debug(f"Cleaned up isolated LVM directory: {lvm_system_dir}")
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.debug(f"Could not clean up LVM directory {lvm_system_dir}: {e}")

    @staticmethod
    def activate_namespace(
        logger: logging.Logger, image_path: str, nbd_device: str | None = None
    ) -> dict[str, Any]:
        """
        Activate LVM volumes using namespace isolation (maximum security).

        This method uses unshare-based namespace isolation for NBD + LVM operations:
        - Creates isolated mount namespace for /dev
        - Runs LVM operations in separate PID namespace
        - Prevents host LVM cache pollution
        - Provides strongest isolation guarantees

        Requires:
        - unshare command (util-linux)
        - CAP_SYS_ADMIN capability (or root)

        Args:
            logger: Logger instance
            image_path: Path to disk image (QCOW2, raw, etc.)
            nbd_device: Optional NBD device to use (auto-detected if None)

        Returns:
            Audit dict: {"attempted": bool, "ok": bool, "error": str | None, "volumes": list}

        Example:
            audit = LVMActivator.activate_namespace(logger, "/path/to/image.qcow2")
            if audit["ok"]:
                for vol in audit["volumes"]:
                    logger.info(f"Activated: {vol}")
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "volumes": []}

        if not NAMESPACE_AVAILABLE:
            audit["error"] = "namespace_lvm_module_not_available"
            logger.warning(
                "Namespace LVM module not available - falling back to standard activation.\n"
                "    This may cause conflicts with host LVM volume groups.\n"
                "    Consider using: --container-isolation for safer LVM handling."
            )
            return audit

        audit["attempted"] = True

        try:
            # Create namespace-isolated LVM engine
            # Hyper2KVM manages its own module-level logger; it has no logger constructor param.
            engine = Hyper2KVM(
                image=image_path,
                nbd=nbd_device,
                mount_options=["ro"],
                debug=logger.isEnabledFor(logging.DEBUG),
            )

            # Activate volumes in isolated namespace
            logger.info("Activating LVM with namespace isolation (unshare-based)")
            volumes = engine.start()

            if volumes:
                logger.info(f"✅ Namespace LVM activated {len(volumes)} volume(s)")
                for vol in volumes:
                    logger.info(f"   {vol}")
                audit["volumes"] = volumes
                audit["ok"] = True
            else:
                logger.warning("No LVM volumes found in namespace")
                audit["ok"] = False
                audit["error"] = "no_volumes_found"

            return audit

        except Hyper2KVMError as e:
            audit["error"] = str(e)
            logger.exception(f"Namespace LVM activation failed: {e}")
            return audit
        except Exception as e:  # pylint: disable=broad-exception-caught
            audit["error"] = str(e)
            logger.exception(f"Unexpected error in namespace LVM activation: {e}")
            return audit

    @staticmethod
    def list_logical_volumes(logger: logging.Logger, nbd_device: str | None = None) -> list[str]:
        """
        List logical volumes, optionally filtered to only NBD-backed LVs.

        Args:
            nbd_device: If provided, only return LVs backed by this NBD device

        Returns:
            List of LV device paths in /dev/mapper/ format (e.g., ['/dev/mapper/vg-lv'])
        """
        try:
            # Use lvs with vg_name, lv_name, and devices columns
            # Disable devices file to make filtering work
            # Return /dev/mapper/ paths which are more reliable than /dev/vg/lv symlinks
            cmd = [
                "lvs",
                "--devicesfile",
                "",
                "--reportformat",
                "json",
                "--noheadings",
                "-o",
                "vg_name,lv_name,devices",
            ]

            result = run_sudo(logger, cmd, check=True, capture=True)

            data = json.loads(result.stdout)
            lvs_data = data.get("report", [{}])[0].get("lv", [])

            devices = []
            for lv in lvs_data:
                vg_name = lv.get("vg_name", "")
                lv_name = lv.get("lv_name", "")
                lv_devices = lv.get("devices", "")

                # If NBD filtering is requested, check if this LV uses NBD partitions
                if nbd_device:
                    if nbd_device in lv_devices or f"{nbd_device}p" in lv_devices:
                        # Construct /dev/mapper/ path (hyphens in vg_name/lv_name are escaped as --)
                        mapper_vg = vg_name.replace("-", "--")
                        mapper_lv = lv_name.replace("-", "--")
                        mapper_path = f"/dev/mapper/{mapper_vg}-{mapper_lv}"
                        devices.append(mapper_path)
                        logger.debug(
                            f"Found NBD-backed LV: {mapper_path} (VG: {vg_name}, LV: {lv_name}, devices: {lv_devices})"
                        )
                # No filtering - return all LVs in /dev/mapper/ format
                elif vg_name and lv_name:
                    mapper_vg = vg_name.replace("-", "--")
                    mapper_lv = lv_name.replace("-", "--")
                    mapper_path = f"/dev/mapper/{mapper_vg}-{mapper_lv}"
                    devices.append(mapper_path)

            if nbd_device:
                logger.info(f"Found {len(devices)} LVs on {nbd_device}: {devices}")

            return devices

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning(f"Failed to list logical volumes: {e}")
            return []


class LVMCreator:
    """
    LVM creation and management operations.

    Creates physical volumes, volume groups, and logical volumes.
    Complements LVMActivator which only activates existing LVM structures.
    """

    @staticmethod
    def pvcreate(logger: logging.Logger, devices: list[str]) -> dict[str, Any]:
        """
        Create physical volumes.

        Args:
            logger: Logger instance
            devices: List of device paths to initialize as PVs

        Returns:
            Audit dict with created PV list

        Example:
            result = LVMCreator.pvcreate(logger, ["/dev/nbd0p1"])
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "pvs": []}

        if not _has_command("pvcreate"):
            audit["error"] = "lvm_tools_not_available"
            return audit

        if not devices:
            audit["error"] = "no_devices_provided"
            return audit

        audit["attempted"] = True

        try:
            cmd = ["pvcreate", "-f", *devices]
            run_sudo(logger, cmd, check=True, capture=True)

            audit["ok"] = True
            audit["pvs"] = devices
            logger.info(f"Created physical volumes: {devices}")
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught
            audit["error"] = str(e)
            logger.warning(f"PV creation failed: {e}")
            return audit

    @staticmethod
    def vgcreate(logger: logging.Logger, vgname: str, pvs: list[str]) -> dict[str, Any]:
        """
        Create volume group.

        Args:
            logger: Logger instance
            vgname: Volume group name
            pvs: List of physical volumes

        Returns:
            Audit dict with VG name

        Example:
            result = LVMCreator.vgcreate(logger, "test_vg", ["/dev/nbd0p1"])
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "vg": None}

        if not _has_command("vgcreate"):
            audit["error"] = "lvm_tools_not_available"
            return audit

        if not vgname or not pvs:
            audit["error"] = "invalid_parameters"
            return audit

        audit["attempted"] = True

        try:
            cmd = ["vgcreate", vgname, *pvs]
            run_sudo(logger, cmd, check=True, capture=True)

            audit["ok"] = True
            audit["vg"] = vgname
            logger.info(f"Created volume group: {vgname}")
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught
            audit["error"] = str(e)
            logger.warning(f"VG creation failed: {e}")
            return audit

    @staticmethod
    def lvcreate(
        logger: logging.Logger,
        lvname: str,
        vgname: str,
        size_mb: int | None = None,
        extents: str | None = None,
    ) -> dict[str, Any]:
        """
        Create logical volume.

        Args:
            logger: Logger instance
            lvname: Logical volume name
            vgname: Volume group name
            size_mb: Size in megabytes (mutually exclusive with extents)
            extents: Size in extents (e.g., "100%FREE")

        Returns:
            Audit dict with LV path

        Example:
            # Create LV with specific size
            result = LVMCreator.lvcreate(logger, "data", "vg0", size_mb=1024)

            # Create LV using all free space
            result = LVMCreator.lvcreate(logger, "data", "vg0", extents="100%FREE")
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "lv": None}

        if not _has_command("lvcreate"):
            audit["error"] = "lvm_tools_not_available"
            return audit

        if not lvname or not vgname:
            audit["error"] = "invalid_parameters"
            return audit

        if not size_mb and not extents:
            audit["error"] = "size_mb or extents required"
            return audit

        if size_mb and extents:
            audit["error"] = "size_mb and extents are mutually exclusive"
            return audit

        audit["attempted"] = True

        try:
            cmd = ["lvcreate", "-n", lvname]

            if size_mb:
                cmd.extend(["-L", f"{size_mb}M"])
            elif extents:
                cmd.extend(["-l", extents])

            cmd.append(vgname)

            run_sudo(logger, cmd, check=True, capture=True)

            lv_path = f"/dev/{vgname}/{lvname}"
            audit["ok"] = True
            audit["lv"] = lv_path
            logger.info(f"Created logical volume: {lv_path}")
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught
            audit["error"] = str(e)
            logger.warning(f"LV creation failed: {e}")
            return audit

    @staticmethod
    def lvresize(logger: logging.Logger, lvpath: str, size_mb: int) -> dict[str, Any]:
        """
        Resize logical volume.

        Args:
            logger: Logger instance
            lvpath: LV device path (e.g., "/dev/vg0/data")
            size_mb: New size in megabytes

        Returns:
            Audit dict

        Example:
            result = LVMCreator.lvresize(logger, "/dev/vg0/data", 2048)
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None}

        if not _has_command("lvresize"):
            audit["error"] = "lvm_tools_not_available"
            return audit

        if not lvpath or size_mb <= 0:
            audit["error"] = "invalid_parameters"
            return audit

        audit["attempted"] = True

        try:
            cmd = ["lvresize", "-L", f"{size_mb}M", lvpath]
            run_sudo(logger, cmd, check=True, capture=True)

            audit["ok"] = True
            logger.info(f"Resized LV {lvpath} to {size_mb}M")
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught
            audit["error"] = str(e)
            logger.warning(f"LV resize failed: {e}")
            return audit

    @staticmethod
    def lvremove(logger: logging.Logger, lvpath: str, force: bool = False) -> dict[str, Any]:
        """
        Remove logical volume.

        Args:
            logger: Logger instance
            lvpath: LV device path
            force: Force removal without confirmation

        Returns:
            Audit dict

        Example:
            result = LVMCreator.lvremove(logger, "/dev/vg0/data", force=True)
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None}

        if not _has_command("lvremove"):
            audit["error"] = "lvm_tools_not_available"
            return audit

        if not lvpath:
            audit["error"] = "invalid_parameters"
            return audit

        audit["attempted"] = True

        try:
            cmd = ["lvremove"]
            if force:
                cmd.append("-f")
            cmd.append(lvpath)

            run_sudo(logger, cmd, check=True, capture=True)

            audit["ok"] = True
            logger.info(f"Removed LV {lvpath}")
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught
            audit["error"] = str(e)
            logger.warning(f"LV removal failed: {e}")
            return audit

    @staticmethod
    def vgremove(logger: logging.Logger, vgname: str, force: bool = False) -> dict[str, Any]:
        """
        Remove volume group.

        Args:
            logger: Logger instance
            vgname: Volume group name
            force: Force removal without confirmation

        Returns:
            Audit dict

        Example:
            result = LVMCreator.vgremove(logger, "vg0", force=True)
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None}

        if not _has_command("vgremove"):
            audit["error"] = "lvm_tools_not_available"
            return audit

        if not vgname:
            audit["error"] = "invalid_parameters"
            return audit

        audit["attempted"] = True

        try:
            cmd = ["vgremove"]
            if force:
                cmd.append("-f")
            cmd.append(vgname)

            run_sudo(logger, cmd, check=True, capture=True)

            audit["ok"] = True
            logger.info(f"Removed VG {vgname}")
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught
            audit["error"] = str(e)
            logger.warning(f"VG removal failed: {e}")
            return audit


class LUKSUnlocker:
    """
    LUKS (Linux Unified Key Setup) encryption unlocking.

    Detects and unlocks LUKS-encrypted devices.
    """

    # Each keyword configures an independent, optional LUKS key-material source;
    # collapsing them into a config object would ripple through every call site.
    # pylint: disable-next=too-many-arguments
    def __init__(
        self,
        logger: logging.Logger,
        *,
        luks_enable: bool = False,
        luks_passphrase: str | None = None,
        luks_passphrase_env: str | None = None,
        luks_keyfile: Path | None = None,
        luks_mapper_prefix: str = "hyper2kvm-crypt",
    ):
        """
        Initialize LUKS unlocker.

        Args:
            logger: Logger instance
            luks_enable: Enable LUKS unlocking
            luks_passphrase: Direct passphrase
            luks_passphrase_env: Environment variable containing passphrase
            luks_keyfile: Path to key file
            luks_mapper_prefix: Prefix for mapper device names
        """
        self.logger = logger
        self.luks_enable = bool(luks_enable)
        self.luks_passphrase = luks_passphrase
        self.luks_passphrase_env = luks_passphrase_env
        self.luks_keyfile = Path(luks_keyfile) if luks_keyfile else None
        self.luks_mapper_prefix = luks_mapper_prefix
        self._luks_opened: dict[str, str] = {}  # device -> mapper_name

    def _read_luks_key_bytes(self) -> bytes | None:
        """Read LUKS key material from keyfile or passphrase."""
        try:
            if self.luks_keyfile and self.luks_keyfile.exists():
                return self.luks_keyfile.read_bytes()
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        pw = self.luks_passphrase
        if (not pw) and self.luks_passphrase_env:
            pw = os.environ.get(self.luks_passphrase_env)
        if pw:
            return pw.encode("utf-8")
        return None

    def _detect_luks_devices(self) -> list[str]:
        """
        Detect LUKS-encrypted devices using blkid.

        Returns:
            List of device paths with LUKS encryption
        """
        try:
            # Use blkid to find LUKS devices
            result = run_sudo(
                self.logger, ["blkid", "-t", "TYPE=crypto_LUKS", "-o", "device"], check=True, capture=True
            )

            return [line.strip() for line in result.stdout.splitlines() if line.strip()]

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.warning(f"Failed to detect LUKS devices: {e}")
            return []

    def unlock(self, nbd_device: str | None = None) -> dict[str, Any]:
        """
        Unlock LUKS devices.

        Args:
            nbd_device: Optional NBD device for LVM re-activation after unlocking

        Returns:
            Audit dict with detailed unlock results
        """
        # pylint: disable=duplicate-code
        # reason: mirrors the equivalent LUKS-unlock audit-dict/scan blocks in
        # hyper2kvm/fixers/offline_fixer.py (_unlock_luks_devices) --
        # structurally similar by coincidence (both build a similar audit
        # dict shape), not shared logic; keeping independent avoids coupling
        # the guestfs-based and host-direct unlock code paths.
        audit: dict[str, Any] = {
            "attempted": False,
            "configured": False,
            "enabled": bool(self.luks_enable),
            "passphrase_env": self.luks_passphrase_env,
            "keyfile": str(self.luks_keyfile) if self.luks_keyfile else None,
            "luks_devices": [],
            "opened": [],
            "skipped": [],
            "errors": [],
        }

        if not self.luks_enable:
            audit["skipped"].append("luks_disabled")
            return audit

        key_bytes = self._read_luks_key_bytes()
        audit["configured"] = bool(key_bytes)
        if not key_bytes:
            audit["skipped"].append("no_key_material_configured")
            return audit

        if not _has_command("cryptsetup"):
            audit["errors"].append("cryptsetup_not_available")
            return audit

        luks_devs = self._detect_luks_devices()
        audit["luks_devices"] = luks_devs
        if not luks_devs:
            audit["skipped"].append("no_crypto_LUKS_devices_found")
            return audit

        audit["attempted"] = True

        for idx, dev in enumerate(luks_devs, 1):
            if dev in self._luks_opened:
                continue

            name = f"{self.luks_mapper_prefix}{idx}"

            try:
                # Write key to temp file for cryptsetup
                with tempfile.NamedTemporaryFile(mode="wb", delete=False) as key_file:
                    key_file.write(key_bytes)
                    key_file_path = key_file.name

                try:
                    # Open LUKS device
                    run_sudo(
                        self.logger,
                        ["cryptsetup", "open", dev, name, "--key-file", key_file_path],
                        check=True,
                        capture=True,
                    )

                    mapped = f"/dev/mapper/{name}"
                    self._luks_opened[dev] = mapped
                    audit["opened"].append({"device": dev, "mapped": mapped})
                    self.logger.info(f"LUKS: opened {dev} -> {mapped}")

                finally:
                    # Clean up temp key file
                    with contextlib.suppress(Exception):
                        os.unlink(key_file_path)

            except Exception as e:  # pylint: disable=broad-exception-caught
                audit["errors"].append({"device": dev, "error": str(e)})
                self.logger.warning(f"LUKS: failed to open {dev}: {e}")

        # After opening LUKS, LVM may appear - re-activate
        if audit["opened"]:
            _ = LVMActivator.activate(self.logger, nbd_device=nbd_device)

        return audit

    def get_opened_devices(self) -> dict[str, str]:
        """Get dict of opened LUKS devices (device -> mapper_path)."""
        return self._luks_opened.copy()


class MDRaidAssembler:  # pylint: disable=too-few-public-methods
    """
    MD RAID (Software RAID) assembler.

    Assembles mdraid arrays using mdadm.

    Namespaced as a class (rather than a bare function) to match the sibling
    LVMActivator/ZFSImporter activators' shape used by StorageStackActivator.
    """

    @staticmethod
    def activate(logger: logging.Logger) -> dict[str, Any]:
        """
        Activate mdraid arrays.

        Returns:
            Audit dict: {"attempted": bool, "ok": bool, "details": str, "error": str | None}
        """
        audit: dict[str, Any] = {"attempted": False, "ok": False, "details": "", "error": None}

        if not _has_command("mdadm"):
            audit["details"] = "mdadm_not_available"
            return audit

        audit["attempted"] = True

        try:
            # Assemble all arrays (log failures as DEBUG since "no arrays" is common)
            run_sudo(
                logger,
                ["mdadm", "--assemble", "--scan", "--run"],
                check=True,
                capture=True,
                failure_log_level=logging.DEBUG,
            )

            audit["ok"] = True
            audit["details"] = "mdadm_assemble_scan_ok"
            logger.info("mdraid arrays assembled successfully")
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught
            audit["error"] = str(e)
            audit["details"] = "mdadm_assemble_scan_failed"
            logger.debug(f"mdraid assembly failed (expected if no RAID): {e}")
            return audit


class ZFSImporter:  # pylint: disable=too-few-public-methods
    """
    ZFS pool importer.

    Imports ZFS pools without mounting datasets.

    Namespaced as a class (rather than a bare function) to match the sibling
    LVMActivator/MDRaidAssembler activators' shape used by StorageStackActivator.
    """

    @staticmethod
    def activate(logger: logging.Logger) -> dict[str, Any]:
        """
        Import ZFS pools.

        Returns:
            Audit dict: {"attempted": bool, "ok": bool, "pools": list, "error": str | None}
        """
        if not _has_command("zpool"):
            return {"attempted": False, "ok": False, "reason": "zpool_not_available"}

        audit: dict[str, Any] = {"attempted": True, "ok": False, "pools": [], "error": None}

        try:
            # List available pools
            result = run_sudo(
                logger,
                ["sh", "-lc", "ZPOOL_VDEV_NAME_PATH=1 zpool import 2>/dev/null || true"],
                check=False,
                capture=True,
            )
            text = result.stdout.strip()
            audit["pools"] = [ln.strip() for ln in text.splitlines() if ln.strip()][:100]

        except Exception:  # pylint: disable=broad-exception-caught
            pass

        try:
            # Import all pools without mounting (-N flag)
            run_sudo(
                logger,
                ["sh", "-lc", "ZPOOL_VDEV_NAME_PATH=1 zpool import -a -N -f 2>/dev/null || true"],
                check=False,
                capture=True,
            )

            audit["ok"] = True
            logger.info("ZFS pools imported successfully")
            return audit

        except Exception as e:  # pylint: disable=broad-exception-caught
            audit["error"] = str(e)
            logger.warning(f"ZFS import failed: {e}")
            return audit


class StorageStackActivator:
    """
    Composite storage stack activator.

    Activates all storage layers in correct order:
    1. mdraid (software RAID)
    2. ZFS pools
    3. LVM volume groups
    4. LUKS encrypted devices (which may contain LVM)
    """

    # pylint: disable-next=too-many-arguments
    def __init__(
        # Each keyword configures an independent, optional LUKS/LVM activation setting;
        # collapsing them into a config object would ripple through every call site.
        self,
        logger: logging.Logger,
        *,
        luks_enable: bool = False,
        luks_passphrase: str | None = None,
        luks_passphrase_env: str | None = None,
        luks_keyfile: Path | None = None,
        luks_mapper_prefix: str = "hyper2kvm-crypt",
        container_isolation: bool = True,
    ):
        """
        Initialize storage stack activator.

        Args:
            logger: Logger instance
            luks_enable: Enable LUKS unlocking
            luks_passphrase: Direct passphrase for LUKS
            luks_passphrase_env: Environment variable containing passphrase
            luks_keyfile: Path to LUKS key file
            luks_mapper_prefix: Prefix for LUKS mapper device names
            container_isolation: Route LVM activation through a Podman container
        """
        self.logger = logger
        self.nbd_device: str | None = None  # Set by VMCraft when needed
        self.container_isolation = container_isolation
        self._activation_audit: dict[str, Any] = {}  # Track what was activated for safe cleanup
        self._imported_zfs_pools: set[str] = set()  # Track ZFS pools we imported
        self.luks_unlocker = LUKSUnlocker(
            logger,
            luks_enable=luks_enable,
            luks_passphrase=luks_passphrase,
            luks_passphrase_env=luks_passphrase_env,
            luks_keyfile=luks_keyfile,
            luks_mapper_prefix=luks_mapper_prefix,
        )

    def activate_all(self) -> dict[str, Any]:
        """
        Activate entire storage stack.

        Returns:
            Audit dict: {"mdraid": dict, "zfs": dict, "lvm": dict, "luks": dict}
        """
        audit: dict[str, Any] = {"mdraid": None, "zfs": None, "lvm": None, "luks": None}

        # Order matters: mdraid -> ZFS -> LVM -> LUKS (which may reveal more LVM)
        with PhaseTimer("mdraid_activate_start", "mdraid_activate_complete", phase="mdraid"):
            audit["mdraid"] = MDRaidAssembler.activate(self.logger)

        with PhaseTimer("zfs_activate_start", "zfs_activate_complete", phase="zfs"):
            audit["zfs"] = ZFSImporter.activate(self.logger)
            # Track which pools were imported by us
            if audit["zfs"] and audit["zfs"].get("ok"):
                for pool_line in audit["zfs"].get("pools", []):
                    # Pool names are the first word on each line
                    pool_name = pool_line.split()[0] if pool_line.split() else ""
                    if pool_name:
                        self._imported_zfs_pools.add(pool_name)

        # Pass NBD device to LVM activator for device-specific scanning
        with PhaseTimer("lvm_activate_start", "lvm_activate_complete", phase="lvm"):
            audit["lvm"] = LVMActivator.activate(
                self.logger,
                nbd_device=self.nbd_device,
                container_isolation=self.container_isolation,
            )

        # LUKS last because it may contain LVM (pass nbd_device for re-activation)
        with PhaseTimer("luks_unlock_start", "luks_unlock_complete", phase="luks"):
            audit["luks"] = self.luks_unlocker.unlock(nbd_device=self.nbd_device)

        # Store audit for safe cleanup - only deactivate what we activated
        self._activation_audit = audit

        log_event(
            "storage_stack_activated",
            nbd_device=self.nbd_device,
            lvm_vgs=audit.get("lvm", {}).get("vgs", []),
        )

        return audit

    def deactivate_all(self) -> None:
        """
        Deactivate entire storage stack.

        Deactivates all storage layers in reverse order:
        1. LUKS devices
        2. LVM volume groups
        3. ZFS pools
        4. mdraid arrays
        """
        self.logger.debug("Deactivating storage stack...")
        with PhaseTimer("storage_deactivate_start", "storage_deactivate_complete", phase="storage_teardown"):
            self._deactivate_luks()
            self._deactivate_lvm()
            self._settle_udev()
            self._deactivate_zfs()
            self._deactivate_mdraid()
            self._final_cleanup()
            self._settle_udev()
        self.logger.debug("Storage stack deactivated")

    def _deactivate_luks(self) -> None:
        """Deactivate LUKS devices."""
        if not _has_command("cryptsetup"):
            return

        try:
            result = run_sudo(
                self.logger,
                ["dmsetup", "ls", "--target", "crypt"],
                check=False,
                capture=True,
                failure_log_level=logging.DEBUG,
            )
            if not result or not result.stdout:
                return

            for line in result.stdout.splitlines():
                if self.luks_unlocker.luks_mapper_prefix in line:
                    dev_name = line.split()[0]
                    run_sudo(
                        self.logger,
                        ["cryptsetup", "close", dev_name],
                        check=False,
                        capture=True,
                        failure_log_level=logging.DEBUG,
                    )
                    self.logger.debug(f"Closed LUKS device: {dev_name}")
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.debug(f"LUKS cleanup warning: {e}")

    def _deactivate_lvm(self) -> None:
        """Deactivate LVM volume groups."""
        if not _has_command("vgchange"):
            return

        try:
            activated_vgs = self._get_activated_vgs()
            if not activated_vgs:
                self.logger.debug("No LVM volume groups tracked - skipping deactivation")
                return

            self.logger.debug(f"Deactivating LVM volume groups: {activated_vgs}")
            deactivation_failures = self._deactivate_vgs(activated_vgs)

            if deactivation_failures:
                self._deactivate_vgs_fallback(deactivation_failures)

            self.logger.debug("LVM volume groups deactivated")
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.debug(f"LVM deactivation warning: {e}")

    def _get_activated_vgs(self) -> list[str]:
        """Get list of volume groups we activated."""
        if self._activation_audit.get("lvm") and self._activation_audit["lvm"].get("vgs"):
            return self._activation_audit["lvm"]["vgs"]
        return []

    def _deactivate_vgs(self, vgs: list[str]) -> list[str]:
        """Deactivate volume groups and return list of failures."""
        failures = []
        for vg in vgs:
            try:
                result = run_sudo(
                    self.logger,
                    ["vgchange", "--devicesfile", "", "-an", vg],
                    check=False,
                    capture=True,
                    failure_log_level=logging.DEBUG,
                )
                self.logger.debug(f"  Deactivated VG: {vg}")

                if result and result.returncode != 0 and "busy" in (result.stderr or "").lower():
                    failures.append(vg)
            except Exception as e:  # pylint: disable=broad-exception-caught
                self.logger.debug(f"  Failed to deactivate VG {vg}: {e}")
                failures.append(vg)
        return failures

    def _deactivate_vgs_fallback(self, failed_vgs: list[str]) -> None:
        """Use dmsetup to forcefully deactivate busy VGs."""
        if not _has_command("dmsetup"):
            return

        self.logger.warning(f"Some VGs are busy, attempting dmsetup fallback: {failed_vgs}")
        try:
            result = run_sudo(
                self.logger,
                ["dmsetup", "ls", "--target", "linear,striped"],
                check=False,
                capture=True,
                failure_log_level=logging.DEBUG,
            )

            if not result or not result.stdout:
                return

            for line in result.stdout.splitlines():
                parts = line.split()
                if not parts:
                    continue

                dm_name = parts[0]
                self._remove_vg_dm_device(dm_name, failed_vgs)
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.debug(f"dmsetup fallback failed: {e}")

    def _remove_vg_dm_device(self, dm_name: str, vgs: list[str]) -> None:
        """Remove device mapper device if it belongs to one of our VGs."""
        for vg in vgs:
            if dm_name.startswith(f"{vg.replace('-', '--')}-"):
                try:
                    run_sudo(
                        self.logger,
                        ["dmsetup", "remove", dm_name],
                        check=False,
                        capture=True,
                        failure_log_level=logging.DEBUG,
                    )
                    self.logger.debug(f"  Removed busy DM device: {dm_name}")
                except Exception as e:  # pylint: disable=broad-exception-caught
                    self.logger.debug(f"  Failed to remove DM device {dm_name}: {e}")
                break

    def _settle_udev(self) -> None:
        """Settle udev events."""
        # pylint: disable=duplicate-code
        # reason: mirrors the equivalent udevadm-settle call in
        # hyper2kvm/vmcraft/nbd.py's VG-activation step -- structurally
        # similar by coincidence (both just settle udev after a device
        # change), not shared logic; keeping independent avoids coupling
        # two unrelated storage-activation code paths.
        try:
            if _has_command("udevadm"):
                run_sudo(
                    self.logger,
                    ["udevadm", "settle"],
                    check=False,
                    capture=True,
                    failure_log_level=logging.DEBUG,
                )
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    def _deactivate_zfs(self) -> None:
        """Export only ZFS pools that were imported by hyper2kvm."""
        if not _has_command("zpool"):
            return

        if not self._imported_zfs_pools:
            self.logger.debug("No ZFS pools tracked for deactivation - skipping")
            return

        try:
            for pool in list(self._imported_zfs_pools):
                run_sudo(
                    self.logger,
                    ["zpool", "export", pool],
                    check=False,
                    capture=True,
                    failure_log_level=logging.DEBUG,
                )
                self.logger.debug(f"Exported ZFS pool: {pool}")
                self._imported_zfs_pools.discard(pool)
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.debug(f"ZFS cleanup warning: {e}")

    def _deactivate_mdraid(self) -> None:
        """Stop mdraid arrays."""
        if not _has_command("mdadm"):
            return

        try:
            result = run_sudo(
                self.logger,
                ["cat", "/proc/mdstat"],
                check=False,
                capture=True,
                failure_log_level=logging.DEBUG,
            )
            if result and result.stdout and "md" in result.stdout:
                run_sudo(
                    self.logger,
                    ["mdadm", "--stop", "--scan"],
                    check=False,
                    capture=True,
                    failure_log_level=logging.DEBUG,
                )
                self.logger.debug("Stopped mdraid arrays")
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.debug(f"mdraid cleanup warning: {e}")

    def _final_cleanup(self) -> None:
        """Final aggressive cleanup of temp mounts and device mapper devices."""
        self._cleanup_temp_mounts()
        self._cleanup_dm_devices()

    def _cleanup_temp_mounts(self) -> None:
        """Unmount all temporary directories."""
        try:
            run_sudo(
                self.logger,
                ["sh", "-c", "umount -R /tmp/hyper2kvm-guestfs-* 2>/dev/null || true"],
                check=False,
                capture=True,
                failure_log_level=logging.DEBUG,
            )
            self.logger.debug("Recursively unmounted all temp directories")
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.debug(f"Recursive unmount warning: {e}")

    def _cleanup_dm_devices(self) -> None:
        """Clean up device mapper devices we created."""
        if not _has_command("dmsetup") or not self.luks_unlocker.luks_mapper_prefix:
            return

        try:
            result = run_sudo(
                self.logger, ["dmsetup", "ls"], check=False, capture=True, failure_log_level=logging.DEBUG
            )
            if not result or not result.stdout:
                return

            for line in result.stdout.splitlines():
                parts = line.split()
                if parts and self.luks_unlocker.luks_mapper_prefix in parts[0]:
                    dev_name = parts[0]
                    try:
                        run_sudo(
                            self.logger,
                            ["dmsetup", "remove", dev_name],
                            check=False,
                            capture=True,
                            failure_log_level=logging.DEBUG,
                        )
                        self.logger.debug(f"Removed device mapper device: {dev_name}")
                    except Exception as e:  # pylint: disable=broad-exception-caught
                        self.logger.debug(f"Failed to remove dm device {dev_name}: {e}")
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.debug(f"dmsetup cleanup warning: {e}")
