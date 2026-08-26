#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Example: VMware to KVM Service Migration

This script demonstrates how to migrate services when converting a VMware VM
to KVM using VMCraft's systemd integration.

Workflow:
1. Disable and mask VMware-specific services
2. Enable KVM/QEMU guest agent
3. Verify service states
4. Generate migration report
"""

import sys
import logging
from pathlib import Path

from h2kvm.vmcraft.main import VMCraft


def setup_logging():
    """Configure logging for the migration script."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    return logging.getLogger(__name__)


def migrate_services(vm_image_path: str):
    """
    Migrate services from VMware to KVM.

    Args:
        vm_image_path: Path to the VM disk image
    """
    logger = setup_logging()
    logger.info(f"Starting service migration for: {vm_image_path}")

    # Validate image exists
    if not Path(vm_image_path).exists():
        logger.error(f"VM image not found: {vm_image_path}")
        sys.exit(1)

    # Launch VMCraft
    with VMCraft(vm_image_path) as g:
        logger.info("VMCraft launched successfully")

        # Check if systemd is available
        if not g.systemd_is_available():
            logger.warning("Systemd not detected in VM - skipping service migration")
            return

        logger.info("Systemd detected - proceeding with service migration")

        # =====================================================================
        # Step 1: Disable VMware Services
        # =====================================================================
        logger.info("Step 1: Disabling VMware services...")

        vmware_services = [
            "vmtoolsd.service",
            "vmware-tools.service",
            "open-vm-tools.service",
            "vmware-tools-thinprint.service",
        ]

        # Disable all VMware services
        disable_results = g.systemd_services_disable_multiple(vmware_services)

        disabled_count = sum(1 for ok in disable_results.values() if ok)
        logger.info(f"Disabled {disabled_count}/{len(vmware_services)} VMware services")

        # Mask VMware services to prevent re-activation
        mask_results = g.systemd_services_mask(vmware_services)

        masked_count = sum(1 for ok in mask_results.values() if ok)
        logger.info(f"Masked {masked_count}/{len(vmware_services)} VMware services")

        # =====================================================================
        # Step 2: Enable KVM/QEMU Services
        # =====================================================================
        logger.info("Step 2: Enabling KVM guest services...")

        kvm_services = ["qemu-guest-agent.service"]

        for service in kvm_services:
            result = g.systemd_service_enable(service)
            if result["ok"]:
                logger.info(f"✓ Enabled {service}")
            else:
                logger.warning(f"✗ Failed to enable {service}: {result.get('error')}")

        # =====================================================================
        # Step 3: Verify Service States
        # =====================================================================
        logger.info("Step 3: Verifying service states...")

        # Check that VMware services are disabled
        for service in vmware_services:
            enabled = g.systemd_is_service_enabled(service)
            status = "ENABLED" if enabled else "disabled"
            logger.info(f"  {service}: {status}")

        # Check that KVM services are enabled
        for service in kvm_services:
            enabled = g.systemd_is_service_enabled(service)
            status = "ENABLED" if enabled else "disabled"
            logger.info(f"  {service}: {status}")

        # =====================================================================
        # Step 4: Generate Migration Report
        # =====================================================================
        logger.info("Step 4: Generating migration report...")

        # Get all active services
        active_services = g.systemd_list_services(state="active")
        logger.info(f"Total active services: {len(active_services)}")

        # Check for failed services
        failed_services = g.systemd_list_failed_services()
        if failed_services:
            logger.warning(f"Failed services detected: {len(failed_services)}")
            for service in failed_services:
                logger.warning(f"  - {service}")
        else:
            logger.info("No failed services detected")

        # Reload systemd to pick up changes
        reload_result = g.systemd_daemon_reload()
        if reload_result["ok"]:
            logger.info("✓ Systemd daemon reloaded successfully")

    logger.info("=" * 70)
    logger.info("Service migration completed successfully!")
    logger.info("=" * 70)
    logger.info("")
    logger.info("Next steps:")
    logger.info("1. Test VM boot in KVM environment")
    logger.info("2. Verify qemu-guest-agent is running")
    logger.info("3. Confirm no VMware services are active")


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: python 01_vmware_to_kvm_services.py <vm_image_path>")
        print("")
        print("Example:")
        print("  python 01_vmware_to_kvm_services.py /path/to/rhel9-vm.qcow2")
        sys.exit(1)

    vm_image_path = sys.argv[1]
    migrate_services(vm_image_path)


if __name__ == "__main__":
    main()
