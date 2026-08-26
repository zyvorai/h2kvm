#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
VMDK Validation Example

Demonstrates how to use hyper2kvm's built-in image validation
capabilities to check disk image integrity before migration.

This example shows:
1. Basic validation (qemu-img metadata check)
2. Deep validation (partition table inspection)
3. Full validation (filesystem integrity checks)
"""

import logging
import sys
from pathlib import Path

from hyper2kvm.vmcraft.nbd import NBDDeviceManager


def setup_logging():
    """Configure logging."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    return logging.getLogger(__name__)


def example_basic_validation(image_path: Path, logger: logging.Logger):
    """
    Example 1: Basic Image Validation

    Fast, safe validation using qemu-img only.
    - No root required
    - No NBD device needed
    - Checks format and detects corruption
    """
    print("\n" + "=" * 70)
    print("Example 1: Basic Image Validation")
    print("=" * 70)

    try:
        # Create NBD manager (won't actually connect for validation)
        nbd = NBDDeviceManager(logger, readonly=True)

        # Validate image - raises RuntimeError if invalid
        metadata = nbd._validate_image(image_path)

        print(f"\n✓ Image is valid: {image_path.name}")
        print(f"  Format: {metadata.get('format')}")
        print(f"  Virtual Size: {metadata.get('virtual-size') / (1024**3):.2f} GiB")
        print(f"  Actual Size: {metadata.get('actual-size') / (1024**3):.2f} GiB")

        if "backing-filename" in metadata:
            print(f"  ⚠ Warning: Has backing file (snapshot): {metadata['backing-filename']}")

        return True

    except RuntimeError as e:
        print(f"\n✗ Validation failed: {e}")
        return False


def example_deep_validation(image_path: Path, logger: logging.Logger):
    """
    Example 2: Deep Filesystem Validation

    Validates partition table by temporarily connecting via NBD.
    - Requires root/sudo
    - Checks partition structure
    - Verifies partition table is readable
    """
    print("\n" + "=" * 70)
    print("Example 2: Deep Filesystem Validation (Partition Table)")
    print("=" * 70)

    try:
        nbd = NBDDeviceManager(logger, readonly=True)

        # Perform deep validation
        report = nbd.validate_filesystems(
            image_path,
            check_partitions=True,
            run_fsck=False,  # Don't run fsck yet
        )

        print(f"\n✓ Deep validation passed: {image_path.name}")
        print(f"\nPartitions found: {len(report['partitions'])}")

        for part in report["partitions"]:
            print(f"  - {part['device']}")

        # Show partition table
        if "partition_table" in report:
            print("\nPartition Table:")
            print(report["partition_table"])

        return True

    except RuntimeError as e:
        print(f"\n✗ Deep validation failed: {e}")
        return False


def example_full_validation(image_path: Path, logger: logging.Logger):
    """
    Example 3: Full Validation with Filesystem Checks

    Runs read-only filesystem checks on all partitions.
    - Requires root/sudo
    - Slower (depends on disk size)
    - Detects filesystem corruption
    """
    print("\n" + "=" * 70)
    print("Example 3: Full Validation with Filesystem Checks (fsck)")
    print("=" * 70)

    try:
        nbd = NBDDeviceManager(logger, readonly=True)

        # Full validation with fsck
        report = nbd.validate_filesystems(
            image_path,
            check_partitions=True,
            run_fsck=True,  # Enable filesystem checks
        )

        print(f"\n✓ Full validation completed: {image_path.name}")

        # Show fsck results
        if report["fsck_results"]:
            print("\nFilesystem Check Results:")
            for fsck in report["fsck_results"]:
                status_icon = "✓" if fsck["status"] == "clean" else "✗"
                print(f"  {status_icon} {fsck['partition']}: {fsck['status']}")

                if fsck["status"] == "errors_found":
                    print(f"     Exit code: {fsck['exit_code']}")
                    print(f"     Output: {fsck['output'][:200]}...")

        return True

    except RuntimeError as e:
        print(f"\n✗ Full validation failed: {e}")
        return False


def example_pre_migration_check(image_path: Path, logger: logging.Logger):
    """
    Example 4: Complete Pre-Migration Validation Workflow

    Recommended workflow before migrating VMs:
    1. Quick structure check
    2. Partition table validation
    3. Optional: Filesystem integrity check
    """
    print("\n" + "=" * 70)
    print("Example 4: Pre-Migration Validation Workflow")
    print("=" * 70)

    # Step 1: Quick check
    print("\n[Step 1/3] Quick structure check...")
    if not example_basic_validation(image_path, logger):
        print("✗ Basic validation failed - image is corrupted or invalid")
        return False

    # Step 2: Partition table check (requires sudo)
    print("\n[Step 2/3] Partition table validation...")
    try:
        nbd = NBDDeviceManager(logger, readonly=True)
        report = nbd.validate_filesystems(image_path, check_partitions=True, run_fsck=False)
        print(f"✓ Found {len(report['partitions'])} partitions")
    except RuntimeError as e:
        print(f"⚠ Warning: Could not validate partitions: {e}")
        print("  (This may require sudo)")

    # Step 3: Optional filesystem check (slow, requires sudo)
    print("\n[Step 3/3] Filesystem integrity check (optional, requires sudo)...")
    print("  Skipping for demo - use --full flag in production")

    print("\n" + "=" * 70)
    print("✓ Pre-migration validation completed")
    print("=" * 70)
    print("\nRecommendation: Image is ready for migration")

    return True


def main():
    """Run validation examples."""
    logger = setup_logging()

    # Check if image path provided
    if len(sys.argv) < 2:
        print("Usage: python examples/vmdk_validation_example.py <image_path>")
        print("\nExample:")
        print("  python examples/vmdk_validation_example.py /vms/centos.vmdk")
        print("\nNote: Deep and full validation require sudo:")
        print("  sudo python examples/vmdk_validation_example.py /vms/centos.vmdk")
        sys.exit(1)

    image_path = Path(sys.argv[1])

    if not image_path.exists():
        print(f"Error: Image not found: {image_path}")
        sys.exit(1)

    print("=" * 70)
    print("VMDK/Disk Image Validation Examples")
    print("=" * 70)
    print(f"\nImage: {image_path}")

    # Run examples
    example_basic_validation(image_path, logger)

    # Check if running as root for advanced examples
    import os

    if os.geteuid() == 0:
        example_deep_validation(image_path, logger)
        # example_full_validation(image_path, logger)  # Uncomment to run fsck
        example_pre_migration_check(image_path, logger)
    else:
        print("\n" + "=" * 70)
        print("Note: Advanced validation examples require sudo")
        print("=" * 70)
        print("\nTo run deep/full validation, use:")
        print(f"  sudo python examples/vmdk_validation_example.py {image_path}")


if __name__ == "__main__":
    main()
