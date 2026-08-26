#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Example: Parallel Mount and Performance Optimizations

This script demonstrates VMCraft's performance optimizations including:
1. Parallel mount operations (2-3x faster than sequential)
2. Partition list caching (reduces redundant scans)
3. Blkid metadata caching (reduces system calls)
4. Mount fallback strategies (handles damaged filesystems)
5. NBD retry logic (handles transient failures)

Workflow:
1. Launch VM with NBD retry logic
2. Use caching to reduce redundant operations
3. Mount partitions in parallel for maximum speed
4. Demonstrate mount fallback for problematic filesystems
"""

import sys
import logging
import time
from pathlib import Path

from h2kvm.vmcraft.main import VMCraft


def setup_logging():
    """Configure logging."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    return logging.getLogger(__name__)


def demonstrate_parallel_performance(vm_image_path: str):
    """
    Demonstrate parallel mount performance improvements.

    Args:
        vm_image_path: Path to VM disk image
    """
    logger = setup_logging()
    logger.info(f"Demonstrating parallel mount performance for: {vm_image_path}")

    with VMCraft(vm_image_path) as g:
        logger.info("VMCraft launched successfully (with NBD retry logic)")

        # =====================================================================
        # Step 1: Partition List Caching
        # =====================================================================
        logger.info("Step 1: Demonstrating partition list caching...")

        # First call - fetches from system
        start = time.perf_counter()
        partitions1 = g.list_partitions(use_cache=True)
        time1 = time.perf_counter() - start
        logger.info(f"  First call (no cache): {time1 * 1000:.2f}ms - found {len(partitions1)} partitions")

        # Second call - uses cache
        start = time.perf_counter()
        partitions2 = g.list_partitions(use_cache=True)
        time2 = time.perf_counter() - start
        logger.info(f"  Second call (cached): {time2 * 1000:.2f}ms - found {len(partitions2)} partitions")

        if time1 > 0:
            speedup = time1 / max(time2, 0.0001)
            logger.info(f"  Cache speedup: {speedup:.1f}x faster")

        # =====================================================================
        # Step 2: Blkid Metadata Caching
        # =====================================================================
        logger.info("Step 2: Demonstrating blkid metadata caching...")

        if partitions1:
            test_partition = partitions1[0]

            # First call - fetches from blkid
            start = time.perf_counter()
            metadata1 = g.blkid(test_partition, use_cache=True)
            time1 = time.perf_counter() - start
            logger.info(f"  First call (no cache): {time1 * 1000:.2f}ms")
            logger.info(f"    Filesystem: {metadata1.get('TYPE', 'unknown')}")
            logger.info(f"    UUID: {metadata1.get('UUID', 'none')}")

            # Second call - uses cache
            start = time.perf_counter()
            metadata2 = g.blkid(test_partition, use_cache=True)
            time2 = time.perf_counter() - start
            logger.info(f"  Second call (cached): {time2 * 1000:.2f}ms")

            if time1 > 0:
                speedup = time1 / max(time2, 0.0001)
                logger.info(f"  Cache speedup: {speedup:.1f}x faster")

        # =====================================================================
        # Step 3: Sequential vs Parallel Mount Performance
        # =====================================================================
        logger.info("Step 3: Comparing sequential vs parallel mount performance...")

        # Unmount any existing mounts first
        g.umount_all()

        # Get partitions and their filesystems
        mount_targets = []
        for i, partition in enumerate(partitions1[:4]):  # Limit to first 4 partitions
            metadata = g.blkid(partition, use_cache=True)
            fstype = metadata.get("TYPE")

            # Only mount known filesystem types
            if fstype in ("ext2", "ext3", "ext4", "xfs", "btrfs", "ntfs", "vfat"):
                mountpoint = f"/partition{i + 1}"
                mount_targets.append((partition, mountpoint))

        if len(mount_targets) >= 2:
            logger.info(f"  Found {len(mount_targets)} partitions to mount")

            # Sequential mounting
            logger.info("  Testing SEQUENTIAL mounting...")
            g.umount_all()
            start = time.perf_counter()
            for device, mountpoint in mount_targets:
                try:
                    g.mount(device, mountpoint, readonly=True)
                except Exception as e:
                    logger.debug(f"    Failed to mount {device}: {e}")
            sequential_time = time.perf_counter() - start
            logger.info(f"    Sequential mount time: {sequential_time * 1000:.2f}ms")

            # Parallel mounting
            logger.info("  Testing PARALLEL mounting...")
            g.umount_all()
            start = time.perf_counter()
            results = g.mount_all_parallel(mount_targets, max_workers=4, readonly=True)
            parallel_time = time.perf_counter() - start
            logger.info(f"    Parallel mount time: {parallel_time * 1000:.2f}ms")

            successful_mounts = sum(1 for success in results.values() if success)
            logger.info(f"    Successfully mounted: {successful_mounts}/{len(mount_targets)}")

            # Calculate speedup
            if parallel_time > 0:
                speedup = sequential_time / parallel_time
                logger.info(f"  Parallel speedup: {speedup:.2f}x faster")

        else:
            logger.warning("  Not enough mountable partitions to demonstrate parallel mounting")

        # =====================================================================
        # Step 4: Mount Fallback Strategies
        # =====================================================================
        logger.info("Step 4: Demonstrating mount fallback strategies...")

        g.umount_all()

        if partitions1:
            test_partition = partitions1[0]
            logger.info(f"  Testing fallback mount on {test_partition}...")

            # Try mount with fallback (handles damaged filesystems)
            success = g.mount_with_fallback(test_partition, "/test-fallback")

            if success:
                logger.info("  ✓ Mount succeeded with fallback strategy")

                # Verify mount
                if g.is_mounted("/test-fallback"):
                    logger.info(f"    Confirmed mounted at /test-fallback")
                    logger.info(f"    Device: {g.get_device('/test-fallback')}")
            else:
                logger.warning("  ✗ Mount failed even with all fallback strategies")

        # =====================================================================
        # Step 5: Cache Invalidation
        # =====================================================================
        logger.info("Step 5: Demonstrating cache invalidation...")

        # Show current cache state
        partitions_before = g.list_partitions(use_cache=True)
        logger.info(f"  Partitions in cache: {len(partitions_before)}")

        # Invalidate partition cache
        g.invalidate_partition_cache()
        logger.info("  Cache invalidated")

        # Next call will re-scan
        partitions_after = g.list_partitions(use_cache=True)
        logger.info(f"  Partitions after cache refresh: {len(partitions_after)}")

        # =====================================================================
        # Performance Summary
        # =====================================================================
        logger.info("=" * 70)
        logger.info("PERFORMANCE OPTIMIZATIONS SUMMARY")
        logger.info("=" * 70)
        logger.info("")
        logger.info("Caching Benefits:")
        logger.info("  - Partition list caching: Reduces redundant partition scans")
        logger.info("  - Blkid metadata caching: Reduces system calls (120s TTL)")
        logger.info("  - Cache invalidation: Automatic after partition operations")
        logger.info("")
        logger.info("Parallel Mount:")
        if len(mount_targets) >= 2:
            logger.info(f"  - Sequential: {sequential_time * 1000:.2f}ms")
            logger.info(f"  - Parallel: {parallel_time * 1000:.2f}ms")
            logger.info(f"  - Speedup: {speedup:.2f}x faster")
        else:
            logger.info("  - Benefit: 2-3x faster on multi-partition VMs")
        logger.info("")
        logger.info("Robustness Features:")
        logger.info("  - NBD retry logic: 3 attempts with exponential backoff")
        logger.info("  - Mount fallback: Multiple strategies for damaged filesystems")
        logger.info("  - Filesystem recovery: ro+norecovery, ro+noload options")
        logger.info("")
        logger.info("Best Practices:")
        logger.info("  1. Use parallel mounting for VMs with multiple partitions")
        logger.info("  2. Enable caching for repeated operations (default: enabled)")
        logger.info("  3. Use mount_with_fallback() for potentially damaged filesystems")
        logger.info("  4. NBD retry logic handles transient connection failures automatically")

    logger.info("")
    logger.info("Performance demonstration completed!")


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: python 01_parallel_mount_performance.py <vm_image_path>")
        print("")
        print("Example:")
        print("  python 01_parallel_mount_performance.py /path/to/rhel9-vm.qcow2")
        print("")
        print("This script demonstrates:")
        print("  - Partition list caching (reduces scans)")
        print("  - Blkid metadata caching (reduces system calls)")
        print("  - Parallel mount operations (2-3x faster)")
        print("  - Mount fallback strategies (damaged filesystems)")
        print("  - NBD connection retry logic (transient failures)")
        sys.exit(1)

    vm_image_path = sys.argv[1]

    if not Path(vm_image_path).exists():
        print(f"Error: VM image not found: {vm_image_path}")
        sys.exit(1)

    demonstrate_parallel_performance(vm_image_path)


if __name__ == "__main__":
    main()
