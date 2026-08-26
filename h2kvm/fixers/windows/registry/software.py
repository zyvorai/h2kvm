# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/windows/registry/software.py
"""
SOFTWARE hive editing for DevicePath and RunOnce entries.

This module provides functions to modify the Windows SOFTWARE registry hive:
- append_devicepath_software_hive: Appends a path to DevicePath for driver discovery
- add_software_runonce: Adds a RunOnce registry entry for first-boot commands

The DevicePath registry value helps Windows PnP discover staged INF packages
during first boot. RunOnce entries execute commands once during system startup,
though the SERVICE-based firstboot mechanism is preferred for higher reliability.
"""

# pylint: disable=duplicate-code
# reason: this module intentionally mirrors the offline-hive-edit boilerplate
# (download/backup/open hive, commit+upload+re-download verification, result-dict
# shape) used by sibling registry fixers (system.py, firstboot.py) -- each editor
# targets a different hive/value with different failure semantics, so the steps
# are kept independently editable rather than merged into one shared routine.
# See git history for the pylint pass that reviewed each instance.

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

# Import shared logging utilities
# Import helper functions from registry sub-modules
from h2kvm.core.logging_utils import safe_logger as _safe_logger_base

from .encoding import (
    _close_best_effort,
    _commit_best_effort,
    _ensure_child,
    _hivex_read_sz,
    _node_id,
    _open_hive_local,
    _set_expand_sz,
    _set_sz,
)
from .io import _download_hive_local, _log_mountpoints_best_effort
from .mount import _ensure_windows_root
from .system import _hive_backup_best_effort

if TYPE_CHECKING:
    import logging

    import guestfs  # type: ignore
else:
    try:
        import guestfs  # type: ignore
    except ImportError:
        guestfs = None  # type: ignore

try:
    import hivex  # type: ignore
except ImportError:
    hivex = None  # type: ignore


def _safe_logger(self) -> logging.Logger:
    """Get logger from self or create default logger."""
    return _safe_logger_base(self, "h2kvm.windows_registry")


# Public: SOFTWARE hive DevicePath append


def _normalize_devicepath_part(p: str) -> str:
    return p.strip().strip(";").strip().lower()


def _resolve_software_cv_node(h: hivex.Hivex, root: int) -> int:
    microsoft = _node_id(h.node_get_child(root, "Microsoft"))
    if microsoft == 0:
        raise RuntimeError(
            "Windows registry SOFTWARE hive is missing the 'Microsoft' key. "
            "The Windows installation may be corrupted or an unsupported version."
        )

    windows = _node_id(h.node_get_child(microsoft, "Windows"))
    if windows == 0:
        raise RuntimeError(
            "Windows registry SOFTWARE hive is missing the 'Microsoft\\Windows' key. "
            "The Windows installation may be corrupted or an unsupported version."
        )

    cv = _node_id(h.node_get_child(windows, "CurrentVersion"))
    if cv == 0:
        raise RuntimeError(
            "Windows registry SOFTWARE hive is missing the 'CurrentVersion' key. "
            "The Windows installation may be corrupted or an unsupported version."
        )
    return cv


