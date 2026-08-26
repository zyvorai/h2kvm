# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Shared fixtures and helpers for phony guest integration tests."""

from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

try:
    import guestfs
except ImportError:
    guestfs = None  # type: ignore[assignment]

PHONY_GUESTS = Path(__file__).parent.parent.parent / "test-data" / "phony-guests"

needs_root = pytest.mark.skipif(os.getuid() != 0, reason="Requires root for guestfs")
needs_guestfs = pytest.mark.skipif(guestfs is None, reason="python3-libguestfs not installed")


def phony_image(name: str) -> Path:
    """Get path to phony guest image, skip if not built."""
    img = PHONY_GUESTS / name
    if not img.exists() or img.stat().st_size == 0:
        pytest.skip(f"Phony guest {name} not built (run: sudo python3 test-data/phony-guests/build_all.py)")
    return img


@contextmanager
def open_phony(name: str, *, readonly: bool = True):
    """Open and mount a phony guest, yielding (g, root). Auto-closes on exit."""
    img = phony_image(name)
    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(str(img), format="qcow2", readonly=readonly)
    g.launch()
    roots = g.inspect_os()
    assert roots, f"No OS roots detected in {name}"
    root = roots[0]
    mps = g.inspect_get_mountpoints(root)
    mount_fn = g.mount_ro if readonly else g.mount
    for mp in sorted(mps.keys()):
        try:
            mount_fn(mps[mp], mp)
        except Exception:
            pass
    try:
        yield g, root
    finally:
        g.shutdown()
        g.close()


@contextmanager
def open_guestfs(*names: str, readonly: bool = True):
    """Open one or more phony images without inspection. Yields g only."""
    g = guestfs.GuestFS(python_return_dict=True)
    for name in names:
        img = phony_image(name)
        g.add_drive_opts(str(img), format="qcow2", readonly=readonly)
    g.launch()
    try:
        yield g
    finally:
        g.shutdown()
        g.close()


@contextmanager
def writable_copy(name: str):
    """Create a writable temp copy of a phony guest image (context manager)."""
    img = phony_image(name)
    tmpdir = tempfile.mkdtemp(prefix="h2kvm-test-")
    try:
        copy = Path(tmpdir) / name
        shutil.copy2(img, copy)
        yield copy
    finally:
        shutil.rmtree(tmpdir)


def make_fixer():
    """Create a mock OfflineFSFix instance with required attributes."""
    from hyper2kvm.fixers.offline_fixer import OfflineFSFix

    with patch.object(OfflineFSFix, "__init__", lambda self: None):
        fixer = OfflineFSFix.__new__(OfflineFSFix)
        fixer.logger = MagicMock()
        fixer.inspect_root = None
        fixer.root_dev = None
        fixer.root_btrfs_subvol = None
        fixer.boot_disk_index = None
        return fixer
