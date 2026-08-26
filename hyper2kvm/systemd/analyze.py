# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd-analyze integration for performance analysis.

This module wraps systemd-analyze to provide boot time analysis,
critical chain inspection, and system verification for migrated VMs.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass

from hyper2kvm.core.exceptions import SystemdError


@dataclass
class BootTime:
    """Boot time analysis results."""

    firmware: float  # Firmware initialization time (seconds)
    loader: float  # Bootloader time (seconds)
    kernel: float  # Kernel initialization time (seconds)
    initrd: float  # Initramfs time (seconds)
    userspace: float  # Userspace initialization time (seconds)
    total: float  # Total boot time (seconds)


@dataclass
class UnitTime:
    """Time taken by a systemd unit."""

    unit: str
    time: float  # Time in seconds
    activated: int  # Timestamp when activated


class SystemdAnalyze:
    """
    Wrapper for systemd-analyze command-line tool.

    Provides boot time analysis, critical chain inspection, and
    system verification for migrated VMs.
    """

    def __init__(self, systemd_analyze: str = "systemd-analyze"):
        """
        Initialize systemd-analyze wrapper.

        Parameters
        ----------
        systemd_analyze : str, default="systemd-analyze"
            Path to systemd-analyze binary
        """
        self.binary = systemd_analyze
        self._check_available()

    def _check_available(self) -> None:
        """Check if systemd-analyze is available."""
        try:
            subprocess.run(
                [self.binary, "--version"],
                capture_output=True,
                check=True,
                timeout=5,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            msg = f"systemd-analyze not available: {e}"
            raise SystemdError(code=127, msg=msg).with_context(
                solutions=["Install systemd (usually pre-installed)"]
            ) from e

    def time(self) -> BootTime:
        """
        Get boot time breakdown.

        Returns
        -------
        BootTime
            Boot time analysis

        Examples
        --------
        >>> analyze = SystemdAnalyze()
        >>> boot = analyze.time()
        >>> print(f"Total boot time: {boot.total}s")
        """
        result = subprocess.run(
            [self.binary, "time"],
            capture_output=True,
            text=True,
            check=True,
        )

        # Parse output like:
        # Startup finished in 2.1s (firmware) + 1.5s (loader) + 3.2s (kernel) + 4.5s (initrd)
        # + 12.3s (userspace) = 23.6s
        output = result.stdout.strip()

        # Extract times using regex to handle "Startup finished in Xs (phase)" format
        times = {}
        parts = output.split(" + ")

        for part in parts:
            # Extract the numeric value immediately before "s" (e.g., "2.1s")
            # Use regex to avoid splitting on 's' in words like "Startup"
            m = re.search(r"([\d.]+)s\s*\((\w+)\)", part)
            if m:
                value, phase = float(m.group(1)), m.group(2)
                times[phase] = value

            # Handle the "= 23.6s" total at the end of the userspace part
            if "=" in part:
                m_total = re.search(r"=\s*([\d.]+)s", part)
                if m_total:
                    times["total"] = float(m_total.group(1))

        return BootTime(
            firmware=times.get("firmware", 0.0),
            loader=times.get("loader", 0.0),
            kernel=times.get("kernel", 0.0),
            initrd=times.get("initrd", 0.0),
            userspace=times.get("userspace", 0.0),
            total=times.get("total", 0.0),
        )

    def blame(self, *, limit: int | None = None) -> list[UnitTime]:
        """
        List units by initialization time.

        Parameters
        ----------
        limit : int | None
            Maximum number of units to return

        Returns
        -------
        list[UnitTime]
            Units sorted by time (slowest first)

        Examples
        --------
        >>> analyze = SystemdAnalyze()
        >>> slow_units = analyze.blame(limit=10)
        >>> for unit in slow_units:
        ...     print(f"{unit.unit}: {unit.time}s")
        """
        result = subprocess.run(
            [self.binary, "blame"],
            capture_output=True,
            text=True,
            check=True,
        )

        units = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue

            # Parse lines like: "5.234s NetworkManager.service"
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2:
                time_str, unit_name = parts
                # Remove 's' or 'ms' suffix
                if time_str.endswith("ms"):
                    time_val = float(time_str[:-2]) / 1000.0
                elif time_str.endswith("s"):
                    time_val = float(time_str[:-1])
                else:
                    continue

                units.append(
                    UnitTime(
                        unit=unit_name,
                        time=time_val,
                        activated=0,  # Not available in blame output
                    )
                )

        if limit:
            return units[:limit]
        return units

    def critical_chain(self, *, unit: str | None = None) -> str:
        """
        Show critical chain for boot or specific unit.

        Parameters
        ----------
        unit : str | None
            Specific unit to analyze (default: boot process)

        Returns
        -------
        str
            Critical chain tree

        Examples
        --------
        >>> analyze = SystemdAnalyze()
        >>> chain = analyze.critical_chain()
        >>> print(chain)
        """
        cmd = [self.binary, "critical-chain"]
        if unit:
            cmd.append(unit)

        # pylint: disable=duplicate-code
        # reason: mirrors the equivalent subprocess.run(...) invocation in
        # hyper2kvm/systemd/path.py's show() -- generic subprocess-call shape reused
        # throughout systemd/*.py wrappers, not shared logic worth extracting.
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )

        return result.stdout

    def verify(self, *units: str) -> dict[str, list[str]]:
        """
        Verify systemd unit files.

        Parameters
        ----------
        units : str
            Unit files to verify (if none, verify all)

        Returns
        -------
        dict[str, list[str]]
            Mapping of unit names to error messages

        Examples
        --------
        >>> analyze = SystemdAnalyze()
        >>> errors = analyze.verify()
        >>> if errors:
        ...     print(f"Found {len(errors)} units with errors")
        """
        cmd = [self.binary, "verify"]
        cmd.extend(units)

        # pylint: disable=duplicate-code
        # reason: mirrors the equivalent subprocess.run(...) invocation in
        # hyper2kvm/luks/tpm.py's PCR-read helper -- generic subprocess-call shape,
        # not shared logic worth extracting across unrelated tpm2/systemd tooling.
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        # Parse verification output
        errors: dict[str, list[str]] = {}

        for line in result.stderr.splitlines():
            if not line.strip():
                continue

            # Lines like: "foo.service: Missing required field 'ExecStart'"
            if ": " in line:
                unit_name = line.split(":")[0].strip()
                error_msg = ":".join(line.split(":")[1:]).strip()

                if unit_name not in errors:
                    errors[unit_name] = []
                errors[unit_name].append(error_msg)

        return errors

    def security(self, unit: str) -> dict[str, str]:
        """
        Analyze security settings of a unit.

        Parameters
        ----------
        unit : str
            Unit name to analyze

        Returns
        -------
        dict[str, str]
            Security analysis results

        Examples
        --------
        >>> analyze = SystemdAnalyze()
        >>> security = analyze.security("nginx.service")
        >>> print(f"Exposure level: {security.get('exposure')}")
        """
        result = subprocess.run(
            [self.binary, "security", "--json=short", unit],
            capture_output=True,
            text=True,
            check=True,
        )

        return json.loads(result.stdout)

    def dot(
        self,
        *,
        to_pattern: str | None = None,
        from_pattern: str | None = None,
    ) -> str:
        """
        Generate dependency graph in DOT format.

        Parameters
        ----------
        to_pattern : str | None
            Only show dependencies to units matching pattern
        from_pattern : str | None
            Only show dependencies from units matching pattern

        Returns
        -------
        str
            DOT format graph

        Examples
        --------
        >>> analyze = SystemdAnalyze()
        >>> graph = analyze.dot(to_pattern="*.target")
        >>> # Save to file and render with graphviz
        >>> Path("deps.dot").write_text(graph)
        """
        cmd = [self.binary, "dot"]

        if to_pattern:
            cmd.extend(["--to-pattern", to_pattern])
        if from_pattern:
            cmd.extend(["--from-pattern", from_pattern])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )

        return result.stdout

    def dump(self) -> dict:
        """
        Dump systemd state in JSON format.

        Returns
        -------
        dict
            Complete systemd state

        Examples
        --------
        >>> analyze = SystemdAnalyze()
        >>> state = analyze.dump()
        >>> print(f"Active units: {len(state.get('units', []))}")
        """
        result = subprocess.run(
            [self.binary, "dump", "--output=json"],
            capture_output=True,
            text=True,
            check=True,
        )

        return json.loads(result.stdout)

    def syscall_filter(self, *, name: str | None = None) -> list[str]:
        """
        List system calls in filter.

        Parameters
        ----------
        name : str | None
            Filter name (e.g., "@system-service")

        Returns
        -------
        list[str]
            System calls in filter

        Examples
        --------
        >>> analyze = SystemdAnalyze()
        >>> syscalls = analyze.syscall_filter(name="@system-service")
        >>> print(f"System calls: {len(syscalls)}")
        """
        cmd = [self.binary, "syscall-filter"]
        if name:
            cmd.append(name)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )

        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
