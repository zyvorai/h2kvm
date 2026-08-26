#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Example: Async Batch VM Migration

Demonstrates parallel VM migrations using async/await for 3-5x speedup.

Features:
- Export multiple VMs concurrently
- Automatic concurrency limiting (default: 5 parallel VMs)
- Progress tracking for each VM
- Automatic retry on failures
- Real-time statistics

Requirements:
    pip install 'h2kvm[async]'

Usage:
    python3 examples/async_batch_migration_example.py

Performance Comparison:
    Sequential (old):  10 VMs × 5min each = 50 minutes
    Parallel (async):  10 VMs / 5 parallel  = ~12 minutes (4x faster!)
"""

import asyncio
import time
from pathlib import Path

from h2kvm.core.optional_imports import HTTPX_AVAILABLE

if not HTTPX_AVAILABLE:
    print("ERROR: httpx library not available!")
    print("Install with: pip install 'h2kvm[async]'")
    exit(1)

from h2kvm.providers.vmware.async_client import AsyncVMwareClient, AsyncVMwareOperations
from h2kvm.providers.vmware.async_client.operations import MigrationProgress


async def demo_async_batch_migration():
    """
    Demonstrate async batch migration with progress tracking.
    """
    print("╔════════════════════════════════════════════════════════════════╗")
    print("║       Async Batch VM Migration Demo (3-5x Faster!)            ║")
    print("╚════════════════════════════════════════════════════════════════╝")
    print()

    # Configuration
    vcenter_config = {
        "host": "vcenter.example.com",
        "username": "admin",
        "password": "secret",
        "datacenter": "DC1",
        "max_concurrent_vms": 5,  # Migrate 5 VMs in parallel
    }

    # VMs to migrate
    vm_names = [
        "web-server-01",
        "web-server-02",
        "web-server-03",
        "db-server-01",
        "db-server-02",
        "app-server-01",
        "app-server-02",
        "cache-server-01",
        "lb-server-01",
        "monitor-server-01",
    ]

    output_dir = Path("/var/lib/h2kvm/output")

    print(f"Configuration:")
    print(f"  vCenter:           {vcenter_config['host']}")
    print(f"  Datacenter:        {vcenter_config['datacenter']}")
    print(f"  Max Parallel VMs:  {vcenter_config['max_concurrent_vms']}")
    print(f"  Total VMs:         {len(vm_names)}")
    print(f"  Output Directory:  {output_dir}")
    print()

    # Progress tracking
    progress_data = {vm: 0.0 for vm in vm_names}
    start_time = time.time()

    def on_progress(prog: MigrationProgress):
        """Progress callback - updates progress display."""
        progress_data[prog.vm_name] = prog.progress

        # Display progress bar
        pct = int(prog.progress * 100)
        bar_len = 30
        filled = int(prog.progress * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)

        print(f"  {prog.vm_name:20s} [{bar}] {pct:3d}% - {prog.stage:30s} ({prog.throughput_mbps:.1f} MB/s)")

    def on_complete(vm_name: str, success: bool, error: str = None):
        """Completion callback - report results."""
        status = "✅ SUCCESS" if success else f"❌ FAILED: {error}"
        print(f"  {vm_name:20s} {status}")

    # Create async client
    print("Connecting to vCenter...")
    async with AsyncVMwareClient(**vcenter_config) as client:
        print(f"✅ Connected! (Max concurrent: {client.concurrency.limits.max_concurrent_vms})")
        print()

        ops = AsyncVMwareOperations(client)

        print(f"Starting parallel export of {len(vm_names)} VMs...")
        print(f"{'─' * 80}")

        # Run batch export
        results = await ops.batch_export(
            vm_names,
            output_dir,
            on_progress=on_progress,
            on_complete=on_complete,
        )

        print(f"{'─' * 80}")
        print()

        # Show results
        elapsed = time.time() - start_time

        print("╔════════════════════════════════════════════════════════════════╗")
        print("║                    Migration Summary                           ║")
        print("╚════════════════════════════════════════════════════════════════╝")
        print()
        print(f"  Total VMs:        {results['total']}")
        print(f"  Succeeded:        {results['succeeded']} ✅")
        print(f"  Failed:           {results['failed']} ❌")
        print(f"  Success Rate:     {results['success_rate'] * 100:.1f}%")
        print(f"  Elapsed Time:     {elapsed:.1f} seconds ({elapsed / 60:.1f} minutes)")
        print()

        if results["failed"] > 0:
            print("Failed VMs:")
            for vm_name, error in results["failures"]:
                print(f"  • {vm_name}: {error}")
            print()

        # Show statistics
        stats = client.get_stats()
        print("Client Statistics:")
        print(f"  Total API Calls:   {stats['api_calls_total']}")
        print(f"  API Calls Throttled: {stats['api_calls_throttled']}")
        print()

        # Performance comparison
        estimated_sequential_time = len(vm_names) * 5 * 60  # 5 min per VM
        speedup = estimated_sequential_time / elapsed if elapsed > 0 else 0

        print("Performance Comparison:")
        print(f"  Sequential (estimated): {estimated_sequential_time / 60:.1f} minutes")
        print(f"  Parallel (actual):      {elapsed / 60:.1f} minutes")
        print(f"  Speedup:                {speedup:.1f}x faster! 🚀")
        print()


async def demo_pattern_matching():
    """
    Demonstrate pattern-based VM selection.
    """
    print("\n╔════════════════════════════════════════════════════════════════╗")
    print("║              Pattern-Based VM Selection Demo                  ║")
    print("╚════════════════════════════════════════════════════════════════╝\n")

    async with AsyncVMwareClient(
        host="vcenter.example.com",
        username="admin",
        password="secret",
    ) as client:
        ops = AsyncVMwareOperations(client)

        # Example 1: Glob pattern
        print("Example 1: Glob pattern (web-server-*)")
        web_servers = await ops.get_vms_by_pattern("web-server-*")
        print(f"  Found {len(web_servers)} web servers")
        for vm in web_servers:
            print(f"    • {vm['name']}")
        print()

        # Example 2: Regex pattern
        print("Example 2: Regex pattern (^db-\\d+$)")
        db_servers = await ops.get_vms_by_pattern(r"^db-\d+$", use_regex=True)
        print(f"  Found {len(db_servers)} database servers")
        for vm in db_servers:
            print(f"    • {vm['name']}")
        print()


async def demo_retry_logic():
    """
    Demonstrate automatic retry on failure.
    """
    print("\n╔════════════════════════════════════════════════════════════════╗")
    print("║              Automatic Retry Demo                             ║")
    print("╚════════════════════════════════════════════════════════════════╝\n")

    async with AsyncVMwareClient(
        host="vcenter.example.com",
        username="admin",
        password="secret",
    ) as client:
        ops = AsyncVMwareOperations(client)

        print("Exporting VM with automatic retry (max 3 attempts)...")
        result = await ops.export_with_retry(
            "critical-server-01",
            Path("/var/lib/h2kvm/output"),
            max_retries=3,
        )

        print(f"✅ Export completed: {result['status']}")


async def main():
    """Run all demos."""
    # Demo 1: Batch migration
    await demo_async_batch_migration()

    # Demo 2: Pattern matching
    # await demo_pattern_matching()

    # Demo 3: Retry logic
    # await demo_retry_logic()


if __name__ == "__main__":
    print("\n🚀 Starting Async VM Migration Demo...\n")
    asyncio.run(main())
    print("\n✅ Demo complete!\n")
