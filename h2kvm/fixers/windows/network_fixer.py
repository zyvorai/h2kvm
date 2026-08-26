# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# pylint: disable=too-many-lines
# Cohesive offline->firstboot Windows network retention pipeline (capture,
# override, PowerShell script generation); splitting it would scatter a
# single coherent feature across files more than it would help readability.

# h2kvm/fixers/windows/network_fixer.py
"""
Windows network configuration retention (VMware -> KVM).

Reality check (Windows is… Windows):
  - NIC hardware identity changes when you move from vmxnet3/e1000 to virtio-net.
  - Even if you preserve the MAC, Windows may still enumerate a *new* adapter instance.
  - Offline registry-only “perfect” migration is unreliable because mapping
    old interface GUIDs -> new interface GUIDs is not deterministic offline.

So this module takes the safest approach:
  1) OFFLINE: read existing TCP/IP config (SYSTEM hive) and serialize it into a JSON payload
     staged in C:\\h2kvm\\net\\saved_network.json (contains full snapshot + "best" candidate).
  2) OPTIONAL OVERRIDE: users may provide a JSON override (host-side path or dict),
     staged as C:\\h2kvm\\net\\network_override.json.
  3) FIRST BOOT (inside Windows): run a PowerShell script that applies the override (if present),
     otherwise applies the "best" captured config to a chosen adapter.

Hooking:
  - This module piggybacks on the existing firstboot provisioning framework in
    windows_registry.py via provision_firstboot_payload_and_service(..., extra_cmd=...).

Outputs:
  - Structured result dict, similar to windows_virtio.py style.

Security/safety:
  - Never deletes global network config.
  - Only touches the selected adapter.
  - Only applies config if a usable payload is detected.

--------------------------------------------------------------------------------
User override option (embedded JSON for now)
--------------------------------------------------------------------------------

You can provide override in two ways (preferred order):
  1) self.windows_network_config (dict)
  2) self.windows_network_config_path (Path/str to JSON file)

The override is staged into the guest at:
  C:\\h2kvm\\net\\network_override.json

Minimal schemas (examples):

1) Static IPv4 + DNS + gateway, targeting adapter by MAC
{
  "schema": 1,
  "mode": "static",
  "adapter": {
    "mac": "52-54-00-12-34-56"
  },
  "static": {
    "ip": "10.73.1.50",
    "mask": "255.255.255.0",
    "gateway": "10.73.1.1",
    "dns_servers": ["10.73.1.53", "1.1.1.1"]
  }
}

2) DHCP but override DNS (leave IP via DHCP)
{
  "schema": 1,
  "mode": "dhcp",
  "dhcp": {
    "dns_servers": ["10.73.1.53"]
  }
}

3) Static, target adapter by Name (fallback if MAC unknown)
{
  "schema": 1,
  "mode": "static",
  "adapter": {
    "name": "Ethernet"
  },
  "static": {
    "ip": "192.168.122.10",
    "mask": "255.255.255.0",
    "gateway": "192.168.122.1",
    "dns_servers": ["8.8.8.8"]
  }
}

Notes:
  - "mask" is subnet mask; PowerShell converts it to PrefixLength.
  - If gateway is omitted/empty, we apply IP/prefix without a default route.
  - dns_servers accepts list or a single string "1.1.1.1, 8.8.8.8"
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import guestfs  # type: ignore
except ImportError:
    guestfs = None  # type: ignore

from h2kvm.core.guest_utils import (
    guest_mkdir_p as _guest_mkdir_p,
    guest_write_text as _guest_write_text,
)
from h2kvm.core.list_utils import dedup_preserve_order_str
from h2kvm.core.logging_utils import (
    log_step as _step,
    log_with_emoji as _log,
    safe_logger as _safe_logger_base,
)
from h2kvm.core.utils import U

from .registry.firstboot import provision_firstboot_payload_and_service
from .registry.mount import _ensure_windows_root
from .virtio.windows_virtio_paths import _guestfs_to_windows_path

# Logging helpers


def _safe_logger(self) -> logging.Logger:
    """Get logger from instance or create default for windows_network_fixer."""
    return _safe_logger_base(self, "h2kvm.windows_network_fixer")


# Windows paths (guestfs paths, not C:\)


@dataclass(frozen=True)
class WindowsSystemPaths:
    """Guestfs-relative paths to key Windows directories and the SYSTEM hive."""

    windows_dir: str
    system32_dir: str
    config_dir: str
    temp_dir: str
    system_hive: str


def _find_windows_root(g: guestfs.GuestFS) -> str | None:
    for p in ("/Windows", "/WINDOWS", "/winnt", "/WINNT"):
        try:
            if g.is_dir(p):
                return p
        except Exception:  # pylint: disable=broad-exception-caught
            # guestfs raises differing exception types across libguestfs
            # versions/bindings for a missing/unreadable path; any failure here
            # just means "not this candidate root", so keep scanning.
            continue
    return None


def _resolve_windows_system_paths(g: guestfs.GuestFS) -> WindowsSystemPaths:
    win = _find_windows_root(g) or "/Windows"
    system32 = f"{win}/System32"
    cfg = f"{system32}/config"
    temp = f"{win}/Temp"
    return WindowsSystemPaths(
        windows_dir=win,
        system32_dir=system32,
        config_dir=cfg,
        temp_dir=temp,
        system_hive=f"{cfg}/SYSTEM",
    )


# guestfs hivex compatibility helpers (same approach as windows_virtio.py)


# pylint: disable=duplicate-code
# reason: mirrors virtio/detection.py's _hivex_call_known -- same multi-binding
# compatibility shim, but each raises a domain-specific error message for its
# own caller context, so kept independently editable.
def _hivex_call_known(
    g: guestfs.GuestFS,
    fn_name: str,
    args: tuple[Any, ...],
    *,
    allow_drop_handle: bool,
    allow_noargs: bool,
) -> Any:
    fn = getattr(g, fn_name, None)
    if fn is None:
        raise AttributeError(
            f"Windows registry access failed: guestfs method '{fn_name}' not found. "
            f"The guestfs backend may not have hivex support."
        )

    last_te: TypeError | None = None

    try:
        return fn(*args)
    except TypeError as te:
        last_te = te

    if allow_drop_handle and args and isinstance(args[0], int):
        try:
            return fn(*args[1:])
        except TypeError as te:
            last_te = te

    if allow_noargs:
        try:
            return fn()
        except TypeError as te:
            last_te = te

    if last_te is not None:
        raise last_te
    raise TypeError(
        f"Windows registry API call '{fn.__name__}' failed with all parameter variants. "
        f"This may indicate an incompatible libguestfs version."
    )


# pylint: enable=duplicate-code


def _hivex_open(g: guestfs.GuestFS, hive_path: str) -> int:
    try:
        return _hivex_call_known(
            g, "hivex_open", (hive_path, 0), allow_drop_handle=False, allow_noargs=False
        )
    except TypeError:
        return _hivex_call_known(g, "hivex_open", (hive_path,), allow_drop_handle=False, allow_noargs=False)


def _hivex_close(g: guestfs.GuestFS, h: int | None) -> None:
    try:
        if h is None:
            _hivex_call_known(g, "hivex_close", (), allow_drop_handle=False, allow_noargs=True)
        else:
            _hivex_call_known(g, "hivex_close", (h,), allow_drop_handle=True, allow_noargs=True)
    except Exception:  # pylint: disable=broad-exception-caught
        # Best-effort cleanup: hivex handle close failures vary by
        # libguestfs/hivex binding version and must never mask the real error.
        pass


def _node_get_child(g: guestfs.GuestFS, h: int, node: Any, name: str) -> Any:
    return _hivex_call_known(
        g, "hivex_node_get_child", (h, node, name), allow_drop_handle=True, allow_noargs=False
    )


def _node_children(g: guestfs.GuestFS, h: int, node: Any) -> list[Any]:
    try:
        kids = _hivex_call_known(
            g, "hivex_node_children", (h, node), allow_drop_handle=True, allow_noargs=False
        )
        return list(kids) if kids else []
    except Exception:  # pylint: disable=broad-exception-caught
        # Dynamic hivex binding call; failure means "no children readable",
        # which is a legitimate best-effort registry-walk outcome.
        return []


def _node_name(g: guestfs.GuestFS, h: int, node: Any) -> str | None:
    try:
        raw = _hivex_call_known(g, "hivex_node_name", (h, node), allow_drop_handle=True, allow_noargs=False)
        s = U.to_text(raw)
        return s if s else None
    except Exception:  # pylint: disable=broad-exception-caught
        # Dynamic hivex binding call; treat any failure as "name unavailable".
        return None


def _node_get_value(g: guestfs.GuestFS, h: int, node: Any, name: str) -> Any:
    return _hivex_call_known(
        g, "hivex_node_get_value", (h, node, name), allow_drop_handle=True, allow_noargs=False
    )


def _value_string(g: guestfs.GuestFS, h: int, v: Any) -> str | None:
    """
    hivex_value_string often returns:
      - plain string for REG_SZ
      - NUL-separated string-ish for REG_MULTI_SZ (varies by binding)
    """
    try:
        raw = _hivex_call_known(g, "hivex_value_string", (h, v), allow_drop_handle=True, allow_noargs=False)
        s = U.to_text(raw)
        return s if s is not None else None
    except Exception:  # pylint: disable=broad-exception-caught
        # Dynamic hivex binding call; treat any failure as "value unreadable".
        return None


def _value_dword(g: guestfs.GuestFS, h: int, v: Any) -> int | None:
    """
    guestfs exposes different hivex helpers depending on version.
    We attempt common patterns and fall back to parsing string-ish representations.
    """
    for fn_name in ("hivex_value_dword", "hivex_value_uint32", "hivex_value_integer"):
        fn = getattr(g, fn_name, None)
        if fn is None:
            continue
        try:
            out = _hivex_call_known(g, fn_name, (h, v), allow_drop_handle=True, allow_noargs=False)
            if isinstance(out, int):
                return out
        except Exception:  # pylint: disable=broad-exception-caught
            # Try the next dword-reading helper name; different libguestfs
            # versions expose different subsets of these hivex functions.
            continue
    s = _value_string(g, h, v)
    if not s:
        return None
    m = re.search(r"(\d+)", s)
    return int(m.group(1)) if m else None


def _read_sz(g: guestfs.GuestFS, h: int, node: Any, name: str) -> str | None:
    try:
        v = _node_get_value(g, h, node, name)
        if not v:
            return None
        s = _value_string(g, h, v)
        return s.strip() if s else None
    except Exception:  # pylint: disable=broad-exception-caught
        # Best-effort registry read; missing/malformed value -> None.
        return None


def _read_dword(g: guestfs.GuestFS, h: int, node: Any, name: str) -> int | None:
    try:
        v = _node_get_value(g, h, node, name)
        if not v:
            return None
        return _value_dword(g, h, v)
    except Exception:  # pylint: disable=broad-exception-caught
        # Best-effort registry read; missing/malformed value -> None.
        return None


# Parsing helpers


_IP_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")


def _split_multi_sz(s: str | None) -> list[str]:
    """
    Best-effort parse for REG_MULTI_SZ-like output:
      - may contain NULs
      - may contain commas/semicolons/spaces
    """
    if not s:
        return []
    # Normalize NUL separators to spaces, then split on common delimiters.
    t = s.replace("\x00", " ")
    parts = re.split(r"[, \s;]+", t)
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        out.append(p)
    return out


def _extract_ipv4_list(s: str | None) -> list[str]:
    if not s:
        return []
    # Fast path for NUL-separated multi-sz
    candidates = _split_multi_sz(s)
    ips: list[str] = []
    for c in candidates:
        m = _IP_RE.search(c)
        if m:
            ips.append(m.group(1))
    # Fallback: regex across raw string
    if not ips:
        ips = [m.group(1) for m in _IP_RE.finditer(s)]
    # Dedup preserve order using shared utility
    return dedup_preserve_order_str(ips)


def _first_non_apipa(ips: list[str]) -> str | None:
    for ip in ips:
        if ip.startswith("169.254."):
            continue
        return ip
    return ips[0] if ips else None


# Network snapshot extraction (SYSTEM hive)


def _get_controlset_path(g: guestfs.GuestFS, h: int, root: Any) -> str:
    """
    Determine the active ControlSet.

    We try:
      HKLM\\SYSTEM\\Select\\Current -> ControlSet00X
    fallback:
      ControlSet001
    """
    select = _node_get_child(g, h, root, "Select")
    if select:
        cur = _read_dword(g, h, select, "Current")
        if cur is not None and 0 <= cur <= 999:
            return f"ControlSet{cur:03d}"
    return "ControlSet001"


def _read_tcpip_interfaces_snapshot(g: guestfs.GuestFS, system_hive_path: str) -> dict[str, Any]:
    # pylint: disable=too-many-locals
    # Walks the Tcpip\Parameters\Interfaces hive subtree and collects many
    # independent per-interface registry values (DHCP flags, static IP/mask/
    # gateway/DNS, DHCP-derived values); each is its own local by design.
    """
    Extract a snapshot of TCP/IP config from:
      SYSTEM\\<ControlSet>\\Services\\Tcpip\\Parameters\\Interfaces\\{GUID}

    We keep it practical:
      - record EnableDHCP
      - record static-ish IPv4, mask, gateway, DNS (often multi-sz)
      - record DHCP-derived values (DhcpIPAddress, DhcpNameServer, etc.)
    """
    h: int | None = None
    try:
        h = _hivex_open(g, system_hive_path)
        root = _hivex_call_known(g, "hivex_root", (h,), allow_drop_handle=True, allow_noargs=True)

        controlset = _get_controlset_path(g, h, root)

        cs = _node_get_child(g, h, root, controlset)
        if not cs:
            return {"controlset": controlset, "interfaces": []}

        services = _node_get_child(g, h, cs, "Services")
        if not services:
            return {"controlset": controlset, "interfaces": []}

        tcpip = _node_get_child(g, h, services, "Tcpip")
        if not tcpip:
            return {"controlset": controlset, "interfaces": []}

        params = _node_get_child(g, h, tcpip, "Parameters")
        if not params:
            return {"controlset": controlset, "interfaces": []}

        interfaces = _node_get_child(g, h, params, "Interfaces")
        if not interfaces:
            return {"controlset": controlset, "interfaces": []}

        out: list[dict[str, Any]] = []
        for iface_node in _node_children(g, h, interfaces):
            guid = (_node_name(g, h, iface_node) or "").strip()
            if not guid:
                continue

            enable_dhcp = _read_dword(g, h, iface_node, "EnableDHCP")

            ip_raw = _read_sz(g, h, iface_node, "IPAddress")
            mask_raw = _read_sz(g, h, iface_node, "SubnetMask")
            gw_raw = _read_sz(g, h, iface_node, "DefaultGateway")
            dns_raw = _read_sz(g, h, iface_node, "NameServer")

            dhcp_ip_raw = _read_sz(g, h, iface_node, "DhcpIPAddress")
            dhcp_mask_raw = _read_sz(g, h, iface_node, "DhcpSubnetMask")
            dhcp_gw_raw = _read_sz(g, h, iface_node, "DhcpDefaultGateway")
            dhcp_dns_raw = _read_sz(g, h, iface_node, "DhcpNameServer")

            profile = _read_sz(g, h, iface_node, "ProfileName")
            domain = _read_sz(g, h, iface_node, "Domain")
            dhcp_domain = _read_sz(g, h, iface_node, "DhcpDomain")

            ip_list = _extract_ipv4_list(ip_raw)
            mask_list = _extract_ipv4_list(mask_raw)
            gw_list = _extract_ipv4_list(gw_raw)
            dns_list = _extract_ipv4_list(dns_raw)

            dhcp_ip_list = _extract_ipv4_list(dhcp_ip_raw)
            dhcp_mask_list = _extract_ipv4_list(dhcp_mask_raw)
            dhcp_gw_list = _extract_ipv4_list(dhcp_gw_raw)
            dhcp_dns_list = _extract_ipv4_list(dhcp_dns_raw)

            out.append(
                {
                    "guid": guid,
                    "enable_dhcp": enable_dhcp,
                    "static": {
                        "ip_raw": ip_raw,
                        "mask_raw": mask_raw,
                        "gateway_raw": gw_raw,
                        "dns_raw": dns_raw,
                        "ips": ip_list,
                        "masks": mask_list,
                        "gateways": gw_list,
                        "dns_servers": dns_list,
                        "ip": _first_non_apipa(ip_list),
                        "mask": mask_list[0] if mask_list else None,
                        "gateway": _first_non_apipa(gw_list),
                        "dns": ", ".join(dns_list) if dns_list else None,
                    },
                    "dhcp": {
                        "ip_raw": dhcp_ip_raw,
                        "mask_raw": dhcp_mask_raw,
                        "gateway_raw": dhcp_gw_raw,
                        "dns_raw": dhcp_dns_raw,
                        "ips": dhcp_ip_list,
                        "masks": dhcp_mask_list,
                        "gateways": dhcp_gw_list,
                        "dns_servers": dhcp_dns_list,
                        "ip": _first_non_apipa(dhcp_ip_list),
                        "mask": dhcp_mask_list[0] if dhcp_mask_list else None,
                        "gateway": _first_non_apipa(dhcp_gw_list),
                        "dns": ", ".join(dhcp_dns_list) if dhcp_dns_list else None,
                    },
                    "meta": {
                        "profile": profile,
                        "domain": domain,
                        "dhcp_domain": dhcp_domain,
                    },
                }
            )

        return {"controlset": controlset, "interfaces": out}
    finally:
        _hivex_close(g, h)


def _score_iface_snapshot(x: dict[str, Any]) -> int:
    """
    Pick the "most useful" config to apply on first boot.

    Prefer:
      - static config with IP/mask
      - otherwise DHCP config with DhcpIPAddress (some environments still want to preserve DNS/domain)
    """
    score = 0
    static = x.get("static") or {}
    dhcp = x.get("dhcp") or {}
    enable_dhcp = x.get("enable_dhcp")

    if static.get("ip") and static.get("mask"):
        score += 50
        if static.get("gateway"):
            score += 10
        if static.get("dns_servers"):
            score += 10
        if enable_dhcp == 0:
            score += 10

    if dhcp.get("ip"):
        score += 20
        if dhcp.get("dns_servers"):
            score += 5

    meta = x.get("meta") or {}
    if meta.get("profile"):
        score += 2

    return score


def _choose_best_network_payload(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    ifaces = snapshot.get("interfaces") or []
    if not isinstance(ifaces, list) or not ifaces:
        return None
    ranked = sorted(ifaces, key=_score_iface_snapshot, reverse=True)
    best = ranked[0] if ranked else None
    if not best:
        return None

    enable_dhcp = best.get("enable_dhcp")
    static = best.get("static") or {}
    dhcp = best.get("dhcp") or {}
    meta = best.get("meta") or {}

    static_ok = bool(static.get("ip") and static.get("mask") and enable_dhcp == 0)

    # Collect all static IPs for multi-IP support (enterprise VMs often have
    # multiple IPs bound to a single NIC for services, clustering, etc.)
    all_ips = static.get("ips") or []
    all_masks = static.get("masks") or []
    complementary_ips: list[dict[str, str]] = []
    if static_ok and len(all_ips) > 1:
        for i in range(1, len(all_ips)):
            ip = all_ips[i]
            if ip.startswith("169.254."):
                continue  # skip APIPA
            mask = all_masks[i] if i < len(all_masks) else (all_masks[0] if all_masks else "255.255.255.0")
            complementary_ips.append({"ip": ip, "mask": mask})

    return {
        "schema": 1,
        "source_guid": best.get("guid"),
        "mode": "static" if static_ok else "dhcp",
        "static": {
            "ip": static.get("ip"),
            "mask": static.get("mask"),
            "gateway": static.get("gateway"),
            "dns_servers": static.get("dns_servers") or [],
        },
        "complementary_ips": complementary_ips,
        "dhcp": {
            "dns_servers": dhcp.get("dns_servers") or [],
            "domain": meta.get("dhcp_domain") or meta.get("domain"),
        },
        "meta": {
            "profile": meta.get("profile"),
            "multiple_ips": len(complementary_ips) > 0,
            "total_ips": 1 + len(complementary_ips) if static_ok else 0,
            "note": "Best-effort snapshot from SYSTEM\\...\\Tcpip\\Parameters\\Interfaces",
        },
    }


# Override loading/staging


def _normalize_override(obj: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize override payload:
      - schema default
      - mode lower
      - adapter.mac normalized
      - dns_servers may be string or list -> list[str]
    """
    o: dict[str, Any] = dict(obj)
    if "schema" not in o:
        o["schema"] = 1
    if "mode" in o and isinstance(o["mode"], str):
        o["mode"] = o["mode"].strip().lower()

    adapter = o.get("adapter")
    if isinstance(adapter, dict):
        mac = adapter.get("mac")
        if isinstance(mac, str) and mac.strip():
            # normalize separators to '-' and uppercase (PowerShell will normalize again)
            m = mac.strip().replace(":", "-").replace(".", "-").upper()
            adapter["mac"] = m

    def _dns_list(v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str):
            return [x.strip() for x in re.split(r"[, \s;]+", v) if x.strip()]
        return []

    st = o.get("static")
    if isinstance(st, dict) and "dns_servers" in st:
        st["dns_servers"] = _dns_list(st.get("dns_servers"))

    dh = o.get("dhcp")
    if isinstance(dh, dict) and "dns_servers" in dh:
        dh["dns_servers"] = _dns_list(dh.get("dns_servers"))

    return o


