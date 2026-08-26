# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""CDI upload compatibility helpers (qcow2 compression vs older importer qemu-img)."""

from hyper2kvm.infrastructure.deployers.kubernetes import (
    _qcow2_json_compression_type,
    _qcow2_json_uses_zstd,
    _stderr_suggests_cdi_pvc_not_ready,
    _stderr_suggests_cdi_qcow2_incompatible,
    _stderr_suggests_cdi_upload_transient,
)


def test_detects_unknown_compression_type():
    stderr = (
        "Saving stream failed: qemu-img: Could not open '/scratch/tmpimage': "
        "qcow2: unknown compression type: 1"
    )
    assert _stderr_suggests_cdi_qcow2_incompatible(stderr) is True


def test_negative_on_unrelated_error():
    stderr = "connection refused to upload proxy"
    assert _stderr_suggests_cdi_qcow2_incompatible(stderr) is False


def test_empty_stderr():
    assert _stderr_suggests_cdi_qcow2_incompatible("") is False


def test_qcow2_json_compression_type_zstd():
    info = {
        "format": "qcow2",
        "format-specific": {"type": "qcow2", "data": {"compression-type": "zstd"}},
    }
    assert _qcow2_json_compression_type(info) == "zstd"
    assert _qcow2_json_uses_zstd(info) is True


def test_qcow2_json_compression_type_zlib_not_zstd():
    info = {
        "format": "qcow2",
        "format-specific": {"data": {"compression-type": "zlib"}},
    }
    assert _qcow2_json_uses_zstd(info) is False


def test_qcow2_json_uses_zstd_wrong_format():
    info = {"format": "raw", "format-specific": {"data": {"compression-type": "zstd"}}}
    assert _qcow2_json_uses_zstd(info) is False


def test_detects_cdi_pvc_not_found():
    stderr = 'persistentvolumeclaims "2025legacy-disk" not found'
    assert _stderr_suggests_cdi_pvc_not_ready(stderr) is True
    assert _stderr_suggests_cdi_upload_transient(stderr) is False


def test_detects_virtctl_rate_limiter_deadline():
    stderr = "client rate limiter Wait returned an error: rate: Wait(n=1) would exceed context deadline"
    assert _stderr_suggests_cdi_upload_transient(stderr) is True
    assert _stderr_suggests_cdi_qcow2_incompatible(stderr) is False


def test_transient_negative_on_compression_error():
    stderr = "qcow2: unknown compression type: 1"
    assert _stderr_suggests_cdi_upload_transient(stderr) is False
    assert _stderr_suggests_cdi_qcow2_incompatible(stderr) is True
