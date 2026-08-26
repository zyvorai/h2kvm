#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Example: LVM Creation and Management

This script demonstrates VMCraft's LVM (Logical Volume Manager) APIs including:
1. Creating physical volumes (pvcreate)
2. Creating volume groups (vgcreate)
3. Creating logical volumes (lvcreate)
4. Resizing logical volumes (lvresize)
5. Removing LVM components (lvremove, vgremove)

Workflow:
1. Create partition for LVM use
2. Initialize physical volume
3. Create volume group
4. Create logical volumes
5. Resize logical volumes
6. Clean up LVM stack

LVM Stack:
  Physical Volumes (PV) -> Volume Groups (VG) -> Logical Volumes (LV)
"""

import sys
import logging
from pathlib import Path

from hyper2kvm.vmcraft.main import VMCraft


def setup_logging():
    """Configure logging."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    return logging.getLogger(__name__)


def demonstrate_lvm_management(disk_image_path: str):
    """
    Demonstrate LVM creation and management capabilities.

    Args:
        disk_image_path: Path to disk image (will be modified!)
    """
    logger = setup_logging()
    logger.info(f"Demonstrating LVM management for: {disk_image_path}")
    logger.info("")
    logger.info("⚠️  WARNING: This will MODIFY the disk image!")
    logger.info("    Only use with test/disposable images")
    logger.info("")

    with VMCraft(disk_image_path) as g:
        logger.info("VMCraft launched successfully")

        device = g.get_nbd_device()
        logger.info(f"Working with device: {device}")

        # =====================================================================
        # Step 1: Create Partition for LVM
        # =====================================================================
        logger.info("Step 1: Creating partition for LVM...")

        # Initialize partition table
        g.part_init(device, "gpt")
        logger.info("  ✓ GPT partition table initialized")

        # Create single partition for LVM (using entire disk)
        g.part_add(device, "primary", 2048, -1)
        logger.info("  ✓ Partition created")

        # Get the partition device
        partitions = g.list_partitions()
        if not partitions:
            logger.error("Failed to create partition")
            return

        lvm_partition = partitions[0]
        logger.info(f"  LVM partition: {lvm_partition}")

        # Set GPT type to Linux LVM
        lvm_guid = "E6D6D379-F507-44C2-A23C-238F2A3DF928"
        g.part_set_gpt_type(device, 1, lvm_guid)
        g.part_set_name(device, 1, "Linux LVM")
        logger.info("  ✓ Partition type set to Linux LVM")

        # =====================================================================
        # Step 2: Create Physical Volume
        # =====================================================================
        logger.info("Step 2: Creating physical volume...")

        result = g.pvcreate([lvm_partition])

        if result["ok"]:
            logger.info("  ✓ Physical volume created")
            logger.info(f"    PVs: {result['pvs']}")
        else:
            logger.error(f"  ✗ Failed to create PV: {result.get('error')}")
            if result.get("error") == "lvm_tools_not_available":
                logger.error("    LVM tools (lvm2) not installed on host")
                logger.error("    Install with: sudo dnf install lvm2")
            return

        # =====================================================================
        # Step 3: Create Volume Group
        # =====================================================================
        logger.info("Step 3: Creating volume group...")

        vg_name = "vg_demo"
        result = g.vgcreate(vg_name, [lvm_partition])

        if result["ok"]:
            logger.info(f"  ✓ Volume group created: {result['vg']}")
        else:
            logger.error(f"  ✗ Failed to create VG: {result.get('error')}")
            return

        # =====================================================================
        # Step 4: Create Logical Volumes
        # =====================================================================
        logger.info("Step 4: Creating logical volumes...")

        # Create root LV (50% of VG)
        logger.info("  Creating root logical volume (50% of VG)...")
        result = g.lvcreate("root", vg_name, extents="50%FREE")

        if result["ok"]:
            logger.info(f"    ✓ Root LV created: {result['lv']}")
            root_lv = result["lv"]
        else:
            logger.error(f"    ✗ Failed to create root LV: {result.get('error')}")
            return

        # Create home LV (25% of remaining space)
        logger.info("  Creating home logical volume (25% of remaining)...")
        result = g.lvcreate("home", vg_name, extents="25%FREE")

        if result["ok"]:
            logger.info(f"    ✓ Home LV created: {result['lv']}")
            home_lv = result["lv"]
        else:
            logger.error(f"    ✗ Failed to create home LV: {result.get('error')}")
            return

        # Create swap LV (fixed 512MB)
        logger.info("  Creating swap logical volume (512MB)...")
        result = g.lvcreate("swap", vg_name, size_mb=512)

        if result["ok"]:
            logger.info(f"    ✓ Swap LV created: {result['lv']}")
            swap_lv = result["lv"]
        else:
            logger.error(f"    ✗ Failed to create swap LV: {result.get('error')}")
            return

        # =====================================================================
        # Step 5: List LVM Components
        # =====================================================================
        logger.info("Step 5: Listing LVM components...")

        # List physical volumes
        pvs = g.pvs()
        if pvs:
            logger.info(f"  Physical Volumes ({len(pvs)}):")
            for pv in pvs:
                logger.info(f"    - {pv}")

        # List volume groups
        vgs = g.vgs()
        if vgs:
            logger.info(f"  Volume Groups ({len(vgs)}):")
            for vg in vgs:
                logger.info(f"    - {vg}")

        # List logical volumes
        lvs = g.lvs()
        if lvs:
            logger.info(f"  Logical Volumes ({len(lvs)}):")
            for lv in lvs:
                logger.info(f"    - {lv}")

        # =====================================================================
        # Step 6: Resize Logical Volume
        # =====================================================================
        logger.info("Step 6: Resizing logical volume...")

        # Resize swap LV to 1GB
        logger.info("  Resizing swap LV from 512MB to 1GB...")
        result = g.lvresize(swap_lv, 1024)

        if result["ok"]:
            logger.info("    ✓ Swap LV resized to 1GB")
        else:
            logger.error(f"    ✗ Failed to resize swap LV: {result.get('error')}")

        # =====================================================================
        # Step 7: Create Filesystems on LVs
        # =====================================================================
        logger.info("Step 7: Creating filesystems on logical volumes...")

        # Create ext4 on root LV
        logger.info("  Creating ext4 filesystem on root LV...")
        try:
            g.mkfs("ext4", root_lv, label="root")
            logger.info("    ✓ ext4 filesystem created on root LV")
        except Exception as e:
            logger.warning(f"    ✗ Failed to create filesystem: {e}")

        # Create ext4 on home LV
        logger.info("  Creating ext4 filesystem on home LV...")
        try:
            g.mkfs("ext4", home_lv, label="home")
            logger.info("    ✓ ext4 filesystem created on home LV")
        except Exception as e:
            logger.warning(f"    ✗ Failed to create filesystem: {e}")

        # Create swap on swap LV
        logger.info("  Creating swap on swap LV...")
        try:
            g.mkswap(swap_lv, label="swap")
            logger.info("    ✓ Swap created on swap LV")
        except Exception as e:
            logger.warning(f"    ✗ Failed to create swap: {e}")

        # =====================================================================
        # Step 8: Cleanup (Optional)
        # =====================================================================
        logger.info("Step 8: Demonstrating LVM cleanup...")

        # Remove logical volumes
        logger.info("  Removing logical volumes...")
        for lv in [swap_lv, home_lv, root_lv]:
            result = g.lvremove(lv, force=True)
            if result["ok"]:
                logger.info(f"    ✓ Removed {lv}")
            else:
                logger.warning(f"    ✗ Failed to remove {lv}: {result.get('error')}")

        # Remove volume group
        logger.info("  Removing volume group...")
        result = g.vgremove(vg_name, force=True)
        if result["ok"]:
            logger.info(f"    ✓ Removed VG {vg_name}")
        else:
            logger.warning(f"    ✗ Failed to remove VG: {result.get('error')}")

        # =====================================================================
        # Summary
        # =====================================================================
        logger.info("=" * 70)
        logger.info("LVM MANAGEMENT SUMMARY")
        logger.info("=" * 70)
        logger.info("")
        logger.info("LVM Stack Hierarchy:")
        logger.info("  Physical Volumes (PV) → Volume Groups (VG) → Logical Volumes (LV)")
        logger.info("")
        logger.info("Physical Volume Operations:")
        logger.info("  - pvcreate([devices])                 Initialize PVs")
        logger.info("  - pvs()                               List PVs")
        logger.info("")
        logger.info("Volume Group Operations:")
        logger.info("  - vgcreate(name, pvs)                 Create VG from PVs")
        logger.info("  - vgremove(name, force=True)          Remove VG")
        logger.info("  - vgs()                               List VGs")
        logger.info("")
        logger.info("Logical Volume Operations:")
        logger.info("  - lvcreate(name, vg, size_mb=N)       Create LV with size in MB")
        logger.info("  - lvcreate(name, vg, extents='50%')   Create LV with percentage")
        logger.info("  - lvresize(path, size_mb)             Resize LV")
        logger.info("  - lvremove(path, force=True)          Remove LV")
        logger.info("  - lvs()                               List LVs")
        logger.info("")
        logger.info("Common Extent Specifications:")
        logger.info("  - '100%FREE' - Use all remaining space")
        logger.info("  - '50%FREE'  - Use 50% of remaining space")
        logger.info("  - '25%VG'    - Use 25% of total VG size")
        logger.info("")
        logger.info("Use Cases:")
        logger.info("  1. Flexible storage - Dynamic volume sizing")
        logger.info("  2. Snapshots - Create point-in-time copies (with lvs_snapshot)")
        logger.info("  3. Volume growth - Resize volumes as needed")
        logger.info("  4. Storage pooling - Combine multiple disks into one VG")
        logger.info("")
        logger.info("Best Practices:")
        logger.info("  1. Always set GPT type to Linux LVM (E6D6D379...)")
        logger.info("  2. Leave some space free in VG for snapshots")
        logger.info("  3. Use percentage extents for flexible layouts")
        logger.info("  4. Label filesystems for easier identification")

    logger.info("")
    logger.info("LVM management demonstration completed!")


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: python 03_lvm_management.py <disk_image_path>")
        print("")
        print("⚠️  WARNING: This script will MODIFY the disk image!")
        print("   Only use with test/disposable images")
        print("")
        print("Requirements:")
        print("  - LVM tools (lvm2) must be installed on host")
        print("  - Install with: sudo dnf install lvm2")
        print("")
        print("Example:")
        print("  # Create test image first (recommend at least 2GB)")
        print("  qemu-img create -f qcow2 test-lvm.qcow2 2G")
        print("  python 03_lvm_management.py test-lvm.qcow2")
        print("")
        print("This script demonstrates:")
        print("  - Creating LVM physical volumes")
        print("  - Creating volume groups")
        print("  - Creating and resizing logical volumes")
        print("  - Creating filesystems on LVs")
        print("  - Cleaning up LVM components")
        sys.exit(1)

    disk_image_path = sys.argv[1]

    if not Path(disk_image_path).exists():
        print(f"Error: Disk image not found: {disk_image_path}")
        print("")
        print("Create a test image with:")
        print(f"  qemu-img create -f qcow2 {disk_image_path} 2G")
        sys.exit(1)

    # Confirm modification
    response = input(f"This will MODIFY {disk_image_path}. Continue? (yes/no): ")
    if response.lower() != "yes":
        print("Aborted.")
        sys.exit(0)

    demonstrate_lvm_management(disk_image_path)


if __name__ == "__main__":
    main()
