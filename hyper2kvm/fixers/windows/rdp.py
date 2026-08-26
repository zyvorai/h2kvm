# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/fixers/windows/rdp.py

"""
RDP (Remote Desktop Protocol) verification for Windows VMs.

Ensures RDP is enabled and accessible after migration to prevent admin lockout
on headless VMs where VNC/console access may not be available.

Uses python-hivex directly (works with both guestfs and VMCraft backends).
"""

from __future__ import annotations

import contextlib
import logging
import os
import tempfile
from typing import Any

try:
    import hivex as _hivex_mod  # type: ignore

    HIVEX_AVAILABLE = True
except ImportError:
    _hivex_mod = None  # type: ignore
    HIVEX_AVAILABLE = False

logger = logging.getLogger(__name__)

_SERVICE_START_LABELS: dict[int, str] = {
    0: "Boot",
    1: "System",
    2: "Automatic",
    3: "Manual",
    4: "Disabled",
}


def service_start_label(start: int | None) -> str:
    """Human-readable Windows service Start value from the SYSTEM hive."""
    if start is None:
        return "unknown"
    return _SERVICE_START_LABELS.get(start, f"Start={start}")


def log_rdp_precheck_summary(
    log: logging.Logger,
    rdp_result: dict[str, Any],
    *,
    firstboot_planned: bool = True,
) -> None:
    """Emit a single INFO/WARNING block summarizing offline RDP readiness."""
    if rdp_result.get("error"):
        log.warning(
            "Windows RDP pre-check (offline): could not read registry (%s)",
            rdp_result["error"],
        )
        for w in rdp_result.get("warnings") or []:
            log.warning("  %s", w)
        return

    registry_ok = rdp_result.get("registry_allows_rdp")
    if registry_ok is None:
        registry_ok = rdp_result.get("rdp_enabled")
    fdeny = rdp_result.get("fdeny_ts_connections")
    term = rdp_result.get("term_service_start_label") or service_start_label(
        rdp_result.get("term_service_start")
    )
    port = rdp_result.get("rdp_port", 3389)

    log.info(
        "Windows RDP pre-check (offline): registry_allow=%s (fDenyTSConnections=%s), "
        "TermService=%s, port=%s",
        registry_ok,
        fdeny if fdeny is not None else "?",
        term,
        port,
    )
    if firstboot_planned:
        log.info("  Firstboot will enable RDP firewall rules and start TermService on first guest boot")
    if rdp_result.get("rdp_enabled"):
        log.info("  Offline check: RDP looks ready before first boot")
    else:
        log.warning("  Offline check: RDP may not listen until firstboot runs (TermService or registry)")
    for w in rdp_result.get("warnings") or []:
        log.warning("  %s", w)


def _download_hive(g, hive_path: str) -> bytes | None:
    """Download a registry hive from the guest filesystem."""
    # pylint: disable=duplicate-code
    # reason: the read_file/cat backend-accessor probe mirrors
    # hyper2kvm/fixers/windows/registry/io.py's _download_hive_local() --
    # coincidental. This helper has no logger to report per-attempt
    # failures to and returns bytes directly, while the registry/io.py
    # version logs each failed attempt and feeds a larger fallback chain.
    for fn_name in ("read_file", "cat"):
        fn = getattr(g, fn_name, None)
        if not callable(fn):
            continue
        try:
            data = fn(hive_path)
            if isinstance(data, (bytes, bytearray)):
                return bytes(data)
            return str(data).encode("latin-1", errors="ignore")
        except Exception:  # pylint: disable=broad-exception-caught  # dynamic guestfs/VMCraft accessor, try next method
            continue

    # Try download to temp file
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".hiv") as tmp:
            tmp_path = tmp.name
        g.download(hive_path, tmp_path)

        with open(tmp_path, "rb") as f:
            data = f.read()
        os.unlink(tmp_path)
        return data
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort hive download, caller treats None as failure
        pass

    return None


def _find_child_ci(h, parent: int, name: str) -> int:
    """Find child node by name (case-insensitive)."""
    try:
        children = h.node_children(parent)
        name_lower = name.lower()
        for child in children:
            if h.node_name(child).lower() == name_lower:
                return child
    except Exception:  # pylint: disable=broad-exception-caught  # dynamic hivex object, treat any failure as "not found"
        pass
    return 0


def _navigate_key(h, root: int, path: str) -> int:
    """Navigate registry path from root (backslash-separated)."""
    node = root
    for part in path.split("\\"):
        if not part:
            continue
        node = _find_child_ci(h, node, part)
        if not node:
            return 0
    return node


