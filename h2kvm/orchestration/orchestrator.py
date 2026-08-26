# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# pylint: disable=too-many-lines  # cohesive end-to-end migration orchestrator; splitting would hurt readability more than help
"""
Main orchestrator for VM migration workflows.

Coordinates the end-to-end migration process including source acquisition,
disk conversion, fixing, and libvirt domain creation.
"""
# h2kvm/orchestrator/orchestrator.py

from __future__ import annotations

import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING, Any

from h2kvm.config.pipeline_config import MigrationConfig
from h2kvm.core.exceptions import Fatal, H2KvmError, create_helpful_error
from h2kvm.core.firmware_resolver import (
    FirmwareResolution,
    FirmwareSignals,
    normalize_user_firmware_mode,
    resolve_firmware,
)
from h2kvm.core.logger import Log
from h2kvm.core.recovery_manager import RecoveryManager
from h2kvm.core.sanity_checker import SanityChecker
from h2kvm.core.structured_log import PhaseTimer, log_event
from h2kvm.core.utils import U
from h2kvm.libvirt.domain_emitter import emit_from_args
from h2kvm.providers.vmware.vsphere.mode import VsphereMode
from h2kvm.quality.testing.libvirt_tester import LibvirtTest
from h2kvm.quality.testing.qemu_tester import QemuTest

from .azure_exporter import AzureExporter
from .disk_discovery import DiskDiscovery
from .disk_processor import DiskProcessor
from .vsphere_exporter import VsphereExporter

if TYPE_CHECKING:
    import argparse
    import logging

# Check availability
try:
    from h2kvm.providers.vmware.clients.client import PYVMOMI_AVAILABLE
except ImportError:
    PYVMOMI_AVAILABLE = False

try:
    from h2kvm.providers.vmware.transports.http_client import REQUESTS_AVAILABLE
except ImportError:
    REQUESTS_AVAILABLE = False


