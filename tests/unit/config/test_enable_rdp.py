# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for enable_rdp resolution and firstboot logging."""

from __future__ import annotations

import logging

import pytest

from hyper2kvm.config.pipeline_config import resolve_enable_rdp
from hyper2kvm.fixers.windows.registry.firstboot import log_firstboot_provision_summary


class TestResolveEnableRdp:
    def test_explicit_false(self):
        assert resolve_enable_rdp(False, guest_os="windows") is False

    def test_explicit_true(self):
        assert resolve_enable_rdp(True, guest_os="linux") is True

    def test_windows_guest_os_default_true(self):
        assert resolve_enable_rdp(None, guest_os="windows") is True

    def test_windows_flag_default_true(self):
        assert resolve_enable_rdp(None, windows=True) is True

    def test_linux_default_none(self):
        assert resolve_enable_rdp(None, guest_os="linux") is None

    def test_linux_ubuntu_default_none(self):
        assert resolve_enable_rdp(None, guest_os="ubuntu-22.04") is None


def test_log_firstboot_summary_when_rdp_disabled(caplog):
    caplog.set_level(logging.INFO)
    logger = logging.getLogger("test.firstboot.rdp")
    log_firstboot_provision_summary(
        logger,
        {
            "success": True,
            "enterprise_features": {"enable_rdp": False},
        },
        virtio_packages=2,
    )
    assert "rdp=False" in caplog.text


def test_log_firstboot_warning_on_failure(caplog):
    caplog.set_level(logging.WARNING)
    logger = logging.getLogger("test.firstboot.fail")
    log_firstboot_provision_summary(logger, {"success": False, "errors": ["upload failed"]})
    assert "provisioning failed" in caplog.text.lower()
