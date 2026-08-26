# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Advanced integration tests using phony guest images.

Tests filesystem analysis, partition tables, boot mode, registry
inspection, mountpoints, user accounts, hostnames, and more.

Build phony guests first:
    sudo python3 test-data/phony-guests/build_all.py

Run:
    sudo python3 -m pytest tests/integration/test_phony_advanced.py -v
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from tests.integration.conftest import (
    make_fixer,
    needs_guestfs,
    needs_root,
    open_guestfs,
    open_phony,
    phony_image,
)

try:
    import guestfs
except ImportError:
    guestfs = None  # type: ignore[assignment]


# ============================================================================
# PARTITION TABLE ANALYSIS
# ============================================================================


@needs_root
@needs_guestfs
class TestPartitionTable:
    """Test partition table type and layout detection."""

    def test_fedora_gpt(self):
        """Fedora phony guest should have GPT partition table."""
        with open_guestfs("fedora.img") as g:
            assert g.part_get_parttype("/dev/sda") == "gpt"

    def test_rhel9_gpt(self):
        """RHEL 9 phony guest should have GPT."""
        with open_guestfs("rhel9.img") as g:
            assert g.part_get_parttype("/dev/sda") == "gpt"

    def test_windows_gpt_with_efi(self):
        """Windows phony guest should have GPT with EFI partition."""
        with open_guestfs("windows.img") as g:
            assert g.part_get_parttype("/dev/sda") == "gpt"
            partitions = g.part_list("/dev/sda")
            assert len(partitions) >= 2, "Windows should have EFI + root partitions"

    def test_partition_count(self):
        """Each guest should have the expected number of partitions."""
        expected = {
            "fedora.img": 1,
            "ubuntu.img": 1,
            "rhel9.img": 1,
            "windows.img": 2,  # EFI + root
        }
        for name, count in expected.items():
            with open_guestfs(name) as g:
                parts = g.part_list("/dev/sda")
                assert len(parts) == count, f"{name}: expected {count} partitions, got {len(parts)}"


# ============================================================================
# FILESYSTEM TYPE DETECTION
# ============================================================================


@needs_root
@needs_guestfs
class TestFilesystemType:
    """Test filesystem type detection on phony guests."""

    def test_linux_ext4(self):
        """Linux phony guests should use ext4."""
        for name in ("fedora.img", "ubuntu.img", "rhel9.img"):
            with open_guestfs(name) as g:
                fs = g.list_filesystems()
                assert "/dev/sda1" in fs, f"{name}: missing /dev/sda1"
                assert fs["/dev/sda1"] == "ext4", f"{name}: expected ext4, got {fs['/dev/sda1']}"

    def test_windows_ntfs(self):
        """Windows phony guest should have NTFS root and VFAT EFI."""
        with open_guestfs("windows.img") as g:
            fs = g.list_filesystems()
            assert fs.get("/dev/sda1") == "vfat", f"EFI partition should be vfat: {fs}"
            assert fs.get("/dev/sda2") == "ntfs", f"Root partition should be ntfs: {fs}"


# ============================================================================
# MOUNTPOINT ANALYSIS
# ============================================================================


@needs_root
@needs_guestfs
class TestMountpoints:
    """Test mountpoint detection via inspect_get_mountpoints."""

    def test_fedora_has_root_mount(self):
        """Fedora should have / mountpoint."""
        with open_phony("fedora.img") as (g, root):
            mps = g.inspect_get_mountpoints(root)
            assert "/" in mps, f"Missing / mountpoint: {mps}"

    def test_windows_has_root_mount(self):
        """Windows should map C:\\ to / mountpoint."""
        with open_phony("windows.img") as (g, root):
            mps = g.inspect_get_mountpoints(root)
            assert "/" in mps, f"Missing / mountpoint: {mps}"

    def test_all_guests_mountable(self):
        """All phony guests should be mountable at /."""
        for name in ("fedora.img", "ubuntu.img", "rhel9.img", "windows.img"):
            with open_phony(name) as (g, root):
                assert g.is_dir("/"), f"{name}: / is not a directory after mount"


# ============================================================================
# BOOT MODE DETECTION (UEFI vs BIOS)
# ============================================================================


