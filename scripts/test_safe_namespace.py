#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Test Safe Namespace Engine with RHEL 8.8 VMDK

Tests the safe namespace engine with a single VM conversion.
"""

import logging
import subprocess
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from h2kvm.vmcraft.safe_namespace_engine import SafeNamespaceEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def main():
    """Run safe namespace engine test."""
    logger.info("=" * 60)
    logger.info("Safe Namespace Engine - RHEL 8.8 Test")
    logger.info("=" * 60)

    # Check if VMDK exists
    vmdk_path = Path("./esx8.0-rhel8.8-with-thin-provision-disk1.vmdk")
    if not vmdk_path.exists():
        logger.error("VMDK file not found: %s", vmdk_path)
        return 1

    # NBD device
    nbd_device = "/dev/nbd0"

    # Create output directory
    output_dir = Path("./output")
    output_dir.mkdir(exist_ok=True)

    logger.info("\nConversion Details:")
    logger.info("  Source: %s", vmdk_path)
    logger.info("  NBD Device: %s", nbd_device)
    logger.info("  Backend: Safe Namespace Engine")
    logger.info("")

    try:
        # Connect VMDK to NBD
        logger.info("Connecting VMDK to NBD device...")
        subprocess.run(
            [
                "qemu-nbd",
                "--connect",
                nbd_device,
                "--cache",
                "writeback",
                str(vmdk_path),
            ],
            check=True,
            timeout=30,
        )

        subprocess.run(["partprobe", nbd_device], check=False, timeout=10)
        subprocess.run(["udevadm", "settle"], check=False, timeout=10)

        logger.info("✅ VMDK connected to %s\n", nbd_device)

        # Create safe namespace engine
        logger.info("Creating safe namespace engine...")
        engine = SafeNamespaceEngine(nbd_device)

        try:
            # Start namespace
            logger.info("Starting namespace...")
            engine.start()
            logger.info("✅ Namespace started\n")

            # Detect OS
            logger.info("[1/5] Detecting OS...")
            try:
                os_release = engine.run("cat /etc/os-release | grep PRETTY_NAME")
                logger.info("OS: %s\n", os_release)
            except Exception as e:
                logger.warning("Could not detect OS: %s\n", e)

            # Check kernel
            logger.info("[2/5] Checking kernel version...")
            try:
                kernel = engine.run("uname -r")
                logger.info("Kernel: %s\n", kernel)
            except Exception as e:
                logger.warning("Could not detect kernel: %s\n", e)

            # Remove VMware tools
            logger.info("[3/5] Removing VMware tools...")
            try:
                engine.run("""
                    systemctl stop vmtoolsd 2>/dev/null || true
                    systemctl disable vmtoolsd 2>/dev/null || true
                    yum remove -y open-vm-tools vmware-tools 2>/dev/null || true
                """)
                logger.info("✅ VMware tools removed\n")
            except Exception as e:
                logger.warning("VMware tools removal failed: %s\n", e)

            # Regenerate initramfs
            logger.info("[4/5] Regenerating initramfs with virtio drivers...")
            logger.info("This may take 1-2 minutes...")
            engine.run(
                "dracut --force --no-hostonly "
                "--add-drivers 'virtio_blk virtio_scsi virtio_net virtio_pci ahci sd_mod' "
                "--add lvm --add dm"
            )
            logger.info("✅ Initramfs regenerated\n")

            # Update GRUB
            logger.info("[5/5] Updating GRUB configuration...")
            engine.run("grub2-mkconfig -o /boot/grub2/grub.cfg")
            logger.info("✅ GRUB configuration updated\n")

            logger.info("=" * 60)
            logger.info("✅ VM conversion completed successfully!")
            logger.info("=" * 60)

        finally:
            # Cleanup namespace
            logger.info("\nCleaning up namespace...")
            engine.cleanup()
            logger.info("✅ Namespace cleaned up")

    finally:
        # Disconnect NBD
        logger.info("Disconnecting NBD device...")
        subprocess.run(
            ["qemu-nbd", "--disconnect", nbd_device],
            check=False,
            timeout=10,
        )
        logger.info("✅ NBD disconnected")

    return 0


if __name__ == "__main__":
    sys.exit(main())
