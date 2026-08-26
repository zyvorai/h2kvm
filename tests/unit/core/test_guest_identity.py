# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for guest_identity: GuestType, GuestIdentity, GuestDetector, emit_guest_identity_log."""

from __future__ import annotations

from unittest.mock import Mock, call

import pytest

from h2kvm.core.guest_identity import (
    GuestDetector,
    GuestIdentity,
    GuestType,
    _fmt_table,
    emit_guest_identity_log,
)


# ---------------------------------------------------------------------------
# GuestType enum
# ---------------------------------------------------------------------------


class TestGuestType:
    def test_linux_value(self):
        assert GuestType.LINUX.value == "linux"

    def test_windows_value(self):
        assert GuestType.WINDOWS.value == "windows"

    def test_bsd_value(self):
        assert GuestType.BSD.value == "bsd"

    def test_macos_value(self):
        assert GuestType.MACOS.value == "macos"

    def test_unknown_value(self):
        assert GuestType.UNKNOWN.value == "unknown"

    def test_from_string_linux(self):
        assert GuestType.from_string("linux") == GuestType.LINUX

    def test_from_string_case_insensitive(self):
        assert GuestType.from_string("LINUX") == GuestType.LINUX
        assert GuestType.from_string("Linux") == GuestType.LINUX

    def test_from_string_windows(self):
        assert GuestType.from_string("windows") == GuestType.WINDOWS

    def test_from_string_bsd(self):
        assert GuestType.from_string("bsd") == GuestType.BSD

    def test_from_string_macos(self):
        assert GuestType.from_string("macos") == GuestType.MACOS

    def test_from_string_unknown_for_unmatched(self):
        assert GuestType.from_string("solaris") == GuestType.UNKNOWN

    def test_from_string_empty(self):
        assert GuestType.from_string("") == GuestType.UNKNOWN

    def test_from_string_none(self):
        assert GuestType.from_string(None) == GuestType.UNKNOWN

    def test_from_string_whitespace(self):
        assert GuestType.from_string("  linux  ") == GuestType.LINUX


# ---------------------------------------------------------------------------
# GuestIdentity dataclass
# ---------------------------------------------------------------------------


class TestGuestIdentity:
    def test_defaults(self):
        ident = GuestIdentity()
        assert ident.type == GuestType.UNKNOWN
        assert ident.hostname is None
        assert ident.machine_id is None
        assert ident.os_name is None
        assert ident.os_pretty_name is None
        assert ident.os_version is None
        assert ident.architecture is None
        assert ident.kernel_version is None
        assert ident.cpe_name is None
        assert ident.support_end is None
        assert ident.windows_major is None
        assert ident.windows_minor is None
        assert ident.windows_distro is None
        assert ident.windows_build is None
        assert ident.windows_display_version is None
        assert ident.windows_edition is None
        assert ident.confidence == 0.0
        assert ident.detection_method == "unknown"
        assert ident.metadata == {}

    def test_metadata_default_factory_isolation(self):
        a = GuestIdentity()
        b = GuestIdentity()
        a.metadata["key"] = "value"
        assert "key" not in b.metadata

    def test_custom_values(self):
        ident = GuestIdentity(
            type=GuestType.LINUX,
            hostname="myhost",
            confidence=0.85,
            detection_method="guestfs_inspection",
        )
        assert ident.type == GuestType.LINUX
        assert ident.hostname == "myhost"
        assert ident.confidence == 0.85
        assert ident.detection_method == "guestfs_inspection"


# ---------------------------------------------------------------------------
# GuestDetector.parse_os_release
# ---------------------------------------------------------------------------


class TestParseOsRelease:
    def test_basic_key_value(self):
        text = 'NAME="Fedora Linux"\nVERSION_ID=41\n'
        result = GuestDetector.parse_os_release(text)
        assert result["NAME"] == "Fedora Linux"
        assert result["VERSION_ID"] == "41"

    def test_strips_double_quotes(self):
        result = GuestDetector.parse_os_release('PRETTY_NAME="Ubuntu 22.04 LTS"')
        assert result["PRETTY_NAME"] == "Ubuntu 22.04 LTS"

    def test_strips_single_quotes(self):
        result = GuestDetector.parse_os_release("PRETTY_NAME='Arch Linux'")
        assert result["PRETTY_NAME"] == "Arch Linux"

    def test_skips_comments(self):
        text = "# This is a comment\nNAME=Fedora\n"
        result = GuestDetector.parse_os_release(text)
        assert "#" not in "".join(result.keys())
        assert result["NAME"] == "Fedora"

    def test_skips_blank_lines(self):
        text = "\n\nNAME=Test\n\n"
        result = GuestDetector.parse_os_release(text)
        assert result == {"NAME": "Test"}

    def test_skips_lines_without_equals(self):
        text = "NAME=Test\nthis has no equals sign\nVERSION=1\n"
        result = GuestDetector.parse_os_release(text)
        assert len(result) == 2
        assert "NAME" in result
        assert "VERSION" in result

    def test_empty_string(self):
        assert GuestDetector.parse_os_release("") == {}

    def test_none_input(self):
        assert GuestDetector.parse_os_release(None) == {}

    def test_value_with_equals_sign(self):
        text = "BUG_REPORT_URL=https://example.com?a=1&b=2\n"
        result = GuestDetector.parse_os_release(text)
        assert result["BUG_REPORT_URL"] == "https://example.com?a=1&b=2"


