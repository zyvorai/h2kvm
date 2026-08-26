# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/dependency_mapper.py
"""
Service dependency and network connection mapping.

Provides comprehensive dependency analysis:
- Service dependencies (systemd, init.d)
- Network port listening
- Outbound connections
- Inter-service communication
- Database connections
- API dependencies

Features:
- Service dependency graph
- Port mapping (listening ports)
- Outbound connection tracking
- Database connection detection
- API endpoint discovery
- Dependency visualization data
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging

    from .file_ops import FileOperations


class DependencyMapper:
    """
    Service dependency and network connection mapper.

    Maps service dependencies and network connections.
    """

    def __init__(self, logger: logging.Logger, file_ops: FileOperations, mount_root: Path):
        """
        Initialize dependency mapper.

        Args:
            logger: Logger instance
            file_ops: FileOperations instance
            mount_root: Root directory where guest filesystem is mounted
        """
        self.logger = logger
        self.file_ops = file_ops
        self.mount_root = mount_root

    def map_dependencies(self) -> dict[str, Any]:
        """
        Map dependencies comprehensively.

        Returns:
            Dependency mapping results
        """
        mapping: dict[str, Any] = {
            "services": [],
            "listening_ports": [],
            "service_dependencies": [],
            "network_connections": [],
            "total_services": 0,
            "total_ports": 0,
        }

        # Map systemd services
        services = self._map_systemd_services()
        mapping["services"] = services
        mapping["total_services"] = len(services)

        # Map listening ports
        ports = self._map_listening_ports()
        mapping["listening_ports"] = ports
        mapping["total_ports"] = len(ports)

        # Map service dependencies
        dependencies = self._map_service_dependencies(services)
        mapping["service_dependencies"] = dependencies

        # Detect network connections
        connections = self._detect_network_connections()
        mapping["network_connections"] = connections

        return mapping

    def _map_systemd_services(self) -> list[dict[str, Any]]:
        """Map systemd services."""
        services = []

        # Check for systemd
        if not self.file_ops.is_dir("/etc/systemd/system"):
            return services

        try:  # pylint: disable=too-many-nested-blocks  # best-effort multi-location systemd unit scan
            # List system services
            service_paths = [
                "/etc/systemd/system",
                "/lib/systemd/system",
                "/usr/lib/systemd/system",
            ]

            for service_path in service_paths:
                if not self.file_ops.is_dir(service_path):
                    continue

                try:
                    service_files = self.file_ops.ls(service_path)
                    for service_file in service_files:
                        if service_file.endswith(".service"):
                            full_path = f"{service_path}/{service_file}"
                            service_info = self._parse_systemd_service(full_path)
                            if service_info:
                                services.append(service_info)

                            if len(services) >= 50:  # Limit to 50 services
                                break
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort scan, must not abort over one location's quirk
                    pass

                if len(services) >= 50:
                    break

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort scan, must not abort the whole dependency mapping
            self.logger.debug(f"Failed to map systemd services: {e}")

        return services

    def _parse_systemd_service(self, service_path: str) -> dict[str, Any] | None:
        """Parse a systemd service unit file."""
        try:
            content = self.file_ops.cat(service_path)
            service_name = Path(service_path).name

            service_info = {
                "name": service_name,
                "path": service_path,
                "type": "systemd",
                "description": None,
                "requires": [],
                "wants": [],
                "after": [],
                "before": [],
            }

            for line in content.splitlines():
                line = line.strip()

                if line.startswith("Description="):
                    service_info["description"] = line.split("=", 1)[1]
                elif line.startswith("Requires="):
                    deps = line.split("=", 1)[1].split()
                    service_info["requires"].extend(deps)
                elif line.startswith("Wants="):
                    deps = line.split("=", 1)[1].split()
                    service_info["wants"].extend(deps)
                elif line.startswith("After="):
                    deps = line.split("=", 1)[1].split()
                    service_info["after"].extend(deps)
                elif line.startswith("Before="):
                    deps = line.split("=", 1)[1].split()
                    service_info["before"].extend(deps)

            return service_info

        except Exception:  # pylint: disable=broad-exception-caught  # best-effort unit file parse, must not abort the whole scan
            return None

    def _map_listening_ports(self) -> list[dict[str, Any]]:
        """Map listening network ports."""
        ports = []

        # Try to read configuration files for common services
        service_ports = {
            "/etc/ssh/sshd_config": {"service": "ssh", "default_port": 22},
            "/etc/apache2/ports.conf": {"service": "apache", "default_port": 80},
            "/etc/nginx/nginx.conf": {"service": "nginx", "default_port": 80},
            "/etc/mysql/my.cnf": {"service": "mysql", "default_port": 3306},
            "/etc/postgresql/*/main/postgresql.conf": {"service": "postgresql", "default_port": 5432},
        }

        for config_path, info in service_ports.items():
            if "*" in config_path:
                # Handle wildcard paths
                base_path = config_path.split("*", maxsplit=1)[0]
                if self.file_ops.is_dir(base_path):
                    # Just use default port for wildcard paths
                    ports.append(
                        {
                            "port": info["default_port"],
                            "service": info["service"],
                            "protocol": "tcp",
                            "detected_from": "configuration",
                        }
                    )
            elif self.file_ops.exists(config_path):
                # Try to parse port from config
                detected_port = self._extract_port_from_config(config_path, info["service"])
                if detected_port:
                    ports.append(
                        {
                            "port": detected_port,
                            "service": info["service"],
                            "protocol": "tcp",
                            "detected_from": config_path,
                        }
                    )
                else:
                    # Use default port
                    ports.append(
                        {
                            "port": info["default_port"],
                            "service": info["service"],
                            "protocol": "tcp",
                            "detected_from": "default",
                        }
                    )

        return ports

    def _extract_port_from_config(self, config_path: str, service: str) -> int | None:
        """Extract port number from configuration file."""
        try:
            content = self.file_ops.cat(config_path)

            if service == "ssh":
                for line in content.splitlines():
                    if line.strip().startswith("Port "):
                        port_str = line.strip().split()[1]
                        return int(port_str)

            elif service in ["apache", "nginx"]:
                # Look for Listen directive
                for line in content.splitlines():
                    if "listen" in line.lower():
                        match = re.search(r"(\d+)", line)
                        if match:
                            return int(match.group(1))

            elif service == "mysql":
                for line in content.splitlines():
                    if line.strip().startswith("port"):
                        parts = line.split("=")
                        if len(parts) >= 2:
                            return int(parts[1].strip())

        except Exception:  # pylint: disable=broad-exception-caught  # best-effort port extraction, must not abort the whole scan
            pass

        return None

    def _map_service_dependencies(self, services: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Map service dependencies."""
        dependencies = []

        for service in services:
            service_name = service.get("name")

            # Add Requires dependencies
            for required in service.get("requires", []):
                dependencies.append(
                    {
                        "from": service_name,
                        "to": required,
                        "type": "requires",
                        "strength": "hard",
                    }
                )

            # Add Wants dependencies
            for wanted in service.get("wants", []):
                dependencies.append(
                    {
                        "from": service_name,
                        "to": wanted,
                        "type": "wants",
                        "strength": "soft",
                    }
                )

            # Add ordering dependencies
            for after_service in service.get("after", []):
                dependencies.append(
                    {
                        "from": service_name,
                        "to": after_service,
                        "type": "after",
                        "strength": "ordering",
                    }
                )

        return dependencies

    def _detect_network_connections(self) -> list[dict[str, Any]]:
        """Detect network connections from configuration files."""
        connections = []

        # Database connections
        # Check for database client configs
        db_configs = [
            "/etc/my.cnf",
            "/root/.my.cnf",
        ]

        for config_path in db_configs:
            if self.file_ops.exists(config_path):
                connections.append(
                    {
                        "type": "database",
                        "config": config_path,
                        "note": "Database client configuration detected",
                    }
                )

        # API endpoints (common patterns)
        # Check for curl/wget commands in scripts

        # This would require deep file analysis - simplified for now

        return connections

    def get_dependency_summary(self, mapping: dict[str, Any]) -> dict[str, Any]:
        """
        Get dependency summary.

        Args:
            mapping: Dependency mapping results

        Returns:
            Summary dictionary
        """
        mapping.get("services", [])
        dependencies = mapping.get("service_dependencies", [])

        # Count dependency types
        requires_count = sum(1 for d in dependencies if d.get("type") == "requires")
        wants_count = sum(1 for d in dependencies if d.get("type") == "wants")

        return {
            "total_services": mapping.get("total_services", 0),
            "total_listening_ports": mapping.get("total_ports", 0),
            "total_dependencies": len(dependencies),
            "hard_dependencies": requires_count,
            "soft_dependencies": wants_count,
            "network_connections": len(mapping.get("network_connections", [])),
        }

    def get_service_graph(self, mapping: dict[str, Any]) -> dict[str, Any]:
        """
        Generate service dependency graph data.

        Args:
            mapping: Dependency mapping results

        Returns:
            Graph data structure
        """
        services = mapping.get("services", [])
        dependencies = mapping.get("service_dependencies", [])

        # Build nodes
        nodes = []
        for service in services:
            nodes.append(
                {
                    "id": service.get("name"),
                    "label": service.get("name"),
                    "description": service.get("description"),
                    "type": "service",
                }
            )

        # Build edges
        edges = []
        for dep in dependencies:
            edges.append(
                {
                    "from": dep.get("from"),
                    "to": dep.get("to"),
                    "type": dep.get("type"),
                    "strength": dep.get("strength"),
                }
            )

        return {
            "nodes": nodes,
            "edges": edges,
        }

    def find_critical_services(self, mapping: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Find critical services (most dependencies).

        Args:
            mapping: Dependency mapping results

        Returns:
            List of critical services
        """
        dependencies = mapping.get("service_dependencies", [])

        # Count dependencies per service
        dep_count: dict[str, int] = {}

        for dep in dependencies:
            to_service = dep.get("to", "")
            dep_count[to_service] = dep_count.get(to_service, 0) + 1

        # Sort by dependency count
        critical = []
        for service, count in sorted(dep_count.items(), key=lambda x: x[1], reverse=True):
            if count >= 2:  # Services with 2+ dependents
                critical.append(
                    {
                        "service": service,
                        "dependent_count": count,
                        "criticality": "high" if count >= 5 else "medium",
                    }
                )

        return critical[:10]  # Top 10

    def detect_circular_dependencies(self, _mapping: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Detect circular dependencies.

        Args:
            _mapping: Dependency mapping results (unused; not yet implemented)

        Returns:
            List of circular dependency cycles
        """
        # Simplified circular dependency detection
        # Full implementation would use graph traversal algorithms
        return []

        # This is a placeholder - full implementation would detect cycles

    def get_port_security_analysis(self, mapping: dict[str, Any]) -> dict[str, Any]:
        """
        Analyze port security.

        Args:
            mapping: Dependency mapping results

        Returns:
            Security analysis
        """
        ports = mapping.get("listening_ports", [])

        # Well-known insecure ports
        insecure_ports = {
            21: "FTP (unencrypted)",
            23: "Telnet (unencrypted)",
            80: "HTTP (unencrypted)",
            3306: "MySQL (external access risk)",
            5432: "PostgreSQL (external access risk)",
        }

        issues = []
        for port_info in ports:
            port = port_info.get("port")
            if port in insecure_ports:
                issues.append(
                    {
                        "port": port,
                        "service": port_info.get("service"),
                        "issue": insecure_ports[port],
                        "recommendation": "Use encrypted alternative or restrict access",
                    }
                )

        return {
            "total_listening_ports": len(ports),
            "potential_issues": len(issues),
            "issues": issues,
        }
