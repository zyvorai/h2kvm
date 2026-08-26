# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""AWS EC2 provider — main orchestrator."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable

from .client import AWSClient
from .converter import Converter
from .downloader import Downloader
from .exceptions import AWSProviderError
from .exporter import Exporter
from .models import (
    AWSConfig,
    DiskExport,
    ExportReport,
)
from .utils import load_state, save_state

logger = logging.getLogger(__name__)


class AWSProvider:  # pylint: disable=too-many-instance-attributes
    # Orchestrator wiring together config, logging, progress reporting, and several
    # independent AWS-side components (client/exporter/downloader/converter).
    """
    AWS EC2 → KVM migration provider.

    Orchestrates the full pipeline:
    1. Describe instance (volumes, platform, architecture)
    2. Stop instance (optional)
    3. Create EBS snapshot
    4. Export snapshot to S3 as VMDK/VHD/RAW
    5. Download from S3
    6. Convert + offline fixes via h2kvmctl
    7. Cleanup (snapshots, S3, temp AMIs)

    Supports resumability via state files — if interrupted,
    re-running with the same config skips completed steps.
    """

    def __init__(
        self,
        config: AWSConfig,
        log: logging.Logger | None = None,
        progress_cb: Callable[[str, str, float], None] | None = None,
    ):
        """
        Args:
            config: AWS provider configuration
            log: Logger instance
            progress_cb: Callback(phase, message, pct_0_to_1)
        """
        self.config = config
        self.log = log or logger
        self.progress_cb = progress_cb

        # Validate
        if not config.bucket:
            raise AWSProviderError("S3 bucket is required (config.bucket)")

        # Workdir
        self.workdir = config.workdir or (config.output_dir / "work")
        self.workdir.mkdir(parents=True, exist_ok=True)
        config.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.client = AWSClient(
            region=config.region,
            profile=config.profile,
            log=self.log,
        )
        self.exporter = Exporter(self.client.ec2, log=self.log)
        self.downloader = Downloader(
            self.client.s3,
            retries=config.download.retries,
            backoff_base=config.download.backoff_base_s,
            backoff_cap=config.download.backoff_cap_s,
            verify_size=config.download.verify_size,
            log=self.log,
        )
        self.converter = Converter(log=self.log)

    def _emit(self, phase: str, msg: str, pct: float = 0.0) -> None:
        """Emit progress update."""
        self.log.info("[%s] %s", phase, msg)
        if self.progress_cb:
            self.progress_cb(phase, msg, pct)

    # Full end-to-end migration pipeline (describe/stop/snapshot/export/download/convert/
    # cleanup); the branch/local/statement count reflects the number of distinct phases.
    def pull_instance(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        self, instance_id: str
    ) -> ExportReport:
        """
        Full pipeline: EC2 instance → local qcow2 ready for KVM.

        Args:
            instance_id: EC2 instance ID (e.g., i-0abc123def456)

        Returns:
            ExportReport with results for each disk
        """
        cfg = self.config
        state_path = self.workdir / f"{instance_id}.state.json"
        state = load_state(state_path) or {}

        report = ExportReport(instance_id=instance_id, region=cfg.region)

        try:
            # Phase 1: Describe
            self._emit("describe", f"Describing instance {instance_id}", 0.05)
            info = self.client.describe_instance(instance_id)
            report.instance_name = info.name
            report.platform = info.platform
            report.architecture = info.architecture

            self.log.info(
                "Instance: name=%s type=%s platform=%s arch=%s volumes=%d",
                info.name,
                info.instance_type,
                info.platform,
                info.architecture,
                len(info.volumes),
            )

            # Select volumes
            if cfg.export.disks == "root":
                volumes = [v for v in info.volumes if v.is_root]
            else:
                volumes = list(info.volumes)

            if not volumes:
                report.errors.append("No eligible volumes found")
                return report

            # Phase 2: Stop instance (optional)
            if cfg.shutdown.stop_instance and info.state == "running":
                self._emit("stop", f"Stopping instance {instance_id}", 0.10)
                self.client.stop_instance(instance_id)

            # Process each volume
            total_disks = len(volumes)
            for idx, vol in enumerate(volumes):
                disk_pct_base = 0.15 + (0.80 * idx / total_disks)
                disk_pct_range = 0.80 / total_disks

                disk_export = DiskExport(
                    volume_id=vol.volume_id,
                    device=vol.device,
                    is_root=vol.is_root,
                    size_gb=vol.size_gb,
                )

                try:
                    self._process_volume(
                        vol.volume_id,
                        instance_id,
                        disk_export,
                        state,
                        state_path,
                        pct_base=disk_pct_base,
                        pct_range=disk_pct_range,
                    )
                    disk_export.ok = True
                except Exception as e:  # pylint: disable=broad-exception-caught
                    # One volume's failure must not abort processing of the remaining volumes.
                    disk_export.errors.append(str(e))
                    self.log.exception("Failed to process volume %s: %s", vol.volume_id, e)

                report.disks.append(disk_export)

            # Phase 7: Convert via h2kvmctl
            self._emit("convert", "Running h2kvmctl pipeline", 0.90)
            for disk in report.disks:
                if disk.ok and disk.local_path:
                    vm_name = info.name or instance_id
                    # Sanitize: keep only alphanumeric, dash, underscore
                    vm_name = re.sub(r"[^a-zA-Z0-9_-]", "-", vm_name).strip("-")[:50] or instance_id

                    rc = self.converter.run_h2kvmctl(
                        disk.local_path,
                        cfg.output_dir,
                        vm_name=vm_name,
                        compress=True,
                        regen_initramfs=True,
                        emit_domain_xml=True,
                    )
                    if rc == 0:
                        disk.qcow2_path = str(cfg.output_dir / f"{vm_name}.qcow2")
                        self.log.info("Migration complete: %s", disk.qcow2_path)
                    else:
                        disk.warnings.append(f"h2kvmctl exited with code {rc}")

            self._emit("done", "Migration complete", 1.0)

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Top-level pipeline guard: any failure must be captured in the report, not crash the run.
            report.errors.append(str(e))
            self.log.error("Migration failed: %s", e, exc_info=True)
        finally:
            # Always clean up AWS resources
            try:
                self._cleanup(state)
                self.exporter.cleanup_temp_amis()
            except Exception as e:  # pylint: disable=broad-exception-caught
                # Best-effort cleanup; must not mask the pipeline's real outcome.
                self.log.warning("Cleanup failed: %s", e)

            # Delete state file on success (stale state breaks re-runs)
            if not report.errors:
                try:
                    state_path.unlink(missing_ok=True)
                except Exception:  # pylint: disable=broad-exception-caught
                    # Best-effort state cleanup; irrelevant to the already-successful result.
                    pass

        # Save report
        report_path = cfg.output_dir / f"{instance_id}-report.json"
        report_path.write_text(json.dumps(report.to_jsonable(), indent=2, default=str))
        self.log.info("Report saved: %s", report_path)

        return report

    # Needs identity (volume/instance), output targets (disk/state/state_path), and
    # progress-window bounds (pct_base/pct_range) to report sub-phase progress accurately.
    def _process_volume(  # pylint: disable=too-many-arguments
        self,
        volume_id: str,
        instance_id: str,
        disk: DiskExport,
        state: dict[str, Any],
        state_path: Path,
        *,
        pct_base: float,
        pct_range: float,
    ) -> None:
        """Process a single volume through snapshot → export → download."""
        cfg = self.config
        vol_state = state.setdefault(volume_id, {})

        # Phase 3: Snapshot
        snapshot_id = vol_state.get("snapshot_id")
        if not snapshot_id:
            self._emit("snapshot", f"Creating snapshot for {volume_id}", pct_base)
            snapshot_id = self.client.create_snapshot(volume_id)
            vol_state["snapshot_id"] = snapshot_id
            save_state(state_path, state)
        else:
            self.log.info("Reusing snapshot %s (from state)", snapshot_id)
        disk.snapshot_id = snapshot_id

        # Phase 4: Export to S3
        export_task_id = vol_state.get("export_task_id")
        if not export_task_id:
            self._emit("export", f"Exporting snapshot {snapshot_id} to S3", pct_base + pct_range * 0.2)
            export_task_id = self.exporter.start_export(
                snapshot_id,
                cfg.bucket,
                prefix=cfg.export.s3_prefix,
                disk_format=cfg.export.disk_format,
                role_name=cfg.export.role_name,
            )
            vol_state["export_task_id"] = export_task_id
            save_state(state_path, state)
        else:
            self.log.info("Reusing export task %s (from state)", export_task_id)
        disk.export_task_id = export_task_id

        # Phase 5: Wait for export
        self._emit("export_wait", f"Waiting for export {export_task_id}", pct_base + pct_range * 0.3)
        task = self.exporter.wait(
            export_task_id,
            progress_cb=lambda status, pct: self._emit(
                "export_wait", f"Export: {status} {pct}", pct_base + pct_range * 0.4
            ),
        )
        disk.s3_bucket = task.s3_bucket
        disk.s3_key = task.s3_key
        vol_state["s3_bucket"] = task.s3_bucket
        vol_state["s3_key"] = task.s3_key
        save_state(state_path, state)

        # Phase 6: Download from S3
        local_name = f"{instance_id}-{volume_id}.{cfg.export.disk_format}"
        local_path = self.workdir / local_name

        if not vol_state.get("downloaded"):
            self._emit("download", "Downloading from S3", pct_base + pct_range * 0.5)
            self.downloader.download(
                task.s3_bucket,
                task.s3_key,
                local_path,
                progress_cb=lambda dl, total: self._emit(
                    "download",
                    f"Downloading: {dl / total:.1%}" if total else "Downloading...",
                    pct_base + pct_range * (0.5 + 0.4 * dl / total) if total else pct_base,
                ),
                resume=cfg.download.resume,
            )
            vol_state["downloaded"] = True
            vol_state["local_path"] = str(local_path)
            save_state(state_path, state)
        else:
            local_path = Path(vol_state["local_path"])
            self.log.info("Reusing downloaded file (from state): %s", local_path)

        disk.local_path = str(local_path)

    def _cleanup(self, state: dict[str, Any]) -> None:
        """Clean up AWS resources (snapshots, S3 objects)."""
        cfg = self.config

        for vol_state in state.values():
            if isinstance(vol_state, dict):
                # Delete S3 export
                s3_bucket = vol_state.get("s3_bucket")
                s3_key = vol_state.get("s3_key")
                if s3_bucket and s3_key:
                    self.downloader.delete_s3_object(s3_bucket, s3_key)

                # Delete snapshot (unless keep_snapshots)
                if not cfg.export.keep_snapshots:
                    snap_id = vol_state.get("snapshot_id")
                    if snap_id:
                        self.client.delete_snapshot(snap_id)

    def pull_all(self) -> list[ExportReport]:
        """Pull all configured instances."""
        reports = []
        for instance_id in self.config.instance_ids:
            report = self.pull_instance(instance_id)
            reports.append(report)
        return reports
