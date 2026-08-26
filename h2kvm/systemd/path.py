# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd-path integration for path unit management.

This module wraps systemd-path to show and monitor filesystem paths,
useful for monitoring migration directories.
"""

from __future__ import annotations

import subprocess

from h2kvm.core.exceptions import SystemdError


class SystemdPath:
    """
    Wrapper for systemd-path command-line tool.

    Provides access to systemd path units and directory locations
    for migration file management.
    """

    def __init__(self, systemd_path: str = "systemd-path"):
        """
        Initialize systemd-path wrapper.

        Parameters
        ----------
        systemd_path : str, default="systemd-path"
            Path to systemd-path binary
        """
        self.binary = systemd_path
        self._check_available()

    def _check_available(self) -> None:
        # pylint: disable=duplicate-code
        # reason: mirrors the equivalent binary-availability check in
        # h2kvm/systemd/nspawn.py (and other systemd/*.py wrappers) -- shared shape
        # across the whole systemd/ package, kept independent per-tool since binary
        # name and remediation hints differ.
        """Check if systemd-path is available."""
        try:
            subprocess.run(
                [self.binary, "--version"],
                capture_output=True,
                check=True,
                timeout=5,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            msg = f"systemd-path not available: {e}"
            raise SystemdError(code=127, msg=msg).with_context(
                solutions=["Install systemd (usually pre-installed)"]
            ) from e

    def show(self, *names: str) -> dict[str, str]:
        """
        Show systemd path values.

        Parameters
        ----------
        names : str
            Specific path names to show (if none, show all)

        Returns
        -------
        dict[str, str]
            Mapping of path names to values

        Examples
        --------
        >>> path = SystemdPath()
        >>> paths = path.show("temporary-directory", "state-directory")
        >>> print(f"Temp: {paths['temporary-directory']}")
        """
        cmd = [self.binary]
        cmd.extend(names)

        # pylint: disable=duplicate-code
        # reason: mirrors the equivalent subprocess.run(...) invocation in
        # h2kvm/systemd/analyze.py's critical_chain() -- generic subprocess-call
        # shape reused throughout systemd/*.py wrappers, not shared logic worth
        # extracting.
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )

        paths = {}
        for line in result.stdout.splitlines():
            if ":" in line:
                name, value = line.split(":", 1)
                paths[name.strip()] = value.strip()

        return paths

    def get_temporary_directory(self) -> str:
        """
        Get systemd temporary directory path.

        Returns
        -------
        str
            Temporary directory path

        Examples
        --------
        >>> path = SystemdPath()
        >>> tmp_dir = path.get_temporary_directory()
        >>> print(f"Using temp dir: {tmp_dir}")
        """
        paths = self.show("temporary-directory")
        return paths.get("temporary-directory", "/tmp")

    def get_state_directory(self) -> str:
        """
        Get systemd state directory path.

        Returns
        -------
        str
            State directory path

        Examples
        --------
        >>> path = SystemdPath()
        >>> state_dir = path.get_state_directory()
        """
        paths = self.show("state-directory")
        return paths.get("state-directory", "/var/lib")

    def get_cache_directory(self) -> str:
        """
        Get systemd cache directory path.

        Returns
        -------
        str
            Cache directory path

        Examples
        --------
        >>> path = SystemdPath()
        >>> cache_dir = path.get_cache_directory()
        """
        paths = self.show("cache-directory")
        return paths.get("cache-directory", "/var/cache")

    def get_runtime_directory(self) -> str:
        """
        Get systemd runtime directory path.

        Returns
        -------
        str
            Runtime directory path

        Examples
        --------
        >>> path = SystemdPath()
        >>> runtime_dir = path.get_runtime_directory()
        """
        paths = self.show("runtime-directory")
        return paths.get("runtime-directory", "/run")

    def get_all(self) -> dict[str, str]:
        """
        Get all systemd path values.

        Returns
        -------
        dict[str, str]
            All path mappings

        Examples
        --------
        >>> path = SystemdPath()
        >>> all_paths = path.get_all()
        >>> for name, value in all_paths.items():
        ...     print(f"{name}: {value}")
        """
        return self.show()
