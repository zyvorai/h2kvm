# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/orchestrator/disk_processor.py
"""
Disk processing pipeline.
Handles single and parallel disk processing operations.
"""
# pylint: disable=too-many-lines
# Cohesive single/parallel disk-processing pipeline; splitting would fragment
# closely-related orchestration logic more than it would help.

from __future__ import annotations

import concurrent.futures
import json
import os
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from h2kvm.config.config_loader import YAML_AVAILABLE, yaml
from h2kvm.config.pipeline_config import DiskProcessingConfig, resolve_enable_rdp
from h2kvm.converters.flatten import Flatten
from h2kvm.converters.qemu.converter import Convert
from h2kvm.core.exceptions import Fatal
from h2kvm.core.logger import Log
from h2kvm.core.structured_log import PhaseTimer, TraceContext, log_event
from h2kvm.core.utils import U, effective_cpu_count
from h2kvm.fixers.offline_fixer import OfflineFixConfig, OfflineFSFix
from h2kvm.providers.vmware.utils.vmdk_parser import VMDK
from h2kvm.quality.validation.vmdk_inspector import RiskLevel, VMDKInspector

if TYPE_CHECKING:
    import argparse
    import logging
    from collections.abc import Callable

    from h2kvm.core.recovery_manager import RecoveryManager