def append_devicepath_software_hive(  # pylint: disable=too-many-locals,too-many-statements
    self,
    g: guestfs.GuestFS,
    software_hive_path: str,
    append_path: str,
) -> dict[str, Any]:
    # reason: single offline-hive-edit routine covering download, backup, edit,
    # commit, upload, and post-write verification, each step tracked in `out`.
    """Append `append_path` to the SOFTWARE hive's DevicePath value, deduped case-insensitively."""
    logger = _safe_logger(self)
    dry_run = bool(getattr(self, "dry_run", False))

    out: dict[str, Any] = {
        "success": False,
        "dry_run": dry_run,
        "hive_path": software_hive_path,
        "modified": False,
        "original": None,
        "new": None,
        "errors": [],
        "notes": [],
        "uploaded_files": [],
        "verification": {},
    }

    try:
        _ensure_windows_root(logger, g, hint_hive_path=software_hive_path)
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline hive edit -- root-detection failure is reported
        # back in the result dict rather than raised, so callers can continue with
        # other fixer steps.
        out["errors"].append(str(e))
        return out

    try:
        if not g.is_file(software_hive_path):
            out["errors"].append(f"SOFTWARE hive not found: {software_hive_path}")
            return out
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: guestfs stat call on a dynamically-typed handle -- report failure in
        # the result dict rather than raise.
        out["errors"].append(f"Failed to stat hive {software_hive_path}: {e}")
        return out

    with tempfile.TemporaryDirectory() as td:
        local = Path(td) / "SOFTWARE"
        h: hivex.Hivex | None = None
        try:
            _log_mountpoints_best_effort(logger, g)
            _hive_backup_best_effort(logger, g, software_hive_path, dry_run=dry_run, results=out)

            _download_hive_local(logger, g, software_hive_path, local)
            orig_hash = hashlib.sha256(local.read_bytes()).hexdigest()

            h = _open_hive_local(local, write=not dry_run)
            root = _node_id(h.root())
            if root == 0:
                out["errors"].append("Invalid hivex root()")
                return out

            cv = _resolve_software_cv_node(h, root)

            cur = _hivex_read_sz(h, cv, "DevicePath") or r"%SystemRoot%\inf"
            out["original"] = cur

            parts_raw = [p.strip() for p in cur.split(";") if p.strip()]
            parts_norm = {_normalize_devicepath_part(p) for p in parts_raw}

            ap_norm = _normalize_devicepath_part(append_path)
            if ap_norm and ap_norm not in parts_norm:
                parts_raw.append(append_path.strip())
            new = ";".join(parts_raw)
            out["new"] = new

            if new != cur:
                logger.info("Updating DevicePath: +%s", append_path)
                _set_expand_sz(h, cv, "DevicePath", new)
                out["modified"] = True
            else:
                logger.info("DevicePath already contains staging path (case-insensitive); no change needed")

            if not dry_run:
                try:
                    _commit_best_effort(h)
                finally:
                    _close_best_effort(h)
                    h = None

                g.upload(str(local), software_hive_path)
                out["uploaded_files"].append(
                    {
                        "guest_path": software_hive_path,
                        "sha256_local": hashlib.sha256(local.read_bytes()).hexdigest(),
                    }
                )

                with tempfile.TemporaryDirectory() as vtd:
                    vlocal = Path(vtd) / "SOFTWARE_verify"
                    _download_hive_local(logger, g, software_hive_path, vlocal)
                    new_hash = hashlib.sha256(vlocal.read_bytes()).hexdigest()

                out["verification"] = {
                    "sha256_before": orig_hash,
                    "sha256_after": new_hash,
                    "changed": (new_hash != orig_hash),
                }
                out["success"] = True
            else:
                out["success"] = True

            out["notes"] += [
                "DevicePath updated to help Windows PnP discover staged INF packages on first boot.",
                "Comparison is case-insensitive to avoid duplicates differing only by case/whitespace.",
                "Value written as REG_EXPAND_SZ (UTF-16LE).",
                "Node ids normalized across python-hivex versions (0 vs None).",
                "Backup created alongside other SOFTWARE edits.",
                "Windows root mount validated to ensure correct C: mapping.",
                "Hive integrity checked via size + 'regf' signature during downloads.",
            ]
            return out

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort offline hive edit covering hivex parsing, guestfs
            # upload, and re-download verification -- any failure is reported back
            # in the result dict rather than raised.
            out["errors"].append(f"DevicePath update failed: {e}")
            return out
        finally:
            _close_best_effort(h)


# Public: SOFTWARE hive Run key helper (persistent, fires every login until removed)


