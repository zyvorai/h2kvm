# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Integration tests: full pipeline stages against phony guest images.

Tests exercise real code paths (fstab stabilization, network detection,
guest identity, GRUB analysis, domain XML emission, format conversion)
against minimal disk images — no real OS installations needed.

Build phony guests first:
    sudo python3 test-data/phony-guests/build_all.py

Run:
    sudo python3 -m pytest tests/integration/test_phony_pipeline.py -v
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import pytest

from tests.integration.conftest import (
    make_fixer,
    needs_guestfs,
    needs_root,
    open_guestfs,
    open_phony,
    phony_image,
    writable_copy,
)

try:
    import guestfs
except ImportError:
    guestfs = None  # type: ignore[assignment]


# ============================================================================
# FSTAB STABILIZATION
# ============================================================================


@needs_root
@needs_guestfs
class TestFstabStabilization:
    """Test fstab stabilization converts device names to UUIDs."""

    def test_rhel9_fstab_needs_stabilization(self):
        """RHEL 9 phony guest has /dev/sda1 in fstab (unstable)."""
        with open_phony("rhel9.img") as (g, root):
            fstab = g.cat("/etc/fstab")
            assert "/dev/sda1" in fstab
            assert "UUID=" not in fstab

    def test_stabilize_rhel9_fstab(self):
        """FstabStabilizer should convert /dev/sda1 to UUID= entry."""
        from hyper2kvm.fixers.filesystem.fstab_stabilizer import FstabStabilizer

        with writable_copy("rhel9.img") as copy:
            g = guestfs.GuestFS(python_return_dict=True)
            g.add_drive_opts(str(copy), format="qcow2")
            g.launch()

            try:
                roots = g.inspect_os()
                root = roots[0]
                mps = g.inspect_get_mountpoints(root)
                for mp in sorted(mps.keys()):
                    try:
                        g.mount(mps[mp], mp)
                    except Exception:
                        pass

                stabilizer = FstabStabilizer(g)
                result = stabilizer.stabilize_fstab()

                assert result is not None
                new_fstab = g.cat("/etc/fstab")
                assert "UUID=" in new_fstab or "LABEL=" in new_fstab, (
                    f"fstab should use UUID or LABEL after stabilization: {new_fstab}"
                )
            finally:
                g.shutdown()
                g.close()

    def test_fedora_fstab_already_stable(self):
        """Fedora phony guest already uses UUID — stabilizer should be a no-op."""
        with open_phony("fedora.img") as (g, root):
            fstab = g.cat("/etc/fstab")
            assert "UUID=" in fstab
            assert "/dev/sda" not in fstab


# ============================================================================
# GUEST IDENTITY DETECTION
# ============================================================================


@needs_root
@needs_guestfs
class TestGuestIdentity:
    """Test GuestDetector identifies OS from phony guest images."""

    def _detect(self, name: str):
        """Detect guest using GuestDetector's inspection strategy."""
        from hyper2kvm.core.guest_identity import GuestDetector

        with open_phony(name) as (g, root):
            guest_type = GuestDetector.detect_by_inspection(g, root)
            distro = g.inspect_get_distro(root)
            return guest_type, distro

    def test_detect_fedora(self):
        """GuestDetector should identify Fedora as Linux."""
        from hyper2kvm.core.guest_identity import GuestType

        guest_type, distro = self._detect("fedora.img")
        assert guest_type == GuestType.LINUX
        assert distro == "fedora", f"Expected fedora, got {distro}"

    def test_detect_ubuntu(self):
        """GuestDetector should identify Ubuntu as Linux."""
        from hyper2kvm.core.guest_identity import GuestType

        guest_type, distro = self._detect("ubuntu.img")
        assert guest_type == GuestType.LINUX
        assert distro == "ubuntu", f"Expected ubuntu, got {distro}"

    def test_detect_rhel(self):
        """GuestDetector should identify RHEL as Linux."""
        from hyper2kvm.core.guest_identity import GuestType

        guest_type, distro = self._detect("rhel9.img")
        assert guest_type == GuestType.LINUX
        assert distro == "rhel", f"Expected rhel, got {distro}"

    def test_detect_windows(self):
        """GuestDetector should identify Windows."""
        from hyper2kvm.core.guest_identity import GuestType

        guest_type, _ = self._detect("windows.img")
        assert guest_type == GuestType.WINDOWS

    def test_indicator_detection_fedora(self):
        """GuestDetector.detect_by_indicators should score Linux highest for Fedora."""
        from hyper2kvm.core.guest_identity import GuestDetector, GuestType

        with open_phony("fedora.img") as (g, root):
            scores = GuestDetector.detect_by_indicators(g)
            assert scores[GuestType.LINUX] > scores[GuestType.WINDOWS]
            assert scores[GuestType.LINUX] > 0

    def test_indicator_detection_windows(self):
        """GuestDetector.detect_by_indicators should score Windows highest."""
        from hyper2kvm.core.guest_identity import GuestDetector, GuestType

        with open_phony("windows.img") as (g, root):
            scores = GuestDetector.detect_by_indicators(g)
            assert scores[GuestType.WINDOWS] > scores[GuestType.LINUX]
            assert scores[GuestType.WINDOWS] > 0