def _load_windows_network_override(self) -> dict[str, Any] | None:
    """
    Load override from:
      - self.windows_network_config (dict)
      - self.windows_network_config_path (JSON file)
    """
    logger = _safe_logger(self)

    cfg_obj = getattr(self, "windows_network_config", None)
    if isinstance(cfg_obj, dict) and cfg_obj:
        _log(logger, logging.INFO, "Loaded Windows network override from self.windows_network_config (dict)")
        return _normalize_override(cfg_obj)

    p = getattr(self, "windows_network_config_path", None)
    if p:
        try:
            jp = Path(str(p))
            if jp.exists() and jp.is_file():
                parsed = json.loads(jp.read_text(encoding="utf-8"))
                if isinstance(parsed, dict) and parsed:
                    _log(logger, logging.INFO, "Loaded Windows network override: %s", jp)
                    return _normalize_override(parsed)
        except (OSError, ValueError) as e:
            _log(logger, logging.WARNING, "Windows network override load failed (%s): %s", p, e)

    return None


# Firstboot PowerShell payload


def _build_apply_network_ps1() -> str:
    """
    PowerShell script (runs in Windows) that applies either:
      1) network_override.json (if present)
      2) saved_network.json -> best

    Adapter selection:
      - If override.adapter.mac present: select adapter with matching MAC.
      - Else if override.adapter.name present: select by Name.
      - Else: prefer an "Up" physical adapter, else first adapter.

    Behavior:
      - Static:
          * Clear IPv4 addresses on chosen adapter (best-effort)
          * Set New-NetIPAddress with prefix, optional gateway
          * Set DNS servers if provided
      - DHCP:
          * Enable DHCP
          * Optionally set DNS servers (override DNS)
    """
    return r"""
$ErrorActionPreference = "Continue"

function Log($msg) {
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Add-Content -Path $LogPath -Value "$ts $msg"
}

function NormalizeMac($mac) {
  if (-not $mac) { return $null }
  $m = $mac.ToString().Trim().ToUpper()
  $m = $m -replace "[:\.]", "-"
  return $m
}

function MaskToPrefix($mask) {
  if (-not $mask) { return 24 }
  try {
    $parts = $mask.Split(".")
    if ($parts.Count -ne 4) { return 24 }
    $bits = 0
    foreach ($p in $parts) {
      $n = [int]$p
      for ($i=7; $i -ge 0; $i--) {
        if (($n -band (1 -shl $i)) -ne 0) { $bits++ }
      }
    }
    return $bits
  } catch {
    return 24
  }
}

function ReadJson($path) {
  if (-not (Test-Path $path)) { return $null }
  try {
    return (Get-Content -Raw -Path $path | ConvertFrom-Json)
  } catch {
    Log "Failed to parse JSON at $path : $($_.Exception.Message)"
    return $null
  }
}

$BaseDir = "C:\h2kvm\net"
$SavedPath = Join-Path $BaseDir "saved_network.json"
$OverridePath = Join-Path $BaseDir "network_override.json"
$LogPath = Join-Path $BaseDir "apply-network.log"

New-Item -ItemType Directory -Force -Path $BaseDir | Out-Null
Log "=== h2kvm network apply starting ==="
Log "SavedPath=$SavedPath OverridePath=$OverridePath"

$override = ReadJson $OverridePath
$saved = ReadJson $SavedPath

# Choose payload: override first, else saved.best, else nothing
$cfg = $null
if ($override) {
  $cfg = $override
  Log "Using override payload."
} elseif ($saved -and $saved.best) {
  $cfg = $saved.best
  Log "Using saved snapshot best payload."
} else {
  Log "No override and no saved best payload. Nothing to do."
  exit 0
}

# Collect adapters (NetTCPIP module should exist on normal Windows)
$adapters = Get-NetAdapter -Physical -ErrorAction SilentlyContinue
if (-not $adapters) {
  $adapters = Get-NetAdapter -ErrorAction SilentlyContinue
}
if (-not $adapters) {
  Log "No adapters found."
  exit 0
}

# Adapter selection
$target = $null
try {
  $wantMac = $null
  $wantName = $null
  if ($cfg.adapter) {
    $wantMac = NormalizeMac $cfg.adapter.mac
    $wantName = $cfg.adapter.name
  }

  if ($wantMac) {
    Log "Selecting adapter by MAC=$wantMac"
    $target = $adapters | Where-Object { (NormalizeMac $_.MacAddress) -eq $wantMac } | Select-Object -First 1
  }
  if (-not $target -and $wantName) {
    Log "Selecting adapter by Name=$wantName"
    $target = $adapters | Where-Object { $_.Name -eq $wantName } | Select-Object -First 1
  }
} catch {
  Log "Adapter selection exception: $($_.Exception.Message)"
}

# Default selection: prefer Up physical-ish adapter; avoid obvious virtual switch names
if (-not $target) {
  $target = $adapters | Where-Object { $_.Status -eq "Up" -and $_.Name -notmatch "vEthernet|Hyper-V|Loopback|Virtual" } | Select-Object -First 1
}
if (-not $target) {
  $target = $adapters | Where-Object { $_.Status -eq "Up" } | Select-Object -First 1
}
if (-not $target) {
  $target = $adapters | Select-Object -First 1
}

Log ("Selected adapter: Name={0} IfIndex={1} Status={2} Mac={3}" -f $target.Name, $target.ifIndex, $target.Status, $target.MacAddress)

# Normalize mode
$mode = $cfg.mode
if (-not $mode) { $mode = "dhcp" }
$mode = $mode.ToString().Trim().ToLower()
Log "Mode=$mode"

try {
  if ($mode -eq "static") {
    $ip = $cfg.static.ip
    $mask = $cfg.static.mask
    $gw = $cfg.static.gateway
    $dns = $cfg.static.dns_servers

    if (-not $ip -or -not $mask) {
      Log "Static requested but missing ip/mask. Falling back to DHCP."
      $mode = "dhcp"
    } else {
      $prefix = MaskToPrefix $mask
      Log ("Applying static IP={0}/{1} GW={2} DNS={3}" -f $ip, $prefix, $gw, ($dns -join ","))

      # Clear existing IPv4 addresses on that interface (best-effort)
      Get-NetIPAddress -InterfaceIndex $target.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | ForEach-Object {
        try {
          if ($_.IPAddress -and ($_.IPAddress -ne $ip)) {
            Remove-NetIPAddress -InterfaceIndex $target.ifIndex -IPAddress $_.IPAddress -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
          }
        } catch {}
      }

      # Apply IP (+ optional GW)
      if ($gw) {
        New-NetIPAddress -InterfaceIndex $target.ifIndex -IPAddress $ip -PrefixLength $prefix -DefaultGateway $gw -ErrorAction SilentlyContinue | Out-Null
      } else {
        New-NetIPAddress -InterfaceIndex $target.ifIndex -IPAddress $ip -PrefixLength $prefix -ErrorAction SilentlyContinue | Out-Null
      }

      # DNS
      if ($dns) {
        $dnsList = @()
        foreach ($d in $dns) {
          if ($d -and $d.ToString().Trim().Length -gt 0) { $dnsList += $d.ToString().Trim() }
        }
        if ($dnsList.Count -gt 0) {
          Set-DnsClientServerAddress -InterfaceIndex $target.ifIndex -ServerAddresses $dnsList -ErrorAction SilentlyContinue | Out-Null
        }
      }

      # Apply complementary (secondary) IPs if present
      $compIps = $cfg.complementary_ips
      if ($compIps -and $compIps.Count -gt 0) {
        Log ("Applying {0} complementary IP(s)" -f $compIps.Count)
        foreach ($comp in $compIps) {
          $cip = $comp.ip
          $cmask = $comp.mask
          if ($cip) {
            $cprefix = MaskToPrefix $cmask
            try {
              New-NetIPAddress -InterfaceIndex $target.ifIndex -IPAddress $cip -PrefixLength $cprefix `
                -SkipAsSource $true -ErrorAction SilentlyContinue | Out-Null
              Log ("  Added complementary IP={0}/{1}" -f $cip, $cprefix)
            } catch {
              Log ("  Failed to add complementary IP={0}: {1}" -f $cip, $_.Exception.Message)
            }
          }
        }
      }

      Log "Static configuration applied."
      exit 0
    }
  }

  if ($mode -eq "dhcp") {
    Log "Enabling DHCP on adapter..."
    Set-NetIPInterface -InterfaceIndex $target.ifIndex -Dhcp Enabled -AddressFamily IPv4 -ErrorAction SilentlyContinue | Out-Null

    $dhcpDns = $null
    if ($cfg.dhcp) { $dhcpDns = $cfg.dhcp.dns_servers }
    if ($dhcpDns) {
      $dnsList = @()
      foreach ($d in $dhcpDns) {
        if ($d -and $d.ToString().Trim().Length -gt 0) { $dnsList += $d.ToString().Trim() }
      }
      if ($dnsList.Count -gt 0) {
        Log ("Setting DNS servers (DHCP mode override): {0}" -f ($dnsList -join ","))
        Set-DnsClientServerAddress -InterfaceIndex $target.ifIndex -ServerAddresses $dnsList -ErrorAction SilentlyContinue | Out-Null
      }
    }

    Log "DHCP enabled."
    exit 0
  }

  Log "Unknown mode=$mode. Nothing done."
  exit 0

} catch {
  Log "Exception applying network: $($_.Exception.Message)"
  exit 0
}
""".lstrip()