@needs_root
@needs_guestfs
class TestBootMode:
    """Test UEFI vs BIOS boot mode detection."""

    def test_windows_has_efi_partition(self):
        """Windows phony guest should have EFI System Partition."""
        with open_guestfs("windows.img") as g:
            gpt_type = g.part_get_gpt_type("/dev/sda", 1)
            assert gpt_type.upper() == "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"

    def test_linux_no_efi_partition(self):
        """Linux phony guests should not have EFI partition (BIOS mode)."""
        for name in ("fedora.img", "rhel9.img"):
            with open_guestfs(name) as g:
                parts = g.part_list("/dev/sda")
                if len(parts) == 1:
                    continue
                gpt_type = g.part_get_gpt_type("/dev/sda", 1)
                assert gpt_type.upper() != "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"


# ============================================================================
# HOSTNAME DETECTION
# ============================================================================


@needs_root
@needs_guestfs
class TestHostname:
    """Test hostname detection from phony guests."""

    def test_fedora_hostname(self):
        with open_phony("fedora.img") as (g, _):
            assert g.cat("/etc/hostname").strip() == "fedora-phony"

    def test_ubuntu_hostname(self):
        with open_phony("ubuntu.img") as (g, _):
            assert g.cat("/etc/hostname").strip() == "ubuntu-phony"

    def test_rhel9_hostname(self):
        with open_phony("rhel9.img") as (g, _):
            assert g.cat("/etc/hostname").strip() == "rhel9-phony"


# ============================================================================
# USER ACCOUNT DETECTION
# ============================================================================


@needs_root
@needs_guestfs
class TestUserAccounts:
    """Test user/shadow file parsing on Linux phony guests."""

    def test_fedora_has_shadow(self):
        """Fedora should have /etc/shadow with root entry."""
        with open_phony("fedora.img") as (g, _):
            assert g.is_file("/etc/shadow")
            shadow = g.cat("/etc/shadow")
            assert "root:" in shadow

    def test_shadow_permissions(self):
        """Shadow file should have restrictive permissions."""
        with open_phony("fedora.img") as (g, _):
            stat = g.stat("/etc/shadow")
            mode = stat["mode"] & 0o777
            assert mode == 0, f"Shadow should be mode 0, got {oct(mode)}"


# ============================================================================
# WINDOWS REGISTRY INSPECTION
# ============================================================================


@needs_root
@needs_guestfs
class TestWindowsRegistry:
    """Test Windows registry hive inspection."""

    def test_registry_hives_exist(self):
        """Windows should have SOFTWARE, SYSTEM, SAM hives."""
        with open_phony("windows.img") as (g, _):
            for hive in ("SOFTWARE", "SYSTEM", "SAM"):
                path = f"/Windows/System32/Config/{hive}"
                assert g.is_file(path), f"Missing registry hive: {path}"

    def test_registry_hives_are_valid(self):
        """Registry hives should be valid NT registry files."""
        with open_phony("windows.img") as (g, _):
            for hive in ("SOFTWARE", "SYSTEM"):
                path = f"/Windows/System32/Config/{hive}"
                header = g.pread(path, 4, 0)
                assert header == b"regf", f"{hive}: expected regf header, got {header!r}"

    def test_windows_directory_structure(self):
        """Windows should have expected directory layout."""
        with open_phony("windows.img") as (g, _):
            for d in (
                "/Windows/System32",
                "/Windows/System32/Config",
                "/Windows/System32/Drivers",
                "/Program Files",
            ):
                assert g.is_dir(d), f"Missing directory: {d}"


# ============================================================================
# KERNEL / INITRAMFS DETECTION
# ============================================================================


@needs_root
@needs_guestfs
class TestKernelDetection:
    """Test kernel and initramfs file detection."""

    def test_fedora_has_kernel(self):
        """Fedora should have vmlinuz and initramfs."""
        with open_phony("fedora.img") as (g, _):
            assert g.is_file("/boot/vmlinuz")
            assert g.is_file("/boot/initramfs.img")

    def test_fedora_has_modules(self):
        """Fedora should have kernel modules directory."""
        with open_phony("fedora.img") as (g, _):
            modules = g.glob_expand("/usr/lib/modules/*/modules.dep")
            assert len(modules) >= 1, "No kernel modules found"

    def test_ubuntu_has_kernel(self):
        """Ubuntu should have vmlinuz."""
        with open_phony("ubuntu.img") as (g, _):
            assert g.is_file("/boot/vmlinuz")


