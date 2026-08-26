# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# pylint: disable=too-many-lines  # cohesive offline-fixing orchestrator; splitting would fragment the fix pipeline
"""
Offline filesystem fixing for migrated VMs.

Comprehensive offline fixing orchestrator for Linux and Windows VMs.
Handles fstab, crypttab, GRUB, network configs, VMware tools removal,
and Windows-specific fixes. Operates via guestfs without booting the VM.

Architecture:
    This orchestrator delegates to focused modules for maintainability:
    - offline/operations/storage.py - Storage stack activation (LVM, LUKS, RAID, ZFS)
    - offline/helpers/root_detection.py - Root filesystem detection
    - offline/helpers/xfs_uuid.py - XFS UUID regeneration for cloned VMs
    - offline/helpers/utilities.py - Common utility functions
    - offline/models.py - Data models for operation results

Refactored: 2,808 → 2,416 lines (-392 lines, -14%)
"""

# pylint: disable=duplicate-code
# reason: this module has 7+ small blocks (LUKS unlock audit dict init,
# subprocess wrappers around qemu-img/lvs/blkid, inspect_os() try/except,
# etc.) that are structurally similar to blocks in several sibling
# fixer/vmcraft modules (e.g. vmcraft/storage.py, luks/unlocker.py,
# orchestration/disk_processor.py, core/guest_identity.py) by coincidence,
# not shared logic; keeping each independently editable avoids coupling
# unrelated fixer code paths. See git history for the pylint pass that
# reviewed each instance.

# h2kvm/fixers/offline_fixer.py
from __future__ import annotations

import contextlib
import datetime as _dt
import os
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

# cyclic-import: h2kvm/__init__.py only imports orchestration/DiskProcessor
# lazily inside a function, so by the time anything reaches this module (via
# orchestration -> disk_processor -> offline_fixer, or the manifest orchestrator
# chain), the top-level h2kvm package is already fully initialized in
# sys.modules -- this import cannot actually trigger a circular ImportError.
from h2kvm import __version__  # pylint: disable=cyclic-import
from h2kvm.core.constants import DEFAULT_CONTAINER_ISOLATION
from h2kvm.core.guestfs_factory import create_guestfs
from h2kvm.core.structured_log import PhaseTimer, TraceContext, log_event
from h2kvm.core.utils import U
from h2kvm.vmcraft._utils import run_sudo

from . import network_fixer  # type: ignore
from .bootloader import grub as grub_fixer  # type: ignore

# Delegated fixers (keep OfflineFSFix "thin")
from .filesystem import fixer as filesystem_fixer  # type: ignore
from .filesystem.fstab import (
    Change,
    FstabMode,
    parse_btrfsvol_spec,
)
from .injectors import (
    firstboot_injector,  # type: ignore
    hostname_config_injector,  # type: ignore
    network_config_injector,  # type: ignore
    service_config_injector,  # type: ignore
    user_config_injector,  # type: ignore
)
from .offline.config_rewriter import FstabCrypttabRewriter

# Extracted modules for focused functionality
# Import extracted models, operations, and helpers
from .offline.helpers import OfflineUtilities, RootDetector, XfsUuidRegenerator
from .offline.models import VmwareRemovalResult
from .offline.operations import StorageActivator
from .offline.spec_converter import SpecConverter
from .offline.validation import OfflineValidationManager
from .offline.vmware_tools_remover import OfflineVmwareToolsRemover
from .report_writer import write_report
from .windows import fixer as windows_fixer  # type: ignore

if TYPE_CHECKING:
    import logging
    from collections.abc import Callable

    from h2kvm.core.guestfs_typing import guestfs
    from h2kvm.core.recovery_manager import RecoveryManager
    from h2kvm.core.validation_suite import ValidationSuite


_T = TypeVar("_T")

# OfflineFSFix (thin orchestrator)


@dataclass
class OfflineFixConfig:  # pylint: disable=too-many-instance-attributes
    """
    Configuration for offline filesystem fixing.

    Groups all parameters for OfflineFSFix into logical categories.
    """

    # Required parameters
    image: Path

    # Flags
    dry_run: bool = False
    no_backup: bool = False
    print_fstab: bool = False
    update_grub: bool = True
    regen_initramfs: bool = True

    # Config
    fstab_mode: str | FstabMode = "by-uuid"
    report_path: Path | None = None
    resize: str | None = None

    # VMware
    remove_vmware_tools: bool = False

    # Windows RDP (firstboot + offline registry). None = auto (enable for Windows guests).
    enable_rdp: bool | None = None

    # Injection configurations
    inject_cloud_init: dict[str, Any] | None = None
    firstboot_scripts: dict[str, Any] | None = None
    network_config_inject: dict[str, Any] | None = None
    user_config_inject: dict[str, Any] | None = None
    service_config_inject: dict[str, Any] | None = None
    hostname_config_inject: dict[str, Any] | None = None

    # Recovery
    recovery_manager: RecoveryManager | None = None

    # Windows
    virtio_drivers_dir: str | None = None

    # LUKS support
    luks_enable: bool = False
    luks_passphrase: str | None = None
    luks_passphrase_env: str | None = None
    luks_keyfile: Path | None = None
    luks_mapper_prefix: str = "h2kvm-crypt"

    # Filesystem repair
    filesystem_repair_enable: bool = False

    # VMCraft
    conversion_dir: str | Path | None = None
    allowed_dirs: list[str] | None = None  # Additional allowed directories for security

    # Backend selection (see BackendType enum in core.guestfs_factory)
    backend: str = "vmcraft"

    # Container isolation for LVM (default: enabled)
    container_isolation: bool = DEFAULT_CONTAINER_ISOLATION

    # Auto-switch to libguestfs backend when LUKS detected
    # (libguestfs uses its own supermin appliance with full device visibility)
    auto_backend_switch: bool = True


