# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for hyper2kvm/converters/qemu/converter.py (ConvertOptions, _build_convert_cmd, _fallback_plan, validate)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from hyper2kvm.converters.qemu.converter import Convert


# ---------------------------------------------------------------------------
# ConvertOptions
# ---------------------------------------------------------------------------


class TestConvertOptionsDefaults:
    """ConvertOptions frozen dataclass defaults."""

    def test_default_cache_mode(self):
        opts = Convert.ConvertOptions()
        assert opts.cache_mode == "none"

    def test_default_threads(self):
        opts = Convert.ConvertOptions()
        assert opts.threads is None

    def test_default_compression_type(self):
        opts = Convert.ConvertOptions()
        assert opts.compression_type == "zstd"

    def test_default_compression_level(self):
        opts = Convert.ConvertOptions()
        assert opts.compression_level is None

    def test_default_preallocation(self):
        opts = Convert.ConvertOptions()
        assert opts.preallocation is None

    def test_custom_values(self):
        opts = Convert.ConvertOptions(
            cache_mode="writeback",
            threads=4,
            compression_type="zlib",
            compression_level=6,
            preallocation="metadata",
        )
        assert opts.cache_mode == "writeback"
        assert opts.threads == 4
        assert opts.compression_type == "zlib"
        assert opts.compression_level == 6
        assert opts.preallocation == "metadata"

    def test_frozen_raises_on_assignment(self):
        opts = Convert.ConvertOptions()
        with pytest.raises(AttributeError):
            opts.cache_mode = "writeback"  # type: ignore[misc]

    def test_short_defaults(self):
        opts = Convert.ConvertOptions()
        s = opts.short()
        assert "cache=none" in s
        assert "threads=off" in s
        assert "ctype=zstd" in s
        assert "clevel=omit" in s
        assert "prealloc=omit" in s

    def test_short_custom(self):
        opts = Convert.ConvertOptions(
            cache_mode="",
            threads=8,
            compression_type=None,
            compression_level=3,
            preallocation="full",
        )
        s = opts.short()
        assert "cache=off" in s
        assert "threads=8" in s
        assert "ctype=omit" in s
        assert "clevel=3" in s
        assert "prealloc=full" in s


# ---------------------------------------------------------------------------
# _build_convert_cmd
# ---------------------------------------------------------------------------


class TestBuildConvertCmd:
    """Static method that assembles the qemu-img convert command list."""

    def _build(self, **kwargs):
        defaults = dict(
            src=Path("/tmp/src.vmdk"),
            dst=Path("/tmp/dst.qcow2"),
            in_format=None,
            out_format="qcow2",
            compress=False,
            opt=Convert.ConvertOptions(),
        )
        defaults.update(kwargs)
        return Convert._build_convert_cmd(**defaults)

    def test_basic_command_structure(self):
        cmd = self._build()
        assert cmd[0:3] == ["qemu-img", "convert", "-p"]
        assert "-O" in cmd
        idx = cmd.index("-O")
        assert cmd[idx + 1] == "qcow2"
        assert cmd[-2] == "/tmp/src.vmdk"
        assert cmd[-1] == "/tmp/dst.qcow2"

    def test_cache_mode_adds_t_flags(self):
        cmd = self._build(opt=Convert.ConvertOptions(cache_mode="none"))
        assert "-t" in cmd
        assert "-T" in cmd
        t_idx = cmd.index("-t")
        assert cmd[t_idx + 1] == "none"
        big_t_idx = cmd.index("-T")
        assert cmd[big_t_idx + 1] == "none"

    def test_empty_cache_mode_omits_t_flags(self):
        cmd = self._build(opt=Convert.ConvertOptions(cache_mode=""))
        assert "-t" not in cmd
        assert "-T" not in cmd

    def test_threads_adds_m_flag(self):
        cmd = self._build(opt=Convert.ConvertOptions(threads=4))
        assert "-m" in cmd
        m_idx = cmd.index("-m")
        assert cmd[m_idx + 1] == "4"

    def test_no_threads_omits_m_flag(self):
        cmd = self._build(opt=Convert.ConvertOptions(threads=None))
        assert "-m" not in cmd

    def test_in_format_adds_f_flag(self):
        cmd = self._build(in_format="vmdk")
        assert "-f" in cmd
        f_idx = cmd.index("-f")
        assert cmd[f_idx + 1] == "vmdk"

    def test_no_in_format_omits_f_flag(self):
        cmd = self._build(in_format=None)
        assert "-f" not in cmd

    def test_qcow2_compress_adds_c_flag(self):
        cmd = self._build(out_format="qcow2", compress=True)
        assert "-c" in cmd

    def test_qcow2_compress_adds_compression_type(self):
        opt = Convert.ConvertOptions(compression_type="zstd")
        cmd = self._build(out_format="qcow2", compress=True, opt=opt)
        assert "-o" in cmd
        o_idx = cmd.index("-o")
        assert "compression_type=zstd" in cmd[o_idx + 1]

    def test_qcow2_compress_adds_compression_level(self):
        opt = Convert.ConvertOptions(compression_type="zlib", compression_level=6)
        cmd = self._build(out_format="qcow2", compress=True, opt=opt)
        o_idx = cmd.index("-o")
        assert "compression_level=6" in cmd[o_idx + 1]

    def test_qcow2_no_compress_omits_c_flag(self):
        cmd = self._build(out_format="qcow2", compress=False)
        assert "-c" not in cmd

    def test_non_qcow2_compress_omits_c_flag(self):
        cmd = self._build(out_format="raw", compress=True)
        assert "-c" not in cmd

    def test_preallocation_in_o_option(self):
        opt = Convert.ConvertOptions(preallocation="metadata")
        cmd = self._build(out_format="qcow2", compress=False, opt=opt)
        assert "-o" in cmd
        o_idx = cmd.index("-o")
        assert "preallocation=metadata" in cmd[o_idx + 1]


