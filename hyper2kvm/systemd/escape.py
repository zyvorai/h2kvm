# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd-escape integration for string escaping.

This module wraps systemd-escape to escape/unescape strings for use
in systemd unit names and paths.
"""

from __future__ import annotations

import subprocess


def systemd_escape(
    string: str,
    *,
    path: bool = False,
    template: str | None = None,
) -> str:
    """
    Escape string for use in systemd unit names.

    Parameters
    ----------
    string : str
        String to escape
    path : bool, default=False
        Escape as path (use forward slashes)
    template : str | None
        Escape as instance of template unit

    Returns
    -------
    str
        Escaped string

    Examples
    --------
    >>> systemd_escape("my service name")
    'my\\x20service\\x20name'

    >>> systemd_escape("/path/to/mount", path=True)
    'path-to-mount'

    >>> systemd_escape("instance1", template="myservice@")
    'myservice@instance1'
    """
    cmd = ["systemd-escape"]

    if path:
        cmd.append("--path")
    if template:
        cmd.extend(["--template", template])

    cmd.append(string)

    # pylint: disable=duplicate-code
    # reason: mirrors the subprocess.run(...) call shape in
    # hyper2kvm/systemd/cgtop.py's snapshot() -- coincidental, both just
    # capture their own binary's text output.
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True,
    )

    return result.stdout.strip()


def systemd_unescape(string: str) -> str:
    """
    Unescape systemd unit name to original string.

    Parameters
    ----------
    string : str
        Escaped string

    Returns
    -------
    str
        Unescaped string

    Examples
    --------
    >>> systemd_unescape("my\\x20service\\x20name")
    'my service name'

    >>> systemd_unescape("path-to-mount")
    '/path/to/mount'
    """
    # pylint: disable=duplicate-code
    # reason: mirrors the subprocess.run(...) + return shape in
    # hyper2kvm/systemd/id128.py's machine_id() -- coincidental, both just
    # capture and strip their own binary's text output.
    result = subprocess.run(
        ["systemd-escape", "--unescape", string],
        capture_output=True,
        text=True,
        check=True,
    )

    return result.stdout.strip()
