#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Build phony guest disk images for testing.

Creates minimal disk images that fool guestfs inspection API heuristics.
These images contain just enough filesystem structure (fstab, os-release,
registry hives, GRUB config) for hyper2kvm's detection and fix pipeline
to exercise all code paths without needing real OS installations.

Requires: guestfs (python3-libguestfs), root privileges for NBD/mount.

Usage:
    sudo python3 test-data/phony-guests/build_all.py
    sudo python3 test-data/phony-guests/build_all.py --only fedora
    sudo python3 test-data/phony-guests/build_all.py --only windows-multi-disk
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import guestfs
except ImportError:
    print("ERROR: python3-libguestfs required. Install: dnf install python3-libguestfs")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent


def _upload_minimal_hives(g: "guestfs.GuestFS") -> None:
    """Upload minimal valid registry hives to a mounted Windows guest.

    Uses a pre-built minimal registry hive (minimal-hive) as a template
    for SOFTWARE, SYSTEM, and SAM hives.
    """
    # Use pre-built registry hive binaries that contain enough structure
    # for guestfs inspection API to detect Windows.
    sw_hive = SCRIPT_DIR / "win2k22-software.reg.bin"
    sys_hive = SCRIPT_DIR / "windows-system.reg.bin"
    sam_hive = SCRIPT_DIR / "minimal-hive"

    for src, dest in [
        (sw_hive, "/Windows/System32/Config/SOFTWARE"),
        (sys_hive, "/Windows/System32/Config/SYSTEM"),
        (sam_hive, "/Windows/System32/Config/SAM"),
    ]:
        if not src.exists():
            raise FileNotFoundError(f"{src.name} not found at {src}")
        g.upload(str(src), dest)


def build_fedora(output_dir: Path) -> Path:
    """Build a minimal Fedora-like phony guest image.

    Creates a 256MB qcow2 with:
    - GPT partition table
    - ext4 root filesystem with /etc/os-release, /etc/fstab, GRUB config
    - Enough to fool guestfs inspect_os() as a Fedora system
    """
    img = output_dir / "fedora.img"
    print(f"  Building {img.name} ...")

    g = guestfs.GuestFS(python_return_dict=True)
    g.disk_create(str(img), "qcow2", 256 * 1024 * 1024)
    g.add_drive_opts(str(img), format="qcow2")
    g.launch()

    # Partition: GPT with one big partition
    g.part_init("/dev/sda", "gpt")
    g.part_add("/dev/sda", "p", 2048, -2048)

    # Filesystem
    g.mkfs("ext4", "/dev/sda1", label="ROOT")
    g.mount("/dev/sda1", "/")

    # /etc structure — must include distro-specific files that guestfs
    # inspection API looks for (redhat-release, rpm db, shadow, etc.)
    g.mkdir_p("/etc/sysconfig")
    g.mkdir_p("/boot/grub2")
    g.mkdir_p("/bin")
    g.mkdir_p("/sbin")
    g.mkdir_p("/usr/lib/modules/6.12.10-200.fc41.x86_64")
    g.mkdir_p("/usr/share/zoneinfo/UTC")
    g.mkdir_p("/var/lib/rpm")
    g.mkdir_p("/var/log")
    g.mkdir_p("/root")

    g.write(
        "/etc/os-release",
        (
            'NAME="Fedora Linux"\n'
            'VERSION="41 (Server Edition)"\n'
            "ID=fedora\n"
            "VERSION_ID=41\n"
            'PLATFORM_ID="platform:f41"\n'
            'PRETTY_NAME="Fedora Linux 41 (Server Edition)"\n'
        ),
    )
    # redhat-release is what guestfs actually keys on for Fedora/RHEL
    g.write("/etc/redhat-release", "Fedora release 41 (Server Edition)")
    g.write("/etc/fedora-release", "Fedora release 41 (Server Edition)")
    g.write("/etc/hostname", "fedora-phony")
    g.write("/etc/shadow", "root::19000:0:99999:7:::\n")
    g.chmod(0o000, "/etc/shadow")

    # fstab with UUID-based entries
    blkid = g.blkid("/dev/sda1")
    root_uuid = blkid.get("UUID", "00000000-0000-0000-0000-000000000001")
    g.write("/etc/fstab", (f"UUID={root_uuid} / ext4 defaults 1 1\n"))

    # GRUB config (minimal)
    g.write(
        "/boot/grub2/grub.cfg",
        (
            "set default=0\n"
            "set timeout=5\n"
            'menuentry "Fedora" {\n'
            "  linux /boot/vmlinuz root=UUID=" + root_uuid + " ro\n"
            "  initrd /boot/initramfs.img\n"
            "}\n"
        ),
    )

    # Fake kernel files
    g.touch("/boot/vmlinuz")
    g.touch("/boot/initramfs.img")
    g.touch("/usr/lib/modules/6.12.10-200.fc41.x86_64/modules.dep")

    g.umount_all()
    g.shutdown()
    g.close()

    print(f"  ✓ {img.name} ({img.stat().st_size // 1024 // 1024}MB)")
    return img


