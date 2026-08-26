#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Disk Inspection Example

Demonstrates using the integrated disk inspection capabilities
in the existing NBDDeviceManager.

Uses auto-detected NBD devices - no manual device specification needed.
"""

import json
import logging
import sys
from pathlib import Path

from h2kvm.vmcraft.nbd import NBDDeviceManager


def setup_logging():
    """Configure logging."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    return logging.getLogger(__name__)


def example_basic_inspection(image_path: Path, logger: logging.Logger):
    """
    Example 1: Basic Disk Inspection

    Inspects partition table and LVM structures.
    NBD device is automatically allocated.
    """
    print("\n" + "=" * 70)
    print("Example 1: Basic Disk Inspection (Partition + LVM)")
    print("=" * 70)

    nbd = NBDDeviceManager(logger, readonly=True)

    try:
        report = nbd.inspect_disk(
            image_path,
            check_lvm=True,
            activate_lvm=False,  # Don't activate for basic inspection
            run_fsck=False,
        )

        print(f"\n✓ Inspection completed:")
        print(f"  Image: {report['image']}")
        print(f"  Format: {report['format']}")
        print(f"  Partitions: {len(report['partitions'])}")
        print(f"  LVM PVs: {len(report['lvm']['physical_volumes'])}")
        print(f"  LVM VGs: {len(report['lvm']['volume_groups'])}")
        print(f"  LVM LVs: {len(report['lvm']['logical_volumes'])}")

        return report

    except Exception as e:
        print(f"\n✗ Inspection failed: {e}")
        return None


def example_full_inspection(image_path: Path, logger: logging.Logger):
    """
    Example 2: Full Disk Inspection with LVM Activation

    Activates LVM to detect logical volumes and filesystems.
    NBD device is automatically allocated.
    """
    print("\n" + "=" * 70)
    print("Example 2: Full Inspection with LVM Activation")
    print("=" * 70)

    nbd = NBDDeviceManager(logger, readonly=True)

    try:
        report = nbd.inspect_disk(
            image_path,
            check_lvm=True,
            activate_lvm=True,  # Activate to see LVs
            run_fsck=False,
        )

        print(f"\n✓ Full inspection completed:")
        print(f"  Partitions: {len(report['partitions'])}")
        print(f"  LVM structures:")
        print(f"    - Physical Volumes: {len(report['lvm']['physical_volumes'])}")
        print(f"    - Volume Groups: {len(report['lvm']['volume_groups'])}")
        print(f"    - Logical Volumes: {len(report['lvm']['logical_volumes'])}")
        print(f"  Filesystems detected: {len(report['filesystems'])}")

        # Show logical volumes
        if report["lvm"]["logical_volumes"]:
            print("\n  Logical Volumes:")
            for lv in report["lvm"]["logical_volumes"]:
                print(f"    - {lv['path']} ({lv['size']})")

        # Show filesystems
        if report["filesystems"]:
            print("\n  Filesystems:")
            for fs in report["filesystems"]:
                print(f"    - {fs['device']}: {fs['fstype']}")

        return report

    except Exception as e:
        print(f"\n✗ Full inspection failed: {e}")
        return None


def example_with_fsck(image_path: Path, logger: logging.Logger):
    """
    Example 3: Complete Inspection with Filesystem Checks

    Performs filesystem integrity checks (read-only).
    NBD device is automatically allocated.
    """
    print("\n" + "=" * 70)
    print("Example 3: Complete Inspection with Filesystem Checks")
    print("=" * 70)

    nbd = NBDDeviceManager(logger, readonly=True)

    try:
        report = nbd.inspect_disk(
            image_path,
            check_lvm=True,
            activate_lvm=True,
            run_fsck=True,  # Run filesystem checks
        )

        print(f"\n✓ Complete inspection with fsck:")
        print(f"  Filesystems checked: {len(report['fsck_results'])}")

        if report["fsck_results"]:
            clean_count = sum(1 for r in report["fsck_results"] if r["status"] == "clean")
            print(f"  Clean: {clean_count}/{len(report['fsck_results'])}")

            print("\n  Filesystem Check Results:")
            for fsck in report["fsck_results"]:
                status_icon = "✓" if fsck["status"] == "clean" else "✗"
                print(f"    {status_icon} {fsck['device']}: {fsck['status']}")

        return report

    except Exception as e:
        print(f"\n✗ Inspection with fsck failed: {e}")
        return None


def example_json_report(image_path: Path, logger: logging.Logger):
    """
    Example 4: Generate JSON Report

    Exports inspection results as JSON for automation.
    """
    print("\n" + "=" * 70)
    print("Example 4: JSON Report Generation")
    print("=" * 70)

    nbd = NBDDeviceManager(logger, readonly=True)

    try:
        report = nbd.inspect_disk(image_path, check_lvm=True, activate_lvm=True, run_fsck=False)

        # Save as JSON
        report_file = Path("inspection-report.json")
        report_file.write_text(json.dumps(report, indent=2))

        print(f"\n✓ JSON report saved to: {report_file}")
        print(f"\nSample output:")
        print(json.dumps(report, indent=2)[:500] + "...")

        return report

    except Exception as e:
        print(f"\n✗ Report generation failed: {e}")
        return None


def main():
    """Run disk inspection examples."""
    logger = setup_logging()

    if len(sys.argv) < 2:
        print("Usage: sudo python examples/inspection/disk-inspection-example.py <image_path>")
        print("\nExample:")
        print("  sudo python examples/inspection/disk-inspection-example.py /vms/centos.vmdk")
        print("\nNote: Requires sudo for NBD operations and LVM inspection")
        sys.exit(1)

    image_path = Path(sys.argv[1])

    if not image_path.exists():
        print(f"Error: Image not found: {image_path}")
        sys.exit(1)

    print("=" * 70)
    print("Disk Inspection Examples")
    print("=" * 70)
    print(f"Image: {image_path}")
    print("\nNote: NBD devices are automatically allocated")

    # Run examples
    example_basic_inspection(image_path, logger)
    example_full_inspection(image_path, logger)
    # example_with_fsck(image_path, logger)  # Uncomment to run fsck
    example_json_report(image_path, logger)

    print("\n" + "=" * 70)
    print("Examples completed")
    print("=" * 70)


if __name__ == "__main__":
    import os

    if os.geteuid() != 0:
        print("Error: This script requires sudo for NBD and LVM operations")
        print("Usage: sudo python examples/inspection/disk-inspection-example.py <image_path>")
        sys.exit(1)

    main()