def add_software_run_key(
    self,
    g: guestfs.GuestFS,
    software_hive_path: str,
    *,
    name: str,
    command: str,
) -> dict[str, Any]:
    """Add a Run key entry (HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run).

    Unlike RunOnce, Run entries persist across logins and execute on every login.
    The firstboot.cmd script must handle idempotency itself (e.g., check a marker file).
    The script should also delete this Run key after successful execution.
    """
    logger = _safe_logger(self)
    dry_run = bool(getattr(self, "dry_run", False))

    logger.debug(
        "add_software_run_key: name=%s, command=%s, hive=%s, dry_run=%s",
        name,
        command,
        software_hive_path,
        dry_run,
    )

    out: dict[str, Any] = {
        "success": False,
        "dry_run": dry_run,
        "name": name,
        "command": command,
        "errors": [],
        "notes": [],
    }

    try:
        _ensure_windows_root(logger, g, hint_hive_path=software_hive_path)
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline hive edit -- root-detection failure is reported
        # back in the result dict rather than raised, so callers can continue with
        # other fixer steps.
        out["errors"].append(str(e))
        return out

    try:
        if not g.is_file(software_hive_path):
            out["errors"].append(f"SOFTWARE hive not found: {software_hive_path}")
            return out
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: guestfs stat call on a dynamically-typed handle -- report failure in
        # the result dict rather than raise.
        out["errors"].append(f"Failed to stat hive: {e}")
        return out

    with tempfile.TemporaryDirectory() as td:
        local = Path(td) / "SOFTWARE"
        h: hivex.Hivex | None = None
        try:
            _download_hive_local(logger, g, software_hive_path, local)
            h = _open_hive_local(local, write=not dry_run)
            root = _node_id(h.root())
            if root == 0:
                out["errors"].append("Invalid hivex root()")
                return out

            cv = _ensure_software_cv_path(h, root)
            run = _node_id(h.node_get_child(cv, "Run"))
            if run == 0:
                logger.debug("Run key does not exist, creating it")
                run = _ensure_child(h, cv, "Run")

            logger.debug(
                r"Setting Run key: HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run\%s = %s",
                name,
                command,
            )
            _set_sz(h, run, name, command)

            if not dry_run:
                try:
                    _commit_best_effort(h)
                finally:
                    _close_best_effort(h)
                    h = None

                g.upload(str(local), software_hive_path)
                out["success"] = True
            else:
                out["success"] = True

            logger.info("Run key set: %s -> %s", name, command)
            out["notes"].append(r"Run key written at HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run")
        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort offline hive edit -- any failure is reported back in
            # the result dict rather than raised.
            out["errors"].append(f"Run key update failed: {e}")
        finally:
            _close_best_effort(h)
    return out


# Public: SOFTWARE hive RunOnce helper (kept, but SERVICE is preferred)


def _ensure_software_cv_path(h: hivex.Hivex, root: int) -> int:
    microsoft = _node_id(h.node_get_child(root, "Microsoft"))
    if microsoft == 0:
        microsoft = _ensure_child(h, root, "Microsoft")

    windows = _node_id(h.node_get_child(microsoft, "Windows"))
    if windows == 0:
        windows = _ensure_child(h, microsoft, "Windows")

    cv = _node_id(h.node_get_child(windows, "CurrentVersion"))
    if cv == 0:
        cv = _ensure_child(h, windows, "CurrentVersion")
    return cv


