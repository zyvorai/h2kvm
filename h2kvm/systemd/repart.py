# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd-repart integration for disk repartitioning.

This module wraps systemd-repart to automatically grow, shrink, or modify
partitions on migrated VM disks.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from h2kvm.systemd._common import check_systemd_binary_available, parse_binary_size

if TYPE_CHECKING:
    from pathlib import Path


class SystemdRepart:
    """
    Wrapper for systemd-repart command-line tool.

    Provides automatic disk repartitioning for migrated VMs,
    including partition resizing and layout modification.
    """

    def __init__(self, systemd_repart: str = "systemd-repart"):
        """
        Initialize systemd-repart wrapper.

        Parameters
        ----------
        systemd_repart : str, default="systemd-repart"
            Path to systemd-repart binary
        """
        self.binary = systemd_repart
        self._check_available()

    def _check_available(self) -> None:
        """Check if systemd-repart is available."""
        check_systemd_binary_available(
            self.binary,
            "systemd-repart",
            solutions=["Install systemd version 245+ (Debian/Ubuntu: apt install systemd)"],
        )

    def apply(
        self,
        device: Path,
        *,
        definitions: Path | None = None,
        dry_run: bool = False,
        pretty: bool = True,
    ) -> None:
        """
        Apply partition definitions to disk.

        Parameters
        ----------
        device : Path
            Block device to repartition
        definitions : Path | None
            Directory with partition definitions (default: /usr/lib/repart.d)
        dry_run : bool, default=False
            Show what would be done without making changes
        pretty : bool, default=True
            Pretty-print changes

        Examples
        --------
        >>> repart = SystemdRepart()
        >>> # Dry run first
        >>> repart.apply(Path("/dev/sda"), dry_run=True)
        >>> # Actually apply
        >>> repart.apply(Path("/dev/sda"))
        """
        cmd = [self.binary, str(device)]

        if definitions:
            cmd.extend(["--definitions", str(definitions)])
        if dry_run:
            cmd.append("--dry-run=yes")
        if pretty:
            cmd.append("--pretty=yes")

        subprocess.run(cmd, check=True)

    def size(
        self,
        device: Path,
        *,
        definitions: Path | None = None,
    ) -> dict[str, int]:
        """
        Calculate minimum size needed for partitions.

        Parameters
        ----------
        device : Path
            Block device to analyze
        definitions : Path | None
            Directory with partition definitions

        Returns
        -------
        dict[str, int]
            Mapping of partition names to minimum sizes in bytes

        Examples
        --------
        >>> repart = SystemdRepart()
        >>> sizes = repart.size(Path("/dev/sda"))
        >>> print(f"Minimum disk size: {sum(sizes.values()) / 1e9:.1f} GB")
        """
        cmd = [self.binary, "--size", str(device)]

        if definitions:
            cmd.extend(["--definitions", str(definitions)])

        # pylint: disable=duplicate-code
        # reason: mirrors the subprocess.run(...) call shape in
        # h2kvm/systemd/machine_id.py's setup() -- coincidental, both
        # just capture their own binary's text output.
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )

        # Parse output
        sizes = {}
        for line in result.stdout.splitlines():
            if ":" in line:
                name, size_str = line.split(":", 1)
                # Parse size (e.g., "1.5G" -> bytes)
                size_bytes = self._parse_size(size_str.strip())
                sizes[name.strip()] = size_bytes

        return sizes

    def _parse_size(self, size_str: str) -> int:
        """Parse size string like '1.5G' to bytes."""
        return parse_binary_size(size_str)

    def verify(
        self,
        *,
        definitions: Path | None = None,
    ) -> list[str]:
        """
        Verify partition definition files.

        Parameters
        ----------
        definitions : Path | None
            Directory with partition definitions

        Returns
        -------
        list[str]
            List of errors found

        Examples
        --------
        >>> repart = SystemdRepart()
        >>> errors = repart.verify(definitions=Path("/etc/repart.d"))
        >>> if errors:
        ...     print(f"Found {len(errors)} errors")
        """
        cmd = [self.binary, "--verify"]

        if definitions:
            cmd.extend(["--definitions", str(definitions)])

        # pylint: disable=duplicate-code
        # reason: mirrors the subprocess.run(...) call shape in
        # h2kvm/systemd/detect_virt.py's detect() -- coincidental,
        # both just capture their own binary's text output without
        # raising on non-zero exit.
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            return []

        return [line.strip() for line in result.stderr.splitlines() if line.strip()]
