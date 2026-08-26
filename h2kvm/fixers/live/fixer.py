# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/live/fixer.py
"""Live migration fixer for running VMs."""

from __future__ import annotations

import base64
import os
import re
import shlex
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from h2kvm.core.utils import U

from .grub_fixer import LiveGrubFixer

if TYPE_CHECKING:
    import logging

    from h2kvm.infrastructure.ssh.ssh_client import SSHClient


@dataclass(frozen=True)
class LiveFixerOptions:
    """Configuration flags for a single LiveFixer run."""

    dry_run: bool
    no_backup: bool
    print_fstab: bool
    update_grub: bool
    regen_initramfs: bool
    remove_vmware_tools: bool = False
    luks_passphrase: str | None = None


class LiveFixer:  # pylint: disable=too-few-public-methods
    # Most methods are intentionally private SSH helpers; run() is the sole
    # public entrypoint by design.
    """
    Live fix via SSH:

      - Rewrite /etc/fstab: /dev/disk/by-path/* -> UUID=/PARTUUID=/LABEL=/PARTLABEL= (best-effort)
      - Optionally remove VMware tools (best-effort across distros)
      - Optionally run LiveGrubFixer (preferred) to stabilize root= + regen initramfs/bootloader

    Design goals:
      - Safe defaults + best-effort behavior
      - Minimal assumptions about distro/tooling
      - Deterministic edits: atomic writes + timestamped backups (unless disabled)
    """

    # keep this conservative; some SSH setups choke on huge one-liners
    _INLINE_B64_MAX_CHARS = 24_000  # ~18KB decoded-ish, depending on content
    _B64_CHUNK_CHARS = 8_000

    def __init__(  # pylint: disable=too-many-arguments  # every field is an independent CLI-level fix toggle
        self,
        logger: logging.Logger,
        sshc: SSHClient,
        *,
        dry_run: bool,
        no_backup: bool,
        print_fstab: bool,
        update_grub: bool,
        regen_initramfs: bool,
        remove_vmware_tools: bool = False,
        luks_passphrase: str | None = None,
        luks_passphrase_env: str | None = None,
        luks_keyfile: str | None = None,
    ):
        self.logger = logger
        self.sshc = sshc

        # Resolve LUKS passphrase from direct value, env var, or keyfile
        resolved_pass = luks_passphrase
        if not resolved_pass and luks_passphrase_env:
            resolved_pass = os.environ.get(luks_passphrase_env)
        if not resolved_pass and luks_keyfile:
            try:
                with open(luks_keyfile, encoding="utf-8") as f:
                    resolved_pass = f.read().strip()
            except OSError:
                pass

        self.opts = LiveFixerOptions(
            dry_run=dry_run,
            no_backup=no_backup,
            print_fstab=print_fstab,
            update_grub=update_grub,
            regen_initramfs=regen_initramfs,
            remove_vmware_tools=remove_vmware_tools,
            luks_passphrase=resolved_pass,
        )

        # one-time warnings to avoid log spam
        self._warned_missing: set[str] = set()

    # SSH helpers

    def _ssh(self, cmd: str) -> str:
        self.logger.debug("SSH: %s", cmd)
        return self.sshc.ssh(cmd) or ""

    def _has(self, cmd: str) -> bool:
        return (
            self._ssh(f"command -v {shlex.quote(cmd)} >/dev/null 2>&1 && echo YES || echo NO").strip()
            == "YES"
        )

    def _warn_once(self, key: str, msg: str, *args: Any) -> None:
        if key in self._warned_missing:
            return
        self._warned_missing.add(key)
        self.logger.warning(msg, *args)

    def _remote_exists(self, path: str) -> bool:
        out = self._ssh(f"test -e {shlex.quote(path)} && echo OK || echo NO").strip()
        return out == "OK"

    def _read_remote_file(self, path: str) -> str:
        return self._ssh(f"cat {shlex.quote(path)} 2>/dev/null || true")

    def _readlink_f(self, path: str) -> str | None:
        out = self._ssh(f"readlink -f -- {shlex.quote(path)} 2>/dev/null || true").strip()
        return out or None

    def _is_remote_blockdev(self, dev: str) -> bool:
        return self._ssh(f"test -b {shlex.quote(dev)} && echo OK || echo NO").strip() == "OK"

    def _blkid(self, dev: str, key: str) -> str | None:
        out = self._ssh(
            f"blkid -s {shlex.quote(key)} -o value -- {shlex.quote(dev)} 2>/dev/null || true"
        ).strip()
        return out or None

    def _run_best_effort(self, cmds: list[str]) -> None:
        for c in cmds:
            if not c.strip():
                continue
            self._ssh(c)

    def _backup(self, path: str) -> str | None:
        if self.opts.no_backup or self.opts.dry_run:
            return None
        b = f"{path}.bak.h2kvm.{U.now_ts()}"
        self._ssh(f"cp -a {shlex.quote(path)} {shlex.quote(b)} 2>/dev/null || true")
        if self._remote_exists(b):
            self.logger.info("Backup: %s -> %s", path, b)
            return b
        self.logger.warning(
            "Backup failed for %s (best-effort): could not create %s. "
            "Check that the SSH user has write permissions and /tmp has available space.",
            path,
            b,
        )
        return None

    def _remote_stat_u_g_a(self, path: str) -> tuple[str | None, str | None, str | None]:
        """
        Return (uid, gid, mode) as strings, best-effort; None if unavailable.
        Uses one stat call to reduce RTT.
        """
        if not self._has("stat"):
            return None, None, None
        out = self._ssh(f"stat -c '%u %g %a' -- {shlex.quote(path)} 2>/dev/null || true").strip()
        if not out:
            return None, None, None
        parts = out.split()
        if len(parts) != 3:
            return None, None, None
        uid, gid, mode = parts
        if not (uid.isdigit() and gid.isdigit() and mode.isdigit()):
            return None, None, None
        return uid, gid, mode

    # one local over the limit; splitting the payload-building steps would hurt readability
    # pylint: disable-next=too-many-locals
    def _write_remote_file_atomic(
        self,
        path: str,
        content: str,
        mode: str = "0644",
        *,
        preserve_owner_mode: bool = True,
    ) -> None:
        """
        Atomic-ish update:
          - mktemp
          - write content (base64 preferred; chunked if large; fallback to heredoc with unique marker)
          - chmod/chown (best-effort)
          - mv over target
          - sync

        Safety:
          - avoids fixed heredoc markers ("EOF") to prevent accidental truncation
          - chunked base64 avoids huge command lines if content grows
        """
        if self.opts.dry_run:
            self.logger.info("DRY-RUN: would write %s (%d bytes)", path, len(content))
            return

        tmp = self._ssh(
            "mktemp /tmp/h2kvm.livefix.XXXXXX 2>/dev/null || mktemp /run/h2kvm.livefix.XXXXXX"
        ).strip()
        if not tmp:
            raise RuntimeError(
                "Failed to create temporary file on the remote host. "
                "Check that /tmp has available space and the SSH user has write permissions."
            )

        uid: str | None = None
        gid: str | None = None
        orig_mode: str | None = None
        if preserve_owner_mode and self._remote_exists(path):
            uid, gid, orig_mode = self._remote_stat_u_g_a(path)

        effective_mode = (orig_mode or "").strip() if preserve_owner_mode else ""
        if not effective_mode:
            effective_mode = mode

        payload_lines: list[str] = []
        payload_lines.append("set -e")
        payload_lines.append("umask 022")
        payload_lines.append(f": > {shlex.quote(tmp)}")  # truncate/create

        # Transfer content
        if self._has("base64"):
            b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")

            if len(b64) <= self._INLINE_B64_MAX_CHARS:
                payload_lines.append(f"printf %s {shlex.quote(b64)} | base64 -d >> {shlex.quote(tmp)}")
            else:
                # Chunked decode to avoid giant one-liners.
                # We still build one sh script, but each chunk line is small.
                payload_lines.append("# chunked base64 decode")
                for i in range(0, len(b64), self._B64_CHUNK_CHARS):
                    chunk = b64[i : i + self._B64_CHUNK_CHARS]
                    payload_lines.append(f"printf %s {shlex.quote(chunk)} | base64 -d >> {shlex.quote(tmp)}")
        else:
            self._warn_once(
                "missing_base64",
                "Remote is missing 'base64'; falling back to heredoc writer (still safe, slightly less robust).",
            )
            marker = f"__H2KVM_EOF_{U.now_ts()}_{re.sub(r'[^A-Za-z0-9]+', '_', tmp)}__"
            payload_lines.append(f"cat >> {shlex.quote(tmp)} <<'{marker}'")
            payload_lines.append(content)
            payload_lines.append(marker)

        payload_lines.append(f"chmod {shlex.quote(effective_mode)} {shlex.quote(tmp)} 2>/dev/null || true")
        if preserve_owner_mode and uid and gid:
            payload_lines.append(
                f"chown {shlex.quote(uid)}:{shlex.quote(gid)} {shlex.quote(tmp)} 2>/dev/null || true"
            )

        payload_lines.append(f"mv -f {shlex.quote(tmp)} {shlex.quote(path)}")
        payload_lines.append("sync 2>/dev/null || true")

        payload = "\n".join(payload_lines) + "\n"
        self._ssh("sh -lc " + shlex.quote(payload))

    # fstab rewrite

    def _convert_spec_to_stable(self, spec: str) -> str:
        """
        Convert /dev/disk/by-path/* to a stable spec, preferring:
          UUID=, PARTUUID=, LABEL=, PARTLABEL=
        """
        if not self._has("readlink"):
            self._warn_once(
                "missing_readlink",
                "Remote is missing 'readlink'; cannot resolve by-path symlinks, leaving entries unchanged.",
            )
            return spec

        resolved = self._readlink_f(spec)
        if not resolved:
            self.logger.debug("fstab: readlink -f failed for %s", spec)
            return spec

        if not self._is_remote_blockdev(resolved):
            self.logger.debug("fstab: resolved path is not a block dev: %s -> %s", spec, resolved)
            return spec

        if not self._has("blkid"):
            self._warn_once(
                "missing_blkid",
                "Remote is missing 'blkid'; cannot map by-path to UUID/PARTUUID, leaving entries unchanged.",
            )
            return spec

        for key, prefix in (
            ("UUID", "UUID="),
            ("PARTUUID", "PARTUUID="),
            ("LABEL", "LABEL="),
            ("PARTLABEL", "PARTLABEL="),
        ):
            v = self._blkid(resolved, key)
            if v:
                return prefix + v

        return spec

    @staticmethod
    def _split_comment(line: str) -> tuple[str, str]:
        s = line.rstrip("\n")
        if not s.strip():
            return s, ""
        if s.lstrip().startswith("#"):
            return s, ""
        m = re.search(r"\s#", s)
        if not m:
            return s, ""
        i = m.start()
        return s[:i].rstrip(), s[i:].lstrip()

    def _rewrite_fstab(self, content: str) -> tuple[str, int, int, list[dict[str, str]]]:
        """
        Returns:
          (new_content, changed_count, seen_bypath_count, changes)
        where changes is a list of {"from": old, "to": new}.
        """
        changed = 0
        seen = 0
        changes: list[dict[str, str]] = []
        out_lines: list[str] = []

        for line in content.splitlines(keepends=False):
            if not line.strip() or line.lstrip().startswith("#"):
                out_lines.append(line + "\n")
                continue

            data, comment = self._split_comment(line)
            parts = data.split()
            if len(parts) < 2:
                out_lines.append(line + "\n")
                continue

            spec = parts[0]
            if spec.startswith("/dev/disk/by-path/"):
                seen += 1
                new_spec = self._convert_spec_to_stable(spec)
                if new_spec != spec:
                    parts[0] = new_spec
                    changed += 1
                    changes.append({"from": spec, "to": new_spec})

            rebuilt = "\t".join(parts)
            if comment:
                if not comment.startswith("#"):
                    comment = "# " + comment
                rebuilt = rebuilt + "\t" + comment

            out_lines.append(rebuilt.rstrip() + "\n")

        return "".join(out_lines), changed, seen, changes

    # VMware tools removal (multi-distro best-effort)

    def _remove_vmware_tools(self) -> None:
        self.logger.info("Removing VMware tools (live)...")

        pkgs = [
            "open-vm-tools",
            "open-vm-tools-desktop",
            "vmware-tools",
            "vmware-tools-desktop",
            "vmtoolsd",
        ]

        # Stop services early (best-effort)
        self._run_best_effort(
            [
                "systemctl disable --now vmware-tools 2>/dev/null || true",
                "systemctl disable --now vmtoolsd 2>/dev/null || true",
                "rc-service vmware-tools stop 2>/dev/null || true",
                "rc-service vmtoolsd stop 2>/dev/null || true",
            ]
        )

        if self._has("apt-get"):
            self._run_best_effort(
                [
                    "DEBIAN_FRONTEND=noninteractive apt-get remove -y "
                    + " ".join(map(shlex.quote, pkgs))
                    + " 2>/dev/null || true",
                    "DEBIAN_FRONTEND=noninteractive apt-get autoremove -y 2>/dev/null || true",
                ]
            )
        elif self._has("dnf"):
            self._run_best_effort(
                ["dnf remove -y " + " ".join(map(shlex.quote, pkgs)) + " 2>/dev/null || true"]
            )
        elif self._has("yum"):
            self._run_best_effort(
                ["yum remove -y " + " ".join(map(shlex.quote, pkgs)) + " 2>/dev/null || true"]
            )
        elif self._has("zypper"):
            self._run_best_effort(
                ["zypper -n rm " + " ".join(map(shlex.quote, pkgs)) + " 2>/dev/null || true"]
            )
        elif self._has("pacman"):
            self._run_best_effort(
                ["pacman -Rns --noconfirm " + " ".join(map(shlex.quote, pkgs)) + " 2>/dev/null || true"]
            )
        elif self._has("apk"):
            self._run_best_effort(["apk del " + " ".join(map(shlex.quote, pkgs)) + " 2>/dev/null || true"])
        elif self._has("xbps-remove"):
            self._run_best_effort(
                ["xbps-remove -Ry " + " ".join(map(shlex.quote, pkgs)) + " 2>/dev/null || true"]
            )
        elif self._has("emerge"):
            self._run_best_effort(["emerge -C " + " ".join(map(shlex.quote, pkgs)) + " 2>/dev/null || true"])
        else:
            self.logger.warning(
                "No known package manager found; skipping package removal.\n"
                "    Supported: dnf, yum, apt, zypper, pacman, apk, xbps, emerge.\n"
                "    Manually remove VMware tools after migration if needed."
            )

        # Cleanup leftovers (best-effort)
        self._run_best_effort(
            [
                "rc-update del vmware-tools default 2>/dev/null || true",
                "rc-update del vmtoolsd default 2>/dev/null || true",
                "rm -f /etc/init.d/vmware-tools /etc/init.d/vmtoolsd 2>/dev/null || true",
                "rm -f /etc/systemd/system/vmware-tools.service "
                "/etc/systemd/system/vmtoolsd.service 2>/dev/null || true",
            ]
        )

        uninstaller = "/usr/bin/vmware-uninstall-tools.pl"
        if self._remote_exists(uninstaller):
            self._run_best_effort([f"{shlex.quote(uninstaller)} 2>/dev/null || true"])

        self._run_best_effort(
            [
                "rm -rf /etc/vmware-tools /usr/lib/vmware-tools /var/log/vmware-* 2>/dev/null || true",
            ]
        )

        self.logger.info("VMware tools removal attempted.")

    # LUKS+TPM preparation

    # LUKS+TPM re-keying covers several device/tool combinations (clevis vs.
    # systemd-cryptenroll) that are safer handled inline than split apart.
    # pylint: disable-next=too-many-locals,too-many-branches,too-many-statements
    def _prepare_luks_tpm(self) -> dict[str, Any]:
        """
        Prepare LUKS+TPM volumes for v2v migration.

        Problem: LUKS sealed to TPM only — after v2v the KVM vTPM has different
        seeds so TPM unlock fails (BSOD / initramfs prompt).

        Solution: While the VM is running on VMware (TPM is valid), detect
        whether the guest uses clevis or systemd-cryptenroll, recover the
        TPM-sealed passphrase, add a new passphrase keyslot, and unbind TPM.

        Supports: Ubuntu 22.04 (clevis), Ubuntu 24.04+ (systemd-cryptenroll),
                  Fedora/RHEL/SUSE (clevis or systemd-cryptenroll)
        """
        passphrase = self.opts.luks_passphrase
        if not passphrase:
            self.logger.debug("No LUKS passphrase provided; skipping LUKS+TPM preparation.")
            return {"skipped": True, "reason": "no passphrase"}

        self.logger.info("LUKS+TPM preparation: detecting encrypted volumes...")

        # Detect LUKS devices
        devs = self._ssh("blkid -t TYPE=crypto_LUKS -o device 2>/dev/null || true").strip()
        if not devs:
            self.logger.info("No LUKS devices found.")
            return {"skipped": True, "reason": "no LUKS devices"}

        has_clevis = self._has("clevis")
        has_cryptenroll = self._has("systemd-cryptenroll")
        self.logger.info("  clevis: %s, systemd-cryptenroll: %s", has_clevis, has_cryptenroll)

        results: list[dict[str, Any]] = []

        for dev in devs.splitlines():
            dev = dev.strip()
            if not dev:
                continue

            self.logger.info("Processing LUKS device: %s", dev)
            result: dict[str, Any] = {"device": dev, "success": False}

            if self.opts.dry_run:
                self.logger.info("  DRY-RUN: would prepare %s for v2v", dev)
                result["dry_run"] = True
                results.append(result)
                continue

            # Try clevis TPM2 recovery first
            tpm_detected = False
            recovered = False
            if has_clevis:
                tpm_slot = self._ssh(
                    f"clevis luks list -d {shlex.quote(dev)} 2>/dev/null"
                    " | grep -i tpm2 | cut -d: -f1 | head -1 || true"
                ).strip()
                if tpm_slot:
                    tpm_detected = True
                    self.logger.info("  Detected: clevis TPM2 binding in slot %s", tpm_slot)
                    recovered_pass = self._ssh(
                        f"clevis luks pass -d {shlex.quote(dev)} -s {shlex.quote(tpm_slot)} 2>/dev/null || true"
                    ).strip()
                    if recovered_pass:
                        self.logger.info(
                            "  Recovered TPM-sealed passphrase (length: %d)", len(recovered_pass)
                        )
                        # Add new keyslot using recovered passphrase
                        add_rc = self._ssh(
                            f"printf '%s' {shlex.quote(recovered_pass)} > /tmp/.h2k_oldkey"
                            f" && printf '%s' {shlex.quote(passphrase)} > /tmp/.h2k_newkey"
                            f" && cryptsetup luksAddKey {shlex.quote(dev)}"
                            f" --key-file /tmp/.h2k_oldkey --key-slot 7 /tmp/.h2k_newkey 2>&1"
                            f" ; shred -u /tmp/.h2k_oldkey /tmp/.h2k_newkey 2>/dev/null; echo RC=$?"
                        )
                        if "RC=0" in add_rc:
                            self.logger.info("  Passphrase keyslot 7 added.")
                            recovered = True
                            result["success"] = True
                        else:
                            self.logger.warning("  Failed to add keyslot: %s", add_rc.strip())

                    # Unbind clevis TPM
                    if recovered:
                        self._ssh(
                            f"clevis luks unbind -d {shlex.quote(dev)}"
                            f" -s {shlex.quote(tpm_slot)} -f 2>/dev/null || true"
                        )
                        self.logger.info("  Clevis TPM2 unbound.")
                        result["tpm_unbound"] = True

            # Try systemd-cryptenroll TPM2 detection
            if not tpm_detected and has_cryptenroll:
                tpm_token = self._ssh(
                    f"cryptsetup luksDump {shlex.quote(dev)} 2>/dev/null | grep -c 'systemd-tpm2' || echo 0"
                ).strip()
                tpm_token = tpm_token.splitlines()[0].strip() if tpm_token else "0"
                if tpm_token.isdigit() and int(tpm_token) > 0:
                    tpm_detected = True
                    self.logger.info("  Detected: systemd-cryptenroll TPM2 token")

            # Fallback: add keyslot with provided passphrase
            if not recovered:
                self.logger.info("  Adding passphrase keyslot 7 with provided passphrase...")
                add_rc = self._ssh(
                    f"printf '%s' {shlex.quote(passphrase)} > /tmp/.h2k_key"
                    f" && cryptsetup luksAddKey {shlex.quote(dev)}"
                    f" --key-file /tmp/.h2k_key --key-slot 7 /tmp/.h2k_key 2>&1"
                    f" ; shred -u /tmp/.h2k_key 2>/dev/null; echo RC=$?"
                )
                if "RC=0" in add_rc:
                    self.logger.info("  Passphrase keyslot 7 added.")
                    result["success"] = True
                else:
                    self.logger.warning("  Could not add keyslot. Wrong passphrase or TPM-only volume.")

            # Unbind systemd-cryptenroll TPM if detected
            if tpm_detected and has_cryptenroll and not has_clevis:
                wipe_rc = self._ssh(
                    f"systemd-cryptenroll --wipe-slot=tpm2 {shlex.quote(dev)} 2>&1; echo RC=$?"
                )
                if "RC=0" in wipe_rc:
                    self.logger.info("  systemd-cryptenroll TPM2 slot wiped.")
                    result["tpm_unbound"] = True
                else:
                    self.logger.warning("  Could not wipe TPM2 slot (may need passphrase).")

            results.append(result)

        success_count = sum(1 for r in results if r.get("success"))
        self.logger.info(
            "LUKS+TPM preparation: %d/%d devices prepared.",
            success_count,
            len(results),
        )
        return {"devices": results, "prepared": success_count}

    # Entrypoint

    def run(self) -> dict[str, Any]:
        """Run the live fix sequence over SSH and return a summary report."""
        U.banner(self.logger, "Live fix (SSH)")
        self.sshc.check()

        # ---- LUKS+TPM preparation (must run first, before any reboot-triggering changes)
        luks_report = self._prepare_luks_tpm()

        # ---- fstab rewrite
        fstab = self._read_remote_file("/etc/fstab")
        if self.opts.print_fstab:
            print("\n--- /etc/fstab (live before) ---\n" + (fstab or ""))

        new_fstab, changed, seen_bypath, changes = self._rewrite_fstab(fstab or "")

        if seen_bypath > 0 and changed == 0:
            self.logger.info(
                "fstab (live): found by-path entries=%d, converted=0 (tools missing or no UUID/PARTUUID/LABEL?)",
                seen_bypath,
            )
        else:
            self.logger.info("fstab (live): by-path_entries=%d converted=%d", seen_bypath, changed)

        if self.opts.print_fstab:
            print("\n--- /etc/fstab (live after) ---\n" + (new_fstab or ""))

        if changed > 0:
            if self.opts.dry_run:
                self.logger.info("DRY-RUN: would update /etc/fstab (live).")
            else:
                if not self.opts.no_backup:
                    self._backup("/etc/fstab")
                self._write_remote_file_atomic(
                    "/etc/fstab", new_fstab, mode="0644", preserve_owner_mode=True
                )
                self.logger.info("/etc/fstab updated (live).")

        # ---- optional VMware tools removal
        if self.opts.remove_vmware_tools:
            if self.opts.dry_run:
                self.logger.info("DRY-RUN: would remove VMware tools (live).")
            else:
                self._remove_vmware_tools()

        # ---- GRUB fixer (owns distro detection + regen logic)
        grub_report: dict[str, Any] | None = None
        if self.opts.update_grub or self.opts.regen_initramfs:
            self.logger.info("Running LiveGrubFixer...")
            gf = LiveGrubFixer(
                logger=self.logger,
                sshc=self.sshc,
                dry_run=self.opts.dry_run,
                no_backup=self.opts.no_backup,
                update_grub=self.opts.update_grub,
                regen_initramfs=self.opts.regen_initramfs,
            )
            grub_report = gf.run()

        self.logger.info("Live fix completed.")
        return {
            "dry_run": self.opts.dry_run,
            "luks_tpm": luks_report,
            "fstab_by_path_seen": seen_bypath,
            "fstab_changed": changed,
            "fstab_changes": changes,  # list of {"from": "...", "to": "..."}
            "update_grub": self.opts.update_grub,
            "regen_initramfs": self.opts.regen_initramfs,
            "remove_vmware_tools": self.opts.remove_vmware_tools,
            "grub_report": grub_report,
        }
