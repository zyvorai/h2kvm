# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
# https://zyvor.dev · info@zyvor.dev

"""Tests for find_exported_disks: where a vSphere export leaves its disks."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

from h2kvm.orchestration.vsphere_exporter import find_exported_disks

LOG = logging.getLogger("test_vsphere_export_discovery")


def _touch(path: Path, data: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_finds_disks_under_govc_ovfdir_layout(tmp_path):
    """govc export.ovf writes <vm>.ovfdir/<vm>/*.vmdk, one level below the job dir."""
    disk0 = _touch(tmp_path / "web.ovfdir" / "web" / "web-disk-0.vmdk")
    disk1 = _touch(tmp_path / "web.ovfdir" / "web" / "web-disk-1.vmdk")
    _touch(tmp_path / "web.ovfdir" / "web" / "web.ovf", b"<ovf/>")
    _touch(tmp_path / "web.ovfdir" / "web" / "web.mf", b"sha")

    assert find_exported_disks(LOG, tmp_path) == [disk0, disk1]


def test_top_level_disk_is_still_found(tmp_path):
    disk = _touch(tmp_path / "vm.qcow2")
    assert find_exported_disks(LOG, tmp_path) == [disk]


def test_vmdk_extents_are_not_disks(tmp_path):
    """A datastore download has a descriptor plus -flat/-delta extents; only the descriptor is the disk."""
    descriptor = _touch(tmp_path / "vm.vmdk")
    _touch(tmp_path / "vm-flat.vmdk")
    _touch(tmp_path / "vm-000001-delta.vmdk")
    _touch(tmp_path / "vm-000002-sesparse.vmdk")

    assert find_exported_disks(LOG, tmp_path) == [descriptor]


def test_empty_files_are_skipped(tmp_path):
    _touch(tmp_path / "empty.vmdk", b"")
    disk = _touch(tmp_path / "real.vmdk")
    assert find_exported_disks(LOG, tmp_path) == [disk]


def test_ova_only_export_is_extracted_not_returned_as_a_disk(tmp_path):
    ova = _touch(tmp_path / "web.ova", b"tar")
    extracted = tmp_path / "web.extracted" / "web-disk-0.vmdk"

    with patch("h2kvm.converters.extractors.ovf.OVF.extract_ova", return_value=[extracted]) as m:
        result = find_exported_disks(LOG, tmp_path)

    assert result == [extracted]
    assert ova not in result
    m.assert_called_once_with(LOG, ova, tmp_path / "web.extracted")


def test_ova_is_ignored_when_a_plain_disk_exists(tmp_path):
    disk = _touch(tmp_path / "web.ovfdir" / "web" / "d.vmdk")
    _touch(tmp_path / "web.ova", b"tar")

    with patch("h2kvm.converters.extractors.ovf.OVF.extract_ova") as m:
        assert find_exported_disks(LOG, tmp_path) == [disk]
    m.assert_not_called()


def test_failed_ova_extraction_returns_nothing_instead_of_raising(tmp_path):
    _touch(tmp_path / "bad.ova", b"not a tar")
    with patch("h2kvm.converters.extractors.ovf.OVF.extract_ova", side_effect=RuntimeError("boom")):
        assert find_exported_disks(LOG, tmp_path) == []


def test_empty_directory(tmp_path):
    assert find_exported_disks(LOG, tmp_path) == []
