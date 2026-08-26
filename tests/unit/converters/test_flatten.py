# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for h2kvm/converters/flatten.py (Flatten static helpers)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from h2kvm.converters.flatten import Flatten


# ---------------------------------------------------------------------------
# _qemu_img_info
# ---------------------------------------------------------------------------


class TestQemuImgInfo:
    """Flatten._qemu_img_info: runs qemu-img info --output=json, returns dict."""

    @patch("h2kvm.converters.flatten.subprocess.run")
    def test_returns_parsed_json(self, mock_run, mock_logger):
        payload = {"format": "vmdk", "virtual-size": 10737418240}
        cp = MagicMock()
        cp.stdout = json.dumps(payload)
        mock_run.return_value = cp

        result = Flatten._qemu_img_info(mock_logger, Path("/tmp/disk.vmdk"))

        assert result["format"] == "vmdk"
        assert result["virtual-size"] == 10737418240
        mock_run.assert_called_once()

    @patch("h2kvm.converters.flatten.subprocess.run")
    def test_returns_empty_dict_on_failure(self, mock_run, mock_logger):
        mock_run.side_effect = subprocess.CalledProcessError(1, "qemu-img")

        result = Flatten._qemu_img_info(mock_logger, Path("/tmp/bad.vmdk"))

        assert result == {}

    @patch("h2kvm.converters.flatten.subprocess.run")
    def test_returns_empty_dict_on_non_dict_json(self, mock_run, mock_logger):
        cp = MagicMock()
        cp.stdout = '"just a string"'
        mock_run.return_value = cp

        result = Flatten._qemu_img_info(mock_logger, Path("/tmp/disk.vmdk"))

        assert result == {}

    @patch("h2kvm.converters.flatten.subprocess.run")
    def test_calls_correct_command(self, mock_run, mock_logger):
        cp = MagicMock()
        cp.stdout = "{}"
        mock_run.return_value = cp

        Flatten._qemu_img_info(mock_logger, Path("/images/test.vhd"))

        args, kwargs = mock_run.call_args
        assert args[0] == ["qemu-img", "info", "--output=json", "/images/test.vhd"]
        assert kwargs["check"] is True
        assert kwargs["capture_output"] is True


# ---------------------------------------------------------------------------
# _qemu_img_virtual_size
# ---------------------------------------------------------------------------


class TestQemuImgVirtualSize:
    """Flatten._qemu_img_virtual_size: extracts virtual-size int."""

    @patch.object(Flatten, "_qemu_img_info")
    def test_returns_virtual_size(self, mock_info, mock_logger):
        mock_info.return_value = {"format": "vmdk", "virtual-size": 5368709120}

        result = Flatten._qemu_img_virtual_size(mock_logger, Path("/tmp/disk.vmdk"))

        assert result == 5368709120

    @patch.object(Flatten, "_qemu_img_info")
    def test_returns_zero_on_missing_key(self, mock_info, mock_logger):
        mock_info.return_value = {"format": "vmdk"}

        result = Flatten._qemu_img_virtual_size(mock_logger, Path("/tmp/disk.vmdk"))

        assert result == 0

    @patch.object(Flatten, "_qemu_img_info")
    def test_returns_zero_on_failure(self, mock_info, mock_logger):
        mock_info.side_effect = Exception("boom")

        result = Flatten._qemu_img_virtual_size(mock_logger, Path("/tmp/disk.vmdk"))

        assert result == 0


# ---------------------------------------------------------------------------
# _fast_path_flat
# ---------------------------------------------------------------------------


class TestFastPathFlat:
    """Flatten._fast_path_flat: checks for small VMDK descriptor with FLAT extent."""

    def test_file_too_large_returns_none(self, mock_logger, tmp_path):
        big = tmp_path / "big.vmdk"
        big.write_bytes(b"x" * (3 * 1024 * 1024))  # 3 MiB > 2 MiB threshold

        result = Flatten._fast_path_flat(mock_logger, big, tmp_path / "out", "qcow2")

        assert result is None

    def test_no_flat_line_returns_none(self, mock_logger, tmp_path):
        desc = tmp_path / "disk.vmdk"
        desc.write_text("# Disk descriptor\n# no FLAT line here\n")

        result = Flatten._fast_path_flat(mock_logger, desc, tmp_path / "out", "qcow2")

        assert result is None

    def test_flat_line_but_extent_missing_returns_none(self, mock_logger, tmp_path):
        desc = tmp_path / "disk.vmdk"
        desc.write_text('# Disk DescriptorFile\nRW 20971520 FLAT "disk-flat.vmdk" 0\n')
        # Do NOT create disk-flat.vmdk

        result = Flatten._fast_path_flat(mock_logger, desc, tmp_path / "out", "qcow2")

        assert result is None

    def test_nonexistent_src_returns_none(self, mock_logger, tmp_path):
        result = Flatten._fast_path_flat(mock_logger, tmp_path / "nope.vmdk", tmp_path / "out", "qcow2")
        assert result is None


