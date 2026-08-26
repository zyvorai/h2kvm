# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/guest_utils.py
"""Shared utility functions for guestfs operations

Provides common helpers for guest file system operations and data manipulation
to avoid duplication across modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from h2kvm.core.guestfs_typing import guestfs


GUESTFS_AVAILABLE = True  # Native implementation always available


def guest_mkdir_p(g: guestfs.GuestFS, path: str, *, dry_run: bool = False) -> None:
    """Create directory and parent directories in guest filesystem.

    Args:
        g: GuestFS instance
        path: Directory path to create
        dry_run: If True, skip actual operation

    Note:
        Best-effort implementation that tolerates various error conditions.
    """
    if dry_run:
        return
    try:
        if not g.is_dir(path):
            g.mkdir_p(path)
    except Exception:  # pylint: disable=broad-exception-caught  # guestfs is_dir() can raise various backend errors; fall back to mkdir_p regardless
        g.mkdir_p(path)


def guest_write_text(g: guestfs.GuestFS, path: str, content: str, *, dry_run: bool = False) -> None:
    """Write text content to a file in guest filesystem.

    Args:
        g: GuestFS instance
        path: File path in guest filesystem
        content: Text content to write
        dry_run: If True, skip actual operation

    Note:
        Content is encoded as UTF-8 with error handling (ignore invalid chars).
    """
    if dry_run:
        return
    g.write(path, content.encode("utf-8", errors="ignore"))


def deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries recursively.

    Args:
        base: Base dictionary
        override: Override dictionary (takes precedence)

    Returns:
        Merged dictionary

    Behavior:
        - Dict values are merged recursively
        - Lists and scalars are replaced (override wins)

    Example:
        >>> base = {"a": {"b": 1, "c": 2}, "d": 3}
        >>> override = {"a": {"c": 99}, "e": 4}
        >>> deep_merge_dict(base, override)
        {'a': {'b': 1, 'c': 99}, 'd': 3, 'e': 4}
    """
    out: dict[str, Any] = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge_dict(out[k], v)
        else:
            out[k] = v
    return out


__all__ = [
    "deep_merge_dict",
    "guest_mkdir_p",
    "guest_write_text",
]
