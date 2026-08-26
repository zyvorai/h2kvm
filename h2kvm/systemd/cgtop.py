# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd-cgtop integration for cgroup resource monitoring.

This module wraps systemd-cgtop to monitor CPU, memory, and I/O usage
of migration processes in real-time.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from h2kvm.systemd._common import check_systemd_binary_available, parse_binary_size


@dataclass
class CgroupStats:
    """Resource statistics for a cgroup."""

    path: str
    tasks: int
    cpu_percent: float
    memory_bytes: int
    io_bytes_per_sec: int


class SystemdCgtop:
    """
    Wrapper for systemd-cgtop command-line tool.

    Provides real-time monitoring of cgroup resource usage during
    VM migration operations.
    """

    def __init__(self, systemd_cgtop: str = "systemd-cgtop"):
        """
        Initialize systemd-cgtop wrapper.

        Parameters
        ----------
        systemd_cgtop : str, default="systemd-cgtop"
            Path to systemd-cgtop binary
        """
        self.binary = systemd_cgtop
        self._check_available()

    def _check_available(self) -> None:
        """Check if systemd-cgtop is available."""
        check_systemd_binary_available(
            self.binary,
            "systemd-cgtop",
            solutions=["Install systemd (usually pre-installed)"],
        )

    def snapshot(
        self,
        *,
        iterations: int = 1,
        delay: int = 1,
        batch: bool = True,
    ) -> list[CgroupStats]:
        """
        Get snapshot of cgroup resource usage.

        Parameters
        ----------
        iterations : int, default=1
            Number of measurement iterations
        delay : int, default=1
            Delay between iterations in seconds
        batch : bool, default=True
            Batch mode (non-interactive)

        Returns
        -------
        list[CgroupStats]
            List of cgroup statistics

        Examples
        --------
        >>> cgtop = SystemdCgtop()
        >>> stats = cgtop.snapshot()
        >>> for cg in stats:
        ...     print(f"{cg.path}: CPU {cg.cpu_percent}%, MEM {cg.memory_bytes}")
        """
        cmd = [self.binary, f"--iterations={iterations}", f"--delay={delay}"]

        if batch:
            cmd.append("--batch")

        # pylint: disable=duplicate-code
        # reason: mirrors the subprocess.run(...) call shape in
        # h2kvm/systemd/delta.py's find_overrides() and
        # h2kvm/systemd/escape.py's systemd_escape() -- coincidental,
        # each just invokes its own binary and captures text output.
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )

        return self._parse_output(result.stdout)

    def _parse_output(self, output: str) -> list[CgroupStats]:
        """Parse cgtop output into structured data."""
        stats = []
        lines = output.splitlines()

        # Skip header lines
        data_lines = [line for line in lines if line.strip() and not line.startswith("Control")]

        for line in data_lines[1:]:  # Skip column headers
            parts = line.split()
            if len(parts) < 5:
                continue

            try:
                stats.append(
                    CgroupStats(
                        path=parts[0],
                        tasks=int(parts[1]) if parts[1].isdigit() else 0,
                        cpu_percent=float(parts[2].rstrip("%")) if "%" in parts[2] else 0.0,
                        memory_bytes=self._parse_size(parts[3]) if len(parts) > 3 else 0,
                        io_bytes_per_sec=self._parse_size(parts[4]) if len(parts) > 4 else 0,
                    )
                )
            except (ValueError, IndexError):
                continue

        return stats

    def _parse_size(self, size_str: str) -> int:
        """Parse size string like '1.5G' to bytes."""
        if not size_str or size_str == "-":
            return 0

        try:
            return parse_binary_size(size_str)
        except ValueError:
            return 0

    def monitor_service(
        self,
        service_name: str,
        *,
        duration: int = 10,
    ) -> list[CgroupStats]:
        """
        Monitor specific service resource usage.

        Parameters
        ----------
        service_name : str
            Systemd service name (e.g., "h2kvm-migration.service")
        duration : int, default=10
            Monitoring duration in seconds

        Returns
        -------
        list[CgroupStats]
            Resource usage snapshots

        Examples
        --------
        >>> cgtop = SystemdCgtop()
        >>> stats = cgtop.monitor_service("h2kvm-migration.service", duration=30)
        >>> avg_cpu = sum(s.cpu_percent for s in stats) / len(stats)
        >>> print(f"Average CPU: {avg_cpu:.1f}%")
        """
        snapshots = []

        for _ in range(duration):
            current = self.snapshot(iterations=1, delay=1)
            # Filter for specific service
            service_stats = [s for s in current if service_name in s.path]
            if service_stats:
                snapshots.extend(service_stats)

        return snapshots
