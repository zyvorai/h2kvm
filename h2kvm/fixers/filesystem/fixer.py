# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/filesystem/fixer.py
"""Filesystem fixing and fstab regeneration."""

from __future__ import annotations

import logging
import os
import re
import time
from typing import TYPE_CHECKING, Any

from h2kvm.core.utils import U

if TYPE_CHECKING:  # pylint: disable=duplicate-code
    # This typing-only guestfs-availability shim is intentionally identical to the
    # same block in other fixer modules (e.g. guest_inspector.py); it's boilerplate
    # for a fallback typing stub, not shared logic worth extracting.
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        # pylint: disable=invalid-name,missing-class-docstring,too-few-public-methods
        # Typing-only fallback stub: name must match the real `guestfs` module/class
        # so annotations below resolve the same way whether or not guestfs is installed.
        class guestfs:  # type: ignore
            class GuestFS(Protocol): ...


class FilesystemFixer:
    """
    Offline filesystem checker/repair helper for guestfs-based workflows.

    Design goals:
      - robust filesystem type detection (multiple fallbacks)
      - never touch dangerous filesystems automatically (btrfs/zfs/...)
      - run safe check/repair tools with high-signal logs
      - for XFS, be extra careful with memory usage:
          * always use -P (noprefetch)
          * always pass -m with a conservative value (approximate cap, not hard)
    """

    # File systems we should NEVER attempt to auto-repair
    DANGEROUS_FS_TYPES = {"btrfs", "zfs", "reiserfs", "reiser4", "f2fs"}

    # File systems requiring special handling (we skip in this fixer)
    SPECIAL_FS_TYPES = {"swap", "crypto_luks", "lvm2_member", "bcachefs"}

    # Canonical "safe" filesystem types we can attempt to check/repair
    SAFE_FS_TYPES = {"ext2", "ext3", "ext4", "xfs", "vfat", "ntfs", "exfat"}

    # Normalization aliases -> canonical type
    FS_ALIASES: dict[str, str] = {
        "fat": "vfat",
        "fat16": "vfat",
        "fat32": "vfat",
        "msdos": "vfat",
        "ntfs_3g": "ntfs",
        "ntfs3": "ntfs",
        "exfatfs": "exfat",
    }

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)
        # NOTE: keep "repaired" for legacy expectations, but also expose "repairs_attempted".
        self.stats: dict[str, Any] = {
            "total_devices": 0,
            "checked": 0,
            "repaired": 0,  # legacy name: actually "repairs_attempted"
            "repairs_attempted": 0,
            "skipped": 0,
            "errors": 0,
            "start_time": 0.0,
            "end_time": 0.0,
        }

    # Logging / small utils

    def _log(self, level: int, msg: str, *args, **kwargs) -> None:
        if self.logger:
            self.logger.log(level, msg, *args, **kwargs)

    def _now(self) -> float:
        return time.time()

    def _bump_stat(self, key: str, inc: int = 1) -> None:
        try:
            self.stats[key] = int(self.stats.get(key, 0)) + inc
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort stat bump, must never abort the fixer over a stats bookkeeping glitch
            self.stats[key] = inc

    # Normalization helpers

    def _normalize_fs_type(self, fs_type: str) -> str:
        s = (fs_type or "").strip().lower().replace("-", "_")
        return self.FS_ALIASES.get(s, s)

    def _tokenize_fs_type(self, fs_type: str) -> list[str]:
        s = self._normalize_fs_type(fs_type)
        toks = [t for t in re.split(r"[^a-z0-9_]+", s) if t]
        return toks or ([s] if s else [])

    # Appliance memory helpers (best-effort)

    def _get_guestfs_memsize_mib_best_effort(self, ctx: Any | None = None) -> int | None:
        for key in ("guestfs_memsize_mib", "memsize_mib", "appliance_memsize_mib"):
            try:
                v = int(getattr(ctx, key))  # type: ignore[arg-type]
                if v > 0:
                    return v
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort probe over an untyped ctx attribute, must not abort memory sizing
                pass

        for k in ("LIBGUESTFS_MEMSIZE", "VMDK2KVM_GUESTFS_MEMSIZE"):
            try:
                v = int(os.environ.get(k, "") or "0")
                if v > 0:
                    return v
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort probe over an env var, must not abort memory sizing
                pass

        return None

    def _xfs_safe_maxmem_mib(self, memsize_mib: int | None) -> int:
        if not memsize_mib or memsize_mib <= 0:
            return 768

        reserve = 1024
        usable = max(256, memsize_mib - reserve)

        m = int(memsize_mib * 0.30)
        m = max(256, min(m, usable))
        return min(m, 2048)

    # Command helpers

    def _has_command(self, g: guestfs.GuestFS) -> bool:
        return bool(hasattr(g, "command"))

    def _run_variants_best_effort(
        self,
        g: guestfs.GuestFS,
        variants: list[list[str]],
        *,
        log_prefix: str,
    ) -> dict[str, Any]:
        out: dict[str, Any] = {"success": False, "command": None, "output": "", "error": None, "tried": []}

        if not self._has_command(g):
            out["error"] = "guestfs handle does not support command()"
            return out

        last_err: str | None = None
        for args in variants:
            cmd = " ".join(args)
            out["tried"].append(cmd)
            try:
                self._log(logging.DEBUG, "%s try: %s", log_prefix, cmd)
                r = g.command(args)
                out["command"] = cmd
                out["output"] = U.to_text(r)
                out["success"] = True
                out["error"] = None
                return out
            except Exception as e:  # pylint: disable=broad-exception-caught  # try each command variant, one failing must not abort probing the rest
                last_err = str(e)
                self._log(logging.DEBUG, "%s failed: %s (%s)", log_prefix, cmd, last_err)

        out["error"] = last_err or "All command variants failed"
        return out

    def _probe_tool_exists(self, g: guestfs.GuestFS, tool: str) -> bool:
        """
        Probe tool existence WITHOUT depending on /bin/sh.

        Strategy:
          - Try "<tool> --help" or "-h"
          - If error message looks like ENOENT, treat as missing.
          - Otherwise assume tool exists (even if help returned non-zero).
        """
        if not self._has_command(g):
            return False

        for flag in ("--help", "-h"):
            try:
                g.command([tool, flag])
                return True
            except Exception as e:  # pylint: disable=broad-exception-caught  # try each help flag, one failing must not abort the existence probe
                msg = str(e).lower()
                if any(s in msg for s in ("no such file", "not found", "enoent", "cannot execute")):
                    continue
                return True
        return False

    # Filesystem type detection

    def _vfs_type(  # pylint: disable=too-many-return-statements,too-many-branches
        # Tries several detection methods (vfs_type, list_filesystems, `file -s`
        # heuristics across many candidate fs names) in order, each with its own
        # early return; splitting further would obscure the fallback order.
        self,
        g: guestfs.GuestFS,
        dev: str,
    ) -> str:
        dev_text = U.to_text(dev)
        self._log(logging.DEBUG, "🔎 vfs detect: probing %s", dev_text)

        # Method 1: guestfs vfs_type()
        try:
            if hasattr(g, "vfs_type"):
                fs_type = U.to_text(g.vfs_type(dev_text)).strip()
                if fs_type:
                    self._log(logging.DEBUG, "🧬 vfs_type: %s -> %s", dev_text, fs_type)
                    return fs_type
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort detection method, must fall through to the next one
            self._log(logging.DEBUG, "🫥 vfs_type failed for %s: %s", dev_text, str(e))

        # Method 2: list_filesystems()
        try:
            fsmap = g.list_filesystems() or {}
            for k, v in fsmap.items():
                if U.to_text(k) == dev_text:
                    fs_type = U.to_text(v).strip()
                    if fs_type:
                        self._log(logging.DEBUG, "🗺️ list_filesystems: %s -> %s", dev_text, fs_type)
                        return fs_type
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort detection method, must fall through to the next one
            self._log(logging.DEBUG, "🫥 list_filesystems failed: %s", str(e))

        # Method 3: file -s heuristic
        try:
            if self._has_command(g):
                # Use command_quiet if available (VMCraft) to suppress error logging
                if hasattr(g, "command_quiet"):
                    out_raw = g.command_quiet(["file", "-s", dev_text])
                else:
                    out_raw = g.command(["file", "-s", dev_text])
                out = U.to_text(out_raw)
                out_l = out.lower()
                if out:
                    self._log(logging.DEBUG, "📄 file -s %s => %s", dev_text, out.strip())

                if "exfat" in out_l:
                    return "exfat"
                if "ntfs" in out_l:
                    return "ntfs"

                ordered = [
                    "bcachefs",
                    "btrfs",
                    "zfs",
                    "reiser4",
                    "reiserfs",
                    "f2fs",
                    "xfs",
                    "ext4",
                    "ext3",
                    "ext2",
                    "vfat",
                    "fat32",
                    "fat",
                ]
                for cand in ordered:
                    if re.search(rf"(^|[^a-z0-9_]){re.escape(cand)}([^a-z0-9_]|$)", out_l):
                        return cand

                # FAT strings often look like: "FAT (32 bit)" / "FAT12/16/32"
                if "fat" in out_l and "exfat" not in out_l:
                    if re.search(r"(^|[^0-9])32([^0-9]|$)", out_l) or "32 bit" in out_l or "fat32" in out_l:
                        return "fat32"
                    return "fat"

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort detection method, final fallback must not raise
            self._log(logging.DEBUG, "🫥 file -s failed for %s: %s", dev_text, str(e))

        self._log(logging.DEBUG, "❓ vfs detect: could not detect filesystem type for %s", dev_text)
        return ""

    # Classification

    def _classify_fs_type(self, fs_type: str) -> dict[str, Any]:
        fs_raw = fs_type or ""
        fs_norm = self._normalize_fs_type(fs_raw)
        toks = set(self._tokenize_fs_type(fs_raw))

        classification: dict[str, Any] = {
            "type": fs_raw,
            "type_normalized": fs_norm,
            "is_dangerous": False,
            "is_safe": False,
            "is_special": False,
            "can_check": False,
            "can_repair": False,
            "recommended_action": "skip",
        }

        if any(d in toks or fs_norm == d for d in self.DANGEROUS_FS_TYPES):
            classification["is_dangerous"] = True
            classification["recommended_action"] = "skip_dangerous"
            return classification

        if any(s in toks or fs_norm == s for s in self.SPECIAL_FS_TYPES):
            classification["is_special"] = True
            classification["recommended_action"] = "skip_special"
            return classification

        if fs_norm in self.SAFE_FS_TYPES:
            classification["is_safe"] = True
            classification["can_check"] = True
            classification["can_repair"] = True
            classification["recommended_action"] = "check_and_repair"

        return classification

    # Repair runners (small + focused)

    def _run_fsck_ext(
        self, g: guestfs.GuestFS, dev: str, dry_run: bool, force_repair: bool = False
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "tool": "e2fsck",
            "device": dev,
            "dry_run": dry_run,
            "force_repair": force_repair,
            "success": False,
            "output": "",
            "error": None,
            "command": None,
            "tried": [],
        }

        try:
            if self._has_command(g):
                args = ["e2fsck"]
                if dry_run:
                    args.extend(["-n", "-v"])
                else:
                    args.extend(["-p", "-f"] if force_repair else ["-p"])
                args.append(dev)

                cmd = " ".join(args)
                self._log(
                    logging.INFO,
                    "🧰 fsck(ext): %s dry_run=%s force=%s cmd=%s",
                    dev,
                    dry_run,
                    force_repair,
                    cmd,
                )
                out = g.command(args)
                result.update({"command": cmd, "output": U.to_text(out), "success": True})
                return result

            if hasattr(g, "e2fsck") and not dry_run:
                result["command"] = "guestfs.e2fsck(correct=True)"
                self._log(logging.INFO, "🧰 fsck(ext): %s via guestfs.e2fsck correct=True", dev)
                g.e2fsck(dev, correct=True)
                result["success"] = True
                return result

            result["error"] = "No supported e2fsck execution method in guestfs handle"
            self._log(logging.WARNING, "⚠️ fsck(ext): %s no supported method", dev)
            return result

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort repair step, must not abort the whole fixer run
            result["error"] = str(e)
            self._log(logging.WARNING, "💥 fsck(ext) failed for %s: %s", dev, str(e))
            return result

    def _run_xfs_repair(
        self,
        g: guestfs.GuestFS,
        dev: str,
        dry_run: bool,
        force_repair: bool = False,
        ctx: Any | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "tool": "xfs_repair",
            "device": dev,
            "dry_run": dry_run,
            "force_repair": force_repair,
            "success": False,
            "output": "",
            "error": None,
            "command": None,
            "tried": [],
        }

        if not self._has_command(g):
            result["error"] = "guestfs handle does not support command()"
            self._log(logging.WARNING, "⚠️ xfs_repair: %s no guestfs.command()", dev)
            return result

        try:
            memsize = self._get_guestfs_memsize_mib_best_effort(ctx)
            maxmem = self._xfs_safe_maxmem_mib(memsize)

            args: list[str] = ["xfs_repair", "-P", "-m", str(maxmem)]
            if dry_run:
                args.append("-n")
            elif force_repair:
                args.append("-L")
            args.append(dev)

            cmd = " ".join(args)
            self._log(
                logging.INFO,
                "🧠 xfs_repair mem: dev=%s memsize=%sMiB maxmem(-m)=%sMiB dry_run=%s force=%s",
                dev,
                str(memsize) if memsize else "unknown",
                maxmem,
                dry_run,
                force_repair,
            )
            self._log(logging.INFO, "🧰 xfs_repair: cmd=%s", cmd)

            out = g.command(args)
            result.update({"command": cmd, "output": U.to_text(out), "success": True})
            return result

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort repair step, must not abort the whole fixer run
            result["error"] = str(e)
            self._log(logging.WARNING, "💥 xfs_repair failed for %s: %s", dev, str(e))
            return result

    def _run_vfat_check(self, g: guestfs.GuestFS, dev: str, dry_run: bool) -> dict[str, Any]:
        result: dict[str, Any] = {
            "tool": "fsck.vfat",
            "device": dev,
            "dry_run": dry_run,
            "success": False,
            "output": "",
            "error": None,
            "command": None,
            "tried": [],
        }

        variants: list[list[str]] = (
            [["fsck.vfat", "-n", dev], ["fsck.vfat", dev]]
            if dry_run
            else [["fsck.vfat", "-a", dev], ["fsck.vfat", "-y", dev], ["fsck.vfat", dev]]
        )
        probe = self._run_variants_best_effort(g, variants, log_prefix="fsck.vfat")
        result.update(
            {
                "tried": probe.get("tried", []),
                "command": probe.get("command"),
                "output": probe.get("output", ""),
                "success": bool(probe.get("success")),
                "error": probe.get("error"),
            }
        )
        if result["success"]:
            self._log(logging.INFO, "🧰 fsck(vfat): %s dry_run=%s cmd=%s", dev, dry_run, result["command"])
        else:
            self._log(logging.WARNING, "💥 fsck.vfat failed for %s: %s", dev, result["error"])
        return result

    def _run_ntfs_check(self, g: guestfs.GuestFS, dev: str, dry_run: bool) -> dict[str, Any]:
        result: dict[str, Any] = {
            "tool": "ntfsfix",
            "device": dev,
            "dry_run": dry_run,
            "success": False,
            "output": "",
            "error": None,
            "command": None,
            "tried": [],
        }

        variants: list[list[str]] = (
            [["ntfsfix", "-n", dev], ["ntfsfix", dev]] if dry_run else [["ntfsfix", dev]]
        )
        probe = self._run_variants_best_effort(g, variants, log_prefix="ntfsfix")
        result.update(
            {
                "tried": probe.get("tried", []),
                "command": probe.get("command"),
                "output": probe.get("output", ""),
                "success": bool(probe.get("success")),
                "error": probe.get("error"),
            }
        )
        if result["success"]:
            self._log(logging.INFO, "🧰 ntfsfix: %s dry_run=%s cmd=%s", dev, dry_run, result["command"])
        else:
            self._log(logging.WARNING, "💥 ntfsfix failed for %s: %s", dev, result["error"])
        return result

    def _run_exfat_check(self, g: guestfs.GuestFS, dev: str, dry_run: bool) -> dict[str, Any]:
        result: dict[str, Any] = {
            "tool": "exfat",
            "device": dev,
            "dry_run": dry_run,
            "success": False,
            "output": "",
            "error": None,
            "command": None,
            "tried": [],
        }

        # Choose candidate without /bin/sh dependency
        candidates = ["fsck.exfat", "exfatfsck"]
        chosen: str | None = None
        for c in candidates:
            if self._probe_tool_exists(g, c):
                chosen = c
                break

        if not chosen:
            result["error"] = "No exFAT checker found (fsck.exfat/exfatfsck missing in appliance)"
            self._log(logging.INFO, "⏭️ exfat: %s no checker available in appliance", dev)
            return result

        if chosen == "fsck.exfat":
            variants = (
                [["fsck.exfat", "-n", dev], ["fsck.exfat", "--no-action", dev], ["fsck.exfat", dev]]
                if dry_run
                else [["fsck.exfat", "-a", dev], ["fsck.exfat", "-y", dev], ["fsck.exfat", dev]]
            )
        else:
            variants = (
                [["exfatfsck", "-n", dev], ["exfatfsck", dev]]
                if dry_run
                else [["exfatfsck", "-y", dev], ["exfatfsck", dev]]
            )

        probe = self._run_variants_best_effort(g, variants, log_prefix="exfat")
        result.update(
            {
                "tool": chosen,
                "tried": probe.get("tried", []),
                "command": probe.get("command"),
                "output": probe.get("output", ""),
                "success": bool(probe.get("success")),
                "error": probe.get("error"),
            }
        )
        if result["success"]:
            self._log(logging.INFO, "🧰 exfat: %s dry_run=%s cmd=%s", dev, dry_run, result["command"])
        else:
            self._log(logging.WARNING, "💥 exfat check failed for %s: %s", dev, result["error"])
        return result

    def _dispatch_action(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        # Each parameter is an independent input the dispatched repair tool needs.
        self,
        g: guestfs.GuestFS,
        dev: str,
        fs_norm: str,
        dry_run: bool,
        force_repair: bool,
        ctx: Any | None,
    ) -> dict[str, Any] | None:
        if fs_norm.startswith("ext"):
            return self._run_fsck_ext(g, dev, dry_run, force_repair)
        if fs_norm == "xfs":
            return self._run_xfs_repair(g, dev, dry_run, force_repair, ctx=ctx)
        if fs_norm == "vfat":
            return self._run_vfat_check(g, dev, dry_run)
        if fs_norm == "ntfs":
            return self._run_ntfs_check(g, dev, dry_run)
        if fs_norm == "exfat":
            return self._run_exfat_check(g, dev, dry_run)
        return None

    def _init_device_result(self, dev_text: str, dry_run: bool, force_repair: bool) -> dict[str, Any]:
        return {
            "device": dev_text,
            "fs_type": None,
            "fs_type_normalized": None,
            "classification": None,
            "dry_run": dry_run,
            "force_repair": force_repair,
            "action_result": None,
            "success": False,
            "warnings": [],
            "errors": [],
            "performed_repair": False,
        }

    def _detect_and_classify(self, g: guestfs.GuestFS, dev_text: str) -> tuple[str, str, dict[str, Any]]:
        fs_type = self._vfs_type(g, dev_text)
        fs_norm = self._normalize_fs_type(fs_type) if fs_type else ""
        classification = (
            self._classify_fs_type(fs_type)
            if fs_type
            else {
                "type": "",
                "type_normalized": "",
                "is_dangerous": False,
                "is_safe": False,
                "is_special": False,
                "can_check": False,
                "can_repair": False,
                "recommended_action": "skip",
            }
        )
        return fs_type, fs_norm, classification

    def _should_skip(
        self, dev_text: str, fs_type: str, classification: dict[str, Any], result: dict[str, Any]
    ) -> bool:
        if not fs_type:
            msg = "Could not detect filesystem type"
            result["errors"].append(msg)
            self._log(logging.WARNING, "⏭️ skip: %s (%s)", dev_text, msg)
            self._bump_stat("skipped")
            return True

        if classification.get("is_dangerous"):
            msg = f"Dangerous filesystem type: {fs_type}"
            result["errors"].append(msg)
            self._log(logging.WARNING, "☢️ skip dangerous: %s (%s)", dev_text, fs_type)
            self._bump_stat("skipped")
            return True

        if classification.get("is_special"):
            msg = f"Special filesystem type: {fs_type}"
            result["warnings"].append(msg)
            self._log(logging.INFO, "🧊 skip special: %s (%s)", dev_text, fs_type)
            self._bump_stat("skipped")
            return True

        if not classification.get("can_check"):
            msg = f"Cannot check filesystem type: {fs_type}"
            result["warnings"].append(msg)
            self._log(logging.INFO, "⏭️ skip: %s (%s)", dev_text, msg)
            self._bump_stat("skipped")
            return True

        return False

    def _run_device_action(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        # Each parameter is an independent input/output the per-device action needs.
        self,
        g: guestfs.GuestFS,
        dev_text: str,
        fs_type: str,
        fs_norm: str,
        dry_run: bool,
        force_repair: bool,
        ctx: Any | None,
        result: dict[str, Any],
    ) -> None:
        self._log(logging.INFO, "🔧 checking: %s (%s -> %s) dry_run=%s", dev_text, fs_type, fs_norm, dry_run)
        self._bump_stat("checked")

        action = self._dispatch_action(g, dev_text, fs_norm, dry_run, force_repair, ctx)
        if action is None:
            msg = f"No handler for filesystem type: {fs_type} (normalized={fs_norm})"
            result["warnings"].append(msg)
            self._log(logging.INFO, "🤷 no handler: %s (%s)", dev_text, msg)
            self._bump_stat("skipped")
            return

        result["action_result"] = action
        result["success"] = bool(action.get("success"))
        result["performed_repair"] = bool(result["success"] and (not dry_run))

        if result["success"] and not dry_run:
            self._bump_stat("repaired")
            self._bump_stat("repairs_attempted")
            self._log(logging.INFO, "✅ repaired (attempted): %s (%s -> %s)", dev_text, fs_type, fs_norm)
        elif result["success"]:
            self._log(logging.INFO, "✅ checked: %s (%s -> %s)", dev_text, fs_type, fs_norm)
        else:
            self._log(
                logging.WARNING,
                "⚠️ check finished but not marked success: %s (%s -> %s) err=%s",
                dev_text,
                fs_type,
                fs_norm,
                (action or {}).get("error"),
            )

    def check_and_repair(
        self,
        g: guestfs.GuestFS,
        dev: str,
        dry_run: bool = True,
        force_repair: bool = False,
        ctx: Any | None = None,
    ) -> dict[str, Any]:
        """
        Per-device check/repair entrypoint (refactored into small helpers).
        """
        t0 = self._now()
        self.stats["start_time"] = self.stats["start_time"] or t0
        self._bump_stat("total_devices")

        dev_text = U.to_text(dev)
        result = self._init_device_result(dev_text, dry_run, force_repair)

        self._log(logging.INFO, "🧪 fs check: dev=%s dry_run=%s force=%s", dev_text, dry_run, force_repair)

        try:
            fs_type, fs_norm, classification = self._detect_and_classify(g, dev_text)
            result["fs_type"] = fs_type
            result["fs_type_normalized"] = fs_norm
            result["classification"] = classification

            self._log(
                logging.DEBUG,
                "🧭 classify: %s -> %s",
                dev_text,
                {
                    "type": classification.get("type"),
                    "norm": classification.get("type_normalized"),
                    "dangerous": classification.get("is_dangerous"),
                    "safe": classification.get("is_safe"),
                    "special": classification.get("is_special"),
                    "action": classification.get("recommended_action"),
                },
            )

            if self._should_skip(dev_text, fs_type, classification, result):
                result["duration"] = self._now() - t0
                self.stats["end_time"] = self._now()
                return result

            self._run_device_action(
                g=g,
                dev_text=dev_text,
                fs_type=fs_type,
                fs_norm=fs_norm,
                dry_run=dry_run,
                force_repair=force_repair,
                ctx=ctx,
                result=result,
            )

        except Exception as e:  # pylint: disable=broad-exception-caught  # per-device check/repair, must not abort the whole run over one device's failure
            msg = f"Check/repair failed: {e!s}"
            result["errors"].append(msg)
            self._log(logging.ERROR, "💥 check/repair failed for %s: %s", dev_text, str(e))
            self._bump_stat("errors")

        result["duration"] = self._now() - t0
        self.stats["end_time"] = self._now()
        return result

    def get_stats(self) -> dict[str, Any]:
        """Return a copy of the run statistics, with `total_duration` filled in."""
        stats = self.stats.copy()
        if stats.get("end_time") and stats.get("start_time"):
            stats["total_duration"] = stats["end_time"] - stats["start_time"]
        stats["repairs_attempted"] = stats.get("repairs_attempted", stats.get("repaired", 0))
        return stats


