# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/containers/podman_extractor.py
"""
Podman container extractor.

Extracts Podman containers from VMs.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .docker_extractor import DockerExtractor

if TYPE_CHECKING:
    from pathlib import Path

    from .detector import ContainerInfo

logger = logging.getLogger(__name__)


class PodmanExtractor(DockerExtractor):
    """
    Podman container extractor.

    Podman is largely compatible with Docker, so we inherit most functionality.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize Podman extractor.

        Args:
            logger: Logger instance
        """
        super().__init__(logger)

    def export_container_image(
        self, vmcraft_instance, container: ContainerInfo, output_dir: Path
    ) -> dict[str, Any]:
        """
        Export Podman container image.

        Args:
            vmcraft_instance: Launched VMCraft instance
            container: Container to export
            output_dir: Directory to save exported image

        Returns:
            Export result dict
        """
        # Podman storage is in different locations:
        # - /var/lib/containers/storage (root)
        # - ~/.local/share/containers/storage (rootless)

        self.logger.info(f"Exporting Podman image: {container.image}:{container.image_tag}")

        # Use parent Docker logic with Podman-specific paths
        return super().export_container_image(vmcraft_instance, container, output_dir)

    def generate_podman_play(self, containers: list[ContainerInfo], output_dir: Path) -> dict[str, Any]:
        """
        Generate Kubernetes YAML for podman play.

        Podman supports podman play kube which uses Kubernetes YAML format.

        Args:
            containers: List of containers
            output_dir: Directory to save play file

        Returns:
            Generation result dict
        """
        from .kubernetes_generator import KubernetesManifestGenerator

        # Use Kubernetes manifest generator for podman play
        k8s_gen = KubernetesManifestGenerator(self.logger)

        result = k8s_gen.generate_deployment(containers, output_dir, deployment_name="podman-deployment")

        if result["success"]:
            self.logger.info(f"Generated podman play YAML: {result.get('manifest_file')}")

        return result
