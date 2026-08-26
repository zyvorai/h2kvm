# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/vmware/async_client/semaphore.py
"""
Concurrency management for async operations.

Controls the number of parallel operations to prevent overwhelming
the vCenter server or network.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ConcurrencyLimits:
    """Limits for concurrent operations."""

    max_concurrent_vms: int = 5  # Max VMs to migrate in parallel
    max_concurrent_exports: int = 3  # Max disk exports per VM
    max_api_calls_per_second: int = 10  # Rate limit for API calls
    max_connections: int = 10  # Max HTTP connections


class ConcurrencyManager:
    """
    Manages concurrency limits for async operations.

    Uses semaphores to limit:
    - Number of concurrent VM migrations
    - Number of concurrent disk exports per VM
    - API call rate limiting
    - HTTP connection pooling

    Example:
        >>> manager = ConcurrencyManager(max_concurrent_vms=5)
        >>> async with manager.vm_slot():
        ...     await migrate_vm()
    """

    def __init__(
        self,
        max_concurrent_vms: int = 5,
        max_concurrent_exports: int = 3,
        max_api_calls_per_second: int = 10,
        max_connections: int = 10,
    ):
        """
        Initialize concurrency manager.

        Args:
            max_concurrent_vms: Maximum VMs to process in parallel
            max_concurrent_exports: Maximum disk exports per VM
            max_api_calls_per_second: API call rate limit
            max_connections: Maximum HTTP connections
        """
        self.limits = ConcurrencyLimits(
            max_concurrent_vms=max_concurrent_vms,
            max_concurrent_exports=max_concurrent_exports,
            max_api_calls_per_second=max_api_calls_per_second,
            max_connections=max_connections,
        )

        # Semaphores for concurrency control
        self._vm_semaphore = asyncio.Semaphore(max_concurrent_vms)
        self._export_semaphore = asyncio.Semaphore(max_concurrent_exports)
        self._api_semaphore = asyncio.Semaphore(max_api_calls_per_second)

        # Rate limiting
        self._api_last_call = 0.0
        self._api_interval = 1.0 / max_api_calls_per_second if max_api_calls_per_second > 0 else 0

        # Statistics
        self._stats = {
            "vms_active": 0,
            "exports_active": 0,
            "api_calls_total": 0,
            "api_calls_throttled": 0,
        }

    def vm_slot(self):
        """
        Context manager for VM migration slot.

        Limits number of concurrent VM migrations.

        Example:
            >>> async with manager.vm_slot():
            ...     await migrate_vm()
        """
        return _SemaphoreContext(self._vm_semaphore, "vms_active", self._stats)

    def export_slot(self):
        """
        Context manager for disk export slot.

        Limits number of concurrent disk exports.

        Example:
            >>> async with manager.export_slot():
            ...     await export_disk()
        """
        return _SemaphoreContext(self._export_semaphore, "exports_active", self._stats)

    async def api_call(self):
        """
        Rate-limited API call context.

        Ensures API calls don't exceed rate limit.

        Example:
            >>> async with await manager.api_call():
            ...     result = await client.get_vm_info()
        """
        async with self._api_semaphore:
            # Rate limiting
            if self._api_interval > 0:
                loop = asyncio.get_event_loop()
                now = loop.time()
                time_since_last = now - self._api_last_call

                if time_since_last < self._api_interval:
                    sleep_time = self._api_interval - time_since_last
                    self._stats["api_calls_throttled"] += 1
                    await asyncio.sleep(sleep_time)

                self._api_last_call = loop.time()

            self._stats["api_calls_total"] += 1

    def get_stats(self) -> dict:
        """Get current statistics."""
        # pylint: disable=protected-access
        # reason: asyncio.Semaphore exposes no public API for the remaining slot
        # count; `_value` is the only way to report it in get_stats().
        return {
            **self._stats,
            "vm_slots_available": self._vm_semaphore._value,
            "export_slots_available": self._export_semaphore._value,
            "api_slots_available": self._api_semaphore._value,
        }

    def __repr__(self) -> str:
        stats = self.get_stats()
        return (
            f"ConcurrencyManager("
            f"vms_active={stats['vms_active']}/{self.limits.max_concurrent_vms}, "
            f"exports_active={stats['exports_active']}/{self.limits.max_concurrent_exports}, "
            f"api_calls={stats['api_calls_total']}"
            f")"
        )


class _SemaphoreContext:
    """Context manager helper for semaphore with stats tracking."""

    def __init__(self, semaphore: asyncio.Semaphore, stat_key: str, stats: dict):
        self.semaphore = semaphore
        self.stat_key = stat_key
        self.stats = stats

    async def __aenter__(self):
        await self.semaphore.acquire()
        self.stats[self.stat_key] += 1
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.stats[self.stat_key] -= 1
        self.semaphore.release()
        return False