def build_ubuntu(output_dir: Path) -> Path:
    """Build a minimal Ubuntu-like phony guest image.

    Creates a 256MB qcow2 with:
    - GPT partition table
    - ext4 root filesystem with /etc/os-release, netplan config
    - Enough to fool guestfs inspect_os() as Ubuntu
    """
    img = output_dir / "ubuntu.img"
    print(f"  Building {img.name} ...")

    g = guestfs.GuestFS(python_return_dict=True)
    g.disk_create(str(img), "qcow2", 256 * 1024 * 1024)
    g.add_drive_opts(str(img), format="qcow2")
    g.launch()

    g.part_init("/dev/sda", "gpt")
    g.part_add("/dev/sda", "p", 2048, -2048)
    g.mkfs("ext4", "/dev/sda1", label="cloudimg-rootfs")
    g.mount("/dev/sda1", "/")

    g.mkdir_p("/etc/netplan")
    g.mkdir_p("/boot/grub")
    g.mkdir_p("/bin")
    g.mkdir_p("/sbin")
    g.mkdir_p("/usr/lib/modules/6.5.0-44-generic")
    g.mkdir_p("/usr/share/zoneinfo/UTC")
    g.mkdir_p("/var/lib/dpkg")
    g.mkdir_p("/var/log")

    g.write(
        "/etc/os-release",
        (
            'NAME="Ubuntu"\n'
            'VERSION="24.04 LTS (Noble Numbat)"\n'
            "ID=ubuntu\n"
            "ID_LIKE=debian\n"
            'VERSION_ID="24.04"\n'
            'PRETTY_NAME="Ubuntu 24.04 LTS"\n'
        ),
    )
    # debian_version is what guestfs keys on for Debian/Ubuntu
    g.write("/etc/debian_version", "trixie/sid")
    g.write("/etc/hostname", "ubuntu-phony")
    g.write("/var/lib/dpkg/status", "")

    blkid = g.blkid("/dev/sda1")
    root_uuid = blkid.get("UUID", "00000000-0000-0000-0000-000000000002")
    g.write("/etc/fstab", (f"UUID={root_uuid} / ext4 defaults 0 1\n"))

    # Netplan config (VMware-style NIC name that should be fixed)
    g.write(
        "/etc/netplan/01-netcfg.yaml",
        ("network:\n  version: 2\n  ethernets:\n    ens160:\n      dhcp4: true\n"),
    )

    g.write(
        "/boot/grub/grub.cfg",
        ('set default=0\nmenuentry "Ubuntu" {\n  linux /boot/vmlinuz root=UUID=' + root_uuid + "\n}\n"),
    )

    g.touch("/boot/vmlinuz")
    g.touch("/usr/lib/modules/6.5.0-44-generic/modules.dep")

    g.umount_all()
    g.shutdown()
    g.close()

    print(f"  ✓ {img.name} ({img.stat().st_size // 1024 // 1024}MB)")
    return img


