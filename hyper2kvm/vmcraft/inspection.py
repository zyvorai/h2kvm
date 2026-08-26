# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/vmcraft/inspection.py
"""
OS inspection and detection orchestration.

Coordinates OS detection across Linux and Windows systems:
- Discovers root filesystems
- Mounts and inspects partitions
- Delegates to OS-specific detectors
- Caches inspection results
- Provides comprehensive OS inspection API
"""

from __future__ import annotations

import contextlib
import logging
import re
from typing import TYPE_CHECKING, Any

from hyper2kvm.core.structured_log import log_event

from ._utils import DeviceError, run_sudo

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class OSInspector:
    """
    OS inspection orchestrator.

    Manages OS detection across multiple filesystems and OS types.
    Provides comprehensive OS inspection capabilities.
    """

    def __init__(
        self,
        inspector_logger: logging.Logger,
        mount_root: Path,
        linux_detector: Any,  # LinuxDetector
        windows_detector: Any,  # WindowsDetector
    ):
        """
        Initialize OS inspector.

        Args:
            inspector_logger: Logger instance
            mount_root: Root directory for mounting filesystems
            linux_detector: Linux detection module
            windows_detector: Windows detection module
        """
        self.logger = inspector_logger
        self.mount_root = mount_root
        self.linux_detector = linux_detector
        self.windows_detector = windows_detector
        self._inspect_cache: dict[str, Any] = {}

    def inspect_partitions(self, partitions: list[str]) -> list[str]:
        """
        Inspect partitions to find root filesystems.

        Args:
            partitions: List of partition device paths

        Returns:
            List of root device paths (partitions containing OS roots)
        """
        candidates = []

        for part in partitions:
            # Try to mount and check for OS indicators
            try:
                self._try_mount_for_inspection(part)

                try:
                    # Check for OS indicators
                    if self._looks_like_root():
                        candidates.append(part)
                        # Cache this as a valid root
                        os_info = self._gather_os_info(part)
                        self._inspect_cache[part] = os_info

                        # Log detected OS information
                        self._log_os_detection(part, os_info)
                finally:
                    # Unmount after inspection even if _gather_os_info raises
                    self._unmount_inspection()

            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort per-partition inspection must not abort the whole scan
                self.logger.debug(f"Failed to inspect {part}: {e}")
                continue

        return candidates

    def _try_mount_for_inspection(self, device: str) -> None:
        """
        Try to mount device for inspection.

        Args:
            device: Device path to mount
        """
        try:
            # Try read-only mount (log failures as DEBUG since we'll retry with different options)
            run_sudo(
                self.logger,
                ["mount", "-o", "ro", device, str(self.mount_root)],
                check=True,
                capture=True,
                failure_log_level=logging.DEBUG,
            )
        except DeviceError:
            # Try with noload option for dirty filesystems
            run_sudo(
                self.logger,
                ["mount", "-o", "ro,noload", device, str(self.mount_root)],
                check=True,
                capture=True,
                failure_log_level=logging.DEBUG,
            )

    def _unmount_inspection(self) -> None:
        """Unmount inspection mount."""
        with contextlib.suppress(Exception):
            run_sudo(self.logger, ["umount", str(self.mount_root)], check=False, capture=True)

    def _looks_like_root(self) -> bool:
        """
        Check if mounted filesystem looks like a root filesystem (Linux or Windows).

        Returns:
            True if filesystem appears to be an OS root
        """
        # Check for Linux root indicators
        linux_indicators = [
            "etc/os-release",
            "etc/fstab",
            "bin/sh",
            "usr/bin",
            "var/lib",
        ]

        linux_hits = sum(1 for ind in linux_indicators if (self.mount_root / ind).exists())
        if linux_hits >= 2:
            return True

        # Check for Windows root indicators (case-insensitive)
        windows_indicators = [
            "Windows/System32",
            "Program Files",
            "Windows/explorer.exe",
            "Windows/regedit.exe",
            "Windows/System32/config/SOFTWARE",
        ]

        windows_hits = sum(1 for ind in windows_indicators if self.windows_detector.path_exists_ci(ind))
        return windows_hits >= 2

    def _gather_os_info(self, root: str) -> dict[str, Any]:
        """
        Gather comprehensive OS information from mounted root (Linux or Windows).

        Supports:
        - All major Linux distributions (Red Hat, Fedora, CentOS, Rocky, Alma, SUSE,
          Debian, Ubuntu, Arch, Gentoo, Alpine, etc.)
        - All Windows versions (11, 10, 8.1, 8, 7, Vista, XP, 2000, NT, Servers)

        Args:
            root: Root device path

        Returns:
            Dict with OS information
        """
        info: dict[str, Any] = {
            "type": "unknown",
            "distro": "unknown",
            "product": "Unknown",
            "major": 0,
            "minor": 0,
            "arch": "unknown",
            "variant": None,  # Server, Desktop, Workstation, etc.
            "codename": None,  # Ubuntu: focal, jammy; Windows: 21H2, 22H2
        }

        # Try Windows detection first
        if self.windows_detector.path_exists_ci("Windows/System32"):
            return self.windows_detector.gather_windows_info(root)

        # Linux detection - multiple methods with fallbacks
        return self.linux_detector.gather_linux_info(root, info)

    def _log_os_detection(self, root: str, os_info: dict[str, Any]) -> None:
        """
        Log comprehensive OS detection results.

        Args:
            root: Root device path
            os_info: Dict with OS information
        """
        log_event(
            "os_detected",
            root=root,
            os_type=os_info.get("type", "unknown"),
            distro=os_info.get("distro", "unknown"),
            product=os_info.get("product", "Unknown"),
        )
        os_type = os_info.get("type", "unknown")

        if os_type == "linux":
            # Linux detection logging
            self.logger.info(f"Detected Linux OS on {root}")
            self.logger.info(f"   Product: {os_info.get('product', 'Unknown')}")
            self.logger.info(f"   Distribution: {os_info.get('distro', 'unknown')}")
            if os_info.get("codename"):
                self.logger.info(f"   Codename: {os_info['codename']}")
            if os_info.get("variant"):
                self.logger.info(f"   Variant: {os_info['variant']}")
            if os_info.get("major") or os_info.get("minor"):
                version_str = f"{os_info.get('major', '')}.{os_info.get('minor', '')}"
                self.logger.info(f"   Version: {version_str}")
            self.logger.info(f"   Architecture: {os_info.get('arch', 'unknown')}")

        elif os_type == "windows":
            # Windows detection logging
            self.logger.info(f"Detected Windows OS on {root}")
            self.logger.info(f"   Product: {os_info.get('product', 'Windows')}")
            if os_info.get("os_name"):
                self.logger.info(f"   OS Name: {os_info['os_name']}")
            if os_info.get("edition"):
                self.logger.info(f"   Edition: {os_info['edition']}")
            if os_info.get("build"):
                self.logger.info(f"   Build: {os_info['build']}")
            if os_info.get("display_version"):
                self.logger.info(f"   Display Version: {os_info['display_version']}")
            elif os_info.get("release_id"):
                self.logger.info(f"   Release ID: {os_info['release_id']}")
            if os_info.get("major") or os_info.get("minor"):
                self.logger.info(f"   Version: {os_info.get('major', 0)}.{os_info.get('minor', 0)}")
            self.logger.info(f"   Architecture: {os_info.get('arch', 'unknown')}")

        else:
            # Unknown OS
            self.logger.info(f"Detected unknown OS on {root}")
            self.logger.info(f"   Product: {os_info.get('product', 'Unknown')}")

    def get_cached_info(self, root: str) -> dict[str, Any]:
        """
        Get cached OS information for root.

        Args:
            root: Root device path

        Returns:
            Cached OS info dict
        """
        return self._inspect_cache.get(root, {})

    def has_cached_info(self, root: str) -> bool:
        """Check if OS info is cached for root."""
        return root in self._inspect_cache

    # Container Detection

    def detect_containers(self) -> dict[str, Any]:
        """
        Detect container runtime installations.

        Checks for:
        - Docker (/.dockerenv, /var/lib/docker)
        - Podman (/run/podman, containers/storage)
        - LXC (/var/lib/lxc)
        - systemd-nspawn (/var/lib/machines)

        Returns:
            Dict with container detection results:
            {
                "is_container": bool,
                "container_type": str | None,
                "indicators": {
                    "docker": bool,
                    "podman": bool,
                    "lxc": bool,
                    "systemd_nspawn": bool
                }
            }
        """
        indicators: dict[str, bool] = {
            "docker": False,
            "podman": False,
            "lxc": False,
            "systemd_nspawn": False,
        }

        # Check for Docker
        docker_indicators = [
            ".dockerenv",  # In-container indicator
            "var/lib/docker",  # Docker root directory
            "usr/bin/docker",  # Docker binary
            "etc/docker",  # Docker config
        ]
        docker_hits = sum(1 for ind in docker_indicators if (self.mount_root / ind).exists())
        if docker_hits >= 1:
            indicators["docker"] = True
            self.logger.info("Detected Docker container runtime")

        # Check for Podman
        podman_indicators = [
            "run/podman",  # Podman runtime directory
            "var/lib/containers/storage",  # Podman storage
            "usr/bin/podman",  # Podman binary
        ]
        podman_hits = sum(1 for ind in podman_indicators if (self.mount_root / ind).exists())
        if podman_hits >= 1:
            indicators["podman"] = True
            self.logger.info("Detected Podman container runtime")

        # Check for LXC
        lxc_indicators = [
            "var/lib/lxc",  # LXC container directory
            "usr/bin/lxc-start",  # LXC binary
            "etc/lxc",  # LXC config
        ]
        lxc_hits = sum(1 for ind in lxc_indicators if (self.mount_root / ind).exists())
        if lxc_hits >= 1:
            indicators["lxc"] = True
            self.logger.info("Detected LXC container runtime")

        # Check for systemd-nspawn
        nspawn_indicators = [
            "var/lib/machines",  # systemd-nspawn machine directory
            "usr/bin/systemd-nspawn",  # systemd-nspawn binary
        ]
        nspawn_hits = sum(1 for ind in nspawn_indicators if (self.mount_root / ind).exists())
        if nspawn_hits >= 1:
            indicators["systemd_nspawn"] = True
            self.logger.info("Detected systemd-nspawn container runtime")

        # Determine if any containers were found and which type
        is_container = any(indicators.values())
        container_type = None
        if indicators["docker"]:
            container_type = "docker"
        elif indicators["podman"]:
            container_type = "podman"
        elif indicators["lxc"]:
            container_type = "lxc"
        elif indicators["systemd_nspawn"]:
            container_type = "systemd-nspawn"

        return {
            "is_container": is_container,
            "container_type": container_type,
            "indicators": indicators,
        }

    def is_inside_container(self) -> dict[str, Any]:
        """
        Check if the inspected OS is running inside a container.

        Detects container environment markers:
        - Docker: /.dockerenv file
        - Podman: /.containerenv or /run/.containerenv
        - LXC: /proc/1/environ contains container=lxc
        - systemd-nspawn: /run/systemd/container

        Returns:
            Dict with container detection and type
        """
        result: dict[str, Any] = {
            "is_container": False,
            "container_type": None,
            "indicators": [],
        }

        # Docker container check
        if (self.mount_root / ".dockerenv").exists():
            result["is_container"] = True
            result["container_type"] = "docker"
            result["indicators"].append("/.dockerenv")
            self.logger.info("System is running inside a Docker container")
            return result

        # Podman container check
        if (self.mount_root / ".containerenv").exists() or (self.mount_root / "run/.containerenv").exists():
            result["is_container"] = True
            result["container_type"] = "podman"
            result["indicators"].append("/.containerenv or /run/.containerenv")
            self.logger.info("System is running inside a Podman container")
            return result

        # systemd-nspawn check
        container_file = self.mount_root / "run/systemd/container"
        if container_file.exists():
            try:
                container_type = container_file.read_text().strip()
                result["is_container"] = True
                result["container_type"] = container_type
                result["indicators"].append(f"/run/systemd/container={container_type}")
                self.logger.info(f"System is running inside a {container_type} container")
                return result
            except OSError:
                pass

        # LXC check via cgroup
        cgroup_file = self.mount_root / "proc/1/cgroup"
        if cgroup_file.exists():
            try:
                content = cgroup_file.read_text()
                if "lxc" in content.lower():
                    result["is_container"] = True
                    result["container_type"] = "lxc"
                    result["indicators"].append("/proc/1/cgroup contains lxc")
                    self.logger.info("System is running inside an LXC container")
                    return result
            except OSError:
                pass

        return result

    # Boot Loader Detection

    def detect_bootloader(  # pylint: disable=too-many-branches  # checks many independent bootloader/firmware indicators
        self,
    ) -> dict[str, Any]:
        """
        Detect bootloader configuration.

        Checks for:
        - GRUB2 (/boot/grub2, /boot/grub)
        - systemd-boot (/boot/loader, /boot/efi/loader)
        - UEFI (/sys/firmware/efi, /boot/efi)
        - LILO (legacy, /etc/lilo.conf)

        Returns:
            Dict with bootloader detection results
        """
        result: dict[str, Any] = {
            "bootloader": None,
            "bootloader_config": None,
            "uefi": False,
            "bios": False,
            "boot_partition": None,
        }

        # Check for UEFI
        uefi_indicators = [
            "sys/firmware/efi",
            "boot/efi/EFI",
            "boot/efi",
        ]
        for indicator in uefi_indicators:
            if (self.mount_root / indicator).exists():
                result["uefi"] = True
                result["bios"] = False
                self.logger.info("Detected UEFI boot mode")
                break

        if not result["uefi"]:
            result["bios"] = True
            self.logger.info("Detected BIOS boot mode")

        # Check for GRUB2
        grub2_paths = [
            "boot/grub2/grub.cfg",
            "boot/grub/grub.cfg",
            "boot/efi/EFI/fedora/grub.cfg",
            "boot/efi/EFI/centos/grub.cfg",
            "boot/efi/EFI/redhat/grub.cfg",
            "boot/efi/EFI/ubuntu/grub.cfg",
            "boot/efi/EFI/debian/grub.cfg",
        ]
        for grub_path in grub2_paths:
            full_path = self.mount_root / grub_path
            if full_path.exists():
                result["bootloader"] = "grub2"
                result["bootloader_config"] = f"/{grub_path}"
                self.logger.info(f"Detected GRUB2 bootloader: {grub_path}")
                break

        # Check for systemd-boot
        if not result["bootloader"]:
            systemd_boot_paths = [
                "boot/loader/loader.conf",
                "boot/efi/loader/loader.conf",
                "efi/loader/loader.conf",
            ]
            for sd_path in systemd_boot_paths:
                full_path = self.mount_root / sd_path
                if full_path.exists():
                    result["bootloader"] = "systemd-boot"
                    result["bootloader_config"] = f"/{sd_path}"
                    self.logger.info(f"Detected systemd-boot: {sd_path}")
                    break

        # Check for LILO (legacy)
        if not result["bootloader"]:
            lilo_conf = self.mount_root / "etc/lilo.conf"
            if lilo_conf.exists():
                result["bootloader"] = "lilo"
                result["bootloader_config"] = "/etc/lilo.conf"
                self.logger.info("Detected LILO bootloader (legacy)")

        # Try to identify boot partition
        if result["uefi"]:
            if (self.mount_root / "boot/efi").exists():
                result["boot_partition"] = "/boot/efi"
        elif (self.mount_root / "boot/grub2").exists() or (self.mount_root / "boot/grub").exists():
            result["boot_partition"] = "/boot"

        if not result["bootloader"]:
            result["bootloader"] = "unknown"
            self.logger.warning("Could not detect bootloader")

        return result

    def get_bootloader_entries(self) -> list[dict[str, Any]]:
        """
        Get boot loader menu entries.

        Parses bootloader configuration to extract boot menu entries.

        Returns:
            List of boot entries with title, kernel, initrd info
        """
        bootloader_info = self.detect_bootloader()
        bootloader = bootloader_info.get("bootloader")
        config_path = bootloader_info.get("bootloader_config")

        entries: list[dict[str, Any]] = []

        if not config_path:
            return entries

        try:
            if bootloader == "grub2":
                entries = self._parse_grub2_entries(config_path)
            elif bootloader == "systemd-boot":
                entries = self._parse_systemd_boot_entries(config_path)
            elif bootloader == "lilo":
                entries = self._parse_lilo_entries(config_path)
        except OSError as e:
            self.logger.warning(f"Failed to parse bootloader entries: {e}")

        return entries

    def _parse_grub2_entries(  # pylint: disable=too-many-branches,too-many-nested-blocks  # line-by-line GRUB2 config parsing with several directive cases
        self, config_path: str
    ) -> list[dict[str, Any]]:
        """Parse GRUB2 menu entries."""
        entries = []
        config_file = self.mount_root / config_path.lstrip("/")

        if not config_file.exists():
            return entries

        try:
            content = config_file.read_text()
            current_entry = None

            for line in content.splitlines():
                line = line.strip()

                if line.startswith("menuentry"):
                    # Extract title from menuentry 'Title' ...
                    match = re.search(r"menuentry\s+['\"]([^'\"]+)['\"]", line)
                    if match:
                        if current_entry:
                            entries.append(current_entry)
                        current_entry = {
                            "title": match.group(1),
                            "kernel": None,
                            "initrd": None,
                        }

                elif current_entry:
                    if "linux" in line or "linux16" in line or "linuxefi" in line:
                        # Extract kernel path
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part in ("linux", "linux16", "linuxefi") and i + 1 < len(parts):
                                current_entry["kernel"] = parts[i + 1]
                                break

                    elif "initrd" in line or "initrd16" in line or "initrdefi" in line:
                        # Extract initrd path
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part in ("initrd", "initrd16", "initrdefi") and i + 1 < len(parts):
                                current_entry["initrd"] = parts[i + 1]
                                break

            if current_entry:
                entries.append(current_entry)

        except OSError as e:
            self.logger.warning(f"Error parsing GRUB2 config: {e}")

        return entries

    def _parse_systemd_boot_entries(self, config_path: str) -> list[dict[str, Any]]:
        """Parse systemd-boot entries."""
        entries = []
        loader_dir = (self.mount_root / config_path.lstrip("/")).parent / "entries"

        if not loader_dir.exists():
            return entries

        try:
            for entry_file in loader_dir.glob("*.conf"):
                entry = {
                    "title": entry_file.stem,
                    "kernel": None,
                    "initrd": None,
                }

                content = entry_file.read_text()
                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith("title"):
                        entry["title"] = (
                            line.split(None, 1)[1] if len(line.split(None, 1)) > 1 else entry_file.stem
                        )
                    elif line.startswith("linux"):
                        entry["kernel"] = line.split(None, 1)[1] if len(line.split(None, 1)) > 1 else None
                    elif line.startswith("initrd"):
                        entry["initrd"] = line.split(None, 1)[1] if len(line.split(None, 1)) > 1 else None

                entries.append(entry)

        except OSError as e:
            self.logger.warning(f"Error parsing systemd-boot entries: {e}")

        return entries

    def _parse_lilo_entries(self, config_path: str) -> list[dict[str, Any]]:
        """Parse LILO entries."""
        entries = []
        config_file = self.mount_root / config_path.lstrip("/")

        if not config_file.exists():
            return entries

        try:
            content = config_file.read_text()
            current_entry = None

            for line in content.splitlines():
                line = line.strip()

                if line.startswith(("image=", "other=")):
                    if current_entry:
                        entries.append(current_entry)
                    current_entry = {
                        "title": None,
                        "kernel": line.split("=", 1)[1] if "=" in line else None,
                        "initrd": None,
                    }

                elif current_entry:
                    if line.startswith("label="):
                        current_entry["title"] = line.split("=", 1)[1] if "=" in line else None
                    elif line.startswith("initrd="):
                        current_entry["initrd"] = line.split("=", 1)[1] if "=" in line else None

            if current_entry:
                entries.append(current_entry)

        except OSError as e:
            self.logger.warning(f"Error parsing LILO config: {e}")

        return entries
