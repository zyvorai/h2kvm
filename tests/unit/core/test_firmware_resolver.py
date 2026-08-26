# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

"""Comprehensive tests for h2kvm.core.firmware_resolver."""

from __future__ import annotations

import pytest

from h2kvm.core.firmware_resolver import (
    BIOS_BOOT_FAILURE_PATTERNS,
    UEFI_BOOT_FAILURE_PATTERNS,
    FirmwareResolution,
    FirmwareSignals,
    normalize_user_firmware_mode,
    reconcile_legacy_firmware_flags,
    resolve_firmware,
    serial_indicates_boot_failure,
)


# ---------------------------------------------------------------------------
# Legacy flag normalization
# ---------------------------------------------------------------------------


class TestReconcileLegacyFirmwareFlags:
    @pytest.mark.parametrize(
        ("firmware_mode", "uefi_flag", "expected"),
        [
            ("auto", None, "auto"),
            ("auto", False, "auto"),
            ("auto", True, "uefi"),
            ("bios", True, "bios"),
            ("uefi", False, "uefi"),
            (" BIOS ", None, "bios"),
            ("UEFI", None, "uefi"),
            (None, True, "uefi"),
            (None, False, "auto"),
            (None, None, "auto"),
        ],
    )
    def test_reconcile(self, firmware_mode, uefi_flag, expected):
        assert reconcile_legacy_firmware_flags(firmware_mode=firmware_mode, uefi_flag=uefi_flag) == expected


class TestNormalizeUserFirmwareMode:
    @pytest.mark.parametrize(
        ("firmware_mode", "uefi_flag", "expected"),
        [
            ("auto", False, "auto"),
            ("auto", True, "uefi"),
            ("bios", None, "bios"),
            ("uefi", None, "uefi"),
        ],
    )
    def test_normalize(self, firmware_mode, uefi_flag, expected):
        assert normalize_user_firmware_mode(firmware_mode=firmware_mode, uefi_flag=uefi_flag) == expected


# ---------------------------------------------------------------------------
# resolve_firmware — user overrides
# ---------------------------------------------------------------------------


class TestResolveFirmwareUserOverride:
    @pytest.mark.parametrize(
        ("user_mode", "expected_firmware", "expected_alternate"),
        [
            ("bios", "bios", "uefi"),
            ("uefi", "uefi", "bios"),
        ],
    )
    def test_explicit_override_ignores_signals(self, user_mode, expected_firmware, expected_alternate):
        res = resolve_firmware(
            user_mode=user_mode,
            signals=FirmwareSignals(
                boot_mode="uefi" if user_mode == "bios" else "bios",
                partition_scheme="gpt" if user_mode == "bios" else "mbr",
                has_efi_partition=user_mode == "bios",
                is_windows=True,
            ),
        )
        assert res.firmware == expected_firmware
        assert res.alternate == expected_alternate
        assert res.source == "user_override"
        assert res.confidence == "high"
        assert res.user_mode == user_mode


# ---------------------------------------------------------------------------
# resolve_firmware — auto detection scenarios
# ---------------------------------------------------------------------------


