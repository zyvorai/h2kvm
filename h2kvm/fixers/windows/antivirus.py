# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Windows antivirus detection and handling for VM migration.

Detects antivirus software from the offline Windows registry and optionally
disables services that may block VirtIO driver installation (BSOD 0x7B).

Detection sources:
  1. Installed applications (Uninstall registry keys) matched by name/publisher
  2. Windows Defender hive (SOFTWARE\\Microsoft\\Windows Defender)
  3. Known AV service entries in SYSTEM hive

Based on libguestfs inspect-apps.c antivirus classification and
libguestfs PR #335 (Windows Defender detection).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Antivirus detection patterns (from libguestfs inspect-apps.c)
AV_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("generic", re.compile(r"virus", re.IGNORECASE)),
    ("kaspersky", re.compile(r"kaspersky", re.IGNORECASE)),
    ("mcafee", re.compile(r"mcafee", re.IGNORECASE)),
    ("norton", re.compile(r"norton", re.IGNORECASE)),
    ("sophos", re.compile(r"sophos", re.IGNORECASE)),
    ("trend", re.compile(r"ApexOneNT", re.IGNORECASE)),
    ("avg", re.compile(r"avg technologies", re.IGNORECASE)),
    ("eset", re.compile(r"eset", re.IGNORECASE)),
    ("bitdefender", re.compile(r"bitdefender", re.IGNORECASE)),
    ("crowdstrike", re.compile(r"crowdstrike|falcon", re.IGNORECASE)),
    ("sentinelone", re.compile(r"sentinelone|sentinel", re.IGNORECASE)),
    ("cylance", re.compile(r"cylance", re.IGNORECASE)),
    ("webroot", re.compile(r"webroot", re.IGNORECASE)),
    ("malwarebytes", re.compile(r"malwarebytes", re.IGNORECASE)),
]

# Known AV service names in SYSTEM\\ControlSet001\\Services
AV_SERVICES: dict[str, str] = {
    "WinDefend": "Microsoft Defender Antivirus",
    "SecurityHealthService": "Windows Security Service",
    "MsMpSvc": "Microsoft Antimalware Service",
    "McShield": "McAfee Real-Time Scanning",
    "McAfeeFramework": "McAfee Framework Service",
    "McTaskManager": "McAfee Task Manager",
    "mfevtp": "McAfee Validation Trust Protection",
    "AVP": "Kaspersky Anti-Virus",
    "klnagent": "Kaspersky Network Agent",
    "Norton AntiVirus": "Norton AntiVirus",
    "NortonSecurity": "Norton Security",
    "SepMasterService": "Symantec Endpoint Protection",
    "SAVService": "Sophos Anti-Virus",
    "Sophos Agent": "Sophos Agent",
    "ntrtscan": "Trend Micro OfficeScan",
    "TmFilter": "Trend Micro Common Client Filter",
    "ESET Service": "ESET NOD32 Antivirus",
    "ekrn": "ESET Kernel Service",
    "BDAgent": "Bitdefender Agent",
    "EPSecurityService": "Bitdefender Endpoint Security",
    "CSFalconService": "CrowdStrike Falcon Sensor",
    "SentinelAgent": "SentinelOne Agent",
    "CylanceSvc": "Cylance PROTECT",
    "WRSA": "Webroot SecureAnywhere",
    "MBAMService": "Malwarebytes Service",
    "avgwd": "AVG Watchdog",
    "avast! Antivirus": "Avast Antivirus",
    "AvastSvc": "Avast Antivirus Service",
}


@dataclass
class AntivirusInfo:
    """Detected antivirus information."""

    name: str
    vendor: str = ""
    source: str = ""  # "uninstall_key", "defender_hive", "service"
    service_name: str = ""
    disabled: bool = False


@dataclass
class AntivirusReport:
    """Result of antivirus detection scan."""

    detected: list[AntivirusInfo] = field(default_factory=list)
    defender_present: bool = False
    defender_disabled: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def has_antivirus(self) -> bool:
        """Return True if at least one antivirus product was detected."""
        return len(self.detected) > 0

    def summary(self) -> str:
        """Return a short human-readable summary of detected antivirus products."""
        if not self.has_antivirus:
            return "No antivirus detected"
        names = [av.name for av in self.detected]
        return f"Antivirus detected: {', '.join(names)}"


