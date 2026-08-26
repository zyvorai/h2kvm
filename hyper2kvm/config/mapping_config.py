# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Network and storage mapping configuration for batch migrations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class MACAddressPolicy(str, Enum):
    """MAC address handling policy for network mappings."""

    PRESERVE = "preserve"  # Keep original MAC addresses
    REGENERATE = "regenerate"  # Generate new MAC addresses
    CUSTOM = "custom"  # Use custom MAC address overrides


class DiskFormat(str, Enum):
    """Supported disk formats for storage mapping."""

    QCOW2 = "qcow2"
    RAW = "raw"
    VDI = "vdi"


@dataclass
class NetworkMapping:
    """
    Network mapping configuration for converting source networks to target bridges/networks.

    Attributes:
        source_networks: Map of source network names to target bridge/network names
        mac_address_policy: How to handle MAC addresses (preserve/regenerate/custom)
        mac_address_overrides: Custom MAC address mappings (only used when policy=custom)
        default_bridge: Default bridge to use if source network not found in mappings
    """

    source_networks: dict[str, str] = field(default_factory=dict)
    mac_address_policy: MACAddressPolicy = MACAddressPolicy.PRESERVE
    mac_address_overrides: dict[str, str] = field(default_factory=dict)
    default_bridge: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NetworkMapping:
        """Create NetworkMapping from dictionary configuration."""
        source_networks = data.get("source_networks", {})
        if not isinstance(source_networks, dict):
            raise TypeError('source_networks must be a dictionary (e.g., {"VM Network": "br0"}).')

        # Parse MAC address policy
        policy_str = data.get("mac_address_policy", "preserve")
        try:
            policy = MACAddressPolicy(policy_str.lower())
        except ValueError as err:
            raise ValueError(
                f"Invalid mac_address_policy: {policy_str}. "
                f"Must be one of: {[p.value for p in MACAddressPolicy]}"
            ) from err

        # Parse MAC address overrides
        mac_overrides = data.get("mac_address_overrides", {})
        if not isinstance(mac_overrides, dict):
            raise TypeError(
                "mac_address_overrides must be a dictionary mapping source MACs to target MACs "
                '(e.g., {"00:11:22:33:44:55": "aa:bb:cc:dd:ee:ff"}).'
            )

        # Validate MAC addresses (basic format check)
        for mac in list(mac_overrides.keys()) + list(mac_overrides.values()):
            if not cls._is_valid_mac(mac):
                raise ValueError(f"Invalid MAC address format '{mac}'. Expected format: 00:11:22:33:44:55.")

        default_bridge = data.get("default_bridge")

        return cls(
            source_networks=source_networks,
            mac_address_policy=policy,
            mac_address_overrides=mac_overrides,
            default_bridge=default_bridge,
        )

    @staticmethod
    def _is_valid_mac(mac: str) -> bool:
        """Basic MAC address format validation."""
        # Match common MAC formats: XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX
        pattern = r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$"
        return bool(re.match(pattern, mac))

    def get_target_bridge(self, source_network: str) -> str | None:
        """
        Get target bridge for a source network name.

        Args:
            source_network: Source network name

        Returns:
            Target bridge name, or default_bridge if not found, or None
        """
        return self.source_networks.get(source_network, self.default_bridge)

    def get_target_mac(self, source_mac: str) -> str | None:
        """
        Get target MAC address for a source MAC.

        Args:
            source_mac: Source MAC address

        Returns:
            Target MAC address if policy=custom and override exists, else None
        """
        if self.mac_address_policy == MACAddressPolicy.CUSTOM:
            return self.mac_address_overrides.get(source_mac)
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source_networks": self.source_networks,
            "mac_address_policy": self.mac_address_policy.value,
            "mac_address_overrides": self.mac_address_overrides,
            "default_bridge": self.default_bridge,
        }


@dataclass
class StorageMapping:
    """
    Storage mapping configuration for disk placement and format conversion.

    Attributes:
        default_pool: Default libvirt storage pool name
        disk_mappings: Map of disk IDs/roles to output directories
        format_override: Override output format for all disks
        preallocate: Whether to preallocate disk space
    """

    default_pool: str | None = None
    disk_mappings: dict[str, str] = field(default_factory=dict)
    format_override: DiskFormat | None = None
    preallocate: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StorageMapping:
        """Create StorageMapping from dictionary configuration."""
        default_pool = data.get("default_pool")

        # Parse disk mappings
        disk_mappings = data.get("disk_mappings", {})
        if not isinstance(disk_mappings, dict):
            raise TypeError('disk_mappings must be a dictionary (e.g., {"disk-0": "/path/to/disk.qcow2"}).')

        # Validate paths in disk_mappings
        for disk_id, path_str in disk_mappings.items():
            Path(path_str).expanduser().resolve()
            # Just validate it's a string, actual path creation happens later
            if not isinstance(path_str, str):
                raise TypeError(
                    f"disk_mappings['{disk_id}'] must be a string file path "
                    f"(e.g., '/var/lib/libvirt/images/disk.qcow2')."
                )

        # Parse format override
        format_override = None
        if "format_override" in data:
            fmt_str = data["format_override"]
            try:
                format_override = DiskFormat(fmt_str.lower())
            except ValueError as err:
                raise ValueError(
                    f"Invalid format_override: {fmt_str}. Must be one of: {[f.value for f in DiskFormat]}"
                ) from err

        preallocate = data.get("preallocate", False)
        if not isinstance(preallocate, bool):
            raise TypeError("preallocate must be a boolean (true or false).")

        return cls(
            default_pool=default_pool,
            disk_mappings=disk_mappings,
            format_override=format_override,
            preallocate=preallocate,
        )

    def get_disk_output_path(self, disk_id: str) -> Path | None:
        """
        Get output path for a disk ID.

        Args:
            disk_id: Disk identifier

        Returns:
            Path object if mapping exists, else None
        """
        path_str = self.disk_mappings.get(disk_id)
        if path_str:
            return Path(path_str).expanduser().resolve()
        return None

    def get_output_format(self, default: str = "qcow2") -> str:
        """
        Get output format for disks.

        Args:
            default: Default format if no override specified

        Returns:
            Output format string
        """
        if self.format_override:
            return self.format_override.value
        return default

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "default_pool": self.default_pool,
            "disk_mappings": self.disk_mappings,
            "format_override": self.format_override.value if self.format_override else None,
            "preallocate": self.preallocate,
        }


@dataclass
class MappingConfig:
    """
    Combined network and storage mapping configuration.

    This provides a unified interface for both network and storage mappings,
    typically loaded from a manifest or configuration file.
    """

    network: NetworkMapping = field(default_factory=NetworkMapping)
    storage: StorageMapping = field(default_factory=StorageMapping)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MappingConfig:
        """Create MappingConfig from dictionary configuration."""
        network_data = data.get("network_mapping", {})
        storage_data = data.get("storage_mapping", {})

        network = NetworkMapping.from_dict(network_data) if network_data else NetworkMapping()
        storage = StorageMapping.from_dict(storage_data) if storage_data else StorageMapping()

        return cls(network=network, storage=storage)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "network_mapping": self.network.to_dict(),
            "storage_mapping": self.storage.to_dict(),
        }

    def has_network_mapping(self) -> bool:
        """Check if any network mappings are defined."""
        return bool(
            self.network.source_networks or self.network.default_bridge or self.network.mac_address_overrides
        )

    def has_storage_mapping(self) -> bool:
        """Check if any storage mappings are defined."""
        return bool(self.storage.default_pool or self.storage.disk_mappings or self.storage.format_override)