RESOLVE_AUTO_CASES = [
    pytest.param(
        FirmwareSignals(
            boot_mode="bios",
            partition_scheme="mbr",
            has_efi_partition=False,
            windows_bcd_bios=True,
            hyperv_generation=1,
            is_windows=True,
        ),
        "bios",
        "uefi",
        id="gen1_mbr_windows_bios_bcd",
    ),
    pytest.param(
        FirmwareSignals(
            boot_mode="uefi",
            partition_scheme="gpt",
            has_efi_partition=True,
            windows_bcd_uefi=True,
            hyperv_generation=2,
            is_windows=True,
        ),
        "uefi",
        "bios",
        id="gen2_gpt_uefi_bcd",
    ),
    pytest.param(
        FirmwareSignals(
            boot_mode="unknown",
            partition_scheme="mbr",
            has_efi_partition=False,
            windows_bcd_bios=True,
            windows_bcd_uefi=True,
            is_windows=True,
        ),
        "bios",
        "uefi",
        id="dual_bcd_mbr_prefers_bios",
    ),
    pytest.param(
        FirmwareSignals(
            boot_mode="unknown",
            partition_scheme="gpt",
            has_efi_partition=True,
            windows_bcd_bios=True,
            windows_bcd_uefi=True,
            is_windows=True,
        ),
        "uefi",
        "bios",
        id="dual_bcd_gpt_prefers_uefi",
    ),
    pytest.param(
        FirmwareSignals(
            boot_mode="uefi",
            partition_scheme="mbr",
            has_efi_partition=False,
            is_windows=True,
        ),
        "bios",
        "uefi",
        id="mbr_no_efi_overrides_uefi_hint",
    ),
    pytest.param(
        FirmwareSignals(),
        "bios",
        "uefi",
        id="no_signals_safe_bios_default",
    ),
    pytest.param(
        FirmwareSignals(boot_mode="bios", is_windows=False),
        "bios",
        "uefi",
        id="linux_bios_boot_mode_only",
    ),
    pytest.param(
        FirmwareSignals(
            boot_mode="uefi",
            partition_scheme="gpt",
            has_efi_partition=True,
            is_windows=False,
        ),
        "uefi",
        "bios",
        id="linux_gpt_efi_boot",
    ),
    pytest.param(
        FirmwareSignals(ovf_firmware="bios", partition_scheme="mbr", is_windows=True),
        "bios",
        "uefi",
        id="ovf_bios_mbr",
    ),
    pytest.param(
        FirmwareSignals(
            ovf_firmware="uefi",
            partition_scheme="gpt",
            has_efi_partition=True,
            is_windows=True,
        ),
        "uefi",
        "bios",
        id="ovf_uefi_gpt",
    ),
    pytest.param(
        FirmwareSignals(
            windows_bcd_bios=True,
            partition_scheme="mbr",
            has_efi_partition=False,
            is_windows=True,
        ),
        "bios",
        "uefi",
        id="windows_bcd_bios_only",
    ),
    pytest.param(
        FirmwareSignals(
            windows_bcd_uefi=True,
            partition_scheme="gpt",
            has_efi_partition=True,
            is_windows=True,
        ),
        "uefi",
        "bios",
        id="windows_bcd_uefi_only",
    ),
    pytest.param(
        FirmwareSignals(hyperv_generation=1, partition_scheme="mbr", is_windows=True),
        "bios",
        "uefi",
        id="hyperv_gen1_mbr",
    ),
    pytest.param(
        FirmwareSignals(
            hyperv_generation=2,
            partition_scheme="gpt",
            has_efi_partition=True,
            is_windows=True,
        ),
        "uefi",
        "bios",
        id="hyperv_gen2_gpt_efi",
    ),
    pytest.param(
        FirmwareSignals(
            boot_mode="bios",
            partition_scheme="mbr",
            has_efi_partition=False,
        ),
        "bios",
        "uefi",
        id="bios_boot_mode_with_mbr_hints",
    ),
    pytest.param(
        FirmwareSignals(
            boot_mode="uefi",
            partition_scheme="gpt",
            has_efi_partition=False,
            is_windows=False,
        ),
        "uefi",
        "bios",
        id="uefi_boot_mode_without_efi_partition_linux",
    ),
    pytest.param(
        FirmwareSignals(has_efi_partition=True, is_windows=False),
        "uefi",
        "bios",
        id="efi_partition_alone_linux",
    ),
    pytest.param(
        FirmwareSignals(partition_scheme="gpt", is_windows=False),
        "uefi",
        "bios",
        id="gpt_label_only_prefers_uefi",
    ),
]


class TestResolveFirmwareAuto:
    @pytest.mark.parametrize(
        ("signals", "expected_firmware", "expected_alternate"),
        RESOLVE_AUTO_CASES,
    )
    def test_auto_resolution(self, signals, expected_firmware, expected_alternate):
        res = resolve_firmware(user_mode="auto", signals=signals)
        assert res.firmware == expected_firmware
        assert res.alternate == expected_alternate
        assert res.user_mode == "auto"
        assert res.source.startswith("auto:") or res.source == "default_safe"


class TestResolveFirmwareMetadata:
    def test_signal_map_populated(self):
        signals = FirmwareSignals(
            boot_mode="bios",
            partition_scheme="mbr",
            has_efi_partition=False,
            windows_bcd_bios=True,
            hyperv_generation=1,
            ovf_firmware="bios",
            is_windows=True,
        )
        res = resolve_firmware(user_mode="auto", signals=signals)
        assert res.signals["boot_mode"] == "bios"
        assert res.signals["partition_scheme"] == "mbr"
        assert res.signals["has_efi_partition"] is False
        assert res.signals["windows_bcd_bios"] is True
        assert res.signals["hyperv_generation"] == 1
        assert res.signals["ovf_firmware"] == "bios"
        assert res.signals["is_windows"] is True

    def test_no_signals_uses_default_safe_low_confidence(self):
        res = resolve_firmware(user_mode="auto", signals=None)
        assert isinstance(res, FirmwareResolution)
        assert res.firmware == "bios"
        assert res.source == "default_safe"
        assert res.confidence == "low"

    @pytest.mark.parametrize(
        ("signals", "expected_confidence"),
        [
            (
                FirmwareSignals(
                    boot_mode="bios",
                    partition_scheme="mbr",
                    has_efi_partition=False,
                    windows_bcd_bios=True,
                ),
                "high",
            ),
            (FirmwareSignals(partition_scheme="mbr"), "medium"),
            (FirmwareSignals(ovf_firmware="bios"), "low"),
        ],
    )
    def test_confidence_bands(self, signals, expected_confidence):
        res = resolve_firmware(user_mode="auto", signals=signals)
        assert res.confidence == expected_confidence

    def test_auto_source_includes_reasons(self):
        res = resolve_firmware(
            user_mode="auto",
            signals=FirmwareSignals(boot_mode="bios", partition_scheme="mbr"),
        )
        assert "offline_boot_mode=bios" in res.source
        assert "partition_table=mbr" in res.source


