#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Example: Azure VM migration using hyper2kvm library.

This example demonstrates:
- Connecting to Azure
- Downloading VM disks
- Converting VHD to qcow2
- Full orchestration workflow

Usage:
    export AZURE_SUBSCRIPTION_ID='your-subscription-id'
    export AZURE_TENANT_ID='your-tenant-id'
    export AZURE_CLIENT_ID='your-client-id'
    export AZURE_CLIENT_SECRET='your-client-secret'

    python library_azure_migration.py my-resource-group my-vm
"""

import logging
import os
import sys

from hyper2kvm import AzureConfig, AzureSourceProvider, Orchestrator

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def migrate_from_azure(resource_group: str, vm_name: str, output_dir: str = "/var/lib/libvirt/images"):
    """
    Migrate a VM from Azure to KVM.

    Args:
        resource_group: Azure resource group name
        vm_name: VM to migrate
        output_dir: Output directory for qcow2
    """

    # Get Azure credentials from environment
    subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID")
    tenant_id = os.environ.get("AZURE_TENANT_ID")
    client_id = os.environ.get("AZURE_CLIENT_ID")
    client_secret = os.environ.get("AZURE_CLIENT_SECRET")

    if not all([subscription_id, tenant_id, client_id, client_secret]):
        raise ValueError(
            "Required Azure credentials not found in environment:\n"
            "  AZURE_SUBSCRIPTION_ID\n"
            "  AZURE_TENANT_ID\n"
            "  AZURE_CLIENT_ID\n"
            "  AZURE_CLIENT_SECRET"
        )

    logger.info(f"Connecting to Azure subscription: {subscription_id}")

    # Configure Azure source
    config = AzureConfig(
        subscription_id=subscription_id,
        resource_group=resource_group,
        vm_name=vm_name,
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
    )

    # Initialize provider
    provider = AzureSourceProvider(config)

    # Download VM disks
    logger.info(f"Downloading VM: {vm_name}")
    try:
        result = provider.download_vm(output_dir=output_dir)

        logger.info("Download complete!")
        logger.info(f"  VM name: {result.vm_name}")
        logger.info(f"  Disks:   {len(result.disks)}")
        logger.info(f"  Path:    {result.output_dir}")

        return result

    except Exception as e:
        logger.error(f"Download failed: {e}")
        raise


def full_orchestration_example(resource_group: str, vm_name: str):
    """
    Full migration using Orchestrator.

    The Orchestrator handles:
    - VM download from Azure
    - VHD to qcow2 conversion
    - Guest OS detection
    - Applying fixes
    - Boot testing
    """

    # Get Azure credentials
    subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID")
    tenant_id = os.environ.get("AZURE_TENANT_ID")
    client_id = os.environ.get("AZURE_CLIENT_ID")
    client_secret = os.environ.get("AZURE_CLIENT_SECRET")

    if not all([subscription_id, tenant_id, client_id, client_secret]):
        raise ValueError("Required Azure credentials not found in environment")

    logger.info("Starting full orchestration workflow")

    # Configure Azure
    config = AzureConfig(
        subscription_id=subscription_id,
        resource_group=resource_group,
        vm_name=vm_name,
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
    )

    # Initialize provider
    provider = AzureSourceProvider(config)

    # Run full migration
    orchestrator = Orchestrator(source_provider=provider)
    result = orchestrator.run(
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
        print(f"Usage: {sys.argv[0]} <resource-group> <vm-name> [mode]")
        print()
        print("Modes:")
        print("  download - Download VM only (default)")
        print("  full     - Full migration with fixes and testing")
        print()
        print("Environment variables required:")
        print("  AZURE_SUBSCRIPTION_ID")
        print("  AZURE_TENANT_ID")
        print("  AZURE_CLIENT_ID")
        print("  AZURE_CLIENT_SECRET")
        print()
        print("Example:")
        print("  export AZURE_SUBSCRIPTION_ID='...'")
        print("  export AZURE_TENANT_ID='...'")
        print("  export AZURE_CLIENT_ID='...'")
        print("  export AZURE_CLIENT_SECRET='...'")
        print(f"  {sys.argv[0]} my-rg ubuntu-vm-01 download")
        sys.exit(1)

    resource_group = sys.argv[1]
    vm_name = sys.argv[2]
    mode = sys.argv[3] if len(sys.argv) > 3 else "download"

    try:
        if mode == "full":
            full_orchestration_example(resource_group, vm_name)
        else:
            migrate_from_azure(resource_group, vm_name)

        logger.info("✓ Success!")
        sys.exit(0)

    except Exception as e:
        logger.error(f"✗ Failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
