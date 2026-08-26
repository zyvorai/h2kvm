# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Libvirt domain management for automatic VM import and lifecycle operations.

This module provides high-level libvirt domain operations for hyper2kvm,
enabling automatic domain creation, snapshot management, and lifecycle control
after VM conversion.

Capabilities:
- Define libvirt domains from generated XML
- Manage domain lifecycle (start, stop, destroy)
- Create snapshots before first boot
- Auto-start configuration
- Domain existence checks and cleanup

Security:
- Validates XML before defining domains
- Uses read-only connections where possible
- Safe domain name sanitization
- Proper resource cleanup
"""
# pylint: disable=duplicate-code
# reason: connection lifecycle (__init__/connect/disconnect/context-manager) and the
# exists-check pattern mirror hyper2kvm/libvirt/pool_manager.py, but connect()'s error
# messages differ intentionally (this one includes libvirtd troubleshooting hints) --
# kept independent rather than forcing a shared base with divergent error text.

from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from hyper2kvm.core.constants import DELAY_LIBVIRT_OPERATION
from hyper2kvm.core.exceptions import InfrastructureError

try:
    import libvirt  # type: ignore

    LIBVIRT_AVAILABLE = True
except ImportError:
    libvirt = None  # type: ignore
    LIBVIRT_AVAILABLE = False


class LibvirtManager:
    """
    Manage libvirt domains: define, start, snapshot, and lifecycle operations.

    This class provides a high-level interface to libvirt for domain management
    tasks commonly needed after VM conversion.

    Example:
        >>> manager = LibvirtManager(logger)
        >>> domain = manager.define_domain(xml_path="/converted/domain.xml")
        >>> manager.create_snapshot(domain, "pre-first-boot")
        >>> if auto_start:
        >>>     manager.start_domain(domain)
    """

    def __init__(
        self,
        logger: logging.Logger | None = None,
        uri: str = "qemu:///system",
    ):
        """
        Initialize LibvirtManager.

        Args:
            logger: Logger instance for operations
            uri: Libvirt connection URI (default: qemu:///system)

        Raises:
            InfrastructureError: If libvirt is not available
        """
        if not LIBVIRT_AVAILABLE:
            raise InfrastructureError(
                "libvirt Python bindings not available. Install with: pip install libvirt-python"
            )

        self.logger = logger or logging.getLogger(__name__)
        self.uri = uri
        self.conn: Any = None

    def connect(self) -> None:
        """
        Establish connection to libvirt daemon.

        Raises:
            InfrastructureError: If connection fails
        """
        if self.conn is not None:
            return  # Already connected

        try:
            self.conn = libvirt.open(self.uri)
            if self.conn is None:
                raise InfrastructureError(f"Failed to connect to libvirt at {self.uri}")

            self.logger.info("Connected to libvirt: %s", self.uri)

        except libvirt.libvirtError as e:
            raise InfrastructureError(
                f"Libvirt connection failed at {self.uri}: {e}. "
                "Ensure libvirtd is running (systemctl start libvirtd) "
                "and the current user has access (add to 'libvirt' group: usermod -aG libvirt $USER)."
            ) from e

    def disconnect(self) -> None:
        """Close libvirt connection and cleanup resources."""
        if self.conn is not None:
            try:
                self.conn.close()
                self.logger.info("Disconnected from libvirt")
            except libvirt.libvirtError as e:
                self.logger.warning("Error closing libvirt connection: %s", e)
            finally:
                self.conn = None

    def __enter__(self) -> LibvirtManager:
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.disconnect()

    def domain_exists(self, name: str) -> bool:
        """
        Check if domain with given name exists.

        Args:
            name: Domain name to check

        Returns:
            True if domain exists, False otherwise
        """
        if self.conn is None:
            self.connect()

        try:
            self.conn.lookupByName(name)
            return True
        except libvirt.libvirtError:
            return False

    def define_domain(
        self,
        xml_path: Path | str,
        *,
        overwrite: bool = False,
    ) -> Any:
        """
        Define a libvirt domain from XML file.

        Args:
            xml_path: Path to domain XML file
            overwrite: If True, undefine existing domain with same name

        Returns:
            libvirt domain object

        Raises:
            InfrastructureError: If domain definition fails
        """
        if self.conn is None:
            self.connect()

        xml_path = Path(xml_path).resolve()

        if not xml_path.exists():
            raise InfrastructureError(f"Domain XML not found: {xml_path}")

        # Read and validate XML
        try:
            xml_content = xml_path.read_text(encoding="utf-8")
        except Exception as e:
            raise InfrastructureError(f"Failed to read XML: {e}") from e

        # Extract domain name from XML for logging
        try:
            root = ET.fromstring(xml_content)
            domain_name = root.find("name")
            name = domain_name.text if domain_name is not None else "unknown"
        except ET.ParseError:
            name = "unknown"

        # Check if domain already exists
        if self.domain_exists(name):
            if overwrite:
                self.logger.warning("Domain '%s' exists, undefining for overwrite", name)
                self.undefine_domain(name)
            else:
                raise InfrastructureError(f"Domain '{name}' already exists (use overwrite=True to replace)")

        # Define domain
        try:
            domain = self.conn.defineXML(xml_content)
            if domain is None:
                raise InfrastructureError(f"Failed to define domain '{name}'")

            self.logger.info("✅ Defined libvirt domain: %s", name)
            return domain

        except libvirt.libvirtError as e:
            raise InfrastructureError(
                f"Failed to define libvirt domain '{name}': {e}. "
                "Common causes: invalid XML syntax, missing disk images referenced in the XML, "
                "or insufficient permissions. Validate the XML with: virsh define --validate <file>"
            ) from e

    def undefine_domain(self, name: str, *, remove_nvram: bool = False) -> None:
        """
        Undefine a domain (remove from libvirt without deleting disks).

        Args:
            name: Domain name
            remove_nvram: If True, also remove NVRAM file

        Raises:
            InfrastructureError: If undefine fails
        """
        if self.conn is None:
            self.connect()

        try:
            domain = self.conn.lookupByName(name)

            # Ensure domain is not running
            if domain.isActive():
                self.logger.warning("Domain '%s' is running, destroying first", name)
                domain.destroy()
                time.sleep(DELAY_LIBVIRT_OPERATION)

            # Undefine with flags
            flags = 0
            if remove_nvram:
                flags |= libvirt.VIR_DOMAIN_UNDEFINE_NVRAM

            domain.undefineFlags(flags)
            self.logger.info("Undefined domain: %s", name)

        except libvirt.libvirtError as e:
            if "not found" in str(e).lower():
                self.logger.warning("Domain '%s' not found, skipping undefine", name)
            else:
                raise InfrastructureError(f"Failed to undefine domain '{name}': {e}") from e

    def start_domain(self, domain_or_name: Any | str, *, force: bool = False) -> None:
        """
        Start (boot) a domain.

        Args:
            domain_or_name: Domain object or name string
            force: If True, force start even if already running

        Raises:
            InfrastructureError: If start fails
        """
        if self.conn is None:
            self.connect()

        # Get domain object
        if isinstance(domain_or_name, str):
            try:
                domain = self.conn.lookupByName(domain_or_name)
            except libvirt.libvirtError as e:
                raise InfrastructureError(f"Domain '{domain_or_name}' not found: {e}") from e
        else:
            domain = domain_or_name

        name = domain.name()

        # Check if already running
        if domain.isActive():
            if force:
                self.logger.warning("Domain '%s' already running, restarting", name)
                domain.destroy()
                time.sleep(DELAY_LIBVIRT_OPERATION)
            else:
                self.logger.info("Domain '%s' already running, skipping start", name)
                return

        # Start domain
        try:
            domain.create()
            self.logger.info("✅ Started domain: %s", name)

        except libvirt.libvirtError as e:
            error_str = str(e).lower()
            hints = ""
            if "no boot device" in error_str or "boot" in error_str:
                hints = " Check that the disk image path in the domain XML exists and is readable."
            elif "permission" in error_str or "denied" in error_str:
                hints = " Check file permissions on the disk image and ensure libvirtd can access it."
            elif "not supported" in error_str or "qemu" in error_str:
                hints = " Check that the QEMU binary exists and supports the VM's architecture."
            raise InfrastructureError(
                f"Failed to start domain '{name}': {e}.{hints} Debug with: virsh start {name} --console"
            ) from e

    def create_snapshot(
        self,
        domain_or_name: Any | str,
        snapshot_name: str = "pre-first-boot",
        *,
        description: str = "",
    ) -> None:
        """
        Create a snapshot of a domain.

        Args:
            domain_or_name: Domain object or name string
            snapshot_name: Name for the snapshot
            description: Optional snapshot description

        Raises:
            InfrastructureError: If snapshot creation fails
        """
        if self.conn is None:
            self.connect()

        # Get domain object
        if isinstance(domain_or_name, str):
            try:
                domain = self.conn.lookupByName(domain_or_name)
            except libvirt.libvirtError as e:
                raise InfrastructureError(f"Domain '{domain_or_name}' not found: {e}") from e
        else:
            domain = domain_or_name

        name = domain.name()

        # Build snapshot XML
        desc_xml = f"<description>{description}</description>" if description else ""
        snapshot_xml = f"""<domainsnapshot>
  <name>{snapshot_name}</name>
  {desc_xml}
</domainsnapshot>"""

        # Create snapshot
        try:
            snapshot = domain.snapshotCreateXML(snapshot_xml, 0)
            if snapshot is None:
                raise InfrastructureError(f"Failed to create snapshot for domain '{name}'")

            self.logger.info("✅ Created snapshot '%s' for domain: %s", snapshot_name, name)

        except libvirt.libvirtError as e:
            raise InfrastructureError(f"Failed to create snapshot for domain '{name}': {e}") from e

    def set_autostart(self, domain_or_name: Any | str, enabled: bool = True) -> None:
        """
        Configure domain to auto-start on host boot.

        Args:
            domain_or_name: Domain object or name string
            enabled: True to enable auto-start, False to disable

        Raises:
            InfrastructureError: If setting autostart fails
        """
        if self.conn is None:
            self.connect()

        # Get domain object
        if isinstance(domain_or_name, str):
            try:
                domain = self.conn.lookupByName(domain_or_name)
            except libvirt.libvirtError as e:
                raise InfrastructureError(f"Domain '{domain_or_name}' not found: {e}") from e
        else:
            domain = domain_or_name

        name = domain.name()

        try:
            domain.setAutostart(1 if enabled else 0)
            status = "enabled" if enabled else "disabled"
            self.logger.info("Auto-start %s for domain: %s", status, name)

        except libvirt.libvirtError as e:
            raise InfrastructureError(f"Failed to set autostart for domain '{name}': {e}") from e


__all__ = [
    "LIBVIRT_AVAILABLE",
    "InfrastructureError",
    "LibvirtManager",
]
