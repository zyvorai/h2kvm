# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

"""Tests for KubeVirt deploy firmware fallback heuristics."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from hyper2kvm.infrastructure.deployers.kubernetes import KubernetesDeployer


def _make_deployer(**args_kw):
    dep = KubernetesDeployer.__new__(KubernetesDeployer)
    dep.logger = Mock()
    dep.vm_name = "test-vm"
    dep.namespace = "default"
    dep.wait_ready = True
    dep.custom_api = Mock()
    defaults = dict(
        uefi=False,
        firmware_mode="auto",
        firmware_alternate="uefi",
        firmware_fallback=True,
        win_secure_boot=False,
    )
    defaults.update(args_kw)
    dep.args = SimpleNamespace(**defaults)
    return dep


class TestMaybeFirmwareFallback:
    @pytest.mark.parametrize("firmware_mode", ["bios", "uefi"])
    def test_skipped_for_explicit_firmware_mode(self, firmware_mode):
        dep = _make_deployer(firmware_mode=firmware_mode)
        with patch.object(dep, "_capture_serial_boot_output") as capture:
            dep._maybe_firmware_fallback_after_deploy()
        capture.assert_not_called()
        dep.logger.info.assert_called()

    def test_skipped_when_no_alternate(self):
        dep = _make_deployer(firmware_alternate=None)
        with patch.object(dep, "_capture_serial_boot_output") as capture:
            dep._maybe_firmware_fallback_after_deploy()
        capture.assert_not_called()

    def test_no_retry_when_serial_healthy(self):
        dep = _make_deployer(uefi=True, firmware_alternate="bios")
        with patch.object(dep, "_capture_serial_boot_output", return_value="systemd started"):
            with patch("hyper2kvm.infrastructure.deployers.kubernetes.time.sleep"):
                with patch.object(dep, "_patch_vm_firmware") as patch_fw:
                    dep._maybe_firmware_fallback_after_deploy()
        patch_fw.assert_not_called()

    def test_retries_with_alternate_on_bios_boot_failure(self):
        dep = _make_deployer(uefi=True, firmware_alternate="bios")
        serials = [
            "BdsDxe: No bootable option or device was found.",
            "SeaBIOS booting kernel",
        ]
        with patch.object(dep, "_capture_serial_boot_output", side_effect=serials):
            with patch("hyper2kvm.infrastructure.deployers.kubernetes.time.sleep"):
                with patch.object(dep, "_virtctl_stop_vm") as stop:
                    with patch.object(dep, "_wait_until_vmi_gone") as gone:
                        with patch.object(dep, "_patch_vm_firmware") as patch_fw:
                            with patch.object(dep, "_start_vm") as start:
                                with patch.object(dep, "_wait_for_vm", return_value=True):
                                    dep._maybe_firmware_fallback_after_deploy()
        stop.assert_called_once()
        gone.assert_called_once()
        patch_fw.assert_called_once_with(uefi=False)
        start.assert_called_once()
        dep.logger.info.assert_any_call("✅ Firmware fallback to %s completed", "BIOS")

    def test_warns_when_retry_still_fails(self):
        dep = _make_deployer(uefi=False, firmware_alternate="uefi")
        bios_fail = "Reboot and select proper boot device"
        uefi_fail = "BdsDxe: No bootable option or device was found."
        with patch.object(
            dep,
            "_capture_serial_boot_output",
            side_effect=[bios_fail, uefi_fail],
        ):
            with patch("hyper2kvm.infrastructure.deployers.kubernetes.time.sleep"):
                with patch.object(dep, "_virtctl_stop_vm"):
                    with patch.object(dep, "_wait_until_vmi_gone"):
                        with patch.object(dep, "_patch_vm_firmware"):
                            with patch.object(dep, "_start_vm"):
                                with patch.object(dep, "_wait_for_vm", return_value=True):
                                    dep._maybe_firmware_fallback_after_deploy()
        dep.logger.warning.assert_any_call(
            "Firmware fallback to %s still shows boot errors in serial console — "
            "check disk boot entries or set firmware_mode explicitly",
            "uefi",
        )


class TestPatchVmFirmware:
    def test_patch_to_uefi_with_secure_boot(self):
        dep = _make_deployer(win_secure_boot=True)
        dep._patch_vm_firmware(uefi=True)
        body = dep.custom_api.patch_namespaced_custom_object.call_args.kwargs["body"]
        domain = body["spec"]["template"]["spec"]["domain"]
        assert domain["firmware"]["bootloader"]["efi"]["secureBoot"] is True
        assert domain["features"]["smm"]["enabled"] is True
        assert dep.args.uefi is True

    def test_patch_to_bios(self):
        dep = _make_deployer(uefi=True)
        dep._patch_vm_firmware(uefi=False)
        body = dep.custom_api.patch_namespaced_custom_object.call_args.kwargs["body"]
        domain = body["spec"]["template"]["spec"]["domain"]
        assert domain["firmware"]["bootloader"]["bios"] == {}
        assert dep.args.uefi is False


class TestCaptureSerialBootOutput:
    def test_returns_empty_when_virtctl_missing(self):
        dep = _make_deployer()
        with patch("hyper2kvm.infrastructure.deployers.kubernetes.shutil.which", return_value=None):
            assert dep._capture_serial_boot_output() == ""

    def test_returns_combined_stdout_stderr(self):
        dep = _make_deployer()
        dep._loaded_incluster = True
        dep._kubeconfig_resolved_path = None
        proc = Mock(returncode=0, stdout="boot log", stderr="warn")
        with patch(
            "hyper2kvm.infrastructure.deployers.kubernetes.shutil.which", return_value="/usr/bin/virtctl"
        ):
            with patch.object(dep, "_find_kubeconfig", return_value=None):
                with patch(
                    "hyper2kvm.infrastructure.deployers.kubernetes.subprocess.run", return_value=proc
                ):
                    out = dep._capture_serial_boot_output(timeout_s=10)
        assert out == "boot logwarn"
