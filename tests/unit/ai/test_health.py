# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Unit tests for hyper2kvm.ai.health.HealthEngine."""

from __future__ import annotations

import pytest

from hyper2kvm.ai.health import HealthEngine, HEALTH_CHECKS
from hyper2kvm.ai.models import HealthStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine():
    return HealthEngine()


# ---------------------------------------------------------------------------
# HEALTH_CHECKS sanity
# ---------------------------------------------------------------------------


class TestHealthChecks:
    def test_health_checks_non_empty(self):
        assert len(HEALTH_CHECKS) > 0

    def test_health_checks_have_required_keys(self):
        for hc in HEALTH_CHECKS:
            assert "name" in hc
            assert "label" in hc
            assert "check" in hc


# ---------------------------------------------------------------------------
# check() with None / empty report
# ---------------------------------------------------------------------------


class TestCheckEdgeCases:
    def test_check_none_report_returns_skip(self, engine):
        report = engine.check(None)
        assert report.overall_status == HealthStatus.SKIP
        assert len(report.checks) == 1
        assert report.checks[0].name == "no_report"
        assert report.checks[0].status == HealthStatus.SKIP

    def test_check_empty_dict_report(self, engine):
        report = engine.check({})
        assert report.overall_status == HealthStatus.SKIP
        assert len(report.checks) == 1
        assert report.checks[0].name == "no_report"

    def test_check_minimal_report(self, engine):
        report = engine.check({"analysis": {}, "actions": [], "warnings": []})
        assert report.overall_status in (
            HealthStatus.PASS,
            HealthStatus.WARN,
            HealthStatus.SKIP,
        )
        # Should have one check per HEALTH_CHECKS entry
        assert len(report.checks) == len(HEALTH_CHECKS)


# ---------------------------------------------------------------------------
# boot_config checks
# ---------------------------------------------------------------------------


class TestBootConfig:
    def test_boot_config_pass_when_grub_installed(self, engine):
        fixer_report = {
            "analysis": {"boot_mode": "bios", "grub_installed": True},
            "actions": ["installed grub to /dev/sda"],
            "warnings": [],
        }
        report = engine.check(fixer_report)
        boot_check = next(c for c in report.checks if c.name == "boot_config")
        assert boot_check.status == HealthStatus.PASS

    def test_boot_config_fail_when_grub_not_installed(self, engine):
        fixer_report = {
            "analysis": {"boot_mode": "bios", "grub_installed": False},
            "actions": [],
            "warnings": [],
        }
        report = engine.check(fixer_report)
        boot_check = next(c for c in report.checks if c.name == "boot_config")
        assert boot_check.status == HealthStatus.FAIL

    def test_boot_config_pass_with_grub_action(self, engine):
        fixer_report = {
            "analysis": {"boot_mode": "uefi"},
            "actions": ["GRUB reinstalled for UEFI"],
            "warnings": [],
        }
        report = engine.check(fixer_report)
        boot_check = next(c for c in report.checks if c.name == "boot_config")
        assert boot_check.status == HealthStatus.PASS


# ---------------------------------------------------------------------------
# fstab checks
# ---------------------------------------------------------------------------


class TestFstab:
    def test_fstab_valid_pass(self, engine):
        fixer_report = {
            "analysis": {},
            "actions": ["fstab entry updated for /dev/sda1"],
            "warnings": [],
        }
        report = engine.check(fixer_report)
        fstab_check = next(c for c in report.checks if c.name == "fstab_valid")
        assert fstab_check.status == HealthStatus.PASS

    def test_fstab_valid_warn_with_warnings(self, engine):
        fixer_report = {
            "analysis": {},
            "actions": [],
            "warnings": ["fstab contains stale UUID entry"],
        }
        report = engine.check(fixer_report)
        fstab_check = next(c for c in report.checks if c.name == "fstab_valid")
        assert fstab_check.status == HealthStatus.WARN

    def test_fstab_pass_when_no_changes_needed(self, engine):
        fixer_report = {
            "analysis": {},
            "actions": ["something unrelated"],
            "warnings": [],
        }
        report = engine.check(fixer_report)
        fstab_check = next(c for c in report.checks if c.name == "fstab_valid")
        assert fstab_check.status == HealthStatus.PASS


# ---------------------------------------------------------------------------
# virtio_drivers checks
# ---------------------------------------------------------------------------


class TestVirtioDrivers:
    def test_virtio_drivers_pass_when_found(self, engine):
        fixer_report = {
            "analysis": {"initramfs_drivers": ["virtio_blk", "virtio_scsi"]},
            "actions": [],
            "warnings": [],
        }
        report = engine.check(fixer_report)
        virtio_check = next(c for c in report.checks if c.name == "virtio_drivers")
        assert virtio_check.status == HealthStatus.PASS

    def test_virtio_drivers_pass_when_injected(self, engine):
        fixer_report = {
            "analysis": {"initramfs_drivers": []},
            "actions": ["initramfs regenerated with virtio modules"],
            "warnings": [],
        }
        report = engine.check(fixer_report)
        virtio_check = next(c for c in report.checks if c.name == "virtio_drivers")
        assert virtio_check.status == HealthStatus.PASS

    def test_virtio_drivers_warn_when_not_found(self, engine):
        fixer_report = {
            "analysis": {"initramfs_drivers": ["ext4", "xfs"]},
            "actions": [],
            "warnings": [],
        }
        report = engine.check(fixer_report)
        virtio_check = next(c for c in report.checks if c.name == "virtio_drivers")
        assert virtio_check.status == HealthStatus.WARN


