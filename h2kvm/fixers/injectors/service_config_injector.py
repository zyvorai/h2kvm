# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Systemd service management injector."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pylint: disable=duplicate-code
    # This typing-only guestfs-availability shim is intentionally identical to the
    # same block in other fixer/inspector modules; it's boilerplate for a fallback
    # typing stub, not shared logic worth extracting.
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        # pylint: disable=invalid-name,missing-class-docstring,too-few-public-methods
        # Typing-only fallback stub: name must match the real `guestfs` module/class
        # so annotations below resolve the same way whether or not guestfs is installed.
        class guestfs:  # type: ignore
            class GuestFS(Protocol): ...


# pylint: disable=too-many-locals,too-many-branches,too-many-statements,too-many-nested-blocks
# Applies enable/disable/mask actions for three independent service lists against
# the guestfs handle; splitting further would obscure the dry-run/live-mode symmetry.
def inject_service_config(self, g: guestfs.GuestFS) -> dict[str, Any]:
    """Enable, disable, or mask systemd services."""
    logger = getattr(self, "logger", None)

    def _log(level: str, msg: str) -> None:
        if logger:
            with contextlib.suppress(Exception):
                getattr(logger, level)(msg)

    # pylint: disable=duplicate-code
    # reason: config-presence/type-check boilerplate mirrors
    # h2kvm/fixers/injectors/hostname_config_injector.py's inject_hostname_config(),
    # but the results dict shape differs per injector (enabled/disabled/masked vs
    # hostname_set/hosts_entries_added) -- coincidental shape, not shared logic.
    config = getattr(self, "service_config_inject", None)
    if config is None:
        return {"injected": False, "reason": "no_config"}
    if not isinstance(config, dict):
        return {"injected": False, "reason": "invalid_config"}

    dry = bool(getattr(self, "dry_run", False))
    results: dict[str, Any] = {
        "injected": True,
        "dry_run": dry,
        "enabled": [],
        "disabled": [],
        "masked": [],
    }

    enable = config.get("enable", [])
    disable = config.get("disable", [])
    mask = config.get("mask", [])

    if not enable and not disable and not mask:
        return {"injected": False, "reason": "no_config"}

    wants_dir = "/etc/systemd/system/multi-user.target.wants"

    for svc in enable:
        if not svc.endswith(".service"):
            svc += ".service"
        if dry:
            _log("info", f"DRY-RUN: would enable {svc}")
            results["enabled"].append(svc)
        else:
            try:
                for base in ["/usr/lib/systemd/system", "/lib/systemd/system"]:
                    svc_path = f"{base}/{svc}"
                    if g.exists(svc_path):
                        if not g.is_dir(wants_dir):
                            g.mkdir_p(wants_dir)
                        g.ln_sf(svc_path, f"{wants_dir}/{svc}")
                        results["enabled"].append(svc)
                        _log("info", f"Enabled {svc}")
                        break
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort per-service enable, must not abort the whole injector
                _log("warning", f"Failed to enable {svc}: {e}")

    for svc in disable:
        if not svc.endswith(".service"):
            svc += ".service"
        if dry:
            _log("info", f"DRY-RUN: would disable {svc}")
            results["disabled"].append(svc)
        else:
            try:
                link = f"{wants_dir}/{svc}"
                if g.exists(link):
                    g.rm(link)
                results["disabled"].append(svc)
                _log("info", f"Disabled {svc}")
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort per-service disable, must not abort the whole injector
                _log("warning", f"Failed to disable {svc}: {e}")

    for svc in mask:
        if not svc.endswith(".service"):
            svc += ".service"
        if dry:
            _log("info", f"DRY-RUN: would mask {svc}")
            results["masked"].append(svc)
        else:
            try:
                svc_path = f"/etc/systemd/system/{svc}"
                g.ln_sf("/dev/null", svc_path)
                results["masked"].append(svc)
                _log("info", f"Masked {svc}")
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort per-service mask, must not abort the whole injector
                _log("warning", f"Failed to mask {svc}: {e}")

    return results
