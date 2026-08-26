#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Complete Filesystem Detection API Demonstration

Demonstrates all 33+ filesystem detection and manipulation APIs in VMCraft.

This example showcases:
- OS inspection (8 methods)
- Filesystem detection (3 methods)
- Block device operations (10 methods)
- Partition operations (2 methods)
- High-level inspection (2 methods)
- Extended attributes (2 methods)
- Filesystem-specific operations (6 methods - NTFS, Btrfs, ZFS)

Usage:
    python3 filesystem_api_demo.py <disk-image>

Example:
    python3 filesystem_api_demo.py /path/to/vm.vmdk
"""

import sys
import json
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from h2kvm.vmcraft.main import VMCraft


def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'=' * 80}")
    print(f" {title}")
    print(f"{'=' * 80}\n")


def demo_os_inspection(g: VMCraft) -> dict[str, Any]:
    """Demonstrate OS inspection APIs."""
    print_section("1. OS INSPECTION APIs (8 methods)")

    results = {}

    # 1. inspect_os() - Get list of operating systems
    print("[*] inspect_os() - Detect operating systems")
    roots = g.inspect_os()
    results["os_roots"] = roots
    print(f"    Found {len(roots)} operating system(s): {roots}\n")

    if not roots:
        print("    No operating systems detected (offline VM)\n")
        return results

    # Use first root for remaining inspection
    root = roots[0]
    print(f"[*] Using root device: {root}\n")

    # 2. inspect_get_type() - Get OS type
    print("[*] inspect_get_type() - Get OS type")
    os_type = g.inspect_get_type(root)
    results["type"] = os_type
    print(f"    OS Type: {os_type}\n")

    # 3. inspect_get_distro() - Get distribution name
    print("[*] inspect_get_distro() - Get distribution")
    distro = g.inspect_get_distro(root)
    results["distro"] = distro
    print(f"    Distribution: {distro}\n")

    # 4. inspect_get_product_name() - Get product name
    print("[*] inspect_get_product_name() - Get product name")
    product = g.inspect_get_product_name(root)
    results["product"] = product
    print(f"    Product: {product}\n")

    # 5 & 6. inspect_get_major_version() & inspect_get_minor_version()
    print("[*] inspect_get_major_version() & inspect_get_minor_version()")
    major = g.inspect_get_major_version(root)
    minor = g.inspect_get_minor_version(root)
    results["version"] = f"{major}.{minor}"
    print(f"    Version: {major}.{minor}\n")

    # 7. inspect_get_arch() - Get architecture
    print("[*] inspect_get_arch() - Get architecture")
    arch = g.inspect_get_arch(root)
    results["arch"] = arch
    print(f"    Architecture: {arch}\n")

    # 8. inspect_get_mountpoints() - Get mount points
    print("[*] inspect_get_mountpoints() - Get filesystem mount points")
    mountpoints = g.inspect_get_mountpoints(root)
    results["mountpoints"] = mountpoints
    print(f"    Mount points ({len(mountpoints)}):")
    if isinstance(mountpoints, dict):
        for mp, device in sorted(mountpoints.items()):
            print(f"      {mp:20} -> {device}")
    else:
        for mp, device in sorted(mountpoints):
            print(f"      {mp:20} -> {device}")
    print()

    return results


def demo_filesystem_detection(g: VMCraft) -> dict[str, Any]:
    """Demonstrate filesystem detection APIs."""
    print_section("2. FILESYSTEM DETECTION APIs (3 methods)")

    results = {}

    # 1. list_filesystems() - List all filesystems
    print("[*] list_filesystems() - List all detected filesystems")
    filesystems = g.list_filesystems()
    results["filesystems"] = filesystems
    print(f"    Found {len(filesystems)} filesystem(s):\n")
    print(f"    {'Device':<20} {'Filesystem Type':<15}")
    print(f"    {'-' * 35}")
    for device, fstype in filesystems.items():
        print(f"    {device:<20} {fstype:<15}")
    print()

    if not filesystems:
        return results

    # Pick first filesystem for detailed inspection
    device = list(filesystems.keys())[0]
    print(f"[*] Detailed inspection of: {device}\n")

    # 2. vfs_type() - Get filesystem type
    print("[*] vfs_type() - Get filesystem type")
    fstype = g.vfs_type(device)
    results["sample_fstype"] = fstype
    print(f"    Type: {fstype}\n")

    # 3a. vfs_uuid() - Get filesystem UUID
    print("[*] vfs_uuid() - Get filesystem UUID")
    uuid = g.vfs_uuid(device)
    results["sample_uuid"] = uuid
    print(f"    UUID: {uuid}\n")

    # 3b. vfs_label() - Get filesystem label
    print("[*] vfs_label() - Get filesystem label")
    label = g.vfs_label(device)
    results["sample_label"] = label
    print(f"    Label: {label if label else '(none)'}\n")

    return results


def demo_block_device_ops(g: VMCraft) -> dict[str, Any]:
    """Demonstrate block device operation APIs."""
    print_section("3. BLOCK DEVICE OPERATION APIs (10 methods)")

    results = {}

    # Get first device
    filesystems = g.list_filesystems()
    if not filesystems:
        print("    No block devices available\n")
        return results

    device = list(filesystems.keys())[0]
    print(f"[*] Using device: {device}\n")

    # 1. blockdev_getsize64() - Get device size in bytes
    print("[*] blockdev_getsize64() - Get device size in bytes")
    size_bytes = g.blockdev_getsize64(device)
    results["size_bytes"] = size_bytes
    size_gb = size_bytes / (1024**3)
    print(f"    Size: {size_bytes:,} bytes ({size_gb:.2f} GiB)\n")

    # 2. blockdev_getss() - Get logical sector size
    print("[*] blockdev_getss() - Get logical sector size")
    sector_size = g.blockdev_getss(device)
    results["sector_size"] = sector_size
    print(f"    Sector size: {sector_size} bytes\n")

    # 3. blockdev_getsz() - Get size in 512-byte sectors
    print("[*] blockdev_getsz() - Get size in 512-byte sectors")
    sectors = g.blockdev_getsz(device)
    results["sectors"] = sectors
    print(f"    Sectors (512-byte): {sectors:,}\n")

    # 4. blockdev_getbsz() - Get block size
    print("[*] blockdev_getbsz() - Get block size")
    block_size = g.blockdev_getbsz(device)
    results["block_size"] = block_size
    print(f"    Block size: {block_size} bytes\n")

    # 5. blockdev_getro() - Check if read-only
    print("[*] blockdev_getro() - Check if device is read-only")
    is_ro = g.blockdev_getro(device)
    results["read_only"] = is_ro
    print(f"    Read-only: {is_ro}\n")

    # 6-9. blockdev_setrw/setro/flushbufs/rereadpt - State modification
    print("[*] blockdev_setrw/setro/flushbufs/rereadpt() - State modification")
    print("    (Skipped in demo - would modify device state)\n")

    # 10. statvfs() - Get filesystem statistics
    print("[*] statvfs() - Get filesystem statistics")
    try:
        stats = g.statvfs("/")
        results["statvfs"] = stats
        print(f"    Filesystem statistics:")
        print(f"      Block size:   {stats.get('bsize', 0)} bytes")
        print(f"      Total blocks: {stats.get('blocks', 0):,}")
        print(f"      Free blocks:  {stats.get('bfree', 0):,}")
        print(f"      Available:    {stats.get('bavail', 0):,}")
        total_gb = (stats.get("blocks", 0) * stats.get("bsize", 0)) / (1024**3)
        free_gb = (stats.get("bavail", 0) * stats.get("bsize", 0)) / (1024**3)
        print(f"      Total space:  {total_gb:.2f} GiB")
        print(f"      Available:    {free_gb:.2f} GiB")
        print()
    except Exception as e:
        print(f"    statvfs failed: {e}\n")

    return results


def demo_partition_ops(g: VMCraft) -> dict[str, Any]:
    """Demonstrate partition operation APIs."""
    print_section("4. PARTITION OPERATION APIs (2 methods)")

    results = {}

    # Get a partition device
    filesystems = g.list_filesystems()
    partition = None
    for device in filesystems.keys():
        if any(device.endswith(str(i)) for i in range(1, 10)):
            partition = device
            break

    if not partition:
        print("    No partition devices found\n")
        return results

    print(f"[*] Using partition: {partition}\n")

    # 1. part_to_partnum() - Extract partition number
    print("[*] part_to_partnum() - Extract partition number")
    try:
        partnum = g.part_to_partnum(partition)
        results["partition_number"] = partnum
        print(f"    {partition} -> Partition #{partnum}\n")
    except Exception as e:
        print(f"    Error: {e}\n")

    # 2. part_to_dev() - Get parent device
    print("[*] part_to_dev() - Get parent device")
    try:
        parent = g.part_to_dev(partition)
        results["parent_device"] = parent
        print(f"    {partition} -> Parent: {parent}\n")
    except Exception as e:
        print(f"    Error: {e}\n")

    return results


def demo_high_level_inspection(g: VMCraft) -> dict[str, Any]:
    """Demonstrate high-level inspection APIs."""
    print_section("5. HIGH-LEVEL INSPECTION APIs (2 methods)")

    results = {}

    # 1. inspect_filesystems() - Group filesystems by OS root
    print("[*] inspect_filesystems() - Group filesystems by OS root")
    fs_by_root = g.inspect_filesystems()
    results["filesystems_by_root"] = fs_by_root
    print(f"    Filesystems grouped by OS root ({len(fs_by_root)}):")
    for root, fs_list in fs_by_root.items():
        print(f"      {root}:")
        for fs in fs_list:
            print(f"        - {fs}")
    print()

    # 2. inspect_get_filesystems() - Get filesystems for specific root
    if fs_by_root:
        root = list(fs_by_root.keys())[0]
        print(f"[*] inspect_get_filesystems('{root}') - Get filesystems for root")
        fs_list = g.inspect_get_filesystems(root)
        results["sample_root_filesystems"] = fs_list
        print(f"    Filesystems for {root}:")
        for fs in fs_list:
            print(f"      - {fs}")
        print()

    return results


def demo_extended_attrs(g: VMCraft) -> dict[str, Any]:
    """Demonstrate extended attribute APIs."""
    print_section("6. EXTENDED ATTRIBUTE APIs (2 methods)")

    results = {}

    # Test on common file
    test_file = "/etc/passwd"

    # 1. get_e2attrs() - Get ext2/3/4 attributes
    print(f"[*] get_e2attrs('{test_file}') - Get ext2/3/4 attributes")
    try:
        attrs = g.get_e2attrs(test_file)
        results["e2attrs"] = attrs
        if attrs:
            print(f"    Attributes: {attrs}")
            if "i" in attrs:
                print(f"      i - Immutable (file cannot be modified)")
            if "a" in attrs:
                print(f"      a - Append-only")
            if "e" in attrs:
                print(f"      e - Extent format")
        else:
            print(f"    No special attributes set (or not ext filesystem)")
        print()
    except Exception as e:
        print(f"    Error: {e}\n")

    # 2. set_e2attrs() - Set ext2/3/4 attributes
    print(f"[*] set_e2attrs() - Set ext2/3/4 attributes")
    print(f"    (Skipped in demo - would modify file attributes)\n")

    return results


def demo_filesystem_specific(g: VMCraft) -> dict[str, Any]:
    """Demonstrate filesystem-specific operation APIs."""
    print_section("7. FILESYSTEM-SPECIFIC OPERATION APIs (6 methods)")

    results = {}

    filesystems = g.list_filesystems()

    # NTFS operations
    print("[*] NTFS Operations\n")
    ntfs_devs = [d for d, t in filesystems.items() if t == "ntfs"]
    if ntfs_devs:
        device = ntfs_devs[0]
        print(f"[*] ntfs_3g_probe('{device}') - Probe NTFS mountability")
        probe_result = g.ntfs_3g_probe(device)
        results["ntfs_probe"] = probe_result
        if probe_result == 0:
            print(f"    Result: 0 (mountable)")
        elif probe_result == 11:
            print(f"    Result: 11 (hibernated - Windows fast startup)")
        else:
            print(f"    Result: {probe_result} (not mountable)")
        print()

        # Test read-write capability
        print(f"[*] ntfs_3g_probe('{device}', rw=True) - Test RW capability")
        rw_result = g.ntfs_3g_probe(device, rw=True)
        results["ntfs_probe_rw"] = rw_result
        print(f"    RW Result: {rw_result} ({'writable' if rw_result == 0 else 'read-only'})\n")
    else:
        print("    No NTFS filesystems found\n")

    # Btrfs operations
    print("[*] Btrfs Operations\n")
    btrfs_devs = [d for d, t in filesystems.items() if t == "btrfs"]
    if btrfs_devs:
        print("[*] btrfs_filesystem_show() - Show Btrfs filesystem info")
        btrfs_info = g.btrfs_filesystem_show()
        results["btrfs_info"] = btrfs_info
        print(f"    Found {len(btrfs_info)} Btrfs filesystem(s):")
        for fs in btrfs_info:
            print(f"      Label: {fs.get('label', '(none)')}")
            print(f"      UUID: {fs.get('uuid', 'unknown')}")
            print(f"      Devices: {fs.get('total_devices', 'unknown')}")
        print()

        print("[*] btrfs_subvolume_list() - List Btrfs subvolumes")
        try:
            subvols = g.btrfs_subvolume_list(btrfs_devs[0])
            results["btrfs_subvolumes"] = subvols
            print(f"    Found {len(subvols)} subvolume(s):")
            for sv in subvols:
                print(f"      ID {sv['id']}: {sv['path']}")
            print()
        except Exception as e:
            print(f"    Error: {e}\n")
    else:
        print("    No Btrfs filesystems found\n")

    # ZFS operations
    print("[*] ZFS Operations\n")
    print("[*] zfs_pool_list() - List ZFS pools")
    pools = g.zfs_pool_list()
    results["zfs_pools"] = pools
    if pools:
        print(f"    Found {len(pools)} ZFS pool(s):")
        for pool in pools:
            print(f"      - {pool}")
        print()

        print("[*] zfs_dataset_list() - List ZFS datasets")
        datasets = g.zfs_dataset_list()
        results["zfs_datasets"] = datasets
        print(f"    Found {len(datasets)} ZFS dataset(s):")
        for ds in datasets[:5]:  # Show first 5
            print(f"      {ds['name']}: {ds['used']} used, {ds['avail']} available")
        print()
    else:
        print("    No ZFS pools found\n")

    return results


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <disk-image>")
        print(f"\nExample: {sys.argv[0]} /path/to/vm.vmdk")
        sys.exit(1)

    disk_path = sys.argv[1]

    if not Path(disk_path).exists():
        print(f"Error: Disk image not found: {disk_path}")
        sys.exit(1)

    print(f"{'=' * 80}")
    print(f" VMCraft Filesystem API Demonstration")
    print(f" Disk: {Path(disk_path).name}")
    print(f"{'=' * 80}")

    g = VMCraft()
    all_results = {}

    try:
        print(f"\n[*] Launching {Path(disk_path).name}...")
        g.add_drive_opts(disk_path, readonly=True)
        g.launch()
        print(f"[*] Launch successful\n")

        # Run all demonstrations
        all_results["os_inspection"] = demo_os_inspection(g)
        all_results["filesystem_detection"] = demo_filesystem_detection(g)
        all_results["block_device_ops"] = demo_block_device_ops(g)
        all_results["partition_ops"] = demo_partition_ops(g)
        all_results["high_level_inspection"] = demo_high_level_inspection(g)
        all_results["extended_attrs"] = demo_extended_attrs(g)
        all_results["filesystem_specific"] = demo_filesystem_specific(g)

        # Print summary
        print_section("SUMMARY")
        print(f"API Categories Demonstrated: 7")
        print(f"Total Methods Demonstrated: 33+")
        print(f"")
        print(f"Category Breakdown:")
        print(f"  1. OS Inspection:           8 methods")
        print(f"  2. Filesystem Detection:    3 methods")
        print(f"  3. Block Device Operations: 10 methods")
        print(f"  4. Partition Operations:    2 methods")
        print(f"  5. High-Level Inspection:   2 methods")
        print(f"  6. Extended Attributes:     2 methods")
        print(f"  7. Filesystem-Specific:     6 methods (NTFS, Btrfs, ZFS)")
        print()

        # Save results
        report_path = f"/tmp/filesystem_api_demo_{Path(disk_path).stem}.json"
        with open(report_path, "w") as f:
            json.dump(all_results, f, indent=2, default=str)
        print(f"📄 Detailed results saved: {report_path}\n")

    except Exception as e:
        print(f"\n✗ Error: {e}\n")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    finally:
        print("[*] Shutting down...")
        g.shutdown()
        print("[*] Complete\n")


if __name__ == "__main__":
    main()
