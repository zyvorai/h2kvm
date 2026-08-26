# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/vmcraft/linux_detection.py
"""
Linux distribution detection and identification.

Provides comprehensive Linux OS detection using multiple methods:
- /etc/os-release (modern systemd standard)
- /etc/lsb-release (LSB standard)
- Distribution-specific files (redhat-release, debian_version, etc.)
- /etc/issue (fallback)

Supports all major distributions:
- Red Hat family (RHEL, CentOS, Fedora, Rocky, AlmaLinux, Oracle Linux)
- Debian family (Debian, Ubuntu)
- SUSE family (SLES, openSUSE)
- Arch Linux
- Gentoo
- Alpine Linux
- Slackware
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class LinuxDetector:  # pylint: disable=too-few-public-methods
    # reason: single-purpose detector class wrapping gather_linux_info; the
    # class exists to hold logger/mount_root state, not to expose many methods.
    """
    Linux distribution detector.

    Detects OS information from a mounted Linux root filesystem.
    """

    def __init__(self, detector_logger: logging.Logger, mount_root: Path):
        """
        Initialize Linux detector.

        Args:
            detector_logger: Logger instance
            mount_root: Root directory where guest filesystem is mounted
        """
        self.logger = detector_logger
        self.mount_root = mount_root

    def gather_linux_info(  # pylint: disable=too-many-return-statements
        self, _root: str, info: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Comprehensive Linux distribution detection.

        Detection order:
        1. /etc/os-release (modern standard)
        2. /etc/lsb-release (LSB standard)
        3. Distribution-specific files (redhat-release, debian_version, etc.)
        4. /etc/issue (fallback)

        Args:
            _root: Root device path (unused here; detection uses self.mount_root,
                kept for call-site symmetry with WindowsDetector.gather_windows_info)
            info: Base OS info dict to populate

        Returns:
            Updated info dict with Linux-specific fields
        """
        info["type"] = "linux"

        # Method 1: /etc/os-release (systemd standard - most reliable)
        if self._try_os_release(info):
            return info

        # Method 2: /etc/lsb-release (older LSB standard)
        if self._try_lsb_release(info):
            return info

        # Method 3: Distribution-specific detection files
        if self._try_redhat_release(info):
            return info

        if self._try_suse_release(info):
            return info

        if self._try_debian_version(info):
            return info

        if self._try_arch_release(info):
            return info

        if self._try_gentoo_release(info):
            return info

        if self._try_alpine_release(info):
            return info

        if self._try_slackware_version(info):
            return info

        # Method 4: Fallback to /etc/issue
        self._try_issue_fallback(info)

        return info

    def _try_os_release(self, info: dict[str, Any]) -> bool:
        """Try /etc/os-release (systemd standard)."""
        os_release = self.mount_root / "etc/os-release"
        if not os_release.exists():
            return False

        try:
            data = {}
            for line in os_release.read_text().splitlines():
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    key, val = line.split("=", 1)
                    data[key.strip()] = val.strip().strip('"').strip("'")

            # Extract comprehensive info
            info["product"] = data.get("PRETTY_NAME", data.get("NAME", "Linux"))
            info["distro"] = data.get("ID", "linux").lower()

            # Version parsing
            version_id = data.get("VERSION_ID", "0")
            if version_id:
                parts = version_id.split(".")
                try:
                    info["major"] = int(parts[0])
                    info["minor"] = int(parts[1]) if len(parts) > 1 else 0
                except (ValueError, IndexError):
                    pass

            # Additional metadata
            info["codename"] = data.get("VERSION_CODENAME") or data.get("UBUNTU_CODENAME")

            # Detect variant (Server, Desktop, etc.)
            variant = data.get("VARIANT") or data.get("VARIANT_ID")
            if variant:
                info["variant"] = variant
            elif "server" in info["product"].lower():
                info["variant"] = "Server"

            return True

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort distro-detection file parse; try the next
            # detection method instead of aborting on a malformed/unreadable file
            self.logger.debug(f"Failed to parse os-release: {e}")
            return False

    def _try_lsb_release(self, info: dict[str, Any]) -> bool:
        """Try /etc/lsb-release (LSB standard)."""
        lsb_release = self.mount_root / "etc/lsb-release"
        if not lsb_release.exists():
            return False

        try:
            data = {}
            for line in lsb_release.read_text().splitlines():
                if "=" in line:
                    key, val = line.split("=", 1)
                    data[key.strip()] = val.strip().strip('"')

            info["product"] = data.get("DISTRIB_DESCRIPTION", "Linux")
            info["distro"] = data.get("DISTRIB_ID", "linux").lower()

            version = data.get("DISTRIB_RELEASE", "0")
            parts = version.split(".")
            try:
                info["major"] = int(parts[0])
                info["minor"] = int(parts[1]) if len(parts) > 1 else 0
            except (ValueError, IndexError):
                pass

            info["codename"] = data.get("DISTRIB_CODENAME")
            return True

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort distro-detection file parse; try the next
            # detection method instead of aborting on a malformed/unreadable file
            self.logger.debug(f"Failed to parse lsb-release: {e}")
            return False

    def _try_redhat_release(self, info: dict[str, Any]) -> bool:
        """Try Red Hat family detection."""
        redhat_release = self.mount_root / "etc/redhat-release"
        if not redhat_release.exists():
            return False

        try:
            content = redhat_release.read_text().strip()
            info["product"] = content

            # Detect distro
            if "Red Hat Enterprise Linux" in content or "RHEL" in content:
                info["distro"] = "rhel"
                info["variant"] = "Server"
            elif "CentOS Stream" in content:
                info["distro"] = "centos-stream"
            elif "CentOS Linux" in content or "CentOS" in content:
                info["distro"] = "centos"
            elif "Fedora" in content:
                info["distro"] = "fedora"
            elif "Rocky Linux" in content:
                info["distro"] = "rocky"
            elif "AlmaLinux" in content:
                info["distro"] = "almalinux"
            elif "Oracle Linux" in content:
                info["distro"] = "ol"
                info["variant"] = "Server"

            # Extract version
            version_match = re.search(r"release\s+(\d+)\.?(\d*)", content)
            if version_match:
                info["major"] = int(version_match.group(1))
                if version_match.group(2):
                    info["minor"] = int(version_match.group(2))

            # Extract codename
            codename_match = re.search(r"\(([^)]+)\)", content)
            if codename_match:
                info["codename"] = codename_match.group(1)

            return True

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort distro-detection file parse; try the next
            # detection method instead of aborting on a malformed/unreadable file
            self.logger.debug(f"Failed to parse redhat-release: {e}")
            return False

    def _try_suse_release(self, info: dict[str, Any]) -> bool:
        """Try SUSE family detection."""
        suse_release = self.mount_root / "etc/SuSE-release"
        if not suse_release.exists():
            return False

        try:
            content = suse_release.read_text()
            lines = content.strip().splitlines()

            if lines:
                info["product"] = lines[0]

                if "openSUSE" in content:
                    info["distro"] = "opensuse"
                    if "Leap" in content:
                        info["variant"] = "Leap"
                    elif "Tumbleweed" in content:
                        info["variant"] = "Tumbleweed"
                elif "SUSE Linux Enterprise Server" in content or "SLES" in content:
                    info["distro"] = "sles"
                    info["variant"] = "Server"
                elif "SUSE Linux Enterprise Desktop" in content:
                    info["distro"] = "sled"
                    info["variant"] = "Desktop"
                else:
                    info["distro"] = "suse"

                # Parse VERSION and PATCHLEVEL
                for line in lines[1:]:
                    if line.startswith("VERSION"):
                        info["major"] = int(line.split("=")[1].strip())
                    elif line.startswith("PATCHLEVEL"):
                        info["minor"] = int(line.split("=")[1].strip())

            return True

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort distro-detection file parse; try the next
            # detection method instead of aborting on a malformed/unreadable file
            self.logger.debug(f"Failed to parse SuSE-release: {e}")
            return False

    def _try_debian_version(self, info: dict[str, Any]) -> bool:
        """Try Debian family detection."""
        debian_version = self.mount_root / "etc/debian_version"
        if not debian_version.exists():
            return False

        try:
            version = debian_version.read_text().strip()
            info["distro"] = "debian"
            info["product"] = f"Debian GNU/Linux {version}"

            # Parse version (e.g., "11.6" or "bookworm/sid")
            if "/" not in version:
                parts = version.split(".")
                try:
                    info["major"] = int(parts[0])
                    info["minor"] = int(parts[1]) if len(parts) > 1 else 0
                except ValueError:
                    pass
            else:
                info["codename"] = version.split("/")[0]

            return True

        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort distro-detection file parse; try the next
            # detection method instead of aborting on a malformed/unreadable file
            self.logger.debug(f"Failed to parse debian_version: {e}")
            return False

    def _try_arch_release(self, info: dict[str, Any]) -> bool:
        """Try Arch Linux detection."""
        arch_release = self.mount_root / "etc/arch-release"
        if not arch_release.exists():
            return False

        info["distro"] = "arch"
        info["product"] = "Arch Linux"
        # Arch is rolling release, no version number
        return True

    def _try_gentoo_release(self, info: dict[str, Any]) -> bool:
        """Try Gentoo detection."""
        gentoo_release = self.mount_root / "etc/gentoo-release"
        if not gentoo_release.exists():
            return False

        try:
            content = gentoo_release.read_text().strip()
            info["distro"] = "gentoo"
            info["product"] = content

            version_match = re.search(r"(\d+)\.(\d+)", content)
            if version_match:
                info["major"] = int(version_match.group(1))
                info["minor"] = int(version_match.group(2))

            return True

        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort distro-detection file parse; try the next
            # detection method instead of aborting on a malformed/unreadable file
            return False

    def _try_alpine_release(self, info: dict[str, Any]) -> bool:
        """Try Alpine Linux detection."""
        alpine_release = self.mount_root / "etc/alpine-release"
        if not alpine_release.exists():
            return False

        try:
            version = alpine_release.read_text().strip()
            info["distro"] = "alpine"
            info["product"] = f"Alpine Linux {version}"

            parts = version.split(".")
            info["major"] = int(parts[0])
            info["minor"] = int(parts[1]) if len(parts) > 1 else 0

            return True

        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort distro-detection file parse; try the next
            # detection method instead of aborting on a malformed/unreadable file
            return False

    def _try_slackware_version(self, info: dict[str, Any]) -> bool:
        """Try Slackware detection."""
        slackware_version = self.mount_root / "etc/slackware-version"
        if not slackware_version.exists():
            return False

        try:
            content = slackware_version.read_text().strip()
            info["distro"] = "slackware"
            info["product"] = content

            version_match = re.search(r"(\d+)\.(\d+)", content)
            if version_match:
                info["major"] = int(version_match.group(1))
                info["minor"] = int(version_match.group(2))

            return True

        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort distro-detection file parse; try the next
            # detection method instead of aborting on a malformed/unreadable file
            return False

    def _try_issue_fallback(self, info: dict[str, Any]) -> None:
        """Fallback to /etc/issue."""
        issue = self.mount_root / "etc/issue"
        if not issue.exists():
            return

        try:
            content = issue.read_text().strip()
            # Remove escape sequences
            content = content.replace("\\n", "").replace("\\l", "").strip()

            if content and content != "Linux":
                info["product"] = content.split("\n")[0]

        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort distro-detection file parse; try the next
            # detection method instead of aborting on a malformed/unreadable file
            pass
