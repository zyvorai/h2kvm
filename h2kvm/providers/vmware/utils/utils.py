# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/vmware/utils/utils.py
"""
Shared utility functions for VMware operations.

Provides common helpers to avoid duplication across VMware modules.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import quote


def safe_vm_name(name: str | None) -> str:
    """
    Sanitize VM name for use in filenames and paths.

    Replaces non-alphanumeric characters (except _, ., -) with underscores.
    Returns "vm" if the input is empty or None.

    Args:
        name: VM name to sanitize (can be None)

    Returns:
        Sanitized VM name safe for use in filenames

    Examples:
        >>> safe_vm_name("My VM (test)")
        'My_VM__test_'
        >>> safe_vm_name(None)
        'vm'
        >>> safe_vm_name("")
        'vm'
    """
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", (name or "vm").strip()) or "vm"


def is_tty(stream=None) -> bool:
    """
    Check if the specified stream (or stdout by default) is a TTY.

    Args:
        stream: File object to check (defaults to sys.stdout)

    Returns:
        True if stream is a TTY, False otherwise
    """
    try:
        if stream is None:
            stream = sys.stdout
        return stream.isatty()
    except Exception:  # pylint: disable=broad-exception-caught  # stream may be an arbitrary/mock file-like object; any failure just means "not a tty"
        return False


def create_console():
    """
    Create a console object for formatted output.

    Returns:
        None (Rich console support has been removed)
    """
    return


def quote_inventory_path(path: str) -> str:
    """Quote inventory path segments for vi:// URLs while keeping '/' as a separator.

    Args:
        path: Inventory path to quote (may contain spaces and special characters)

    Returns:
        URL-quoted path with '/' preserved as separator

    Note:
        Spaces and special characters do appear in vCenter inventory paths.
        Common safe characters plus '/' separators are preserved unescaped.

    Example:
        >>> quote_inventory_path("My VM/Folder Name")
        'My%20VM/Folder%20Name'
        >>> quote_inventory_path("vm-folder/test.vm")
        'vm-folder/test.vm'
    """
    # keep common safe characters plus '/' separators
    return quote(path, safe="/-_.()@")


def ensure_output_dir(base: Path) -> Path:
    """Ensure output directory exists and return the resolved path.

    Args:
        base: Base directory path (may be relative, use ~, etc.)

    Returns:
        Resolved absolute Path with directory created

    Note:
        Creates parent directories as needed (like mkdir -p).
        Expands user home directory (~) and resolves to absolute path.

    Example:
        >>> ensure_output_dir(Path("~/output"))
        PosixPath('/home/user/output')
    """
    out = Path(base).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    return out