# ---------------------------------------------------------------------------
# serial_indicates_boot_failure
# ---------------------------------------------------------------------------


class TestSerialBootFailure:
    @pytest.mark.parametrize("pattern", UEFI_BOOT_FAILURE_PATTERNS)
    def test_uefi_patterns_detected(self, pattern):
        text = f"OVMF output: {pattern.upper()} on serial"
        assert serial_indicates_boot_failure(text, current_uefi=True) is True

    @pytest.mark.parametrize("pattern", BIOS_BOOT_FAILURE_PATTERNS)
    def test_bios_patterns_detected(self, pattern):
        text = f"SeaBIOS: {pattern.upper()} please check"
        assert serial_indicates_boot_failure(text, current_uefi=False) is True

    @pytest.mark.parametrize(
        ("text", "current_uefi", "expected"),
        [
            ("", True, False),
            ("   \n\t  ", False, False),
            ("kernel started successfully", True, False),
            ("login:", False, False),
            ("systemd[1]: Started", False, False),
            ("no bootable device", True, False),
            ("no bootable option or device was found", False, False),
        ],
    )
    def test_serial_negative_and_cross_mode(self, text, current_uefi, expected):
        assert serial_indicates_boot_failure(text, current_uefi=current_uefi) is expected

    def test_realistic_ovmf_serial_snippet(self):
        blob = """
        BdsDxe: loading Boot0001 "UEFI Misc Device" from PciRoot(0x0)/Pci(0x1,0x0)
        BdsDxe: failed to load Boot0001 "UEFI Misc Device": Not Found
        BdsDxe: No bootable option or device was found.
        """
        assert serial_indicates_boot_failure(blob, current_uefi=True)

    def test_realistic_seabios_serial_snippet(self):
        blob = """
        SeaBIOS (version ...)
        Booting from Hard Disk...
        Boot failed: not a bootable disk
        Reboot and select proper boot device
        """
        assert serial_indicates_boot_failure(blob, current_uefi=False)


# ---------------------------------------------------------------------------
# Backward-compatible named tests (original suite)
# ---------------------------------------------------------------------------


def test_gen1_mbr_windows_prefers_bios():
    res = resolve_firmware(
        user_mode="auto",
        signals=FirmwareSignals(
            boot_mode="bios",
            partition_scheme="mbr",
            has_efi_partition=False,
            windows_bcd_bios=True,
            hyperv_generation=1,
            is_windows=True,
        ),
    )
    assert res.firmware == "bios"
    assert res.alternate == "uefi"
    assert res.confidence in ("high", "medium")


def test_gen2_gpt_uefi_bcd_prefers_uefi():
    res = resolve_firmware(
        user_mode="auto",
        signals=FirmwareSignals(
            boot_mode="uefi",
            partition_scheme="gpt",
            has_efi_partition=True,
            windows_bcd_uefi=True,
            hyperv_generation=2,
            is_windows=True,
        ),
    )
    assert res.firmware == "uefi"
    assert res.alternate == "bios"


def test_dual_bcd_mbr_prefers_bios():
    res = resolve_firmware(
        user_mode="auto",
        signals=FirmwareSignals(
            boot_mode="unknown",
            partition_scheme="mbr",
            has_efi_partition=False,
            windows_bcd_bios=True,
            windows_bcd_uefi=True,
            is_windows=True,
        ),
    )
    assert res.firmware == "bios"


def test_user_override_wins():
    res = resolve_firmware(
        user_mode="uefi",
        signals=FirmwareSignals(boot_mode="bios", partition_scheme="mbr", is_windows=True),
    )
    assert res.firmware == "uefi"
    assert res.source == "user_override"


def test_serial_uefi_failure_pattern():
    assert serial_indicates_boot_failure(
        "BdsDxe: No bootable option or device was found.",
        current_uefi=True,
    )


def test_normalize_auto_ignores_uefi_false():
    assert normalize_user_firmware_mode(firmware_mode="auto", uefi_flag=False) == "auto"


def test_normalize_legacy_explicit_uefi():
    assert normalize_user_firmware_mode(firmware_mode="auto", uefi_flag=True) == "uefi"


def test_mbr_no_efi_overrides_inspection_uefi_hint():
    res = resolve_firmware(
        user_mode="auto",
        signals=FirmwareSignals(
            boot_mode="uefi",
            partition_scheme="mbr",
            has_efi_partition=False,
            is_windows=True,
        ),
    )
    assert res.firmware == "bios"


def test_reconcile_legacy_uefi_promotes_mode():
    assert reconcile_legacy_firmware_flags(firmware_mode="auto", uefi_flag=True) == "uefi"
    assert reconcile_legacy_firmware_flags(firmware_mode="auto", uefi_flag=False) == "auto"


def test_normalize_legacy_explicit_bios():
    assert normalize_user_firmware_mode(firmware_mode="bios") == "bios"
