# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

"""Tests for DiskProcessor firmware partition hint detection."""

from __future__ import annotations

import types
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from hyper2kvm.orchestration.disk_processor import DiskProcessor


def _make_processor(mock_logger, **overrides):
    defaults = dict(
        workdir=None,
        skip_vmdk_inspection=False,
        vmdk_auto_fix_controller=False,
        flatten=False,
        flatten_format="qcow2",
        report=None,
        dry_run=False,
        no_backup=False,
        print_fstab=False,
        no_grub=False,
        regen_initramfs=True,
        fstab_mode="stabilize-all",
        remove_vmware_tools=False,
        resize=None,
        serial_console=True,
        initramfs_add_drivers=None,
        virtio_drivers_dir=None,
        luks_enable=False,
        luks_passphrase=None,
        luks_passphrase_env=None,
        luks_keyfile=None,
        luks_mapper_prefix="hyper2kvm-crypt",
        backend="vmcraft",
        container_isolation=True,
        conversion_dir=None,
        allowed_dirs=None,
        cloud_init_config=None,
        firstboot_scripts=None,
        network_config_inject=None,
        user_config_inject=None,
        service_config_inject=None,
        hostname_config_inject=None,
        root_password=None,
        ssh_authorized_key=None,
        to_output=None,
        out_format="qcow2",
        compress=False,
        compress_level=None,
        checksum=False,
        cleanup_cache=True,
    )
    defaults.update(overrides)
    args = types.SimpleNamespace(**defaults)
    return DiskProcessor(mock_logger, args)


MBR_DUMP = """
label: dos
device: /dev/nbd0
unit: sectors

/dev/nbd0p1 : start=2048, size=1048576, type=7, bootable
/dev/nbd0p2 : start=1050624, size=41943040, type=83
"""

GPT_EFI_DUMP = """
label: gpt
device: /dev/nbd0
unit: sectors

/dev/nbd0p1 : start=2048, size=204800, type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B, name="EFI System Partition"
/dev/nbd0p2 : start=206848, size=41943040, type=8300, name="root"
"""

GPT_NO_EFI_DUMP = """
label: gpt
device: /dev/nbd0
unit: sectors

/dev/nbd0p1 : start=2048, size=41943040, type=8300, name="root"
"""


class TestAutoDetectUefiFromPartitions:
    @pytest.mark.parametrize(
        ("dump", "expected_scheme", "expected_efi"),
        [
            (MBR_DUMP, "mbr", False),
            (GPT_EFI_DUMP, "gpt", True),
            (GPT_NO_EFI_DUMP, "gpt", False),
        ],
    )
    def test_sfdisk_dump_sets_hints(self, mock_logger, tmp_path, dump, expected_scheme, expected_efi):
        disk = tmp_path / "guest.img"
        disk.write_bytes(b"\x00" * 512)

        proc = _make_processor(mock_logger)
        with patch(
            "subprocess.run",
            return_value=Mock(returncode=0, stdout=dump, stderr=""),
        ):
            proc._auto_detect_uefi_from_partitions(disk)

        assert proc.args.disk_partition_scheme == expected_scheme
        assert proc.args.disk_has_efi_partition is expected_efi

    def test_sfdisk_failure_falls_back_to_nbd_path(self, mock_logger, tmp_path):
        disk = tmp_path / "guest.qcow2"
        disk.write_bytes(b"\x00" * 512)

        proc = _make_processor(mock_logger)
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[0] == "sfdisk":
                return Mock(returncode=1, stdout="", stderr="")
            if cmd[0] == "bash":
                return Mock(returncode=0, stdout=GPT_EFI_DUMP, stderr="")
            return Mock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            with patch("hyper2kvm.orchestration.disk_processor.Path") as path_cls:
                path_cls.return_value.exists.return_value = True
                path_cls.return_value.read_text.return_value = "0"
                proc._auto_detect_uefi_from_partitions(disk)

        assert any(c[0] == "bash" for c in calls)
        assert proc.args.disk_partition_scheme == "gpt"
        assert proc.args.disk_has_efi_partition is True

    def test_no_free_nbd_logs_warning(self, mock_logger, tmp_path):
        disk = tmp_path / "guest.img"
        disk.write_bytes(b"\x00" * 512)
        proc = _make_processor(mock_logger)

        with patch(
            "subprocess.run",
            return_value=Mock(returncode=1, stdout="", stderr=""),
        ):
            with patch("hyper2kvm.orchestration.disk_processor.Path") as path_cls:
                path_cls.return_value.exists.return_value = False
                proc._auto_detect_uefi_from_partitions(disk)

        mock_logger.warning.assert_called()
        assert "No free NBD device" in str(mock_logger.warning.call_args)

    def test_permission_error_logs_warning(self, mock_logger, tmp_path):
        disk = tmp_path / "guest.img"
        disk.write_bytes(b"\x00" * 512)
        proc = _make_processor(mock_logger)

        with patch(
            "subprocess.run",
            side_effect=PermissionError("denied"),
        ):
            proc._auto_detect_uefi_from_partitions(disk)

        mock_logger.warning.assert_called()
        assert "permission denied" in str(mock_logger.warning.call_args).lower()

    def test_missing_disk_file_is_debug_not_fatal(self, mock_logger, tmp_path):
        disk = tmp_path / "missing.img"
        proc = _make_processor(mock_logger)

        with patch(
            "subprocess.run",
            side_effect=FileNotFoundError("missing"),
        ):
            proc._auto_detect_uefi_from_partitions(disk)

        mock_logger.debug.assert_called()