def add_software_runonce(  # pylint: disable=too-many-locals,too-many-statements
    self,
    g: guestfs.GuestFS,
    software_hive_path: str,
    *,
    name: str,
    command: str,
) -> dict[str, Any]:
    # reason: single offline-hive-edit routine covering download, backup, edit,
    # commit, upload, and post-write verification, each step tracked in `out`.
    """Add a RunOnce entry to the SOFTWARE hive (fires once, then Windows removes it)."""
    logger = _safe_logger(self)
    dry_run = bool(getattr(self, "dry_run", False))

    logger.debug(
        "add_software_runonce: name=%s, command=%s, hive=%s, dry_run=%s",
        name,
        command,
        software_hive_path,
        dry_run,
    )

    out: dict[str, Any] = {
        "success": False,
        "dry_run": dry_run,
        "hive_path": software_hive_path,
        "name": name,
        "command": command,
        "modified": False,
        "original": None,
        "new": None,
        "errors": [],
        "notes": [],
        "uploaded_files": [],
        "verification": {},
    }

    try:
        _ensure_windows_root(logger, g, hint_hive_path=software_hive_path)
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline hive edit -- root-detection failure is reported
        # back in the result dict rather than raised, so callers can continue with
        # other fixer steps.
        out["errors"].append(str(e))
        return out

    try:
        if not g.is_file(software_hive_path):
            out["errors"].append(f"SOFTWARE hive not found: {software_hive_path}")
            return out
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: guestfs stat call on a dynamically-typed handle -- report failure in
        # the result dict rather than raise.
        out["errors"].append(f"Failed to stat hive {software_hive_path}: {e}")
        return out

    with tempfile.TemporaryDirectory() as td:
        local = Path(td) / "SOFTWARE"
        h: hivex.Hivex | None = None
        try:
            _log_mountpoints_best_effort(logger, g)
            _hive_backup_best_effort(logger, g, software_hive_path, dry_run=dry_run, results=out)

            _download_hive_local(logger, g, software_hive_path, local)
            orig_hash = hashlib.sha256(local.read_bytes()).hexdigest()

            h = _open_hive_local(local, write=not dry_run)
            root = _node_id(h.root())
            if root == 0:
                out["errors"].append("Invalid hivex root()")
                return out

            cv = _ensure_software_cv_path(h, root)
            runonce = _node_id(h.node_get_child(cv, "RunOnce"))
            if runonce == 0:
                logger.debug("RunOnce key does not exist, creating it")
                runonce = _ensure_child(h, cv, "RunOnce")

            logger.debug(
                r"Setting RunOnce key: HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce\%s",
                name,
            )

            old = _hivex_read_sz(h, runonce, name)
            out["original"] = old

            if old != command:
                _set_sz(h, runonce, name, command)
                out["modified"] = True
                out["new"] = command
            else:
                out["new"] = old

            if not dry_run:
                try:
                    _commit_best_effort(h)
                finally:
                    _close_best_effort(h)
                    h = None

                g.upload(str(local), software_hive_path)
                out["uploaded_files"].append(
                    {
                        "guest_path": software_hive_path,
                        "sha256_local": hashlib.sha256(local.read_bytes()).hexdigest(),
                    }
                )

                with tempfile.TemporaryDirectory() as vtd:
                    vlocal = Path(vtd) / "SOFTWARE_verify"
                    _download_hive_local(logger, g, software_hive_path, vlocal)
                    new_hash = hashlib.sha256(vlocal.read_bytes()).hexdigest()

                out["verification"] = {
                    "sha256_before": orig_hash,
                    "sha256_after": new_hash,
                    "changed": (new_hash != orig_hash),
                }
                out["success"] = True
            else:
                out["success"] = True

            logger.info("RunOnce set: %s -> %s", name, command)
            out["notes"] += [
                r"RunOnce written at HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",
                "Value written as REG_SZ (UTF-16LE).",
                "Node ids normalized across python-hivex versions (0 vs None).",
                "Windows root mount validated to ensure correct C: mapping.",
                "Hive integrity checked via size + 'regf' signature during downloads.",
                "Consider using provision_firstboot_payload_and_service() for higher reliability than RunOnce.",
            ]
            return out

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort offline hive edit covering hivex parsing, guestfs
            # upload, and re-download verification -- any failure is reported back
            # in the result dict rather than raised.
            out["errors"].append(f"RunOnce update failed: {e}")
            return out
        finally:
            _close_best_effort(h)
