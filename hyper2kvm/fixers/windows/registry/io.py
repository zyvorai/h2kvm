# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/fixers/windows/registry/io.py
"""
Registry hive I/O operations - downloading and validation.

Provides robust hive download with fallback mechanisms and validation.
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging
    from pathlib import Path

try:
    import guestfs  # type: ignore
except ImportError:
    guestfs = None  # type: ignore


def _is_probably_regf(path: Path) -> bool:
    """
    Windows registry hives start with ASCII 'regf' signature.
    Cheap corruption/truncation guardrail.
    """
    try:
        b = path.read_bytes()
        return len(b) >= 4 and b[:4] == b"regf"
    except OSError:
        return False


def _download_hive_local(logger: logging.Logger, g: guestfs.GuestFS, remote: str, local: Path) -> None:
    """
    Robustly download a hive from the guest to a local path.

    We've seen cases where g.download() does not materialize the local file
    (or produces an empty/truncated file) without raising. This helper:
      1) tries g.download()
      2) verifies local exists + size >= 4KiB + 'regf' signature
      3) falls back to g.read_file()/g.cat() and writes bytes locally
    """
    local.parent.mkdir(parents=True, exist_ok=True)

    # backend-agnostic (native guestfs or VMCraft) download; various exception types possible, best-effort
    try:
        logger.info("Downloading hive: %r -> %r", remote, str(local))
        g.download(remote, str(local))
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("g.download(%r, %r) failed: %s", remote, str(local), e)

    try:
        if local.exists() and local.stat().st_size >= 4096 and _is_probably_regf(local):
            return
    except OSError:
        pass

    logger.warning("Hive not materialized after download; falling back to guestfs read: %r", remote)
    data: bytes | None = None

    # pylint: disable=duplicate-code
    # reason: the read_file/cat backend-accessor probe mirrors
    # hyper2kvm/fixers/windows/rdp.py's _download_hive() -- coincidental.
    # This version logs each failed attempt and feeds a larger fallback
    # chain below, while rdp.py's standalone helper has no logger and
    # returns bytes directly.
    for fn_name in ("read_file", "cat"):
        fn = getattr(g, fn_name, None)
        if not callable(fn):
            continue
        try:
            out = fn(remote)
            if isinstance(out, (bytes, bytearray)):
                data = bytes(out)
            else:
                # guestfs bindings sometimes return str-ish
                data = str(out).encode("latin-1", errors="ignore")
            break
        # backend-agnostic (native guestfs or VMCraft) call; various exception types possible, best-effort
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("%s(%r) failed: %s", fn_name, remote, e)

    if not data or len(data) < 4096:
        raise RuntimeError(
            f"Failed to download hive locally: remote={remote} local={local} (len={len(data) if data else 0})"
        )

    local.write_bytes(data)

    if not local.exists() or local.stat().st_size < 4096:
        raise RuntimeError(
            f"Windows registry hive could not be downloaded from guest disk to {local}. "
            f"The guest filesystem may not be properly mounted."
        )

    if not _is_probably_regf(local):
        raise RuntimeError(
            f"Downloaded file at {local} is not a valid Windows registry hive — "
            f"it is missing the expected 'regf' signature. The file may be corrupted or not a registry hive."
        )


def _log_mountpoints_best_effort(logger: logging.Logger, g: guestfs.GuestFS) -> None:
    """Log current guestfs mountpoints for debugging."""
    # backend-agnostic (native guestfs or VMCraft) call; various exception types possible, best-effort debug logging
    try:
        mps = g.mountpoints()
        logger.debug("guestfs mountpoints=%r", mps)
    except Exception:  # pylint: disable=broad-exception-caught
        pass


def detect_windows_hive(g: guestfs.GuestFS, root: str, hive_name: str) -> str | None:
    """
    Detect Windows registry hive path.

    Args:
        g: GuestFS instance
        root: Windows root path (e.g., "/mnt/windows" or "/")
        hive_name: Hive name (e.g., "SYSTEM", "SOFTWARE", "SAM")

    Returns:
        Full path to hive file, or None if not found
    """
    # Try standard locations
    candidates = [
        f"{root}/Windows/System32/config/{hive_name}",
        f"{root}/WINDOWS/System32/config/{hive_name}",
        f"{root}/Windows/System32/Config/{hive_name}",
        f"{root}/winnt/system32/config/{hive_name}",
        f"{root}/WINNT/system32/config/{hive_name}",
    ]

    for path in candidates:
        # backend-agnostic (native guestfs or VMCraft) call; various exception types possible, best-effort
        try:
            if g.is_file(path):
                return path
        except Exception:  # pylint: disable=broad-exception-caught
            continue

    return None


def download_and_open_hive(
    logger: logging.Logger,
    g: guestfs.GuestFS,
    remote_path: str,
    local_temp_path: Path,
    write: bool = False,
):
    """
    Download Windows registry hive and open with hivex.

    Args:
        logger: Logger instance
        g: GuestFS instance
        remote_path: Path to hive in guest filesystem
        local_temp_path: Local temporary path to download to
        write: Whether to open hive for writing

    Returns:
        hivex.Hivex instance (caller must close)

    Raises:
        RuntimeError: If download or open fails
    """
    if importlib.util.find_spec("hivex") is None:
        raise RuntimeError(
            "python-hivex module is required for Windows registry operations. "
            "Install it with: sudo dnf install python3-hivex (Fedora/RHEL) "
            "or sudo apt install python3-hivex (Debian/Ubuntu)"
        )

    # encoding.py imports from this module at top level; a top-level import here would be circular
    from .encoding import _open_hive_local  # pylint: disable=import-outside-toplevel,cyclic-import

    # Download hive to local temp file
    _download_hive_local(logger, g, remote_path, local_temp_path)

    # Open with hivex
    return _open_hive_local(local_temp_path, write=write)


def open_system_hive_for_edit(
    logger: logging.Logger,
    g: guestfs.GuestFS,
    system_path: str,
    local_hive: Path,
):
    """
    Download the SYSTEM hive for writing and return it positioned at its
    root node, alongside the active CurrentControlSet name.

    This is the common "open hive, then locate the active control set"
    sequence shared by the registry-editing fixers under
    hyper2kvm/fixers/windows/performance/.

    Args:
        logger: Logger instance
        g: GuestFS instance
        system_path: Path to SYSTEM hive in guest filesystem
        local_hive: Local temporary path to download to

    Returns:
        Tuple of (hive, root_node, controlset_name). Caller owns ``hive``
        and must close it (e.g. via ``_close_best_effort``).
    """
    # encoding.py imports from this module at top level; a top-level import here would be circular
    from .encoding import _detect_current_controlset  # pylint: disable=import-outside-toplevel,cyclic-import

    hive = download_and_open_hive(logger, g, system_path, local_hive, write=True)
    root_node = hive.root()
    controlset_name = _detect_current_controlset(hive, root_node)
    return hive, root_node, controlset_name
