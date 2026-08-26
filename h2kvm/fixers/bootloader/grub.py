# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
GRUB bootloader fixing for offline Linux VM migration.

Handles bootloader configuration stabilization, device.map cleanup, initramfs
regeneration, and bootloader reinstallation. Operates offline via VMCraft.

Philosophy:
- Anything that mutates kernel cmdline/bootloader config/initramfs belongs here
- Best-effort approach: failures should not hard-fail the overall conversion
- Mounts /boot and /boot/efi temporarily from fstab before regeneration
"""
# h2kvm/fixers/bootloader/grub.py
# pylint: disable=too-many-lines
# Cohesive GRUB bootloader fixer (device.map, initramfs, config regen, reinstall across
# distro families); splitting would hurt readability more than help.

from __future__ import annotations

import contextlib
import re
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from h2kvm.core.utils import U, guest_has_cmd
from h2kvm.fixers.filesystem.fstab import Ident, parse_btrfsvol_spec

if TYPE_CHECKING:
    from h2kvm.core.guestfs_typing import guestfs

# tiny helpers


def _logger(self):
    return getattr(self, "logger", None)


def _log_info(self, msg: str) -> None:
    lg = _logger(self)
    if lg:
        lg.info(msg)
    else:
        print(msg)


def _log_warn(self, msg: str) -> None:
    lg = _logger(self)
    if lg:
        lg.warning(msg)
    else:
        print(f"WARNING: {msg}")


def _log_debug(self, msg: str) -> None:
    lg = _logger(self)
    if lg:
        lg.debug(msg)


def _dedup_keep_order(xs: list[str]) -> list[str]:
    seen = set()
    out: list[str] = []
    for x in xs:
        s = (x or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _read_text(g: guestfs.GuestFS, path: str) -> str:
    try:
        return U.to_text(g.read_file(path)) if g.is_file(path) else ""
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        return ""


def _write_text(self, g: guestfs.GuestFS, path: str, text: str) -> None:
    if getattr(self, "dry_run", False):
        return
    if hasattr(self, "backup_file"):
        with contextlib.suppress(Exception):
            self.backup_file(g, path)
    g.write(path, text.encode("utf-8"))


def _append_text(self, g: guestfs.GuestFS, path: str, text: str) -> None:
    if getattr(self, "dry_run", False):
        return
    cur = _read_text(g, path) if g.is_file(path) else ""
    if hasattr(self, "backup_file") and g.is_file(path):
        with contextlib.suppress(Exception):
            self.backup_file(g, path)
    g.write(path, (cur + text).encode("utf-8"))


def _file_exists(g: guestfs.GuestFS, p: str) -> bool:
    try:
        return g.is_file(p)
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        return False


def _dir_exists(g: guestfs.GuestFS, p: str) -> bool:
    try:
        return g.is_dir(p)
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        return False


def _glob(g: guestfs.GuestFS, pattern: str) -> list[str]:
    try:
        return [U.to_text(x) for x in g.glob_expand(pattern)]
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        return []


def _run_guestfs_cmd(self, g: guestfs.GuestFS, cmd: list[str]) -> tuple[bool, str]:
    """
    Best-effort command execution via VMCraft.

    For bootloader commands (grub2-mkconfig, update-grub, etc.), uses command_with_mounts
    to provide /proc, /dev, /sys access. Falls back to command_quiet for other commands.

    Note: Bootloader commands need /proc/self/mountinfo and /dev to work properly.
    Failures are logged at DEBUG level only.
    """
    try:
        _log_info(self, f"Running (guestfs): {' '.join(cmd)}")

        # Commands that need /proc, /dev, /sys mounted inside chroot
        commands_needing_mounts = [
            "grub2-mkconfig",
            "grub-mkconfig",
            "update-grub",
            "update-grub2",
            "grub2-install",
            "grub-install",
            "grub2-probe",
            "grub-probe",
            "update-initramfs",
            "mkinitramfs",
            "dracut",
            "mkinitcpio",
            "mkinitrd",
            "mkinitfs",
            "booster",
            "genkernel",
            "kernel-install",
        ]

        # Check if this command needs bind mounts
        needs_mounts = any(cmd[0] == c for c in commands_needing_mounts) if cmd else False

        # Try command_with_mounts for commands needing /proc, /dev, /sys (VMCraft only)
        if needs_mounts and hasattr(g, "command_with_mounts"):
            _log_debug(self, f"Using chroot with bind mounts (/proc,/dev,/sys) for {cmd[0]}")
            out = g.command_with_mounts(cmd, quiet=True)
            return True, U.to_text(out)

        # Fall back to standard command_quiet
        out = g.command_quiet(cmd) if hasattr(g, "command_quiet") else g.command(cmd)
        return True, U.to_text(out)

    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        # Failure is expected in offline mode; already logged at DEBUG level
        return False, str(e)


def _run_guestfs_cmd_with_heartbeat(
    self,
    g,
    cmd: list[str],
    heartbeat_s: float = 10.0,
) -> tuple[bool, str, float]:
    """Run a guestfs command with periodic heartbeat logging.

    Long-running commands like dracut can take minutes inside the guest.
    This wrapper runs the command in a background thread and logs a
    heartbeat every *heartbeat_s* seconds so the user knows it's still
    working.

    Returns:
        (ok, output, elapsed_seconds)
    """
    result: list[tuple[bool, str]] = []

    def _worker():
        result.append(_run_guestfs_cmd(self, g, cmd))

    t0 = time.monotonic()
    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    while thread.is_alive():
        thread.join(timeout=heartbeat_s)
        if thread.is_alive():
            elapsed = time.monotonic() - t0
            _log_info(self, f"  ⏳ Still running ({elapsed:.0f}s elapsed)...")

    elapsed = time.monotonic() - t0

    if result:
        ok, out = result[0]
    else:
        ok, out = False, "Thread completed without result"

    return ok, out, elapsed


# distro / family hints


def _inspect_distro_major(self, g: guestfs.GuestFS) -> tuple[str, int]:
    distro = ""
    major = 0
    try:
        if getattr(self, "inspect_root", None):
            distro = (U.to_text(g.inspect_get_distro(self.inspect_root)) or "").lower()
            major = int(g.inspect_get_major_version(self.inspect_root) or 0)
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        pass

    # Extra: Photon sometimes comes back as "photon" or unknown; /etc/os-release is reliable.
    if not distro:
        osr = _read_text(g, "/etc/os-release")
        m = re.search(r'(?m)^\s*ID="?([^"\n]+)"?\s*$', osr)
        if m:
            distro = m.group(1).strip().lower()
    return distro, major


# Maps many distro name variants to a small set of families; each family is a
# distinct early return, so the count is inherent to the classification table.
# pylint: disable-next=too-many-return-statements
def _detect_family(distro: str) -> str:
    d = (distro or "").lower()

    # RHEL-ish (+ common derivatives and cloud distros)
    if d in (
        "fedora",
        "rhel",
        "centos",
        "circle",
        "scientificlinux",
        "redhat-based",
        "oraclelinux",
        "rocky",
        "almalinux",
        "amzn",
        "amazon",
        "amazonlinux",  # Amazon Linux
        "mariner",
        "cbl-mariner",  # Microsoft CBL-Mariner
        "mageia",
        "openmandriva",  # rpm-ish
        "photon",  # VMware Photon (tdnf + dracut)
    ):
        return "rhel"

    # SUSE-ish
    if d in ("sles", "sled", "suse-based", "opensuse", "opensuse-leap", "opensuse-tumbleweed"):
        return "suse"

    # Debian-ish
    if d in (
        "debian",
        "ubuntu",
        "linuxmint",
        "kalilinux",
        "kali",
        "raspbian",
        "pop",
        "popos",
        "elementary",
        "zorin",
        "deepin",
    ):
        return "debian"

    # Arch-ish
    if d in ("arch", "manjaro", "endeavouros", "garuda"):
        return "arch"

    # Alpine
    if d in ("alpine",):
        return "alpine"

    # Gentoo-ish
    if d in ("gentoo", "funtoo"):
        return "gentoo"

    # Void
    if d in ("void",):
        return "void"

    # NixOS
    if d in ("nixos",):
        return "nixos"

    return "other"


# Boot layout heuristics (offline)


def _guest_looks_uefi(g: guestfs.GuestFS) -> bool:
    # Strong: presence of an EFI tree with .efi binaries
    try:  # pylint: disable=too-many-nested-blocks
        for base in ("/boot/efi", "/efi"):
            if _dir_exists(g, base) and _dir_exists(g, f"{base}/EFI"):
                try:
                    for x in g.find(f"{base}/EFI"):
                        p = U.to_text(x)
                        if p.lower().endswith(".efi"):
                            return True
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
                    try:
                        return bool(g.ls(f"{base}/EFI"))
                    except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
                        pass
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        pass

    # Weak: fstab has /boot/efi vfat
    try:
        fstab = _read_text(g, "/etc/fstab")
        if re.search(r"^\S+\s+/(boot/efi|efi)\s+vfat\b", fstab, flags=re.M):
            return True
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        pass

    return False


def _guest_has_bls(g: guestfs.GuestFS) -> bool:
    return _dir_exists(g, "/boot/loader/entries")


# root= stabilization


def _stable_root_id(self, g: guestfs.GuestFS) -> str | None:
    """
    Compute a stable root identifier usable as kernel cmdline root=...
    Returns UUID=... / PARTUUID=... / LABEL=... best-effort.
    """
    root_dev = getattr(self, "root_dev", None)
    if not root_dev:
        return None

    # btrfsvol: underlying device
    if isinstance(root_dev, str) and root_dev.startswith("btrfsvol:"):
        dev, _sv = parse_btrfsvol_spec(root_dev)
        root_dev = dev.strip()

    # /dev/disk/by-* -> resolve to /dev/..
    if isinstance(root_dev, str) and root_dev.startswith("/dev/disk/by-"):
        try:
            rp = U.to_text(g.realpath(root_dev)).strip()
            if rp.startswith("/dev/"):
                root_dev = rp
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
            pass

    if not isinstance(root_dev, str) or not root_dev.startswith("/dev/"):
        return None

    blk = Ident.g_blkid_map(g, root_dev)
    stable = Ident.choose_stable(blk)

    # Sometimes root is a DM or btrfs wrapper; try "parent-ish" heuristic
    if not stable:
        try:
            parent = re.sub(r"p?\d+$", "", root_dev)
            if parent != root_dev and parent.startswith("/dev/"):
                blk2 = Ident.g_blkid_map(g, parent)
                stable2 = Ident.choose_stable(blk2)
                if stable2:
                    stable = stable2
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
            pass

    return stable


def _replace_root_tokens(text: str, new_root_token: str) -> str:
    """
    Replace any existing root=... in a cmdline-ish string with new_root_token.
    If no root= exists, append it (conservatively).
    """
    if re.search(r"\broot=\S+", text):
        return re.sub(r"\broot=\S+", new_root_token, text)

    # Append into GRUB_CMDLINE_* assignment lines or plain cmdline files.
    if text.strip() and not text.endswith("\n"):
        text += "\n"
    # best-effort: append root= at end of each non-comment line if it's a cmdline file
    if "\n" not in text.strip():
        return text.strip() + " " + new_root_token + "\n"
    return text


def _update_file_cmdline(self, g: guestfs.GuestFS, path: str, new_root_token: str) -> bool:
    old = _read_text(g, path)
    if not old:
        return False
    new = _replace_root_tokens(old, new_root_token)
    if new == old:
        return False
    _log_info(self, f"Updated root= in {path}" + (" (dry-run)" if self.dry_run else ""))
    if not getattr(self, "dry_run", False):
        _write_text(self, g, path, new)
    return True


def _update_bls_root(self, g: guestfs.GuestFS, new_root_token: str) -> int:
    changed = 0
    if not _dir_exists(g, "/boot/loader/entries"):
        return 0
    try:
        for ent in g.ls("/boot/loader/entries"):
            ent_s = U.to_text(ent).strip()
            if not ent_s.endswith(".conf"):
                continue
            p = f"/boot/loader/entries/{ent_s}"
            # BLS uses: options ...
            old = _read_text(g, p)
            if not old:
                continue
            lines = old.splitlines(True)
            out: list[str] = []
            did = False
            for ln in lines:
                if ln.lstrip().startswith("options "):
                    if re.search(r"\broot=\S+", ln):
                        ln2 = re.sub(r"\broot=\S+", new_root_token, ln)
                    else:
                        ln2 = ln.rstrip("\n") + " " + new_root_token + "\n"
                    did = did or (ln2 != ln)
                    out.append(ln2)
                else:
                    out.append(ln)
            new = "".join(out)
            if did and new != old:
                _log_info(self, f"Updated root= in {p}" + (" (dry-run)" if self.dry_run else ""))
                changed += 1
                if not getattr(self, "dry_run", False):
                    _write_text(self, g, p, new)
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        _log_warn(
            self,
            f"BLS update failed while updating root= in /boot/loader/entries/*.conf: {e}. "
            "The VM may fail to boot if root= points to the wrong device. "
            "Manually check BLS entries with: ls /boot/loader/entries/",
        )
    return changed


def _inject_serial_console_bls(self, g: guestfs.GuestFS, console_arg: str) -> int:
    """Inject console= argument into BLS entries if not already present."""
    changed = 0
    if not _dir_exists(g, "/boot/loader/entries"):
        return 0
    try:
        for ent in g.ls("/boot/loader/entries"):
            ent_s = U.to_text(ent).strip()
            if not ent_s.endswith(".conf"):
                continue
            p = f"/boot/loader/entries/{ent_s}"
            old = _read_text(g, p)
            if not old:
                continue
            if console_arg in old:
                continue
            lines = old.splitlines(True)
            out: list[str] = []
            did = False
            for ln in lines:
                if ln.lstrip().startswith("options "):
                    ln2 = ln.rstrip("\n") + " " + console_arg + "\n"
                    did = True
                    out.append(ln2)
                else:
                    out.append(ln)
            new = "".join(out)
            if did and new != old:
                _log_info(self, f"Injected serial console in {p}")
                changed += 1
                if not getattr(self, "dry_run", False):
                    _write_text(self, g, p, new)
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        _log_warn(
            self,
            f"BLS serial console injection failed while adding console=ttyS0 to /boot/loader/entries/*.conf: {e}. "
            "'virsh console' may not work after migration. "
            "Manually add 'console=ttyS0,115200' to the 'options' line in BLS entry files.",
        )
    return changed


def inject_serial_console(self, g: guestfs.GuestFS) -> dict[str, Any]:
    """
    Inject serial console configuration into guest bootloader.

    Adds console=ttyS0,115200 to kernel cmdline and configures GRUB
    serial terminal output so `virsh console` works after conversion.

    Gated by self.serial_console (bool, default True for headless).
    """
    if not getattr(self, "serial_console", False):
        return {"enabled": False, "reason": "serial_console_disabled"}

    console_arg = "console=ttyS0,115200"
    info: dict[str, Any] = {"enabled": True, "console_arg": console_arg}

    p = "/etc/default/grub"
    changed = 0

    # 1) Update /etc/default/grub: inject console= into GRUB_CMDLINE_LINUX
    if _file_exists(g, p):
        old = _read_text(g, p)
        new = old

        # Inject console= into GRUB_CMDLINE_LINUX if not present
        if console_arg not in old:

            def _inject_console(m: re.Match[str]) -> str:
                line = m.group(0)
                match_eq = re.search(r"=\s*(.*)$", line)
                if not match_eq:
                    return line
                value_part = match_eq.group(1).rstrip()
                if value_part.startswith('"') and value_part.endswith('"'):
                    inner = value_part[1:-1]
                    return line[: match_eq.start(1)] + f'"{inner} {console_arg}"'
                if value_part.startswith("'") and value_part.endswith("'"):
                    inner = value_part[1:-1]
                    return line[: match_eq.start(1)] + f"'{inner} {console_arg}'"
                return line[: match_eq.start(1)] + f'"{value_part} {console_arg}"'

            new = re.sub(r"(?m)^\s*GRUB_CMDLINE_LINUX=.*$", _inject_console, new)

        # Add/update GRUB_TERMINAL_OUTPUT to include serial
        if re.search(r"(?m)^\s*GRUB_TERMINAL_OUTPUT=", new):
            if "serial" not in new.split("GRUB_TERMINAL_OUTPUT")[1].split("\n")[0]:
                new = re.sub(
                    r'(?m)^(\s*GRUB_TERMINAL_OUTPUT=)"?([^"\n]*)"?\s*$',
                    r'\1"serial console"',
                    new,
                )
        else:
            new += '\nGRUB_TERMINAL_OUTPUT="serial console"\n'

        # Add GRUB_SERIAL_COMMAND if not present
        if "GRUB_SERIAL_COMMAND" not in new:
            new += 'GRUB_SERIAL_COMMAND="serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1"\n'

        if new != old:
            _log_info(self, "Injected serial console config in /etc/default/grub")
            changed += 1
            if not getattr(self, "dry_run", False):
                _write_text(self, g, p, new)

    info["default_grub_changed"] = changed

    # 2) Update BLS entries
    bls_changed = _inject_serial_console_bls(self, g, console_arg)
    info["bls_entries_changed"] = bls_changed

    # 3) Update /etc/kernel/cmdline if present
    kc_path = "/etc/kernel/cmdline"
    if _file_exists(g, kc_path):
        kc_old = _read_text(g, kc_path)
        if console_arg not in kc_old:
            kc_new = kc_old.rstrip() + " " + console_arg + "\n"
            _log_info(self, f"Injected serial console in {kc_path}")
            if not getattr(self, "dry_run", False):
                _write_text(self, g, kc_path, kc_new)
            info["kernel_cmdline_changed"] = True

    _log_info(self, f"Serial console injection: default_grub={changed}, bls={bls_changed}")
    return info


def _update_default_grub(self, g: guestfs.GuestFS, new_root_token: str) -> int:
    """
    Update GRUB_CMDLINE_LINUX* in /etc/default/grub (if present).
    """
    p = "/etc/default/grub"
    if not _file_exists(g, p):
        return 0
    old = _read_text(g, p)
    if not old:
        return 0

    # Each quote-style variant (double/single/unterminated/unquoted) is a distinct
    # early return; the count is inherent to correctly rewriting all of them.
    def repl(m: re.Match[str]) -> str:  # pylint: disable=too-many-return-statements
        line = m.group(0)

        # Replace existing root= parameter if found
        if re.search(r"\broot=\S+", line):
            return re.sub(r"\broot=\S+", new_root_token, line)

        # Find the value part after the = sign
        match_eq = re.search(r"=\s*(.*)$", line)
        if not match_eq:
            return line  # No = sign found, skip

        value_part = match_eq.group(1).rstrip()

        # Detect quote style
        if value_part.startswith('"') and value_part.endswith('"'):
            # Double-quoted value - insert before closing quote
            inner = value_part[1:-1]
            new_value = f'"{inner} {new_root_token}"' if inner.strip() else f'"{new_root_token}"'
            return line[: match_eq.start(1)] + new_value
        if value_part.startswith("'") and value_part.endswith("'"):
            # Single-quoted value - insert before closing quote
            inner = value_part[1:-1]
            new_value = f"'{inner} {new_root_token}'" if inner.strip() else f"'{new_root_token}'"
            return line[: match_eq.start(1)] + new_value
        if value_part.startswith('"'):
            # Double quote opened but not closed - append before newline and add closing quote
            inner = value_part[1:]
            new_value = f'"{inner} {new_root_token}"' if inner.strip() else f'"{new_root_token}"'
            return line[: match_eq.start(1)] + new_value
        if value_part.startswith("'"):
            # Single quote opened but not closed - append before newline and add closing quote
            inner = value_part[1:]
            new_value = f"'{inner} {new_root_token}'" if inner.strip() else f"'{new_root_token}'"
            return line[: match_eq.start(1)] + new_value
        # No quotes - wrap in quotes
        if value_part.strip():
            return line[: match_eq.start(1)] + f'"{value_part} {new_root_token}"'
        return line[: match_eq.start(1)] + f'"{new_root_token}"'

    new = re.sub(r"(?m)^\s*GRUB_CMDLINE_LINUX(?:_DEFAULT)?=.*$", repl, old)
    if new == old:
        return 0

    _log_info(self, f"Updated root= in {p}" + (" (dry-run)" if self.dry_run else ""))
    if not getattr(self, "dry_run", False):
        _write_text(self, g, p, new)
    return 1


def _update_kernel_cmdline_file(self, g: guestfs.GuestFS, new_root_token: str) -> int:
    # systemd kernel-install uses /etc/kernel/cmdline on some distros
    p = "/etc/kernel/cmdline"
    if _file_exists(g, p) and _update_file_cmdline(self, g, p, new_root_token):
        return 1
    return 0


def _update_grub_cfg_fallback(self, g: guestfs.GuestFS, new_root_token: str) -> int:
    """
    Fallback only: treat grub.cfg as generated output. Still useful when users ship static cfg.
    """
    changed = 0
    for p in ("/boot/grub2/grub.cfg", "/boot/grub/grub.cfg"):
        if _file_exists(g, p) and _update_file_cmdline(self, g, p, new_root_token):
            changed += 1
    return changed


def _update_extlinux_syslinux_fallback(self, g: guestfs.GuestFS, new_root_token: str) -> int:
    changed = 0
    candidates = (
        "/boot/extlinux/extlinux.conf",
        "/extlinux/extlinux.conf",
        "/boot/syslinux/syslinux.cfg",
        "/syslinux/syslinux.cfg",
    )
    for p in candidates:
        if _file_exists(g, p) and _update_file_cmdline(self, g, p, new_root_token):
            changed += 1
    return changed


def update_grub_root(self, g: guestfs.GuestFS) -> int:
    """
    Public API used by OfflineFSFix:
      - respects self.update_grub boolean
      - rewrites root= to stable token in BLS, /etc/kernel/cmdline, /etc/default/grub
      - falls back to grub.cfg and extlinux/syslinux configs
    """
    if not getattr(self, "update_grub", False):
        return 0

    stable = _stable_root_id(self, g)
    if not stable:
        _log_warn(
            self,
            f"boot: could not determine a stable identifier (UUID/PARTUUID/LABEL) for root device "
            f"'{getattr(self, 'root_dev', 'unknown')}'; skipping root= update. "
            "The VM may fail to boot if device names change. "
            "Run 'blkid' on the disk to verify filesystem UUIDs exist.",
        )
        return 0

    new_root_token = f"root={stable}"
    looks_uefi = _guest_looks_uefi(g)
    has_bls = _guest_has_bls(g)
    _log_info(self, f"Boot heuristics: {'UEFI' if looks_uefi else 'BIOS'}; BLS={'yes' if has_bls else 'no'}")
    _log_info(self, f"Setting kernel cmdline {new_root_token}")

    changed = 0
    if has_bls:
        changed += _update_bls_root(self, g, new_root_token)
    changed += _update_kernel_cmdline_file(self, g, new_root_token)
    changed += _update_default_grub(self, g, new_root_token)
    changed += _update_grub_cfg_fallback(self, g, new_root_token)
    changed += _update_extlinux_syslinux_fallback(self, g, new_root_token)
    return changed


# GRUB device.map cleanup


def remove_stale_device_map(self, g: guestfs.GuestFS) -> int:
    """
    Removes stale GRUB device.map files that often break after controller/bus changes.
    """
    removed = 0
    for p in ("/boot/grub2/device.map", "/boot/grub/device.map", "/etc/grub2-device.map"):
        try:
            if _file_exists(g, p):
                txt = _read_text(g, p)
                # any content is suspect; but keep heuristic to avoid nuking custom ones
                if "hd0" in txt or "sda" in txt or "vda" in txt or "nvme" in txt:
                    _log_info(
                        self,
                        f"GRUB: removing stale device.map: {p}" + (" (dry-run)" if self.dry_run else ""),
                    )
                    removed += 1
                    if not getattr(self, "dry_run", False):
                        g.rm_f(p)
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
            continue
    return removed


# initramfs driver injection (boot-relevant, keep here)


# Probes multiple search directories and compressed-module suffixes to determine
# module availability; the branch count reflects the real number of distinct checks.
# pylint: disable-next=too-many-branches
def _find_available_modules(g: guestfs.GuestFS, kver: str, candidates: list[str]) -> list[str]:
    """
    Check which candidate modules actually exist in the guest kernel modules directory.

    Args:
        g: GuestFS instance
        kver: Kernel version (e.g., "4.18.0-348.el8.x86_64")
        candidates: List of module names to check (without .ko extension)

    Returns:
        List of modules that actually exist on the guest system
    """
    available = []
    modules_base = f"/lib/modules/{kver}"

    # Check if modules directory exists
    try:
        if not g.is_dir(modules_base):
            return []
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        return []

    # Common module search paths within /lib/modules/<kver>/
    search_dirs = [
        f"{modules_base}/kernel/drivers/block",
        f"{modules_base}/kernel/drivers/scsi",
        f"{modules_base}/kernel/drivers/net",
        f"{modules_base}/kernel/drivers/virtio",
        f"{modules_base}/kernel/drivers/nvme/host",
        f"{modules_base}/kernel/drivers/ata",
        f"{modules_base}/kernel/drivers/md",
        f"{modules_base}/kernel/crypto",
    ]

    # Also check the modules.builtin file for built-in modules
    builtin_modules = set()
    builtin_path = f"{modules_base}/modules.builtin"
    try:
        if g.is_file(builtin_path):
            builtin_content = g.read_file(builtin_path)
            # modules.builtin has paths like kernel/drivers/block/virtio_blk.ko
            for line in builtin_content.splitlines():
                # Extract module name from path
                if line.strip() and line.endswith(".ko"):
                    mod_name = line.rsplit("/", 1)[-1].replace(".ko", "")
                    builtin_modules.add(mod_name)
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        pass

    # Check each candidate module
    for mod_name in candidates:  # pylint: disable=too-many-nested-blocks
        # Check if it's built-in
        if mod_name in builtin_modules:
            available.append(mod_name)
            continue

        # Check if .ko file exists in any search directory
        found = False
        for search_dir in search_dirs:
            try:
                if not g.is_dir(search_dir):
                    continue

                # Check for both .ko and .ko.xz (compressed modules)
                for files in [g.ls(search_dir)]:
                    for file in files:
                        if file in [f"{mod_name}.ko", f"{mod_name}.ko.xz", f"{mod_name}.ko.gz"]:
                            available.append(mod_name)
                            found = True
                            break
                    if found:
                        break
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
                continue

            if found:
                break

    return available


def _get_initramfs_add_drivers(self) -> list[str]:
    """
    Knob sources (highest → lowest):
      1) self.initramfs_add_drivers (list[str] or "a b c")
      2) self.regen_add_drivers (legacy alias)
      3) sane defaults (virtio-ish + common crypto mode)
    """
    val = getattr(self, "initramfs_add_drivers", None) or getattr(self, "regen_add_drivers", None)
    if val:
        if isinstance(val, str):
            drivers = [x for x in val.split() if x.strip()]
        else:
            drivers = [str(x).strip() for x in list(val) if str(x).strip()]
        return _dedup_keep_order(drivers)

    # Default drivers for KVM/virtio migration
    # Keep legacy virtio aliases for compatibility with existing configs/tests.
    # Non-existent modules are filtered later against available kernel modules.
    return _dedup_keep_order(
        [
            "virtio",
            "virtio_ring",
            "virtio_blk",
            "virtio_scsi",
            "virtio_net",
            "virtio_pci",
            "nvme",
            "ahci",
            "sd_mod",
            "dm_mod",
            "dm_crypt",
            "xts",
        ]
    )


def _write_modules_linefile(self, g: guestfs.GuestFS, path: str, drivers: list[str]) -> dict[str, Any]:
    drivers = _dedup_keep_order(drivers)
    if not drivers:
        return {"path": path, "changed": False, "reason": "no_drivers"}

    before = _read_text(g, path)
    before_lines = [
        ln.strip() for ln in before.splitlines() if ln.strip() and not ln.strip().startswith("#")
    ]
    missing = [d for d in drivers if d not in before_lines]
    if not missing:
        return {"path": path, "changed": False, "reason": "already_present"}

    new = before.rstrip() + ("\n" if before and not before.endswith("\n") else "")
    new += "# Added by h2kvm (initramfs driver injection)\n"
    for d in missing:
        new += f"{d}\n"

    if getattr(self, "dry_run", False):
        return {"path": path, "changed": True, "dry_run": True, "added": missing}

    _write_text(self, g, path, new)
    return {"path": path, "changed": True, "added": missing}


# Distinct early returns for each no-op/dry-run/changed outcome of the MODULES= patch.
# pylint: disable-next=too-many-return-statements
def _patch_mkinitcpio_modules(self, g: guestfs.GuestFS, drivers: list[str]) -> dict[str, Any]:
    path = "/etc/mkinitcpio.conf"
    drivers = _dedup_keep_order(drivers)
    if not drivers:
        return {"path": path, "changed": False, "reason": "no_drivers"}
    if not _file_exists(g, path):
        return {"path": path, "changed": False, "reason": "missing"}

    old = _read_text(g, path)
    m = re.search(r"(?m)^\s*MODULES=\((.*?)\)\s*$", old)
    if not m:
        insert = "MODULES=(" + " ".join(drivers) + ")\n"
        new = old.rstrip() + "\n\n" + insert
        if getattr(self, "dry_run", False):
            return {
                "path": path,
                "changed": True,
                "dry_run": True,
                "added": drivers,
                "note": "MODULES_line_added",
            }
        _write_text(self, g, path, new)
        return {"path": path, "changed": True, "added": drivers, "note": "MODULES_line_added"}

    inner = m.group(1).strip()
    cur = [x for x in inner.split() if x.strip()]
    merged = _dedup_keep_order(cur + drivers)
    if merged == cur:
        return {"path": path, "changed": False, "reason": "already_present"}

    new_line = "MODULES=(" + " ".join(merged) + ")"
    new = re.sub(r"(?m)^\s*MODULES=\(.*?\)\s*$", new_line, old, count=1)
    if getattr(self, "dry_run", False):
        return {
            "path": path,
            "changed": True,
            "dry_run": True,
            "added": [d for d in drivers if d not in cur],
        }

    _write_text(self, g, path, new)
    return {"path": path, "changed": True, "added": [d for d in drivers if d not in cur]}


def _patch_suse_sysconfig_initrd_modules(self, g: guestfs.GuestFS, drivers: list[str]) -> dict[str, Any]:
    path = "/etc/sysconfig/kernel"
    drivers = _dedup_keep_order(drivers)
    if not drivers:
        return {"path": path, "changed": False, "reason": "no_drivers"}
    if not _file_exists(g, path):
        return {"path": path, "changed": False, "reason": "missing"}

    old = _read_text(g, path)
    if re.search(r"(?m)^\s*INITRD_MODULES=", old):

        def _repl(m: re.Match[str]) -> str:
            cur_s = (m.group(1) or "").strip()
            cur = [x for x in cur_s.split() if x.strip()]
            merged = _dedup_keep_order(cur + drivers)
            return f'INITRD_MODULES="{" ".join(merged)}"'

        new = re.sub(r'(?m)^\s*INITRD_MODULES="([^"]*)"\s*$', _repl, old, count=1)
    else:
        new = old.rstrip() + '\nINITRD_MODULES="' + " ".join(drivers) + '"\n'

    if new == old:
        return {"path": path, "changed": False, "reason": "already_present"}

    if getattr(self, "dry_run", False):
        return {"path": path, "changed": True, "dry_run": True, "note": "suse_sysconfig"}

    _write_text(self, g, path, new)
    return {"path": path, "changed": True, "note": "suse_sysconfig"}


def _patch_modules_load_d(self, g: guestfs.GuestFS, drivers: list[str]) -> dict[str, Any]:
    """
    Cross-distro fallback: ensure modules are loaded at boot via modules-load.d.
    This does NOT guarantee availability in early initramfs, but helps for some guests.
    """
    path = "/etc/modules-load.d/h2kvm.conf"
    drivers = _dedup_keep_order(drivers)
    if not drivers:
        return {"path": path, "changed": False, "reason": "no_drivers"}

    existing = _read_text(g, path) if _file_exists(g, path) else ""
    existing_lines = {
        ln.strip() for ln in existing.splitlines() if ln.strip() and not ln.strip().startswith("#")
    }

    missing = [d for d in drivers if d not in existing_lines]
    if not missing:
        return {"path": path, "changed": False, "reason": "already_present"}

    new = existing.rstrip() + ("\n" if existing and not existing.endswith("\n") else "")
    new += "# Added by h2kvm (modules-load.d fallback)\n"
    for d in missing:
        new += f"{d}\n"

    if getattr(self, "dry_run", False):
        return {"path": path, "changed": True, "dry_run": True, "added": missing}

    _write_text(self, g, path, new)
    return {"path": path, "changed": True, "added": missing, "note": "modules_load_d_fallback"}


def _detect_lvm_in_guest(g: guestfs.GuestFS) -> dict[str, Any]:
    """
    Detect if LVM is present in the guest system.
    Returns dict with:
      - has_lvm: bool
      - vgs: list of volume group names
      - lvs: list of logical volume paths
      - pvs: list of physical volume paths
    """
    result = {"has_lvm": False, "vgs": [], "lvs": [], "pvs": []}

    try:
        # Check for LVM physical volumes
        pvs = g.pvs()
        if pvs:
            result["pvs"] = [U.to_text(pv) for pv in pvs]
            result["has_lvm"] = True
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        pass

    try:
        # Check for volume groups
        vgs = g.vgs()
        if vgs:
            result["vgs"] = [U.to_text(vg) for vg in vgs]
            result["has_lvm"] = True
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        pass

    try:
        # Check for logical volumes
        lvs = g.lvs()
        if lvs:
            result["lvs"] = [U.to_text(lv) for lv in lvs]
            result["has_lvm"] = True
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        pass

    return result


def _ensure_var_tmp(g: guestfs.GuestFS) -> dict[str, Any]:
    """
    Ensure /var/tmp exists with proper permissions.
    dracut requires /var/tmp to exist and be writable.
    Returns dict with created: bool, existed: bool.
    """
    result = {"existed": False, "created": False, "error": None}

    try:
        # Check if /var/tmp exists - use helper to avoid type issues
        if _dir_exists(g, "/var/tmp"):
            result["existed"] = True
            # Ensure proper permissions (1777 = sticky bit + rwx for all)
            try:
                g.chmod(0o1777, "/var/tmp")
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
                pass  # Best effort
            return result

        # Create /var/tmp with sticky bit
        g.mkdir_p("/var/tmp")
        try:
            g.chmod(0o1777, "/var/tmp")
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
            pass  # Not all guestfs versions support chmod
        result["created"] = True
        return result
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        result["error"] = str(e)
        return result


def _maybe_add_dracut_drivers(cmd: list[str], drivers: list[str]) -> list[str]:
    if not cmd or cmd[0] != "dracut":
        return cmd
    if not drivers:
        return cmd
    # If caller already set add-drivers, don't stomp.
    if "--add-drivers" in cmd:
        return cmd
    return [*cmd, "--add-drivers", " ".join(drivers)]


def _maybe_add_dracut_lvm(cmd: list[str], has_lvm: bool) -> list[str]:
    """
    Add LVM/device-mapper dracut hooks if LVM is detected.
    Adds --add 'lvm dm' to ensure initramfs can activate LVM devices at boot.
    """
    if not cmd or cmd[0] != "dracut":
        return cmd
    if not has_lvm:
        return cmd
    # If caller already set --add, don't stomp
    if "--add" in cmd:
        return cmd
    return [*cmd, "--add", "lvm dm"]


# fstab-based /boot, /boot/efi mounting (critical for correct regen)


@dataclass
class _MountSpec:
    spec: str
    mountpoint: str
    fstype: str
    options: str


def _parse_fstab_mounts(g: guestfs.GuestFS) -> list[_MountSpec]:
    txt = _read_text(g, "/etc/fstab")
    out: list[_MountSpec] = []
    for ln in txt.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        cols = s.split()
        if len(cols) < 4:
            continue
        out.append(_MountSpec(spec=cols[0], mountpoint=cols[1], fstype=cols[2], options=cols[3]))
    return out


# Each spec kind (UUID/LABEL/PARTUUID/by-*/btrfsvol) is a distinct resolution
# path with its own early return; branch/return count is inherent to covering them all.
# 'self' is unused but kept for consistency with this module's other _helper(self, g, ...) calls.
# pylint: disable-next=too-many-return-statements,too-many-branches,unused-argument
def _resolve_spec_to_dev(self, g: guestfs.GuestFS, spec: str) -> str | None:
    """
    Convert fstab spec to a /dev/... node (best-effort):
      - /dev/* direct
      - UUID= / LABEL= via guestfs findfs helpers
      - PARTUUID= via blkid scan (Ident)
      - /dev/disk/by-* via realpath
      - btrfsvol:... unwrap device
    """
    if not spec:
        return None

    if spec.startswith("btrfsvol:"):
        dev, _sv = parse_btrfsvol_spec(spec)
        spec = dev.strip()

    if spec.startswith("/dev/disk/by-"):
        try:
            rp = U.to_text(g.realpath(spec)).strip()
            if rp.startswith("/dev/"):
                return rp
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
            return None

    if spec.startswith("/dev/"):
        return spec

    m = re.match(r"^(UUID|LABEL|PARTUUID)=(.+)$", spec)
    if not m:
        return None

    kind = m.group(1)
    val = m.group(2).strip().strip('"').strip("'")

    try:
        if kind == "UUID" and hasattr(g, "findfs_uuid"):
            dev = U.to_text(g.findfs_uuid(val)).strip()
            return dev if dev.startswith("/dev/") else None
        if kind == "LABEL" and hasattr(g, "findfs_label"):
            dev = U.to_text(g.findfs_label(val)).strip()
            return dev if dev.startswith("/dev/") else None
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        pass

    if kind == "PARTUUID":
        # brute-force: scan candidates from list_filesystems + partitions, match PARTUUID
        candidates: list[str] = []
        with contextlib.suppress(Exception):
            candidates.extend([U.to_text(p) for p in (g.list_partitions() or [])])
        try:
            fsmap = g.list_filesystems() or {}
            for d in fsmap:
                dd = U.to_text(d)
                if dd.startswith("/dev/"):
                    candidates.append(dd)
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
            pass

        for dev in _dedup_keep_order(candidates):
            try:
                blk = Ident.g_blkid_map(g, dev)
                if (blk.get("PARTUUID") or "").strip() == val:
                    return dev
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
                continue

    return None


def _mount_boot_partitions_best_effort(self, g: guestfs.GuestFS) -> dict[str, Any]:
    """
    Mount /boot and /boot/efi (or /efi) from fstab if present.
    Returns audit + list of mounted mountpoints to unmount later.
    """
    audit: dict[str, Any] = {"attempted": True, "mounted": [], "errors": []}
    if not _file_exists(g, "/etc/fstab"):
        audit["attempted"] = False
        audit["reason"] = "no_fstab"
        return audit

    want = {"/boot", "/boot/efi", "/efi"}
    entries = [m for m in _parse_fstab_mounts(g) if m.mountpoint in want]

    # Ensure parent dirs exist (some minimal images are weird)
    for mp in sorted({m.mountpoint for m in entries}, key=len):
        try:
            if not _dir_exists(g, mp) and not getattr(self, "dry_run", False):
                g.mkdir_p(mp)
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
            pass

    # Mount in dependency order: /boot first, then EFI dirs
    entries_sorted = sorted(entries, key=lambda x: 0 if x.mountpoint == "/boot" else 1)

    for m in entries_sorted:
        dev = _resolve_spec_to_dev(self, g, m.spec)
        if not dev:
            audit["errors"].append(
                {
                    "mountpoint": m.mountpoint,
                    "spec": m.spec,
                    "error": f"Could not resolve fstab device spec '{m.spec}' for {m.mountpoint} — "
                    "the UUID/LABEL/PARTUUID may not match any partition on the converted disk. "
                    "The /boot partition may not be mounted during initramfs rebuild. "
                    "Verify with 'blkid' that the referenced filesystem exists.",
                }
            )
            continue
        try:
            if getattr(self, "dry_run", False):
                # Prefer ro on dry-run
                opts = m.options or "defaults"
                if "ro" not in opts.split(","):
                    opts = "ro," + opts
                g.mount_options(opts, dev, m.mountpoint)
            else:
                # Respect options (best-effort) but avoid "nofail" semantics; irrelevant offline
                opts = m.options or "defaults"
                g.mount_options(opts, dev, m.mountpoint)
            audit["mounted"].append(
                {"mountpoint": m.mountpoint, "dev": dev, "opts": m.options, "fstype": m.fstype}
            )
            _log_info(self, f"Mounted {m.mountpoint} ({dev}) for boot regen")
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort fixer step
            audit["errors"].append({"mountpoint": m.mountpoint, "dev": dev, "error": str(e)})

    return audit


def _umount_boot_partitions_best_effort(  # pylint: disable=unused-argument
    self, g: guestfs.GuestFS, mounted: list[dict[str, Any]]
) -> None:
    # 'self' unused but kept for consistency with this module's other _helper(self, g, ...) calls.
    # Unmount in reverse: EFI first, then /boot
    mps = [x.get("mountpoint") for x in mounted if x.get("mountpoint")]
    for mp in sorted(mps, key=len, reverse=True):
        with contextlib.suppress(Exception):
            g.umount(mp)


# initramfs + bootloader regeneration


# This is the top-level GRUB regeneration orchestrator: it walks distro-family detection,
# UEFI/BIOS layout, BLS vs. classic config, driver injection, initramfs regen, and bootloader
# reinstall as one best-effort sequential pipeline. Splitting it risks silently changing the
# order/interaction of these steps in a way that's hard to verify is behavior-preserving, so
# the complexity is intentionally kept in one place per the module's "best-effort" philosophy.
# pylint: disable-next=too-many-locals,too-many-branches,too-many-statements
def regen(self, g: guestfs.GuestFS) -> dict[str, Any]:
    """
    Linux-only initramfs + bootloader regen.

    Expected knobs on self:
      - regen_initramfs: bool
      - update_grub: bool (root= stabilization)
      - initramfs_add_drivers / regen_add_drivers: list[str] or "a b c"
      - dry_run: bool
    """
    if not getattr(self, "regen_initramfs", False):
        return {"enabled": False}

    # Skip Windows.
    try:
        if getattr(self, "inspect_root", None):
            if U.to_text(g.inspect_get_type(self.inspect_root)).lower() == "windows":
                _log_info(self, "regen(): Windows guest detected; skipping Linux regen.")
                return {"enabled": True, "skipped": "windows"}
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        pass

    distro, major = _inspect_distro_major(self, g)
    family = _detect_family(distro)
    looks_uefi = _guest_looks_uefi(g)
    has_bls = _guest_has_bls(g)

    info: dict[str, Any] = {
        "enabled": True,
        "distro": distro,
        "major": major,
        "family": family,
        "guest_boot": "uefi" if looks_uefi else "bios",
        "bls": has_bls,
        "dry_run": bool(getattr(self, "dry_run", False)),
    }

    # device.map cleanup (optional)
    try:
        info["device_map_removed"] = remove_stale_device_map(self, g)
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        info["device_map_error"] = str(e)

    # Get candidate drivers from config or defaults
    candidate_drivers = _get_initramfs_add_drivers(self)

    # Determine guest kernels early so we can filter drivers
    guest_kvers: list[str] = []
    try:
        if _dir_exists(g, "/lib/modules"):
            guest_kvers = sorted([U.to_text(x) for x in g.ls("/lib/modules") if U.to_text(x).strip()])
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        guest_kvers = []

    # Detect LVM in the guest (critical for initramfs configuration)
    lvm_info = _detect_lvm_in_guest(g)
    has_lvm = lvm_info.get("has_lvm", False)
    if has_lvm:
        _log_info(self, f"LVM detected: VGs={lvm_info.get('vgs', [])}, LVs={lvm_info.get('lvs', [])}")
    info["lvm_detected"] = lvm_info

    # Detect LUKS — only if /etc/crypttab has actual (non-comment, non-empty)
    # entries. Many distros ship an empty/comment-only crypttab by default.
    # If real LUKS entries exist, the guest already has cryptsetup in its
    # initramfs. Do NOT force CRYPTSETUP=y or modify crypttab in that case.
    has_luks = False
    if _file_exists(g, "/etc/crypttab"):
        try:
            crypttab = g.cat("/etc/crypttab")
            # Check for non-comment, non-empty lines
            active_lines = [
                ln.strip() for ln in crypttab.splitlines() if ln.strip() and not ln.strip().startswith("#")
            ]
            has_luks = len(active_lines) > 0
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
            has_luks = False
    if has_luks:
        _log_info(self, "LUKS detected (crypttab has active entries) — preserving existing LUKS boot config")
    info["has_luks"] = has_luks

    # Dynamically filter to only modules that actually exist on the guest system
    add_drivers = candidate_drivers
    if guest_kvers:
        # Use the latest kernel version for module detection
        latest_kver = guest_kvers[-1]
        available_drivers = _find_available_modules(g, latest_kver, candidate_drivers)
        if available_drivers:
            add_drivers = available_drivers
            _log_info(self, f"Filtered initramfs drivers to available modules: {add_drivers}")
        else:
            # Fallback to candidates if detection fails
            _log_info(self, f"Could not detect available modules, using candidates: {add_drivers}")
    else:
        _log_info(self, f"No kernel versions found, using candidate drivers: {add_drivers}")

    info["initramfs_add_drivers_candidates"] = candidate_drivers
    info["initramfs_add_drivers"] = add_drivers

    # Mount /boot, /boot/efi for correct output location (critical)
    boot_mount_audit: dict[str, Any] = {"attempted": False}
    mounted_boot: list[dict[str, Any]] = []
    try:
        boot_mount_audit = _mount_boot_partitions_best_effort(self, g)
        mounted_boot = boot_mount_audit.get("mounted", []) or []
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        boot_mount_audit = {"attempted": True, "mounted": [], "errors": [str(e)]}
    info["boot_mounts"] = boot_mount_audit

    # root= stabilization: runs AFTER /boot is mounted so grub.cfg is accessible
    root_changed = 0
    try:
        root_changed = update_grub_root(self, g)
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        _log_warn(
            self,
            f"update_grub_root failed while stabilizing root= in bootloader config: {e}. "
            "The kernel command line may still reference unstable device names (e.g., /dev/sda2). "
            "After boot, verify root= with: cat /proc/cmdline",
        )
    info["root_update_changed"] = root_changed

    # If dry-run: do not run heavy regen tools (but we *can* report what we'd do)
    if getattr(self, "dry_run", False):
        _log_info(self, "DRY-RUN: skipping initramfs/bootloader regeneration commands.")
        if mounted_boot:
            _umount_boot_partitions_best_effort(self, g, mounted_boot)
        return info

    # Driver injection edits (best-effort; these are boot-related config changes)
    inject_audit: dict[str, Any] = {"drivers": add_drivers, "actions": [], "warnings": []}
    try:
        # Debian/Ubuntu initramfs-tools
        if guest_has_cmd(g, "update-initramfs") and _dir_exists(g, "/etc/initramfs-tools"):
            inject_audit["actions"].append(
                _write_modules_linefile(self, g, "/etc/initramfs-tools/modules", add_drivers)
            )

        # Arch mkinitcpio
        if guest_has_cmd(g, "mkinitcpio") and _file_exists(g, "/etc/mkinitcpio.conf"):
            inject_audit["actions"].append(_patch_mkinitcpio_modules(self, g, add_drivers))

        # SUSE sysconfig kernel
        if _file_exists(g, "/etc/sysconfig/kernel"):
            inject_audit["actions"].append(_patch_suse_sysconfig_initrd_modules(self, g, add_drivers))

        # dracut config drop-in (RHEL/Fedora/Photon/etc.) — deterministic and clean
        if guest_has_cmd(g, "dracut"):
            drop = "/etc/dracut.conf.d/h2kvm-drivers.conf"
            line = f'add_drivers+=" {" ".join(add_drivers)} "\n'
            # Only write if not already matching
            old = _read_text(g, drop)
            if line.strip() not in old:
                _write_text(self, g, drop, "# Added by h2kvm\n" + line)
                inject_audit["actions"].append({"path": drop, "changed": True, "note": "dracut_dropin"})
            else:
                inject_audit["actions"].append(
                    {"path": drop, "changed": False, "note": "dracut_dropin_already_present"}
                )

            # Add LVM support if LVM is detected
            if has_lvm:
                lvm_drop = "/etc/dracut.conf.d/h2kvm-lvm.conf"
                lvm_line = 'add_dracutmodules+=" lvm dm "\n'
                old_lvm = _read_text(g, lvm_drop)
                if lvm_line.strip() not in old_lvm:
                    _write_text(self, g, lvm_drop, "# Added by h2kvm (LVM support)\n" + lvm_line)
                    inject_audit["actions"].append(
                        {"path": lvm_drop, "changed": True, "note": "dracut_lvm_dropin"}
                    )
                else:
                    inject_audit["actions"].append(
                        {"path": lvm_drop, "changed": False, "note": "dracut_lvm_dropin_already_present"}
                    )

        # Alpine mkinitfs: config differs per image; warn only
        if guest_has_cmd(g, "mkinitfs"):
            inject_audit["warnings"].append(
                "mkinitfs_detected: no deterministic module-injection implemented (config varies)"
            )

        # Cross-distro fallback (Void/Gentoo/minimal images): try modules-load.d
        inject_audit["actions"].append(_patch_modules_load_d(self, g, add_drivers))
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        inject_audit["warnings"].append(f"driver_injection_failed:{e}")

    info["initramfs_driver_injection"] = inject_audit

    # guest_kvers already determined earlier for module filtering
    info["guest_kernels"] = guest_kvers

    # Initramfs regen attempts (highest success probability first)
    initramfs_attempts: list[list[str]] = []

    if guest_has_cmd(g, "update-initramfs"):
        initramfs_attempts += [["update-initramfs", "-u", "-k", "all"], ["update-initramfs", "-u"]]

    if guest_has_cmd(g, "mkinitcpio"):
        initramfs_attempts += [["mkinitcpio", "-P"]]

    # booster (used by some modern/immutable-ish distros; best-effort)
    if guest_has_cmd(g, "booster"):
        initramfs_attempts += [["booster", "build"]]

    if guest_has_cmd(g, "dracut"):
        # Ensure /var/tmp exists (required by dracut)
        var_tmp_result = _ensure_var_tmp(g)
        info["var_tmp_prepared"] = var_tmp_result
        if var_tmp_result.get("error"):
            _log_info(self, f"Warning: failed to create /var/tmp: {var_tmp_result['error']}")

        # Build dracut commands with driver and LVM support
        # Prefer regenerate-all; it handles multiple kernels cleanly on many distros
        cmd_regen_all = _maybe_add_dracut_drivers(["dracut", "-f", "--regenerate-all"], add_drivers)
        cmd_regen_all = _maybe_add_dracut_lvm(cmd_regen_all, has_lvm)
        initramfs_attempts += [cmd_regen_all]

        # Then a specific latest-kernel attempt if we can guess
        if guest_kvers:
            cmd_kver = _maybe_add_dracut_drivers(["dracut", "-f", "--kver", guest_kvers[-1]], add_drivers)
            cmd_kver = _maybe_add_dracut_lvm(cmd_kver, has_lvm)
            initramfs_attempts.insert(0, cmd_kver)

        # Fallback to plain dracut -f
        cmd_plain = _maybe_add_dracut_drivers(["dracut", "-f"], add_drivers)
        cmd_plain = _maybe_add_dracut_lvm(cmd_plain, has_lvm)
        initramfs_attempts += [cmd_plain]

    if guest_has_cmd(g, "mkinitrd"):
        initramfs_attempts += [["mkinitrd"]]

    if guest_has_cmd(g, "mkinitfs") and guest_kvers:
        initramfs_attempts += [["mkinitfs", "-b", "/", guest_kvers[-1]]]
        if _file_exists(g, "/etc/mkinitfs/mkinitfs.conf"):
            initramfs_attempts.insert(
                0, ["mkinitfs", "-c", "/etc/mkinitfs/mkinitfs.conf", "-b", "/", guest_kvers[-1]]
            )

    if guest_has_cmd(g, "genkernel"):
        initramfs_attempts += [["genkernel", "--install", "initramfs"]]

    if guest_has_cmd(g, "kernel-install") and guest_kvers:
        k = guest_kvers[-1]
        for vml in (f"/boot/vmlinuz-{k}", "/boot/vmlinuz", f"/lib/modules/{k}/vmlinuz"):
            if _file_exists(g, vml):
                initramfs_attempts += [["kernel-install", "add", k, vml]]
                break

    # Dedup attempts
    seen = set()
    deduped: list[list[str]] = []
    for c in initramfs_attempts:
        t = tuple(c)
        if t not in seen:
            seen.add(t)
            deduped.append(c)
    initramfs_attempts = deduped

    initramfs_ran: list[dict[str, Any]] = []
    did_initramfs = False

    # Skip initramfs rebuild for LUKS disks (same as virt-v2v).
    # The guest's existing initramfs already has cryptsetup support.
    # Rebuilding inside libguestfs breaks LUKS UUID references because
    # the device mapper paths differ inside the supermin appliance.
    # Driver config files were already written above — they'll take
    # effect when the user rebuilds initramfs inside the booted VM.
    if has_luks:
        _log_info(self, "Skipping initramfs rebuild (LUKS disk — preserving existing cryptsetup config)")
        _log_info(self, "  Virtio driver configs written to /etc/dracut.conf.d/ and /etc/initramfs-tools/")
        _log_info(
            self, "  After first boot, run: update-initramfs -u  (or dracut -f) to pick up virtio drivers"
        )
        info["initramfs"] = {"skipped": "luks_disk", "success": True}
    else:
        for cmd in initramfs_attempts:
            _log_info(self, f"Running initramfs rebuild: {' '.join(cmd)}")
            _log_info(self, "  (this runs inside the guest and may take several minutes)")
            ok, out, elapsed = _run_guestfs_cmd_with_heartbeat(self, g, cmd)
            _log_info(self, f"  ✅ Completed in {elapsed:.1f}s (ok={ok})")
            initramfs_ran.append({"cmd": cmd, "ok": ok, "out": out[-3000:]})
            if ok:
                did_initramfs = True
                break
        info["initramfs"] = {"attempts": initramfs_ran, "success": did_initramfs}

    # Bootloader regen attempts
    boot_attempts: list[list[str]] = []

    if guest_has_cmd(g, "update-grub"):
        boot_attempts.append(["update-grub"])

    grub_cfg_targets: list[str] = []
    if _dir_exists(g, "/boot/grub2"):
        grub_cfg_targets.append("/boot/grub2/grub.cfg")
    if _dir_exists(g, "/boot/grub"):
        grub_cfg_targets.append("/boot/grub/grub.cfg")

    if guest_has_cmd(g, "grub2-mkconfig"):
        if not grub_cfg_targets:
            grub_cfg_targets = ["/boot/grub2/grub.cfg"]
        for tgt in grub_cfg_targets:
            boot_attempts.append(["grub2-mkconfig", "-o", tgt])

    if guest_has_cmd(g, "grub-mkconfig"):
        if not grub_cfg_targets:
            grub_cfg_targets = ["/boot/grub/grub.cfg"]
        for tgt in grub_cfg_targets:
            boot_attempts.append(["grub-mkconfig", "-o", tgt])

    # Best-effort GRUB reinstall attempts (non-fatal, often fixes "grub prompt" cases)
    # NOTE: offline environment may lack device nodes; we try only when commands exist.
    if guest_has_cmd(g, "grub2-install"):
        # BIOS install (may fail offline; that's OK)
        boot_attempts.append(["grub2-install", "--recheck"])

        # UEFI install attempt (only if ESP likely present)
        if looks_uefi and (_dir_exists(g, "/boot/efi") or _dir_exists(g, "/efi")):
            # Avoid assuming distro path layout; try common EFI directory locations.
            efi_dir = "/boot/efi" if _dir_exists(g, "/boot/efi") else "/efi"
            boot_attempts.append(
                ["grub2-install", "--target=x86_64-efi", f"--efi-directory={efi_dir}", "--recheck"]
            )

    if guest_has_cmd(g, "grub-install"):
        boot_attempts.append(["grub-install", "--recheck"])
        if looks_uefi and (_dir_exists(g, "/boot/efi") or _dir_exists(g, "/efi")):
            efi_dir = "/boot/efi" if _dir_exists(g, "/boot/efi") else "/efi"
            boot_attempts.append(
                ["grub-install", "--target=x86_64-efi", f"--efi-directory={efi_dir}", "--recheck"]
            )

    # systemd-boot: update is safe-ish, but only meaningful if ESP is mounted
    if guest_has_cmd(g, "bootctl"):
        boot_attempts.append(["bootctl", "status"])
        if looks_uefi and (bool(mounted_boot) or _dir_exists(g, "/boot/efi") or _dir_exists(g, "/efi")):
            boot_attempts.append(["bootctl", "update"])

    # Dedup
    seen = set()
    deduped = []
    for c in boot_attempts:
        t = tuple(c)
        if t not in seen:
            seen.add(t)
            deduped.append(c)
    boot_attempts = deduped

    boot_ran: list[dict[str, Any]] = []
    did_boot = False
    for cmd in boot_attempts:
        _log_info(self, f"Running bootloader command: {' '.join(cmd)}")
        ok, out = _run_guestfs_cmd(self, g, cmd)
        boot_ran.append({"cmd": cmd, "ok": ok, "out": out[-3000:]})
        if ok:
            _log_info(self, f"  Succeeded: {' '.join(cmd)}")
            did_boot = True
            # If we ran mkconfig, continue to run the next mkconfig target (multi-target)
            if cmd and cmd[0] not in ("grub2-mkconfig", "grub-mkconfig"):
                break
        else:
            _log_info(self, f"  Failed: {' '.join(cmd)}")

    info["bootloader"] = {"attempts": boot_ran, "success": did_boot}

    # Fallback: if grub2-mkconfig/grub-mkconfig failed, directly patch grub.cfg
    # with the correct root= token. This is critical when UUID was regenerated
    # but grub2-mkconfig can't run in the offline chroot environment.
    if not did_boot:
        stable = _stable_root_id(self, g)
        if stable:
            new_root_token = f"root={stable}"
            fallback_changed = _update_grub_cfg_fallback(self, g, new_root_token)
            fallback_changed += _update_extlinux_syslinux_fallback(self, g, new_root_token)
            if fallback_changed:
                _log_info(self, f"Patched grub.cfg directly with {new_root_token} (grub2-mkconfig fallback)")
                info["bootloader"]["grub_cfg_fallback"] = True
                info["bootloader"]["grub_cfg_fallback_changed"] = fallback_changed

    # Stage 4: Validate root UUID exists in grub.cfg
    stable = _stable_root_id(self, g)
    if stable:
        validated = False
        for cfg_path in ("/boot/grub2/grub.cfg", "/boot/grub/grub.cfg"):
            cfg_text = _read_text(g, cfg_path)
            if cfg_text and stable in cfg_text:
                validated = True
                break
        info["bootloader"]["root_uuid_validated"] = validated
        if not validated:
            _log_warn(
                self,
                f"GRUB validation: root UUID {stable} NOT found in grub.cfg — "
                "the VM may fail to find its root filesystem at boot. "
                "Boot into rescue mode and run: grub2-mkconfig -o /boot/grub2/grub.cfg",
            )

    # Unmount boot mounts if we mounted them
    try:
        if mounted_boot:
            _umount_boot_partitions_best_effort(self, g, mounted_boot)
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        pass

    # Serial console injection (runs after regen so grub.cfg updates don't overwrite)
    try:
        serial_info = inject_serial_console(self, g)
        info["serial_console"] = serial_info
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        _log_warn(
            self,
            f"Serial console injection failed: {e}. "
            "'virsh console <vm>' will not work for headless access. "
            "Manually add 'console=ttyS0,115200' to GRUB_CMDLINE_LINUX in /etc/default/grub "
            "and run 'grub2-mkconfig -o /boot/grub2/grub.cfg' (or 'update-grub' on Debian/Ubuntu).",
        )
        info["serial_console"] = {"enabled": False, "error": str(e)}

    # Sanity listing
    sanity: dict[str, Any] = {"boot": {}}
    try:
        if _dir_exists(g, "/boot"):
            sanity["boot"]["boot_ls"] = sorted([U.to_text(x) for x in g.ls("/boot")])[-80:]
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort fixer step
        pass
    if _dir_exists(g, "/boot/loader/entries"):
        with contextlib.suppress(Exception):
            sanity["boot"]["loader_entries"] = sorted([U.to_text(x) for x in g.ls("/boot/loader/entries")])
    info["sanity"] = sanity

    return info


# Optional: compatibility wiring (not used in your OfflineFSFix, but kept)


def wire_into(cls: type) -> type:
    """
    Monkey-patch these helpers as instance methods:
      - remove_stale_device_map
      - update_grub_root
      - regen
    """
    cls.remove_stale_device_map = remove_stale_device_map
    cls.update_grub_root = update_grub_root
    cls.regen = regen
    return cls
