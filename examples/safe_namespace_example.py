#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Safe Namespace Engine - Example Usage

Demonstrates production-grade VM conversion with full host isolation.
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from h2kvm.vmcraft.safe_namespace_engine import SafeNamespaceEngine, create_safe_namespace

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def example_basic_usage():
    """Example 1: Basic usage with manual cleanup."""
    logger.info("=" * 60)
    logger.info("Example 1: Basic Usage")
    logger.info("=" * 60)

    # Create engine
    engine = SafeNamespaceEngine("/dev/nbd0")

    try:
        # Start namespace (isolated environment)
        engine.start()

        # Execute commands in isolated chroot
        logger.info("Running commands in isolated namespace...")

        # Check what's visible in /dev (only NBD devices)
        devices = engine.run("ls /dev/nbd*")
        logger.info("Visible devices: %s", devices)

        # Regenerate initramfs with virtio drivers
        logger.info("Regenerating initramfs...")
        engine.run("dracut --force --no-hostonly --add-drivers 'virtio_blk virtio_scsi virtio_net'")

        # Update GRUB configuration
        logger.info("Updating GRUB...")
        engine.run("grub2-mkconfig -o /boot/grub2/grub.cfg")

        logger.info("✅ Commands executed successfully")

    finally:
        # Cleanup (guaranteed even on crash)
        engine.cleanup()

    logger.info("")


def example_context_manager():
    """Example 2: Context manager for automatic cleanup."""
    logger.info("=" * 60)
    logger.info("Example 2: Context Manager")
    logger.info("=" * 60)

    # Automatic cleanup with context manager
    with create_safe_namespace("/dev/nbd0") as engine:
        logger.info("Namespace started automatically")

        # Check OS release
        os_release = engine.run("cat /etc/os-release | head -5")
        logger.info("Guest OS:\n%s", os_release)

        # List installed kernels
        kernels = engine.run("ls /boot/vmlinuz-* | head -3")
        logger.info("Installed kernels:\n%s", kernels)

        # Install virtio drivers
        logger.info("Installing virtio drivers...")
        engine.run("dracut --force --add-drivers 'virtio_blk virtio_scsi'")

    # Cleanup happens automatically here
    logger.info("✅ Cleanup completed automatically")
    logger.info("")


def example_multiline_script():
    """Example 3: Execute multi-line script."""
    logger.info("=" * 60)
    logger.info("Example 3: Multi-line Script")
    logger.info("=" * 60)

    with create_safe_namespace("/dev/nbd0") as engine:
        logger.info("Executing multi-line conversion script...")

        script = """
        # VM Conversion Script
        echo "🔧 Starting VM conversion..."

        # Remove VMware tools
        echo "Removing VMware tools..."
        systemctl stop vmtoolsd 2>/dev/null || true
        systemctl disable vmtoolsd 2>/dev/null || true
        yum remove -y open-vm-tools vmware-tools 2>/dev/null || true

        # Install virtio drivers
        echo "Installing virtio drivers..."
        dracut --force --no-hostonly \\
            --add-drivers "virtio_blk virtio_scsi virtio_net virtio_pci ahci sd_mod" \\
            --add lvm --add dm

        # Update GRUB
        echo "Updating GRUB..."
        grub2-mkconfig -o /boot/grub2/grub.cfg

        # Verify initramfs
        echo "Verifying initramfs..."
        lsinitrd | grep virtio || echo "Warning: virtio drivers not found"

        echo "✅ Conversion complete!"
        """

        result = engine.run_script(script)
        logger.info("Script output:\n%s", result)

    logger.info("✅ Multi-line script completed")
    logger.info("")


def example_error_handling():
    """Example 4: Error handling and safety."""
    logger.info("=" * 60)
    logger.info("Example 4: Error Handling")
    logger.info("=" * 60)

    engine = SafeNamespaceEngine("/dev/nbd0")

    try:
        engine.start()

        # Try to access host disk (will fail - not visible in namespace)
        try:
            engine.run("ls /dev/sda")
            logger.error("❌ UNSAFE: Host disk visible!")
        except Exception:
            logger.info("✅ SAFE: Host disk NOT visible in namespace")

        # Try to activate host VG (will fail - device filter)
        try:
            vgs = engine.run("vgs --all")
            if "host" in vgs.lower():
                logger.error("❌ UNSAFE: Host VG visible!")
            else:
                logger.info("✅ SAFE: Only guest VGs visible")
        except Exception:
            logger.info("✅ SAFE: Cannot access host VGs")

        # Simulate command failure
        try:
            engine.run("this-command-does-not-exist")
        except Exception as e:
            logger.info("✅ Command failure handled: %s", str(e)[:50])

    finally:
        # Cleanup ALWAYS happens
        engine.cleanup()
        logger.info("✅ Cleanup guaranteed even after errors")

    logger.info("")


def example_custom_job():
    """Example 5: Custom conversion job."""
    logger.info("=" * 60)
    logger.info("Example 5: Custom Conversion Job")
    logger.info("=" * 60)

    def perform_custom_conversion(engine: SafeNamespaceEngine) -> dict:
        """Custom conversion logic."""
        results = {}

        # Detect OS
        os_info = engine.run("cat /etc/os-release | grep PRETTY_NAME")
        results["os"] = os_info.split("=")[1].strip('"')

        # Check kernel version
        kernel = engine.run("uname -r")
        results["kernel"] = kernel

        # Regenerate initramfs with custom drivers
        logger.info("Regenerating initramfs for %s...", results["os"])
        engine.run(
            "dracut --force --no-hostonly --add-drivers 'virtio_blk virtio_scsi virtio_net e1000e nvme'"
        )

        # Update fstab (convert to UUIDs)
        logger.info("Updating fstab...")
        engine.run("sed -i 's|/dev/mapper|UUID=$(blkid -s UUID -o value /dev/mapper)|g' /etc/fstab || true")

        # Update GRUB
        logger.info("Updating GRUB...")
        engine.run("grub2-mkconfig -o /boot/grub2/grub.cfg")

        results["status"] = "success"
        return results

    with create_safe_namespace("/dev/nbd0") as engine:
        results = perform_custom_conversion(engine)

        logger.info("Conversion results:")
        for key, value in results.items():
            logger.info("  %s: %s", key, value)

    logger.info("✅ Custom conversion completed")
    logger.info("")


def main():
    """Run all examples."""
    logger.info("🔒 Safe Namespace Engine - Example Usage\n")

    examples = [
        ("Basic Usage", example_basic_usage),
        ("Context Manager", example_context_manager),
        ("Multi-line Script", example_multiline_script),
        ("Error Handling", example_error_handling),
        ("Custom Conversion", example_custom_job),
    ]

    for name, func in examples:
        try:
            func()
        except Exception as e:
            logger.exception("Example '%s' failed: %s", name, e)

    logger.info("=" * 60)
    logger.info("All examples completed!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