# ---------------------------------------------------------------------------
# GuestDetector.parse_issue_file
# ---------------------------------------------------------------------------


class TestParseIssueFile:
    def test_strips_single_letter_escapes(self):
        result = GuestDetector.parse_issue_file(r"Welcome to \S \l")
        # \S and \l are single-letter escapes => removed
        assert result is not None
        assert "\\S" not in result
        assert "\\l" not in result
        assert "Welcome to" in result

    def test_returns_none_for_empty(self):
        assert GuestDetector.parse_issue_file("") is None

    def test_returns_none_for_none(self):
        assert GuestDetector.parse_issue_file(None) is None

    def test_returns_none_for_only_escapes(self):
        result = GuestDetector.parse_issue_file(r"\S \l \n")
        # After removing \S, \l, \n and stripping, should be None or empty
        assert result is None

    def test_preserves_real_content(self):
        result = GuestDetector.parse_issue_file("Fedora release 41 (Forty One)")
        assert result == "Fedora release 41 (Forty One)"


# ---------------------------------------------------------------------------
# GuestDetector._normalize_mountpoints
# ---------------------------------------------------------------------------


class TestNormalizeMountpoints:
    def test_dict_input(self):
        mps = {"/": "/dev/sda1", "/boot": "/dev/sda2"}
        result = GuestDetector._normalize_mountpoints(mps)
        assert isinstance(result, list)
        assert ("/dev/sda1", "/") in result
        assert ("/dev/sda2", "/boot") in result

    def test_list_of_tuples(self):
        mps = [("/dev/sda1", "/"), ("/dev/sda2", "/boot")]
        result = GuestDetector._normalize_mountpoints(mps)
        assert ("/dev/sda1", "/") in result
        assert ("/dev/sda2", "/boot") in result

    def test_none_input(self):
        assert GuestDetector._normalize_mountpoints(None) == []

    def test_empty_dict(self):
        assert GuestDetector._normalize_mountpoints({}) == []

    def test_empty_list(self):
        assert GuestDetector._normalize_mountpoints([]) == []

    def test_non_string_values_filtered_in_dict(self):
        mps = {"/": "/dev/sda1", 123: "/dev/sda2", "/boot": 456}
        result = GuestDetector._normalize_mountpoints(mps)
        # Only the first entry has both str key and str value
        assert len(result) == 1
        assert ("/dev/sda1", "/") in result

    def test_invalid_tuples_skipped(self):
        mps = [("/dev/sda1", "/"), "bad_entry", (1, 2, 3)]
        result = GuestDetector._normalize_mountpoints(mps)
        assert len(result) == 1
        assert ("/dev/sda1", "/") in result

    def test_non_iterable_input(self):
        assert GuestDetector._normalize_mountpoints(42) == []


# ---------------------------------------------------------------------------
# GuestDetector._path_depth
# ---------------------------------------------------------------------------


class TestPathDepth:
    def test_root_returns_zero(self):
        assert GuestDetector._path_depth("/") == 0

    def test_single_component(self):
        assert GuestDetector._path_depth("/foo") == 1

    def test_two_components(self):
        assert GuestDetector._path_depth("/foo/bar") == 2

    def test_empty_string_returns_zero(self):
        assert GuestDetector._path_depth("") == 0

    def test_trailing_slash(self):
        assert GuestDetector._path_depth("/foo/bar/") == 2

    def test_none_returns_zero(self):
        assert GuestDetector._path_depth(None) == 0


# ---------------------------------------------------------------------------
# GuestDetector._versionish_key
# ---------------------------------------------------------------------------


