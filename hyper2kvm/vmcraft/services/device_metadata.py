# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Device metadata helpers for VMCraft (blkid and partition caching)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, TypeVar

from ._runner import RunCommandFn, run_captured

if TYPE_CHECKING:
    import logging

T = TypeVar("T")


def _get_cached_value(
    cache: dict[str, tuple[T, float]],
    key: str,
    *,
    ttl_seconds: int,
) -> T | None:
    """Return cached value for key if present and within TTL."""
    entry = cache.get(key)
    if not entry:
        return None

    value, cache_time = entry
    if time.time() - cache_time < ttl_seconds:
        return value
    return None


def _parse_blkid_export(stdout: str) -> dict[str, str]:
    """Parse `blkid -o export` output into a metadata dictionary."""
    metadata: dict[str, str] = {}
    for line in stdout.strip().split("\n"):
        if "=" in line:
            key, value = line.split("=", 1)
            metadata[key] = value
    return metadata


def blkid_lookup(  # pylint: disable=too-many-arguments  # caller-managed cache state (dict+ttl) alongside lookup inputs is inherent here
    logger: logging.Logger,
    run_sudo: RunCommandFn,
    device: str,
    *,
    use_cache: bool,
    blkid_cache: dict[str, tuple[dict[str, str], float]],
    blkid_cache_ttl: int,
) -> dict[str, str]:
    """Resolve device metadata using blkid with optional cache."""
    if use_cache:
        cached_metadata = _get_cached_value(blkid_cache, device, ttl_seconds=blkid_cache_ttl)
        if cached_metadata is not None:
            logger.debug("Using cached blkid for %s", device)
            return cached_metadata

    try:
        cmd = ["blkid", "-p", "-o", "export", device]
        result = run_captured(logger, run_sudo, cmd, debug_failure=True)

        metadata = _parse_blkid_export(result.stdout)

        if use_cache:
            blkid_cache[device] = (metadata, time.time())

        logger.debug("blkid(%s): %s", device, metadata)
        return metadata
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort metadata lookup, must not abort the caller over a blkid failure
        logger.debug("blkid failed for %s: %s", device, e)
        return {}


def list_partitions_cached(  # pylint: disable=too-many-arguments  # caller-managed cache state alongside NBD lookup inputs is inherent here
    logger: logging.Logger,
    nbd_manager: Any | None,
    nbd_device: str | None,
    partition_cache: dict[str, tuple[list[str], float]],
    *,
    device: str | None = None,
    use_cache: bool = True,
) -> list[str]:
    """List partitions from NBD manager with optional 60s cache."""
    if not nbd_manager or not nbd_device:
        return []

    cache_key = device or nbd_device
    if use_cache:
        cached_parts = _get_cached_value(partition_cache, cache_key, ttl_seconds=60)
        if cached_parts is not None:
            logger.debug("Using cached partition list for %s", cache_key)
            return cached_parts

    partitions = nbd_manager.get_partitions(nbd_device)

    if use_cache:
        partition_cache[cache_key] = (partitions, time.time())

    return partitions


def invalidate_partition_cache(
    logger: logging.Logger,
    partition_cache: dict[str, tuple[list[str], float]],
    device: str | None = None,
) -> None:
    """Invalidate partition cache for one device or all devices."""
    if device:
        partition_cache.pop(device, None)
        logger.debug("Invalidated partition cache for %s", device)
    else:
        partition_cache.clear()
        logger.debug("Cleared all partition caches")