# ============================================================================
# NETWORK CONFIG DETECTION
# ============================================================================


@needs_root
@needs_guestfs
class TestNetworkConfigDetection:
    """Test network configuration type detection on phony guests."""

    def test_ubuntu_has_netplan(self):
        """Ubuntu phony guest should be detected as netplan."""
        with open_phony("ubuntu.img") as (g, root):
            files = g.glob_expand("/etc/netplan/*.yaml")
            assert len(files) > 0, "Ubuntu should have netplan config files"

            for f in files:
                content = g.cat(f)
                if "ens160" in content:
                    return  # Found VMware NIC
            pytest.fail("No VMware NIC name (ens160) found in netplan configs")

    def test_fedora_has_no_ifcfg(self):
        """Fedora phony guest should not have ifcfg-rh network scripts."""
        with open_phony("fedora.img") as (g, root):
            files = g.glob_expand("/etc/sysconfig/network-scripts/ifcfg-*")
            assert len(files) == 0, "Fedora phony guest should not have ifcfg files"


# ============================================================================
# GRUB CONFIG ANALYSIS
# ============================================================================


@needs_root
@needs_guestfs
class TestGrubAnalysis:
    """Test GRUB configuration analysis on phony guests."""

    def test_fedora_has_grub2(self):
        """Fedora phony guest should have GRUB2 config."""
        with open_phony("fedora.img") as (g, root):
            assert g.is_file("/boot/grub2/grub.cfg")
            grub_cfg = g.cat("/boot/grub2/grub.cfg")
            assert "menuentry" in grub_cfg
            assert "linux" in grub_cfg.lower()

    def test_ubuntu_has_grub(self):
        """Ubuntu phony guest should have GRUB config."""
        with open_phony("ubuntu.img") as (g, root):
            assert g.is_file("/boot/grub/grub.cfg")
            grub_cfg = g.cat("/boot/grub/grub.cfg")
            assert "menuentry" in grub_cfg

    def test_rhel9_grub_has_device_root(self):
        """RHEL 9 GRUB should have /dev/sda1 root (needs fixing)."""
        with open_phony("rhel9.img") as (g, root):
            grub_cfg = g.cat("/boot/grub2/grub.cfg")
            assert "/dev/sda1" in grub_cfg, "GRUB should reference /dev/sda1 (pre-fix)"


# ============================================================================
# DOMAIN XML EMISSION
# ============================================================================


@needs_root
@needs_guestfs
class TestDomainXMLEmission:
    """Test libvirt domain XML generation from phony guest images."""

    def test_emit_linux_domain_bios(self):
        """Generate BIOS domain XML for Fedora phony guest."""
        from hyper2kvm.libvirt.linux_domain import LinuxDomainConfig, emit_linux_domain

        img = phony_image("fedora.img")
        with tempfile.TemporaryDirectory() as tmpdir:
            config = LinuxDomainConfig(
                name="fedora-test",
                image_path=img,
                out_dir=Path(tmpdir),
                firmware="bios",
                memory_mib=1024,
                vcpus=1,
            )
            paths = emit_linux_domain(config)
            assert paths.xml_path.exists()

            xml = paths.xml_path.read_text()
            assert "<name>fedora-test</name>" in xml
            assert "bus='virtio'" in xml
            assert str(img) in xml

    def test_emit_windows_domain_bootstrap(self):
        """Generate bootstrap (SATA) domain XML for Windows phony guest."""
        from hyper2kvm.libvirt.windows_domain import (
            WindowsDomainConfig,
            emit_windows_domain,
        )

        img = phony_image("windows.img")
        with tempfile.TemporaryDirectory() as tmpdir:
            config = WindowsDomainConfig(
                name="win-test",
                image_path=img,
                out_dir=Path(tmpdir),
                stage="bootstrap",
                firmware="bios",
            )
            paths = emit_windows_domain(config)
            assert paths.xml_path.exists()

            xml = paths.xml_path.read_text()
            assert "<name>win-test</name>" in xml
            assert "bus='sata'" in xml  # bootstrap uses SATA

    def test_emit_windows_domain_with_boot_order(self):
        """Windows domain XML with disk_boot_order should set correct boot element."""
        from hyper2kvm.libvirt.windows_domain import WinDomainSpec, render_windows_domain_xml

        spec = WinDomainSpec(
            name="win-multi",
            img_path=str(phony_image("windows.img")),
            firmware="uefi",
            disk_boot_order=2,
        )
        xml = render_windows_domain_xml(spec, stage="final")
        assert "boot order='2'" in xml, f"Expected boot order=2 in XML:\n{xml}"


# ============================================================================
# FORMAT CONVERSION
# ============================================================================