class Orchestrator:  # pylint: disable=too-many-instance-attributes  # coordinates many independent handler components across the migration pipeline
    """
    Main pipeline orchestrator for VM migration workflows.

    Coordinates all phases of VM migration including:
    - Source discovery (vSphere, Azure, local files)
    - Disk format conversion (VMDK, OVA, VHD → QCOW2)
    - Offline guest fixes (fstab, bootloader, drivers)
    - Validation and testing (libvirt, QEMU)
    - Recovery management (checkpoint/resume)

    Supported source types:
        - local: Local VMDK/OVA/VHD files
        - vsphere: VMware vCenter/ESXi
        - azure: Azure VMs
        - ova: OVA archives
        - ovf: OVF packages

    Attributes:
        logger: Logger instance for status/error reporting
        args: Parsed command-line arguments
        recovery_manager: Optional recovery manager for resumable operations
        disks: List of discovered disk files to process
        vsphere_exporter: Handler for vSphere exports
        azure_exporter: Handler for Azure exports
        disk_discovery: Component for finding/validating disk files
        disk_processor: Component for conversion and fixing

    Examples:
        >>> logger = logging.getLogger(__name__)
        >>> args = parse_args_with_config()
        >>> orchestrator = Orchestrator(logger, args)
        >>> orchestrator.run()  # Execute full pipeline
    """

    def __init__(self, logger: logging.Logger, args: argparse.Namespace):
        self.logger = logger
        self.args = args  # Kept for external component compatibility
        self.config = MigrationConfig.from_args(args)
        self.recovery_manager: RecoveryManager | None = None
        self.disks: list[Path] = []
        self._ai = None  # AIOrchestrator (fail-safe, optional)

        # Initialize component handlers
        # Note: using only internal converters
        self.vsphere_exporter = VsphereExporter(logger, args)
        self.azure_exporter = AzureExporter(logger, args)
        self.disk_discovery = DiskDiscovery(logger, args)
        self.disk_processor: DiskProcessor | None = None  # Created after recovery setup

        Log.trace(
            self.logger,
            "🧠 Orchestrator init: cmd=%r output_dir=%r batch=%r",
            self.config.cmd,
            self.config.output_dir,
            self.config.batch_manifest,
        )

    def _handle_batch_mode(self) -> None:
        """Handle batch conversion mode."""
        # pylint: disable-next=import-outside-toplevel,cyclic-import  # avoids loading the whole batch subsystem for the common single-VM path
        from .manifest.batch_orchestrator import BatchOrchestrator

        batch_manifest_path = self.config.batch_manifest
        self.logger.info(
            "🔄 Batch mode detected",
            extra={"ctx": {"event": "batch_mode_start", "manifest": str(batch_manifest_path)}},
        )
        self.logger.info(f"📋 Batch manifest: {batch_manifest_path}")

        try:
            batch_orchestrator = BatchOrchestrator(batch_manifest_path, logger=self.logger)
            report = batch_orchestrator.run()

            # Overall success/failure
            if report["batch"]["success"]:
                self.logger.info(
                    "✅ All VMs converted successfully",
                    extra={
                        "ctx": {
                            "event": "batch_complete",
                            "success": True,
                            "total_vms": report["batch"]["total_vms"],
                        }
                    },
                )
            else:
                failed = report["batch"]["failed_vms"]
                total = report["batch"]["total_vms"]
                self.logger.warning(
                    f"⚠️  Batch completed with {failed}/{total} failures",
                    extra={
                        "ctx": {
                            "event": "batch_complete",
                            "success": False,
                            "failed_vms": failed,
                            "total_vms": total,
                        }
                    },
                )

        except Exception as e:  # pylint: disable=broad-exception-caught  # top-level batch-mode handler must report any failure and exit cleanly, not crash
            self.logger.debug("Batch mode exception details", exc_info=True)
            U.die(
                self.logger,
                f"Batch conversion failed: {e}\n"
                "    Check the batch manifest file for syntax errors and verify all referenced VM manifests exist.\n"
                "    Re-run with --verbose for detailed logs.",
                1,
            )

    def _setup_recovery(self, out_root: Path) -> None:
        """Setup recovery manager if enabled."""
        if self.config.enable_recovery:
            recovery_dir = out_root / "recovery"
            self.recovery_manager = RecoveryManager(self.logger, recovery_dir)
            self.logger.info(
                f"🛟 Recovery mode enabled: {recovery_dir}",
                extra={"ctx": {"event": "recovery_mode_enabled", "recovery_dir": str(recovery_dir)}},
            )
            # Now create disk processor with recovery manager
            self.disk_processor = DiskProcessor(self.logger, self.args, self.recovery_manager)
        else:
            Log.trace(self.logger, "🛟 Recovery mode disabled")
            self.disk_processor = DiskProcessor(self.logger, self.args, None)

    def load_checkpoint(self) -> dict[str, Any] | None:
        """
        Load the last checkpoint and return its progress state.

        Reads the most recent completed checkpoint from the recovery directory,
        validates its integrity, and returns the saved progress data.  This
        includes which disks have already been processed (``completed_disks``)
        and which are still pending (``pending_disks``).

        Returns:
            A dict with checkpoint data if a valid checkpoint exists, or
            ``None`` when no checkpoint is available or recovery is disabled.
        """
        if not self.recovery_manager:
            Log.trace(self.logger, "load_checkpoint: recovery not enabled, nothing to load")
            return None

        # Try the fast-path pointer first (latest completed checkpoint)
        checkpoint_data = self.recovery_manager.recover_from_checkpoint(
            "disk_processing",
            allow_same_stage=True,
            allow_later_stage=True,
            prefer_pointer=True,
        )

        if checkpoint_data is not None:
            self.logger.info(
                "Loaded checkpoint: completed=%d pending=%d",
                len(checkpoint_data.get("completed_disks", [])),
                len(checkpoint_data.get("pending_disks", [])),
                extra={
                    "ctx": {
                        "event": "checkpoint_loaded",
                        "completed_count": len(checkpoint_data.get("completed_disks", [])),
                        "pending_count": len(checkpoint_data.get("pending_disks", [])),
                    }
                },
            )
            return checkpoint_data

        # Fallback: try the discovery checkpoint (at least we know which disks
        # were originally discovered)
        discovery_data = self.recovery_manager.recover_from_checkpoint(
            "disks_discovered",
            allow_same_stage=True,
            allow_later_stage=False,
            prefer_pointer=True,
        )
        if discovery_data is not None:
            self.logger.info(
                "Loaded discovery checkpoint (no processing progress yet): disks=%d",
                discovery_data.get("count", 0),
                extra={"ctx": {"event": "discovery_checkpoint_loaded"}},
            )
            return discovery_data

        self.logger.debug("No checkpoint found to resume from")
        return None

    def _save_disk_progress(
        self,
        all_disks: list[Path],
        completed_disks: list[Path],
        pending_disks: list[Path],
        fixed_images: list[Path],
    ) -> None:
        """
        Persist the current disk-processing progress to a checkpoint.

        Args:
            all_disks: The full list of disks originally discovered.
            completed_disks: Disks that have been successfully processed.
            pending_disks: Disks that still need processing.
            fixed_images: Output images produced so far.
        """
        if not self.recovery_manager:
            return

        progress_data = {
            "all_disks": [str(d) for d in all_disks],
            "completed_disks": [str(d) for d in completed_disks],
            "pending_disks": [str(d) for d in pending_disks],
            "fixed_images": [str(img) for img in fixed_images],
            "total": len(all_disks),
            "done": len(completed_disks),
            "remaining": len(pending_disks),
        }

        self.recovery_manager.save_checkpoint("disk_processing", progress_data)
        self.recovery_manager.mark_checkpoint_complete("disk_processing")

        Log.trace(
            self.logger,
            "Saved disk progress checkpoint: done=%d remaining=%d",
            len(completed_disks),
            len(pending_disks),
        )

    @staticmethod
    def _require_dependency(
        available: bool, name: str, solutions: list[str], causes: list[str], doc_link: str
    ) -> None:
        """Raise a helpful Fatal error if a required dependency is not available."""
        if not available:
            raise create_helpful_error(
                Fatal,
                f"{name} not installed",
                code=2,
                solutions=solutions,
                causes=causes,
                doc_link=doc_link,
            )

    def _discover_exported_disks(self, out_root: Path) -> list[Path]:
        """Discover VMDK/qcow2/raw disk images in output directory after vSphere export."""
        pats = ["**/*.vmdk", "**/*.qcow2", "**/*.raw", "**/*.img", "**/*.ova", "**/*.vhd", "**/*.vhdx"]
        disks: list[Path] = []
        for pat in pats:
            for p in sorted(out_root.glob(pat)):
                if p.is_file() and p.stat().st_size > 0:
                    disks.append(p)
        if disks:
            self.logger.info(
                "📦 Discovered %d exported disk(s) for pipeline: %s", len(disks), [str(d) for d in disks]
            )
        return disks

    def _accept_export(self, exported: list[Path] | None, source_name: str) -> bool:
        """Store exported disks and return True if export produced results."""
        if exported:
            self.disks = exported
            self.logger.info(
                "📦 %s export produced %d disk(s)",
                source_name,
                len(self.disks),
                extra={
                    "ctx": {"event": f"{source_name.lower()}_export_complete", "disk_count": len(self.disks)}
                },
            )
            return True
        self.logger.warning(f"{source_name} export produced no disks")
        return False

    def _handle_vsphere_mode(self, out_root: Path) -> bool:
        """
        Handle vSphere mode operations.

        Returns:
            True if handled and should continue pipeline, False if should exit
        """
        self._require_dependency(
            PYVMOMI_AVAILABLE,
            "pyvmomi",
            solutions=[
                "Install pyvmomi: pip install pyvmomi",
                "Or install with vSphere support: pip install h2kvm[vsphere]",
            ],
            causes=["pyvmomi package not found in Python environment", "Virtual environment not activated"],
            doc_link="02-Installation.md#vsphere-integration",
        )

        vs_action = self.config.vs_action
        if vs_action in ("download_datastore_file", "download_vm_disk", "cbt_sync"):
            self._require_dependency(
                REQUESTS_AVAILABLE,
                "requests library",
                solutions=[
                    "Install requests: pip install requests",
                    "Required for HTTP downloads and vCenter API calls",
                ],
                causes=["requests package not installed", "Missing optional dependencies"],
                doc_link="02-Installation.md#python-dependencies",
            )

        # Check if vSphere export (sync) mode enabled
        if self.vsphere_exporter.is_export_enabled():
            U.banner(self.logger, "vSphere export (sync)")
            exported = self.vsphere_exporter.export_many_sync(out_root)
            if self._accept_export(exported, "vSphere"):
                return True
            self.logger.warning("Falling back to VsphereMode")
            VsphereMode(self.logger, self.args).run()
            return False

        # Standard vsphere mode (govc export_vm, ovftool_export, etc.)
        VsphereMode(self.logger, self.args).run()

        # After export, check if there are downstream pipeline steps requested
        # (flatten, to_output, regen_initramfs, emit_domain_xml, libvirt_test, etc.)
        has_pipeline = any(
            [
                getattr(self.args, "flatten", False),
                getattr(self.args, "to_output", None),
                getattr(self.args, "regen_initramfs", False),
                getattr(self.args, "emit_domain_xml", False),
                getattr(self.args, "libvirt_test", False),
            ]
        )

        # Normalize action for comparison
        norm_action = str(vs_action or "").strip().lower().replace("-", "_")
        export_actions = {"export_vm", "ovftool_export", "export", "exportvm", "export_vmin"}
        if has_pipeline and norm_action in export_actions:
            # Discover exported VMDKs/images in output directory
            exported = self._discover_exported_disks(out_root)
            if self._accept_export(exported, "vSphere (govc/ovftool)"):
                return True
            self.logger.info("vSphere export completed (no downstream pipeline)")

        return False

    def _handle_azure_mode(self, out_root: Path) -> bool:
        """
        Handle Azure mode operations.

        Returns:
            True if handled and should continue pipeline, False if should exit
        """
        if self.azure_exporter.is_enabled():
            U.banner(self.logger, "Azure export")
            exported = self.azure_exporter.export_vms(out_root)
            return self._accept_export(exported, "Azure")
        return True  # Not Azure mode, continue

    def _discover_disks(self, out_root: Path) -> Path | None:
        """
        Discover disks from various sources.

        Returns:
            temp_dir if cleanup needed, None otherwise
        """
        cmd = self.config.cmd
        Log.trace(self.logger, "🧭 _discover_disks: cmd=%r", cmd)

        if cmd == "azure":
            should_continue = self._handle_azure_mode(out_root)
            if not should_continue:
                return None  # Azure mode handled everything

        if cmd == "vsphere":
            should_continue = self._handle_vsphere_mode(out_root)
            if not should_continue:
                return None  # VsphereMode handled everything

        # Use DiskDiscovery for all other modes
        if not self.disks:  # Only if vsphere/azure didn't already populate
            self.disks, temp_dir = self.disk_discovery.discover(out_root)
            return temp_dir

        return None

    def _process_disks(  # pylint: disable=too-many-locals  # tracks recovery-checkpoint state alongside the disk-processing loop
        self, out_root: Path
    ) -> list[Path]:
        """
        Process disks through internal pipeline.

        When recovery is enabled, loads the last checkpoint and skips
        already-completed disks so the pipeline resumes where it left off.
        After each disk completes, progress is saved to a new checkpoint.
        """
        if not self.disk_processor:
            raise Fatal(
                code=1,
                msg=(
                    "Migration pipeline not fully initialized — the disk processor was not created. "
                    "This is an internal error. Please report it at "
                    "https://github.com/ssahani/h2kvm/issues with your config and logs."
                ),
            )

        Log.trace(
            self.logger,
            "_process_disks: disks=%d parallel=%s",
            len(self.disks),
            self.config.parallel_processing,
        )

        # --- Checkpoint-aware resume logic ---
        completed_disk_strs: set[str] = set()
        resumed_images: list[Path] = []

        checkpoint_data = self.load_checkpoint()
        if checkpoint_data and checkpoint_data.get("completed_disks"):
            completed_disk_strs = set(checkpoint_data["completed_disks"])
            # Restore previously produced images
            for img_str in checkpoint_data.get("fixed_images", []):
                img_path = Path(img_str)
                if img_path.exists():
                    resumed_images.append(img_path)
            self.logger.info(
                "Resuming from checkpoint: %d disk(s) already done, %d pending",
                len(completed_disk_strs),
                len(self.disks) - len(completed_disk_strs),
                extra={
                    "ctx": {
                        "event": "checkpoint_resume",
                        "completed": len(completed_disk_strs),
                        "pending": len(self.disks) - len(completed_disk_strs),
                    }
                },
            )

        # Separate disks into already-done and still-pending
        pending_disks = [d for d in self.disks if str(d) not in completed_disk_strs]
        completed_disks = [d for d in self.disks if str(d) in completed_disk_strs]

        if not pending_disks:
            self.logger.info(
                "All %d disk(s) already processed (checkpoint resume), nothing to do",
                len(self.disks),
            )
            return resumed_images

        # --- Parallel path (no per-disk checkpointing) ---
        if len(pending_disks) > 1 and self.config.parallel_processing:
            self.logger.info(
                "Processing %d disk images in parallel (multiple disks for this VM; "
                "each path is distinct — not multiple separate migration jobs).",
                len(pending_disks),
                extra={"ctx": {"event": "parallel_disk_processing", "disk_count": len(pending_disks)}},
            )
            new_images = self.disk_processor.process_disks_parallel(pending_disks, out_root)
            all_images = resumed_images + new_images
            # Save final progress
            self._save_disk_progress(
                self.disks,
                completed_disks=list(self.disks),
                pending_disks=[],
                fixed_images=all_images,
            )
            return all_images

        # --- Sequential path with per-disk checkpointing ---
        fixed_images: list[Path] = list(resumed_images)
        total_disks = len(self.disks)

        for disk in pending_disks:
            if not disk.exists():
                U.die(self.logger, f"Disk not found: {disk}", 1)

            # Use original index for logging consistency
            original_idx = self.disks.index(disk)
            result = self.disk_processor.process_single_disk(
                disk,
                out_root,
                original_idx,
                total_disks,
            )
            fixed_images.append(result)
            completed_disks.append(disk)

            # Remaining disks after this one
            still_pending = [d for d in pending_disks if d not in completed_disks]

            # Save progress after each disk so we can resume
            self._save_disk_progress(
                all_disks=self.disks,
                completed_disks=completed_disks,
                pending_disks=still_pending,
                fixed_images=fixed_images,
            )

        Log.trace(self.logger, "_process_disks: produced=%d", len(fixed_images))
        return fixed_images

    def _get_vm_test_params(self) -> dict[str, object]:
        """Extract common VM test parameters from config."""
        params: dict[str, object] = {
            "memory_mib": self.config.memory,
            "vcpus": self.config.vcpus,
            "uefi": self.config.uefi,
        }
        # Windows guests need SATA disk bus on first boot (bootstrap stage)
        is_windows = (
            self.config.windows
            or self.config.guest_os == "windows"
            or getattr(self.args, "guest_os", "") == "windows"
        )
        if is_windows:
            params["guest_os"] = "windows"
            params["windows_stage"] = "bootstrap"
        return params

    def _run_tests(self, out_images: list[Path], *, emitted_xml: Path | None = None) -> None:
        """Run validation tests if requested."""
        if not out_images:
            return

        test_image = out_images[0]

        if self.config.libvirt_test:
            network = self.config.libvirt_network

            # Auto-create network from inline config if provided
            if self.config.libvirt_network_config:
                network = LibvirtTest.create_network_from_config(
                    self.logger,
                    self.config.libvirt_network_config,
                )

            Log.step(self.logger, "Libvirt smoke test")

            if not emitted_xml or not emitted_xml.exists():
                self.logger.warning("No emitted domain XML found; skipping libvirt test")
                return

            # Use the emitted domain XML — same code path as production.
            # This ensures the smoke test exercises the exact XML the user
            # would use (SATA bootstrap, virtio-win CDROM, Hyper-V, etc.).
            # Read actual domain name from XML (may have been renamed on conflict).
            actual_name = self.config.vm_name
            try:
                _tree = ET.parse(emitted_xml)
                _name_el = _tree.getroot().find("name")
                if _name_el is not None and _name_el.text:
                    actual_name = _name_el.text
            except (OSError, ET.ParseError, AttributeError):
                pass
            LibvirtTest.run_from_xml(
                self.logger,
                emitted_xml,
                name=actual_name,
                network=network,
                timeout_s=self.config.timeout,
                keep=self.config.keep_domain,
                health_check=self.config.health_check,
                health_check_timeout_s=self.config.health_check_timeout,
            )
            Log.ok(self.logger, "Libvirt test complete")

        if self.config.qemu_test:
            vm_params = self._get_vm_test_params()
            Log.step(self.logger, "QEMU smoke test")
            QemuTest.run(self.logger, test_image, **vm_params)
            Log.ok(self.logger, "QEMU test complete")

    def _deploy_to_kubernetes(self, out_images: list[Path]) -> None:
        """Deploy migrated VMs to Kubernetes/k3s cluster."""
        try:
            # pylint: disable-next=import-outside-toplevel  # optional deployer, only needed when targeting Kubernetes
            from h2kvm.infrastructure.deployers.kubernetes import deploy_to_kubernetes

            self.logger.info("")
            self.logger.info("=" * 80)
            self.logger.info("Kubernetes/k3s Deployment")
            self.logger.info("=" * 80)

            # Deploy each image
            for img in out_images:
                if str(img).endswith(".qcow2"):
                    try:
                        result = deploy_to_kubernetes(self.logger, self.args, str(img))
                        self.logger.info("")
                        self.logger.info(f"✅ Deployed: {result['vm_name']}")
                        self.logger.info(f"   Namespace: {result['namespace']}")
                        self.logger.info(f"   PVC: {result['pvc_name']}")
                        if result.get("vm_started"):
                            self.logger.info("   Status: Running")
                        else:
                            self.logger.info("   Status: Created (not started)")
                            self.logger.info(
                                "   To start: kubectl patch vm %s -n %s --type merge "
                                '-p \'{"spec":{"running":true}}\'',
                                result["vm_name"],
                                result["namespace"],
                            )
                    except Exception as e:  # pylint: disable=broad-exception-caught  # one image's deployment failure must not abort the rest
                        err_text = (
                            e.user_message(include_context=True) if isinstance(e, H2KvmError) else str(e)
                        )
                        self.logger.exception(
                            "Kubernetes deployment failed for image '%s': %s",
                            img,
                            err_text,
                        )
                        if not isinstance(e, H2KvmError):
                            self.logger.exception(
                                "    Verify the Kubernetes cluster is reachable (kubectl cluster-info)\n"
                                "    and that KubeVirt is installed (kubectl get crd virtualmachines.kubevirt.io).",
                            )
                        self.logger.debug("Kubernetes deploy exception details", exc_info=True)
                        if not self.config.k8s_continue_on_error:
                            footer = (
                                "\nTo continue despite deployment failures, use --k8s-continue-on-error."
                            )
                            raise Fatal(
                                code=1,
                                msg=(f"Kubernetes deployment failed for '{img.name}':\n{err_text}" + footer),
                            ) from e
                else:
                    self.logger.warning(f"Skipping non-QCOW2 image: {img}")

            self.logger.info("")
            self.logger.info("=" * 80)

        except ImportError as e:
            raise Fatal(
                code=2,
                msg=(
                    "Kubernetes deployment requires the 'kubernetes' Python package, which is not installed.\n"
                    "Install with: pip install kubernetes\n"
                    "Or install with KubeVirt support: pip install h2kvm[kubernetes]"
                ),
            ) from e

    def _deploy_to_openstack(self, out_images: list[Path]) -> None:
        """Upload converted disks to OpenStack Glance; optionally boot Nova."""
        try:
            # pylint: disable-next=import-outside-toplevel  # optional deployer, only needed when targeting OpenStack
            from h2kvm.infrastructure.deployers.openstack import deploy_to_openstack

            self.logger.info("")
            self.logger.info("=" * 80)
            self.logger.info("OpenStack deployment")
            self.logger.info("=" * 80)

            qcow2_images = [img for img in out_images if str(img).endswith(".qcow2")]
            if len(qcow2_images) > 1:
                self.logger.warning(
                    "deploy_openstack uploads one Glance image per migration; "
                    "using %s and skipping %d other qcow2 disk(s)",
                    qcow2_images[0].name,
                    len(qcow2_images) - 1,
                )
                qcow2_images = qcow2_images[:1]

            for img in qcow2_images:
                if not str(img).endswith(".qcow2"):
                    self.logger.warning("Skipping non-QCOW2 image: %s", img)
                    continue
                try:
                    result = deploy_to_openstack(self.logger, self.args, str(img))
                    if result.get("dry_run"):
                        continue
                    self.logger.info("")
                    self.logger.info("Uploaded to Glance: %s", result.get("glance_name"))
                    self.logger.info("   Image ID: %s", result.get("image_id"))
                    if result.get("server_id"):
                        self.logger.info(
                            "   Instance: %s (%s)", result.get("server_name"), result.get("server_id")
                        )
                except Exception as e:  # pylint: disable=broad-exception-caught  # one image's deployment failure must not abort the rest
                    err_text = (
                        e.user_message(include_context=True) if isinstance(e, H2KvmError) else str(e)
                    )
                    self.logger.exception("OpenStack deployment failed for '%s': %s", img, err_text)
                    if not self.config.openstack_continue_on_error:
                        raise Fatal(
                            code=1,
                            msg=f"OpenStack deployment failed for '{img.name}':\n{err_text}",
                        ) from e

            self.logger.info("")
            self.logger.info("=" * 80)

        except ImportError as e:
            raise Fatal(
                code=2,
                msg=(
                    "OpenStack deployment requires openstacksdk.\n"
                    "Install with: pip install 'h2kvm[openstack]'"
                ),
            ) from e

    # Daemon mode registry: (flag_attr, dir_attr, error_message, module_path, class_name)
    _DAEMON_MODES = [
        (
            "manifest_workflow_mode",
            "manifest_workflow_dir",
            "Manifest workflow mode requires --manifest-workflow-dir",
            "h2kvm.runtime.daemon.manifest_workflow_daemon",
            "ManifestWorkflowDaemon",
        ),
        (
            "workflow_mode",
            "workflow_dir",
            "Workflow mode requires --workflow-dir or config: workflow_dir",
            "h2kvm.runtime.daemon.workflow_daemon",
            "WorkflowDaemon",
        ),
    ]

    def _run_daemon_mode(self) -> None:
        """Dispatch to the appropriate daemon mode based on args flags."""
        # pylint: disable-next=import-outside-toplevel  # dynamic dispatch avoids importing every daemon subsystem module
        from importlib import import_module

        # Check specialized daemon modes first (manifest workflow, workflow)
        for flag_attr, dir_attr, error_msg, module_path, class_name in self._DAEMON_MODES:
            if getattr(self.config, flag_attr, False):
                if not getattr(self.config, dir_attr, None):
                    raise Fatal(2, error_msg)
                mod = import_module(module_path)
                daemon_cls = getattr(mod, class_name)
                daemon_cls(self.logger, self.args).run()
                return

        # Standard daemon mode (fallback)
        if not self.config.watch_dir:
            raise Fatal(2, "Daemon mode requires --watch-dir or config: watch_dir")

        from h2kvm.runtime.daemon.daemon_watcher import (  # pylint: disable=import-outside-toplevel  # daemon subsystem only needed when this mode is selected
            DaemonWatcher,
        )

        DaemonWatcher(self.logger, self.args).run()

    def _apply_windows_virtio_deploy(self, out_images: list[Path]) -> None:
        """Apply Windows VirtIO deployment fixes if this is a Windows migration."""
        self.logger.debug(
            "Checking Windows VirtIO deploy: config.windows=%s config.guest_os=%s",
            self.config.windows,
            self.config.guest_os,
        )
        # Check all config sources. YAML values don't always propagate to argparse
        # due to store_true defaults, so we check self.config (MigrationConfig) which
        # reads from args, AND the raw config files that were loaded during init.
        is_windows = (
            self.config.windows
            or self.config.guest_os == "windows"
            or getattr(self.args, "windows", False)
            or getattr(self.args, "guest_os", "") == "windows"
        )
        if not is_windows or not out_images:
            return

        # Skip if staged boot is enabled — the injector handles everything
        if self.config.virtio_deploy_boot:
            self.logger.debug("Skipping legacy VirtIO deploy — staged boot will handle it")
            return

        virtio_iso = (
            self.config.virtio_drivers_dir
            or getattr(self.args, "virtio_drivers_dir", None)
            or getattr(self.args, "virtio_win_iso", None)
            or getattr(self.args, "win_driver_iso", None)
        )

        custom_pnp = self.config.custom_pnp_drivers or getattr(self.args, "custom_pnp_drivers", None) or []

        if not virtio_iso and not custom_pnp:
            self.logger.debug("No VirtIO ISO or custom PnP drivers specified — skipping VirtIO deploy")
            return

        try:
            # pylint: disable-next=import-outside-toplevel  # optional Windows-only fixer, only needed for VirtIO deploy
            from h2kvm.fixers.windows.virtio_deploy import WindowsVirtioDeployer

            qcow2 = str(out_images[0])
            self.logger.info("➡️ Windows VirtIO deployment (offline registry fix)...")

            deployer = WindowsVirtioDeployer(
                qcow2_path=qcow2,
                virtio_iso=virtio_iso,
                custom_pnp_drivers=custom_pnp,
            )
            result = deployer.prepare_offline()

            if result.success:
                self.logger.info(
                    "✅ VirtIO deploy: %d VMware services disabled, %d custom drivers staged, RunOnce=%s",
                    len(result.vmware_services_disabled),
                    len(result.custom_drivers_staged),
                    result.runonce_set,
                )
            else:
                self.logger.warning("⚠️  VirtIO deploy had issues: %s", result.errors)

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort deployment step, must not abort the whole migration
            self.logger.warning("⚠️  VirtIO driver deployment failed and was skipped: %s", e)
            self.logger.debug("💥 VirtIO deploy exception", exc_info=True)

    def _run_virtio_staged_boot(self, out_root: Path, out_images: list[Path]) -> None:
        """Run multi-stage VirtIO boot deployment if enabled."""
        if not self.config.virtio_deploy_boot or not out_images:
            return

        is_windows = (
            self.config.windows
            or self.config.guest_os == "windows"
            or getattr(self.args, "windows", False)
            or getattr(self.args, "guest_os", "") == "windows"
        )
        if not is_windows:
            self.logger.debug("virtio-deploy-boot: not a Windows guest — skipping")
            return

        virtio_iso = (
            self.config.virtio_drivers_dir
            or getattr(self.args, "virtio_drivers_dir", None)
            or getattr(self.args, "virtio_win_iso", None)
            or getattr(self.args, "win_driver_iso", None)
        )
        if not virtio_iso or not str(virtio_iso).lower().endswith(".iso"):
            self.logger.warning(
                "virtio-deploy-boot requires a VirtIO ISO (--virtio-drivers-dir path/to/virtio-win.iso) — skipping"
            )
            return

        try:
            # pylint: disable-next=import-outside-toplevel  # optional Windows-only fixer, only needed for staged VirtIO boot
            from h2kvm.fixers.windows.virtio_stage import VirtioStagedDeployer

            qcow2 = out_images[0]
            vm_name = self.config.vm_name

            # Detect Win11+ from offline fixer results (build >= 22000).
            # Win11 requires manual VirtIO driver install from CD — the
            # automatic bootstrap-shutdown cycle corrupts NTFS on Win11.
            win11_manual = False
            detected_build = None
            if self.disk_processor and hasattr(self.disk_processor, "last_fixer_report"):
                report = getattr(self.disk_processor, "last_fixer_report", None) or {}
                analysis = report.get("analysis", {})
                detected_build = analysis.get("windows_build")
            if detected_build and detected_build >= 22000:
                win11_manual = True
                self.logger.info(
                    "🪟 Windows 11+ detected (build %d) — using manual VirtIO driver mode",
                    detected_build,
                )

            self.logger.info("➡️ Multi-stage VirtIO boot deployment...")
            deployer = VirtioStagedDeployer(
                logger=self.logger,
                qcow2_path=qcow2,
                virtio_iso=Path(virtio_iso),
                vm_name=vm_name,
                out_dir=out_root,
                memory_mib=self.config.memory,
                vcpus=self.config.vcpus,
                guest_agent_timeout=self.config.virtio_deploy_timeout,
                start_final=self.config.virtio_deploy_start_final,
                win11_manual_mode=win11_manual,
            )
            result = deployer.run()

            if result.success:
                self.logger.info(
                    "✅ Staged VirtIO deploy complete: bus=%s agent=%s drivers=%s",
                    result.final_disk_bus,
                    result.guest_agent_responded,
                    result.drivers_found,
                )
            else:
                self.logger.warning(
                    "⚠️  Staged VirtIO deploy incomplete (stage %d): %s",
                    result.stage_reached,
                    result.errors,
                )

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort deployment step, must not abort the whole migration
            self.logger.warning("⚠️  Staged VirtIO boot deployment failed and was skipped: %s", e)
            self.logger.debug("💥 Staged VirtIO deploy exception", exc_info=True)

    def _emit_domain_xml(self, out_root: Path, out_images: list[Path]) -> Path | None:
        """Emit libvirt domain XML if requested. Returns path to emitted XML."""
        if not out_images:
            return None

        try:
            return emit_from_args(self.logger, self.args, out_root=out_root, out_images=out_images)
        except Exception as e:  # pylint: disable=broad-exception-caught  # domain XML emission is best-effort; the conversion itself already succeeded
            self.logger.warning(
                "Failed to generate libvirt domain XML — the VM was converted but cannot be "
                "auto-defined in libvirt. Define it manually with 'virsh define <xml>'. Error: %s",
                e,
            )
            self.logger.debug("💥 emit_from_args exception", exc_info=True)
            return None

    def _log_welcome_banner(self) -> None:
        """Display the welcome banner."""
        self.logger.info("━" * 80)
        self.logger.info("🚀 h2kvm - Production-Grade Hypervisor to KVM Migration Toolkit")
        self.logger.info("   Built for the Enterprise Linux ecosystem (Fedora/RHEL/CentOS)")
        self.logger.info("")
        self.logger.info("   ✨ Features:")
        self.logger.info("      • Multi-platform import: VMware, Hyper-V, Azure, AWS, OVA/OVF/VMDK/VHD")
        self.logger.info("      • Offline guest fixes with VMCraft disk manipulation engine")
        self.logger.info("      • Windows driver injection & registry editing (VirtIO, SATA)")
        self.logger.info("      • Deterministic fstab/grub repair for first-boot success")
        self.logger.info("      • Deploy to libvirt + KubeVirt with web dashboard monitoring")
        self.logger.info("━" * 80)

    def _check_write_actions(self) -> None:
        """Check if write operations are needed and require root if so."""
        write_actions = (not self.config.dry_run) or bool(self.config.to_output) or self.config.flatten
        Log.trace(
            self.logger,
            "🧾 write_actions=%s (dry_run=%s to_output=%r flatten=%s)",
            write_actions,
            self.config.dry_run,
            self.config.to_output,
            self.config.flatten,
        )
        U.require_root_if_needed(self.logger, write_actions)

    def _auto_detect_guest_os(self) -> None:
        """Auto-detect Windows guest OS from the offline fixer report.

        The offline fixer inspects the actual filesystem and detects Windows
        via registry hives.  Propagate that detection to args so the domain
        emitter generates correct libvirt XML (e.g. <os><type>hvm</type></os>
        with Windows-specific features, SATA disk bus, etc.).

        Also auto-enables:
          - Hyper-V enlightenments (all Windows guests)
          - TPM 2.0 (Windows 11+ / Server 2025+, build >= 22000)
          - Secure Boot (UEFI Windows 11+ / Server 2025+)
        """
        if not self.disk_processor or not hasattr(self.disk_processor, "last_fixer_report"):
            return
        report = getattr(self.disk_processor, "last_fixer_report", None) or {}
        analysis = report.get("analysis") or {}
        is_windows = analysis.get("windows")
        if not is_windows:
            return

        # If guest_os was explicitly set to "linux" in the config, trust it
        explicit_os = getattr(self.args, "guest_os", None) or getattr(self.config, "guest_os", None)
        if explicit_os == "linux":
            self.logger.info(
                "Skipping Windows auto-detection — guest_os explicitly set to 'linux' in config",
            )
            return

        if explicit_os != "windows":
            product = analysis.get("windows_product") or "Windows"
            self.logger.info(
                "Auto-detected Windows guest from offline analysis: %s",
                product,
            )
            self.args.guest_os = "windows"
            self.config.guest_os = "windows"
            self.config.windows = True

        # Always enable Hyper-V enlightenments for Windows guests
        if not getattr(self.args, "win_hyperv", False):
            self.args.win_hyperv = True
            self.logger.info("Auto-enabled Hyper-V enlightenments for Windows guest")

        # Windows 11 / Server 2025+ (build >= 22000) need TPM 2.0 and Secure Boot
        windows_build = analysis.get("windows_build")
        if windows_build and int(windows_build) >= 22000:
            product = analysis.get("windows_product") or "Windows 11+"
            if not getattr(self.args, "win_tpm", False):
                self.args.win_tpm = True
                self.logger.info(
                    "Auto-enabled TPM 2.0 for %s (build %s)",
                    product,
                    windows_build,
                )
            is_uefi = getattr(self.args, "uefi", False) or self.config.uefi
            # None = unset → opt in for Win11+ UEFI; False = user/--no-win-secure-boot override
            if is_uefi and getattr(self.args, "win_secure_boot", None) is None:
                self.args.win_secure_boot = True
                self.logger.info(
                    "Auto-enabled Secure Boot for %s (UEFI + build %s)",
                    product,
                    windows_build,
                )

    def _propagate_linux_guest_metadata(self) -> None:
        """Propagate Linux distro/variant from offline fixer report for KubeVirt deploy."""
        if not self.disk_processor or not hasattr(self.disk_processor, "last_fixer_report"):
            return
        report = getattr(self.disk_processor, "last_fixer_report", None)
        if not report:
            return
        try:
            # pylint: disable-next=import-outside-toplevel  # optional deployer helper, only needed for KubeVirt deploy
            from h2kvm.infrastructure.deployers.kubevirt_guest_profile import (
                propagate_linux_metadata_from_report,
            )

            self.args.last_fixer_report = report  # type: ignore[attr-defined]
            propagate_linux_metadata_from_report(self.args, report)
            variant = getattr(self.args, "k8s_os_variant", None)
            pretty = getattr(self.args, "linux_os_pretty_name", None)
            if variant or pretty:
                self.logger.info(
                    "Auto-detected Linux guest for KubeVirt: %s (variant=%s)",
                    pretty or getattr(self.args, "linux_distro", "linux"),
                    variant or "generic",
                )
        except Exception as exc:  # pylint: disable=broad-exception-caught  # best-effort metadata propagation, must not abort the migration
            self.logger.debug("Linux guest metadata propagation skipped: %s", exc)

    def _collect_firmware_signals(self, report: dict) -> FirmwareSignals:
        analysis = report.get("analysis") or {}
        guest_os = (getattr(self.args, "guest_os", None) or self.config.guest_os or "").lower()
        is_windows = (
            guest_os == "windows"
            or bool(getattr(self.args, "windows", False))
            or bool(analysis.get("windows"))
        )
        gen = getattr(self.args, "hyperv_generation", None)
        if gen is None and hasattr(self.args, "metadata"):
            meta = getattr(self.args, "metadata", None) or {}
            if isinstance(meta, dict):
                raw = meta.get("generation")
                if isinstance(raw, (int, float)):
                    gen = int(raw)
        ovf_fw = None
        try:
            # pylint: disable-next=import-outside-toplevel  # avoids loading the OVF extractor for non-OVF migrations
            from h2kvm.converters.extractors.ovf import OVF

            if getattr(OVF, "last_firmware", None) in ("bios", "uefi"):
                ovf_fw = OVF.last_firmware
        except (ImportError, AttributeError):
            pass
        return FirmwareSignals(
            boot_mode=analysis.get("boot_mode"),
            partition_scheme=getattr(self.args, "disk_partition_scheme", None),
            has_efi_partition=getattr(self.args, "disk_has_efi_partition", None),
            windows_bcd_bios=bool(analysis.get("windows_bcd_bios")),
            windows_bcd_uefi=bool(analysis.get("windows_bcd_uefi")),
            hyperv_generation=int(gen) if gen is not None else None,
            ovf_firmware=ovf_fw,
            is_windows=is_windows,
        )

    def _resolve_deploy_firmware(self) -> None:
        """Resolve BIOS vs UEFI from signals; honor explicit firmware_mode overrides."""
        report: dict = {}
        if self.disk_processor and hasattr(self.disk_processor, "last_fixer_report"):
            report = getattr(self.disk_processor, "last_fixer_report", None) or {}

        user_mode = normalize_user_firmware_mode(
            firmware_mode=getattr(self.args, "firmware_mode", None),
            uefi_flag=getattr(self.args, "uefi", None),
        )

        signals = self._collect_firmware_signals(report)
        resolution: FirmwareResolution = resolve_firmware(user_mode=user_mode, signals=signals)

        use_uefi = resolution.firmware == "uefi"
        prev_uefi = bool(getattr(self.args, "uefi", False) or self.config.uefi)
        self.config.uefi = use_uefi
        self.args.uefi = use_uefi
        self.args.firmware_resolution = resolution
        self.args.firmware_alternate = resolution.alternate

        if report:
            analysis = report.setdefault("analysis", {})
            analysis["firmware_mode"] = resolution.firmware
            analysis["firmware_user_mode"] = resolution.user_mode
            analysis["firmware_source"] = resolution.source
            analysis["firmware_confidence"] = resolution.confidence
            analysis["firmware_alternate"] = resolution.alternate

        if prev_uefi != use_uefi:
            self.logger.info(
                "Firmware resolved: %s (user=%s confidence=%s source=%s alternate=%s)",
                resolution.firmware.upper(),
                resolution.user_mode,
                resolution.confidence,
                resolution.source,
                resolution.alternate or "none",
            )
        else:
            self.logger.info(
                "Firmware: %s (user=%s confidence=%s)",
                resolution.firmware.upper(),
                resolution.user_mode,
                resolution.confidence,
            )

        if not use_uefi and getattr(self.args, "win_secure_boot", None) not in (None, False):
            self.args.win_secure_boot = False

    def _discover_and_validate(self, out_root: Path) -> Path | None:
        """
        Discover disks and validate that the pipeline should continue.

        Returns:
            temp_dir if cleanup is needed, None otherwise.
            Raises SystemExit (via return) if mode handled everything.
        """
        temp_dir = self._discover_disks(out_root)
        cmd = self.config.cmd

        if temp_dir is None and cmd in ("live-fix", "vsphere", "azure", "daemon"):
            if cmd in ("vsphere", "azure") and self.disks:
                Log.trace(
                    self.logger, "🌐 %s: continuing pipeline with exported disks=%d", cmd, len(self.disks)
                )
            else:
                return None  # Signal early exit

        if self.recovery_manager:
            self.recovery_manager.save_checkpoint(
                "disks_discovered",
                {"count": len(self.disks), "disks": [str(d) for d in self.disks]},
            )

        return temp_dir  # May be None for non-cleanup paths

    def _auto_detect_boot_disk_index(self) -> None:
        """Pass boot disk index from fixer report to args for domain XML emission."""
        if not self.disk_processor or not hasattr(self.disk_processor, "last_fixer_report"):
            return
        report = getattr(self.disk_processor, "last_fixer_report", None) or {}
        guest = (report.get("analysis") or {}).get("guest") or {}
        boot_disk_index = guest.get("boot_disk_index")
        if boot_disk_index is not None and boot_disk_index > 0:
            self.logger.info(
                f"Multi-disk boot order: boot disk index={boot_disk_index} "
                f"(disk {boot_disk_index + 1} will get boot order=1)"
            )
            self.args.boot_disk_index = boot_disk_index

    def _auto_detect_hardware_from_ovf(self) -> None:
        """Propagate memory, vCPU, NIC count, secure boot from OVF metadata."""
        try:
            # pylint: disable-next=import-outside-toplevel  # avoids loading the OVF extractor for non-OVF migrations
            from h2kvm.converters.extractors.ovf import OVF
        except ImportError:
            return
        hw = getattr(OVF, "last_hardware", None) or {}
        if not hw:
            return

        # Memory: only override if user didn't explicitly set it
        mem = hw.get("memory_mib")
        if mem and mem > 0:
            current = getattr(self.args, "memory", None)
            # Check if it's still the default (2048 Linux / 8192 Windows)
            if current in (None, 2048, 4096, 8192):
                self.args.memory = mem
                self.config.memory = mem
                self.logger.info("OVF hardware: memory=%dMiB", mem)

        # vCPUs
        cpus = hw.get("vcpus")
        if cpus and cpus > 0:
            current = getattr(self.args, "vcpus", None)
            if current in (None, 1, 2, 4):
                self.args.vcpus = cpus
                self.config.vcpus = cpus
                self.logger.info("OVF hardware: vcpus=%d", cpus)

        # NIC count
        nics = hw.get("nic_count", 1)
        if nics > 1:
            self.args.nic_count = nics
            self.logger.info("OVF hardware: nic_count=%d", nics)

        # CPU topology
        topo = hw.get("cpu_topology")
        if topo and not getattr(self.args, "cpu_topology", None):
            self.args.cpu_topology = topo
            self.logger.info("OVF hardware: cpu_topology=%s", topo)

        # Secure Boot from OVF
        if hw.get("secure_boot"):
            is_uefi = getattr(self.args, "uefi", False) or self.config.uefi
            if is_uefi and getattr(self.args, "win_secure_boot", None) is not False:
                self.args.win_secure_boot = True
                self.logger.info("OVF hardware: secure_boot detected")

        # Guest OS hint from OVF
        os_type = hw.get("os_type", "")
        os_desc = hw.get("os_description", "")
        if os_type and not getattr(self.args, "guest_os", None):
            combined = (os_type + " " + os_desc).lower()
            if "windows" in combined or "win" in combined:
                self.args.guest_os = "windows"
                self.config.guest_os = "windows"
                self.config.windows = True
                self.logger.info("OVF hardware: guest_os=windows (osType=%s)", os_type)

    def _auto_detect_hardware_from_govc(self) -> None:
        """Propagate memory/vCPU from govc VM info if available."""
        if not self.disk_processor:
            return
        # govc VM info is stored by the vSphere export path
        vm_info = getattr(self.disk_processor, "vm_info", None) or {}
        if not vm_info:
            return

        mem = vm_info.get("memory_mib") or vm_info.get("memory")
        if mem and int(mem) > 0:
            current = getattr(self.args, "memory", None)
            if current in (None, 2048, 4096, 8192):
                self.args.memory = int(mem)
                self.config.memory = int(mem)
                self.logger.info("vSphere VM info: memory=%dMiB", int(mem))

        cpus = vm_info.get("vcpus") or vm_info.get("cpus") or vm_info.get("cpu")
        if cpus and int(cpus) > 0:
            current = getattr(self.args, "vcpus", None)
            if current in (None, 1, 2, 4):
                self.args.vcpus = int(cpus)
                self.config.vcpus = int(cpus)
                self.logger.info("vSphere VM info: vcpus=%d", int(cpus))

    def _auto_detect_virtio_readiness(self) -> None:
        """Check if Linux guest initramfs rebuild failed; fall back to SATA if so.

        Only triggers when regen was attempted and explicitly errored out.
        Does NOT fall back when regen was skipped or disabled — the guest
        may already have virtio drivers (e.g., Fedora, modern Ubuntu).
        """
        if not self.disk_processor or not hasattr(self.disk_processor, "last_fixer_report"):
            return
        # Only relevant for Linux guests
        if getattr(self.args, "guest_os", None) == "windows" or self.config.windows:
            return

        report = getattr(self.disk_processor, "last_fixer_report", None) or {}
        analysis = report.get("analysis") or {}

        regen = analysis.get("regen") or {}
        # Only fall back to SATA if regen was attempted (enabled=True) but failed
        regen_failed = regen.get("enabled", False) and regen.get("error")

        if regen_failed:
            current_bus = getattr(self.args, "disk_bus", "virtio")
            if current_bus == "virtio":
                self.args.disk_bus = "sata"
                self.logger.warning(
                    "Initramfs rebuild failed — using SATA disk bus for safe boot "
                    "(VirtIO drivers may not be present)"
                )

    def _auto_detect_swap_memory(self) -> None:
        """Estimate memory from swap partition size as a last-resort fallback."""
        # Only use this if no OVF/govc metadata set memory
        current = getattr(self.args, "memory", None)
        if current not in (None, 2048, 4096, 8192):
            return  # Already set by OVF or govc

        if not self.disk_processor or not hasattr(self.disk_processor, "last_fixer_report"):
            return
        report = getattr(self.disk_processor, "last_fixer_report", None) or {}
        analysis = report.get("analysis") or {}
        guest = analysis.get("guest") or {}

        swap_mib = guest.get("swap_size_mib")
        if swap_mib and int(swap_mib) > 512:
            # Heuristic: swap is typically 1-2x RAM for servers
            estimated = max(int(swap_mib), 2048)
            self.args.memory = estimated
            self.config.memory = estimated
            self.logger.info(
                "Estimated memory from swap size: %dMiB (swap=%dMiB)",
                estimated,
                int(swap_mib),
            )

    def _auto_detect_secure_boot_from_guest(self) -> None:
        """Detect Secure Boot from guest filesystem (shim/grub EFI binaries)."""
        if not self.disk_processor or not hasattr(self.disk_processor, "last_fixer_report"):
            return
        # Skip guest heuristics if user or OVF/Windows-build already set an explicit value
        if getattr(self.args, "win_secure_boot", None) is not None:
            return
        if not (getattr(self.args, "uefi", False) or self.config.uefi):
            return

        report = getattr(self.disk_processor, "last_fixer_report", None) or {}
        analysis = report.get("analysis") or {}
        secure_boot = analysis.get("secure_boot_detected")
        if secure_boot:
            self.args.win_secure_boot = True
            self.logger.info("Secure Boot detected from guest filesystem (shim/grub EFI binaries)")

    def _emit_legacy_qcow2_symlinks(  # pylint: disable=too-many-branches  # per-disk symlink creation covers several independent path/existence checks
        self, out_root: Path, out_images: list[Path]
    ) -> None:
        """Symlink ``<out_root>/qcow2/<name>.qcow2`` → ``../<name>.qcow2`` when the final disk sits in ``out_root``.

        Older integrations (and some job wrappers) probe the historical path where
        intermediate conversion wrote qcow2 files. The modern pipeline commonly
        leaves the finished image directly under ``out_root``. A relative symlink
        satisfies those checks without copying multi-GiB data.
        """
        try:
            root = out_root.expanduser().resolve(strict=False)
        except OSError:
            return
        for raw in out_images:
            try:
                img = raw.expanduser().resolve(strict=False)
            except OSError:
                continue
            if img.suffix.lower() != ".qcow2":
                continue
            if not img.is_file():
                continue
            if img.parent != root:
                continue
            legacy_dir = root / "qcow2"
            try:
                legacy_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                Log.trace(self.logger, "legacy qcow2 dir skipped: %s", e)
                continue
            legacy_path = legacy_dir / img.name
            if legacy_path.exists(follow_symlinks=False) or legacy_path.is_symlink():
                try:
                    if legacy_path.is_symlink():
                        if legacy_path.resolve() == img:
                            continue
                        legacy_path.unlink(missing_ok=True)
                    else:
                        # A real file already occupies the name; do not replace.
                        continue
                except OSError as e:
                    Log.trace(self.logger, "legacy qcow2 symlink: could not adjust %s: %s", legacy_path, e)
                    continue
            try:
                legacy_path.symlink_to(f"../{img.name}")
                Log.trace(
                    self.logger,
                    "legacy qcow2 symlink: %s -> ../%s",
                    legacy_path.relative_to(root),
                    img.name,
                )
            except OSError as e:
                Log.trace(self.logger, "legacy qcow2 symlink failed: %s", e)

    def _finalize(self, out_root: Path, out_images: list[Path]) -> None:
        """Run post-processing: domain XML, tests, k8s deployment, summary."""
        # Auto-detect guest properties from all available sources.
        # Order matters: UEFI must be detected before guest OS (which checks
        # UEFI to decide Secure Boot), and OVF/govc hardware must come before
        # swap-based memory estimation (last-resort fallback).
        self._resolve_deploy_firmware()
        self._auto_detect_boot_disk_index()
        self._auto_detect_guest_os()
        self._propagate_linux_guest_metadata()
        self._auto_detect_hardware_from_ovf()
        self._auto_detect_hardware_from_govc()
        self._auto_detect_virtio_readiness()
        self._auto_detect_swap_memory()
        self._auto_detect_secure_boot_from_guest()

        # Remote deploy (KubeVirt / OpenStack) must not define or boot local libvirt domains.
        if self.config.deploy_k8s or self.config.deploy_openstack:
            self.args.emit_domain_xml = False
            self.args.virsh_define = False
            self.config.libvirt_test = False

        # Always emit domain XML when libvirt_test is requested — the smoke
        # test uses the emitted XML (same code path as production) rather than
        # building its own.
        if self.config.libvirt_test and not getattr(self.args, "emit_domain_xml", False):
            self.args.emit_domain_xml = True

        # Auto-enable virsh_define when emit_domain_xml is set, so VMs are
        # automatically defined + started in libvirt after conversion.
        if getattr(self.args, "emit_domain_xml", False) and not getattr(self.args, "virsh_define", False):
            self.args.virsh_define = True
            self.logger.info("Auto-enabling virsh_define (emit_domain_xml is set)")
        emitted_xml = self._emit_domain_xml(out_root, out_images)
        self._run_tests(out_images, emitted_xml=emitted_xml)

        # VirtIO deploy runs AFTER the smoke test — the SATA bootstrap boot
        # must succeed without VirtIO modifications.  VirtIO deploy stages
        # RunOnce scripts and registry changes for the subsequent final boot.
        self._apply_windows_virtio_deploy(out_images)
        self._run_virtio_staged_boot(out_root, out_images)

        if self.recovery_manager:
            self.recovery_manager.cleanup_old_checkpoints()

        if self.config.deploy_k8s and out_images:
            self._deploy_to_kubernetes(out_images)

        if self.config.deploy_openstack and out_images:
            self._deploy_to_openstack(out_images)

        U.banner(self.logger, "Done")

    # ------------------------------------------------------------------
    # AI integration helpers
    # ------------------------------------------------------------------

    def _init_ai(self, merged_config: dict[str, Any] | None = None) -> None:
        """Fail-safe AI initialisation.  Never raises."""
        if self.config.no_ai:
            Log.trace(self.logger, "AI disabled via --no-ai")
            return
        try:
            # pylint: disable-next=import-outside-toplevel  # optional AI subsystem, only needed when AI features are enabled
            from h2kvm.ai.orchestrator import AIOrchestrator

            self._ai = AIOrchestrator()
            ok = self._ai.initialize(merged_config)
            if ok:
                self.logger.info(
                    "AI migration intelligence enabled",
                    extra={"ctx": {"event": "ai_enabled"}},
                )
            else:
                self._ai = None
        except Exception as exc:  # pylint: disable=broad-exception-caught  # AI features are optional and best-effort; must never block migration
            self.logger.debug("AI init failed (non-blocking): %s", exc)
            self._ai = None

    def _ai_pre_analysis(self, features: Any | None = None) -> dict[str, Any] | None:
        """Run AI pre-migration analysis.  Never raises."""
        if self._ai is None or features is None:
            return None
        try:
            result = self._ai.pre_migration_analysis(features)
            if result:
                pred = result.get("prediction")
                if pred:
                    self.logger.info(
                        "AI prediction: success=%.0f%% confidence=%s risks=%d",
                        pred.success_probability * 100,
                        pred.confidence,
                        len(pred.risks),
                        extra={
                            "ctx": {
                                "event": "ai_prediction",
                                "success_probability": pred.success_probability,
                                "confidence": pred.confidence,
                            }
                        },
                    )
                    for risk in pred.risks:
                        self.logger.info("  AI risk: [%s] %s", risk.level.value, risk.message)
                wp = result.get("workload")
                if wp and wp.workload_type.value != "generic":
                    self.logger.info(
                        "AI workload: %s (confidence=%.0f%%)",
                        wp.workload_type.value,
                        wp.confidence * 100,
                    )
            return result
        except Exception as exc:  # pylint: disable=broad-exception-caught  # AI features are optional and best-effort; must never block migration
            self.logger.debug("AI pre-analysis failed (non-blocking): %s", exc)
            return None

    def _ai_post_analysis(
        self,
        features: Any | None = None,
        success: bool = True,
        errors: list[str] | None = None,
        phases: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Run AI post-migration analysis.  Never raises."""
        if self._ai is None or features is None:
            return None
        try:
            fixer_report = None
            fixer_actions: list[str] = []
            if self.disk_processor:
                fixer_report = getattr(self.disk_processor, "last_fixer_report", None)
                if fixer_report:
                    fixer_actions = fixer_report.get("actions", []) or []
            result = self._ai.post_migration_analysis(
                features,
                success,
                errors=errors,
                phases=phases,
                fixer_report=fixer_report,
                fixer_actions=fixer_actions,
            )
            if result:
                health = result.get("health")
                if health:
                    self.logger.info(
                        "AI health: %s (%s)",
                        health.overall_status.value,
                        ", ".join(f"{k}={v}" for k, v in health.summary().items()),
                        extra={
                            "ctx": {
                                "event": "ai_health",
                                "overall": health.overall_status.value,
                            }
                        },
                    )
                anomalies = result.get("anomalies")
                if anomalies:
                    for a in anomalies:
                        self.logger.warning("AI anomaly: %s", a.message)
            return result
        except Exception as exc:  # pylint: disable=broad-exception-caught  # AI features are optional and best-effort; must never block migration
            self.logger.debug("AI post-analysis failed (non-blocking): %s", exc)
            return None

    def _handle_ai_info(self, merged_config: dict[str, Any] | None = None) -> None:
        """Handle --ai-info: print AI status and exit."""
        self._init_ai(merged_config)
        if self._ai:
            info = self._ai.get_info()
            if info:
                self.logger.info("AI Module Information:")
                self.logger.info(json.dumps(info, indent=2, default=str))
            else:
                self.logger.info("AI module initialised but returned no info")
            self._ai.shutdown()
        else:
            self.logger.info("AI module is not available or disabled")
        raise SystemExit(0)

    def run(self) -> None:
        """Main orchestration pipeline."""

        # Handle --ai-info early
        if self.config.ai_info:
            self._handle_ai_info()

        # Check for batch mode first
        if self.config.batch_manifest:
            self._handle_batch_mode()
            return

        self._log_welcome_banner()

        out_root = Path(self.config.output_dir).expanduser().resolve()
        U.ensure_dir(out_root)

        self._setup_recovery(out_root)

        # Sanity checks
        sanity = SanityChecker(self.logger, self.args)
        Log.step(self.logger, "Sanity checks")
        with PhaseTimer("sanity_check_start", "sanity_check_complete", phase="sanity"):
            sanity.check_all()
        sanity.die_if_failed()
        Log.ok(self.logger, "Sanity checks passed")

        U.banner(self.logger, f"Mode: {self.config.cmd}")

        # Handle daemon mode
        if self.config.cmd == "daemon":
            self._run_daemon_mode()
            return

        self._check_write_actions()

        # Initialise AI (fail-safe)
        self._init_ai()

        # Discover and validate disks
        temp_dir = self._discover_and_validate(out_root)
        if temp_dir is None and not self.disks:
            return  # Early exit for modes that don't produce disks

        # AI pre-migration analysis (fail-safe)
        self._ai_pre_analysis()

        # Process disks and finalize
        migration_errors: list[str] = []
        migration_success = True
        try:
            with PhaseTimer("disk_processing_start", "disk_processing_complete", phase="disk_processing"):
                out_images = self._process_disks(out_root)
            self._finalize(out_root, out_images)
        except Exception as exc:
            migration_success = False
            migration_errors.append(str(exc))
            raise
        finally:
            # AI post-migration analysis (fail-safe)
            self._ai_post_analysis(
                success=migration_success,
                errors=migration_errors,
                phases=["discovery", "disk_processing", "finalize"],
            )
            if self._ai:
                self._ai.shutdown()
            if temp_dir and temp_dir.exists():
                Log.trace(self.logger, "cleaning temp_dir=%s", temp_dir)
                shutil.rmtree(temp_dir, ignore_errors=True)

        if migration_success:
            self._emit_legacy_qcow2_symlinks(out_root, out_images)

        log_event(
            "pipeline_complete", output_dir=str(out_root), image_count=len(out_images) if out_images else 0
        )
        self.logger.info(
            f"📦 Output directory: {out_root}",
            extra={
                "ctx": {
                    "event": "pipeline_complete",
                    "output_dir": str(out_root),
                    "image_count": len(out_images) if out_images else 0,
                    "images": [str(img) for img in out_images] if out_images else [],
                }
            },
        )
        if out_images:
            self.logger.info("🎉 Generated images:")
            for img in out_images:
                self.logger.info(f" - {img}")
