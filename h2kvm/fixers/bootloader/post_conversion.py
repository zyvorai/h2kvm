# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/bootloader/post_conversion.py
"""
Post-conversion boot hardening for Linux guests.

Implements the "3 Golden Fixes" for reliable KVM boot after VM migration:
1. Fstab hardening - Add nofail flags to prevent boot hangs
2. Generic initramfs - Rebuild with all virtio drivers
3. GRUB regeneration - Fix config and rebuild

These fixes prevent the most common post-migration boot failures:
- "Reached target Paths" hang (missing devices in fstab)
- Kernel panic (missing virtio drivers in initramfs)
- GRUB config errors (malformed cmdline)
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from h2kvm.core.utils import U

if TYPE_CHECKING:
    from h2kvm.core.guestfs_typing import guestfs


def _resolve_fstab_spec(g: guestfs.GuestFS, spec: str) -> str | None:
    """
    Resolve fstab device spec to a device node that guestfs can mount.
    Handles UUID=, LABEL=, /dev/..., and falls back to None.
    """
    spec = spec.strip()

    try:
        if spec.startswith("UUID="):
            uuid = spec.split("=", 1)[1]
            return U.to_text(g.findfs_uuid(uuid))
        if spec.startswith("LABEL="):
            label = spec.split("=", 1)[1]
            return U.to_text(g.findfs_label(label))
        if spec.startswith("/dev/"):
            return spec
    except Exception:  # pylint: disable=broad-exception-caught
        # reason: best-effort fstab spec resolution -- guestfs lookup failures just mean
        # "couldn't resolve", not a fatal error.
        pass

    return None


def _looks_like_root_fs(g: guestfs.GuestFS) -> bool:
    """
    Check if mounted filesystem looks like real root (not /boot).

    /boot partitions will have vmlinuz/grub2 but not /etc/os-release.
    Real root has /etc/os-release OR (/usr + /etc).
    """
    try:
        has_os_release = g.is_file("/etc/os-release")
        has_usr = g.is_dir("/usr") and (g.is_file("/usr/bin/dracut") or g.is_file("/usr/bin/systemctl"))
        has_etc = g.is_dir("/etc")

        # Require at least one strong root signal
        if has_os_release or (has_usr and has_etc):
            return True

        # Strong /boot signal: grub + vmlinuz present but no os-release
        if (g.is_dir("/grub2") or g.is_dir("/loader")) and not has_os_release:
            return False

    except Exception:  # pylint: disable=broad-exception-caught
        # reason: best-effort heuristic detection -- any guestfs lookup failure just
        # means "can't tell", so we fall through to the False default.
        pass

    return False


class PostConversionBootFixer:
    """
    Post-conversion boot hardening for Linux VMs.

    Automatically applies production-grade fixes to prevent common boot failures
    after VMware → KVM migration.
    """

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)
        self.stats: dict[str, Any] = {
            "attempted": False,
            "uuid_regenerated": [],
            "fstab_hardened": False,
            "initramfs_rebuilt": False,
            "grub_regenerated": False,
            "services_disabled": [],
            "errors": [],
        }

    def _get_xfs_uuid(self, g: guestfs.GuestFS, device: str) -> str | None:
        """Get current XFS UUID from device."""
        try:
            # Try blkid first (most reliable)
            uuid = U.to_text(g.vfs_uuid(device))
            if uuid:
                return uuid
        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort UUID lookup -- fall through to the command-based fallback.
            pass

        # Fallback to command execution
        try:
            output = U.to_text(g.command(["blkid", "-s", "UUID", "-o", "value", device]))
            return output.strip() if output.strip() else None
        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort UUID lookup -- caller treats None as "unknown".
            pass

        return None

    def _find_xfs_partitions(self, g: guestfs.GuestFS) -> list[str]:
        """Find all XFS partitions/devices in the guest."""
        xfs_devices = []

        try:
            # Get all partitions
            partitions = g.list_partitions()
            for part in partitions:
                try:
                    fstype = U.to_text(g.vfs_type(part))
                    if fstype == "xfs":
                        xfs_devices.append(part)
                except Exception:  # pylint: disable=broad-exception-caught
                    # reason: per-partition probe -- one unreadable partition must not
                    # abort discovery of the rest.
                    continue
        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort discovery -- return whatever was found so far rather
            # than abort the whole fixer run.
            self.logger.debug("Error listing partitions: %s", e)

        return xfs_devices

    def _regenerate_xfs_uuid(self, g: guestfs.GuestFS, device: str) -> tuple[bool, str | None]:
        """
        Generate new UUID for XFS filesystem.

        Returns:
            Tuple of (success: bool, new_uuid: str | None)
        """
        try:
            # Verify it's XFS
            fstype = U.to_text(g.vfs_type(device))
            if fstype != "xfs":
                return False, f"Not XFS filesystem: {fstype}"

            # Generate new UUID using xfs_admin
            # Note: Device must be unmounted to change UUID
            try:
                g.command(["xfs_admin", "-U", "generate", device])
            except Exception as e:  # pylint: disable=broad-exception-caught
                # reason: need to inspect the error message for "mounted" before deciding
                # whether to swallow it (expected) or re-raise (unexpected xfs_admin failure).
                error_msg = str(e).lower()
                if "mounted" in error_msg:
                    return False, "device_mounted"
                raise

            # Get the new UUID
            new_uuid = self._get_xfs_uuid(g, device)
            if new_uuid:
                return True, new_uuid
            return False, "could_not_read_new_uuid"

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort UUID regeneration step -- any failure is reported back
            # as a (False, reason) result rather than aborting the whole fixer run.
            return False, str(e)

    def regenerate_filesystem_uuids(self, g: guestfs.GuestFS) -> list[dict[str, Any]]:
        """
        Regenerate UUIDs for all XFS filesystems to avoid duplicates.

        This is critical for cloned VMware VMs which often have duplicate
        XFS UUIDs that prevent mounting.

        Returns:
            List of dicts with device, old_uuid, new_uuid for each regenerated filesystem
        """
        self.logger.info("🔄 Fix 0/4: Regenerating XFS UUIDs to fix duplicates")

        # Find all XFS partitions
        xfs_partitions = self._find_xfs_partitions(g)
        if not xfs_partitions:
            self.logger.info("  No XFS filesystems found, skipping")
            return []

        self.logger.info("  Found %d XFS filesystem(s)", len(xfs_partitions))

        regenerated = []

        for device in xfs_partitions:
            try:
                # Get old UUID for logging
                old_uuid = self._get_xfs_uuid(g, device)
                if not old_uuid:
                    self.logger.debug("  Skipping %s: could not read UUID", device)
                    continue

                # Generate new UUID
                success, result = self._regenerate_xfs_uuid(g, device)

                if success:
                    new_uuid = result
                    regenerated.append({"device": device, "old_uuid": old_uuid, "new_uuid": new_uuid})
                    self.logger.info("  ✓ Regenerated UUID for %s", device)
                    self.logger.debug("    Old: %s", old_uuid)
                    self.logger.debug("    New: %s", new_uuid)
                else:
                    error = result
                    if error == "device_mounted":
                        # This is expected - devices are unmounted before UUID regeneration
                        self.logger.debug("  Skipping %s: currently mounted", device)
                    else:
                        self.logger.warning("  ⚠️  Failed to regenerate UUID for %s: %s", device, error)

            except Exception as e:  # pylint: disable=broad-exception-caught
                # reason: per-device best-effort regeneration -- one device's failure must
                # not abort processing the rest.
                self.logger.debug("  Error processing %s: %s", device, e)
                continue

        if regenerated:
            self.logger.info("  ✓ Successfully regenerated %d UUIDs", len(regenerated))
        else:
            self.logger.info("  No UUIDs were regenerated (devices may be mounted)")

        self.stats["uuid_regenerated"] = regenerated
        return regenerated

    def _update_fstab_uuids(self, g: guestfs.GuestFS, uuid_changes: list[dict[str, Any]]) -> None:
        """
        Update /etc/fstab with new UUIDs after regeneration.

        Args:
            uuid_changes: List of dicts with old_uuid, new_uuid, device
        """
        if not uuid_changes:
            return

        try:
            if not g.is_file("/etc/fstab"):
                self.logger.debug("  No /etc/fstab found")
                return

            fstab_content = g.read_file("/etc/fstab")
            if isinstance(fstab_content, bytes):
                fstab_content = fstab_content.decode("utf-8", errors="replace")

            modified = False
            new_lines = []

            for line in fstab_content.splitlines():
                new_line = line

                # Check if line contains any old UUIDs we changed
                for change in uuid_changes:
                    old_uuid = change["old_uuid"]
                    new_uuid = change["new_uuid"]

                    if f"UUID={old_uuid}" in line:
                        new_line = line.replace(f"UUID={old_uuid}", f"UUID={new_uuid}")
                        modified = True
                        self.logger.info(
                            "  Updated fstab entry: %s... → %s...", old_uuid[:8], new_uuid[:8]
                        )
                        break

                new_lines.append(new_line)

            if modified:
                new_fstab = "\n".join(new_lines) + "\n"
                g.write("/etc/fstab", new_fstab.encode("utf-8"))
                self.logger.info("  ✓ Updated /etc/fstab with new UUIDs")
            else:
                self.logger.debug("  /etc/fstab does not reference changed UUIDs")

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort fstab UUID update -- must not abort the whole migration
            # over one guest's fstab quirk; failure is recorded in stats["errors"] instead.
            error = (
                f"Failed to update /etc/fstab with new UUIDs after XFS UUID regeneration: {e}. "
                "The VM may fail to mount filesystems at boot due to UUID mismatch. "
                "Manually update UUID= entries in /etc/fstab to match output of 'blkid'."
            )
            self.logger.exception("  ⚠️  %s", error)
            self.stats["errors"].append(error)

    def apply_golden_fixes(
        self,
        g: guestfs.GuestFS,
        *,
        harden_fstab: bool = True,
        rebuild_initramfs: bool = True,
        regenerate_grub: bool = True,
        disable_blocking_services: bool = True,
    ) -> dict[str, Any]:
        """
        Apply the golden fixes for reliable KVM boot after VMware migration.

        Args:
            g: GuestFS instance (must be mounted)
            harden_fstab: Add nofail flags to non-root mounts
            rebuild_initramfs: Rebuild generic initramfs with all drivers
            regenerate_grub: Fix and regenerate GRUB config
            disable_blocking_services: Disable VMware and network wait services

        Returns:
            Stats dict with results of each fix
        """
        self.stats["attempted"] = True

        # Fix 1: Harden fstab
        if harden_fstab:
            self.logger.info("🔧 Fix 1/4: Hardening fstab with nofail flags")
            self._harden_fstab(g)

        # Fix 2: Rebuild generic initramfs
        if rebuild_initramfs:
            self.logger.info("🔧 Fix 2/4: Rebuilding generic initramfs")
            self._rebuild_initramfs(g)

        # Fix 3: Regenerate GRUB config
        if regenerate_grub:
            self.logger.info("🔧 Fix 3/4: Regenerating GRUB configuration")
            self._regenerate_grub(g)

        # Fix 4: Disable blocking services (VMware tools, network-wait)
        if disable_blocking_services:
            self.logger.info("🔧 Fix 4/4: Disabling boot-blocking services")
            self._disable_blocking_services(g)

        return self.stats

    def _harden_fstab(  # pylint: disable=too-many-locals,too-many-branches
        self, g: guestfs.GuestFS
    ) -> None:
        # reason: parsing and rewriting each fstab line (skip comments/short lines/root/swap,
        # then rebuild with added options) needs this many local variables and branches to
        # stay a single readable pass over the file.
        """
        Add nofail and device-timeout flags to non-root mounts in fstab.

        This prevents systemd from blocking boot if non-critical filesystems
        (like /home, /boot) are temporarily unavailable or have UUID mismatches.
        """
        try:
            if not g.is_file("/etc/fstab"):
                self.logger.debug("No /etc/fstab found, skipping")
                return

            fstab_content = g.read_file("/etc/fstab")
            if isinstance(fstab_content, bytes):
                fstab_content = fstab_content.decode("utf-8", errors="replace")

            lines = fstab_content.splitlines()
            modified = False
            new_lines = []

            for line in lines:
                # Skip comments and empty lines
                if line.strip().startswith("#") or not line.strip():
                    new_lines.append(line)
                    continue

                # Parse fstab entry
                parts = line.split()
                if len(parts) < 4:
                    new_lines.append(line)
                    continue

                device, mountpoint, fstype, options = parts[0], parts[1], parts[2], parts[3]

                # Only harden non-root, non-swap filesystems
                if mountpoint in ("/", "none") or fstype == "swap":
                    new_lines.append(line)
                    continue

                # Add nofail and timeout if not already present
                if "nofail" not in options:
                    # Add after existing options
                    if "x-systemd.device-timeout" not in options:
                        new_options = f"{options},nofail,x-systemd.device-timeout=5s"
                    else:
                        new_options = f"{options},nofail"

                    # Reconstruct line
                    new_line = f"{device}\t{mountpoint}\t{fstype}\t{new_options}"
                    if len(parts) >= 5:
                        new_line += f"\t{parts[4]}"
                    if len(parts) >= 6:
                        new_line += f"\t{parts[5]}"

                    new_lines.append(new_line)
                    modified = True
                    self.logger.info("  ✓ Hardened: %s (%s)", mountpoint, device)
                else:
                    new_lines.append(line)

            if modified:
                new_fstab = "\n".join(new_lines) + "\n"
                g.write("/etc/fstab", new_fstab.encode("utf-8"))
                self.stats["fstab_hardened"] = True
                self.logger.info("  ✓ fstab hardening complete")
            else:
                self.logger.debug("  fstab already hardened or no non-root mounts found")

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort fixer step -- must not abort the whole migration over
            # one guest's fstab quirk; failure is recorded in stats["errors"] instead.
            error = (
                f"fstab hardening failed while adding nofail flags to /etc/fstab: {e}. "
                "Non-root mounts may cause boot hangs ('Reached target Paths' freeze). "
                "Manually add 'nofail,x-systemd.device-timeout=5s' to non-root entries in /etc/fstab."
            )
            self.logger.warning("  ⚠️  %s", error)
            self.stats["errors"].append(error)

    def _rebuild_initramfs(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        self, g: guestfs.GuestFS
    ) -> None:
        # reason: rebuilding initramfs has to cover locating/mounting a separate /boot,
        # detecting the right kernel version, running dracut with a fallback to
        # update-initramfs, and verifying the result -- each step needs its own
        # best-effort error handling to keep the fixer robust across distros.
        """
        Rebuild initramfs without hostonly mode to include all drivers.

        Generic initramfs includes:
        - virtio_blk, virtio_scsi, virtio_net
        - All LVM/dm/md drivers
        - All filesystem drivers

        This prevents kernel panic when disk controller changes from VMware to KVM.
        """
        try:  # pylint: disable=too-many-nested-blocks
            # reason: walking fstab lines to find and mount a separate /boot needs several
            # levels of if/for/try to parse, match, and resolve the device spec safely.
            # CRITICAL: Verify we're on the real root, not /boot
            if not _looks_like_root_fs(g):
                error = "Mounted filesystem does not look like guest root (likely /boot). Skipping dracut."
                self.logger.warning("  ⚠️  %s", error)
                self.stats["errors"].append(error)
                return

            # Check if /boot is a separate mount point and mount it
            boot_mounted = False
            try:
                if g.is_file("/etc/fstab"):
                    fstab_content = g.read_file("/etc/fstab")
                    if isinstance(fstab_content, bytes):
                        fstab_content = fstab_content.decode("utf-8", errors="replace")

                    for line in fstab_content.splitlines():
                        if line.strip() and not line.strip().startswith("#"):
                            parts = line.split()
                            if len(parts) >= 2 and parts[1] == "/boot":
                                # /boot is a separate mount point
                                device_spec = parts[0]
                                self.logger.debug("  /boot is separate partition: %s", device_spec)

                                # Try to mount /boot using findfs_uuid
                                try:
                                    boot_device = _resolve_fstab_spec(g, device_spec)

                                    if boot_device:
                                        g.mount(boot_device, "/boot")
                                        boot_mounted = True
                                        self.logger.info("  ✓ Mounted /boot from %s", boot_device)
                                    else:
                                        self.logger.debug(
                                            "  Could not resolve device spec: %s", device_spec
                                        )

                                except Exception as e:  # pylint: disable=broad-exception-caught
                                    # reason: best-effort /boot mount -- rebuild continues
                                    # without it if this fails.
                                    self.logger.debug("  Could not mount /boot: %s", e)

                                break
            except Exception as e:  # pylint: disable=broad-exception-caught
                # reason: best-effort /boot detection -- must not abort initramfs rebuild.
                self.logger.debug("  Error checking /boot mount: %s", e)

            # Verify /boot is really /boot (if mounted)
            if boot_mounted:
                try:
                    boot_entries = [U.to_text(x) for x in g.ls("/boot") if U.to_text(x)]
                    if not any(x.startswith("vmlinuz-") for x in boot_entries):
                        error = "/boot mounted but no vmlinuz-* found; dracut may write to wrong place"
                        self.logger.warning("  ⚠️  %s", error)
                        self.stats["errors"].append(error)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    # reason: best-effort verification -- must not abort initramfs rebuild.
                    self.logger.debug("  Could not verify /boot contents: %s", e)

            # Detect kernel version
            if not g.is_dir("/lib/modules"):
                self.logger.debug("No /lib/modules found, skipping initramfs rebuild")
                return

            kvers = sorted([U.to_text(x) for x in g.ls("/lib/modules") if U.to_text(x).strip()])
            if not kvers:
                self.logger.warning("  ⚠️  No kernel versions found in /lib/modules")
                return

            # Prefer kernel version that has initramfs in /boot (aligns with what bootloader uses)
            try:
                boot_entries = [U.to_text(x) for x in g.ls("/boot")]
                boot_kvers = sorted(
                    {
                        m.group(1)
                        for name in boot_entries
                        for m in [re.match(r"initramfs-(.+)\.img$", name)]
                        if m
                    }
                )
                if boot_kvers:
                    latest_kver = boot_kvers[-1]
                    self.logger.debug("  Using kernel from /boot: %s", latest_kver)
                else:
                    latest_kver = kvers[-1]
                    self.logger.debug("  Using latest from /lib/modules: %s", latest_kver)
            except Exception:  # pylint: disable=broad-exception-caught
                # reason: best-effort kernel version preference -- fall back to the
                # latest installed kernel module directory on any lookup failure.
                latest_kver = kvers[-1]

            self.logger.info("  Detected kernel: %s", latest_kver)

            # Get initramfs path and check both mtime AND size before rebuild
            initramfs_path = f"/boot/initramfs-{latest_kver}.img"
            old_mtime = None
            old_size = None
            try:
                stat_info = g.stat(initramfs_path)
                old_mtime = stat_info["mtime"]
                old_size = stat_info["size"]
                self.logger.debug("  Old initramfs: mtime=%s, size=%s bytes", old_mtime, old_size)
            except Exception:  # pylint: disable=broad-exception-caught
                # reason: best-effort pre-rebuild snapshot -- absence just means there's
                # no prior initramfs to compare against.
                self.logger.debug("  No existing initramfs at %s", initramfs_path)

            # Check for dracut (RHEL/CentOS/Fedora)
            has_dracut = (
                g.is_file("/usr/bin/dracut") or g.is_file("/bin/dracut") or g.is_file("/sbin/dracut")
            )

            if has_dracut:
                self.logger.info("  Rebuilding with: dracut -f --no-hostonly --kver %s", latest_kver)
                try:
                    # CRITICAL: Run depmod first to update module dependencies
                    self.logger.debug("  Running depmod -a %s", latest_kver)
                    try:
                        depmod_output = g.command(["depmod", "-a", latest_kver])
                        if depmod_output.strip():
                            self.logger.debug("  depmod output: %s", depmod_output[:200])
                    except Exception as e:  # pylint: disable=broad-exception-caught
                        # reason: depmod failure is non-fatal -- dracut may still succeed.
                        self.logger.debug("  depmod warning (non-fatal): %s", e)

                    # Run dracut inside the guest filesystem
                    # CRITICAL: Force dracut to write to the exact file we will verify
                    # This makes verification meaningful and prevents dracut from writing elsewhere
                    self.logger.debug(
                        "  Executing: dracut -f -v --no-hostonly --kver %s %s", latest_kver, initramfs_path
                    )

                    # Try to capture stderr via shell redirection
                    try:
                        output = g.command(
                            ["dracut", "-f", "-v", "--no-hostonly", "--kver", latest_kver, initramfs_path]
                        )

                        # Log dracut output immediately for debugging
                        if output and output.strip():
                            # Log full output to see errors
                            self.logger.info("  dracut output:\n%s", output)
                        else:
                            self.logger.warning(
                                "  ⚠️  dracut produced no output (may indicate silent failure)"
                            )

                    except Exception as dracut_error:  # pylint: disable=broad-exception-caught
                        # reason: dracut may fail for many reasons (missing binary,
                        # unsupported --kver, internal errors) -- must fall back to a
                        # retry without --kver rather than abort the fixer run.
                        error_msg = str(dracut_error)
                        self.logger.warning("  ⚠️  dracut command failed: %s", error_msg[:200])

                        # Try without --kver as a fallback
                        try:
                            self.logger.info("  Retrying: dracut -f -v --no-hostonly %s", initramfs_path)
                            output = g.command(["dracut", "-f", "-v", "--no-hostonly", initramfs_path])
                            if output and output.strip():
                                self.logger.info("  dracut fallback output:\n%s", output)
                        except Exception:  # pylint: disable=broad-exception-caught
                            # reason: both dracut attempts failed -- record as a non-fatal
                            # fixer error rather than aborting the whole migration.
                            error = (
                                f"dracut execution failed (both attempts): {dracut_error}. "
                                "The initramfs may lack virtio drivers, causing kernel panic on KVM boot. "
                                "Boot into rescue mode and run: dracut -f --no-hostonly --kver $(uname -r)"
                            )
                            self.logger.warning("  ⚠️  %s", error)
                            self.stats["errors"].append(error)
                            return

                    # Verify initramfs was actually rebuilt (check both mtime AND size)
                    try:
                        stat_info = g.stat(initramfs_path)
                        new_mtime = stat_info["mtime"]
                        new_size = stat_info["size"]

                        # Check if file was modified (mtime+size comparison)
                        # Filesystem timestamps can have 1-second granularity, so check size too
                        if old_mtime is not None and old_size is not None:
                            if new_mtime == old_mtime and new_size == old_size:
                                # File unchanged - dracut decided existing initramfs is sufficient
                                # This is not an error - just means no rebuild was needed
                                self.logger.info(
                                    "  ✓ initramfs unchanged: dracut determined existing initramfs "
                                    "is sufficient (%s bytes, mtime=%s)",
                                    old_size,
                                    old_mtime,
                                )
                                # Don't mark as error - this is normal behavior
                                # The later virtio driver injection will rebuild if needed
                                self.stats["initramfs_rebuilt"] = False
                                return

                        self.logger.info(
                            "  ✓ initramfs rebuilt: %s bytes (was %s), mtime=%s (was %s)",
                            new_size,
                            old_size,
                            new_mtime,
                            old_mtime,
                        )

                        # Verify initramfs contains virtio modules
                        try:
                            lsinitrd_output = g.command(["lsinitrd", initramfs_path])
                            has_virtio = "virtio" in lsinitrd_output.lower()
                            has_lvm = "lvm" in lsinitrd_output.lower() or "dm_mod" in lsinitrd_output.lower()

                            if has_virtio and has_lvm:
                                self.logger.info("  ✓ Verified: initramfs contains virtio and LVM drivers")
                            else:
                                self.logger.warning(
                                    "  ⚠️  initramfs may be incomplete (virtio=%s, lvm=%s)",
                                    has_virtio,
                                    has_lvm,
                                )
                        except Exception as e:  # pylint: disable=broad-exception-caught
                            # reason: best-effort verification -- rebuild already succeeded.
                            self.logger.debug("  Could not verify initramfs contents: %s", e)

                        self.stats["initramfs_rebuilt"] = True

                    except Exception as e:  # pylint: disable=broad-exception-caught
                        # reason: verification step failure shouldn't be fatal -- the
                        # rebuild itself may have succeeded; record as a non-fatal error.
                        error = (
                            f"Could not verify initramfs rebuild at {initramfs_path}: {e}. "
                            "The initramfs may or may not have been rebuilt successfully. "
                            "After first boot, verify with: lsinitrd /boot/initramfs-$(uname -r).img | grep virtio"
                        )
                        self.logger.warning("  ⚠️  %s", error)
                        self.stats["errors"].append(error)
                        return

                    if output.strip():
                        self.logger.debug("  dracut output: %s", output[:200])

                except Exception as e:  # pylint: disable=broad-exception-caught
                    # reason: best-effort fixer step -- dracut failures must not abort
                    # the whole migration; recorded in stats["errors"] instead.
                    error = (
                        f"dracut execution failed inside guest: {e}. "
                        "The initramfs was not rebuilt. On KVM, the VM may kernel panic due to missing virtio drivers. "
                        "After booting into rescue mode, run: dracut -f --no-hostonly --kver $(uname -r)"
                    )
                    self.logger.warning("  ⚠️  %s", error)
                    self.stats["errors"].append(error)
            else:
                # Check for update-initramfs (Debian/Ubuntu)
                has_update_initramfs = g.is_file("/usr/sbin/update-initramfs") or g.is_file(
                    "/sbin/update-initramfs"
                )

                if has_update_initramfs:
                    self.logger.info("  Rebuilding with: update-initramfs -u -k %s", latest_kver)
                    try:
                        output = g.command(["update-initramfs", "-u", "-k", latest_kver])
                        self.stats["initramfs_rebuilt"] = True
                        self.logger.info("  ✓ initramfs rebuilt successfully")
                    except Exception as e:  # pylint: disable=broad-exception-caught
                        # reason: best-effort fixer step -- must not abort the whole
                        # migration over one guest's initramfs quirk.
                        error = (
                            f"update-initramfs execution failed for kernel {latest_kver}: {e}. "
                            "The initramfs was not rebuilt. On KVM, the VM may fail to boot. "
                            "After booting into rescue mode, run: update-initramfs -u -k all"
                        )
                        self.logger.warning("  ⚠️  %s", error)
                        self.stats["errors"].append(error)
                else:
                    self.logger.debug("  No initramfs tool found (dracut or update-initramfs)")

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: top-level catch-all for this best-effort fixer step -- must not
            # abort the whole migration run over one guest's initramfs quirk.
            error = (
                f"initramfs rebuild failed: {e}. "
                "Without a working initramfs containing virtio drivers, the VM will likely kernel panic on KVM. "
                "Recovery: boot from rescue media and rebuild initramfs manually with dracut or update-initramfs."
            )
            self.logger.warning("  ⚠️  %s", error)
            self.stats["errors"].append(error)

    def _regenerate_grub(self, g: guestfs.GuestFS) -> None:  # pylint: disable=too-many-branches
        # reason: fixing GRUB config covers detecting grub2 vs legacy grub, fixing
        # malformed cmdline quoting, and regenerating -- each with its own fallback path.
        """
        Fix GRUB config and regenerate.

        Fixes common issues:
        - Malformed GRUB_CMDLINE_LINUX (missing closing quote)
        - Outdated kernel references
        - Wrong root device
        """
        try:
            # Check for GRUB config file
            grub_default = "/etc/default/grub"
            if not g.is_file(grub_default):
                self.logger.debug("No /etc/default/grub found, skipping")
                return

            # Read and validate GRUB_CMDLINE_LINUX
            content = g.read_file(grub_default)
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")

            # Fix malformed GRUB_CMDLINE_LINUX (missing closing quote)
            fixed_content = self._fix_grub_cmdline(content)

            if fixed_content != content:
                self.logger.info("  Fixing malformed GRUB_CMDLINE_LINUX")
                # Debug: show what we're fixing
                self.logger.debug("=" * 60)
                self.logger.debug("BEFORE fix:")
                for i, line in enumerate(content.splitlines(), 1):
                    if "GRUB_CMDLINE_LINUX" in line or i >= 40:  # Show GRUB lines and lines near 44
                        self.logger.debug("  %3d: %r", i, line)
                self.logger.debug("AFTER fix:")
                for i, line in enumerate(fixed_content.splitlines(), 1):
                    if "GRUB_CMDLINE_LINUX" in line or i >= 40:
                        self.logger.debug("  %3d: %r", i, line)
                self.logger.debug("=" * 60)
                g.write(grub_default, fixed_content.encode("utf-8"))

            # Regenerate GRUB config
            grub_cfg = None
            if g.is_file("/boot/grub2/grub.cfg"):
                grub_cfg = "/boot/grub2/grub.cfg"
                grub_cmd = f"grub2-mkconfig -o {grub_cfg}"
            elif g.is_file("/boot/grub/grub.cfg"):
                grub_cfg = "/boot/grub/grub.cfg"
                grub_cmd = f"grub-mkconfig -o {grub_cfg}"
            else:
                self.logger.debug("  No GRUB config file found")
                return

            self.logger.info("  Regenerating: %s", grub_cmd)
            try:
                # Parse grub command
                if grub_cmd.startswith("grub2-mkconfig"):
                    cmd_parts = ["grub2-mkconfig", "-o", grub_cfg]
                else:
                    cmd_parts = ["grub-mkconfig", "-o", grub_cfg]

                output = g.command(cmd_parts)
                self.stats["grub_regenerated"] = True
                self.logger.info("  ✓ GRUB config regenerated successfully")
                if "error" in output.lower():
                    self.logger.debug("  GRUB output: %s", output[:200])
            except Exception as e:  # pylint: disable=broad-exception-caught
                # reason: best-effort fixer step -- must not abort the whole migration
                # over one guest's GRUB quirk.
                error = (
                    f"GRUB config regeneration failed ({grub_cmd}): {e}. "
                    "The bootloader config may reference outdated kernel versions or wrong root devices. "
                    "After booting into rescue mode, run: grub2-mkconfig -o /boot/grub2/grub.cfg "
                    "(or 'update-grub' on Debian/Ubuntu)."
                )
                self.logger.warning("  ⚠️  %s", error)
                self.stats["errors"].append(error)

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: top-level catch-all for this best-effort fixer step -- must not
            # abort the whole migration run over one guest's GRUB config quirk.
            error = (
                f"GRUB regeneration failed while reading/fixing /etc/default/grub: {e}. "
                "The bootloader may have malformed configuration. "
                "Check /etc/default/grub for syntax errors (unbalanced quotes) and regenerate with grub2-mkconfig."
            )
            self.logger.warning("  ⚠️  %s", error)
            self.stats["errors"].append(error)

    def _disable_blocking_services(  # pylint: disable=too-many-branches
        self, g: guestfs.GuestFS
    ) -> None:
        # reason: removing enablement symlinks and masking services each need their own
        # existence/already-done checks per service, across two independent service lists.
        """
        Disable services that block boot after VMware → KVM migration.

        Critical services to disable:
        - NetworkManager-wait-online.service: Blocks boot waiting for network that never comes
        - vmtoolsd.service: VMware Tools daemon (doesn't work on KVM)
        - vgauthd.service: VMware VGAuth daemon (doesn't work on KVM)

        These services cause "Reached target Paths" hangs because they wait forever
        for VMware-specific devices/states that don't exist on KVM.

        IMPORTANT: We use direct symlink removal instead of 'systemctl disable'
        because systemctl doesn't work reliably in offline/guestfs environments
        (requires running systemd, dbus, /run state, etc.).
        """
        try:
            # Service enablement symlinks to remove
            # Format: (symlink_path, service_name_for_logging)
            symlinks_to_remove = [
                # NetworkManager-wait-online.service
                (
                    "/etc/systemd/system/network-online.target.wants/NetworkManager-wait-online.service",
                    "NetworkManager-wait-online.service",
                ),
                # vmtoolsd.service
                ("/etc/systemd/system/multi-user.target.wants/vmtoolsd.service", "vmtoolsd.service"),
                # vgauthd.service (dependency of vmtoolsd)
                ("/etc/systemd/system/vmtoolsd.service.requires/vgauthd.service", "vgauthd.service"),
                ("/etc/systemd/system/multi-user.target.wants/vgauthd.service", "vgauthd.service"),
            ]

            disabled_services = []

            for symlink_path, service_name in symlinks_to_remove:
                try:
                    # Check if symlink exists
                    if g.is_file(symlink_path) or g.is_link(symlink_path):
                        # Remove the enablement symlink
                        g.rm(symlink_path)
                        disabled_services.append(service_name)
                        self.logger.info("  ✓ Disabled: %s (removed %s)", service_name, symlink_path)
                    else:
                        self.logger.debug("  Symlink not found: %s", symlink_path)

                except Exception as e:  # pylint: disable=broad-exception-caught
                    # Non-fatal - symlink might not exist
                    self.logger.debug("  Could not remove %s: %s", symlink_path, e)

            # Optional: Mask services by creating symlinks to /dev/null
            # This ensures they can't be started even if re-enabled
            services_to_mask = [
                "vmtoolsd.service",
                "vgauthd.service",
            ]

            for service in services_to_mask:
                try:
                    mask_path = f"/etc/systemd/system/{service}"

                    # Only mask if service file exists in /usr/lib or /lib
                    service_exists = g.is_file(f"/usr/lib/systemd/system/{service}") or g.is_file(
                        f"/lib/systemd/system/{service}"
                    )

                    if service_exists:
                        # Check if already masked (file or symlink exists at mask path)
                        # Note: g.is_link() may not exist in some bindings, use is_file() as fallback
                        is_link_func = getattr(g, "is_link", None) or getattr(g, "is_symlink", None)
                        try:
                            already_masked = g.is_file(mask_path) or (
                                is_link_func(mask_path) if is_link_func else False
                            )
                        except Exception:  # pylint: disable=broad-exception-caught
                            # reason: best-effort mask-state probe -- treat as not masked.
                            already_masked = False

                        if not already_masked:
                            # Create symlink to /dev/null (systemd mask)
                            g.ln_sf("/dev/null", mask_path)
                            self.logger.info("  ✓ Masked: %s", service)
                        else:
                            self.logger.debug("  Service %s already masked", service)

                except Exception as e:  # pylint: disable=broad-exception-caught
                    # reason: best-effort masking -- one service's failure must not
                    # abort masking the rest.
                    self.logger.debug("  Could not mask %s: %s", service, e)

            # Deduplicate disabled services list
            self.stats["services_disabled"] = list(set(disabled_services))

            if disabled_services:
                self.logger.info("  ✓ Disabled %d boot-blocking service(s)", len(set(disabled_services)))
            else:
                self.logger.debug("  No boot-blocking services found to disable")

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: top-level catch-all for this best-effort fixer step -- must not
            # abort the whole migration run over one guest's service-disabling quirk.
            error = (
                f"Service disabling failed while removing boot-blocking service symlinks: {e}. "
                "VMware services (vmtoolsd, vgauthd) or NetworkManager-wait-online may still be enabled, "
                "causing boot hangs. After boot, run: systemctl disable vmtoolsd vgauthd NetworkManager-wait-online"
            )
            self.logger.warning("  ⚠️  %s", error)
            self.stats["errors"].append(error)

    def _fix_grub_cmdline(self, content: str) -> str:
        """
        Fix malformed GRUB config entries with unclosed quotes.

        Common issue: Missing closing quote causes shell syntax error.
        Example:
            GRUB_CMDLINE_LINUX="... root=UUID=xxx
            GRUB_DISABLE_RECOVERY="true"

        Fix: Add closing quote before newline for any line with unbalanced quotes.
        """
        lines = content.splitlines()
        fixed_lines = []

        for i, line in enumerate(lines, 1):
            original_line = line

            # Skip comments and empty lines
            stripped = line.lstrip()
            if not stripped or stripped.startswith("#"):
                fixed_lines.append(line)
                continue

            # Check any line that looks like a shell variable assignment
            if "=" in line:
                # Count quotes
                double_quote_count = line.count('"')
                single_quote_count = line.count("'")

                # Fix double quotes if unbalanced
                if double_quote_count % 2 == 1:
                    line = line.rstrip() + '"'
                    self.logger.debug("  Fixed line %d: added closing double quote", i)
                    self.logger.debug("    Before: %r", original_line)
                    self.logger.debug("    After:  %r", line)

                # Fix single quotes if unbalanced
                elif single_quote_count % 2 == 1:
                    line = line.rstrip() + "'"
                    self.logger.debug("  Fixed line %d: added closing single quote", i)
                    self.logger.debug("    Before: %r", original_line)
                    self.logger.debug("    After:  %r", line)

            fixed_lines.append(line)

        return "\n".join(fixed_lines) + "\n"
