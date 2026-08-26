# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/config/validation.py
"""
Configuration validation with optional pydantic support.

Falls back to manual validation if pydantic is not available (RHEL 10 compatibility).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from h2kvm.core.exceptions import ConfigurationError
from h2kvm.core.optional_imports import PYDANTIC_AVAILABLE

if TYPE_CHECKING:
    import builtins

# Import pydantic if available
if PYDANTIC_AVAILABLE:
    from h2kvm.core.optional_imports import BaseModel, ConfigDict, Field, field_validator


# Validation errors (unified interface)
class ConfigValidationError(ConfigurationError):
    """Configuration validation error (works with or without pydantic)."""

    def __init__(self, errors: list[dict[str, Any]]):
        self.errors = errors
        messages = [f"{e['field']}: {e['message']}" for e in errors]
        # Call ConfigurationError with formatted message
        super().__init__(msg="\n".join(messages), code=10, context={"validation_errors": errors})


# Base configuration classes
if PYDANTIC_AVAILABLE:
    # Use pydantic for validation
    class NetworkConfigBase(BaseModel):  # type: ignore
        """Network configuration with pydantic validation."""

        model_config = ConfigDict(extra="forbid")  # type: ignore

        interface_name: str = Field(..., pattern=r"^[a-zA-Z][a-zA-Z0-9._-]*$")  # type: ignore
        mac_address: str | None = Field(None, pattern=r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")  # type: ignore
        ip_address: str | None = Field(None, pattern=r"^\d{1,3}(\.\d{1,3}){3}$")  # type: ignore
        gateway: str | None = None
        dns_servers: list[str] = Field(default_factory=list)  # type: ignore

        @field_validator("dns_servers")  # type: ignore
        @classmethod
        def validate_dns(cls, v):
            """Reject more than 3 DNS servers."""
            if len(v) > 3:
                raise ValueError(
                    "Maximum 3 DNS servers allowed. Remove extra entries from the dns_servers list."
                )
            return v

        @field_validator("ip_address", "gateway")  # type: ignore
        @classmethod
        def validate_ip(cls, v):
            """Validate an IPv4-formatted address string."""
            if v is None:
                return v
            parts = v.split(".")
            if len(parts) != 4:
                raise ValueError(f"Invalid IP address '{v}'. Expected format: A.B.C.D (e.g., 192.168.1.1).")
            for part in parts:
                try:
                    if not 0 <= int(part) <= 255:
                        raise ValueError(
                            f"Invalid IP address '{v}'. Expected format: A.B.C.D (e.g., 192.168.1.1)."
                        )
                except ValueError as err:
                    raise ValueError(
                        f"Invalid IP address '{v}'. Expected format: A.B.C.D (e.g., 192.168.1.1)."
                    ) from err
            return v

else:
    # Fallback to manual validation (stdlib only)
    class NetworkConfigBase:  # pylint: disable=too-few-public-methods
        """Network configuration with manual validation (no pydantic).

        Mirrors the pydantic model's public surface (dict() + attribute
        access); not meant to grow more public methods.
        """

        def __init__(
            self,
            interface_name: str,
            mac_address: str | None = None,
            ip_address: str | None = None,
            gateway: str | None = None,
            dns_servers: list[str] | None = None,
        ):
            self.interface_name = interface_name
            self.mac_address = mac_address
            self.ip_address = ip_address
            self.gateway = gateway
            self.dns_servers = dns_servers or []

            # Validate
            errors = self._validate()
            if errors:
                raise ConfigValidationError(errors)

        def _validate(self) -> list[builtins.dict[str, Any]]:
            """Manual validation."""
            errors = []

            # Validate interface name
            if not re.match(r"^[a-zA-Z][a-zA-Z0-9._-]*$", self.interface_name):
                errors.append(
                    {
                        "field": "interface_name",
                        "message": (
                            "Interface name must start with a letter and contain only "
                            "letters, numbers, dots, hyphens, and underscores"
                        ),
                    }
                )

            # Validate MAC address
            if self.mac_address and not re.match(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", self.mac_address):
                errors.append(
                    {
                        "field": "mac_address",
                        "message": (
                            f"Invalid MAC address format '{self.mac_address}'. "
                            "Expected format: 00:11:22:33:44:55"
                        ),
                    }
                )

            # Validate IP addresses
            for field in ["ip_address", "gateway"]:
                value = getattr(self, field)
                if value and not self._is_valid_ip(value):
                    errors.append(
                        {
                            "field": field,
                            "message": f"Invalid IP address '{value}'. Expected format: A.B.C.D (e.g., 192.168.1.1)",
                        }
                    )

            # Validate DNS servers
            if len(self.dns_servers) > 3:
                errors.append(
                    {
                        "field": "dns_servers",
                        "message": "Maximum 3 DNS servers allowed. Remove extra entries from the dns_servers list.",
                    }
                )

            return errors

        @staticmethod
        def _is_valid_ip(ip: str) -> bool:
            """Validate IP address."""
            parts = ip.split(".")
            if len(parts) != 4:
                return False
            try:
                return all(0 <= int(part) <= 255 for part in parts)
            except ValueError:
                return False

        def dict(self) -> builtins.dict[str, Any]:
            """Convert to dict (pydantic-compatible interface)."""
            return {
                "interface_name": self.interface_name,
                "mac_address": self.mac_address,
                "ip_address": self.ip_address,
                "gateway": self.gateway,
                "dns_servers": self.dns_servers,
            }


# Public API (unified interface)
class NetworkConfig(NetworkConfigBase):
    """Network configuration (uses pydantic if available, otherwise manual validation)."""


# VMware source configuration
if PYDANTIC_AVAILABLE:

    class VMwareSourceConfigBase(BaseModel):  # type: ignore
        """VMware source configuration with pydantic."""

        model_config = ConfigDict(extra="forbid")  # type: ignore

        host: str
        username: str
        password: str = Field(..., repr=False)  # type: ignore
        vm_name: str | None = None
        vm_uuid: str | None = None
        datacenter: str | None = None
        datastore: str | None = None
        port: int = Field(default=443, ge=1, le=65535)  # type: ignore
        verify_ssl: bool = True

        @field_validator("vm_name")  # type: ignore
        @classmethod
        def require_identifier(cls, v, info):
            """Require that either vm_name or vm_uuid is set."""
            # Check if at least one identifier is provided
            if v is None:
                # Access the data being validated
                data = info.data if hasattr(info, "data") else {}
                vm_uuid = data.get("vm_uuid")
                if vm_uuid is None:
                    raise ValueError("Either vm_name or vm_uuid must be provided")
            return v

else:

    class VMwareSourceConfigBase:  # pylint: disable=too-many-instance-attributes,too-few-public-methods
        # Mirrors the pydantic model's fields 1:1 (host/username/password/vm identity/
        # datacenter/datastore/port/verify_ssl) and its public surface (dict()); not
        # meant to grow more public methods or shed fields.
        """VMware source configuration with manual validation."""

        def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            self,
            host: str,
            username: str,
            password: str,
            vm_name: str | None = None,
            vm_uuid: str | None = None,
            datacenter: str | None = None,
            datastore: str | None = None,
            port: int = 443,
            verify_ssl: bool = True,
        ):
            self.host = host
            self.username = username
            self.password = password
            self.vm_name = vm_name
            self.vm_uuid = vm_uuid
            self.datacenter = datacenter
            self.datastore = datastore
            self.port = port
            self.verify_ssl = verify_ssl

            errors = self._validate()
            if errors:
                raise ConfigValidationError(errors)

        def _validate(self) -> list[builtins.dict[str, Any]]:
            errors = []

            # Require at least one identifier
            if not self.vm_name and not self.vm_uuid:
                errors.append(
                    {"field": "vm_name/vm_uuid", "message": "Either vm_name or vm_uuid must be provided"}
                )

            # Validate port range
            if not 1 <= self.port <= 65535:
                errors.append(
                    {"field": "port", "message": f"Port must be between 1 and 65535, got {self.port}"}
                )

            return errors

        def dict(self) -> builtins.dict[str, Any]:
            """Convert to dict (pydantic-compatible interface)."""
            return {
                "host": self.host,
                "username": self.username,
                "password": self.password,
                "vm_name": self.vm_name,
                "vm_uuid": self.vm_uuid,
                "datacenter": self.datacenter,
                "datastore": self.datastore,
                "port": self.port,
                "verify_ssl": self.verify_ssl,
            }


class VMwareSourceConfig(VMwareSourceConfigBase):
    """VMware source configuration (auto-selects implementation)."""


# Disk configuration
if PYDANTIC_AVAILABLE:

    class DiskConfigBase(BaseModel):  # type: ignore
        """Disk configuration with pydantic validation."""

        model_config = ConfigDict(extra="forbid")  # type: ignore

        source_path: Path
        output_format: str = Field(default="qcow2", pattern=r"^(qcow2|raw|vmdk|vhd)$")  # type: ignore
        compression: bool = True
        size_gb: int | None = Field(None, ge=1, le=16384)  # type: ignore

        @field_validator("source_path")  # type: ignore
        @classmethod
        def disk_exists(cls, v):
            """Validate that the source path exists and is a regular file."""
            if not v.exists():
                raise ValueError(f"Disk image not found at '{v}'. Verify the path exists.")
            if not v.is_file():
                raise ValueError(f"'{v}' is not a regular file. Provide a path to a disk image file.")
            return v

else:

    class DiskConfigBase:  # pylint: disable=too-few-public-methods
        # Mirrors the pydantic model's public surface (dict() + attribute access);
        # not meant to grow more public methods.
        """Disk configuration with manual validation."""

        def __init__(
            self,
            source_path: str | Path,
            output_format: str = "qcow2",
            compression: bool = True,
            size_gb: int | None = None,
        ):
            self.source_path = Path(source_path) if isinstance(source_path, str) else source_path
            self.output_format = output_format
            self.compression = compression
            self.size_gb = size_gb

            errors = self._validate()
            if errors:
                raise ConfigValidationError(errors)

        def _validate(self) -> list[builtins.dict[str, Any]]:
            errors = []

            # Validate source path
            if not self.source_path.exists():
                errors.append(
                    {
                        "field": "source_path",
                        "message": f"Disk image not found at '{self.source_path}'. Verify the path exists.",
                    }
                )
            elif not self.source_path.is_file():
                errors.append(
                    {
                        "field": "source_path",
                        "message": f"'{self.source_path}' is not a regular file. Provide a path to a disk image file.",
                    }
                )

            # Validate output format
            if self.output_format not in ("qcow2", "raw", "vmdk", "vhd"):
                errors.append(
                    {
                        "field": "output_format",
                        "message": (
                            f"Unsupported output format '{self.output_format}'. "
                            "Must be one of: qcow2, raw, vmdk, vhd"
                        ),
                    }
                )

            # Validate size
            if self.size_gb is not None and not 1 <= self.size_gb <= 16384:
                errors.append(
                    {
                        "field": "size_gb",
                        "message": f"Size must be between 1 and 16384 GB, got {self.size_gb}",
                    }
                )

            return errors

        def dict(self) -> builtins.dict[str, Any]:
            """Convert to dict (pydantic-compatible interface)."""
            return {
                "source_path": str(self.source_path),
                "output_format": self.output_format,
                "compression": self.compression,
                "size_gb": self.size_gb,
            }


class DiskConfig(DiskConfigBase):
    """Disk configuration (auto-selects implementation)."""


# Configuration loader utilities
def load_yaml_config(yaml_path: Path) -> dict[str, Any]:
    """
    Load and validate YAML configuration.

    Uses pydantic if available, otherwise manual validation.
    """
    yaml_path = Path(yaml_path)
    if not yaml_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {yaml_path}\n"
            "Verify the path is correct. Example: --config /path/to/migration.yaml"
        )

    try:
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigurationError(
            msg=(
                f"Invalid YAML syntax in '{yaml_path}': {e}\n"
                "Check for indentation errors, missing colons, or unquoted special characters."
            ),
        ) from e
    except PermissionError as e:
        raise ConfigurationError(
            msg=f"Permission denied reading config file '{yaml_path}': {e}",
        ) from e
    except OSError as e:
        raise ConfigurationError(
            msg=f"Cannot read config file '{yaml_path}': {e}",
        ) from e

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigurationError(
            msg=(
                f"Config file '{yaml_path}' must contain a YAML mapping (key: value), "
                f"not a {type(data).__name__}."
            ),
        )
    return data


def validate_config(config_dict: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Validate configuration dictionary.

    Returns list of validation errors (empty if valid).
    """
    errors = []

    # Basic validation
    if "hypervisor" not in config_dict:
        errors.append(
            {
                "field": "hypervisor",
                "message": "The 'hypervisor' field is required. Set to 'vmware', 'hyperv', or 'azure'.",
            }
        )

    hypervisor = config_dict.get("hypervisor")

    # Hypervisor-specific validation
    if hypervisor == "vmware":
        if "vmware" not in config_dict:
            errors.append(
                {
                    "field": "vmware",
                    "message": (
                        "A 'vmware' configuration section is required when hypervisor=vmware. "
                        "Include host, username, password, and vm_name or vm_uuid."
                    ),
                }
            )
        else:
            try:
                VMwareSourceConfig(**config_dict["vmware"])
            except ConfigValidationError as e:
                errors.extend(e.errors)
            except Exception as e:  # pylint: disable=broad-exception-caught
                # VMwareSourceConfig() may raise pydantic's ValidationError (when
                # pydantic is available) or arbitrary TypeError/ValueError from the
                # manual-validation fallback's __init__ (e.g. missing required kwargs);
                # both must be reported as a validation error rather than propagate.
                errors.append({"field": "vmware", "message": str(e)})

    return errors
