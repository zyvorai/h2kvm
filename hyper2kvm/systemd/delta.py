# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd-delta integration for configuration management.

This module wraps systemd-delta to find overridden configuration files,
useful for understanding VM configuration changes during migration.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from hyper2kvm.systemd._common import check_systemd_binary_available


@dataclass
class ConfigOverride:
    """Configuration file override information."""

    type: str  # masked, overridden, equivalent, redirected, extended
    original: str  # Original file path
    override: str  # Override file path


class SystemdDelta:
    """
    Wrapper for systemd-delta command-line tool.

    Provides configuration override detection to understand
    VM configuration changes during migration.
    """

    def __init__(self, systemd_delta: str = "systemd-delta"):
        """
        Initialize systemd-delta wrapper.

        Parameters
        ----------
        systemd_delta : str, default="systemd-delta"
            Path to systemd-delta binary
        """
        self.binary = systemd_delta
        self._check_available()

    def _check_available(self) -> None:
        """Check if systemd-delta is available."""
        check_systemd_binary_available(
            self.binary,
            "systemd-delta",
            solutions=["Install systemd (usually pre-installed)"],
        )

    def find_overrides(
        self,
        *,
        override_type: str | None = None,
    ) -> list[ConfigOverride]:
        """
        Find configuration file overrides.

        Parameters
        ----------
        override_type : str | None
            Filter by type (masked, overridden, equivalent, redirected, extended)

        Returns
        -------
        list[ConfigOverride]
            List of configuration overrides

        Examples
        --------
        >>> delta = SystemdDelta()
        >>> overrides = delta.find_overrides()
        >>> for override in overrides:
        ...     print(f"{override.type}: {override.original}")
        """
        cmd = [self.binary]

        if override_type:
            cmd.extend(["--type", override_type])

        # pylint: disable=duplicate-code
        # reason: mirrors the subprocess.run(...) call shape in
        # hyper2kvm/systemd/cgtop.py's snapshot() and
        # hyper2kvm/systemd/mount.py's mount() -- coincidental, each just
        # captures its own binary's text output.
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )

        return self._parse_output(result.stdout)

    def _parse_output(self, output: str) -> list[ConfigOverride]:
        """Parse systemd-delta output."""
        overrides = []

        for line in output.splitlines():
            if not line.strip() or line.startswith("["):
                continue

            # Parse lines like: "[MASKED]    /etc/systemd/system/foo.service → /dev/null"
            if "→" in line:
                parts = line.split("→")
                if len(parts) == 2:
                    left = parts[0].strip()
                    right = parts[1].strip()

                    # Extract type and original path
                    if "[" in left and "]" in left:
                        type_end = left.index("]")
                        override_type = left[1:type_end].lower()
                        original = left[type_end + 1 :].strip()

                        overrides.append(
                            ConfigOverride(
                                type=override_type,
                                original=original,
                                override=right,
                            )
                        )

        return overrides

    def find_masked(self) -> list[ConfigOverride]:
        """
        Find masked configuration files.

        Returns
        -------
        list[ConfigOverride]
            List of masked files

        Examples
        --------
        >>> delta = SystemdDelta()
        >>> masked = delta.find_masked()
        >>> for m in masked:
        ...     print(f"Masked: {m.original}")
        """
        return self.find_overrides(override_type="masked")

    def find_overridden(self) -> list[ConfigOverride]:
        """
        Find overridden configuration files.

        Returns
        -------
        list[ConfigOverride]
            List of overridden files

        Examples
        --------
        >>> delta = SystemdDelta()
        >>> overridden = delta.find_overridden()
        >>> for o in overridden:
        ...     print(f"{o.original} -> {o.override}")
        """
        return self.find_overrides(override_type="overridden")

    def check_equivalent(self) -> list[ConfigOverride]:
        """
        Find equivalent configuration files (same content).

        Returns
        -------
        list[ConfigOverride]
            List of equivalent files

        Examples
        --------
        >>> delta = SystemdDelta()
        >>> equivalent = delta.check_equivalent()
        >>> print(f"Found {len(equivalent)} equivalent overrides")
        """
        return self.find_overrides(override_type="equivalent")
