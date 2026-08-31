# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Feature flags for h2kvm.

Controls experimental features and gradual rollouts. Flags can be set via:
  - Environment variables: H2KVM_FF_<FLAG_NAME>=1
  - Config file: feature_flags section in config.yaml
  - CLI: --enable-feature <name>

Usage:
    from h2kvm.core.feature_flags import is_enabled, enable, disable

    if is_enabled("ai_diagnostics"):
        run_ai_analysis()
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Default flag states (False = disabled, True = enabled)
_DEFAULTS: dict[str, bool] = {
    # Stable features (enabled by default)
    "vmcraft_backend": False,
    "fstab_stabilize": True,
    "initramfs_regen": True,
    "serial_console": True,
    "buslogic_autofix": True,
    # Beta features (disabled by default)
    "ai_diagnostics": False,
    "multi_drive": False,
    "live_migration": False,
    "parallel_conversion": False,
    "container_isolation": False,
    "incremental_sync": False,
    # Experimental features (disabled by default)
    "veeam_backup": False,
    "azure_live": False,
    "tpm_enrollment": False,
    "luks_auto_unlock": False,
    "network_topology_map": False,
}

# Runtime overrides
_overrides: dict[str, bool] = {}


def is_enabled(flag: str) -> bool:
    """Check if a feature flag is enabled."""
    # Runtime override takes precedence
    if flag in _overrides:
        return _overrides[flag]

    # Environment variable: H2KVM_FF_<FLAG>=1
    env_key = f"H2KVM_FF_{flag.upper()}"
    env_val = os.environ.get(env_key)
    if env_val is not None:
        return env_val in ("1", "true", "yes", "on")

    # Default
    return _DEFAULTS.get(flag, False)


def enable(flag: str) -> None:
    """Enable a feature flag at runtime."""
    _overrides[flag] = True
    logger.info("Feature flag enabled: %s", flag)


def disable(flag: str) -> None:
    """Disable a feature flag at runtime."""
    _overrides[flag] = False
    logger.info("Feature flag disabled: %s", flag)


def reset(flag: str | None = None) -> None:
    """Reset flag(s) to defaults."""
    if flag:
        _overrides.pop(flag, None)
    else:
        _overrides.clear()


def list_flags() -> dict[str, dict[str, Any]]:
    """List all flags with current state."""
    result = {}
    for flag, default in _DEFAULTS.items():
        result[flag] = {
            "default": default,
            "current": is_enabled(flag),
            "overridden": flag in _overrides,
            "env_var": f"H2KVM_FF_{flag.upper()}",
        }
    return result


def load_from_config(config: dict[str, Any]) -> None:
    """Load feature flags from a config dict."""
    flags = config.get("feature_flags", {})
    for flag, enabled in flags.items():
        if isinstance(enabled, bool):
            _overrides[flag] = enabled
            logger.debug("Feature flag from config: %s=%s", flag, enabled)
