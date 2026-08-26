# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for hyper2kvm.vmcraft.main.VMCraft and service-layer helpers."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from hyper2kvm.vmcraft.services import partition_to_device, partition_to_number


# ---------------------------------------------------------------------------
# partition_to_number  (pure function, no I/O)
# ---------------------------------------------------------------------------


class TestPartitionToNumber:
    def test_sda1(self):
        assert partition_to_number("/dev/sda1") == 1

    def test_sda12(self):
        assert partition_to_number("/dev/sda12") == 12

    def test_nvme0n1p2(self):
        assert partition_to_number("/dev/nvme0n1p2") == 2

    def test_nbd0p3(self):
        assert partition_to_number("/dev/nbd0p3") == 3

    def test_mmcblk0p1(self):
        assert partition_to_number("/dev/mmcblk0p1") == 1

    def test_loop0p1(self):
        assert partition_to_number("/dev/loop0p1") == 1

    def test_invalid_raises(self):
        with pytest.raises(RuntimeError):
            partition_to_number("/dev/mapper/vg-lv")

    def test_invalid_no_number_raises(self):
        with pytest.raises(RuntimeError):
            partition_to_number("not-a-device")


# ---------------------------------------------------------------------------
# partition_to_device  (pure function, no I/O)
# ---------------------------------------------------------------------------


class TestPartitionToDevice:
    def test_sda1(self):
        assert partition_to_device("/dev/sda1") == "/dev/sda"

    def test_nvme0n1p2(self):
        assert partition_to_device("/dev/nvme0n1p2") == "/dev/nvme0n1"

    def test_nbd0p3(self):
        assert partition_to_device("/dev/nbd0p3") == "/dev/nbd0"

    def test_mmcblk0p1(self):
        assert partition_to_device("/dev/mmcblk0p1") == "/dev/mmcblk0"

    def test_loop0p1(self):
        assert partition_to_device("/dev/loop0p1") == "/dev/loop0"

    def test_invalid_raises(self):
        with pytest.raises(RuntimeError):
            partition_to_device("/dev/mapper/vg-lv")


# ---------------------------------------------------------------------------
# VMCraft class  (heavy mocking required due to many imports)
# ---------------------------------------------------------------------------


@pytest.fixture()
def vmcraft_class():
    """Import and return the VMCraft class with _initialize_ops mocked out.

    This avoids importing all the ops classes which would pull in the entire
    dependency tree.
    """
    with patch("hyper2kvm.vmcraft.main.VMCraft._initialize_ops"):
        from hyper2kvm.vmcraft.main import VMCraft

        yield VMCraft


@pytest.fixture()
def vmcraft(vmcraft_class):
    """Return a freshly-constructed VMCraft instance (ops init skipped)."""
    return vmcraft_class()


# ---------------------------------------------------------------------------
# __init__ defaults
# ---------------------------------------------------------------------------


class TestVMCraftInit:
    def test_drives_empty(self, vmcraft):
        assert vmcraft._drives == []

    def test_launched_false(self, vmcraft):
        assert vmcraft._launched is False

    def test_trace_false(self, vmcraft):
        assert vmcraft._trace is False

    def test_return_dict_default(self, vmcraft):
        assert vmcraft._return_dict is True

    def test_nbd_manager_none(self, vmcraft):
        assert vmcraft._nbd_manager is None

    def test_nbd_device_none(self, vmcraft):
        assert vmcraft._nbd_device is None

    def test_mount_root_none(self, vmcraft):
        assert vmcraft._mount_root is None

    def test_custom_return_dict(self, vmcraft_class):
        v = vmcraft_class(python_return_dict=False)
        assert v._return_dict is False

    def test_custom_conversion_dir(self, vmcraft_class, tmp_path):
        v = vmcraft_class(conversion_dir=str(tmp_path))
        assert v._conversion_dir == str(tmp_path)

    def test_custom_allowed_dirs(self, vmcraft_class):
        v = vmcraft_class(allowed_dirs=["/opt", "/data"])
        assert v._allowed_dirs == ["/opt", "/data"]

    def test_container_isolation_default(self, vmcraft):
        assert vmcraft._container_isolation is True

    def test_container_isolation_custom(self, vmcraft_class):
        v = vmcraft_class(container_isolation=False)
        assert v._container_isolation is False

    def test_perf_metrics_empty(self, vmcraft):
        assert vmcraft._perf_metrics == {}


# ---------------------------------------------------------------------------
# add_drive_opts
# ---------------------------------------------------------------------------