@needs_root
@needs_guestfs
class TestFormatConversion:
    """Test qemu-img format conversion with phony guest images."""

    def test_qcow2_to_raw(self):
        """Convert Fedora phony guest from qcow2 to raw."""
        from hyper2kvm.converters.qemu.converter import Convert

        img = phony_image("fedora.img")
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_path = Path(tmpdir) / "fedora.raw"
            logger = logging.getLogger("test")

            Convert.convert_image_with_progress(
                logger,
                img,
                raw_path,
                out_format="raw",
                compress=False,
                in_format="qcow2",
            )

            assert raw_path.exists()
            assert raw_path.stat().st_size > 0

    def test_qcow2_compressed_copy(self):
        """Create a compressed qcow2 copy of Fedora phony guest."""
        from hyper2kvm.converters.qemu.converter import Convert

        img = phony_image("fedora.img")
        with tempfile.TemporaryDirectory() as tmpdir:
            compressed = Path(tmpdir) / "fedora-compressed.qcow2"
            logger = logging.getLogger("test")

            Convert.convert_image_with_progress(
                logger,
                img,
                compressed,
                out_format="qcow2",
                compress=True,
                in_format="qcow2",
            )

            assert compressed.exists()
            assert compressed.stat().st_size > 0


# ============================================================================
# SELINUX AUTORELABEL
# ============================================================================


@needs_root
@needs_guestfs
class TestSELinuxAutorelabel:
    """Test SELinux autorelabel creation on RHEL/Fedora phony guests."""

    def test_create_autorelabel(self):
        """Creating /.autorelabel should succeed on Fedora phony guest."""
        with writable_copy("fedora.img") as copy:
            g = guestfs.GuestFS(python_return_dict=True)
            g.add_drive_opts(str(copy), format="qcow2")
            g.launch()

            try:
                roots = g.inspect_os()
                root = roots[0]
                mps = g.inspect_get_mountpoints(root)
                for mp in sorted(mps.keys()):
                    g.mount(mps[mp], mp)

                assert not g.is_file("/.autorelabel")
                g.touch("/.autorelabel")
                assert g.is_file("/.autorelabel")
            finally:
                g.shutdown()
                g.close()


# ============================================================================
# MULTI-DISK INSPECTION
# ============================================================================


@needs_root
@needs_guestfs
class TestMultiDiskInspection:
    """Test inspection with multiple disks attached."""

    def test_two_linux_disks(self):
        """Two Linux disks should both be detected by inspect_os."""
        with open_guestfs("fedora.img", "rhel9.img") as g:
            roots = g.inspect_os()
            assert len(roots) >= 2, f"Expected 2 roots, got {len(roots)}: {roots}"

            distros = {g.inspect_get_distro(root) for root in roots}
            assert "fedora" in distros, f"Missing fedora in {distros}"
            assert "rhel" in distros, f"Missing rhel in {distros}"

    def test_linux_plus_windows(self):
        """Linux + Windows disks should both be detected."""
        with open_guestfs("fedora.img", "windows.img") as g:
            roots = g.inspect_os()
            assert len(roots) >= 2, f"Expected 2 roots, got {len(roots)}"

            types = {g.inspect_get_type(root) for root in roots}
            assert "linux" in types
            assert "windows" in types

    def test_boot_disk_index_for_each_root(self):
        """Each root's boot disk index should match its disk position."""
        with open_guestfs("fedora.img", "windows.img") as g:
            roots = g.inspect_os()
            fixer = make_fixer()

            for root in roots:
                os_type = g.inspect_get_type(root)
                idx = fixer._detect_boot_disk_index(g, root)
                parent = g.part_to_dev(root)
                actual_idx = g.device_index(parent)

                if os_type == "linux":
                    assert idx is None
                else:
                    assert idx == actual_idx


# ============================================================================
# QEMU-IMG INFO (Disk Metadata)
# ============================================================================


class TestDiskMetadata:
    """Test disk metadata inspection via qemu-img."""

    def test_qemu_img_info(self):
        """qemu-img info should report correct format for phony guests."""
        import json
        import subprocess

        for name in ("fedora.img", "ubuntu.img", "windows.img"):
            img = phony_image(name)
            result = subprocess.run(
                ["qemu-img", "info", "--output=json", str(img)],
                capture_output=True,
                text=True,
                check=True,
            )
            info = json.loads(result.stdout)
            assert info["format"] == "qcow2", f"{name}: expected qcow2, got {info['format']}"
            assert info["virtual-size"] > 0

    def test_disk_sizes(self):
        """Phony guests should have expected virtual sizes."""
        import json
        import subprocess

        expected = {
            "fedora.img": 256 * 1024 * 1024,
            "ubuntu.img": 256 * 1024 * 1024,
            "rhel9.img": 256 * 1024 * 1024,
            "windows.img": 512 * 1024 * 1024,
        }
        for name, expected_size in expected.items():
            img = phony_image(name)
            result = subprocess.run(
                ["qemu-img", "info", "--output=json", str(img)],
                capture_output=True,
                text=True,
                check=True,
            )
            info = json.loads(result.stdout)
            assert info["virtual-size"] == expected_size, (
                f"{name}: expected {expected_size}, got {info['virtual-size']}"
            )