class TestVersionishKey:
    def test_pure_numeric(self):
        result = GuestDetector._versionish_key("123")
        assert result == [(0, 123)]

    def test_mixed_version_string(self):
        result = GuestDetector._versionish_key("6.12.10")
        # "6" => (0,6), "." => (1,"."), "12" => (0,12), "." => (1,"."), "10" => (0,10)
        assert (0, 6) in result
        assert (0, 12) in result
        assert (0, 10) in result

    def test_version_with_text(self):
        result = GuestDetector._versionish_key("6.12.10-200.fc41")
        ints_only = [v for tag, v in result if tag == 0]
        assert 6 in ints_only
        assert 12 in ints_only
        assert 10 in ints_only
        assert 200 in ints_only
        assert 41 in ints_only

    def test_empty_string(self):
        assert GuestDetector._versionish_key("") == []

    def test_none_input(self):
        assert GuestDetector._versionish_key(None) == []

    def test_pure_alpha(self):
        result = GuestDetector._versionish_key("abc")
        assert result == [(1, "abc")]

    def test_ordering_comparison(self):
        # Ensure keys can be compared for sorting
        k1 = GuestDetector._versionish_key("5.15.0")
        k2 = GuestDetector._versionish_key("6.1.0")
        assert k1 < k2


# ---------------------------------------------------------------------------
# GuestDetector.detect_by_inspection (mock guestfs)
# ---------------------------------------------------------------------------


class TestDetectByInspection:
    def test_returns_windows(self):
        g = Mock()
        g.inspect_get_type.return_value = "windows"
        assert GuestDetector.detect_by_inspection(g, "/dev/sda1") == GuestType.WINDOWS

    def test_returns_linux(self):
        g = Mock()
        g.inspect_get_type.return_value = "linux"
        assert GuestDetector.detect_by_inspection(g, "/dev/sda1") == GuestType.LINUX

    def test_returns_bsd(self):
        g = Mock()
        g.inspect_get_type.return_value = "freebsd"
        assert GuestDetector.detect_by_inspection(g, "/dev/sda1") == GuestType.BSD

    def test_returns_macos_for_darwin(self):
        g = Mock()
        g.inspect_get_type.return_value = "darwin"
        assert GuestDetector.detect_by_inspection(g, "/dev/sda1") == GuestType.MACOS

    def test_returns_macos_for_macos(self):
        g = Mock()
        g.inspect_get_type.return_value = "macos"
        assert GuestDetector.detect_by_inspection(g, "/dev/sda1") == GuestType.MACOS

    def test_returns_none_for_empty_type(self):
        g = Mock()
        g.inspect_get_type.return_value = ""
        assert GuestDetector.detect_by_inspection(g, "/dev/sda1") is None

    def test_returns_none_for_none_type(self):
        g = Mock()
        g.inspect_get_type.return_value = None
        assert GuestDetector.detect_by_inspection(g, "/dev/sda1") is None

    def test_returns_none_on_exception(self):
        g = Mock()
        g.inspect_get_type.side_effect = RuntimeError("guestfs error")
        assert GuestDetector.detect_by_inspection(g, "/dev/sda1") is None

    def test_case_insensitive_windows(self):
        g = Mock()
        g.inspect_get_type.return_value = "WINDOWS"
        assert GuestDetector.detect_by_inspection(g, "/dev/sda1") == GuestType.WINDOWS

    def test_unknown_os_type_returns_none(self):
        g = Mock()
        g.inspect_get_type.return_value = "haiku"
        assert GuestDetector.detect_by_inspection(g, "/dev/sda1") is None


# ---------------------------------------------------------------------------
# GuestDetector.best_root (mock guestfs)
# ---------------------------------------------------------------------------


class TestBestRoot:
    def test_prefers_windows_root(self):
        g = Mock()
        g.inspect_os.return_value = ["/dev/sda1", "/dev/sda2"]
        g.inspect_get_type.side_effect = lambda r: "linux" if r == "/dev/sda1" else "windows"
        assert GuestDetector.best_root(g) == "/dev/sda2"

    def test_returns_first_when_no_windows(self):
        g = Mock()
        g.inspect_os.return_value = ["/dev/sda1", "/dev/sda2"]
        g.inspect_get_type.return_value = "linux"
        assert GuestDetector.best_root(g) == "/dev/sda1"

    def test_returns_none_for_no_roots(self):
        g = Mock()
        g.inspect_os.return_value = []
        assert GuestDetector.best_root(g) is None

    def test_returns_none_on_exception(self):
        g = Mock()
        g.inspect_os.side_effect = RuntimeError("oops")
        assert GuestDetector.best_root(g) is None

    def test_single_root(self):
        g = Mock()
        g.inspect_os.return_value = ["/dev/sda1"]
        g.inspect_get_type.return_value = "linux"
        assert GuestDetector.best_root(g) == "/dev/sda1"

    def test_handles_inspect_get_type_exception(self):
        """If inspect_get_type raises for all roots, falls back to first root."""
        g = Mock()
        g.inspect_os.return_value = ["/dev/sda1", "/dev/sda2"]
        g.inspect_get_type.side_effect = RuntimeError("no info")
        assert GuestDetector.best_root(g) == "/dev/sda1"