# ---------------------------------------------------------------------------
# _flatten_cmd_attempts
# ---------------------------------------------------------------------------


class TestFlattenCmdAttempts:
    """Flatten._flatten_cmd_attempts: returns list of command lists."""

    def test_returns_two_attempts(self):
        attempts = Flatten._flatten_cmd_attempts(
            src=Path("/tmp/src.vmdk"),
            tmp_dst=Path("/tmp/dst.qcow2.part"),
            fmt="qcow2",
            in_fmt="vmdk",
        )
        assert len(attempts) == 2

    def test_first_attempt_has_cache_bypass(self):
        attempts = Flatten._flatten_cmd_attempts(
            src=Path("/tmp/src.vmdk"),
            tmp_dst=Path("/tmp/dst.qcow2.part"),
            fmt="qcow2",
            in_fmt="vmdk",
        )
        first = attempts[0]
        assert "-t" in first
        assert "none" in first
        assert "-T" in first

    def test_second_attempt_no_cache_flags(self):
        attempts = Flatten._flatten_cmd_attempts(
            src=Path("/tmp/src.vmdk"),
            tmp_dst=Path("/tmp/dst.qcow2.part"),
            fmt="qcow2",
            in_fmt="vmdk",
        )
        second = attempts[1]
        assert "-t" not in second
        assert "-T" not in second

    def test_with_in_fmt_adds_f_flag(self):
        attempts = Flatten._flatten_cmd_attempts(
            src=Path("/tmp/src.vmdk"),
            tmp_dst=Path("/tmp/dst.qcow2.part"),
            fmt="qcow2",
            in_fmt="vmdk",
        )
        for cmd in attempts:
            assert "-f" in cmd
            f_idx = cmd.index("-f")
            assert cmd[f_idx + 1] == "vmdk"

    def test_without_in_fmt_no_f_flag(self):
        attempts = Flatten._flatten_cmd_attempts(
            src=Path("/tmp/src.vmdk"),
            tmp_dst=Path("/tmp/dst.qcow2.part"),
            fmt="qcow2",
            in_fmt=None,
        )
        for cmd in attempts:
            assert "-f" not in cmd

    def test_output_format_in_command(self):
        attempts = Flatten._flatten_cmd_attempts(
            src=Path("/tmp/src.vmdk"),
            tmp_dst=Path("/tmp/dst.raw.part"),
            fmt="raw",
            in_fmt=None,
        )
        for cmd in attempts:
            o_idx = cmd.index("-O")
            assert cmd[o_idx + 1] == "raw"

    def test_src_and_dst_at_end(self):
        src = Path("/tmp/src.vmdk")
        dst = Path("/tmp/dst.qcow2.part")
        attempts = Flatten._flatten_cmd_attempts(
            src=src,
            tmp_dst=dst,
            fmt="qcow2",
            in_fmt=None,
        )
        for cmd in attempts:
            assert cmd[-2] == str(src)
            assert cmd[-1] == str(dst)


# ---------------------------------------------------------------------------
# _raw_to_fmt_cmd_attempts
# ---------------------------------------------------------------------------


class TestRawToFmtCmdAttempts:
    """Flatten._raw_to_fmt_cmd_attempts: returns commands for raw conversion."""

    def test_returns_two_attempts(self):
        attempts = Flatten._raw_to_fmt_cmd_attempts(
            raw_src=Path("/tmp/flat.raw"),
            tmp_dst=Path("/tmp/dst.qcow2.part"),
            fmt="qcow2",
        )
        assert len(attempts) == 2

    def test_always_has_f_raw(self):
        attempts = Flatten._raw_to_fmt_cmd_attempts(
            raw_src=Path("/tmp/flat.raw"),
            tmp_dst=Path("/tmp/dst.qcow2.part"),
            fmt="qcow2",
        )
        for cmd in attempts:
            assert "-f" in cmd
            f_idx = cmd.index("-f")
            assert cmd[f_idx + 1] == "raw"

    def test_first_attempt_has_cache_bypass(self):
        attempts = Flatten._raw_to_fmt_cmd_attempts(
            raw_src=Path("/tmp/flat.raw"),
            tmp_dst=Path("/tmp/dst.qcow2.part"),
            fmt="qcow2",
        )
        first = attempts[0]
        assert "-t" in first
        assert "-T" in first

    def test_second_attempt_no_cache_flags(self):
        attempts = Flatten._raw_to_fmt_cmd_attempts(
            raw_src=Path("/tmp/flat.raw"),
            tmp_dst=Path("/tmp/dst.qcow2.part"),
            fmt="qcow2",
        )
        second = attempts[1]
        assert "-t" not in second
        assert "-T" not in second
