#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Profiling utilities for h2kvm vmspawn."""

import asyncio
import cProfile
import io
import json
import pstats
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Optional


class PerformanceProfiler:
    """Performance profiling utilities."""

    def __init__(self, output_dir: Optional[Path] = None):
        """Initialize profiler."""
        self.output_dir = output_dir or Path("./profiling_results")
        self.output_dir.mkdir(exist_ok=True)
        self.profiler = None

    @contextmanager
    def profile(self, name: str = "profile"):
        """Context manager for profiling code blocks."""
        profiler = cProfile.Profile()
        profiler.enable()

        try:
            yield profiler
        finally:
            profiler.disable()
            self._save_profile(profiler, name)

    def _save_profile(self, profiler: cProfile.Profile, name: str):
        """Save profiling results."""
        # Save binary stats
        stats_file = self.output_dir / f"{name}.prof"
        profiler.dump_stats(str(stats_file))

        # Save human-readable report
        s = io.StringIO()
        ps = pstats.Stats(profiler, stream=s)
        ps.sort_stats("cumulative")
        ps.print_stats(50)  # Top 50 functions

        report_file = self.output_dir / f"{name}.txt"
        report_file.write_text(s.getvalue())

        print(f"Profile saved to {stats_file}")
        print(f"Report saved to {report_file}")

    def profile_function(self, func: Callable, *args, **kwargs):
        """Profile a single function."""
        with self.profile(func.__name__):
            return func(*args, **kwargs)

    async def profile_async_function(self, func: Callable, *args, **kwargs):
        """Profile an async function."""
        with self.profile(func.__name__):
            return await func(*args, **kwargs)


class TimingProfiler:
    """Simple timing profiler for measuring execution times."""

    def __init__(self):
        """Initialize timing profiler."""
        self.timings = {}
        self.call_counts = {}

    @contextmanager
    def measure(self, name: str):
        """Measure execution time of code block."""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            if name not in self.timings:
                self.timings[name] = []
                self.call_counts[name] = 0
            self.timings[name].append(elapsed)
            self.call_counts[name] += 1

    def get_stats(self) -> dict:
        """Get timing statistics."""
        stats = {}
        for name, times in self.timings.items():
            stats[name] = {
                "count": self.call_counts[name],
                "total": sum(times),
                "mean": sum(times) / len(times),
                "min": min(times),
                "max": max(times),
            }
        return stats

    def print_stats(self):
        """Print timing statistics."""
        stats = self.get_stats()
        print("\n" + "=" * 70)
        print("TIMING STATISTICS")
        print("=" * 70)
        print(f"{'Operation':<30} {'Count':>8} {'Total':>10} {'Mean':>10} {'Min':>10} {'Max':>10}")
        print("-" * 70)

        for name, s in sorted(stats.items(), key=lambda x: x[1]["total"], reverse=True):
            print(
                f"{name:<30} {s['count']:>8} "
                f"{s['total']:>10.4f}s {s['mean']:>10.6f}s "
                f"{s['min']:>10.6f}s {s['max']:>10.6f}s"
            )
        print("=" * 70)

    def save_json(self, output_file: Path):
        """Save statistics to JSON."""
        stats = self.get_stats()
        output_file.write_text(json.dumps(stats, indent=2))
        print(f"Timing stats saved to {output_file}")


class MemoryProfiler:  # pylint: disable=too-few-public-methods  # a focused profiling helper; measure() is its sole entry point
    """Memory profiling utilities."""

    def __init__(self):
        """Initialize memory profiler."""
        try:
            import tracemalloc  # pylint: disable=import-outside-toplevel  # optional: some minimal Python builds lack tracemalloc

            self.tracemalloc = tracemalloc
            self.available = True
        except ImportError:
            self.available = False
            print("Warning: tracemalloc not available")

    @contextmanager
    def measure(self):
        """Measure memory usage."""
        if not self.available:
            yield None
            return

        self.tracemalloc.start()
        try:
            yield self
        finally:
            snapshot = self.tracemalloc.take_snapshot()
            self.tracemalloc.stop()
            self._print_snapshot(snapshot)

    def _print_snapshot(self, snapshot):
        """Print memory snapshot statistics."""
        print("\n" + "=" * 70)
        print("MEMORY STATISTICS")
        print("=" * 70)

        top_stats = snapshot.statistics("lineno")

        print("Top 10 memory consumers:")
        for stat in top_stats[:10]:
            print(f"{stat.size / 1024:.1f} KB - {stat}")

        total = sum(stat.size for stat in top_stats)
        print(f"\nTotal memory: {total / 1024 / 1024:.2f} MB")
        print("=" * 70)