# ---------------------------------------------------------------------------
# _fallback_plan
# ---------------------------------------------------------------------------


class TestFallbackPlan:
    """Static method that yields progressively simpler ConvertOptions."""

    def test_first_item_is_base(self):
        base = Convert.ConvertOptions(cache_mode="none", threads=4, compression_type="zstd")
        plan = list(Convert._fallback_plan(base, out_format="qcow2", compress=True))
        assert plan[0] is base

    def test_last_item_is_minimal(self):
        base = Convert.ConvertOptions(cache_mode="none", threads=4, compression_type="zstd")
        plan = list(Convert._fallback_plan(base, out_format="qcow2", compress=True))
        last = plan[-1]
        assert last.cache_mode == ""
        assert last.threads is None
        assert last.compression_type is None
        assert last.compression_level is None
        assert last.preallocation is None

    def test_deduplicates(self):
        # If base is already minimal, plan should not repeat it
        minimal = Convert.ConvertOptions(
            cache_mode="",
            threads=None,
            compression_type=None,
            compression_level=None,
            preallocation=None,
        )
        plan = list(Convert._fallback_plan(minimal, out_format="raw", compress=False))
        keys = [
            (o.cache_mode, o.threads, o.compression_type, o.compression_level, o.preallocation) for o in plan
        ]
        assert len(keys) == len(set(keys))

    def test_qcow2_compress_zstd_includes_zlib_fallback(self):
        base = Convert.ConvertOptions(compression_type="zstd")
        plan = list(Convert._fallback_plan(base, out_format="qcow2", compress=True))
        ctypes = [o.compression_type for o in plan]
        assert "zlib" in ctypes

    def test_raw_format_no_compress_plan(self):
        base = Convert.ConvertOptions()
        plan = list(Convert._fallback_plan(base, out_format="raw", compress=False))
        # Should have at least base + minimal
        assert len(plan) >= 2


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


class TestValidate:
    """Convert.validate: mock subprocess, U.which, U.run_cmd."""

    @patch.object(Convert, "_prefer_descriptor_for_flat", side_effect=lambda _l, p: p)
    @patch("hyper2kvm.converters.qemu.converter.U")
    def test_validate_success(self, mock_u, _mock_pref, mock_logger, tmp_path):
        img = tmp_path / "disk.qcow2"
        img.write_bytes(b"\x00" * 64)

        cp = MagicMock()
        cp.returncode = 0
        cp.stdout = ""
        cp.stderr = ""
        mock_u.which.return_value = "/usr/bin/qemu-img"
        mock_u.run_cmd.return_value = cp

        Convert.validate(mock_logger, img)

        mock_u.run_cmd.assert_called_once()
        args = mock_u.run_cmd.call_args
        assert args[0][1] == ["qemu-img", "check", str(img)]
        mock_logger.info.assert_called()

    @patch.object(Convert, "_prefer_descriptor_for_flat", side_effect=lambda _l, p: p)
    def test_validate_file_not_found(self, _mock_pref, mock_logger):
        missing = Path("/nonexistent/disk.qcow2")
        Convert.validate(mock_logger, missing)
        mock_logger.warning.assert_called()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "not found" in warning_msg.lower()

    @patch.object(Convert, "_prefer_descriptor_for_flat", side_effect=lambda _l, p: p)
    @patch("hyper2kvm.converters.qemu.converter.U")
    def test_validate_check_failure_strict(self, mock_u, _mock_pref, mock_logger, tmp_path):
        from hyper2kvm.core.exceptions import DiskConversionError

        img = tmp_path / "disk.qcow2"
        img.write_bytes(b"\x00" * 64)

        cp = MagicMock()
        cp.returncode = 3
        cp.stdout = "bad"
        cp.stderr = "corrupt"
        mock_u.which.return_value = "/usr/bin/qemu-img"
        mock_u.run_cmd.return_value = cp

        with pytest.raises(DiskConversionError):
            Convert.validate(mock_logger, img, strict=True)

    @patch.object(Convert, "_prefer_descriptor_for_flat", side_effect=lambda _l, p: p)
    @patch("hyper2kvm.converters.qemu.converter.U")
    def test_validate_check_failure_non_strict_warns(self, mock_u, _mock_pref, mock_logger, tmp_path):
        img = tmp_path / "disk.qcow2"
        img.write_bytes(b"\x00" * 64)

        cp = MagicMock()
        cp.returncode = 3
        cp.stdout = ""
        cp.stderr = "x"
        mock_u.which.return_value = "/usr/bin/qemu-img"
        mock_u.run_cmd.return_value = cp

        Convert.validate(mock_logger, img, strict=False)
        mock_logger.warning.assert_called()
        img = tmp_path / "disk.qcow2"
        img.write_bytes(b"\x00" * 64)
        mock_u.which.return_value = None

        Convert.validate(mock_logger, img)

        mock_logger.warning.assert_called()
        mock_u.run_cmd.assert_not_called()
