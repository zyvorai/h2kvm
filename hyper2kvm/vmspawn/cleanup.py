# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Automatic cleanup engine for VM resources."""

import asyncio
import fnmatch
import logging

from .async_machine import AsyncMachine

logger = logging.getLogger(__name__)


class CleanupEngine:
    """
    Automatic resource cleanup for VMs.

    Handles:
    - Failed VM cleanup
    - Batch cleanup
    - Graceful shutdown
    - Force termination
    """

    def __init__(self, machines: list[AsyncMachine]):
        """
        Initialize cleanup engine.

        Args:
            machines: List of machines to manage
        """
        self.machines = machines

    async def cleanup_failed(self) -> int:
        """
        Clean up failed VMs.

        Returns:
            Number of VMs cleaned up
        """
        cleaned = 0

        for machine in self.machines:
            try:
                if not await machine.is_running():
                    logger.info("Cleaning up failed VM: %s", machine.name)
                    await machine.terminate()
                    cleaned += 1
            except Exception as e:  # pylint: disable=broad-exception-caught
                # reason: best-effort cleanup of one VM must not abort cleanup of the rest
                logger.exception("Error cleaning up %s: %s", machine.name, e)

        return cleaned

    async def cleanup_all(self, graceful: bool = True) -> None:
        """
        Clean up all VMs.

        Args:
            graceful: Use graceful shutdown vs force terminate
        """
        logger.info("Cleaning up %d VMs (graceful=%s)", len(self.machines), graceful)

        if graceful:
            tasks = [asyncio.create_task(m.stop()) for m in self.machines]
        else:
            tasks = [asyncio.create_task(m.terminate()) for m in self.machines]

        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("Cleanup complete")

    async def cleanup_by_pattern(self, pattern: str) -> int:
        """
        Clean up VMs matching name pattern.

        Args:
            pattern: VM name pattern (e.g., "test-*")

        Returns:
            Number of VMs cleaned up
        """
        cleaned = 0

        for machine in self.machines:
            if fnmatch.fnmatch(machine.name, pattern):
                logger.info("Cleaning up %s (matches %s)", machine.name, pattern)
                await machine.terminate()
                cleaned += 1

        return cleaned

    async def cleanup_timeout(self, _timeout_seconds: int = 300) -> int:
        """
        Clean up VMs running longer than timeout.

        Args:
            _timeout_seconds: Max runtime in seconds (not yet used: this would
                require tracking each VM's start time; for now all running VMs
                are cleaned up regardless of runtime)

        Returns:
            Number of VMs cleaned up
        """

        cleaned = 0

        for machine in self.machines:
            # This would require tracking start time
            # For now, just cleanup all running VMs
            try:
                if await machine.is_running():
                    logger.info("Terminating long-running VM: %s", machine.name)
                    await machine.terminate()
                    cleaned += 1
            except Exception as e:  # pylint: disable=broad-exception-caught
                # reason: best-effort cleanup of one VM must not abort cleanup of the rest
                logger.exception("Error terminating %s: %s", machine.name, e)

        return cleaned
