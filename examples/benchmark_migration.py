#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Migration Performance Benchmarking Tool

Benchmarks and compares migration performance across different:
- Disk image formats (VMDK, VHD, RAW)
- Compression levels
- Filesystem types
- VM sizes

Generates detailed performance reports with:
- Throughput metrics (MB/s)
- Compression ratios
- Memory usage
- CPU utilization
- Time breakdowns by phase

Usage:
    python3 benchmark_migration.py <disk-image> [options]

Example:
    python3 benchmark_migration.py /vmware/vm.vmdk --iterations 3 --output benchmark_results.json
"""

import sys
import time
import json
import psutil
import argparse
from pathlib import Path
from typing import Any
from dataclasses import dataclass, asdict
from datetime import datetime

from hyper2kvm.vmcraft.main import VMCraft


@dataclass
class BenchmarkResult:
    """Single benchmark measurement result."""

    iteration: int
    phase: str
    duration_seconds: float
    throughput_mbps: float
    memory_mb: float
    cpu_percent: float
    disk_read_mb: float
    disk_write_mb: float


@dataclass
class PhaseMetrics:
    """Aggregated metrics for a phase."""

    phase_name: str
    avg_duration: float
    min_duration: float
    max_duration: float
    avg_throughput: float
    avg_memory_mb: float
    avg_cpu_percent: float
    total_disk_read_mb: float
    total_disk_write_mb: float


class MigrationBenchmark:
    """Performance benchmarking for VM migrations."""

    def __init__(self, disk_image: Path, iterations: int = 3):
        """
        Initialize benchmark.

        Args:
            disk_image: Path to disk image to benchmark
            iterations: Number of iterations to run
        """
        self.disk_image = disk_image
        self.iterations = iterations
        self.results: list[BenchmarkResult] = []

        # Get disk size
        self.disk_size_mb = disk_image.stat().st_size / (1024 * 1024)

        # Process monitoring
        self.process = psutil.Process()

    def measure_resource_usage(self) -> tuple[float, float, float, float]:
        """
        Measure current resource usage.

        Returns:
            Tuple of (memory_mb, cpu_percent, disk_read_mb, disk_write_mb)
        """
        mem_info = self.process.memory_info()
        memory_mb = mem_info.rss / (1024 * 1024)
        cpu_percent = self.process.cpu_percent(interval=0.1)

        # Get disk I/O
        try:
            io_counters = self.process.io_counters()
            disk_read_mb = io_counters.read_bytes / (1024 * 1024)
            disk_write_mb = io_counters.write_bytes / (1024 * 1024)
        except Exception:
            disk_read_mb = 0
            disk_write_mb = 0

        return memory_mb, cpu_percent, disk_read_mb, disk_write_mb

    def benchmark_phase(self, phase_name: str, operation: callable, iteration: int):
        """
        Benchmark a single phase.

        Args:
            phase_name: Name of the phase
            operation: Callable to execute
            iteration: Current iteration number
        """
        print(f"  [{iteration}/{self.iterations}] {phase_name}...", end=" ", flush=True)

        # Measure baseline
        baseline_mem, _, baseline_read, baseline_write = self.measure_resource_usage()

        # Execute operation with timing
        start_time = time.time()
        operation()
        duration = time.time() - start_time

        # Measure final
        final_mem, cpu_pct, final_read, final_write = self.measure_resource_usage()

        # Calculate metrics
        memory_mb = max(final_mem - baseline_mem, 0)
        disk_read_mb = final_read - baseline_read
        disk_write_mb = final_write - baseline_write
        throughput_mbps = self.disk_size_mb / duration if duration > 0 else 0

        # Store result
        result = BenchmarkResult(
            iteration=iteration,
            phase=phase_name,
            duration_seconds=duration,
            throughput_mbps=throughput_mbps,
            memory_mb=memory_mb,
            cpu_percent=cpu_pct,
            disk_read_mb=disk_read_mb,
            disk_write_mb=disk_write_mb,
        )
        self.results.append(result)

        print(f"{duration:.2f}s ({throughput_mbps:.1f} MB/s)")

    def benchmark_vmcraft_operations(self):
        """Benchmark VMCraft operations."""
        print(f"\n{'=' * 80}")
        print(f" Benchmarking: {self.disk_image.name}")
        print(f" Size: {self.disk_size_mb:.2f} MB ({self.disk_size_mb / 1024:.2f} GB)")
        print(f" Iterations: {self.iterations}")
        print(f"{'=' * 80}\n")

        for iteration in range(1, self.iterations + 1):
            print(f"Iteration {iteration}/{self.iterations}:")

            # Phase 1: Launch (NBD connection + mount)
            def launch_phase():
                g = VMCraft()
                g.add_drive_opts(str(self.disk_image), readonly=True)
                g.launch()
                return g

            g = None
            self.benchmark_phase("Launch", lambda: globals().update({"g": launch_phase()}), iteration)
            g = globals()["g"]

            # Phase 2: OS Inspection
            def inspect_os_phase():
                g.inspect_os()

            self.benchmark_phase("OS Inspection", inspect_os_phase, iteration)

            # Phase 3: Filesystem Detection
            def filesystem_phase():
                filesystems = g.list_filesystems()
                for device in list(filesystems.keys())[:5]:  # First 5
                    g.vfs_type(device)
                    g.vfs_uuid(device)

            self.benchmark_phase("Filesystem Detection", filesystem_phase, iteration)

            # Phase 4: Partition Analysis
            def partition_phase():
                filesystems = g.list_filesystems()
                for device in filesystems.keys():
                    try:
                        g.part_to_partnum(device)
                        g.part_to_dev(device)
                    except Exception:
                        pass

            self.benchmark_phase("Partition Analysis", partition_phase, iteration)

            # Phase 5: Block Device Query
            def blockdev_phase():
                devices = g.list_devices()
                for device in devices:
                    g.blockdev_getsize64(device)
                    g.blockdev_getss(device)
                    g.blockdev_getbsz(device)

            self.benchmark_phase("Block Device Query", blockdev_phase, iteration)

            # Phase 6: Systemd Analysis (if available)
            def systemd_phase():
                try:
                    g.systemctl_list_units("service", all_units=True)
                    g.systemctl_list_failed()
                    g.systemd_analyze_time()
                except Exception:
                    pass  # Skip if not available

            self.benchmark_phase("Systemd Analysis", systemd_phase, iteration)

            # Phase 7: Shutdown
            def shutdown_phase():
                g.shutdown()

            self.benchmark_phase("Shutdown", shutdown_phase, iteration)

            print()

    def calculate_phase_metrics(self) -> list[PhaseMetrics]:
        """
        Calculate aggregated metrics per phase.

        Returns:
            List of PhaseMetrics
        """
        phases = {}

        # Group results by phase
        for result in self.results:
            if result.phase not in phases:
                phases[result.phase] = []
            phases[result.phase].append(result)

        # Calculate metrics for each phase
        metrics = []
        for phase_name, phase_results in phases.items():
            durations = [r.duration_seconds for r in phase_results]
            throughputs = [r.throughput_mbps for r in phase_results]
            memories = [r.memory_mb for r in phase_results]
            cpus = [r.cpu_percent for r in phase_results]
            disk_reads = [r.disk_read_mb for r in phase_results]
            disk_writes = [r.disk_write_mb for r in phase_results]

            metrics.append(
                PhaseMetrics(
                    phase_name=phase_name,
                    avg_duration=sum(durations) / len(durations),
                    min_duration=min(durations),
                    max_duration=max(durations),
                    avg_throughput=sum(throughputs) / len(throughputs),
                    avg_memory_mb=sum(memories) / len(memories),
                    avg_cpu_percent=sum(cpus) / len(cpus),
                    total_disk_read_mb=sum(disk_reads),
                    total_disk_write_mb=sum(disk_writes),
                )
            )

        return metrics

    def print_summary(self):
        """Print benchmark summary."""
        print(f"\n{'=' * 80}")
        print(f" BENCHMARK SUMMARY")
        print(f"{'=' * 80}\n")

        metrics = self.calculate_phase_metrics()

        # Print phase-by-phase breakdown
        print(f"{'Phase':<25s} {'Avg Time':>10s} {'Min Time':>10s} {'Max Time':>10s} {'Throughput':>12s}")
        print(f"{'-' * 80}")

        total_avg_time = 0
        for m in metrics:
            total_avg_time += m.avg_duration
            print(
                f"{m.phase_name:<25s} "
                f"{m.avg_duration:>9.2f}s "
                f"{m.min_duration:>9.2f}s "
                f"{m.max_duration:>9.2f}s "
                f"{m.avg_throughput:>10.1f} MB/s"
            )

        print(f"{'-' * 80}")
        print(f"{'TOTAL':<25s} {total_avg_time:>9.2f}s")

        # Resource usage summary
        print(f"\n{'=' * 80}")
        print(f" RESOURCE USAGE")
        print(f"{'=' * 80}\n")

        print(f"{'Phase':<25s} {'Memory':>12s} {'CPU':>10s} {'Disk Read':>12s} {'Disk Write':>12s}")
        print(f"{'-' * 80}")

        for m in metrics:
            print(
                f"{m.phase_name:<25s} "
                f"{m.avg_memory_mb:>10.1f} MB "
                f"{m.avg_cpu_percent:>8.1f}% "
                f"{m.total_disk_read_mb:>10.1f} MB "
                f"{m.total_disk_write_mb:>10.1f} MB"
            )

        # Overall statistics
        total_disk_read = sum(m.total_disk_read_mb for m in metrics)
        total_disk_write = sum(m.total_disk_write_mb for m in metrics)
        avg_memory = sum(m.avg_memory_mb for m in metrics) / len(metrics)
        avg_cpu = sum(m.avg_cpu_percent for m in metrics) / len(metrics)

        print(f"\n{'=' * 80}")
        print(f" OVERALL STATISTICS")
        print(f"{'=' * 80}\n")

        print(f"  Disk Image:        {self.disk_image.name}")
        print(f"  Size:              {self.disk_size_mb:.2f} MB ({self.disk_size_mb / 1024:.2f} GB)")
        print(f"  Iterations:        {self.iterations}")
        print(f"  Total Time (avg):  {total_avg_time:.2f}s")
        print(f"  Avg Memory:        {avg_memory:.1f} MB")
        print(f"  Avg CPU:           {avg_cpu:.1f}%")
        print(f"  Total Disk Read:   {total_disk_read:.1f} MB")
        print(f"  Total Disk Write:  {total_disk_write:.1f} MB")

    def save_results(self, output_file: Path):
        """
        Save benchmark results to JSON file.

        Args:
            output_file: Path to output JSON file
        """
        metrics = self.calculate_phase_metrics()

        report = {
            "benchmark_timestamp": datetime.now().isoformat(),
            "disk_image": str(self.disk_image),
            "disk_size_mb": self.disk_size_mb,
            "iterations": self.iterations,
            "system_info": {
                "cpu_count": psutil.cpu_count(),
                "total_memory_mb": psutil.virtual_memory().total / (1024 * 1024),
                "platform": sys.platform,
            },
            "phase_metrics": [asdict(m) for m in metrics],
            "raw_results": [asdict(r) for r in self.results],
        }

        output_file.write_text(json.dumps(report, indent=2))
        print(f"\n✓ Results saved to: {output_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Benchmark VM migration performance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("disk_image", type=Path, help="Path to disk image to benchmark")
    parser.add_argument("-i", "--iterations", type=int, default=3, help="Number of iterations (default: 3)")
    parser.add_argument("-o", "--output", type=Path, help="Output JSON file for results")

    args = parser.parse_args()

    if not args.disk_image.exists():
        print(f"Error: Disk image not found: {args.disk_image}")
        sys.exit(1)

    # Run benchmark
    benchmark = MigrationBenchmark(args.disk_image, args.iterations)
    benchmark.benchmark_vmcraft_operations()
    benchmark.print_summary()

    # Save results if requested
    if args.output:
        benchmark.save_results(args.output)


if __name__ == "__main__":
    main()
