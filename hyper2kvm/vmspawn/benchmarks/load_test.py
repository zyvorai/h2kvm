#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Load testing tool for vmspawn parallel validation."""

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import dataclass, field

from hyper2kvm.vmspawn.async_manager import AsyncVMManager
from hyper2kvm.vmspawn.models import VMConfig


@dataclass
class LoadTestConfig:  # pylint: disable=too-many-instance-attributes  # models many independent CLI-tunable load-test parameters
    """Load test configuration."""

    vm_count: int = 10
    max_parallel: int = 10
    image_path: str = "/path/to/test.qcow2"
    memory: int = 2048
    cpus: int = 2
    timeout: int = 300
    warmup_runs: int = 2
    test_runs: int = 5


@dataclass
class LoadTestResult:  # pylint: disable=too-many-instance-attributes  # models many independent measured/derived benchmark metrics
    """Load test results."""

    vm_count: int
    max_parallel: int
    total_time: float
    avg_time_per_vm: float
    throughput: float  # VMs per second
    success_count: int
    failure_count: int
    times: list[float] = field(default_factory=list)

    @property
    def p50(self) -> float:
        """Median latency."""
        return statistics.median(self.times) if self.times else 0.0

    @property
    def p95(self) -> float:
        """95th percentile latency."""
        if not self.times:
            return 0.0
        sorted_times = sorted(self.times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[idx]

    @property
    def p99(self) -> float:
        """99th percentile latency."""
        if not self.times:
            return 0.0
        sorted_times = sorted(self.times)
        idx = int(len(sorted_times) * 0.99)
        return sorted_times[idx]

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "vm_count": self.vm_count,
            "max_parallel": self.max_parallel,
            "total_time": self.total_time,
            "avg_time_per_vm": self.avg_time_per_vm,
            "throughput": self.throughput,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "latency": {
                "p50": self.p50,
                "p95": self.p95,
                "p99": self.p99,
            },
        }


class LoadTester:
    """Load testing orchestrator."""

    def __init__(self, config: LoadTestConfig):
        """Initialize load tester."""
        self.config = config

    async def run_single_test(self) -> LoadTestResult:
        """Run a single load test iteration."""
        manager = AsyncVMManager(max_parallel=self.config.max_parallel)

        # Create VM configurations
        configs = [
            VMConfig(
                name=f"loadtest-vm-{i}",
                image=self.config.image_path,
                memory_mb=self.config.memory,
                cpus=self.config.cpus,
            )
            for i in range(self.config.vm_count)
        ]

        # Track individual VM times
        times = []
        success_count = 0
        failure_count = 0

        async def validate_with_timing(config: VMConfig):
            """Validate VM and track timing."""
            nonlocal success_count, failure_count

            start = time.perf_counter()
            try:
                # AsyncVMManager has no single-shot validate_vm(); create+start (which waits
                # for the VM to report running) is the closest equivalent "validation" it offers.
                machine = await manager.create_machine(
                    name=config.name,
                    image=config.image,
                    memory_mb=config.memory_mb,
                    cpus=config.cpus,
                )
                try:
                    await manager.start_machine(machine)
                    elapsed = time.perf_counter() - start
                    times.append(elapsed)
                    success_count += 1
                finally:
                    await machine.terminate()
            except Exception as e:  # pylint: disable=broad-exception-caught  # one VM's validation failure must not abort the parallel batch
                elapsed = time.perf_counter() - start
                times.append(elapsed)
                failure_count += 1
                print(f"Validation failed for {config.name}: {e}")

        # Run validations
        start_time = time.perf_counter()
        await asyncio.gather(*[validate_with_timing(config) for config in configs])
        total_time = time.perf_counter() - start_time

        # Calculate metrics
        avg_time = total_time / self.config.vm_count if self.config.vm_count > 0 else 0
        throughput = self.config.vm_count / total_time if total_time > 0 else 0

        return LoadTestResult(
            vm_count=self.config.vm_count,
            max_parallel=self.config.max_parallel,
            total_time=total_time,
            avg_time_per_vm=avg_time,
            throughput=throughput,
            success_count=success_count,
            failure_count=failure_count,
            times=times,
        )

    async def run_load_test(self) -> list[LoadTestResult]:
        """Run full load test with warmup."""
        print("Starting load test:")
        print(f"  VMs: {self.config.vm_count}")
        print(f"  Max parallel: {self.config.max_parallel}")
        print(f"  Warmup runs: {self.config.warmup_runs}")
        print(f"  Test runs: {self.config.test_runs}")
        print()

        # Warmup
        print("Running warmup...")
        for i in range(self.config.warmup_runs):
            result = await self.run_single_test()
            print(f"  Warmup {i + 1}/{self.config.warmup_runs}: {result.throughput:.2f} VMs/sec")

        # Actual test runs
        print("\nRunning tests...")
        results = []
        for i in range(self.config.test_runs):
            result = await self.run_single_test()
            results.append(result)
            print(
                f"  Run {i + 1}/{self.config.test_runs}: "
                f"{result.throughput:.2f} VMs/sec "
                f"(p50: {result.p50:.2f}s, p95: {result.p95:.2f}s)"
            )

        return results

    def print_summary(self, results: list[LoadTestResult]):
        """Print test summary."""
        if not results:
            print("No results to summarize")
            return

        throughputs = [r.throughput for r in results]
        avg_throughput = statistics.mean(throughputs)
        std_throughput = statistics.stdev(throughputs) if len(throughputs) > 1 else 0

        all_times = []
        for r in results:
            all_times.extend(r.times)

        print("\n" + "=" * 60)
        print("LOAD TEST SUMMARY")
        print("=" * 60)
        print(f"VM count:        {self.config.vm_count}")
        print(f"Max parallel:    {self.config.max_parallel}")
        print(f"Test runs:       {self.config.test_runs}")
        print()
        print(f"Throughput:      {avg_throughput:.2f} ± {std_throughput:.2f} VMs/sec")
        print(f"Total VMs:       {sum(r.success_count + r.failure_count for r in results)}")
        print(f"Success:         {sum(r.success_count for r in results)}")
        print(f"Failures:        {sum(r.failure_count for r in results)}")
        print()
        print("Latency percentiles:")
        print(f"  p50: {statistics.median(all_times):.2f}s")
        print(f"  p95: {sorted(all_times)[int(len(all_times) * 0.95)]:.2f}s")
        print(f"  p99: {sorted(all_times)[int(len(all_times) * 0.99)]:.2f}s")
        print("=" * 60)


