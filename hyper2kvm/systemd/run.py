# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd-run integration for transient service execution.

This module wraps systemd-run to execute migration tasks in
isolated systemd scopes/services with resource limits.
"""

from __future__ import annotations

import subprocess

from hyper2kvm.systemd._common import check_systemd_binary_available


# run() is the sole public entrypoint by design; _check_available() is an internal helper.
# pylint: disable-next=too-few-public-methods
class SystemdRun:
    """
    Wrapper for systemd-run command-line tool.

    Executes commands in transient systemd scopes or services with
    resource limits, isolation, and proper cleanup.
    """

    def __init__(self, systemd_run: str = "systemd-run"):
        """
        Initialize systemd-run wrapper.

        Parameters
        ----------
        systemd_run : str, default="systemd-run"
            Path to systemd-run binary
        """
        self.binary = systemd_run
        self._check_available()

    def _check_available(self) -> None:
        """Check if systemd-run is available."""
        check_systemd_binary_available(
            self.binary,
            "systemd-run",
            solutions=["Install systemd (usually pre-installed)"],
        )

    # pylint: disable-next=too-many-arguments  # keyword-only systemd-run resource/isolation knobs
    def run(
        self,
        command: list[str],
        *,
        scope: bool = True,
        unit_name: str | None = None,
        description: str | None = None,
        memory_max: str | None = None,
        cpu_quota: str | None = None,
        io_weight: int | None = None,
        working_directory: str | None = None,
        user: bool = False,
        wait: bool = True,
    ) -> subprocess.CompletedProcess:
        """
        Execute command in systemd scope/service.

        Parameters
        ----------
        command : list[str]
            Command and arguments to execute
        scope : bool, default=True
            Run as scope (True) or service (False)
        unit_name : str | None
            Custom unit name
        description : str | None
            Unit description
        memory_max : str | None
            Maximum memory (e.g., "2G", "500M")
        cpu_quota : str | None
            CPU quota (e.g., "50%", "200%")
        io_weight : int | None
            I/O weight (1-10000)
        working_directory : str | None
            Working directory for command
        user : bool, default=False
            Run as user service (not system)
        wait : bool, default=True
            Wait for command to complete

        Returns
        -------
        subprocess.CompletedProcess
            Result of command execution

        Examples
        --------
        >>> runner = SystemdRun()
        >>> result = runner.run(
        ...     ["qemu-img", "convert", "input.vmdk", "output.qcow2"],
        ...     description="VM disk conversion",
        ...     memory_max="4G",
        ...     cpu_quota="200%",
        ... )
        """
        cmd = [self.binary]

        if scope:
            cmd.append("--scope")

        if user:
            cmd.append("--user")

        if wait:
            cmd.append("--wait")

        if unit_name:
            cmd.extend(["--unit", unit_name])

        if description:
            cmd.extend(["--description", description])

        if memory_max:
            cmd.extend(["--property", f"MemoryMax={memory_max}"])

        if cpu_quota:
            cmd.extend(["--property", f"CPUQuota={cpu_quota}"])

        if io_weight:
            cmd.extend(["--property", f"IOWeight={io_weight}"])

        if working_directory:
            cmd.extend(["--working-directory", working_directory])

        cmd.append("--")
        cmd.extend(command)

        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
