# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/vmcraft/_utils.py
"""
Shared utilities for VMCraft modules.

Provides common helper functions used across all VMCraft submodules.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

# MountError is unused in this module but re-exported by vmcraft/__init__.py (`from ._utils import ... MountError`).
from hyper2kvm.core.exceptions import MountError, VMCraftError  # noqa: F401  # pylint: disable=unused-import
from hyper2kvm.core.retry import retry_with_backoff
from hyper2kvm.core.utils import U

if TYPE_CHECKING:
    import logging


class DeviceError(VMCraftError):
    """Error with device operations (NBD, LVM, etc.)."""


class FileSystemError(VMCraftError):
    """Error with filesystem operations."""


class RegistryError(VMCraftError):
    """Error with Windows registry operations."""


class DetectionError(VMCraftError):
    """Error during OS/component detection."""


class CacheError(VMCraftError):
    """Error with cache operations."""


# Retry logic - Use core.retry for all retry operations
# Backward compatibility alias (not currently used in codebase)


def run_sudo(  # pylint: disable=too-many-arguments  # thin sudo/subprocess wrapper: each knob is a passthrough option
    logger: logging.Logger,
    cmd: list[str],
    *,
    check: bool = True,
    capture: bool = True,
    retry: bool = False,
    max_retries: int = 3,
    failure_log_level: int | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """
    Run a privileged command with optional sudo prefix and enhanced error handling.

    By default, commands are executed directly and the caller is expected to run
    vmcraft as root. Set `HYPER2KVM_VMCRAFT_USE_SUDO=1` to force sudo prefixing
    when running as non-root.

    Args:
        logger: Logger instance for output
        cmd: Command and arguments to execute
        check: Raise on non-zero exit (default: True)
        capture: Capture stdout/stderr (default: True)
        retry: Enable retry on failure (default: False)
        max_retries: Maximum retry attempts if retry=True (default: 3)
        failure_log_level: Log level for failures (default: ERROR, can be WARNING or DEBUG)
        env: Environment variables to pass to the command (default: None)

    Returns:
        CompletedProcess with command results

    Raises:
        DeviceError: If command fails and check=True

    Example:
        result = run_sudo(logger, ["mount", "/dev/sda1", "/mnt"], retry=True)
    """
    use_sudo = os.getenv("HYPER2KVM_VMCRAFT_USE_SUDO", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    effective_cmd = ["sudo", *cmd] if (os.geteuid() != 0 and use_sudo) else cmd

    try:
        if retry:
            # Use retry logic
            @retry_with_backoff(max_attempts=max_retries)
            def _run_with_retry():
                return U.run_cmd(
                    logger,
                    effective_cmd,
                    check=check,
                    capture=capture,
                    failure_log_level=failure_log_level,
                    env=env,
                )

            return _run_with_retry()
        return U.run_cmd(
            logger,
            effective_cmd,
            check=check,
            capture=capture,
            failure_log_level=failure_log_level,
            env=env,
        )

    except subprocess.CalledProcessError as e:
        # Enhance error with context
        cmd_str = " ".join(effective_cmd)
        context = {
            "command": cmd_str,
            "returncode": e.returncode,
            "stdout": e.stdout[:200] if e.stdout else None,  # Limit output
            "stderr": e.stderr[:200] if e.stderr else None,
        }

        if check:
            raise DeviceError(msg=f"Command failed: {cmd_str}", context=context) from e
        logger.debug(f"Command failed (check=False): {cmd_str}, rc={e.returncode}")
        # Return CompletedProcess even on failure when check=False
        return subprocess.CompletedProcess(
            args=effective_cmd, returncode=e.returncode, stdout=e.stdout or "", stderr=e.stderr or ""
        )


def validate_path(
    path: str, must_exist: bool = False, must_be_file: bool = False, must_be_dir: bool = False
) -> None:
    """
    Validate path with helpful error messages.

    Args:
        path: Path to validate
        must_exist: Path must exist
        must_be_file: Path must be a file
        must_be_dir: Path must be a directory

    Raises:
        FileSystemError: If validation fails
    """
    p = Path(path)

    if must_exist and not p.exists():
        raise FileSystemError(
            msg=f"Path does not exist: {path}", context={"path": path, "absolute": str(p.absolute())}
        )

    if must_be_file and not p.is_file():
        raise FileSystemError(
            msg=f"Path is not a file: {path}",
            context={"path": path, "exists": p.exists(), "is_dir": p.is_dir()},
        )

    if must_be_dir and not p.is_dir():
        raise FileSystemError(
            msg=f"Path is not a directory: {path}",
            context={"path": path, "exists": p.exists(), "is_file": p.is_file()},
        )