class DiskProcessor:  # pylint: disable=too-many-instance-attributes
    """
    Disk processing pipeline coordinator for VM migration workflows.

    Orchestrates the complete disk processing workflow including:
    - Disk validation and inspection (controller compatibility, snapshots, boot mode)
    - Automatic BusLogic→LSI Logic controller fixes (VMDK-specific)
    - Snapshot flattening (multi-extent images → single image)
    - Offline guest filesystem repairs (fstab, initramfs, grub, drivers)
    - Format conversion (VMDK/OVA/VHD/VHDX/RAW → QCOW2/RAW)
    - Progress monitoring and error recovery
    - Parallel multi-disk processing with thread pooling

    Capabilities:
    - Single-threaded sequential processing (default)
    - Multi-threaded parallel processing (via --parallel-processing)
    - Recovery checkpoint integration for resumable operations
    - Cloud-init configuration injection
    - Firstboot script injection
    - Network/hostname/user configuration injection
    - LUKS encrypted volume support
    - Virtio driver injection for controller compatibility

    Attributes:
        logger: Logger instance for status/error reporting
        args: Parsed command-line arguments from argparse
        recovery_manager: Optional recovery manager for checkpoint/resume

    Examples:
        >>> processor = DiskProcessor(logger, args, recovery_manager)
        >>> disks = [Path("vm1.vmdk"), Path("vm2.vmdk")]
        >>> output = processor.process_disks_parallel(disks, Path("/output"))

        >>> # Or single disk:
        >>> result = processor.process_single_disk(disk, Path("/output"), 0, 1)

    See Also:
        - OfflineFSFix: Handles guest filesystem modifications
        - Flatten: Snapshot flattening implementation
        - Convert: QEMU-based image format conversion
        - VMDKInspector: Pre-migration validation and risk assessment
    """

    def __init__(
        self,
        logger: logging.Logger,
        args: argparse.Namespace,
        recovery_manager: RecoveryManager | None = None,
    ):
        self.logger = logger
        self.args = args  # Kept for external component compatibility
        self.config = DiskProcessingConfig.from_args(args)
        self.recovery_manager = recovery_manager
        self._buslogic_lock = threading.Lock()
        self._config_lock = threading.Lock()
        self._buslogic_temp_dir: Path | None = None
        self.last_fixer_report: Any = None

    def _choose_workdir(self, out_root: Path) -> Path:
        """Choose working directory for intermediate files."""
        if self.config.workdir:
            return Path(self.config.workdir).expanduser().resolve()
        return out_root / "work"

    @staticmethod
    def _resolve_output_path(to_output: str, out_root: Path, disk_index: int, multi: bool) -> Path:
        """Resolve final output path for a disk, auto-renaming if destination exists."""
        base_output = Path(to_output)
        if multi:
            base_output = base_output.parent / f"{base_output.stem}_disk{disk_index}{base_output.suffix}"
        if not base_output.is_absolute():
            base_output = out_root / base_output
        resolved = base_output.expanduser().resolve()
        if resolved.exists():
            # Auto-rename with timestamp: rhel8.8-fixed-20260219-164532.qcow2
            stem = resolved.stem
            suffix = resolved.suffix
            parent = resolved.parent
            resolved = parent / f"{stem}-{datetime.now().strftime('%Y%m%d-%H%M%S')}{suffix}"
        return resolved

    @staticmethod
    def _throttled_progress_logger(logger: logging.Logger, step_pct: int = 5) -> Callable[[float], None]:
        """Create a throttled progress callback that logs at intervals."""
        if step_pct <= 0:
            step_pct = 5
        last_bucket = {"b": -1}

        def cb(progress: float) -> None:
            b = int((progress * 100.0) // step_pct)
            if b != last_bucket["b"]:
                last_bucket["b"] = b
                if progress < 1.0:
                    logger.info(f"⏳ Conversion progress: {progress:.1%}")
                else:
                    logger.info("✅ Conversion complete")

        return cb

    def log_input_layout(self, vmdk: Path) -> None:
        """Log disk image layout information."""
        suffix = vmdk.suffix.lower()
        disk_type = {
            ".vmdk": "VMDK",
            ".qcow2": "QCOW2",
            ".vhd": "VHD",
            ".vhdx": "VHDX",
            ".raw": "RAW",
            ".img": "RAW",
        }.get(suffix, "disk")

        try:
            st = vmdk.stat()
            self.logger.info(
                f"📥 Input {disk_type}: {vmdk} ({U.human_bytes(st.st_size)})",
                extra={
                    "ctx": {
                        "event": "disk_input",
                        "path": str(vmdk),
                        "size_bytes": st.st_size,
                    }
                },
            )
        except FileNotFoundError:
            self.logger.warning(
                f"📥 Input {disk_type}: {vmdk} (file not found — may have been moved or deleted)"
            )
        except PermissionError:
            self.logger.warning(f"📥 Input {disk_type}: {vmdk} (permission denied — check file ownership)")
        except OSError as e:
            self.logger.debug("Could not stat input disk '%s': %s", vmdk, e)
            self.logger.info(f"📥 Input {disk_type}: {vmdk}")

        # VMDK layout analysis (only relevant for actual VMDKs)
        if suffix == ".vmdk":
            layout, extent = VMDK.guess_layout(self.logger, vmdk)
            Log.trace(
                self.logger,
                "🧩 VMDK.guess_layout: layout=%r extent=%r",
                layout,
                str(extent) if extent else None,
            )
            if layout == "monolithic":
                self.logger.info("VMDK layout: monolithic/binary (no separate extent) ✅")
            elif extent and extent.exists():
                self.logger.info(f"VMDK layout: descriptor + extent ✅ ({extent})")
            else:
                self.logger.warning(f"VMDK layout: descriptor (extent missing?) ⚠️ ({extent})")

    # Several independent "not found / wrong format / parse error" early-outs;
    # each is a distinct terminal outcome for config loading, not true complexity.
    # pylint: disable-next=too-many-return-statements
    def _load_config_file(self, attr_name: str, label: str, emoji: str) -> dict[str, Any] | None:
        """
        Load a JSON/YAML configuration file from a config attribute.

        Generic loader that replaces per-config-type methods. Supports both
        JSON and YAML formats with graceful fallback.

        Args:
            attr_name: Name of the DiskProcessingConfig attribute containing the file path
            label: Human-readable label for log messages (e.g. "cloud-init")
            emoji: Emoji prefix for trace logs

        Returns:
            Parsed config dict, or None if not specified / not found / failed
        """
        p = getattr(self.config, attr_name, None)
        if not p:
            Log.trace(self.logger, "%s %s: no config provided", emoji, label)
            return None
        try:
            config_path = Path(p).expanduser().resolve()
            if not config_path.exists():
                self.logger.warning(f"{label} config not found: {config_path}")
                return None
            Log.trace(self.logger, "%s %s: loading %s", emoji, label, config_path)
            if config_path.suffix.lower() == ".json":
                return json.loads(config_path.read_text(encoding="utf-8"))
            if YAML_AVAILABLE:
                return yaml.safe_load(config_path.read_text(encoding="utf-8"))
            self.logger.warning(f"YAML not available, cannot load {label} config")
            return None
        except json.JSONDecodeError as e:
            self.logger.warning(
                "Failed to parse %s config file '%s' as JSON: %s\n"
                "    Check for syntax errors (missing commas, unquoted keys, trailing commas).",
                label,
                config_path,
                e,
            )
            return None
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Config injection is optional/best-effort; any load failure degrades to "no config".
            self.logger.warning(
                "Failed to load %s config from '%s': %s\n"
                "    Verify the file exists, is readable, and contains valid JSON or YAML.",
                label,
                p,
                e,
            )
            Log.trace(self.logger, "%s load exception", label, exc_info=True)
            return None

    def _is_luks_enabled(self) -> bool:
        """Check if LUKS unlocking is enabled."""
        enabled = self.config.is_luks_enabled()
        Log.trace(self.logger, "🔐 luks enabled: %s", enabled)
        return enabled

    def _fix_buslogic_controller(self, vmdk_path: Path) -> Path:
        """
        Fix BusLogic controller by rewriting VMDK descriptor to LSI Logic.

        BusLogic has no KVM driver, but LSI Logic does. We can inject virtio
        drivers for LSI Logic guests, so changing the descriptor makes migration possible.

        Args:
            vmdk_path: Original VMDK path

        Returns:
            Path to fixed VMDK (temporary copy with modified descriptor)
        """
        self.logger.info("")
        self.logger.info("🔧 Auto-fixing BusLogic controller...")
        self.logger.info('   Changing: ddb.adapterType = "buslogic" → "lsilogic"')

        # Read VMDK descriptor (text-based descriptor file only)
        # Check if this is a text descriptor or binary monolithic VMDK
        try:
            with open(vmdk_path, "rb") as bf:
                header = bf.read(4)
        except FileNotFoundError:
            self.logger.warning("   BusLogic fix skipped: VMDK file not found at '%s'", vmdk_path)
            return vmdk_path
        except PermissionError:
            self.logger.warning("   BusLogic fix skipped: permission denied reading '%s'", vmdk_path)
            return vmdk_path
        if header == b"KDMV":
            # Binary sparse VMDK -- cannot safely modify as text
            # (b"KDMV" and b"\x4b\x44\x4d\x56" are the same 4 bytes; the ASCII
            # form is the readable spelling of the VMDK sparse-file magic number.)
            self.logger.warning("   Binary VMDK detected, skipping BusLogic text fix")
            return vmdk_path

        with open(vmdk_path, encoding="ascii", errors="ignore") as f:
            lines = f.readlines()

        # Modify adapter type
        modified = False
        new_lines = []
        for line in lines:
            if "ddb.adapterType" in line and "buslogic" in line.lower():
                # Change buslogic to lsilogic
                new_line = line.replace("buslogic", "lsilogic").replace("BusLogic", "lsilogic")
                new_lines.append(new_line)
                modified = True
                self.logger.info(f"   Old: {line.strip()}")
                self.logger.info(f"   New: {new_line.strip()}")
            else:
                new_lines.append(line)

        if not modified:
            self.logger.warning("   ⚠️  BusLogic not found in descriptor, skipping fix")
            return vmdk_path

        # Create temporary fixed VMDK in workdir (avoid /tmp space issues)
        workdir = self.config.workdir or "/tmp"
        temp_dir = Path(tempfile.mkdtemp(prefix="h2kvm-buslogic-fix-", dir=workdir))
        with self._buslogic_lock:
            self._buslogic_temp_dir = temp_dir  # Track for cleanup
        fixed_vmdk = temp_dir / vmdk_path.name

        # Write modified descriptor
        with open(fixed_vmdk, "w", encoding="ascii", errors="ignore") as f:
            f.writelines(new_lines)

        # Copy extent file if it exists (for split VMDKs)
        extent_file = vmdk_path.parent / (vmdk_path.stem + "-flat.vmdk")
        if extent_file.exists():
            fixed_extent = temp_dir / extent_file.name
            shutil.copy2(extent_file, fixed_extent)
            self.logger.info(f"   Copied extent: {extent_file.name}")

        self.logger.info(f"   ✅ Fixed VMDK: {fixed_vmdk}")
        self.logger.info("")

        return fixed_vmdk

    # Reports FATAL/HIGH risk findings with per-risk-type remediation advice and an
    # optional auto-fix; the branch/statement count covers each distinct risk category.
    # pylint: disable-next=too-many-branches,too-many-statements
    def _inspect_vmdk(self, disk: Path) -> Any:
        """
        Perform pre-migration disk inspection.

        Analyzes disk image for migration risks including:
        - Controller compatibility (BusLogic, LSI Logic, etc.)
        - Snapshot chains
        - UEFI vs BIOS boot mode
        - Extent file integrity (VMDK-specific)

        Args:
            disk: Path to disk image (VMDK, QCOW2, VHD, etc.)

        Returns:
            Inspection result

        Raises:
            H2KvmError: If FATAL risks detected
        """

        # Skip inspection if disabled
        if self.config.skip_vmdk_inspection:
            Log.trace(self.logger, "🔍 Disk inspection skipped (--skip-vmdk-inspection)")
            return None

        Log.step(self.logger, "Pre-migration validation")
        inspector = VMDKInspector(self.logger)

        try:
            result = inspector.inspect(disk)
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Inspection is a best-effort pre-flight check; any failure must not abort migration.
            self.logger.warning(f"⚠️  Disk inspection failed — continuing without pre-flight checks: {e}")
            Log.trace(self.logger, "💥 Inspection exception", exc_info=True)
            return None

        # Display findings
        if result.risks:
            self.logger.info(
                "🔍 Migration Risk Analysis:",
                extra={
                    "ctx": {
                        "event": "disk_inspection_complete",
                        "disk": str(disk),
                        "risk_count": len(result.risks),
                        "has_fatal": result.has_fatal_risks,
                        "has_high": result.has_high_risks,
                    }
                },
            )
            for risk in result.risks:
                level_icon = {
                    RiskLevel.FATAL: "❌",
                    RiskLevel.HIGH: "⚠️ ",
                    RiskLevel.MEDIUM: "ℹ️ ",
                    RiskLevel.INFO: "💡",
                }.get(risk.level, "•")

                self.logger.info(f"  {level_icon} [{risk.level.value}] {risk.message}")

        # VMDK/virt-inspector boot hints are noisy on legacy MBR disks (false UEFI positives).
        # Firmware is resolved later from partition layout + offline fixer signals.
        if hasattr(result, "boot_mode") and result.boot_mode:
            boot_mode = (
                str(result.boot_mode.value) if hasattr(result.boot_mode, "value") else str(result.boot_mode)
            )
            if boot_mode.upper() == "UEFI":
                self.logger.info(
                    "🔔 VMDK inspection reported UEFI — deferring to firmware resolver "
                    "(partition table + offline analysis)"
                )

        # Warn on FATAL risks but continue (user requested non-blocking mode)
        if result.has_fatal_risks:
            fatal_risks = [r for r in result.risks if r.level == RiskLevel.FATAL]
            self.logger.warning("")
            self.logger.warning("=" * 70)
            self.logger.warning(f"⚠️  FATAL: {len(fatal_risks)} CRITICAL risk(s) detected!")
            self.logger.warning("=" * 70)

            for risk in fatal_risks:
                self.logger.warning(f"   ❌ {risk.message}")

            # Check for BusLogic and auto-fix if detected
            has_buslogic = any("buslogic" in r.message.lower() for r in fatal_risks)

            if has_buslogic:
                self.logger.warning("")
                self.logger.warning("🔧 ATTEMPTING AUTOMATIC BUSLOGIC FIX...")
                self.logger.warning("   Rewriting VMDK descriptor: BusLogic → LSI Logic")
                self.logger.warning("   (LSI Logic has KVM driver + virtio injection support)")

                try:
                    fixed_vmdk = self._fix_buslogic_controller(disk)
                    result.fixed_vmdk_path = fixed_vmdk
                    self.logger.warning("   ✅ BusLogic auto-fix complete!")
                    self.logger.warning(f"   Using fixed VMDK: {fixed_vmdk}")
                except Exception as e:  # pylint: disable=broad-exception-caught
                    # Auto-fix is best-effort; any failure falls back to the original VMDK.
                    self.logger.exception(f"   ❌ BusLogic auto-fix failed: {e}")
                    self.logger.exception("   Migration will continue with original VMDK")

            self.logger.warning("")
            self.logger.warning("💡 Recommended solutions:")

            for risk in fatal_risks:
                if "snapshot" in risk.message.lower():
                    self.logger.warning("   → Consolidate snapshots in VMware before migration")
                    self.logger.warning("      (vSphere: Right-click VM → Snapshots → Consolidate)")
                elif "buslogic" in risk.message.lower():
                    if result.fixed_vmdk_path:
                        self.logger.warning("   ✅ BusLogic auto-fixed: Descriptor rewritten to LSI Logic")
                        self.logger.warning("      Migration will continue with virtio driver injection")
                    else:
                        self.logger.warning(
                            "   → Change controller from BusLogic to LSI Logic or PVSCSI in VMware"
                        )
                        self.logger.warning("      (BusLogic has no KVM driver - VM may not boot)")
                elif "extent" in risk.message.lower() and "missing" in risk.message.lower():
                    self.logger.warning("   → Verify all VMDK files are present (descriptor + extent)")
                    self.logger.warning("      (Re-export VM from vSphere if files are incomplete)")
                elif "size mismatch" in risk.message.lower():
                    self.logger.warning("   → Re-export VMDK from vSphere")
                    self.logger.warning("      (Current extent file appears truncated or corrupted)")

            self.logger.warning("")
            if result.fixed_vmdk_path:
                self.logger.warning("✅ FATAL RISK AUTO-FIXED: Continuing migration with fixed VMDK")
            else:
                self.logger.warning("⚠️  CONTINUING MIGRATION DESPITE FATAL RISKS!")
                self.logger.warning("    Guest may not boot - manual intervention may be required")
            self.logger.warning("=" * 70)
            self.logger.warning("")

        # Warn on HIGH risks but continue
        if result.has_high_risks:
            high_risks = [r for r in result.risks if r.level == RiskLevel.HIGH]
            self.logger.warning("")
            self.logger.warning(
                f"⚠️  {len(high_risks)} HIGH risk(s) detected - migration may require manual fixes"
            )

            # Check for controller mismatch
            has_controller_mismatch = False
            for risk in high_risks:
                if "controller" in risk.message.lower() and (
                    "mismatch" in risk.message.lower() or "initramfs" in risk.message.lower()
                ):
                    has_controller_mismatch = True
                    self.logger.warning("   → h2kvm will rebuild initramfs with virtio drivers")
                elif "uefi" in risk.message.lower():
                    self.logger.warning("   → Use OVMF firmware in libvirt (not SeaBIOS)")

            # Auto-fix controller mismatch if enabled
            # Note: use thread-local lock to avoid race conditions in parallel processing
            if has_controller_mismatch and self.config.vmdk_auto_fix_controller:
                self.logger.info("")
                self.logger.info("Auto-fix enabled: Injecting virtio drivers into initramfs")

                # Ensure regen_initramfs is enabled
                with self._config_lock:
                    if not self.config.regen_initramfs:
                        self.logger.info("   Enabling regen_initramfs for controller fix")
                        self.config.regen_initramfs = True

                    # Add virtio drivers if not already specified
                    if not self.config.initramfs_add_drivers:
                        virtio_drivers = ["virtio", "virtio_blk", "virtio_scsi", "virtio_net", "virtio_pci"]
                        self.config.initramfs_add_drivers = virtio_drivers
                        self.logger.info(f"   Adding drivers: {', '.join(virtio_drivers)}")
                    else:
                        self.logger.info(f"   Using custom drivers: {self.config.initramfs_add_drivers}")

                self.logger.info("")

            self.logger.warning("")

        return result

    def _inspect_and_prepare(self, disk: Path) -> Path:
        """
        Run disk inspection and return the working image path.

        VMDK-specific inspection (descriptor parsing, BusLogic fix) only
        runs for .vmdk files. Other formats skip straight to the working path.
        """
        # Skip VMDK-specific inspection for non-VMDK formats
        if disk.suffix.lower() != ".vmdk":
            Log.trace(self.logger, "Skipping VMDK inspection for %s format", disk.suffix)
            return disk

        inspection_result = self._inspect_vmdk(disk)

        if (
            inspection_result
            and hasattr(inspection_result, "fixed_vmdk_path")
            and inspection_result.fixed_vmdk_path
        ):
            self.logger.info(f"📌 Using auto-fixed VMDK: {inspection_result.fixed_vmdk_path}")
            return inspection_result.fixed_vmdk_path

        return disk

    def _auto_detect_uefi_from_partitions(self, disk: Path) -> None:
        """Capture partition/firmware hints from sfdisk (used by firmware resolver)."""

        def _has_efi(text: str) -> bool:
            t = text.lower()
            return "efi system" in t or "efi_system" in t or "c12a7328-f81f-11d2" in t

        def _partition_scheme(text: str) -> str:
            t = (text or "").lower()
            if "label: gpt" in t or "type=efi" in t:
                return "gpt"
            if "label: dos" in t:
                return "mbr"
            return "unknown"

        def _apply_dump(text: str) -> None:
            scheme = _partition_scheme(text)
            has_efi = _has_efi(text)
            self.args.disk_partition_scheme = scheme
            self.args.disk_has_efi_partition = has_efi
            self.logger.info(
                "Disk firmware hints: scheme=%s efi_partition=%s",
                scheme,
                has_efi,
            )

        # pylint: disable=duplicate-code
        # reason: this subprocess.run(...capture_output=True, timeout=10)
        # shape mirrors similar subprocess wrappers in
        # h2kvm/fixers/offline_fixer.py (lvs LVM scan) -- structurally
        # similar by coincidence, not shared logic; keeping independent
        # avoids coupling unrelated subprocess-invocation code paths.
        try:
            self.logger.info(f"🔍 Auto-detecting boot firmware from {disk.name}...")

            result = subprocess.run(
                ["sfdisk", "--dump", str(disk)],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                _apply_dump(result.stdout)
                return

            nbd_dev = None
            for i in range(15, -1, -1):
                dev = f"/dev/nbd{i}"
                sys_size = Path(f"/sys/block/nbd{i}/size")
                try:
                    if sys_size.exists() and int(sys_size.read_text(encoding="utf-8").strip()) == 0:
                        nbd_dev = dev
                        break
                except (ValueError, OSError):
                    continue
            if not nbd_dev:
                self.logger.warning("No free NBD device for firmware partition scan")
                return

            nbd_result = subprocess.run(
                [
                    "bash",
                    "-c",
                    f"qemu-nbd --connect={nbd_dev} '{disk}' 2>/dev/null && sleep 1 && "
                    f"sfdisk --dump {nbd_dev} 2>/dev/null; "
                    f"qemu-nbd --disconnect {nbd_dev} 2>/dev/null",
                ],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            if nbd_result.stdout and nbd_result.stdout.strip():
                _apply_dump(nbd_result.stdout)
        except FileNotFoundError:
            self.logger.debug("Firmware partition scan skipped: disk image not found at '%s'", disk)
        except PermissionError:
            self.logger.warning(
                "Firmware partition scan skipped for '%s': permission denied. "
                "Run with sudo to enable automatic detection, or set firmware_mode manually.",
                disk.name,
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Firmware auto-detection is a best-effort hint; any unexpected failure must not
            # abort migration (firmware falls back to its default resolution).
            self.logger.debug("Firmware partition scan failed for '%s': %s", disk.name, e)

    def _flatten_if_requested(self, disk: Path, out_root: Path) -> Path:
        """Flatten snapshot chain if --flatten was specified."""
        if not self.config.flatten:
            return disk

        workdir = self._choose_workdir(out_root)
        U.ensure_dir(workdir)
        Log.step(self.logger, f"Flatten snapshots → {workdir}")
        working = Flatten.to_working(
            self.logger,
            disk,
            workdir,
            fmt=self.config.flatten_format,
        )
        Log.ok(self.logger, f"Flattened: {working.name}")
        return working

    def _resolve_report_path(self, out_root: Path, disk_index: int, total_disks: int) -> Path | None:
        """Resolve the report output path if --report was specified."""
        if not self.config.report:
            return None

        rp = Path(self.config.report)
        if total_disks > 1:
            report_path = (
                (out_root / f"{rp.stem}_disk{disk_index}{rp.suffix}") if not rp.is_absolute() else rp
            )
        else:
            report_path = rp if rp.is_absolute() else (out_root / rp)
        Log.trace(self.logger, "🧾 report_path=%s", report_path)
        return report_path

    def _load_all_injection_configs(self) -> dict[str, dict[str, Any] | None]:
        """Load all injection configuration files and return as a dict."""
        config_specs = [
            ("cloud_init_config", "cloud-init", "☁️"),
            ("firstboot_scripts", "firstboot", "🚀"),
            ("network_config_inject", "network-config-inject", "🌐"),
            ("user_config_inject", "user-config-inject", "👤"),
            ("service_config_inject", "service-config-inject", "⚙️"),
            ("hostname_config_inject", "hostname-config-inject", "🏷️"),
        ]

        configs: dict[str, dict[str, Any] | None] = {}
        for attr, label, emoji in config_specs:
            data = self._load_config_file(attr, label, emoji)
            if data is not None:
                Log.trace(
                    self.logger,
                    "%s %s loaded: keys=%s",
                    emoji,
                    label,
                    sorted(data.keys()) if isinstance(data, dict) else type(data).__name__,
                )
            configs[attr] = data

        # Convenience: root_password / ssh_authorized_key auto-build user_config_inject
        user_config_data = configs["user_config_inject"]
        root_password = self.config.root_password
        ssh_authorized_key = self.config.ssh_authorized_key
        if root_password or ssh_authorized_key:
            root_user: dict[str, object] = {"name": "root"}
            if root_password:
                root_user["password"] = root_password
            if ssh_authorized_key:
                root_user["ssh_keys"] = [ssh_authorized_key]
            if user_config_data and isinstance(user_config_data, dict):
                existing_users = user_config_data.get("users", [])
                if isinstance(existing_users, list):
                    existing_users.append(root_user)
                else:
                    user_config_data["users"] = [root_user]
            else:
                user_config_data = {"users": [root_user]}
            configs["user_config_inject"] = user_config_data
            Log.trace(
                self.logger, "Convenience root_password/ssh_authorized_key wired into user_config_inject"
            )

        return configs

    def _run_offline_fixes(
        self,
        working: Path,
        report_path: Path | None,
        configs: dict[str, dict[str, Any] | None],
    ) -> tuple[OfflineFSFix, Path]:
        """
        Run offline filesystem fixes and return (fixer, working_image_path).
        """
        Log.step(self.logger, "Offline filesystem fixes")
        c = self.config
        enable_rdp = resolve_enable_rdp(
            c.enable_rdp,
            guest_os=c.guest_os,
            windows=c.windows,
        )
        fix_config = OfflineFixConfig(
            image=working,
            dry_run=c.dry_run,
            no_backup=c.no_backup,
            print_fstab=c.print_fstab,
            update_grub=not c.no_grub,
            regen_initramfs=c.regen_initramfs,
            fstab_mode=c.fstab_mode,
            report_path=report_path,
            remove_vmware_tools=c.remove_vmware_tools,
            enable_rdp=enable_rdp,
            inject_cloud_init=configs.get("cloud_init_config"),
            firstboot_scripts=configs.get("firstboot_scripts"),
            network_config_inject=configs.get("network_config_inject"),
            user_config_inject=configs.get("user_config_inject"),
            service_config_inject=configs.get("service_config_inject"),
            hostname_config_inject=configs.get("hostname_config_inject"),
            recovery_manager=self.recovery_manager,
            resize=c.resize,
            virtio_drivers_dir=c.virtio_drivers_dir,
            luks_enable=self._is_luks_enabled(),
            luks_passphrase=c.luks_passphrase,
            luks_passphrase_env=c.luks_passphrase_env,
            luks_keyfile=c.luks_keyfile,
            luks_mapper_prefix=c.luks_mapper_prefix,
            conversion_dir=c.conversion_dir,
            allowed_dirs=c.allowed_dirs,
            backend=c.backend,
            container_isolation=c.container_isolation,
        )
        fixer = OfflineFSFix(self.logger, fix_config)

        if c.initramfs_add_drivers:
            fixer.initramfs_add_drivers = c.initramfs_add_drivers
        fixer.serial_console = c.serial_console

        fixer.run()
        self.last_fixer_report = fixer.report

        if fixer.converted_image_path:
            working = fixer.converted_image_path
            self.logger.info(
                f"Using converted image for final conversion: {working.name}",
                extra={"ctx": {"event": "using_converted_image", "converted_image": str(working)}},
            )

        Log.ok(self.logger, "Offline fixes complete")
        return fixer, working

    def _convert_output(
        self, working: Path, out_root: Path, disk_index: int, total_disks: int
    ) -> Path | None:
        """Convert to final output format if --to-output was specified."""
        if not self.config.to_output or self.config.dry_run:
            return None

        out_image = self._resolve_output_path(
            self.config.to_output,
            out_root,
            disk_index=disk_index,
            multi=(total_disks > 1),
        )
        U.ensure_dir(out_image.parent)

        Log.step(self.logger, f"Convert image → {out_image.name}")
        Log.trace(
            self.logger,
            "🧪 convert: in=%s out=%s fmt=%s compress=%s level=%r",
            working,
            out_image,
            self.config.out_format,
            self.config.compress,
            self.config.compress_level,
        )

        progress_callback = self._throttled_progress_logger(self.logger, step_pct=5)
        Convert.convert_image_with_progress(
            self.logger,
            working,
            out_image,
            out_format=self.config.out_format,
            compress=self.config.compress,
            compress_level=self.config.compress_level,
            progress_callback=progress_callback,
        )
        Convert.validate(self.logger, out_image)
        Log.ok(self.logger, f"Validated: {out_image.name}")

        if self.config.checksum:
            cs = U.checksum(out_image)
            self.logger.info(f"🧾 SHA256 checksum: {cs}")

        return out_image

    def _cleanup_intermediates(self, out_image: Path | None, fixer: OfflineFSFix) -> None:
        """Clean up intermediate files after successful processing."""
        # Clean cached conversion if final output was produced
        if (
            out_image
            and fixer.converted_image_path
            and fixer.converted_image_path.exists()
            and fixer.converted_image_path != out_image
            and self.config.cleanup_cache
        ):
            try:
                fixer.converted_image_path.unlink()
                self.logger.info(f"Cleaned up cached conversion: {fixer.converted_image_path}")
            except Exception as e:  # pylint: disable=broad-exception-caught
                # Best-effort temp-file cleanup; must not fail an otherwise-successful run.
                self.logger.warning(f"Failed to clean up cached conversion: {e}")

        # Clean BusLogic temp dir
        buslogic_dir = self._buslogic_temp_dir
        if buslogic_dir and buslogic_dir.exists():
            try:
                shutil.rmtree(buslogic_dir)
                self.logger.debug("Cleaned up buslogic temp dir: %s", buslogic_dir)
            except Exception as e:  # pylint: disable=broad-exception-caught
                # Best-effort temp-dir cleanup; must not fail an otherwise-successful run.
                self.logger.warning("Failed to clean up buslogic temp dir: %s", e)
            self._buslogic_temp_dir = None

    def process_single_disk(self, disk: Path, out_root: Path, disk_index: int, total_disks: int) -> Path:
        """
        Process a single disk through the full pipeline.

        Pipeline stages: inspect → flatten → load configs → offline fixes → convert → cleanup.

        Args:
            disk: Input disk path
            out_root: Output directory root
            disk_index: Index of this disk (for naming)
            total_disks: Total number of disks being processed

        Returns:
            Path to final output image
        """
        Log.step(
            self.logger,
            f"Processing disk {disk_index + 1}/{total_disks}: {disk.name}",
            disk_index=disk_index,
            total_disks=total_disks,
            disk=str(disk),
        )
        Log.trace(self.logger, "🧱 process_single_disk: disk=%s out_root=%s", disk, out_root)

        with TraceContext(vm_id=disk.name, workflow="disk_processing", component="disk_processor"):
            self.log_input_layout(disk)

            # Stage 1: Inspect and prepare (BusLogic auto-fix)
            with PhaseTimer("vmdk_inspect_start", "vmdk_inspect_complete", phase="inspection"):
                working = self._inspect_and_prepare(disk)

            # Stage 2: Flatten snapshots if requested
            working = self._flatten_if_requested(working, out_root)

            # Stage 2.5: Auto-detect UEFI from partition table (EFI System Partition)
            self._auto_detect_uefi_from_partitions(working)

            # Stage 3: Load injection configs
            report_path = self._resolve_report_path(out_root, disk_index, total_disks)
            configs = self._load_all_injection_configs()

            # Stage 4: Offline filesystem fixes
            with PhaseTimer("offline_fix_start", "offline_fix_complete", phase="offline_fixes"):
                fixer, working = self._run_offline_fixes(working, report_path, configs)

            # Stage 5: Convert to output format
            with PhaseTimer("convert_start", "convert_complete", phase="conversion"):
                out_image = self._convert_output(working, out_root, disk_index, total_disks)

            # Stage 6: Cleanup intermediates
            self._cleanup_intermediates(out_image, fixer)

            log_event("disk_processing_complete", disk=disk.name, disk_index=disk_index, status="success")

        return out_image if out_image else working

    # Worker-count resolution, futures dispatch, per-disk result/error bookkeeping, and final
    # aggregation each need their own locals; splitting further would obscure the pipeline shape.
    # pylint: disable-next=too-many-locals
    def process_disks_parallel(self, disks: list[Path], out_root: Path) -> list[Path]:
        """
        Process multiple disks in parallel.

        Args:
            disks: List of disk paths to process
            out_root: Output directory root

        Returns:
            List of output image paths
        """
        self.logger.info(
            f"🧵 Processing {len(disks)} disks in parallel",
            extra={
                "ctx": {
                    "event": "parallel_disk_processing_start",
                    "disk_count": len(disks),
                    "disks": [str(d) for d in disks],
                }
            },
        )
        Log.trace(self.logger, "🧵 process_disks_parallel: out_root=%s", out_root)

        results: list[Path | None] = [None] * len(disks)

        env_workers = os.environ.get("VMDK2KVM_WORKERS")
        if env_workers:
            try:
                max_workers = max(1, int(env_workers))
            except (ValueError, TypeError):
                max_workers = min(4, len(disks), effective_cpu_count())
        else:
            max_workers = min(4, len(disks), effective_cpu_count())

        Log.trace(
            self.logger,
            "👷 parallel workers: max_workers=%d (env=%r cpu=%r)",
            max_workers,
            env_workers,
            effective_cpu_count(),
        )

        errors: list[tuple[int, Path, BaseException]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.process_single_disk, disk, out_root, idx, len(disks)): idx
                for idx, disk in enumerate(disks)
            }
            for future in concurrent.futures.as_completed(futures):
                idx = futures[future]
                disk = disks[idx]
                try:
                    result = future.result()
                    results[idx] = result
                    self.logger.info(
                        f"✅ Completed processing disk {idx + 1}/{len(disks)}: {disk.name}",
                        extra={
                            "ctx": {
                                "event": "disk_processing_complete",
                                "disk_index": idx,
                                "disk_name": disk.name,
                                "total_disks": len(disks),
                            }
                        },
                    )
                except Exception as e:  # pylint: disable=broad-exception-caught
                    # Any per-disk failure (of many possible causes across the whole pipeline)
                    # must be captured and reported without killing sibling worker threads.
                    errors.append((idx, disk, e))
                    self.logger.exception(
                        "Failed processing disk %d/%d ('%s'): %s\n"
                        "    Parallel mode requires every disk to succeed — aborting migration.\n"
                        "    Re-run with --verbose for detailed error information.",
                        idx + 1,
                        len(disks),
                        disk.name,
                        e,
                    )
                    self.logger.debug(
                        "Parallel disk processing exception for disk %d (%s)",
                        idx,
                        disk,
                        exc_info=True,
                    )

        out = [r for r in results if r is not None]
        if len(out) != len(disks):
            failed = [disks[i] for i, r in enumerate(results) if r is None]
            names = ", ".join(p.name for p in failed[:8])
            suffix = f" (+{len(failed) - 8} more)" if len(failed) > 8 else ""
            msg = (
                f"Parallel disk processing failed: {len(failed)}/{len(disks)} disk(s) did not complete "
                f"({names}{suffix}). The migration cannot be reported as successful."
            )
            if errors:
                raise Fatal(1, msg) from errors[0][2]
            raise Fatal(1, msg)
        Log.trace(self.logger, "📦 process_disks_parallel: outputs=%d", len(out))
        return out
