# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/windows/virtio/utils.py
"""Shared utility functions for Windows VirtIO driver injection"""

from __future__ import annotations

import hashlib
import logging
import re
import tempfile
from pathlib import Path
from typing import Any

try:
    import guestfs  # type: ignore
except ImportError:
    guestfs = None  # type: ignore

# Import shared logging utilities (use directly, no wrappers)
# Import shared guest utilities (use directly, no wrappers)
from h2kvm.core.guest_utils import (
    deep_merge_dict,
    guest_mkdir_p,
    guest_write_text,
)
from h2kvm.core.logging_utils import (
    log_step,
    log_with_emoji as _log,
    safe_logger as _safe_logger_base,
)

# Logging helpers


def _safe_logger(self) -> logging.Logger:
    """Get logger from instance or create default for windows_virtio modules."""
    return _safe_logger_base(self, "h2kvm.windows_virtio")


def _step(logger: logging.Logger, description: str):
    """Context manager for logging and timing operation steps.

    Wrapper around core logging_utils.log_step for consistency.

    Args:
        logger: Logger instance to use
        description: Description of the operation

    Yields:
        None
    """
    return log_step(logger, description)


def _deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries.

    Wrapper around core guest_utils.deep_merge_dict for consistency.

    Args:
        base: Base dictionary
        override: Dictionary to merge into base

    Returns:
        Merged dictionary
    """
    return deep_merge_dict(base, override)


# Misc helpers


def _is_probably_driver_payload(p: Path) -> bool:
    """Check if a file is likely a driver payload file.

    Args:
        p: Path to check

    Returns:
        True if the file extension indicates a driver payload file

    Note:
        Checks for .inf, .cat, .sys, .dll, .mui extensions.
    """
    ext = p.suffix.lower()
    return ext in (".inf", ".cat", ".sys", ".dll", ".mui")


def _to_int(v: Any, default: int = 0) -> int:
    if isinstance(v, int):
        return v
    try:
        return int(float(v)) if isinstance(v, (float, str)) else default
    except (ValueError, TypeError):
        return default


def _normalize_product_name(name: str) -> str:
    if not name:
        return ""
    s = name.lower()
    s = re.sub(r"\([^)]*\)", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _guest_download_bytes(g: guestfs.GuestFS, guest_path: str, max_bytes: int | None = None) -> bytes:
    with tempfile.TemporaryDirectory() as td:
        lp = Path(td) / "dl"
        g.download(guest_path, str(lp))
        b = lp.read_bytes()
        return b[:max_bytes] if max_bytes is not None else b


def _guest_sha256(g: guestfs.GuestFS, guest_path: str) -> str | None:
    try:
        return hashlib.sha256(_guest_download_bytes(g, guest_path)).hexdigest()
    except (RuntimeError, OSError) as e:
        logging.getLogger(__name__).debug("SHA256 computation failed for guest path '%s': %s", guest_path, e)
        return None


def _sha256_path(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _guest_mkdir_p(g: guestfs.GuestFS, path: str, *, dry_run: bool = False) -> None:
    """Create directory and parent directories in guest filesystem.

    Wrapper around core guest_utils.guest_mkdir_p for consistency.

    Args:
        g: GuestFS instance
        path: Directory path to create
        dry_run: If True, skip actual operation
    """
    guest_mkdir_p(g, path, dry_run=dry_run)


def _guest_write_text(g: guestfs.GuestFS, path: str, content: str, *, dry_run: bool = False) -> None:
    """Write text content to a file in guest filesystem.

    Wrapper around core guest_utils.guest_write_text for consistency.

    Args:
        g: GuestFS instance
        path: File path in guest filesystem
        content: Text content to write
        dry_run: If True, skip actual operation
    """
    guest_write_text(g, path, content, dry_run=dry_run)


def _log_mountpoints_best_effort(logger: logging.Logger, g: guestfs.GuestFS) -> None:
    try:
        mps = g.mountpoints()
        _log(logger, logging.DEBUG, "guestfs mountpoints=%r", mps)
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort diagnostic logging, must not abort the caller
        pass
