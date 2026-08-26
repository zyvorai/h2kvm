# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/daemon/daemon_watcher.py
"""
Enhanced daemon mode file watcher with all improvements.

Features:
1. Concurrent processing with worker pool
2. File completion detection (wait for stable file size)
3. Comprehensive statistics tracking
4. Retry mechanism with exponential backoff
5. Health check & control API (Unix socket)
6. Notifications (webhook, email)
7. File deduplication
8. Better error context and logging
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
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

from ...core.constants import DELAY_STATUS_POLL
from ...core.logger import Log
from ...core.utils import U
from .control import DEFAULT_CONTROL_SOCKET, DaemonControl
from .deduplicator import FileDeduplicator
from .notifier import DaemonNotifier
from .stats import DaemonStatistics

if TYPE_CHECKING:
    import logging


class VMFileHandler(FileSystemEventHandler):
    """
    Watches for new VM disk files and queues them for processing.

    Supported file extensions:
    - .vmdk (VMware)
    - .ova, .ovf (OVF archives)
    - .vhd, .vhdx (Hyper-V)
    - .raw, .img (Raw disk images)
    - .ami (AWS AMI images)
    """

    SUPPORTED_EXTENSIONS = {
        ".vmdk",
        ".ova",
        ".ovf",
        ".vhd",
        ".vhdx",
        ".raw",
        ".img",
        ".ami",
        ".yaml",
        ".yml",
    }

    def __init__(
        self,
        logger: logging.Logger,
        queue: Queue,
        watch_dir: Path,
        deduplicator: FileDeduplicator | None = None,
        file_stable_timeout: int = 30,
    ):
        super().__init__()
        self.logger = logger
        self.queue = queue
        self.watch_dir = watch_dir
        self.deduplicator = deduplicator
        self.file_stable_timeout = file_stable_timeout
        self.processing: set[str] = set()
        self.processed: set[str] = set()
        self.lock = Lock()

    def _is_valid_file(self, path: Path) -> bool:
        """Check if file is a supported VM disk file."""
        if not path.is_file():
            return False
        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            return False

        with self.lock:
            if str(path) in self.processing or str(path) in self.processed:
                return False

        return True

    def _wait_for_file_stable(self, path: Path) -> bool:
        """
        Wait for file size to stabilize (file completely written).

        Returns:
            True if file is stable, False if timeout or file disappeared
        """
        last_size = -1
        stable_count = 0
        required_stable_checks = 3  # File must be same size for 3 consecutive checks

        for _ in range(self.file_stable_timeout):
            if not path.exists():
                self.logger.warning(f"File disappeared: {path.name}")
                return False

            try:
                current_size = path.stat().st_size

                if current_size == last_size:
                    stable_count += 1
                    if stable_count >= required_stable_checks:
                        Log.trace(self.logger, f"File stable: {path.name} ({current_size} bytes)")
                        return True
                else:
                    stable_count = 0
                    Log.trace(self.logger, f"File still growing: {path.name} ({current_size} bytes)")

                last_size = current_size
                time.sleep(DELAY_STATUS_POLL)

            except OSError as e:
                self.logger.warning(f"Error checking file size: {e}")
                return False

        self.logger.warning(f"File stability timeout: {path.name}")
        return False

    def _queue_file(self, path: Path) -> None:
        """Add file to processing queue after validation."""
        if not self._is_valid_file(path):
            return

        # Check for duplicate
        if self.deduplicator:
            duplicate_info = self.deduplicator.is_duplicate(path)
            if duplicate_info:
                self.logger.info(
                    f"⏭️ Skipping duplicate: {path.name} "
                    f"(originally processed: {duplicate_info['processed_at']})"
                )
                with self.lock:
                    self.processed.add(str(path))
                return

        # Wait for file to be fully written
        if not self._wait_for_file_stable(path):
            self.logger.error(f"File not stable, skipping: {path.name}")
            return

        # Queue for processing
        with self.lock:
            self.processing.add(str(path))

        Log.trace(self.logger, f"📥 Queuing file: {path.name}")
        self.queue.put(path)
        self.logger.info(f"📥 New file queued: {path.name}")

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events."""
        if event.is_directory:
            return
        path = Path(event.src_path)
        self._queue_file(path)

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file move events (e.g., mv from temp location)."""
        if event.is_directory:
            return
        path = Path(event.dest_path)
        self._queue_file(path)

    def mark_completed(self, path: Path, success: bool) -> None:
        """Mark file as processed."""
        with self.lock:
            self.processing.discard(str(path))
            if success:
                self.processed.add(str(path))


class RetryManager:
    """Manages retry logic with exponential backoff."""

    def __init__(
        self,
        logger: logging.Logger,
        max_retries: int = 3,
        initial_delay: int = 300,
        backoff_multiplier: float = 2.0,
    ):
        self.logger = logger
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.backoff_multiplier = backoff_multiplier
        self.retry_queue: dict[str, dict[str, Any]] = {}
        self.lock = Lock()

    def should_retry(self, filename: str, error: str) -> bool:
        """Check if file should be retried."""
        with self.lock:
            if filename not in self.retry_queue:
                self.retry_queue[filename] = {
                    "attempts": 0,
                    "last_error": error,
                    "next_retry": time.time() + self.initial_delay,
                }
                return True

            retry_info = self.retry_queue[filename]
            if retry_info["attempts"] >= self.max_retries:
                self.logger.info(f"Max retries reached for {filename}")
                return False

            return not time.time() < retry_info["next_retry"]

    def record_retry(self, filename: str) -> int:
        """Record retry attempt and return retry count."""
        with self.lock:
            if filename not in self.retry_queue:
                return 0

            retry_info = self.retry_queue[filename]
            retry_info["attempts"] += 1

            # Calculate next retry time with exponential backoff
            delay = self.initial_delay * (self.backoff_multiplier ** retry_info["attempts"])
            retry_info["next_retry"] = time.time() + delay

            retry_count = retry_info["attempts"]
            next_retry_in = delay / 60

            self.logger.info(
                f"Retry {retry_count}/{self.max_retries} for {filename} "
                f"(next retry in {next_retry_in:.1f} minutes)"
            )

            return retry_count

    def get_pending_retries(self) -> list[tuple[str, dict]]:
        """Get files ready for retry."""
        with self.lock:
            now = time.time()
            return [
                (filename, info)
                for filename, info in self.retry_queue.items()
                if info["next_retry"] <= now and info["attempts"] < self.max_retries
            ]

    def clear_retry(self, filename: str) -> None:
        """Clear retry info (called on success)."""
        with self.lock:
            self.retry_queue.pop(filename, None)


class DaemonWatcher:
    """
    Enhanced daemon mode file watcher.

    Monitors a watch directory for new VM disk files and processes them
    through the h2kvm conversion pipeline with:
    - Concurrent processing
    - Retry on failure
    - Statistics tracking
    - Notifications
    - Deduplication
    - Control API
    """

    def __init__(self, logger: logging.Logger, args: argparse.Namespace):
        self.logger = logger
        self.args = args
        self.watch_dir = Path(args.watch_dir).expanduser().resolve()
        self.output_dir = Path(args.output_dir).expanduser().resolve()

        # Core components
        self.queue: Queue = Queue()
        self.stop_event = Event()
        self.pause_event = Event()  # For pause/resume
        self.drain_mode = False
        self.observer: Observer | None = None
        self.handler: VMFileHandler | None = None
        self.executor: ThreadPoolExecutor | None = None

        # Configuration
        self.max_workers = getattr(args, "max_concurrent_jobs", 3)
        self.file_stable_timeout = getattr(args, "file_stable_timeout", 30)
        self.enable_deduplication = getattr(args, "enable_deduplication", True)
        self.deduplication_use_md5 = getattr(args, "deduplication_use_md5", False)

        # Statistics
        stats_dir = self.output_dir / ".daemon"
        stats_dir.mkdir(parents=True, exist_ok=True)
        self.stats = DaemonStatistics(logger, stats_dir / "stats.json")

        # Deduplication
        self.deduplicator: FileDeduplicator | None = None
        if self.enable_deduplication:
            db_path = stats_dir / "deduplication.db"
            self.deduplicator = FileDeduplicator(logger, db_path, self.deduplication_use_md5)

        # Retry mechanism
        retry_config = getattr(args, "retry_policy", {})
        if isinstance(retry_config, dict) and retry_config.get("enabled", True):
            max_retries = retry_config.get("max_retries", 3)
            retry_delay = retry_config.get("retry_delay", 300)
            backoff_multiplier = retry_config.get("backoff_multiplier", 2.0)
        else:
            max_retries = 3
            retry_delay = 300
            backoff_multiplier = 2.0

        self.retry_manager = RetryManager(logger, max_retries, retry_delay, backoff_multiplier)

        # Notifications
        notification_config = getattr(args, "notifications", {})
        if isinstance(notification_config, dict):
            self.notifier = DaemonNotifier(logger, notification_config)
        else:
            self.notifier = DaemonNotifier(logger, {"enabled": False})

        # Control API (fixed path under /run/h2kvm, not output_dir/.daemon)
        self.control = DaemonControl(
            logger,
            DEFAULT_CONTROL_SOCKET,
            get_stats_callback=self.stats.get_summary,
            pause_callback=self.pause_event.set,
            resume_callback=self.pause_event.clear,
            stop_callback=self.stop,
        )

        # Last activity tracking (for stall detection)
        self.last_activity = datetime.now()

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGUSR1, self._stats_signal_handler)  # Print stats on SIGUSR1

    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals."""
        sig_name = signal.Signals(signum).name
        self.logger.info(f"🛑 Received {sig_name}, shutting down gracefully...")
        self.stop()

    def _stats_signal_handler(self, signum: int, frame) -> None:
        """Handle stats signal (USR1) - print statistics."""
        self.stats.print_summary()

    def _validate_directories(self) -> None:
        """Validate watch and output directories."""
        if not self.watch_dir.exists():
            Log.trace(self.logger, f"Creating watch directory: {self.watch_dir}")
            U.ensure_dir(self.watch_dir)

        if not self.watch_dir.is_dir():
            U.die(self.logger, f"Watch path is not a directory: {self.watch_dir}", 1)

        if not self.output_dir.exists():
            Log.trace(self.logger, f"Creating output directory: {self.output_dir}")
            U.ensure_dir(self.output_dir)

        if not self.output_dir.is_dir():
            U.die(self.logger, f"Output path is not a directory: {self.output_dir}", 1)

    def _save_error_context(
        self, file_path: Path, error: str, phase: str, exception_info: str | None = None
    ) -> None:
        """Save detailed error context to JSON file."""
        error_dir = self.watch_dir / ".errors"
        U.ensure_dir(error_dir)

        error_file = error_dir / f"{file_path.name}.error.json"

        error_context = {
            "filename": file_path.name,
            "filepath": str(file_path.absolute()),
            "file_size_mb": file_path.stat().st_size / (1024 * 1024) if file_path.exists() else 0,
            "timestamp": datetime.now().isoformat(),
            "error": error,
            "phase": phase,
            "exception_traceback": exception_info,
            "suggestion": self._get_error_suggestion(error, phase),
            "system_info": {
                "python_version": sys.version,
                "disk_space_free_gb": self._get_disk_space_free() / (1024**3),
            },
        }

        try:
            with open(error_file, "w") as f:
                json.dump(error_context, f, indent=2)
            Log.trace(self.logger, f"Error context saved: {error_file}")
        except Exception as e:
            self.logger.exception(f"Failed to save error context: {e}")

    def _get_error_suggestion(self, error: str, phase: str) -> str:
        """Get actionable suggestion based on error."""
        error_lower = error.lower()

        if "disk" in error_lower and ("full" in error_lower or "space" in error_lower):
            return "Free up disk space or configure a different output directory"
        if "permission" in error_lower or "denied" in error_lower:
            return "Check file permissions and ensure daemon has required access"
        if "corrupt" in error_lower or "invalid" in error_lower:
            return "Re-export the VM from source, the disk image may be corrupted"
        if "network" in error_lower or "timeout" in error_lower:
            return "Check network connectivity to source system"
        if "memory" in error_lower:
            return "Reduce max_concurrent_jobs or increase system memory"
        return f"Review logs for {phase} phase errors and retry if transient"

    def _get_disk_space_free(self) -> int:
        """Get free disk space in bytes."""
        try:
            stat = os.statvfs(str(self.output_dir))
            return stat.f_bavail * stat.f_frsize
        except OSError as e:
            self.logger.debug(f"Failed to get free space for {self.output_dir}: {e}")
            return 0

    def _process_file(self, file_path: Path, retry_count: int = 0) -> None:
        """
        Process a single VM disk file through the conversion pipeline.

        Args:
            file_path: Path to the VM disk file
            retry_count: Current retry attempt number
        """
        start_time = time.time()
        success = False
        error_message = None
        phase = "initialization"

        try:
            # Update last activity
            self.last_activity = datetime.now()

            # Check if paused
            while self.pause_event.is_set() and not self.stop_event.is_set():
                time.sleep(DELAY_STATUS_POLL)

            if self.stop_event.is_set():
                return

            # Log retry info
            retry_prefix = (
                f"[Retry {retry_count}/{self.retry_manager.max_retries}] " if retry_count > 0 else ""
            )
            self.logger.info(f"🔄 {retry_prefix}Processing: {file_path.name}")

            # Get file info for stats
            file_size_mb = file_path.stat().st_size / (1024 * 1024)
            file_type = file_path.suffix.lower().lstrip(".")

            # Record job start
            self.stats.job_started(file_path.name, file_type, file_size_mb)

            if retry_count > 0:
                self.stats.job_retried(file_path.name)

            # Determine file type and set appropriate command
            phase = "file_type_detection"
            ext = file_path.suffix.lower()

            # YAML config files: run h2kvmctl with --config directly
            if ext in {".yaml", ".yml"}:
                self.logger.info("📋 YAML config detected: %s — running as migration config", file_path.name)
                phase = "yaml_config_execution"
                import subprocess

                result = subprocess.run(
                    ["h2kvmctl", "--config", str(file_path)],
                    capture_output=True,
                    text=True,
                    timeout=3600,
                    check=False,
                )
                if result.returncode != 0:
                    error_message = f"h2kvmctl failed (exit {result.returncode}): {result.stderr[-500:] if result.stderr else 'no stderr'}"
                    raise RuntimeError(error_message)
                duration = time.time() - start_time
                self.logger.info("✅ YAML config completed: %s (%.1fs)", file_path.name, duration)
                success = True
                # Archive the YAML
                if getattr(self.args, "archive_processed", True):
                    date_dir = datetime.now().strftime("%Y-%m-%d")
                    archive_dir = self.watch_dir / ".processed" / date_dir
                    U.ensure_dir(archive_dir)
                    file_path.rename(archive_dir / file_path.name)
                self.stats.job_completed(file_path.name, duration, 0)
                self.notifier.notify_success(file_path.name, duration, None)
                return

            if ext == ".vmdk":
                cmd = "local"
            elif ext in {".ova"}:
                cmd = "ova"
            elif ext == ".ovf":
                cmd = "ovf"
            elif ext in {".vhd", ".vhdx"}:
                cmd = "vhd"
            elif ext in {".raw", ".img"}:
                cmd = "raw"
            elif ext == ".ami":
                cmd = "ami"
            else:
                error_message = f"Unknown file type: {ext}"
                self.logger.warning(f"⚠️ {error_message}, skipping {file_path.name}")
                return

            # Create a new args namespace for this file
            phase = "argument_preparation"
            file_args = argparse.Namespace(**vars(self.args))
            file_args.cmd = cmd

            # Set the input file path based on command type
            if cmd == "local":
                file_args.vmdk = str(file_path)
            elif cmd == "ova":
                file_args.ova = str(file_path)
            elif cmd == "ovf":
                file_args.ovf = str(file_path)
            elif cmd == "vhd":
                file_args.vhd = str(file_path)
            elif cmd == "raw":
                file_args.raw = str(file_path)
            elif cmd == "ami":
                file_args.ami = str(file_path)

            # Auto-detect Windows from filename and apply Windows-specific settings.
            name_lower = file_path.stem.lower()
            if "win" in name_lower:
                self.logger.info("🪟 Windows detected from filename: %s", file_path.name)
                file_args.guest_os = "windows"
                file_args.fstab_mode = "noop"
                file_args.regen_initramfs = False
                file_args.no_grub = True
                file_args.win_stage = "bootstrap"
                if not getattr(file_args, "memory", None) or file_args.memory < 4096:
                    file_args.memory = 8192
                if not getattr(file_args, "vcpus", None) or file_args.vcpus < 2:
                    file_args.vcpus = 4

            # Ensure SATA disk bus (default for all, required for Windows).
            if not getattr(file_args, "disk_bus", None):
                file_args.disk_bus = "sata"
            if not getattr(file_args, "machine", None):
                file_args.machine = "q35"
            if not getattr(file_args, "graphics", None):
                file_args.graphics = "vnc"
            if not getattr(file_args, "net_model", None):
                file_args.net_model = "virtio"

            # Set VM name from filename with unique suffix to avoid conflicts.
            import uuid

            short_id = uuid.uuid4().hex[:6]
            base_name = file_path.stem.replace(" ", "-")
            if not getattr(file_args, "vm_name", None):
                file_args.vm_name = f"{base_name}-{short_id}"

            # Ensure output format is qcow2 (convert VHD/VHDX/VMDK).
            if not getattr(file_args, "out_format", None):
                file_args.out_format = "qcow2"
            if not getattr(file_args, "to_output", None):
                file_args.to_output = f"{base_name}-{short_id}.qcow2"

            # Create output directory for this file
            phase = "output_directory_creation"
            # Use date-based subdirectory for better organization
            date_dir = datetime.now().strftime("%Y-%m-%d")
            file_output_dir = self.output_dir / date_dir / file_path.stem
            file_args.output_dir = str(file_output_dir)
            U.ensure_dir(file_output_dir)

            # Import here to avoid circular dependency
            from h2kvm.orchestration.orchestrator import Orchestrator

            # Run the conversion pipeline
            phase = "conversion"
            Log.step(self.logger, f"Converting: {file_path.name} → {file_output_dir}")
            orchestrator = Orchestrator(self.logger, file_args)
            orchestrator.run()

            # Success
            phase = "completion"
            duration = time.time() - start_time
            self.logger.info(f"✅ Completed: {file_path.name} ({duration:.1f}s)")
            success = True

            # Record in deduplication DB
            if self.deduplicator:
                self.deduplicator.mark_processed(file_path, file_output_dir, "success")

            # Clear retry info
            self.retry_manager.clear_retry(file_path.name)

            # Archive processed file
            if getattr(self.args, "archive_processed", True):  # Default to True
                archive_dir = self.watch_dir / ".processed" / date_dir
                U.ensure_dir(archive_dir)
                archive_path = archive_dir / file_path.name
                file_path.rename(archive_path)
                Log.trace(self.logger, f"📦 Archived: {file_path.name} → {archive_path}")

            # Send success notification
            self.notifier.notify_success(file_path.name, duration, file_output_dir)

        except Exception as e:
            success = False
            error_message = str(e)
            exception_trace = traceback.format_exc()

            self.logger.exception(f"❌ Failed to process {file_path.name}: {error_message}")
            self.logger.debug(f"💥 Processing exception:\n{exception_trace}")

            # Save detailed error context
            self._save_error_context(file_path, error_message, phase, exception_trace)

            # Check if should retry
            if not retry_count and self.retry_manager.should_retry(file_path.name, error_message):
                retry_count = self.retry_manager.record_retry(file_path.name)
                self.logger.info(f"🔄 Scheduling retry for {file_path.name}")
                # Don't move to errors, keep for retry
                return

            # Record in deduplication DB as failed
            if self.deduplicator:
                error_dir = self.watch_dir / ".errors"
                self.deduplicator.mark_processed(file_path, error_dir / file_path.name, "failed")

            # Move failed file to error directory
            error_dir = self.watch_dir / ".errors"
            U.ensure_dir(error_dir)
            error_path = error_dir / file_path.name
            try:
                if file_path.exists():
                    file_path.rename(error_path)
                    Log.trace(self.logger, f"📛 Moved to errors: {file_path.name} → {error_path}")
            except Exception as move_err:
                self.logger.exception(f"Failed to move error file: {move_err}")

            # Send failure notification
            self.notifier.notify_failure(file_path.name, error_message, retry_count)

        finally:
            # Record completion in stats
            duration = time.time() - start_time
            self.stats.job_completed(file_path.name, success, error_message)

    def _process_retries(self) -> None:
        """Process pending retries."""
        pending_retries = self.retry_manager.get_pending_retries()

        for filename, retry_info in pending_retries:
            # Find file in errors directory
            error_path = self.watch_dir / ".errors" / filename
            if error_path.exists():
                retry_count = retry_info["attempts"]
                self.logger.info(f"🔄 Retrying {filename} (attempt {retry_count + 1})")

                # Move back to watch directory
                retry_path = self.watch_dir / filename
                try:
                    error_path.rename(retry_path)
                    # Queue for processing with retry count
                    self.executor.submit(self._process_file, retry_path, retry_count)
                except Exception as e:
                    self.logger.exception(f"Failed to queue retry for {filename}: {e}")

    def _check_stalled(self) -> None:
        """Check if daemon appears stalled and send notification."""
        idle_minutes = (datetime.now() - self.last_activity).total_seconds() / 60
        stall_threshold_minutes = 60  # Alert if no activity for 60 minutes

        if idle_minutes > stall_threshold_minutes:
            queue_depth = self.queue.qsize()
            if queue_depth > 0:
                self.logger.warning(
                    f"⚠️ Daemon may be stalled: {queue_depth} items in queue, "
                    f"idle for {idle_minutes:.0f} minutes"
                )
                self.notifier.notify_stalled(queue_depth, self.last_activity)

    def _scan_existing_files(self) -> None:
        """Scan watch directory for existing files to process."""
        self.logger.info(f"🔍 Scanning existing files in: {self.watch_dir}")

        for ext in VMFileHandler.SUPPORTED_EXTENSIONS:
            pattern = f"*{ext}"
            for file_path in self.watch_dir.glob(pattern):
                if file_path.is_file():
                    # Check for duplicate
                    if self.deduplicator:
                        duplicate_info = self.deduplicator.is_duplicate(file_path)
                        if duplicate_info:
                            self.logger.info(f"⏭️ Skipping duplicate: {file_path.name}")
                            continue

                    Log.trace(self.logger, f"📥 Queuing existing file: {file_path.name}")
                    self.queue.put(file_path)
                    if self.handler:
                        with self.handler.lock:
                            self.handler.processing.add(str(file_path))

        queue_size = self.queue.qsize()
        if queue_size > 0:
            self.logger.info(f"📥 Found {queue_size} existing file(s) to process")
        else:
            self.logger.info("📭 No existing files found")

    def _worker_loop(self) -> None:
        """Worker loop for processing files from queue."""
        while not self.stop_event.is_set():
            try:
                # Wait for new file with timeout
                try:
                    file_path = self.queue.get(timeout=1.0)
                except Empty:
                    continue

                # Check drain mode
                if self.drain_mode and self.queue.empty():
                    self.logger.info("🚰 Queue drained, exiting")
                    self.stop()
                    break

                # Process the file
                self._process_file(file_path)

                # Mark as completed
                if self.handler:
                    self.handler.mark_completed(file_path, success=True)

                self.queue.task_done()

            except Exception as e:
                self.logger.exception(f"💥 Unexpected error in worker loop: {e}")
                self.logger.debug("💥 Worker loop exception", exc_info=True)
                time.sleep(5)  # Back off before retrying

    def run(self) -> None:
        """
        Start the daemon watcher.

        This method:
        1. Validates directories
        2. Starts control API
        3. Scans for existing files
        4. Starts file system observer
        5. Starts worker pool
        6. Monitors for retries and stalls
        """
        self.logger.info("🚀 Starting enhanced daemon mode")
        self.logger.info(f"👀 Watching: {self.watch_dir}")
        self.logger.info(f"📤 Output: {self.output_dir}")
        self.logger.info(f"⚙️  Workers: {self.max_workers}")

        self._validate_directories()

        # Start control API
        self.control.start()

        # Setup file system observer
        self.handler = VMFileHandler(
            self.logger, self.queue, self.watch_dir, self.deduplicator, self.file_stable_timeout
        )
        self.observer = Observer()
        self.observer.schedule(self.handler, str(self.watch_dir), recursive=False)
        self.observer.start()

        self.logger.info("👂 File system observer started")

        # Scan for existing files
        self._scan_existing_files()

        # Start worker pool
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        for _i in range(self.max_workers):
            self.executor.submit(self._worker_loop)

        self.logger.info("✅ Daemon ready")

        # Monitoring loop
        last_retry_check = time.time()
        last_stall_check = time.time()
        last_stats_print = time.time()

        retry_check_interval = 60  # Check for retries every minute
        stall_check_interval = 300  # Check for stalls every 5 minutes
        stats_print_interval = 3600  # Print stats every hour

        while not self.stop_event.is_set():
            try:
                time.sleep(10)  # Main loop sleep

                # Check for retries
                if time.time() - last_retry_check > retry_check_interval:
                    self._process_retries()
                    last_retry_check = time.time()

                # Check for stalls
                if time.time() - last_stall_check > stall_check_interval:
                    self._check_stalled()
                    last_stall_check = time.time()

                # Print stats periodically
                if time.time() - last_stats_print > stats_print_interval:
                    self.stats.print_summary()
                    last_stats_print = time.time()

            except Exception as e:
                self.logger.exception(f"💥 Monitoring loop error: {e}")

        self.logger.info("🛑 Daemon stopped")

    def stop(self) -> None:
        """Stop the daemon watcher."""
        self.logger.info("🛑 Stopping daemon...")
        self.stop_event.set()

        # Stop observer
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)

        # Stop executor
        if self.executor:
            self.executor.shutdown(wait=True, cancel_futures=False)

        # Stop control API
        self.control.stop()

        # Wait for queue to finish
        remaining = self.queue.qsize()
        if remaining > 0:
            self.logger.info(f"⏳ Waiting for {remaining} file(s) to complete...")
            # Don't wait indefinitely, give it max 60 seconds
            try:
                self.queue.join()
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as e:
                self.logger.debug(f"Queue join interrupted: {e}")

        # Save final stats
        self.stats.save(force=True)
        self.stats.print_summary()

        # Cleanup old deduplication records
        if self.deduplicator:
            self.deduplicator.cleanup_old_records(days=90)

        self.logger.info("✅ Daemon shutdown complete")
