# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/windows/virtio/detection.py
"""Windows version detection and driver plan selection"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

try:
    import guestfs  # type: ignore
except ImportError:
    guestfs = None  # type: ignore

from h2kvm.core.utils import U

from .windows_virtio_config import DriverStartType, DriverType, WindowsRelease, is_legacy_windows
from .windows_virtio_paths import WindowsSystemPaths, _resolve_windows_system_paths
from .windows_virtio_utils import (
    _log,
    _normalize_product_name,
    _safe_logger,
    _to_int,
)

if TYPE_CHECKING:
    from pathlib import Path


# Plan + Driver model


@dataclass(frozen=True)
class WindowsVirtioPlan:
    """Resolved VirtIO driver-selection plan for a detected Windows release."""

    arch_dir: str
    bucket_hint: str
    release: WindowsRelease
    drivers_needed: set[DriverType]

    @classmethod
    def default_needed(cls) -> set[DriverType]:
        """Return the default set of VirtIO driver types every plan requires."""
        return {DriverType.STORAGE, DriverType.NETWORK, DriverType.BALLOON}


@dataclass
class DriverFile:  # pylint: disable=too-many-instance-attributes  # models a driver .inf/package's many independent metadata fields
    """A single VirtIO driver file resolved from the driver package, with its install metadata."""

    name: str
    type: DriverType
    src_path: Path
    dest_name: str

    start_type: DriverStartType
    service_name: str

    pci_ids: list[str]
    class_guid: str

    package_dir: Path | None = None
    inf_path: Path | None = None

    bucket_used: str | None = None
    match_pattern: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize this driver file's metadata to a plain dict."""
        return {
            "name": self.name,
            "type": self.type.value,
            "src_path": str(self.src_path),
            "dest_name": self.dest_name,
            "start_type": self.start_type.value,
            "service_name": self.service_name,
            "pci_ids": list(self.pci_ids),
            "class_guid": self.class_guid,
            "package_dir": str(self.package_dir) if self.package_dir else None,
            "inf_path": str(self.inf_path) if self.inf_path else None,
            "bucket_used": self.bucket_used,
            "match_pattern": self.match_pattern,
        }


def _plan_to_dict(plan: WindowsVirtioPlan) -> dict[str, Any]:
    return {
        "arch_dir": plan.arch_dir,
        "bucket_hint": plan.bucket_hint,
        "release": plan.release.value,
        "drivers_needed": sorted([d.value for d in plan.drivers_needed]),
    }


# Windows detection + version/build


def is_windows(self, g: guestfs.GuestFS) -> bool:
    """Detect whether the inspected root filesystem is a Windows installation."""
    logger = _safe_logger(self)
    if not getattr(self, "inspect_root", None):
        _log(logger, logging.DEBUG, "Windows detect: inspect_root missing -> not Windows")
        return False

    root = self.inspect_root

    try:
        try:
            os_type = U.to_text(g.inspect_get_type(root))
            if os_type and os_type.lower() == "windows":
                _log(logger, logging.DEBUG, "Windows detect: inspect_get_type says windows")
                return True
        except Exception:  # pylint: disable=broad-exception-caught  # backend-agnostic guestfs call; best-effort detection signal
            pass

        for dir_path in ["/Windows", "/WINDOWS", "/winnt", "/WINNT", "/Program Files"]:
            try:
                if g.is_dir(dir_path):
                    _log(logger, logging.DEBUG, "Windows detect: found dir %s", dir_path)
                    return True
            except Exception:  # pylint: disable=broad-exception-caught  # backend-agnostic guestfs call; best-effort detection signal
                continue

        for reg_file in [
            "/Windows/System32/config/SOFTWARE",
            "/WINDOWS/System32/config/SOFTWARE",
            "/winnt/system32/config/SOFTWARE",
        ]:
            try:
                if g.is_file(reg_file):
                    _log(logger, logging.DEBUG, "Windows detect: found SOFTWARE hive %s", reg_file)
                    return True
            except Exception:  # pylint: disable=broad-exception-caught  # backend-agnostic guestfs call; best-effort detection signal
                continue

        _log(logger, logging.DEBUG, "Windows detect: no signals -> not Windows")
        return False

    except Exception as e:  # pylint: disable=broad-exception-caught  # top-level detection guard; must not crash the whole probe
        _log(logger, logging.DEBUG, "Windows detect: exception -> not Windows: %s", e)
        return False


