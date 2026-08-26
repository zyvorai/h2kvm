# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Core machine operations for systemd-vmspawn."""

import subprocess
import time

from .exceptions import VMStartError, VMStopError, VMTimeoutError
from .models import VMConfig, VMStatus


class Machine:
    """
    Low-level machine operations.

    Wraps systemd-vmspawn and machinectl for VM lifecycle management.
    """

    def __init__(self, config: VMConfig):
        """
        Initialize machine.

        Args:
            config: VM configuration
        """
        self.config = config

    def start(self) -> None:
        """
        Start VM using systemd-vmspawn.

        Raises:
            VMStartError: If VM fails to start
        """
        cmd = [
            "systemd-vmspawn",
            f"--machine={self.config.name}",
            f"--image={self.config.image}",
            f"--memory={self.config.memory_mb}M",
            f"--cpus={self.config.cpus}",
            "--quiet",
        ]

        if self.config.vsock:
            cmd.append("--vsock=yes")

        if self.config.network_user:
            cmd.append("--network-user-mode")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)

        if result.returncode != 0:
            raise VMStartError(f"Failed to start VM {self.config.name}: {result.stderr}")

    def stop(self) -> None:
        """
        Stop VM gracefully.

        Raises:
            VMStopError: If VM fails to stop
        """
        cmd = ["machinectl", "stop", self.config.name]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)

        if result.returncode != 0:
            raise VMStopError(f"Failed to stop VM {self.config.name}: {result.stderr}")

    def terminate(self) -> None:
        """Force terminate VM."""
        cmd = ["machinectl", "terminate", self.config.name]
        subprocess.run(cmd, capture_output=True, text=True, check=False)

    def status(self) -> VMStatus:
        """
        Get VM status.

        Returns:
            VMStatus with current VM state
        """
        cmd = ["machinectl", "show", self.config.name, "--property=State"]

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        running = "running" in result.stdout.lower()
        state = None

        if "=" in result.stdout:
            state = result.stdout.split("=")[1].strip()

        return VMStatus(name=self.config.name, running=running, pid=self._get_pid(), state=state)

    def wait_for_running(self, timeout: int | None = None) -> None:
        """
        Wait for VM to reach running state.

        Args:
            timeout: Timeout in seconds (uses config.timeout if None)

        Raises:
            VMTimeoutError: If VM doesn't start within timeout
        """
        timeout = timeout or self.config.timeout
        start = time.time()

        while time.time() - start < timeout:
            try:
                if self.status().running:
                    return
            except Exception:  # pylint: disable=broad-exception-caught
                # reason: status() may transiently fail while the VM is still coming
                # up; keep polling until the timeout instead of aborting the wait
                pass

            time.sleep(2)

        raise VMTimeoutError(f"VM {self.config.name} failed to start within {timeout}s")

    def exec(self, command: str, timeout: int = 30) -> str:
        """
        Execute command inside VM.

        Args:
            command: Shell command to execute
            timeout: Command timeout in seconds

        Returns:
            Command stdout
        """
        cmd = ["machinectl", "shell", self.config.name, "/bin/sh", "-c", command]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)

        return result.stdout

    def journal(self, lines: int = 200) -> str:
        """
        Get VM journal logs.

        Args:
            lines: Number of log lines to retrieve

        Returns:
            Journal logs as string
        """
        cmd = ["journalctl", "-M", self.config.name, "-n", str(lines), "--no-pager"]

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        return result.stdout

    def _get_pid(self) -> int | None:
        """Get VM leader process PID."""
        cmd = ["machinectl", "show", self.config.name, "--property=Leader"]

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if "=" in result.stdout:
            try:
                return int(result.stdout.split("=")[1].strip())
            except ValueError:
                return None

        return None
