# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
# https://zyvor.dev · info@zyvor.dev

# pylint: disable=too-many-lines  # cohesive offline-fixing orchestrator; splitting would fragment the fix pipeline
"""
Offline guest fixing for migrated VMs.

GuestKit repairs the disk image: boot, fstab, GRUB, initramfs and VirtIO for Linux,
and the equivalent fixes for Windows. This module runs that repair
(``guestkit.run_migrate_repair``), then applies h2kvm's own injectors (cloud-init,
first-boot, network, users, services, hostname) through guestfs, and writes the report.
It never boots the VM.

Architecture:
    This orchestrator delegates to focused modules for maintainability:
    - offline/operations/storage.py - Storage stack activation (LVM, LUKS, RAID, ZFS)
    - offline/helpers/root_detection.py - Root filesystem detection
    - offline/helpers/xfs_uuid.py - XFS UUID regeneration for cloned VMs
    - offline/helpers/utilities.py - Common utility functions
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
import subprocess
import tempfile
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
from h2kvm.core.structured_log import PhaseTimer
from h2kvm.core.sudo import run_sudo
from h2kvm.core.utils import U

# Delegated fixers (keep OfflineFSFix "thin")
from .filesystem import fixer as filesystem_fixer  # type: ignore
from .filesystem.fstab import (
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
from .offline.operations import StorageActivator
from .offline.spec_converter import SpecConverter
from .offline.validation import OfflineValidationManager
from .report_writer import write_report

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
    fstab_mode: str | FstabMode = FstabMode.STABILIZE_ALL
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

    # VMCraft demoted — GuestKit is the disk/inspect/repair layer
    conversion_dir: str | Path | None = None
    allowed_dirs: list[str] | None = None  # Additional allowed directories for security

    # Backend selection (see BackendType enum in core.guestfs_factory)
    backend: str = "guestkit"

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

    # guestfs open/close helpers
    def open(self) -> guestfs.GuestFS:
        """
        Open guestfs with configured backend.

        Backend options:
        - "guestkit" (default): GuestKit Rust Guestfs (qemu-nbd + LVM/LUKS)
        - "guestfs": Native libguestfs with supermin appliance
        - "auto": GuestKit first, then libguestfs
        Legacy aliases "vmcraft" / "namespace" map to guestkit in create_guestfs().
        """
        backend = self.backend

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

    # Filesystem fixer (delegated)
    def fix_filesystems(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Delegate to the filesystem fixer module."""
        return filesystem_fixer.fix_filesystems(self, g)

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

    # ── Pipeline stages (extracted from run()) ──────────────────────────

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

    def _uses_guestkit_repair(self) -> bool:
        """True when GuestKit should own fstab/grub/initramfs/virtio repair."""
        return self.backend in ("guestkit", "guestfs", "auto", "vmcraft", "namespace", None, "")

    def _guestkit_ignored_options(self) -> dict[str, Any]:
        """Options that only the removed in-process fixer honored.

        ``guestkit.run_migrate_repair`` has no parameters for these: GuestKit
        decides the fstab, GRUB and initramfs changes itself. Return the ones
        the caller moved off their defaults so the run can say so.
        """
        ignored: dict[str, Any] = {}
        if self.fstab_mode is not FstabMode.STABILIZE_ALL:
            ignored["fstab_mode"] = self.fstab_mode.value
        if not self.update_grub:
            ignored["no_grub"] = True
        if not self.regen_initramfs:
            ignored["regen_initramfs"] = False
        return ignored

    def _has_injectors(self) -> bool:
        """True when h2kvm-specific injectors are configured."""
        return bool(
            self.inject_cloud_init_data
            or self.firstboot_config
            or self.network_config_inject
            or self.user_config_inject
            or self.service_config_inject
            or self.hostname_config_inject
        )

    def _apply_injectors_only(self, g: Any) -> dict[str, Any]:
        """Run h2kvm-only config injectors (GuestKit handles boot/fstab/grub repair)."""
        not_attempted: dict[str, Any] = {"injected": False, "reason": "not_attempted"}
        cloud_init = self._run_stage(
            "inject_cloud_init",
            lambda: self.inject_cloud_init(g) if hasattr(self, "inject_cloud_init") else {"enabled": False},
            default={"enabled": False},
        )
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
            "cloud_init": cloud_init,
            "firstboot": firstboot,
            "network_config": network_config,
            "user_config": user_config,
            "service_config": service_config,
            "hostname_config": hostname_config,
        }

    def _run_guestkit_pipeline(self) -> None:
        """Delegate boot/fstab/grub/virtio repair to GuestKit; run injectors locally."""
        from h2kvm.core import guestkit_client

        if self.backend == "guestfs":
            self.logger.warning("backend 'guestfs' is ignored; h2kvm uses GuestKit only")

        ignored = self._guestkit_ignored_options()
        if ignored:
            self.logger.warning(
                "GuestKit decides fstab, GRUB and initramfs changes itself; these options had no effect: %s",
                ", ".join(f"{k}={v}" for k, v in ignored.items()),
            )

        if self.resize:
            self.report["analysis"]["image_resize"] = self._run_stage(
                "image_resize", self._resize_image_container
            )  # type: ignore

        gk = guestkit_client.migrate_repair(
            self.image,
            apply=not self.dry_run,
            include_destructive=self.remove_vmware_tools,
            virtio_win=self.virtio_drivers_dir,
            verbose=self.logger.isEnabledFor(10),  # DEBUG
        )
        self.report["guestkit"] = gk
        self.report["analysis"]["guestkit"] = {
            "applied": gk.get("applied"),
            "dry_run": gk.get("dry_run"),
            "score": gk.get("assessment_score"),
            "message": gk.get("message"),
            "notes": gk.get("notes", []),
            "ignored_options": ignored,
        }
        self.logger.info("GuestKit migration repair: %s", gk.get("message", ""))

        if self._has_injectors():
            g = self.open()
            try:
                with PhaseTimer(
                    "storage_activation_start", "storage_activation_complete", phase="storage_activation"
                ):
                    self._activate_storage(g)
                with PhaseTimer(
                    "guest_validation_start", "guest_validation_complete", phase="guest_validation"
                ):
                    self._validate_guest(g)
                inject_results = self._apply_injectors_only(g)
                self.report["analysis"]["injectors"] = inject_results
                if not self.dry_run:
                    self._run_stage("guestfs_sync", g.sync, default=None)
                self._safe_umount_all(g)
            finally:
                with contextlib.suppress(Exception):
                    self._safe_umount_all(g)
                with contextlib.suppress(Exception):
                    g.close()

        self.report["timestamps"]["end"] = _dt.datetime.now().isoformat()
        self.write_report()

    # ── Main entry point ─────────────────────────────────────────────

    def run(self) -> None:
        """
        Main offline fix pipeline.

        GuestKit repairs boot, fstab, GRUB and VirtIO on the disk image; h2kvm then
        applies its own injectors (cloud-init, first-boot, network, users, services,
        hostname) and writes the report.
        """
        U.banner(self.logger, "Offline guest fix")
        self.logger.info(f"Opening offline image: {self.image}")

        if self.recovery_manager:
            self.recovery_manager.save_checkpoint("start", {"image": str(self.image)})

        if not self._uses_guestkit_repair():
            raise RuntimeError(
                f"Unsupported offline repair backend {self.backend!r}. h2kvm repairs guests with GuestKit only; "
                "install it with: pip install hypersdk-guestkit"
            )
        self._run_guestkit_pipeline()