def _vfs_type(g: guestfs.GuestFS, dev: str) -> str:
    """Module-level convenience wrapper around FilesystemFixer's vfs_type detection."""
    fixer = FilesystemFixer()
    return fixer._vfs_type(g, dev)  # pylint: disable=protected-access  # same-module reuse of the fixer's internal detection logic


def log_vfs_type_best_effort(ctx: Any, g: guestfs.GuestFS, dev: str) -> None:
    """Detect and log `dev`'s filesystem type, storing it on `ctx.root_fstype` if present."""
    fixer = FilesystemFixer(ctx.logger if hasattr(ctx, "logger") else None)
    try:
        vt = fixer._vfs_type(g, dev)  # pylint: disable=protected-access  # same-module reuse of the fixer's internal detection logic
        if vt:
            # Store on ctx so is_windows() can use it without calling g.vfs_type()
            if hasattr(ctx, "root_fstype"):
                ctx.root_fstype = vt
            if hasattr(ctx, "logger") and ctx.logger:
                ctx.logger.info("🧬 Root vfs_type(%s) = %s", dev, vt)
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort informational logging, must never abort the caller
        pass


def best_effort_fsck(ctx: Any, g: guestfs.GuestFS, dev: str) -> dict[str, Any]:
    """Run check_and_repair for `dev` and return a flattened best-effort result summary."""
    fixer = FilesystemFixer(ctx.logger if hasattr(ctx, "logger") else None)
    dry_run = bool(getattr(ctx, "dry_run", False))
    result = fixer.check_and_repair(g, dev, dry_run=dry_run, ctx=ctx)

    return {
        "attempted": result["success"] or bool(result.get("action_result")),
        "fstype": result.get("fs_type"),
        "fstype_normalized": result.get("fs_type_normalized"),
        "mode": "dry_run" if dry_run else "repair",
        "ok": result["success"],
        "performed_repair": result.get("performed_repair", False),
        "error": "\n".join(result.get("errors", [])) if result.get("errors") else None,
        "cmd": (result.get("action_result") or {}).get("command"),
        "tool": (result.get("action_result") or {}).get("tool"),
        "tried": (result.get("action_result") or {}).get("tried", []),
        "classification": result.get("classification"),
        "warnings": result.get("warnings", []),
    }


