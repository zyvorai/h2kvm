# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/windows/virtio/paths.py
"""Path resolution utilities for Windows filesystem operations"""

from __future__ import annotations

import logging
from dataclasses import dataclass

try:
    import guestfs  # type: ignore
except ImportError:
    guestfs = None  # type: ignore

from h2kvm.core.logging_utils import log_with_emoji as _log

from .windows_virtio_utils import _safe_logger

# Windows path model (WindowsRoot + System32 + drivers + hives)


@dataclass(frozen=True)
class WindowsSystemPaths:
    """Resolved guestfs-mounted-filesystem paths for a Windows installation."""

    # GuestFS paths (mounted filesystem paths, NOT Windows-style C:\ paths)
    windows_dir: str  # e.g. "/Windows" or "/WINNT"
    system32_dir: str  # e.g. "/Windows/System32"
    drivers_dir: str  # e.g. "/Windows/System32/drivers"
    config_dir: str  # e.g. "/Windows/System32/config"
    temp_dir: str  # e.g. "/Windows/Temp"

    system_hive: str  # e.g. "/Windows/System32/config/SYSTEM"
    software_hive: str  # e.g. "/Windows/System32/config/SOFTWARE"


def _find_windows_root(self, g: guestfs.GuestFS) -> str | None:
    logger = _safe_logger(self)
    for p in ["/Windows", "/WINDOWS", "/winnt", "/WINNT"]:
        try:
            if g.is_dir(p):
                _log(logger, logging.DEBUG, "Windows root: found %s", p)
                return p
        except Exception:  # pylint: disable=broad-exception-caught  # probing candidate paths, must not abort
            continue
    _log(logger, logging.DEBUG, "Windows root: no direct hit")
    return None


def _resolve_windows_system_paths(self, g: guestfs.GuestFS) -> WindowsSystemPaths:
    """
    Resolve Windows directory + System32 + drivers/config/temp locations.

    IMPORTANT:
      - Assumes REAL Windows system volume (C:) is mounted at '/' already.
      - Call _ensure_windows_root(...) first to avoid "wrong partition" surprises.
    """
    logger = _safe_logger(self)

    win_dir = _find_windows_root(self, g) or "/Windows"
    if not g.is_dir(win_dir):
        _log(logger, logging.WARNING, "Windows dir not found at %s; defaulting to /Windows", win_dir)
        win_dir = "/Windows"

    system32 = f"{win_dir}/System32"
    try:
        if not g.is_dir(system32):
            alt = f"{win_dir}/system32"
            if g.is_dir(alt):
                system32 = alt
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort alt-casing probe, must not abort
        pass

    drivers = f"{system32}/drivers"
    config = f"{system32}/config"
    temp = f"{win_dir}/Temp"

    return WindowsSystemPaths(
        windows_dir=win_dir,
        system32_dir=system32,
        drivers_dir=drivers,
        config_dir=config,
        temp_dir=temp,
        system_hive=f"{config}/SYSTEM",
        software_hive=f"{config}/SOFTWARE",
    )


def _guestfs_to_windows_path(p: str) -> str:
    """
    Best-effort conversion for logs/UI: guestfs path under /Windows -> C:\\Windows\\...
    If Windows dir is /WINNT, it still maps to C:\\WINNT\\...
    """
    if not p:
        return p
    s = p.replace("/", "\\")
    if s.startswith("\\"):
        s = s[1:]
    return f"C:\\{s}"