def detect_antivirus_from_registry(
    mount_path: str | Path,
    av_logger: logging.Logger | None = None,
) -> AntivirusReport:
    """
    Detect antivirus software from offline Windows registry.

    Args:
        mount_path: Path to mounted Windows filesystem (e.g., /mnt/windows)
        av_logger: Optional logger

    Returns:
        AntivirusReport with detected AV software
    """
    log = av_logger or logger
    report = AntivirusReport()
    mount = Path(mount_path)

    # --- 1. Check Uninstall keys for known AV patterns ---
    _scan_uninstall_keys(mount, report, log)

    # --- 2. Check Windows Defender hive (PR #335 approach) ---
    _check_defender_hive(mount, report, log)

    # --- 3. Check for known AV services ---
    _check_av_services(mount, report, log)

    # --- Generate warnings ---
    if report.has_antivirus:
        av_names = ", ".join(av.name for av in report.detected)
        report.warnings.append(
            f"Antivirus software detected: {av_names}. "
            "AV may block VirtIO driver installation on first boot, "
            "potentially causing BSOD 0x7B (INACCESSIBLE_BOOT_DEVICE). "
            "Consider disabling AV services before migration."
        )

    if report.defender_present and not report.defender_disabled:
        report.warnings.append(
            "Windows Defender is active. Real-time protection may "
            "interfere with VirtIO driver loading at boot time."
        )

    return report


def _scan_uninstall_keys(  # pylint: disable=too-many-nested-blocks,too-many-locals  # walks hive path -> children -> AV patterns -> fields
    mount: Path, report: AntivirusReport, log: logging.Logger
) -> None:
    """Scan Uninstall registry keys for antivirus patterns."""
    # Look for SOFTWARE hive
    software_hive = _find_hive(mount, "SOFTWARE")
    if not software_hive:
        return

    try:
        import hivex  # pylint: disable=import-outside-toplevel  # keeps python-hivex an optional dependency
    except ImportError:
        log.debug("hivex not available, skipping Uninstall key scan")
        return

    try:
        h = hivex.Hivex(str(software_hive))
    except Exception as e:  # pylint: disable=broad-exception-caught  # hivex raises dynamic/untyped errors on malformed or locked hives
        log.debug(f"Failed to open SOFTWARE hive: {e}")
        return

    try:
        # Check both 32-bit and 64-bit uninstall paths
        for path in [
            ["Microsoft", "Windows", "CurrentVersion", "Uninstall"],
            ["WOW6432Node", "Microsoft", "Windows", "CurrentVersion", "Uninstall"],
        ]:
            node = _navigate_hive(h, path)
            if not node:
                continue

            for child in h.node_children(node):
                child_name = h.node_name(child)
                display_name = _get_hive_value_str(h, child, "DisplayName")
                publisher = _get_hive_value_str(h, child, "Publisher")

                for av_id, pattern in AV_PATTERNS:
                    for field_val in [child_name, display_name, publisher]:
                        if field_val and pattern.search(field_val):
                            av = AntivirusInfo(
                                name=display_name or child_name,
                                vendor=publisher or "",
                                source="uninstall_key",
                            )
                            if not any(x.name == av.name for x in report.detected):
                                report.detected.append(av)
                                log.info(f"Antivirus detected (registry): {av.name} ({av_id})")
                            break
    finally:
        del h


def _check_defender_hive(mount: Path, report: AntivirusReport, log: logging.Logger) -> None:
    """
    Check Windows Defender status from SOFTWARE hive.
    Based on libguestfs PR #335.
    """
    software_hive = _find_hive(mount, "SOFTWARE")
    if not software_hive:
        return

    try:
        import hivex  # pylint: disable=import-outside-toplevel  # keeps python-hivex an optional dependency
    except ImportError:
        log.debug("hivex not available, skipping Defender check")
        return

    try:
        h = hivex.Hivex(str(software_hive))
    except Exception as e:  # pylint: disable=broad-exception-caught  # hivex raises dynamic/untyped errors on malformed or locked hives
        log.debug(f"Failed to open SOFTWARE hive: {e}")
        return

    try:
        node = _navigate_hive(h, ["Microsoft", "Windows Defender"])
        if not node:
            return

        report.defender_present = True

        # Check DisableAntiVirus (DWORD)
        disabled = False
        for val_name in ["DisableAntiVirus", "DisableAntiSpyware"]:
            val = _get_hive_value_dword(h, node, val_name)
            if val == 1:
                disabled = True
                break

        report.defender_disabled = disabled

        if not disabled:
            av = AntivirusInfo(
                name="Microsoft Defender Antivirus",
                vendor="Microsoft Corporation",
                source="defender_hive",
                service_name="WinDefend",
            )
            if not any(x.service_name == "WinDefend" for x in report.detected):
                report.detected.append(av)
                log.info("Windows Defender detected (active)")
        else:
            log.info("Windows Defender detected but disabled")
    finally:
        del h


