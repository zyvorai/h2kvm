# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/security.py
"""
Security audit operations for guest filesystems.

Provides security analysis and auditing:
- Permission auditing
- SUID/SGID file detection
- World-writable file detection
- Security policy analysis
"""

from __future__ import annotations

import logging
import os
import re
import stat
from pathlib import Path
from typing import Any

from h2kvm.core.structured_log import log_event

from ._utils import DeviceError, run_sudo

logger = logging.getLogger(__name__)


class SecurityAuditor:
    """
    Security auditor for guest filesystems.

    Analyzes filesystem for security issues.
    """

    def __init__(self, security_logger: logging.Logger, mount_root: Path):
        """
        Initialize security auditor.

        Args:
            security_logger: Logger instance
            mount_root: Root directory where guest filesystem is mounted
        """
        self.logger = security_logger
        self.mount_root = mount_root

    def audit_permissions(self, path: str = "/") -> dict[str, Any]:
        """
        Audit file permissions for security issues.

        Args:
            path: Starting path for audit

        Returns:
            Dict with audit results including SUID, SGID, and world-writable files
        """
        audit_path = self.mount_root / path.lstrip("/")

        result: dict[str, Any] = {
            "suid_files": [],
            "sgid_files": [],
            "world_writable": [],
            "total_checked": 0,
        }

        try:
            for root, _dirs, files in os.walk(audit_path):
                for name in files:
                    filepath = Path(root) / name
                    try:
                        st = filepath.lstat()
                        result["total_checked"] += 1

                        # Check for SUID
                        if st.st_mode & stat.S_ISUID:
                            result["suid_files"].append(str(filepath.relative_to(self.mount_root)))

                        # Check for SGID
                        if st.st_mode & stat.S_ISGID:
                            result["sgid_files"].append(str(filepath.relative_to(self.mount_root)))

                        # Check for world-writable
                        if st.st_mode & stat.S_IWOTH:
                            result["world_writable"].append(str(filepath.relative_to(self.mount_root)))

                    except (PermissionError, OSError):
                        pass

            self.logger.info(f"Security audit complete: checked {result['total_checked']} files")
            log_event(
                "security_audit_complete",
                total_checked=result["total_checked"],
                suid_count=len(result["suid_files"]),
                sgid_count=len(result["sgid_files"]),
                world_writable_count=len(result["world_writable"]),
            )

        # pylint: disable-next=broad-exception-caught  # best-effort fs walk; unpredictable guest state must not abort
        except Exception as e:
            self.logger.exception(f"Audit failed: {e}")

        return result

    # SELinux and AppArmor Detection

    def detect_selinux(self) -> dict[str, Any]:
        """
        Detect SELinux configuration and status.

        Checks:
        - SELinux config file (/etc/selinux/config)
        - Current enforcement mode
        - SELinux policy type

        Returns:
            Dict with SELinux information
        """
        result: dict[str, Any] = {
            "installed": False,
            "enabled": False,
            "enforcing": False,
            "mode": None,  # enforcing, permissive, disabled
            "policy": None,  # targeted, mls, minimum
            "config_file": "/etc/selinux/config",
        }

        config_path = self.mount_root / "etc/selinux/config"

        if not config_path.exists():
            self.logger.debug("SELinux config not found")
            return result

        result["installed"] = True

        try:
            content = config_path.read_text()

            for line in content.splitlines():
                line = line.strip()

                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue

                # Parse SELINUX=enforcing|permissive|disabled
                if line.startswith("SELINUX="):
                    mode = line.split("=", 1)[1].strip()
                    result["mode"] = mode
                    if mode == "enforcing":
                        result["enabled"] = True
                        result["enforcing"] = True
                    elif mode == "permissive":
                        result["enabled"] = True
                        result["enforcing"] = False
                    elif mode == "disabled":
                        result["enabled"] = False
                        result["enforcing"] = False

                # Parse SELINUXTYPE=targeted|mls|minimum
                elif line.startswith("SELINUXTYPE="):
                    policy = line.split("=", 1)[1].strip()
                    result["policy"] = policy

            if result["enabled"]:
                self.logger.info(f"SELinux detected: mode={result['mode']}, policy={result['policy']}")
                log_event("selinux_detected", mode=result["mode"], policy=result["policy"])
            else:
                self.logger.info("SELinux installed but disabled")
                log_event("selinux_detected", mode="disabled")

        except OSError as e:
            self.logger.warning(f"Error parsing SELinux config: {e}")

        return result

    def detect_apparmor(self) -> dict[str, Any]:
        """
        Detect AppArmor configuration and status.

        Checks:
        - AppArmor kernel module (/sys/kernel/security/apparmor)
        - AppArmor profiles (/etc/apparmor.d)
        - Profile enforcement status

        Returns:
            Dict with AppArmor information
        """
        result: dict[str, Any] = {
            "installed": False,
            "enabled": False,
            "profiles_dir": "/etc/apparmor.d",
            "profiles_count": 0,
            "profiles": [],
        }

        # Check for AppArmor sysfs interface
        apparmor_sys = self.mount_root / "sys/kernel/security/apparmor"
        profiles_dir = self.mount_root / "etc/apparmor.d"

        # Check if AppArmor is present
        if apparmor_sys.exists() or profiles_dir.exists():
            result["installed"] = True

        # Check if enabled via sysfs
        if apparmor_sys.exists():
            result["enabled"] = True
            self.logger.info("AppArmor detected (enabled)")

        # Count profiles
        if profiles_dir.exists():
            try:
                profiles = [
                    f.name for f in profiles_dir.iterdir() if f.is_file() and not f.name.startswith(".")
                ]
                result["profiles_count"] = len(profiles)
                result["profiles"] = profiles[:10]  # Limit to first 10 for brevity

                if result["profiles_count"] > 0:
                    self.logger.info(f"AppArmor: {result['profiles_count']} profiles found")

            except OSError as e:
                self.logger.warning(f"Error reading AppArmor profiles: {e}")

        if not result["installed"]:
            self.logger.debug("AppArmor not detected")

        return result

    def get_security_modules(self) -> dict[str, Any]:
        """
        Get comprehensive security module information.

        Combines SELinux and AppArmor detection.

        Returns:
            Dict with security module status
        """
        result = {
            "selinux": self.detect_selinux(),
            "apparmor": self.detect_apparmor(),
        }

        # Determine active LSM (Linux Security Module)
        if result["selinux"]["enabled"]:
            result["active_lsm"] = "selinux"
        elif result["apparmor"]["enabled"]:
            result["active_lsm"] = "apparmor"
        else:
            result["active_lsm"] = None

        return result

    # Package Manager Operations

    def query_package(self, package_name: str, manager: str = "auto") -> dict[str, Any]:
        """
        Query installed package information.

        Supports:
        - RPM (Red Hat, Fedora, CentOS, SUSE)
        - APT (Debian, Ubuntu)
        - Pacman (Arch Linux)

        Args:
            package_name: Name of package to query
            manager: Package manager to use ('rpm', 'dpkg', 'pacman', 'auto')

        Returns:
            Dict with package info (name, version, files, etc.)
        """
        if manager == "auto":
            manager = self._detect_package_manager()

        result: dict[str, Any] = {
            "name": package_name,
            "installed": False,
            "version": None,
            "package_manager": manager,
        }

        try:
            if manager == "rpm":
                result.update(self._query_rpm_package(package_name))
            elif manager == "dpkg":
                result.update(self._query_dpkg_package(package_name))
            elif manager == "pacman":
                result.update(self._query_pacman_package(package_name))
            else:
                self.logger.warning(f"Unsupported package manager: {manager}")

        # pylint: disable-next=broad-exception-caught  # dispatches across 3 pkg-manager backends; failure must not abort caller
        except Exception as e:
            self.logger.warning(f"Error querying package {package_name}: {e}")

        return result

    def list_installed_packages(self, manager: str = "auto", limit: int = 0) -> list[dict[str, str]]:
        """
        List all installed packages.

        Args:
            manager: Package manager to use ('rpm', 'dpkg', 'pacman', 'auto')
            limit: Maximum number of packages to return (0 = all)

        Returns:
            List of dicts with package name and version
        """
        if manager == "auto":
            manager = self._detect_package_manager()

        packages: list[dict[str, str]] = []

        try:
            if manager == "rpm":
                packages = self._list_rpm_packages()
            elif manager == "dpkg":
                packages = self._list_dpkg_packages()
            elif manager == "pacman":
                packages = self._list_pacman_packages()
            else:
                self.logger.warning(f"Unsupported package manager: {manager}")

        # pylint: disable-next=broad-exception-caught  # dispatches across 3 pkg-manager backends; failure must not abort caller
        except Exception as e:
            self.logger.warning(f"Error listing packages: {e}")

        if limit > 0:
            packages = packages[:limit]

        return packages

    def _detect_package_manager(self) -> str:
        """Auto-detect which package manager is in use."""
        # Check for RPM database
        if (self.mount_root / "var/lib/rpm").exists():
            return "rpm"

        # Check for dpkg database
        if (self.mount_root / "var/lib/dpkg").exists():
            return "dpkg"

        # Check for pacman database
        if (self.mount_root / "var/lib/pacman").exists():
            return "pacman"

        self.logger.warning("Could not detect package manager")
        return "unknown"

    def _query_rpm_package(self, package_name: str) -> dict[str, Any]:
        """Query RPM package using chroot rpm command."""
        info: dict[str, Any] = {}

        try:
            # Use rpm command in chroot
            cmd = ["chroot", str(self.mount_root), "rpm", "-q", package_name]
            result = run_sudo(self.logger, cmd, check=False, capture=True)

            if result.returncode == 0:
                info["installed"] = True
                # Parse package version from output (e.g., "bash-5.1.8-6.fc36")
                output = result.stdout.strip()
                info["full_name"] = output

                # Extract version
                match = re.search(r"-(\d+[\d\.\-]+)", output)
                if match:
                    info["version"] = match.group(1)

        except (DeviceError, OSError) as e:
            self.logger.debug(f"RPM query failed: {e}")

        return info

    def _query_dpkg_package(self, package_name: str) -> dict[str, Any]:
        """Query dpkg package using chroot dpkg command."""
        info: dict[str, Any] = {}

        try:
            # Use dpkg-query in chroot
            cmd = [
                "chroot",
                str(self.mount_root),
                "dpkg-query",
                "-W",
                "-f=${Status}|${Version}",
                package_name,
            ]
            result = run_sudo(self.logger, cmd, check=False, capture=True)

            if result.returncode == 0:
                output = result.stdout.strip()
                parts = output.split("|")

                if len(parts) >= 2:
                    status = parts[0]
                    if "installed" in status:
                        info["installed"] = True
                        info["version"] = parts[1]

        except (DeviceError, OSError) as e:
            self.logger.debug(f"dpkg query failed: {e}")

        return info

    def _query_pacman_package(self, package_name: str) -> dict[str, Any]:
        """Query pacman package using chroot pacman command."""
        info: dict[str, Any] = {}

        try:
            # Use pacman in chroot
            cmd = ["chroot", str(self.mount_root), "pacman", "-Q", package_name]
            result = run_sudo(self.logger, cmd, check=False, capture=True)

            if result.returncode == 0:
                info["installed"] = True
                # Parse output (e.g., "bash 5.1.016-1")
                output = result.stdout.strip()
                parts = output.split()
                if len(parts) >= 2:
                    info["version"] = parts[1]

        except (DeviceError, OSError) as e:
            self.logger.debug(f"pacman query failed: {e}")

        return info

    def _list_rpm_packages(self) -> list[dict[str, str]]:
        """List all RPM packages."""
        packages = []

        try:
            cmd = [
                "chroot",
                str(self.mount_root),
                "rpm",
                "-qa",
                "--queryformat",
                "%{NAME}|%{VERSION}-%{RELEASE}\\n",
            ]
            result = run_sudo(self.logger, cmd, check=True, capture=True)

            for line in result.stdout.splitlines():
                if "|" in line:
                    name, version = line.split("|", 1)
                    packages.append({"name": name, "version": version})

        except (DeviceError, OSError) as e:
            self.logger.debug(f"RPM list failed: {e}")

        return packages

    def _list_dpkg_packages(self) -> list[dict[str, str]]:
        """List all dpkg packages."""
        packages = []

        try:
            cmd = [
                "chroot",
                str(self.mount_root),
                "dpkg-query",
                "-W",
                "-f=${Package}|${Version}|${Status}\\n",
            ]
            result = run_sudo(self.logger, cmd, check=True, capture=True)

            for line in result.stdout.splitlines():
                parts = line.split("|")
                if len(parts) >= 3 and "installed" in parts[2]:
                    packages.append({"name": parts[0], "version": parts[1]})

        except (DeviceError, OSError) as e:
            self.logger.debug(f"dpkg list failed: {e}")

        return packages

    def _list_pacman_packages(self) -> list[dict[str, str]]:
        """List all pacman packages."""
        packages = []

        try:
            cmd = ["chroot", str(self.mount_root), "pacman", "-Q"]
            result = run_sudo(self.logger, cmd, check=True, capture=True)

            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    packages.append({"name": parts[0], "version": parts[1]})

        except (DeviceError, OSError) as e:
            self.logger.debug(f"pacman list failed: {e}")

        return packages
