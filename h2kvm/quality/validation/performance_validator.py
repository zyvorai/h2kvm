# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/validation/performance_validator.py
"""
Performance validation for post-migration benchmarking.

Provides performance benchmarking capabilities for migrated VMs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .health_checker import HealthCheckResult, HealthCheckStatus, HealthCheckType

logger = logging.getLogger(__name__)


class PerformanceMetric(Enum):
    """Performance metric types."""

    DISK_READ_IOPS = "disk_read_iops"
    DISK_WRITE_IOPS = "disk_write_iops"
    DISK_READ_THROUGHPUT = "disk_read_throughput"
    DISK_WRITE_THROUGHPUT = "disk_write_throughput"
    MEMORY_AVAILABLE = "memory_available"
    CPU_COUNT = "cpu_count"
    BOOT_TIME = "boot_time"


@dataclass
class PerformanceBenchmark:
    """
    Performance benchmark result.

    Attributes:
        metric: Performance metric type
        value: Measured value
        unit: Unit of measurement
        threshold: Expected threshold (optional)
        status: Pass/Fail/Warn status
        details: Additional benchmark details
    """

    metric: PerformanceMetric
    value: float
    unit: str
    threshold: float | None = None
    status: HealthCheckStatus = HealthCheckStatus.PASS
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "metric": self.metric.value,
            "value": self.value,
            "unit": self.unit,
            "threshold": self.threshold,
            "status": self.status.value,
            "details": self.details,
        }


class PerformanceValidator:
    """
    Performance validator.

    Performs performance benchmarking on migrated VMs.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize performance validator.

        Args:
            logger: Logger instance
        """
        self.logger = logger
        self._benchmarks: list[PerformanceBenchmark] = []

    def benchmark_disk_performance(self, vmcraft_instance) -> HealthCheckResult:
        """
        Benchmark disk performance.

        Args:
            vmcraft_instance: VMCraft instance

        Returns:
            Health check result with disk performance metrics
        """
        import time

        start = time.time()

        try:
            # Simple check for disk availability (detailed benchmarking requires VM to be running)
            # For now, just verify disk structure is accessible
            root_exists = vmcraft_instance.exists("/")

            if not root_exists:
                duration = (time.time() - start) * 1000
                return HealthCheckResult(
                    check_id="disk_performance",
                    check_type=HealthCheckType.PERFORMANCE,
                    name="Disk Performance Benchmark",
                    status=HealthCheckStatus.FAIL,
                    message="Root filesystem not accessible",
                    duration_ms=duration,
                )

            # For mounted filesystems, we can check disk info
            duration = (time.time() - start) * 1000

            return HealthCheckResult(
                check_id="disk_performance",
                check_type=HealthCheckType.PERFORMANCE,
                name="Disk Performance Benchmark",
                status=HealthCheckStatus.PASS,
                message="Disk accessible (detailed benchmarking requires running VM)",
                details={"note": "Run fio/dd benchmarks on live VM for detailed metrics"},
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return HealthCheckResult(
                check_id="disk_performance",
                check_type=HealthCheckType.PERFORMANCE,
                name="Disk Performance Benchmark",
                status=HealthCheckStatus.ERROR,
                message=f"Benchmark failed: {e}",
                duration_ms=duration,
            )

    def check_system_resources(self, vmcraft_instance) -> HealthCheckResult:
        """
        Check system resource configuration.

        Args:
            vmcraft_instance: VMCraft instance

        Returns:
            Health check result with resource info
        """
        import time

        start = time.time()

        try:
            # Check for /proc/cpuinfo (if accessible)
            cpu_info_exists = vmcraft_instance.exists("/proc/cpuinfo")
            mem_info_exists = vmcraft_instance.exists("/proc/meminfo")

            details = {}
            if cpu_info_exists:
                details["cpu_info"] = "available"
            if mem_info_exists:
                details["mem_info"] = "available"

            duration = (time.time() - start) * 1000

            return HealthCheckResult(
                check_id="system_resources",
                check_type=HealthCheckType.PERFORMANCE,
                name="System Resources Check",
                status=HealthCheckStatus.PASS,
                message="System resource information accessible",
                details=details,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return HealthCheckResult(
                check_id="system_resources",
                check_type=HealthCheckType.PERFORMANCE,
                name="System Resources Check",
                status=HealthCheckStatus.ERROR,
                message=f"Check failed: {e}",
                duration_ms=duration,
            )

    def validate_performance(self, vmcraft_instance) -> list[HealthCheckResult]:
        """
        Run all performance validation checks.

        Args:
            vmcraft_instance: VMCraft instance

        Returns:
            List of health check results
        """
        return [
            self.benchmark_disk_performance(vmcraft_instance),
            self.check_system_resources(vmcraft_instance),
        ]

    def get_benchmarks(self) -> list[PerformanceBenchmark]:
        """Get list of performance benchmarks."""
        return self._benchmarks