# Orchestrated "fix all filesystems" entrypoint (also refactored)


def _umount_all_best_effort(ctx: Any, g: guestfs.GuestFS, logger: logging.Logger | None) -> None:
    """Unmount everything via ctx's own helper if present, else fall back to g.umount_all()."""
    try:
        if hasattr(ctx, "_safe_umount_all"):
            if logger:
                logger.debug("🔻 umount: using ctx._safe_umount_all()")
            ctx._safe_umount_all(g)  # pylint: disable=protected-access  # part of the fixers' shared ctx protocol
            return
        try:
            if logger:
                logger.debug("🔻 umount: using g.umount_all()")
            g.umount_all()
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort unmount, must not abort the fixer run
            if logger:
                logger.debug("🫥 umount_all failed (ignored): %s", str(e))
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort unmount, must not abort the fixer run
        if logger:
            logger.warning("⚠️ umount step failed: %s", str(e))
        # Caller can decide whether to record as warning in audit


def _list_candidate_devices(g: guestfs.GuestFS) -> list[tuple[str, str]]:
    """
    Return devices as (dev, hinted_fstype) from guestfs list_filesystems(),
    filtering obvious non-dev paths and obvious non-filesystem entries.
    """
    devices: list[tuple[str, str]] = []
    fsmap = g.list_filesystems() or {}
    for dev, fstype in fsmap.items():
        d = U.to_text(dev)
        t = U.to_text(fstype)
        if not d.startswith("/dev/"):
            continue

        t_norm = (t or "").lower().replace("-", "_")
        if t_norm in ("swap", "crypto_luks", "lvm2_member"):
            continue

        devices.append((d, t))
    return devices


