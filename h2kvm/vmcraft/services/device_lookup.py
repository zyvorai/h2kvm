# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Device lookup helpers for VMCraft."""

from __future__ import annotations

from typing import Callable


def _require_nbd_device(nbd_device: str | None) -> None:
    """Ensure lookup helpers are only used when backend is launched."""
    if not nbd_device:
        raise RuntimeError("VMCraft not initialized. Call launch() before performing disk operations.")


def _find_by_probe(
    nbd_device: str | None,
    target_value: str,
    list_partitions_fn: Callable[[], list[str]],
    probe_fn: Callable[[str], str],
    *,
    field_name: str,
) -> str:
    """Find first partition whose probe result matches target_value."""
    _require_nbd_device(nbd_device)

    for part in list_partitions_fn():
        try:
            if probe_fn(part) == target_value:
                return part
        except Exception:  # pylint: disable=broad-exception-caught  # probe_fn is an arbitrary guestfs-backed callback; any failure just means "not a match"
            continue

    raise RuntimeError(
        f"No partition or device found matching {field_name}='{target_value}' on the disk image. "
        f"The filesystem may have a different UUID/label than expected."
    )


def find_by_uuid(
    nbd_device: str | None,
    target_uuid: str,
    list_partitions_fn: Callable[[], list[str]],
    vfs_uuid_fn: Callable[[str], str],
) -> str:
    """Find a partition device by filesystem UUID."""
    return _find_by_probe(
        nbd_device,
        target_uuid,
        list_partitions_fn,
        vfs_uuid_fn,
        field_name="UUID",
    )


def find_by_label(
    nbd_device: str | None,
    target_label: str,
    list_partitions_fn: Callable[[], list[str]],
    vfs_label_fn: Callable[[str], str],
) -> str:
    """Find a partition device by filesystem label."""
    return _find_by_probe(
        nbd_device,
        target_label,
        list_partitions_fn,
        vfs_label_fn,
        field_name="LABEL",
    )


def list_devices(nbd_device: str | None) -> list[str]:
    """Return currently connected block devices."""
    if nbd_device:
        return [nbd_device]
    return []
