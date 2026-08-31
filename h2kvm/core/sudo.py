# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Privileged command helpers for offline guest fix paths."""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

from h2kvm.core.exceptions import DeviceError
from h2kvm.core.retry import retry_with_backoff
from h2kvm.core.utils import U

if TYPE_CHECKING:
    import logging


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
    as root. Set ``H2KVM_USE_SUDO=1`` (or legacy ``H2KVM_VMCRAFT_USE_SUDO=1``)
    to force sudo prefixing when running as non-root.
    """
    use_sudo_env = os.getenv("H2KVM_USE_SUDO") or os.getenv("H2KVM_VMCRAFT_USE_SUDO", "")
    use_sudo = use_sudo_env.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    effective_cmd = ["sudo", *cmd] if (os.geteuid() != 0 and use_sudo) else cmd

    try:
        if retry:

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
        cmd_str = " ".join(effective_cmd)
        context = {
            "command": cmd_str,
            "returncode": e.returncode,
            "stdout": e.stdout[:200] if e.stdout else None,
            "stderr": e.stderr[:200] if e.stderr else None,
        }

        if check:
            raise DeviceError(msg=f"Command failed: {cmd_str}", context=context) from e
        logger.debug(f"Command failed (check=False): {cmd_str}, rc={e.returncode}")
        return subprocess.CompletedProcess(
            args=effective_cmd, returncode=e.returncode, stdout=e.stdout or "", stderr=e.stderr or ""
        )
