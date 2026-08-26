# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Performance benchmarks for vmspawn SDK."""

import asyncio
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from h2kvm.vmspawn.async_machine import AsyncMachine
from h2kvm.vmspawn.async_manager import AsyncVMManager
from h2kvm.vmspawn.machine import Machine
from h2kvm.vmspawn.models import VMConfig


# Minimal test double implementing AsyncVMManager.validate_batch()'s single-method
# validator_class protocol (__init__(machine) + async validate()); no room for a
# second public method without adding unused surface area.
# pylint: disable-next=too-few-public-methods
class _MockValidator:
    """Mimics the validator_class protocol expected by AsyncVMManager.validate_batch()."""

    def __init__(self, machine):
        self.machine = machine

    async def validate(self) -> bool:
        """Simulate a validation pass without touching a real VM."""
        await asyncio.sleep(0.01)
        return True


class TestMachinePerformance:
    """Performance benchmarks for Machine class."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return VMConfig(
            name="bench-vm",
            image="/path/to/image.qcow2",
            memory_mb=2048,
            cpus=2,
        )

    @pytest.mark.benchmark(group="machine-creation")
    def test_machine_creation_performance(self, benchmark, config):
        """Benchmark machine creation."""

        def create_machine():
            return Machine(config)

        result = benchmark(create_machine)
        assert result is not None

    @pytest.mark.benchmark(group="command-building")
    def test_command_building_performance(self, benchmark, config):
        """Benchmark command building (via Machine.start(), with subprocess mocked out)."""
        machine = Machine(config)

        def build_command():
            with patch(
                "h2kvm.vmspawn.machine.subprocess.run",
                return_value=MagicMock(returncode=0, stdout="", stderr=""),
            ) as mock_run:
                machine.start()
                return mock_run.call_args[0][0]

        result = benchmark(build_command)
        assert len(result) > 0

    @pytest.mark.benchmark(group="config-validation")
    def test_config_validation_performance(self, benchmark):
        """Benchmark configuration validation."""

        def create_config():
            # pylint: disable=duplicate-code
            # reason: mirrors VMConfig(...) fixture literals in
            # test_machine.py::TestVMConfig.test_full_config -- coincidental
            # shared test data, not shared logic; keeping independent avoids
            # coupling this benchmark to the correctness test's fixture.
            return VMConfig(
                name=f"vm-{time.time_ns()}",
                image="/path/to/image.qcow2",
                memory_mb=4096,
                cpus=4,
                tpm=True,
                vsock=True,
                vsock_cid=42,
            )

        result = benchmark(create_config)
        assert result.memory == 4096


class TestAsyncMachinePerformance:
    """Performance benchmarks for AsyncMachine class."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return VMConfig(
            name="async-bench-vm",
            image="/path/to/image.qcow2",
        )

    @pytest.mark.benchmark(group="async-machine-creation")
    def test_async_machine_creation_performance(self, benchmark, config):
        """Benchmark async machine creation."""

        def create_machine():
            return AsyncMachine(name=config.name, image=config.image, memory_mb=config.memory_mb)

        result = benchmark(create_machine)
        assert result is not None

    @pytest.mark.asyncio
    @pytest.mark.benchmark(group="async-operations")
    async def test_async_start_overhead(self, benchmark, config):
        """Measure async operation overhead."""
        machine = AsyncMachine(name=config.name, image=config.image, memory_mb=config.memory_mb)

        async def mock_start():
            # Simulate async operation
            await asyncio.sleep(0.001)
            return True

        with patch.object(machine, "start", side_effect=mock_start):
            result = await benchmark.pedantic(
                mock_start,
                rounds=100,
                iterations=10,
            )
            assert result is True


class TestParallelValidationPerformance:
    """Performance benchmarks for parallel VM validation."""

    @pytest.mark.asyncio
    @pytest.mark.benchmark(group="parallel-validation")
    async def test_parallel_vm_creation_performance(self, benchmark):
        """Benchmark parallel VM creation."""

        async def create_vms_parallel(count=10):
            manager = AsyncVMManager(max_parallel=10)
            machines = [
                AsyncMachine(name=f"vm-{i}", image="/path/to/image.qcow2") for i in range(count)
            ]
            return await manager.validate_batch(machines, _MockValidator)

        results = await benchmark.pedantic(
            create_vms_parallel,
            args=(10,),
            rounds=10,
            iterations=5,
        )
        assert len(results) == 10

    @pytest.mark.asyncio
    @pytest.mark.benchmark(group="parallel-validation")
    async def test_scaling_performance(self):
        """Benchmark performance scaling with different VM counts."""

        async def validate_batch(vm_count):
            manager = AsyncVMManager(max_parallel=100)
            machines = [
                AsyncMachine(name=f"vm-{i}", image="/path/to/image.qcow2") for i in range(vm_count)
            ]

            start = time.perf_counter()
            await manager.validate_batch(machines, _MockValidator)
            return time.perf_counter() - start

        # Test with different batch sizes
        for batch_size in [10, 50, 100]:
            elapsed = await validate_batch(batch_size)
            throughput = batch_size / elapsed
            print(f"\nBatch size {batch_size}: {elapsed:.2f}s ({throughput:.1f} VMs/sec)")


