#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Complete example: Daemon Mode + Prometheus Metrics

This example demonstrates:
1. Manifest file watching (with watchdog or polling fallback)
2. Prometheus metrics collection
3. HTTP metrics endpoint
4. Automatic manifest processing

Features work on RHEL 10 even without watchdog!
"""

import logging
import signal
import sys
import time
from pathlib import Path

# Check what's available
from hyper2kvm.core.optional_imports import WATCHDOG_AVAILABLE
from hyper2kvm.core.metrics import PROMETHEUS_AVAILABLE

print("=" * 70)
print("Daemon Mode + Prometheus Metrics Example")
print("=" * 70)
print(f"Watchdog available: {WATCHDOG_AVAILABLE}")
print(f"  Mode: {'Efficient inotify' if WATCHDOG_AVAILABLE else 'Polling fallback (RHEL 10)'}")
print(f"Prometheus available: {PROMETHEUS_AVAILABLE}")
print(f"  Metrics: {'Enabled' if PROMETHEUS_AVAILABLE else 'Disabled (stubs)'}")
print("=" * 70)
print()

# Setup logging
from hyper2kvm.core.logger import Log

logger = Log.setup(verbose=2, json_logs=False, show_proc=True)

# Import components
from hyper2kvm.runtime.daemon.manifest_watcher import DaemonManifestWatcher
from hyper2kvm.runtime.daemon.manifest_processor import create_manifest_processor_callback
from hyper2kvm.runtime.daemon.metrics_server import start_metrics_server
from hyper2kvm.core.metrics import (
    manifests_processed_total,
    manifest_vms_total,
    migrations_total,
    get_metrics,
)

# Configuration
WATCH_DIR = Path("/tmp/hyper2kvm-daemon-example/manifests")
OUTPUT_DIR = Path("/tmp/hyper2kvm-daemon-example/output")
METRICS_PORT = 9091  # Use 9091 to avoid conflicts

# Create directories
WATCH_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print(f"Watch directory: {WATCH_DIR}")
print(f"Output directory: {OUTPUT_DIR}")
print()


# Example: Custom manifest processor with metrics
class ExampleProcessor:
    """Enhanced processor that tracks metrics."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.processed_count = 0

    def process_manifest(self, manifest_path: Path) -> bool:
        """Process manifest with metrics tracking."""
        logger.info(f"Processing manifest: {manifest_path.name}")

        try:
            # Simulate processing
            time.sleep(0.5)

            # Update counters
            self.processed_count += 1

            # Update metrics
            manifests_processed_total.labels(status="success").inc()
            manifest_vms_total.labels(status="success").inc()
            migrations_total.labels(hypervisor="vmware", status="success").inc()

            logger.info(f"Successfully processed: {manifest_path.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to process {manifest_path.name}: {e}")
            manifests_processed_total.labels(status="failed").inc()
            return False


# Setup components
def main():
    """Main daemon loop."""

    # 1. Start metrics server
    logger.info("Starting metrics server")
    try:
        metrics_server = start_metrics_server(port=METRICS_PORT)
        logger.info(f"✓ Metrics server running on http://localhost:{METRICS_PORT}/metrics")
        if PROMETHEUS_AVAILABLE:
            logger.info("  Open in browser to see metrics")
        else:
            logger.warning("  Prometheus client not installed - metrics are stubs")
    except Exception as e:
        logger.error(f"Failed to start metrics server: {e}")
        return 1

    # 2. Create manifest processor
    processor = ExampleProcessor(OUTPUT_DIR)

    # 3. Start manifest watcher daemon
    logger.info("Starting manifest watcher daemon")
    daemon = DaemonManifestWatcher(
        watch_dir=WATCH_DIR,
        processor_callback=processor.process_manifest,
        poll_interval=2,  # 2s for demo
    )

    daemon.start()
    logger.info(f"✓ Daemon watching: {WATCH_DIR}")

    if WATCHDOG_AVAILABLE:
        logger.info("  Using watchdog for efficient file monitoring")
    else:
        logger.info("  Using polling mode (RHEL 10 compatible)")

    # 4. Print instructions
    print()
    print("=" * 70)
    print("Daemon is now running!")
    print("=" * 70)
    print()
    print("Try it out:")
    print(f"  1. Create a test manifest:")
    print(f"     echo 'hypervisor: vmware' > {WATCH_DIR}/test.yaml")
    print(f"     echo 'vmware:' >> {WATCH_DIR}/test.yaml")
    print(f"       vm_name: test-vm' >> {WATCH_DIR}/test.yaml")
    print()
    print(f"  2. View metrics:")
    print(f"     curl http://localhost:{METRICS_PORT}/metrics")
    print()
    print(f"  3. View metrics in browser:")
    print(f"     http://localhost:{METRICS_PORT}/")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 70)
    print()

    # 5. Handle shutdown gracefully
    def signal_handler(signum, frame):
        logger.info("\nReceived shutdown signal")
        daemon.stop()
        metrics_server.stop()
        logger.info("Shutdown complete")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 6. Main loop - monitor and report
    try:
        iteration = 0
        while daemon.is_running():
            time.sleep(5)
            iteration += 1

            # Print status every 30 seconds
            if iteration % 6 == 0:
                logger.info(
                    f"Status: Processed {processor.processed_count} manifests, "
                    f"daemon running: {daemon.is_running()}, "
                    f"metrics server running: {metrics_server.is_running()}"
                )

                # Show current metrics (if available)
                if PROMETHEUS_AVAILABLE:
                    metrics = get_metrics().decode("utf-8")
                    # Extract interesting metrics
                    for line in metrics.split("\n"):
                        if "hyper2kvm_manifests" in line and not line.startswith("#"):
                            logger.info(f"  Metric: {line}")

    except KeyboardInterrupt:
        logger.info("\nShutting down...")
        daemon.stop()
        metrics_server.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
