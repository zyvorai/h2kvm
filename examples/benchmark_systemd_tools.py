#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Performance Benchmark Suite for systemd Tools

Benchmarks all production tools across multiple VMs to measure:
- Execution time
- Memory usage
- Disk I/O
- Report generation time
- Scalability with VM size

Usage:
    python3 benchmark_systemd_tools.py [vm-paths...]

Example:
    python3 benchmark_systemd_tools.py /vmware/vm1.vmdk /vmware/vm2.vmdk
    python3 benchmark_systemd_tools.py /vmware/*.vmdk
"""

import sys
import time
import json
import psutil
import subprocess
from pathlib import Path
from typing import Any
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))


class ToolBenchmark:
    """Benchmark a single tool execution."""

    def __init__(self, tool_name: str, tool_script: str):
        self.tool_name = tool_name
        self.tool_script = tool_script
        self.examples_dir = Path(__file__).parent

    def benchmark(self, vm_path: str, extra_args: list[str] = None) -> dict[str, Any]:
        """Run benchmark for a tool on a VM."""
        print(f"  Benchmarking {self.tool_name}...")

        # Get initial system stats
        process = psutil.Process()
        initial_memory = process.memory_info().rss / (1024 * 1024)  # MB

        # Get VM size
        vm_size_gb = Path(vm_path).stat().st_size / (1024**3)

        # Run tool and measure time
        start_time = time.time()
        start_cpu_time = time.process_time()

        cmd = ["python3", str(self.examples_dir / self.tool_script)]
        if extra_args:
            cmd.extend(extra_args)
        cmd.append(vm_path)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )
            success = result.returncode == 0
            output_size = len(result.stdout) + len(result.stderr)
        except subprocess.TimeoutExpired:
            success = False
            output_size = 0
        except Exception as e:
            success = False
            output_size = 0

        # Measure elapsed time
        elapsed_time = time.time() - start_time
        cpu_time = time.process_time() - start_cpu_time

        # Get peak memory usage (approximate)
        peak_memory = process.memory_info().rss / (1024 * 1024)  # MB
        memory_delta = peak_memory - initial_memory

        return {
            "tool": self.tool_name,
            "vm_path": str(vm_path),
            "vm_name": Path(vm_path).name,
            "vm_size_gb": round(vm_size_gb, 2),
            "success": success,
            "elapsed_time_seconds": round(elapsed_time, 2),
            "cpu_time_seconds": round(cpu_time, 2),
            "memory_mb": round(memory_delta if memory_delta > 0 else peak_memory, 2),
            "output_size_bytes": output_size,
            "throughput_gb_per_sec": round(vm_size_gb / elapsed_time, 3) if elapsed_time > 0 else 0,
        }


class BenchmarkSuite:
    """Complete benchmark suite for all tools."""

    def __init__(self, vm_paths: list[str]):
        self.vm_paths = vm_paths
        self.results = []

        # Define tools to benchmark
        self.tools = [
            ToolBenchmark("systemd_forensic_analysis", "systemd_forensic_analysis.py"),
            ToolBenchmark("migration_readiness_check", "migration_readiness_check.py"),
            ToolBenchmark("security_audit", "security_audit.py"),
            ToolBenchmark("filesystem_api_demo", "filesystem_api_demo.py"),
        ]

    def run(self) -> dict[str, Any]:
        """Run complete benchmark suite."""
        print("=" * 80)
        print(" Performance Benchmark Suite")
        print("=" * 80)
        print(f"\nVMs to benchmark: {len(self.vm_paths)}")
        print(f"Tools to benchmark: {len(self.tools)}")
        print(f"Total tests: {len(self.vm_paths) * len(self.tools)}")
        print()

        for vm_path in self.vm_paths:
            if not Path(vm_path).exists():
                print(f"⚠ Skipping (not found): {vm_path}")
                continue

            vm_name = Path(vm_path).name
            print(f"\n{'=' * 80}")
            print(f" Benchmarking: {vm_name}")
            print(f"{'=' * 80}\n")

            # Benchmark each tool
            for tool in self.tools:
                result = tool.benchmark(vm_path)
                self.results.append(result)

                # Print immediate result
                if result["success"]:
                    print(
                        f"    ✓ {result['elapsed_time_seconds']:6.2f}s  "
                        f"{result['memory_mb']:6.1f} MB  "
                        f"{result['throughput_gb_per_sec']:.3f} GB/s"
                    )
                else:
                    print(f"    ✗ FAILED")

        # Generate summary
        return self._generate_summary()

    def _generate_summary(self) -> dict[str, Any]:
        """Generate benchmark summary statistics."""
        summary = {
            "timestamp": datetime.now().isoformat(),
            "total_tests": len(self.results),
            "successful_tests": sum(1 for r in self.results if r["success"]),
            "failed_tests": sum(1 for r in self.results if not r["success"]),
            "results": self.results,
        }

        # Calculate per-tool statistics
        tool_stats = {}
        for tool in self.tools:
            tool_results = [r for r in self.results if r["tool"] == tool.tool_name and r["success"]]

            if tool_results:
                times = [r["elapsed_time_seconds"] for r in tool_results]
                memories = [r["memory_mb"] for r in tool_results]
                throughputs = [r["throughput_gb_per_sec"] for r in tool_results]

                tool_stats[tool.tool_name] = {
                    "count": len(tool_results),
                    "avg_time": round(sum(times) / len(times), 2),
                    "min_time": round(min(times), 2),
                    "max_time": round(max(times), 2),
                    "avg_memory": round(sum(memories) / len(memories), 2),
                    "max_memory": round(max(memories), 2),
                    "avg_throughput": round(sum(throughputs) / len(throughputs), 3),
                }

        summary["tool_statistics"] = tool_stats

        # Calculate per-VM statistics
        vm_stats = {}
        for vm_path in self.vm_paths:
            vm_results = [r for r in self.results if r["vm_path"] == str(vm_path) and r["success"]]

            if vm_results:
                times = [r["elapsed_time_seconds"] for r in vm_results]
                vm_stats[Path(vm_path).name] = {
                    "total_time": round(sum(times), 2),
                    "avg_time_per_tool": round(sum(times) / len(times), 2),
                    "vm_size_gb": vm_results[0]["vm_size_gb"],
                }

        summary["vm_statistics"] = vm_stats

        return summary

    def print_summary(self, summary: dict[str, Any]):
        """Print formatted summary report."""
        print("\n" + "=" * 80)
        print(" BENCHMARK SUMMARY")
        print("=" * 80 + "\n")

        print(f"Total Tests:      {summary['total_tests']}")
        print(f"Successful:       {summary['successful_tests']}")
        print(f"Failed:           {summary['failed_tests']}")
        print()

        # Tool statistics
        print("Tool Performance Statistics:")
        print(f"{'Tool':<35} {'Avg Time':<12} {'Min/Max':<15} {'Avg Mem':<12}")
        print("-" * 80)

        for tool_name, stats in summary["tool_statistics"].items():
            print(
                f"{tool_name:<35} "
                f"{stats['avg_time']:>6.2f}s      "
                f"{stats['min_time']:>5.2f}/{stats['max_time']:<5.2f}s    "
                f"{stats['avg_memory']:>6.1f} MB"
            )
        print()

        # VM statistics
        if summary["vm_statistics"]:
            print("Per-VM Statistics:")
            print(f"{'VM Name':<40} {'Size':<12} {'Total Time':<15}")
            print("-" * 80)

            for vm_name, stats in summary["vm_statistics"].items():
                print(f"{vm_name:<40} {stats['vm_size_gb']:>6.2f} GB   {stats['total_time']:>6.2f}s")
            print()

        # Performance insights
        print("Performance Insights:")

        tool_stats = summary["tool_statistics"]
        if tool_stats:
            # Fastest tool
            fastest = min(tool_stats.items(), key=lambda x: x[1]["avg_time"])
            print(f"  ⚡ Fastest tool:  {fastest[0]} ({fastest[1]['avg_time']:.2f}s avg)")

            # Slowest tool
            slowest = max(tool_stats.items(), key=lambda x: x[1]["avg_time"])
            print(f"  🐌 Slowest tool:  {slowest[0]} ({slowest[1]['avg_time']:.2f}s avg)")

            # Most memory intensive
            most_mem = max(tool_stats.items(), key=lambda x: x[1]["avg_memory"])
            print(f"  💾 Most memory:   {most_mem[0]} ({most_mem[1]['avg_memory']:.1f} MB avg)")

            # Best throughput
            best_throughput = max(tool_stats.items(), key=lambda x: x[1]["avg_throughput"])
            print(
                f"  🚀 Best throughput: {best_throughput[0]} "
                f"({best_throughput[1]['avg_throughput']:.3f} GB/s)"
            )

        print()


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <vm-path> [vm-path2 ...]")
        print(f"\nExample: {sys.argv[0]} /vmware/vm1.vmdk /vmware/vm2.vmdk")
        print(f"         {sys.argv[0]} /vmware/*.vmdk")
        sys.exit(1)

    vm_paths = sys.argv[1:]

    # Verify all VMs exist
    valid_vms = [vm for vm in vm_paths if Path(vm).exists()]

    if not valid_vms:
        print("Error: No valid VM disk images found")
        sys.exit(1)

    # Run benchmark suite
    suite = BenchmarkSuite(valid_vms)
    summary = suite.run()

    # Print summary
    suite.print_summary(summary)

    # Save detailed results
    report_path = "/tmp/systemd_tools_benchmark.json"
    with open(report_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"📄 Detailed results saved: {report_path}\n")

    # Exit with error if any tests failed
    if summary["failed_tests"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
