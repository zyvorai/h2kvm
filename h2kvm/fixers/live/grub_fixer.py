# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Live GRUB fixing via SSH for running VMs."""

# h2kvm/fixers/live/grub_fixer.py
from __future__ import annotations

import base64
import contextlib
import re
import shlex
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from h2kvm.core.utils import U

if TYPE_CHECKING:
    import logging

    from h2kvm.infrastructure.ssh.ssh_client import SSHClient

# Report model (JSON-friendly)


@dataclass
class LiveGrubFixReport:  # pylint: disable=too-many-instance-attributes  # flat JSON-friendly report of all fix-run outcomes
    """Structured, JSON-friendly report of a live GRUB fix run."""

    distro_id: str = ""
    distro_like: list[str] = field(default_factory=list)
    family: str = ""

    root_source: str = ""
    root_resolved: str = ""
    stable_root: str = ""

    removed_device_maps: list[str] = field(default_factory=list)
    updated_default_grub: bool = False
    updated_files: list[str] = field(default_factory=list)

    commands_ran: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# Live fixer (SSH)


class LiveGrubFixer:  # pylint: disable=too-many-instance-attributes  # tracks dry-run/backup/regen knobs plus SSH client and report state
    """
    LIVE boot fix via SSH (safer + more distro-aware):

      - Remove stale device.map (only if it looks auto-generated / references legacy disk names)
      - Stabilize root= in /etc/default/grub using UUID/PARTUUID/LABEL/PARTLABEL if possible
      - Best-effort initramfs + bootloader regeneration using capability detection (not distro-only)
      - Optional post-check: search generated config (grub.cfg and/or BLS entries) for stable root token (warning only)

    Knobs:
      - dry_run: do not mutate, but still probe/detect
      - no_backup: disable timestamped backups
      - update_grub: enable root= stabilization in /etc/default/grub
      - regen_initramfs: enable initramfs regeneration (bootloader regen may still run if grub root was updated)
    """

    _INLINE_B64_MAX_CHARS = 24_000
    _B64_CHUNK_CHARS = 8_000

    def __init__(  # pylint: disable=too-many-arguments  # each knob independently controls fixer behavior
        self,
        logger: logging.Logger,
        sshc: SSHClient,
        *,
        dry_run: bool,
        no_backup: bool,
        update_grub: bool,
        regen_initramfs: bool,
        prefer: tuple[str, ...] = ("UUID", "PARTUUID", "LABEL", "PARTLABEL"),
    ):
        self.logger = logger
        self.sshc = sshc
        self.dry_run = dry_run
        self.no_backup = no_backup
        self.update_grub = update_grub
        self.regen_initramfs = regen_initramfs
        self.prefer = prefer
        self.report = LiveGrubFixReport()

        self._warned_once: set[str] = set()

    # ssh helpers

    def _warn_once(self, key: str, msg: str, *args: Any) -> None:
        if key in self._warned_once:
            return
        self._warned_once.add(key)
        self.logger.warning(msg, *args)

    def _ssh(self, cmd: str) -> str:
        self.logger.debug("SSH: %s", cmd)
        return self.sshc.ssh(cmd) or ""

    def _sh(self, cmd: str, *, allow_fail: bool = True) -> tuple[int, str]:
        """
        Run a command remotely and capture rc reliably.

        Robustness:
          - pipefail is best-effort (dash/busybox sh may not support it)
          - rc marker is unique per call to avoid output spoofing
          - if multiple markers appear, we take the LAST one
        """
        # If U.now_ts() is second-resolution, add a cheap extra entropy component (python-side).
        marker = f"__H2KVM_RC_{U.now_ts()}_{id(cmd)}__"

        wrapped_body = f"""
set -u
set -o pipefail 2>/dev/null || true
{cmd}
rc=$?
printf "\\n{marker}=%s\\n" "$rc"
exit 0
""".strip()

        wrapped = "sh -lc " + shlex.quote(wrapped_body)
        out = self._ssh(wrapped)

        rc = 0
        matches = list(re.finditer(rf"{re.escape(marker)}=(\d+)\s*$", out, flags=re.M))
        if matches:
            rc = int(matches[-1].group(1))
            out = re.sub(rf"\n?{re.escape(marker)}=\d+\s*$", "", out, flags=re.M)
        else:
            rc = 0
            self._warn_once(
                "missing_rc_marker",
                "Could not parse remote rc marker (unexpected shell output); treating as rc=0 for: %s",
                cmd,
            )

        self.report.commands_ran.append({"cmd": cmd, "rc": str(rc)})
        if rc != 0 and not allow_fail:
            raise RuntimeError(
                f"Remote command failed on the target host (exit code {rc}). "
                f"Check SSH connectivity and that the target system is in a healthy state. "
                f"Command: {cmd}"
            )
        return rc, out

    def _has_cmd(self, name: str) -> bool:
        _, out = self._sh(f"command -v {shlex.quote(name)} >/dev/null 2>&1 && echo OK || echo NO")
        return out.strip() == "OK"

    def _remote_exists(self, path: str) -> bool:
        _, out = self._sh(f"test -e {shlex.quote(path)} && echo OK || echo NO")
        return out.strip() == "OK"

    def _remote_is_dir(self, path: str) -> bool:
        _, out = self._sh(f"test -d {shlex.quote(path)} && echo OK || echo NO")
        return out.strip() == "OK"

    def _read_remote_file(self, path: str) -> str:
        _, out = self._sh(f"cat {shlex.quote(path)} 2>/dev/null || true")
        return out

    def _remote_stat_u_g_a(self, path: str) -> tuple[str | None, str | None, str | None]:
        if not self._has_cmd("stat"):
            return None, None, None
        _, out = self._sh(f"stat -c '%u %g %a' -- {shlex.quote(path)} 2>/dev/null || true")
        s = out.strip()
        if not s:
            return None, None, None
        parts = s.split()
        if len(parts) != 3:
            return None, None, None
        uid, gid, mode = parts
        if not (uid.isdigit() and gid.isdigit() and mode.isdigit()):
            return None, None, None
        return uid, gid, mode

    def _write_remote_file_atomic(self, path: str, content: str, mode: str = "0644") -> None:
        """
        Atomic-ish update:
          - mktemp
          - write content (base64 preferred; chunked if large; fallback to heredoc with unique marker)
          - chmod/chown from existing target when possible
          - mv over target
          - sync
        """
        if self.dry_run:
            self.logger.info("DRY-RUN: would write %s (%d bytes)", path, len(content))
            return

        _, tmp = self._sh(
            "mktemp /tmp/h2kvm.grubfix.XXXXXX 2>/dev/null || mktemp /run/h2kvm.grubfix.XXXXXX",
            allow_fail=True,
        )
        tmp = tmp.strip()
        if not tmp:
            raise RuntimeError(
                "Failed to create temporary file on the remote host. "
                "Check that /tmp has available space and the SSH user has write permissions."
            )

        uid: str | None = None
        gid: str | None = None
        orig_mode: str | None = None
        if self._remote_exists(path):
            uid, gid, orig_mode = self._remote_stat_u_g_a(path)

        effective_mode = (orig_mode or "").strip() or mode

        lines: list[str] = []
        lines.append("set -e")
        lines.append("umask 022")
        lines.append(f": > {shlex.quote(tmp)}")

        if self._has_cmd("base64"):
            b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
            if len(b64) <= self._INLINE_B64_MAX_CHARS:
                lines.append(f"printf %s {shlex.quote(b64)} | base64 -d >> {shlex.quote(tmp)}")
            else:
                lines.append("# chunked base64 decode")
                for i in range(0, len(b64), self._B64_CHUNK_CHARS):
                    chunk = b64[i : i + self._B64_CHUNK_CHARS]
                    lines.append(f"printf %s {shlex.quote(chunk)} | base64 -d >> {shlex.quote(tmp)}")
        else:
            self._warn_once(
                "missing_base64",
                "Remote is missing 'base64'; falling back to heredoc writer (safe, slightly less robust).",
            )
            marker = f"__H2KVM_EOF_{U.now_ts()}_{re.sub(r'[^A-Za-z0-9]+', '_', tmp)}__"
            lines.append(f"cat >> {shlex.quote(tmp)} <<'{marker}'")
            lines.append(content)
            lines.append(marker)

        lines.append(f"chmod {shlex.quote(effective_mode)} {shlex.quote(tmp)} 2>/dev/null || true")
        if uid and gid:
            lines.append(
                f"chown {shlex.quote(uid)}:{shlex.quote(gid)} {shlex.quote(tmp)} 2>/dev/null || true"
            )

        lines.append(f"mv -f {shlex.quote(tmp)} {shlex.quote(path)}")
        lines.append("sync 2>/dev/null || true")

        payload = "\n".join(lines) + "\n"
        self._sh("sh -lc " + shlex.quote(payload), allow_fail=False)

    def _backup_remote_file(self, path: str) -> str | None:
        if self.no_backup or self.dry_run:
            return None
        b = f"{path}.bak.h2kvm.{U.now_ts()}"
        self._sh(f"cp -a {shlex.quote(path)} {shlex.quote(b)} 2>/dev/null || true")
        if self._remote_exists(b):
            self.logger.info("Backup: %s -> %s", path, b)
            return b
        self.logger.warning("Backup failed (best-effort): %s -> %s", path, b)
        return None

    def _remove_remote_file(self, path: str) -> None:
        if self.dry_run:
            self.logger.info("DRY-RUN: would remove %s", path)
            return
        self._sh(f"rm -f {shlex.quote(path)} 2>/dev/null || true")
        self.logger.info("Removed %s (if existed)", path)

    # detection helpers

    def _read_os_release(self) -> tuple[str, list[str]]:
        _, out = self._sh(
            r""". /etc/os-release 2>/dev/null || true
echo "ID=${ID:-}"
echo "ID_LIKE=${ID_LIKE:-}"
""",
            allow_fail=True,
        )
        did = ""
        like: list[str] = []
        for ln in out.splitlines():
            if ln.startswith("ID="):
                did = ln.split("=", 1)[1].strip().strip('"').lower()
            elif ln.startswith("ID_LIKE="):
                raw = ln.split("=", 1)[1].strip().strip('"')
                like = [x.strip().lower() for x in raw.split() if x.strip()]
        return did, like

    # pylint: disable-next=too-many-return-statements  # one dedicated branch per distro family
    def _detect_family(self, did: str, like: list[str]) -> str:
        d = (did or "").lower()
        lk = {x.lower() for x in (like or [])}

        if d in {
            "debian",
            "ubuntu",
            "linuxmint",
            "pop",
            "popos",
            "kali",
            "raspbian",
            "elementary",
            "zorin",
            "deepin",
        }:
            return "debian"
        if {"debian", "ubuntu"} & lk:
            return "debian"

        if d in {
            "rhel",
            "centos",
            "fedora",
            "rocky",
            "almalinux",
            "oraclelinux",
            "ol",
            "redhat",
            "amzn",
            "amazonlinux",
            "mariner",
            "cbl-mariner",
            "photon",
        }:
            return "rhel"
        if {"rhel", "fedora", "centos", "redhat"} & lk:
            return "rhel"

        if d in {"sles", "sled", "opensuse", "opensuse-leap", "opensuse-tumbleweed", "suse"}:
            return "suse"
        if "suse" in lk:
            return "suse"

        if d in {"arch", "manjaro", "endeavouros", "garuda"}:
            return "arch"
        if "arch" in lk:
            return "arch"

        if d == "alpine" or "alpine" in lk:
            return "alpine"

        if d in {"gentoo", "funtoo"} or "gentoo" in lk:
            return "gentoo"

        if d == "void" or "void" in lk:
            return "void"

        if d == "nixos" or "nixos" in lk:
            return "nixos"

        return "other"

    def _detect_distro(self) -> None:
        did, like = self._read_os_release()
        fam = self._detect_family(did, like)
        self.report.distro_id = did
        self.report.distro_like = like
        self.report.family = fam

    def _readlink_f(self, path: str) -> str | None:
        if not self._has_cmd("readlink"):
            self._warn_once(
                "missing_readlink", "readlink not found on remote; root path resolution may be limited."
            )
            return None
        _, out = self._sh(f"readlink -f -- {shlex.quote(path)} 2>/dev/null || true")
        s = out.strip()
        return s or None

    def _is_remote_blockdev(self, dev: str) -> bool:
        _, out = self._sh(f"test -b {shlex.quote(dev)} && echo OK || echo NO")
        return out.strip() == "OK"

    def _blkid(self, dev: str, key: str) -> str | None:
        if not self._has_cmd("blkid"):
            self._warn_once(
                "missing_blkid", "blkid not found on remote; cannot convert devices to UUID/PARTUUID."
            )
            return None
        _, out = self._sh(f"blkid -s {shlex.quote(key)} -o value -- {shlex.quote(dev)} 2>/dev/null || true")
        v = out.strip()
        return v or None

    def _findmnt_root_source(self) -> str:
        cmds = [
            "findmnt -n -o SOURCE -T / 2>/dev/null || true",
            "findmnt -n -o SOURCE / 2>/dev/null || true",
            "awk '$2==\"/\"{print $1; exit}' /proc/mounts 2>/dev/null || true",
        ]
        for c in cmds:
            _, out = self._sh(c)
            s = out.strip()
            if not s:
                continue

            # initramfs/rescue environments: / may be overlay/tmpfs
            if s in {"overlay", "tmpfs"}:
                for alt in ("/sysroot", "/mnt/sysimage"):
                    _, o2 = self._sh(f"findmnt -n -o SOURCE -T {shlex.quote(alt)} 2>/dev/null || true")
                    s2 = o2.strip()
                    if s2 and s2 not in {"overlay", "tmpfs"}:
                        return s2
            return s
        return ""

    def _sanitize_root_spec(self, spec: str) -> str:
        s = (spec or "").strip()
        if not s:
            return s
        return re.sub(r"\[.*\]$", "", s).strip()  # btrfs subvol suffix

    def _convert_spec_to_stable(self, spec: str) -> str:
        spec = self._sanitize_root_spec(spec)

        if re.match(r"^(UUID|PARTUUID|LABEL|PARTLABEL)=.+", spec):
            return spec

        resolved = spec

        if spec.startswith("/dev/disk/by-"):
            rp = self._readlink_f(spec)
            if rp:
                resolved = rp

        if resolved.startswith("/dev/mapper/"):
            rp = self._readlink_f(resolved)
            if rp and rp.startswith("/dev/"):
                resolved = rp

        if not resolved.startswith("/dev/"):
            return spec

        if not self._is_remote_blockdev(resolved):
            return spec

        for key in self.prefer:
            v = self._blkid(resolved, key)
            if v:
                return f"{key}={v}"

        return spec

    # operations

    def remove_stale_device_map(self) -> int:
        """Back up and remove device.map files that look auto-generated with legacy disk names."""
        removed = 0
        paths = [
            "/boot/grub2/device.map",
            "/boot/grub/device.map",
            "/etc/grub2-device.map",
            "/etc/grub/device.map",
        ]
        stale_re = re.compile(r"\b(sd[a-z]|vd[a-z]|hd[a-z]|xvd[a-z]|nvme\d+n\d+)\b")

        for p in paths:
            if not self._remote_exists(p):
                continue
            txt = self._read_remote_file(p)

            # conservative: must mention disk tokens and hd-mapping style
            if stale_re.search(txt) and ("(hd" in txt or "hd0" in txt):
                self.logger.info("GRUB: removing stale device.map: %s", p)
                if not self.dry_run:
                    self._backup_remote_file(p)
                self._remove_remote_file(p)
                self.report.removed_device_maps.append(p)
                removed += 1

        return removed

    # pylint: disable-next=too-many-return-statements,too-many-statements  # each guard/step needs its own early exit with a distinct warning
    def update_grub_root(self) -> bool:
        """Stabilize root= in /etc/default/grub with a UUID/PARTUUID/LABEL/PARTLABEL spec, if possible."""
        if not self.update_grub:
            return False

        root_src = self._findmnt_root_source()
        self.report.root_source = root_src

        if not root_src:
            msg = "GRUB root=: could not detect root source; skipping."
            self.logger.warning(msg)
            self.report.warnings.append(msg)
            return False

        root_src_s = self._sanitize_root_spec(root_src)
        root_resolved = root_src_s
        if root_src_s.startswith(("/dev/disk/by-", "/dev/mapper/")):
            rp = self._readlink_f(root_src_s)
            if rp:
                root_resolved = rp
        self.report.root_resolved = root_resolved

        stable = self._convert_spec_to_stable(root_src_s)
        self.report.stable_root = stable

        if stable == root_src_s:
            self.logger.info("GRUB root=: already stable (or could not improve): %s", root_src_s)
            return False

        path = "/etc/default/grub"
        if not self._remote_exists(path):
            msg = f"GRUB root=: {path} not found; skipping."
            self.logger.warning(msg)
            self.report.warnings.append(msg)
            return False

        old = self._read_remote_file(path)
        if not old.strip():
            msg = f"GRUB root=: {path} unreadable/empty; skipping."
            self.logger.warning(msg)
            self.report.warnings.append(msg)
            return False

        cmdline_re = re.compile(r'^(GRUB_CMDLINE_LINUX(?:_DEFAULT)?)=(["\'])(.*)\2\s*$')

        touched = False

        def patch_line(line: str) -> str:
            nonlocal touched
            m = cmdline_re.match(line)
            if not m:
                return line
            key, quote, val = m.group(1), m.group(2), m.group(3)

            # Handle root=token, root="token", root='token'
            if re.search(r'\broot=("|\')', val):
                val2 = re.sub(r'\broot=(["\'])[^"\']+\1', f"root={quote}{stable}{quote}", val)
            elif re.search(r"\broot=", val):
                val2 = re.sub(r"\broot=[^\s\"']+", f"root={stable}", val)
            else:
                val2 = (val + f" root={stable}").strip()

            if val2 != val:
                touched = True
            return f"{key}={quote}{val2}{quote}"

        lines_in = old.splitlines()
        new_lines = [patch_line(line) for line in lines_in]

        if not touched:
            new_lines.append(f'GRUB_CMDLINE_LINUX="root={stable}"')
            touched = True

        new = "\n".join(new_lines) + "\n"

        if new == old:
            self.logger.info("GRUB root=: no change needed.")
            return False

        if self.dry_run:
            self.logger.info("DRY-RUN: would update %s (root=%s).", path, stable)
            self.report.updated_default_grub = True
            self.report.updated_files.append(path)
            return True

        self._backup_remote_file(path)
        self._write_remote_file_atomic(path, new, mode="0644")
        self.logger.info("GRUB root=: updated %s (root=%s).", path, stable)
        self.report.updated_default_grub = True
        self.report.updated_files.append(path)
        return True

    # regen logic (capability-first, split initramfs vs bootloader)

    def _detect_grub_cfg_targets(self) -> list[str]:
        targets: list[str] = []
        if self._remote_exists("/boot/grub2"):
            targets.append("/boot/grub2/grub.cfg")
        if self._remote_exists("/boot/grub"):
            targets.append("/boot/grub/grub.cfg")
        if not targets:
            targets = ["/boot/grub2/grub.cfg", "/boot/grub/grub.cfg"]

        out: list[str] = []
        seen = set()
        for t in targets:
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out

    def _detect_bls_entries_dir(self) -> str | None:
        for d in ("/boot/loader/entries", "/boot/efi/loader/entries"):
            if self._remote_is_dir(d):
                return d
        return None

    def _run_best_effort_until_ok(self, label: str, cmds: list[str]) -> None:
        for c in cmds:
            rc, out = self._sh(c, allow_fail=True)
            if rc == 0:
                self.logger.info("%s: success: %s", label, c)
                return
            tail = (out or "")[-1200:].strip()
            self.logger.debug("%s: failed rc=%s cmd=%s out=%s", label, rc, c, tail)
        self.report.warnings.append(f"{label}: all attempts failed (non-fatal)")

    def _regen_initramfs(self) -> None:
        if not self.regen_initramfs:
            return

        fam = self.report.family

        if self.dry_run:
            self.logger.info("DRY-RUN: would regenerate initramfs.")
            return

        initramfs_cmds: list[str] = []

        if self._has_cmd("update-initramfs"):
            initramfs_cmds += [
                "update-initramfs -u -k all 2>/dev/null",
                "update-initramfs -u 2>/dev/null",
            ]

        if self._has_cmd("mkinitcpio"):
            initramfs_cmds += ["mkinitcpio -P 2>/dev/null"]

        if self._has_cmd("dracut"):
            initramfs_cmds += [
                "dracut -f --regenerate-all 2>/dev/null",
                "dracut -f 2>/dev/null",
            ]

        if self._has_cmd("mkinitrd"):
            initramfs_cmds += ["mkinitrd 2>/dev/null"]

        if self._has_cmd("mkinitfs"):
            initramfs_cmds += [
                'k=$(uname -r 2>/dev/null || true); [ -n "$k" ] && mkinitfs -b / "$k" 2>/dev/null || true'
            ]

        if self._has_cmd("genkernel"):
            initramfs_cmds += ["genkernel --install initramfs 2>/dev/null"]

        if fam == "nixos":
            self.report.warnings.append("initramfs: nixos detected; skipping nixos-rebuild (manual step)")
            return

        if initramfs_cmds:
            self._run_best_effort_until_ok("initramfs", initramfs_cmds)
        else:
            self.report.warnings.append("initramfs: no known initramfs tool detected; skipping")

    def _regen_bootloader(self) -> None:
        if self.dry_run:
            self.logger.info("DRY-RUN: would regenerate bootloader config.")
            return

        grub_targets = self._detect_grub_cfg_targets()
        boot_cmds: list[str] = []

        if self._has_cmd("update-grub"):
            boot_cmds.append("update-grub 2>/dev/null")

        if self._has_cmd("grub2-mkconfig"):
            for tgt in grub_targets:
                boot_cmds.append(f"grub2-mkconfig -o {shlex.quote(tgt)} 2>/dev/null")

        if self._has_cmd("grub-mkconfig"):
            for tgt in grub_targets:
                boot_cmds.append(f"grub-mkconfig -o {shlex.quote(tgt)} 2>/dev/null")

        if boot_cmds:
            self._run_best_effort_until_ok("bootloader", boot_cmds)
            return

        if self._has_cmd("bootctl"):
            self._sh("bootctl status 2>/dev/null || true", allow_fail=True)
            self._sh("bootctl update 2>/dev/null || true", allow_fail=True)
            return

        self.report.warnings.append("bootloader: no grub/bootctl tooling detected; skipping")

    def regen(self, *, force_bootloader: bool) -> None:
        """
        Regen orchestration:

          - initramfs: only when self.regen_initramfs is True
          - bootloader: when force_bootloader True OR self.regen_initramfs True
            (i.e., if we updated /etc/default/grub, we force bootloader regen even if initramfs knob is off)
        """
        if not self.report.distro_id:
            with contextlib.suppress(Exception):
                self._detect_distro()

        did = self.report.distro_id
        fam = self.report.family

        if self.dry_run:
            self.logger.info(
                "DRY-RUN: would regen (bootloader=%s, initramfs=%s) (id=%s family=%s).",
                force_bootloader or self.regen_initramfs,
                self.regen_initramfs,
                did,
                fam,
            )
            return

        self._regen_initramfs()

        if force_bootloader or self.regen_initramfs:
            self._regen_bootloader()

        self.logger.info("Live regen done (id=%s family=%s).", did, fam)

    def postcheck_configs(self) -> None:
        """Warn (non-fatally) if the stable root token isn't found in generated grub.cfg/BLS entries."""
        stable = (self.report.stable_root or "").strip()
        if not stable:
            return

        token = f"root={stable}"

        # Check grub.cfg targets
        candidates = self._detect_grub_cfg_targets()
        for p in candidates:
            if not self._remote_exists(p):
                continue
            txt = self._read_remote_file(p)
            if token in txt or stable in txt:
                return

        # Check BLS entries (Fedora/RHEL-ish)
        bls_dir = self._detect_bls_entries_dir()
        if bls_dir:
            _, out = self._sh(
                f"grep -R --line-number -F {shlex.quote(token)} {shlex.quote(bls_dir)} 2>/dev/null || true"
            )
            if (out or "").strip():
                return
            _, out2 = self._sh(
                f"grep -R --line-number -F {shlex.quote(stable)} {shlex.quote(bls_dir)} 2>/dev/null || true"
            )
            if (out2 or "").strip():
                return

        msg = (
            f"Postcheck: stable root '{stable}' not found in grub.cfg/BLS entries "
            f"(may still be OK; generator tooling or bootloader may apply it differently)."
        )
        self.logger.warning(msg)
        self.report.warnings.append(msg)

    # main entry

    def run(self) -> dict[str, Any]:
        """Run the full live GRUB fix pipeline (detect, cleanup, stabilize root=, regen, postcheck)."""
        U.banner(self.logger, "GRUB fix (SSH)")

        try:
            self._detect_distro()
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort step; a failed detection must not abort the whole fix run
            self.report.warnings.append(f"distro_detect_failed:{e}")

        removed = 0
        updated = False

        try:
            removed = self.remove_stale_device_map()
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort step; must not abort the whole fix run
            msg = f"remove_device_map_failed:{e}"
            self.logger.warning(msg)
            self.report.warnings.append(msg)

        try:
            updated = self.update_grub_root()
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort step; must not abort the whole fix run
            msg = f"update_grub_root_failed:{e}"
            self.logger.warning(msg)
            self.report.warnings.append(msg)

        # Key fix: even if regen_initramfs knob is off, if we updated /etc/default/grub we should
        # at least regen bootloader config (best-effort).
        if self.regen_initramfs or updated:
            try:
                self.regen(force_bootloader=updated)
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort step; must not abort the whole fix run
                msg = f"regen_failed:{e}"
                self.logger.warning(msg)
                self.report.warnings.append(msg)

        try:
            self.postcheck_configs()
        except Exception as e:  # pylint: disable=broad-exception-caught  # postcheck is advisory only; must not abort the whole fix run
            self.logger.debug("Postcheck failed: %s", e)

        self.logger.info("GRUB fix: removed_device_maps=%d, updated_grub_root=%s", removed, updated)
        self.logger.info("GRUB fix completed.")

        return {
            "distro_id": self.report.distro_id,
            "distro_like": self.report.distro_like,
            "family": self.report.family,
            "root_source": self.report.root_source,
            "root_resolved": self.report.root_resolved,
            "stable_root": self.report.stable_root,
            "removed_device_maps": self.report.removed_device_maps,
            "updated_default_grub": self.report.updated_default_grub,
            "updated_files": self.report.updated_files,
            "commands_ran": self.report.commands_ran,
            "warnings": self.report.warnings,
            "errors": self.report.errors,
            "dry_run": self.dry_run,
        }