def _sort_devices_root_first(devices: list[tuple[str, str]], root_dev: str) -> list[tuple[str, str]]:
    if not root_dev:
        return devices
    return sorted(devices, key=lambda x: (0 if x[0] == root_dev else 1, x[0]))


def _update_classification_summary(summary: dict[str, int], classification: dict[str, Any] | None) -> None:
    c = classification or {}
    if c.get("is_dangerous"):
        summary["dangerous"] += 1
    elif c.get("is_safe"):
        summary["safe"] += 1
    elif c.get("is_special"):
        summary["special"] += 1
    else:
        summary["unknown"] += 1


def _finalize_audit(
    audit: dict[str, Any], fixer: FilesystemFixer, devices: list[tuple[str, str]], dry_run: bool
) -> dict[str, Any]:
    stats = fixer.get_stats()
    audit["statistics"] = stats
    audit["summary"] = {
        "total_devices": len(devices),
        "successfully_checked": stats.get("checked", 0),
        "repairs_attempted": stats.get("repairs_attempted", stats.get("repaired", 0)) if not dry_run else 0,
        "skipped": stats.get("skipped", 0),
        "errors": stats.get("errors", 0),
        "has_dangerous_filesystems": audit["classification_summary"]["dangerous"] > 0,
    }
    return audit


