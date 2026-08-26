# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/vmcraft/firewall_analyzer.py
"""
Firewall configuration analysis for both Windows and Linux.

Provides comprehensive firewall rule detection:
- iptables rules (Linux)
- firewalld configuration (Linux)
- ufw rules (Linux)
- nftables rules (Linux)
- Windows Firewall rules (via registry)

Features:
- Parse firewall rules
- Identify open ports
- Detect blocked/allowed services
- Security policy analysis
- Rule count and statistics
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging

    from .file_ops import FileOperations


class FirewallAnalyzer:
    """
    Firewall configuration analyzer.

    Analyzes firewall rules for both Windows and Linux systems.

    Does not subclass BaseAnalyzer: unlike most vmcraft analyzers, this one needs
    no mount_root or the inherited path-helper methods, it only uses file_ops
    directly (matching the same standalone (logger, file_ops) pattern used by
    ScheduledTaskAnalyzer and AdvancedAnalyzer).
    """

    def __init__(self, logger: logging.Logger, file_ops: FileOperations):
        """
        Initialize firewall analyzer.

        Args:
            logger: Logger instance
            file_ops: FileOperations instance
        """
        self.logger = logger
        self.file_ops = file_ops

    def analyze_firewall(self, os_type: str) -> dict[str, Any]:
        """
        Analyze firewall configuration based on OS type.

        Args:
            os_type: Operating system type ("windows" or "linux")

        Returns:
            Firewall configuration dictionary
        """
        if os_type == "windows":
            return self._analyze_windows_firewall()
        if os_type == "linux":
            return self._analyze_linux_firewall()
        return {"error": f"Unsupported OS type: {os_type}"}

    def _analyze_linux_firewall(self) -> dict[str, Any]:
        """
        Analyze Linux firewall configuration.

        Detects and parses:
        - iptables (/etc/sysconfig/iptables, /etc/iptables/)
        - firewalld (/etc/firewalld/)
        - ufw (/etc/ufw/)
        - nftables (/etc/nftables.conf)

        Returns:
            Firewall configuration dictionary
        """
        config: dict[str, Any] = {
            "firewall_type": None,
            "enabled": False,
            "rules": [],
            "open_ports": [],
            "blocked_ports": [],
        }

        # Detect firewall type
        if self.file_ops.is_dir("/etc/firewalld"):
            config["firewall_type"] = "firewalld"
            config.update(self._parse_firewalld())
        elif self.file_ops.is_dir("/etc/ufw"):
            config["firewall_type"] = "ufw"
            config.update(self._parse_ufw())
        elif self.file_ops.exists("/etc/sysconfig/iptables"):
            config["firewall_type"] = "iptables"
            config.update(self._parse_iptables("/etc/sysconfig/iptables"))
        elif self.file_ops.exists("/etc/iptables/rules.v4"):
            config["firewall_type"] = "iptables"
            config.update(self._parse_iptables("/etc/iptables/rules.v4"))
        elif self.file_ops.exists("/etc/nftables.conf"):
            config["firewall_type"] = "nftables"
            config.update(self._parse_nftables())

        return config

    def _parse_firewalld(self) -> dict[str, Any]:
        """
        Parse firewalld configuration.

        Reads:
        - /etc/firewalld/zones/*.xml
        - Default zone
        - Enabled services

        Returns:
            Firewalld configuration
        """
        config = {
            "enabled": True,
            "zones": [],
            "services": [],
            "rules": [],
        }

        try:
            # Check if firewalld is enabled
            if self.file_ops.exists("/etc/firewalld/firewalld.conf"):
                conf = self.file_ops.cat("/etc/firewalld/firewalld.conf")
                # Parse default zone
                for line in conf.splitlines():
                    if line.startswith("DefaultZone="):
                        config["default_zone"] = line.split("=", 1)[1].strip()

            # Parse zones
            zones_dir = "/etc/firewalld/zones"
            if self.file_ops.is_dir(zones_dir):
                zone_files = self.file_ops.ls(zones_dir)
                for zone_file in zone_files:
                    if zone_file.endswith(".xml"):
                        zone_name = zone_file.replace(".xml", "")
                        config["zones"].append(zone_name)

                        # Parse zone file for services
                        zone_content = self.file_ops.cat(f"{zones_dir}/{zone_file}")
                        services = re.findall(r'<service name="([^"]+)"', zone_content)
                        config["services"].extend(services)

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Best-effort config parse; a malformed firewalld config must not abort analysis.
            self.logger.debug(f"Failed to parse firewalld config: {e}")

        return config

    def _parse_ufw(self) -> dict[str, Any]:
        """
        Parse ufw (Uncomplicated Firewall) configuration.

        Reads:
        - /etc/ufw/ufw.conf
        - /etc/ufw/user.rules
        - /etc/ufw/user6.rules

        Returns:
            UFW configuration
        """
        config = {
            "enabled": False,
            "rules": [],
            "default_incoming": None,
            "default_outgoing": None,
        }

        try:
            # Check if enabled
            if self.file_ops.exists("/etc/ufw/ufw.conf"):
                conf = self.file_ops.cat("/etc/ufw/ufw.conf")
                if "ENABLED=yes" in conf:
                    config["enabled"] = True

            # Parse user rules
            if self.file_ops.exists("/etc/ufw/user.rules"):
                rules_content = self.file_ops.cat("/etc/ufw/user.rules")
                rules = self._parse_ufw_rules(rules_content)
                config["rules"].extend(rules)

            # Parse IPv6 rules
            if self.file_ops.exists("/etc/ufw/user6.rules"):
                rules6_content = self.file_ops.cat("/etc/ufw/user6.rules")
                rules6 = self._parse_ufw_rules(rules6_content)
                config["rules"].extend(rules6)

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Best-effort config parse; a malformed ufw config must not abort analysis.
            self.logger.debug(f"Failed to parse ufw config: {e}")

        return config

    def _parse_ufw_rules(self, content: str) -> list[dict[str, Any]]:
        """Parse UFW rules from content."""
        rules = []

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Parse iptables-style rules used by ufw
            if "-A" in line:
                rule = {
                    "raw": line,
                    "action": None,
                    "port": None,
                    "protocol": None,
                }

                # Extract action (ACCEPT, DROP, REJECT)
                if "ACCEPT" in line:
                    rule["action"] = "ACCEPT"
                elif "DROP" in line:
                    rule["action"] = "DROP"
                elif "REJECT" in line:
                    rule["action"] = "REJECT"

                # Extract port
                port_match = re.search(r"--dport (\d+)", line)
                if port_match:
                    rule["port"] = int(port_match.group(1))

                # Extract protocol
                if "-p tcp" in line:
                    rule["protocol"] = "tcp"
                elif "-p udp" in line:
                    rule["protocol"] = "udp"

                rules.append(rule)

        return rules

    def _parse_iptables(self, filepath: str) -> dict[str, Any]:
        """
        Parse iptables rules file.

        Args:
            filepath: Path to iptables rules file

        Returns:
            IPtables configuration
        """
        config = {
            "enabled": True,
            "rules": [],
            "chains": {},
        }

        # The read-file/split-lines/strip/skip-comments opening below mirrors
        # scheduled_tasks.py's crontab parser, but the two parse unrelated formats
        # (iptables chains/rules vs. cron fields) - shared only by coincidental boilerplate.
        # pylint: disable=duplicate-code
        try:
            content = self.file_ops.cat(filepath)

            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
        # pylint: enable=duplicate-code

                # Parse chain policies
                if line.startswith(":"):
                    parts = line.split()
                    if len(parts) >= 3:
                        chain_name = parts[0][1:]  # Remove leading ':'
                        policy = parts[1]
                        config["chains"][chain_name] = policy

                # Parse rules
                elif line.startswith("-A"):
                    rule = self._parse_iptables_rule(line)
                    if rule:
                        config["rules"].append(rule)

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Best-effort config parse; a malformed iptables config must not abort analysis.
            self.logger.debug(f"Failed to parse iptables: {e}")

        return config

    def _parse_iptables_rule(self, line: str) -> dict[str, Any] | None:
        """Parse a single iptables rule."""
        try:
            rule = {
                "raw": line,
                "chain": None,
                "action": None,
                "protocol": None,
                "port": None,
                "source": None,
                "destination": None,
            }

            parts = line.split()

            # Chain
            if len(parts) > 1:
                rule["chain"] = parts[1]

            # Action (-j ACCEPT, -j DROP, etc.)
            if "-j" in parts:
                j_index = parts.index("-j")
                if j_index + 1 < len(parts):
                    rule["action"] = parts[j_index + 1]

            # Protocol
            if "-p" in parts:
                p_index = parts.index("-p")
                if p_index + 1 < len(parts):
                    rule["protocol"] = parts[p_index + 1]

            # Port
            if "--dport" in parts:
                dport_index = parts.index("--dport")
                if dport_index + 1 < len(parts):
                    rule["port"] = parts[dport_index + 1]

            # Source
            if "-s" in parts:
                s_index = parts.index("-s")
                if s_index + 1 < len(parts):
                    rule["source"] = parts[s_index + 1]

            # Destination
            if "-d" in parts:
                d_index = parts.index("-d")
                if d_index + 1 < len(parts):
                    rule["destination"] = parts[d_index + 1]

            return rule

        except Exception:  # pylint: disable=broad-exception-caught
            # Best-effort single-rule parse; a malformed line just yields no parsed rule.
            return None

    def _parse_nftables(self) -> dict[str, Any]:
        """
        Parse nftables configuration.

        Reads:
        - /etc/nftables.conf

        Returns:
            nftables configuration
        """
        config = {
            "enabled": True,
            "rules": [],
            "tables": [],
        }

        try:
            if self.file_ops.exists("/etc/nftables.conf"):
                content = self.file_ops.cat("/etc/nftables.conf")

                # Basic parsing - nftables syntax is complex
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    if line.startswith("table"):
                        parts = line.split()
                        if len(parts) >= 3:
                            config["tables"].append(parts[2])

                    config["rules"].append({"raw": line})

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Best-effort config parse; a malformed nftables config must not abort analysis.
            self.logger.debug(f"Failed to parse nftables: {e}")

        return config

    def _analyze_windows_firewall(self) -> dict[str, Any]:
        """
        Analyze Windows Firewall configuration.

        Windows firewall rules are in:
        - HKLM\\SYSTEM\\CurrentControlSet\\Services\\SharedAccess\\Parameters\\FirewallPolicy

        Returns:
            Windows Firewall configuration
        """
        return {
            "note": "Windows Firewall requires registry parsing",
            "firewall_type": "Windows Firewall",
            "enabled": None,
            "rules": [],
        }

        # Would need registry access to fully implement

    def get_open_ports(self, config: dict[str, Any]) -> list[int]:
        """
        Extract list of open ports from firewall configuration.

        Args:
            config: Firewall configuration dictionary

        Returns:
            List of open port numbers
        """
        open_ports = []

        for rule in config.get("rules", []):
            if rule.get("action") == "ACCEPT" and rule.get("port"):
                try:
                    port = int(rule["port"])
                    if port not in open_ports:
                        open_ports.append(port)
                except (ValueError, TypeError):
                    pass

        return sorted(open_ports)

    def get_blocked_ports(self, config: dict[str, Any]) -> list[int]:
        """
        Extract list of blocked ports from firewall configuration.

        Args:
            config: Firewall configuration dictionary

        Returns:
            List of blocked port numbers
        """
        blocked_ports = []

        for rule in config.get("rules", []):
            if rule.get("action") in ["DROP", "REJECT"] and rule.get("port"):
                try:
                    port = int(rule["port"])
                    if port not in blocked_ports:
                        blocked_ports.append(port)
                except (ValueError, TypeError):
                    pass

        return sorted(blocked_ports)

    def get_firewall_stats(self, config: dict[str, Any]) -> dict[str, Any]:
        """
        Get firewall statistics.

        Args:
            config: Firewall configuration dictionary

        Returns:
            Statistics dictionary
        """
        return {
            "type": config.get("firewall_type"),
            "enabled": config.get("enabled", False),
            "total_rules": len(config.get("rules", [])),
            "open_ports_count": len(self.get_open_ports(config)),
            "blocked_ports_count": len(self.get_blocked_ports(config)),
            "zones_count": len(config.get("zones", [])),
            "services_count": len(config.get("services", [])),
        }
