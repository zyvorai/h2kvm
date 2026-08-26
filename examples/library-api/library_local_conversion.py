#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Example: Local VMDK to qcow2 conversion using hyper2kvm library.

This example demonstrates:
- Converting a local VMDK file to qcow2
- Detecting guest OS
- Flattening snapshot chains
- Compressing output

Usage:
    python library_local_conversion.py /path/to/source.vmdk /path/to/output.qcow2
"""

import logging
import sys
from pathlib import Path

from hyper2kvm import DiskProcessor, GuestDetector

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def convert_vmdk_to_qcow2(source_path: str, output_path: str):
    """Convert VMDK to qcow2 with optimizations."""

    logger.info(f"Converting {source_path} to {output_path}")

    # Initialize disk processor
    processor = DiskProcessor()

    # Optional: Detect guest OS for optimizations
    # Note: This requires mounting the disk, so it's optional
    try:
        GuestDetector()
        # For offline detection, we'd need to mount first
        # guest = detector.detect_from_image(source_path)
        # logger.info(f"Detected guest: {guest.os_pretty}")
        guest = None
    except Exception as e:
        logger.warning(f"Could not detect guest OS: {e}")
        guest = None

    # Convert disk
    try:
        result = processor.process_disk(
            source_path=source_path,
            output_path=output_path,
            flatten=True,  # Flatten VMDK snapshot chains
            compress=True,  # Compress output qcow2
            guest_identity=guest,
        )

        logger.info("Conversion complete!")
        logger.info(f"  Input:  {result.source_path}")
        logger.info(f"  Output: {result.output_path}")
        logger.info(f"  Size:   {result.output_size:,} bytes")
        logger.info(f"  Time:   {result.duration:.2f}s")

        return result

    except Exception as e:
        logger.error(f"Conversion failed: {e}")
        raise


def main():
    """Main entry point."""

    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <source.vmdk> <output.qcow2>")
        print()
        print("Example:")
        print(f"  {sys.argv[0]} /data/vm.vmdk /data/vm.qcow2")
        sys.exit(1)

    source_path = sys.argv[1]
    output_path = sys.argv[2]

    # Validate input
    if not Path(source_path).exists():
        logger.error(f"Source file not found: {source_path}")
        sys.exit(1)

    # Run conversion
    try:
        convert_vmdk_to_qcow2(source_path, output_path)
        logger.info("✓ Conversion successful!")
        sys.exit(0)

    except Exception as e:
        logger.error(f"✗ Conversion failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
