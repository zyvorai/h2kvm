#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
VMDK/Disk Image Validation Script

Validates disk images using qemu-img for integrity checking and
optionally performs deep filesystem validation via NBD.

Usage:
    # Basic validation (metadata + structure check)
    python scripts/validate_vmdk.py /path/to/disk.vmdk

    # Deep validation (includes partition table check)
    sudo python scripts/validate_vmdk.py --deep /path/to/disk.vmdk

    # Full validation (includes read-only filesystem checks)
    sudo python scripts/validate_vmdk.py --full /path/to/disk.vmdk

Requirements:
    - qemu-img (for all modes)
    - qemu-nbd, NBD kernel module (for --deep and --full)
    - fsck (for --full)
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from h2kvm.vmcraft.nbd import NBDDeviceManager


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")
    return logging.getLogger(__name__)


def format_size(bytes_val: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} PiB"


def basic_validation(image_path: Path, logger: logging.Logger) -> bool:
    """
    Perform basic image validation using qemu-img.

    This is fast, safe, and does not require root or NBD devices.
    """
    logger.info("=" * 70)
    logger.info(f"Basic Validation: {image_path.name}")
    logger.info("=" * 70)

    try:
        # Create NBD manager just for validation (won't connect)
        nbd = NBDDeviceManager(logger, readonly=True)

        # Use internal validation method
        metadata = nbd._validate_image(image_path)

        # Display results
        logger.info("\n✓ Image Structure: VALID")
        logger.info("\nImage Metadata:")
        logger.info(f"  Format: {metadata.get('format', 'unknown')}")
        logger.info(f"  Virtual Size: {format_size(metadata.get('virtual-size', 0))}")
        logger.info(f"  Actual Size: {format_size(metadata.get('actual-size', 0))}")

        if "backing-filename" in metadata:
            logger.warning(f"\n⚠ Backing File: {metadata['backing-filename']}")
            logger.warning("  This is a snapshot or linked clone.")

        if metadata.get("encrypted", False):
            logger.warning("\n⚠ Image is encrypted")

        # Check for snapshots
        if "snapshots" in metadata:
            logger.info(f"\nSnapshots: {len(metadata['snapshots'])}")
            for snap in metadata["snapshots"][:5]:  # Show first 5
                logger.info(f"  - {snap.get('name', 'unknown')}")

        logger.info("\n" + "=" * 70)
        logger.info("Basic validation completed successfully")
        logger.info("=" * 70)
        return True

    except Exception as e:
        logger.error(f"\n✗ Validation Failed: {e}")
        return False


def deep_validation(image_path: Path, logger: logging.Logger, run_fsck: bool = False) -> bool:
    """
    Perform deep filesystem validation.

    Temporarily connects image via NBD to check partition table
    and optionally run filesystem checks.

    Requires root/sudo and NBD kernel module.
    """
    logger.info("=" * 70)
    logger.info(f"Deep Validation: {image_path.name}")
    logger.info("=" * 70)

    try:
        nbd = NBDDeviceManager(logger, readonly=True)

        # Perform deep validation
        report = nbd.validate_filesystems(image_path, check_partitions=True, run_fsck=run_fsck)

        # Display results
        logger.info("\n✓ Deep Validation: PASSED")
        logger.info(f"\nImage: {report['image']}")
        logger.info(f"Format: {report['format']}")
        logger.info(f"Virtual Size: {report['virtual_size_gb']:.2f} GiB")
        logger.info(f"Actual Size: {report['actual_size_gb']:.2f} GiB")

        # Show partition table
        if "partition_table" in report:
            logger.info("\nPartition Table:")
            logger.info(report["partition_table"])

        # Show partition details
        if report["partitions"]:
            logger.info(f"\nFound {len(report['partitions'])} partitions:")
            for part in report["partitions"]:
                logger.info(f"  - {part['device']}: {part['info']}")

        # Show fsck results
        if report["fsck_results"]:
            logger.info("\nFilesystem Checks:")
            for fsck in report["fsck_results"]:
                status_icon = "✓" if fsck["status"] == "clean" else "✗"
                logger.info(f"  {status_icon} {fsck['partition']}: {fsck['status']}")

                if fsck["status"] == "errors_found":
                    logger.warning(f"    Output: {fsck['output'][:200]}")

        logger.info("\n" + "=" * 70)
        logger.info("Deep validation completed successfully")
        logger.info("=" * 70)
        return True

    except Exception as e:
        logger.error(f"\n✗ Deep Validation Failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Validate VMDK and disk images for integrity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic validation (fast, no root required)
  python scripts/validate_vmdk.py /vms/centos.vmdk

  # Deep validation with partition table check (requires sudo)
  sudo python scripts/validate_vmdk.py --deep /vms/centos.vmdk

  # Full validation with filesystem checks (requires sudo, slower)
  sudo python scripts/validate_vmdk.py --full /vms/centos.vmdk

  # Verbose output
  python scripts/validate_vmdk.py -v /vms/centos.vmdk

Validation Levels:
  Basic (default): qemu-img metadata + structure check
  Deep (--deep):   Basic + partition table inspection via NBD
  Full (--full):   Deep + read-only filesystem checks (fsck -n)

Note:
  - Basic mode works without root privileges
  - Deep and Full modes require sudo and NBD kernel module
  - Full mode may take several minutes for large disks
        """,
    )

    parser.add_argument("image", type=Path, help="Path to disk image (VMDK, QCOW2, VHD, etc.)")

    parser.add_argument(
        "--deep", action="store_true", help="Enable deep validation (partition table check via NBD)"
    )

    parser.add_argument(
        "--full", action="store_true", help="Enable full validation (includes read-only fsck)"
    )

    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output (debug logging)")

    parser.add_argument(
        "--json", action="store_true", help="Output results as JSON (for --deep/--full only)"
    )

    args = parser.parse_args()

    # Setup logging
    logger = setup_logging(args.verbose)

    # Validate image path
    if not args.image.exists():
        logger.error(f"Image not found: {args.image}")
        sys.exit(1)

    # Determine validation level
    if args.full:
        # Full validation includes fsck
        success = deep_validation(args.image, logger, run_fsck=True)
    elif args.deep:
        # Deep validation without fsck
        success = deep_validation(args.image, logger, run_fsck=False)
    else:
        # Basic validation (default)
        success = basic_validation(args.image, logger)

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