# Public API


def retain_windows_network_config(self, g: guestfs.GuestFS) -> dict[str, Any]:
    # pylint: disable=too-many-locals,too-many-statements
    # Top-level public entry point for this fixer: sequences hive-presence
    # check, snapshot capture, optional override load, payload staging, and
    # firstboot provisioning, each step with its own result/path locals -
    # splitting it would fragment one linear best-effort pipeline.
    """
    Capture network configuration snapshot and provision a firstboot action to re-apply it.

    Attributes consumed from `self`:
      - dry_run: bool
      - logger: optional
      - windows_network_config: dict (optional override)
      - windows_network_config_path: str|Path (optional override)
    """
    logger = _safe_logger(self)
    dry_run = bool(getattr(self, "dry_run", False))

    result: dict[str, Any] = {
        "windows": True,
        "dry_run": dry_run,
        "captured": False,
        "provisioned": False,
        "paths": {},
        "snapshot": {},
        "best": None,
        "override": None,
        "artifacts": [],
        "warnings": [],
        "notes": [],
    }

    with _step(logger, "🧭 Ensure Windows system volume mounted (C: -> /)"):
        _ensure_windows_root(logger, g, hint_hive_path="/Windows/System32/config/SYSTEM")

    paths = _resolve_windows_system_paths(g)
    result["paths"] = {
        "windows_dir": paths.windows_dir,
        "system_hive": paths.system_hive,
        "temp_dir": paths.temp_dir,
    }

    try:
        if not g.is_file(paths.system_hive):
            return {
                **result,
                "captured": False,
                "reason": "system_hive_missing",
                "system_hive": paths.system_hive,
            }
    except Exception:  # pylint: disable=broad-exception-caught
        # guestfs.is_file() can raise a variety of backend errors depending on
        # mount/hive state; this is a best-effort capability check that must
        # degrade to "not captured" rather than abort the whole migration.
        return {
            **result,
            "captured": False,
            "reason": "system_hive_stat_failed",
            "system_hive": paths.system_hive,
        }

    # 1) Snapshot extraction
    with _step(logger, "📡 Capture TCP/IP config snapshot (SYSTEM hive)"):
        try:
            snap = _read_tcpip_interfaces_snapshot(g, paths.system_hive)
            result["snapshot"] = snap
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Registry/hivex snapshot extraction is best-effort; any failure
            # must degrade gracefully to "not captured" instead of aborting
            # the migration over one guest's registry quirks.
            msg = f"Network snapshot failed: {e}"
            result["warnings"].append(msg)
            _log(logger, logging.WARNING, "%s", msg)
            return {**result, "captured": False, "reason": "snapshot_failed", "error": str(e)}

    best = _choose_best_network_payload(result["snapshot"])
    if not best:
        result["notes"].append("No usable TCP/IP interface config found; skipping retention provisioning.")
        return {**result, "captured": False, "reason": "no_usable_config"}

    result["best"] = best
    result["captured"] = True

    # 2) Load optional override (host-side)
    override = _load_windows_network_override(self)
    if override:
        result["override"] = override

    # 3) Stage payload + PS script
    base_dir = "/h2kvm/net"
    saved_path = f"{base_dir}/saved_network.json"
    override_path = f"{base_dir}/network_override.json"
    ps1_path = f"{base_dir}/apply-network.ps1"
    log_path = f"{base_dir}/apply-network.log"

    saved_payload = {
        "schema": 1,
        "snapshot": result["snapshot"],
        "best": best,
    }

    try:
        with _step(logger, "🧾 Stage network payload + PowerShell apply script"):
            _guest_mkdir_p(g, "/h2kvm", dry_run=dry_run)
            _guest_mkdir_p(g, base_dir, dry_run=dry_run)
            _guest_write_text(
                g, saved_path, json.dumps(saved_payload, indent=2, default=str), dry_run=dry_run
            )
            _guest_write_text(g, ps1_path, _build_apply_network_ps1(), dry_run=dry_run)
            if override:
                _guest_write_text(
                    g, override_path, json.dumps(override, indent=2, default=str), dry_run=dry_run
                )

        result["artifacts"].append(
            {
                "kind": "saved_network_json",
                "dst": saved_path,
                "action": "written" if not dry_run else "dry_run",
            }
        )
        result["artifacts"].append(
            {"kind": "apply_network_ps1", "dst": ps1_path, "action": "written" if not dry_run else "dry_run"}
        )
        if override:
            result["artifacts"].append(
                {
                    "kind": "network_override_json",
                    "dst": override_path,
                    "action": "written" if not dry_run else "dry_run",
                }
            )
        result["artifacts"].append(
            {"kind": "apply_network_log", "dst": log_path, "note": "created at runtime"}
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        # Guest filesystem write helpers can raise a variety of guestfs
        # backend errors; staging is best-effort and must not abort the
        # migration, only skip network-retention provisioning.
        msg = f"Staging network payload failed: {e}"
        result["warnings"].append(msg)
        _log(logger, logging.WARNING, "%s", msg)
        return {**result, "reason": "staging_failed", "error": str(e)}

    # 4) Provision firstboot: run PS
    extra_cmd = (
        r'powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\h2kvm\net\apply-network.ps1"'
    )
    with _step(logger, "🛠️ Provision firstboot hook for network apply"):
        try:
            fb = provision_firstboot_payload_and_service(
                self,
                g,
                system_hive_path=paths.system_hive,
                service_name="h2kvm-net-firstboot",
                guest_dir="/h2kvm",
                log_path=f"{paths.temp_dir}/h2kvm-net-firstboot.log",
                driver_stage_dir="/h2kvm/drivers/virtio",  # may or may not exist; framework tolerates
                extra_cmd=extra_cmd,
                remove_vmware_tools=False,
            )
            result["firstboot"] = fb
            result["provisioned"] = bool(fb.get("success", True))
            if not result["provisioned"]:
                msg = f"Firstboot provisioning reported errors: {fb.get('errors')}"
                result["warnings"].append(msg)
                _log(logger, logging.WARNING, "%s", msg)
        except Exception as e:  # pylint: disable=broad-exception-caught
            # provision_firstboot_payload_and_service() covers a wide range of
            # guest registry/service-install operations; any failure here must
            # degrade to "not provisioned" rather than abort the migration.
            msg = f"Firstboot provisioning exception: {e}"
            result["warnings"].append(msg)
            _log(logger, logging.WARNING, "%s", msg)
            result["provisioned"] = False

    result["notes"] += [
        "Windows NIC identity changes across hypervisors; offline GUID mapping is unreliable.",
        "This fixer snapshots TCP/IP config from SYSTEM hive and reapplies it at first boot via PowerShell.",
        r"Artifacts: C:\h2kvm\net\saved_network.json, C:\h2kvm\net\apply-network.ps1",
        r"Optional override: C:\h2kvm\net\network_override.json (if provided via windows_network_config[_path])",
        r"Log (inside Windows): C:\h2kvm\net\apply-network.log",
        "Best results when you preserve the original NIC MAC in the libvirt XML (Windows tends to behave better).",
    ]

    _log(
        logger,
        logging.INFO,
        "Network retention staged: saved=%s override=%s ps1=%s log=%s",
        _guestfs_to_windows_path(saved_path),
        _guestfs_to_windows_path(override_path) if override else "(none)",
        _guestfs_to_windows_path(ps1_path),
        _guestfs_to_windows_path(log_path),
    )

    return result


__all__ = ["retain_windows_network_config"]
