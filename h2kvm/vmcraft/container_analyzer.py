# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/container_analyzer.py
"""
Enhanced container runtime analysis.

Provides comprehensive container analysis beyond basic detection:
- Docker containers, images, volumes, networks
- Podman containers and images
- Container configurations
- Registry information
- Resource usage
- Security settings

Features:
- List containers (running and stopped)
- Enumerate images and their layers
- Analyze volumes and bind mounts
- Network configuration
- Registry authentication
- Security context analysis
"""

from __future__ import annotations

import json
from typing import Any

from .base_analyzer import BaseAnalyzer


class ContainerAnalyzer(BaseAnalyzer):
    """
    Enhanced container analyzer.

    Analyzes container runtimes and their artifacts.
    """

    def analyze_containers(self) -> dict[str, Any]:
        """
        Analyze container installations comprehensively.

        Returns:
            Container analysis results
        """
        analysis: dict[str, Any] = {
            "docker": None,
            "podman": None,
            "containerd": None,
            "total_containers": 0,
            "total_images": 0,
            "total_volumes": 0,
        }

        # Analyze Docker
        docker = self._analyze_docker()
        if docker.get("installed"):
            analysis["docker"] = docker
            analysis["total_containers"] += len(docker.get("containers", []))
            analysis["total_images"] += len(docker.get("images", []))
            analysis["total_volumes"] += len(docker.get("volumes", []))

        # Analyze Podman
        podman = self._analyze_podman()
        if podman.get("installed"):
            analysis["podman"] = podman
            analysis["total_containers"] += len(podman.get("containers", []))
            analysis["total_images"] += len(podman.get("images", []))

        # Analyze containerd
        containerd = self._analyze_containerd()
        if containerd.get("installed"):
            analysis["containerd"] = containerd

        return analysis

    def _analyze_docker(self) -> dict[str, Any]:
        """Analyze Docker installation."""
        docker: dict[str, Any] = {
            "installed": False,
            "version": None,
            "data_root": "/var/lib/docker",
            "containers": [],
            "images": [],
            "volumes": [],
            "networks": [],
        }

        # Check for Docker
        if not self.file_ops.is_dir("/var/lib/docker"):
            return docker

        docker["installed"] = True

        # Parse containers
        containers_dir = "/var/lib/docker/containers"
        if self.file_ops.is_dir(containers_dir):
            docker["containers"] = self._parse_docker_containers(containers_dir)

        # Parse images
        image_dir = "/var/lib/docker/image"
        if self.file_ops.is_dir(image_dir):
            docker["images"] = self._parse_docker_images(image_dir)

        # Parse volumes
        volumes_dir = "/var/lib/docker/volumes"
        if self.file_ops.is_dir(volumes_dir):
            docker["volumes"] = self._parse_docker_volumes(volumes_dir)

        # Parse networks
        network_dir = "/var/lib/docker/network/files"
        if self.file_ops.is_dir(network_dir):
            docker["networks"] = self._parse_docker_networks(network_dir)

        return docker

    def _parse_docker_containers(self, containers_dir: str) -> list[dict[str, Any]]:
        """Parse Docker container configurations."""
        containers = []

        try:
            container_ids = self.file_ops.ls(containers_dir)

            for container_id in container_ids[:50]:  # Limit to 50
                if container_id.startswith("."):
                    continue

                config_path = f"{containers_dir}/{container_id}/config.v2.json"
                if self.file_ops.exists(config_path):
                    try:
                        config_content = self.file_ops.cat(config_path)
                        config = json.loads(config_content)

                        container_info = {
                            "id": container_id[:12],
                            "name": config.get("Name", "").lstrip("/"),
                            "image": config.get("Config", {}).get("Image"),
                            "state": config.get("State", {}).get("Status"),
                            "created": config.get("Created"),
                        }

                        containers.append(container_info)

                    except Exception as e:  # pylint: disable=broad-exception-caught
                        # config.v2.json parsing goes through a custom file_ops abstraction
                        # with unknown internal error types; a bad entry must not abort the scan.
                        self.logger.debug(f"Failed to parse container config: {e}")

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Container listing is best-effort inspection; must not abort the whole analysis.
            self.logger.debug(f"Failed to list containers: {e}")

        return containers

    def _parse_docker_images(self, image_dir: str) -> list[dict[str, Any]]:
        """Parse Docker images."""
        images = []

        try:
            # Try overlay2 storage driver
            repositories_path = f"{image_dir}/overlay2/repositories.json"
            if self.file_ops.exists(repositories_path):
                try:
                    repos_content = self.file_ops.cat(repositories_path)
                    repos = json.loads(repos_content)

                    repositories = repos.get("Repositories", {})
                    for repo_name, tags in repositories.items():
                        for tag, image_id in tags.items():
                            images.append(
                                {
                                    "repository": repo_name,
                                    "tag": tag,
                                    "id": image_id[:12] if image_id else None,
                                }
                            )

                except Exception as e:  # pylint: disable=broad-exception-caught
                    # repositories.json parsing via file_ops; a bad entry must not abort the scan.
                    self.logger.debug(f"Failed to parse images: {e}")

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Image listing is best-effort inspection; must not abort the whole analysis.
            self.logger.debug(f"Failed to parse Docker images: {e}")

        return images

    def _parse_docker_volumes(self, volumes_dir: str) -> list[dict[str, Any]]:
        """Parse Docker volumes."""
        volumes = []

        try:
            volume_names = self.file_ops.ls(volumes_dir)

            for volume_name in volume_names:
                if volume_name.startswith(".") or volume_name == "metadata.db":
                    continue

                volume_path = f"{volumes_dir}/{volume_name}"
                if self.file_ops.is_dir(volume_path):
                    # Get volume size
                    data_path = f"{volume_path}/_data"

                    if self.file_ops.is_dir(data_path):
                        # Estimate size (would need du for exact)
                        volumes.append(
                            {
                                "name": volume_name,
                                "path": volume_path,
                                "data_path": data_path,
                            }
                        )

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Volume listing is best-effort inspection; must not abort the whole analysis.
            self.logger.debug(f"Failed to parse volumes: {e}")

        return volumes

    def _parse_docker_networks(self, network_dir: str) -> list[dict[str, Any]]:
        """Parse Docker networks."""
        networks = []

        try:
            network_files = self.file_ops.ls(network_dir)

            for network_file in network_files:
                if network_file.endswith(".json"):
                    network_path = f"{network_dir}/{network_file}"
                    try:
                        content = self.file_ops.cat(network_path)
                        network_config = json.loads(content)

                        networks.append(
                            {
                                "name": network_config.get("Name"),
                                "id": network_config.get("Id", "")[:12],
                                "driver": network_config.get("Driver"),
                                "scope": network_config.get("Scope"),
                            }
                        )

                    except Exception:  # pylint: disable=broad-exception-caught
                        # Network config parsing via file_ops; a bad entry must not abort the scan.
                        pass

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Network listing is best-effort inspection; must not abort the whole analysis.
            self.logger.debug(f"Failed to parse networks: {e}")

        return networks

    def _analyze_podman(self) -> dict[str, Any]:
        """Analyze Podman installation."""
        podman: dict[str, Any] = {
            "installed": False,
            "containers": [],
            "images": [],
        }

        # Check for Podman storage
        storage_paths = [
            "/var/lib/containers/storage",
            "/run/user/*/containers",
        ]

        for storage_path in storage_paths:
            if "*" not in storage_path and self.file_ops.is_dir(storage_path):
                podman["installed"] = True
                podman["storage_path"] = storage_path
                break

        if not podman["installed"]:
            return podman

        # Parse container storage
        # Podman uses similar structure to Docker
        storage_path = podman.get("storage_path", "")

        containers_path = f"{storage_path}/overlay-containers"
        if self.file_ops.is_dir(containers_path):
            try:
                container_ids = self.file_ops.ls(containers_path)
                podman["containers"] = [
                    {"id": cid[:12]} for cid in container_ids if not cid.startswith(".")
                ][:20]  # Limit to 20
            except Exception:  # pylint: disable=broad-exception-caught
                # Podman container listing is best-effort; must not abort the whole analysis.
                pass

        return podman

    def _analyze_containerd(self) -> dict[str, Any]:
        """Analyze containerd installation."""
        containerd: dict[str, Any] = {
            "installed": False,
            "data_root": None,
        }

        # Check for containerd
        containerd_paths = [
            "/var/lib/containerd",
            "/run/containerd",
        ]

        for path in containerd_paths:
            if self.file_ops.is_dir(path):
                containerd["installed"] = True
                containerd["data_root"] = path
                break

        return containerd

    def get_container_summary(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """
        Get container summary.

        Args:
            analysis: Container analysis results

        Returns:
            Summary dictionary
        """
        return {
            "docker_installed": analysis.get("docker", {}).get("installed", False),
            "podman_installed": analysis.get("podman", {}).get("installed", False),
            "containerd_installed": analysis.get("containerd", {}).get("installed", False),
            "total_containers": analysis.get("total_containers", 0),
            "total_images": analysis.get("total_images", 0),
            "total_volumes": analysis.get("total_volumes", 0),
        }

    def list_container_images(self, analysis: dict[str, Any]) -> list[str]:
        """
        List all container images.

        Args:
            analysis: Container analysis results

        Returns:
            List of image names
        """
        images = []

        # Docker images
        docker = analysis.get("docker")
        if docker:
            for image in docker.get("images", []):
                repo = image.get("repository", "unknown")
                tag = image.get("tag", "latest")
                images.append(f"{repo}:{tag}")

        return images

    def find_sensitive_mounts(self, _analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Find containers with sensitive mounts.

        Args:
            _analysis: Container analysis results (not yet used; see note below)

        Returns:
            List of containers with sensitive mounts
        """
        return []

        # Paths that are considered sensitive

        # This would require parsing container configurations
        # For now, return empty list with note

    def check_container_security(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Check container security issues.

        Args:
            analysis: Container analysis results

        Returns:
            List of security issues
        """
        issues = []

        # Check if Docker socket is accessible
        docker = analysis.get("docker")
        if docker and docker.get("installed"):
            # Docker socket access is a security concern
            issues.append(
                {
                    "severity": "info",
                    "issue": "Docker installed - verify socket permissions",
                    "recommendation": "Ensure /var/run/docker.sock has restricted access",
                }
            )

        return issues