class TestAddDriveOpts:
    def test_drive_added(self, vmcraft):
        vmcraft.add_drive_opts("/images/disk.qcow2")
        assert len(vmcraft._drives) == 1
        assert vmcraft._drives[0]["path"] == "/images/disk.qcow2"

    def test_readonly_default(self, vmcraft):
        vmcraft.add_drive_opts("/images/disk.qcow2")
        assert vmcraft._drives[0]["readonly"] is True

    def test_readonly_false(self, vmcraft):
        vmcraft.add_drive_opts("/images/disk.qcow2", readonly=0)
        assert vmcraft._drives[0]["readonly"] is False

    def test_format_param(self, vmcraft):
        vmcraft.add_drive_opts("/images/disk.vmdk", format="vmdk")
        assert vmcraft._drives[0]["format"] == "vmdk"

    def test_format_default_none(self, vmcraft):
        vmcraft.add_drive_opts("/images/disk.qcow2")
        assert vmcraft._drives[0]["format"] is None

    def test_after_launch_raises(self, vmcraft):
        vmcraft._launched = True
        with pytest.raises(RuntimeError, match="Cannot add drives after VMCraft has been launched"):
            vmcraft.add_drive_opts("/images/disk.qcow2")

    def test_multiple_drives(self, vmcraft):
        vmcraft.add_drive_opts("/images/disk1.qcow2")
        vmcraft.add_drive_opts("/images/disk2.qcow2")
        assert len(vmcraft._drives) == 2


# ---------------------------------------------------------------------------
# set_trace
# ---------------------------------------------------------------------------


class TestSetTrace:
    def test_sets_trace_true(self, vmcraft):
        vmcraft.set_trace(True)
        assert vmcraft._trace is True

    def test_sets_logger_level_debug(self, vmcraft):
        vmcraft.set_trace(True)
        assert vmcraft.logger.level == logging.DEBUG

    def test_sets_trace_false(self, vmcraft):
        vmcraft._trace = True
        vmcraft.set_trace(False)
        assert vmcraft._trace is False

    def test_int_truthy_value(self, vmcraft):
        vmcraft.set_trace(1)
        assert vmcraft._trace is True


# ---------------------------------------------------------------------------
# converted_image_path
# ---------------------------------------------------------------------------


class TestConvertedImagePath:
    def test_returns_none_when_no_nbd_manager(self, vmcraft):
        assert vmcraft.converted_image_path is None

    def test_returns_path_from_nbd_manager(self, vmcraft):
        from pathlib import Path

        mgr = MagicMock()
        mgr.converted_image_path = Path("/tmp/converted.qcow2")
        vmcraft._nbd_manager = mgr
        assert vmcraft.converted_image_path == Path("/tmp/converted.qcow2")


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------


class TestSync:
    def test_returns_without_error_when_not_launched(self, vmcraft):
        """sync() should be a no-op when not launched."""
        vmcraft.sync()  # must not raise

    @patch("hyper2kvm.vmcraft.main.os.sync")
    def test_calls_os_sync_when_launched(self, mock_os_sync, vmcraft):
        vmcraft._launched = True
        vmcraft.sync()
        mock_os_sync.assert_called_once()


# ---------------------------------------------------------------------------
# __getattr__
# ---------------------------------------------------------------------------


class TestGetattr:
    def test_raises_attribute_error_for_unknown(self, vmcraft):
        with pytest.raises(AttributeError, match="has no attribute 'nonexistent_method_xyz'"):
            vmcraft.nonexistent_method_xyz

    def test_delegates_to_ops_instance(self, vmcraft):
        """If an ops instance has the attribute, __getattr__ should find it."""
        mock_ops = MagicMock()
        mock_ops.some_method.return_value = 42
        vmcraft._ops_instances = [mock_ops]
        assert vmcraft.some_method() == 42


# ---------------------------------------------------------------------------
# part_to_partnum / part_to_dev  (via VMCraft instance delegation)
# ---------------------------------------------------------------------------


class TestPartToPartnumViaInstance:
    def test_sda1(self, vmcraft):
        assert vmcraft.part_to_partnum("/dev/sda1") == 1

    def test_nvme(self, vmcraft):
        assert vmcraft.part_to_partnum("/dev/nvme0n1p2") == 2

    def test_invalid_raises(self, vmcraft):
        with pytest.raises(RuntimeError):
            vmcraft.part_to_partnum("/dev/mapper/vg-lv")


class TestPartToDevViaInstance:
    def test_sda1(self, vmcraft):
        assert vmcraft.part_to_dev("/dev/sda1") == "/dev/sda"

    def test_nvme(self, vmcraft):
        assert vmcraft.part_to_dev("/dev/nvme0n1p2") == "/dev/nvme0n1"

    def test_invalid_raises(self, vmcraft):
        with pytest.raises(RuntimeError):
            vmcraft.part_to_dev("/dev/mapper/vg-lv")


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestContextManager:
    def test_enter_returns_self(self, vmcraft):
        assert vmcraft.__enter__() is vmcraft

    def test_exit_calls_close(self, vmcraft):
        with patch.object(vmcraft, "close") as mock_close:
            vmcraft.__exit__(None, None, None)
            mock_close.assert_called_once()

    def test_exit_returns_false(self, vmcraft):
        with patch.object(vmcraft, "close"):
            result = vmcraft.__exit__(None, None, None)
            assert result is False

    def test_exit_suppresses_close_exception(self, vmcraft):
        """__exit__ should not propagate exceptions from close()."""
        with patch.object(vmcraft, "close", side_effect=RuntimeError("boom")):
            # Should not raise
            result = vmcraft.__exit__(None, None, None)
            assert result is False
