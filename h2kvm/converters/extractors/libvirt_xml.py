# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Libvirt domain XML parser and Artifact Manifest v1 generator."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from h2kvm.core.constants import SIZE_1_GIB, SIZE_1_KIB, SIZE_1_MIB
from h2kvm.core.utils import U

if TYPE_CHECKING:
    import logging


@dataclass
class _DomainInfo:  # pylint: disable=too-many-instance-attributes  # plain data container modeling independent domain-XML fields
    """Parsed libvirt domain metadata used to log a summary and build the manifest."""

    domain_name: str
    domain_uuid: str | None
    firmware: str
    os_type: str
    os_distro: str
    disks: list[dict[str, Any]]
    networks: list[dict[str, Any]]
    memory_bytes: int | None
    vcpus: int | None


class LibvirtXML:  # pylint: disable=too-few-public-methods  # namespace class of static parsing helpers; only one is meant to be public
    """
    Parse libvirt domain XML and generate Artifact Manifest v1.

    This extractor enables importing existing libvirt VMs into h2kvm
    by parsing their domain XML configuration and discovering disk artifacts.

    Capabilities:
    - Parse disk paths and formats from libvirt domain XML
    - Extract network configuration (interfaces, bridges, MAC addresses)
    - Detect firmware type (BIOS/UEFI)
    - Extract memory/CPU settings
    - Extract OS metadata (type, distro hints)
    - Generate complete Artifact Manifest v1 for conversion

    Security:
    - Uses defusedxml if available to mitigate XML entity expansion
    - Validates disk paths exist before including in manifest
    - Safe path handling for disk artifacts
    """

    @staticmethod
    def parse_domain_xml(
        logger: logging.Logger | None,
        xml_path: Path,
        output_dir: Path | None = None,
        *,
        compute_checksums: bool = True,
        manifest_filename: str = "manifest.json",
    ) -> dict[str, Any]:
        """
        Parse libvirt domain XML and generate Artifact Manifest v1.

        Args:
            logger: Logger instance
            xml_path: Path to libvirt domain XML file
            output_dir: Output directory for manifest (defaults to xml_path.parent)
            compute_checksums: Whether to compute SHA256 checksums for disks
            manifest_filename: Manifest filename (default: "manifest.json")

        Returns:
            dict: Artifact Manifest v1 dictionary

        Raises:
            FileNotFoundError: If XML file doesn't exist
            ET.ParseError: If XML is invalid
        """
        U.banner(logger, "Parse Libvirt Domain XML")

        xml_path = Path(xml_path).resolve()
        if not xml_path.exists():
            U.die(logger, f"Domain XML not found: {xml_path}", 1)

        if not xml_path.is_file():
            U.die(logger, f"Domain XML is not a file: {xml_path}", 1)

        if logger:
            logger.info("Domain XML: %s", xml_path)

        root = LibvirtXML._parse_xml_tree(logger, xml_path)
        info = LibvirtXML._collect_domain_info(logger, root, compute_checksums)

        LibvirtXML._log_summary(logger, info)

        # Build and write Artifact Manifest v1
        manifest = LibvirtXML._build_manifest(info, xml_path, output_dir)
        LibvirtXML._write_manifest(logger, manifest, (output_dir or xml_path.parent) / manifest_filename)

        return manifest

    @staticmethod
    def _collect_domain_info(
        logger: logging.Logger | None,
        root: ET.Element,
        compute_checksums: bool,
    ) -> _DomainInfo:
        """Extract domain metadata, disks, and networks from a parsed domain XML root."""
        os_type, os_distro = LibvirtXML._extract_os_metadata(root)

        disks = LibvirtXML._extract_disks(logger, root, compute_checksums)
        if not disks:
            U.die(logger, "No disks found in domain XML", 1)

        return _DomainInfo(
            domain_name=LibvirtXML._get_text(root, "name", "unknown"),
            domain_uuid=LibvirtXML._get_text(root, "uuid"),
            firmware=LibvirtXML._detect_firmware(root),
            os_type=os_type,
            os_distro=os_distro,
            disks=disks,
            networks=LibvirtXML._extract_networks(logger, root),
            memory_bytes=LibvirtXML._extract_memory(root),
            vcpus=LibvirtXML._extract_vcpus(root),
        )

    @staticmethod
    def _parse_xml_tree(logger: logging.Logger | None, xml_path: Path) -> ET.Element:
        """Parse the domain XML file into an ElementTree root, dying with a helpful message on failure."""
        # Prefer defusedxml if available (optional dependency, only used if installed)
        try:
            from defusedxml.ElementTree import parse as safe_parse  # pylint: disable=import-outside-toplevel
        except ImportError:
            safe_parse = None

        try:
            tree = safe_parse(xml_path) if safe_parse else ET.parse(xml_path)
        except ET.ParseError as e:
            U.die(
                logger,
                f"Failed to parse domain XML '{xml_path}': {e}\n"
                "    The file contains invalid XML. Verify with: xmllint --noout <file>\n"
                "    Generate a fresh copy with: virsh dumpxml <vm-name> > domain.xml",
                1,
            )
        except PermissionError as e:
            U.die(
                logger,
                f"Permission denied reading domain XML '{xml_path}': {e}\n"
                "    Try: sudo cat {xml_path} | head -5  (to verify access)",
                1,
            )
        # defusedxml/ElementTree can raise a variety of errors on malformed/unreadable input;
        # must report cleanly via U.die rather than crash.
        except Exception as e:  # pylint: disable=broad-exception-caught
            U.die(
                logger,
                f"Failed to read domain XML '{xml_path}': {e}\n    Verify the file exists and is readable.",
                1,
            )

        return tree.getroot()

    @staticmethod
    def _log_summary(logger: logging.Logger | None, info: _DomainInfo) -> None:
        """Log a human-readable summary of the parsed domain."""
        if not logger:
            return

        logger.info("Domain: %s", info.domain_name)
        if info.domain_uuid:
            logger.info("UUID:   %s", info.domain_uuid)
        logger.info("Firmware: %s", info.firmware)
        logger.info("OS Type: %s", info.os_type)

        logger.info("Disks: %s found", len(info.disks))
        for disk in info.disks:
            logger.info("  - %s: %s (%s)", disk["id"], disk["local_path"], disk["source_format"])

        if info.networks:
            logger.info("Networks: %s interface(s)", len(info.networks))
            for net in info.networks:
                logger.info("  - %s: %s", net.get("type", "unknown"), net.get("source", "unknown"))

        if info.memory_bytes:
            logger.info("Memory: %s", U.human_bytes(info.memory_bytes))
        if info.vcpus:
            logger.info("vCPUs: %s", info.vcpus)

    @staticmethod
    def _build_manifest(info: _DomainInfo, xml_path: Path, output_dir: Path | None) -> dict[str, Any]:
        """Assemble the Artifact Manifest v1 dictionary from extracted domain data."""
        manifest: dict[str, Any] = {
            "manifest_version": "1.0",
            "source": {
                "provider": "libvirt",
                "vm_id": info.domain_uuid or info.domain_name,
                "vm_name": info.domain_name,
                "hypervisor_version": "unknown",
                "export_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "libvirt_xml_path": str(xml_path),
            },
            "disks": info.disks,
            "firmware": {"type": info.firmware},
            "os_hint": info.os_distro if info.os_distro != "unknown" else info.os_type,
        }

        # Add network metadata if present
        if info.networks:
            manifest["metadata"] = {
                "networks": info.networks,
                "memory_bytes": info.memory_bytes,
                "vcpus": info.vcpus,
            }

        # Add pipeline configuration with sensible defaults
        manifest["pipeline"] = {
            "inspect": {"enabled": True, "collect_guest_info": False},
            "fix": {
                "enabled": True,
                "backup": True,
                "update_grub": True,
                "regen_initramfs": True,
                "fstab_mode": "stabilize-all",
            },
            "convert": {"enabled": True, "compress": True, "compress_level": 6},
            "validate": {"enabled": True, "check_image_integrity": True},
        }

        # Default output configuration
        if output_dir:
            manifest["output"] = {
                "directory": str(output_dir),
                "format": "qcow2",
            }
        else:
            manifest["output"] = {"format": "qcow2"}

        return manifest

    @staticmethod
    def _get_text(root: ET.Element, tag: str, default: str | None = None) -> str | None:
        """Get text content of a direct child element."""
        elem = root.find(tag)
        if elem is not None and elem.text:
            return elem.text.strip()
        return default

    @staticmethod
    def _detect_firmware(root: ET.Element) -> str:
        """
        Detect firmware type (BIOS or UEFI) from domain XML.

        Looks for:
        - <os><loader type="pflash"> indicates UEFI
        - <os firmware="efi"> indicates UEFI
        - Otherwise assume BIOS
        """
        os_elem = root.find("os")
        if os_elem is None:
            return "bios"

        # Check for loader element (UEFI)
        loader = os_elem.find("loader")
        if loader is not None:
            loader_type = loader.get("type", "")
            if "pflash" in loader_type.lower():
                return "uefi"

        # Check firmware attribute
        firmware_attr = os_elem.get("firmware", "")
        if firmware_attr and "efi" in firmware_attr.lower():
            return "uefi"

        # Check if loader path contains "OVMF" (common UEFI firmware)
        if loader is not None and loader.text and ("OVMF" in loader.text or "ovmf" in loader.text):
            return "uefi"

        return "bios"

    @staticmethod
    def _extract_os_metadata(root: ET.Element) -> tuple[str, str]:
        """
        Extract OS type and distro hints from domain XML.

        Returns:
            (os_type, os_distro): e.g., ("linux", "rhel9")
        """
        os_elem = root.find("os")
        if os_elem is None:
            return ("unknown", "unknown")

        # Get OS type
        type_elem = os_elem.find("type")
        os_type = "unknown"
        if type_elem is not None and type_elem.text:
            os_type = type_elem.text.strip().lower()
            if os_type == "hvm":
                os_type = "linux"  # Default assumption

        # Try to extract distro from metadata (if present)
        metadata_elem = root.find("metadata")
        os_distro = "unknown"

        if metadata_elem is not None:
            # Check for libosinfo metadata
            for ns_uri in [
                "http://libosinfo.org/xmlns/libvirt/domain/1.0",
                "libosinfo",
            ]:
                ns = {"libosinfo": ns_uri} if ns_uri.startswith("http") else {}

                libosinfo = metadata_elem.find("libosinfo:libosinfo", ns) if ns else None
                if libosinfo is None:
                    libosinfo = metadata_elem.find("libosinfo")
                if libosinfo is None:
                    continue

                os_elem_info = libosinfo.find(f"{{{ns_uri}}}os") if ns else libosinfo.find("os")
                if os_elem_info is None:
                    continue

                os_id = os_elem_info.get("id", "")
                if not os_id:
                    continue

                # Extract distro from OS ID (e.g., "http://redhat.com/rhel/9.0")
                os_distro = LibvirtXML._distro_from_os_id(os_id)
                break

        return (os_type, os_distro)

    @staticmethod
    def _distro_from_os_id(os_id: str) -> str:
        """Map a libosinfo OS id (e.g. "http://redhat.com/rhel/9.0") to a distro hint."""
        os_id_lower = os_id.lower()
        if "rhel" in os_id_lower:
            return "rhel9" if "9" in os_id else "rhel"
        if "ubuntu" in os_id_lower:
            return "ubuntu22" if "22" in os_id else "ubuntu"
        if "debian" in os_id_lower:
            return "debian"
        if "centos" in os_id_lower:
            return "centos"
        if "fedora" in os_id_lower:
            return "fedora"
        return "unknown"

    @staticmethod
    def _extract_disks(
        logger: logging.Logger | None,
        root: ET.Element,
        compute_checksums: bool,
    ) -> list[dict[str, Any]]:
        """
        Extract disk artifacts from domain XML.

        Parses <devices><disk> elements to find disk paths, formats, and types.
        """
        devices = root.find("devices")
        if devices is None:
            return []

        disks: list[dict[str, Any]] = []

        for disk_elem in devices.findall("disk"):
            entry = LibvirtXML._build_disk_entry(logger, disk_elem, len(disks), compute_checksums)
            if entry is not None:
                disks.append(entry)

        return disks

    @staticmethod
    def _resolve_disk_source(logger: logging.Logger | None, disk_elem: ET.Element) -> Path | None:
        """Resolve and validate the on-disk path for a <disk> element, or None if it should be skipped."""
        device_type = disk_elem.get("device", "disk")
        # Skip CD-ROMs and floppies
        if device_type in ("cdrom", "floppy"):
            return None

        source = disk_elem.find("source")
        if source is None:
            return None

        disk_type = disk_elem.get("type", "file")
        source_path = None
        if disk_type == "file":
            source_path = source.get("file")
        elif disk_type == "block":
            source_path = source.get("dev")

        if not source_path:
            return None

        disk_path = Path(source_path).resolve()

        # Skip if disk doesn't exist
        if not disk_path.exists():
            if logger:
                logger.warning(f"Disk not found (skipping): {disk_path}")
            return None

        if not disk_path.is_file():
            if logger:
                logger.warning(f"Disk is not a file (skipping): {disk_path}")
            return None

        return disk_path

    @staticmethod
    def _build_disk_entry(
        logger: logging.Logger | None,
        disk_elem: ET.Element,
        existing_count: int,
        compute_checksums: bool,
    ) -> dict[str, Any] | None:
        """Build a single disk manifest entry from a <disk> element, or None if it should be skipped."""
        disk_path = LibvirtXML._resolve_disk_source(logger, disk_elem)
        if disk_path is None:
            return None

        # Get disk format
        driver = disk_elem.find("driver")
        source_format = driver.get("type", "raw") if driver is not None else "raw"

        # Get target device name (e.g., vda, sda)
        target = disk_elem.find("target")
        target_dev = target.get("dev", "disk") if target is not None else "disk"

        # Determine disk type (boot vs data)
        # First disk is typically boot, others are data
        disk_id = target_dev if target_dev != "disk" else f"disk{existing_count}"
        is_boot = existing_count == 0

        disk_bytes = disk_path.stat().st_size

        # Compute checksum if requested
        checksum = None
        if compute_checksums:
            if logger:
                logger.info(f"Computing SHA256 for {disk_id}...")
            checksum = LibvirtXML._compute_sha256(disk_path)

        return {
            "id": disk_id,
            "source_format": source_format,
            "local_path": str(disk_path),
            "bytes": disk_bytes,
            "checksum": checksum,
            "boot_order_hint": existing_count if is_boot else existing_count + existing_count,
            "disk_type": "boot" if is_boot else "data",
        }

    @staticmethod
    def _extract_networks(
        logger: logging.Logger | None,
        root: ET.Element,
    ) -> list[dict[str, Any]]:
        """
        Extract network interface configuration from domain XML.

        Returns list of network interface metadata for reference.
        """
        devices = root.find("devices")
        if devices is None:
            return []

        networks: list[dict[str, Any]] = []

        for iface in devices.findall("interface"):
            iface_type = iface.get("type", "unknown")

            net_info: dict[str, Any] = {"type": iface_type}

            # Get source (network, bridge, VDS distributed switch, etc.)
            source = iface.find("source")
            if source is not None:
                if iface_type == "network":
                    net_info["source"] = source.get("network", "unknown")
                elif iface_type == "bridge":
                    net_info["source"] = source.get("bridge", "unknown")
                elif iface_type == "vds":
                    # VMware vSphere Distributed Switch — use portgroupid as
                    # the network name so --network / --mac mappings work.
                    net_info["source"] = source.get(
                        "portgroupid",
                        source.get("portid", "unknown"),
                    )
                    net_info["switchid"] = source.get("switchid")
                    net_info["portid"] = source.get("portid")
                    net_info["portgroupid"] = source.get("portgroupid")
                    net_info["connectionid"] = source.get("connectionid")
                    if logger:
                        logger.info(
                            "VDS interface detected: portgroup=%s switchid=%s",
                            net_info.get("portgroupid"),
                            net_info.get("switchid"),
                        )
                else:
                    net_info["source"] = source.get("dev", "unknown")

            # Get MAC address
            mac = iface.find("mac")
            if mac is not None:
                net_info["mac"] = mac.get("address")

            # Get model
            model = iface.find("model")
            if model is not None:
                net_info["model"] = model.get("type", "virtio")

            networks.append(net_info)

        return networks

    @staticmethod
    def _extract_memory(root: ET.Element) -> int | None:
        """Extract memory size in bytes from domain XML."""
        memory_elem = root.find("memory")
        if memory_elem is None or not memory_elem.text:
            return None

        unit_multipliers = {
            "b": 1,
            "KiB": SIZE_1_KIB,
            "KB": SIZE_1_KIB,
            "MiB": SIZE_1_MIB,
            "MB": SIZE_1_MIB,
            "GiB": SIZE_1_GIB,
            "GB": SIZE_1_GIB,
        }

        try:
            # Memory is in KiB by default
            unit = memory_elem.get("unit", "KiB")
            value = int(memory_elem.text.strip())
            # Convert to bytes (unknown units default to KiB)
            return value * unit_multipliers.get(unit, SIZE_1_KIB)
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _extract_vcpus(root: ET.Element) -> int | None:
        """Extract vCPU count from domain XML."""
        vcpu_elem = root.find("vcpu")
        if vcpu_elem is None or not vcpu_elem.text:
            return None

        try:
            return int(vcpu_elem.text.strip())
        except ValueError:
            return None

    @staticmethod
    def _compute_sha256(file_path: Path) -> str:
        """Compute SHA256 checksum of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(8192 * 1024):  # 8MB chunks
                sha256.update(chunk)
        return f"sha256:{sha256.hexdigest()}"

    @staticmethod
    def _write_manifest(
        logger: logging.Logger | None,
        manifest: dict[str, Any],
        output_path: Path,
    ) -> None:
        """Write Artifact Manifest v1 to JSON file."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write atomically (temp + replace)
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(output_path.parent),
            prefix=f".{output_path.name}.",
            suffix=".tmp",
        )

        try:
            with open(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, sort_keys=False)
                f.write("\n")

            os.replace(tmp_path, str(output_path))

            if logger:
                logger.info(f"✅ Manifest written: {output_path}")

        except Exception:
            # Clean up temp file on error
            with contextlib.suppress(Exception):
                Path(tmp_path).unlink()
            raise
