#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Example: Using systemd tools in hyper2kvm.

This script demonstrates how to use the systemd integration module
to leverage systemd command-line tools for VM migration tasks.
"""

from pathlib import Path

from hyper2kvm.systemd import (
    SystemdDetectVirt,
    SystemdDissect,
    systemd_escape,
)


def example_detect_virtualization():
    """Example: Detect virtualization environment."""
    print("🔍 === Virtualization Detection ===\n")

    detector = SystemdDetectVirt()

    # Detect current environment
    if detector.is_virtualized():
        virt_type = detector.detect()
        hypervisor = detector.get_hypervisor_name()
        print("✅ Running in virtualized environment")
        print(f"   Type: {virt_type.value}")
        print(f"   Hypervisor: {hypervisor}")

        if detector.is_vm():
            print("   Category: Full VM")
        elif detector.is_container():
            print("   Category: Container")
    else:
        print("ℹ️  Running on bare metal (not virtualized)")

    print()


def example_inspect_disk_image():
    """Example: Inspect disk image with systemd-dissect."""
    print("🔍 === Disk Image Inspection ===\n")

    # NOTE: This is a demo - adjust path to actual image
    image_path = Path("/path/to/disk.img")

    if not image_path.exists():
        print(f"⚠️  Image not found: {image_path}")
        print("   (This is a demo - adjust path to actual image)")
        return

    dissect = SystemdDissect()

    # Validate image
    if dissect.validate(image_path):
        print(f"✅ Image is valid: {image_path}")
    else:
        print(f"❌ Invalid image: {image_path}")
        return

    # Inspect image
    info = dissect.inspect(image_path)

    print("📄 Image Information:")
    print(f"   Path: {info.path}")
    print(f"   Format: {info.format}")
    print(f"   Size: {info.size:,} bytes")

    if info.os_release:
        print("\n💻 OS Information:")
        for key, value in info.os_release.items():
            print(f"   {key}: {value}")

    if info.partitions:
        print(f"\n💾 Partitions ({len(info.partitions)}):")
        for part in info.partitions:
            print(f"   {part.number}. {part.type} - {part.size:,} bytes")
            if part.name:
                print(f"      Name: {part.name}")

    print()


def example_mount_and_extract():
    """Example: Mount image and extract files."""
    print("📂 === Mount and Extract Files ===\n")

    image_path = Path("/path/to/disk.img")
    mountpoint = Path("/tmp/disk-mount")

    if not image_path.exists():
        print(f"⚠️  Image not found: {image_path}")
        print("   (This is a demo - adjust path to actual image)")
        return

    dissect = SystemdDissect()

    try:
        # Mount image
        print(f"📌 Mounting {image_path} at {mountpoint}...")
        dissect.mount(image_path, mountpoint, read_only=True, mkdir=True)
        print("✅ Mounted successfully")

        # List partitions
        partitions = dissect.list_partitions(image_path)
        print(f"\n📋 Found {len(partitions)} partitions")

        # Extract a file (example)
        try:
            print("\n📄 Extracting /etc/hostname...")
            hostname_file = dissect.copy_from(
                image_path,
                "/etc/hostname",
                Path("/tmp/hostname.txt"),
            )
            print(f"✅ Extracted to: {hostname_file}")

            with open(hostname_file) as f:
                hostname = f.read().strip()
                print(f"   Hostname: {hostname}")

        except Exception as e:
            print(f"⚠️  Could not extract file: {e}")

    finally:
        # Unmount
        print(f"\n📌 Unmounting {mountpoint}...")
        dissect.umount(mountpoint, rmdir=True)
        print("✅ Unmounted successfully")

    print()


def example_execute_command():
    """Example: Execute command with image mounted."""
    print("⚡ === Execute Command in Image ===\n")

    image_path = Path("/path/to/disk.img")

    if not image_path.exists():
        print(f"⚠️  Image not found: {image_path}")
        print("   (This is a demo - adjust path to actual image)")
        return

    dissect = SystemdDissect()

    # Execute command with image temporarily mounted
    try:
        print("⚡ Running 'cat /etc/os-release' in image...")
        result = dissect.with_image(
            image_path,
            ["cat", "/etc/os-release"],
        )

        print("✅ Command output:")
        print(result.stdout)

    except Exception as e:
        print(f"❌ Command failed: {e}")

    print()


def example_systemd_escape():
    """Example: Escape strings for systemd unit names."""
    print("🔤 === Systemd String Escaping ===\n")

    # Escape service name
    service_name = "my migration service"
    escaped = systemd_escape(service_name)
    print(f"Original: {service_name}")
    print(f"Escaped:  {escaped}")
    print()

    # Escape path
    mount_path = "/mnt/vm disks/disk1"
    escaped_path = systemd_escape(mount_path, path=True)
    print(f"Path:     {mount_path}")
    print(f"Escaped:  {escaped_path}")
    print()


def example_integration_workflow():
    """Example: Complete integration workflow."""
    print("🔄 === Complete Integration Workflow ===\n")

    # 1. Detect source environment
    print("Step 1: Detect source environment")
    detector = SystemdDetectVirt()
    if detector.is_vm():
        print(f"   ✅ Running in VM: {detector.get_hypervisor_name()}")
    else:
        print("   ℹ️  Not running in VM")

    print()

    # 2. Validate disk image (demo)
    print("Step 2: Validate disk image")
    print("   ⚠️  Demo mode - adjust path to actual image")

    print()

    # 3. Inspect image (demo)
    print("Step 3: Inspect disk image")
    print("   ⚠️  Demo mode - adjust path to actual image")

    print()

    # 4. Extract OS information (demo)
    print("Step 4: Extract OS information")
    print("   ⚠️  Demo mode - adjust path to actual image")

    print()

    print("✅ Workflow complete (demo)")
    print()


def main():
    """Run all examples."""
    print("🚀 === Systemd Integration Examples ===\n")

    # Example 1: Detect virtualization
    example_detect_virtualization()

    # Example 2: String escaping
    example_systemd_escape()

    # Example 3: Disk image inspection (demo only)
    print("📝 Note: Disk image examples require actual disk image files")
    print("   Adjust paths in the code to try them with real images\n")

    # Example 4: Integration workflow
    example_integration_workflow()

    print("✅ All examples completed!")


if __name__ == "__main__":
    main()
