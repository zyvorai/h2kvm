# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Artifact Manifest v1 pipeline orchestrator for hypersdk integration."""

from __future__ import annotations

import argparse
import logging
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

import yaml

try:
    import guestfs

    _GUESTFS_AVAILABLE = True
except ImportError:
    guestfs = None  # type: ignore[assignment]
    _GUESTFS_AVAILABLE = False


from hyper2kvm.converters.qemu.converter import Convert
from hyper2kvm.core.utils import U
from hyper2kvm.fixers.offline_fixer import OfflineFixConfig, OfflineFSFix
from hyper2kvm.infrastructure.deployers.openstack import deploy_to_openstack
from hyper2kvm.infrastructure.hooks import HookRunner, create_hook_context

from .loader import ManifestLoader
from .reporter import ManifestReporter


class ManifestOrchestrator:
    # pylint: disable=too-many-instance-attributes,too-few-public-methods
    # This class coordinates an 8-stage VM migration pipeline (manifest load,
    # inspect, fix, convert, validate, plus optional libvirt/KubeVirt/OpenStack
    # deploy stages) and needs to hold state (loader, reporter, hook runner,
    # pipeline progress) across all of them; `run()` is intentionally the sole
    # public entry point, with stage methods kept private.
    """
    Orchestrates the Artifact Manifest v1 conversion pipeline.

    Pipeline stages:
    1. LOAD_MANIFEST: Load and validate Artifact Manifest v1
    2. INSPECT: Gather information about disk artifacts
    3. FIX: Apply offline fixes to boot disk filesystem
    4. CONVERT: Convert all disks to target format
    5. VALIDATE: Verify output integrity for all disks
    """

    def __init__(self, manifest_path: str | Path, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)
        self.manifest_path = Path(manifest_path)
        self.loader = ManifestLoader(self.logger)
        self.reporter = ManifestReporter(self.logger)
        self.manifest: dict[str, Any] = {}
        self.hook_runner: HookRunner | None = None

        # Pipeline state
        self.current_stage = "none"
        self.output_dir: Path | None = None
        self.converted_disks: dict[str, Path] = {}  # disk_id -> output_path

    def run(self) -> dict[str, Any]:
        # pylint: disable=too-many-branches,too-many-statements
        # This drives the full 8-stage pipeline (each stage individually
        # gated by an enable/disable check plus pre/post hooks), so the
        # branch/statement count is inherent to sequencing the whole run.
        """
        Execute the complete pipeline.

        Returns:
            Final report dictionary
        """
        self.logger.info("=" * 80)
        self.logger.info("🚀 Artifact Manifest v1 Conversion Pipeline")
        self.logger.info("=" * 80)

        pipeline_start = time.time()

        try:
            # Pre-extraction hook (before manifest load)
            self._execute_hook_stage(
                "pre_extraction",
                {
                    "manifest_path": str(self.manifest_path),
                },
            )

            # Stage 1: LOAD_MANIFEST (always runs)
            self._run_stage("load_manifest", self._stage_load_manifest)

            # Initialize hook runner from manifest (if hooks are present)
            self.hook_runner = HookRunner.from_manifest(self.manifest, self.logger)

            # Post-extraction hook (after manifest load)
            self._execute_hook_stage("post_extraction", self._create_hook_context())

            # Stage 2: INSPECT
            if self.loader.is_stage_enabled("inspect"):
                self._run_stage("inspect", self._stage_inspect)
            else:
                self.logger.info("⏭️  INSPECT stage disabled")

            # Stage 3: FIX (boot disk only)
            if self.loader.is_stage_enabled("fix"):
                # Pre-fix hook
                self._execute_hook_stage("pre_fix", self._create_hook_context())

                self._run_stage("fix", self._stage_fix)

                # Post-fix hook
                self._execute_hook_stage("post_fix", self._create_hook_context())
            else:
                self.logger.info("⏭️  FIX stage disabled")

            # Stage 4: CONVERT (all disks)
            if self.loader.is_stage_enabled("convert"):
                # Pre-convert hook
                self._execute_hook_stage("pre_convert", self._create_hook_context())

                self._run_stage("convert", self._stage_convert)

                # Post-convert hook
                self._execute_hook_stage("post_convert", self._create_hook_context())
            else:
                self.logger.info("⏭️  CONVERT stage disabled")

            # Stage 5: VALIDATE (all converted disks)
            if self.loader.is_stage_enabled("validate"):
                self._run_stage("validate", self._stage_validate)

                # Post-validate hook
                self._execute_hook_stage("post_validate", self._create_hook_context())
            else:
                self.logger.info("⏭️  VALIDATE stage disabled")

            # Stage 6: LIBVIRT_INTEGRATION (optional - define domain and import disks)
            if self.loader.is_libvirt_integration_enabled():
                self._run_stage("libvirt_integration", self._stage_libvirt_integration)
            else:
                self.logger.info("⏭️  LIBVIRT_INTEGRATION stage disabled")

            # Stage 7: KUBEVIRT_DEPLOY (optional - deploy as KubeVirt VM)
            if self._is_kubevirt_enabled():
                self._run_stage("kubevirt_deploy", self._stage_kubevirt_deploy)
            else:
                self.logger.info("⏭️  KUBEVIRT_DEPLOY stage disabled")

            # Stage 8: OPENSTACK_DEPLOY (optional - Glance upload / Nova boot)
            if self._is_openstack_enabled():
                self._run_stage("openstack_deploy", self._stage_openstack_deploy)
            else:
                self.logger.info("⏭️  OPENSTACK_DEPLOY stage disabled")

            # Finalize
            pipeline_duration = time.time() - pipeline_start
            self.reporter.set_duration(pipeline_duration)
            self.reporter.set_success(True)

            self.logger.info("=" * 80)
            self.logger.info("✅ Pipeline completed successfully in %.2fs", pipeline_duration)
            self.logger.info("=" * 80)

        except Exception as e:
            pipeline_duration = time.time() - pipeline_start
            self.reporter.set_duration(pipeline_duration)
            self.reporter.set_success(False)
            self.reporter.add_error(self.current_stage, str(e))

            self.logger.exception("💥 Pipeline failed at stage '%s': %s", self.current_stage, e)
            raise

        finally:
            # Write report
            report = self.reporter.generate()
            self._write_report(report)

        return report

    def _run_stage(self, stage_name: str, stage_func: Callable[[], Any]) -> Any:
        """Execute a pipeline stage with timing and error handling."""
        self.current_stage = stage_name
        self.logger.info("\n%s", "─" * 80)
        self.logger.info("➡️  Stage: %s", stage_name.upper().replace("_", " "))
        self.logger.info("%s", "─" * 80)

        stage_start = time.time()
        try:
            result = stage_func()
            duration = time.time() - stage_start

            self.reporter.add_stage_result(
                stage_name,
                {
                    "success": True,
                    "duration": duration,
                    "result": result or {},
                },
            )

            self.logger.info("✅ %s completed in %.2fs", stage_name, duration)
            return result

        except Exception as e:
            duration = time.time() - stage_start
            self.reporter.add_stage_result(
                stage_name,
                {
                    "success": False,
                    "duration": duration,
                    "error": str(e),
                },
            )
            self.logger.exception("❌ %s failed: %s", stage_name, e)
            raise

    # Pipeline Stages

    def _stage_load_manifest(self) -> dict[str, Any]:
        """Stage 1: Load and validate Artifact Manifest v1."""
        self.manifest = self.loader.load(self.manifest_path)

        # Verify checksums if present
        if any(disk.checksum for disk in self.loader.get_disks()):
            self.logger.info("🔐 Verifying checksums...")
            checksum_results = self.loader.verify_checksums()
            self.logger.info("✅ Verified %d checksum(s)", len(checksum_results))

        # Display summary
        source_meta = self.loader.get_source_metadata()
        disks = self.loader.get_disks()
        firmware = self.loader.get_firmware()
        os_hint = self.loader.get_os_hint()

        self.logger.info("📋 Manifest: v%s", self.loader.get_version())
        if source_meta.get("provider"):
            self.logger.info(
                "📥 Source: %s / %s",
                source_meta.get("provider"),
                source_meta.get("vm_name", "unknown"),
            )
        self.logger.info("💾 Disks: %d artifact(s)", len(disks))
        for disk in disks:
            size_human = U.human_bytes(disk.bytes)
            self.logger.info("   - %s: %s (%s)", disk.id, disk.source_format, size_human)
        self.logger.info("⚙️  Firmware: %s", firmware)
        if os_hint != "unknown":
            self.logger.info("🖥️  OS Hint: %s", os_hint)

        return {
            "manifest_version": self.loader.get_version(),
            "manifest_path": str(self.manifest_path),
            "source_provider": source_meta.get("provider"),
            "source_vm_id": source_meta.get("vm_id"),
            "source_vm_name": source_meta.get("vm_name"),
            "disks_count": len(disks),
            "firmware": firmware,
            "os_hint": os_hint,
            "checksums_verified": any(disk.checksum for disk in disks),
        }

    def _stage_inspect(self) -> dict[str, Any]:
        """Stage 2: Inspect all disk artifacts."""
        inspect_config = self.loader.get_stage_config("inspect")
        disks = self.loader.get_disks()

        self.logger.info("🔍 Inspecting %d disk artifact(s)...", len(disks))

        disk_results = []

        for disk in disks:
            self.logger.info("\n📀 Disk: %s", disk.id)
            self.logger.info("   Path: %s", disk.local_path)
            self.logger.info("   Format: %s", disk.source_format)
            self.logger.info("   Expected size: %s", U.human_bytes(disk.bytes))

            # Verify file exists
            if not disk.local_path.exists():
                raise FileNotFoundError(
                    f"Converted disk artifact not found at {disk.local_path}. "
                    f"The conversion step may have failed or the output directory was cleaned up."
                )

            # Get actual size
            stat = disk.local_path.stat()
            actual_bytes = stat.st_size
            size_match = actual_bytes == disk.bytes

            self.logger.info("   Actual size: %s", U.human_bytes(actual_bytes))
            if not size_match:
                self.reporter.add_warning(
                    "inspect", f"Disk {disk.id}: Size mismatch (expected {disk.bytes}, got {actual_bytes})"
                )
                self.logger.warning("   ⚠️  Size mismatch!")

            disk_result = {
                "id": disk.id,
                "source_format": disk.source_format,
                "expected_bytes": disk.bytes,
                "actual_bytes": actual_bytes,
                "size_match": size_match,
                "size_human": U.human_bytes(actual_bytes),
                "path": str(disk.local_path),
            }

            # Guest inspection if enabled (boot disk only)
            boot_disk = self.loader.get_boot_disk()
            if inspect_config.get("collect_guest_info", False) and disk.id == boot_disk.id:
                if not _GUESTFS_AVAILABLE:
                    self.logger.warning(
                        "Guest inspection requested but libguestfs not installed. "
                        "Install with: pip install guestfs"
                    )
                    disk_results.append(disk_result)
                    continue

                self.logger.info("🔍 Collecting guest information...")
                try:
                    g = guestfs.GuestFS(python_return_dict=True)
                    try:
                        g.add_drive_opts(str(disk.local_path), readonly=1)
                        g.launch()
                        roots = g.inspect_os()
                        if roots:
                            root = roots[0]
                            disk_result["guest"] = {
                                "type": g.inspect_get_type(root),
                                "distro": g.inspect_get_distro(root),
                                "product_name": g.inspect_get_product_name(root),
                                "major_version": g.inspect_get_major_version(root),
                                "minor_version": g.inspect_get_minor_version(root),
                            }
                            self.logger.info(
                                "   📦 Guest: %s", disk_result["guest"]["product_name"]
                            )
                    finally:
                        g.close()
                except Exception as e:  # pylint: disable=broad-exception-caught
                    # guestfs inspection is best-effort diagnostics; any failure
                    # (launch errors, unsupported guest, etc.) must not abort the
                    # whole pipeline run over one disk's inspection quirk.
                    self.logger.warning("Guest inspection failed: %s", e)
                    disk_result["guest_inspection_error"] = str(e)

            disk_results.append(disk_result)

        return {"disks": disk_results}

    def _stage_fix(self) -> dict[str, Any]:
        """Stage 3: Apply offline fixes to boot disk only."""
        fix_config = self.loader.get_stage_config("fix")
        configuration = self.loader.get_configuration()
        boot_disk = self.loader.get_boot_disk()

        self.logger.info("🔧 Applying offline fixes to boot disk: %s", boot_disk.id)
        self.logger.info("   (Data disks will be skipped)")

        enable_rdp = fix_config.get("enable_rdp")
        if enable_rdp is None:
            vm_meta = self.loader.manifest.get("vm") or {}
            enable_rdp = str(vm_meta.get("os_hint", "")).lower() == "windows"

        self.logger.info(
            "Fix stage: enable_rdp=%s (Windows firstboot RDP + TermService when true)",
            enable_rdp,
        )

        # Setup fixer for boot disk
        offline_fix_config = OfflineFixConfig(
            image=boot_disk.local_path,
            dry_run=self.loader.is_dry_run(),
            no_backup=not fix_config.get("backup", True),
            print_fstab=fix_config.get("print_fstab", False),
            update_grub=fix_config.get("update_grub", True),
            regen_initramfs=fix_config.get("regen_initramfs", True),
            fstab_mode=fix_config.get("fstab_mode", "stabilize-all"),
            report_path=None,
            remove_vmware_tools=fix_config.get("remove_vmware_tools", False),
            enable_rdp=bool(enable_rdp),
            user_config_inject=configuration.get("users"),
            service_config_inject=configuration.get("services"),
            hostname_config_inject=configuration.get("hostname"),
            network_config_inject=configuration.get("network"),
            allowed_dirs=None,  # Manifest mode uses default allowed dirs
        )
        fixer = OfflineFSFix(self.logger, offline_fix_config)

        # Run fixes
        fixer.run()

        # Note about data disks
        all_disks = self.loader.get_disks()
        data_disks = [d for d in all_disks if d.id != boot_disk.id]
        if data_disks:
            for disk in data_disks:
                self.reporter.add_warning(
                    "fix", f"Data disk {disk.id} skipped (fixes only apply to boot disk)"
                )

        return {
            "boot_disk_id": boot_disk.id,
            "data_disks_skipped": len(data_disks),
            "fstab_mode": fix_config.get("fstab_mode", "stabilize-all"),
            "grub_updated": fix_config.get("update_grub", True),
            "initramfs_regenerated": fix_config.get("regen_initramfs", True),
            "vmware_tools_removed": fix_config.get("remove_vmware_tools", False),
            "enable_rdp": bool(enable_rdp),
        }

    def _stage_convert(self) -> dict[str, Any]:
        """Stage 4: Convert all disks to target format."""
        convert_config = self.loader.get_stage_config("convert")
        output_format = self.loader.get_output_format()
        self.output_dir = self.loader.get_output_directory()
        disks = self.loader.get_disks()

        # Ensure output directory exists
        U.ensure_dir(self.output_dir)

        self.logger.info("🔄 Converting %d disk(s) to %s...", len(disks), output_format)
        self.logger.info("📤 Output: %s", self.output_dir)

        converted = []

        for disk in disks:
            self.logger.info("\n💾 Converting disk: %s", disk.id)

            # Determine output filename
            output_filename = f"{disk.id}.{output_format}"
            output_path = self.output_dir / output_filename

            self.logger.info("   Input: %s", disk.local_path)
            self.logger.info("   Output: %s", output_path)

            # Perform conversion
            Convert.convert_image_with_progress(
                self.logger,
                disk.local_path,
                output_path,
                out_format=output_format,
                compress=convert_config.get("compress", False),
                compress_level=convert_config.get("compress_level"),
                progress_callback=lambda p: (
                    self.logger.info("⏳ Progress: %.1f%%", p * 100) if int(p * 100) % 10 == 0 else None
                ),
            )

            # Get output size
            output_stat = output_path.stat()
            output_size_human = U.human_bytes(output_stat.st_size)

            self.logger.info("✅ Converted: %s", output_size_human)

            # Store converted path
            self.converted_disks[disk.id] = output_path

            converted.append(
                {
                    "disk_id": disk.id,
                    "input_format": disk.source_format,
                    "output_format": output_format,
                    "output_path": str(output_path),
                    "output_size_bytes": output_stat.st_size,
                    "output_size_human": output_size_human,
                    "boot_order_hint": disk.boot_order_hint,
                }
            )

        return {
            "disks_converted": len(converted),
            "output_format": output_format,
            "output_directory": str(self.output_dir),
            "compressed": convert_config.get("compress", False),
            "converted_disks": converted,
        }

    def _stage_validate(self) -> dict[str, Any]:
        """Stage 5: Validate all converted disks."""
        validate_config = self.loader.get_stage_config("validate")

        self.logger.info("✅ Validating %d converted disk(s)...", len(self.converted_disks))

        validation_results = []

        for disk_id, output_path in self.converted_disks.items():
            self.logger.info("\n🔍 Validating: %s", disk_id)

            result = {
                "disk_id": disk_id,
                "output_path": str(output_path),
                "exists": output_path.exists(),
            }

            if not output_path.exists():
                result["integrity_check"] = "failed"
                result["error"] = "Output file does not exist"
                self.reporter.add_error("validate", f"Disk {disk_id}: Output file missing")
                raise FileNotFoundError(
                    f"Output disk image not found at {output_path}. "
                    f"The conversion may have failed silently — check earlier log messages for errors."
                )

            # Check image integrity
            if validate_config.get("check_image_integrity", True):
                try:
                    Convert.validate(self.logger, output_path)
                    result["integrity_check"] = "passed"
                    self.logger.info("✅ %s: Integrity check passed", disk_id)
                except Exception as e:
                    # Convert.validate() can raise a variety of errors depending on
                    # the underlying qemu-img check failure mode; record and
                    # re-raise so the pipeline still fails loudly on bad output.
                    # pylint: disable=broad-exception-caught
                    result["integrity_check"] = "failed"
                    result["integrity_error"] = str(e)
                    self.logger.exception("❌ %s: Integrity check failed: %s", disk_id, e)
                    raise

            validation_results.append(result)

        return {
            "disks_validated": len(validation_results),
            "all_passed": all(r.get("integrity_check") == "passed" for r in validation_results),
            "validation_results": validation_results,
        }

    def _stage_libvirt_integration(self) -> dict[str, Any]:
        """Stage 6: Libvirt integration - define domain and import disks to pools."""
        # pylint: disable=import-outside-toplevel,too-many-locals
        # too-many-locals: this stage tracks domain/pool config, snapshot,
        # autostart, and per-disk import state together; splitting it up would
        # obscure the libvirt define/import sequence more than it would help.
        # Deliberately lazy: libvirt-python is an optional dependency and this
        # module must import cleanly without it installed.
        from hyper2kvm.core.exceptions import InfrastructureError
        from hyper2kvm.libvirt import LIBVIRT_AVAILABLE, LibvirtManager, PoolManager

        if not LIBVIRT_AVAILABLE:
            self.logger.warning(
                "⚠️  Libvirt Python bindings not available. Install with: pip install libvirt-python"
            )
            return {"enabled": False, "reason": "libvirt not available"}

        libvirt_config = self.loader.get_libvirt_integration_config()

        domain_xml_path = self.output_dir / "domain.xml"
        if not domain_xml_path.exists():
            self.logger.warning("⚠️  Domain XML not found: %s", domain_xml_path)
            return {"enabled": False, "reason": "domain XML not found"}

        self.logger.info("🔧 Integrating with libvirt...")

        results = {
            "domain_defined": False,
            "disks_imported": 0,
            "snapshot_created": False,
            "domain_started": False,
        }

        try:
            # Define domain
            if libvirt_config.get("define_domain", True):
                with LibvirtManager(self.logger) as manager:
                    domain = manager.define_domain(
                        domain_xml_path,
                        overwrite=libvirt_config.get("overwrite_domain", False),
                    )
                    results["domain_defined"] = True
                    results["domain_name"] = domain.name()

                    # Create snapshot if requested
                    if libvirt_config.get("create_snapshot", False):
                        snapshot_name = libvirt_config.get("snapshot_name", "pre-first-boot")
                        manager.create_snapshot(
                            domain,
                            snapshot_name,
                            description="Snapshot created by hyper2kvm before first boot",
                        )
                        results["snapshot_created"] = True
                        results["snapshot_name"] = snapshot_name

                    # Set autostart if requested
                    if libvirt_config.get("autostart", False):
                        manager.set_autostart(domain, True)
                        results["autostart_enabled"] = True

                    # Start domain if requested
                    if libvirt_config.get("auto_start", False):
                        manager.start_domain(domain)
                        results["domain_started"] = True

            # Import disks to pool if requested
            pool_name = libvirt_config.get("import_to_pool")
            if pool_name:
                pool_path = libvirt_config.get("pool_path", "/var/lib/libvirt/images")

                with PoolManager(self.logger) as pool_mgr:
                    pool = pool_mgr.ensure_pool(pool_name, pool_path)

                    # Import each converted disk
                    for disk_id, output_path in self.converted_disks.items():
                        volume_name = f"{libvirt_config.get('vm_name', 'vm')}-{disk_id}"
                        pool_mgr.import_disk(
                            pool,
                            output_path,
                            volume_name,
                            copy=libvirt_config.get("copy_disks", True),
                            overwrite=libvirt_config.get("overwrite_volumes", False),
                        )
                        results["disks_imported"] += 1

            self.logger.info("✅ Libvirt integration completed successfully")
            return results

        except InfrastructureError as e:
            self.logger.exception("❌ Libvirt integration failed: %s", e)
            self.reporter.add_error("libvirt_integration", str(e))
            raise

    def _write_report(self, _report: dict[str, Any]) -> None:
        """Write report to file."""
        options = self.loader.get_options()
        report_config = options.get("report", {})

        if not report_config.get("enabled", True):
            self.logger.info("📊 Report generation disabled")
            return

        # Determine report path
        report_path = report_config.get("path")
        if not report_path:
            if self.output_dir:
                report_path = self.output_dir / "report.json"
            else:
                # Fallback to manifest directory
                report_path = self.manifest_path.parent / "report.json"
        else:
            report_path = Path(report_path)
            if not report_path.is_absolute():
                if self.output_dir:
                    report_path = self.output_dir / report_path
                else:
                    report_path = self.manifest_path.parent / report_path

        # Ensure parent directory exists
        report_path.parent.mkdir(parents=True, exist_ok=True)

        # Write report
        self.reporter.write_json(report_path)
        self.logger.info("📊 Report written: %s", report_path)

    def _execute_hook_stage(self, stage: str, context: dict[str, Any]) -> None:
        """
        Execute hooks for a given pipeline stage.

        Args:
            stage: Stage name (e.g., "pre_fix", "post_convert")
            context: Context variables for template substitution
        """
        if not self.hook_runner:
            return

        if not self.hook_runner.has_hooks_for_stage(stage):
            return

        try:
            success = self.hook_runner.execute_stage_hooks(stage, context)
            if not success:
                self.reporter.add_warning(
                    self.current_stage, f"One or more {stage} hooks failed (continue_on_error enabled)"
                )
        except Exception as e:
            # User-defined hooks can run arbitrary commands/templates, so the
            # failure mode here is inherently unpredictable; log, record, and
            # re-raise so the pipeline still fails loudly.
            # pylint: disable=broad-exception-caught
            self.logger.exception("💥 Hook stage '%s' failed: %s", stage, e)
            self.reporter.add_error(self.current_stage, f"Hook {stage} failed: {e}")
            raise

    def _is_kubevirt_enabled(self) -> bool:
        """Check if KubeVirt deployment is enabled in the manifest."""
        pipeline = self.manifest.get("pipeline", {})
        kv = pipeline.get("kubevirt", {})
        return kv.get("enabled", False)

    def _stage_kubevirt_deploy(self) -> dict[str, Any]:
        # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        # Builds a full KubeVirt VirtualMachine CR (metadata, network,
        # firmware, DataVolume template) from many independent manifest
        # options, then applies it and optionally uploads the disk; splitting
        # this up would fragment a single coherent CR-construction step.
        """Stage 7: Deploy converted VM as KubeVirt VirtualMachine."""
        pipeline = self.manifest.get("pipeline", {})
        kv = pipeline.get("kubevirt", {})

        namespace = kv.get("namespace", "default")
        vm_name = kv.get("vm_name", "")
        if not vm_name:
            source = self.manifest.get("source", {})
            vm_name = source.get("vm_name", "migrated-vm").lower().replace(" ", "-")

        storage_class = kv.get("storage_class", "")
        access_mode = kv.get("access_mode", "ReadWriteOnce")
        volume_mode = kv.get("volume_mode", "Filesystem")
        network = kv.get("network", "pod")
        running = kv.get("running", False)
        upload_disk = kv.get("upload_disk", False)
        labels = kv.get("labels", {})
        annotations = kv.get("annotations", {})

        # Get VM metadata from manifest
        vm_meta = self.manifest.get("vm", {})
        cpu = vm_meta.get("cpu", 2)
        mem_gb = vm_meta.get("mem_gb", 4)
        firmware = vm_meta.get("firmware", "bios")

        # Find the converted boot disk
        boot_disk = self.loader.get_boot_disk()
        if not boot_disk:
            raise RuntimeError(
                "No boot disk found for KubeVirt deployment. "
                "Ensure the manifest defines at least one disk with boot=true, "
                "or that the conversion step completed successfully."
            )

        # Resolve output directory from manifest or instance
        out_dir = self.output_dir
        if out_dir is None:
            out_cfg = self.manifest.get("output", {})
            out_dir = Path(out_cfg.get("directory", ".")) if out_cfg.get("directory") else Path()

        disk_path = out_dir / f"{boot_disk.id}.qcow2"
        if not disk_path.exists():
            # Try the original path
            disk_path = Path(boot_disk.local_path)

        disk_size_gi = max(1, boot_disk.bytes // (1024**3) + 1)

        self.logger.info("🚀 Deploying to KubeVirt: %s in namespace %s", vm_name, namespace)
        self.logger.info("   CPU: %s, Memory: %sGi, Firmware: %s", cpu, mem_gb, firmware)
        self.logger.info("   Disk: %s (%sGi)", disk_path, disk_size_gi)

        # Build VirtualMachine CR
        vm_labels = {"app": vm_name, "hypersdk.io/migrated": "true"}
        vm_labels.update(labels)

        vm_annotations = {
            "hypersdk.io/source-provider": self.manifest.get("source", {}).get("provider", "unknown")
        }
        vm_annotations.update(annotations)

        # Network interface
        if network == "bridge":
            net_config = {"name": "default", "bridge": {}}
            net_source = {"name": "default", "multus": {"networkName": kv.get("network_name", "bridge-net")}}
        elif network == "multus":
            net_config = {"name": "default", "bridge": {}}
            net_source = {"name": "default", "multus": {"networkName": kv.get("network_name", "default")}}
        else:
            net_config = {"name": "default", "masquerade": {}}
            net_source = {"name": "default", "pod": {}}

        vm_cr = {
            "apiVersion": "kubevirt.io/v1",
            "kind": "VirtualMachine",
            "metadata": {
                "name": vm_name,
                "namespace": namespace,
                "labels": vm_labels,
                "annotations": vm_annotations,
            },
            "spec": {
                "running": running,
                "template": {
                    "metadata": {"labels": vm_labels},
                    "spec": {
                        "domain": {
                            "cpu": {"cores": cpu},
                            "memory": {"guest": f"{mem_gb}Gi"},
                            "devices": {
                                "disks": [{"name": "rootdisk", "disk": {"bus": "virtio"}}],
                                "interfaces": [net_config],
                            },
                            "firmware": {"bootloader": {"efi": {}} if firmware == "uefi" else {"bios": {}}},
                        },
                        "networks": [net_source],
                        "volumes": [
                            {
                                "name": "rootdisk",
                                "dataVolume": {"name": f"{vm_name}-rootdisk"},
                            }
                        ],
                    },
                },
                "dataVolumeTemplates": [
                    {
                        "metadata": {"name": f"{vm_name}-rootdisk"},
                        "spec": {
                            "pvc": {
                                "accessModes": [access_mode],
                                "volumeMode": volume_mode,
                                "resources": {"requests": {"storage": f"{disk_size_gi}Gi"}},
                                **({"storageClassName": storage_class} if storage_class else {}),
                            },
                            "source": ({"upload": {}} if upload_disk else {"blank": {}}),
                        },
                    }
                ],
            },
        }

        # Write CR to file
        cr_path = out_dir / f"{vm_name}-kubevirt-vm.yaml"
        with open(cr_path, "w", encoding="utf-8") as f:
            yaml.dump(vm_cr, f, default_flow_style=False, sort_keys=False)
        self.logger.info("📄 VirtualMachine CR written: %s", cr_path)

        results = {
            "cr_path": str(cr_path),
            "vm_name": vm_name,
            "namespace": namespace,
            "applied": False,
            "disk_uploaded": False,
        }

        # Apply CR if kubectl is available
        try:
            subprocess.run(
                ["kubectl", "apply", "-f", str(cr_path)],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            results["applied"] = True
            self.logger.info("✅ VirtualMachine CR applied: %s in %s", vm_name, namespace)
        except FileNotFoundError:
            self.logger.warning("⚠️  kubectl not found — CR written but not applied")
        except subprocess.CalledProcessError as e:
            self.logger.warning("⚠️  kubectl apply failed: %s", e.stderr.strip())
        except subprocess.TimeoutExpired:
            self.logger.warning("⚠️  kubectl apply timed out")

        # Upload disk via virtctl if requested
        if upload_disk and results["applied"]:
            try:
                upload_cmd = [
                    "virtctl",
                    "image-upload",
                    "dv",
                    f"{vm_name}-rootdisk",
                    f"--image-path={disk_path}",
                    f"--namespace={namespace}",
                    "--insecure",
                    "--no-create",
                    "--access-mode=ReadWriteOnce",
                    "--volume-mode=filesystem",
                ]
                if storage_class:
                    upload_cmd.append(f"--storage-class={storage_class}")
                subprocess.run(
                    upload_cmd,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=3600,
                )
                results["disk_uploaded"] = True
                self.logger.info("✅ Disk uploaded to DataVolume: %s-rootdisk", vm_name)
            except FileNotFoundError:
                self.logger.warning("⚠️  virtctl not found — install with: kubectl krew install virt")
            except subprocess.CalledProcessError as e:
                self.logger.warning("⚠️  virtctl upload failed: %s", e.stderr.strip())
            except subprocess.TimeoutExpired:
                self.logger.warning("⚠️  virtctl upload timed out")

        self.reporter.add_stage_result("kubevirt_deploy", results)
        return results

    def _is_openstack_enabled(self) -> bool:
        """Check if OpenStack Glance upload is enabled in the manifest."""
        pipeline = self.manifest.get("pipeline", {})
        os_cfg = pipeline.get("openstack", {})
        return os_cfg.get("enabled", False)

    def _stage_openstack_deploy(self) -> dict[str, Any]:
        """Stage 8: Upload converted boot disk to OpenStack Glance."""
        pipeline = self.manifest.get("pipeline", {})
        os_cfg = pipeline.get("openstack", {})

        boot_disk = self.loader.get_boot_disk()
        if not boot_disk:
            raise RuntimeError("No boot disk found for OpenStack deployment")

        out_dir = self.output_dir
        if out_dir is None:
            out_cfg = self.manifest.get("output", {})
            out_dir = Path(out_cfg.get("directory", ".")) if out_cfg.get("directory") else Path()

        disk_path = out_dir / f"{boot_disk.id}.qcow2"
        if not disk_path.exists():
            disk_path = Path(boot_disk.local_path)

        source = self.manifest.get("source", {})
        glance_name = os_cfg.get("glance_name") or source.get("vm_name") or boot_disk.id

        args = argparse.Namespace(
            glance_name=glance_name,
            vm_name=glance_name,
            dry_run=self.manifest.get("options", {}).get("dry_run", False),
            os_cloud=os_cfg.get("os_cloud"),
            os_auth_url=os_cfg.get("os_auth_url"),
            os_username=os_cfg.get("os_username"),
            os_password=os_cfg.get("os_password"),
            os_project_name=os_cfg.get("os_project_name"),
            openstack_description=os_cfg.get("description"),
            openstack_visibility=os_cfg.get("visibility", "private"),
            openstack_boot_instance=os_cfg.get("boot_instance", False),
            openstack_server_name=os_cfg.get("server_name"),
            openstack_flavor=os_cfg.get("flavor"),
            openstack_network=os_cfg.get("network"),
            openstack_key_name=os_cfg.get("key_name"),
            openstack_security_group=os_cfg.get("security_group"),
            openstack_availability_zone=os_cfg.get("availability_zone"),
            openstack_wait=os_cfg.get("wait", False),
        )

        self.logger.info("☁️  Uploading to OpenStack Glance: %s", glance_name)
        result = deploy_to_openstack(self.logger, args, str(disk_path))
        self.reporter.add_stage_result("openstack_deploy", result)
        return result

    def _create_hook_context(self) -> dict[str, Any]:
        """
        Create context dictionary for hook variable substitution.

        Returns:
            Dictionary of context variables
        """
        source_meta = self.loader.get_source_metadata()
        boot_disk = self.loader.get_boot_disk()

        # Get source and output paths
        source_path = str(boot_disk.local_path) if boot_disk else ""
        output_path = ""
        if self.output_dir and boot_disk:
            output_format = self.loader.get_output_format()
            output_path = str(self.output_dir / f"{boot_disk.id}.{output_format}")

        return create_hook_context(
            stage=self.current_stage,
            vm_name=source_meta.get("vm_name"),
            source_path=source_path,
            output_path=output_path,
        )
