# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/windows/virtio/config.py
"""Configuration and validation for Windows VirtIO driver injection"""

from __future__ import annotations

import json
import logging
import re
from enum import Enum
from pathlib import Path
from typing import Any

from h2kvm.config.config_loader import YAML_AVAILABLE, yaml

from .windows_virtio_utils import _deep_merge_dict, _log, _safe_logger

# Windows Constants & Enums


class DriverType(Enum):
    """Category of VirtIO driver being injected into the Windows guest."""

    STORAGE = "storage"
    NETWORK = "network"
    BALLOON = "balloon"
    INPUT = "input"
    GPU = "gpu"
    FILESYSTEM = "filesystem"
    SERIAL = "serial"
    RNG = "rng"


class WindowsRelease(Enum):
    """
    Windows release family (NOT edition like Pro/Home/Enterprise).

    Why: "Edition" is ambiguous terminology in Windows land.
    This enum describes the OS generation / release line.
    """

    SERVER_2022 = "server_2022"
    SERVER_2019 = "server_2019"
    SERVER_2016 = "server_2016"
    SERVER_2012 = "server_2012"
    SERVER_2008 = "server_2008"
    WINDOWS_12 = "windows_12"  # heuristic/future bucket; best-effort only
    WINDOWS_11 = "windows_11"
    WINDOWS_10 = "windows_10"
    WINDOWS_8_1 = "windows_8_1"
    WINDOWS_8 = "windows_8"
    WINDOWS_7 = "windows_7"
    WINDOWS_VISTA = "vista"
    WINDOWS_XP = "xp"
    UNKNOWN = "unknown"


class DriverStartType(Enum):
    """Windows service Start value for a driver (registry ``Start`` REG_DWORD)."""

    BOOT = 0
    SYSTEM = 1
    AUTO = 2
    MANUAL = 3
    DISABLED = 4


# Legacy Windows releases that lack SHA-2 code signing support.
# Drivers for these OSes must be SHA-1 signed (or unsigned with test-signing).
# See: https://support.microsoft.com/en-us/topic/sha-2-code-signing-support
LEGACY_WINDOWS_RELEASES = frozenset(
    {
        WindowsRelease.WINDOWS_XP,
        WindowsRelease.WINDOWS_VISTA,
        WindowsRelease.WINDOWS_7,
        WindowsRelease.SERVER_2008,
    }
)


def is_legacy_windows(release: WindowsRelease) -> bool:
    """
    Check if a Windows release requires SHA-1/legacy signed drivers.

    Windows XP, Vista, 7, and Server 2008 do not support SHA-2
    code signing by default (KB3033929 adds it to Win7/2008R2 but
    may not be installed). Drivers for these OSes must use the
    legacy/SHA-1 signed packages from virtio-win.

    Args:
        release: Windows release enum value

    Returns:
        True if the release needs legacy (SHA-1) drivers
    """
    return release in LEGACY_WINDOWS_RELEASES


# Config (drivers + OS->bucket mapping)