def _read_dword(h, node: int, value_name: str) -> int | None:
    """Read a DWORD value from a registry node."""
    try:
        values = h.node_values(node)
        name_lower = value_name.lower()
        for val in values:
            if h.value_key(val).lower() == name_lower:
                t, data = h.value_value(val)
                if t == 4 and len(data) >= 4:  # REG_DWORD
                    return int.from_bytes(data[:4], byteorder="little")
    except Exception:  # pylint: disable=broad-exception-caught  # dynamic hivex object, treat any failure as "value missing"
        pass
    return None


def _find_current_controlset(h, root: int) -> int:
    """Find current ControlSet via Select\\Current."""
    select = _find_child_ci(h, root, "Select")
    if select:
        current = _read_dword(h, select, "Current")
        if current is not None:
            return _find_child_ci(h, root, f"ControlSet{current:03d}")
    # Fallback
    return _find_child_ci(h, root, "ControlSet001")


# pylint: disable=too-many-locals,too-many-branches,too-many-statements
# multi-field registry readout (fDeny, TermService, NLA, port) with per-field warnings
def verify_rdp_enabled(
    g,
    root: str = "",  # pylint: disable=unused-argument  # kept for call-signature parity with enable_rdp_if_disabled
) -> dict[str, Any]:
    """
    Verify Remote Desktop is enabled in Windows registry.

    Downloads the SYSTEM hive and uses python-hivex directly,
    so it works with both guestfs and VMCraft backends.
    """
    result: dict[str, Any] = {
        "rdp_enabled": False,
        "registry_allows_rdp": None,
        "fdeny_ts_connections": None,
        "term_service_start": None,
        "term_service_start_label": None,
        "nla_enabled": False,
        "rdp_port": 3389,
        "warnings": [],
        "recommendations": [],
        "error": None,
    }

    if not HIVEX_AVAILABLE:
        result["error"] = "python-hivex not installed"
        result["warnings"].append("Could not verify RDP configuration (hivex not available)")
        return result

    system_hive_path = "/Windows/System32/config/SYSTEM"

    if not g.exists(system_hive_path):
        result["error"] = "SYSTEM registry hive not found"
        result["warnings"].append("Could not verify RDP configuration")
        return result

    h = None
    tmp_path = None
    try:
        # Download hive to temp file
        data = _download_hive(g, system_hive_path)
        if not data or len(data) < 4096:
            result["error"] = "Failed to download SYSTEM hive"
            result["warnings"].append("Could not verify RDP configuration")
            return result

        with tempfile.NamedTemporaryFile(delete=False, suffix=".hiv") as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        h = _hivex_mod.Hivex(tmp_path, write=False)
        root_node = h.root()

        cs = _find_current_controlset(h, root_node)
        if not cs:
            result["warnings"].append("Could not find CurrentControlSet in registry")
            return result

        ts_node = _navigate_key(h, cs, "Control\\Terminal Server")
        if not ts_node:
            result["warnings"].append("Terminal Server registry key not found")
            return result

        # Check fDenyTSConnections
        fdeny = _read_dword(h, ts_node, "fDenyTSConnections")
        if fdeny is not None:
            result["fdeny_ts_connections"] = fdeny
            result["registry_allows_rdp"] = fdeny == 0
            result["rdp_enabled"] = fdeny == 0
            if not result["rdp_enabled"]:
                result["warnings"].append(
                    "Remote Desktop is DISABLED - you may not be able to access VM after migration"
                )
                result["recommendations"].append(
                    "Enable RDP before migration:\n"
                    "  PowerShell: Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' "
                    "-Name 'fDenyTSConnections' -Value 0\n"
                    "  Or: System Properties -> Remote tab -> Allow remote connections"
                )
        else:
            result["warnings"].append("Could not determine RDP status from registry")

        term_node = _navigate_key(h, cs, "Services\\TermService")
        if term_node:
            term_start = _read_dword(h, term_node, "Start")
            result["term_service_start"] = term_start
            result["term_service_start_label"] = service_start_label(term_start)
            if term_start is not None and term_start != 2:
                result["warnings"].append(
                    f"TermService Start={term_start} ({result['term_service_start_label']}) "
                    "— RDP may not listen until firstboot runs"
                )
                result["rdp_enabled"] = False

        # Check NLA
        nla = _read_dword(h, ts_node, "UserAuthentication")
        if nla is not None:
            result["nla_enabled"] = nla == 1

        # Check RDP port
        rdp_tcp = _navigate_key(h, ts_node, "WinStations\\RDP-Tcp")
        if rdp_tcp:
            port = _read_dword(h, rdp_tcp, "PortNumber")
            if port is not None:
                result["rdp_port"] = port
                if port != 3389:
                    result["warnings"].append(f"RDP uses non-standard port {port} (default: 3389)")
                    result["recommendations"].append(f"Ensure firewall allows port {port} for RDP access")

    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort offline check, must not abort migration
        result["error"] = str(e)
        result["warnings"].append(f"RDP verification failed: {e}")
        logger.debug("RDP verification error: %s", e)
    finally:
        if h:
            with contextlib.suppress(Exception):
                h.close()
        if tmp_path:
            with contextlib.suppress(Exception):
                os.unlink(tmp_path)

    return result
