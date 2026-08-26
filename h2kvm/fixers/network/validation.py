# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/network/validation.py
"""
Network configuration fix validation.

This module validates that network configuration fixes didn't corrupt
the config files and that essential sections/keywords are preserved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from h2kvm.config.config_loader import YAML_AVAILABLE, yaml

from .model import IfcfgKV, NetworkConfigType

if TYPE_CHECKING:
    import logging


class NetworkValidation:  # pylint: disable=too-few-public-methods  # single-purpose validator; validate_fix is its only public entry point
    """
    Network configuration fix validator.

    Validates that fixes don't corrupt configuration files by checking:
    - YAML validity for netplan
    - Essential sections preserved (systemd, NetworkManager)
    - Required keywords present (ifcfg DEVICE, interfaces iface)
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize validator.

        Args:
            logger: Logger instance
        """
        self.logger = logger

    def _has_live_section(self, text: str, header: str) -> bool:
        """
        Check if INI-style config has a non-commented section header.

        Args:
            text: Configuration file content
            header: Section header to find (e.g., "[Network]")

        Returns:
            True if section exists and is not commented out
        """
        want = header.strip().lower()
        for ln in text.splitlines():
            s = ln.strip()
            if not s or s.startswith(("#", ";")):
                continue
            if s.lower() == want:
                return True
        return False

    def validate_fix(  # pylint: disable=too-many-branches  # one independent validation branch per config-file format
        self,
        original: str,
        fixed: str,
        config_type: NetworkConfigType,
    ) -> list[str]:
        """
        Validate that fix didn't corrupt configuration.

        Args:
            original: Original config content
            fixed: Fixed config content
            config_type: Configuration file type

        Returns:
            List of validation error messages (empty if valid)
        """
        errors: list[str] = []

        # Check for empty result
        if not fixed.strip():
            errors.append("Empty configuration after fix")

        # Netplan: validate YAML syntax
        if config_type == NetworkConfigType.NETPLAN and YAML_AVAILABLE:
            try:
                obj = yaml.safe_load(fixed)
                if obj is None:
                    errors.append("Netplan YAML became empty")
            # yaml.safe_load can raise various parser-specific error types;
            # any failure here means invalid YAML.
            except Exception as e:  # pylint: disable=broad-exception-caught
                errors.append(f"Invalid YAML: {e}")

        # ifcfg-rh/wicked: check DEVICE keyword
        if config_type in (NetworkConfigType.IFCFG_RH, NetworkConfigType.WICKED_IFCFG):
            try:
                ifcfg = IfcfgKV.parse(fixed)
                dev = (ifcfg.get("DEVICE") or "").strip()
                if not dev:
                    # Allow missing DEVICE when intentionally removed for VMware NIC migration.
                    # h2kvm comments out VMware-specific DEVICE= and relies on
                    # TYPE=Ethernet for NetworkManager auto-binding.
                    device_removed_by_fixer = any(
                        "DEVICE=" in ln and "removed by h2kvm" in ln
                        for ln in fixed.splitlines()
                        if ln.lstrip().startswith("#")
                    )
                    if not device_removed_by_fixer:
                        errors.append("ifcfg missing DEVICE after fix")
            # IfcfgKV.parse's failure modes aren't a fixed set;
            # any failure here means the fix is invalid.
            except Exception as e:  # pylint: disable=broad-exception-caught
                errors.append(f"ifcfg parse failed after fix: {e}")

        # systemd-networkd: check for [Network] section
        if config_type == NetworkConfigType.SYSTEMD_NETWORK and (
            self._has_live_section(fixed, "[Network]") is False
            and self._has_live_section(original, "[Network]") is True
        ):
            errors.append("Missing live [Network] section after fix")

        # systemd-netdev: check for [NetDev] section
        if config_type == NetworkConfigType.SYSTEMD_NETDEV and (
            self._has_live_section(fixed, "[NetDev]") is False
            and self._has_live_section(original, "[NetDev]") is True
        ):
            errors.append("Missing live [NetDev] section after fix")

        # NetworkManager: check for [connection] section
        if config_type == NetworkConfigType.NETWORK_MANAGER and (
            self._has_live_section(fixed, "[connection]") is False
            and self._has_live_section(original, "[connection]") is True
        ):
            errors.append("Missing live [connection] section after fix")

        # Debian interfaces: check for iface keyword
        if config_type == NetworkConfigType.INTERFACES:
            if "iface" in original and "iface" not in fixed:
                errors.append("Missing essential keyword: iface")

        return errors


__all__ = ["NetworkValidation"]
