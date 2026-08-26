# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/worker/metrics.py
"""
Prometheus metrics for Worker Job Protocol.

Exposes metrics for monitoring job execution, worker health, and resource usage.
"""

from __future__ import annotations

import logging
import threading
import time

try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        Info,
        start_http_server,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

from ...core.constants import DELAY_STATUS_POLL

logger = logging.getLogger(__name__)


class WorkerMetrics:
    """
    Prometheus metrics for worker operations.

    Metrics exposed:
    - hyper2kvm_migration_total: Total migrations (by status)
    - hyper2kvm_migration_duration_seconds: Migration duration histogram
    - hyper2kvm_migration_failures_total: Total migration failures
    - hyper2kvm_worker_info: Worker information (static)
    - hyper2kvm_worker_jobs_active: Current active jobs
    - hyper2kvm_vmdk_size_bytes: VMDK size distribution
    - hyper2kvm_conversion_temp_usage_bytes: Temp storage usage
    """

    def __init__(self, worker_id: str, enabled: bool = True):
        """
        Initialize metrics.

        Args:
            worker_id: Worker identifier
            enabled: Whether to enable metrics collection
        """
        self.worker_id = worker_id
        self.enabled = enabled and PROMETHEUS_AVAILABLE

        if not self.enabled:
            if not PROMETHEUS_AVAILABLE:
                logger.warning("Prometheus client not available, metrics disabled")
            return

        # Migration metrics
        self.migration_total = Counter(
            "hyper2kvm_migration_total", "Total number of migrations", ["worker_id", "operation", "status"]
        )

        self.migration_duration = Histogram(
            "hyper2kvm_migration_duration_seconds",
            "Migration duration in seconds",
            ["worker_id", "operation"],
            buckets=[60, 300, 600, 1800, 3600, 7200],
        )

        self.migration_failures = Counter(
            "hyper2kvm_migration_failures_total",
            "Total number of failed migrations",
            ["worker_id", "operation", "error_type"],
        )

        # Worker info (static labels)
        self.worker_info = Info("hyper2kvm_worker", "Worker information")

        # Active jobs
        self.jobs_active = Gauge(
            "hyper2kvm_worker_jobs_active", "Number of currently active jobs", ["worker_id"]
        )

        # Disk image size distribution
        self.vmdk_size = Histogram(
            "hyper2kvm_disk_image_size_bytes",
            "Disk image size distribution",
            ["worker_id"],
            buckets=[
                1e9,  # 1 GB
                10e9,  # 10 GB
                50e9,  # 50 GB
                100e9,  # 100 GB
                500e9,  # 500 GB
                1e12,  # 1 TB
                5e12,  # 5 TB
            ],
        )

        # Temp storage usage
        self.temp_usage = Gauge(
            "hyper2kvm_conversion_temp_usage_bytes", "Temporary storage usage in bytes", ["worker_id"]
        )

        self.temp_capacity = Gauge(
            "hyper2kvm_conversion_temp_capacity_bytes", "Temporary storage capacity in bytes", ["worker_id"]
        )

        logger.info(f"Metrics initialized for worker: {worker_id}")

    def set_worker_info(self, **kwargs):
        """Set worker information labels."""
        if not self.enabled:
            return

        info = {"worker_id": self.worker_id, **kwargs}
        self.worker_info.info(info)

    def record_migration_start(self, operation: str):
        """Record migration start."""
        if not self.enabled:
            return

        self.jobs_active.labels(worker_id=self.worker_id).inc()

    def record_migration_complete(
        self, operation: str, duration: float, success: bool, error_type: str | None = None
    ):
        """
        Record migration completion.

        Args:
            operation: Operation type (inspect, convert, etc.)
            duration: Duration in seconds
            success: Whether migration succeeded
            error_type: Error type if failed
        """
        if not self.enabled:
            return

        status = "success" if success else "failed"

        # Update counters
        self.migration_total.labels(worker_id=self.worker_id, operation=operation, status=status).inc()

        # Record duration
        self.migration_duration.labels(worker_id=self.worker_id, operation=operation).observe(duration)

        # Record failure details
        if not success and error_type:
            self.migration_failures.labels(
                worker_id=self.worker_id, operation=operation, error_type=error_type
            ).inc()

        # Decrement active jobs
        self.jobs_active.labels(worker_id=self.worker_id).dec()

    def record_vmdk_size(self, size_bytes: int):
        """Record disk image file size."""
        if not self.enabled:
            return

        self.vmdk_size.labels(worker_id=self.worker_id).observe(size_bytes)

    def update_temp_usage(self, usage_bytes: int, capacity_bytes: int):
        """Update temporary storage usage."""
        if not self.enabled:
            return

        self.temp_usage.labels(worker_id=self.worker_id).set(usage_bytes)
        self.temp_capacity.labels(worker_id=self.worker_id).set(capacity_bytes)


class MetricsServer:
    """
    HTTP server for Prometheus metrics.

    Runs in a background thread.
    """

    def __init__(self, port: int = 9090):
        """
        Initialize metrics server.

        Args:
            port: Port to listen on
        """
        self.port = port
        self._server_thread: threading.Thread | None = None
        self._running = False

        self.logger = logging.getLogger(__name__)

    def start(self):
        """Start metrics server in background thread."""
        if not PROMETHEUS_AVAILABLE:
            self.logger.warning("Prometheus client not available, metrics server not started")
            return

        if self._running:
            self.logger.warning("Metrics server already running")
            return

        def _run_server():
            try:
                self.logger.info(f"Starting metrics server on port {self.port}")
                start_http_server(self.port)
                self._running = True
                self.logger.info(f"Metrics server listening on :{self.port}/metrics")

                # Keep thread alive
                while self._running:
                    time.sleep(DELAY_STATUS_POLL)
            except Exception as e:
                self.logger.exception(f"Metrics server error: {e}")

        self._server_thread = threading.Thread(target=_run_server, daemon=True)
        self._server_thread.start()

    def stop(self):
        """Stop metrics server."""
        if self._running:
            self._running = False
            self.logger.info("Metrics server stopped")


# Global metrics instance
_metrics: WorkerMetrics | None = None
_metrics_server: MetricsServer | None = None


def get_metrics(worker_id: str) -> WorkerMetrics:
    """Get or create global metrics instance."""
    global _metrics
    if _metrics is None:
        _metrics = WorkerMetrics(worker_id)
    return _metrics


def start_metrics_server(port: int = 9090):
    """Start global metrics server."""
    global _metrics_server
    if _metrics_server is None:
        _metrics_server = MetricsServer(port)
        _metrics_server.start()
    return _metrics_server
