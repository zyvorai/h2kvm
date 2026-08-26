#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Example: Guest OS fixing using hyper2kvm library.

This example demonstrates:
- Detecting guest OS from disk image
- Applying offline fixes (fstab, GRUB, network)
- Regenerating initramfs
- Removing VMware Tools
- Generating migration report

Usage:
    sudo python library_guest_fixing.py /var/lib/libvirt/images/vm.qcow2
"""

import logging
import sys
from pathlib import Path

from hyper2kvm import GuestDetector
from hyper2kvm.fixers import OfflineFSFix

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def fix_guest_os(image_path: str, report_path: str = None):
    """
    Apply offline fixes to a converted VM disk image.

    Args:
        image_path: Path to qcow2 disk image
        report_path: Optional path for migration report
    """

    logger.info(f"Fixing guest OS in: {image_path}")

    # Step 1: Detect guest OS
    logger.info("Detecting guest OS...")
    try:
        detector = GuestDetector()
        guest = detector.detect_from_image(image_path)

        logger.info("Detected guest OS:")
        logger.info(f"  OS:           {guest.os_pretty}")
        logger.info(f"  Type:         {guest.guest_type}")
        logger.info(f"  Architecture: {guest.architecture}")
        logger.info(f"  Firmware:     {guest.firmware}")
        logger.info(f"  Init system:  {guest.init_system}")

    except Exception as e:
        logger.error(f"Guest detection failed: {e}")
        raise

    # Step 2: Initialize fixer
    logger.info("Initializing offline fixer...")
    fixer = OfflineFSFix(image_path=image_path, guest_identity=guest, verbose=True)

    # Track results
    fixes_applied = []
    fixes_failed = []

    # Step 3: Fix fstab
    logger.info("Fixing /etc/fstab (UUID-based mounting)...")
    try:
        result = fixer.fix_fstab()
        if result.success:
            logger.info(f"✓ fstab fixed: {result.changes_made} changes")
            fixes_applied.append("fstab")
        else:
            logger.warning(f"✗ fstab fix failed: {result.error}")
            fixes_failed.append(("fstab", result.error))
    except Exception as e:
        logger.error(f"✗ fstab fix exception: {e}")
        fixes_failed.append(("fstab", str(e)))

    # Step 4: Fix GRUB
    logger.info("Fixing GRUB bootloader...")
    try:
        result = fixer.fix_grub()
        if result.success:
            logger.info("✓ GRUB fixed")
            fixes_applied.append("grub")
        else:
            logger.warning(f"✗ GRUB fix failed: {result.error}")
            fixes_failed.append(("grub", result.error))
    except Exception as e:
        logger.error(f"✗ GRUB fix exception: {e}")
        fixes_failed.append(("grub", str(e)))

    # Step 5: Fix network configuration
    logger.info("Fixing network configuration...")
    try:
        result = fixer.fix_network()
        if result.success:
            logger.info(f"✓ Network fixed: {result.interfaces_fixed} interfaces")
            fixes_applied.append("network")
        else:
            logger.warning(f"✗ Network fix failed: {result.error}")
            fixes_failed.append(("network", result.error))
    except Exception as e:
        logger.error(f"✗ Network fix exception: {e}")
        fixes_failed.append(("network", str(e)))

    # Step 6: Regenerate initramfs (important for virtio drivers)
    if guest.guest_type.value == "linux":
        logger.info("Regenerating initramfs with virtio drivers...")
        try:
            result = fixer.regenerate_initramfs()
            if result.success:
                logger.info("✓ Initramfs regenerated")
                fixes_applied.append("initramfs")
            else:
                logger.warning(f"✗ Initramfs regeneration failed: {result.error}")
                fixes_failed.append(("initramfs", result.error))
        except Exception as e:
            logger.error(f"✗ Initramfs exception: {e}")
            fixes_failed.append(("initramfs", str(e)))

    # Step 7: Remove VMware Tools
    logger.info("Removing VMware Tools...")
    try:
        result = fixer.remove_vmware_tools()
        if result.success:
            logger.info(f"✓ VMware Tools removed: {result.items_removed} items")
            fixes_applied.append("vmware-tools")
        else:
            logger.info("VMware Tools not found or already removed")
    except Exception as e:
        logger.warning(f"VMware Tools removal exception: {e}")

    # Step 8: Generate report
    logger.info("Generating migration report...")
    try:
        report = fixer.generate_report()
        if report_path:
            # Copy report to specified location
            import shutil

            shutil.copy(report.path, report_path)
            logger.info(f"✓ Report saved to: {report_path}")
        else:
            logger.info(f"✓ Report saved to: {report.path}")
    except Exception as e:
        logger.warning(f"Report generation failed: {e}")

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("Fix Summary")
    logger.info("=" * 60)
    logger.info(f"Fixes applied:  {len(fixes_applied)}")
    for fix in fixes_applied:
        logger.info(f"  ✓ {fix}")
    logger.info(f"Fixes failed:   {len(fixes_failed)}")
    for fix, error in fixes_failed:
        logger.info(f"  ✗ {fix}: {error}")
    logger.info("=" * 60)

    return {"guest": guest, "fixes_applied": fixes_applied, "fixes_failed": fixes_failed}


def main():
    """Main entry point."""

    if len(sys.argv) < 2:
        print(f"Usage: sudo {sys.argv[0]} <image.qcow2> [report.md]")
        print()
        print("Example:")
        print(f"  sudo {sys.argv[0]} /var/lib/libvirt/images/vm.qcow2")
        print(f"  sudo {sys.argv[0]} /var/lib/libvirt/images/vm.qcow2 /tmp/report.md")
        print()
        print("Note: This script requires root/sudo for guest filesystem access")
        sys.exit(1)

    image_path = sys.argv[1]
    report_path = sys.argv[2] if len(sys.argv) > 2 else None

    # Validate input
    if not Path(image_path).exists():
        logger.error(f"Image file not found: {image_path}")
        sys.exit(1)

    # Check if running as root
    import os

    if os.geteuid() != 0:
        logger.error("This script must be run as root (sudo)")
        sys.exit(1)

    # Run fixes
    try:
        result = fix_guest_os(image_path, report_path)

        if result["fixes_failed"]:
            logger.warning("⚠ Some fixes failed, but migration may still work")
            sys.exit(0)
        else:
            logger.info("✓ All fixes applied successfully!")
            sys.exit(0)

    except Exception as e:
        logger.error(f"✗ Fix process failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