# ---------------------------------------------------------------------------
# no_vmware_remnants checks
# ---------------------------------------------------------------------------


class TestVmwareRemnants:
    def test_no_vmware_remnants_pass(self, engine):
        fixer_report = {
            "analysis": {},
            "actions": ["removed vmware-tools package"],
            "warnings": [],
        }
        report = engine.check(fixer_report)
        vmw_check = next(c for c in report.checks if c.name == "no_vmware_remnants")
        assert vmw_check.status == HealthStatus.PASS

    def test_no_vmware_remnants_warn(self, engine):
        fixer_report = {
            "analysis": {},
            "actions": [],
            "warnings": ["vmware modules still loaded in kernel"],
        }
        report = engine.check(fixer_report)
        vmw_check = next(c for c in report.checks if c.name == "no_vmware_remnants")
        assert vmw_check.status == HealthStatus.WARN

    def test_no_vmware_remnants_pass_when_clean(self, engine):
        fixer_report = {
            "analysis": {},
            "actions": ["installed qemu-guest-agent"],
            "warnings": [],
        }
        report = engine.check(fixer_report)
        vmw_check = next(c for c in report.checks if c.name == "no_vmware_remnants")
        assert vmw_check.status == HealthStatus.PASS


# ---------------------------------------------------------------------------
# network_config checks
# ---------------------------------------------------------------------------


class TestNetworkConfig:
    def test_network_config_pass(self, engine):
        fixer_report = {
            "analysis": {},
            "actions": ["updated ifcfg-eth0 for KVM"],
            "warnings": [],
        }
        report = engine.check(fixer_report)
        net_check = next(c for c in report.checks if c.name == "network_config")
        assert net_check.status == HealthStatus.PASS

    def test_network_config_warn(self, engine):
        fixer_report = {
            "analysis": {},
            "actions": [],
            "warnings": ["network interface naming may change on reboot"],
        }
        report = engine.check(fixer_report)
        net_check = next(c for c in report.checks if c.name == "network_config")
        assert net_check.status == HealthStatus.WARN


# ---------------------------------------------------------------------------
# Overall status aggregation
# ---------------------------------------------------------------------------


class TestStatusAggregation:
    def test_fail_takes_precedence(self, engine):
        fixer_report = {
            "analysis": {"grub_installed": False},
            "actions": [],
            "warnings": [],
        }
        report = engine.check(fixer_report)
        assert report.overall_status == HealthStatus.FAIL

    def test_warn_when_no_fail(self, engine):
        fixer_report = {
            "analysis": {"grub_installed": True, "initramfs_drivers": ["ext4"]},
            "actions": ["grub configured"],
            "warnings": [],
        }
        report = engine.check(fixer_report)
        # virtio_drivers warns because no virtio found
        assert report.overall_status == HealthStatus.WARN

    def test_pass_when_all_good(self, engine):
        fixer_report = {
            "analysis": {
                "boot_mode": "bios",
                "grub_installed": True,
                "initramfs_drivers": ["virtio_blk", "virtio_net"],
            },
            "actions": [
                "grub reinstalled",
                "fstab stabilised",
                "initramfs regenerated with virtio",
                "vmware-tools removed",
                "network config updated for eth0",
            ],
            "warnings": [],
        }
        report = engine.check(fixer_report)
        assert report.overall_status == HealthStatus.PASS


# ---------------------------------------------------------------------------
# HealthReport methods
# ---------------------------------------------------------------------------


class TestHealthReportModel:
    def test_passed_returns_true_for_pass(self):
        from hyper2kvm.ai.models import HealthReport

        report = HealthReport(overall_status=HealthStatus.PASS)
        assert report.passed() is True

    def test_passed_returns_true_for_skip(self):
        from hyper2kvm.ai.models import HealthReport

        report = HealthReport(overall_status=HealthStatus.SKIP)
        assert report.passed() is True

    def test_passed_returns_false_for_fail(self):
        from hyper2kvm.ai.models import HealthReport

        report = HealthReport(overall_status=HealthStatus.FAIL)
        assert report.passed() is False

    def test_passed_returns_false_for_warn(self):
        from hyper2kvm.ai.models import HealthReport

        report = HealthReport(overall_status=HealthStatus.WARN)
        assert report.passed() is False

    def test_summary_counts_statuses(self):
        from hyper2kvm.ai.models import HealthCheck, HealthReport

        report = HealthReport(
            checks=[
                HealthCheck(name="a", status=HealthStatus.PASS),
                HealthCheck(name="b", status=HealthStatus.PASS),
                HealthCheck(name="c", status=HealthStatus.WARN),
                HealthCheck(name="d", status=HealthStatus.FAIL),
                HealthCheck(name="e", status=HealthStatus.SKIP),
            ]
        )
        s = report.summary()
        assert s["pass"] == 2
        assert s["warn"] == 1
        assert s["fail"] == 1
        assert s["skip"] == 1
