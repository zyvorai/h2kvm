# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""System-wide configuration loader for h2kvm."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

from h2kvm.core.utils import effective_cpu_count

# User-level configuration (highest precedence)
_xdg_config = os.environ.get("XDG_CONFIG_HOME", str(Path("~/.config").expanduser()))
USER_CONFIG_PATHS = [
    Path(_xdg_config) / "h2kvm" / "config.yaml",
    Path(_xdg_config) / "h2kvm" / "config.yml",
    Path.home() / ".h2kvm.yaml",
]

# System-wide configuration locations (in order of precedence)
SYSTEM_CONFIG_PATHS = [
    Path("/etc/h2kvm/config.yaml"),
    Path("/etc/h2kvm/config.yml"),
    Path("/usr/local/etc/h2kvm/config.yaml"),
]


def load_system_config(logger: logging.Logger | None = None) -> dict[str, Any]:
    """
    Load system-wide configuration from /etc/h2kvm/config.yaml.

    Returns empty dict if no system config exists.
    This is merged as the base layer before user configs.
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    # Check user-level config first (higher precedence)
    for config_path in USER_CONFIG_PATHS:
        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                logger.debug("Loaded user config from %s", config_path)
                return data
            except (OSError, yaml.YAMLError) as e:
                logger.warning("Failed to load user config from %s: %s", config_path, e)
                continue

    # Fall back to system-wide config
    for config_path in SYSTEM_CONFIG_PATHS:
        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                logger.debug("Loaded system config from %s", config_path)
                return data
            except (OSError, yaml.YAMLError) as e:
                logger.warning("Failed to load system config from %s: %s", config_path, e)
                continue

    logger.debug("No system config found, using defaults")
    return {}


def get_allowed_dirs(logger: logging.Logger | None = None) -> list[str]:
    """Get allowed directories from system config."""
    system_config = load_system_config(logger)
    return system_config.get("allowed_dirs", [])


def get_conversion_dir(logger: logging.Logger | None = None) -> str | None:
    """Get conversion cache directory from system config."""
    system_config = load_system_config(logger)
    conversion = system_config.get("conversion", {})
    return conversion.get("cache_dir")


def get_smart_defaults(logger: logging.Logger | None = None) -> dict[str, Any]:
    """
    Return CPU-aware default values for performance-sensitive settings.

    Values are capped to avoid over-subscribing small or large machines:
        - workers: min(cpu_count, 8) — parallel disk processing workers
        - max_concurrent_jobs: min(cpu_count, 8) — daemon concurrent job limit
        - io_threads: min(cpu_count // 2 or 1, 4) — qemu-nbd I/O threads

    Args:
        logger: Logger instance (optional)

    Returns:
        Dictionary with smart defaults suitable for merging into user config.

    Example:
        defaults = get_smart_defaults()
        # {'workers': 4, 'max_concurrent_jobs': 4, 'io_threads': 2, 'cpu_count': 4}
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    cpu_count = effective_cpu_count()
    workers = min(cpu_count, 8)
    io_threads = min(max(cpu_count // 2, 1), 4)

    defaults = {
        "workers": workers,
        "max_concurrent_jobs": workers,
        "io_threads": io_threads,
        "cpu_count": cpu_count,
    }

    logger.debug(
        "Smart defaults: workers=%d, max_concurrent_jobs=%d, io_threads=%d (cpu_count=%d)",
        workers,
        workers,
        io_threads,
        cpu_count,
    )
    return defaults


def merge_with_system_config(
    user_config: dict[str, Any], logger: logging.Logger | None = None
) -> dict[str, Any]:
    """
    Merge user configuration with system-wide configuration.

    System config provides defaults that user config can override.

    Args:
        user_config: User's migration config
        logger: Logger instance

    Returns:
        Merged configuration (user config takes precedence)
    """
    system_config = load_system_config(logger)

    # Start with system config as base
    merged = system_config.copy()

    # Merge allowed_dirs (append user dirs to system dirs)
    system_dirs = system_config.get("allowed_dirs", [])
    user_dirs = user_config.get("allowed_dirs", [])
    if system_dirs or user_dirs:
        # Combine and deduplicate
        all_dirs = list(dict.fromkeys(system_dirs + user_dirs))
        merged["allowed_dirs"] = all_dirs

    # Merge libvirt defaults
    if "libvirt" in system_config:
        libvirt_defaults = system_config["libvirt"]
        # Apply defaults only if user hasn't specified
        if "libvirt_network" not in user_config and "default_network" in libvirt_defaults:
            merged["libvirt_network"] = libvirt_defaults["default_network"]
        if "machine" not in user_config and "default_machine" in libvirt_defaults:
            merged["machine"] = libvirt_defaults["default_machine"]
        if "vcpus" not in user_config and "default_vcpus" in libvirt_defaults:
            merged["vcpus"] = libvirt_defaults["default_vcpus"]
        if "memory" not in user_config and "default_memory_mb" in libvirt_defaults:
            merged["memory"] = libvirt_defaults["default_memory_mb"]

    # User config overrides system config for all other keys
    for key, value in user_config.items():
        if key not in ("allowed_dirs",):  # Skip already-merged keys
            merged[key] = value

    return merged
