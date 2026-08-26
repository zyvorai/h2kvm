# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for hyper2kvm.orchestration.disk_discovery.DiskDiscovery."""

from __future__ import annotations

import types
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from hyper2kvm.core.exceptions import Fatal
from hyper2kvm.orchestration.disk_discovery import DiskDiscovery


# ---------------------------------------------------------------------------
# _normalize_ssh_opts (static)
# ---------------------------------------------------------------------------


class TestNormalizeSshOpts:
    """DiskDiscovery._normalize_ssh_opts static method."""

    def test_none_returns_none(self):
        assert DiskDiscovery._normalize_ssh_opts(None) is None

    def test_string_returns_single_element_list(self):
        result = DiskDiscovery._normalize_ssh_opts("foo")
        assert result == ["foo"]

    def test_list_returns_same_list(self):
        result = DiskDiscovery._normalize_ssh_opts(["a", "b"])
        assert result == ["a", "b"]

    def test_empty_list_returns_none(self):
        result = DiskDiscovery._normalize_ssh_opts([])
        assert result is None

    def test_list_with_none_filtered(self):
        result = DiskDiscovery._normalize_ssh_opts([None, "a"])
        assert result == ["a"]

    def test_list_all_none_returns_none(self):
        result = DiskDiscovery._normalize_ssh_opts([None, None])
        assert result is None

    def test_tuple_treated_as_sequence(self):
        result = DiskDiscovery._normalize_ssh_opts(("x", "y"))
        assert result == ["x", "y"]

    def test_integer_coerced_to_string(self):
        result = DiskDiscovery._normalize_ssh_opts(42)
        assert result == ["42"]


# ---------------------------------------------------------------------------
# discover -- dispatch tests
# ---------------------------------------------------------------------------


class TestDiscoverDispatch:
    """DiskDiscovery.discover dispatches to correct handler based on cmd."""

    def test_cmd_local_calls_discover_local(self, mock_logger, tmp_path):
        args = types.SimpleNamespace(cmd="local")
        dd = DiskDiscovery(mock_logger, args)
        with patch.object(dd, "_discover_local", return_value=([tmp_path / "d.vmdk"], None)) as m:
            disks, temp = dd.discover(tmp_path)
            m.assert_called_once_with(tmp_path)
        assert len(disks) == 1

    def test_cmd_none_calls_die(self, mock_logger, tmp_path):
        args = types.SimpleNamespace(cmd=None)
        dd = DiskDiscovery(mock_logger, args)
        with pytest.raises(Fatal):
            dd.discover(tmp_path)

    def test_cmd_unknown_calls_die(self, mock_logger, tmp_path):
        args = types.SimpleNamespace(cmd="not-a-real-cmd")
        dd = DiskDiscovery(mock_logger, args)
        with pytest.raises(Fatal):
            dd.discover(tmp_path)

    def test_cmd_daemon_returns_empty(self, mock_logger, tmp_path):
        args = types.SimpleNamespace(cmd="daemon")
        dd = DiskDiscovery(mock_logger, args)
        disks, temp = dd.discover(tmp_path)
        assert disks == []
        assert temp is None

    def test_cmd_generate_systemd_returns_empty(self, mock_logger, tmp_path):
        args = types.SimpleNamespace(cmd="generate-systemd")
        dd = DiskDiscovery(mock_logger, args)
        disks, temp = dd.discover(tmp_path)
        assert disks == []
        assert temp is None


# ---------------------------------------------------------------------------
# discover -- handler map keys
# ---------------------------------------------------------------------------


class TestHandlerMap:
    """The internal handler dispatch map has all expected keys."""

    def test_handler_map_has_expected_keys(self, mock_logger):
        args = types.SimpleNamespace(cmd="daemon")
        dd = DiskDiscovery(mock_logger, args)

        expected_keys = {
            "local",
            "fetch-and-fix",
            "ova",
            "ovf",
            "vhd",
            "raw",
            "ami",
            "live-fix",
            "libvirt-xml",
            "daemon",
            "generate-systemd",
        }

        # We can't directly access the handlers dict since it's built inside
        # discover(). Instead, verify that each expected cmd dispatches without
        # hitting the "Unknown command" U.die path.  We patch the private
        # handler methods so they don't do real I/O.
        sentinel = ([Path("/fake")], None)

        with (
            patch.object(dd, "_discover_local", return_value=sentinel),
            patch.object(dd, "_discover_fetch_and_fix", return_value=sentinel),
            patch.object(dd, "_discover_ova", return_value=sentinel),
            patch.object(dd, "_discover_ovf", return_value=sentinel),
            patch.object(dd, "_discover_vhd", return_value=sentinel),
            patch.object(dd, "_discover_raw", return_value=sentinel),
            patch.object(dd, "_discover_ami", return_value=sentinel),
            patch.object(dd, "_discover_live_fix", return_value=sentinel),
            patch.object(dd, "_discover_libvirt_xml", return_value=sentinel),
        ):
            for cmd in expected_keys:
                dd.args.cmd = cmd
                disks, _ = dd.discover(Path("/out"))
                # Should not raise -- handler is found
                assert isinstance(disks, list)

    def test_handler_map_rejects_unknown_key(self, mock_logger):
        args = types.SimpleNamespace(cmd="bogus-handler")
        dd = DiskDiscovery(mock_logger, args)
        with pytest.raises(Fatal):
            dd.discover(Path("/out"))
