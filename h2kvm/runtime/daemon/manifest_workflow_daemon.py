# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/daemon/manifest_workflow_daemon.py
"""
3-Directory Manifest Workflow Daemon for h2kvm.

Processes manifest files through a production-ready workflow:
  - to_be_processed/  Drop zone for manifest files
  - processing/       Manifests currently being processed
  - processed/        Successfully completed manifests with reports
  - failed/           Failed manifests with error context

Supports:
  - Single VM manifests
  - Batch manifests (multiple VMs)
  - Declarative pipeline (LOAD→INSPECT→FIX→CONVERT→VALIDATE)
  - Detailed reporting with artifact tracking
"""

from __future__ import annotations

import json
import shutil
import signal
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Lock
from typing import TYPE_CHECKING, Any

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from ...core.logger import Log
from ...core.utils import U
from .stats import DaemonStatistics

if TYPE_CHECKING:
    import argparse
    import logging


class ManifestFileHandler(FileSystemEventHandler):
    """
    Watches to_be_processed/ directory for manifest files.

    Supported files:
    - .json (manifest files)
    - .yaml, .yml (manifest files)
    """

    MANIFEST_EXTENSIONS = {".json", ".yaml", ".yml"}

    def __init__(self, logger: logging.Logger, queue: Queue, to_be_processed_dir: Path):
        super().__init__()
        self.logger = logger
        self.queue = queue
        self.to_be_processed_dir = to_be_processed_dir
        self.queued: set[str] = set()
        self.lock = Lock()

    def _is_valid_file(self, path: Path) -> bool:
        """Check if file should be processed."""
        if not path.is_file():
            return False

        if path.suffix.lower() not in self.MANIFEST_EXTENSIONS:
            return False

        with self.lock:
            if str(path) in self.queued:
                return False

        return True

    def _queue_file(self, path: Path) -> None:
        """Add file to processing queue."""
        if not self._is_valid_file(path):
            return

        with self.lock:
            self.queued.add(str(path))

        Log.trace(self.logger, f"📥 Queuing manifest: {path.name}")
        self.queue.put(path)
        self.logger.info(f"📥 New manifest queued: {path.name}")

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events."""
        if event.is_directory:
            return
        path = Path(event.src_path)
        self._queue_file(path)

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file move events."""
        if event.is_directory:
            return
        path = Path(event.dest_path)
        self._queue_file(path)