def _check_av_services(mount: Path, report: AntivirusReport, log: logging.Logger) -> None:
    """Check for known antivirus services in SYSTEM hive."""
    system_hive = _find_hive(mount, "SYSTEM")
    if not system_hive:
        return

    try:
        import hivex  # pylint: disable=import-outside-toplevel  # keeps python-hivex an optional dependency
    except ImportError:
        log.debug("hivex not available, skipping service scan")
        return

    try:
        h = hivex.Hivex(str(system_hive))
    except Exception as e:  # pylint: disable=broad-exception-caught  # hivex raises dynamic/untyped errors on malformed or locked hives
        log.debug(f"Failed to open SYSTEM hive: {e}")
        return

    try:
        # Find ControlSet001\Services
        services_node = _navigate_hive(h, ["ControlSet001", "Services"])
        if not services_node:
            return

        for svc_name, display_name in AV_SERVICES.items():
            node = None
            try:
                node = h.node_get_child(services_node, svc_name)
            # pylint: disable-next=broad-exception-caught  # hivex errors are dynamic/untyped; missing key means "not present"
            except Exception:
                continue

            if not node:
                continue

            # Check if service is disabled (Start = 4)
            start_val = _get_hive_value_dword(h, node, "Start")
            is_disabled = start_val == 4

            av = AntivirusInfo(
                name=display_name,
                vendor="",
                source="service",
                service_name=svc_name,
                disabled=is_disabled,
            )

            if not any(x.service_name == svc_name for x in report.detected):
                report.detected.append(av)
                status = "disabled" if is_disabled else "enabled"
                log.info(f"AV service found: {svc_name} ({display_name}) — {status}")
    finally:
        del h


