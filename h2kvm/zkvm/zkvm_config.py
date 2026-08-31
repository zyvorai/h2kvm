# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/zkvm/zkvm_config.py
"""
TUI configuration management.

Handles loading and saving TUI-specific settings to a user config file.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

# Default configuration file path
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "h2kvm"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "zkvm.json"


class TUIConfig:
    """
    Manages TUI configuration settings.

    Settings are stored in ~/.config/h2kvm/tui.json by default.
    """

    def __init__(self, config_path: Path | None = None, logger: logging.Logger | None = None):
        """
        Initialize TUI config manager.

        Args:
            config_path: Optional custom path to config file
            logger: Optional logger for debug output
        """
        self.config_path = config_path or DEFAULT_CONFIG_FILE
        self.logger = logger or logging.getLogger(__name__)
        self.settings: dict[str, Any] = {}

    def load(self) -> dict[str, Any]:
        """
        Load settings from config file.

        Returns:
            Dict of settings (empty dict if file doesn't exist or has errors)
        """
        if not self.config_path.exists():
            self.logger.debug("Config file not found: %s, using defaults", self.config_path)
            return {}

        try:
            with open(self.config_path, encoding="utf-8") as f:
                self.settings = json.load(f)
            self.logger.debug("Loaded TUI config from %s", self.config_path)
            return self.settings
        except json.JSONDecodeError as e:
            self.logger.warning("Invalid JSON in config file %s: %s, using defaults", self.config_path, e)
            return {}
        except OSError as e:
            self.logger.warning("Failed to load config from %s: %s, using defaults", self.config_path, e)
            return {}

    def save(self, settings: dict[str, Any]) -> bool:
        """
        Save settings to config file.

        Args:
            settings: Dict of settings to save

        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure config directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            # Write settings to file with nice formatting
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2, sort_keys=True)

            self.settings = settings
            self.logger.debug("Saved TUI config to %s", self.config_path)
            return True

        except (OSError, TypeError) as e:
            self.logger.exception("Failed to save config to %s: %s", self.config_path, e)
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a setting value.

        Args:
            key: Setting key (supports dot notation for nested keys)
            default: Default value if key doesn't exist

        Returns:
            Setting value or default
        """
        # Support dot notation for nested keys (e.g., "migration.default_format")
        keys = key.split(".")
        value = self.settings

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any) -> None:
        """
        Set a setting value.

        Args:
            key: Setting key (supports dot notation for nested keys)
            value: Value to set
        """
        # Support dot notation for nested keys
        keys = key.split(".")
        current = self.settings

        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]

        current[keys[-1]] = value

    def get_all(self) -> dict[str, Any]:
        """
        Get all settings.

        Returns:
            Dict of all settings
        """
        return self.settings.copy()

    def update(self, settings: dict[str, Any]) -> None:
        """
        Update multiple settings.

        Args:
            settings: Dict of settings to update
        """
        self._deep_update(self.settings, settings)

    def _deep_update(self, base: dict[str, Any], updates: dict[str, Any]) -> None:
        """
        Recursively update a dict with another dict.

        Args:
            base: Base dict to update
            updates: Dict with updates
        """
        for key, value in updates.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_update(base[key], value)
            else:
                base[key] = value


def get_default_settings() -> dict[str, Any]:
    """
    Get default TUI settings.

    Returns:
        Dict of default settings matching the structure expected by SettingsPanel
    """
    return {
        # General
        "general": {
            "default_output_dir": "/tmp/h2kvm-output",
            "log_level": "info",
            "log_to_file": True,
            "log_file_path": "/tmp/h2kvm.log",
        },
        # Migration
        "migration": {
            "default_format": "qcow2",
            "enable_compression": True,
            "parallel_migrations": 2,
            "skip_existing": False,
        },
        # vSphere
        "vsphere": {
            "vcenter_host": "",
            "vcenter_username": "",
            "vcenter_save_credentials": False,
            "vcenter_verify_ssl": True,
        },
        # Offline Fixes
        "offline_fixes": {
            "fstab_mode": "stabilize-all",
            "regen_initramfs": True,
            "update_grub": True,
            "fix_network": True,
            "enhanced_chroot": True,
        },
        # Performance
        "performance": {
            "max_concurrent_operations": 4,
            "operation_timeout": 3600,
            "network_timeout": 300,
        },
        # Advanced
        "advanced": {
            "guestfs_backend": "guestkit",
            "debug_mode": False,
            "verbose_output": False,
        },
    }


def load_tui_settings(
    config_path: Path | None = None, logger: logging.Logger | None = None
) -> dict[str, Any]:
    """
    Convenience function to load TUI settings.

    Args:
        config_path: Optional custom path to config file
        logger: Optional logger

    Returns:
        Dict of settings (merged with defaults)
    """
    config = TUIConfig(config_path, logger)
    settings = config.load()

    # Merge with defaults (settings override defaults)
    defaults = get_default_settings()
    config_manager = TUIConfig(logger=logger)
    config_manager.settings = defaults
    config_manager.update(settings)

    return config_manager.get_all()


def save_tui_settings(
    settings: dict[str, Any], config_path: Path | None = None, logger: logging.Logger | None = None
) -> bool:
    """
    Convenience function to save TUI settings.

    Args:
        settings: Settings to save
        config_path: Optional custom path to config file
        logger: Optional logger

    Returns:
        True if successful, False otherwise
    """
    config = TUIConfig(config_path, logger)
    return config.save(settings)