class OfflineFSFix:  # pylint: disable=too-many-instance-attributes,too-many-public-methods
    """
    Offline guest fix engine (thin orchestrator):
      - robust root detection + safe mount
      - rewrite fstab/crypttab -> stable IDs
      - optional filesystem fixer pass (delegated)
      - network config sanitization (delegated)
      - grub root/device.map + regen (delegated)
      - Windows hooks (delegated)
      - VMware tools removal (mounted-tree remover)
      - report + recovery checkpoints
      - FULL LUKS support: unlock + map + LVM activation + audit

    Additive storage-stack support:
      - mdraid assemble (mdadm --assemble --scan --run) if available in appliance
      - best-effort ZFS import if zpool exists in appliance
      - stronger brute-force root choice via scoring (multi-root safety)
    """

    _BTRFS_COMMON_SUBVOLS = ["@", "@/", "@root", "@rootfs", "@/.snapshots/1/snapshot"]
    _ROOT_HINT_FILES = ["/etc/fstab", "/etc/os-release", "/bin/sh", "/sbin/init"]
    _ROOT_STRONG_HINTS = ["/etc/passwd", "/usr/bin/env", "/var/lib", "/proc"]  # heuristic only

    # pylint: disable=too-many-statements  # VM fixer step handles many device/filesystem-specific cases
    def __init__(self, logger: logging.Logger, config: OfflineFixConfig):
        """
        Initialize OfflineFSFix with configuration object.

        Args:
            logger: Logger instance
            config: Complete configuration object

        Example:
            config = OfflineFixConfig(
                image=Path("/path/to/disk.qcow2"),
                dry_run=False,
                update_grub=True,
                luks_enable=True,
            )
            fixer = OfflineFSFix(logger, config)
        """
        self.logger = logger
        self.image = Path(config.image)
        self.dry_run = bool(config.dry_run)
        self.no_backup = bool(config.no_backup)
        self.print_fstab = bool(config.print_fstab)
        self.update_grub = bool(config.update_grub)
        self.regen_initramfs = bool(config.regen_initramfs)
        self.fstab_mode = FstabMode(config.fstab_mode)
        self.report_path = Path(config.report_path) if config.report_path else None
        self.remove_vmware_tools = bool(config.remove_vmware_tools)
        self.enable_rdp = config.enable_rdp  # True/False/None; Windows firstboot + optional offline fallback
        self.inject_cloud_init_data = config.inject_cloud_init or {}
        self.firstboot_config = config.firstboot_scripts or {}
        self.network_config_inject = config.network_config_inject or {}
        self.user_config_inject = config.user_config_inject or {}
        self.service_config_inject = config.service_config_inject or {}
        self.hostname_config_inject = config.hostname_config_inject or {}
        self.recovery_manager = config.recovery_manager
        self.resize = config.resize
        self.virtio_drivers_dir = config.virtio_drivers_dir

        # LUKS configuration
        self.luks_enable = bool(config.luks_enable)
        self.luks_passphrase = config.luks_passphrase
        self.luks_passphrase_env = config.luks_passphrase_env
        self.luks_keyfile = Path(config.luks_keyfile) if config.luks_keyfile else None
        self.luks_mapper_prefix = config.luks_mapper_prefix
        self._luks_opened: dict[str, str] = {}  # luks_dev -> /dev/mapper/name

        # Storage stack activation tracking (prevent redundant activations)
        self._lvm_activated: bool = False

        # Security - allowed directories
        self.allowed_dirs = config.allowed_dirs or []

        # Backend selection
        self.backend = config.backend

        # Container isolation for LVM
        self.container_isolation = bool(config.container_isolation)

        # LVM/LUKS detection (for reporting)
        self._detected_lvm = False
        self._detected_luks = False

        # Initialize storage activator
        self._storage_activator = StorageActivator(logger=self.logger)

        # Initialize helper modules
        self._root_detector = RootDetector(logger=self.logger)
        self._uuid_regenerator = XfsUuidRegenerator(logger=self.logger)
        self._utilities = OfflineUtilities(logger=self.logger)

        # Filesystem fixer flag (avoid shadowing method name)
        self.filesystem_repair_enable = bool(config.filesystem_repair_enable)

        # VMCraft conversion directory
        self.conversion_dir = config.conversion_dir

        self.inspect_root: str | None = None
        self.root_dev: str | None = None
        self.root_btrfs_subvol: str | None = None
        self.boot_disk_index: int | None = None  # For multi-disk boot order detection
        self.converted_image_path: Path | None = None  # Path to converted qcow2 if created
        self.detected_windows_build: int | None = None  # Windows build number (22000+ = Win11)
        self.detected_windows_product: str | None = None  # e.g. "Windows 11 Pro"
        self.root_fstype: str | None = None  # Filesystem type of root (ext4, ntfs, xfs, ...)

        self.report: dict[str, Any] = {
            "tool": "h2kvm",
            "version": __version__,
            "image": str(self.image),
            "dry_run": self.dry_run,
            "changes": {},
            "analysis": {},
            "timestamps": {"start": _dt.datetime.now().isoformat()},
        }

        # Timings/metrics stash
        self._timings: dict[str, float] = {}

        # Initialize helper modules (composition over inheritance)
        self._spec_converter = SpecConverter(
            fstab_mode=self.fstab_mode,
            root_dev=None,  # Will be set after root detection
        )
        self._config_rewriter = FstabCrypttabRewriter(
            logger=self.logger,
            spec_converter=self._spec_converter,
            dry_run=self.dry_run,
            no_backup=self.no_backup,
            print_fstab=self.print_fstab,
            fstab_mode=self.fstab_mode,
        )
        self._validation_manager = OfflineValidationManager(logger=self.logger)

    # stage runner (timing + per-stage error capture)
    @contextlib.contextmanager
    def _time_stage(self, name: str) -> Any:
        t0 = time.time()
        try:
            yield
        finally:
            dt = time.time() - t0
            self._timings[name] = dt
            try:
                self.report.setdefault("analysis", {}).setdefault("stages", {})[name] = {
                    "duration_s": round(dt, 6),
                }
            except (KeyError, TypeError) as e:
                self.logger.debug(f"Failed to record stage timing for {name}: {e}")

    def _update_stage_report(self, name: str, data: dict[str, Any]) -> None:
        """Update the stage report entry. Swallows only dict/type errors."""
        try:
            self.report.setdefault("analysis", {}).setdefault("stages", {})[name].update(data)
        except (KeyError, TypeError, AttributeError) as e:
            self.logger.debug(f"Failed to update stage report for {name}: {e}")

    def _run_stage(
        self,
        name: str,
        fn: Callable[[], _T],
        *,
        critical: bool = False,
        default: _T | None = None,
    ) -> _T:
        """
        Run a stage, capture duration, and write a structured entry into report.
        - critical=True re-raises on failure (preserving existing "fail fast" semantics where needed)
        - critical=False returns default and records error (keeps report complete)
        """
        self.logger.debug(f"Stage start: {name}")
        with self._time_stage(name):
            try:
                out = fn()
                self._update_stage_report(name, {"ok": True, "error": None})
                self.logger.debug(f"Stage ok: {name}")
                return out
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception as e:
                tb = traceback.format_exc(limit=50)
                self.logger.warning(f"Stage failed: {name}: {e}")
                self._update_stage_report(name, {"ok": False, "error": str(e), "traceback": tb})
                if critical:
                    raise
                return default  # type: ignore[return-value]

    def _stash_guestfs_info(self, g: guestfs.GuestFS) -> None:
        """Stash guestfs info for reporting (delegates to OfflineUtilities)."""
        try:
            info = self._utilities.stash_guestfs_info(g)
            self.report.setdefault("analysis", {})["guestfs"] = info
        except (AttributeError, KeyError, TypeError) as e:
            self.logger.debug(f"Failed to store guestfs info in report: {e}")

    def _quick_probe_lvm_luks(self) -> bool:
        """Quick probe: check if disk contains LVM or LUKS before choosing backend.

        Uses qemu-nbd + blkid to scan partitions without fully launching guestfs.
        Returns True if LVM2_member or crypto_LUKS is found.
        """
        # pylint: disable=too-many-nested-blocks  # VM fixer step handles many device/filesystem-specific cases
        try:
            result = subprocess.run(
                ["qemu-img", "info", "--output=json", str(self.image)],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode != 0:
                return False

            # Quick NBD probe: connect, blkid, disconnect
            # Find a free NBD device
            for nbd_idx in range(8, 16):  # Use high-numbered NBD to avoid conflicts
                nbd_dev = f"/dev/nbd{nbd_idx}"
                if os.path.exists(nbd_dev):
                    lock_result = subprocess.run(
                        [
                            "qemu-nbd",
                            "--connect",
                            nbd_dev,
                            "--read-only",
                            "--format",
                            "qcow2",
                            str(self.image),
                        ],
                        capture_output=True,
                        timeout=10,
                        check=False,
                    )
                    if lock_result.returncode == 0:
                        try:
                            subprocess.run(
                                ["partprobe", nbd_dev], capture_output=True, timeout=5, check=False
                            )
                            time.sleep(0.3)
                            blkid_result = subprocess.run(
                                ["blkid", "-o", "value", "-s", "TYPE"]
                                + [f"{nbd_dev}p{i}" for i in range(1, 5)],
                                capture_output=True,
                                text=True,
                                timeout=10,
                                check=False,
                            )
                            types = blkid_result.stdout.strip().splitlines()
                            has_lvm = any("LVM2_member" in t for t in types)
                            has_luks = any("crypto_LUKS" in t for t in types)
                            if has_lvm or has_luks:
                                reasons = []
                                if has_lvm:
                                    reasons.append("LVM")
                                if has_luks:
                                    reasons.append("LUKS")
                                self.logger.info("Quick probe: detected %s on disk", "+".join(reasons))
                                return True
                        finally:
                            subprocess.run(
                                ["qemu-nbd", "--disconnect", nbd_dev],
                                capture_output=True,
                                timeout=5,
                                check=False,
                            )
                        return False
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as e:
            self.logger.debug("Quick LVM/LUKS probe failed: %s", e)
        return False

    # guestfs open/close helpers
    def open(self) -> guestfs.GuestFS:
        """
        Open guestfs with configured backend.

        Backend options:
        - "vmcraft" (default): Fast pure-Python backend with native LVM handling
        - "guestfs": Native libguestfs with supermin appliance (full LUKS/TPM support)
        - "namespace": Unshare-based isolation for maximum security (experimental)

        Auto-switches to "guestfs" when LUKS is enabled, because libguestfs's
        supermin appliance provides full device visibility for cryptsetup_open,
        clevis_luks_unlock, and LVM-inside-LUKS activation.
        """
        backend = self.backend

        # Auto-switch to libguestfs when LVM or LUKS is detected.
        # libguestfs boots a supermin appliance with full device visibility —
        # LVM activation, cryptsetup_open, and dracut all run inside the VM.
        # Same technique as virt-v2v.
        if backend == "vmcraft" and (self.luks_enable or self._quick_probe_lvm_luks()):
            # pylint: disable=import-outside-toplevel  # lazy import: optional dependency or avoids a circular import
            from h2kvm.core.guestfs_factory import _guestfs_appliance_available

            if _guestfs_appliance_available():
                backend = "guestfs"
                self.logger.info(
                    "Auto-switched to libguestfs backend (LVM/LUKS detected — "
                    "supermin appliance provides full device visibility)"
                )
            else:
                self.logger.warning(
                    "LVM/LUKS detected but libguestfs supermin appliance not available — "
                    "staying on VMCraft backend. "
                    "Install: dnf install -y libguestfs libguestfs-tools supermin python3-libguestfs  "
                    "(Debian/Ubuntu: apt install -y libguestfs-tools supermin python3-guestfs). "
                    "Re-run `h2kvm doctor` or `libguestfs-test-tool` after installing."
                )

        self.logger.debug(f"Using backend: {backend}")

        g = create_guestfs(
            python_return_dict=True,
            backend=backend,
            conversion_dir=self.conversion_dir,
            allowed_dirs=self.allowed_dirs,
            container_isolation=self.container_isolation,
        )
        # NOTE: read-only when dry_run (prevents accidental writes).
        # Detect disk format for libguestfs (VMDK needs explicit format hint)
        drive_kwargs: dict[str, Any] = {"readonly": self.dry_run}
        ext = Path(self.image).suffix.lower()
        fmt_map = {
            ".vmdk": "vmdk",
            ".qcow2": "qcow2",
            ".raw": "raw",
            ".vhd": "vpc",
            ".vhdx": "vhdx",
            ".img": "raw",
        }
        if ext in fmt_map:
            drive_kwargs["format"] = fmt_map[ext]
        g.add_drive_opts(str(self.image), **drive_kwargs)
        g.launch()

        # Log backend info if available (VMCraft backend specific)
        if hasattr(g, "get_backend_info"):
            try:
                backend_info = g.get_backend_info()
                self.logger.debug(f"Backend: {backend_info.get('implementation', 'unknown')}")
                if hasattr(g, "get_performance_metrics"):
                    metrics = g.get_performance_metrics()
                    if metrics:
                        self.logger.debug(f"Launch performance: {metrics}")
            except (AttributeError, OSError):
                pass  # Backend info not available on this implementation

        self._stash_guestfs_info(g)
        return g

    @staticmethod
    def _safe_umount_all(g: guestfs.GuestFS) -> None:
        """Safely unmount all (delegates to OfflineUtilities)."""
        OfflineUtilities.safe_umount_all(g)

    # LUKS / LVM
    def _read_luks_key_bytes(self) -> bytes | None:
        """Read LUKS key (delegates to OfflineUtilities)."""
        return self._utilities.read_luks_key_bytes(
            self.luks_passphrase, self.luks_passphrase_env, self.luks_keyfile
        )

    def _activate_lvm(self, g: guestfs.GuestFS) -> None:
        """Activate LVM (delegates to StorageActivator)."""
        self._storage_activator.activate_lvm(g)
        # pylint: disable=protected-access  # tight coupling with sibling fixer/backend internals in this package
        self._lvm_activated = self._storage_activator._lvm_activated

    def _regenerate_uuids(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Regenerate filesystem UUIDs on LVM volumes (delegates to FilesystemUUIDRegenerator)."""
        return self._uuid_regenerator.regenerate_uuids(g)

    # Helper methods for _rebuild_fstab_from_disk_layout (complexity reduction)

    def _parse_fstab_expected_mounts(self, old_fstab: str) -> dict[str, tuple[str, str, str, str]]:
        """Parse mountpoints from old fstab content."""
        expected_mounts = {}  # mountpoint -> (fstype, options, dump, pass)
        for line in old_fstab.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if len(parts) >= 4:
                mountpoint = parts[1]
                fstype = parts[2]
                options = parts[3] if len(parts) > 3 else "defaults"
                dump = parts[4] if len(parts) > 4 else "0"
                passno = parts[5] if len(parts) > 5 else "0"
                expected_mounts[mountpoint] = (fstype, options, dump, passno)
        self.logger.debug(f"  Expected mountpoints from old fstab: {list(expected_mounts.keys())}")
        return expected_mounts

    def _infer_mountpoint_devices(
        self, device_to_uuid: dict[str, str], expected_mounts: dict[str, tuple[str, str, str, str]]
    ) -> dict[str, str]:
        """Infer which devices should be mounted where using heuristics."""
        mountpoint_to_device = {}

        # Root device is already known
        if self.root_dev and "/" in expected_mounts:
            mountpoint_to_device["/"] = self.root_dev
            self.logger.debug(f"  Root: {self.root_dev} → /")

        # Use partition numbering heuristics
        for device in device_to_uuid:
            if device == self.root_dev:
                continue

            # Common patterns: p1/sda1 → /boot, p5/sda5 → /home
            if device.endswith(("p1", "sda1")):
                if "/boot" in expected_mounts and "/boot" not in mountpoint_to_device:
                    mountpoint_to_device["/boot"] = device
                    self.logger.debug(f"  Boot: {device} → /boot")
            elif device.endswith(("p5", "sda5")):
                if "/home" in expected_mounts and "/home" not in mountpoint_to_device:
                    mountpoint_to_device["/home"] = device
                    self.logger.debug(f"  Home: {device} → /home")

        return mountpoint_to_device

    # pylint: disable=too-many-locals  # VM fixer step handles many device/filesystem-specific cases
    def _build_fstab_entries(
        self,
        old_fstab: str,
        expected_mounts: dict[str, tuple[str, str, str, str]],
        mountpoint_to_device: dict[str, str],
        device_to_uuid: dict[str, str],
    ) -> tuple[list[str], int]:
        """Build new fstab entries from device mappings."""
        new_lines = [
            "#",
            "# /etc/fstab",
            "# Rebuilt by h2kvm based on actual disk UUIDs",
            "#",
            "# Accessible filesystems, by reference, are maintained under '/dev/disk/'.",
            "# See man pages fstab(5), findfs(8), mount(8) and/or blkid(8) for more info.",
            "#",
        ]

        rebuilt_count = 0

        for mountpoint in sorted(expected_mounts.keys()):
            # Special case: swap
            if mountpoint == "none":
                for line in old_fstab.splitlines():
                    if not line.strip().startswith("#") and "swap" in line:
                        new_lines.append(line)
                        rebuilt_count += 1
                continue

            # Check if we have device and UUID
            if mountpoint not in mountpoint_to_device:
                self.logger.warning(
                    f"  Could not determine which disk device maps to mountpoint {mountpoint} — "
                    "no matching partition found by heuristics. "
                    "This mount entry will be omitted from the rebuilt fstab. "
                    "After boot, manually add it using 'blkid' to find the correct UUID."
                )
                continue

            device = mountpoint_to_device[mountpoint]
            if device not in device_to_uuid:
                self.logger.warning(
                    f"  No filesystem UUID found for device {device} (mountpoint: {mountpoint}). "
                    "The filesystem may not have a UUID assigned, or blkid could not read it. "
                    "After boot, run 'blkid {device}' and update /etc/fstab manually.".format(
                        device=device, mountpoint=mountpoint
                    )
                )
                continue

            uuid = device_to_uuid[device]
            fstype, options, dump, passno = expected_mounts[mountpoint]

            # Build entry
            spec = f"UUID={uuid}"
            entry = f"{spec} {mountpoint}\t{fstype}\t{options}\t{dump} {passno}"
            new_lines.append(entry)
            rebuilt_count += 1

            self.logger.info(f"  ✓ Rebuilt entry: {mountpoint} → {device} (UUID: {uuid[:8]}...)")

        return new_lines, rebuilt_count

    def _write_fstab_with_backup(self, g: guestfs.GuestFS, new_fstab_content: str) -> bool:
        """Write new fstab using sudo with backup."""
        try:
            # Write to temp file first
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".fstab") as tf:
                tf.write(new_fstab_content)
                temp_path = tf.name

            # Get the actual mount path
            # pylint: disable=protected-access  # tight coupling with sibling fixer/backend internals in this package
            if hasattr(g, "_mount_root") and g._mount_root:
                # pylint: disable=protected-access  # tight coupling with sibling fixer/backend internals in this package
                fstab_path = Path(g._mount_root) / "etc" / "fstab"
            else:
                self.logger.error("  Could not determine mount root")
                return False

            # Backup old fstab first
            backup_path = Path(str(fstab_path) + ".h2kvm_backup")
            try:
                run_sudo(self.logger, ["cp", str(fstab_path), str(backup_path)], check=True, capture=True)
                self.logger.debug(f"  Backed up old fstab to {backup_path}")
            except (OSError, PermissionError, subprocess.CalledProcessError) as e:
                self.logger.debug(f"  Could not backup old fstab: {e}")

            # Copy temp file to fstab using sudo
            run_sudo(self.logger, ["cp", temp_path, str(fstab_path)], check=True, capture=True)

            # Cleanup temp file
            Path(temp_path).unlink()

            return True

        except (OSError, PermissionError, subprocess.CalledProcessError) as e:
            self.logger.exception(
                f"  Failed to write /etc/fstab to the guest disk: {e}. "
                "The VM may fail to mount filesystems on boot. "
                "After booting into rescue mode, manually create /etc/fstab "
                "using 'blkid' to find filesystem UUIDs."
            )
            return False

    def _rebuild_fstab_from_disk_layout(
        self, g: guestfs.GuestFS, uuid_changes: list[dict[str, Any]]
    ) -> bool:
        """
        Completely rebuild fstab when UUIDs don't match (indicates fstab from different VM).

        Uses actual device layout and new UUIDs to create a fresh, correct fstab.

        Args:
            uuid_changes: List of dicts with device, old_uuid, new_uuid

        Returns:
            True if fstab was rebuilt, False otherwise
        """
        if not uuid_changes:
            return False

        self.logger.info("🔧 Rebuilding fstab from actual disk layout...")

        try:
            # Phase 1: Build device-to-UUID mapping
            device_to_uuid = {change["device"]: change["new_uuid"] for change in uuid_changes}

            # Phase 2: Read and parse old fstab
            if not g.is_file("/etc/fstab"):
                self.logger.warning(
                    "  No /etc/fstab found.\n"
                    "    The guest may use a non-standard filesystem layout or be a container image.\n"
                    "    The VM may still boot if the root device is specified in the bootloader config."
                )
                return False

            old_fstab = g.read_file("/etc/fstab")
            if isinstance(old_fstab, bytes):
                old_fstab = old_fstab.decode("utf-8", errors="replace")

            expected_mounts = self._parse_fstab_expected_mounts(old_fstab)

            # Phase 3: Infer mountpoint-to-device mapping
            mountpoint_to_device = self._infer_mountpoint_devices(device_to_uuid, expected_mounts)

            # Phase 4: Build new fstab entries
            new_lines, rebuilt_count = self._build_fstab_entries(
                old_fstab, expected_mounts, mountpoint_to_device, device_to_uuid
            )

            if rebuilt_count == 0:
                self.logger.warning(
                    "  No entries could be rebuilt.\n"
                    "    This can happen when partition UUIDs have changed and cannot be mapped.\n"
                    "    Manual fix: boot a rescue image and run 'blkid' to find current UUIDs,\n"
                    "    then update /etc/fstab accordingly."
                )
                return False

            # Phase 5: Write new fstab
            new_fstab = "\n".join(new_lines) + "\n"
            if self._write_fstab_with_backup(g, new_fstab):
                self.logger.info(f"  ✓ Rebuilt /etc/fstab with {rebuilt_count} entries")
                return True
            return False

        except (OSError, KeyError, ValueError) as e:
            self.logger.exception(f"  ⚠️  Failed to rebuild fstab: {e}")
            return False

    # pylint: disable=too-many-locals,too-many-branches,too-many-statements  # VM fixer step handles many device/filesystem-specific cases
    def _update_fstab_with_new_uuids(self, g: guestfs.GuestFS, uuid_changes: list[dict[str, Any]]) -> None:
        """
        Update /etc/fstab with new UUIDs after XFS UUID regeneration.

        Uses simple direct approach: for any fstab entry with a UUID= spec,
        check if that device exists in our regenerated list and update it.

        Args:
            uuid_changes: List of dicts with device, old_uuid, new_uuid
        """
        if not uuid_changes:
            self.logger.debug("  No UUID changes to apply to fstab")
            return

        self.logger.debug(f"  Received {len(uuid_changes)} UUID changes to apply")
        for change in uuid_changes:
            self.logger.debug(f"    {change['device']}: {change['old_uuid']} → {change['new_uuid']}")

        # Build device-to-new-uuid mapping
        device_to_new_uuid = {change["device"]: change["new_uuid"] for change in uuid_changes}
        old_uuid_to_new = {
            change["old_uuid"]: (change["new_uuid"], change["device"]) for change in uuid_changes
        }

        try:
            if not g.is_file("/etc/fstab"):
                self.logger.debug("No /etc/fstab found, skipping UUID update")
                return

            fstab_content = g.read_file("/etc/fstab")
            if isinstance(fstab_content, bytes):
                fstab_content = fstab_content.decode("utf-8", errors="replace")

            self.logger.debug(
                f"  Read fstab content ({len(fstab_content)} bytes, {len(fstab_content.splitlines())} lines)"
            )

            # Show what UUIDs are currently in fstab
            fstab_uuids = set()
            for line in fstab_content.splitlines():
                if "UUID=" in line and not line.strip().startswith("#"):
                    parts = line.strip().split()
                    if parts and parts[0].startswith("UUID="):
                        uuid_val = parts[0][5:]
                        fstab_uuids.add(uuid_val)
                        self.logger.debug(f"    fstab references UUID: {uuid_val}")

            # Try matching by old UUID first
            modified = False
            new_lines = []
            update_count = 0

            for i, line in enumerate(fstab_content.splitlines(), 1):
                new_line = line

                # Skip comments and empty lines
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    new_lines.append(new_line)
                    continue

                # Parse fstab entry
                parts = stripped.split()
                if len(parts) < 2:
                    new_lines.append(new_line)
                    continue

                fs_spec = parts[0]

                # Update UUID= entries
                if fs_spec.startswith("UUID="):
                    old_uuid_in_fstab = fs_spec[5:]

                    # Check if this is one of the old UUIDs we just changed
                    if old_uuid_in_fstab in old_uuid_to_new:
                        new_uuid, device = old_uuid_to_new[old_uuid_in_fstab]
                        new_spec = f"UUID={new_uuid}"
                        new_line = line.replace(fs_spec, new_spec, 1)
                        modified = True
                        update_count += 1
                        mountpoint = parts[1] if len(parts) > 1 else "unknown"
                        self.logger.info(
                            f"  ✓ Updated fstab line {i} ({mountpoint}): "
                            f"UUID={old_uuid_in_fstab[:8]}... → UUID={new_uuid[:8]}..."
                        )
                        self.logger.debug(f"    Device: {device}")
                        self.logger.debug(f"    Old line: {line.strip()}")
                        self.logger.debug(f"    New line: {new_line.strip()}")

                new_lines.append(new_line)

            if modified:
                new_fstab = "\n".join(new_lines) + "\n"

                # Write using sudo (VMCraft mounts are owned by root)
                try:
                    # Write to temp file first
                    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".fstab") as tf:
                        tf.write(new_fstab)
                        temp_path = tf.name

                    # Get the actual mount path
                    # pylint: disable=protected-access  # tight coupling with sibling fixer/backend internals in this package
                    if hasattr(g, "_mount_root") and g._mount_root:
                        # pylint: disable=protected-access  # tight coupling with sibling fixer/backend internals in this package
                        fstab_path = Path(g._mount_root) / "etc" / "fstab"

                        # Backup old fstab first
                        backup_path = Path(str(fstab_path) + ".h2kvm_backup")
                        try:
                            run_sudo(
                                self.logger,
                                ["cp", str(fstab_path), str(backup_path)],
                                check=True,
                                capture=True,
                            )
                            self.logger.debug(f"  Backed up old fstab to {backup_path}")
                        except (OSError, PermissionError, subprocess.CalledProcessError) as e:
                            self.logger.debug(f"  Could not backup old fstab: {e}")

                        # Copy temp file to fstab using sudo
                        run_sudo(self.logger, ["cp", temp_path, str(fstab_path)], check=True, capture=True)

                        # Cleanup temp file
                        Path(temp_path).unlink()

                        self.logger.info(f"  ✓ Updated /etc/fstab with {update_count} new UUID(s)")
                    else:
                        self.logger.error("  Could not determine mount root for fstab write")
                        Path(temp_path).unlink()

                except (OSError, PermissionError, subprocess.CalledProcessError) as write_error:
                    self.logger.exception(
                        f"  Failed to write updated /etc/fstab after UUID regeneration: {write_error}. "
                        "The fstab still references old UUIDs that no longer match the disk. "
                        "The VM will fail to mount filesystems on boot. "
                        "After booting into rescue mode, update UUID= entries in /etc/fstab "
                        "to match output of 'blkid'."
                    )
                    if "temp_path" in locals():
                        Path(temp_path).unlink(missing_ok=True)
            else:
                self.logger.warning("  ⚠️  fstab UUIDs don't match any regenerated UUIDs.")
                self.logger.warning(
                    "  This likely means fstab is from a different VM or previous migration.\n"
                    "    h2kvm will attempt an automatic fstab rebuild next.\n"
                    "    If that fails, boot a rescue image and update /etc/fstab with 'blkid' output."
                )
                self.logger.debug(f"  fstab UUIDs: {fstab_uuids}")
                self.logger.debug(f"  Old UUIDs we regenerated: {set(old_uuid_to_new.keys())}")
                self.logger.debug(f"  Devices with new UUIDs: {list(device_to_new_uuid.keys())}")

                # Try automatic fstab rebuild
                self.logger.info("  Attempting automatic fstab rebuild...")
                if self._rebuild_fstab_from_disk_layout(g, uuid_changes):
                    self.logger.info("  ✓ fstab successfully rebuilt from disk layout")
                else:
                    self.logger.error("  ⚠️  Automatic fstab rebuild failed - manual intervention required")

        except (OSError, KeyError, ValueError) as e:
            self.logger.exception(f"  ⚠️  Failed to update fstab with new UUIDs: {e}")

    # pylint: disable=too-many-locals,too-many-branches,too-many-statements  # VM fixer step handles many device/filesystem-specific cases
    def _unlock_luks_devices(self, g: guestfs.GuestFS) -> dict[str, Any]:
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
        if not hasattr(g, "cryptsetup_open"):
            audit["errors"].append("guestfs_missing:cryptsetup_open")
            return audit

        # Detect LUKS devices using two methods:
        # 1. list_filesystems() — works on VMCraft (returns crypto_LUKS)
        # 2. list_partitions() + vfs_type() — works on libguestfs
        #    (list_filesystems skips LUKS on native guestfs, same as decrypt.c)
        luks_devs: list[str] = []

        try:
            fsmap = g.list_filesystems() or {}
        except (RuntimeError, OSError) as e:
            audit["errors"].append(f"list_filesystems_failed:{e}")
            fsmap = {}

        # Method 1: from list_filesystems
        for dev, fstype in fsmap.items():
            if U.to_text(fstype) == "crypto_LUKS":
                luks_devs.append(U.to_text(dev))

        # Method 2: scan partitions directly (libguestfs style — decrypt.c)
        if not luks_devs and hasattr(g, "list_partitions"):
            try:
                for part in g.list_partitions() or []:
                    part_str = U.to_text(part)
                    try:
                        vfs = U.to_text(g.vfs_type(part_str))
                        if vfs == "crypto_LUKS":
                            luks_devs.append(part_str)
                    # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                    except Exception as e:
                        self.logger.debug("Could not detect filesystem type on %s: %s", part_str, e)
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception as e:
                self.logger.debug(f"Partition scan for LUKS failed: {e}")
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
                # libguestfs cryptsetup_open expects str key, not bytes
                key_str = (
                    key_bytes.decode("utf-8", errors="strict") if isinstance(key_bytes, bytes) else key_bytes
                )
                g.cryptsetup_open(dev, key_str, name)
                mapped = f"/dev/mapper/{name}"
                self._luks_opened[dev] = mapped
                audit["opened"].append({"device": dev, "mapped": mapped})
                self.logger.info(f"LUKS: opened {dev} -> {mapped}")
            except (RuntimeError, OSError) as e:
                audit["errors"].append({"device": dev, "error": str(e)})
                self.logger.warning(
                    f"LUKS: failed to open {dev}: {e}\n"
                    f"    Check passphrase/keyfile: --luks-passphrase or --luks-keyfile\n"
                    f"    Or set via env var: --luks-passphrase-env VARNAME\n"
                    f"    Verify LUKS header: cryptsetup luksDump {dev}"
                )

        # pylint: disable=too-many-nested-blocks  # VM fixer step handles many device/filesystem-specific cases
        if audit["opened"]:
            # After LUKS open, rescan for LVM PVs inside the decrypted volume.
            # Method depends on backend:
            #   - libguestfs: g.lvm_scan(True) — runs inside supermin appliance
            #   - VMCraft: host subprocess (pvscan/vgscan/vgchange)
            if hasattr(g, "lvm_scan"):
                # Real libguestfs backend — use native API (runs inside appliance)
                try:
                    g.lvm_scan(True)  # True = activate volumes
                    lvs = g.lvs() or []
                    self.logger.info("LVM after LUKS open (libguestfs): %s", lvs)
                # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                except Exception as e:
                    self.logger.warning(
                        "LVM rescan after LUKS open failed: %s. "
                        "LVM volumes inside the LUKS container may not be visible. "
                        "If the VM uses LVM-on-LUKS, ensure cryptsetup and lvm2 are installed.",
                        e,
                    )
            else:
                # VMCraft backend — host-based LVM rescan
                try:
                    time.sleep(0.5)
                    # Create UUID symlinks for initramfs cryptroot hook
                    Path("/dev/disk/by-uuid").mkdir(parents=True, exist_ok=True)
                    for dev_path in audit.get("opened", []):
                        luks_dev = dev_path.get("device", "")
                        if luks_dev:
                            result = subprocess.run(
                                ["blkid", "-s", "UUID", "-o", "value", luks_dev],
                                capture_output=True,
                                text=True,
                                timeout=10,
                                check=False,
                            )
                            if result.returncode == 0 and result.stdout.strip():
                                uuid = result.stdout.strip()
                                symlink = f"/dev/disk/by-uuid/{uuid}"
                                if not os.path.lexists(symlink):
                                    Path(symlink).symlink_to(luks_dev)
                # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                except Exception as e:
                    self.logger.debug("LUKS UUID symlink creation failed: %s", e)

                try:
                    subprocess.run(
                        ["pvscan", "--devicesfile", "", "--cache"],
                        capture_output=True,
                        timeout=10,
                        check=False,
                    )
                    subprocess.run(
                        ["vgscan", "--devicesfile", "", "--cache"],
                        capture_output=True,
                        timeout=10,
                        check=False,
                    )
                    subprocess.run(
                        ["vgchange", "--devicesfile", "", "-ay"],
                        capture_output=True,
                        timeout=10,
                        check=False,
                    )
                    result = subprocess.run(
                        ["lvs", "--devicesfile", "", "--noheadings", "-o", "lv_path,vg_name"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=False,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        self.logger.info(
                            "LVM after LUKS open (host): %s", result.stdout.strip().replace("\n", ", ")
                        )
                # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                except Exception as e:
                    self.logger.warning("LVM rescan after LUKS failed: %s", e)

            self._activate_lvm(g)
        return audit

    # storage stack activation (mdraid/zfs) — additive (delegates to StorageActivator)
    def _guestfs_can_run(self, g: guestfs.GuestFS, prog: str) -> bool:
        """Check if command is available (delegates to StorageActivator)."""
        return self._storage_activator.can_run_command(g, prog)

    def _activate_mdraid(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Activate MD RAID (delegates to StorageActivator)."""
        return self._storage_activator.activate_mdraid(g)

    def _activate_zfs(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Activate ZFS pools (delegates to StorageActivator)."""
        return self._storage_activator.activate_zfs(g)

    def _pre_mount_activate_storage_stack(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """
        Additive activation pipeline (best-effort, do-no-harm):
          - mdraid assemble
          - zfs import
          - lvm activate
        """
        audit: dict[str, Any] = {"mdraid": None, "zfs": None, "lvm": None}
        audit["mdraid"] = self._activate_mdraid(g)
        audit["zfs"] = self._activate_zfs(g)
        try:
            self._activate_lvm(g)
            audit["lvm"] = {"attempted": True, "ok": True}
        except (RuntimeError, OSError, subprocess.CalledProcessError) as e:
            audit["lvm"] = {"attempted": True, "ok": False, "error": str(e)}
        return audit

    # mount logic (safe + robust)
    def _mount_root_direct(self, g: guestfs.GuestFS, dev: str, subvol: str | None) -> None:
        """
        Enhanced (non-breaking): keep original behavior, but add a safe mount fallback ladder
        and a best-effort fsck pass for ext4/xfs when mount fails.

        Helps cases where guestfs mount fails with superblock/journal quirks.
        """
        filesystem_fixer.log_vfs_type_best_effort(self, g, dev)

        def _try_mount(mode: str) -> None:
            # mode: "rw" | "ro" | "opts:<csv>"
            if subvol:
                self.root_btrfs_subvol = subvol
                opts = f"subvol={subvol}"
                if self.dry_run or mode == "ro":
                    opts = f"ro, {opts}"
                if mode.startswith("opts:"):
                    extra = mode.split(":", 1)[1]
                    opts = f"{extra}, {opts}"
                g.mount_options(opts, dev, "/")
                return

            if mode == "rw" and not self.dry_run:
                g.mount(dev, "/")
                return
            if mode == "ro" or self.dry_run:
                g.mount_ro(dev, "/")
                return
            if mode.startswith("opts:"):
                opts = mode.split(":", 1)[1]
                if self.dry_run and "ro" not in opts:
                    opts = f"ro, {opts}"
                g.mount_options(opts, dev, "/")
                return

            # fallback
            g.mount_ro(dev, "/")

        # 1) original behavior path
        try:
            _try_mount("rw" if not self.dry_run else "ro")
            self.root_dev = dev
            self.logger.info(
                f"Mounted root at / using {dev}" + (f" (btrfs subvol={subvol})" if subvol else "")
            )
            return
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as e:
            first_err = e

        # 2) fallback ladder
        tries = ["ro", "opts:noload", "opts:ro, noload", "opts:ro, norecovery"]
        last_err: Exception | None = None
        for t in tries:
            self._safe_umount_all(g)
            try:
                _try_mount(t)
                self.root_dev = dev
                self.logger.info(
                    f"Mounted root at / using {dev}"
                    + (f" (btrfs subvol={subvol})" if subvol else "")
                    + f" [{t}]"
                )
                return
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception as e:
                last_err = e

        # 3) best-effort fsck then retry RO once
        self._safe_umount_all(g)
        fsck_audit = filesystem_fixer.best_effort_fsck(self, g, dev)
        try:
            self.report.setdefault("analysis", {}).setdefault("mount", {})["fsck"] = fsck_audit
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as e:
            self.logger.debug(f"Failed to store fsck audit in report: {e}")

        self._safe_umount_all(g)
        try:
            _try_mount("ro")
            self.root_dev = dev
            self.logger.info(
                f"Mounted root at / using {dev}"
                + (f" (btrfs subvol={subvol})" if subvol else "")
                + " [ro-after-fsck]"
            )
            return
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as e:
            last_err = e

        raise RuntimeError(
            f"Failed to mount root filesystem from {dev}"
            + (f" (btrfs subvol={subvol})" if subvol else "")
            + ". The filesystem may be corrupted or use an unsupported type. "
            "Try running fsck on the source disk before migration. "
            f"Detail: {last_err or first_err}"
        )

    def _path_exists_ci_guestfs(self, g: guestfs.GuestFS, path: str) -> bool:
        """Check if path exists (case-insensitive, delegates to RootDetector)."""
        return self._root_detector.path_exists_case_insensitive(g, path)

    def _looks_like_root(self, g: guestfs.GuestFS) -> bool:
        """Check if mounted filesystem looks like root (delegates to RootDetector)."""
        return self._root_detector.looks_like_root(g)

    def _score_root(self, g: guestfs.GuestFS) -> int:
        """Score root filesystem likelihood (delegates to RootDetector)."""
        return self._root_detector.score_root(g)

    # pylint: disable=too-many-locals,too-many-branches,too-many-statements  # VM fixer step handles many device/filesystem-specific cases
    def detect_and_mount_root(self, g: guestfs.GuestFS) -> None:
        """Detect the guest's root filesystem via inspect_os(), falling back to brute-force mount, and mount it."""
        try:
            roots = g.inspect_os()
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception:
            roots = []
        if not roots:
            self.logger.warning(
                "inspect_os() found no roots; falling back to brute-force mount.\n"
                "    This can happen with LUKS-encrypted, LVM-only, or non-standard disk layouts.\n"
                "    For LUKS volumes, provide: --luks-passphrase or --luks-keyfile"
            )
            self.mount_root_bruteforce(g)
            return

        # Pick best-looking root (avoid roots[0] roulette)
        best_root: str | None = None
        best_score = -(10**9)
        for r in roots:
            rr = U.to_text(r)
            score = 0
            try:
                if g.inspect_get_product_name(rr):
                    score += 2
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception:
                pass
            try:
                if g.inspect_get_distro(rr):
                    score += 2
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception:
                pass
            try:
                mp = g.inspect_get_mountpoints(rr) or {}
                if U.to_text(mp.get("/", "")).strip():
                    score += 2
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception:
                pass
            if score > best_score:
                best_score = score
                best_root = rr

        root = best_root or U.to_text(roots[0])
        self.inspect_root = root

        # Detect boot disk index from inspect root (for multi-disk boot order).
        # Maps root partition (e.g. /dev/sdb2) → parent disk → disk index.
        self.boot_disk_index = self._detect_boot_disk_index(g, root)

        # Log identity (best-effort)
        product = "Unknown"
        distro = "unknown"
        major = 0
        minor = 0
        try:
            product_val = g.inspect_get_product_name(root)
            if product_val:
                product = U.to_text(product_val)
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception:
            pass
        with contextlib.suppress(Exception):
            distro = U.to_text(g.inspect_get_distro(root))
        try:
            major = g.inspect_get_major_version(root)
            minor = g.inspect_get_minor_version(root)
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception:
            pass
        self.logger.info(f"Detected guest: {product} {major}.{minor} (distro={distro})")

        try:
            mp_map = g.inspect_get_mountpoints(root)
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception:
            mp_map = {}

        root_spec = U.to_text(mp_map.get("/", "")).strip()
        if not root_spec:
            self.logger.warning(
                "Inspection did not provide a root (/) devspec; brute-force mounting.\n"
                "    This can happen with non-standard partition layouts or missing OS metadata."
            )
            self.mount_root_bruteforce(g)
            return

        root_dev = root_spec
        subvol: str | None = None
        if root_spec.startswith("btrfsvol:"):
            root_dev, subvol = parse_btrfsvol_spec(root_spec)
            root_dev = root_dev.strip()

        real: str | None = None
        if root_dev.startswith("/dev/disk/by-"):
            # Try guestfs realpath first (works for by-uuid, by-label inside guest)
            try:
                rp = U.to_text(g.realpath(root_dev)).strip()
                if rp.startswith("/dev/"):
                    real = rp
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception:
                real = None

            # For by-path devices, use host-level symlink resolution
            # because VMCraft device paths are on the host, not in the guest filesystem
            if not real and root_dev.startswith("/dev/disk/by-path/"):
                try:
                    real_dev = str(Path(root_dev).readlink())
                    # Handle relative symlinks
                    if not real_dev.startswith("/"):
                        real_dev = os.path.normpath(os.path.join(os.path.dirname(root_dev), real_dev))
                    if real_dev.startswith("/dev/"):
                        real = real_dev
                        self.logger.info(f"Resolved by-path root device: {root_dev} -> {real}")
                # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                except Exception as e:
                    self.logger.warning(f"Failed to resolve by-path root device {root_dev}: {e}")
                    real = None

        # by-path from inspection may be meaningless in a different VM topology
        if not real and root_dev.startswith("/dev/disk/by-path/"):
            self.logger.warning(
                "Root spec is by-path and not resolvable; falling back to brute-force root detection."
            )
            self.mount_root_bruteforce(g)
            return

        if not real and root_dev.startswith("/dev/"):
            real = root_dev

        if not real:
            self.logger.warning("Could not determine root device from inspection; brute-force mounting.")
            self.mount_root_bruteforce(g)
            return

        try:
            self._mount_root_direct(g, real, subvol)
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as e:
            self.logger.warning(f"{e}; brute-force mounting.")
            self.mount_root_bruteforce(g)

    # Helper methods for _candidate_root_devices (complexity reduction)

    def _list_partition_candidates(self, g: guestfs.GuestFS) -> list[str]:
        """List partition candidates."""
        try:
            partitions = [U.to_text(p) for p in (g.list_partitions() or [])]
            self.logger.debug(f"Partitions: {partitions}")
            return partitions
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as e:
            self.logger.warning(f"Failed to list partitions: {e}")
            return []

    def _list_filesystem_candidates(self, g: guestfs.GuestFS) -> list[str]:
        """List filesystem candidates (excludes swap, LUKS, LVM2_member)."""
        candidates = []
        try:
            fsmap = g.list_filesystems() or {}
            self.logger.debug(f"Filesystems map: {list(fsmap.keys())}")
            for dev, fstype in fsmap.items():
                d = U.to_text(dev)
                t = U.to_text(fstype)
                # Skip non-mountable filesystem types
                if t in ("swap", "crypto_LUKS", "LVM2_member"):
                    self.logger.debug(f"Skipping {d} (type={t})")
                    continue
                if d.startswith("/dev/"):
                    candidates.append(d)
                    self.logger.debug(f"Added from filesystems: {d} (type={t})")
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as e:
            self.logger.warning(f"Failed to list filesystems: {e}")
        return candidates

    def _list_lvm_candidates(self, g: guestfs.GuestFS) -> list[str]:
        """List LVM logical volume candidates (excludes swap LVs)."""
        candidates = []
        try:
            if hasattr(g, "lvs"):
                lvs_list = g.lvs() or []
                self.logger.info(f"LVM logical volumes: {lvs_list}")
                for lv in lvs_list:
                    d = U.to_text(lv)
                    if d.startswith("/dev/"):
                        if "swap" in d.lower():
                            self.logger.debug(f"Skipping swap LV: {d}")
                            continue
                        candidates.append(d)
                        self.logger.info(f"Added LV candidate: {d}")
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as e:
            self.logger.warning(f"LVM enumeration failed: {e}")

        # Host-direct LV scan for LUKS volumes (container can't see /dev/mapper/*)
        if self._luks_opened and not candidates:
            try:
                result = subprocess.run(
                    ["lvs", "--devicesfile", "", "--noheadings", "-o", "lv_path"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        lv = line.strip()
                        if lv and lv.startswith("/dev/") and "swap" not in lv.lower():
                            candidates.append(lv)
                            self.logger.info(f"Added LV candidate (host-direct): {lv}")
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception as e:
                self.logger.debug(f"Host-direct LV scan failed: {e}")

        return candidates

    def _deduplicate_candidates(self, candidates: list[str]) -> list[str]:
        """Remove duplicates while preserving order."""
        seen: set[str] = set()
        out: list[str] = []
        for d in candidates:
            if d and d not in seen:
                seen.add(d)
                out.append(d)
        return out

    def _filter_non_root_devices(self, candidates: list[str]) -> list[str]:
        """Filter out loop devices, LUKS placeholders, and resolve by-path devices."""
        filtered = []
        for d in candidates:
            # Skip VMCraft loop devices
            if d.startswith("/dev/loop"):
                self.logger.debug(f"Filtering out loop device: {d}")
                continue
            # Skip LUKS placeholder devices that don't exist
            if "/luks-" in d and not d.startswith("/dev/mapper/luks-"):
                self.logger.debug(f"Filtering out LUKS placeholder: {d}")
                continue

            # Resolve by-path devices to real device paths
            if d.startswith("/dev/disk/by-path/"):
                try:
                    real_dev = str(Path(d).readlink())
                    if not real_dev.startswith("/"):
                        real_dev = os.path.normpath(os.path.join(os.path.dirname(d), real_dev))
                    self.logger.debug(f"Resolved by-path device: {d} -> {real_dev}")
                    d = real_dev
                # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                except Exception as e:
                    self.logger.warning(f"Failed to resolve by-path device {d}: {e}; skipping")
                    continue

            filtered.append(d)
        return filtered

    def _get_current_nbd_info(self, g: guestfs.GuestFS) -> tuple[str | None, list[str], set[str]]:
        """Get current NBD device, its partitions, and LVM devices."""
        current_nbd = None
        current_nbd_parts = []
        current_disk_lv = set()

        try:
            devices = g.list_devices() or []
            if devices:
                current_nbd = U.to_text(devices[0])
                self.logger.debug(f"Current NBD device: {current_nbd}")
                parts = g.list_partitions() or []
                current_nbd_parts = [U.to_text(p) for p in parts if U.to_text(p).startswith(current_nbd)]
                self.logger.debug(f"Current NBD partitions: {current_nbd_parts}")
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as e:
            self.logger.warning(f"Failed to get current NBD device: {e}")

        if current_nbd_parts:
            try:
                lvs_list = g.lvs() or [] if hasattr(g, "lvs") else []
                for lv in lvs_list:
                    current_disk_lv.add(U.to_text(lv))
                self.logger.debug(f"LVM devices from current disk: {current_disk_lv}")
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception as e:
                self.logger.warning(f"Failed to filter LVM devices: {e}")

        return current_nbd, current_nbd_parts, current_disk_lv

    def _filter_to_current_disk(
        self, candidates: list[str], current_nbd: str | None, current_disk_lv: set[str]
    ) -> list[str]:
        """Filter candidates to only include devices from current NBD disk."""
        nbd_filtered = []
        for d in candidates:
            # Include LVM devices only if they're from current disk.
            # LVs can appear as /dev/mapper/VG-LV or /dev/VG/LV (guestfs style)
            is_lvm = (d.startswith("/dev/mapper/") and "control" not in d.lower()) or d in current_disk_lv
            if is_lvm:
                if d in current_disk_lv:
                    nbd_filtered.append(d)
                    self.logger.debug(f"Including LVM device: {d}")
                else:
                    self.logger.debug(f"Filtering out LVM device not from current disk: {d}")
            # Include partitions from current NBD device
            elif current_nbd and d.startswith(current_nbd):
                nbd_filtered.append(d)
            # Skip devices from other disks
            elif current_nbd:
                self.logger.debug(f"Filtering out device from different disk: {d}")
            else:
                # If we can't determine current NBD, include all (fallback)
                nbd_filtered.append(d)
        return nbd_filtered

    def _prioritize_candidates(self, candidates: list[str]) -> list[str]:
        """Prioritize LVM logical volumes over standard partitions."""
        priority = []
        standard = []
        for d in candidates:
            if d.startswith("/dev/mapper/") and "control" not in d.lower():
                priority.append(d)
            else:
                standard.append(d)
        return priority + standard

    def _candidate_root_devices(self, g: guestfs.GuestFS) -> list[str]:
        """
        Build candidate list for root filesystem detection.

        Uses native guestfs calls instead of shell commands to avoid
        dependencies on /bin/sh in minimal appliances.

        After LUKS open + mdraid assemble + LVM activation, new mountables appear.
        list_filesystems() often includes LV paths.
        """
        # Phase 1: Collect candidates from all sources
        candidates: list[str] = []
        candidates.extend(self._list_partition_candidates(g))
        candidates.extend(self._list_filesystem_candidates(g))
        candidates.extend(self._list_lvm_candidates(g))

        # Phase 2: Deduplicate
        candidates = self._deduplicate_candidates(candidates)

        # Phase 3: Filter out non-root devices and resolve by-path
        candidates = self._filter_non_root_devices(candidates)

        # Phase 4: Get current NBD info
        current_nbd, _current_nbd_parts, current_disk_lv = self._get_current_nbd_info(g)

        # Phase 5: Filter to current disk
        candidates = self._filter_to_current_disk(candidates, current_nbd, current_disk_lv)
        self.logger.info(f"Filtered to current disk: {len(candidates)} candidates")

        # Phase 6: Prioritize (LVM first)
        result = self._prioritize_candidates(candidates)
        self.logger.info(f"Candidate priority order: {result}")
        return result

    # Helper methods for mount_root_bruteforce (complexity reduction)

    def _validate_partition_devices(self, candidates: list[str]) -> tuple[list[str], list[dict[str, str]]]:
        """Validate that partition devices exist before attempting mount."""
        validated = []
        failures = []

        for dev in candidates:
            if os.path.exists(dev):
                validated.append(dev)
            else:
                self.logger.warning(f"⚠️ Device {dev} doesn't exist, skipping")
                failures.append({"device": dev, "error": "device_not_found"})

        return validated, failures

    def _try_xfs_mount_strategies(self, g: guestfs.GuestFS, dev: str) -> None:
        """Try XFS-specific mount recovery strategies."""
        # Strategy 1: Read-only with norecovery
        self.logger.info(f"XFS mount failed, retrying with ro,norecovery for {dev}")
        try:
            g.mount_options("ro,norecovery", dev, "/")
            self.logger.info(f"✓ Mount succeeded with ro,norecovery: {dev}")
            return
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as xfs_error:
            self.logger.debug(f"XFS recovery mount also failed: {xfs_error}")

        # Strategy 2: Try nouuid (common for cloned VMware VMs)
        self.logger.info(f"XFS mount failed, retrying with nouuid for {dev}")
        g.mount_options("nouuid", dev, "/")
        self.logger.info(f"✓ Mount succeeded with nouuid: {dev}")

    def _try_ext4_mount_strategies(self, g: guestfs.GuestFS, dev: str) -> None:
        """Try ext4-specific mount recovery strategies (fsck + remount)."""
        self.logger.info(f"Attempting fsck for ext4 partition {dev}")
        # Run fsck in non-interactive mode
        run_sudo(self.logger, ["fsck.ext4", "-p", "-f", dev], check=False, capture=True)
        # Retry mount after repair
        if self.dry_run:
            g.mount_ro(dev, "/")
        else:
            g.mount(dev, "/")
        self.logger.info(f"✓ Mount succeeded after fsck: {dev}")

    def _try_ntfs_mount_strategies(self, g: guestfs.GuestFS, dev: str) -> None:
        """Try NTFS-specific mount recovery strategies."""
        self.logger.info(f"NTFS mount failed, trying recovery strategies for {dev}")

        # Strategy 1: Force mount (removes dirty flag)
        try:
            self.logger.info(f"Trying NTFS force mount for {dev}")
            g.mount_options("force", dev, "/")
            self.logger.info(f"✓ Mount succeeded with force option: {dev}")
            return
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as force_error:
            self.logger.debug(f"NTFS force mount failed: {force_error}")

        # Strategy 2: Read-only mount
        try:
            self.logger.info(f"Trying NTFS read-only mount for {dev}")
            g.mount_ro(dev, "/")
            self.logger.info(f"✓ Mount succeeded in read-only mode: {dev}")
            return
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as ro_error:
            self.logger.debug(f"NTFS read-only mount failed: {ro_error}")

        # Strategy 3: ntfsfix repair then remount
        try:
            self.logger.info(f"Attempting ntfsfix repair for {dev}")
            run_sudo(self.logger, ["ntfsfix", "-d", dev], check=False, capture=True)
            g.mount_options("force", dev, "/")
            self.logger.info(f"✓ Mount succeeded after ntfsfix repair: {dev}")
            return
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as repair_error:
            self.logger.debug(f"NTFS repair and mount failed: {repair_error}")

        # Strategy 4: Case-sensitive mode (last resort)
        self.logger.info(f"Trying NTFS case-sensitive mount for {dev}")
        g.mount_options("windows=0,force", dev, "/")
        self.logger.info(f"✓ Mount succeeded with windows=0,force: {dev}")

    def _try_mount_with_recovery(self, g: guestfs.GuestFS, dev: str, vfs_type: str | None) -> None:
        """Try to mount device with filesystem-specific recovery strategies."""
        # Try normal mount first
        try:
            if self.dry_run:
                g.mount_ro(dev, "/")
            else:
                g.mount(dev, "/")
            return
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as mount_error:
            self.logger.debug(f"Mount failed for {dev} (type={vfs_type}): {mount_error}")

            # Try filesystem-specific recovery strategies
            if vfs_type == "xfs":
                self._try_xfs_mount_strategies(g, dev)
            elif vfs_type == "ext4":
                self._try_ext4_mount_strategies(g, dev)
            elif vfs_type == "ntfs":
                self._try_ntfs_mount_strategies(g, dev)
            else:
                raise

    def _discover_btrfs_subvolumes(self, dev: str) -> list[str]:
        """Discover btrfs subvolumes using host-side btrfs command."""
        discovered_subvols = []
        temp_mount = None

        try:
            # Create temporary mount point for btrfs inspection
            temp_mount = tempfile.mkdtemp(prefix="h2kvm-btrfs-")
            self.logger.debug(f"Created temp mount point: {temp_mount}")

            # Mount the btrfs filesystem on the host to list subvolumes
            self.logger.debug(f"Mounting {dev} at {temp_mount} with subvolid=5")
            run_sudo(
                self.logger, ["mount", "-o", "ro,subvolid=5", dev, temp_mount], check=True, capture=True
            )
            self.logger.debug("Mount successful, listing subvolumes")

            # List subvolumes using host btrfs command
            result = run_sudo(
                self.logger, ["btrfs", "subvolume", "list", temp_mount], check=True, capture=True
            )

            output = U.to_text(result.stdout).strip()
            self.logger.debug(f"Btrfs subvolume list output: {output[:200]}")

            # Parse output like: "ID 256 gen 7 top level 5 path @"
            for line in output.splitlines():
                parts = line.split()
                if "path" in parts:
                    idx = parts.index("path")
                    if idx + 1 < len(parts):
                        subvol = parts[idx + 1]
                        discovered_subvols.append(subvol)
                        self.logger.debug(f"Found subvolume: {subvol}")

            self.logger.info(
                f"✅ Discovered {len(discovered_subvols)} btrfs subvolumes: {discovered_subvols}"
            )

        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as e:
            self.logger.warning(f"Could not discover btrfs subvolumes on {dev}: {e}")
        finally:
            # Unmount and cleanup
            if temp_mount:
                try:
                    run_sudo(self.logger, ["umount", temp_mount], check=False, capture=True)
                    Path(temp_mount).rmdir()
                    self.logger.debug(f"Cleaned up temp mount: {temp_mount}")
                # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                except Exception as cleanup_error:
                    self.logger.debug(f"Cleanup warning: {cleanup_error}")

        return discovered_subvols

    def _find_best_root_device(
        self, g: guestfs.GuestFS, candidates: list[str]
    ) -> tuple[tuple[int, str | None], list[dict[str, str]]]:
        """Find best root device by trying mounts and scoring."""
        best: tuple[int, str | None] = (-(10**9), None)
        mount_failures = []

        for dev in candidates:
            self._safe_umount_all(g)
            try:
                # Get filesystem type
                vfs_type = None
                try:
                    # pylint: disable=protected-access  # tight coupling with sibling fixer/backend internals in this package
                    vfs_type = filesystem_fixer._vfs_type(g, dev)
                    self.logger.debug(f"Device {dev} has filesystem type: {vfs_type}")
                # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                except Exception as e:
                    self.logger.debug(f"Could not determine vfs_type for {dev}: {e}")

                filesystem_fixer.log_vfs_type_best_effort(self, g, dev)

                # Skip non-mountable device types
                if vfs_type in ("LVM2_member", "swap"):
                    self.logger.debug(f"Skipping non-mountable device: {dev} (type={vfs_type})")
                    continue

                self.logger.info(f"🔄 Attempting to mount {dev} at /...")

                # Try mount with recovery strategies
                self._try_mount_with_recovery(g, dev, vfs_type)

                self.logger.info(f"✓ Mount succeeded for {dev}, checking if it looks like root...")

                # Check if it looks like root
                if self._looks_like_root(g):
                    sc = self._score_root(g)
                    self.logger.info(f"✓ {dev} looks like root (score={sc})")
                    if sc > best[0]:
                        best = (sc, dev)
                else:
                    self.logger.info(f"✗ {dev} doesn't look like root filesystem")

                self._safe_umount_all(g)
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception as e:
                self.logger.debug(f"Mount failed for {dev}: {e}")
                mount_failures.append({"device": dev, "error": str(e)})
                continue

        return best, mount_failures

    def _find_best_btrfs_subvolume(
        self, g: guestfs.GuestFS, candidates: list[str]
    ) -> tuple[tuple[int, str | None, str | None], list[dict[str, str]]]:
        """Find best btrfs subvolume by trying mounts and scoring."""
        best_btrfs: tuple[int, str | None, str | None] = (-(10**9), None, None)
        mount_failures = []

        for dev in candidates:
            # Check filesystem type
            try:
                # pylint: disable=protected-access  # tight coupling with sibling fixer/backend internals in this package
                vfs_type = filesystem_fixer._vfs_type(g, dev)
                self.logger.debug(f"Btrfs check: {dev} has vfs_type={vfs_type}")
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception:
                vfs_type = "unknown"

            # Skip non-btrfs filesystems
            if vfs_type != "btrfs":
                self.logger.debug(f"Skipping {dev} for btrfs subvolumes (type={vfs_type})")
                continue

            self.logger.info(f"Discovering btrfs subvolumes on {dev}")

            # Discover subvolumes
            discovered_subvols = self._discover_btrfs_subvolumes(dev)

            # Combine discovered and common subvolumes
            subvols_to_try = discovered_subvols if discovered_subvols else self._BTRFS_COMMON_SUBVOLS
            if discovered_subvols:
                for common in self._BTRFS_COMMON_SUBVOLS:
                    if common not in subvols_to_try:
                        subvols_to_try.append(common)

            self.logger.info(f"Trying {len(subvols_to_try)} btrfs subvolumes on {dev}")
            for sv in subvols_to_try:
                self._safe_umount_all(g)
                try:
                    filesystem_fixer.log_vfs_type_best_effort(self, g, dev)
                    opts = f"subvol={sv}"
                    if self.dry_run:
                        opts = f"ro,{opts}"
                    g.mount_options(opts, dev, "/")

                    if self._looks_like_root(g):
                        sc = self._score_root(g)
                        self.logger.info(f"✓ {dev} subvol={sv} looks like root (score={sc})")
                        if sc > best_btrfs[0]:
                            best_btrfs = (sc, dev, sv)
                    else:
                        self.logger.debug(f"✗ {dev} subvol={sv} doesn't look like root")

                    self._safe_umount_all(g)
                # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                except Exception as e:
                    mount_failures.append({"device": f"{dev} subvol={sv}", "error": str(e)})
                    continue

        return best_btrfs, mount_failures

    def _detect_boot_disk_index(self, g: guestfs.GuestFS, root: str) -> int | None:
        """Detect which disk contains the boot root for multi-disk guests.

        For non-Linux guests (e.g. Windows with multiple OS installations on
        different disks), uses the inspected root partition to determine which
        disk should get boot order=1 in the output libvirt XML.

        Returns the 0-based disk index, or None if detection fails.
        """
        try:
            os_type = U.to_text(g.inspect_get_type(root)).lower()
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception:
            os_type = "unknown"

        # For Linux, GRUB detection in the bootloader fixer handles boot order.
        # This path is specifically for non-Linux guests.
        if os_type == "linux":
            return None

        try:
            parent_disk = g.part_to_dev(root)
            disk_index = g.device_index(parent_disk)
            if disk_index > 0:
                self.logger.info(
                    f"Multi-disk boot detection: root {root} is on disk {parent_disk} (index {disk_index})"
                )
            return disk_index
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as e:
            self.logger.debug(f"Boot disk index detection failed for {root}: {e}")
            return None

    # pylint: disable=too-many-locals,too-many-branches,too-many-statements  # VM fixer step handles many device/filesystem-specific cases
    def mount_root_bruteforce(self, g: guestfs.GuestFS) -> None:
        """
        Attempt to mount root filesystem by trying all candidates.

        Uses a multi-phase approach:
        1. Validate devices exist
        2. Try normal mounts with filesystem-specific recovery
        3. Try btrfs subvolumes if no root found
        """
        candidates = self._candidate_root_devices(g)
        if not candidates:
            U.die(self.logger, "Failed to list partitions/filesystems for brute-force mount.", 1)

        # Validate partition devices exist
        candidates, mount_failures = self._validate_partition_devices(candidates)
        if not candidates:
            U.die(self.logger, "No valid partition devices found.", 1)

        self.logger.info(f"Validated {len(candidates)} candidate devices")

        # Give a brief pause for devices to settle
        time.sleep(0.3)

        # Phase 1: Try normal mounts and find best root device
        best, new_failures = self._find_best_root_device(g, candidates)
        mount_failures.extend(new_failures)

        # Phase 2: If we found a best device, mount it and return
        if best[1]:
            dev = best[1]
            self._safe_umount_all(g)
            try:
                # Get filesystem type for proper mounting
                vfs_type = None
                with contextlib.suppress(Exception):
                    # pylint: disable=protected-access  # tight coupling with sibling fixer/backend internals in this package
                    vfs_type = filesystem_fixer._vfs_type(g, dev)

                # Try mount with appropriate options (including XFS nouuid for cloned VMs)
                mounted = False
                try:
                    if self.dry_run:
                        g.mount_ro(dev, "/")
                    else:
                        g.mount(dev, "/")
                    mounted = True
                # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                except Exception as mount_error:
                    # Apply same XFS recovery strategies as during detection
                    if vfs_type == "xfs":
                        self.logger.info(f"Retrying root mount with XFS recovery options for {dev}")
                        try:
                            g.mount_options("ro,norecovery", dev, "/")
                            mounted = True
                        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                        except Exception:
                            try:
                                g.mount_options("nouuid", dev, "/")
                                mounted = True
                                self.logger.info("Root mounted with nouuid option")
                            except Exception as nouuid_error:
                                raise mount_error from nouuid_error
                    else:
                        raise

                if mounted:
                    self.root_dev = dev
                    # Store the filesystem type for is_windows() detection
                    if vfs_type:
                        self.root_fstype = vfs_type
                    self.logger.info(
                        f"✅ Mounted root filesystem: {dev} (score={best[0]}, fstype={vfs_type})"
                    )
                    if mount_failures:
                        try:
                            self.report.setdefault("analysis", {}).setdefault("mount", {})[
                                "bruteforce_failures"
                            ] = mount_failures
                        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                        except Exception as e:
                            self.logger.debug(f"Failed to store mount failures in report: {e}")
                    return
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception as e:
                mount_failures.append({"device": dev, "error": f"best_root_mount_failed:{e}"})

        # Phase 3: If no root found, try btrfs subvolumes
        if not best[1]:
            self.logger.warning(
                "No candidate devices passed _looks_like_root check. Trying btrfs subvolumes..."
            )
            best_btrfs, btrfs_failures = self._find_best_btrfs_subvolume(g, candidates)
            mount_failures.extend(btrfs_failures)
        else:
            best_btrfs: tuple[int, str | None, str | None] = (-(10**9), None, None)

        # Phase 4: Mount best btrfs subvolume if found
        if best_btrfs[1] and best_btrfs[2]:
            dev = best_btrfs[1]
            sv = best_btrfs[2]
            self._safe_umount_all(g)
            try:
                filesystem_fixer.log_vfs_type_best_effort(self, g, dev)
                opts = f"subvol={sv}"
                if self.dry_run:
                    opts = f"ro, {opts}"
                g.mount_options(opts, dev, "/")
                self.root_dev = dev
                self.root_btrfs_subvol = sv
                self.logger.info(
                    f"Fallback btrfs root detected at {dev} (subvol={sv}, score={best_btrfs[0]})"
                )
                if mount_failures:
                    try:
                        self.report.setdefault("analysis", {}).setdefault("mount", {})[
                            "bruteforce_failures"
                        ] = mount_failures
                    # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                    except Exception as e:
                        self.logger.debug(f"Failed to store mount failures in report: {e}")
                return
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception as e:
                mount_failures.append(
                    {"device": f"{dev} subvol={sv}", "error": f"best_btrfs_mount_failed:{e}"}
                )

        # stash failures before dying
        if mount_failures:
            try:
                self.report.setdefault("analysis", {}).setdefault("mount", {})["bruteforce_failures"] = (
                    mount_failures
                )
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception as e:
                self.logger.debug(f"Failed to store mount failures in report: {e}")

        # Check if BitLocker was detected — provide actionable message
        bitlocker_hint = ""
        for fail in mount_failures:
            if "BitLocker" in fail.get("error", "") or "bitlocker" in fail.get("error", "").lower():
                bitlocker_hint = (
                    " BitLocker encryption detected — disable BitLocker in the guest VM before migration."
                )
                break
        U.die(self.logger, f"Failed to mount root filesystem.{bitlocker_hint}", 1)

    # normalize validation results (bool/dict compatibility)
    @staticmethod
    def _normalize_validation_results(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Delegate to validation manager."""
        return OfflineValidationManager.normalize_validation_results(raw)

    @staticmethod
    def _summarize_validation(norm: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """Delegate to validation manager."""
        return OfflineValidationManager.summarize_validation(norm)

    # Configuration rewriting (delegated to modules)
    def backup_file(self, g: guestfs.GuestFS, path: str) -> None:
        """Delegate to config rewriter."""
        self._config_rewriter.backup_file(g, path)

    def convert_spec(self, g: guestfs.GuestFS, spec: str) -> tuple[str, str]:
        """Delegate to spec converter."""
        # Update root_dev in spec_converter if it's been detected
        if self.root_dev and self._spec_converter.root_dev != self.root_dev:
            self._spec_converter.root_dev = self.root_dev
        return self._spec_converter.convert_spec(g, spec)

    def rewrite_fstab(self, g: guestfs.GuestFS) -> tuple[int, list[Change], dict[str, Any]]:
        """Delegate to config rewriter."""
        return self._config_rewriter.rewrite_fstab(g)

    def rewrite_crypttab(self, g: guestfs.GuestFS) -> int:
        """Delegate to config rewriter."""
        return self._config_rewriter.rewrite_crypttab(g)

    # Filesystem fixer (delegated)
    def fix_filesystems(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Delegate to the filesystem fixer module."""
        return filesystem_fixer.fix_filesystems(self, g)

    # Delegated fixers (explicit wrappers; no monkey-patching)
    def fix_network_config(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Delegate to the network fixer module."""
        return network_fixer.fix_network_config(self, g)

    def remove_stale_device_map(self, g: guestfs.GuestFS) -> int:
        """Delegate to the grub fixer module."""
        return grub_fixer.remove_stale_device_map(self, g)

    def update_grub_root(self, g: guestfs.GuestFS) -> int:
        """Delegate to the grub fixer module."""
        return grub_fixer.update_grub_root(self, g)

    def regen(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Delegate to the grub fixer module."""
        return grub_fixer.regen(self, g)

    # Windows delegation
    def is_windows(self, g: guestfs.GuestFS) -> bool:
        """Detect whether the mounted guest is Windows, trying several fallback heuristics."""
        # Try the standard detection first (requires inspect_root for libguestfs)
        try:
            if windows_fixer.is_windows(self, g):
                return True
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as e:
            self.logger.debug("windows_fixer.is_windows failed: %s", e)

        # Fastest check: root_fstype was set during mount detection
        # (log_vfs_type_best_effort stores it on self before mount)
        if getattr(self, "root_fstype", None) and self.root_fstype.lower() == "ntfs":
            self.logger.info("Windows detected via cached root_fstype=ntfs")
            return True

        # Fallback: direct filesystem check for VMCraft backend
        for win_dir in ("/Windows", "/WINDOWS", "/winnt", "/WINNT"):
            try:
                if g.is_dir(win_dir):
                    self.logger.info("Windows detected via dir check: %s", win_dir)
                    return True
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception as e:
                self.logger.debug("is_dir(%s) failed: %s", win_dir, e)
                continue

        # Check via ls("/") for Windows-like directory names
        try:
            root_entries = g.ls("/")
            for entry in root_entries:
                if entry.lower() in ("windows", "program files", "users", "programdata"):
                    self.logger.info("Windows detected via ls(/): found %s", entry)
                    return True
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as e:
            self.logger.debug("ls(/) failed: %s", e)
        return False

    def windows_bcd_actual_fix(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Delegate to the Windows fixer module."""
        return windows_fixer.windows_bcd_actual_fix(self, g)

    def inject_virtio_drivers(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Delegate to the Windows fixer module."""
        return windows_fixer.inject_virtio_drivers(self, g)

    def retain_windows_network_config(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Delegate to the Windows fixer module."""
        return windows_fixer.retain_windows_network_config(self, g)

    def stage_route_cleanup(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Delegate to the Windows fixer module."""
        return windows_fixer.stage_route_cleanup(self, g)

    def stage_disk_online(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Delegate to the Windows fixer module."""
        return windows_fixer.stage_disk_online(self, g)

    # VMware tools removal (mounted tree remover)
    def _mount_local_run_threaded(
        self,
        g: guestfs.GuestFS,
        mountpoint: Path,
        *,
        ready_timeout_s: float = 15.0,
    ) -> tuple[bool, str | None, threading.Thread | None, list[str]]:
        """
        guestfs.mount_local_run() is a blocking FUSE loop.
        Pattern:
          - mount_local(mountpoint)
          - start background thread calling mount_local_run()
          - do host-side file operations against mountpoint
          - umount_local() to stop

        Returns any mount_local_run() exceptions collected in the background thread.
        """
        err: list[str] = []

        try:
            g.mount_local(str(mountpoint))
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as e:
            return False, f"mount_local_failed:{e}", None, err

        def _runner() -> None:
            try:
                g.mount_local_run()
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception as e:
                err.append(str(e))

        t = threading.Thread(target=_runner, name="guestfs-mount-local-run", daemon=True)
        t.start()

        deadline = time.time() + ready_timeout_s
        while time.time() < deadline:
            try:
                if mountpoint.exists():
                    _ = list(mountpoint.iterdir())
                    return True, None, t, err
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception:
                pass
            time.sleep(0.1)

        with contextlib.suppress(Exception):
            g.umount_local()
        return False, "mount_local_ready_timeout", t, err

    def remove_vmware_tools_func(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """
        Exposes the mounted guest filesystem via mount_local + background mount_local_run(),
        then runs OfflineVmwareToolsRemover against that host-visible tree.

        Always attempts umount_local() + cleanup.
        """
        if not self.remove_vmware_tools:
            return {"enabled": False}

        U.banner(self.logger, "VMware tools removal (OFFLINE)")
        res = VmwareRemovalResult(enabled=True)

        if self.dry_run:
            res.notes.append("dry_run: remover will only log; no changes written")
        if self.no_backup:
            res.notes.append("no_backup: remover will not create .bak copies")
        if not self.root_dev:
            res.errors.append("root_not_mounted")
            return res.as_dict()

        mnt = Path(tempfile.mkdtemp(prefix="h2kvm.guestfs.mnt."))
        mounted_local = False
        t: threading.Thread | None = None
        thread_errs: list[str] = []

        try:
            ok, why, t, thread_errs = self._mount_local_run_threaded(g, mnt)
            if not ok:
                res.errors.append(why or "mount_local_failed")
                if thread_errs:
                    res.warnings.append(f"mount_local_run_errors:{thread_errs[:3]}")
                return res.as_dict()
            mounted_local = True

            remover = OfflineVmwareToolsRemover(
                logger=self.logger,
                mount_point=mnt,
                dry_run=self.dry_run,
                no_backup=self.no_backup,
            )
            rr = remover.run()

            res.removed_paths = rr.removed_paths
            res.removed_services = rr.removed_services
            res.removed_symlinks = rr.removed_symlinks
            res.package_hints = rr.package_hints
            res.touched_files = rr.touched_files
            res.errors = rr.errors
            if getattr(rr, "warnings", None):
                res.warnings.extend(rr.warnings)

            if thread_errs:
                res.warnings.append(f"mount_local_run_errors:{thread_errs[:5]}")

            return res.as_dict()

        finally:
            if mounted_local:
                with contextlib.suppress(Exception):
                    g.umount_local()
            if t:
                t.join(timeout=3.0)
                if t.is_alive():
                    res.warnings.append("mount_local_thread_still_alive_after_join")
            with contextlib.suppress(Exception):
                shutil.rmtree(str(mnt), ignore_errors=True)

    # disk usage analysis
    def analyze_disk_space(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Delegate to validation manager."""
        return self._validation_manager.analyze_disk_space(g)

    def create_validation_suite(self, g: guestfs.GuestFS) -> ValidationSuite:
        """Delegate to validation manager."""
        return self._validation_manager.create_validation_suite(g)

    # resizing (image-level)
    def _resize_image_container(self) -> dict[str, Any] | None:
        """Resize image container (delegates to OfflineUtilities)."""
        return self._utilities.resize_image_container(self.image, self.resize, self.dry_run)

    # report writer
    def write_report(self) -> None:
        """Delegate to the report writer module."""
        write_report(self)

    # systemd boot integration
    # Helper methods for apply_systemd_boot_integration (complexity reduction)

    def _setup_machine_id(self, g: guestfs.GuestFS) -> tuple[dict[str, str], list[str]]:
        """Setup machine ID if not present."""
        features = {}
        errors = []
        try:
            machine_id_exists = g.is_file("/etc/machine-id") and g.filesize("/etc/machine-id") > 0
            if not machine_id_exists:
                # pylint: disable=import-outside-toplevel  # lazy import: optional dependency or avoids a circular import
                import uuid

                new_machine_id = uuid.uuid4().hex
                g.write("/etc/machine-id", f"{new_machine_id}\n")
                features["machine_id"] = "created"
                self.logger.info(f"✓ Created machine ID: {new_machine_id}")
            else:
                features["machine_id"] = "already_exists"
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as e:
            self.logger.debug(f"Machine ID setup failed: {e}")
            errors.append(f"machine_id: {e}")
        return features, errors

    def _configure_auto_grow(self, g: guestfs.GuestFS, root_fstype) -> tuple[dict[str, str], list[str]]:
        """Configure auto-grow for root filesystem."""
        features = {}
        errors = []
        try:
            # pylint: disable=import-outside-toplevel  # lazy import: optional dependency or avoids a circular import
            from h2kvm.infrastructure.systemd.boot import FilesystemType

            if root_fstype in [FilesystemType.EXT4, FilesystemType.XFS, FilesystemType.BTRFS]:
                dropin_dir = "/etc/systemd/system/-.mount.d"
                if not g.is_dir(dropin_dir):
                    g.mkdir_p(dropin_dir)

                growfs_conf = f"{dropin_dir}/growfs.conf"
                growfs_content = """[Mount]
# Automatically grow filesystem to partition size at boot
Options=x-systemd.growfs
"""
                g.write(growfs_conf, growfs_content)
                features["auto_grow"] = "configured"
                self.logger.info(f"✓ Configured auto-grow for root filesystem ({root_fstype.value})")
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as e:
            self.logger.debug(f"Auto-grow configuration failed: {e}")
            errors.append(f"auto_grow: {e}")
        return features, errors

    def _configure_tmpfiles(self, g: guestfs.GuestFS) -> tuple[dict[str, str], list[str]]:
        """Create VM-specific tmpfiles configuration."""
        features = {}
        errors = []
        try:
            tmpfiles_dir = "/etc/tmpfiles.d"
            if not g.is_dir(tmpfiles_dir):
                g.mkdir_p(tmpfiles_dir)

            tmpfiles_conf = f"{tmpfiles_dir}/h2kvm.conf"
            tmpfiles_content = """# h2kvm tmpfiles configuration
d /var/lib/h2kvm 0755 root root -
d /var/log/h2kvm 0755 root root -
d /run/h2kvm 0755 root root -
"""
            g.write(tmpfiles_conf, tmpfiles_content)
            features["tmpfiles"] = "configured"
            self.logger.info("✓ Created h2kvm tmpfiles configuration")
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as e:
            self.logger.debug(f"Tmpfiles configuration failed: {e}")
            errors.append(f"tmpfiles: {e}")
        return features, errors

    def _configure_recovery_mode(self, g: guestfs.GuestFS) -> tuple[dict[str, str], list[str]]:
        """Configure recovery mode (rescue target drop-in)."""
        features = {}
        errors = []
        try:
            rescue_dropin_dir = "/etc/systemd/system/rescue.target.d"
            if not g.is_dir(rescue_dropin_dir):
                g.mkdir_p(rescue_dropin_dir)

            rescue_conf = f"{rescue_dropin_dir}/vm-recovery.conf"
            rescue_content = """[Unit]
Description=VM Recovery Mode
# Additional recovery services
Wants=systemd-fsck-root.service
After=systemd-fsck-root.service
"""
            g.write(rescue_conf, rescue_content)
            features["recovery"] = "configured"
            self.logger.info("✓ Configured VM recovery mode")
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as e:
            self.logger.debug(f"Recovery mode configuration failed: {e}")
            errors.append(f"recovery: {e}")
        return features, errors

    # pylint: disable=too-many-locals,too-many-branches,too-many-statements  # VM fixer step handles many device/filesystem-specific cases
    def _apply_rhel_boot_repair(
        self, g: guestfs.GuestFS
    ) -> tuple[dict[str, Any], dict[str, str], list[str]]:
        """Apply RHEL/CentOS boot repair fixes."""
        rhel_result = {}
        features = {}
        errors = []

        # pylint: disable=too-many-nested-blocks  # VM fixer step handles many device/filesystem-specific cases
        try:
            # Detect RHEL version
            rhel_version = None
            try:
                if g.is_file("/etc/os-release"):
                    os_release = g.read_file("/etc/os-release").decode("utf-8")
                    for line in os_release.split("\n"):
                        if line.startswith("VERSION_ID="):
                            rhel_version = int(line.split("=")[1].strip('"').split(".")[0])
                            break
            except (RuntimeError, UnicodeDecodeError, ValueError) as e:
                self.logger.debug(f"Could not detect RHEL version from /etc/os-release: {e}")

            if not rhel_version:
                rhel_result = {"skipped": "not_rhel_centos"}
                return rhel_result, features, errors

            rhel_issues = []
            rhel_fixes = []

            # Check 1: LVM filter
            if g.is_file("/etc/lvm/lvm.conf"):
                lvm_conf_content = g.read_file("/etc/lvm/lvm.conf").decode("utf-8")
                if "filter =" in lvm_conf_content and "a/.*/" not in lvm_conf_content:
                    rhel_issues.append({"component": "lvm_filter", "severity": "critical"})
                    # pylint: disable=import-outside-toplevel  # lazy import: optional dependency or avoids a circular import
                    import re

                    new_content = re.sub(
                        r"(filter\s*=\s*\[)[^]]*(\])", r'\1 "a/.*/", "r|.*|" \2', lvm_conf_content
                    )
                    g.write("/etc/lvm/lvm.conf", new_content)
                    rhel_fixes.append("lvm_filter")
                    self.logger.info("✓ Fixed restrictive LVM filter")

            # Check 2: LVM devices file (RHEL 9+)
            if rhel_version >= 9 and g.is_file("/etc/lvm/devices/system.devices"):
                rhel_issues.append({"component": "lvm_devices_file", "severity": "high"})
                g.rm("/etc/lvm/devices/system.devices")
                rhel_fixes.append("lvm_devices_file")
                self.logger.info("✓ Removed LVM devices file (RHEL 9+)")

            # Check 3: nsswitch.conf group ordering
            if g.is_file("/etc/nsswitch.conf"):
                nsswitch_content = g.read_file("/etc/nsswitch.conf").decode("utf-8")
                lines = nsswitch_content.split("\n")
                modified = False
                for i, line in enumerate(lines):
                    if line.strip().startswith("group:"):
                        parts = line.split(":")
                        if len(parts) >= 2:
                            sources = parts[1].strip().split()
                            if sources and sources[0] != "files" and "files" in sources:
                                rhel_issues.append({"component": "nsswitch_group", "severity": "medium"})
                                sources.remove("files")
                                sources.insert(0, "files")
                                lines[i] = f"group: {' '.join(sources)}"
                                modified = True
                                break
                if modified:
                    g.write("/etc/nsswitch.conf", "\n".join(lines))
                    rhel_fixes.append("nsswitch_group")
                    self.logger.info("✓ Fixed nsswitch.conf group ordering")

            # Check 4: systemd default.target
            if not g.is_file("/etc/systemd/system/default.target") and not g.is_symlink(
                "/etc/systemd/system/default.target"
            ):
                rhel_issues.append({"component": "systemd_default_target", "severity": "low"})
                multi_user = "/usr/lib/systemd/system/multi-user.target"
                if not g.is_file(multi_user):
                    multi_user = "/lib/systemd/system/multi-user.target"
                if g.is_file(multi_user):
                    g.ln_s(multi_user, "/etc/systemd/system/default.target")
                    rhel_fixes.append("systemd_default_target")
                    self.logger.info("✓ Created systemd default.target symlink")

            # Store results
            rhel_result = {
                "rhel_version": rhel_version,
                "issues_detected": len(rhel_issues),
                "fixes_applied": len(rhel_fixes),
                "issues": rhel_issues,
                "fixes": rhel_fixes,
            }

            if rhel_fixes:
                features["rhel_boot_repair"] = f"{len(rhel_fixes)} fixes"
                self.logger.info(f"✅ RHEL boot repair: {len(rhel_fixes)} critical fixes applied")
            elif rhel_issues:
                self.logger.info(
                    f"ℹ️  RHEL boot repair: {len(rhel_issues)} issues detected (no auto-fix applied)"
                )

        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as e:
            self.logger.debug(f"RHEL boot repair failed: {e}")
            rhel_result = {"error": str(e), "issues_detected": 0, "fixes_applied": 0}
            errors.append(f"rhel_boot_repair: {e}")

        return rhel_result, features, errors

    # pylint: disable=too-many-branches,too-many-statements  # VM fixer step handles many device/filesystem-specific cases
    def _apply_firstboot_integration(
        self, g: guestfs.GuestFS
    ) -> tuple[dict[str, Any], dict[str, str], list[str]]:
        """
        Apply systemd firstboot integration using direct guestfs file writes.

        Writes the generator, service unit, firstboot script, and conversion
        markers directly via g.write/g.mkdir_p/g.chmod -- works with all
        backends without needing mount_local FUSE.
        """
        firstboot_result: dict[str, Any] = {
            "generator_created": False,
            "service_created": False,
            "script_created": False,
            "marked_for_firstboot": False,
            "errors": [],
        }
        features: dict[str, str] = {}
        errors: list[str] = []

        try:
            # pylint: disable=import-outside-toplevel  # lazy import: optional dependency or avoids a circular import
            from h2kvm.infrastructure.systemd.firstboot import (
                FirstbootConfig,
                generate_enterprise_firstboot_script,
            )

            firstboot_config = FirstbootConfig(
                regenerate_machine_id=True,
                regenerate_initramfs=True,
                regenerate_grub=True,
                reinstall_grub=True,
                activate_lvm=True,
                settle_udev=True,
                trigger_hardware_detection=True,
                install_qemu_guest_agent=True,
                regenerate_network=True,
                remove_persistent_net_rules=True,
                reconfigure_network_manager=True,
                regenerate_ssh_keys=True,
                apply_virtual_guest_tuning=True,
                enable_cloud_init=False,
                verify_boot_health=True,
                create_conversion_metadata=True,
                custom_commands=None,
            )

            # 1) Generator
            try:
                generator_dir = "/usr/lib/systemd/system-generators"
                if not g.is_dir(generator_dir):
                    g.mkdir_p(generator_dir)
                generator_content = self._firstboot_generator_script()
                g.write(f"{generator_dir}/h2kvm-generator", generator_content)
                g.chmod(0o755, f"{generator_dir}/h2kvm-generator")
                firstboot_result["generator_created"] = True
                self.logger.info("Created systemd generator: h2kvm-generator")
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception as e:
                firstboot_result["errors"].append(f"generator: {e}")
                self.logger.debug(f"Failed to create generator: {e}")

            # 2) Service unit
            try:
                service_dir = "/usr/lib/systemd/system"
                if not g.is_dir(service_dir):
                    g.mkdir_p(service_dir)
                service_content = self._firstboot_service_unit()
                g.write(f"{service_dir}/h2kvm-firstboot.service", service_content)
                g.chmod(0o644, f"{service_dir}/h2kvm-firstboot.service")
                firstboot_result["service_created"] = True
                self.logger.info("Created firstboot service: h2kvm-firstboot.service")
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception as e:
                firstboot_result["errors"].append(f"service: {e}")
                self.logger.debug(f"Failed to create service: {e}")

            # 3) Firstboot script
            try:
                libexec_dir = "/usr/libexec"
                if not g.is_dir(libexec_dir):
                    g.mkdir_p(libexec_dir)
                script_content = generate_enterprise_firstboot_script(firstboot_config)
                g.write(f"{libexec_dir}/h2kvm-firstboot", script_content)
                g.chmod(0o755, f"{libexec_dir}/h2kvm-firstboot")
                firstboot_result["script_created"] = True
                self.logger.info("Created firstboot script: h2kvm-firstboot")
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception as e:
                firstboot_result["errors"].append(f"script: {e}")
                self.logger.debug(f"Failed to create script: {e}")

            # 4) Mark for firstboot (conversion flag + machine-id reset)
            try:
                if not g.is_dir("/etc/h2kvm"):
                    g.mkdir_p("/etc/h2kvm")
                g.write("/etc/h2kvm/converted", "Converted by H2KVM\n")

                if g.is_file("/etc/machine-id"):
                    g.write("/etc/machine-id", "")
                    self.logger.info("Reset machine-id for firstboot regeneration")

                with contextlib.suppress(Exception):
                    if g.is_file("/var/lib/dbus/machine-id"):
                        g.rm("/var/lib/dbus/machine-id")

                firstboot_result["marked_for_firstboot"] = True
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception as e:
                firstboot_result["errors"].append(f"mark_firstboot: {e}")
                self.logger.debug(f"Failed to mark for firstboot: {e}")

            if firstboot_result["generator_created"] and firstboot_result["service_created"]:
                features["firstboot_integration"] = "installed"
                self.logger.info("Systemd firstboot integration installed")
                self.logger.info("   Journal will show firstboot initialization on next boot")

        except ImportError:
            firstboot_result = {"skipped": "firstboot_module_not_available"}
            self.logger.debug("Systemd firstboot module not available")
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as e:
            self.logger.debug(f"Firstboot integration failed: {e}")
            firstboot_result = {"error": str(e), "components_installed": False}
            errors.append(f"firstboot_integration: {e}")

        return firstboot_result, features, errors

    @staticmethod
    def _firstboot_generator_script() -> str:
        """Return the systemd generator script content."""
        return '''#!/usr/bin/env python3
"""H2KVM systemd generator - enables firstboot service if conversion detected"""
import os, sys

def main():
    if not os.path.exists("/etc/h2kvm/converted"):
        sys.exit(0)
    wants_dir = os.path.join("/run/systemd/system", "multi-user.target.wants")
    os.makedirs(wants_dir, exist_ok=True)
    symlink = os.path.join(wants_dir, "h2kvm-firstboot.service")
    if not os.path.exists(symlink):
        try:
            os.symlink("/usr/lib/systemd/system/h2kvm-firstboot.service", symlink)
        except FileExistsError:
            pass

if __name__ == "__main__":
    main()
'''

    @staticmethod
    def _firstboot_service_unit() -> str:
        """Return the systemd firstboot service unit content."""
        return """\
[Unit]
Description=H2KVM First Boot Initialization
DefaultDependencies=no
After=local-fs.target systemd-remount-fs.service
Before=multi-user.target network-pre.target
Wants=local-fs.target
ConditionPathExists=/etc/h2kvm/converted
ConditionFirstBoot=yes

[Service]
Type=oneshot
ExecStart=/usr/libexec/h2kvm-firstboot
RemainAfterExit=yes
StandardOutput=journal
StandardError=journal
SyslogIdentifier=h2kvm-firstboot

[Install]
WantedBy=multi-user.target
"""

    # pylint: disable=too-many-locals,too-many-branches,too-many-statements  # VM fixer step handles many device/filesystem-specific cases
    def apply_systemd_boot_integration(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """
        Apply systemd boot integration features for optimized VM boot.

        Integrates systemd-based boot tools including:
        - Machine ID setup
        - Auto-grow filesystem configuration
        - Boot environment verification
        - Recovery mode setup
        - RHEL/CentOS boot repair (LVM, udev, etc.)

        Args:
            g: Mounted guestfs instance

        Returns:
            Integration results dictionary
        """
        result: dict[str, Any] = {
            "enabled": False,
            "applied": False,
            "features": {},
            "rhel_boot_repair": {},
            "errors": [],
        }

        try:
            # Check if systemd integration is available
            try:
                # pylint: disable=import-outside-toplevel  # lazy import: optional dependency or avoids a circular import
                from h2kvm.infrastructure.systemd.boot import (
                    BootEnvironment,
                    BootType,
                    FilesystemType,
                )

                result["enabled"] = True
            except ImportError as e:
                result["skipped"] = "systemd_integration_not_available"
                result["import_error"] = str(e)
                self.logger.debug(f"Systemd integration not available: {e}")
                return result

            # Only apply for Linux guests
            if self.is_windows(g):
                result["skipped"] = "windows_guest"
                return result

            # Get root mount point from guestfs
            root_mount = None
            try:
                mounts = g.mounts()
                if mounts and len(mounts) > 0:
                    # Find the root mount (usually first mount or explicitly "/")
                    for mount_info in g.inspect_get_mountpoints(self.inspect_root or "/dev/sda1"):
                        if mount_info[0] == "/":
                            root_mount = mount_info[1]
                            break
                    if not root_mount and mounts:
                        root_mount = mounts[0]
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception as e:
                self.logger.debug(f"Could not determine root mount: {e}")
                root_mount = self.root_dev

            if not root_mount:
                result["skipped"] = "no_root_mount"
                return result

            # Detect boot type (UEFI vs BIOS)
            boot_type = BootType.UNKNOWN
            try:
                if g.is_dir("/sys/firmware/efi"):
                    boot_type = BootType.UEFI
                elif g.is_file("/boot/grub/grub.cfg") or g.is_file("/boot/grub2/grub.cfg"):
                    boot_type = BootType.BIOS
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception:
                boot_type = BootType.UEFI  # Default to UEFI for modern VMs

            # Detect filesystem type
            root_fstype = FilesystemType.EXT4  # Default
            try:
                fstype_output = g.vfs_type(root_mount)
                if "xfs" in fstype_output.lower():
                    root_fstype = FilesystemType.XFS
                elif "btrfs" in fstype_output.lower():
                    root_fstype = FilesystemType.BTRFS
                elif "ext4" in fstype_output.lower() or "ext3" in fstype_output.lower():
                    root_fstype = FilesystemType.EXT4
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception as e:
                self.logger.debug(f"Could not detect filesystem type: {e}")

            # Get hostname if available
            hostname = None
            try:
                if g.is_file("/etc/hostname"):
                    hostname = g.read_file("/etc/hostname").decode("utf-8").strip()
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception:
                pass

            # Create boot environment
            BootEnvironment(
                boot_type=boot_type, root_device=root_mount, root_fstype=root_fstype, hostname=hostname
            )

            # Get guestfs mount point (if using mount-local)
            # For direct integration, we'll work within the guestfs context
            # and apply settings that persist to the image

            # Apply systemd boot features via guestfs commands using helper methods
            features_applied = {}

            # 1. Setup machine ID
            machine_id_features, machine_id_errors = self._setup_machine_id(g)
            features_applied.update(machine_id_features)
            result["errors"].extend(machine_id_errors)

            # 2. Configure auto-grow for root filesystem
            autogrow_features, autogrow_errors = self._configure_auto_grow(g, root_fstype)
            features_applied.update(autogrow_features)
            result["errors"].extend(autogrow_errors)

            # 3. Create VM-specific tmpfiles configuration
            tmpfiles_features, tmpfiles_errors = self._configure_tmpfiles(g)
            features_applied.update(tmpfiles_features)
            result["errors"].extend(tmpfiles_errors)

            # 4. Configure recovery mode (rescue target drop-in)
            recovery_features, recovery_errors = self._configure_recovery_mode(g)
            features_applied.update(recovery_features)
            result["errors"].extend(recovery_errors)

            # 5. RHEL/CentOS boot repair
            rhel_result, rhel_features, rhel_errors = self._apply_rhel_boot_repair(g)
            result["rhel_boot_repair"] = rhel_result
            features_applied.update(rhel_features)
            result["errors"].extend(rhel_errors)

            # 6. Systemd Firstboot Integration (uses direct guestfs writes)
            firstboot_result, firstboot_features, firstboot_errors = self._apply_firstboot_integration(g)
            result["firstboot_integration"] = firstboot_result
            features_applied.update(firstboot_features)
            result["errors"].extend(firstboot_errors)

            result["applied"] = len(features_applied) > 0
            result["features"] = features_applied
            result["boot_environment"] = {
                "boot_type": boot_type.value,
                "root_device": root_mount,
                "root_fstype": root_fstype.value,
                "hostname": hostname,
            }

            if result["applied"]:
                self.logger.info(f"✅ Systemd boot integration applied: {len(features_applied)} features")

        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as e:
            result["error"] = str(e)
            result["errors"].append(f"general: {e}")
            self.logger.warning(f"Systemd boot integration failed: {e}")
            self.logger.debug("Systemd boot integration error details:", exc_info=True)

        return result

    # ── Pipeline stages (extracted from run()) ──────────────────────────

    # pylint: disable=too-many-statements  # VM fixer step handles many device/filesystem-specific cases
    def _apply_migration_hardening(self, g: Any) -> dict[str, Any]:
        """
        Post-migration hardening: clean up VMware artifacts that can silently
        degrade the guest after migration to KVM.

        Fixes applied:
        - Blacklist VMware kernel modules (noisy log spam)
        - Remove VMware yum/apt repos (dnf/apt update failures)
        - Remove Xorg VMware SVGA driver config (X11 won't start on KVM)
        - Remove SSH host keys (security: cloned identity)
        - Clean cloud-init stale state (cloud-init won't re-run)
        - Bump GRUB_TIMEOUT=0 to 5 (recovery impossible otherwise)
        - Mask systemd-networkd-wait-online (90s boot hang)
        """
        result: dict[str, Any] = {"enabled": True, "fixes": []}
        fixes = result["fixes"]

        def _safe(label: str, fn: Any) -> None:
            try:
                fn()
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception as e:
                self.logger.debug("migration_hardening/%s: %s", label, e)

        # 1. Blacklist VMware kernel modules
        def _blacklist_vmware_modules() -> None:
            content = (
                "# Blacklist VMware-specific modules (not needed on KVM)\n"
                "# Written by h2kvm migration\n"
                "blacklist vmw_balloon\n"
                "blacklist vmw_vmci\n"
                "blacklist vmw_vsock_vmci_transport\n"
                "blacklist vmxnet3\n"
                "blacklist vmw_pvscsi\n"
            )
            g.write("/etc/modprobe.d/blacklist-vmware.conf", content.encode("utf-8"))
            fixes.append("blacklisted-vmware-modules")
            self.logger.info("✓ Blacklisted VMware kernel modules")

        _safe("blacklist_vmware_modules", _blacklist_vmware_modules)

        # 2. Remove VMware yum/apt repos
        def _remove_vmware_repos() -> None:
            repo_paths = [
                "/etc/yum.repos.d/vmware-tools.repo",
                "/etc/yum.repos.d/open-vm-tools.repo",
            ]
            for path in repo_paths:
                try:
                    if g.is_file(path):
                        g.rm(path)
                        fixes.append(f"removed-repo-{path.rsplit('/', maxsplit=1)[-1]}")
                        self.logger.info("✓ Removed VMware repo: %s", path)
                # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                except Exception:
                    pass
            # Glob-based removal for VMware-*.repo
            try:
                if g.is_dir("/etc/yum.repos.d"):
                    for f in g.ls("/etc/yum.repos.d"):
                        if f.lower().startswith("vmware") and f.endswith(".repo"):
                            fpath = f"/etc/yum.repos.d/{f}"
                            g.rm(fpath)
                            fixes.append(f"removed-repo-{f}")
                            self.logger.info("✓ Removed VMware repo: %s", fpath)
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception:
                pass
            # apt sources
            for apt_path in [
                "/etc/apt/sources.list.d/vmware-tools.list",
                "/etc/apt/sources.list.d/open-vm-tools.list",
            ]:
                try:
                    if g.is_file(apt_path):
                        g.rm(apt_path)
                        fixes.append(f"removed-repo-{apt_path.rsplit('/', maxsplit=1)[-1]}")
                        self.logger.info("✓ Removed VMware apt source: %s", apt_path)
                # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                except Exception:
                    pass

        _safe("remove_vmware_repos", _remove_vmware_repos)

        # 3. Remove Xorg VMware SVGA driver config
        def _fix_xorg_config() -> None:
            xorg_conf = "/etc/X11/xorg.conf"
            try:
                if g.is_file(xorg_conf):
                    content = g.read_file(xorg_conf).decode("utf-8", errors="replace")
                    if "vmware" in content.lower() or "vmwgfx" in content.lower():
                        g.mv(xorg_conf, xorg_conf + ".vmware.bak")
                        fixes.append("removed-xorg-vmware-config")
                        self.logger.info("✓ Renamed VMware xorg.conf → xorg.conf.vmware.bak")
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception:
                pass
            # Also check xorg.conf.d drop-ins
            try:
                if g.is_dir("/etc/X11/xorg.conf.d"):
                    for f in g.ls("/etc/X11/xorg.conf.d"):
                        fpath = f"/etc/X11/xorg.conf.d/{f}"
                        try:
                            content = g.read_file(fpath).decode("utf-8", errors="replace")
                            if "vmware" in content.lower() or "vmwgfx" in content.lower():
                                g.mv(fpath, fpath + ".vmware.bak")
                                fixes.append(f"removed-xorg-dropin-{f}")
                                self.logger.info("✓ Renamed VMware xorg drop-in: %s", f)
                        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                        except Exception:
                            pass
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception:
                pass

        _safe("fix_xorg_config", _fix_xorg_config)

        # 4. Remove SSH host keys — only if sshd or firstboot can regenerate them.
        # Without a regeneration mechanism, removing keys breaks SSH permanently.
        def _remove_ssh_host_keys() -> None:
            try:
                if not g.is_dir("/etc/ssh"):
                    return
                # Check that at least one regeneration mechanism exists
                has_regen = False
                # sshd on RHEL/Fedora regenerates keys on start via sshd-keygen@.service
                for path in [
                    "/usr/lib/systemd/system/sshd-keygen@.service",  # RHEL 8+/Fedora
                    "/usr/lib/systemd/system/sshd-keygen.service",  # RHEL 7
                    "/lib/systemd/system/ssh.service",  # Debian/Ubuntu
                    "/usr/lib/systemd/system/sshd.service",  # SUSE/openSUSE
                ]:
                    try:
                        if g.is_file(path):
                            has_regen = True
                            break
                    # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                    except Exception:
                        pass
                # Also check for cloud-init or firstboot script
                if not has_regen:
                    for path in ["/usr/bin/cloud-init", "/etc/h2kvm/firstboot.sh"]:
                        try:
                            if g.is_file(path):
                                has_regen = True
                                break
                        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                        except Exception:
                            pass
                if has_regen:
                    for f in g.ls("/etc/ssh"):
                        if f.startswith("ssh_host_") and ("_key" in f):
                            g.rm(f"/etc/ssh/{f}")
                    fixes.append("removed-ssh-host-keys")
                    self.logger.info("✓ Removed SSH host keys (will regenerate on boot)")
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception:
                pass

        _safe("remove_ssh_host_keys", _remove_ssh_host_keys)

        # 5. Clean cloud-init stale state (only if cloud-init is installed)
        def _clean_cloud_init() -> None:
            try:
                has_cloud_init = False
                for ci_path in ["/usr/bin/cloud-init", "/usr/local/bin/cloud-init"]:
                    try:
                        if g.is_file(ci_path):
                            has_cloud_init = True
                            break
                    # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                    except Exception:
                        pass
                if not has_cloud_init:
                    return
                cleaned = False
                if g.is_dir("/var/lib/cloud/instance"):
                    g.rm_rf("/var/lib/cloud/instance")
                    fixes.append("cleaned-cloud-init-instance")
                    cleaned = True
                if g.is_dir("/var/lib/cloud/data"):
                    g.rm_rf("/var/lib/cloud/data")
                    fixes.append("cleaned-cloud-init-data")
                    cleaned = True
                if cleaned:
                    self.logger.info("✓ Cleaned cloud-init stale state")
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception:
                pass

        _safe("clean_cloud_init", _clean_cloud_init)

        # 6. Bump GRUB_TIMEOUT=0 → 5 (allow recovery intervention)
        def _fix_grub_timeout() -> None:
            grub_default = "/etc/default/grub"
            try:
                if not g.is_file(grub_default):
                    return
                content = g.read_file(grub_default).decode("utf-8", errors="replace")
                # pylint: disable=import-outside-toplevel  # lazy import: optional dependency or avoids a circular import
                import re as _re

                if _re.search(r"""^\s*GRUB_TIMEOUT\s*=\s*["']?0["']?\s*$""", content, _re.MULTILINE):
                    new_content = _re.sub(
                        r"""^\s*GRUB_TIMEOUT\s*=\s*["']?0["']?\s*$""",
                        "GRUB_TIMEOUT=5",
                        content,
                        flags=_re.MULTILINE,
                    )
                    g.write(grub_default, new_content.encode("utf-8"))
                    fixes.append("bumped-grub-timeout-0-to-5")
                    self.logger.info("✓ Bumped GRUB_TIMEOUT=0 → 5 (allows recovery)")
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception:
                pass

        _safe("fix_grub_timeout", _fix_grub_timeout)

        # 7. Warn about firewalld zones with stale VMware interface names
        def _check_firewalld_zones() -> None:
            try:
                if not g.is_dir("/etc/firewalld/zones"):
                    return
                # pylint: disable=import-outside-toplevel  # lazy import: optional dependency or avoids a circular import
                from h2kvm.fixers.network.topology import INTERFACE_NAME_PATTERNS

                for f in g.ls("/etc/firewalld/zones"):
                    if not f.endswith(".xml"):
                        continue
                    fpath = f"/etc/firewalld/zones/{f}"
                    try:
                        content = g.read_file(fpath).decode("utf-8", errors="replace")
                        for pat, _tag in INTERFACE_NAME_PATTERNS:
                            # pylint: disable=import-outside-toplevel  # lazy import: optional dependency or avoids a circular import
                            import re as _fre

                            # Strip regex anchors/flags to extract the name pattern
                            inner = pat.removeprefix("(?i)").removeprefix("^").removesuffix("$")
                            m = _fre.search(
                                r'interface\s+name=["\'](' + inner + r')["\']', content, _fre.IGNORECASE
                            )
                            if m:
                                iface = m.group(1)
                                fixes.append(f"warned-firewalld-stale-{iface}")
                                self.logger.warning(
                                    "⚠️  Firewalld zone %s binds to VMware interface %s — "
                                    "this interface won't exist on KVM. Review zone config after boot.",
                                    f,
                                    iface,
                                )
                                break
                    # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                    except Exception:
                        pass
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception:
                pass

        _safe("check_firewalld_zones", _check_firewalld_zones)

        # 8. Mask systemd-networkd-wait-online.service (can hang 90s on renamed interfaces)
        def _mask_networkd_wait_online() -> None:
            unit = "/etc/systemd/system/systemd-networkd-wait-online.service"
            # pylint: disable=too-many-nested-blocks  # VM fixer step handles many device/filesystem-specific cases
            try:
                # Only mask if systemd-networkd is NOT enabled as the network manager.
                # Check for the systemd enable symlink rather than .network file
                # existence (vendor dirs ship .network files on many distros).
                networkd_enabled = False
                for wants_dir in [
                    "/etc/systemd/system/multi-user.target.wants",
                    "/etc/systemd/system/network-online.target.wants",
                ]:
                    try:
                        if g.is_dir(wants_dir):
                            for f in g.ls(wants_dir):
                                if "systemd-networkd" in f:
                                    networkd_enabled = True
                                    break
                    # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                    except Exception:
                        pass
                    if networkd_enabled:
                        break

                if not networkd_enabled and not g.is_symlink(unit):
                    g.ln_sf("/dev/null", unit)
                    fixes.append("masked-networkd-wait-online")
                    self.logger.info("✓ Masked systemd-networkd-wait-online (prevents 90s boot hang)")
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception:
                pass

        _safe("mask_networkd_wait_online", _mask_networkd_wait_online)

        if fixes:
            self.logger.info("✅ Migration hardening: %d fixes applied", len(fixes))

        return result

    def _detect_lvm_luks(self, g: Any) -> dict[str, Any]:
        """Probe the disk for LVM and LUKS volumes via guestfs list_filesystems."""
        detection: dict[str, Any] = {"has_lvm": False, "has_luks": False, "filesystems": {}}
        try:
            fsmap = g.list_filesystems() or {}
            detection["filesystems"] = {U.to_text(dev): U.to_text(fstype) for dev, fstype in fsmap.items()}
            for fstype in fsmap.values():
                t = U.to_text(fstype)
                if t == "LVM2_member":
                    detection["has_lvm"] = True
                elif t == "crypto_LUKS":
                    detection["has_luks"] = True
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as e:
            self.logger.debug(f"LVM/LUKS detection via list_filesystems failed: {e}")
        return detection

    def _detect_and_record_lvm_luks(self, g: Any) -> None:
        """Probe the disk for LVM and LUKS via guestfs list_filesystems.

        Records _detected_lvm/_detected_luks for reporting.
        """
        detection = self._detect_lvm_luks(g)
        self._detected_lvm = detection["has_lvm"]
        self._detected_luks = detection["has_luks"]
        self.report.setdefault("analysis", {})["lvm_luks_detection"] = detection

        if self._detected_lvm or self._detected_luks:
            reasons = []
            if self._detected_lvm:
                reasons.append("LVM")
            if self._detected_luks:
                reasons.append("LUKS")
            self.logger.info("Detected %s on disk", "+".join(reasons))

    def _activate_storage(self, g: Any) -> dict[str, str]:
        """Phase 1: Activate storage stack (LUKS, LVM, UUIDs) and mount root."""
        # Detect LVM/LUKS for later appliance-based initramfs rebuild
        self._detect_and_record_lvm_luks(g)

        # Storage activation always goes through guestfs/VMCraft
        # (the disk is already NBD-attached, so appliance VM can't access it)
        luks_audit = self._run_stage("luks_unlock", lambda: self._unlock_luks_devices(g), default={})
        self.report["analysis"]["luks"] = luks_audit
        self.logger.info(f"LUKS audit: {U.json_dump(luks_audit)}")

        stack_audit = self._run_stage(
            "storage_stack", lambda: self._pre_mount_activate_storage_stack(g), default={}
        )
        self.report.setdefault("analysis", {})["storage_stack"] = stack_audit

        self._run_stage("lvm_activate", lambda: self._activate_lvm(g), default=None)

        uuid_audit = self._run_stage("regenerate_uuids", lambda: self._regenerate_uuids(g), default={})
        self.report.setdefault("analysis", {})["uuid_regeneration"] = uuid_audit
        uuid_map: dict[str, str] = uuid_audit.get("uuid_map", {}) if uuid_audit else {}

        mount_ok = self._run_stage(
            "mount_root", lambda: self.detect_and_mount_root(g), critical=False, default="failed"
        )
        if mount_ok == "failed":
            self.logger.info("")
            self.logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            self.logger.info("⚠️  Root filesystem could not be mounted for offline fixes.")
            self.logger.info("   This can happen with BTRFS subvolumes, encrypted disks,")
            self.logger.info("   or unsupported filesystem types.")
            self.logger.info("")
            self.logger.info("   The disk image was converted successfully — the VM should")
            self.logger.info("   still boot. Offline fixes (fstab, initramfs, VMware cleanup)")
            self.logger.info("   were skipped. You may need to apply them manually after boot.")
            self.logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            self.logger.info("")
            return None  # Skip all offline fixes — conversion is still valid

        if uuid_map:
            self.logger.info(f"Updating fstab/crypttab with {len(uuid_map)} regenerated UUID(s)...")
            self._run_stage(
                "update_fstab_uuids",
                lambda: self._uuid_regenerator.update_fstab(g, uuid_map),
                default=False,
            )
            self._run_stage(
                "update_crypttab_uuids",
                lambda: self._uuid_regenerator.update_crypttab(g, uuid_map),
                default=False,
            )

        return uuid_map

    # pylint: disable=too-many-locals,too-many-branches,too-many-statements  # VM fixer step handles many device/filesystem-specific cases
    def _validate_guest(self, g: Any) -> None:
        """Phase 2: Filesystem repair, guest identity detection, and validation."""
        fs_audit = self._run_stage(
            "filesystem_repair", lambda: self.fix_filesystems(g), default={"enabled": False}
        )
        self.report.setdefault("analysis", {})["filesystem_repair"] = fs_audit
        if (fs_audit or {}).get("enabled"):
            remount_ok = self._run_stage(
                "remount_root_after_fs_repair",
                lambda: self.detect_and_mount_root(g),
                critical=False,
                default="failed",
            )
            if remount_ok == "failed":
                self.logger.warning(
                    "⚠️  Could not remount root after filesystem repair — continuing without offline fixes"
                )
                return

        def _read_os_release() -> str:
            try:
                return U.to_text(g.read_file("/etc/os-release")) if g.is_file("/etc/os-release") else ""
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception:
                return ""

        osr = self._run_stage("read_os_release", _read_os_release, default="")
        # Detect swap size for memory estimation fallback
        swap_mib = 0
        # pylint: disable=too-many-nested-blocks  # VM fixer step handles many device/filesystem-specific cases
        try:
            # Check fstab for swap entries and try to get partition sizes
            if g.is_file("/etc/fstab"):
                fstab = U.to_text(g.read_file("/etc/fstab"))
                for line in fstab.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 3 and parts[2] == "swap" and not line.strip().startswith("#"):
                        # Try to get swap partition size from blkid/blockdev
                        swap_dev = parts[0]
                        try:
                            if swap_dev.startswith("/dev/"):
                                size_bytes = g.blockdev_getsize64(swap_dev)
                                swap_mib = max(swap_mib, size_bytes // (1024 * 1024))
                        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                        except Exception:
                            pass
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception:
            pass

        # Detect Secure Boot from guest EFI binaries
        secure_boot_detected = False
        try:
            for shim_path in (
                "/boot/efi/EFI/fedora/shimx64.efi",
                "/boot/efi/EFI/redhat/shimx64.efi",
                "/boot/efi/EFI/centos/shimx64.efi",
                "/boot/efi/EFI/BOOT/BOOTX64.EFI",
                "/boot/efi/EFI/ubuntu/shimx64.efi",
                "/boot/efi/EFI/debian/shimx64.efi",
                "/boot/efi/EFI/suse/shim.efi",
            ):
                try:
                    if g.is_file(shim_path):
                        secure_boot_detected = True
                        self.logger.info("Secure Boot shim detected: %s", shim_path)
                        break
                # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                except Exception:
                    pass
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception:
            pass

        self.report["analysis"]["guest"] = {
            "inspect_root": self.inspect_root,
            "root_dev": self.root_dev,
            "root_btrfs_subvol": self.root_btrfs_subvol,
            "boot_disk_index": self.boot_disk_index,
            "os_release": osr,
            "swap_size_mib": swap_mib if swap_mib > 0 else None,
        }
        self.report["analysis"]["secure_boot_detected"] = secure_boot_detected

        def _do_validation() -> dict[str, Any]:
            suite = self.create_validation_suite(g)
            ctx = {"image": str(self.image), "root_dev": self.root_dev, "subvol": self.root_btrfs_subvol}
            raw = suite.run_all(ctx)
            # Extract only the actual check results, not meta-keys like
            # ok/failed_critical/stats/exit_code which are payload-level fields.
            checks = raw.get("results", raw) if isinstance(raw, dict) else raw
            norm = self._normalize_validation_results(checks)
            summary = self._summarize_validation(norm)
            return {"results": norm, "summary": summary}

        self.report["validation"] = self._run_stage(
            "validation", _do_validation, default={"results": {}, "summary": {}}
        )

        norm = (self.report.get("validation") or {}).get("results", {}) or {}
        critical_failures = [name for name, r in norm.items() if r.get("critical") and not r.get("passed")]
        if critical_failures:
            self.logger.warning(f"Critical validation failures: {critical_failures}")

        if self.recovery_manager:
            self.recovery_manager.save_checkpoint(
                "mounted",
                {
                    "root_dev": self.root_dev,
                    "root_btrfs_subvol": self.root_btrfs_subvol,
                    "validation": self.report.get("validation"),
                },
            )

    # pylint: disable=too-many-locals  # VM fixer step handles many device/filesystem-specific cases
    def _apply_config_fixes(self, g: Any) -> dict[str, Any]:
        """Phase 3: Apply fstab, crypttab, network, GRUB, and injection fixes."""
        if self.root_dev and self._spec_converter.root_dev != self.root_dev:
            self._spec_converter.root_dev = self.root_dev

        c_fstab, fstab_changes, fstab_audit = self._run_stage(
            "rewrite_fstab", lambda: self.rewrite_fstab(g), default=(0, [], {})
        )
        c_crypt = self._run_stage("rewrite_crypttab", lambda: self.rewrite_crypttab(g), default=0)
        network_audit = self._run_stage(
            "fix_network", lambda: self.fix_network_config(g), default={"enabled": False}
        )

        c_devmap = 0
        if self.update_grub:
            c_devmap = self._run_stage(
                "grub_remove_device_map", lambda: self.remove_stale_device_map(g), default=0
            )

        mdraid = self._run_stage(
            "mdraid_check",
            lambda: self.mdraid_check(g) if hasattr(self, "mdraid_check") else {"present": False},
            default={"present": False},
        )
        cloud_init = self._run_stage(
            "inject_cloud_init",
            lambda: self.inject_cloud_init(g) if hasattr(self, "inject_cloud_init") else {"enabled": False},
            default={"enabled": False},
        )

        # Linux-only config injections
        not_attempted: dict[str, Any] = {"injected": False, "reason": "not_attempted"}
        firstboot = self._run_stage(
            "inject_firstboot",
            lambda: firstboot_injector.inject_firstboot(self, g),
            default=not_attempted,
        )
        network_config = self._run_stage(
            "inject_network_config",
            lambda: network_config_injector.inject_network_config(self, g),
            default=not_attempted,
        )
        user_config = self._run_stage(
            "inject_user_config",
            lambda: user_config_injector.inject_user_config(self, g),
            default=not_attempted,
        )
        service_config = self._run_stage(
            "inject_service_config",
            lambda: service_config_injector.inject_service_config(self, g),
            default=not_attempted,
        )
        hostname_config = self._run_stage(
            "inject_hostname_config",
            lambda: hostname_config_injector.inject_hostname_config(self, g),
            default=not_attempted,
        )

        return {
            "c_fstab": c_fstab,
            "fstab_changes": fstab_changes,
            "fstab_audit": fstab_audit,
            "c_crypt": c_crypt,
            "network_audit": network_audit,
            "c_devmap": c_devmap,
            "mdraid": mdraid,
            "cloud_init": cloud_init,
            "firstboot": firstboot,
            "network_config": network_config,
            "user_config": user_config,
            "service_config": service_config,
            "hostname_config": hostname_config,
        }

    def _schedule_selinux_relabel(self, g: Any) -> dict[str, Any]:
        """Touch /.autorelabel on SELinux-enabled guests to trigger boot-time relabel."""
        result: dict[str, Any] = {"enabled": False}

        # Only relevant for distros that use SELinux
        try:
            selinux_config = g.read_file("/etc/selinux/config").decode("utf-8", errors="replace")
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception:
            result["skipped"] = "no_selinux_config"
            return result

        # Check if SELinux is enabled (not disabled)
        for line in selinux_config.splitlines():
            stripped = line.strip()
            if stripped.startswith("SELINUX="):
                mode = stripped.split("=", 1)[1].strip().lower()
                if mode == "disabled":
                    result["skipped"] = "selinux_disabled"
                    self.logger.info("SELinux is disabled, skipping autorelabel")
                    return result
                break

        # Touch /.autorelabel
        if self.dry_run:
            self.logger.info("[dry-run] Would touch /.autorelabel for SELinux relabel")
            result["enabled"] = True
            result["dry_run"] = True
            return result

        try:
            g.touch("/.autorelabel")
            self.logger.info("Touched /.autorelabel — SELinux will relabel on next boot")
            result["enabled"] = True
            result["autorelabel_created"] = True
        # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
        except Exception as e:
            self.logger.warning(f"Failed to create /.autorelabel: {e}")
            result["error"] = str(e)

        return result

    # pylint: disable=too-many-locals,too-many-branches,too-many-statements  # VM fixer step handles many device/filesystem-specific cases
    def _apply_os_specific_fixes(self, g: Any) -> dict[str, Any]:
        """Phase 4: Windows/Linux-specific fixes, disk analysis, VMware removal."""
        is_win = self._run_stage("detect_windows", lambda: self.is_windows(g), default=False)

        # pylint: disable=too-many-nested-blocks  # VM fixer step handles many device/filesystem-specific cases
        if is_win:
            # Detect Windows version (build number) for Win11-specific handling.
            # Try multiple sources: VMCraft inspection cache, guestfs inspect API,
            # or registry-based detection.
            try:
                # Source 1: VMCraft backend inspection cache (most reliable for VMCraft)
                # The guestfs handle `g` may be a VMCraft GuestFS wrapper with
                # _os_inspector._inspect_cache populated during mount_root_bruteforce
                for attr_path in ("_os_inspector._inspect_cache", "_enhanced_inspector._inspect_cache"):
                    parts = attr_path.split(".")
                    obj = g
                    for part in parts:
                        obj = getattr(obj, part, None)
                        if obj is None:
                            break
                    if isinstance(obj, dict):
                        for os_info in obj.values():
                            if (
                                isinstance(os_info, dict)
                                and os_info.get("type") == "windows"
                                and os_info.get("build")
                            ):
                                self.detected_windows_build = os_info["build"]
                                self.detected_windows_product = os_info.get("product") or os_info.get(
                                    "os_name"
                                )
                                break
                    if self.detected_windows_build:
                        break

                # Source 2: libguestfs inspect_get_product_name (if inspect_root set)
                if not self.detected_windows_build and self.inspect_root:
                    try:
                        product = U.to_text(g.inspect_get_product_name(self.inspect_root))
                        if product:
                            self.detected_windows_product = product
                            if "11" in product or "12" in product:
                                self.detected_windows_build = 22000  # Approximate
                    # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                    except Exception:
                        pass

                # Source 3: Check registry via hivex (last resort)
                if not self.detected_windows_build:
                    try:
                        # pylint: disable=import-outside-toplevel  # lazy import: optional dependency or avoids a circular import
                        from h2kvm.fixers.windows.virtio.detection import (
                            _read_windows_build_from_software_hive,
                        )

                        for sw_path in (
                            "/Windows/System32/config/SOFTWARE",
                            "/WINDOWS/System32/config/SOFTWARE",
                        ):
                            try:
                                if g.is_file(sw_path):
                                    build = _read_windows_build_from_software_hive(self, g, sw_path)
                                    if build:
                                        self.detected_windows_build = build
                                        break
                            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                            except Exception:
                                continue
                    # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
                    except Exception:
                        pass

                if self.detected_windows_build:
                    self.logger.info(
                        "Windows version: product=%s build=%s",
                        self.detected_windows_product,
                        self.detected_windows_build,
                    )
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception as e:
                self.logger.debug("Windows version detection failed: %s", e)

            win = self._run_stage(
                "windows_bcd_fix",
                lambda: self.windows_bcd_actual_fix(g),
                default={"enabled": True, "error": "failed"},
            )
            # VirtIO driver injection (critical for boot on KVM)
            virtio = self._run_stage(
                "inject_virtio_drivers",
                lambda: self.inject_virtio_drivers(g),
                default={"injected": False, "error": "failed"},
            )
            if self.enable_rdp is not False:
                fb = virtio.get("firstboot") if isinstance(virtio, dict) else {}
                fb_ok = bool(fb.get("success", True)) if isinstance(fb, dict) else True
                if not fb_ok:
                    root = getattr(self, "inspect_root", None) or ""
                    if root:
                        self._run_stage(
                            "offline_rdp_registry_fallback",
                            lambda: windows_fixer.enable_rdp_if_disabled(g, root, self.logger),
                            default={"modified": False, "error": "failed"},
                        )
                        self.logger.info(
                            "Firstboot RDP provisioning did not succeed — applied offline registry RDP fallback"
                        )
            # Network config retention (re-apply static IPs at firstboot)
            net_retain = self._run_stage(
                "retain_windows_network",
                lambda: self.retain_windows_network_config(g),
                default={"captured": False, "error": "failed"},
            )
            # Route cleanup (remove duplicate default gateways after NIC swap)
            route_cleanup = self._run_stage(
                "route_cleanup",
                lambda: self.stage_route_cleanup(g),
                default={"staged": False, "error": "failed"},
            )
            # Disk online (bring VirtIO disks online at firstboot)
            disk_online = self._run_stage(
                "disk_online",
                lambda: self.stage_disk_online(g),
                default={"staged": False, "error": "failed"},
            )
        else:
            win = {"enabled": False, "skipped": "not_windows"}
            virtio = {"injected": False, "skipped": "not_windows"}
            net_retain = {"captured": False, "skipped": "not_windows"}
            route_cleanup = {"staged": False, "skipped": "not_windows"}
            disk_online = {"staged": False, "skipped": "not_windows"}

        disk = self._run_stage(
            "disk_analysis", lambda: self.analyze_disk_space(g), default={"analysis": "failed"}
        )
        vmware_removal = self._run_stage(
            "vmware_tools_removal",
            lambda: self.remove_vmware_tools_func(g),
            default={"enabled": False, "error": "failed"},
        )

        return {
            "is_win": is_win,
            "win": win,
            "virtio": virtio,
            "net_retain": net_retain,
            "route_cleanup": route_cleanup,
            "disk_online": disk_online,
            "disk": disk,
            "vmware_removal": vmware_removal,
        }

    def _apply_boot_fixes(self, g: Any, is_win: bool) -> dict[str, Any]:
        """Phase 5: Post-conversion boot hardening, boot mode detection, initramfs regen."""
        post_conversion_audit: dict[str, Any] = {"enabled": False}
        if not is_win and self.regen_initramfs:
            # pylint: disable=import-outside-toplevel  # lazy import: optional dependency or avoids a circular import
            from .bootloader.post_conversion import PostConversionBootFixer

            post_conversion_audit = self._run_stage(
                "post_conversion_boot_hardening",
                lambda: PostConversionBootFixer(self.logger).apply_golden_fixes(
                    g,
                    harden_fstab=True,
                    rebuild_initramfs=False,
                    regenerate_grub=False,
                ),
                default={"enabled": False, "error": "failed"},
            )
            self.logger.info(f"Post-conversion boot hardening: {U.json_dump(post_conversion_audit)}")

        def _detect_boot_mode() -> str:
            try:
                if is_win:
                    bcd_bios = "/Windows/Boot/BCD"
                    uefi_bcd_paths = (
                        "/boot/efi/EFI/Microsoft/Boot/BCD",
                        "/boot/EFI/Microsoft/Boot/BCD",
                        "/efi/EFI/Microsoft/Boot/BCD",
                        "/EFI/Microsoft/Boot/BCD",
                    )
                    has_bios = bool(g.is_file(bcd_bios))
                    has_uefi = any(g.is_file(p) for p in uefi_bcd_paths)
                    self.report["analysis"]["windows_bcd_bios"] = has_bios
                    self.report["analysis"]["windows_bcd_uefi"] = has_uefi
                    if has_uefi and not has_bios:
                        return "uefi"
                    if has_bios and not has_uefi:
                        return "bios"
                    if has_bios and has_uefi:
                        # Dual stores: defer to partition hints in firmware resolver.
                        return "unknown"
                    return "unknown"
                # pylint: disable=protected-access  # tight coupling with sibling fixer/backend internals in this package
                return "uefi" if grub_fixer._guest_looks_uefi(g) else "bios"
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception:
                return "unknown"

        boot_mode = self._run_stage("detect_boot_mode", _detect_boot_mode, default="unknown")
        self.report["analysis"]["boot_mode"] = boot_mode
        self.logger.info(f"Detected boot mode: {boot_mode}")

        skip_old_regen = post_conversion_audit.get("initramfs_rebuilt", False)
        if skip_old_regen:
            self.logger.info(
                "Skipping old initramfs regen (post_conversion already rebuilt generic initramfs)"
            )
            regen_info = {"enabled": False, "skipped": "post_conversion_handled_initramfs"}
        elif self.regen_initramfs:
            regen_info = self._run_stage(
                "regen_initramfs_and_bootloader",
                lambda: self.regen(g),
                default={"enabled": True, "error": "failed"},
            )
        else:
            regen_info = {"enabled": False, "skipped": "regen_initramfs_disabled"}

        systemd_boot = self._run_stage(
            "systemd_boot_integration",
            lambda: (
                self.apply_systemd_boot_integration(g)
                if not is_win
                else {"enabled": False, "skipped": "not_linux"}
            ),
            default={"enabled": False, "skipped": "not_attempted"},
        )

        # Post-migration hardening: clean up VMware artifacts that can
        # silently degrade the guest (stale repos, Xorg driver, SSH keys,
        # kernel module noise, cloud-init state, GRUB timeout, etc.)
        migration_hardening = self._run_stage(
            "migration_hardening",
            lambda: (
                self._apply_migration_hardening(g)
                if not is_win
                else {"enabled": False, "skipped": "not_linux"}
            ),
            default={"enabled": False},
        )

        return {
            "post_conversion": post_conversion_audit,
            "regen": regen_info,
            "systemd_boot": systemd_boot,
            "migration_hardening": migration_hardening,
        }

    def _aggregate_report(
        self, config_results: dict[str, Any], os_results: dict[str, Any], boot_results: dict[str, Any]
    ) -> None:
        """Phase 6: Aggregate all stage results into the final report."""
        self.report["changes"] = {
            "fstab": config_results["c_fstab"],
            "crypttab": config_results["c_crypt"],
            "network": config_results["network_audit"],
            "grub_root": 0,
            "grub_device_map_removed": config_results["c_devmap"],
            "vmware_tools_removed": os_results["vmware_removal"],
            "cloud_init_injected": config_results["cloud_init"],
            "firstboot_scripts_injected": config_results["firstboot"],
            "network_config_injected": config_results["network_config"],
            "user_config_injected": config_results["user_config"],
            "service_config_injected": config_results["service_config"],
            "hostname_config_injected": config_results["hostname_config"],
        }
        self.report["analysis"]["fstab_audit"] = config_results["fstab_audit"]
        self.report["analysis"]["fstab_changes"] = [vars(x) for x in config_results["fstab_changes"]]
        self.report["analysis"]["mdraid"] = config_results["mdraid"]
        self.report["analysis"]["windows"] = os_results["win"]
        self.report["analysis"]["windows_build"] = self.detected_windows_build
        self.report["analysis"]["windows_product"] = self.detected_windows_product
        self.report["analysis"]["disk"] = os_results["disk"]
        self.report["analysis"]["regen"] = boot_results["regen"]
        self.report["analysis"]["post_conversion_boot_hardening"] = boot_results["post_conversion"]
        self.report["analysis"]["systemd_boot_integration"] = boot_results["systemd_boot"]
        self.report["analysis"]["migration_hardening"] = boot_results.get("migration_hardening", {})
        self.report["analysis"]["timings"] = dict(self._timings)
        self.report["timestamps"]["end"] = _dt.datetime.now().isoformat()

    # ── Main entry point ─────────────────────────────────────────────

    def run(self) -> None:
        """
        Main offline fix pipeline.

        Phases: storage activation → validation → config fixes →
        OS-specific fixes → boot fixes → report aggregation.
        """
        U.banner(self.logger, "Offline guest fix")
        self.logger.info(f"Opening offline image: {self.image}")

        if self.recovery_manager:
            self.recovery_manager.save_checkpoint("start", {"image": str(self.image)})

        if self.resize:
            self.report["analysis"]["image_resize"] = self._run_stage(
                "image_resize", self._resize_image_container
            )  # type: ignore

        g = self.open()
        try:
            with TraceContext(
                vm_id=Path(str(self.image)).name, workflow="offline_fix", component="offline_fixer"
            ):
                with PhaseTimer(
                    "storage_activation_start", "storage_activation_complete", phase="storage_activation"
                ):
                    self._activate_storage(g)

                with PhaseTimer(
                    "guest_validation_start", "guest_validation_complete", phase="guest_validation"
                ):
                    self._validate_guest(g)

                with PhaseTimer("config_fixes_start", "config_fixes_complete", phase="config_fixes"):
                    config_results = self._apply_config_fixes(g)

                with PhaseTimer("os_fixes_start", "os_fixes_complete", phase="os_specific_fixes"):
                    os_results = self._apply_os_specific_fixes(g)

                with PhaseTimer("boot_fixes_start", "boot_fixes_complete", phase="boot_fixes"):
                    boot_results = self._apply_boot_fixes(g, os_results["is_win"])

                # SELinux autorelabel: schedule boot-time relabel for Linux guests
                # after offline modifications (fstab, initramfs, grub) invalidate contexts
                selinux_result = {"enabled": False, "skipped": "not_linux"}
                if not os_results["is_win"]:
                    selinux_result = self._run_stage(
                        "selinux_autorelabel",
                        lambda: self._schedule_selinux_relabel(g),
                        default={"enabled": False, "error": "failed"},
                    )

                if not self.dry_run:
                    self._run_stage("guestfs_sync", g.sync, default=None)
                self._safe_umount_all(g)

                self._aggregate_report(config_results, os_results, boot_results)
                self.report["analysis"]["selinux"] = selinux_result

                log_event(
                    "offline_fix_complete",
                    image=str(self.image),
                    is_windows=os_results.get("is_win", False),
                    fstab_changes=config_results.get("c_fstab", 0),
                    boot_mode=self.report.get("analysis", {}).get("boot_mode", "unknown"),
                )

        finally:
            with contextlib.suppress(Exception):
                self._safe_umount_all(g)

            try:
                if g.converted_image_path:
                    self.converted_image_path = g.converted_image_path
                    g.keep_converted_image()
                    self.logger.info(
                        f"Preserved converted image for final conversion: {self.converted_image_path.name}"
                    )
            # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            except Exception as e:
                self.logger.debug(f"Could not preserve converted image: {e}")

            with contextlib.suppress(Exception):
                g.close()

        self.write_report()
