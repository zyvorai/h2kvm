# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for hyper2kvm.orchestration.disk_processor.DiskProcessor."""

from __future__ import annotations

import types
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from hyper2kvm.orchestration.disk_processor import DiskProcessor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_processor(mock_logger, **overrides):
    """Build a DiskProcessor with a SimpleNamespace args; override any field."""
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


# ---------------------------------------------------------------------------
# _resolve_output_path (static)
# ---------------------------------------------------------------------------


class TestResolveOutputPath:
    """DiskProcessor._resolve_output_path static method."""

    def test_single_disk_uses_to_output_directly(self, tmp_path):
        result = DiskProcessor._resolve_output_path(
            "output.qcow2",
            tmp_path,
            disk_index=0,
            multi=False,
        )
        assert result.name == "output.qcow2"

    def test_multi_disk_appends_disk_index(self, tmp_path):
        result = DiskProcessor._resolve_output_path(
            "output.qcow2",
            tmp_path,
            disk_index=2,
            multi=True,
        )
        assert "_disk2" in result.name
        assert result.suffix == ".qcow2"

    def test_multi_disk_index_zero(self, tmp_path):
        result = DiskProcessor._resolve_output_path(
            "out.raw",
            tmp_path,
            disk_index=0,
            multi=True,
        )
        assert result.name == "out_disk0.raw"

    def test_relative_path_joined_with_out_root(self, tmp_path):
        result = DiskProcessor._resolve_output_path(
            "rel/output.qcow2",
            tmp_path,
            disk_index=0,
            multi=False,
        )
        # Should be under out_root somewhere
        assert str(tmp_path) in str(result)

    def test_absolute_path_used_as_is(self, tmp_path):
        abs_path = "/absolute/output.qcow2"
        result = DiskProcessor._resolve_output_path(
            abs_path,
            tmp_path,
            disk_index=0,
            multi=False,
        )
        assert str(result) == "/absolute/output.qcow2"

    def test_existing_file_gets_timestamp_suffix(self, tmp_path):
        # Create a file so the path "exists"
        existing = tmp_path / "exists.qcow2"
        existing.touch()
        result = DiskProcessor._resolve_output_path(
            str(existing),
            tmp_path,
            disk_index=0,
            multi=False,
        )
        # Should have been renamed with a timestamp, not the original name
        assert result != existing
        assert result.suffix == ".qcow2"
        assert "exists-" in result.name

    def test_nonexistent_file_returns_resolved_path(self, tmp_path):
        result = DiskProcessor._resolve_output_path(
            "new.qcow2",
            tmp_path,
            disk_index=0,
            multi=False,
        )
        assert result.is_absolute()


# ---------------------------------------------------------------------------
# _throttled_progress_logger (static)
# ---------------------------------------------------------------------------


class TestThrottledProgressLogger:
    """DiskProcessor._throttled_progress_logger static method."""

    def test_returns_callable(self, mock_logger):
        cb = DiskProcessor._throttled_progress_logger(mock_logger)
        assert callable(cb)

    def test_logs_progress_at_step_boundaries(self, mock_logger):
        cb = DiskProcessor._throttled_progress_logger(mock_logger, step_pct=50)
        cb(0.0)  # bucket 0
        cb(0.5)  # bucket 1
        assert mock_logger.info.call_count == 2

    def test_deduplicates_same_bucket(self, mock_logger):
        cb = DiskProcessor._throttled_progress_logger(mock_logger, step_pct=10)
        cb(0.01)  # bucket 0
        cb(0.05)  # bucket 0 again
        # Only one log call since both map to bucket 0
        assert mock_logger.info.call_count == 1

    def test_logs_complete_at_100_percent(self, mock_logger):
        cb = DiskProcessor._throttled_progress_logger(mock_logger, step_pct=50)
        cb(1.0)
        call_arg = mock_logger.info.call_args[0][0]
        assert "complete" in call_arg.lower() or "complete" in str(call_arg).lower()

    def test_progress_below_100_shows_percentage(self, mock_logger):
        cb = DiskProcessor._throttled_progress_logger(mock_logger, step_pct=10)
        cb(0.3)
        call_arg = mock_logger.info.call_args[0][0]
        assert "30" in call_arg or "progress" in call_arg.lower()

    def test_step_pct_zero_defaults_to_five(self, mock_logger):
        """step_pct <= 0 should be clamped to 5."""
        cb = DiskProcessor._throttled_progress_logger(mock_logger, step_pct=0)
        # Exercise it -- should not raise
        cb(0.0)
        cb(0.05)
        assert mock_logger.info.call_count == 2


# ---------------------------------------------------------------------------
# _choose_workdir (instance)
# ---------------------------------------------------------------------------


class TestChooseWorkdir:
    """DiskProcessor._choose_workdir instance method."""

    def test_uses_config_workdir_when_set(self, mock_logger, tmp_path):
        workdir = tmp_path / "custom_work"
        proc = _make_processor(mock_logger, workdir=str(workdir))
        result = proc._choose_workdir(tmp_path)
        assert result == workdir.expanduser().resolve()

    def test_defaults_to_out_root_slash_work(self, mock_logger, tmp_path):
        proc = _make_processor(mock_logger, workdir=None)
        result = proc._choose_workdir(tmp_path)
        assert result == tmp_path / "work"

    def test_workdir_tilde_expanded(self, mock_logger):
        proc = _make_processor(mock_logger, workdir="~/my_work")
        result = proc._choose_workdir(Path("/out"))
        assert "~" not in str(result)
        assert result.is_absolute()


# ---------------------------------------------------------------------------
# _is_luks_enabled (instance -- delegates to config)
# ---------------------------------------------------------------------------


class TestIsLuksEnabled:
    """DiskProcessor._is_luks_enabled delegates to config.is_luks_enabled()."""

    def test_delegates_true_when_flag(self, mock_logger):
        proc = _make_processor(mock_logger, luks_enable=True)
        assert proc._is_luks_enabled() is True

    def test_delegates_true_when_passphrase(self, mock_logger):
        proc = _make_processor(mock_logger, luks_passphrase="pw")
        assert proc._is_luks_enabled() is True

    def test_delegates_true_when_env(self, mock_logger):
        proc = _make_processor(mock_logger, luks_passphrase_env="ENV")
        assert proc._is_luks_enabled() is True

    def test_delegates_true_when_keyfile(self, mock_logger):
        proc = _make_processor(mock_logger, luks_keyfile="/k")
        assert proc._is_luks_enabled() is True

    def test_delegates_false_when_none(self, mock_logger):
        proc = _make_processor(mock_logger)
        assert proc._is_luks_enabled() is False
