# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
LVM operations for VMCraft.

"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path


class LVMError(Exception):
    """LVM operation failed."""


class LVM:  # pylint: disable=too-many-public-methods
    # reason: wraps the full LVM command surface (pv/vg/lv scan, create, activate,
    # resize, remove, etc.) as one cohesive, discoverable API.
    """
    LVM operations wrapper for VMCraft.

    Pure Python implementation providing:
    - Proper udev settling after operations
    - Canonical LV name resolution
    - Safe error handling
    - Output parsing that filters "unknown device"
    - Caching for performance
    - Timeout protection

    Example:
        # Scan and activate all VGs
        lvm = LVM()
        lvm.scan(activate=True)

        # List logical volumes
        lvs = lvm.lvs()

        # Activate specific VGs
        lvm.vg_activate(True, ["vg_name"])
    """

    MAX_ARGS = 64
    DEFAULT_TIMEOUT = 30

    def __init__(
        self,
        logger: logging.Logger | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        use_cache: bool = True,
        env: dict[str, str] | None = None,
        device_filter: str | None = None,
    ):
        """
        Initialize LVM wrapper.

        Args:
            logger: Optional logger instance
            timeout: Command timeout in seconds (default: 30)
            use_cache: Enable caching of list operations (default: True)
            env: Environment dict (e.g. with LVM_SYSTEM_DIR for isolation)
            device_filter: LVM --config string to restrict device scanning
        """
        self.logger = logger or logging.getLogger(__name__)
        self.timeout = timeout
        self.use_cache = use_cache
        self._cache: dict[str, list[str]] = {}
        self._env = env
        self._device_filter = device_filter

    # -----------------------------
    # Core command runner
    # -----------------------------
    def _run(self, *args: str, capture_output: bool = True, ignore_error: bool = False) -> str:
        """
        Run LVM command with proper error handling.

        If a device_filter was set, it is automatically injected as
        --config <filter> after the LVM subcommand. If an env dict was
        set (e.g. with LVM_SYSTEM_DIR), it is passed to subprocess.

        Args:
            *args: Command and arguments
            capture_output: Capture stdout (default: True)
            ignore_error: Don't raise on non-zero exit (default: False)

        Returns:
            Command stdout if capture_output=True, else empty string

        Raises:
            LVMError: If command fails and ignore_error=False
        """
        # Inject --config <device_filter> if set.
        # LVM commands are typically: lvm <subcmd> [options...]
        # Insert --config after the subcommand (index 2) so it applies.
        cmd = list(args)
        if self._device_filter and len(cmd) >= 2:
            cmd.insert(2, "--config")
            cmd.insert(3, self._device_filter)

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE if capture_output else None,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.timeout,
                env=self._env,
                check=False,
            )

            if result.returncode != 0 and not ignore_error:
                stderr = result.stderr.strip()
                sl = stderr.lower()
                hint = ""
                if "not found" in sl or "no such file" in sl:
                    hint = (
                        "\n\nLVM tools not installed. Install with:\n"
                        "  RHEL/Fedora: dnf install lvm2\n"
                        "  Ubuntu/Debian: apt install lvm2\n"
                        "Also ensure the dm_mod kernel module is loaded: modprobe dm_mod"
                    )
                elif "device not found" in sl or "no devices found" in sl:
                    hint = (
                        "\n\nLVM cannot find the expected devices. Ensure:\n"
                        "  - The NBD device is connected: qemu-nbd --connect /dev/nbdN <image>\n"
                        "  - Partitions are scanned: partprobe /dev/nbdN\n"
                        "  - The disk actually contains LVM physical volumes"
                    )
                elif "duplicate" in sl:
                    hint = (
                        "\n\nDuplicate VG/PV UUIDs detected (common with cloned VMs). "
                        "Use vgimportclone to safely import the cloned disk:\n"
                        "  vgimportclone /dev/nbdNpM"
                    )
                raise LVMError(f"{stderr}{hint}")

            return result.stdout.strip() if capture_output else ""

        except FileNotFoundError as e:
            cmd_name = args[0] if args else "lvm"
            raise LVMError(
                f"LVM command '{cmd_name}' not found. Install lvm2:\n"
                "  RHEL/Fedora: dnf install lvm2\n"
                "  Ubuntu/Debian: apt install lvm2"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise LVMError(
                f"LVM command timed out after {self.timeout}s: {' '.join(args)}\n"
                "This may indicate a stuck device-mapper operation. Check:\n"
                "  - dmesg for I/O errors\n"
                "  - dmsetup status for stuck DM devices\n"
                "  - Whether the underlying storage is responsive"
            ) from e
        except subprocess.CalledProcessError as e:
            if not ignore_error:
                raise LVMError(e.stderr.strip()) from e
            return ""

    def _run_no_output(self, *args: str) -> None:
        """Run LVM command without capturing output."""
        self._run(*args, capture_output=False)

    # -----------------------------
    # udev settle equivalent
    # -----------------------------
    def udev_settle(self) -> None:
        """
        Wait for udev to settle after LVM operations.

        Wait for udev to process pending events, ensuring device nodes
        are fully created and visible before proceeding.
        """
        try:
            subprocess.run(
                ["udevadm", "settle"],
                check=False,
                timeout=10,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    # -----------------------------
    # Cache management
    # -----------------------------
    def _cache_get(self, key: str) -> list[str] | None:
        """Get cached value if caching enabled."""
        if not self.use_cache:
            return None
        return self._cache.get(key)

    def _cache_set(self, key: str, value: list[str]) -> None:
        """Set cached value if caching enabled."""
        if self.use_cache:
            self._cache[key] = value

    def invalidate_cache(self) -> None:
        """Clear all cached values."""
        self._cache.clear()

    # -----------------------------
    # Convert LVM output
    # -----------------------------
    @staticmethod
    def _convert_output(output: str, prefix: str | None = None) -> list[str]:
        """
        Parse and filter LVM command output.

        Filters out:
        - Empty lines
        - "unknown device" entries

        Args:
            output: Raw LVM command output
            prefix: Optional prefix to add to each line

        Returns:
            Sorted list of valid entries
        """
        result = []

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue

            if prefix:
                line = prefix + line

            # Filter out "unknown device" entries
            if line != "unknown device":
                result.append(line)

        result.sort()
        return result

    # -----------------------------
    # List commands
    # -----------------------------
    def pvs(self) -> list[str]:
        """
        List all physical volumes (cached).

        Returns:
            Sorted list of PV device paths (e.g., ['/dev/sda2'])
        """
        cached = self._cache_get("pvs")
        if cached is not None:
            return cached

        out = self._run("lvm", "pvs", "-o", "pv_name", "--noheadings")
        result = self._convert_output(out)
        self._cache_set("pvs", result)
        return result

    def vgs(self) -> list[str]:
        """
        List all volume groups (cached).

        Returns:
            Sorted list of VG names (e.g., ['rhel', 'vg_data'])
        """
        cached = self._cache_get("vgs")
        if cached is not None:
            return cached

        out = self._run("lvm", "vgs", "-o", "vg_name", "--noheadings")
        result = self._convert_output(out)
        self._cache_set("vgs", result)
        return result

    def lvs(self) -> list[str]:
        """
        List all logical volumes in /dev/VG/LV format (cached).

        Returns:
            Sorted list of LV paths (e.g., ['/dev/rhel/root', '/dev/rhel/swap'])
        """
        cached = self._cache_get("lvs")
        if cached is not None:
            return cached

        out = self._run("lvm", "lvs", "-o", "lv_path", "--noheadings")
        result = self._convert_output(out)
        self._cache_set("lvs", result)
        return result

    # -----------------------------
    # Create operations
    # -----------------------------
    def pvcreate(self, device: str) -> None:
        """Create physical volume on device."""
        self._run_no_output("lvm", "pvcreate", "--force", device)
        self.udev_settle()

    def vgcreate(self, vg: str, devices: list[str]) -> None:
        """Create volume group from physical volumes."""
        self._run_no_output("lvm", "vgcreate", vg, *devices)
        self.udev_settle()

    def lvcreate(self, name: str, vg: str, size_mb: int) -> None:
        """Create logical volume with fixed size in MB."""
        self._run_no_output("lvm", "lvcreate", "--yes", "-L", str(size_mb), "-n", name, vg)
        self.udev_settle()

    def lvcreate_free(self, name: str, vg: str, percent: int) -> None:
        """
        Create logical volume using percentage of free space.

        Args:
            name: LV name
            vg: VG name
            percent: Percentage of free space (0-100)
        """
        if not 0 <= percent <= 100:
            raise ValueError(f"LV free-space percentage must be 0-100, got {percent}.")

        self._run_no_output("lvm", "lvcreate", "-l", f"{percent}%FREE", "-n", name, vg)
        self.udev_settle()

    # -----------------------------
    # Remove operations
    # -----------------------------
    def lvremove(self, device: str) -> None:
        """Remove logical volume."""
        self._run_no_output("lvm", "lvremove", "-f", device)
        self.udev_settle()

    def vgremove(self, vg: str) -> None:
        """Remove volume group."""
        self._run_no_output("lvm", "vgremove", "-f", vg)
        self.udev_settle()

    def pvremove(self, device: str) -> None:
        """Remove physical volume."""
        self._run_no_output("lvm", "pvremove", "-ff", device)
        self.udev_settle()

    # -----------------------------
    # Resize operations
    # -----------------------------
    def lvresize(self, device: str, size_mb: int) -> None:
        """
        Resize logical volume to fixed size.

        Ignores "matches existing size" errors (benign).
        """
        try:
            self._run_no_output("lvm", "lvresize", "--force", "-L", str(size_mb), device)
        except LVMError as e:
            if "matches existing size" not in str(e):
                raise

    def lvresize_free(self, device: str, percent: int) -> None:
        """
        Extend logical volume by percentage of free space.

        Ignores "matches existing size" errors (benign).
        """
        try:
            self._run_no_output("lvm", "lvresize", "-l", f"+{percent}%FREE", device)
        except LVMError as e:
            if "matches existing size" not in str(e):
                raise

    def pvresize(self, device: str) -> None:
        """Resize physical volume to fill device."""
        self._run_no_output("lvm", "pvresize", device)

    def pvresize_size(self, device: str, size_bytes: int) -> None:
        """Resize physical volume to specific size in bytes."""
        self._run_no_output("lvm", "pvresize", "--yes", "--setphysicalvolumesize", f"{size_bytes}b", device)

    # -----------------------------
    # Activate / deactivate
    # -----------------------------
    def vg_activate(self, activate: bool, vgs: list[str]) -> None:
        """
        Activate or deactivate specific volume groups.

        After activation, device nodes like /dev/VG/LV become visible.

        Args:
            activate: True to activate, False to deactivate
            vgs: List of VG names to activate
        """
        state = "y" if activate else "n"
        self._run_no_output("lvm", "vgchange", "-a", state, *vgs)
        self.udev_settle()

    def vg_activate_all(self, activate: bool) -> None:
        """
        Activate or deactivate all volume groups.

        Args:
            activate: True to activate, False to deactivate
        """
        state = "y" if activate else "n"
        self._run_no_output("lvm", "vgchange", "-a", state)
        self.udev_settle()

    # -----------------------------
    # UUID operations
    # -----------------------------
    def pvuuid(self, device: str) -> str:
        """Get physical volume UUID."""
        return self._run("lvm", "pvs", "--noheadings", "-o", "pv_uuid", device).strip()

    def vguuid(self, vg: str) -> str:
        """Get volume group UUID."""
        return self._run("lvm", "vgs", "--noheadings", "-o", "vg_uuid", vg).strip()

    def lvuuid(self, device: str) -> str:
        """Get logical volume UUID."""
        return self._run("lvm", "lvs", "--noheadings", "-o", "lv_uuid", device).strip()

    # -----------------------------
    # Scan
    # -----------------------------
    def scan(self, activate: bool = False) -> None:
        """
        Scan for LVM physical volumes and optionally activate them.

        When activate=True, newly found VGs/LVs become visible.

        Args:
            activate: If True, activate found volume groups
        """
        args = ["lvm", "pvscan", "--cache"]
        if activate:
            args.extend(["--activate", "ay"])
        self._run_no_output(*args)
        self.udev_settle()

    # -----------------------------
    # Canonical LV resolution
    # -----------------------------
    def canonical_lv(self, device: str) -> str | None:
        """
        Resolve device to canonical /dev/VG/LV path.

        Uses device number (st_rdev) comparison to find the canonical path.

        Args:
            device: Device path (e.g., /dev/mapper/rhel-root or /dev/dm-0)

        Returns:
            Canonical path (e.g., /dev/rhel/root) or None if not found
        """
        try:
            target_stat = Path(device).stat()
        except FileNotFoundError:
            return None

        for lv in self.lvs():
            try:
                lv_stat = Path(lv).stat()
                # Compare device numbers (major:minor)
                if target_stat.st_rdev == lv_stat.st_rdev:
                    return lv
            except FileNotFoundError:
                pass

        return None

    # -----------------------------
    # VG metadata backup
    # -----------------------------
    def vgmeta(self, vg: str) -> bytes:
        """
        Export volume group metadata.

        Returns:
            Raw VG metadata in LVM format
        """
        with tempfile.NamedTemporaryFile(delete=False) as f:
            tmp = f.name

        try:
            self._run_no_output("lvm", "vgcfgbackup", "-f", tmp, vg)

            with open(tmp, "rb") as f:
                return f.read()

        finally:
            os.unlink(tmp)

    # -----------------------------
    # Change UUID
    # -----------------------------
    def pvchange_uuid(self, device: str) -> None:
        """Generate new UUID for physical volume."""
        self._run_no_output("lvm", "pvchange", "-u", device)
        self.udev_settle()

    def vgchange_uuid(self, vg: str) -> None:
        """Generate new UUID for volume group."""
        self._run_no_output("lvm", "vgchange", "-u", vg)
        self.udev_settle()

    def vgimportclone(self, device: str) -> None:
        """
        Safely regenerate PV and VG UUIDs for a cloned disk.

        Uses ``vgimportclone`` which atomically handles the PV UUID
        regeneration and VG rename in a single operation.  This is
        safer than separate ``pvchange -u`` + ``vgchange -u`` calls
        because it avoids a window where duplicate UUIDs are visible.

        Args:
            device: Block device containing the cloned PV
                (e.g. ``/dev/nbd0p2``, ``/dev/sdb1``)

        Raises:
            LVMError: If vgimportclone fails
        """
        self._run_no_output("lvm", "vgimportclone", device)
        self.invalidate_cache()
        self.udev_settle()