def disable_defender_offline(  # pylint: disable=too-many-nested-blocks  # two independent hive-edit blocks, each with its own try/for/try
    mount_path: str | Path,
    av_logger: logging.Logger | None = None,
) -> dict[str, Any]:
    """
    Disable Windows Defender services offline via registry editing.

    Sets Start=4 (disabled) for WinDefend, SecurityHealthService, and MsMpSvc.
    Sets DisableAntiSpyware=1 in SOFTWARE hive.

    Args:
        mount_path: Path to mounted Windows filesystem
        av_logger: Optional logger

    Returns:
        Dict with services disabled and status
    """
    log = av_logger or logger
    mount = Path(mount_path)
    result: dict[str, Any] = {"disabled_services": [], "registry_keys_set": [], "errors": []}

    # --- Disable services in SYSTEM hive ---
    system_hive = _find_hive(mount, "SYSTEM")
    if system_hive:
        try:
            import hivex  # pylint: disable=import-outside-toplevel  # keeps python-hivex an optional dependency

            h = hivex.Hivex(str(system_hive), write=True)

            services_node = _navigate_hive(h, ["ControlSet001", "Services"])
            if services_node:
                # pylint: disable=duplicate-code
                # reason: mirrors the Start=4 hive-set idiom in virtio_injector.py's
                # disable_services_in_hive() -- different service list and per-service
                # error/result tracking, so kept independent rather than coupling
                # antivirus disabling to the VirtIO VMware-service disabling path.
                for svc in ["WinDefend", "SecurityHealthService", "MsMpSvc"]:
                    try:
                        node = h.node_get_child(services_node, svc)
                        if node:
                            # Set Start = 4 (disabled)
                            h.node_set_value(
                                node,
                                {
                                    "key": "Start",
                                    "t": 4,  # REG_DWORD
                                    "value": (4).to_bytes(4, "little"),
                                },
                            )
                            result["disabled_services"].append(svc)
                            log.info(f"Disabled service: {svc} (Start=4)")
                    # pylint: disable-next=broad-exception-caught  # hivex errors are dynamic/untyped; one service failing must not abort the others
                    except Exception as e:
                        result["errors"].append(f"{svc}: {e}")
                # pylint: enable=duplicate-code

            h.commit(str(system_hive))
            del h
        except ImportError:
            result["errors"].append("hivex not available")
        except Exception as e:  # pylint: disable=broad-exception-caught  # hivex raises dynamic/untyped errors; must not abort the SOFTWARE-hive edit below
            result["errors"].append(f"SYSTEM hive error: {e}")

    # --- Set DisableAntiSpyware in SOFTWARE hive ---
    software_hive = _find_hive(mount, "SOFTWARE")
    if software_hive:
        try:
            import hivex  # pylint: disable=import-outside-toplevel  # keeps python-hivex an optional dependency

            h = hivex.Hivex(str(software_hive), write=True)

            policies = _navigate_hive(
                h,
                ["Policies", "Microsoft", "Windows Defender"],
                create=True,
            )
            if policies:
                h.node_set_value(
                    policies,
                    {
                        "key": "DisableAntiSpyware",
                        "t": 4,  # REG_DWORD
                        "value": (1).to_bytes(4, "little"),
                    },
                )
                result["registry_keys_set"].append(
                    r"HKLM\SOFTWARE\Policies\Microsoft\Windows Defender\DisableAntiSpyware=1"
                )
                log.info("Set DisableAntiSpyware=1 in Windows Defender policy")

            h.commit(str(software_hive))
            del h
        except ImportError:
            result["errors"].append("hivex not available")
        except Exception as e:  # pylint: disable=broad-exception-caught  # hivex raises dynamic/untyped errors on malformed or locked hives
            result["errors"].append(f"SOFTWARE hive error: {e}")

    return result


# ── Hive helpers ──


def _find_hive(mount: Path, hive_name: str) -> Path | None:
    """Find a Windows registry hive file (case-insensitive)."""
    candidates = [
        mount / "Windows" / "System32" / "config" / hive_name,
        mount / "windows" / "system32" / "config" / hive_name.lower(),
        mount / "WINDOWS" / "system32" / "config" / hive_name,
    ]
    for c in candidates:
        if c.exists():
            return c
    # Glob fallback
    for p in mount.rglob(f"config/{hive_name}"):
        if p.is_file():
            return p
    return None


def _navigate_hive(h, path: list[str], create: bool = False):
    """Navigate hivex node path. Returns node or None."""
    try:
        node = h.root()
        for name in path:
            child = None
            try:
                child = h.node_get_child(node, name)
            except Exception:  # pylint: disable=broad-exception-caught  # hivex raises dynamic/untyped errors; missing child just means "not found"
                pass
            if not child:
                if create:
                    child = h.node_add_child(node, name)
                else:
                    return None
            node = child
        return node
    except Exception:  # pylint: disable=broad-exception-caught  # hivex raises dynamic/untyped errors on a malformed hive tree
        return None


def _get_hive_value_str(h, node, name: str) -> str:
    """Get a REG_SZ value from a hivex node."""
    try:
        val = h.node_get_value(node, name)
        if not val:
            return ""
        t = h.value_type(val)
        # REG_SZ = 1, REG_EXPAND_SZ = 2
        if t[0] in (1, 2):
            return h.value_string(val)
        return ""
    except Exception:  # pylint: disable=broad-exception-caught  # hivex raises dynamic/untyped errors on a malformed value
        return ""


def _get_hive_value_dword(h, node, name: str) -> int | None:
    """Get a REG_DWORD value from a hivex node."""
    try:
        val = h.node_get_value(node, name)
        if not val:
            return None
        data = h.value_value(val)
        if data[0] == 4 and len(data[1]) >= 4:  # REG_DWORD
            return int.from_bytes(data[1][:4], "little")
        return None
    except Exception:  # pylint: disable=broad-exception-caught  # hivex raises dynamic/untyped errors on a malformed value
        return None
