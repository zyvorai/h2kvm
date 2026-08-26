#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Example: Boot testing using h2kvm library.

This example demonstrates:
- Testing boot with QEMU
- Testing boot with libvirt
- Validating migrated VMs

Usage:
    python library_boot_testing.py /var/lib/libvirt/images/vm.qcow2
"""

import logging
import sys
from pathlib import Path

from h2kvm import GuestDetector
from h2kvm.quality.testing import LibvirtTest, QemuTest

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def test_boot_qemu(
    image_path: str,
    memory: int = 4096,
    vcpus: int = 2,
    uefi: bool = False,
    timeout: int = 180,
    headless: bool = True,
):
    """
    Test boot using QEMU directly.

    Args:
        image_path: Path to qcow2 disk image
        memory: RAM in MB
        vcpus: Number of virtual CPUs
        uefi: Use UEFI firmware (vs BIOS)
        timeout: Boot timeout in seconds
        headless: Run without GUI
    """

    logger.info(f"Testing boot with QEMU: {image_path}")
    logger.info(f"  Memory:   {memory}MB")
    logger.info(f"  vCPUs:    {vcpus}")
    logger.info(f"  Firmware: {'UEFI' if uefi else 'BIOS'}")
    logger.info(f"  Timeout:  {timeout}s")
    logger.info(f"  Headless: {headless}")

    # Initialize tester
    tester = QemuTest(
        image_path=image_path, memory=memory, vcpus=vcpus, uefi=uefi, timeout=timeout, headless=headless
    )

    # Run boot test
    logger.info("Starting boot test...")
    try:
        result = tester.test_boot()

        if result.success:
            logger.info("✓ Boot test PASSED")
            logger.info(f"  Boot time: {result.boot_time:.2f}s")
            if result.console_log:
                logger.info(f"  Console log: {len(result.console_log)} bytes")
        else:
            logger.error("✗ Boot test FAILED")
            logger.error(f"  Error: {result.error}")
            if result.last_console_lines:
                logger.error("  Last console output:")
                for line in result.last_console_lines[-10:]:
                    logger.error(f"    {line}")

        return result

    except Exception as e:
        logger.error(f"✗ Boot test exception: {e}")
        raise


def test_boot_libvirt(
    image_path: str, memory: int = 4096, vcpus: int = 2, uefi: bool = False, timeout: int = 180
):
    """
    Test boot using libvirt.

    Args:
        image_path: Path to qcow2 disk image
        memory: RAM in MB
        vcpus: Number of virtual CPUs
        uefi: Use UEFI firmware (vs BIOS)
        timeout: Boot timeout in seconds
    """

    logger.info(f"Testing boot with libvirt: {image_path}")
    logger.info(f"  Memory:   {memory}MB")
    logger.info(f"  vCPUs:    {vcpus}")
    logger.info(f"  Firmware: {'UEFI' if uefi else 'BIOS'}")
    logger.info(f"  Timeout:  {timeout}s")

    # Initialize tester
    tester = LibvirtTest(image_path=image_path, memory=memory, vcpus=vcpus, uefi=uefi, timeout=timeout)

    # Run boot test
    logger.info("Starting boot test...")
    try:
        result = tester.test_boot()

        if result.success:
            logger.info("✓ Boot test PASSED")
            logger.info(f"  Boot time: {result.boot_time:.2f}s")
            logger.info(f"  Domain:    {result.domain_name}")
        else:
            logger.error("✗ Boot test FAILED")
            logger.error(f"  Error: {result.error}")
            if result.console_log:
                logger.error("  Console output available")

        return result

    except Exception as e:
        logger.error(f"✗ Boot test exception: {e}")
        raise


def auto_detect_and_test(image_path: str):
    """
    Auto-detect guest firmware and test boot.

    This function:
    1. Detects guest OS and firmware type
    2. Tests with appropriate settings
    """

    logger.info("Auto-detecting guest configuration...")

    # Detect guest OS
    try:
        detector = GuestDetector()
        guest = detector.detect_from_image(image_path)

        logger.info("Detected guest:")
        logger.info(f"  OS:       {guest.os_pretty}")
        logger.info(f"  Firmware: {guest.firmware}")
        logger.info(f"  Arch:     {guest.architecture}")

        # Determine if UEFI
        uefi = guest.firmware.lower() == "uefi"

    except Exception as e:
        logger.warning(f"Guest detection failed: {e}")
        logger.info("Defaulting to BIOS boot")
        uefi = False

    # Test boot
    logger.info(f"Testing boot ({'UEFI' if uefi else 'BIOS'})...")
    return test_boot_qemu(image_path=image_path, uefi=uefi, timeout=180, headless=True)


def main():
    """Main entry point."""

    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <image.qcow2> [method] [firmware]")
        print()
        print("Methods:")
        print("  qemu     - Test with QEMU (default)")
        print("  libvirt  - Test with libvirt")
        print("  auto     - Auto-detect and test")
        print()
        print("Firmware:")
        print("  bios - Use BIOS/SeaBIOS (default)")
        print("  uefi - Use UEFI/OVMF")
        print()
        print("Examples:")
        print(f"  {sys.argv[0]} /var/lib/libvirt/images/vm.qcow2")
        print(f"  {sys.argv[0]} /var/lib/libvirt/images/vm.qcow2 qemu uefi")
        print(f"  {sys.argv[0]} /var/lib/libvirt/images/vm.qcow2 auto")
        sys.exit(1)

    image_path = sys.argv[1]
    method = sys.argv[2] if len(sys.argv) > 2 else "qemu"
    firmware = sys.argv[3] if len(sys.argv) > 3 else "bios"

    # Validate input
    if not Path(image_path).exists():
        logger.error(f"Image file not found: {image_path}")
        sys.exit(1)

    # Determine UEFI
    uefi = firmware.lower() == "uefi"

    # Run test
    try:
        if method == "auto":
            result = auto_detect_and_test(image_path)
        elif method == "libvirt":
            result = test_boot_libvirt(image_path, uefi=uefi)
        else:  # qemu
            result = test_boot_qemu(image_path, uefi=uefi, headless=True)

        if result.success:
            logger.info("✓ Boot test successful!")
            sys.exit(0)
        else:
            logger.error("✗ Boot test failed!")
            sys.exit(1)

    except Exception as e:
        logger.error(f"✗ Test failed with exception: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