def fix_filesystems(ctx: Any, g: guestfs.GuestFS) -> dict[str, Any]:  # pylint: disable=too-many-branches
    """
    Offline filesystem fixer driver.
    - unmounts everything (best effort)
    - enumerates filesystem devices
    - runs per-device check/repair via FilesystemFixer
    - aggregates a detailed audit

    The branches are mostly independent optional-logging checks (`if logger:`)
    around each orchestration step; splitting further would obscure the flow.
    """
    enabled = bool(getattr(ctx, "filesystem_repair_enable", False))
    logger = ctx.logger if hasattr(ctx, "logger") else None

    if not enabled:
        if logger:
            logger.info("⏭️ filesystem fixer disabled (filesystem_repair_enable=false)")
        return {"enabled": False, "skipped": "filesystem_repair_disabled"}

    dry_run = bool(getattr(ctx, "dry_run", False))
    fixer = FilesystemFixer(logger)

    if logger:
        logger.info("🧰 filesystem fixer: enabled=true dry_run=%s", dry_run)

    audit: dict[str, Any] = {
        "enabled": True,
        "dry_run": dry_run,
        "fixer_version": "2.5",
        "devices_processed": [],
        "classification_summary": {"dangerous": 0, "safe": 0, "special": 0, "unknown": 0},
        "statistics": {},
        "errors": [],
        "warnings": [],
    }

    # Unmount first (best effort)
    try:
        _umount_all_best_effort(ctx, g, logger)
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort unmount step, must not abort the whole fixer run
        audit["warnings"].append(f"Unmount failed: {e!s}")

    # List devices
    try:
        devices = _list_candidate_devices(g)
    except Exception as e:  # pylint: disable=broad-exception-caught  # device enumeration failure is fatal for this run but must be reported, not crash the caller
        audit["errors"].append(f"list_filesystems failed: {e!s}")
        if logger:
            logger.exception("💥 list_filesystems failed: %s", str(e))
        return audit

    root_dev = U.to_text(getattr(ctx, "root_dev", "") or "").strip()
    devices = _sort_devices_root_first(devices, root_dev)

    if logger:
        logger.info("📦 filesystem devices: %d (root_dev=%s)", len(devices), root_dev or "unknown")
        logger.debug("🧾 devices: %s", [d for d, _t in devices])

    # Process devices
    for dev, hinted_fstype in devices:
        if logger:
            logger.info("➡️ device: %s (hint=%s)", dev, hinted_fstype or "n/a")

        device_result = fixer.check_and_repair(g, dev, dry_run=dry_run, ctx=ctx)
        audit["devices_processed"].append(device_result)

        _update_classification_summary(audit["classification_summary"], device_result.get("classification"))

        if device_result.get("errors"):
            audit["errors"].extend([f"{dev}: {err}" for err in device_result["errors"]])
            if logger:
                logger.warning("❌ device errors: %s => %s", dev, device_result["errors"])

        if device_result.get("warnings"):
            audit["warnings"].extend([f"{dev}: {warn}" for warn in device_result["warnings"]])
            if logger:
                logger.info("⚠️ device warnings: %s => %s", dev, device_result["warnings"])

    audit = _finalize_audit(audit, fixer, devices, dry_run)

    if logger:
        logger.info(
            "📊 fs summary: total=%d checked=%d repairs_attempted=%d skipped=%d errors=%d dangerous=%d",
            audit["summary"]["total_devices"],
            audit["summary"]["successfully_checked"],
            audit["summary"]["repairs_attempted"],
            audit["summary"]["skipped"],
            audit["summary"]["errors"],
            audit["classification_summary"]["dangerous"],
        )

    return audit