# Example usage functions
async def profile_validation_example():
    """Example: Profile VM validation."""
    # pylint: disable=import-outside-toplevel  # keeps vmspawn's process-management deps optional at module import time
    from h2kvm.vmspawn.async_manager import AsyncVMManager
    from h2kvm.vmspawn.async_validator import AsyncValidator

    profiler = PerformanceProfiler()
    timing = TimingProfiler()
    memory = MemoryProfiler()

    manager = AsyncVMManager(max_parallel=10)

    machines = [
        await manager.create_machine(
            name=f"profile-vm-{i}",
            image=Path("/path/to/image.qcow2"),
        )
        for i in range(10)
    ]

    with (
        memory.measure(),
        profiler.profile("validation_batch"),
        timing.measure("total_validation"),
        timing.measure("single_validation"),
    ):
        results = await manager.validate_batch(machines, AsyncValidator)

    print(f"Validated {sum(1 for ok in results.values() if ok)}/{len(results)} VMs successfully")
    timing.print_stats()
    timing.save_json(Path("timing_stats.json"))


def profile_sync_operations():
    """Example: Profile synchronous operations."""
    # pylint: disable=import-outside-toplevel  # keeps vmspawn's process-management deps optional at module import time
    from h2kvm.vmspawn.machine import Machine
    from h2kvm.vmspawn.models import VMConfig

    profiler = PerformanceProfiler()
    timing = TimingProfiler()

    with profiler.profile("sync_operations"):
        for i in range(100):
            with timing.measure("config_creation"):
                config = VMConfig(
                    name=f"vm-{i}",
                    image="/path/to/image.qcow2",
                    memory_mb=2048,
                    cpus=2,
                )

            with timing.measure("machine_creation"):
                Machine(config)

    timing.print_stats()


def compare_implementations():
    """Compare performance of different implementations."""
    # pylint: disable=import-outside-toplevel  # keeps vmspawn's process-management deps optional at module import time
    from h2kvm.vmspawn.async_machine import AsyncMachine
    from h2kvm.vmspawn.machine import Machine
    from h2kvm.vmspawn.models import VMConfig

    print("\n" + "=" * 70)
    print("IMPLEMENTATION COMPARISON")
    print("=" * 70)

    config = VMConfig(
        name="compare-vm",
        image="/path/to/image.qcow2",
    )

    # Sync implementation
    sync_start = time.perf_counter()
    for _ in range(100):
        Machine(config)
    sync_time = time.perf_counter() - sync_start

    # Async implementation
    async def async_test():
        for _ in range(100):
            AsyncMachine(
                name=config.name,
                image=config.image,
                memory_mb=config.memory_mb,
                cpus=config.cpus,
                tpm=config.tpm,
                vsock=config.vsock,
            )

    async_start = time.perf_counter()
    asyncio.run(async_test())
    async_time = time.perf_counter() - async_start

    print(f"Sync implementation:  {sync_time:.4f}s ({100 / sync_time:.1f} ops/sec)")
    print(f"Async implementation: {async_time:.4f}s ({100 / async_time:.1f} ops/sec)")
    print(f"Speedup: {sync_time / async_time:.2f}x")
    print("=" * 70)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "async":
        print("Profiling async validation...")
        asyncio.run(profile_validation_example())
    elif len(sys.argv) > 1 and sys.argv[1] == "sync":
        print("Profiling sync operations...")
        profile_sync_operations()
    elif len(sys.argv) > 1 and sys.argv[1] == "compare":
        print("Comparing implementations...")
        compare_implementations()
    else:
        print("Usage: python profiler.py [async|sync|compare]")
        sys.exit(1)