# ============================================================================
# OS VERSION DETECTION
# ============================================================================


@needs_root
@needs_guestfs
class TestOSVersion:
    """Test OS version detection via guestfs inspection."""

    def test_fedora_version(self):
        with open_phony("fedora.img") as (g, root):
            assert g.inspect_get_major_version(root) == 41

    def test_rhel9_version(self):
        with open_phony("rhel9.img") as (g, root):
            assert g.inspect_get_major_version(root) == 9
            assert g.inspect_get_minor_version(root) == 4

    def test_ubuntu_version(self):
        with open_phony("ubuntu.img") as (g, root):
            assert g.inspect_get_major_version(root) == 24

    def test_windows_arch(self):
        """Windows should be detected as x86_64."""
        with open_phony("windows.img") as (g, root):
            arch = g.inspect_get_arch(root)
            assert arch in ("x86_64", "i386"), f"Unexpected arch: {arch}"

    def test_all_guests_have_product_name(self):
        """All guests should have a non-empty product name."""
        for name in ("fedora.img", "ubuntu.img", "rhel9.img", "windows.img"):
            with open_phony(name) as (g, root):
                product = g.inspect_get_product_name(root)
                assert product and len(product) > 0, f"{name}: empty product name"


# ============================================================================
# FSTAB ENTRY PARSING
# ============================================================================


@needs_root
@needs_guestfs
class TestFstabParsing:
    """Test fstab entry parsing with FstabStabilizer."""

    def test_parse_rhel9_fstab(self):
        """Parse RHEL 9 fstab entries."""
        from h2kvm.fixers.filesystem.fstab_stabilizer import FstabStabilizer

        with open_phony("rhel9.img") as (g, root):
            stabilizer = FstabStabilizer(g)
            fstab = g.cat("/etc/fstab")
            lines = fstab.strip().split("\n")
            entries = []
            for i, line in enumerate(lines):
                entry = stabilizer.parse_fstab_line(line, i + 1)
                if entry:
                    entries.append(entry)

            assert len(entries) >= 1
            root_entry = [e for e in entries if e.mountpoint == "/"]
            assert len(root_entry) == 1
            assert root_entry[0].spec == "/dev/sda1"

    def test_parse_fedora_fstab_uuid(self):
        """Parse Fedora fstab — should have UUID entries."""
        from h2kvm.fixers.filesystem.fstab_stabilizer import FstabStabilizer

        with open_phony("fedora.img") as (g, root):
            stabilizer = FstabStabilizer(g)
            fstab = g.cat("/etc/fstab")
            for i, line in enumerate(fstab.strip().split("\n")):
                entry = stabilizer.parse_fstab_line(line, i + 1)
                if entry and entry.mountpoint == "/":
                    assert entry.spec.startswith("UUID="), f"Expected UUID spec, got {entry.spec}"


# ============================================================================
# DOMAIN XML VALIDATION
# ============================================================================


