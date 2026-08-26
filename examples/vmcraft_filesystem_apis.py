#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
VMCraft Filesystem API Reference and Examples

Demonstrates all 37+ filesystem detection and manipulation APIs available
in VMCraft for comprehensive disk image analysis.

Categories:
  1. OS Inspection (8 methods)
  2. Filesystem Detection (3 methods)
  3. Partition Operations (2 methods)
  4. Block Device Operations (9 methods)
  5. Extended Attributes (2 methods)
  6. Filesystem-Specific Operations (13+ methods)
     - Btrfs (2 methods)
     - ZFS (2 methods)
     - XFS (5 methods)
     - NTFS (1 method)

Usage:
    python3 vmcraft_filesystem_apis.py <disk-image-path>

Example:
    python3 vmcraft_filesystem_apis.py /path/to/vm-disk.vmdk
    python3 vmcraft_filesystem_apis.py /path/to/vm-disk.qcow2
"""

import sys
from pathlib import Path
from hyper2kvm.vmcraft.main import VMCraft


def print_section(title: str):
    """Print formatted section header."""
    print(f"\n{'=' * 80}")
    print(f" {title}")
    print(f"{'=' * 80}\n")


def demo_os_inspection(g: VMCraft):
    """Demonstrate OS inspection APIs."""
    print_section("OS INSPECTION APIs (8 methods)")

    # 1. Inspect OS roots
    print("1. inspect_os() - Detect operating system roots")
    print("-" * 60)
    roots = g.inspect_os()
    print(f"Detected {len(roots)} OS root(s):")
    for root in roots:
        print(f"  - {root}")

    if not roots:
        print("  (No OS detected - disk may be data-only or unformatted)")
        return

    root = roots[0]

    # 2-7. Get OS details
    print("\n2-7. OS Details for root:", root)
    print("-" * 60)
    os_type = g.inspect_get_type(root)
    distro = g.inspect_get_distro(root)
    product = g.inspect_get_product_name(root)
    major = g.inspect_get_major_version(root)
    minor = g.inspect_get_minor_version(root)
    arch = g.inspect_get_arch(root)

    print(f"  Type:         {os_type}")
    print(f"  Distribution: {distro}")
    print(f"  Product:      {product}")
    print(f"  Version:      {major}.{minor}")
    print(f"  Architecture: {arch}")

    # 8. Get mountpoints
    print("\n8. inspect_get_mountpoints() - Get filesystem mount structure")
    print("-" * 60)
    mountpoints = g.inspect_get_mountpoints(root)
    print(f"Mountpoints: {len(mountpoints)}")
    for mp, device in sorted(mountpoints.items()):
        print(f"  {mp:20s} -> {device}")


def demo_filesystem_detection(g: VMCraft):
    """Demonstrate filesystem detection APIs."""
    print_section("FILESYSTEM DETECTION APIs (4 methods)")

    # 1. List all filesystems
    print("1. list_filesystems() - Detect all filesystems on disk")
    print("-" * 60)
    filesystems = g.list_filesystems()
    print(f"Found {len(filesystems)} filesystem(s):")
    for device, fstype in filesystems.items():
        print(f"  {device:30s} {fstype}")

    if not filesystems:
        print("  (No filesystems detected)")
        return

    # Pick first filesystem for detailed info
    device = list(filesystems.keys())[0]

    # 2-4. Get filesystem metadata
    print(f"\n2-4. Filesystem Metadata for {device}")
    print("-" * 60)
    vfs_type = g.vfs_type(device)
    vfs_uuid = g.vfs_uuid(device)
    vfs_label = g.vfs_label(device)

    print(f"  Type:  {vfs_type}")
    print(f"  UUID:  {vfs_uuid or '(none)'}")
    print(f"  Label: {vfs_label or '(none)'}")


def demo_partition_operations(g: VMCraft):
    """Demonstrate partition operation APIs."""
    print_section("PARTITION OPERATIONS APIs (2 methods)")

    filesystems = g.list_filesystems()
    if not filesystems:
        print("No filesystems available for partition operations demo")
        return

    # Find a partition device (not whole disk)
    partition = None
    for device in filesystems.keys():
        try:
            # Try to extract partition number - this will work for partitions
            num = g.part_to_partnum(device)
            partition = device
            break
        except Exception:
            continue

    if not partition:
        print("No partition devices found (only whole disks)")
        return

    print(f"Using partition: {partition}")
    print("-" * 60)

    # 1. part_to_partnum
    print(f"1. part_to_partnum('{partition}')")
    try:
        partnum = g.part_to_partnum(partition)
        print(f"   → Partition number: {partnum}")
    except Exception as e:
        print(f"   → Error: {e}")

    # 2. part_to_dev
    print(f"\n2. part_to_dev('{partition}')")
    try:
        parent = g.part_to_dev(partition)
        print(f"   → Parent device: {parent}")
    except Exception as e:
        print(f"   → Error: {e}")


def demo_blockdev_operations(g: VMCraft):
    """Demonstrate block device operation APIs."""
    print_section("BLOCK DEVICE OPERATIONS APIs (9 methods)")

    devices = g.list_devices()
    if not devices:
        print("No block devices available")
        return

    device = devices[0]
    print(f"Using device: {device}")
    print("-" * 60)

    # 1-4. Get device geometry
    print("1-4. Device Geometry:")
    size_bytes = g.blockdev_getsize64(device)
    sector_size = g.blockdev_getss(device)
    sector_count = g.blockdev_getsz(device)
    block_size = g.blockdev_getbsz(device)

    print(f"  Size (bytes):     {size_bytes:,} ({size_bytes / (1024**3):.2f} GiB)")
    print(f"  Sector size:      {sector_size} bytes")
    print(f"  Sector count:     {sector_count:,}")
    print(f"  Block size:       {block_size} bytes")

    # 5. Check read-only status
    print("\n5. blockdev_getro() - Check if device is read-only:")
    is_ro = g.blockdev_getro(device)
    print(f"   Read-only: {is_ro}")

    # 6-9. Device modification operations (informational - not executed)
    print("\n6-9. Device Modification Operations (available but not executed):")
    print("   blockdev_setrw()    - Set device to read-write mode")
    print("   blockdev_setro()    - Set device to read-only mode")
    print("   blockdev_flushbufs() - Flush device buffers")
    print("   blockdev_rereadpt()  - Re-read partition table")


def demo_inspection_wrappers(g: VMCraft):
    """Demonstrate high-level inspection wrapper APIs."""
    print_section("INSPECTION WRAPPER APIs (2 methods)")

    # 1. inspect_filesystems
    print("1. inspect_filesystems() - Group filesystems by OS root")
    print("-" * 60)
    fs_by_root = g.inspect_filesystems()
    for root, filesystems in fs_by_root.items():
        print(f"  Root: {root}")
        for fs in filesystems:
            print(f"    - {fs}")

    if not fs_by_root:
        print("  (No OS roots detected)")
        return

    # 2. inspect_get_filesystems
    root = list(fs_by_root.keys())[0]
    print(f"\n2. inspect_get_filesystems('{root}')")
    print("-" * 60)
    filesystems = g.inspect_get_filesystems(root)
    print(f"  Filesystems for this root: {len(filesystems)}")
    for fs in filesystems:
        print(f"    - {fs}")


def demo_extended_attributes(g: VMCraft):
    """Demonstrate ext2/3/4 extended attribute APIs."""
    print_section("EXTENDED ATTRIBUTES APIs (2 methods)")

    # Check if we have an ext filesystem mounted
    filesystems = g.list_filesystems()
    has_ext = any(fs.startswith("ext") for fs in filesystems.values())

    if not has_ext:
        print("No ext2/3/4 filesystems available for extended attributes demo")
        print("(Extended attributes are specific to ext filesystems)")
        return

    print("1-2. get_e2attrs() and set_e2attrs() - Manage ext file attributes")
    print("-" * 60)
    print("These methods allow reading and setting ext2/3/4 file attributes:")
    print("  - 'i' (immutable): File cannot be modified")
    print("  - 'a' (append-only): File can only be appended")
    print("  - 'd' (no dump): File not backed up by dump")
    print("  - 'e' (extent): File uses extents (ext4)")
    print()
    print("Example usage:")
    print("  attrs = g.get_e2attrs('/etc/passwd')       # Get current attributes")
    print("  g.set_e2attrs('/tmp/file', 'i')            # Make file immutable")
    print("  g.set_e2attrs('/tmp/file', 'i', clear=True) # Remove immutable flag")


def demo_filesystem_specific(g: VMCraft):
    """Demonstrate filesystem-specific operation APIs."""
    print_section("FILESYSTEM-SPECIFIC OPERATIONS APIs (13+ methods)")

    filesystems = g.list_filesystems()
    fs_types = set(filesystems.values())

    # Btrfs operations
    print("BTRFS OPERATIONS (2 methods):")
    print("-" * 60)
    if "btrfs" in fs_types:
        btrfs_dev = [d for d, t in filesystems.items() if t == "btrfs"][0]

        # 1. btrfs_filesystem_show
        print(f"1. btrfs_filesystem_show('{btrfs_dev}')")
        info = g.btrfs_filesystem_show(btrfs_dev)
        if info:
            for fs_info in info:
                print(f"   Label: {fs_info.get('label', '(none)')}")
                print(f"   UUID:  {fs_info.get('uuid', 'N/A')}")
                print(f"   Total devices: {fs_info.get('total_devices', 'N/A')}")

        # 2. btrfs_subvolume_list
        print(f"\n2. btrfs_subvolume_list('{btrfs_dev}')")
        try:
            subvols = g.btrfs_subvolume_list(btrfs_dev)
            print(f"   Found {len(subvols)} subvolume(s):")
            for subvol in subvols[:5]:  # Show first 5
                print(f"     ID {subvol.get('id')}: {subvol.get('path')}")
        except Exception as e:
            print(f"   Error: {e}")
    else:
        print("  (No Btrfs filesystems detected)")

    # ZFS operations
    print("\n\nZFS OPERATIONS (2 methods):")
    print("-" * 60)
    if "zfs" in fs_types:
        # 1. zfs_pool_list
        print("1. zfs_pool_list()")
        pools = g.zfs_pool_list()
        if pools:
            print(f"   Found {len(pools)} pool(s):")
            for pool in pools:
                print(f"     - {pool}")

            # 2. zfs_dataset_list
            pool = pools[0]
            print(f"\n2. zfs_dataset_list('{pool}')")
            datasets = g.zfs_dataset_list(pool)
            print(f"   Found {len(datasets)} dataset(s):")
            for ds in datasets[:5]:  # Show first 5
                print(f"     {ds.get('name'):30s} {ds.get('used'):>10s} / {ds.get('avail'):>10s}")
        else:
            print("   (No ZFS pools imported)")
    else:
        print("  (No ZFS filesystems detected)")

    # XFS operations
    print("\n\nXFS OPERATIONS (5 methods):")
    print("-" * 60)
    if "xfs" in fs_types:
        xfs_dev = [d for d, t in filesystems.items() if t == "xfs"][0]

        print(f"Available XFS operations for {xfs_dev}:")
        print("  1. xfs_info()   - Get XFS filesystem information and geometry")
        print("  2. xfs_admin()  - Modify XFS filesystem parameters")
        print("  3. xfs_growfs() - Grow XFS filesystem")
        print("  4. xfs_repair() - Repair XFS filesystem")
        print("  5. xfs_db()     - XFS debugging/diagnostic tool")
        print()

        # Example: xfs_info
        print(f"Example - xfs_info('{xfs_dev}'):")
        try:
            info = g.xfs_info(xfs_dev)
            print(f"  Block size:  {info.get('blocksize', 'N/A')} bytes")
            print(f"  AG count:    {info.get('agcount', 'N/A')}")
            print(f"  Inode size:  {info.get('inodesize', 'N/A')} bytes")
            print(f"  Label:       {info.get('label', '(none)')}")
        except Exception as e:
            print(f"  Error: {e}")
    else:
        print("  (No XFS filesystems detected)")

    # NTFS operations
    print("\n\nNTFS OPERATIONS (1 method):")
    print("-" * 60)
    if "ntfs" in fs_types:
        ntfs_dev = [d for d, t in filesystems.items() if t == "ntfs"][0]

        print(f"1. ntfs_3g_probe('{ntfs_dev}')")
        result = g.ntfs_3g_probe(ntfs_dev)
        if result == 0:
            print(f"   ✓ NTFS filesystem is mountable")
        else:
            print(f"   ✗ NTFS filesystem may have issues (return code: {result})")

        print(f"\n   ntfs_3g_probe('{ntfs_dev}', rw=True)")
        result = g.ntfs_3g_probe(ntfs_dev, rw=True)
        if result == 0:
            print(f"   ✓ NTFS filesystem is read-write mountable")
        else:
            print(f"   ✗ NTFS filesystem may be read-only or have issues")
    else:
        print("  (No NTFS filesystems detected)")


def demo_statvfs(g: VMCraft):
    """Demonstrate filesystem statistics API."""
    print_section("FILESYSTEM STATISTICS API")

    roots = g.inspect_os()
    if not roots:
        print("No OS detected, cannot demonstrate statvfs()")
        return

    print("statvfs() - Get filesystem usage statistics")
    print("-" * 60)

    try:
        stats = g.statvfs("/")
        total = stats["blocks"] * stats["bsize"]
        free = stats["bfree"] * stats["bsize"]
        avail = stats["bavail"] * stats["bsize"]
        used = total - free

        print(f"Root filesystem statistics:")
        print(f"  Block size:     {stats['bsize']:,} bytes")
        print(f"  Total blocks:   {stats['blocks']:,}")
        print(f"  Total size:     {total / (1024**3):.2f} GiB")
        print(f"  Used:           {used / (1024**3):.2f} GiB")
        print(f"  Free:           {free / (1024**3):.2f} GiB")
        print(f"  Available:      {avail / (1024**3):.2f} GiB")
        print(f"  Usage:          {(used / total * 100):.1f}%")
    except Exception as e:
        print(f"Error: {e}")


def main():
    """Main demonstration function."""
    if len(sys.argv) < 2:
        print(__doc__)
        print(f"\nError: Please provide a disk image path")
        print(f"Usage: {sys.argv[0]} <disk-image-path>")
        sys.exit(1)

    disk_image = sys.argv[1]

    if not Path(disk_image).exists():
        print(f"Error: Disk image not found: {disk_image}")
        sys.exit(1)

    print(f"{'#' * 80}")
    print(f"# VMCraft Filesystem API Reference")
    print(f"#")
    print(f"# Disk Image: {disk_image}")
    print(f"# Total APIs: 37+ filesystem detection and manipulation methods")
    print(f"{'#' * 80}")

    # Create VMCraft instance and launch
    print("\n[*] Launching VMCraft and connecting to disk image...")
    g = VMCraft()
    g.add_drive_opts(disk_image, readonly=True)
    g.launch()

    try:
        # Demonstrate each category of APIs
        demo_os_inspection(g)
        demo_filesystem_detection(g)
        demo_partition_operations(g)
        demo_blockdev_operations(g)
        demo_inspection_wrappers(g)
        demo_extended_attributes(g)
        demo_filesystem_specific(g)
        demo_statvfs(g)

        # Summary
        print_section("API REFERENCE SUMMARY")
        print("Complete filesystem API coverage:")
        print("  • OS Inspection:          8 methods")
        print("  • Filesystem Detection:   4 methods")
        print("  • Partition Operations:   2 methods")
        print("  • Block Device Ops:       9 methods")
        print("  • Inspection Wrappers:    2 methods")
        print("  • Extended Attributes:    2 methods")
        print("  • Filesystem-Specific:   13+ methods")
        print("    - Btrfs:                2 methods")
        print("    - ZFS:                  2 methods")
        print("    - XFS:                  5 methods")
        print("    - NTFS:                 1 method")
        print("  • Filesystem Stats:       1 method")
        print()
        print("Total: 37+ comprehensive filesystem APIs")
        print(f"{'=' * 80}\n")

    finally:
        print("[*] Shutting down VMCraft...")
        g.shutdown()


if __name__ == "__main__":
    main()
