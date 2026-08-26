#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Example: Archive and Backup Operations

This script demonstrates VMCraft's archive and block device APIs including:
1. Creating tar archives from VM directories
2. Extracting tar archives to VM
3. Using compression (gzip, bzip2, xz)
4. Block device size queries
5. Direct block device copying with dd

Workflow:
1. Mount VM filesystem
2. Create archives of important directories
3. Extract archives to different locations
4. Query block device information
5. Perform block-level backups

Use Cases:
- VM backup and restore
- Directory migration between VMs
- Configuration backup
- Block-level disk cloning
"""

import sys
import logging
import tempfile
from pathlib import Path

from hyper2kvm.vmcraft.main import VMCraft


def setup_logging():
    """Configure logging."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    return logging.getLogger(__name__)


def demonstrate_archive_operations(vm_image_path: str):
    """
    Demonstrate archive and backup operations.

    Args:
        vm_image_path: Path to VM disk image
    """
    logger = setup_logging()
    logger.info(f"Demonstrating archive operations for: {vm_image_path}")

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

        # Create temporary directory for archives
        with tempfile.TemporaryDirectory() as tmpdir:
            logger.info(f"Using temporary directory: {tmpdir}")

            # =================================================================
            # Step 1: Create Uncompressed Archive
            # =================================================================
            logger.info("Step 1: Creating uncompressed tar archive...")

            tar_file = Path(tmpdir) / "etc-backup.tar"

            try:
                g.tar_out("/etc", str(tar_file), compress=None)
                logger.info(f"  ✓ Created {tar_file.name}")
                logger.info(f"    Size: {tar_file.stat().st_size:,} bytes")
            except Exception as e:
                logger.error(f"  ✗ Failed to create archive: {e}")

            # =================================================================
            # Step 2: Create Compressed Archives
            # =================================================================
            logger.info("Step 2: Creating compressed archives...")

            # Gzip compressed
            logger.info("  Creating gzip compressed archive...")
            tgz_file = Path(tmpdir) / "etc-backup.tar.gz"
            try:
                g.tar_out("/etc", str(tgz_file), compress="gzip")
                logger.info(f"    ✓ Created {tgz_file.name}")
                logger.info(f"      Size: {tgz_file.stat().st_size:,} bytes")
            except Exception as e:
                logger.error(f"    ✗ Failed: {e}")

            # Bzip2 compressed
            logger.info("  Creating bzip2 compressed archive...")
            tbz_file = Path(tmpdir) / "etc-backup.tar.bz2"
            try:
                g.tar_out("/etc", str(tbz_file), compress="bzip2")
                logger.info(f"    ✓ Created {tbz_file.name}")
                logger.info(f"      Size: {tbz_file.stat().st_size:,} bytes")
            except Exception as e:
                logger.error(f"    ✗ Failed: {e}")

            # XZ compressed (best compression)
            logger.info("  Creating xz compressed archive...")
            txz_file = Path(tmpdir) / "etc-backup.tar.xz"
            try:
                g.tar_out("/etc", str(txz_file), compress="xz")
                logger.info(f"    ✓ Created {txz_file.name}")
                logger.info(f"      Size: {txz_file.stat().st_size:,} bytes")
            except Exception as e:
                logger.error(f"    ✗ Failed: {e}")

            # Compare compression ratios
            if tar_file.exists() and tgz_file.exists():
                ratio = (1 - tgz_file.stat().st_size / tar_file.stat().st_size) * 100
                logger.info(f"  Gzip compression ratio: {ratio:.1f}%")

            if tar_file.exists() and txz_file.exists():
                ratio = (1 - txz_file.stat().st_size / tar_file.stat().st_size) * 100
                logger.info(f"  XZ compression ratio: {ratio:.1f}%")

            # =================================================================
            # Step 3: Convenience Wrappers (tgz_in/tgz_out)
            # =================================================================
            logger.info("Step 3: Using convenience wrappers...")

            var_backup = Path(tmpdir) / "var-backup.tgz"

            try:
                # Create backup with tgz_out (automatically uses gzip)
                g.tgz_out("/var/log", str(var_backup))
                logger.info(f"  ✓ Created {var_backup.name} using tgz_out()")
                logger.info(f"    Size: {var_backup.stat().st_size:,} bytes")
            except Exception as e:
                logger.error(f"  ✗ Failed: {e}")

            # =================================================================
            # Step 4: Extract Archive to VM
            # =================================================================
            logger.info("Step 4: Extracting archive back to VM...")

            if tgz_file.exists():
                try:
                    # Create restore directory
                    logger.info("  Extracting to /tmp/etc-restore...")
                    g.tar_in(str(tgz_file), "/tmp/etc-restore", compress="gzip")
                    logger.info("    ✓ Archive extracted successfully")

                    # Verify extraction
                    files = g.ls("/tmp/etc-restore")
                    logger.info(f"    Extracted files: {len(files)}")
                except Exception as e:
                    logger.error(f"    ✗ Failed to extract: {e}")

            # =================================================================
            # Step 5: Block Device Information
            # =================================================================
            logger.info("Step 5: Querying block device information...")

            device = g.get_nbd_device()
            logger.info(f"  Working with device: {device}")

            # Get device size in bytes
            size_bytes = g.blockdev_getsize64(device)
            size_gb = size_bytes / (1024**3)
            logger.info(f"  Device size: {size_bytes:,} bytes ({size_gb:.2f} GB)")

            # Get device size in 512-byte sectors
            size_sectors = g.blockdev_getsz(device)
            logger.info(f"  Device size: {size_sectors:,} sectors")

            # Query partition sizes
            if partitions:
                logger.info("  Partition sizes:")
                for partition in partitions:
                    try:
                        part_size = g.blockdev_getsize64(partition)
                        part_gb = part_size / (1024**3)
                        logger.info(f"    {partition}: {part_size:,} bytes ({part_gb:.2f} GB)")
                    except Exception:
                        continue

            # =================================================================
            # Step 6: Block-Level Backup with dd
            # =================================================================
            logger.info("Step 6: Demonstrating block-level operations...")

            # Create a small test file in the VM
            logger.info("  Creating test data file...")
            test_data = "/tmp/test-dd-source"
            try:
                g.write(test_data, b"This is test data for dd copy\n" * 100)
                logger.info("    ✓ Test file created")

                # Copy using dd
                test_dest = "/tmp/test-dd-dest"
                logger.info(f"  Copying {test_data} to {test_dest} using dd...")

                g.dd_copy(
                    src=test_data,
                    dest=test_dest,
                    blocksize=512,
                    count=None,  # Copy entire file
                )
                logger.info("    ✓ dd copy completed")

                # Verify copy
                source_content = g.read_file(test_data)
                dest_content = g.read_file(test_dest)

                if source_content == dest_content:
                    logger.info("    ✓ Copy verified - files match")
                else:
                    logger.warning("    ⚠ Copy verification failed - files differ")

            except Exception as e:
                logger.error(f"    ✗ Failed: {e}")

            # =================================================================
            # Step 7: Backup and Restore Workflow
            # =================================================================
            logger.info("Step 7: Complete backup/restore workflow example...")

            workflow_backup = Path(tmpdir) / "full-backup.tar.xz"

            try:
                # Backup important directories
                logger.info("  Creating full system backup...")
                logger.info("    Directories: /etc, /var/log, /root")

                # In real scenario, you'd backup multiple directories
                # For this demo, just backup /etc
                g.tar_out("/etc", str(workflow_backup), compress="xz")

                logger.info(f"    ✓ Backup created: {workflow_backup.name}")
                logger.info(f"      Size: {workflow_backup.stat().st_size:,} bytes")

                # Simulate restore
                logger.info("  Simulating restore...")
                restore_dir = "/tmp/restore-test"

                g.tar_in(str(workflow_backup), restore_dir, compress="xz")
                logger.info(f"    ✓ Restored to {restore_dir}")

                # Verify
                files = g.ls(restore_dir)
                logger.info(f"    Verified: {len(files)} files restored")

            except Exception as e:
                logger.error(f"    ✗ Workflow failed: {e}")

        # =====================================================================
        # Summary
        # =====================================================================
        logger.info("=" * 70)
        logger.info("ARCHIVE AND BACKUP OPERATIONS SUMMARY")
        logger.info("=" * 70)
        logger.info("")
        logger.info("Archive Operations:")
        logger.info("  - tar_out(dir, file, compress=None)   Create tar from VM directory")
        logger.info("  - tar_in(file, dir, compress=None)    Extract tar to VM directory")
        logger.info("  - tgz_out(dir, file)                  Create gzipped tar (convenience)")
        logger.info("  - tgz_in(file, dir)                   Extract gzipped tar (convenience)")
        logger.info("")
        logger.info("Compression Options:")
        logger.info("  - None        No compression (fastest, largest)")
        logger.info("  - 'gzip'      Good balance of speed and size")
        logger.info("  - 'bzip2'     Better compression, slower")
        logger.info("  - 'xz'        Best compression, slowest")
        logger.info("")
        logger.info("Block Device Operations:")
        logger.info("  - blockdev_getsize64(device)          Get size in bytes")
        logger.info("  - blockdev_getsz(device)              Get size in 512-byte sectors")
        logger.info("  - dd_copy(src, dest, bs, count)       Block-level copy")
        logger.info("")
        logger.info("Use Cases:")
        logger.info("  1. VM Backup:")
        logger.info("     - Backup /etc, /var, /home to archive")
        logger.info("     - Store archives offsite")
        logger.info("     - Restore on disaster recovery")
        logger.info("")
        logger.info("  2. Configuration Migration:")
        logger.info("     - Export /etc from source VM")
        logger.info("     - Import to target VM")
        logger.info("     - Merge with existing config")
        logger.info("")
        logger.info("  3. Log Collection:")
        logger.info("     - Archive /var/log for analysis")
        logger.info("     - Extract on separate system")
        logger.info("     - Preserve for compliance")
        logger.info("")
        logger.info("  4. Block-Level Operations:")
        logger.info("     - Query disk geometry")
        logger.info("     - Copy boot sectors")
        logger.info("     - Clone partitions")
        logger.info("")
        logger.info("Best Practices:")
        logger.info("  1. Use xz compression for long-term storage")
        logger.info("  2. Use gzip for frequently accessed archives")
        logger.info("  3. Test restores regularly")
        logger.info("  4. Include checksums with backups")
        logger.info("  5. Store backups on separate systems/media")

    logger.info("")
    logger.info("Archive and backup operations demonstration completed!")


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: python 05_archive_backup_operations.py <vm_image_path>")
        print("")
        print("Example:")
        print("  python 05_archive_backup_operations.py /path/to/rhel9-vm.qcow2")
        print("")
        print("This script demonstrates:")
        print("  - Creating tar archives from VM directories")
        print("  - Using different compression methods (gzip, bzip2, xz)")
        print("  - Extracting archives back to VM")
        print("  - Querying block device information")
        print("  - Block-level copying with dd")
        print("  - Complete backup/restore workflows")
        sys.exit(1)

    vm_image_path = sys.argv[1]

    if not Path(vm_image_path).exists():
        print(f"Error: VM image not found: {vm_image_path}")
        sys.exit(1)

    demonstrate_archive_operations(vm_image_path)


if __name__ == "__main__":
    main()
