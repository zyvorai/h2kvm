# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/vmware/vsphere/errors.py
"""Error classification and exit code handling for vSphere operations"""

from __future__ import annotations

import errno
import socket
from enum import IntEnum

from ....core.exceptions import VMwareError


class VsphereExitCode(IntEnum):
    """Process exit codes for vSphere CLI operations, by failure category."""

    OK = 0
    UNKNOWN = 1
    USAGE = 2

    AUTH = 10
    NOT_FOUND = 11
    NETWORK = 12
    TOOL_MISSING = 13

    EXTERNAL_TOOL = 20
    VSPHERE_API = 30
    LOCAL_IO = 40

    INTERRUPTED = 130


def _is_usage_error(e: BaseException) -> bool:
    msg = str(e).lower()
    return (
        "unknown action" in msg
        or "missing vs_action" in msg
        or "missing required arg" in msg
        or "argparse" in msg
        or "usage:" in msg
    )


def _is_tool_missing_error(e: BaseException) -> bool:
    msg = str(e).lower()
    return (
        ("govc" in msg and ("not found" in msg or "no such file" in msg))
        or ("ovftool" in msg and ("not found" in msg or "no such file" in msg))
        or ("executable file not found" in msg)
    )


def _is_auth_error(e: BaseException) -> bool:
    msg = str(e).lower()
    needles = [
        "not authenticated",
        "authentication",
        "unauthorized",
        "forbidden",
        "invalid login",
        "no permission",
        "access denied",
        "permission denied",
        "authorization",
    ]
    return any(n in msg for n in needles)


def _is_not_found_error(e: BaseException) -> bool:
    msg = str(e).lower()
    needles = [
        "vm not found",
        "snapshot not found",
        "not found",
        "does not exist",
        "no such file",
        "file not found",
    ]
    return any(n in msg for n in needles)


def _is_network_error(e: BaseException) -> bool:
    if isinstance(e, (socket.timeout, TimeoutError, ConnectionError)):
        return True
    if isinstance(e, OSError) and e.errno in (
        errno.ECONNREFUSED,
        errno.ETIMEDOUT,
        errno.EHOSTUNREACH,
        errno.ENETUNREACH,
        errno.ECONNRESET,
    ):
        return True
    msg = str(e).lower()
    needles = [
        "timed out",
        "timeout",
        "connection refused",
        "connection reset",
        "name or service not known",
        "temporary failure in name resolution",
        "tls",
        "ssl",
        "handshake",
        "certificate verify failed",
    ]
    return any(n in msg for n in needles)


def _is_local_io_error(e: BaseException) -> bool:
    if isinstance(e, OSError) and e.errno in (
        errno.EACCES,
        errno.EPERM,
        errno.ENOSPC,
        errno.EROFS,
        errno.EDQUOT,
    ):
        return True
    msg = str(e).lower()
    needles = ["no space left", "permission denied", "read-only file system"]
    return any(n in msg for n in needles)


def _is_external_tool_error(e: BaseException) -> bool:
    msg = str(e).lower()
    return "govc failed" in msg or "subprocess" in msg


# pylint: disable-next=too-many-return-statements  # each branch maps one error category to an exit code
def _classify_exit_code(e: BaseException) -> VsphereExitCode:
    if isinstance(e, KeyboardInterrupt):
        return VsphereExitCode.INTERRUPTED

    # Treat VMwareError as "expected operational failure" buckets.
    if isinstance(e, VMwareError):
        if _is_usage_error(e):
            return VsphereExitCode.USAGE
        if _is_tool_missing_error(e):
            return VsphereExitCode.TOOL_MISSING
        if _is_auth_error(e):
            return VsphereExitCode.AUTH
        if _is_not_found_error(e):
            return VsphereExitCode.NOT_FOUND
        if _is_network_error(e):
            return VsphereExitCode.NETWORK
        if _is_external_tool_error(e):
            return VsphereExitCode.EXTERNAL_TOOL
        return VsphereExitCode.VSPHERE_API

    # Non-VMwareError exceptions
    if _is_usage_error(e):
        return VsphereExitCode.USAGE
    if _is_local_io_error(e):
        return VsphereExitCode.LOCAL_IO
    if _is_network_error(e):
        return VsphereExitCode.NETWORK
    if _is_tool_missing_error(e):
        return VsphereExitCode.TOOL_MISSING

    return VsphereExitCode.UNKNOWN
