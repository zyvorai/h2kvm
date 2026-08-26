# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Integration tests using phony guest images.

These tests exercise the full h2kvm pipeline (inspection, fstab
stabilization, boot order detection, domain XML emission) against
minimal disk images that fool the guestfs inspection API.

Requires:
    - Phony guest images built: sudo python3 test-data/phony-guests/build_all.py
    - Root access for guestfs NBD operations
    - libguestfs available

Skip reason shown if images not built or not running as root.
"""

from __future__ import annotations

import shutil
import tempfile
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


@needs_root
@needs_guestfs
class TestFedoraPhonyGuest:
    """Test inspection and fixes on Fedora phony guest."""

    def test_inspect_detects_fedora(self):
        """guestfs inspection should identify the image as Fedora."""
        with open_phony("fedora.img") as (g, root):
            distro = g.inspect_get_distro(root)
            assert distro == "fedora", f"Expected fedora, got {distro}"

            product = g.inspect_get_product_name(root)
            assert "Fedora" in product

    def test_fstab_has_uuid(self):
        """Fedora image fstab should use UUID entries."""
        with open_phony("fedora.img") as (g, root):
            fstab = g.cat("/etc/fstab")
            assert "UUID=" in fstab, f"fstab should use UUID entries: {fstab}"


@needs_root
@needs_guestfs
class TestUbuntuPhonyGuest:
    """Test inspection and fixes on Ubuntu phony guest."""

    def test_inspect_detects_ubuntu(self):
        """guestfs inspection should identify the image as Ubuntu."""
        with open_phony("ubuntu.img") as (g, root):
            distro = g.inspect_get_distro(root)
            assert distro == "ubuntu", f"Expected ubuntu, got {distro}"

    def test_netplan_has_vmware_nic(self):
        """Ubuntu image should have VMware NIC name in netplan (pre-fix)."""
        with open_phony("ubuntu.img") as (g, root):
            netplan = g.cat("/etc/netplan/01-netcfg.yaml")
            assert "ens160" in netplan, "Should have VMware NIC name for testing fixes"


@needs_root
@needs_guestfs
class TestRHEL9PhonyGuest:
    """Test inspection and fixes on RHEL 9 phony guest."""

    def test_inspect_detects_rhel(self):
        """guestfs inspection should identify the image as RHEL."""
        with open_phony("rhel9.img") as (g, root):
            distro = g.inspect_get_distro(root)
            assert distro == "rhel", f"Expected rhel, got {distro}"

            major = g.inspect_get_major_version(root)
            assert major == 9

    def test_fstab_uses_device_name(self):
        """RHEL 9 image fstab should use /dev/sda1 (needs stabilization)."""
        with open_phony("rhel9.img") as (g, root):
            fstab = g.cat("/etc/fstab")
            assert "/dev/sda1" in fstab, "Should use device name (pre-stabilization)"


@needs_root
@needs_guestfs
class TestWindowsPhonyGuest:
    """Test inspection on Windows phony guest."""

    def test_inspect_detects_windows(self):
        """guestfs inspection should identify the image as Windows."""
        with open_phony("windows.img") as (g, root):
            os_type = g.inspect_get_type(root)
            assert os_type == "windows", f"Expected windows, got {os_type}"


@needs_root
@needs_guestfs
class TestWindowsMultiDiskBootOrder:
    """Test boot order detection for multi-disk Windows guests.

    Windows is installed on the second disk (sdb). The boot disk index
    detection should identify sdb as the boot disk (index 1), not sda.
    """

    def test_inspect_finds_windows_on_second_disk(self):
        """guestfs should find Windows root on /dev/sdb2."""
        with open_guestfs("windows-multi-disk-sda.img", "windows-multi-disk-sdb.img") as g:
            roots = g.inspect_os()
            assert len(roots) >= 1, "No OS roots detected"

            root = roots[0]
            os_type = g.inspect_get_type(root)
            assert os_type == "windows", f"Expected windows, got {os_type}"
            assert "sdb" in root, f"Expected root on sdb, got {root}"

    def test_boot_disk_index_detects_second_disk(self):
        """_detect_boot_disk_index should return 1 for Windows on sdb."""
        with open_guestfs("windows-multi-disk-sda.img", "windows-multi-disk-sdb.img") as g:
            roots = g.inspect_os()
            root = roots[0]

            parent_disk = g.part_to_dev(root)
            disk_index = g.device_index(parent_disk)

            assert disk_index == 1, (
                f"Expected boot disk index 1 (sdb), got {disk_index} "
                f"(root={root}, parent_disk={parent_disk})"
            )

    def test_full_pipeline_boot_order(self):
        """Full pipeline: fixer should set boot_disk_index=1 for Windows on sdb."""
        sda = phony_image("windows-multi-disk-sda.img")
        sdb = phony_image("windows-multi-disk-sdb.img")

        with tempfile.TemporaryDirectory() as tmpdir:
            sda_copy = Path(tmpdir) / "sda.img"
            sdb_copy = Path(tmpdir) / "sdb.img"
            shutil.copy2(sda, sda_copy)
            shutil.copy2(sdb, sdb_copy)

            g = guestfs.GuestFS(python_return_dict=True)
            g.add_drive_opts(str(sda_copy), format="qcow2")
            g.add_drive_opts(str(sdb_copy), format="qcow2")
            g.launch()

            try:
                roots = g.inspect_os()
                root = roots[0]

                fixer = make_fixer()
                result = fixer._detect_boot_disk_index(g, root)

                assert result == 1, f"Expected boot_disk_index=1, got {result}"
            finally:
                g.shutdown()
                g.close()
