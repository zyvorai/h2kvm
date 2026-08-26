#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Example: vSphere VM migration using h2kvm library.

This example demonstrates:
- Connecting to vCenter/ESXi (powered by hypersdk - VMware's modern Python SDK)
- Listing available VMs
- Exporting a VM to local disk
- Full orchestration workflow

The vCenter integration leverages hypersdk for robust, type-safe VMware API access,
providing enterprise-grade connectivity to vSphere infrastructure.

Usage:
    export VCENTER_PASSWORD='your-password'
    python library_vsphere_migration.py vcenter.example.com vm-name
"""

import logging
import os
import sys

from h2kvm import Orchestrator, VMwareClient

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def migrate_from_vsphere(
    vcenter_host: str,
    vm_name: str,
    user: str = "administrator@vsphere.local",
    datacenter: str = None,
    output_dir: str = "/var/lib/libvirt/images",
):
    """
    Migrate a VM from vSphere to KVM.

    Args:
        vcenter_host: vCenter or ESXi hostname
        vm_name: VM to migrate
        user: vCenter username
        datacenter: Datacenter name (optional)
        output_dir: Output directory for qcow2
    """

    # Get password from environment
    password = os.environ.get("VCENTER_PASSWORD")
    if not password:
        raise ValueError("VCENTER_PASSWORD environment variable not set")

    logger.info(f"🔌 Connecting to vCenter: {vcenter_host}")
    logger.info("   Using hypersdk for enterprise-grade VMware API integration")

    # Connect to vSphere (powered by hypersdk)
    client = VMwareClient(
        host=vcenter_host,
        user=user,
        password=password,
        datacenter=datacenter,
        insecure=True,  # Set False to verify SSL certificate
    )

    # List available VMs (optional)
    logger.info("Listing available VMs...")
    try:
        vms = client.list_vms()
        logger.info(f"Found {len(vms)} VMs:")
        for vm in vms[:10]:  # Show first 10
            logger.info(f"  - {vm}")
        if len(vms) > 10:
            logger.info(f"  ... and {len(vms) - 10} more")
    except Exception as e:
        logger.warning(f"Could not list VMs: {e}")

    # Export VM
    logger.info(f"Exporting VM: {vm_name}")
    try:
        result = client.export_vm(
            vm_name=vm_name,
            output_dir=output_dir,
            transport="vddk",  # or 'ssh'
            vddk_libdir="/opt/vmware-vix-disklib-distrib",  # if using VDDK
        )

        logger.info("Export complete!")
        logger.info(f"  VM name: {result.vm_name}")
        logger.info(f"  Disks:   {len(result.disks)}")
        logger.info(f"  Path:    {result.output_dir}")

        return result

    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise


def full_orchestration_example(vcenter_host: str, vm_name: str):
    """
    Full migration using Orchestrator.

    The Orchestrator handles:
    - VM export
    - Disk conversion
    - Guest OS detection
    - Applying fixes
    - Boot testing
    """

    password = os.environ.get("VCENTER_PASSWORD")
    if not password:
        raise ValueError("VCENTER_PASSWORD environment variable not set")

    logger.info("Starting full orchestration workflow")

    # Connect to vSphere
    client = VMwareClient(
        host=vcenter_host, user="administrator@vsphere.local", password=password, insecure=True
    )

    # Run full migration
    orchestrator = Orchestrator(vmware_client=client)
    result = orchestrator.run(
        vm_name=vm_name,
        output_dir="/var/lib/libvirt/images",
        compress=True,
        apply_fixes=True,  # Apply guest OS fixes
        test_boot=True,  # Test boot after migration
    )

    logger.info("Migration complete!")
    logger.info(f"  Source VM: {result.source_vm}")
    logger.info(f"  Output:    {result.output_path}")
    logger.info(f"  Fixes:     {len(result.fixes_applied)}")
    logger.info(f"  Boot test: {'✓ Passed' if result.boot_test_passed else '✗ Failed'}")

    return result


def main():
    """Main entry point."""

    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <vcenter-host> <vm-name> [mode]")
        print()
        print("Modes:")
        print("  export  - Export VM only (default)")
        print("  full    - Full migration with fixes and testing")
        print()
        print("Example:")
        print("  export VCENTER_PASSWORD='password'")
        print(f"  {sys.argv[0]} vcenter.example.com rhel9-prod export")
        sys.exit(1)

    vcenter_host = sys.argv[1]
    vm_name = sys.argv[2]
    mode = sys.argv[3] if len(sys.argv) > 3 else "export"

    try:
        if mode == "full":
            full_orchestration_example(vcenter_host, vm_name)
        else:
            migrate_from_vsphere(vcenter_host, vm_name)

        logger.info("✓ Success!")
        sys.exit(0)

    except Exception as e:
        logger.error(f"✗ Failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