# pylint: disable=duplicate-code
# reason: mirrors network_fixer.py's _hivex_call_known -- same multi-binding
# compatibility shim, but each raises a domain-specific error message for its
# own caller context, so kept independently editable.
def _hivex_call_known(
    g: guestfs.GuestFS, fn_name: str, args: tuple[Any, ...], *, allow_drop_handle: bool, allow_noargs: bool
) -> Any:
    """
    Call guestfs hivex_* function with binding compatibility.

    Rules:
      - Always try the provided args first.
      - If TypeError and allow_drop_handle is True and first arg looks like a handle,
        retry without the first arg.
      - If still TypeError and allow_noargs is True, retry with no args.
      - Otherwise raise the last TypeError without calling again.
    """
    fn = getattr(g, fn_name, None)
    if fn is None:
        raise AttributeError(
            f"VirtIO driver detection failed: guestfs method '{fn_name}' not found. "
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


def _read_windows_build_from_software_hive(  # pylint: disable=too-many-return-statements,too-many-branches
    self, g: guestfs.GuestFS, software_hive_path: str
) -> int | None:
    """
    Read Windows build number from SOFTWARE hive:
      HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\CurrentBuildNumber (or CurrentBuild)

    Uses guestfs hivex API (no extra deps). Handle-vs-global-hive differences are normalized.
    Many early-return checkpoints while walking the hive tree node by node.
    """
    logger = _safe_logger(self)

    try:
        if not g.is_file(software_hive_path):
            return None
    except Exception:  # pylint: disable=broad-exception-caught  # backend-agnostic guestfs call; best-effort
        return None

    h: int | None = None
    try:
        try:
            h = _hivex_call_known(
                g, "hivex_open", (software_hive_path, 0), allow_drop_handle=False, allow_noargs=False
            )
        except TypeError:
            h = _hivex_call_known(
                g, "hivex_open", (software_hive_path,), allow_drop_handle=False, allow_noargs=False
            )

        root = _hivex_call_known(g, "hivex_root", (h,), allow_drop_handle=True, allow_noargs=True)

        node = _hivex_call_known(
            g, "hivex_node_get_child", (h, root, "Microsoft"), allow_drop_handle=True, allow_noargs=False
        )
        if not node:
            return None
        node = _hivex_call_known(
            g, "hivex_node_get_child", (h, node, "Windows NT"), allow_drop_handle=True, allow_noargs=False
        )
        if not node:
            return None
        node = _hivex_call_known(
            g,
            "hivex_node_get_child",
            (h, node, "CurrentVersion"),
            allow_drop_handle=True,
            allow_noargs=False,
        )
        if not node:
            return None

        def _val(name: str) -> str | None:
            try:
                v = _hivex_call_known(
                    g, "hivex_node_get_value", (h, node, name), allow_drop_handle=True, allow_noargs=False
                )
                if not v:
                    return None
                raw = _hivex_call_known(
                    g, "hivex_value_string", (h, v), allow_drop_handle=True, allow_noargs=False
                )
                s = U.to_text(raw)
                return s.strip() if s else None
            except Exception:  # pylint: disable=broad-exception-caught  # backend-agnostic guestfs hivex call; best-effort
                return None

        for key in ("CurrentBuildNumber", "CurrentBuild"):
            s = _val(key)
            if not s:
                continue
            m = re.search(r"(\d{4,6})", s)
            if m:
                return int(m.group(1))
        return None

    except Exception as e:  # pylint: disable=broad-exception-caught  # top-level hive-read guard; must not crash the whole probe
        _log(logger, logging.DEBUG, "hivex build read failed: %s", e)
        return None
    finally:
        try:
            if h is not None:
                _hivex_call_known(g, "hivex_close", (h,), allow_drop_handle=True, allow_noargs=True)
            else:
                _hivex_call_known(g, "hivex_close", (), allow_drop_handle=False, allow_noargs=True)
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort cleanup, must not mask the real result
            pass


def _windows_version_info(
    self, g: guestfs.GuestFS, paths: WindowsSystemPaths | None = None
) -> dict[str, Any]:
    logger = _safe_logger(self)
    info: dict[str, Any] = {
        "windows": True,
        "bits": 64,
        "build": None,
        "product_name": None,
        "arch": None,
        "major": None,
        "minor": None,
        "distro": None,
    }

    root = getattr(self, "inspect_root", None)
    if root:
        try:
            info["arch"] = U.to_text(g.inspect_get_arch(root))
            info["major"] = g.inspect_get_major_version(root)
            info["minor"] = g.inspect_get_minor_version(root)
            info["product_name"] = U.to_text(g.inspect_get_product_name(root))
            info["distro"] = U.to_text(g.inspect_get_distro(root))
        except Exception as e:  # pylint: disable=broad-exception-caught  # backend-agnostic guestfs call; best-effort
            _log(logger, logging.DEBUG, "Windows info: inspect getters failed: %s", e)

    arch = (info.get("arch") or "").lower()
    if arch in ("x86_64", "amd64", "arm64", "aarch64"):
        info["bits"] = 64
    elif arch in ("i386", "i686", "x86"):
        info["bits"] = 32
    else:
        info["bits"] = 64

    try:
        if paths is None:
            paths = _resolve_windows_system_paths(self, g)
        build = _read_windows_build_from_software_hive(self, g, paths.software_hive)
        if build:
            info["build"] = build
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort build-number lookup, must not abort inspection
        _log(logger, logging.DEBUG, "Windows info: build read failed: %s", e)

    return info


def _detect_windows_release(  # pylint: disable=too-many-return-statements,too-many-branches,unused-argument
    self, win_info: dict[str, Any], cfg: dict[str, Any]
) -> WindowsRelease:
    """
    Detect Windows release family.

    Priority:
      1) product_name hints (best signal)
      2) build number for Win10/Win11 split (>=22000 => Win11+)
      3) major/minor only for older OSes (<=8.1 era)
      4) config default (Windows 11)

    NOTE: Any "Windows 12" mapping is best-effort heuristic only.

    `self` is unused here but kept for signature consistency with the other
    self-taking module functions in this file (attached as methods elsewhere).
    Sequential product-name / build-number / major-minor checks by priority,
    each with its own early return.
    """
    product = _normalize_product_name(str(win_info.get("product_name", "") or ""))
    build = _to_int(win_info.get("build"), default=0)
    major = _to_int(win_info.get("major"), default=0)
    minor = _to_int(win_info.get("minor"), default=0)

    if "server 2022" in product:
        return WindowsRelease.SERVER_2022
    if "server 2019" in product:
        return WindowsRelease.SERVER_2019
    if "server 2016" in product:
        return WindowsRelease.SERVER_2016
    if "server 2012" in product:
        return WindowsRelease.SERVER_2012
    if "server 2008" in product:
        return WindowsRelease.SERVER_2008

    if "windows 12" in product:
        return WindowsRelease.WINDOWS_12
    if "windows 11" in product:
        return WindowsRelease.WINDOWS_11
    if "windows 10" in product:
        return WindowsRelease.WINDOWS_11 if build >= 22000 else WindowsRelease.WINDOWS_10
    if "windows 8.1" in product:
        return WindowsRelease.WINDOWS_8_1
    if "windows 8" in product:
        return WindowsRelease.WINDOWS_8
    if "windows 7" in product:
        return WindowsRelease.WINDOWS_7
    if "vista" in product:
        return WindowsRelease.WINDOWS_VISTA
    if "xp" in product:
        return WindowsRelease.WINDOWS_XP

    if build:
        if build >= 26000:
            return WindowsRelease.WINDOWS_12
        if build >= 22000:
            return WindowsRelease.WINDOWS_11
        if build >= 10240:
            return WindowsRelease.WINDOWS_10

    if major == 6 and minor == 3:
        return WindowsRelease.WINDOWS_8_1
    if major == 6 and minor == 2:
        return WindowsRelease.WINDOWS_8
    if major == 6 and minor == 1:
        return WindowsRelease.WINDOWS_7
    if major == 6 and minor == 0:
        return WindowsRelease.WINDOWS_VISTA
    if major == 5:
        return WindowsRelease.WINDOWS_XP

    d = str(cfg.get("default_release", "windows_11")).strip().lower()
    try:
        return WindowsRelease(d)
    except Exception:  # pylint: disable=broad-exception-caught  # config value may not map to a valid enum member; fall back to a safe default
        return WindowsRelease.WINDOWS_11


def _norm_arch_to_dir(arch: str, cfg: dict[str, Any]) -> str:
    a = (arch or "").lower().strip()
    mapping = {
        "x86_64": "amd64",
        "amd64": "amd64",
        "x64": "amd64",
        "i386": "x86",
        "i686": "x86",
        "x86": "x86",
        "ia64": "ia64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    return mapping.get(a, str(cfg.get("default_arch_dir", "amd64")))


def _bucket_candidates(release: WindowsRelease, cfg: dict[str, Any]) -> list[str]:
    m = cfg.get("bucket_candidates") or {}
    if isinstance(m, dict):
        c = m.get(release.value)
        if isinstance(c, list) and c:
            return [str(x) for x in c]
    return ["w11", "w10", "w8", "w7"]


def _bucket_hint(release: WindowsRelease, cfg: dict[str, Any]) -> str:
    m = cfg.get("release_to_bucket") or {}
    if isinstance(m, dict):
        v = m.get(release.value)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "w11"


def _choose_driver_plan(self, win_info: dict[str, Any], cfg: dict[str, Any]) -> WindowsVirtioPlan:
    logger = _safe_logger(self)

    release = _detect_windows_release(self, win_info, cfg)
    arch_dir = _norm_arch_to_dir(str(win_info.get("arch") or ""), cfg)
    hint = _bucket_hint(release, cfg)
    drivers_needed = WindowsVirtioPlan.default_needed()

    if getattr(self, "enable_virtio_gpu", False):
        drivers_needed.add(DriverType.GPU)
    if getattr(self, "enable_virtio_input", False):
        drivers_needed.add(DriverType.INPUT)
    if getattr(self, "enable_virtio_fs", False):
        drivers_needed.add(DriverType.FILESYSTEM)
    if getattr(self, "enable_virtio_serial", False):
        drivers_needed.add(DriverType.SERIAL)
    if getattr(self, "enable_virtio_rng", False):
        drivers_needed.add(DriverType.RNG)

    # Legacy Windows (XP/Vista/7/Server 2008) needs SHA-1 signed drivers.
    # Warn the user and adjust bucket candidates to prefer legacy driver paths.
    legacy = is_legacy_windows(release)
    if legacy:
        _log(
            logger,
            logging.WARNING,
            "⚠️ Legacy Windows detected (%s) - requires SHA-1 signed VirtIO drivers. "
            "Modern SHA-2-only drivers will NOT load on this OS. "
            "Ensure you have the legacy virtio-win package or use --virtio-legacy-drivers.",
            release.value,
        )
        # For legacy Windows, reduce driver set to essentials only
        # (GPU, input, filesystem, RNG may not have legacy-signed versions)
        drivers_needed = {DriverType.STORAGE, DriverType.NETWORK}
        if DriverType.BALLOON in WindowsVirtioPlan.default_needed():
            drivers_needed.add(DriverType.BALLOON)

    plan = WindowsVirtioPlan(
        arch_dir=arch_dir,
        bucket_hint=hint,
        release=release,
        drivers_needed=drivers_needed,
    )

    _log(
        logger,
        logging.INFO,
        "🧩 Windows plan: release=%s arch=%s bucket_hint=%s candidates=%s drivers=%s legacy=%s",
        plan.release.value,
        plan.arch_dir,
        plan.bucket_hint,
        _bucket_candidates(plan.release, cfg),
        sorted([d.value for d in plan.drivers_needed]),
        legacy,
    )
    return plan
