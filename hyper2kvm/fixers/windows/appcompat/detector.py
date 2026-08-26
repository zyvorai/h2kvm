# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Hardware-dependent application and license service detection.

Scans Windows registry and filesystem for applications and services that may
require special attention after VM migration.
"""

import logging
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from hyper2kvm.fixers.windows.registry.encoding import _close_best_effort, _detect_current_controlset
from hyper2kvm.fixers.windows.registry.io import detect_windows_hive, download_and_open_hive

# pylint: disable=duplicate-code  # shared optional-dependency import boilerplate, also present in registry/firstboot.py
try:
    import guestfs  # type: ignore
except ImportError:
    guestfs = None  # type: ignore

try:
    import hivex  # type: ignore
except ImportError:
    hivex = None  # type: ignore
# pylint: enable=duplicate-code

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Migration risk level assessment."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class AppCompatFinding:
    """Application compatibility finding."""

    finding_type: str  # "app", "license_service", "dongle_driver"
    name: str
    vendor: Optional[str] = None
    version: Optional[str] = None
    risk_level: RiskLevel = RiskLevel.LOW
    recommendations: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.finding_type,
            "name": self.name,
            "vendor": self.vendor,
            "version": self.version,
            "risk_level": self.risk_level.value,
            "recommendations": self.recommendations,
            "details": self.details,
        }


# Known hardware-dependent software vendors
HARDWARE_DEPENDENT_VENDORS = {
    "Autodesk": {
        "risk": RiskLevel.HIGH,
        "reason": "Hardware-locked licensing",
        "mitigation": "Reactivate license after migration using Autodesk Account",
    },
    "Adobe Systems": {
        "risk": RiskLevel.HIGH,
        "reason": "Hardware fingerprinting for activation",
        "mitigation": "Deactivate before migration, reactivate after",
    },
    "Bentley": {
        "risk": RiskLevel.HIGH,
        "reason": "License tied to hardware ID",
        "mitigation": "Contact Bentley support for license transfer",
    },
    "Dassault": {
        "risk": RiskLevel.HIGH,
        "reason": "CATIA/SolidWorks hardware-locked licenses",
        "mitigation": "Use license server or contact support for license transfer",
    },
    "Siemens": {
        "risk": RiskLevel.HIGH,
        "reason": "NX/Solid Edge hardware dongles or locked licenses",
        "mitigation": "Ensure dongle passthrough or use network licensing",
    },
    "PTC": {
        "risk": RiskLevel.HIGH,
        "reason": "Creo/Windchill hardware fingerprinting",
        "mitigation": "Update license server or reactivate licenses",
    },
    "Ansys": {
        "risk": RiskLevel.MEDIUM,
        "reason": "Workbench may require license reconfiguration",
        "mitigation": "Update Ansys license manager configuration",
    },
    "MathWorks": {
        "risk": RiskLevel.MEDIUM,
        "reason": "MATLAB license may need reactivation",
        "mitigation": "Reactivate using MATLAB Account or license server",
    },
    "ESRI": {
        "risk": RiskLevel.MEDIUM,
        "reason": "ArcGIS licensing tied to machine ID",
        "mitigation": "Deauthorize before migration, reauthorize after",
    },
    "Altium": {
        "risk": RiskLevel.HIGH,
        "reason": "PCB design software with hardware dongles",
        "mitigation": "Ensure dongle passthrough or use network licensing",
    },
}

# Known license manager services
LICENSE_SERVICES = {
    "lmgrd": {
        "name": "FlexLM License Manager",
        "risk": RiskLevel.HIGH,
        "mitigation": "Update license.dat with new hostname/MAC address",
    },
    "rlm": {
        "name": "Reprise License Manager",
        "risk": RiskLevel.HIGH,
        "mitigation": "Reconfigure RLM server settings in rlm.opt",
    },
    "hasplms": {
        "name": "Sentinel HASP License Manager",
        "risk": RiskLevel.HIGH,
        "mitigation": "Update HASP License Manager with new server details",
    },
    "aksusb": {
        "name": "Aladdin HASP Driver",
        "risk": RiskLevel.CRITICAL,
        "mitigation": "Ensure HASP dongle is passed through to VM or use network dongle",
    },
}

# Known dongle drivers
DONGLE_DRIVERS = {
    "akshasp": {
        "name": "Aladdin HASP",
        "risk": RiskLevel.CRITICAL,
        "mitigation": "USB dongle passthrough required or use network HASP server",
    },
    "sentinel": {
        "name": "SafeNet Sentinel",
        "risk": RiskLevel.CRITICAL,
        "mitigation": "USB passthrough or Sentinel Protection Server required",
    },
    "haspvlib": {
        "name": "HASP Virtual Library",
        "risk": RiskLevel.HIGH,
        "mitigation": "Virtual dongle may need reconfiguration",
    },
    "cmstick": {
        "name": "CodeMeter Stick",
        "risk": RiskLevel.CRITICAL,
        "mitigation": "USB passthrough or CodeMeter License Central required",
    },
    "wibukey": {
        "name": "WIBU-KEY Dongle",
        "risk": RiskLevel.CRITICAL,
        "mitigation": "USB passthrough or WIBU-Systems CodeMeter network server",
    },
    "rockey": {
        "name": "Rockey Dongle",
        "risk": RiskLevel.CRITICAL,
        "mitigation": "USB passthrough required",
    },
}


def detect_hardware_dependent_apps(g: "guestfs.GuestFS", root: str) -> list[AppCompatFinding]:
    """Detect hardware-dependent applications from registry.

    Args:
        g: GuestFS instance
        root: Windows root path

    Returns:
        List of findings for hardware-dependent applications
    """
    logger.info("Scanning for hardware-dependent applications")

    findings = []

    try:
        software_path = detect_windows_hive(g, root, "SOFTWARE")
        if not software_path:
            logger.warning("SOFTWARE hive not found")
            return findings

        with tempfile.TemporaryDirectory() as tmpdir:
            local_hive = Path(tmpdir) / "SOFTWARE"
            hive = download_and_open_hive(logger, g, software_path, local_hive, write=False)

            try:
                # Scan 32-bit and 64-bit Uninstall keys
                uninstall_paths = [
                    "Microsoft\\Windows\\CurrentVersion\\Uninstall",
                    "Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
                ]

                for uninstall_path in uninstall_paths:
                    findings.extend(_scan_uninstall_key(hive, uninstall_path))

            finally:
                _close_best_effort(hive)

    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort hive scan, must not abort the whole migration
        logger.exception("Failed to scan for hardware-dependent apps: %s", e)
        logger.debug("App detection error", exc_info=True)

    logger.info("Found %d hardware-dependent applications", len(findings))
    return findings


def _scan_uninstall_key(hive: "hivex.Hivex", uninstall_path: str) -> list[AppCompatFinding]:
    """Scan a registry Uninstall key for installed applications.

    Args:
        hive: Opened SOFTWARE hive
        uninstall_path: Path to Uninstall key

    Returns:
        List of findings for detected applications
    """
    findings = []

    try:
        root = hive.root()
        uninstall_node = hive.node_get_child(root, uninstall_path.replace("\\", "\\"))

        if not uninstall_node:
            return findings

        # Enumerate all app GUIDs/names under Uninstall
        app_keys = hive.node_children(uninstall_node)

        for app_key in app_keys:
            app_name = hive.node_name(app_key)
            app_info = _read_app_info(hive, app_key)

            if not app_info.get("DisplayName"):
                continue  # Skip entries without display name

            # Check if vendor is hardware-dependent
            vendor_info = _check_vendor(app_info.get("Publisher", ""))

            if vendor_info:
                finding = AppCompatFinding(
                    finding_type="app",
                    name=app_info.get("DisplayName", app_name),
                    vendor=app_info.get("Publisher"),
                    version=app_info.get("DisplayVersion"),
                    risk_level=vendor_info["risk"],
                    recommendations=[
                        vendor_info["reason"],
                        vendor_info["mitigation"],
                    ],
                    details={
                        "install_location": app_info.get("InstallLocation"),
                        "uninstall_string": app_info.get("UninstallString"),
                    },
                )
                findings.append(finding)

    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort per-key scan, must not abort the rest
        logger.debug("Error scanning Uninstall key %s: %s", uninstall_path, e)

    return findings


def _read_app_info(hive: "hivex.Hivex", app_node: int) -> dict[str, str]:
    """Read application metadata from registry node.

    Args:
        hive: Hivex instance
        app_node: Node ID for application key

    Returns:
        Dictionary of application metadata
    """
    app_info = {}

    value_names = [
        "DisplayName",
        "DisplayVersion",
        "Publisher",
        "InstallLocation",
        "UninstallString",
        "InstallDate",
    ]

    for value_name in value_names:
        try:
            value = hive.node_get_value(app_node, value_name)
            if value:
                val_type = hive.value_type(value)[0]
                val_data = hive.value_value(value)

                # Decode string values
                if val_type in [1, 2]:  # REG_SZ or REG_EXPAND_SZ
                    try:
                        app_info[value_name] = val_data.decode("utf-16le", errors="ignore").rstrip("\x00")
                    except Exception:  # pylint: disable=broad-exception-caught  # decode failure just falls back to raw string
                        app_info[value_name] = str(val_data)

        except Exception:  # pylint: disable=broad-exception-caught  # any single value read failure just skips that value
            continue

    return app_info


def _check_vendor(publisher: str) -> Optional[dict[str, Any]]:
    """Check if publisher is a known hardware-dependent vendor.

    Args:
        publisher: Publisher name from registry

    Returns:
        Vendor info dict if match found, None otherwise
    """
    if not publisher:
        return None

    publisher_lower = publisher.lower()

    for vendor, info in HARDWARE_DEPENDENT_VENDORS.items():
        if vendor.lower() in publisher_lower:
            return info

    return None


def detect_license_services(  # pylint: disable=too-many-locals  # single-pass SYSTEM hive scan across controlset/services/known-service lookups
    g: "guestfs.GuestFS", root: str
) -> list[AppCompatFinding]:
    """Detect license manager services in SYSTEM hive.

    Args:
        g: GuestFS instance
        root: Windows root path

    Returns:
        List of findings for detected license services
    """
    logger.info("Scanning for license manager services")

    findings = []

    # pylint: disable=duplicate-code
    # reason: SYSTEM-hive open + current-controlset resolution mirrors the
    # equivalent step in appcompat/sqlserver.py's service-account lookup --
    # coincidentally similar shape (both read the Services subtree), but each
    # walks a different path and returns different data, so kept independent.
    try:
        system_path = detect_windows_hive(g, root, "SYSTEM")
        if not system_path:
            logger.warning("SYSTEM hive not found")
            return findings

        with tempfile.TemporaryDirectory() as tmpdir:
            local_hive = Path(tmpdir) / "SYSTEM"
            hive = download_and_open_hive(logger, g, system_path, local_hive, write=False)

            try:
                root_node = hive.root()
                controlset_name = _detect_current_controlset(hive, root_node)
                services_path = f"{controlset_name}\\Services"
                # pylint: enable=duplicate-code

                services_node = hive.node_get_child(root_node, services_path)
                if not services_node:
                    return findings

                # Check for known license services
                for service_name, service_info in LICENSE_SERVICES.items():
                    try:
                        service_node = hive.node_get_child(services_node, service_name)
                        if service_node:
                            finding = AppCompatFinding(
                                finding_type="license_service",
                                name=service_info["name"],
                                risk_level=service_info["risk"],
                                recommendations=[service_info["mitigation"]],
                                details={"service_name": service_name},
                            )
                            findings.append(finding)
                    except Exception:  # pylint: disable=broad-exception-caught  # best-effort per-service lookup, must not abort the scan
                        continue

            finally:
                _close_best_effort(hive)

    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort hive scan, must not abort the whole migration
        logger.exception("Failed to scan for license services: %s", e)
        logger.debug("License service detection error", exc_info=True)

    logger.info("Found %d license manager services", len(findings))
    return findings


def detect_dongle_drivers(g: "guestfs.GuestFS", root: str) -> list[AppCompatFinding]:
    """Detect hardware dongle drivers in System32/drivers.

    Args:
        g: GuestFS instance
        root: Windows root path

    Returns:
        List of findings for detected dongle drivers
    """
    logger.info("Scanning for hardware dongle drivers")

    findings = []

    drivers_dir = f"{root}/Windows/System32/drivers"

    try:
        for driver_name, driver_info in DONGLE_DRIVERS.items():
            driver_path = f"{drivers_dir}/{driver_name}.sys"

            try:
                if g.exists(driver_path):
                    finding = AppCompatFinding(
                        finding_type="dongle_driver",
                        name=driver_info["name"],
                        risk_level=driver_info["risk"],
                        recommendations=[driver_info["mitigation"]],
                        details={
                            "driver_file": driver_path,
                            "driver_name": driver_name,
                        },
                    )
                    findings.append(finding)
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort per-driver check, must not abort the scan
                logger.debug("Error checking for driver %s: %s", driver_name, e)

    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort driver scan, must not abort the whole migration
        logger.exception("Failed to scan for dongle drivers: %s", e)
        logger.debug("Dongle driver detection error", exc_info=True)

    logger.info("Found %d dongle drivers", len(findings))
    return findings
