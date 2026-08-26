# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Async machine operations for high-scale VM validation."""

import asyncio
import time
from pathlib import Path

from hyper2kvm.vmspawn.exceptions import VMStartError


class AsyncMachine:  # pylint: disable=too-many-instance-attributes  # models the full set of independent systemd-vmspawn launch parameters
    """
    Async VM machine for non-blocking operations.

    Supports:
    - Async start/stop
    - TPM emulation
    - vsock communication
    - cloud-init injection
    - 1000+ parallel VM support
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # each argument maps 1:1 to a distinct systemd-vmspawn launch parameter
        self,
        name: str,
        image: Path,
        memory_mb: int = 2048,
        cpus: int = 2,
        timeout: int = 120,
        tpm: bool = False,
        vsock: bool = True,
        cloud_init: Path | None = None,
    ):
        """
        Initialize async machine.

        Args:
            name: VM name
            image: Disk image path
            memory_mb: Memory in MB
            cpus: Number of CPUs
            timeout: Boot timeout
            tpm: Enable TPM emulation
            vsock: Enable vsock
            cloud_init: Cloud-init config path
        """
        self.name = name
        self.image = image
        self.memory_mb = memory_mb
        self.cpus = cpus
        self.timeout = timeout
        self.tpm = tpm
        self.vsock = vsock
        self.cloud_init = cloud_init

    async def start(self) -> None:
        """
        Start VM asynchronously.

        Raises:
            Exception: If VM fails to start
        """
        cmd = [
            "systemd-vmspawn",
            f"--machine={self.name}",
            f"--image={self.image}",
            f"--memory={self.memory_mb}M",
            f"--cpus={self.cpus}",
            "--quiet",
        ]

        if self.tpm:
            cmd.append("--tpm")

        if self.vsock:
            cmd.append("--vsock=yes")

        if self.cloud_init:
            cmd.append(f"--cloud-init={self.cloud_init}")

        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise VMStartError(
                f"Failed to start VM '{self.name}': {stderr.decode().strip()}. "
                f"Check that the disk image exists and systemd-vmspawn is installed."
            )

    async def stop(self) -> None:
        """Stop VM gracefully."""
        proc = await asyncio.create_subprocess_exec(
            "machinectl",
            "stop",
            self.name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        await proc.wait()

    async def terminate(self) -> None:
        """Force terminate VM."""
        proc = await asyncio.create_subprocess_exec(
            "machinectl",
            "terminate",
            self.name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        await proc.wait()

    async def is_running(self) -> bool:
        """
        Check if VM is running.

        Returns:
            True if VM is in running state
        """
        proc = await asyncio.create_subprocess_exec(
            "machinectl",
            "show",
            self.name,
            "--property=State",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, _ = await proc.communicate()

        return b"running" in stdout.lower()

    async def wait_running(self) -> None:
        """
        Wait for VM to reach running state.

        Raises:
            TimeoutError: If VM doesn't start within timeout
        """
        start = time.time()

        while time.time() - start < self.timeout:
            if await self.is_running():
                return

            await asyncio.sleep(1)

        raise TimeoutError(f"VM {self.name} failed to start within {self.timeout}s")

    async def exec(self, command: str) -> str:
        """
        Execute command in VM.

        Args:
            command: Shell command

        Returns:
            Command output
        """
        proc = await asyncio.create_subprocess_exec(
            "machinectl",
            "shell",
            self.name,
            "/bin/sh",
            "-c",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, _ = await proc.communicate()

        return stdout.decode()

    async def journal(self, lines: int = 200) -> str:
        """
        Get VM journal logs.

        Args:
            lines: Number of lines

        Returns:
            Journal output
        """
        proc = await asyncio.create_subprocess_exec(
            "journalctl",
            "-M",
            self.name,
            "-n",
            str(lines),
            "--no-pager",
            stdout=asyncio.subprocess.PIPE,
        )

        stdout, _ = await proc.communicate()

        return stdout.decode()
