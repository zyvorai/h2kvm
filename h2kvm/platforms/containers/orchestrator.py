# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/containers/orchestrator.py
"""
Container extraction orchestrator.

Coordinates container detection, extraction, and Kubernetes migration.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .detector import ContainerDetector, ContainerRuntime
from .docker_extractor import DockerExtractor
from .kubernetes_generator import KubernetesManifestGenerator
from .podman_extractor import PodmanExtractor

logger = logging.getLogger(__name__)


class ContainerExtractionOrchestrator:
    """
    Container extraction orchestrator.

    Unified workflow for extracting containers from VMs and migrating to Kubernetes.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize container extraction orchestrator.

        Args:
            logger: Logger instance
        """
        self.logger = logger
        self.detector = ContainerDetector(logger)
        self.docker_extractor = DockerExtractor(logger)
        self.podman_extractor = PodmanExtractor(logger)
        self.k8s_generator = KubernetesManifestGenerator(logger)

    def extract_containers(
        self, vmcraft_instance, output_dir: Path, target_platform: str = "kubernetes"
    ) -> dict[str, Any]:
        """
        Extract containers from VM.

        Args:
            vmcraft_instance: Launched VMCraft instance
            output_dir: Directory for extracted artifacts
            target_platform: Target platform (kubernetes, docker, podman)

        Returns:
            Extraction result dict
        """
        result = {
            "success": False,
            "runtime_detected": None,
            "containers_found": 0,
            "containers_extracted": 0,
            "manifests_generated": [],
            "errors": [],
            "warnings": [],
        }

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Step 1: Detect containers
            self.logger.info("Detecting containers in VM...")
            runtime, containers = self.detector.detect_containers(vmcraft_instance)

            if not runtime:
                result["warnings"].append("No container runtime detected in VM")
                self.logger.warning("No containers found in VM")
                result["success"] = True  # Not an error, just no containers
                return result

            result["runtime_detected"] = runtime.value
            result["containers_found"] = len(containers)

            if not containers:
                result["warnings"].append("Container runtime detected but no containers found")
                result["success"] = True
                return result

            self.logger.info(f"Found {len(containers)} container(s) running on {runtime.value}")

            # Step 2: Extract containers based on target platform
            if target_platform == "kubernetes":
                extraction_result = self._extract_for_kubernetes(
                    vmcraft_instance, runtime, containers, output_dir
                )
            elif target_platform == "docker":
                extraction_result = self._extract_for_docker(
                    vmcraft_instance, runtime, containers, output_dir
                )
            else:
                result["errors"].append(f"Unsupported target platform: {target_platform}")
                return result

            # Merge extraction results
            result.update(extraction_result)
            result["success"] = extraction_result.get("success", False)

        except Exception as e:
            self.logger.exception(f"Container extraction failed: {e}")
            result["errors"].append(str(e))
            result["success"] = False

        return result

    def _extract_for_kubernetes(
        self, vmcraft_instance, runtime: ContainerRuntime, containers: list, output_dir: Path
    ) -> dict[str, Any]:
        """Extract containers for Kubernetes deployment."""
        result = {"success": False, "containers_extracted": 0, "manifests_generated": [], "errors": []}

        try:
            # Select appropriate extractor
            if runtime == ContainerRuntime.DOCKER:
                extractor = self.docker_extractor
            elif runtime == ContainerRuntime.PODMAN:
                extractor = self.podman_extractor
            else:
                result["errors"].append(f"Unsupported runtime: {runtime.value}")
                return result

            # Create subdirectories
            k8s_dir = output_dir / "kubernetes"
            k8s_dir.mkdir(exist_ok=True)

            images_dir = output_dir / "images"
            images_dir.mkdir(exist_ok=True)

            # Process each container
            for container in containers:
                self.logger.info(f"Processing container: {container.name}")

                # Generate Kubernetes manifests
                # 1. Deployment
                deploy_result = self.k8s_generator.generate_deployment(
                    [container], k8s_dir, deployment_name=container.name
                )

                if deploy_result["success"]:
                    result["manifests_generated"].append(deploy_result["manifest_file"])

                # 2. Service (if ports exposed)
                if container.ports:
                    svc_result = self.k8s_generator.generate_service(
                        container, k8s_dir, service_type="ClusterIP"
                    )

                    if svc_result["success"]:
                        result["manifests_generated"].append(svc_result["manifest_file"])

                # 3. ConfigMap (if environment variables)
                if container.env_vars:
                    cm_result = self.k8s_generator.generate_configmap(container, k8s_dir)

                    if cm_result["success"]:
                        result["manifests_generated"].append(cm_result["manifest_file"])

                # 4. PersistentVolumeClaim (if volumes)
                if container.volumes:
                    pvc_result = self.k8s_generator.generate_persistent_volume_claim(container, k8s_dir)

                    if pvc_result["success"]:
                        result["manifests_generated"].extend(pvc_result["manifest_files"])

                # 5. Export container image
                image_result = extractor.export_container_image(vmcraft_instance, container, images_dir)

                if image_result["success"]:
                    self.logger.info(f"Exported image for {container.name}")

                result["containers_extracted"] += 1

            result["success"] = True
            self.logger.info(f"Generated {len(result['manifests_generated'])} Kubernetes manifests")

        except Exception as e:
            result["errors"].append(str(e))
            self.logger.exception(f"Kubernetes extraction failed: {e}")

        return result

    def _extract_for_docker(
        self, vmcraft_instance, runtime: ContainerRuntime, containers: list, output_dir: Path
    ) -> dict[str, Any]:
        """Extract containers for Docker environment."""
        result = {"success": False, "containers_extracted": 0, "manifests_generated": [], "errors": []}

        try:
            # Select appropriate extractor
            if runtime == ContainerRuntime.DOCKER:
                extractor = self.docker_extractor
            elif runtime == ContainerRuntime.PODMAN:
                extractor = self.podman_extractor
            else:
                result["errors"].append(f"Unsupported runtime: {runtime.value}")
                return result

            # Create subdirectories
            docker_dir = output_dir / "docker"
            docker_dir.mkdir(exist_ok=True)

            # Generate docker-compose.yml
            compose_result = extractor.generate_docker_compose(containers, docker_dir)

            if compose_result["success"]:
                result["manifests_generated"].append(compose_result["compose_file"])

            # Generate Dockerfiles for each container
            for container in containers:
                dockerfile_result = extractor.generate_dockerfile(container, docker_dir)

                if dockerfile_result["success"]:
                    result["manifests_generated"].append(dockerfile_result["dockerfile"])

                result["containers_extracted"] += 1

            result["success"] = True

        except Exception as e:
            result["errors"].append(str(e))
            self.logger.exception(f"Docker extraction failed: {e}")

        return result

    def generate_migration_guide(
        self, containers: list, runtime: ContainerRuntime, target_platform: str, output_dir: Path
    ) -> str:
        """
        Generate container migration guide.

        Args:
            containers: List of extracted containers
            runtime: Source container runtime
            target_platform: Target platform
            output_dir: Directory with extracted artifacts

        Returns:
            Markdown-formatted migration guide
        """
        lines = [
            "# Container Migration Guide",
            "",
            f"**Source Runtime**: {runtime.value}",
            f"**Target Platform**: {target_platform}",
            f"**Containers**: {len(containers)}",
            "",
            "---",
            "",
        ]

        if target_platform == "kubernetes":
            lines.extend(
                [
                    "## Kubernetes Migration Steps",
                    "",
                    "### 1. Import Container Images",
                    "",
                    "```bash",
                    "# Import images to container registry",
                    "for img in images/*.tar; do",
                    "    docker load -i $img",
                    "    # Tag and push to your registry",
                    "    # docker tag <image> registry.example.com/<image>",
                    "    # docker push registry.example.com/<image>",
                    "done",
                    "```",
                    "",
                    "### 2. Apply Kubernetes Manifests",
                    "",
                    "```bash",
                    "# Apply all manifests",
                    "kubectl apply -f kubernetes/",
                    "",
                    "# Or apply individually:",
                ]
            )

            # List generated manifests
            for container in containers:
                lines.extend(
                    [
                        f"kubectl apply -f kubernetes/deployment-{container.name}.yaml",
                        f"kubectl apply -f kubernetes/service-{container.name}.yaml",
                    ]
                )

            lines.extend(
                [
                    "```",
                    "",
                    "### 3. Verify Deployment",
                    "",
                    "```bash",
                    "# Check pod status",
                    "kubectl get pods",
                    "",
                    "# Check services",
                    "kubectl get services",
                    "",
                    "# View logs",
                    "kubectl logs -f deployment/<deployment-name>",
                    "```",
                    "",
                ]
            )

        elif target_platform == "docker":
            lines.extend(
                [
                    "## Docker Migration Steps",
                    "",
                    "### 1. Start Containers",
                    "",
                    "```bash",
                    "# Using docker-compose",
                    "cd docker/",
                    "docker-compose up -d",
                    "",
                    "# Or build and run individually:",
                ]
            )

            for container in containers:
                lines.extend(
                    [
                        f"docker build -t {container.image}:{container.image_tag} -f Dockerfile.{container.name} .",
                        f"docker run -d --name {container.name} {container.image}:{container.image_tag}",
                    ]
                )

            lines.extend(
                [
                    "```",
                    "",
                    "### 2. Verify Containers",
                    "",
                    "```bash",
                    "docker ps",
                    "docker logs <container-name>",
                    "```",
                    "",
                ]
            )

        # Container-specific notes
        lines.extend(["## Container Details", ""])

        for container in containers:
            lines.extend(
                [
                    f"### {container.name}",
                    "",
                    f"**Image**: {container.image}:{container.image_tag}",
                    f"**Runtime**: {container.runtime.value}",
                    "",
                ]
            )

            if container.ports:
                lines.append("**Exposed Ports**:")
                for port in container.ports:
                    lines.append(f"- {port.get('host_port')}:{port.get('container_port')}")
                lines.append("")

            if container.volumes:
                lines.append("**Volumes**:")
                for vol in container.volumes:
                    lines.append(f"- {vol.get('name')}: {vol.get('mount_path')}")
                lines.append("")

            if container.env_vars:
                lines.append(f"**Environment Variables**: {len(container.env_vars)} configured")
                lines.append("")

        return "\n".join(lines)