def build_windows(output_dir: Path) -> Path:
    """Build a minimal Windows-like phony guest image.

    Creates a 512MB qcow2 with:
    - GPT partition table
    - NTFS root with Windows directory structure
    - Minimal registry hives (empty SYSTEM/SOFTWARE files)
    - Enough to fool guestfs inspect_os() as Windows
    """
    img = output_dir / "windows.img"
    print(f"  Building {img.name} ...")

    g = guestfs.GuestFS(python_return_dict=True)
    g.disk_create(str(img), "qcow2", 512 * 1024 * 1024)
    g.add_drive_opts(str(img), format="qcow2")
    g.launch()

    # Check ntfs-3g support
    try:
        g.available(["ntfs3g"])
    except Exception:
        print("  ⚠ ntfs-3g not available, creating empty placeholder")
        g.shutdown()
        g.close()
        img.touch()
        return img

    g.part_init("/dev/sda", "gpt")
    # EFI System Partition
    g.part_add("/dev/sda", "p", 2048, 206847)
    # Windows partition
    g.part_add("/dev/sda", "p", 206848, -2048)

    g.mkfs("vfat", "/dev/sda1")
    g.part_set_gpt_type("/dev/sda", 1, "C12A7328-F81F-11D2-BA4B-00A0C93EC93B")

    g.mkfs("ntfs", "/dev/sda2")
    g.mount("/dev/sda2", "/")

    # Windows directory structure
    g.mkdir_p("/Windows/System32/Config")
    g.mkdir_p("/Windows/System32/Drivers")
    g.mkdir_p("/Windows/TEMP")
    g.mkdir_p("/Program Files")

    # Upload registry hives with enough structure for guestfs inspection
    _upload_minimal_hives(g)

    # cmd.exe is checked by guestfs to confirm Windows
    # Upload a real PE64 binary so guestfs can detect architecture
    cmd_exe = SCRIPT_DIR / "cmd.exe"
    if cmd_exe.exists():
        g.upload(str(cmd_exe), "/Windows/System32/cmd.exe")
    else:
        g.write("/Windows/System32/cmd.exe", "MZ")
    g.touch("/autoexec.bat")

    g.umount_all()
    g.shutdown()
    g.close()

    print(f"  ✓ {img.name} ({img.stat().st_size // 1024 // 1024}MB)")
    return img


def build_windows_multi_disk(output_dir: Path) -> tuple[Path, Path]:
    """Build a multi-disk Windows phony guest for boot order testing.

    Creates two disks:
    - sda: blank data disk with NTFS partition (not bootable)
    - sdb: Windows OS disk (the actual boot disk)

    This tests that hyper2kvm correctly identifies the boot disk when
    Windows is NOT on the first disk.
    """
    img_sda = output_dir / "windows-multi-disk-sda.img"
    img_sdb = output_dir / "windows-multi-disk-sdb.img"
    print(f"  Building {img_sda.name} + {img_sdb.name} ...")

    # Check ntfs-3g support before creating disk images
    g = guestfs.GuestFS(python_return_dict=True)
    g.disk_create(str(img_sda), "qcow2", 256 * 1024 * 1024)
    g.add_drive_opts(str(img_sda), format="qcow2")
    g.launch()

    try:
        g.available(["ntfs3g"])
    except Exception:
        print("  ⚠ ntfs-3g not available, creating empty placeholders")
        g.shutdown()
        g.close()
        # Replace qcow2 with empty files so tests skip properly
        img_sda.write_bytes(b"")
        img_sdb.touch()
        return img_sda, img_sdb

    g.shutdown()
    g.close()

    g = guestfs.GuestFS(python_return_dict=True)
    g.disk_create(str(img_sdb), "qcow2", 512 * 1024 * 1024)
    g.add_drive_opts(str(img_sda), format="qcow2")
    g.add_drive_opts(str(img_sdb), format="qcow2")
    g.launch()

    # Disk 1 (sda): blank data disk
    g.part_init("/dev/sda", "gpt")
    g.part_add("/dev/sda", "p", 2048, -2048)
    g.mkfs("ntfs", "/dev/sda1")

    # Disk 2 (sdb): Windows OS disk
    g.part_init("/dev/sdb", "gpt")
    # EFI partition
    g.part_add("/dev/sdb", "p", 2048, 206847)
    # Windows root
    g.part_add("/dev/sdb", "p", 206848, -2048)

    g.mkfs("vfat", "/dev/sdb1")
    g.part_set_gpt_type("/dev/sdb", 1, "C12A7328-F81F-11D2-BA4B-00A0C93EC93B")

    g.mkfs("ntfs", "/dev/sdb2")
    g.mount("/dev/sdb2", "/")

    # Windows structure on second disk
    g.mkdir_p("/Windows/System32/Config")
    g.mkdir_p("/Windows/System32/Drivers")
    g.mkdir_p("/Windows/TEMP")
    g.mkdir_p("/Program Files")

    _upload_minimal_hives(g)
    cmd_exe = SCRIPT_DIR / "cmd.exe"
    if cmd_exe.exists():
        g.upload(str(cmd_exe), "/Windows/System32/cmd.exe")
    g.touch("/autoexec.bat")

    g.umount_all()
    g.shutdown()
    g.close()

    for p in (img_sda, img_sdb):
        print(f"  ✓ {p.name} ({p.stat().st_size // 1024 // 1024}MB)")
    return img_sda, img_sdb


