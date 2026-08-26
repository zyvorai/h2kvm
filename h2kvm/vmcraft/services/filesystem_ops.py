# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""File operation delegators for VMCraft wrappers."""

from __future__ import annotations

from typing import Any


def _require_file_ops(file_ops: Any | None) -> Any:
    """Ensure file operations backend is initialized."""
    if not file_ops:
        raise RuntimeError("VMCraft not initialized. Call launch() before performing file operations.")
    return file_ops


def call_file_ops(file_ops: Any | None, method: str, *args, **kwargs) -> Any:
    """Call a method on file ops object, enforcing launch precondition."""
    ops = _require_file_ops(file_ops)
    fn = getattr(ops, method)
    return fn(*args, **kwargs)
