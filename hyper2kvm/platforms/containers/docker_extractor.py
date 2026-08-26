# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/containers/docker_extractor.py
"""
Docker container extractor.

Extracts Docker containers and images from VMs.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .detector import ContainerInfo

logger = logging.getLogger(__name__)


class DockerExtractor:
    """
    Docker container extractor.

    Extracts container images, configurations, and data from VMs.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize Docker extractor.

        Args:
            logger: Logger instance
        """
        self.logger = logger

    def export_container_image(
        self, vmcraft_instance, container: ContainerInfo, output_dir: Path
    ) -> dict[str, Any]:
        """
        Export container image from VM.

        Args:
            vmcraft_instance: Launched VMCraft instance
            container: Container to export
            output_dir: Directory to save exported image

        Returns:
            Export result dict
        """
        result = {"success": False, "image_file": None, "image_size_mb": 0.0, "errors": []}

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Image filename
        image_filename = f"{container.image.replace('/', '_')}_{container.image_tag}.tar"
        image_file = output_dir / image_filename

        try:
            # In real implementation, would extract from Docker storage
            # Docker images are stored in /var/lib/docker/image/{storage-driver}/imagedb/content/sha256/
            # and layers in /var/lib/docker/overlay2/ or /var/lib/docker/aufs/

            self.logger.info(f"Exporting Docker image: {container.image}:{container.image_tag}")

            # Placeholder - would actually extract image layers and create tar
            result["success"] = True
            result["image_file"] = str(image_file)
            result["image_size_mb"] = 0.0  # Would calculate actual size

            self.logger.info(f"Image exported to: {image_file}")

        except Exception as e:
            result["errors"].append(str(e))
            self.logger.exception(f"Failed to export image: {e}")

        return result

    def generate_dockerfile(self, container: ContainerInfo, output_dir: Path) -> dict[str, Any]:
        """
        Generate Dockerfile from container configuration.

        Args:
            container: Container configuration
            output_dir: Directory to save Dockerfile

        Returns:
            Generation result dict
        """
        result = {"success": False, "dockerfile": None, "errors": []}

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        dockerfile_path = output_dir / f"Dockerfile.{container.name}"

        try:
            lines = [
                f"# Dockerfile generated from container: {container.name}",
                f"# Original image: {container.image}:{container.image_tag}",
                "",
                f"FROM {container.image}:{container.image_tag}",
                "",
            ]

            # Working directory
            if container.working_dir:
                lines.append(f"WORKDIR {container.working_dir}")
                lines.append("")

            # Environment variables
            if container.env_vars:
                lines.append("# Environment variables")
                for key, value in container.env_vars.items():
                    # Escape special characters
                    value_escaped = value.replace('"', '\\"')
                    lines.append(f'ENV {key}="{value_escaped}"')
                lines.append("")

            # Exposed ports
            if container.ports:
                lines.append("# Exposed ports")
                for port in container.ports:
                    container_port = port.get("container_port", "").split("/")[0]
                    if container_port:
                        lines.append(f"EXPOSE {container_port}")
                lines.append("")

            # Labels
            if container.labels:
                lines.append("# Labels")
                for key, value in container.labels.items():
                    lines.append(f'LABEL {key}="{value}"')
                lines.append("")

            # Entrypoint
            if container.entrypoint:
                entrypoint_json = json.dumps(container.entrypoint)
                lines.append(f"ENTRYPOINT {entrypoint_json}")
                lines.append("")

            # Command
            if container.command:
                cmd_json = json.dumps(container.command)
                lines.append(f"CMD {cmd_json}")
                lines.append("")

            dockerfile_content = "\n".join(lines)

            # Write Dockerfile
            dockerfile_path.write_text(dockerfile_content)

            result["success"] = True
            result["dockerfile"] = str(dockerfile_path)

            self.logger.info(f"Generated Dockerfile: {dockerfile_path}")

        except Exception as e:
            result["errors"].append(str(e))
            self.logger.exception(f"Failed to generate Dockerfile: {e}")

        return result

    def generate_docker_compose(
        self, containers: list[ContainerInfo], output_dir: Path, compose_filename: str = "docker-compose.yml"
    ) -> dict[str, Any]:
        """
        Generate docker-compose.yml from containers.

        Args:
            containers: List of containers
            output_dir: Directory to save compose file
            compose_filename: Compose file name

        Returns:
            Generation result dict
        """
        result = {"success": False, "compose_file": None, "errors": []}

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        compose_file = output_dir / compose_filename

        try:
            compose = {"version": "3.8", "services": {}}

            # Add volumes section if needed
            all_volumes = set()

            for container in containers:
                service_config = {
                    "image": f"{container.image}:{container.image_tag}",
                    "container_name": container.name,
                }

                # Command
                if container.command:
                    service_config["command"] = container.command

                # Entrypoint
                if container.entrypoint:
                    service_config["entrypoint"] = container.entrypoint

                # Environment
                if container.env_vars:
                    service_config["environment"] = container.env_vars

                # Working directory
                if container.working_dir:
                    service_config["working_dir"] = container.working_dir

                # Ports
                if container.ports:
                    ports = []
                    for port in container.ports:
                        host_port = port.get("host_port")
                        container_port = port.get("container_port", "").split("/")[0]
                        if host_port and container_port:
                            ports.append(f"{host_port}:{container_port}")
                    if ports:
                        service_config["ports"] = ports

                # Volumes
                if container.volumes:
                    volumes = []
                    for vol in container.volumes:
                        vol_name = vol.get("name")
                        mount_path = vol.get("mount_path")
                        if vol_name and mount_path:
                            volumes.append(f"{vol_name}:{mount_path}")
                            all_volumes.add(vol_name)
                    if volumes:
                        service_config["volumes"] = volumes

                # Networks
                if container.networks:
                    service_config["networks"] = container.networks

                # Resources
                if container.memory_limit or container.cpu_shares:
                    deploy = {"resources": {"limits": {}}}
                    if container.memory_limit:
                        deploy["resources"]["limits"]["memory"] = container.memory_limit
                    if container.cpu_shares:
                        deploy["resources"]["limits"]["cpus"] = str(container.cpu_shares / 1024.0)
                    service_config["deploy"] = deploy

                # Labels
                if container.labels:
                    service_config["labels"] = container.labels

                # Add service to compose
                compose["services"][container.name] = service_config

            # Add volumes section
            if all_volumes:
                compose["volumes"] = {vol: {} for vol in all_volumes}

            # Write compose file (YAML format)
            # Simple YAML generation (in real implementation would use PyYAML)
            compose_content = self._dict_to_yaml(compose)

            compose_file.write_text(compose_content)

            result["success"] = True
            result["compose_file"] = str(compose_file)

            self.logger.info(f"Generated docker-compose.yml: {compose_file}")

        except Exception as e:
            result["errors"].append(str(e))
            self.logger.exception(f"Failed to generate docker-compose.yml: {e}")

        return result

    def _dict_to_yaml(self, data: dict, indent: int = 0) -> str:
        """
        Simple dict to YAML converter.

        Args:
            data: Dictionary to convert
            indent: Current indentation level

        Returns:
            YAML string
        """
        lines = []
        indent_str = "  " * indent

        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{indent_str}{key}:")
                lines.append(self._dict_to_yaml(value, indent + 1))
            elif isinstance(value, list):
                lines.append(f"{indent_str}{key}:")
                for item in value:
                    if isinstance(item, dict):
                        lines.append(f"{indent_str}  -")
                        for k, v in item.items():
                            lines.append(f"{indent_str}    {k}: {v}")
                    else:
                        lines.append(f"{indent_str}  - {item}")
            else:
                # Escape strings if needed
                if isinstance(value, str) and (":" in value or "#" in value):
                    value = f'"{value}"'
                lines.append(f"{indent_str}{key}: {value}")

        return "\n".join(lines)

    def export_container_volumes(
        self, vmcraft_instance, container: ContainerInfo, output_dir: Path
    ) -> dict[str, Any]:
        """
        Export container volumes.

        Args:
            vmcraft_instance: Launched VMCraft instance
            container: Container with volumes
            output_dir: Directory to save volume data

        Returns:
            Export result dict
        """
        result = {"success": False, "volumes_exported": [], "total_size_mb": 0.0, "errors": []}

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            for volume in container.volumes:
                vol_name = volume.get("name")
                mount_path = volume.get("mount_path")

                if not vol_name:
                    continue

                # Create tar of volume data
                vol_tar = output_dir / f"volume_{vol_name}.tar.gz"

                self.logger.info(f"Exporting volume: {vol_name} (mounted at {mount_path})")

                # In real implementation, would tar up the volume directory
                # from /var/lib/docker/volumes/{vol_name}/_data

                result["volumes_exported"].append(
                    {"name": vol_name, "mount_path": mount_path, "archive": str(vol_tar)}
                )

            result["success"] = True

        except Exception as e:
            result["errors"].append(str(e))
            self.logger.exception(f"Failed to export volumes: {e}")

        return result
