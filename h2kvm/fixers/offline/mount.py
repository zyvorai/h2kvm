# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Filesystem mount/unmount utilities for offline VM fixing."""

# h2kvm/fixers/offline/mount.py
from __future__ import annotations

import contextlib
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from h2kvm.core.utils import U, guest_has_cmd
from h2kvm.fixers.filesystem import fixer as filesystem_fixer  # type: ignore
from h2kvm.fixers.filesystem.fstab import parse_btrfsvol_spec

# This TYPE_CHECKING guestfs/GuestFS typing shim is intentionally duplicated
# verbatim in h2kvm/fixers/offline/config_rewriter.py (and other offline
# fixer modules) -- it's a tiny, self-contained typing-only fallback, not
# shared business logic, so extracting it into a common helper would add an
# import indirection for no real benefit.
# pylint: disable=duplicate-code
if TYPE_CHECKING:
    import logging

    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        # Typing-only shim: named "guestfs" (not PascalCase) so that
        # `guestfs.GuestFS` annotations below resolve the same way whether or
        # not the real python3-guestfs bindings are installed.
        class guestfs:  # type: ignore  # pylint: disable=invalid-name,missing-class-docstring,too-few-public-methods
            class GuestFS(Protocol):  # pylint: disable=missing-class-docstring,too-few-public-methods
                ...


@dataclass
class RootMountResult:
    """Result of locating and mounting the guest's root filesystem."""

    inspect_root: str | None
    root_dev: str | None
    root_btrfs_subvol: str | None
    method: str
    details: dict[str, Any]