# ---------------------------------------------------------------------------
# emit_guest_identity_log
# ---------------------------------------------------------------------------


class TestEmitGuestIdentityLog:
    def test_linux_identity_log(self):
        logger = Mock()
        ident = GuestIdentity(
            type=GuestType.LINUX,
            hostname="testhost",
            machine_id="abc123",
            os_name="Fedora Linux",
            os_pretty_name="Fedora Linux 41 (Workstation Edition)",
            os_version="41 (Workstation Edition)",
            cpe_name="cpe:/o:fedoraproject:fedora:41",
            support_end="2025-05-13",
            architecture="x86_64",
            kernel_version="6.12.10-200.fc41.x86_64",
            confidence=0.85,
            detection_method="guestfs_inspection",
        )
        emit_guest_identity_log(logger, ident)
        logger.info.assert_called_once()
        logged_msg = logger.info.call_args[0][1]
        assert "Guest Identity (Linux)" in logged_msg
        assert "testhost" in logged_msg
        assert "abc123" in logged_msg
        assert "Fedora Linux" in logged_msg

    def test_windows_identity_log(self):
        logger = Mock()
        ident = GuestIdentity(
            type=GuestType.WINDOWS,
            os_name="Windows 10 Enterprise",
            architecture="x86_64",
            windows_distro="windows",
            windows_major="10",
            windows_minor="0",
            windows_build="19045",
            windows_display_version="22H2",
            windows_edition="Enterprise",
            confidence=0.90,
            detection_method="canonical_windows_virtio",
            metadata={
                "registry_hives": ["/Windows/System32/config/SOFTWARE"],
                "windows_dirs": ["/Windows"],
            },
        )
        emit_guest_identity_log(logger, ident)
        logger.info.assert_called_once()
        logged_msg = logger.info.call_args[0][1]
        assert "Guest Identity (Windows)" in logged_msg
        assert "Windows 10 Enterprise" in logged_msg

    def test_unknown_identity_log(self):
        logger = Mock()
        ident = GuestIdentity(
            type=GuestType.UNKNOWN,
            confidence=0.10,
            detection_method="indicator_files",
        )
        emit_guest_identity_log(logger, ident)
        logger.info.assert_called_once()
        logged_msg = logger.info.call_args[0][1]
        assert "Guest Identity (Unknown)" in logged_msg

    def test_linux_defaults_show_na(self):
        logger = Mock()
        ident = GuestIdentity(type=GuestType.LINUX)
        emit_guest_identity_log(logger, ident)
        logged_msg = logger.info.call_args[0][1]
        assert "n/a" in logged_msg

    def test_windows_defaults_show_na(self):
        logger = Mock()
        ident = GuestIdentity(type=GuestType.WINDOWS)
        emit_guest_identity_log(logger, ident)
        logged_msg = logger.info.call_args[0][1]
        assert "n/a" in logged_msg

    def test_windows_log_shows_registry_hive_count(self):
        logger = Mock()
        ident = GuestIdentity(
            type=GuestType.WINDOWS,
            metadata={
                "registry_hives": ["/Windows/System32/config/SOFTWARE", "/Windows/System32/config/SYSTEM"],
                "windows_dirs": ["/Windows"],
            },
        )
        emit_guest_identity_log(logger, ident)
        logged_msg = logger.info.call_args[0][1]
        assert "2" in logged_msg  # two registry hives


# ---------------------------------------------------------------------------
# _fmt_table helper
# ---------------------------------------------------------------------------


class TestFmtTable:
    def test_produces_bordered_output(self):
        rows = [("Key", "Value")]
        result = _fmt_table("Title", rows)
        assert result.startswith("\u250c")  # top-left corner
        assert result.endswith("\u2518")  # bottom-right corner
        assert "Title" in result
        assert "Key" in result
        assert "Value" in result

    def test_alignment(self):
        rows = [("Short", "A"), ("Much Longer Key", "B")]
        result = _fmt_table("Test", rows)
        lines = result.splitlines()
        # All data lines should have consistent box borders
        for line in lines:
            assert (
                line.startswith("\u2502")
                or line.startswith("\u250c")
                or line.startswith("\u2514")
                or line.startswith("\u251c")
            )
