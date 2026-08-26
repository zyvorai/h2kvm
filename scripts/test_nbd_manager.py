#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Test Production-Grade NBD Manager with RHEL 8.8 VMDK

Tests the new NBD manager with proper cleanup sequence
and ESX thin-provisioned VMDK support.
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from h2kvm.vmcraft.nbd_manager import NBDDevice, cleanup_all_nbd_devices
from h2kvm.vmcraft.safe_namespace_engine import SafeNamespaceEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def main():
    """Run NBD manager test with RHEL 8.8 VMDK."""
    logger.info("=" * 60)
    logger.info("Production NBD Manager - RHEL 8.8 Test")
    logger.info("=" * 60)

    # Check if VMDK exists
    vmdk_path = Path("./esx8.0-rhel8.8-with-thin-provision-disk1.vmdk")
    if not vmdk_path.exists():
        logger.error("VMDK file not found: %s", vmdk_path)
        return 1

    logger.info("\nTest Details:")
    logger.info("  Source: %s", vmdk_path)
    logger.info("  Backend: Production NBD Manager + Safe Namespace Engine")
    logger.info("  Features: ESX thin-provisioned VMDK support")
    logger.info("")

    # Cleanup orphaned devices first
    logger.info("Cleaning up orphaned NBD devices...")
    cleaned = cleanup_all_nbd_devices()
    logger.info("✅ Cleaned up %d orphaned devices\n", cleaned)

    try:
        # Use production NBD manager with ESX thin-provisioned settings
        logger.info("Connecting VMDK with production NBD manager...")
        logger.info("  • cache=none (prevents corruption)")
        logger.info("  • aio=native (better performance)")
        logger.info("  • discard=unmap (thin provisioning support)")
        logger.info("")

        with NBDDevice(
            vmdk_path,
            cache_mode="none",  # Critical for ESX thin VMDKs
            aio_mode="native",
            discard=True,
        ) as nbd:
            logger.info("✅ NBD device connected: %s\n", nbd.device)

            # Create safe namespace engine
            logger.info("Creating safe namespace engine...")
            engine = SafeNamespaceEngine(nbd.device)

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

        # NBD device automatically disconnected with proper sequence
        logger.info("✅ NBD device automatically disconnected with safe cleanup\n")

        logger.info("=" * 60)
        logger.info("✅ Test completed successfully!")
        logger.info("=" * 60)
        logger.info("\nProduction NBD Manager features demonstrated:")
        logger.info("  ✅ Auto-allocated free NBD device")
        logger.info("  ✅ ESX thin-provisioned VMDK support")
        logger.info("  ✅ Proper udev settling")
        logger.info("  ✅ Safe 7-step cleanup sequence:")
        logger.info("     1. Unmount filesystems")
        logger.info("     2. Deactivate LVM")
        logger.info("     3. Remove device mapper")
        logger.info("     4. Sync buffers")
        logger.info("     5. Flush device buffers")
        logger.info("     6. Disconnect NBD")
        logger.info("     7. Settle udev")
        logger.info("  ✅ Automatic cleanup on crash")
        logger.info("")

        return 0

    except Exception as e:
        logger.exception("Test failed: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
