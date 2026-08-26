# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd-analyze integration for VMCraft.

Provides system and service analysis capabilities.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    import logging


class SystemdAnalyzer:
    """Analyze systemd performance and configuration."""

    def __init__(self, command_runner: Callable[[list[str]], str], logger: logging.Logger):
        """
        Initialize SystemdAnalyzer.

        Args:
            command_runner: Function to execute commands in guest
            logger: Logger instance
        """
        self.command = command_runner
        self.logger = logger

    def time(self) -> dict[str, Any]:
        """
        Analyze system boot time.

        Returns:
            Dict with boot timing information:
            - firmware: Firmware initialization time (seconds)
            - loader: Bootloader time (seconds)
            - kernel: Kernel initialization time (seconds)
            - initrd: Initial ramdisk time (seconds)
            - userspace: Userspace initialization time (seconds)
            - total: Total boot time (seconds)

        Example:
            timing = analyzer.time()
            print(f"Total boot time: {timing['total']}s")
            print(f"Userspace: {timing['userspace']}s")
        """
        try:
            result = self.command(["systemd-analyze", "time"])

            # Parse output like:
            # "Startup finished in 2.5s (firmware) + 1.2s (loader) +
            #  3.4s (kernel) + 5.6s (initrd) + 12.3s (userspace) = 25.0s"

            timing = {}

            # Helper to parse time values
            def parse_time(text):
                """Parse time value like '2.5s' or '1min 30s' to seconds."""
                total = 0.0
                # Handle minutes
                match = re.search(r"(\d+)min", text)
                if match:
                    total += float(match.group(1)) * 60
                # Handle seconds
                match = re.search(r"(\d+\.?\d*)s", text)
                if match:
                    total += float(match.group(1))
                # Handle milliseconds
                match = re.search(r"(\d+)ms", text)
                if match:
                    total += float(match.group(1)) / 1000
                return total

            # Extract individual timings
            patterns = {
                "firmware": r"([\d.]+(?:min|s|ms)?)\s*\(firmware\)",
                "loader": r"([\d.]+(?:min|s|ms)?)\s*\(loader\)",
                "kernel": r"([\d.]+(?:min|s|ms)?)\s*\(kernel\)",
                "initrd": r"([\d.]+(?:min|s|ms)?)\s*\(initrd\)",
                "userspace": r"([\d.]+(?:min|s|ms)?)\s*\(userspace\)",
            }

            for key, pattern in patterns.items():
                match = re.search(pattern, result)
                if match:
                    timing[key] = parse_time(match.group(1))

            # Extract total
            match = re.search(r"=\s*([\d.]+(?:min|s|ms)?)", result)
            if match:
                timing["total"] = parse_time(match.group(1))
            else:
                timing["total"] = sum(timing.values())

            return timing

        except Exception as e:  # pylint: disable=broad-exception-caught
            # systemd-analyze subprocess/parse best-effort; must not abort the caller
            self.logger.debug(f"systemd-analyze time failed: {e}")
            return {}

    def blame(self, lines: int | None = None) -> list[dict[str, str]]:
        """
        Show which services took the longest to initialize.

        Args:
            lines: Number of services to return (None = all)

        Returns:
            List of dicts sorted by initialization time (slowest first)
            Keys: time, unit

        Example:
            blame = analyzer.blame(10)
            print("Slowest services:")
            for svc in blame:
                print(f"  {svc['time']}: {svc['unit']}")
        """
        # pylint: disable=duplicate-code
        # reason: mirrors the equivalent "for line in result.splitlines():
        # parts = line.split(None, N)" output-parsing loop in
        # vmcraft/systemd/systemctl.py (list_unit_files) -- structurally
        # similar by coincidence, not shared logic; keeping independent
        # avoids coupling unrelated systemd-output parsing.
        try:
            result = self.command(["systemd-analyze", "blame"])

            services = []
            for line in result.splitlines():
                line = line.strip()
                if not line:
                    continue

                # Format: "12.345s some.service"
                parts = line.split(None, 1)
                if len(parts) == 2:
                    services.append(
                        {
                            "time": parts[0],
                            "unit": parts[1],
                        }
                    )

            # Limit results if requested
            if lines is not None:
                services = services[:lines]

            return services

        except Exception as e:  # pylint: disable=broad-exception-caught
            # systemd-analyze subprocess/parse best-effort; must not abort the caller
            self.logger.debug(f"systemd-analyze blame failed: {e}")
            return []

    def critical_chain(self, unit: str | None = None) -> str:
        """
        Show critical chain for boot or specific unit.

        The critical chain shows the path of units that delayed boot the most.

        Args:
            unit: Optional unit to show critical chain for

        Returns:
            Critical chain as formatted string

        Example:
            chain = analyzer.critical_chain()
            print("Boot critical chain:")
            print(chain)

            chain = analyzer.critical_chain("nginx.service")
            print(f"Critical chain for nginx:")
            print(chain)
        """
        try:
            cmd = ["systemd-analyze", "critical-chain"]
            if unit:
                cmd.append(unit)

            return self.command(cmd)

        except Exception as e:  # pylint: disable=broad-exception-caught
            # systemd-analyze subprocess/parse best-effort; must not abort the caller
            self.logger.debug(f"systemd-analyze critical-chain failed: {e}")
            return ""

    def security(self, unit: str | None = None) -> list[dict[str, Any]]:
        """
        Analyze security settings of services.

        Args:
            unit: Optional specific unit to analyze (if None, analyzes all)

        Returns:
            List of dicts with security analysis
            Keys: unit, exposure, predicate, description

        Example:
            security = analyzer.security("sshd.service")
            for check in security:
                if check.get('exposure', 0) > 7.0:
                    print(f"⚠️  High exposure: {check['predicate']}")
        """
        try:
            cmd = ["systemd-analyze", "security"]
            if unit:
                cmd.append(unit)

            result = self.command(cmd)

            # Try to parse as table output
            security_items = []
            current_unit = unit

            for line in result.splitlines():
                line = line.strip()
                if not line or line.startswith(("→", "NAME")):
                    continue

                # If no unit specified, first column is unit name
                if not unit:
                    parts = line.split(None, 1)
                    if len(parts) >= 2:
                        current_unit = parts[0]
                        line = parts[1]

                # Parse security checks
                # Format varies, try to extract key info
                if "EXPOSURE" in line.upper() or "/" in line:
                    parts = line.split()
                    if len(parts) >= 1:
                        security_items.append(
                            {
                                "unit": current_unit or "unknown",
                                "description": line,
                            }
                        )

            return security_items

        except Exception as e:  # pylint: disable=broad-exception-caught
            # systemd-analyze subprocess/parse best-effort; must not abort the caller
            self.logger.debug(f"systemd-analyze security failed: {e}")
            return []

    def verify(self, unit: str) -> dict[str, Any]:
        """
        Verify unit file syntax and configuration.

        Args:
            unit: Unit name to verify

        Returns:
            Dict with verification results
            Keys: valid, errors, warnings

        Example:
            result = analyzer.verify("custom.service")
            if not result['valid']:
                print(f"Errors: {result['errors']}")
        """
        try:
            result = self.command(["systemd-analyze", "verify", unit])

            verification = {
                "valid": True,
                "errors": [],
                "warnings": [],
            }

            # Parse errors and warnings
            for line in result.splitlines():
                line_lower = line.lower()
                if "error" in line_lower:
                    verification["valid"] = False
                    verification["errors"].append(line.strip())
                elif "warning" in line_lower:
                    verification["warnings"].append(line.strip())

            return verification

        except Exception as e:  # pylint: disable=broad-exception-caught
            # systemd-analyze subprocess/parse best-effort; must not abort the caller
            return {
                "valid": False,
                "errors": [str(e)],
                "warnings": [],
            }

    def dot(self, pattern: str | None = None, to_pattern: str | None = None) -> str:
        """
        Generate dependency graph in GraphViz dot format.

        Args:
            pattern: Pattern to filter units (e.g., "*.service")
            to_pattern: Show dependencies to matching units

        Returns:
            GraphViz dot format string

        Example:
            # Generate full dependency graph
            dot = analyzer.dot()
            # Save to file and render with: dot -Tpng -o deps.png

            # Show only service dependencies
            dot = analyzer.dot("*.service")
        """
        try:
            cmd = ["systemd-analyze", "dot"]
            if pattern:
                cmd.append(pattern)
            if to_pattern:
                cmd.extend(["--to-pattern", to_pattern])

            return self.command(cmd)

        except Exception as e:  # pylint: disable=broad-exception-caught
            # systemd-analyze subprocess/parse best-effort; must not abort the caller
            self.logger.debug(f"systemd-analyze dot failed: {e}")
            return ""

    def calendar(self, expression: str) -> dict[str, str]:
        """
        Validate and show next elapse times for calendar expressions.

        Args:
            expression: Calendar expression (e.g., "daily", "Mon *-*-* 00:00:00")

        Returns:
            Dict with parsed calendar information
            Keys: normalized, next_elapse

        Example:
            cal = analyzer.calendar("daily")
            print(f"Next run: {cal['next_elapse']}")

            cal = analyzer.calendar("Mon,Fri *-*-* 12:00:00")
            print(f"Normalized: {cal['normalized']}")
        """
        try:
            result = self.command(["systemd-analyze", "calendar", expression])

            info = {
                "normalized": "",
                "next_elapse": "",
                "output": result,
            }

            # Parse output
            for line in result.splitlines():
                if "Normalized form:" in line:
                    info["normalized"] = line.split(":", 1)[1].strip()
                elif "Next elapse:" in line:
                    info["next_elapse"] = line.split(":", 1)[1].strip()

            return info

        except Exception as e:  # pylint: disable=broad-exception-caught
            # systemd-analyze subprocess/parse best-effort; must not abort the caller
            self.logger.debug(f"systemd-analyze calendar failed for {expression}: {e}")
            return {"normalized": "", "next_elapse": "", "output": str(e)}

    def dump(self) -> str:
        """
        Dump server state in human-readable form.

        Returns:
            Complete system state dump

        Note: Output can be very large
        """
        try:
            return self.command(["systemd-analyze", "dump"])
        except Exception as e:  # pylint: disable=broad-exception-caught
            # systemd-analyze subprocess/parse best-effort; must not abort the caller
            self.logger.debug(f"systemd-analyze dump failed: {e}")
            return ""

    def plot(self) -> str:
        """
        Generate SVG boot time plot.

        Returns:
            SVG content as string

        Example:
            svg = analyzer.plot()
            with open("boot.svg", "w") as f:
                f.write(svg)
        """
        try:
            return self.command(["systemd-analyze", "plot"])
        except Exception as e:  # pylint: disable=broad-exception-caught
            # systemd-analyze subprocess/parse best-effort; must not abort the caller
            self.logger.debug(f"systemd-analyze plot failed: {e}")
            return ""

    def syscall_filter(self, set_name: str | None = None) -> list[str]:
        """
        List system calls in seccomp filter sets.

        Args:
            set_name: Optional filter set name (e.g., "@system-service")

        Returns:
            List of system call names

        Example:
            syscalls = analyzer.syscall_filter("@system-service")
            print(f"System calls in @system-service: {len(syscalls)}")
        """
        try:
            cmd = ["systemd-analyze", "syscall-filter"]
            if set_name:
                cmd.append(set_name)

            result = self.command(cmd)

            syscalls = []
            for line in result.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    syscalls.append(line)

            return syscalls

        except Exception as e:  # pylint: disable=broad-exception-caught
            # systemd-analyze subprocess/parse best-effort; must not abort the caller
            self.logger.debug(f"systemd-analyze syscall-filter failed: {e}")
            return []
