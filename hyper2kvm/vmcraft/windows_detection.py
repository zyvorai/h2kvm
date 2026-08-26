# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/vmcraft/windows_detection.py
"""
Windows OS detection and identification.

Provides comprehensive Windows version detection using:
- Registry hive parsing (SOFTWARE hive)
- Filesystem structure analysis
- Build number mapping

Supports all Windows versions:
- Windows 12, 11, 10, 8.1, 8, 7, Vista, XP, 2000, NT 4.0
- Windows Server 2025, 2022, 2019, 2016, 2012 R2, 2012, 2008 R2, 2008, 2003

Detection methods:
- ProductName from registry (most reliable)
- Build number analysis (Win10/11 split at build 22000)
- Major/minor version numbers
- Filesystem indicators
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from ._utils import run_sudo

logger = logging.getLogger(__name__)


class WindowsDetector:
    """
    Windows OS detector.

    Detects Windows version from mounted Windows filesystem.
    """

    def __init__(self, log: logging.Logger, mount_root: Path):
        """
        Initialize Windows detector.

        Args:
            log: Logger instance
            mount_root: Root directory where guest filesystem is mounted
        """
        self.logger = log
        self.mount_root = mount_root

    def path_exists_ci(self, path: str) -> bool:
        """
        Check if path exists (case-insensitive).

        Needed for Windows filesystems which may have mixed case.

        Args:
            path: Path to check (relative to mount root)

        Returns:
            True if path exists (case-insensitive match)
        """
        # Try exact path first
        full_path = self.mount_root / path
        if full_path.exists():
            return True

        # Try case-insensitive search for Windows filesystems
        parts = Path(path).parts
        current = self.mount_root

        for part in parts:
            if not current.is_dir():
                return False

            # Look for matching entry (case-insensitive)
            found = False
            try:
                for entry in current.iterdir():
                    if entry.name.lower() == part.lower():
                        current = entry
                        found = True
                        break
            except (PermissionError, OSError):
                return False

            if not found:
                return False

        return current.exists()

    def gather_windows_info(self, root: str) -> dict[str, Any]:  # pylint: disable=unused-argument  # shared detector interface
        """
        Gather Windows OS information from registry and filesystem.

        Returns comprehensive Windows version information including:
        - type: "windows"
        - distro: "windows"
        - product: Friendly OS name (e.g., "Windows 11 Pro", "Windows Server 2019")
        - os_name: Detected OS name (e.g., "Windows 11", "Windows 10")
        - major/minor: Version numbers
        - build: Build number (critical for Win10/11 detection)
        - release_id: Windows 10 version (e.g., "21H2")
        - display_version: Windows 11 version (e.g., "22H2")
        - edition: Edition type (Pro, Enterprise, Home, etc.)
        - arch: Architecture (x86_64, i686, etc.)

        Args:
            root: Root device path

        Returns:
            Dict with Windows version information
        """
        info: dict[str, Any] = {
            "type": "windows",
            "distro": "windows",
            "product": "Windows",
            "major": 0,
            "minor": 0,
            "arch": "unknown",
        }

        # Detect architecture from System32 presence
        if self.path_exists_ci("Windows/SysWOW64"):
            info["arch"] = "x86_64"  # 64-bit Windows has SysWOW64
        elif self.path_exists_ci("Windows/System32"):
            info["arch"] = "i686"  # 32-bit Windows

        # Try to parse SOFTWARE registry hive for version info
        software_hive = None
        for try_path in ["Windows/System32/config/SOFTWARE", "windows/system32/config/software"]:
            test_path = self.mount_root / try_path
            if test_path.exists():
                software_hive = test_path
                break

        if software_hive:
            version_info = self._parse_windows_version(software_hive)
            info.update(version_info)

            # Use os_name as the primary product if available
            if version_info.get("os_name"):
                # If we have edition info, append it to product
                if version_info.get("edition"):
                    edition_map = {
                        "Professional": "Pro",
                        "Enterprise": "Enterprise",
                        "Core": "Home",
                        "Education": "Education",
                        "ServerStandard": "Standard",
                        "ServerDatacenter": "Datacenter",
                    }
                    edition = edition_map.get(version_info["edition"], version_info["edition"])
                    info["product"] = f"{version_info['os_name']} {edition}"
                elif version_info.get("product"):
                    # Use registry ProductName as-is (already has edition)
                    pass
                else:
                    info["product"] = version_info["os_name"]

        return info

    def _parse_windows_version(  # pylint: disable=too-many-branches,too-many-statements  # reads and normalizes many independent registry fields
        self, software_hive: Path
    ) -> dict[str, Any]:
        r"""
        Parse Windows version from SOFTWARE registry hive using hivexget.

        Supports comprehensive detection for:
        - Windows 11 (builds 22000+)
        - Windows 10 (versions 1507-22H2, builds 10240-19045)
        - Windows 8.1 (major=6, minor=3)
        - Windows 8 (major=6, minor=2)
        - Windows 7 (major=6, minor=1)
        - Windows Vista (major=6, minor=0)
        - Windows XP (major=5)
        - Windows Server 2022, 2019, 2016, 2012 R2, 2012, 2008 R2, 2008, 2003

        Registry key: Microsoft\Windows NT\CurrentVersion
        Values read:
        - ProductName (e.g., "Windows 11 Pro", "Windows Server 2019")
        - CurrentMajorVersionNumber / CurrentMinorVersionNumber (DWORD, Windows 10+)
        - CurrentBuild or CurrentBuildNumber (string)
        - ReleaseId (e.g., "2009", "21H2" for Windows 10 versions)
        - DisplayVersion (e.g., "22H2", "23H2" for Windows 11)
        - EditionID (e.g., "Professional", "Enterprise", "ServerStandard")

        Args:
            software_hive: Path to SOFTWARE registry hive file

        Returns:
            Dict with version information
        """
        version_info = {}

        def _read_registry_value(value_name: str) -> str | None:
            """Helper to read a registry value."""
            try:
                result = run_sudo(
                    self.logger,
                    ["hivexget", str(software_hive), r"Microsoft\Windows NT\CurrentVersion", value_name],
                    check=True,
                    capture=True,
                )
                val = result.stdout.strip().strip('"')
                return val if val else None
            except (subprocess.CalledProcessError, FileNotFoundError):
                return None

        try:
            # Read ProductName (most reliable identifier)
            product_name = _read_registry_value("ProductName")
            if product_name:
                version_info["product"] = product_name
                version_info["product_lower"] = product_name.lower()

            # Read version numbers (Windows 10+ uses DWORD values)
            major_str = _read_registry_value("CurrentMajorVersionNumber")
            if major_str:
                try:
                    # May be hex (0x0000000a) or decimal
                    if major_str.startswith("0x"):
                        version_info["major"] = int(major_str, 16)
                    elif major_str.isdigit():
                        version_info["major"] = int(major_str)
                except ValueError:
                    pass

            minor_str = _read_registry_value("CurrentMinorVersionNumber")
            if minor_str:
                try:
                    if minor_str.startswith("0x"):
                        version_info["minor"] = int(minor_str, 16)
                    elif minor_str.isdigit():
                        version_info["minor"] = int(minor_str)
                except ValueError:
                    pass

            # Read build number (critical for Windows 10/11 detection)
            for build_key in ("CurrentBuild", "CurrentBuildNumber"):
                build_str = _read_registry_value(build_key)
                if build_str:
                    # Extract numeric build (e.g., "22631" from "22631.2861")
                    match = re.search(r"(\d+)", build_str)
                    if match:
                        version_info["build"] = int(match.group(1))
                        break

            # Read release identifiers (Windows 10/11)
            release_id = _read_registry_value("ReleaseId")
            if release_id:
                version_info["release_id"] = release_id

            display_version = _read_registry_value("DisplayVersion")
            if display_version:
                version_info["display_version"] = display_version

            # Read edition (Pro, Enterprise, Home, etc.)
            edition_id = _read_registry_value("EditionID")
            if edition_id:
                version_info["edition"] = edition_id

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort registry parse; falls back to filesystem detection
            self.logger.debug(f"Failed to parse Windows version from registry: {e}")

        # Map to friendly OS name using product, build, and major/minor
        version_info["os_name"] = self._detect_windows_os_name(version_info)

        # Fallback: detect version from filesystem structure
        if "product" not in version_info:
            if self.path_exists_ci("Program Files/Windows NT"):
                version_info["product"] = "Windows NT-based"
            elif self.path_exists_ci("Program Files"):
                version_info["product"] = "Windows"

        return version_info

    def _detect_windows_os_name(  # pylint: disable=too-many-return-statements,too-many-branches  # priority ladder over many Windows/Server versions
        self, version_info: dict[str, Any]
    ) -> str:
        """
        Detect friendly Windows OS name from version information.

        Detection priority:
        1. ProductName string matching (most reliable)
        2. Build number for Windows 10/11 split (>=22000 = Win11)
        3. Major/minor version for legacy Windows (7, Vista, XP)

        Reference:
        - Windows 11: build >= 22000
        - Windows 10: build >= 10240 and < 22000
        - Windows 8.1: major=6, minor=3
        - Windows 8: major=6, minor=2
        - Windows 7: major=6, minor=1
        - Windows Vista: major=6, minor=0
        - Windows XP: major=5, minor=1 or 2
        - Windows 2000: major=5, minor=0
        - Windows NT 4.0: major=4

        Args:
            version_info: Dict with version fields (product, build, major, minor)

        Returns:
            Friendly OS name string
        """
        product = version_info.get("product_lower", "").lower()
        build = version_info.get("build", 0)
        major = version_info.get("major", 0)
        minor = version_info.get("minor", 0)

        # Server editions (check first as they're more specific)
        if "server 2025" in product:
            return "Windows Server 2025"
        if "server 2022" in product:
            return "Windows Server 2022"
        if "server 2019" in product:
            return "Windows Server 2019"
        if "server 2016" in product:
            return "Windows Server 2016"
        if "server 2012 r2" in product:
            return "Windows Server 2012 R2"
        if "server 2012" in product:
            return "Windows Server 2012"
        if "server 2008 r2" in product:
            return "Windows Server 2008 R2"
        if "server 2008" in product:
            return "Windows Server 2008"
        if "server 2003" in product:
            return "Windows Server 2003"

        # Client editions
        if "windows 12" in product:
            return "Windows 12"
        if "windows 11" in product:
            return "Windows 11"
        if "windows 10" in product:
            # Distinguish Win11 from Win10 by build
            if build >= 22000:
                return "Windows 11"
            return "Windows 10"
        if "windows 8.1" in product or "windows blue" in product:
            return "Windows 8.1"
        if "windows 8" in product:
            return "Windows 8"
        if "windows 7" in product:
            return "Windows 7"
        if "vista" in product:
            return "Windows Vista"
        if "xp" in product or "windows xp" in product:
            return "Windows XP"
        if "2000" in product or "windows 2000" in product:
            return "Windows 2000"
        if "nt" in product and "4.0" in product:
            return "Windows NT 4.0"

        # Build number detection (no ProductName match)
        if build >= 26000:
            return "Windows 12"
        if build >= 22000:
            return "Windows 11"
        if build >= 10240:
            return "Windows 10"
        if build >= 9600:
            return "Windows 8.1"
        if build >= 9200:
            return "Windows 8"
        if build >= 7600:
            return "Windows 7"
        if build >= 6000:
            return "Windows Vista"

        # Major/minor version detection (legacy)
        if major == 10 and minor == 0:
            # Windows 10/11 (check build)
            if build >= 22000:
                return "Windows 11"
            if build >= 10240:
                return "Windows 10"
            return "Windows 10/11"
        if major == 6 and minor == 3:
            return "Windows 8.1"
        if major == 6 and minor == 2:
            return "Windows 8"
        if major == 6 and minor == 1:
            return "Windows 7"
        if major == 6 and minor == 0:
            return "Windows Vista"
        if major == 5 and minor == 2:
            return "Windows XP 64-bit / Server 2003"
        if major == 5 and minor == 1:
            return "Windows XP"
        if major == 5 and minor == 0:
            return "Windows 2000"
        if major == 4:
            return "Windows NT 4.0"

        # Unknown Windows version
        return "Windows"