@needs_root
@needs_guestfs
class TestDomainXMLValidation:
    """Test that generated domain XML is well-formed and parseable."""

    def test_linux_xml_is_valid(self):
        """Generated Linux domain XML should be valid XML."""
        from h2kvm.libvirt.linux_domain import LinuxDomainConfig, emit_linux_domain

        with tempfile.TemporaryDirectory() as tmpdir:
            config = LinuxDomainConfig(
                name="test-xml-valid",
                image_path=phony_image("fedora.img"),
                out_dir=Path(tmpdir),
                firmware="bios",
                memory_mib=512,
                vcpus=1,
            )
            paths = emit_linux_domain(config)
            xml = paths.xml_path.read_text()

            root = ET.fromstring(xml)
            assert root.tag == "domain"
            assert root.get("type") == "kvm"
            assert root.find("name").text == "test-xml-valid"
            assert root.find("memory") is not None
            assert root.find("vcpu") is not None
            assert root.find("devices") is not None

    def test_linux_xml_has_disk(self):
        """Linux domain XML should contain a disk device."""
        from h2kvm.libvirt.linux_domain import LinuxDomainConfig, emit_linux_domain

        with tempfile.TemporaryDirectory() as tmpdir:
            config = LinuxDomainConfig(
                name="test-disk",
                image_path=phony_image("fedora.img"),
                out_dir=Path(tmpdir),
                firmware="bios",
            )
            paths = emit_linux_domain(config)
            root = ET.fromstring(paths.xml_path.read_text())
            disks = root.findall(".//disk[@device='disk']")
            assert len(disks) >= 1, "XML should have at least one disk"

            disk = disks[0]
            assert disk.find("source") is not None
            assert disk.find("target") is not None

    def test_linux_xml_has_network(self):
        """Linux domain XML should contain a network interface."""
        from h2kvm.libvirt.linux_domain import LinuxDomainConfig, emit_linux_domain

        with tempfile.TemporaryDirectory() as tmpdir:
            config = LinuxDomainConfig(
                name="test-net",
                image_path=phony_image("fedora.img"),
                out_dir=Path(tmpdir),
                firmware="bios",
            )
            paths = emit_linux_domain(config)
            root = ET.fromstring(paths.xml_path.read_text())
            interfaces = root.findall(".//interface")
            assert len(interfaces) >= 1, "XML should have at least one network interface"

    def test_linux_uefi_has_loader(self):
        """UEFI domain XML should have os/loader element."""
        from h2kvm.libvirt.linux_domain import LinuxDomainConfig, emit_linux_domain

        with tempfile.TemporaryDirectory() as tmpdir:
            config = LinuxDomainConfig(
                name="test-uefi",
                image_path=phony_image("fedora.img"),
                out_dir=Path(tmpdir),
                profile="default",
                firmware="uefi",
                memory_mib=512,
                vcpus=1,
            )
            paths = emit_linux_domain(config)
            root = ET.fromstring(paths.xml_path.read_text())
            loader = root.find(".//os/loader")
            assert loader is not None, "UEFI XML should have os/loader element"
            assert "OVMF" in (loader.text or "")


# ============================================================================
# MULTI-FORMAT CONVERSION
# ============================================================================


