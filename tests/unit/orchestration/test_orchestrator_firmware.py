# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

"""Tests for orchestrator firmware signal collection and deploy resolution."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from h2kvm.config.pipeline_config import MigrationConfig
from h2kvm.converters.extractors.ovf import OVF
from h2kvm.core.firmware_resolver import FirmwareResolution
from h2kvm.orchestration.orchestrator import Orchestrator


def _make_orchestrator(**args_kw):
    orch = Orchestrator.__new__(Orchestrator)
    orch.logger = Mock()
    defaults = dict(
        uefi=False,
        firmware_mode="auto",
        guest_os=None,
        windows=False,
        hyperv_generation=None,
        metadata=None,
        disk_partition_scheme=None,
        disk_has_efi_partition=None,
        win_secure_boot=None,
    )
    defaults.update(args_kw)
    orch.args = SimpleNamespace(**defaults)
    orch.config = MigrationConfig()
    orch.config.uefi = bool(defaults.get("uefi", False))
    orch.disk_processor = Mock()
    orch.disk_processor.last_fixer_report = {}
    return orch


class TestCollectFirmwareSignals:
    def test_windows_from_guest_os(self):
        orch = _make_orchestrator(guest_os="windows")
        report = {"analysis": {"boot_mode": "bios", "windows_bcd_bios": True}}
        sig = orch._collect_firmware_signals(report)
        assert sig.is_windows is True
        assert sig.boot_mode == "bios"
        assert sig.windows_bcd_bios is True

    def test_windows_from_analysis_flag(self):
        orch = _make_orchestrator(guest_os="linux", windows=False)
        report = {"analysis": {"windows": True, "boot_mode": "uefi"}}
        sig = orch._collect_firmware_signals(report)
        assert sig.is_windows is True
        assert sig.boot_mode == "uefi"

    def test_hyperv_generation_from_metadata(self):
        orch = _make_orchestrator(metadata={"generation": 2})
        sig = orch._collect_firmware_signals({})
        assert sig.hyperv_generation == 2

    def test_disk_partition_hints_from_args(self):
        orch = _make_orchestrator(
            disk_partition_scheme="mbr",
            disk_has_efi_partition=False,
        )
        sig = orch._collect_firmware_signals({})
        assert sig.partition_scheme == "mbr"
        assert sig.has_efi_partition is False

    def test_ovf_firmware_propagated(self, monkeypatch):
        monkeypatch.setattr(OVF, "last_firmware", "uefi", raising=False)
        orch = _make_orchestrator()
        sig = orch._collect_firmware_signals({})
        assert sig.ovf_firmware == "uefi"

    def test_bcd_flags_from_offline_report(self):
        orch = _make_orchestrator(guest_os="windows")
        report = {
            "analysis": {
                "windows_bcd_bios": True,
                "windows_bcd_uefi": True,
                "boot_mode": "unknown",
            }
        }
        sig = orch._collect_firmware_signals(report)
        assert sig.windows_bcd_bios is True
        assert sig.windows_bcd_uefi is True
        assert sig.boot_mode == "unknown"


class TestResolveDeployFirmware:
    def test_auto_mbr_windows_sets_bios_and_alternate(self):
        orch = _make_orchestrator(guest_os="windows")
        orch.disk_processor.last_fixer_report = {
            "analysis": {
                "boot_mode": "bios",
                "windows_bcd_bios": True,
            }
        }
        orch.args.disk_partition_scheme = "mbr"
        orch.args.disk_has_efi_partition = False

        orch._resolve_deploy_firmware()

        assert orch.args.uefi is False
        assert orch.config.uefi is False
        assert orch.args.firmware_alternate == "uefi"
        assert isinstance(orch.args.firmware_resolution, FirmwareResolution)
        analysis = orch.disk_processor.last_fixer_report["analysis"]
        assert analysis["firmware_mode"] == "bios"
        assert analysis["firmware_user_mode"] == "auto"
        assert analysis["firmware_alternate"] == "uefi"

    def test_explicit_uefi_override(self):
        orch = _make_orchestrator(firmware_mode="uefi", guest_os="windows")
        orch.disk_processor.last_fixer_report = {"analysis": {"boot_mode": "bios", "windows_bcd_bios": True}}
        orch.args.disk_partition_scheme = "mbr"

        orch._resolve_deploy_firmware()

        assert orch.args.uefi is True
        assert orch.config.uefi is True
        assert orch.args.firmware_alternate == "bios"
        assert orch.args.firmware_resolution.source == "user_override"

    def test_legacy_uefi_flag_promoted(self):
        orch = _make_orchestrator(firmware_mode="auto", uefi=True)
        orch.disk_processor.last_fixer_report = {"analysis": {"boot_mode": "bios"}}

        orch._resolve_deploy_firmware()

        assert orch.args.uefi is True
        assert orch.args.firmware_resolution.user_mode == "uefi"

    def test_bios_clears_win_secure_boot(self):
        orch = _make_orchestrator(guest_os="windows", win_secure_boot=True)
        orch.disk_processor.last_fixer_report = {"analysis": {"boot_mode": "bios", "windows_bcd_bios": True}}
        orch.args.disk_partition_scheme = "mbr"
        orch.args.disk_has_efi_partition = False

        orch._resolve_deploy_firmware()

        assert orch.args.uefi is False
        assert orch.args.win_secure_boot is False

    def test_uefi_resolution_preserves_secure_boot(self):
        orch = _make_orchestrator(
            firmware_mode="uefi",
            guest_os="windows",
            win_secure_boot=True,
        )
        orch.disk_processor.last_fixer_report = {}

        orch._resolve_deploy_firmware()

        assert orch.args.uefi is True
        assert orch.args.win_secure_boot is True

    @pytest.mark.parametrize("prev_uefi", [False, True])
    def test_logs_on_firmware_change(self, prev_uefi):
        orch = _make_orchestrator(guest_os="windows", uefi=prev_uefi)
        orch.config.uefi = prev_uefi
        orch.disk_processor.last_fixer_report = {
            "analysis": {
                "boot_mode": "uefi",
                "windows_bcd_uefi": True,
            }
        }
        orch.args.disk_partition_scheme = "gpt"
        orch.args.disk_has_efi_partition = True

        orch._resolve_deploy_firmware()

        assert orch.logger.info.called

    def test_empty_report_still_resolves(self):
        orch = _make_orchestrator()
        orch.disk_processor.last_fixer_report = {}

        orch._resolve_deploy_firmware()

        assert orch.args.firmware_resolution.firmware == "bios"
        assert orch.args.firmware_alternate == "uefi"