# Single-purpose benchmark class (one test method); pytest test classes are grouped by
# theme rather than by public-method count, so the usual OOP heuristic doesn't apply here.
# pylint: disable-next=too-few-public-methods
class TestMemoryPerformance:
    """Memory usage benchmarks."""

    @pytest.mark.benchmark(group="memory-usage")
    def test_machine_memory_footprint(self, benchmark):
        """Measure memory footprint of Machine instances."""

        def create_machines(count=100):
            machines = []
            for i in range(count):
                config = VMConfig(
                    name=f"vm-{i}",
                    image="/path/to/image.qcow2",
                )
                machines.append(Machine(config))
            return machines

        machines = benchmark(create_machines)

        # Estimate memory per machine
        total_size = sum(sys.getsizeof(m) for m in machines)
        avg_size = total_size / len(machines)
        print(f"\nAverage machine object size: {avg_size:.1f} bytes")
        assert len(machines) == 100


class TestConcurrencyPerformance:
    """Concurrency and rate limiting benchmarks."""

    @pytest.mark.asyncio
    @pytest.mark.benchmark(group="rate-limiting")
    async def test_rate_limiting_overhead(self, benchmark):
        """Measure overhead of semaphore-based rate limiting."""

        async def with_rate_limiting(max_concurrent=10):
            semaphore = asyncio.Semaphore(max_concurrent)

            async def limited_task():
                async with semaphore:
                    await asyncio.sleep(0.001)
                    return True

            tasks = [limited_task() for _ in range(100)]
            results = await asyncio.gather(*tasks)
            return len(results)

        result = await benchmark.pedantic(
            with_rate_limiting,
            rounds=10,
            iterations=5,
        )
        assert result == 100

    @pytest.mark.asyncio
    @pytest.mark.benchmark(group="queue-processing")
    async def test_queue_processing_performance(self, benchmark):
        """Benchmark async queue processing."""

        async def process_queue(items=100):
            queue = asyncio.Queue()

            # Producer
            async def produce():
                for i in range(items):
                    await queue.put(i)
                await queue.put(None)  # Sentinel

            # Consumer
            async def consume():
                results = []
                while True:
                    item = await queue.get()
                    if item is None:
                        break
                    results.append(item)
                return results

            producer_task = asyncio.create_task(produce())
            consumer_task = asyncio.create_task(consume())

            await producer_task
            results = await consumer_task
            return len(results)

        result = await benchmark.pedantic(
            process_queue,
            rounds=10,
            iterations=5,
        )
        assert result == 100


# Performance regression tests
class TestPerformanceRegression:
    """Tests to detect performance regressions."""

    @pytest.mark.benchmark(group="regression")
    def test_machine_start_command_generation(self, benchmark):
        """Ensure command generation stays fast (via Machine.start(), with subprocess mocked out)."""
        # pylint: disable=duplicate-code
        # reason: mirrors VMConfig(...) fixture literals in
        # test_machine.py::TestVMConfig.test_full_config -- coincidental
        # shared test data, not shared logic; keeping independent avoids
        # coupling this benchmark to the correctness test's fixture.
        config = VMConfig(
            name="test-vm",
            image="/path/to/image.qcow2",
            memory_mb=4096,
            cpus=4,
            tpm=True,
            vsock=True,
        )
        machine = Machine(config)

        def start_with_mocked_subprocess():
            with patch(
                "h2kvm.vmspawn.machine.subprocess.run",
                return_value=MagicMock(returncode=0, stdout="", stderr=""),
            ):
                machine.start()

        benchmark(start_with_mocked_subprocess)

        # Command generation should be < 1ms
        assert benchmark.stats.stats.mean < 0.001

    @pytest.mark.asyncio
    async def test_async_manager_scales_linearly(self):
        """Ensure async manager scales linearly with VM count."""

        async def measure_time(vm_count, max_parallel):
            manager = AsyncVMManager(max_parallel=max_parallel)
            machines = [AsyncMachine(name=f"vm-{i}", image="/test.qcow2") for i in range(vm_count)]

            start = time.perf_counter()
            await manager.validate_batch(machines, _MockValidator)
            return time.perf_counter() - start

        # Test scaling
        time_10 = await measure_time(10, max_parallel=10)
        time_20 = await measure_time(20, max_parallel=10)

        # Should scale roughly linearly (allow 30% variance for overhead)
        ratio = time_20 / time_10
        assert 1.7 <= ratio <= 2.3, f"Scaling ratio {ratio:.2f} outside expected range"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--benchmark-only"])
