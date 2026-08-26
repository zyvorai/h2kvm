# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd Path Monitor Integration
=================================

inotify-based path monitoring for automatic VM repair triggering.
Monitors VM image directories and triggers repairs on changes.
"""

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

try:
    import inotify.adapters
    import inotify.constants

    INOTIFY_AVAILABLE = True
except ImportError:
    INOTIFY_AVAILABLE = False

try:
    import systemd.daemon

    SYSTEMD_AVAILABLE = True
except ImportError:
    SYSTEMD_AVAILABLE = False

from ...core.constants import DELAY_STATUS_POLL


@dataclass
class PathEvent:
    """File system event"""

    event_type: str
    path: Path
    filename: str
    timestamp: datetime
    is_directory: bool = False

    def __str__(self):
        return f"{self.event_type}: {self.path / self.filename} at {self.timestamp}"


class VMPathMonitor:
    """Monitor VM image directories for changes"""

    def __init__(
        self,
        watch_paths: Optional[list[str]] = None,
        callback: Optional[Callable[[PathEvent], None]] = None,
        file_extensions: Optional[list[str]] = None,
    ):
        """
        Args:
            watch_paths: List of directories to monitor
            callback: Function to call on file events
            file_extensions: Only monitor files with these extensions
        """
        self.logger = logging.getLogger(__name__)
        self.watch_paths = [Path(p) for p in (watch_paths or ["/var/lib/libvirt/images"])]
        self.callback = callback or self._default_callback
        self.file_extensions = file_extensions or [".vmdk", ".qcow2", ".vdi", ".vhd", ".vhdx"]

        self.monitoring = False
        self.monitor_thread = None
        self.event_history: list[PathEvent] = []
        self.max_history = 1000

        # Debouncing
        self.debounce_seconds = 5.0
        self.last_event_time: dict[Path, datetime] = {}
        self.processed_events: set[str] = set()

        if not INOTIFY_AVAILABLE:
            self.logger.error("inotify not available, path monitoring disabled")
            self.inotify = None
        else:
            self._setup_inotify()

    def _setup_inotify(self):
        """Setup inotify watcher"""
        try:
            self.inotify = inotify.adapters.Inotify()

            # Add watch paths
            for path in self.watch_paths:
                if not path.exists():
                    self.logger.warning(f"Watch path does not exist: {path}")
                    continue

                if not path.is_dir():
                    self.logger.warning(f"Watch path is not a directory: {path}")
                    continue

                # Watch for modifications, creations, and deletions
                mask = (
                    inotify.constants.IN_MODIFY
                    | inotify.constants.IN_CREATE
                    | inotify.constants.IN_DELETE
                    | inotify.constants.IN_MOVED_TO
                    | inotify.constants.IN_MOVED_FROM
                    | inotify.constants.IN_CLOSE_WRITE
                )

                self.inotify.add_watch(str(path), mask=mask)
                self.logger.info(f"Added watch for: {path}")

        except Exception as e:
            self.logger.exception(f"Failed to setup inotify: {e}")
            self.inotify = None

    def start(self):
        """Start monitoring"""
        if not INOTIFY_AVAILABLE or not self.inotify:
            self.logger.error("Cannot start monitoring: inotify not available")
            return

        if self.monitoring:
            self.logger.warning("Monitoring already active")
            return

        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

        # Notify systemd we're ready
        if SYSTEMD_AVAILABLE:
            systemd.daemon.notify("READY=1")

        self.logger.info("Path monitoring started")

    def stop(self):
        """Stop monitoring"""
        self.monitoring = False

        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)

        # Notify systemd we're stopping
        if SYSTEMD_AVAILABLE:
            systemd.daemon.notify("STOPPING=1")

        self.logger.info("Path monitoring stopped")

    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.monitoring:
            try:
                # Get events with 1 second timeout
                events = self.inotify.event_gen(timeout_s=1, yield_nones=False)

                for event in events:
                    self._process_event(event)

                # Clean up old processed events (keep last hour)
                self._cleanup_processed_events()

            except Exception as e:
                self.logger.exception(f"Error in monitoring loop: {e}")
                time.sleep(DELAY_STATUS_POLL)

    def _process_event(self, event):
        """Process an inotify event"""
        try:
            (header, type_names, watch_path, filename) = event

            # Skip if no filename
            if not filename:
                return

            # Get full path
            full_path = Path(watch_path) / filename

            # Filter by extension
            if not self._should_process_file(full_path):
                return

            # Check debounce
            if not self._check_debounce(full_path):
                return

            # Create event object
            event_type = "|".join(type_names)
            path_event = PathEvent(
                event_type=event_type,
                path=Path(watch_path),
                filename=filename,
                timestamp=datetime.now(),
                is_directory=header.dir,
            )

            # Add to history
            self.event_history.append(path_event)
            if len(self.event_history) > self.max_history:
                self.event_history = self.event_history[-self.max_history :]

            # Log event
            self.logger.info(f"File event: {path_event}")

            # Call callback
            try:
                self.callback(path_event)
            except Exception as e:
                self.logger.exception(f"Error in event callback: {e}")

        except Exception as e:
            self.logger.exception(f"Error processing event: {e}")

    def _should_process_file(self, path: Path) -> bool:
        """Check if file should be processed based on extension"""
        if path.is_dir():
            return False

        # Check extension
        if self.file_extensions:
            return path.suffix.lower() in [ext.lower() for ext in self.file_extensions]

        return True

    def _check_debounce(self, path: Path) -> bool:
        """Check if enough time has passed since last event for this path

        Args:
            path: File path

        Returns:
            True if event should be processed
        """
        now = datetime.now()
        event_key = str(path)

        # Check if we've seen this event recently
        if event_key in self.last_event_time:
            time_since_last = (now - self.last_event_time[event_key]).total_seconds()
            if time_since_last < self.debounce_seconds:
                self.logger.debug(f"Debouncing event for {path}")
                return False

        # Update last event time
        self.last_event_time[event_key] = now
        return True

    def _cleanup_processed_events(self):
        """Remove old entries from processed events set"""
        # This is a simple cleanup - in production might want to track timestamps
        if len(self.processed_events) > 10000:
            self.processed_events.clear()

    def _default_callback(self, event: PathEvent):
        """Default event callback - just log"""
        self.logger.info(f"Default handler: {event}")

    def get_recent_events(self, minutes: int = 60) -> list[PathEvent]:
        """Get events from recent time period

        Args:
            minutes: Number of minutes to look back

        Returns:
            List of recent events
        """
        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [e for e in self.event_history if e.timestamp >= cutoff]

    def get_events_for_path(self, path: Path) -> list[PathEvent]:
        """Get all events for a specific path

        Args:
            path: Path to filter by

        Returns:
            List of events for the path
        """
        return [e for e in self.event_history if (e.path / e.filename) == path]

    def add_watch_path(self, path: str):
        """Add a new directory to watch

        Args:
            path: Directory path to watch
        """
        if not INOTIFY_AVAILABLE or not self.inotify:
            self.logger.error("Cannot add watch: inotify not available")
            return

        watch_path = Path(path)

        if not watch_path.exists():
            self.logger.error(f"Path does not exist: {watch_path}")
            return

        if not watch_path.is_dir():
            self.logger.error(f"Path is not a directory: {watch_path}")
            return

        try:
            mask = (
                inotify.constants.IN_MODIFY
                | inotify.constants.IN_CREATE
                | inotify.constants.IN_DELETE
                | inotify.constants.IN_MOVED_TO
                | inotify.constants.IN_MOVED_FROM
                | inotify.constants.IN_CLOSE_WRITE
            )

            self.inotify.add_watch(str(watch_path), mask=mask)
            self.watch_paths.append(watch_path)
            self.logger.info(f"Added watch for: {watch_path}")

        except Exception as e:
            self.logger.exception(f"Failed to add watch for {watch_path}: {e}")

    def remove_watch_path(self, path: str):
        """Remove a directory from watch list

        Args:
            path: Directory path to stop watching
        """
        if not INOTIFY_AVAILABLE or not self.inotify:
            return

        watch_path = Path(path)

        try:
            self.inotify.remove_watch(str(watch_path))
            if watch_path in self.watch_paths:
                self.watch_paths.remove(watch_path)
            self.logger.info(f"Removed watch for: {watch_path}")

        except Exception as e:
            self.logger.exception(f"Failed to remove watch for {watch_path}: {e}")


class AutoRepairTrigger:
    """Automatically trigger repairs based on path events"""

    def __init__(
        self,
        watch_paths: Optional[list[str]] = None,
        repair_callback: Optional[Callable[[Path], None]] = None,
        min_file_size: int = 1024 * 1024,  # 1MB minimum
        cooldown_minutes: int = 30,
    ):
        """
        Args:
            watch_paths: Directories to monitor
            repair_callback: Function to call to trigger repair
            min_file_size: Minimum file size to trigger repair
            cooldown_minutes: Minutes to wait between repairs of same file
        """
        self.logger = logging.getLogger(__name__)
        self.repair_callback = repair_callback or self._default_repair
        self.min_file_size = min_file_size
        self.cooldown_minutes = cooldown_minutes

        # Track last repair times
        self.last_repair: dict[Path, datetime] = {}

        # Create path monitor with our event handler
        self.monitor = VMPathMonitor(watch_paths=watch_paths, callback=self._handle_event)

    def start(self):
        """Start auto-repair monitoring"""
        self.monitor.start()
        self.logger.info("Auto-repair trigger started")

    def stop(self):
        """Stop auto-repair monitoring"""
        self.monitor.stop()
        self.logger.info("Auto-repair trigger stopped")

    def _handle_event(self, event: PathEvent):
        """Handle file system event and potentially trigger repair"""
        # Only process CLOSE_WRITE events (file finished being written)
        if "IN_CLOSE_WRITE" not in event.event_type:
            return

        full_path = event.path / event.filename

        # Check if file exists and meets size requirement
        if not full_path.exists():
            return

        try:
            file_size = full_path.stat().st_size
            if file_size < self.min_file_size:
                self.logger.debug(f"File too small, skipping: {full_path}")
                return
        except Exception as e:
            self.logger.exception(f"Failed to check file size: {e}")
            return

        # Check cooldown
        if not self._check_cooldown(full_path):
            self.logger.info(f"Cooldown active for {full_path}, skipping repair")
            return

        # Trigger repair
        self.logger.info(f"Triggering auto-repair for: {full_path}")
        self._trigger_repair(full_path)

    def _check_cooldown(self, path: Path) -> bool:
        """Check if cooldown period has passed

        Args:
            path: File path to check

        Returns:
            True if repair can be triggered
        """
        if path not in self.last_repair:
            return True

        time_since_repair = datetime.now() - self.last_repair[path]
        return time_since_repair > timedelta(minutes=self.cooldown_minutes)

    def _trigger_repair(self, path: Path):
        """Trigger repair for a VM image

        Args:
            path: Path to VM image
        """
        try:
            self.repair_callback(path)
            self.last_repair[path] = datetime.now()
        except Exception as e:
            self.logger.exception(f"Failed to trigger repair for {path}: {e}")

    def _default_repair(self, path: Path):
        """Default repair callback - just log"""
        self.logger.info(f"Default repair triggered for: {path}")


def start_path_monitor_daemon(watch_paths: Optional[list[str]] = None, callback: Optional[Callable] = None):
    """Start path monitor as a daemon service

    This function is designed to be called from a systemd service.

    Args:
        watch_paths: Directories to monitor
        callback: Event callback function
    """
    import signal
    import sys

    logger = logging.getLogger(__name__)

    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    monitor = VMPathMonitor(watch_paths, callback)

    # Setup signal handlers
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        monitor.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Start monitoring
    try:
        logger.info("Starting path monitor daemon")
        monitor.start()

        # Keep main thread alive
        while monitor.monitoring:
            time.sleep(DELAY_STATUS_POLL)

    except Exception as e:
        logger.exception(f"Monitor failed: {e}")
        sys.exit(1)
