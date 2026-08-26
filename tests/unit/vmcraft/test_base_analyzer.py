# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for h2kvm.vmcraft.base_analyzer.BaseAnalyzer."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from h2kvm.vmcraft.base_analyzer import BaseAnalyzer


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestBaseAnalyzerInit:
    """Verify that __init__ stores all three dependencies."""

    def test_stores_logger(self, mock_logger, mock_file_ops, mock_mount_root):
        analyzer = BaseAnalyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert analyzer.logger is mock_logger

    def test_stores_file_ops(self, mock_logger, mock_file_ops, mock_mount_root):
        analyzer = BaseAnalyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert analyzer.file_ops is mock_file_ops

    def test_stores_mount_root(self, mock_logger, mock_file_ops, mock_mount_root):
        analyzer = BaseAnalyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert analyzer.mount_root is mock_mount_root


# ---------------------------------------------------------------------------
# _check_exists
# ---------------------------------------------------------------------------


class TestCheckExists:
    def test_returns_true_when_exists(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.exists.return_value = True
        analyzer = BaseAnalyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert analyzer._check_exists("/etc/fstab") is True
        mock_file_ops.exists.assert_called_once_with("/etc/fstab")

    def test_returns_false_when_missing(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.exists.return_value = False
        analyzer = BaseAnalyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert analyzer._check_exists("/nonexistent") is False


# ---------------------------------------------------------------------------
# _is_dir
# ---------------------------------------------------------------------------


class TestIsDir:
    def test_delegates_true(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.is_dir.return_value = True
        analyzer = BaseAnalyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert analyzer._is_dir("/var") is True
        mock_file_ops.is_dir.assert_called_once_with("/var")

    def test_delegates_false(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.is_dir.return_value = False
        analyzer = BaseAnalyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert analyzer._is_dir("/not_a_dir") is False


# ---------------------------------------------------------------------------
# _is_file
# ---------------------------------------------------------------------------


class TestIsFile:
    def test_delegates_true(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.is_file.return_value = True
        analyzer = BaseAnalyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert analyzer._is_file("/etc/passwd") is True
        mock_file_ops.is_file.assert_called_once_with("/etc/passwd")

    def test_delegates_false(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.is_file.return_value = False
        analyzer = BaseAnalyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert analyzer._is_file("/var") is False


# ---------------------------------------------------------------------------
# _read_file
# ---------------------------------------------------------------------------


class TestReadFile:
    def test_returns_file_content(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.cat.return_value = "root:x:0:0:root:/root:/bin/bash"
        analyzer = BaseAnalyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert analyzer._read_file("/etc/passwd") == "root:x:0:0:root:/root:/bin/bash"
        mock_file_ops.cat.assert_called_once_with("/etc/passwd")

    def test_propagates_exception(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.cat.side_effect = FileNotFoundError("no such file")
        analyzer = BaseAnalyzer(mock_logger, mock_file_ops, mock_mount_root)
        with pytest.raises(FileNotFoundError):
            analyzer._read_file("/missing")


# ---------------------------------------------------------------------------
# _read_lines
# ---------------------------------------------------------------------------


class TestReadLines:
    def test_splits_content(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.cat.return_value = "line1\nline2\nline3"
        analyzer = BaseAnalyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert analyzer._read_lines("/etc/hosts") == ["line1", "line2", "line3"]

    def test_empty_content(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.cat.return_value = ""
        analyzer = BaseAnalyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert analyzer._read_lines("/empty") == []


# ---------------------------------------------------------------------------
# _list_dir
# ---------------------------------------------------------------------------


class TestListDir:
    def test_delegates(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.ls.return_value = ["a", "b", "c"]
        analyzer = BaseAnalyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert analyzer._list_dir("/var/lib") == ["a", "b", "c"]
        mock_file_ops.ls.assert_called_once_with("/var/lib")


# ---------------------------------------------------------------------------
# _safe_read
# ---------------------------------------------------------------------------


class TestSafeRead:
    def test_returns_content_on_success(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.cat.return_value = "hello"
        analyzer = BaseAnalyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert analyzer._safe_read("/ok") == "hello"

    def test_returns_default_on_exception(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.cat.side_effect = OSError("read error")
        analyzer = BaseAnalyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert analyzer._safe_read("/bad") == ""

    def test_returns_custom_default(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.cat.side_effect = OSError("oops")
        analyzer = BaseAnalyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert analyzer._safe_read("/bad", default="fallback") == "fallback"


# ---------------------------------------------------------------------------
# _safe_read_lines
# ---------------------------------------------------------------------------


class TestSafeReadLines:
    def test_returns_lines_on_success(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.cat.return_value = "a\nb\nc"
        analyzer = BaseAnalyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert analyzer._safe_read_lines("/ok") == ["a", "b", "c"]

    def test_none_default_becomes_empty_list(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.cat.side_effect = OSError("fail")
        analyzer = BaseAnalyzer(mock_logger, mock_file_ops, mock_mount_root)
        result = analyzer._safe_read_lines("/bad")
        assert result == []

    def test_custom_default_list(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.cat.side_effect = OSError("fail")
        analyzer = BaseAnalyzer(mock_logger, mock_file_ops, mock_mount_root)
        result = analyzer._safe_read_lines("/bad", default=["x", "y"])
        assert result == ["x", "y"]

    def test_empty_content_returns_empty_list(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.cat.return_value = ""
        analyzer = BaseAnalyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert analyzer._safe_read_lines("/empty") == []


# ---------------------------------------------------------------------------
# Subclassing
# ---------------------------------------------------------------------------


class TestSubclassing:
    def test_subclass_inherits_init(self, mock_logger, mock_file_ops, mock_mount_root):
        class MyAnalyzer(BaseAnalyzer):
            def custom_method(self):
                return "custom"

        sub = MyAnalyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert sub.logger is mock_logger
        assert sub.file_ops is mock_file_ops
        assert sub.mount_root is mock_mount_root
        assert sub.custom_method() == "custom"

    def test_subclass_can_use_base_methods(self, mock_logger, mock_file_ops, mock_mount_root):
        class Checker(BaseAnalyzer):
            def check(self, path):
                return self._check_exists(path)

        mock_file_ops.exists.return_value = True
        checker = Checker(mock_logger, mock_file_ops, mock_mount_root)
        assert checker.check("/etc/os-release") is True