# pylint: enable=too-many-locals,too-many-branches,too-many-statements


# pylint: disable=too-many-locals,too-many-branches,too-many-statements
# mirrors verify_rdp_enabled's multi-field registry read-and-modify flow
def enable_rdp_if_disabled(
    g,
    root: str = "",  # pylint: disable=unused-argument  # kept for call-signature parity with verify_rdp_enabled
    log: logging.Logger | None = None,
) -> dict[str, Any]:
    """
    Enable Remote Desktop if currently disabled.

    Downloads SYSTEM hive, modifies it, uploads back.
    Works with both guestfs and VMCraft backends.
    """
    if log is None:
        log = logging.getLogger(__name__)

    result = {
        "modified": False,
        "previous_state": None,
        "current_state": None,
        "error": None,
    }

    if not HIVEX_AVAILABLE:
        result["error"] = "python-hivex not installed"
        return result

    system_hive_path = "/Windows/System32/config/SYSTEM"

    if not g.exists(system_hive_path):
        result["error"] = "SYSTEM registry hive not found"
        return result

    h = None
    tmp_path = None
    try:
        data = _download_hive(g, system_hive_path)
        if not data or len(data) < 4096:
            result["error"] = "Failed to download SYSTEM hive"
            return result

        with tempfile.NamedTemporaryFile(delete=False, suffix=".hiv") as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        h = _hivex_mod.Hivex(tmp_path, write=True)
        root_node = h.root()

        cs = _find_current_controlset(h, root_node)
        if not cs:
            result["error"] = "CurrentControlSet not found"
            return result

        ts_node = _navigate_key(h, cs, "Control\\Terminal Server")
        if not ts_node:
            result["error"] = "Terminal Server registry key not found"
            return result

        fdeny = _read_dword(h, ts_node, "fDenyTSConnections")
        result["previous_state"] = (fdeny == 0) if fdeny is not None else None
        registry_modified = False

        if fdeny != 0:
            h.node_set_value(
                ts_node,
                {
                    "key": "fDenyTSConnections",
                    "t": 4,  # REG_DWORD
                    "value": (0).to_bytes(4, byteorder="little"),
                },
            )
            registry_modified = True
            log.info("Enabled Remote Desktop (set fDenyTSConnections = 0)")
        else:
            result["current_state"] = True
            log.info("Remote Desktop registry already allows connections")

        # TermService must be Automatic or RDP listens on nothing after boot.
        for svc_name in ("TermService", "UmRdpService"):
            svc_node = _navigate_key(h, cs, f"Services\\{svc_name}")
            if not svc_node:
                continue
            start = _read_dword(h, svc_node, "Start")
            if start is not None and start != 2:
                h.node_set_value(
                    svc_node,
                    {
                        "key": "Start",
                        "t": 4,
                        "value": (2).to_bytes(4, byteorder="little"),
                    },
                )
                registry_modified = True
                log.info("Set %s Start=Automatic in offline registry", svc_name)

        if registry_modified:
            h.commit(tmp_path)
            h.close()
            h = None
            g.upload(tmp_path, system_hive_path)
            result["modified"] = True
            result["current_state"] = True
        elif result.get("current_state") is not True:
            result["current_state"] = True

    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort registry patch, must not abort migration
        result["error"] = str(e)
        log.debug("Failed to enable RDP: %s", e)
    finally:
        if h:
            with contextlib.suppress(Exception):
                h.close()
        if tmp_path:
            with contextlib.suppress(Exception):
                os.unlink(tmp_path)

    return result
# pylint: enable=too-many-locals,too-many-branches,too-many-statements


def check_rdp_firewall_rules(
    g,  # pylint: disable=unused-argument  # kept for call-signature parity with verify_rdp_enabled/enable_rdp_if_disabled
    root: str = "",  # pylint: disable=unused-argument  # kept for call-signature parity
) -> dict[str, Any]:
    """
    Check Windows Firewall rules for RDP (port 3389).

    NOTE: This is informational only - firewall rules are migrated separately.
    """
    return {
        "rdp_rule_found": False,
        "rdp_rule_enabled": False,
        "warnings": [
            "Verify Windows Firewall allows RDP after migration:\n"
            "  PowerShell: Enable-NetFirewallRule -DisplayGroup 'Remote Desktop'\n"
            "  Or: Control Panel -> Windows Defender Firewall -> Allow an app"
        ],
    }
