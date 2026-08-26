#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Example: Partition Management

This script demonstrates VMCraft's partition management APIs including:
1. Creating partition tables (GPT, MBR)
2. Adding and deleting partitions
3. Setting partition names and type GUIDs
4. Querying partition information
5. Partition disk initialization

Workflow:
1. Create new partition table
2. Add partitions with specific layouts
3. Set partition metadata (names, type GUIDs)
4. Query and verify partition configuration
5. Clean up and demonstrate part_disk utility
"""

import sys
import logging
from pathlib import Path

from hyper2kvm.vmcraft.main import VMCraft


def setup_logging():
    """Configure logging."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    return logging.getLogger(__name__)


def demonstrate_partition_management(disk_image_path: str):
    """
    Demonstrate partition management capabilities.

    Args:
        disk_image_path: Path to disk image (will be modified!)
    """
    logger = setup_logging()
    logger.info(f"Demonstrating partition management for: {disk_image_path}")
    logger.info("")
    logger.info("⚠️  WARNING: This will MODIFY the disk image!")
    logger.info("    Only use with test/disposable images")
    logger.info("")

    with VMCraft(disk_image_path) as g:
        logger.info("VMCraft launched successfully")

        # Get NBD device path
        device = g.get_nbd_device()
        logger.info(f"Working with device: {device}")

        # =====================================================================
        # Step 1: Check Current Partition Table
        # =====================================================================
        logger.info("Step 1: Checking current partition table...")

        parttype = g.part_get_parttype(device)
        logger.info(f"  Current partition table type: {parttype}")

        partitions = g.list_partitions()
        logger.info(f"  Current partitions: {len(partitions)}")
        for part in partitions:
            logger.info(f"    - {part}")

        # =====================================================================
        # Step 2: Create New GPT Partition Table
        # =====================================================================
        logger.info("Step 2: Creating new GPT partition table...")

        # Initialize empty partition table
        g.part_init(device, "gpt")
        logger.info("  ✓ GPT partition table initialized")

        # Verify
        parttype = g.part_get_parttype(device)
        logger.info(f"  Partition table type: {parttype}")

        partitions = g.list_partitions()
        logger.info(f"  Partitions after init: {len(partitions)}")

        # =====================================================================
        # Step 3: Add Partitions
        # =====================================================================
        logger.info("Step 3: Adding partitions...")

        # Add EFI System Partition (first 512MB)
        logger.info("  Creating EFI System Partition (512MB)...")
        # Sectors: 2048 (1MB) to 1050623 (512MB)
        g.part_add(device, "primary", 2048, 1050623)
        logger.info("    ✓ EFI partition added")

        # Add root partition (rest of disk)
        logger.info("  Creating root partition (remaining space)...")
        # Start after EFI, use -1 for end of disk
        g.part_add(device, "primary", 1050624, -1)
        logger.info("    ✓ Root partition added")

        # Verify partitions were created
        partitions = g.list_partitions()
        logger.info(f"  Total partitions: {len(partitions)}")
        for i, part in enumerate(partitions, 1):
            logger.info(f"    {i}. {part}")

        # =====================================================================
        # Step 4: Set Partition Names (GPT)
        # =====================================================================
        logger.info("Step 4: Setting partition names...")

        if len(partitions) >= 2:
            # Name the EFI partition
            g.part_set_name(device, 1, "EFI System")
            logger.info("  ✓ Set partition 1 name: 'EFI System'")

            # Name the root partition
            g.part_set_name(device, 2, "Linux Root")
            logger.info("  ✓ Set partition 2 name: 'Linux Root'")

        # =====================================================================
        # Step 5: Set GPT Type GUIDs
        # =====================================================================
        logger.info("Step 5: Setting GPT partition type GUIDs...")

        if len(partitions) >= 2:
            # Set EFI System Partition type
            efi_guid = "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"
            g.part_set_gpt_type(device, 1, efi_guid)
            logger.info(f"  ✓ Set partition 1 type: EFI System ({efi_guid})")

            # Set Linux filesystem type
            linux_guid = "0FC63DAF-8483-4772-8E79-3D69D8477DE4"
            g.part_set_gpt_type(device, 2, linux_guid)
            logger.info(f"  ✓ Set partition 2 type: Linux filesystem ({linux_guid})")

        # =====================================================================
        # Step 6: Delete a Partition
        # =====================================================================
        logger.info("Step 6: Demonstrating partition deletion...")

        if len(partitions) >= 2:
            # Delete the second partition
            logger.info("  Deleting partition 2...")
            g.part_del(device, 2)
            logger.info("    ✓ Partition 2 deleted")

            # Verify deletion
            partitions = g.list_partitions()
            logger.info(f"  Remaining partitions: {len(partitions)}")

        # =====================================================================
        # Step 7: Demonstrate part_disk Utility
        # =====================================================================
        logger.info("Step 7: Demonstrating part_disk (quick disk setup)...")

        # part_disk creates a partition table and single partition covering entire disk
        logger.info("  Creating GPT table with single partition...")
        g.part_disk(device, "gpt")
        logger.info("    ✓ Partition table and full-disk partition created")

        # Verify
        parttype = g.part_get_parttype(device)
        partitions = g.list_partitions()
        logger.info(f"  Partition table type: {parttype}")
        logger.info(f"  Partitions: {len(partitions)}")

        # =====================================================================
        # Step 8: Create MBR/MSDOS Partition Table
        # =====================================================================
        logger.info("Step 8: Demonstrating MBR partition table...")

        # Initialize MBR/MSDOS partition table
        g.part_init(device, "msdos")
        logger.info("  ✓ MBR partition table initialized")

        parttype = g.part_get_parttype(device)
        logger.info(f"  Partition table type: {parttype}")

        # Add primary partition
        g.part_add(device, "primary", 2048, -1)
        logger.info("  ✓ Primary partition added")

        partitions = g.list_partitions()
        logger.info(f"  Partitions: {len(partitions)}")

        # =====================================================================
        # Summary
        # =====================================================================
        logger.info("=" * 70)
        logger.info("PARTITION MANAGEMENT SUMMARY")
        logger.info("=" * 70)
        logger.info("")
        logger.info("Partition Table Operations:")
        logger.info("  - part_init(device, 'gpt'|'msdos')    Create empty partition table")
        logger.info("  - part_get_parttype(device)           Query partition table type")
        logger.info("  - part_disk(device, 'gpt'|'msdos')    Quick full-disk partition")
        logger.info("")
        logger.info("Partition Operations:")
        logger.info("  - part_add(device, type, start, end)  Add partition (sectors)")
        logger.info("  - part_del(device, partnum)           Delete partition")
        logger.info("  - list_partitions()                   List all partitions")
        logger.info("")
        logger.info("GPT Metadata Operations:")
        logger.info("  - part_set_name(device, num, name)    Set partition name")
        logger.info("  - part_set_gpt_type(device, num, guid) Set type GUID")
        logger.info("")
        logger.info("Common GPT Type GUIDs:")
        logger.info("  - EFI System:        C12A7328-F81F-11D2-BA4B-00A0C93EC93B")
        logger.info("  - Linux filesystem:  0FC63DAF-8483-4772-8E79-3D69D8477DE4")
        logger.info("  - Linux swap:        0657FD6D-A4AB-43C4-84E5-0933C84B4F4F")
        logger.info("  - Linux LVM:         E6D6D379-F507-44C2-A23C-238F2A3DF928")
        logger.info("")
        logger.info("Use Cases:")
        logger.info("  1. VM customization - Repartition for specific workloads")
        logger.info("  2. Disk expansion - Add partitions to utilize new space")
        logger.info("  3. Multi-boot setup - Create partitions for multiple OSes")
        logger.info("  4. Disk conversion - Convert MBR to GPT or vice versa")

    logger.info("")
    logger.info("Partition management demonstration completed!")


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: python 02_partition_management.py <disk_image_path>")
        print("")
        print("⚠️  WARNING: This script will MODIFY the disk image!")
        print("   Only use with test/disposable images")
        print("")
        print("Example:")
        print("  # Create test image first")
        print("  qemu-img create -f qcow2 test-partition.qcow2 1G")
        print("  python 02_partition_management.py test-partition.qcow2")
        print("")
        print("This script demonstrates:")
        print("  - Creating GPT and MBR partition tables")
        print("  - Adding and deleting partitions")
        print("  - Setting partition names and type GUIDs")
        print("  - Querying partition information")
        sys.exit(1)

    disk_image_path = sys.argv[1]

    if not Path(disk_image_path).exists():
        print(f"Error: Disk image not found: {disk_image_path}")
        print("")
        print("Create a test image with:")
        print(f"  qemu-img create -f qcow2 {disk_image_path} 1G")
        sys.exit(1)

    # Confirm modification
    response = input(f"This will MODIFY {disk_image_path}. Continue? (yes/no): ")
    if response.lower() != "yes":
        print("Aborted.")
        sys.exit(0)

    demonstrate_partition_management(disk_image_path)


if __name__ == "__main__":
    main()