def build_rhel(output_dir: Path) -> Path:
    """Build a minimal RHEL-like phony guest image.

    Creates a 256MB qcow2 with:
    - GPT partition table, LVM-style layout (single partition, no actual LVM)
    - ext4 root with /etc/os-release identifying as RHEL 9
    - GRUB2 config, fstab with device names (needs stabilization)
    """
    img = output_dir / "rhel9.img"
    print(f"  Building {img.name} ...")

    g = guestfs.GuestFS(python_return_dict=True)
    g.disk_create(str(img), "qcow2", 256 * 1024 * 1024)
    g.add_drive_opts(str(img), format="qcow2")
    g.launch()

    g.part_init("/dev/sda", "gpt")
    g.part_add("/dev/sda", "p", 2048, -2048)
    g.mkfs("ext4", "/dev/sda1", label="root")
    g.mount("/dev/sda1", "/")

    g.mkdir_p("/etc/sysconfig")
    g.mkdir_p("/boot/grub2")
    g.mkdir_p("/bin")
    g.mkdir_p("/sbin")
    g.mkdir_p("/usr/lib/modules/5.14.0-362.el9.x86_64")
    g.mkdir_p("/usr/share/zoneinfo/UTC")
    g.mkdir_p("/var/lib/rpm")
    g.mkdir_p("/var/log")

    g.write(
        "/etc/os-release",
        (
            'NAME="Red Hat Enterprise Linux"\n'
            'VERSION="9.4 (Plow)"\n'
            'ID="rhel"\n'
            'ID_LIKE="fedora"\n'
            'VERSION_ID="9.4"\n'
            'PRETTY_NAME="Red Hat Enterprise Linux 9.4 (Plow)"\n'
        ),
    )
    g.write("/etc/redhat-release", "Red Hat Enterprise Linux release 9.4 (Plow)")
    g.write("/etc/hostname", "rhel9-phony")
    g.write("/etc/shadow", "root::19000:0:99999:7:::\n")
    g.chmod(0o000, "/etc/shadow")

    # fstab with device name (not UUID) — tests fstab stabilization
    g.write("/etc/fstab", ("/dev/sda1 / ext4 defaults 1 1\n"))

    g.write(
        "/boot/grub2/grub.cfg",
        ('set default=0\nmenuentry "RHEL 9" {\n  linux /boot/vmlinuz root=/dev/sda1 ro\n}\n'),
    )

    g.touch("/boot/vmlinuz")
    g.touch("/usr/lib/modules/5.14.0-362.el9.x86_64/modules.dep")

    g.umount_all()
    g.shutdown()
    g.close()

    print(f"  ✓ {img.name} ({img.stat().st_size // 1024 // 1024}MB)")
    return img


BUILDERS = {
    "fedora": build_fedora,
    "ubuntu": build_ubuntu,
    "rhel9": build_rhel,
    "windows": build_windows,
    "windows-multi-disk": build_windows_multi_disk,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build phony guest images for testing")
    parser.add_argument("--only", choices=list(BUILDERS.keys()), help="Build only this image")
    parser.add_argument("--output-dir", type=Path, default=SCRIPT_DIR, help="Output directory")
    args = parser.parse_args()

    if os.getuid() != 0:
        print("WARNING: Building phony guests may require root for guestfs/NBD")

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    builders = {args.only: BUILDERS[args.only]} if args.only else BUILDERS

    print(f"Building {len(builders)} phony guest image(s) in {output_dir}/")
    for name, builder in builders.items():
        try:
            builder(output_dir)
        except Exception as e:
            print(f"  ✗ {name}: {e}")

    print("Done.")


if __name__ == "__main__":
    main()
