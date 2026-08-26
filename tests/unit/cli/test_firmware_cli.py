# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

"""CLI tests for firmware-related flags."""

from __future__ import annotations

import pytest

from hyper2kvm.cli.args.parser import build_parser


@pytest.fixture()
def parser():
    return build_parser()


class TestFirmwareCliFlags:
    def test_firmware_mode_auto_default(self, parser):
        args = parser.parse_args(["--vmdk", "disk.vmdk"])
        assert args.firmware_mode == "auto"
        assert args.firmware_fallback is True
        assert args.hyperv_generation is None

    @pytest.mark.parametrize("mode", ["auto", "bios", "uefi"])
    def test_firmware_mode_choices(self, parser, mode):
        args = parser.parse_args(["--vmdk", "disk.vmdk", "--firmware-mode", mode])
        assert args.firmware_mode == mode

    def test_legacy_uefi_flag(self, parser):
        args = parser.parse_args(["--vmdk", "disk.vmdk", "--uefi"])
        assert args.uefi is True

    def test_firmware_fallback_can_be_disabled(self, parser):
        args = parser.parse_args(["--vmdk", "disk.vmdk", "--no-firmware-fallback"])
        assert args.firmware_fallback is False

    def test_hyperv_generation_parsed(self, parser):
        args = parser.parse_args(["--vmdk", "disk.vmdk", "--hyperv-generation", "2"])
        assert args.hyperv_generation == 2

    @pytest.mark.parametrize("generation", [1, 2])
    def test_hyperv_generation_values(self, parser, generation):
        args = parser.parse_args(["--vmdk", "disk.vmdk", "--hyperv-generation", str(generation)])
        assert args.hyperv_generation == generation
