#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Example: Network Configuration Migration to systemd-networkd

This script demonstrates migrating network configurations from legacy formats
(ifcfg, NetworkManager) to systemd-networkd during VM migration.

Workflow:
1. Detect existing network configuration
2. Migrate ifcfg files to systemd-networkd
3. Create KVM bridge configuration (optional)
4. Enable systemd-networkd
5. Verify configuration files
"""

import sys
import logging
from pathlib import Path

from h2kvm.vmcraft.main import VMCraft


def setup_logging():
    """Configure logging."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    return logging.getLogger(__name__)


def migrate_network_config(vm_image_path: str, create_bridge: bool = False):
    """
    Migrate network configuration to systemd-networkd.

    Args:
        vm_image_path: Path to VM disk image
        create_bridge: Whether to create KVM bridge configuration
    """
    logger = setup_logging()
    logger.info(f"Starting network configuration migration for: {vm_image_path}")

    with VMCraft(vm_image_path) as g:
        logger.info("VMCraft launched successfully")

        # =====================================================================
        # Step 1: Detect Existing Network Configuration
        # =====================================================================
        logger.info("Step 1: Detecting existing network configuration...")

        # List existing network files
        network_files = g.networkd_list_network_files()
        logger.info(f"Found {len(network_files)} existing networkd files")

        # Check for ifcfg files (RHEL/Fedora)
        ifcfg_dir = Path("/etc/sysconfig/network-scripts")
        logger.info(f"Checking for ifcfg files in {ifcfg_dir}...")

        # =====================================================================
        # Step 2: Migrate ifcfg Files to systemd-networkd
        # =====================================================================
        logger.info("Step 2: Migrating ifcfg configurations...")

        # Example interfaces to migrate
        interfaces_to_migrate = ["eth0", "eth1", "ens3"]

        migrated_count = 0
        for interface in interfaces_to_migrate:
            logger.info(f"  Attempting to migrate {interface}...")
            result = g.networkd_migrate_from_ifcfg(interface)

            if result["ok"]:
                logger.info(f"  ✓ Migrated {interface} successfully")
                logger.info(f"    Created: {result.get('networkd_file')}")
                migrated_count += 1
            elif result["error"] == "ifcfg_not_found":
                logger.debug(f"  - No ifcfg file found for {interface}")
            else:
                logger.warning(f"  ✗ Failed to migrate {interface}: {result.get('error')}")

        logger.info(f"Migrated {migrated_count} network interfaces")

        # =====================================================================
        # Step 3: Create KVM Bridge Configuration (Optional)
        # =====================================================================
        if create_bridge:
            logger.info("Step 3: Creating KVM bridge configuration...")

            bridge_result = g.networkd_create_bridge_network(
                bridge_name="br0",
                interfaces=["eth0"],  # Add eth0 to bridge
            )

            if bridge_result["ok"]:
                logger.info(f"✓ Created bridge '{bridge_result['bridge']}'")
                logger.info(f"  Files created: {len(bridge_result['files_created'])}")
                for file_path in bridge_result["files_created"]:
                    logger.info(f"    - {file_path}")
            else:
                logger.error(f"✗ Bridge creation failed: {bridge_result.get('error')}")
        else:
            logger.info("Step 3: Skipping bridge creation (not requested)")

        # =====================================================================
        # Step 4: Enable systemd-networkd
        # =====================================================================
        logger.info("Step 4: Enabling systemd-networkd...")

        enable_result = g.networkd_enable_networkd()
        if enable_result["ok"]:
            logger.info("✓ systemd-networkd enabled successfully")
        else:
            logger.error(f"✗ Failed to enable systemd-networkd: {enable_result.get('error')}")

        # =====================================================================
        # Step 5: Verify Configuration Files
        # =====================================================================
        logger.info("Step 5: Verifying network configuration files...")

        # List all network files after migration
        all_network_files = g.networkd_list_network_files()

        logger.info(f"Total networkd files: {len(all_network_files)}")

        # Group by type
        by_type = {}
        for file_info in all_network_files:
            file_type = file_info.get("type", "unknown")
            by_type.setdefault(file_type, []).append(file_info["name"])

        for file_type, files in by_type.items():
            logger.info(f"  {file_type} files ({len(files)}):")
            for filename in files:
                logger.info(f"    - {filename}")

        # Parse and validate a network file
        if all_network_files:
            sample_file = all_network_files[0]["name"]
            logger.info(f"  Parsing sample file: {sample_file}")

            parsed = g.networkd_parse_network_file(sample_file)
            if parsed["ok"]:
                logger.info(f"  ✓ File is valid")
                for section, values in parsed["sections"].items():
                    logger.info(f"    [{section}]")
                    for key, value in values.items():
                        logger.info(f"      {key}={value}")
            else:
                logger.warning(f"  ✗ Failed to parse: {parsed.get('error')}")

    logger.info("=" * 70)
    logger.info("Network configuration migration completed!")
    logger.info("=" * 70)
    logger.info("")
    logger.info("Next steps:")
    logger.info("1. Boot VM in KVM environment")
    logger.info("2. Verify network connectivity")
    logger.info("3. Check 'systemctl status systemd-networkd'")
    logger.info("4. Review 'networkctl status' output")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python 02_network_config_migration.py <vm_image_path> [--bridge]")
        print("")
        print("Options:")
        print("  --bridge    Create KVM bridge configuration")
        print("")
        print("Example:")
        print("  python 02_network_config_migration.py /path/to/rhel9-vm.qcow2")
        print("  python 02_network_config_migration.py /path/to/rhel9-vm.qcow2 --bridge")
        sys.exit(1)

    vm_image_path = sys.argv[1]
    create_bridge = "--bridge" in sys.argv

    if not Path(vm_image_path).exists():
        print(f"Error: VM image not found: {vm_image_path}")
        sys.exit(1)

    migrate_network_config(vm_image_path, create_bridge)


if __name__ == "__main__":
    main()
