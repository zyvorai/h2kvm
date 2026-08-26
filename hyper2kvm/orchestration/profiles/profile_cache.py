# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Profile caching for improved performance in batch conversions.

This module provides caching for profile loading to avoid redundant file I/O
and YAML parsing when the same profiles are used across multiple VMs.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


class ProfileCacheEntry:
    """A single cache entry for a profile."""

    def __init__(
        self,
        profile_data: dict[str, Any],
        mtime: float | None = None,
        source_path: Path | None = None,
    ):
        """
        Initialize cache entry.

        Args:
            profile_data: Resolved profile configuration
            mtime: File modification time (for custom profiles)
            source_path: Path to profile file (for custom profiles)
        """
        self.profile_data = profile_data
        self.mtime = mtime
        self.source_path = source_path
        self.created_at = time.time()
        self.access_count = 0
        self.last_accessed = time.time()

    def is_valid(self) -> bool:
        """
        Check if cache entry is still valid.

        For built-in profiles: always valid
        For custom profiles: check if file modification time changed

        Returns:
            True if cache entry is valid
        """
        # Built-in profiles never expire
        if self.source_path is None:
            return True

        # Check if custom profile file still exists
        if not self.source_path.exists():
            return False

        # Check if modification time changed
        current_mtime = self.source_path.stat().st_mtime
        return current_mtime == self.mtime

    def access(self) -> dict[str, Any]:
        """
        Access cached profile data.

        Returns:
            Profile configuration dictionary
        """
        self.access_count += 1
        self.last_accessed = time.time()
        return self.profile_data

    def __repr__(self) -> str:
        age = time.time() - self.created_at
        source = self.source_path.name if self.source_path else "builtin"
        return f"ProfileCacheEntry(source={source}, age={age:.1f}s, accesses={self.access_count})"


class ProfileCache:
    """
    Thread-safe cache for profile configurations.

    Features:
    - Caches built-in profiles (never expire)
    - Caches custom profiles with mtime validation
    - Thread-safe for parallel batch processing
    - Cache statistics and monitoring
    - Optional cache disabling
    """

    def __init__(self, enabled: bool = True, logger: logging.Logger | None = None):
        """
        Initialize profile cache.

        Args:
            enabled: Enable caching (default: True)
            logger: Logger instance
        """
        self.enabled = enabled
        self.logger = logger or logging.getLogger(__name__)
        self._cache: dict[str, ProfileCacheEntry] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
        self._invalidations = 0

    def get(self, profile_name: str) -> dict[str, Any] | None:
        """
        Get cached profile if available and valid.

        Args:
            profile_name: Name of profile to retrieve

        Returns:
            Profile configuration if cached and valid, else None
        """
        if not self.enabled:
            return None

        with self._lock:
            entry = self._cache.get(profile_name)

            if entry is None:
                self._misses += 1
                return None

            # Check if entry is still valid
            if not entry.is_valid():
                self.logger.debug("Profile cache: '%s' invalidated (file modified)", profile_name)
                del self._cache[profile_name]
                self._invalidations += 1
                self._misses += 1
                return None

            # Cache hit
            self._hits += 1
            self.logger.debug("Profile cache: HIT for '%s' (accesses=%s)", profile_name, entry.access_count + 1)
            return entry.access()

    def put(
        self,
        profile_name: str,
        profile_data: dict[str, Any],
        source_path: Path | None = None,
    ) -> None:
        """
        Store profile in cache.

        Args:
            profile_name: Name of profile
            profile_data: Profile configuration
            source_path: Path to profile file (None for built-in profiles)
        """
        if not self.enabled:
            return

        with self._lock:
            # Get mtime for custom profiles
            mtime = None
            if source_path and source_path.exists():
                mtime = source_path.stat().st_mtime

            entry = ProfileCacheEntry(
                profile_data=profile_data,
                mtime=mtime,
                source_path=source_path,
            )

            self._cache[profile_name] = entry

            source = source_path.name if source_path else "builtin"
            self.logger.debug(f"Profile cache: STORE '{profile_name}' (source={source})")

    def invalidate(self, profile_name: str) -> bool:
        """
        Invalidate a specific profile in cache.

        Args:
            profile_name: Name of profile to invalidate

        Returns:
            True if profile was in cache and invalidated
        """
        with self._lock:
            if profile_name in self._cache:
                del self._cache[profile_name]
                self._invalidations += 1
                self.logger.debug(f"Profile cache: INVALIDATE '{profile_name}'")
                return True
            return False

    def clear(self) -> None:
        """Clear all cached profiles."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._invalidations += count
            self.logger.debug(f"Profile cache: CLEAR (removed {count} entries)")

    def get_statistics(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0.0

            return {
                "enabled": self.enabled,
                "size": len(self._cache),
                "hits": self._hits,
                "misses": self._misses,
                "invalidations": self._invalidations,
                "total_requests": total_requests,
                "hit_rate_percent": hit_rate,
                "entries": {
                    name: {
                        "accesses": entry.access_count,
                        "age_seconds": time.time() - entry.created_at,
                        "source": (entry.source_path.name if entry.source_path else "builtin"),
                    }
                    for name, entry in self._cache.items()
                },
            }

    def log_statistics(self) -> None:
        """Log cache statistics."""
        stats = self.get_statistics()

        if not self.enabled:
            self.logger.info("Profile cache: DISABLED")
            return

        self.logger.info(
            "Profile cache statistics: %s hits, %s misses, %.1f%% hit rate, %s cached profiles",
            stats["hits"],
            stats["misses"],
            stats["hit_rate_percent"],
            stats["size"],
        )

        # Log individual entries
        for name, entry_stats in stats["entries"].items():
            self.logger.debug(
                "  - %s: %s accesses, %.1fs old, source=%s",
                name,
                entry_stats["accesses"],
                entry_stats["age_seconds"],
                entry_stats["source"],
            )

    def __repr__(self) -> str:
        stats = self.get_statistics()
        return (
            f"ProfileCache(enabled={self.enabled}, size={stats['size']}, "
            f"hit_rate={stats['hit_rate_percent']:.1f}%)"
        )


# Global cache instance (shared across all profile loaders)
_global_cache: ProfileCache | None = None  # pylint: disable=invalid-name  # mutable singleton reference, not a constant
_global_cache_lock = threading.Lock()


def get_global_cache(enabled: bool = True) -> ProfileCache:
    """
    Get global profile cache instance.

    Args:
        enabled: Enable caching (default: True)

    Returns:
        Global ProfileCache instance
    """
    global _global_cache  # pylint: disable=global-statement  # lazily initializes the module-level singleton cache

    with _global_cache_lock:
        if _global_cache is None:
            _global_cache = ProfileCache(enabled=enabled)
        return _global_cache


def reset_global_cache() -> None:
    """Reset global profile cache (for testing)."""
    global _global_cache  # pylint: disable=global-statement  # resets the module-level singleton cache for tests

    with _global_cache_lock:
        if _global_cache:
            _global_cache.clear()
        _global_cache = None


__all__ = [
    "ProfileCache",
    "ProfileCacheEntry",
    "get_global_cache",
    "reset_global_cache",
]
