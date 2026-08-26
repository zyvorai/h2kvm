# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Async VM manager for massive parallel validation (1000+ VMs)."""

import asyncio
from pathlib import Path

from .async_machine import AsyncMachine


class AsyncVMManager:
    """
    Async VM manager for high-scale parallel operations.

    Supports:
    - 1000+ parallel VM validation
    - Semaphore-based rate limiting
    - Batch operations
    - Automatic cleanup
    """

    def __init__(self, max_parallel: int = 100):
        """
        Initialize async manager.

        Args:
            max_parallel: Maximum concurrent VM operations
        """
        self.machines: dict[str, AsyncMachine] = {}
        self.semaphore = asyncio.Semaphore(max_parallel)

    async def create_machine(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # mirrors AsyncMachine's full VM config surface
        self,
        name: str,
        image: Path,
        memory_mb: int = 2048,
        cpus: int = 2,
        tpm: bool = False,
        vsock: bool = True,
        cloud_init: Path | None = None,
    ) -> AsyncMachine:
        """
        Create VM machine.

        Args:
            name: VM name
            image: Disk image
            memory_mb: Memory in MB
            cpus: CPU count
            tpm: Enable TPM
            vsock: Enable vsock
            cloud_init: Cloud-init config

        Returns:
            AsyncMachine instance
        """
        machine = AsyncMachine(
            name=name,
            image=image,
            memory_mb=memory_mb,
            cpus=cpus,
            tpm=tpm,
            vsock=vsock,
            cloud_init=cloud_init,
        )

        self.machines[name] = machine
        return machine

    async def start_machine(self, machine: AsyncMachine) -> None:
        """
        Start machine with semaphore rate limiting.

        Args:
            machine: Machine to start
        """
        async with self.semaphore:
            await machine.start()
            await machine.wait_running()

    async def start_all(self, machines: list[AsyncMachine]) -> None:
        """
        Start all machines in parallel.

        Args:
            machines: List of machines to start
        """
        tasks = [asyncio.create_task(self.start_machine(m)) for m in machines]

        await asyncio.gather(*tasks, return_exceptions=True)

    async def stop_all(self) -> None:
        """Stop all managed VMs."""
        tasks = [asyncio.create_task(m.stop()) for m in self.machines.values()]

        await asyncio.gather(*tasks, return_exceptions=True)

    async def terminate_all(self) -> None:
        """Force terminate all managed VMs."""
        tasks = [asyncio.create_task(m.terminate()) for m in self.machines.values()]

        await asyncio.gather(*tasks, return_exceptions=True)

    async def validate_batch(self, machines: list[AsyncMachine], validator_class) -> dict[str, bool]:
        """
        Validate batch of machines in parallel.

        Args:
            machines: Machines to validate
            validator_class: Validator class to use

        Returns:
            Dict mapping machine name to validation result
        """
        results = {}

        async def validate_one(machine):
            try:
                validator = validator_class(machine)
                result = await validator.validate()
                results[machine.name] = result
            except Exception:  # pylint: disable=broad-exception-caught  # one VM's validation failure must not abort the parallel batch
                results[machine.name] = False

        tasks = [asyncio.create_task(validate_one(m)) for m in machines]

        await asyncio.gather(*tasks, return_exceptions=True)

        return results

    def get_machine(self, name: str) -> AsyncMachine:
        """
        Get machine by name.

        Args:
            name: Machine name

        Returns:
            AsyncMachine instance
        """
        return self.machines[name]

    def list_machines(self) -> list[str]:
        """
        List all machine names.

        Returns:
            List of machine names
        """
        return list(self.machines.keys())
