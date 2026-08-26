# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""VMware Tools removal for clean VM migration to KVM."""

# h2kvm/fixers/offline/vmware_tools_remover.py
from __future__ import annotations

import fnmatch
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from h2kvm.core.utils import U

if TYPE_CHECKING:
    import logging


@dataclass
class RemovalResult:  # pylint: disable=too-many-instance-attributes
    # reason: flat result record tallying every distinct category of change made by
    # the VMware tools removal run (paths, services, symlinks, hints, touched files, etc).
    """Outcome of an offline VMware tools removal run."""

    removed_paths: list[str]
    removed_services: list[str]
    removed_symlinks: list[str]
    package_hints: list[str]
    touched_files: list[str]
    errors: list[str]
    distro_id: str = ""
    warnings: list[str] = None  # type: ignore


class OfflineVmwareToolsRemover:  # pylint: disable=too-many-instance-attributes,too-few-public-methods
    # reason: attributes hold independent, orthogonal configuration for the removal run
    # (mount point, dry-run/backup flags, extra paths/units, chroot opt-in); the class
    # deliberately exposes a single `run()` entry point with the rest as private helpers.
    """
    OFFLINE VMware tools removal on a mounted filesystem tree.

    What "offline" means here:
      - No execution of guest package manager (unless you opt-in to chroot mode)
      - We remove unit files, SysV scripts, known vmware tooling binaries/dirs
      - We also *neutralize* autostarts by removing wants symlinks + disabling
        a few common launch hooks.

    Goals:
      - Make the converted guest stop trying to run VMware agents on KVM.
      - Avoid breaking unrelated system services.
      - Be auditable: produce a result dict for reports.

    Safety:
      - Optional backups for every removed file (atomic + timestamped)
      - Dry-run mode logs everything but makes no changes.
      - Restricts all operations to mount_point subtree (no escape).
    """

    # Common binaries / dirs (broad but conservative)
    DEFAULT_PATHS_TO_REMOVE = [
        "/etc/vmware-tools/",
        "/etc/vmware/",
        "/usr/lib/vmware-tools/",
        "/usr/lib/open-vm-tools/",
        "/usr/lib64/vmware-tools/",
        "/usr/lib64/open-vm-tools/",
        "/usr/share/open-vm-tools/",
        "/usr/share/vmware-tools/",
        "/var/lib/vmware-tools/",
        "/var/log/vmware/",
        "/var/run/vmware/",
        "/usr/bin/vmtoolsd",
        "/usr/sbin/vmtoolsd",
        "/usr/bin/vmware-*",
        "/usr/sbin/vmware-*",
        "/usr/bin/vmware-toolbox-cmd",
        "/usr/sbin/vmware-toolbox-cmd",
        "/sbin/vmware-*",
        "/bin/vmware-*",
    ]

    # systemd service names seen in the wild
    DEFAULT_SYSTEMD_UNITS = [
        "open-vm-tools.service",
        "vmtoolsd.service",
        "vmware-tools.service",
        "vgauth.service",
        "vmware-vgauth.service",
        "vmware-vmblock-fuse.service",
        "vmware-vmblock-fuse.mount",
    ]

    # SysV init script names / patterns
    DEFAULT_INITD = [
        "/etc/init.d/vmware-tools",
        "/etc/init.d/open-vm-tools",
        "/etc/init.d/vmtoolsd",
        "/etc/init.d/vgauth",
    ]

    # Common systemd unit locations (distro dependent)
    SYSTEMD_UNIT_DIRS = [
        "/etc/systemd/system",
        "/lib/systemd/system",
        "/usr/lib/systemd/system",
    ]

    # Common wants directories we should unlink from
    SYSTEMD_WANTS_DIRS = [
        "/etc/systemd/system/multi-user.target.wants",
        "/etc/systemd/system/graphical.target.wants",
        "/etc/systemd/system/default.target.wants",
        "/etc/systemd/system/sysinit.target.wants",
    ]

    def __init__(  # pylint: disable=too-many-arguments
        self,
        logger: logging.Logger,
        mount_point: Path,
        *,
        dry_run: bool,
        no_backup: bool,
        # optional advanced knobs
        extra_paths: list[str] | None = None,
        extra_units: list[str] | None = None,
        allow_chroot: bool = False,
    ):
        self.logger = logger
        self.mount_point = mount_point.resolve()
        self.dry_run = dry_run
        self.no_backup = no_backup
        self.extra_paths = extra_paths or []
        self.extra_units = extra_units or []
        self.allow_chroot = allow_chroot

        self._result = RemovalResult(
            removed_paths=[],
            removed_services=[],
            removed_symlinks=[],
            package_hints=[],
            touched_files=[],
            errors=[],
            distro_id="",
            warnings=[],
        )

    # Path safety helpers
    def _resolve_path(self, rel_path: str) -> Path:
        # Ensure a caller can't escape mount_point with "../"
        # We resolve and then validate prefix.
        candidate = self.mount_point / rel_path.lstrip("/")
        # Reject symlinks before resolution to prevent TOCTOU race
        if candidate.is_symlink():
            raise RuntimeError(
                f"Security: refusing to follow symlink at '{rel_path}' — "
                f"this prevents potential path traversal in the guest disk."
            )
        candidate = candidate.resolve()
        try:
            candidate.relative_to(self.mount_point)
        except ValueError:
            raise RuntimeError(
                f"Security: path '{rel_path}' resolves outside the mounted filesystem. "
                f"This may indicate a symlink escape attempt in the guest disk."
            ) from None
        return candidate

    def _rel_from_mount(self, p: Path) -> str:
        return "/" + str(p.relative_to(self.mount_point))

    def _remote_exists(self, path: str) -> bool:
        try:
            return self._resolve_path(path).exists()
        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort existence probe -- any resolution/OS error just
            # means "doesn't exist" for this caller's purposes.
            return False

    def _read_remote_file(self, path: str) -> str:
        try:
            p = self._resolve_path(path)
            if p.exists() and p.is_file():
                return p.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort read -- caller treats "" as "couldn't read it".
            pass
        return ""

    def _write_remote_file_atomic(self, path: str, content: str, mode: int = 0o644) -> None:
        if self.dry_run:
            self.logger.info(f"DRY-RUN: would write {path} (len={len(content)})")
            self._result.touched_files.append(path)
            return
        p = self._resolve_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", delete=False, dir=str(p.parent), encoding="utf-8") as tmp:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_name = tmp.name
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, str(p))
        self._result.touched_files.append(path)

    def _backup_remote_path(self, path: str) -> None:
        if self.no_backup or self.dry_run:
            return
        try:
            p = self._resolve_path(path)
            if not p.exists():
                return
            b = Path(str(p) + f".bak.h2kvm.{U.now_ts()}")
            if p.is_file() or p.is_symlink():
                shutil.copy2(str(p), str(b), follow_symlinks=False)
            elif p.is_dir():
                shutil.copytree(str(p), str(b), symlinks=True)
            self.logger.info(f"Backup: {path} -> {self._rel_from_mount(b)}")
        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort fixer step -- a failed backup must not abort the
            # whole migration; recorded in the result's errors list instead.
            self._result.errors.append(f"backup:{path}:{e}")
            self.logger.warning(f"Backup failed for {path}: {e}")

    def _remove_remote_path(self, path: str) -> None:
        try:
            p = self._resolve_path(path)
            if not p.exists():
                return
            if self.dry_run:
                self.logger.info(f"DRY-RUN: would remove {path}")
                self._result.removed_paths.append(path)
                return

            # Back up first (unless opted out)
            self._backup_remote_path(path)

            if p.is_symlink() or p.is_file():
                p.unlink()
            elif p.is_dir():
                shutil.rmtree(str(p))
            else:
                # fallback: attempt unlink
                try:
                    p.unlink()
                except Exception:  # pylint: disable=broad-exception-caught
                    # reason: last-resort cleanup -- if unlink fails for any reason
                    # (e.g. it's actually a directory), fall back to a forced rmtree.
                    shutil.rmtree(str(p), ignore_errors=True)

            self.logger.info(f"Removed {path}")
            self._result.removed_paths.append(path)
        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort fixer step -- a failed removal must not abort the
            # whole migration; recorded in the result's errors list instead.
            self._result.errors.append(f"remove:{path}:{e}")
            self.logger.warning(f"Failed removing {path}: {e}")

    # Distro detection
    def _detect_distro_id(self) -> str:
        os_release = self._read_remote_file("/etc/os-release")
        # robust parse: ID=... may be quoted
        m = re.search(r'^\s*ID\s*=\s*"?([^"\n]+)"?\s*$', os_release, re.MULTILINE)
        distro = m.group(1).strip().lower() if m else ""
        self._result.distro_id = distro
        return distro

    # Unit / service disabling
    def _unlink_if_symlink(self, path: str) -> None:
        try:
            p = self._resolve_path(path)
            if not p.exists():
                return
            if not p.is_symlink():
                return
            if self.dry_run:
                self.logger.info(f"DRY-RUN: would unlink {path}")
                self._result.removed_symlinks.append(path)
                return
            self._backup_remote_path(path)
            p.unlink()
            self.logger.info(f"Unlinked {path}")
            self._result.removed_symlinks.append(path)
        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort fixer step -- a failed unlink must not abort the
            # whole migration; recorded in the result's errors list instead.
            self._result.errors.append(f"unlink:{path}:{e}")
            self.logger.warning(f"Failed unlinking {path}: {e}")

    def _disable_systemd_units(  # pylint: disable=too-many-nested-blocks
        self, unit_names: list[str]
    ) -> None:
        # reason: for each unit, checking every unit-dir/wants-dir plus the
        # templated-instance fallback naturally nests several levels of for/if.
        # Remove unit files, and unlink wants symlinks
        for unit in unit_names:
            # Unit file locations
            for d in self.SYSTEMD_UNIT_DIRS:
                self._remove_remote_path(f"{d.rstrip('/')}/{unit}")

            # Wants symlinks
            for wd in self.SYSTEMD_WANTS_DIRS:
                self._unlink_if_symlink(f"{wd.rstrip('/')}/{unit}")

            # also catch templated instances: vmtoolsd@.service and vmtoolsd@foo.service
            # Remove templates + instances if present.
            if "@" not in unit:
                templ = unit.replace(".service", "@.service")
                for d in self.SYSTEMD_UNIT_DIRS:
                    self._remove_remote_path(f"{d.rstrip('/')}/{templ}")
                for wd in self.SYSTEMD_WANTS_DIRS:
                    # instances: vmtoolsd@*.service (match on filesystem)
                    base_dir = self._resolve_path(wd)
                    if base_dir.is_dir():
                        for f in base_dir.iterdir():
                            if f.is_symlink() and fnmatch.fnmatch(
                                f.name, unit.replace(".service", "@*.service")
                            ):
                                self._unlink_if_symlink(self._rel_from_mount(f))

            self._result.removed_services.append(unit)

    def _disable_sysv(self) -> None:
        # /etc/init.d scripts
        for script in self.DEFAULT_INITD:
            if self._remote_exists(script):
                self._remove_remote_path(script)
                self._result.removed_services.append(Path(script).name)

        # rc?.d links
        for level in ["0", "1", "2", "3", "4", "5", "6"]:
            rc_dir = f"/etc/rc{level}.d"
            rc_path = self._resolve_path(rc_dir)
            if not rc_path.is_dir():
                continue
            for entry in rc_path.iterdir():
                name = entry.name
                # typical: S??vmware-tools / K??vmware-tools / S??open-vm-tools / etc.
                if re.match(r"^[SK]\d\d(vmw|vmware|vmtools|vgauth)", name, re.IGNORECASE):
                    rel = self._rel_from_mount(entry)
                    if entry.is_symlink():
                        self._unlink_if_symlink(rel)
                    else:
                        self._remove_remote_path(rel)

    # Known files / dirs removal
    def _remove_known_files(self, patterns: list[str]) -> None:
        # Patterns may include globs like /usr/bin/vmware-*
        for pat in patterns:
            if "*" not in pat and "?" not in pat and "[" not in pat:
                if self._remote_exists(pat):
                    self._remove_remote_path(pat)
                continue

            # Glob: resolve parent and glob within it
            parent = str(Path(pat).parent)
            name_pat = Path(pat).name
            try:
                d = self._resolve_path(parent)
                if not d.is_dir():
                    continue
                for f in d.iterdir():
                    if fnmatch.fnmatch(f.name, name_pat):
                        self._remove_remote_path(self._rel_from_mount(f))
            except Exception as e:  # pylint: disable=broad-exception-caught
                # reason: best-effort fixer step -- one bad glob pattern must not
                # abort the whole migration; recorded in the result's errors list instead.
                self._result.errors.append(f"glob:{pat}:{e}")
                self.logger.debug(f"Glob failed for {pat}: {e}")

    # Offline "package removal" hints / optional chroot mode
    def _package_manager_hints(self, distro: str) -> list[str]:
        pkgs = ["open-vm-tools", "open-vm-tools-desktop", "vmware-tools", "vmware-tools-desktop", "vgauth"]
        # Keep hints as commands the user can run after boot (or in chroot)
        hints = []
        if distro in ("ubuntu", "debian"):
            hints.append("apt-get purge -y " + " ".join(pkgs))
            hints.append("apt-get autoremove -y")
        elif distro in ("fedora", "rhel", "centos", "rocky", "almalinux", "mariner", "photon"):
            hints.append("dnf remove -y " + " ".join(pkgs) + " || yum remove -y " + " ".join(pkgs))
        elif distro in ("opensuse", "sles", "sled"):
            hints.append("zypper --non-interactive rm -y " + " ".join(pkgs))
        elif distro == "arch":
            hints.append("pacman -Rns --noconfirm " + " ".join(pkgs))
        else:
            hints.append("Remove VMware tools packages with your distro package manager: " + " ".join(pkgs))
        return hints

    def _remove_packages_offline(self, distro: str) -> None:
        # Offline package removal is intentionally not done by default.
        self._result.warnings.append(
            "Offline package removal is limited; prefer running inside guest after boot, or enable chroot mode."
        )
        self._result.package_hints = self._package_manager_hints(distro)

        self.logger.warning(
            "Offline package removal is limited; prefer removing packages inside the guest after first boot."
        )
        for h in self._result.package_hints:
            self.logger.info(f"Package removal hint: {h}")

        # Optional: chroot mode (advanced; depends on host capabilities and mount completeness)
        if not self.allow_chroot:
            return

        # If you enable this, you *must* have /proc, /sys, /dev bind mounted too.
        # We’ll just sanity-check and refuse if too risky.
        proc_ok = (self.mount_point / "proc").exists()
        sys_ok = (self.mount_point / "sys").exists()
        dev_ok = (self.mount_point / "dev").exists()
        if not (proc_ok and sys_ok and dev_ok):
            self._result.warnings.append(
                "Chroot mode requested but /proc, /sys, /dev are not present under mount. Skipping."
            )
            self.logger.warning(
                "Chroot mode requested but mount_point lacks /proc, /sys, /dev. Skipping chroot removal."
            )
            return

        # We still won’t run it automatically unless you really want it.
        self._result.warnings.append(
            "Chroot mode is enabled, but automatic execution is intentionally not performed here."
        )
        self.logger.warning(
            "Chroot mode enabled, but automatic package manager execution is intentionally not performed."
        )

    # Extra hardening: neutralize misc autostart hooks
    def _neutralize_autostart_hooks(self) -> None:
        """
        Some distros start vmtoolsd via:
          - /etc/rc.local
          - /etc/profile.d scripts
          - cron/systemd timers
        We do a *light-touch* approach:
          - comment out obvious vmtoolsd/vmware-tools invocations in rc.local if present.
        """
        rc_local_candidates = ["/etc/rc.local", "/etc/rc.d/rc.local"]
        for rc in rc_local_candidates:
            txt = self._read_remote_file(rc)
            if not txt:
                continue
            if not re.search(r"\b(vmtoolsd|open-vm-tools|vmware-tools)\b", txt, re.IGNORECASE):
                continue

            self.logger.info(f"Neutralizing VMware hooks in {rc}")
            lines = txt.splitlines(True)
            out = []
            changed = False
            for ln in lines:
                if re.search(
                    r"\b(vmtoolsd|open-vm-tools|vmware-tools)\b", ln, re.IGNORECASE
                ) and not ln.lstrip().startswith("#"):
                    out.append("# " + ln)
                    changed = True
                else:
                    out.append(ln)

            if changed:
                if not self.dry_run:
                    self._backup_remote_path(rc)
                self._write_remote_file_atomic(rc, "".join(out), mode=0o755)
                self._result.touched_files.append(rc)

    # Public API
    def run(self) -> RemovalResult:
        """Run the full offline VMware tools removal against `self.mount_point`."""
        U.banner(self.logger, "VMware tools removal (OFFLINE)")

        # distro detection
        distro = self._detect_distro_id()
        self.logger.info(f"Guest distro ID (best-effort): {distro or 'unknown'}")

        # package hints (offline)
        self._remove_packages_offline(distro)

        # disable services
        units = list(dict.fromkeys(self.DEFAULT_SYSTEMD_UNITS + self.extra_units))
        self._disable_systemd_units(units)
        self._disable_sysv()

        # remove known files
        paths = list(dict.fromkeys(self.DEFAULT_PATHS_TO_REMOVE + self.extra_paths))
        self._remove_known_files(paths)

        # neutralize misc autostarts
        self._neutralize_autostart_hooks()

        # final notes
        self.logger.info("VMware tools removal attempted offline.")
        self.logger.info(
            "For complete removal, remove packages inside the guest after first boot (see hints)."
        )

        return self._result