# holds dry-run + LUKS config plus opened-device tracking as separate fields
# pylint: disable-next=too-many-instance-attributes
class OfflineMountEngine:
    """
    Storage-stack + root-mount engine for OfflineFSFix.

    Responsibilities:
      - Additive storage activation: mdraid, zfs, lvm, luks-open
      - Root detection: inspect_os + scoring + fallback brute-force
      - Mount ladder: rw/ro/options + fsck best-effort retry
    """

    _BTRFS_COMMON_SUBVOLS = ["@", "@/", "@root", "@rootfs", "@/.snapshots/1/snapshot"]
    _ROOT_HINT_FILES = ["/etc/fstab", "/etc/os-release", "/bin/sh", "/sbin/init"]
    _ROOT_STRONG_HINTS = ["/etc/passwd", "/usr/bin/env", "/var/lib", "/proc"]  # heuristic only

    @staticmethod
    def _sanitize_subvol_path(subvol: str) -> str:
        """
        Sanitize BTRFS subvolume path to prevent path traversal and option injection.

        SECURITY: Validates subvolume paths to prevent:
        - Path traversal attacks (../)
        - Mount option injection (commas, special chars)
        - Command injection attempts

        Args:
            subvol: BTRFS subvolume path to validate

        Returns:
            Sanitized subvolume path

        Raises:
            ValueError: If subvolume path contains dangerous characters
        """
        if not subvol:
            raise ValueError(
                "Btrfs subvolume path cannot be empty. Provide a subvolume name (e.g., '@' or '@rootfs')."
            )

        # Check for path traversal attempts
        if ".." in subvol:
            raise ValueError(
                "Btrfs subvolume path contains '..', which is not allowed for security reasons. "
                "Use an absolute subvolume path instead (e.g., '@' or '@rootfs')."
            )

        # Check for null bytes (path truncation attack)
        if "\x00" in subvol:
            raise ValueError(
                "Btrfs subvolume path contains invalid characters (null byte). "
                "Check the subvolume name for corruption."
            )

        # Check for mount option injection attempts (commas separate mount options)
        if "," in subvol:
            raise ValueError(
                "Btrfs subvolume path cannot contain commas. "
                "Remove commas from the subvolume name or use a different subvolume."
            )

        # Check for shell metacharacters (defense in depth)
        dangerous_chars = [";", "&", "|", "`", "$", "(", ")", "<", ">", "\n", "\r"]
        for char in dangerous_chars:
            if char in subvol:
                raise ValueError(
                    f"Btrfs subvolume path contains an unsafe character ('{char}'). "
                    f"Use only alphanumeric characters, hyphens, underscores, and slashes."
                )

        # Normalize path separators and remove redundant slashes
        normalized = subvol.replace("\\", "/")
        # Remove double slashes but preserve leading slash
        parts = [p for p in normalized.split("/") if p]
        normalized = "/" + "/".join(parts) if normalized.startswith("/") else "/".join(parts)

        # Additional length check (defense in depth)
        if len(normalized) > 4096:
            raise ValueError(
                f"Btrfs subvolume path is too long ({len(normalized)} chars, max 4096). "
                f"Use a shorter subvolume path."
            )

        return normalized

    def __init__(  # pylint: disable=too-many-arguments  # config init, mostly keyword-only LUKS options
        self,
        logger: logging.Logger,
        *,
        dry_run: bool,
        # LUKS config
        luks_enable: bool = False,
        luks_passphrase: str | None = None,
        luks_passphrase_env: str | None = None,
        luks_keyfile: Path | None = None,
        luks_mapper_prefix: str = "h2kvm-crypt",
    ):
        self.logger = logger
        self.dry_run = bool(dry_run)

        self.luks_enable = bool(luks_enable)
        self.luks_passphrase = luks_passphrase
        self.luks_passphrase_env = luks_passphrase_env
        self.luks_keyfile = Path(luks_keyfile) if luks_keyfile else None
        self.luks_mapper_prefix = luks_mapper_prefix

        self._luks_opened: dict[str, str] = {}  # luks_dev -> /dev/mapper/name
        # Set when mount_root_bruteforce() detects a BitLocker-encrypted
        # partition; consumed by offline_fixer to explain a mount failure.
        self._bitlocker_detected = False

    # safe helpers

    @staticmethod
    def safe_umount_all(g: guestfs.GuestFS) -> None:
        """Unmount everything in the guestfs handle, ignoring any failure."""
        with contextlib.suppress(Exception):
            g.umount_all()

    # LUKS / LVM

    def _read_luks_key_bytes(self) -> bytes | None:
        try:
            if self.luks_keyfile and self.luks_keyfile.exists():
                return self.luks_keyfile.read_bytes()
        except OSError:
            pass

        pw = self.luks_passphrase
        if (not pw) and self.luks_passphrase_env:
            pw = os.environ.get(self.luks_passphrase_env)
        if pw:
            return pw.encode("utf-8")
        return None

    def activate_lvm(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Best-effort vgscan + vgchange -ay to bring up LVM volume groups."""
        audit: dict[str, Any] = {"attempted": False, "ok": False, "error": None}
        if not hasattr(g, "vgscan") or not hasattr(g, "vgchange_activate_all"):
            audit["error"] = (
                "LVM activation unavailable — the guestfs backend does not support vgscan/vgchange. "
                "If the disk uses LVM, try the libguestfs backend: --backend guestfs"
            )
            return audit
        audit["attempted"] = True
        try:
            g.vgscan()
            try:
                g.vgchange_activate_all(True)
            # older guestfs backends want an int, not a bool
            except Exception:  # pylint: disable=broad-exception-caught
                g.vgchange_activate_all(1)
            audit["ok"] = True
            return audit
        # best-effort LVM activation, must not abort the fixer
        except Exception as e:  # pylint: disable=broad-exception-caught
            audit["error"] = str(e)
            return audit

    def unlock_luks_devices(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Open any crypto_LUKS devices found on the disk using configured key material."""
        audit: dict[str, Any] = {
            "attempted": False,
            "configured": False,
            "enabled": bool(self.luks_enable),
            "passphrase_env": self.luks_passphrase_env,
            "keyfile": str(self.luks_keyfile) if self.luks_keyfile else None,
            "luks_devices": [],
            "opened": [],
            "skipped": [],
            "errors": [],
        }
        if not self.luks_enable:
            audit["skipped"].append("luks_disabled")
            return audit

        key_bytes = self._read_luks_key_bytes()
        audit["configured"] = bool(key_bytes)
        if not key_bytes:
            audit["skipped"].append("no_key_material_configured")
            return audit
        if not hasattr(g, "cryptsetup_open"):
            audit["errors"].append(
                "LUKS unlock unavailable — the guestfs backend does not support cryptsetup_open. "
                "Install python3-libguestfs and use --backend guestfs for LUKS support."
            )
            return audit

        try:
            fsmap = g.list_filesystems() or {}
        # best-effort LUKS detection, must not abort the fixer
        except Exception as e:  # pylint: disable=broad-exception-caught
            audit["errors"].append(
                f"Failed to enumerate disk filesystems for LUKS detection: {e}. "
                "The disk image may be corrupt or inaccessible. "
                "Verify the image with: qemu-img check <disk_path>"
            )
            return audit

        luks_devs = [U.to_text(dev) for dev, fstype in fsmap.items() if U.to_text(fstype) == "crypto_LUKS"]
        audit["luks_devices"] = luks_devs
        if not luks_devs:
            audit["skipped"].append("no_crypto_LUKS_devices_found")
            return audit

        audit["attempted"] = True
        for idx, dev in enumerate(luks_devs, 1):
            if dev in self._luks_opened:
                continue
            name = f"{self.luks_mapper_prefix}{idx}"
            try:
                key_str = (
                    key_bytes.decode("utf-8", errors="strict") if isinstance(key_bytes, bytes) else key_bytes
                )
                g.cryptsetup_open(dev, key_str, name)
                mapped = f"/dev/mapper/{name}"
                self._luks_opened[dev] = mapped
                audit["opened"].append({"device": dev, "mapped": mapped})
                self.logger.info(f"LUKS: opened {dev} -> {mapped}")
            # best-effort LUKS unlock, must not abort the fixer
            except Exception as e:  # pylint: disable=broad-exception-caught
                audit["errors"].append({"device": dev, "error": str(e)})
                self.logger.warning(
                    f"LUKS: failed to open {dev}: {e}\n"
                    f"    Check passphrase/keyfile: --luks-passphrase or --luks-keyfile\n"
                    f"    Or set via env var: --luks-passphrase-env VARNAME\n"
                    f"    Verify LUKS header: cryptsetup luksDump {dev}"
                )

        # After opening LUKS on the host, LVM PVs inside LUKS become visible.
        # Run vgscan + vgchange directly on the host (container can't see
        # /dev/mapper/* devices created by host cryptsetup).
        if audit["opened"]:
            try:
                # Force kernel to re-read partitions, then scan for LVM PVs
                subprocess.run(["partprobe"], capture_output=True, timeout=10, check=False)
                time.sleep(0.5)
                # Use --devicesfile "" to bypass LVM device filter
                # (Fedora/RHEL restrict LVM to /etc/lvm/devices/system.devices)
                subprocess.run(
                    ["pvscan", "--devicesfile", "", "--cache"], capture_output=True, timeout=10, check=False
                )
                subprocess.run(
                    ["vgscan", "--devicesfile", "", "--cache"], capture_output=True, timeout=10, check=False
                )
                subprocess.run(
                    ["vgchange", "--devicesfile", "", "-ay"], capture_output=True, timeout=10, check=False
                )
                subprocess.run(["lvscan", "--devicesfile", ""], capture_output=True, timeout=10, check=False)
                result = subprocess.run(
                    ["lvs", "--devicesfile", "", "--noheadings", "-o", "lv_path,vg_name"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if result.returncode == 0 and result.stdout.strip():
                    self.logger.info(
                        "LVM after LUKS open (host-direct): %s", result.stdout.strip().replace("\n", ", ")
                    )
                else:
                    self.logger.info("LVM: no volumes found after LUKS open")
            except (OSError, subprocess.SubprocessError) as e:
                self.logger.warning("LVM rescan after LUKS failed: %s", e)
            _ = self.activate_lvm(g)
        return audit

    # mdraid/zfs — additive

    def _guestfs_can_run(self, g: guestfs.GuestFS, prog: str) -> bool:
        try:
            return bool(getattr(g, "command", None)) and guest_has_cmd(g, prog)
        # best-effort capability probe, must not abort the fixer
        except Exception:  # pylint: disable=broad-exception-caught
            return False

    def activate_mdraid(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Best-effort `mdadm --assemble --scan --run` to bring up mdraid arrays."""
        audit: dict[str, Any] = {"attempted": False, "ok": False, "details": "", "error": None}
        if not self._guestfs_can_run(g, "mdadm"):
            audit["details"] = "mdadm_not_available_in_appliance"
            return audit
        audit["attempted"] = True
        try:
            g.command(["mdadm", "--assemble", "--scan", "--run"])
            audit["ok"] = True
            audit["details"] = "mdadm_assemble_scan_ok"
            return audit
        # best-effort mdraid activation, must not abort the fixer
        except Exception as e:  # pylint: disable=broad-exception-caught
            audit["error"] = str(e)
            audit["details"] = "mdadm_assemble_scan_failed"
            return audit

    def activate_zfs(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Best-effort `zpool import` to bring up ZFS pools found on the disk."""
        if not self._guestfs_can_run(g, "zpool"):
            return {"attempted": False, "ok": False, "reason": "zpool_not_available_in_appliance"}
        audit: dict[str, Any] = {"attempted": True, "ok": False, "pools": [], "error": None}
        try:
            out = g.command(["sh", "-lc", "ZPOOL_VDEV_NAME_PATH=1 zpool import 2>/dev/null || true"])
            text = U.to_text(out).strip()
            audit["pools"] = [ln.strip() for ln in text.splitlines() if ln.strip()][:100]
        # best-effort pool listing, must not abort the fixer
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        try:
            g.command(["sh", "-lc", "ZPOOL_VDEV_NAME_PATH=1 zpool import -a -N -f 2>/dev/null || true"])
            audit["ok"] = True
            return audit
        # best-effort ZFS activation, must not abort the fixer
        except Exception as e:  # pylint: disable=broad-exception-caught
            audit["error"] = str(e)
            return audit

    def pre_mount_activate_storage_stack(self, g: guestfs.GuestFS) -> dict[str, Any]:
        """Run mdraid, ZFS, and LVM activation before attempting to mount the root filesystem."""
        audit: dict[str, Any] = {"mdraid": None, "zfs": None, "lvm": None}
        audit["mdraid"] = self.activate_mdraid(g)
        audit["zfs"] = self.activate_zfs(g)
        audit["lvm"] = self.activate_lvm(g)
        return audit

    # mount logic

    def _try_mount_root(self, g: guestfs.GuestFS, dev: str, subvol: str | None, mode: str) -> None:
        # mode: "rw" | "ro" | "opts:<csv>"
        if subvol:
            # SECURITY: Validate subvolume path to prevent path traversal and option injection
            try:
                sanitized_subvol = self._sanitize_subvol_path(subvol)
            except ValueError as e:
                self.logger.exception(f"Rejecting dangerous subvolume path: {e}")
                raise RuntimeError(f"Btrfs subvolume path rejected for security reasons: {e}") from e

            opts = f"subvol={sanitized_subvol}"
            if self.dry_run or mode == "ro":
                opts = f"ro,{opts}"
            if mode.startswith("opts:"):
                extra = mode.split(":", 1)[1]
                opts = f"{extra},{opts}"
            g.mount_options(opts, dev, "/")
            return

        if mode == "rw" and not self.dry_run:
            g.mount(dev, "/")
            return
        if mode == "ro" or self.dry_run:
            g.mount_ro(dev, "/")
            return
        if mode.startswith("opts:"):
            opts = mode.split(":", 1)[1]
            if self.dry_run and "ro" not in opts:
                opts = f"ro,{opts}"
            g.mount_options(opts, dev, "/")
            return

        g.mount_ro(dev, "/")

    def mount_root_direct(self, g: guestfs.GuestFS, dev: str, subvol: str | None) -> None:
        """
        Mount ladder:
          1) rw/ro (original)
          2) ro + mount_options fallback (noload/norecovery)
          3) best-effort fsck then ro retry
        """
        filesystem_fixer.log_vfs_type_best_effort(self, g, dev)

        # 1) original path
        try:
            self._try_mount_root(g, dev, subvol, "rw" if not self.dry_run else "ro")
            return
        # first attempt of a multi-step mount ladder; failure falls through to the fallbacks below
        except Exception as first_err:  # pylint: disable=broad-exception-caught
            last_err: Exception = first_err  # type: ignore[assignment]

        # 2) fallback ladder
        tries = ["ro", "opts:noload", "opts:ro,noload", "opts:ro,norecovery"]
        for t in tries:
            self.safe_umount_all(g)
            try:
                self._try_mount_root(g, dev, subvol, t)
                return
            # best-effort mount ladder retry, must not abort the fixer
            except Exception as e:  # pylint: disable=broad-exception-caught
                last_err = e  # type: ignore[misc]

        # 3) fsck then ro retry
        self.safe_umount_all(g)
        _ = filesystem_fixer.best_effort_fsck(self, g, dev)

        self.safe_umount_all(g)
        try:
            self._try_mount_root(g, dev, subvol, "ro")
            return
        # final mount ladder retry, must not abort the fixer
        except Exception as e:  # pylint: disable=broad-exception-caught
            last_err = e  # type: ignore[misc]

        raise RuntimeError(
            f"Failed to mount root filesystem from {dev}"
            + (f" (btrfs subvol={subvol})" if subvol else "")
            + ". The filesystem may be corrupted or use an unsupported type. "
            "Try running fsck on the source disk before migration. "
            f"Detail: {last_err}"
        )

    def looks_like_root(self, g: guestfs.GuestFS) -> bool:
        """Heuristically check whether the currently-mounted filesystem looks like a Linux root."""
        hits = 0
        for p in self._ROOT_HINT_FILES:
            try:
                if g.is_file(p):
                    hits += 1
            # best-effort probe; a missing/unreadable path just doesn't count as a hit
            except Exception:  # pylint: disable=broad-exception-caught
                continue
        for p in self._ROOT_STRONG_HINTS:
            try:
                if p.endswith("/"):
                    if g.is_dir(p[:-1]):
                        hits += 1
                elif g.is_file(p) or g.is_dir(p):
                    hits += 1
            except Exception:  # pylint: disable=broad-exception-caught
                continue
        return hits >= 2

    # scores several independent heuristics; splitting them apart would obscure the scoring rules
    # pylint: disable-next=too-many-branches
    def score_root(self, g: guestfs.GuestFS) -> int:
        """Score how likely the currently-mounted filesystem is to be the true root (higher is better)."""
        score = 0
        for p in self._ROOT_HINT_FILES:
            try:
                if g.is_file(p):
                    score += 5
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        for p in self._ROOT_STRONG_HINTS:
            try:
                if p.endswith("/"):
                    if g.is_dir(p[:-1]):
                        score += 2
                elif g.is_file(p) or g.is_dir(p):
                    score += 2
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        try:
            if g.is_file("/etc/os-release"):
                score += 10
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        try:
            if g.is_file("/usr/lib/systemd/systemd") or g.is_file("/sbin/init"):
                score += 5
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        try:
            if g.is_file("/.discinfo") or g.is_file("/isolinux/isolinux.cfg"):
                score -= 20
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        return score

    # candidate discovery covers several device sources (partitions, filesystems,
    # LVM, host-direct LUKS/LVM) that are safer enumerated inline than split apart
    # pylint: disable-next=too-many-locals,too-many-branches,too-many-statements
    def _candidate_root_devices(self, g: guestfs.GuestFS) -> list[str]:
        """
        Build candidate list for root filesystem detection.

        Uses native guestfs calls instead of shell commands to avoid
        dependencies on /bin/sh in minimal appliances.
        """
        candidates: list[str] = []

        # 1. Partitions
        try:
            partitions = [U.to_text(p) for p in (g.list_partitions() or [])]
            candidates.extend(partitions)
            self.logger.debug(f"Partitions: {partitions}")
        # best-effort candidate enumeration, must not abort the fixer
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.warning(f"Failed to list partitions: {e}")

        # 2. Filesystems (includes /dev/mapper/* from list_filesystems)
        try:
            fsmap = g.list_filesystems() or {}
            self.logger.debug(f"Filesystems map: {list(fsmap.keys())}")
            for dev, fstype in fsmap.items():
                d = U.to_text(dev)
                t = U.to_text(fstype)
                # Skip swap, LUKS containers, and LVM physical volumes (we want unlocked devices and LVs)
                if t in ("swap", "crypto_LUKS", "LVM2_member"):
                    self.logger.debug(f"Skipping {d} (type={t})")
                    continue
                if d.startswith("/dev/"):
                    candidates.append(d)
                    self.logger.debug(f"Added from filesystems: {d} (type={t})")
        # best-effort candidate enumeration, must not abort the fixer
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.warning(f"Failed to list filesystems: {e}")

        # 3. LVM logical volumes (native guestfs call)
        try:
            if hasattr(g, "lvs"):
                lvs_list = g.lvs() or []
                self.logger.info(f"🔍 LVM logical volumes: {lvs_list}")
                for lv in lvs_list:
                    d = U.to_text(lv)
                    if d.startswith("/dev/"):
                        candidates.append(d)
                        self.logger.info(f"✅ Added LV candidate: {d}")
        # best-effort candidate enumeration, must not abort the fixer
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.warning(f"⚠️ LVM enumeration failed: {e}")

        # 3b. Host-direct scan for /dev/mapper/* devices (LUKS + LVM on host)
        # When LUKS is opened on the host via cryptsetup, LVM volumes inside
        # appear under /dev/mapper/ but the container-based LVM can't see them.
        if self._luks_opened:
            try:
                # Get LVs directly from host lvs command
                result = subprocess.run(
                    ["lvs", "--devicesfile", "", "--noheadings", "-o", "lv_path"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        lv = line.strip()
                        if lv and lv.startswith("/dev/"):
                            candidates.append(lv)
                            self.logger.info(f"Added LV candidate (host-direct): {lv}")
            except (OSError, subprocess.SubprocessError) as e:
                self.logger.debug(f"Host-direct LV scan failed: {e}")

            # Also add any /dev/mapper/vg* devices
            for mp in Path("/dev/mapper").glob("vg*"):
                mp = str(mp)
                if mp not in candidates:
                    candidates.append(mp)
                    self.logger.info(f"Added mapper candidate: {mp}")

        # 4. Deduplicate while preserving order
        seen: set[str] = set()
        out: list[str] = []
        for d in candidates:
            if d and d not in seen:
                seen.add(d)
                out.append(d)

        # Filter out known non-root devices
        filtered = []
        for d in out:
            # Skip appliance loop devices
            if d.startswith("/dev/loop"):
                self.logger.debug(f"Filtering out loop device: {d}")
                continue
            # Skip LUKS placeholder devices that don't exist
            if "/luks-" in d and not d.startswith("/dev/mapper/luks-"):
                self.logger.debug(f"Filtering out LUKS placeholder: {d}")
                continue
            filtered.append(d)

        # Prioritize LVM logical volumes and mapper devices
        # Try these first as they're most likely to be root filesystems
        priority = []
        standard = []
        for d in filtered:
            if d.startswith("/dev/mapper/") and "control" not in d.lower():
                priority.append(d)
            elif "/dev/" in d and ("-" in d.split("/")[-1] or d.startswith("/dev/vg")):
                # LVM naming pattern: /dev/vgname-lvname or /dev/vgname/lvname
                priority.append(d)
            else:
                standard.append(d)

        result = priority + standard
        self.logger.info(f"📋 Candidate priority order: {result}")
        return result

    # tries every candidate device, then every btrfs subvolume on top; the two
    # scan passes are safer kept inline than split into helpers
    # pylint: disable-next=too-many-branches,too-many-statements
    def mount_root_bruteforce(self, g: guestfs.GuestFS) -> RootMountResult:
        """Try mounting every candidate device (and btrfs subvolume) to find the best-scoring root."""
        candidates = self._candidate_root_devices(g)
        self.logger.info(f"🔍 Brute-force mount candidates: {candidates}")
        if not candidates:
            raise RuntimeError(
                "No partitions or filesystems detected on the disk image. "
                "The disk may be empty, encrypted, or use an unsupported partition scheme. "
                "Verify the disk image with: qemu-img info <disk_path>"
            )

        mount_failures: list[dict[str, str]] = []
        best: tuple[int, str | None] = (-(10**9), None)
        for dev in candidates:
            self.safe_umount_all(g)
            try:
                filesystem_fixer.log_vfs_type_best_effort(self, g, dev)

                # Skip BitLocker-encrypted partitions — cannot mount offline
                vfs = getattr(self, "root_fstype", "")
                if vfs and "bitlocker" in vfs.lower():
                    self.logger.info(
                        f"🔒 Skipping {dev} — BitLocker encrypted partition "
                        f"(offline guest fixes not possible on encrypted volumes)"
                    )
                    self._bitlocker_detected = True  # propagate to offline_fixer error message
                    continue

                if self.dry_run:
                    g.mount_ro(dev, "/")
                else:
                    g.mount(dev, "/")
                if self.looks_like_root(g):
                    sc = self.score_root(g)
                    if sc > best[0]:
                        best = (sc, dev)
                self.safe_umount_all(g)
            # best-effort mount attempt against one candidate device
            except Exception as e:  # pylint: disable=broad-exception-caught
                mount_failures.append({"device": dev, "error": str(e)})

        if best[1]:
            dev = best[1]
            self.safe_umount_all(g)
            if self.dry_run:
                g.mount_ro(dev, "/")
            else:
                g.mount(dev, "/")
            return RootMountResult(
                inspect_root=None,
                root_dev=dev,
                root_btrfs_subvol=None,
                method="bruteforce",
                details={"score": best[0], "failures": mount_failures[:200]},
            )

        best_btrfs: tuple[int, str | None, str | None] = (-(10**9), None, None)
        for dev in candidates:
            # Check filesystem type before trying btrfs subvolumes
            self.logger.info(f"🔍 Checking {dev} for btrfs subvolume mounting...")
            try:
                # internal helper shared within the fixers package
                vfs_type = filesystem_fixer._vfs_type(g, dev)  # pylint: disable=protected-access
                filesystem_fixer.log_vfs_type_best_effort(self, g, dev)
            # best-effort filesystem-type probe, must not abort the scan
            except Exception:  # pylint: disable=broad-exception-caught
                vfs_type = "unknown"

            # Only try btrfs subvolume mounting on actual btrfs filesystems
            if vfs_type != "btrfs":
                self.logger.info(f"⏭️ Skipping {dev} (vfs_type={vfs_type}, not btrfs) - NO SUBVOL MOUNTS")
                continue

            self.logger.info(f"✅ {dev} is btrfs, trying subvolume mounts...")
            for sv in self._BTRFS_COMMON_SUBVOLS:
                self.safe_umount_all(g)
                try:
                    opts = f"subvol={sv}"
                    if self.dry_run:
                        opts = f"ro,{opts}"
                    g.mount_options(opts, dev, "/")
                    if self.looks_like_root(g):
                        sc = self.score_root(g)
                        if sc > best_btrfs[0]:
                            best_btrfs = (sc, dev, sv)
                    self.safe_umount_all(g)
                # best-effort mount attempt against one subvolume
                except Exception as e:  # pylint: disable=broad-exception-caught
                    mount_failures.append({"device": f"{dev} subvol={sv}", "error": str(e)})

        if best_btrfs[1] and best_btrfs[2]:
            dev = best_btrfs[1]
            sv = best_btrfs[2]
            self.safe_umount_all(g)
            opts = f"subvol={sv}"
            if self.dry_run:
                opts = f"ro,{opts}"
            g.mount_options(opts, dev, "/")
            return RootMountResult(
                inspect_root=None,
                root_dev=dev,
                root_btrfs_subvol=sv,
                method="bruteforce-btrfs",
                details={"score": best_btrfs[0], "failures": mount_failures[:200]},
            )

        raise RuntimeError(
            f"Could not find and mount the root filesystem after trying all partitions. "
            f"The disk image may not contain a supported Linux/Windows root filesystem, "
            f"or all filesystems are corrupted. Tried {len(mount_failures)} candidate(s)."
        )

    # inspect_os path covers multiple fallbacks (score-based root pick, btrfsvol
    # parsing, by-path resolution) that are safer kept inline than split apart
    # pylint: disable-next=too-many-locals,too-many-branches,too-many-statements
    def detect_and_mount_root(self, g: guestfs.GuestFS) -> RootMountResult:
        """
        Preferred path: inspect_os -> mountpoints -> mount_root_direct.
        Fallback: bruteforce.
        """
        try:
            roots = g.inspect_os()
        # best-effort inspect_os; on failure fall through to bruteforce below
        except Exception:  # pylint: disable=broad-exception-caught
            roots = []

        if not roots:
            return self.mount_root_bruteforce(g)

        # Pick best-looking root (avoid roots[0] roulette)
        best_root: str | None = None
        best_score = -(10**9)
        for r in roots:
            rr = U.to_text(r)
            score = 0
            try:
                if g.inspect_get_product_name(rr):
                    score += 2
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            try:
                if g.inspect_get_distro(rr):
                    score += 2
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            try:
                mp = g.inspect_get_mountpoints(rr) or {}
                if U.to_text(mp.get("/", "")).strip():
                    score += 2
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            if score > best_score:
                best_score = score
                best_root = rr

        root = best_root or U.to_text(roots[0])

        try:
            mp_map = g.inspect_get_mountpoints(root)
        except Exception:  # pylint: disable=broad-exception-caught
            mp_map = {}

        root_spec = U.to_text(mp_map.get("/", "")).strip()
        if not root_spec:
            return self.mount_root_bruteforce(g)

        root_dev = root_spec
        subvol: str | None = None
        if root_spec.startswith("btrfsvol:"):
            root_dev, subvol = parse_btrfsvol_spec(root_spec)
            root_dev = root_dev.strip()

        real: str | None = None
        if root_dev.startswith("/dev/disk/by-"):
            try:
                rp = U.to_text(g.realpath(root_dev)).strip()
                if rp.startswith("/dev/"):
                    real = rp
            except Exception:  # pylint: disable=broad-exception-caught
                real = None

        if not real and root_dev.startswith("/dev/disk/by-path/"):
            return self.mount_root_bruteforce(g)

        if not real and root_dev.startswith("/dev/"):
            real = root_dev

        if not real:
            return self.mount_root_bruteforce(g)

        try:
            self.mount_root_direct(g, real, subvol)
            return RootMountResult(
                inspect_root=root,
                root_dev=real,
                root_btrfs_subvol=subvol,
                method="inspect_os",
                details={"chosen_root_score": best_score},
            )
        except Exception:  # pylint: disable=broad-exception-caught
            # fallback
            return self.mount_root_bruteforce(g)
