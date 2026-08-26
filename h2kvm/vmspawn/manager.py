# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""High-level VM manager."""

from pathlib import Path

from .machine import Machine
from .models import VMConfig


class VMSpawnManager:
    """
    High-level VM manager.

    Manages multiple VMs with simplified API.
    """

    def __init__(self):
        """Initialize VM manager."""
        self.machines: dict[str, Machine] = {}

    def create(  # pylint: disable=too-many-arguments  # each param is an independent VM config knob
        self,
        name: str,
        image: Path,
        *,
        memory_mb: int = 2048,
        cpus: int = 2,
        timeout: int = 120,
        vsock: bool = True,
        network_user: bool = True,
    ) -> Machine:
        """
        Create new VM configuration.

        Args:
            name: VM name
            image: Path to disk image
            memory_mb: Memory in MB
            cpus: Number of CPUs
            timeout: Boot timeout in seconds
            vsock: Enable vsock
            network_user: Enable user-mode networking

        Returns:
            Machine instance
        """
        config = VMConfig(
            name=name,
            image=image,
            memory_mb=memory_mb,
            cpus=cpus,
            timeout=timeout,
            vsock=vsock,
            network_user=network_user,
        )

        machine = Machine(config)
        self.machines[name] = machine

        return machine

    def start(self, name: str) -> None:
        """
        Start VM and wait for boot.

        Args:
            name: VM name
        """
        machine = self.machines[name]
        machine.start()
        machine.wait_for_running()

    def stop(self, name: str) -> None:
        """
        Stop VM gracefully.

        Args:
            name: VM name
        """
        self.machines[name].stop()

    def terminate(self, name: str) -> None:
        """
        Force terminate VM.

        Args:
            name: VM name
        """
        self.machines[name].terminate()

    def destroy(self, name: str) -> None:
        """
        Stop and remove VM.

        Args:
            name: VM name
        """
        try:
            self.stop(name)
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort stop before removal, must not block destroy
            pass
        del self.machines[name]

    def get(self, name: str) -> Machine:
        """
        Get machine by name.

        Args:
            name: VM name

        Returns:
            Machine instance
        """
        return self.machines[name]

    def list(self) -> list[str]:
        """
        List all managed VMs.

        Returns:
            List of VM names
        """
        return list(self.machines.keys())