DEFAULT_VIRTIO_CONFIG: dict[str, Any] = {
    # Default is Windows 11, not Windows 10.
    "default_release": "windows_11",
    "default_arch_dir": "amd64",
    # Release -> canonical bucket hint
    "release_to_bucket": {
        "windows_12": "w12",
        "windows_11": "w11",
        "windows_10": "w10",
        "windows_8_1": "w8",
        "windows_8": "w8",
        "windows_7": "w7",
        "vista": "vista",
        "xp": "xp",
        "server_2022": "w11",
        "server_2019": "w10",
        "server_2016": "w10",
        "server_2012": "w8",
        "server_2008": "w7",
        "unknown": "w11",
    },
    # Release -> bucket candidates (fallback order)
    "bucket_candidates": {
        "windows_12": ["w12", "w11", "w10", "w8", "w7"],
        "windows_11": ["w11", "w10", "w8", "w7"],
        "windows_10": ["w10", "w11", "w8", "w7"],
        "windows_8_1": ["w8", "w10", "w7"],
        "windows_8": ["w8", "w10", "w7"],
        "windows_7": ["w7", "w8", "w10"],
        "vista": ["vista", "w7", "w8"],
        "xp": ["xp", "w7"],
        "server_2022": ["w11", "w10", "w8", "w7"],
        "server_2019": ["w10", "w11", "w8", "w7"],
        "server_2016": ["w10", "w11", "w8", "w7"],
        "server_2012": ["w8", "w10", "w7"],
        "server_2008": ["w7", "w8", "w10"],
        "unknown": ["w11", "w10", "w8", "w7"],
    },
    # Driver definitions live in config (extensible per vendor / custom PNP IDs).
    "drivers": {
        "storage": [
            {
                "name": "viostor",
                "pattern": "viostor/{bucket}/{arch}/viostor.sys",
                "inf_hint": "viostor.inf",
                "service": "viostor",
                "start": 0,  # BOOT
                "class_guid": "{4D36E967-E325-11CE-BFC1-08002BE10318}",  # SCSIAdapter
                "pci_ids": [
                    "pci#ven_1af4&dev_1001&subsys_00081af4",
                    "pci#ven_1af4&dev_1042&subsys_00081af4",
                ],
            },
            {
                "name": "vioscsi",
                "pattern": "vioscsi/{bucket}/{arch}/vioscsi.sys",
                "inf_hint": "vioscsi.inf",
                "service": "vioscsi",
                "start": 0,  # BOOT
                "class_guid": "{4D36E967-E325-11CE-BFC1-08002BE10318}",  # SCSIAdapter
                "pci_ids": [
                    "pci#ven_1af4&dev_1004&subsys_00081af4",
                    "pci#ven_1af4&dev_1048&subsys_00081af4",
                ],
            },
        ],
        "network": [
            {
                "name": "NetKVM",
                "pattern": "NetKVM/{bucket}/{arch}/netkvm.sys",
                "inf_hint": "netkvm.inf",
                "service": "netkvm",
                "start": 2,  # AUTO
                "class_guid": "{4D36E972-E325-11CE-BFC1-08002BE10318}",  # Net
                "pci_ids": [
                    "pci#ven_1af4&dev_1000&subsys_00081af4",
                    "pci#ven_1af4&dev_1041&subsys_00081af4",
                ],
            },
        ],
        "balloon": [
            {
                "name": "Balloon",
                "pattern": "Balloon/{bucket}/{arch}/balloon.sys",
                "inf_hint": "balloon.inf",
                "service": "balloon",
                "start": 2,  # AUTO
                "class_guid": "{4D36E97D-E325-11CE-BFC1-08002BE10318}",  # System
                "pci_ids": [
                    "pci#ven_1af4&dev_1002&subsys_00051af4",
                    "pci#ven_1af4&dev_1045&subsys_00051af4",
                ],
            },
        ],
        "gpu": [
            {
                "name": "viogpudo",
                "pattern": "viogpudo/{bucket}/{arch}/viogpudo.sys",
                "inf_hint": "viogpudo.inf",
                "service": "viogpudo",
                "start": 3,  # MANUAL
                "class_guid": "{4D36E968-E325-11CE-BFC1-08002BE10318}",  # Display
                "pci_ids": ["pci#ven_1af4&dev_1050&subsys_11001af4"],
            },
        ],
        "input": [
            {
                "name": "vioinput",
                "pattern": "vioinput/{bucket}/{arch}/vioinput.sys",
                "inf_hint": "vioinput.inf",
                "service": "vioinput",
                "start": 3,  # MANUAL
                "class_guid": "{4D36E96F-E325-11CE-BFC1-08002BE10318}",  # Mouse
                "pci_ids": ["pci#ven_1af4&dev_1052&subsys_11001af4"],
            },
        ],
        "filesystem": [
            {
                "name": "virtiofs",
                "pattern": "virtiofs/{bucket}/{arch}/virtiofs.sys",
                "inf_hint": "virtiofs.inf",
                "service": "virtiofs",
                "start": 1,  # SYSTEM
                "class_guid": "{4D36E967-E325-11CE-BFC1-08002BE10318}",  # Storage-ish
                "pci_ids": ["pci#ven_1af4&dev_105a&subsys_11001af4"],
            },
        ],
        "serial": [
            {
                "name": "vioser",
                "pattern": "vioser/{bucket}/{arch}/vioser.sys",
                "inf_hint": "vioser.inf",
                "service": "vioser",
                "start": 3,  # MANUAL
                "class_guid": "{4D36E978-E325-11CE-BFC1-08002BE10318}",  # Ports
                "pci_ids": [
                    "pci#ven_1af4&dev_1003&subsys_00031af4",
                    "pci#ven_1af4&dev_1043&subsys_00031af4",
                ],
            },
        ],
        "rng": [
            {
                "name": "viorng",
                "pattern": "viorng/{bucket}/{arch}/viorng.sys",
                "inf_hint": "viorng.inf",
                "service": "viorng",
                "start": 2,  # AUTO
                "class_guid": "{4D36E97D-E325-11CE-BFC1-08002BE10318}",  # System
                "pci_ids": [
                    "pci#ven_1af4&dev_1005&subsys_00041af4",
                    "pci#ven_1af4&dev_1044&subsys_00041af4",
                ],
            },
        ],
    },
}


