# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/fixers/windows/virtio/discovery.py
"""VirtIO driver file discovery and matching"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .detection import DriverFile, WindowsVirtioPlan, _bucket_candidates
from .windows_virtio_config import DriverStartType, DriverType, _parse_start_type
from .windows_virtio_utils import _log, _safe_logger

if TYPE_CHECKING:
    from pathlib import Path

# Driver discovery helpers


def _get_driver_definitions(cfg: dict[str, Any], dt: DriverType) -> list[dict[str, Any]]:
    d = cfg.get("drivers") or {}
    if not isinstance(d, dict):
        return []
    arr = d.get(dt.value)
    if not isinstance(arr, list):
        return []
    out: list[dict[str, Any]] = []
    for item in arr:
        if isinstance(item, dict) and item.get("name") and item.get("pattern") and item.get("service"):
            out.append(item)
    return out


def _warn_if_driver_defs_suspicious(self, cfg: dict[str, Any]) -> None:
    """
    Emit warnings for malformed driver definitions that will likely break registry binding.
    Especially important for storage drivers.
    """
    logger = _safe_logger(self)
    for dt in DriverType:
        defs = _get_driver_definitions(cfg, dt)
        for dfn in defs:
            name = str(dfn.get("name") or "")
            service = str(dfn.get("service") or "")
            class_guid = str(dfn.get("class_guid") or "")
            pci_ids = dfn.get("pci_ids") or []
            if dt == DriverType.STORAGE:
                if not class_guid:
                    _log(
                        logger,
                        logging.WARNING,
                        "Config: storage driver %s/%s missing class_guid (SYSTEM hive edits may be incomplete)",
                        name,
                        service,
                    )
                if not pci_ids:
                    _log(
                        logger,
                        logging.WARNING,
                        "Config: storage driver %s/%s missing pci_ids (CDD population will be incomplete)",
                        name,
                        service,
                    )
            elif not class_guid:
                _log(logger, logging.DEBUG, "Config: driver %s/%s missing class_guid", name, service)


def _pick_best_match(paths: list[Path]) -> Path:
    """
    Pick best candidate among multiple matches:
      1) shortest path (usually most specific / canonical)
      2) newest mtime
      3) lexical tie-break
    """

    def _key(p: Path) -> tuple[int, float, str]:
        try:
            mt = p.stat().st_mtime
        except OSError:
            mt = 0.0
        return (len(str(p)), -mt, str(p))

    return sorted(paths, key=_key)[0]


# pylint: disable-next=too-many-locals,too-many-statements  # discovers drivers across many pattern/bucket/type combinations in one pass
def _discover_virtio_drivers(
    self, virtio_src: Path, plan: WindowsVirtioPlan, cfg: dict[str, Any]
) -> list[DriverFile]:
    # Local import to avoid circular dependency (core imports this module)
    from .core import _materialize_virtio_source  # pylint: disable=import-outside-toplevel,cyclic-import

    logger = _safe_logger(self)
    drivers: list[DriverFile] = []
    buckets = _bucket_candidates(plan.release, cfg)

    search_patterns = [
        "{pattern}",
        "{driver}/{bucket}/{arch}/*.sys",
        "{driver}/{arch}/*.sys",
        "{driver}/*/{arch}/*.sys",
        "{driver}/*/*/{arch}/*.sys",
    ]

    def _glob_all(base: Path, pat: str) -> list[Path]:
        try:
            return sorted([p for p in base.glob(pat) if p.is_file()])
        except OSError:
            return []

    def _find_inf_near_sys(sys_path: Path, inf_hint: str | None) -> Path | None:
        pkg = sys_path.parent
        try:
            if inf_hint:
                cand = pkg / inf_hint
                if cand.exists() and cand.is_file():
                    return cand
            infs = sorted([p for p in pkg.glob("*.inf") if p.is_file()])
            return infs[0] if infs else None
        except OSError:
            return None

    _log(logger, logging.INFO, "🔎 Discovering VirtIO drivers ...")
    _log(logger, logging.INFO, "VirtIO source: %s", virtio_src)
    _log(logger, logging.INFO, "Bucket candidates: %s", buckets)

    with _materialize_virtio_source(self, virtio_src) as base:
        _log(logger, logging.INFO, "VirtIO materialized dir: %s", base)

        for driver_type in sorted(plan.drivers_needed, key=lambda d: d.value):
            defs = _get_driver_definitions(cfg, driver_type)
            if not defs:
                continue

            for dfn in defs:
                driver_name = str(dfn.get("name") or "")
                service = str(dfn.get("service") or "")
                pattern_tmpl = str(dfn.get("pattern") or "")
                inf_hint = dfn.get("inf_hint") or None
                class_guid = str(dfn.get("class_guid") or "")
                pci_ids = [str(x).lower() for x in (dfn.get("pci_ids") or []) if str(x).strip()]

                start_val = _parse_start_type(dfn.get("start", DriverStartType.AUTO.value))
                try:
                    start_enum = DriverStartType(start_val)
                except ValueError:
                    start_enum = DriverStartType.AUTO

                found = False
                for bucket in buckets:
                    if found:
                        break

                    canonical = pattern_tmpl.format(bucket=bucket, arch=plan.arch_dir)

                    for tmpl in search_patterns:
                        pat = tmpl.format(
                            pattern=canonical,
                            driver=driver_name,
                            bucket=bucket,
                            arch=plan.arch_dir,
                        )

                        matches = _glob_all(base, pat)
                        if not matches:
                            continue

                        src = matches[0]
                        if len(matches) > 1:
                            src = _pick_best_match(matches)
                            _log(
                                logger,
                                logging.WARNING,
                                "Multiple matches for %s (picked %s): %s",
                                pat,
                                src,
                                [str(m) for m in matches[:10]],
                            )

                        infp = _find_inf_near_sys(src, str(inf_hint) if inf_hint else None)
                        pkg_dir = src.parent

                        drivers.append(
                            DriverFile(
                                name=driver_name,
                                type=driver_type,
                                src_path=src,
                                dest_name=f"{service}.sys",
                                start_type=start_enum,
                                service_name=service,
                                pci_ids=pci_ids,
                                class_guid=class_guid,
                                package_dir=pkg_dir,
                                inf_path=infp,
                                bucket_used=bucket,
                                match_pattern=pat,
                            )
                        )
                        _log(
                            logger,
                            logging.INFO,
                            "📦 Found driver: type=%s service=%s bucket=%s -> %s",
                            driver_type.value,
                            service,
                            bucket,
                            src,
                        )
                        if infp:
                            _log(logger, logging.INFO, "📄 INF: %s", infp)
                        else:
                            _log(
                                logger,
                                logging.WARNING,
                                "📄 INF missing near %s (PnP may still work via SYS only)",
                                src,
                            )
                        found = True
                        break

                if not found:
                    lvl = logging.WARNING if driver_type == DriverType.STORAGE else logging.INFO
                    _log(
                        logger,
                        lvl,
                        "Driver not found: type=%s name=%s arch=%s buckets=%s",
                        driver_type.value,
                        driver_name,
                        plan.arch_dir,
                        buckets,
                    )

    return drivers


# Note: The following helper functions are referenced but need to be imported from other modules:
# - _materialize_virtio_source: should be in windows_virtio_utils or windows_virtio.py
# - _parse_start_type: should be in windows_virtio_config
# - _bucket_candidates: should be in windows_virtio_config
# - DriverStartType: already imported from windows_virtio_config