class ManifestWorkflowDaemon:
    """
    3-Directory Manifest Workflow Daemon for h2kvm.

    Directory structure:
      base_dir/
        ├── to_be_processed/   # Drop zone for manifest files
        ├── processing/        # Active manifests
        ├── processed/         # Completed with reports
        └── failed/            # Failed with error info
    """

    def __init__(self, logger: logging.Logger, args: argparse.Namespace):
        self.logger = logger
        self.args = args

        # Directory structure
        self.base_dir = (
            Path(args.manifest_workflow_dir if hasattr(args, "manifest_workflow_dir") else args.watch_dir)
            .expanduser()
            .resolve()
        )
        self.to_be_processed_dir = self.base_dir / "to_be_processed"
        self.processing_dir = self.base_dir / "processing"
        self.processed_dir = self.base_dir / "processed"
        self.failed_dir = self.base_dir / "failed"
        self.output_dir = Path(args.output_dir).expanduser().resolve()

        # Core components
        self.queue: Queue = Queue()
        self.stop_event = Event()
        self.observer: Observer | None = None
        self.handler: ManifestFileHandler | None = None
        self.executor: ThreadPoolExecutor | None = None

        # Configuration
        self.max_workers = getattr(args, "max_concurrent_jobs", 3)

        # Daemon-level deploy defaults (applied to each job if not overridden)
        self.deploy_defaults = {}
        for key in (
            "emit_domain_xml",
            "virsh_define",
            "deploy_k8s",
            "deploy_openstack",
            "glance_name",
            "os_cloud",
            "openstack_description",
            "openstack_visibility",
            "openstack_boot_instance",
            "openstack_server_name",
            "openstack_flavor",
            "openstack_network",
            "openstack_key_name",
            "openstack_security_group",
            "openstack_availability_zone",
            "openstack_wait",
            "openstack_continue_on_error",
            "k8s_namespace",
            "k8s_vm_name",
            "k8s_storage_class",
            "k8s_stop_before_deploy",
            "k8s_stop_wait_timeout",
            "k8s_disk_bus",
            "libvirt_test",
            "boot_test",
            "keep_domain",
            "vm_name",
            "memory",
            "vcpus",
            "machine",
            "uefi",
            "flatten",
            "compress",
            "regen_initramfs",
            "fstab_mode",
            "out_format",
            "guest_os",
            "windows",
        ):
            val = getattr(args, key, None)
            if val is not None:
                self.deploy_defaults[key] = val

        # Kubeconfig for KubeVirt deploy
        kubeconfig = getattr(args, "kubeconfig", None)
        if kubeconfig:
            import os

            os.environ["KUBECONFIG"] = str(kubeconfig)
            self.logger.info(f"🔑 KUBECONFIG set: {kubeconfig}")

        # Statistics
        stats_dir = self.base_dir / ".stats"
        stats_dir.mkdir(parents=True, exist_ok=True)
        self.stats = DaemonStatistics(logger, stats_dir / "stats.json")

        # Job tracking
        self.active_jobs: dict[str, Path] = {}
        self.active_jobs_lock = Lock()

        # Signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals."""
        sig_name = signal.Signals(signum).name
        self.logger.info(f"🛑 Received {sig_name}, shutting down gracefully...")
        self.stop()

    def _setup_directories(self) -> None:
        """Create workflow directory structure."""
        for dir_path in [
            self.to_be_processed_dir,
            self.processing_dir,
            self.processed_dir,
            self.failed_dir,
            self.output_dir,
        ]:
            U.ensure_dir(dir_path)
            self.logger.info(f"📁 {dir_path.name:20} → {dir_path}")

    def _move_to_processing(self, file_path: Path) -> Path:
        """Move manifest from to_be_processed to processing directory."""
        processing_path = self.processing_dir / file_path.name

        # Handle name collision
        if processing_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            processing_path = self.processing_dir / f"{file_path.stem}_{timestamp}{file_path.suffix}"

        try:
            shutil.move(str(file_path), str(processing_path))
            Log.trace(self.logger, f"📤 Moved to processing: {file_path.name}")
            return processing_path
        except Exception as e:
            self.logger.exception(f"Failed to move to processing: {e}")
            raise

    def _move_to_processed(self, processing_path: Path, job_id: str, report: dict[str, Any]) -> None:
        """Move manifest from processing to processed directory."""
        # Create dated subdirectory
        date_dir = self.processed_dir / datetime.now().strftime("%Y-%m-%d")
        U.ensure_dir(date_dir)

        processed_path = date_dir / processing_path.name

        try:
            shutil.move(str(processing_path), str(processed_path))
            Log.trace(self.logger, f"✅ Moved to processed: {processing_path.name}")

            # Save manifest report
            report_file = processed_path.with_suffix(processed_path.suffix + ".report.json")
            with open(report_file, "w") as f:
                json.dump(report, f, indent=2)

            self.logger.info(f"📝 Report saved: {report_file.name}")

        except Exception as e:
            self.logger.exception(f"Failed to move to processed: {e}")

    def _move_to_failed(
        self, processing_path: Path, job_id: str, error: str, exception_info: str | None = None
    ) -> None:
        """Move manifest from processing to failed directory with error context."""
        # Create dated subdirectory
        date_dir = self.failed_dir / datetime.now().strftime("%Y-%m-%d")
        U.ensure_dir(date_dir)

        failed_path = date_dir / processing_path.name

        try:
            shutil.move(str(processing_path), str(failed_path))
            Log.trace(self.logger, f"❌ Moved to failed: {processing_path.name}")

            # Save error context
            error_file = failed_path.with_suffix(failed_path.suffix + ".error.json")
            error_context = {
                "job_id": job_id,
                "original_name": processing_path.name,
                "failed_at": datetime.now().isoformat(),
                "error": error,
                "exception": exception_info,
                "status": "failed",
            }
            with open(error_file, "w") as f:
                json.dump(error_context, f, indent=2)

            self.logger.info(f"📝 Error details saved: {error_file.name}")

        except Exception as e:
            self.logger.exception(f"Failed to move to failed directory: {e}")

    def _load_manifest(self, manifest_path: Path) -> dict[str, Any]:
        """Load manifest from JSON or YAML file."""
        import yaml

        with open(manifest_path) as f:
            if manifest_path.suffix.lower() == ".json":
                return json.load(f)
            return yaml.safe_load(f)

    def _process_manifest(self, manifest_path: Path) -> None:
        """Process a manifest file."""
        processing_path = None
        start_time = time.time()

        try:
            # Move to processing directory
            processing_path = self._move_to_processing(manifest_path)

            # Load manifest
            manifest = self._load_manifest(processing_path)
            job_id = processing_path.stem

            # Track active job
            with self.active_jobs_lock:
                self.active_jobs[job_id] = processing_path

            # Record job start
            self.stats.job_started(job_id, "manifest", 0)

            self.logger.info(f"🔄 Processing manifest: {job_id}")

            # Create output directory for this manifest
            date_dir = datetime.now().strftime("%Y-%m-%d")
            manifest_output_dir = self.output_dir / date_dir / job_id
            U.ensure_dir(manifest_output_dir)

            # Detect format: Artifact Manifest v1.0 or regular migration config
            is_artifact_manifest = manifest.get("manifest_version") == "1.0" and manifest.get("disks")
            has_cmd = manifest.get("cmd") or manifest.get("command")

            if is_artifact_manifest:
                # Artifact Manifest v1.0 (generated by hypersdk)
                provider = manifest.get("source", {}).get("provider", "unknown")
                disk_count = len(manifest.get("disks", []))
                self.logger.info(f"📋 Artifact Manifest: {disk_count} disk(s) from {provider}")

                from h2kvm.orchestration.manifest.orchestrator import ManifestOrchestrator

                orch = ManifestOrchestrator(str(processing_path), self.logger)
                orch.run()

            elif has_cmd:
                # Regular migration config (same as h2kvmctl --config)
                cmd = manifest.get("cmd") or manifest.get("command")
                self.logger.info(f"📋 Migration config: cmd={cmd}")

                # Apply daemon-level defaults to manifest (job can override)
                for key, val in self.deploy_defaults.items():
                    if key not in manifest:
                        manifest[key] = val
                if "output_dir" not in manifest:
                    manifest["output_dir"] = str(manifest_output_dir)

                # Write merged config back so Orchestrator picks up defaults
                import yaml

                with open(processing_path, "w") as f:
                    yaml.dump(manifest, f, default_flow_style=False)

                # Run via the Orchestrator directly (same process, no binary lookup)
                from h2kvm.cli.args import parse_args_with_config

                args, _conf, _logger = parse_args_with_config(argv=["--config", str(processing_path)])
                from h2kvm.orchestration.orchestrator import Orchestrator

                Orchestrator(self.logger, args).run()

                deploy_targets = []
                if manifest.get("emit_domain_xml"):
                    deploy_targets.append("libvirt")
                if manifest.get("virsh_define"):
                    deploy_targets.append("virsh-define")
                if manifest.get("deploy_k8s"):
                    deploy_targets.append("kubevirt")
                self.logger.info(
                    "✅ Migration completed successfully"
                    + (f" (deployed to: {', '.join(deploy_targets)})" if deploy_targets else "")
                )

            else:
                raise ValueError(
                    "Unsupported manifest format. "
                    "Drop either a migration config (with cmd: local/vsphere/...) "
                    "or an Artifact Manifest (with manifest_version: '1.0' and disks[])."
                )

            # Success
            duration = time.time() - start_time
            self.logger.info(f"✅ Job completed: {job_id} ({duration:.1f}s)")

            # Move to processed with report
            report = {"job_id": job_id, "status": "success", "duration_s": round(duration, 1)}
            self._move_to_processed(processing_path, job_id, report)

            # Record success
            self.stats.job_completed(job_id, success=True, error=None)

        except Exception as e:
            error_msg = str(e)
            exception_trace = traceback.format_exc()

            job_id = manifest_path.stem if not processing_path else processing_path.stem
            self.logger.exception(f"❌ Manifest failed: {job_id} - {error_msg}")
            self.logger.debug(f"Exception:\n{exception_trace}")

            # Move to failed
            if processing_path and processing_path.exists():
                self._move_to_failed(processing_path, job_id, error_msg, exception_trace)
            elif manifest_path.exists():
                self._move_to_failed(manifest_path, job_id, error_msg, exception_trace)

            # Record failure
            self.stats.job_completed(job_id, success=False, error=error_msg)

        finally:
            # Remove from active jobs
            if processing_path:
                job_id = processing_path.stem
                with self.active_jobs_lock:
                    self.active_jobs.pop(job_id, None)

    def _scan_existing_files(self) -> None:
        """Scan to_be_processed directory for existing manifests."""
        self.logger.info(f"🔍 Scanning for existing manifests in: {self.to_be_processed_dir}")

        count = 0
        for ext in ManifestFileHandler.MANIFEST_EXTENSIONS:
            for file_path in self.to_be_processed_dir.glob(f"*{ext}"):
                if file_path.is_file():
                    Log.trace(self.logger, f"📥 Queuing: {file_path.name}")
                    self.queue.put(file_path)
                    count += 1

        if count > 0:
            self.logger.info(f"📥 Found {count} existing manifest(s)")
        else:
            self.logger.info("📭 No existing manifests found")

    def _worker_loop(self) -> None:
        """Worker loop for processing manifests from queue."""
        while not self.stop_event.is_set():
            try:
                # Wait for new manifest with timeout
                try:
                    manifest_path = self.queue.get(timeout=1.0)
                except Empty:
                    continue

                # Process the manifest
                self._process_manifest(manifest_path)

                self.queue.task_done()

            except Exception as e:
                self.logger.exception(f"💥 Worker loop error: {e}")
                self.logger.debug("Exception details", exc_info=True)
                time.sleep(5)

    def run(self) -> None:
        """Start the manifest workflow daemon."""
        self.logger.info("=" * 80)
        self.logger.info("🚀 Starting Manifest Workflow Daemon (3-Directory)")
        self.logger.info("=" * 80)

        # Setup directories
        self._setup_directories()

        self.logger.info("")
        self.logger.info(f"⚙️  Max Workers: {self.max_workers}")
        self.logger.info(f"📤 Output: {self.output_dir}")
        self.logger.info("")

        # Setup file system observer
        self.handler = ManifestFileHandler(self.logger, self.queue, self.to_be_processed_dir)
        self.observer = Observer()
        self.observer.schedule(self.handler, str(self.to_be_processed_dir), recursive=False)
        self.observer.start()

        self.logger.info("👂 File system observer started")

        # Scan for existing files
        self._scan_existing_files()

        # Start worker pool
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        for _ in range(self.max_workers):
            self.executor.submit(self._worker_loop)

        self.logger.info("")
        self.logger.info("✅ Manifest workflow daemon ready")
        self.logger.info("=" * 80)
        self.logger.info("")
        self.logger.info("📋 Usage:")
        self.logger.info("  1. Drop manifest files (.json, .yaml) into:")
        self.logger.info(f"     {self.to_be_processed_dir}")
        self.logger.info(f"  2. Monitor progress in: {self.processing_dir}")
        self.logger.info(f"  3. Check results in: {self.processed_dir}")
        self.logger.info("  4. View reports: <processed>/<date>/<manifest>.report.json")
        self.logger.info("")

        # Main loop
        while not self.stop_event.is_set():
            try:
                time.sleep(10)

                # Print active jobs
                with self.active_jobs_lock:
                    if self.active_jobs:
                        self.logger.info(f"🔄 Active manifests: {len(self.active_jobs)}")
                        for job_id in list(self.active_jobs.keys())[:3]:
                            self.logger.info(f"  • {job_id}")

            except Exception as e:
                self.logger.exception(f"💥 Main loop error: {e}")

        self.logger.info("🛑 Manifest workflow daemon stopped")

    def stop(self) -> None:
        """Stop the manifest workflow daemon."""
        self.logger.info("🛑 Stopping manifest workflow daemon...")
        self.stop_event.set()

        # Stop observer
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)

        # Stop executor
        if self.executor:
            self.executor.shutdown(wait=True, cancel_futures=False)

        # Save stats
        self.stats.save(force=True)
        self.stats.print_summary()

        self.logger.info("✅ Manifest workflow daemon shutdown complete")