def _parse_start_type(v: Any) -> int:
    if isinstance(v, int):
        return v if 0 <= v <= 4 else DriverStartType.AUTO.value
    if isinstance(v, str):
        s = v.strip()
        if re.fullmatch(r"\d+", s):
            n = int(s)
            return n if 0 <= n <= 4 else DriverStartType.AUTO.value
        s2 = s.upper()
        try:
            return DriverStartType[s2].value
        except KeyError:
            return DriverStartType.AUTO.value
    return DriverStartType.AUTO.value


def _validate_virtio_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize + validate config.

    - Ensures drivers are lists of dicts with required keys
    - Normalizes pci_ids to lowercase strings
    - Normalizes start to int (0..4) or enum-name
    - Keeps class_guid/inf_hint as strings (inf_hint may be None)

    Lists are NOT merged; if user overrides drivers.storage, they replace that list.
    """
    d = cfg.get("drivers")
    if isinstance(d, dict):
        for dtype, defs in list(d.items()):
            if not isinstance(defs, list):
                d.pop(dtype, None)
                continue

            cleaned: list[dict[str, Any]] = []
            for item in defs:
                if not isinstance(item, dict):
                    continue

                name = str(item.get("name") or "").strip()
                pattern = str(item.get("pattern") or "").strip()
                service = str(item.get("service") or "").strip()
                if not (name and pattern and service):
                    continue

                pci_ids = item.get("pci_ids") or []
                if not isinstance(pci_ids, list):
                    pci_ids = []
                pci_ids = [str(x).strip().lower() for x in pci_ids if str(x).strip()]

                start_val = _parse_start_type(item.get("start", DriverStartType.AUTO.value))

                cleaned.append(
                    {
                        **item,
                        "name": name,
                        "pattern": pattern,
                        "service": service,
                        "pci_ids": pci_ids,
                        "start": start_val,
                        "class_guid": str(item.get("class_guid") or "").strip(),
                        "inf_hint": (str(item.get("inf_hint") or "").strip() or None),
                    }
                )

            d[dtype] = cleaned

    return cfg


def _read_structured_file(path: Path) -> dict[str, Any]:
    """
    Read a JSON/YAML file into a dict.

    Supported:
      - *.json
      - *.yml / *.yaml (requires YAML_AVAILABLE)
    """
    sfx = path.suffix.lower()
    raw = path.read_text(encoding="utf-8", errors="replace")
    if sfx == ".json":
        parsed = json.loads(raw)
    elif sfx in (".yml", ".yaml"):
        if not YAML_AVAILABLE:
            raise RuntimeError("YAML support not available (PyYAML not installed). Use JSON instead.")
        parsed = yaml.safe_load(raw)  # type: ignore[attr-defined]
    else:
        # Try JSON first, then YAML if available (nice UX for no-suffix files)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            if not YAML_AVAILABLE:
                raise
            parsed = yaml.safe_load(raw)  # type: ignore[attr-defined]
    if not isinstance(parsed, dict):
        raise TypeError("top-level config must be a mapping/object (dict)")
    return parsed


def _extract_virtio_cfg_from_global_config(global_cfg: Any) -> dict[str, Any] | None:
    """
    Accept VirtIO config from the *merged app config* if present.

    We support several keys so you can evolve without breaking users:
      - windows_virtio:
      - virtio_windows:
      - virtio:
      - fixers: { windows_virtio: { ... } }
    """
    if not isinstance(global_cfg, dict) or not global_cfg:
        return None

    for k in ("windows_virtio", "virtio_windows", "virtio"):
        v = global_cfg.get(k)
        if isinstance(v, dict) and v:
            return v

    fx = global_cfg.get("fixers")
    if isinstance(fx, dict):
        v = fx.get("windows_virtio")
        if isinstance(v, dict) and v:
            return v

    return None


def _load_virtio_config(self) -> dict[str, Any]:
    """
    Load VirtIO config (drivers + OS bucket logic) from **any** of:

    1) self.virtio_config (dict) [highest priority]
    2) self.virtio_config_inline_json (str JSON) (or self.virtio_config_json for compat)
    3) self.virtio_config_path (Path|str) JSON/YAML file
    4) self.config (merged YAML app config dict) keys: windows_virtio/virtio/fixers.windows_virtio
    5) baked DEFAULT_VIRTIO_CONFIG

    Merge semantics:
      - dicts deep-merge
      - lists replaced (so overriding drivers.storage replaces storage list only)
    """
    logger = _safe_logger(self)

    cfg: dict[str, Any] = dict(DEFAULT_VIRTIO_CONFIG)

    # 1) explicit dict on object
    cfg_obj = getattr(self, "virtio_config", None)
    if isinstance(cfg_obj, dict) and cfg_obj:
        cfg = _deep_merge_dict(cfg, cfg_obj)
        cfg = _validate_virtio_config(cfg)
        _log(logger, logging.INFO, "Loaded VirtIO config from self.virtio_config (dict)")
        return cfg

    # 2) inline JSON string on object (CLI/YAML can map into this)
    inline = getattr(self, "virtio_config_inline_json", None)
    if not inline:
        inline = getattr(self, "virtio_config_json", None)
    if isinstance(inline, str) and inline.strip():
        try:
            parsed = json.loads(inline)
            if isinstance(parsed, dict):
                cfg = _deep_merge_dict(cfg, parsed)
                cfg = _validate_virtio_config(cfg)
                _log(
                    logger,
                    logging.INFO,
                    "Loaded VirtIO config from inline JSON (self.virtio_config_inline_json)",
                )
                return cfg
        except Exception as e:  # pylint: disable=broad-exception-caught  # bad inline config must not abort loading; falls through to next source
            _log(logger, logging.WARNING, "Inline VirtIO config JSON parse failed: %s", e)

    # 3) path to file (JSON/YAML)
    p = getattr(self, "virtio_config_path", None)
    if p:
        try:
            fp = Path(str(p))
            if fp.exists() and fp.is_file():
                parsed = _read_structured_file(fp)
                cfg = _deep_merge_dict(cfg, parsed)
                cfg = _validate_virtio_config(cfg)
                _log(logger, logging.INFO, "Loaded VirtIO config from file: %s", fp)
                return cfg
        except Exception as e:  # pylint: disable=broad-exception-caught  # bad config file must not abort loading; falls through to next source
            _log(logger, logging.WARNING, "VirtIO config load failed (%s): %s", p, e)

    # 4) merged global app config (YAML)
    global_cfg = getattr(self, "config", None)
    vcfg = _extract_virtio_cfg_from_global_config(global_cfg)
    if isinstance(vcfg, dict) and vcfg:
        cfg = _deep_merge_dict(cfg, vcfg)
        cfg = _validate_virtio_config(cfg)
        _log(logger, logging.INFO, "Loaded VirtIO config from self.config (merged YAML)")
        return cfg

    # 5) baked defaults
    return _validate_virtio_config(cfg)