@needs_root
@needs_guestfs
class TestMultiFormatConversion:
    """Test converting phony guests to various output formats."""

    def test_qcow2_to_vmdk(self):
        """Convert Fedora from qcow2 to VMDK using Convert API."""
        from h2kvm.converters.qemu.converter import Convert

        img = phony_image("fedora.img")
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "fedora.vmdk"
            logger = logging.getLogger("test")

            Convert.convert_image_with_progress(
                logger,
                img,
                out,
                out_format="vmdk",
                compress=False,
                in_format="qcow2",
            )

            assert out.exists()
            info = json.loads(
                subprocess.run(
                    ["qemu-img", "info", "--output=json", str(out)],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
            )
            assert info["format"] == "vmdk"

    def test_qcow2_to_vdi(self):
        """Convert Fedora from qcow2 to VDI using Convert API."""
        from h2kvm.converters.qemu.converter import Convert

        img = phony_image("fedora.img")
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "fedora.vdi"
            logger = logging.getLogger("test")

            Convert.convert_image_with_progress(
                logger,
                img,
                out,
                out_format="vdi",
                compress=False,
                in_format="qcow2",
            )

            assert out.exists()
            info = json.loads(
                subprocess.run(
                    ["qemu-img", "info", "--output=json", str(out)],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
            )
            assert info["format"] == "vdi"

    def test_round_trip_qcow2(self):
        """Convert qcow2 -> raw -> qcow2 and verify content survives."""
        from h2kvm.converters.qemu.converter import Convert

        img = phony_image("fedora.img")
        with tempfile.TemporaryDirectory() as tmpdir:
            raw = Path(tmpdir) / "step1.raw"
            final = Path(tmpdir) / "step2.qcow2"
            logger = logging.getLogger("test")

            Convert.convert_image_with_progress(
                logger,
                img,
                raw,
                out_format="raw",
                compress=False,
                in_format="qcow2",
            )
            Convert.convert_image_with_progress(
                logger,
                raw,
                final,
                out_format="qcow2",
                compress=False,
                in_format="raw",
            )

            # Verify the round-tripped image is still inspectable
            g = guestfs.GuestFS(python_return_dict=True)
            g.add_drive_opts(str(final), format="qcow2", readonly=True)
            g.launch()
            try:
                roots = g.inspect_os()
                assert roots, "Round-tripped image should still be inspectable"
                distro = g.inspect_get_distro(roots[0])
                assert distro == "fedora"
            finally:
                g.shutdown()
                g.close()


# ============================================================================
# CHECKSUM GENERATION
# ============================================================================


@needs_root
@needs_guestfs
class TestChecksumGeneration:
    """Test SHA256 checksum generation for converted images."""

    def test_sha256_consistent_across_conversions(self):
        """Two separate conversions of the same source should produce identical raw output."""
        from h2kvm.converters.qemu.converter import Convert

        img = phony_image("fedora.img")
        with tempfile.TemporaryDirectory() as tmpdir:
            out1 = Path(tmpdir) / "fedora1.raw"
            out2 = Path(tmpdir) / "fedora2.raw"
            logger = logging.getLogger("test")

            Convert.convert_image_with_progress(
                logger,
                img,
                out1,
                out_format="raw",
                compress=False,
                in_format="qcow2",
            )
            Convert.convert_image_with_progress(
                logger,
                img,
                out2,
                out_format="raw",
                compress=False,
                in_format="qcow2",
            )

            h1 = hashlib.sha256(out1.read_bytes()).hexdigest()
            h2 = hashlib.sha256(out2.read_bytes()).hexdigest()
            assert h1 == h2, "Two conversions of same source should produce identical output"
            assert len(h1) == 64, "SHA256 hex digest should be 64 chars"


# ============================================================================
# OFFLINE FIXER: detect_and_mount_root
# ============================================================================


@needs_root
@needs_guestfs
class TestOfflineFixerDetectRoot:
    """Test OfflineFSFix.detect_and_mount_root on phony guests."""

    def test_detect_fedora_root(self):
        """detect_and_mount_root should find Fedora root on /dev/sda1."""
        fixer = make_fixer()
        with open_guestfs("fedora.img", readonly=False) as g:
            fixer.detect_and_mount_root(g)
            assert fixer.inspect_root is not None
            assert "sda" in fixer.inspect_root
            assert fixer.boot_disk_index is None

    def test_detect_windows_root(self):
        """detect_and_mount_root should find Windows root."""
        fixer = make_fixer()
        with open_guestfs("windows.img", readonly=False) as g:
            fixer.detect_and_mount_root(g)
            assert fixer.inspect_root is not None
            assert fixer.boot_disk_index == 0

    def test_detect_multi_disk_windows(self):
        """detect_and_mount_root should find Windows on second disk."""
        fixer = make_fixer()
        with open_guestfs("windows-multi-disk-sda.img", "windows-multi-disk-sdb.img", readonly=False) as g:
            fixer.detect_and_mount_root(g)
            assert fixer.inspect_root is not None
            assert "sdb" in fixer.inspect_root, f"Root should be on sdb: {fixer.inspect_root}"
            assert fixer.boot_disk_index == 1, f"Boot disk should be index 1: {fixer.boot_disk_index}"

    def test_detect_rhel9_product_name(self):
        """detect_and_mount_root should log RHEL 9 product name."""
        fixer = make_fixer()
        with open_guestfs("rhel9.img", readonly=False) as g:
            fixer.detect_and_mount_root(g)
            info_calls = [str(c) for c in fixer.logger.info.call_args_list]
            found = any("Red Hat" in c or "rhel" in c.lower() for c in info_calls)
            assert found, f"Should log RHEL detection. Calls: {info_calls}"


# ============================================================================
# FILESYSTEM LABEL DETECTION
# ============================================================================


@needs_root
@needs_guestfs
class TestFilesystemLabels:
    """Test filesystem label detection."""

    def test_fedora_root_label(self):
        """Fedora root partition should have label ROOT."""
        with open_guestfs("fedora.img") as g:
            assert g.blkid("/dev/sda1").get("LABEL") == "ROOT"

    def test_ubuntu_root_label(self):
        """Ubuntu root partition should have label cloudimg-rootfs."""
        with open_guestfs("ubuntu.img") as g:
            assert g.blkid("/dev/sda1").get("LABEL") == "cloudimg-rootfs"

    def test_all_linux_have_uuid(self):
        """All Linux partitions should have a UUID."""
        for name in ("fedora.img", "ubuntu.img", "rhel9.img"):
            with open_guestfs(name) as g:
                blkid = g.blkid("/dev/sda1")
                assert "UUID" in blkid, f"{name}: missing UUID in blkid"
                assert len(blkid["UUID"]) > 0
