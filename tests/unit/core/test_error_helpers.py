# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for hyper2kvm/core/error_helpers.py — ErrorHelper builder and pre-defined helpers."""

from __future__ import annotations

import pytest

from hyper2kvm.core.error_helpers import (
    DOCS_BASE,
    ErrorHelper,
    boot_failure_error,
    config_validation_error,
    disk_full_error,
    missing_dependency_error,
    network_error,
    no_backup_warning,
    permission_error,
    selinux_disabled_warning,
    validation_failure_error,
    vm_not_found_error,
    vmdk_parsing_error,
)


# ---------------------------------------------------------------------------
# DOCS_BASE constant
# ---------------------------------------------------------------------------


def test_docs_base_constant():
    assert DOCS_BASE == "https://github.com/ssahani/hyper2kvm/blob/main/docs"


# ---------------------------------------------------------------------------
# ErrorHelper — fluent builder API
# ---------------------------------------------------------------------------


class TestErrorHelperBuilder:
    """ErrorHelper fluent-builder basics."""

    def test_basic_build_message_only(self):
        result = ErrorHelper("something broke").build()
        assert result == "ERROR: something broke"

    def test_add_solution_returns_self(self):
        helper = ErrorHelper("msg")
        ret = helper.add_solution("fix it")
        assert ret is helper

    def test_add_cause_returns_self(self):
        helper = ErrorHelper("msg")
        ret = helper.add_cause("bad input")
        assert ret is helper

    def test_add_doc_returns_self(self):
        helper = ErrorHelper("msg")
        ret = helper.add_doc("README.md")
        assert ret is helper

    def test_add_example_returns_self(self):
        helper = ErrorHelper("msg")
        ret = helper.add_example("do this")
        assert ret is helper

    def test_build_with_all_sections(self):
        result = (
            ErrorHelper("kaboom")
            .add_cause("cosmic rays")
            .add_solution("reboot")
            .add_example("sudo reboot")
            .add_doc("troubleshooting.md", "Guide")
            .build()
        )
        assert "ERROR: kaboom" in result
        assert "Common causes:" in result
        assert "cosmic rays" in result
        assert "Solutions:" in result
        assert "reboot" in result
        assert "Examples:" in result
        assert "sudo reboot" in result
        assert "Documentation:" in result
        assert "Guide:" in result
        assert f"{DOCS_BASE}/troubleshooting.md" in result

    def test_chaining_multiple_adds(self):
        result = (
            ErrorHelper("oops")
            .add_cause("cause1")
            .add_cause("cause2")
            .add_solution("sol1")
            .add_solution("sol2")
            .add_example("ex1")
            .add_example("ex2")
            .add_doc("a.md")
            .add_doc("b.md")
            .build()
        )
        assert "cause1" in result
        assert "cause2" in result
        assert "sol1" in result
        assert "sol2" in result
        assert "ex1" in result
        assert "ex2" in result
        assert f"{DOCS_BASE}/a.md" in result
        assert f"{DOCS_BASE}/b.md" in result


# ---------------------------------------------------------------------------
# missing_dependency_error
# ---------------------------------------------------------------------------


class TestMissingDependencyError:
    def test_generic_package(self):
        msg = missing_dependency_error("somepkg")
        assert "somepkg" in msg
        assert "pip install" in msg

    def test_pyvmomi(self):
        msg = missing_dependency_error("pyvmomi")
        assert "pyvmomi" in msg
        assert "vsphere" in msg.lower()

    def test_guestfs(self):
        msg = missing_dependency_error("guestfs")
        assert "python3-guestfs" in msg
        assert "dnf" in msg
        assert "apt" in msg

    def test_azure_mgmt_compute(self):
        msg = missing_dependency_error("azure-mgmt-compute")
        assert "azure" in msg.lower()

    def test_custom_install_cmd(self):
        msg = missing_dependency_error("custom", install_cmd="brew install custom")
        assert "brew install custom" in msg


# ---------------------------------------------------------------------------
# vm_not_found_error
# ---------------------------------------------------------------------------


class TestVmNotFoundError:
    def test_basic(self):
        msg = vm_not_found_error("my-vm")
        assert "my-vm" in msg
        assert "govc" in msg

    def test_with_vcenter(self):
        msg = vm_not_found_error("my-vm", vcenter="vc.example.com")
        assert "vc.example.com" in msg


# ---------------------------------------------------------------------------
# boot_failure_error
# ---------------------------------------------------------------------------


class TestBootFailureError:
    def test_no_reason(self):
        msg = boot_failure_error()
        assert "boot" in msg.lower()
        assert "initramfs" in msg

    def test_with_reason(self):
        msg = boot_failure_error("missing kernel")
        assert "missing kernel" in msg


# ---------------------------------------------------------------------------
# permission_error
# ---------------------------------------------------------------------------


def test_permission_error():
    msg = permission_error("/some/path")
    assert "/some/path" in msg
    assert "sudo" in msg


# ---------------------------------------------------------------------------
# disk_full_error
# ---------------------------------------------------------------------------


class TestDiskFullError:
    def test_basic(self):
        msg = disk_full_error("/data")
        assert "/data" in msg
        assert "df" in msg

    def test_with_needed(self):
        msg = disk_full_error("/data", needed="50GB")
        assert "50GB" in msg


# ---------------------------------------------------------------------------
# network_error
# ---------------------------------------------------------------------------


def test_network_error():
    msg = network_error("host.example.com")
    assert "host.example.com" in msg
    assert "ping" in msg


# ---------------------------------------------------------------------------
# config_validation_error
# ---------------------------------------------------------------------------


def test_config_validation_error():
    msg = config_validation_error("memory", "abc", "integer")
    assert "memory" in msg
    assert "abc" in msg
    assert "integer" in msg


# ---------------------------------------------------------------------------
# vmdk_parsing_error
# ---------------------------------------------------------------------------


class TestVmdkParsingError:
    def test_basic(self):
        msg = vmdk_parsing_error("/path/to/disk.vmdk")
        assert "disk.vmdk" in msg
        assert "qemu-img" in msg

    def test_with_reason(self):
        msg = vmdk_parsing_error("/path/disk.vmdk", reason="corrupt header")
        assert "corrupt header" in msg


# ---------------------------------------------------------------------------
# validation_failure_error
# ---------------------------------------------------------------------------


def test_validation_failure_error():
    msg = validation_failure_error("boot_check")
    assert "boot_check" in msg
    assert "console" in msg


# ---------------------------------------------------------------------------
# no_backup_warning
# ---------------------------------------------------------------------------


def test_no_backup_warning():
    msg = no_backup_warning()
    assert "WARNING" in msg
    assert "snapshot" in msg


# ---------------------------------------------------------------------------
# selinux_disabled_warning
# ---------------------------------------------------------------------------


def test_selinux_disabled_warning():
    msg = selinux_disabled_warning()
    assert "SELinux" in msg
    assert "restorecon" in msg
