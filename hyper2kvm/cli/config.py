# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/cli/config.py
"""
Configuration management for CLI.

Handles loading and saving migration configurations.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from hyper2kvm.core.exceptions import ConfigurationError

logger = logging.getLogger(__name__)


@dataclass
class MigrationConfig:  # pylint: disable=too-many-instance-attributes  # dataclass models config with many independent fields
    """
    Migration configuration.

    Attributes:
        source_path: Source VM disk image path
        target_path: Target VM path (optional)
        source_format: Source disk format
        target_format: Target disk format
        readonly: Mount source read-only
        create_snapshot: Create pre-migration snapshot
        fix_bootloader: Fix bootloader configuration
        fix_network: Fix network configuration
        stabilize_fstab: Stabilize fstab entries
        run_validation: Run post-migration validation
        validate_services: Validate services
        validate_network: Validate network
        validate_databases: Validate databases
        output_dir: Output directory for reports
        metadata: Additional metadata
    """

    source_path: str
    target_path: str | None = None
    source_format: str = "qcow2"
    target_format: str = "qcow2"
    readonly: bool = True
    create_snapshot: bool = True
    fix_bootloader: bool = True
    fix_network: bool = True
    stabilize_fstab: bool = True
    run_validation: bool = True
    validate_services: bool = True
    validate_network: bool = True
    validate_databases: bool = True
    output_dir: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MigrationConfig:
        """Create from dictionary."""
        # Filter out unknown fields
        valid_fields = {f.name for f in fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)


class ConfigManager:
    """
    Configuration manager.

    Loads and saves migration configurations from/to files.
    """

    def __init__(self, logger_instance: logging.Logger | None = None):
        """
        Initialize configuration manager.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)

    def load_config(self, config_file: str | Path) -> MigrationConfig:
        """
        Load configuration from file.

        Args:
            config_file: Path to configuration file (JSON or YAML)

        Returns:
            Migration configuration

        Raises:
            FileNotFoundError: If config file not found
            ConfigurationError: If config file is invalid
        """
        config_path = Path(config_file)

        if not config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {config_path}\n"
                f"    Verify the path is correct (absolute paths recommended).\n"
                f"    Create a config file with: h2kvmctl --generate-config > {config_path}"
            )

        self.logger.info(f"Loading configuration from {config_path}")

        try:
            # Determine format from extension
            if config_path.suffix.lower() in [".yaml", ".yml"]:
                data = self._load_yaml(config_path)
            elif config_path.suffix.lower() == ".json":
                data = self._load_json(config_path)
            else:
                # Try JSON first, then YAML
                try:
                    data = self._load_json(config_path)
                except (json.JSONDecodeError, ValueError):
                    data = self._load_yaml(config_path)

            return MigrationConfig.from_dict(data)

        except Exception as e:
            raise ConfigurationError(
                code=78, msg=f"Failed to load configuration from {config_path}: {e}"
            ).with_context(
                solutions=[
                    "Verify the file format is valid JSON or YAML",
                    "Check file permissions are readable",
                    "Ensure required fields are present (source_path)",
                ],
                config_file=str(config_path),
            ) from e

    def save_config(
        self,
        config: MigrationConfig,
        config_file: str | Path,
        *,
        config_format: str = "json",
    ) -> None:
        """
        Save configuration to file.

        Args:
            config: Migration configuration
            config_file: Path to configuration file
            config_format: Output format ("json" or "yaml")

        Raises:
            ConfigurationError: If format is invalid
        """
        config_path = Path(config_file)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        self.logger.info(f"Saving configuration to {config_path}")

        data = config.to_dict()

        if config_format == "json":
            self._save_json(config_path, data)
        elif config_format == "yaml":
            self._save_yaml(config_path, data)
        else:
            raise ConfigurationError(
                code=78, msg=f"Unsupported configuration format: {config_format}"
            ).with_context(
                solutions=['Use format="json" or format="yaml"'],
                valid_formats=["json", "yaml"],
                requested_format=config_format,
            )

    def _load_json(self, path: Path) -> dict[str, Any]:
        """Load JSON file."""
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _save_json(self, path: Path, data: dict[str, Any]) -> None:
        """Save JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        """Load YAML file."""
        try:
            import yaml  # pylint: disable=import-outside-toplevel  # PyYAML is an optional dependency, kept lazy

            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f)
        except ImportError as e:
            raise ConfigurationError(
                code=69, msg=f"Cannot load YAML configuration from {path}: PyYAML library not installed"
            ).with_context(
                solutions=[
                    "Install PyYAML: pip install pyyaml",
                    "Or use JSON format instead: save_config(..., format='json')",
                ]
            ) from e

    def _save_yaml(self, path: Path, data: dict[str, Any]) -> None:
        """Save YAML file."""
        try:
            import yaml  # pylint: disable=import-outside-toplevel  # PyYAML is an optional dependency, kept lazy

            with open(path, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, default_flow_style=False)
        except ImportError as e:
            raise ConfigurationError(
                code=69, msg=f"Cannot save YAML configuration to {path}: PyYAML library not installed"
            ).with_context(
                solutions=[
                    "Install PyYAML: pip install pyyaml",
                    "Or use JSON format instead: save_config(..., format='json')",
                ]
            ) from e

    def create_default_config(self, source_path: str) -> MigrationConfig:
        """
        Create default configuration.

        Args:
            source_path: Source VM disk image path

        Returns:
            Default migration configuration
        """
        return MigrationConfig(source_path=source_path)

    def validate_config(self, config: MigrationConfig) -> list[str]:
        """
        Validate configuration.

        Args:
            config: Migration configuration

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Validate source path
        if not config.source_path:
            errors.append(
                "Source path is required. Specify the disk image to migrate "
                "(e.g., source_path: /path/to/vm.vmdk)"
            )
        elif not Path(config.source_path).exists():
            errors.append(
                f"Source disk image not found: {config.source_path}\n"
                f"    Verify the file exists and the path is correct."
            )

        # Validate formats
        valid_formats = ["qcow2", "raw", "vmdk", "vdi", "vhd", "vhdx"]
        if config.source_format not in valid_formats:
            errors.append(
                f"Unsupported source format '{config.source_format}'. "
                f"Supported formats: {', '.join(valid_formats)}"
            )
        if config.target_format not in valid_formats:
            errors.append(
                f"Unsupported target format '{config.target_format}'. "
                f"Supported formats: {', '.join(valid_formats)}"
            )

        return errors
