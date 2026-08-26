# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for hyper2kvm.core.constants module.

Pure value checks verifying that global constants are set to their expected values.
"""

from __future__ import annotations

from hyper2kvm.core.constants import (
    DEFAULT_BOOT_TIMEOUT,
    DEFAULT_COMPRESSION_LEVEL,
    DEFAULT_MACHINE_TYPE,
    DEFAULT_NETWORK_TIMEOUT,
    DEFAULT_QEMU_TIMEOUT,
    DEFAULT_SSH_TIMEOUT,
    DEFAULT_VM_MEMORY,
    DEFAULT_VM_VCPUS,
    DEFAULT_VSPHERE_TIMEOUT,
    ENV_LUKS_PASSPHRASE,
    ENV_VC_PASSWORD,
    EXIT_CONFIG_ERROR,
    EXIT_FAILURE,
    EXIT_PERMISSION_ERROR,
    EXIT_SUCCESS,
    LEGACY_MACHINE_TYPE,
    MAX_API_RETRIES,
    MAX_COMPRESSION_LEVEL,
    MAX_FILE_RETRIES,
    MAX_NETWORK_RETRIES,
    MIN_COMPRESSION_LEVEL,
    NBD_BASE_PATH,
    NBD_MAX_DEVICE,
    PORT_RDP,
    PORT_SSH,
    PORT_VNC,
    PORT_VSPHERE_API,
    SIZE_1_GIB,
    SIZE_1_KIB,
    SIZE_1_MIB,
    SUPPORTED_INPUT_FORMATS,
    SUPPORTED_OUTPUT_FORMATS,
    DEFAULT_CONTAINER_ISOLATION,
    VIRTIO_DRIVERS,
)


# --- Timeouts ---


def test_default_network_timeout_is_30():
    assert DEFAULT_NETWORK_TIMEOUT == 30


def test_default_ssh_timeout_is_60():
    assert DEFAULT_SSH_TIMEOUT == 60


def test_default_boot_timeout_is_300():
    assert DEFAULT_BOOT_TIMEOUT == 300


def test_default_qemu_timeout_is_120():
    assert DEFAULT_QEMU_TIMEOUT == 120


def test_default_vsphere_timeout_is_300():
    assert DEFAULT_VSPHERE_TIMEOUT == 300


def test_all_timeouts_are_positive():
    for timeout in (
        DEFAULT_NETWORK_TIMEOUT,
        DEFAULT_SSH_TIMEOUT,
        DEFAULT_BOOT_TIMEOUT,
        DEFAULT_QEMU_TIMEOUT,
        DEFAULT_VSPHERE_TIMEOUT,
    ):
        assert timeout > 0


# --- Retry Limits ---


def test_max_network_retries():
    assert MAX_NETWORK_RETRIES == 5


def test_max_file_retries():
    assert MAX_FILE_RETRIES == 3


def test_max_api_retries():
    assert MAX_API_RETRIES == 4


def test_all_retry_limits_are_positive():
    for retries in (MAX_NETWORK_RETRIES, MAX_FILE_RETRIES, MAX_API_RETRIES):
        assert retries > 0


# --- Network Ports ---


def test_port_rdp():
    assert PORT_RDP == 3389


def test_port_vnc():
    assert PORT_VNC == 5900


def test_port_ssh():
    assert PORT_SSH == 22


def test_port_vsphere_api():
    assert PORT_VSPHERE_API == 443


# --- Size Constants ---


def test_size_1_kib():
    assert SIZE_1_KIB == 1024


def test_size_1_mib():
    assert SIZE_1_MIB == 1024 * 1024


def test_size_1_gib():
    assert SIZE_1_GIB == 1024**3


# --- NBD Constants ---


def test_nbd_base_path():
    assert NBD_BASE_PATH == "/dev/nbd"


def test_nbd_max_device():
    assert NBD_MAX_DEVICE == 15


# --- Exit Codes ---


def test_exit_success():
    assert EXIT_SUCCESS == 0


def test_exit_failure():
    assert EXIT_FAILURE == 1


def test_exit_config_error():
    assert EXIT_CONFIG_ERROR == 2


def test_exit_permission_error():
    assert EXIT_PERMISSION_ERROR == 13


# --- Supported Formats ---


def test_supported_input_formats_is_a_set():
    assert isinstance(SUPPORTED_INPUT_FORMATS, set)


def test_supported_input_formats_contains_vmdk():
    assert "vmdk" in SUPPORTED_INPUT_FORMATS


def test_supported_input_formats_contains_ova():
    assert "ova" in SUPPORTED_INPUT_FORMATS


def test_supported_input_formats_contains_expected_members():
    expected = {"vmdk", "ova", "ovf", "vhd", "vhdx", "raw", "qcow2"}
    assert SUPPORTED_INPUT_FORMATS == expected


def test_supported_output_formats_is_a_set():
    assert isinstance(SUPPORTED_OUTPUT_FORMATS, set)


def test_supported_output_formats_contains_qcow2():
    assert "qcow2" in SUPPORTED_OUTPUT_FORMATS


# --- Virtio Drivers ---


def test_virtio_drivers_is_a_list():
    assert isinstance(VIRTIO_DRIVERS, list)


def test_virtio_drivers_contains_virtio_blk():
    assert "virtio_blk" in VIRTIO_DRIVERS


def test_virtio_drivers_contains_expected_entries():
    assert VIRTIO_DRIVERS == ["virtio_blk", "virtio_scsi", "virtio_net", "nvme"]


# --- Compression Levels ---


def test_default_compression_level():
    assert DEFAULT_COMPRESSION_LEVEL == 6


def test_min_compression_level():
    assert MIN_COMPRESSION_LEVEL == 1


def test_max_compression_level():
    assert MAX_COMPRESSION_LEVEL == 9


def test_compression_level_ordering():
    assert MIN_COMPRESSION_LEVEL < DEFAULT_COMPRESSION_LEVEL < MAX_COMPRESSION_LEVEL


# --- VM Defaults ---


def test_default_vm_memory():
    assert DEFAULT_VM_MEMORY == 2048


def test_default_vm_vcpus():
    assert DEFAULT_VM_VCPUS == 2


# --- Machine Types ---


def test_default_machine_type():
    assert DEFAULT_MACHINE_TYPE == "pc-q35"


def test_legacy_machine_type():
    assert LEGACY_MACHINE_TYPE == "pc"


# --- Environment Variable Names ---


def test_env_vc_password():
    assert ENV_VC_PASSWORD == "VC_PASSWORD"


def test_env_luks_passphrase():
    assert ENV_LUKS_PASSPHRASE == "LUKS_PASSPHRASE"


# --- Feature Flags ---


def test_default_container_isolation_is_true():
    assert DEFAULT_CONTAINER_ISOLATION is True
