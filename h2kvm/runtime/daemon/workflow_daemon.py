# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/daemon/workflow_daemon.py
"""
3-Directory Workflow Daemon for h2kvm.

Implements a production-ready workflow with clear state separation:
  - to_be_processed/  Drop zone for new jobs (disk files or config files)
  - processing/       Jobs currently being converted
  - processed/        Successfully completed jobs
  - failed/           Failed jobs with error context

Supports both:
  - Direct disk files (.vmdk, .ova, .vhd, etc.)
  - Job config files (.yaml, .json) for complex conversions
"""

from __future__ import annotations

import argparse
import json
import os
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

import yaml
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from ...core.logger import Log
from ...core.utils import U
from ...infrastructure.systemd.systemd_core import SystemdIntegration
from .stats import DaemonStatistics

if TYPE_CHECKING:
    import logging


class WorkflowJobConfig:
    """Represents a conversion job configuration."""

    def __init__(self, config_data: dict[str, Any], source_file: Path):
        self.config = config_data
        self.source_file = source_file
        self.job_id = source_file.stem
        self.created_at = datetime.now()

    @staticmethod
    def from_yaml(yaml_file: Path) -> WorkflowJobConfig:
        """Load job config from YAML file."""
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        return WorkflowJobConfig(data, yaml_file)

    @staticmethod
    def from_json(json_file: Path) -> WorkflowJobConfig:
        """Load job config from JSON file."""
        with open(json_file) as f:
            data = json.load(f)
        return WorkflowJobConfig(data, json_file)

    @staticmethod
    def from_disk_file(disk_file: Path, default_config: dict[str, Any]) -> WorkflowJobConfig:
        """Create job config from a disk file with defaults."""
        config = {
            "input": str(disk_file),
            "output_format": default_config.get("output_format", "qcow2"),
            "compress": default_config.get("compress", True),
            "flatten": default_config.get("flatten", True),
        }
        # Merge with defaults
        config.update(default_config)
        return WorkflowJobConfig(config, disk_file)

    def get_input_file(self) -> Path | None:
        """Get the input file path from config."""
        input_path = self.config.get("input")
        if input_path:
            return Path(input_path)
        return None

    def is_batch_job(self) -> bool:
        """Check if this is a batch job with multiple inputs."""
        return "jobs" in self.config

    def get_batch_jobs(self) -> list[dict[str, Any]]:
        """Get list of jobs from batch config."""
        return self.config.get("jobs", [])


class WorkflowFileHandler(FileSystemEventHandler):
    """
    Watches to_be_processed/ directory for new jobs.

    Supported files:
    - VM disk files: .vmdk, .ova, .ovf, .vhd, .vhdx, .raw, .img, .ami
    - Config files: .yaml, .yml, .json
    """

    DISK_EXTENSIONS = {".vmdk", ".ova", ".ovf", ".vhd", ".vhdx", ".raw", ".img", ".ami"}
    CONFIG_EXTENSIONS = {".yaml", ".yml", ".json"}
    ALL_EXTENSIONS = DISK_EXTENSIONS | CONFIG_EXTENSIONS

    def __init__(
        self, logger: logging.Logger, queue: Queue, to_be_processed_dir: Path, default_config: dict[str, Any]
    ):
        super().__init__()
        self.logger = logger
        self.queue = queue
        self.to_be_processed_dir = to_be_processed_dir
        self.default_config = default_config
        self.queued: set[str] = set()
        self.lock = Lock()

    def _is_valid_file(self, path: Path) -> bool:
        """Check if file should be processed (without lock — caller must hold lock if needed)."""
        if not path.is_file():
            return False

        if path.suffix.lower() not in self.ALL_EXTENSIONS:
            return False

        return str(path) not in self.queued

    def _queue_file(self, path: Path) -> None:
        """Add file to processing queue (atomic check-and-add)."""
        with self.lock:
            if not self._is_valid_file(path):
                return
            self.queued.add(str(path))

        Log.trace(self.logger, f"📥 Queuing: {path.name}")
        self.queue.put(path)
        self.logger.info(f"📥 New job queued: {path.name}")

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


