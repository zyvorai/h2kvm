# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/vmcraft/mount.py
"""
Mount management for guest filesystems.

Handles mounting and unmounting of filesystems with support for:
- Linux filesystems (ext2/3/4, XFS, Btrfs, ZFS)
- Windows filesystems (NTFS via ntfs-3g, FAT32, exFAT)
- Read-only and read-write modes
- Filesystem-specific mount options
- Multi-device mount tracking
"""

from __future__ import annotations

import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

from hyper2kvm.core.structured_log import log_event

from ._utils import DeviceError, run_sudo

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class MountManager:
    """
    Manages filesystem mounting and unmounting.

    Tracks mounted filesystems and handles cleanup on shutdown.
    Provides filesystem-specific mount options for optimal compatibility.
    """

    def __init__(self, mount_logger: logging.Logger, mount_root: Path):
        """
        Initialize mount manager.

        Args:
            mount_logger: Logger instance
            mount_root: Root directory for mounting guest filesystems
        """
        self.logger = mount_logger
        self.mount_root = mount_root
        self._mounted: dict[str, str] = {}  # mountpoint -> device

    # Mount options per filesystem plus several recovery paths (NTFS dirty journal, XFS dup UUID, RO fallback).
    def mount(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        self,
        device: str,
        mountpoint: str,
        *,
        readonly: bool = False,
        options: str | None = None,
        failure_log_level: int | None = None,
    ) -> None:
        """
        Mount device at mountpoint.

        Args:
            device: Device path (e.g., /dev/nbd0p1)
            mountpoint: Mount point path (e.g., /)
            readonly: Mount read-only if True
            options: Custom mount options string
            failure_log_level: Log level for mount failures (default: ERROR, use DEBUG for probing)

        Raises:
            RuntimeError: If mount fails
        """
        # Check if already mounted at this mountpoint
        if mountpoint in self._mounted:
            current_device = self._mounted[mountpoint]
            if current_device == device:
                self.logger.debug(f"Device {device} already mounted at {mountpoint}, skipping")
                return
            self.logger.warning(
                f"Mountpoint {mountpoint} already has {current_device} mounted, cannot mount {device} there"
            )
            raise RuntimeError(
                f"Mountpoint {mountpoint} already in use by {current_device}, cannot mount {device}"
            )

        # Resolve mountpoint relative to mount root
        if mountpoint.startswith("/"):
            target = self.mount_root / mountpoint[1:]
        else:
            target = self.mount_root / mountpoint

        # Create mountpoint if needed
        target.mkdir(parents=True, exist_ok=True)

        # Detect filesystem type for appropriate mount options
        fstype = self._detect_fstype(device)

        # Build mount command with filesystem-specific options
        cmd = ["mount"]
        mount_opts = []

        if options:
            mount_opts.append(options)
        # Auto-configure based on filesystem type
        elif fstype == "ntfs":
            # Use ntfs-3g for full read-write support
            cmd.extend(["-t", "ntfs-3g"])
            if readonly:
                mount_opts.append("ro")
            else:
                # Enable permissions, compression, and streams
                mount_opts.extend(["permissions", "streams_interface=windows"])
        elif fstype in ("vfat", "msdos", "fat"):
            # FAT filesystems
            cmd.extend(["-t", "vfat"])
            mount_opts.extend(["iocharset=utf8", "shortname=mixed"])
            if readonly:
                mount_opts.append("ro")
        elif fstype == "exfat":
            # exFAT filesystem
            cmd.extend(["-t", "exfat"])
            mount_opts.append("iocharset=utf8")
            if readonly:
                mount_opts.append("ro")
        elif fstype in ("ext2", "ext3", "ext4"):
            # Linux ext filesystems
            if readonly:
                mount_opts.extend(["ro", "noload"])
        elif fstype == "xfs":
            # XFS filesystem
            if readonly:
                mount_opts.extend(["ro", "norecovery"])
        elif fstype == "btrfs":
            # Btrfs filesystem
            if readonly:
                mount_opts.extend(["ro", "norecovery"])
        # Generic fallback
        elif readonly:
            mount_opts.append("ro")

        if mount_opts:
            cmd.extend(["-o", ",".join(mount_opts)])

        cmd.extend([device, str(target)])

        # Mount with retries for different filesystem states
        try:
            run_sudo(self.logger, cmd, check=True, capture=True, failure_log_level=failure_log_level)
            self._mounted[mountpoint] = device
            self.logger.debug(f"Mounted {device} at {mountpoint} (fstype={fstype})")
            log_event("fs_mounted", device=device, mountpoint=mountpoint, fstype=fstype)
        except (subprocess.CalledProcessError, Exception) as e:
            # Extract return code from CalledProcessError or DeviceError context
            returncode = getattr(e, "returncode", 0)
            if not returncode and hasattr(e, "__cause__") and hasattr(e.__cause__, "returncode"):
                # pylint: disable-next=no-member  # guarded by hasattr() above; __cause__'s type isn't static
                returncode = e.__cause__.returncode
            error_msg = getattr(e, "stderr", "") or str(e)
            error_msg = error_msg.lower() if isinstance(error_msg, str) else ""
            stdout_msg = getattr(e, "stdout", "") or ""
            stdout_msg = stdout_msg.lower() if isinstance(stdout_msg, str) else ""

            if "already mounted" in error_msg or "already mounted" in stdout_msg:
                self.logger.debug(f"Device {device} is already mounted at {mountpoint}, treating as success")
                self._mounted[mountpoint] = device
                return

            # Check for NTFS unclean journal (Windows fast startup / hibernation)
            # ntfs-3g returns exit code 16 when the journal is dirty
            is_ntfs_dirty = (fstype in ("ntfs-3g", "ntfs")) or "ntfs" in str(e).lower()
            if is_ntfs_dirty and (returncode == 16 or returncode != 0):
                self.logger.warning("NTFS unclean journal detected — running ntfsfix and retrying...")
                try:
                    run_sudo(
                        self.logger,
                        ["ntfsfix", device],
                        check=False,
                        capture=True,
                        failure_log_level=logging.DEBUG,
                    )
                    # Retry: read-only mount always works with dirty journal
                    # For read-write, use remove_hiberfile after ntfsfix
                    retry_cmd = ["ntfs-3g"]
                    retry_opts = ["ro"] if readonly else ["remove_hiberfile"]
                    retry_cmd.extend(["-o", ",".join(retry_opts)])
                    retry_cmd.extend([device, str(target)])
                    run_sudo(
                        self.logger, retry_cmd, check=True, capture=True, failure_log_level=failure_log_level
                    )
                    self._mounted[mountpoint] = device
                    self.logger.info("NTFS mounted after ntfsfix (unclean journal fixed)")
                    log_event(
                        "fs_mounted",
                        device=device,
                        mountpoint=mountpoint,
                        fstype=fstype,
                        note="ntfsfix_applied",
                    )
                    return
                # pylint: disable-next=broad-exception-caught  # best-effort retry; falls through to error path
                except Exception as ntfs_err:
                    self.logger.warning("NTFS mount failed even after ntfsfix: %s", ntfs_err)

            # Check for XFS duplicate UUID error (common in cloned VMware VMs)
            # XFS duplicate UUID errors appear in dmesg, not stderr
            is_xfs_dup_uuid = False

            if fstype == "xfs":
                # Check stderr for generic mount errors
                if "wrong fs type" in error_msg or "bad superblock" in error_msg:
                    # Check dmesg for XFS duplicate UUID
                    try:
                        dmesg_result = run_sudo(
                            self.logger,
                            ["dmesg", "-T"],
                            check=True,
                            capture=True,
                            failure_log_level=logging.DEBUG,
                        )
                        dmesg_lines = dmesg_result.stdout.split("\n")[-50:]  # Last 50 lines
                        device_name = device.rsplit("/", maxsplit=1)[-1]  # Extract nbd2p1 from /dev/nbd2p1
                        for line in dmesg_lines:
                            if device_name in line and "duplicate uuid" in line.lower():
                                is_xfs_dup_uuid = True
                                break
                    # pylint: disable-next=broad-exception-caught  # best-effort dmesg probe; missing signal skips nouuid retry
                    except Exception:
                        pass

            if is_xfs_dup_uuid:
                self.logger.warning(
                    f"XFS duplicate UUID detected for {device}, retrying with nouuid option..."
                )
                # Retry with nouuid option
                cmd_nouuid = ["mount", "-t", "xfs"]
                # Preserve existing options and add nouuid
                nouuid_opts = [*mount_opts, "nouuid"] if mount_opts else ["nouuid"]
                cmd_nouuid.extend(["-o", ",".join(nouuid_opts)])
                cmd_nouuid.extend([device, str(target)])
                try:
                    run_sudo(
                        self.logger,
                        cmd_nouuid,
                        check=True,
                        capture=True,
                        failure_log_level=failure_log_level,
                    )
                    self._mounted[mountpoint] = device
                    self.logger.info(f"Mounted {device} at {mountpoint} (fstype=xfs, nouuid)")
                    return
                except subprocess.CalledProcessError as e2:
                    raise RuntimeError(
                        f"Failed to mount XFS filesystem on {device} (tried with nouuid option).\n"
                        "The filesystem may be severely corrupted. Try:\n"
                        f"  1. Run filesystem repair: sudo xfs_repair {device}\n"
                        f"  2. If repair fails, try with -L flag (clears log, may lose data): "
                        f"sudo xfs_repair -L {device}\n"
                        f"  3. Re-export the VM from the source hypervisor\n"
                        f"Detail: {e2.stderr}"
                    ) from e2

            # If mount failed and it's a Windows filesystem, try with additional recovery options
            if fstype in ("ntfs", "vfat", "exfat") and not readonly:
                self.logger.warning(f"Mount failed, retrying {device} in read-only mode...")
                # Retry in read-only mode
                cmd_ro = ["mount", "-t", fstype if fstype != "fat" else "vfat", "-o", "ro"]
                cmd_ro.extend([device, str(target)])
                try:
                    run_sudo(
                        self.logger, cmd_ro, check=True, capture=True, failure_log_level=failure_log_level
                    )
                    self._mounted[mountpoint] = device
                    self.logger.info(f"Mounted {device} at {mountpoint} in read-only mode")
                    return
                except subprocess.CalledProcessError:
                    pass
            # Build a helpful error message based on the filesystem type
            hints = []
            if fstype == "ntfs":
                hints.append("For NTFS: install ntfs-3g (dnf install ntfs-3g / apt install ntfs-3g)")
                hints.append("Windows Fast Startup may be locking the filesystem - disable it in Windows")
            elif fstype == "xfs":
                hints.append("For XFS duplicate UUID errors: try mounting with -o nouuid")
                hints.append("Run xfs_repair -L on the device if the filesystem is corrupted")
            elif fstype in ("ext2", "ext3", "ext4"):
                hints.append("Try: sudo e2fsck -f <device> to repair the filesystem")
                hints.append("For journal issues: mount with -o ro,noload")
            elif fstype == "btrfs":
                hints.append("Try: btrfs check --repair <device>")
                hints.append("For recovery: mount with -o ro,recovery")
            elif fstype == "unknown":
                hints.append(
                    "Filesystem type could not be detected - the partition may be swap, LVM, or raw data"
                )
                hints.append("Check the partition type: sudo blkid <device>")
            hint_text = "\n  ".join(hints) if hints else "Check system logs: journalctl -xe"
            raise RuntimeError(
                f"Failed to mount {device} (detected filesystem: {fstype}).\n"
                f"Suggestions:\n  {hint_text}\n"
                f"Detail: {e.stderr}"
            ) from e

    def _detect_fstype(self, device: str) -> str:
        """
        Detect filesystem type using multiple probing methods.

        Uses blkid -p (low-level probe) first, then falls back to lsblk.
        This is more reliable after LVM activation.

        Args:
            device: Device path

        Returns:
            Filesystem type string (e.g., "ext4", "ntfs", "xfs", "unknown")
        """
        # Try blkid with -p flag for fresh low-level probing (bypasses cache)
        try:
            result = run_sudo(
                self.logger,
                ["blkid", "-p", "-o", "value", "-s", "TYPE", device],
                check=True,
                capture=True,
                failure_log_level=logging.DEBUG,
            )
            fstype = result.stdout.strip()
            if fstype:
                return fstype
        except DeviceError:
            pass

        # Fallback to lsblk (often works when blkid doesn't after LVM activation)
        try:
            result = run_sudo(
                self.logger,
                ["lsblk", "-no", "FSTYPE", device],
                check=True,
                capture=True,
                failure_log_level=logging.DEBUG,
            )
            fstype = result.stdout.strip()
            if fstype:
                return fstype
        except DeviceError:
            pass

        return "unknown"

    def _mount_single(self, device: str, mountpoint: str, readonly: bool) -> bool:
        """
        Mount single device (internal helper for parallel execution).

        Args:
            device: Device path
            mountpoint: Mount point path
            readonly: Mount read-only if True

        Returns:
            True if mount succeeded, False otherwise
        """
        try:
            self.mount(device, mountpoint, readonly=readonly)
            return True
        # pylint: disable-next=broad-exception-caught  # mount() raises several error types; one failure must not abort the batch
        except Exception as e:
            self.logger.debug(
                f"Mount failed for {device} at {mountpoint}: {e}. "
                "This partition will be skipped. If it contains the root filesystem, "
                "check the filesystem type with 'blkid %s'.",
                device,
            )
            return False

    def mount_all_parallel(
        self, devices: list[tuple[str, str]], max_workers: int = 4, readonly: bool = True
    ) -> dict[str, bool]:
        """
        Mount multiple devices in parallel.

        This provides significant performance improvements (2-3x faster) when
        mounting multiple partitions compared to sequential mounting.

        Args:
            devices: List of (device, mountpoint) tuples
            max_workers: Maximum concurrent mount operations (default: 4)
            readonly: Mount in read-only mode (default: True)

        Returns:
            Dict mapping mountpoint to success status

        Example:
            devices = [
                ("/dev/nbd0p1", "/boot"),
                ("/dev/nbd0p2", "/"),
                ("/dev/nbd0p3", "/home"),
            ]
            results = manager.mount_all_parallel(devices, max_workers=3)
            # results: {"/boot": True, "/": True, "/home": True}
        """
        results = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all mount operations
            futures = {
                executor.submit(self._mount_single, device, mountpoint, readonly): mountpoint
                for device, mountpoint in devices
            }

            # Collect results as they complete
            for future in as_completed(futures):
                mountpoint = futures[future]
                try:
                    success = future.result()
                    results[mountpoint] = success
                # pylint: disable-next=broad-exception-caught  # one worker failure must not abort collecting the rest
                except Exception as e:
                    self.logger.warning(f"Mount failed for {mountpoint}: {e}")
                    results[mountpoint] = False

        return results

    def mount_with_fallback(self, device: str, mountpoint: str, fstype: str | None = None) -> bool:
        """
        Mount with multiple fallback strategies.

        Tries progressively more permissive mount options to handle damaged
        or problematic filesystems:
        1. Normal mount with detected filesystem type
        2. Read-only + norecovery (for damaged filesystems)
        3. Read-only + noload (for XFS/ext journals)
        4. Force mount (for NTFS)

        Args:
            device: Device path
            mountpoint: Mount point path
            fstype: Optional filesystem type (auto-detected if None)

        Returns:
            True if mount succeeded with any strategy, False otherwise

        Example:
            # Try to mount potentially damaged filesystem
            if manager.mount_with_fallback("/dev/nbd0p1", "/"):
                print("Mounted successfully with fallback")
        """
        if not fstype:
            fstype = self._detect_fstype(device)

        # Resolve mountpoint relative to mount root
        if mountpoint.startswith("/"):
            target = self.mount_root / mountpoint[1:]
        else:
            target = self.mount_root / mountpoint

        # Create mountpoint if needed
        target.mkdir(parents=True, exist_ok=True)

        strategies = [
            {"opts": None, "desc": "normal mount"},
            {"opts": "ro,norecovery", "desc": "read-only + norecovery"},
            {"opts": "ro,noload", "desc": "read-only + noload (XFS/ext)"},
        ]

        # Add NTFS-specific force option if applicable
        if fstype == "ntfs":
            strategies.append({"opts": "force", "desc": "force mount (NTFS)"})

        for strategy in strategies:
            try:
                self.logger.debug(f"Trying mount strategy: {strategy['desc']}")

                if strategy["opts"]:
                    # Custom mount with specific options
                    cmd = ["mount", "-t", fstype or "auto", "-o", strategy["opts"]]
                    cmd.extend([device, str(target)])
                    run_sudo(self.logger, cmd, check=True, capture=True, failure_log_level=logging.DEBUG)
                else:
                    # Normal mount (use existing method)
                    self.mount(device, mountpoint, readonly=False)

                self.logger.info(f"Mount succeeded with strategy: {strategy['desc']}")
                return True

            # pylint: disable-next=broad-exception-caught  # try the next fallback strategy regardless of failure
            except Exception as e:
                self.logger.debug(f"Strategy '{strategy['desc']}' failed: {e}")
                continue

        self.logger.error(f"All mount strategies failed for {device}")
        return False

    def umount_all(self) -> None:
        """Unmount all mounted filesystems."""
        # Unmount in reverse order (deepest first)
        for mountpoint in sorted(self._mounted.keys(), reverse=True):
            try:
                if mountpoint.startswith("/"):
                    target = self.mount_root / mountpoint[1:]
                else:
                    target = self.mount_root / mountpoint

                run_sudo(self.logger, ["umount", str(target)], check=False, capture=True)
                self.logger.debug(f"Unmounted {mountpoint}")
                log_event("fs_unmounted", mountpoint=mountpoint)
            # pylint: disable-next=broad-exception-caught  # best-effort cleanup; one failure must not abort the rest
            except Exception as e:
                self.logger.warning(f"Failed to unmount {mountpoint}: {e}")

        self._mounted.clear()

    def umount(self, mountpoint: str) -> None:
        """
        Unmount a specific mountpoint.

        Args:
            mountpoint: Mount point path to unmount
        """
        if mountpoint not in self._mounted:
            return

        try:
            if mountpoint.startswith("/"):
                target = self.mount_root / mountpoint[1:]
            else:
                target = self.mount_root / mountpoint

            run_sudo(self.logger, ["umount", str(target)], check=True, capture=True)
            del self._mounted[mountpoint]
            self.logger.debug(f"Unmounted {mountpoint}")
        except DeviceError as e:
            self.logger.warning(f"Failed to unmount {mountpoint}: {e}")

    def mountpoints(self) -> list[str]:
        """Get list of current mountpoints."""
        return list(self._mounted.keys())

    def mounts(self) -> list[str]:
        """Get list of mounted devices."""
        return list(self._mounted.values())

    def is_mounted(self, mountpoint: str) -> bool:
        """Check if a mountpoint is currently mounted."""
        return mountpoint in self._mounted

    def get_device(self, mountpoint: str) -> str | None:
        """Get the device mounted at a specific mountpoint."""
        return self._mounted.get(mountpoint)
