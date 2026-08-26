# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/daemon/manifest_watcher.py
"""
Manifest file watcher for automatic migration processing.

Watches for YAML/JSON manifest files and triggers migrations automatically.
Uses watchdog when available, falls back to polling for RHEL 10 compatibility.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Callable

from ...core.constants import DELAY_STATUS_POLL
from ...core.optional_imports import WATCHDOG_AVAILABLE

if WATCHDOG_AVAILABLE:
    from ...core.optional_imports import FileCreatedEvent, FileSystemEventHandler, Observer

logger = logging.getLogger(__name__)


class ManifestHandler:
    """Handler for new migration manifest files."""

    SUPPORTED_EXTENSIONS = {".yaml", ".yml", ".json"}

    def __init__(self, processor_callback: Callable[[Path], None]):
        self.processor_callback = processor_callback
        self._lock = Lock()
        self.processing: set[str] = set()  # Track files currently being processed
        self.processed: set[str] = set()  # Track files already processed

    def _is_valid_manifest(self, file_path: Path) -> bool:
        """Check if file is a valid manifest."""
        if not file_path.is_file():
            return False
        if file_path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            return False
        path_str = str(file_path)
        with self._lock:
            if path_str in self.processing or path_str in self.processed:
                return False
        # Ignore hidden files and temp files
        return not (file_path.name.startswith(".") or file_path.name.endswith("~"))

    def _process_manifest(self, manifest_path: Path):
        """Process a detected manifest file."""
        path_str = str(manifest_path)

        with self._lock:
            if path_str in self.processing or path_str in self.processed:
                logger.debug(f"Manifest already processed or being processed: {manifest_path.name}")
                return
            self.processing.add(path_str)

        try:
            logger.info(f"Manifest detected: {manifest_path.name}")

            # Wait a bit to ensure file is fully written
            time.sleep(0.5)

            if not manifest_path.exists():
                logger.warning(f"Manifest disappeared: {manifest_path.name}")
                return

            # Process the manifest
            self.processor_callback(manifest_path)

            logger.info(f"Manifest processed successfully: {manifest_path.name}")

            # Mark as processed
            with self._lock:
                self.processed.add(path_str)

        except Exception as e:
            logger.error(f"Failed to process manifest {manifest_path.name}: {e}", exc_info=True)

        finally:
            with self._lock:
                self.processing.discard(path_str)


if WATCHDOG_AVAILABLE:
    # Use watchdog for efficient file watching

    class WatchdogManifestHandler(FileSystemEventHandler):  # type: ignore
        """Watchdog-based file system event handler."""

        def __init__(self, handler: ManifestHandler):
            super().__init__()
            self.handler = handler

        def on_created(self, event):
            """Handle file creation events."""
            if not isinstance(event, FileCreatedEvent):
                return

            file_path = Path(event.src_path)

            if self.handler._is_valid_manifest(file_path):
                self.handler._process_manifest(file_path)

    class ManifestWatcher:
        """Watchdog-based manifest watcher."""

        def __init__(self, watch_dir: Path, processor_callback: Callable[[Path], None]):
            self.watch_dir = Path(watch_dir)
            self.processor_callback = processor_callback
            self.handler = ManifestHandler(processor_callback)
            self.fs_handler = WatchdogManifestHandler(self.handler)
            self.observer = Observer()  # type: ignore
            self._running = False

        def start(self):
            """Start watching directory."""
            self.watch_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"Starting manifest watcher (watchdog): {self.watch_dir}")

            self.observer.schedule(self.fs_handler, path=str(self.watch_dir), recursive=False)
            self.observer.start()
            self._running = True

            logger.info("Manifest watcher started successfully")

        def stop(self):
            """Stop watching."""
            if self._running:
                logger.info("Stopping manifest watcher")
                self.observer.stop()
                self.observer.join()
                self._running = False

        def is_running(self) -> bool:
            """Check if watcher is running."""
            return self._running

else:
    # Polling fallback for RHEL 10

    class ManifestWatcher:
        """Polling-based manifest watcher (RHEL 10 compatible)."""

        def __init__(
            self, watch_dir: Path, processor_callback: Callable[[Path], None], poll_interval: int = 5
        ):
            self.watch_dir = Path(watch_dir)
            self.processor_callback = processor_callback
            self.poll_interval = poll_interval
            self.handler = ManifestHandler(processor_callback)
            self._stop_event = Event()
            self._thread: Thread | None = None
            self._seen_files: set[str] = set()

        def _poll_directory(self):
            """Poll directory for new manifest files."""
            try:
                if not self.watch_dir.exists():
                    return

                for file_path in self.watch_dir.iterdir():
                    if not self.handler._is_valid_manifest(file_path):
                        continue

                    path_str = str(file_path)

                    # Check if this is a new file we haven't seen
                    if path_str not in self._seen_files:
                        self._seen_files.add(path_str)
                        self.handler._process_manifest(file_path)

            except Exception as e:
                logger.exception(f"Error polling directory: {e}")

        def _poll_loop(self):
            """Main polling loop."""
            logger.info(f"Starting manifest watcher (polling mode, interval={self.poll_interval}s)")

            while not self._stop_event.is_set():
                self._poll_directory()
                self._stop_event.wait(self.poll_interval)

            logger.info("Polling loop stopped")

        def start(self):
            """Start watching directory."""
            self.watch_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"Starting manifest watcher (polling): {self.watch_dir}")

            # Scan existing files first
            for file_path in self.watch_dir.iterdir():
                if self.handler._is_valid_manifest(file_path):
                    self._seen_files.add(str(file_path))

            # Start polling thread
            self._stop_event.clear()
            self._thread = Thread(target=self._poll_loop, daemon=True)
            self._thread.start()

            logger.info("Manifest watcher started successfully (polling mode)")

        def stop(self):
            """Stop watching."""
            if self._thread and self._thread.is_alive():
                logger.info("Stopping manifest watcher")
                self._stop_event.set()
                self._thread.join(timeout=10)

        def is_running(self) -> bool:
            """Check if watcher is running."""
            return self._thread is not None and self._thread.is_alive()


class DaemonManifestWatcher:
    """
    High-level daemon for watching and processing migration manifests.

    Automatically selects watchdog or polling based on availability.
    """

    def __init__(self, watch_dir: Path, processor_callback: Callable[[Path], None], poll_interval: int = 5):
        """
        Initialize manifest watcher daemon.

        Args:
            watch_dir: Directory to watch for manifest files
            processor_callback: Function to call when manifest is detected
            poll_interval: Polling interval in seconds (only used in polling mode)
        """
        self.watch_dir = Path(watch_dir)
        self.processor_callback = processor_callback
        self.poll_interval = poll_interval

        # Create appropriate watcher
        if WATCHDOG_AVAILABLE:
            logger.info("Using watchdog for efficient file watching")
            self.watcher = ManifestWatcher(watch_dir, processor_callback)
        else:
            logger.info(f"Watchdog not available, using polling (interval={poll_interval}s)")
            self.watcher = ManifestWatcher(watch_dir, processor_callback, poll_interval)  # type: ignore

    def start(self):
        """Start the daemon."""
        self.watcher.start()

    def stop(self):
        """Stop the daemon."""
        self.watcher.stop()

    def run_forever(self):
        """Run daemon in foreground (blocks)."""
        self.start()

        try:
            while self.watcher.is_running():
                time.sleep(DELAY_STATUS_POLL)
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        finally:
            self.stop()

    def is_running(self) -> bool:
        """Check if daemon is running."""
        return self.watcher.is_running()


# Convenience function
def start_manifest_daemon(
    watch_dir: Path, processor_callback: Callable[[Path], None], poll_interval: int = 5
):
    """
    Start manifest watching daemon.

    Args:
        watch_dir: Directory to watch
        processor_callback: Function to process manifests
        poll_interval: Polling interval for fallback mode

    Returns:
        DaemonManifestWatcher instance
    """
    daemon = DaemonManifestWatcher(watch_dir, processor_callback, poll_interval)
    daemon.start()
    return daemon
