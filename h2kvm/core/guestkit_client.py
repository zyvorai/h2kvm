# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Thin facade over hypersdk-guestkit — no duplicate disk/repair logic."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from h2kvm.core.guestfs_factory import create_guestfs


def _require_guestkit():
    try:
        import guestkit  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "GuestKit is required for offline disk operations.\n"
            "  pip install hypersdk-guestkit\n"
            "  or: pip install -e ~/tt/guestkit"
        ) from exc


def open_guest(path: str | Path, *, backend: str = "guestkit") -> Any:
    """Return a GuestFS-compatible handle for *path*."""
    _require_guestkit()
    g = create_guestfs(backend=backend)
    g.add_drive_ro(str(path))
    g.launch()
    return g


def doctor(
    path: str | Path,
    *,
    target: str = "kvm",
    explain: bool = False,
    verbose: bool = False,
) -> dict[str, Any]:
    """Run GuestKit bootability doctor."""
    _require_guestkit()
    import guestkit

    return guestkit.run_doctor(str(path), target=target, explain=explain, verbose=verbose)


def boot_inspect(
    path: str | Path,
    *,
    target: str = "kvm",
    verbose: bool = False,
) -> dict[str, Any]:
    """Summarize boot-related guest state from an offline disk."""
    _require_guestkit()
    import guestkit

    return guestkit.run_boot_inspect(str(path), target=target, verbose=verbose)


def migrate_plan(
    path: str | Path,
    *,
    target: str = "kvm",
    explain: bool = False,
    verbose: bool = False,
    export_fix_plan: bool = False,
) -> dict[str, Any]:
    """Generate a hypervisor-aware migration plan."""
    _require_guestkit()
    import guestkit

    return guestkit.run_migrate_plan(
        str(path),
        target=target,
        explain=explain,
        verbose=verbose,
        export_fix_plan=export_fix_plan,
    )


def repair_boot(
    path: str | Path,
    *,
    dry_run: bool = True,
    verbose: bool = False,
    fix_cloud_init_network: bool = False,
    validate_fstab: bool = False,
) -> dict[str, Any]:
    """Generate or apply a boot repair plan (fstab/grub/initramfs)."""
    _require_guestkit()
    import guestkit

    return guestkit.run_repair_plan(
        str(path),
        dry_run=dry_run,
        verbose=verbose,
        fix_cloud_init_network=fix_cloud_init_network,
        validate_fstab=validate_fstab,
    )


def migrate_repair(
    path: str | Path,
    *,
    target: str = "kvm",
    apply: bool = False,
    include_destructive: bool = False,
    virtio_win: str | Path | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """Generate or apply a hypervisor-aware migration repair plan."""
    _require_guestkit()
    import guestkit

    return guestkit.run_migrate_repair(
        str(path),
        target=target,
        apply=apply,
        include_destructive=include_destructive,
        virtio_win=str(virtio_win) if virtio_win else None,
        verbose=verbose,
    )


def convert_disk(
    source: str | Path,
    output: str | Path,
    *,
    fmt: str = "qcow2",
    compress: bool = False,
    flatten: bool = True,
) -> dict[str, Any]:
    """Convert a disk image using GuestKit DiskConverter."""
    _require_guestkit()
    from guestkit import DiskConverter

    converter = DiskConverter()
    return converter.convert(str(source), str(output), fmt, compress=compress, flatten=flatten)
