# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Utility functions for offline VM fixes.

These are low-level helpers for:
- Block device inspection (UUID, LABEL, filesystem type)
- OS detection from mounted root filesystem
- LVM handling
- Safe file operations with backups
"""

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BlockDevice:
    """Block device information."""

    device: str
    uuid: Optional[str] = None
    label: Optional[str] = None
    fstype: Optional[str] = None
    mountpoint: Optional[str] = None
    is_lvm: bool = False


def run_command(cmd: list[str], check: bool = True, timeout: int = 30) -> tuple[int, str, str]:
    """
    Run a command and return (returncode, stdout, stderr).

    Args:
        cmd: Command and arguments as list
        check: Raise exception on non-zero exit
        timeout: Command timeout in seconds

    Returns:
        Tuple of (returncode, stdout, stderr)
    """
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=check)
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.CalledProcessError as e:
        if check:
            raise
        return e.returncode, e.stdout.strip() if e.stdout else "", e.stderr.strip() if e.stderr else ""
    except subprocess.TimeoutExpired:
        logger.exception("Command timed out after %ss: %s", timeout, " ".join(cmd))
        raise


def get_block_device_uuid(device: str) -> Optional[str]:
    """
    Get UUID of a block device using blkid.

    Args:
        device: Block device path (e.g., /dev/sda1, /dev/mapper/vg0-root)

    Returns:
        UUID string or None if not found

    Example:
        >>> get_block_device_uuid("/dev/sda1")
        "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    """
    try:
        # blkid -s UUID -o value /dev/sda1
        returncode, stdout, _ = run_command(["blkid", "-s", "UUID", "-o", "value", device], check=False)

        if returncode == 0 and stdout:
            uuid = stdout.strip()
            logger.debug("Found UUID for %s: %s", device, uuid)
            return uuid

        logger.debug("No UUID found for %s", device)
        return None

    except Exception as e:  # pylint: disable=broad-exception-caught
        # Best-effort UUID lookup; any blkid/subprocess failure should
        # degrade to None rather than abort the caller.
        logger.warning("Failed to get UUID for %s: %s", device, e)
        return None


def get_block_device_label(device: str) -> Optional[str]:
    """
    Get filesystem label of a block device.

    Args:
        device: Block device path

    Returns:
        Label string or None if not found
    """
    try:
        returncode, stdout, _ = run_command(["blkid", "-s", "LABEL", "-o", "value", device], check=False)

        if returncode == 0 and stdout:
            label = stdout.strip()
            logger.debug("Found LABEL for %s: %s", device, label)
            return label

        return None

    except Exception as e:  # pylint: disable=broad-exception-caught
        # Best-effort LABEL lookup; any blkid/subprocess failure should
        # degrade to None rather than abort the caller.
        logger.warning("Failed to get LABEL for %s: %s", device, e)
        return None


def get_block_device_fstype(device: str) -> Optional[str]:
    """
    Get filesystem type of a block device.

    Args:
        device: Block device path

    Returns:
        Filesystem type (ext4, xfs, swap, etc.) or None
    """
    try:
        returncode, stdout, _ = run_command(["blkid", "-s", "TYPE", "-o", "value", device], check=False)

        if returncode == 0 and stdout:
            fstype = stdout.strip()
            logger.debug("Found TYPE for %s: %s", device, fstype)
            return fstype

        return None

    except Exception as e:  # pylint: disable=broad-exception-caught
        # Best-effort TYPE lookup; any blkid/subprocess failure should
        # degrade to None rather than abort the caller.
        logger.warning("Failed to get TYPE for %s: %s", device, e)
        return None


def get_block_device_info(device: str) -> BlockDevice:
    """
    Get comprehensive information about a block device.

    Args:
        device: Block device path

    Returns:
        BlockDevice dataclass with all available information
    """
    return BlockDevice(
        device=device,
        uuid=get_block_device_uuid(device),
        label=get_block_device_label(device),
        fstype=get_block_device_fstype(device),
        is_lvm=is_lvm_device(device),
    )


def is_lvm_device(device: str) -> bool:
    """
    Check if a device is an LVM logical volume.

    Args:
        device: Block device path

    Returns:
        True if device is LVM, False otherwise

    Examples:
        >>> is_lvm_device("/dev/mapper/vg0-root")
        True
        >>> is_lvm_device("/dev/sda1")
        False
    """
    # Method 1: Check /dev/mapper/ path
    if device.startswith("/dev/mapper/"):
        # Exclude multipath devices (mpath*)
        if "mpath" not in device:
            return True

    # Method 2: Check /dev/vg_name/lv_name path
    if device.startswith("/dev/") and "/" in device[5:]:
        parts = device[5:].split("/")
        if len(parts) == 2 and not parts[0].startswith("sd") and not parts[0].startswith("nvme"):
            return True

    # Method 3: Use lvdisplay if available
    try:
        returncode, _, _ = run_command(["lvdisplay", device], check=False, timeout=5)
        if returncode == 0:
            return True
    except Exception:  # pylint: disable=broad-exception-caught
        # Best-effort LVM detection fallback; lvdisplay not being
        # available/working must not abort the caller.
        pass

    return False