class WorkflowDaemon:
    """
    3-Directory Workflow Daemon for h2kvm.

    Directory structure:
      base_dir/
        ├── to_be_processed/   # Drop zone for new jobs
        ├── processing/        # Active jobs
        ├── processed/         # Completed successfully
        └── failed/            # Failed jobs with error info
    """

    def __init__(self, logger: logging.Logger, args: argparse.Namespace):
        self.logger = logger
        self.args = args

        # Directory structure
        self.base_dir = (
            Path(args.workflow_dir if hasattr(args, "workflow_dir") else args.watch_dir)
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
        self.handler: WorkflowFileHandler | None = None
        self.executor: ThreadPoolExecutor | None = None

        # Configuration
        self.max_workers = getattr(args, "max_concurrent_jobs", 3)
        self.default_config = {
            "output_format": getattr(args, "out_format", "qcow2"),
            "compress": getattr(args, "compress", True),
            "flatten": getattr(args, "flatten", True),
            "fstab_mode": getattr(args, "fstab_mode", "stabilize-all"),
            "regen_initramfs": getattr(args, "regen_initramfs", True),
        }

        # Statistics
        stats_dir = self.base_dir / ".stats"
        stats_dir.mkdir(parents=True, exist_ok=True)
        self.stats = DaemonStatistics(logger, stats_dir / "stats.json")

        # Job tracking
        self.active_jobs: dict[str, Path] = {}
        self.active_jobs_lock = Lock()

        # Systemd integration (sd_notify ready/watchdog/stopping)
        self._sd = SystemdIntegration()

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
        """Move file from to_be_processed to processing directory."""
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

    def _move_to_processed(self, processing_path: Path, job_id: str) -> None:
        """Move file from processing to processed directory."""
        # Create dated subdirectory for organization
        date_dir = self.processed_dir / datetime.now().strftime("%Y-%m-%d")
        U.ensure_dir(date_dir)

        processed_path = date_dir / processing_path.name

        try:
            shutil.move(str(processing_path), str(processed_path))
            Log.trace(self.logger, f"✅ Moved to processed: {processing_path.name}")

            # Save job metadata
            metadata_file = processed_path.with_suffix(processed_path.suffix + ".meta.json")
            metadata = {
                "job_id": job_id,
                "original_name": processing_path.name,
                "completed_at": datetime.now().isoformat(),
                "status": "success",
            }
            with open(metadata_file, "w") as f:
                json.dump(metadata, f, indent=2)

        except Exception as e:
            self.logger.exception(f"Failed to move to processed: {e}")

    def _move_to_failed(
        self, processing_path: Path, job_id: str, error: str, exception_info: str | None = None
    ) -> None:
        """Move file from processing to failed directory with error context."""
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

    def _load_job_config(self, file_path: Path) -> WorkflowJobConfig:
        """Load job configuration from file."""
        ext = file_path.suffix.lower()

        if ext in {".yaml", ".yml"}:
            return WorkflowJobConfig.from_yaml(file_path)
        if ext == ".json":
            return WorkflowJobConfig.from_json(file_path)
        if ext in WorkflowFileHandler.DISK_EXTENSIONS:
            return WorkflowJobConfig.from_disk_file(file_path, self.default_config)
        raise ValueError(
            f"Unsupported file type '{ext}'. "
            f"Supported: .json (config), {', '.join(WorkflowFileHandler.DISK_EXTENSIONS)} (disk images)."
        )

    def _create_args_from_config(
        self, job_config: WorkflowJobConfig, output_dir: Path
    ) -> argparse.Namespace:
        """Create argument namespace from job config.

        Input-file → cmd dispatch stays explicit (extension-based).
        All other config keys are applied generically via the argparse
        parser so that every supported flag (libvirt XML, cloud-init,
        LUKS, VirtIO, serial console, etc.) is honoured.
        """
        from ...cli.args.parser import build_parser
        from ...config.config_loader import Config

        config = job_config.config
        file_args = argparse.Namespace(**vars(self.args))

        # Determine input file and command
        input_path = job_config.get_input_file()
        if input_path:
            ext = input_path.suffix.lower()
            if ext == ".vmdk":
                file_args.cmd = "local"
                file_args.vmdk = str(input_path)
            elif ext == ".ova":
                file_args.cmd = "ova"
                file_args.ova = str(input_path)
            elif ext == ".ovf":
                file_args.cmd = "ovf"
                file_args.ovf = str(input_path)
            elif ext in {".vhd", ".vhdx"}:
                file_args.cmd = "vhd"
                file_args.vhd = str(input_path)
            elif ext in {".raw", ".img"}:
                file_args.cmd = "raw"
                file_args.raw = str(input_path)
            elif ext == ".ami":
                file_args.cmd = "ami"
                file_args.ami = str(input_path)

        # Apply ALL config keys generically (type-coerced via argparse)
        parser = build_parser()
        Config.apply_config_to_namespace(self.logger, parser, config, file_args)

        # Daemon always controls output_dir
        file_args.output_dir = str(output_dir)

        return file_args

    def _process_single_job(self, job_config: WorkflowJobConfig, processing_path: Path) -> None:
        """Process a single conversion job."""
        start_time = time.time()
        job_id = job_config.job_id

        try:
            # Track active job
            with self.active_jobs_lock:
                self.active_jobs[job_id] = processing_path

            # Get input file
            input_file = job_config.get_input_file()
            if not input_file:
                raise ValueError(
                    "No input file specified in the job configuration. "
                    "Add 'source_path' or 'vmdk' to the config, or drop a disk image file into the watch directory."
                )

            if not input_file.exists():
                raise FileNotFoundError(f"Input file not found: {input_file}")

            # Create output directory
            date_dir = datetime.now().strftime("%Y-%m-%d")
            output_dir = self.output_dir / date_dir / job_id
            U.ensure_dir(output_dir)

            # Create args for orchestrator
            file_args = self._create_args_from_config(job_config, output_dir)

            # Record job start
            file_size_mb = input_file.stat().st_size / (1024 * 1024) if input_file.exists() else 0
            file_type = input_file.suffix.lower().lstrip(".")
            self.stats.job_started(job_id, file_type, file_size_mb)

            # Run conversion
            from ...orchestration.orchestrator import Orchestrator

            Log.step(self.logger, f"Converting: {input_file.name} → {output_dir}")
            orchestrator = Orchestrator(self.logger, file_args)
            orchestrator.run()

            # Success
            duration = time.time() - start_time
            self.logger.info(f"✅ Job completed: {job_id} ({duration:.1f}s)")

            # Move to processed
            self._move_to_processed(processing_path, job_id)

            # Record success
            self.stats.job_completed(job_id, success=True, error=None)

        except Exception as e:
            error_msg = str(e)
            exception_trace = traceback.format_exc()

            self.logger.exception(f"❌ Job failed: {job_id} - {error_msg}")
            self.logger.debug(f"Exception:\n{exception_trace}")

            # Move to failed
            self._move_to_failed(processing_path, job_id, error_msg, exception_trace)

            # Record failure
            self.stats.job_completed(job_id, success=False, error=error_msg)

        finally:
            # Remove from active jobs
            with self.active_jobs_lock:
                self.active_jobs.pop(job_id, None)

    def _process_file(self, file_path: Path) -> None:
        """Process a file from the queue."""
        processing_path = None

        try:
            # Move to processing directory
            processing_path = self._move_to_processing(file_path)

            # Load job configuration
            job_config = self._load_job_config(processing_path)

            # Check if batch job
            if job_config.is_batch_job():
                self.logger.info(f"📦 Batch job detected: {job_config.job_id}")
                batch_jobs = job_config.get_batch_jobs()

                for idx, job_data in enumerate(batch_jobs):
                    sub_job_config = WorkflowJobConfig(job_data, processing_path)
                    sub_job_config.job_id = f"{job_config.job_id}_job{idx + 1}"
                    self.logger.info(f"  ├─ Processing job {idx + 1}/{len(batch_jobs)}")
                    self._process_single_job(sub_job_config, processing_path)

                # Move batch config to processed after all jobs complete (guard against double-move)
                if processing_path.exists():
                    self._move_to_processed(processing_path, job_config.job_id)
            else:
                # Single job
                self._process_single_job(job_config, processing_path)

        except Exception as e:
            error_msg = str(e)
            exception_trace = traceback.format_exc()

            self.logger.exception(f"❌ Failed to process {file_path.name}: {error_msg}")
            self.logger.debug(f"Exception:\n{exception_trace}")

            # Clean up any stale active_jobs entries from partial batch runs
            with self.active_jobs_lock:
                stale = [k for k in self.active_jobs if k.startswith(file_path.stem)]
                for k in stale:
                    self.active_jobs.pop(k, None)

            # Move to failed if we have a processing path
            if processing_path and processing_path.exists():
                self._move_to_failed(processing_path, file_path.stem, error_msg, exception_trace)
            elif file_path.exists():
                # If move to processing failed, move original to failed
                self._move_to_failed(file_path, file_path.stem, error_msg, exception_trace)

    def _scan_existing_files(self) -> None:
        """Scan to_be_processed directory for existing files."""
        self.logger.info(f"🔍 Scanning for existing jobs in: {self.to_be_processed_dir}")

        count = 0
        for ext in WorkflowFileHandler.ALL_EXTENSIONS:
            for file_path in self.to_be_processed_dir.glob(f"*{ext}"):
                if file_path.is_file():
                    Log.trace(self.logger, f"📥 Queuing: {file_path.name}")
                    self.queue.put(file_path)
                    count += 1

        if count > 0:
            self.logger.info(f"📥 Found {count} existing job(s)")
        else:
            self.logger.info("📭 No existing jobs found")

    def _worker_loop(self) -> None:
        """Worker loop for processing jobs from queue."""
        while not self.stop_event.is_set():
            try:
                # Wait for new job with timeout
                try:
                    file_path = self.queue.get(timeout=1.0)
                except Empty:
                    continue

                # Process the job
                self._process_file(file_path)

                self.queue.task_done()

            except Exception as e:
                self.logger.exception(f"💥 Worker loop error: {e}")
                self.logger.debug("Exception details", exc_info=True)
                time.sleep(5)

    def run(self) -> None:
        """Start the workflow daemon."""
        self.logger.info("=" * 80)
        self.logger.info("🚀 Starting 3-Directory Workflow Daemon")
        self.logger.info("=" * 80)

        # Setup directories
        self._setup_directories()

        self.logger.info("")
        self.logger.info(f"⚙️  Max Workers: {self.max_workers}")
        self.logger.info(f"📤 Output: {self.output_dir}")
        self.logger.info("")

        # Setup file system observer
        self.handler = WorkflowFileHandler(
            self.logger, self.queue, self.to_be_processed_dir, self.default_config
        )
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
        self.logger.info("✅ Workflow daemon ready")
        self.logger.info("=" * 80)
        self.logger.info("")
        self.logger.info("📋 Usage:")
        self.logger.info("  1. Drop VM disk files (.vmdk, .ova, etc.) into:")
        self.logger.info(f"     {self.to_be_processed_dir}")
        self.logger.info("  2. Or drop job config files (.yaml, .json) for custom settings")
        self.logger.info(f"  3. Monitor progress in: {self.processing_dir}")
        self.logger.info(f"  4. Check results in: {self.processed_dir}")
        self.logger.info("")

        # Write PID file for health checks (Kubernetes liveness/readiness probes)
        self._write_pid_file()

        # Notify systemd that the daemon is ready to accept jobs
        self._sd.notify_ready()

        # Main loop
        while not self.stop_event.is_set():
            try:
                time.sleep(10)

                # Watchdog keepalive and status update
                self._sd.watchdog_ping()
                with self.active_jobs_lock:
                    n_jobs = len(self.active_jobs)
                self._sd.notify_status(f"jobs={n_jobs}")

                # Print active jobs
                with self.active_jobs_lock:
                    if self.active_jobs:
                        self.logger.info(f"🔄 Active jobs: {len(self.active_jobs)}")
                        for job_id in list(self.active_jobs.keys())[:3]:  # Show max 3
                            self.logger.info(f"  • {job_id}")

            except Exception as e:
                self.logger.exception(f"💥 Main loop error: {e}")

        self.logger.info("🛑 Workflow daemon stopped")

    def _write_pid_file(self) -> None:
        """Write PID file for health checks (Kubernetes liveness probes)."""
        try:
            pid_dir = Path("/var/lib/h2kvm")
            pid_dir.mkdir(parents=True, exist_ok=True)
            pid_file = pid_dir / "daemon.pid"

            with open(pid_file, "w") as f:
                f.write(str(os.getpid()))

            self.logger.info(f"📝 PID file written: {pid_file} (PID: {os.getpid()})")
        except Exception as e:
            self.logger.warning(f"Failed to write PID file: {e}")

    def _remove_pid_file(self) -> None:
        """Remove PID file on shutdown."""
        try:
            pid_file = Path("/var/lib/h2kvm/daemon.pid")
            if pid_file.exists():
                pid_file.unlink()
                self.logger.info("🗑️  PID file removed")
        except Exception as e:
            self.logger.warning(f"Failed to remove PID file: {e}")

    def stop(self) -> None:
        """Stop the workflow daemon gracefully."""
        self._sd.notify_stopping()
        self.logger.info("🛑 Stopping workflow daemon...")
        self.logger.info("⏳ Waiting for active jobs to complete...")

        self.stop_event.set()

        # Stop observer
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)

        # Stop executor (wait for current jobs to finish)
        if self.executor:
            self.executor.shutdown(wait=True, cancel_futures=False)
            self.logger.info("✅ All jobs completed")

        # Save stats
        self.stats.save(force=True)
        self.stats.print_summary()

        # Remove PID file
        self._remove_pid_file()

        self.logger.info("✅ Workflow daemon shutdown complete")
        self.logger.info("💡 Note: NBD devices and LVM volumes are cleaned up per-job")