async def run_scaling_test(base_config: LoadTestConfig):
    """Run scaling test with different VM counts."""
    print("\n" + "=" * 60)
    print("SCALING TEST")
    print("=" * 60)

    results_by_count = {}

    for vm_count in [10, 50, 100, 500, 1000]:
        config = LoadTestConfig(
            vm_count=vm_count,
            max_parallel=base_config.max_parallel,
            image_path=base_config.image_path,
            memory=base_config.memory,
            cpus=base_config.cpus,
            warmup_runs=1,
            test_runs=3,
        )

        tester = LoadTester(config)
        results = await tester.run_load_test()

        throughputs = [r.throughput for r in results]
        avg_throughput = statistics.mean(throughputs)

        results_by_count[vm_count] = {
            "throughput": avg_throughput,
            "avg_time": statistics.mean([r.avg_time_per_vm for r in results]),
        }

        print(f"\n{vm_count} VMs: {avg_throughput:.2f} VMs/sec")

    print("\n" + "=" * 60)
    print("Scaling results:")
    for vm_count, metrics in results_by_count.items():
        print(f"  {vm_count:4d} VMs: {metrics['throughput']:6.2f} VMs/sec")
    print("=" * 60)


async def run_concurrency_test(base_config: LoadTestConfig):
    """Test different concurrency levels."""
    print("\n" + "=" * 60)
    print("CONCURRENCY TEST")
    print("=" * 60)

    results_by_concurrency = {}

    for concurrency in [1, 5, 10, 25, 50, 100]:
        config = LoadTestConfig(
            vm_count=100,
            max_parallel=concurrency,
            image_path=base_config.image_path,
            memory=base_config.memory,
            cpus=base_config.cpus,
            warmup_runs=1,
            test_runs=3,
        )

        tester = LoadTester(config)
        results = await tester.run_load_test()

        throughputs = [r.throughput for r in results]
        avg_throughput = statistics.mean(throughputs)

        results_by_concurrency[concurrency] = avg_throughput
        print(f"\nConcurrency {concurrency}: {avg_throughput:.2f} VMs/sec")

    print("\n" + "=" * 60)
    print("Optimal concurrency:")
    optimal = max(results_by_concurrency.items(), key=lambda x: x[1])
    print(f"  {optimal[0]} parallel VMs: {optimal[1]:.2f} VMs/sec")
    print("=" * 60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Load test vmspawn parallel validation")
    parser.add_argument("--vms", type=int, default=10, help="Number of VMs to test")
    parser.add_argument("--parallel", type=int, default=10, help="Max parallel VMs")
    parser.add_argument("--image", type=str, default="/path/to/test.qcow2", help="VM image path")
    parser.add_argument("--memory", type=int, default=2048, help="VM memory in MB")
    parser.add_argument("--cpus", type=int, default=2, help="VM CPU count")
    parser.add_argument("--timeout", type=int, default=300, help="Validation timeout")
    parser.add_argument("--warmup", type=int, default=2, help="Warmup runs")
    parser.add_argument("--runs", type=int, default=5, help="Test runs")
    parser.add_argument(
        "--mode", choices=["basic", "scaling", "concurrency"], default="basic", help="Test mode"
    )
    parser.add_argument("--output", type=str, help="Output JSON file")

    args = parser.parse_args()

    config = LoadTestConfig(
        vm_count=args.vms,
        max_parallel=args.parallel,
        image_path=args.image,
        memory=args.memory,
        cpus=args.cpus,
        timeout=args.timeout,
        warmup_runs=args.warmup,
        test_runs=args.runs,
    )

    if args.mode == "basic":
        tester = LoadTester(config)
        results = asyncio.run(tester.run_load_test())
        tester.print_summary(results)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump([r.to_dict() for r in results], f, indent=2)

    elif args.mode == "scaling":
        asyncio.run(run_scaling_test(config))

    elif args.mode == "concurrency":
        asyncio.run(run_concurrency_test(config))


if __name__ == "__main__":
    main()