def resolve_device_to_path(device_spec: str, _root_mount: str = "/mnt") -> Optional[str]:
    """
    Resolve a device specification to actual device path.

    Handles:
    - UUID=xxx → /dev/sdaX
    - LABEL=xxx → /dev/sdaX
    - /dev/sdaX → /dev/sdaX
    - /dev/mapper/xxx → /dev/mapper/xxx

    Args:
        device_spec: Device specification from fstab
        _root_mount: Root filesystem mount point; accepted for interface
            parity with callers but not currently used by this resolution
            strategy (blkid is queried directly rather than scoped to a
            mounted root).

    Returns:
        Resolved device path or None if not found

    Example:
        >>> resolve_device_to_path("UUID=a1b2c3d4-...")
        "/dev/sda1"
    """
    device_spec = device_spec.strip()

    # Already a device path
    if device_spec.startswith("/dev/"):
        return device_spec

    # UUID=xxx
    if device_spec.startswith("UUID="):
        uuid = device_spec[5:]
        try:
            returncode, stdout, _ = run_command(["blkid", "-U", uuid], check=False)
            if returncode == 0 and stdout:
                return stdout.strip()
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Best-effort UUID resolution; any blkid/subprocess failure
            # should degrade to None rather than abort the caller.
            logger.warning("Failed to resolve UUID=%s: %s", uuid, e)
        return None

    # LABEL=xxx
    if device_spec.startswith("LABEL="):
        label = device_spec[6:]
        try:
            returncode, stdout, _ = run_command(["blkid", "-L", label], check=False)
            if returncode == 0 and stdout:
                return stdout.strip()
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Best-effort LABEL resolution; any blkid/subprocess failure
            # should degrade to None rather than abort the caller.
            logger.warning("Failed to resolve LABEL=%s: %s", label, e)
        return None

    return None


def detect_os_from_root(root_mount: str) -> dict[str, str]:
    """
    Detect OS distribution from mounted root filesystem.

    Args:
        root_mount: Path where root filesystem is mounted

    Returns:
        Dictionary with OS information:
        - family: centos, rhel, ubuntu, debian, etc.
        - name: Full OS name
        - version: Version number
        - version_id: Version ID

    Example:
        >>> detect_os_from_root("/mnt")
        {'family': 'centos', 'name': 'CentOS Stream', 'version': '9', 'version_id': '9'}
    """
    os_release_path = Path(root_mount) / "etc/os-release"

    if not os_release_path.exists():
        # Try legacy redhat-release
        redhat_release = Path(root_mount) / "etc/redhat-release"
        if redhat_release.exists():
            content = redhat_release.read_text()
            return _parse_redhat_release(content)

        logger.warning("No /etc/os-release found in %s", root_mount)
        return {"family": "unknown", "name": "Unknown", "version": "unknown", "version_id": "unknown"}

    # pylint: disable=duplicate-code
    # reason: mirrors the equivalent "split key/value lines" config parsing
    # loop in vmcraft/enhanced_inspection.py (ifcfg/BOOTPROTO parsing) --
    # structurally similar by coincidence, not shared logic; keeping
    # independent avoids coupling unrelated config-parsing code paths.
    # Parse /etc/os-release
    os_info = {}
    content = os_release_path.read_text()

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if "=" in line:
            key, value = line.split("=", 1)
            # Remove quotes
            value = value.strip('"').strip("'")
            os_info[key] = value

    # Determine family from ID
    os_id = os_info.get("ID", "unknown").lower()
    family_map = {
        "centos": "centos",
        "rhel": "rhel",
        "redhat": "rhel",
        "fedora": "fedora",
        "ubuntu": "ubuntu",
        "debian": "debian",
        "photon": "photon",
        "sles": "sles",
        "opensuse": "suse",
    }

    family = family_map.get(os_id, os_id)

    return {
        "family": family,
        "name": os_info.get("NAME", "Unknown"),
        "version": os_info.get("VERSION", "unknown"),
        "version_id": os_info.get("VERSION_ID", "unknown"),
        "pretty_name": os_info.get("PRETTY_NAME", "Unknown OS"),
    }


def _parse_redhat_release(content: str) -> dict[str, str]:
    """Parse legacy /etc/redhat-release file."""
    # Example: "CentOS Linux release 7.9.2009 (Core)"
    if "CentOS" in content:
        family = "centos"
    elif "Red Hat" in content or "RHEL" in content:
        family = "rhel"
    elif "Fedora" in content:
        family = "fedora"
    else:
        family = "unknown"

    # Extract version number
    version_match = re.search(r"release (\d+(?:\.\d+)?)", content)
    version = version_match.group(1) if version_match else "unknown"

    return {
        "family": family,
        "name": content.strip(),
        "version": version,
        "version_id": version.split(".")[0] if "." in version else version,
    }


def create_backup(file_path: Path, suffix: str = ".backup") -> Path:
    """
    Create a backup of a file.

    Args:
        file_path: Path to file to backup
        suffix: Backup file suffix

    Returns:
        Path to backup file

    Raises:
        IOError: If backup creation fails
    """
    if not file_path.exists():
        raise FileNotFoundError(
            f"Required file not found: {file_path}. Ensure the file exists and the path is correct."
        )

    backup_path = file_path.with_suffix(file_path.suffix + suffix)

    # Don't overwrite existing backup
    counter = 1
    while backup_path.exists():
        backup_path = file_path.with_suffix(f"{file_path.suffix}{suffix}.{counter}")
        counter += 1

    try:
        shutil.copy2(file_path, backup_path)
        logger.info("Created backup: %s", backup_path)
        return backup_path
    except Exception as e:
        logger.exception("Failed to create backup of %s: %s", file_path, e)
        raise


def validate_uuid_format(uuid: str) -> bool:
    """
    Validate UUID format.

    Args:
        uuid: UUID string to validate

    Returns:
        True if valid UUID format, False otherwise

    Example:
        >>> validate_uuid_format("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        True
        >>> validate_uuid_format("not-a-uuid")
        False
    """
    # Standard UUID format: 8-4-4-4-12 hex digits
    uuid_pattern = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
    )
    return bool(uuid_pattern.match(uuid))
