#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Example: Configuration Management with Augeas

This script demonstrates VMCraft's Augeas integration for consistent
configuration file editing including:
1. Modifying /etc/fstab entries
2. Editing network configuration
3. Modifying systemd unit files
4. Managing SSH configuration
5. Pattern matching and bulk operations

Workflow:
1. Initialize Augeas with guest filesystem
2. Modify fstab mount options
3. Update network configuration
4. Edit SSH daemon config
5. Save changes to disk

Augeas provides a consistent API for editing various configuration file
formats without manual parsing.
"""

import sys
import logging
from pathlib import Path

from hyper2kvm.vmcraft.main import VMCraft


def setup_logging():
    """Configure logging."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    return logging.getLogger(__name__)


def demonstrate_augeas_config_management(vm_image_path: str):
    """
    Demonstrate Augeas configuration management.

    Args:
        vm_image_path: Path to VM disk image
    """
    logger = setup_logging()
    logger.info(f"Demonstrating Augeas config management for: {vm_image_path}")

    try:
        import augeas as aug_module

        logger.info("Augeas library is available")
    except ImportError:
        logger.error("Augeas library not available!")
        logger.error("Install with: pip install python-augeas")
        logger.error("             sudo dnf install augeas augeas-libs")
        return

    with VMCraft(vm_image_path) as g:
        logger.info("VMCraft launched successfully")

        # Mount root filesystem
        partitions = g.list_partitions()
        if not partitions:
            logger.error("No partitions found")
            return

        # Try to mount root partition
        mounted = False
        for partition in partitions:
            try:
                g.mount(partition, "/", readonly=False)
                logger.info(f"Mounted {partition} as root")
                mounted = True
                break
            except Exception:
                continue

        if not mounted:
            logger.error("Failed to mount root filesystem")
            return

        # =====================================================================
        # Step 1: Initialize Augeas
        # =====================================================================
        logger.info("Step 1: Initializing Augeas...")

        try:
            g.aug_init()
            logger.info("  ✓ Augeas initialized with guest filesystem")
        except Exception as e:
            logger.error(f"  ✗ Failed to initialize Augeas: {e}")
            return

        # =====================================================================
        # Step 2: Modify /etc/fstab
        # =====================================================================
        logger.info("Step 2: Modifying /etc/fstab...")

        # List all fstab entries
        fstab_entries = g.aug_match("/files/etc/fstab/*")
        logger.info(f"  Found {len(fstab_entries)} fstab entries")

        if fstab_entries:
            # Show first entry
            first_entry = fstab_entries[0]
            spec = g.aug_get(f"{first_entry}/spec")
            file = g.aug_get(f"{first_entry}/file")
            vfstype = g.aug_get(f"{first_entry}/vfstype")
            logger.info(f"  First entry: {spec} -> {file} ({vfstype})")

            # Modify dump value for all entries
            logger.info("  Setting dump=0 for all entries...")
            for entry in fstab_entries:
                g.aug_set(f"{entry}/dump", "0")
            logger.info("    ✓ Modified all dump values")

            # Modify pass value for root filesystem
            logger.info("  Setting pass=1 for root filesystem...")
            for entry in fstab_entries:
                mountpoint = g.aug_get(f"{entry}/file")
                if mountpoint == "/":
                    g.aug_set(f"{entry}/passno", "1")
                    logger.info("    ✓ Set pass=1 for /")
                    break

        # =====================================================================
        # Step 3: Edit SSH Daemon Configuration
        # =====================================================================
        logger.info("Step 3: Modifying SSH daemon configuration...")

        # Check if sshd_config exists
        sshd_entries = g.aug_match("/files/etc/ssh/sshd_config/*")

        if sshd_entries:
            logger.info(f"  Found {len(sshd_entries)} sshd_config entries")

            # Disable root login
            logger.info("  Disabling root login...")
            g.aug_set("/files/etc/ssh/sshd_config/PermitRootLogin", "no")
            logger.info("    ✓ Set PermitRootLogin=no")

            # Disable password authentication (force key-based)
            logger.info("  Disabling password authentication...")
            g.aug_set("/files/etc/ssh/sshd_config/PasswordAuthentication", "no")
            logger.info("    ✓ Set PasswordAuthentication=no")

            # Enable public key authentication
            logger.info("  Enabling public key authentication...")
            g.aug_set("/files/etc/ssh/sshd_config/PubkeyAuthentication", "yes")
            logger.info("    ✓ Set PubkeyAuthentication=yes")

        else:
            logger.info("  sshd_config not found (skipping)")

        # =====================================================================
        # Step 4: Pattern Matching and Bulk Operations
        # =====================================================================
        logger.info("Step 4: Demonstrating pattern matching...")

        # Find all commented entries
        logger.info("  Searching for configuration patterns...")

        # Match all services in /etc/services
        services = g.aug_match("/files/etc/services/service-name")
        if services:
            logger.info(f"  Found {len(services)} service definitions in /etc/services")
            # Show first few
            for service_path in services[:5]:
                name = g.aug_get(service_path)
                logger.info(f"    - {name}")

        # =====================================================================
        # Step 5: Define Variables for Complex Queries
        # =====================================================================
        logger.info("Step 5: Using Augeas variables...")

        # Define variable for root filesystem entry
        g.aug_defvar("rootfs", "/files/etc/fstab/*[file = '/']")
        logger.info("  ✓ Defined variable 'rootfs' for root filesystem entry")

        # Get root filesystem spec using variable
        root_spec = g.aug_get("$rootfs/spec")
        if root_spec:
            logger.info(f"  Root filesystem device: {root_spec}")

        # =====================================================================
        # Step 6: Insert New Configuration Entry
        # =====================================================================
        logger.info("Step 6: Inserting new configuration entry...")

        if fstab_entries:
            # Insert a new fstab entry
            last_entry = fstab_entries[-1]
            logger.info("  Inserting new fstab entry for /data...")

            # Insert after last entry
            g.aug_insert(last_entry, "01", before=False)

            # Set values for new entry
            new_entry = f"{last_entry}/../01"
            g.aug_set(f"{new_entry}/spec", "/dev/sdb1")
            g.aug_set(f"{new_entry}/file", "/data")
            g.aug_set(f"{new_entry}/vfstype", "ext4")
            g.aug_set(f"{new_entry}/opt", "defaults")
            g.aug_set(f"{new_entry}/dump", "0")
            g.aug_set(f"{new_entry}/passno", "2")

            logger.info("    ✓ New fstab entry created")

        # =====================================================================
        # Step 7: Remove Configuration Entry
        # =====================================================================
        logger.info("Step 7: Removing configuration entry...")

        # Remove the entry we just added
        if fstab_entries:
            removed_count = g.aug_rm(f"{last_entry}/../01")
            if removed_count > 0:
                logger.info(f"    ✓ Removed {removed_count} entry")

        # =====================================================================
        # Step 8: Save Changes
        # =====================================================================
        logger.info("Step 8: Saving changes to disk...")

        try:
            g.aug_save()
            logger.info("  ✓ All changes saved successfully")
        except Exception as e:
            logger.error(f"  ✗ Failed to save changes: {e}")

        # Close Augeas
        g.aug_close()
        logger.info("  Augeas closed")

        # =====================================================================
        # Summary
        # =====================================================================
        logger.info("=" * 70)
        logger.info("AUGEAS CONFIGURATION MANAGEMENT SUMMARY")
        logger.info("=" * 70)
        logger.info("")
        logger.info("Initialization:")
        logger.info("  - aug_init()                          Initialize Augeas")
        logger.info("  - aug_close()                         Close Augeas")
        logger.info("")
        logger.info("Read Operations:")
        logger.info("  - aug_get(path)                       Get value at path")
        logger.info("  - aug_match(pattern)                  Find paths matching pattern")
        logger.info("")
        logger.info("Write Operations:")
        logger.info("  - aug_set(path, value)                Set value at path")
        logger.info("  - aug_insert(path, label, before)     Insert new node")
        logger.info("  - aug_rm(path)                        Remove node(s)")
        logger.info("  - aug_save()                          Save changes to disk")
        logger.info("")
        logger.info("Advanced Features:")
        logger.info("  - aug_defvar(name, expr)              Define variable")
        logger.info("  - aug_defnode(name, expr, value)      Define node variable")
        logger.info("")
        logger.info("Supported Configuration Files:")
        logger.info("  - /etc/fstab                          Filesystem mounts")
        logger.info("  - /etc/ssh/sshd_config                SSH daemon config")
        logger.info("  - /etc/hosts                          Host entries")
        logger.info("  - /etc/resolv.conf                    DNS configuration")
        logger.info("  - /etc/systemd/system/*.service       Systemd units")
        logger.info("  - /etc/sysconfig/network-scripts/*    Network configs")
        logger.info("  - And many more...")
        logger.info("")
        logger.info("Path Examples:")
        logger.info("  - /files/etc/fstab/*                  All fstab entries")
        logger.info("  - /files/etc/fstab/*[file='/']        Root filesystem entry")
        logger.info("  - /files/etc/ssh/sshd_config/*        All sshd options")
        logger.info("")
        logger.info("Use Cases:")
        logger.info("  1. Consistent config editing across distributions")
        logger.info("  2. Automated security hardening (SSH, firewall)")
        logger.info("  3. Network reconfiguration during migration")
        logger.info("  4. Bulk configuration updates")
        logger.info("")
        logger.info("Benefits:")
        logger.info("  - No manual parsing of config file formats")
        logger.info("  - Preserves file structure and comments")
        logger.info("  - Atomic saves (all or nothing)")
        logger.info("  - Supports 100+ file formats")

    logger.info("")
    logger.info("Augeas configuration management demonstration completed!")


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: python 04_config_management_augeas.py <vm_image_path>")
        print("")
        print("Requirements:")
        print("  - python-augeas library")
        print("  - augeas system packages")
        print("")
        print("Install with:")
        print("  pip install python-augeas")
        print("  sudo dnf install augeas augeas-libs")
        print("")
        print("Example:")
        print("  python 04_config_management_augeas.py /path/to/rhel9-vm.qcow2")
        print("")
        print("This script demonstrates:")
        print("  - Modifying /etc/fstab entries")
        print("  - Editing SSH daemon configuration")
        print("  - Pattern matching for bulk operations")
        print("  - Inserting and removing config entries")
        print("  - Using Augeas variables for complex queries")
        sys.exit(1)

    vm_image_path = sys.argv[1]

    if not Path(vm_image_path).exists():
        print(f"Error: VM image not found: {vm_image_path}")
        sys.exit(1)

    demonstrate_augeas_config_management(vm_image_path)


if __name__ == "__main__":
    main()
