# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/containers/kubernetes_generator.py
"""
Kubernetes manifest generator.

Generates Kubernetes YAML manifests from container configurations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .detector import ContainerInfo

logger = logging.getLogger(__name__)


class KubernetesManifestGenerator:
    """
    Kubernetes manifest generator.

    Converts container configurations to Kubernetes manifests.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize Kubernetes generator.

        Args:
            logger: Logger instance
        """
        self.logger = logger

    def generate_deployment(
        self,
        containers: list[ContainerInfo],
        output_dir: Path,
        deployment_name: str = "app-deployment",
        namespace: str = "default",
        replicas: int = 1,
    ) -> dict[str, Any]:
        """
        Generate Kubernetes Deployment manifest.

        Args:
            containers: List of containers
            output_dir: Directory to save manifest
            deployment_name: Deployment name
            namespace: Kubernetes namespace
            replicas: Number of replicas

        Returns:
            Generation result dict
        """
        result = {"success": False, "manifest_file": None, "errors": []}

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        manifest_file = output_dir / f"deployment-{deployment_name}.yaml"

        try:
            # Build deployment manifest
            deployment = {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": deployment_name, "namespace": namespace},
                "spec": {
                    "replicas": replicas,
                    "selector": {"matchLabels": {"app": deployment_name}},
                    "template": {
                        "metadata": {"labels": {"app": deployment_name}},
                        "spec": {"containers": []},
                    },
                },
            }

            # Convert each container
            for container in containers:
                k8s_container = self._convert_container_to_k8s(container)
                deployment["spec"]["template"]["spec"]["containers"].append(k8s_container)

            # Convert to YAML
            yaml_content = self._dict_to_yaml(deployment)

            # Write manifest
            manifest_file.write_text(yaml_content)

            result["success"] = True
            result["manifest_file"] = str(manifest_file)

            self.logger.info(f"Generated Kubernetes Deployment: {manifest_file}")

        except Exception as e:
            result["errors"].append(str(e))
            self.logger.exception(f"Failed to generate Deployment: {e}")

        return result

    def generate_service(
        self,
        container: ContainerInfo,
        output_dir: Path,
        service_name: str | None = None,
        namespace: str = "default",
        service_type: str = "ClusterIP",
    ) -> dict[str, Any]:
        """
        Generate Kubernetes Service manifest.

        Args:
            container: Container with exposed ports
            output_dir: Directory to save manifest
            service_name: Service name (defaults to container name)
            namespace: Kubernetes namespace
            service_type: Service type (ClusterIP, NodePort, LoadBalancer)

        Returns:
            Generation result dict
        """
        result = {"success": False, "manifest_file": None, "errors": []}

        if not container.ports:
            result["errors"].append("Container has no exposed ports")
            return result

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        service_name = service_name or container.name
        manifest_file = output_dir / f"service-{service_name}.yaml"

        try:
            # Build service ports
            ports = []
            for i, port_config in enumerate(container.ports):
                container_port_str = port_config.get("container_port", "")
                container_port = int(container_port_str.split("/")[0])

                port_entry = {
                    "name": f"port-{i}",
                    "port": container_port,
                    "targetPort": container_port,
                    "protocol": "TCP",
                }

                # Add nodePort for NodePort service type
                if service_type == "NodePort":
                    host_port = port_config.get("host_port")
                    if host_port and 30000 <= int(host_port) <= 32767:
                        port_entry["nodePort"] = int(host_port)

                ports.append(port_entry)

            # Build service manifest
            service = {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {"name": service_name, "namespace": namespace},
                "spec": {"type": service_type, "selector": {"app": service_name}, "ports": ports},
            }

            # Convert to YAML
            yaml_content = self._dict_to_yaml(service)

            # Write manifest
            manifest_file.write_text(yaml_content)

            result["success"] = True
            result["manifest_file"] = str(manifest_file)

            self.logger.info(f"Generated Kubernetes Service: {manifest_file}")

        except Exception as e:
            result["errors"].append(str(e))
            self.logger.exception(f"Failed to generate Service: {e}")

        return result

    def generate_configmap(
        self,
        container: ContainerInfo,
        output_dir: Path,
        configmap_name: str | None = None,
        namespace: str = "default",
    ) -> dict[str, Any]:
        """
        Generate Kubernetes ConfigMap from environment variables.

        Args:
            container: Container with environment variables
            output_dir: Directory to save manifest
            configmap_name: ConfigMap name
            namespace: Kubernetes namespace

        Returns:
            Generation result dict
        """
        result = {"success": False, "manifest_file": None, "errors": []}

        if not container.env_vars:
            result["errors"].append("Container has no environment variables")
            return result

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        configmap_name = configmap_name or f"{container.name}-config"
        manifest_file = output_dir / f"configmap-{configmap_name}.yaml"

        try:
            # Build ConfigMap
            configmap = {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {"name": configmap_name, "namespace": namespace},
                "data": container.env_vars,
            }

            # Convert to YAML
            yaml_content = self._dict_to_yaml(configmap)

            # Write manifest
            manifest_file.write_text(yaml_content)

            result["success"] = True
            result["manifest_file"] = str(manifest_file)

            self.logger.info(f"Generated Kubernetes ConfigMap: {manifest_file}")

        except Exception as e:
            result["errors"].append(str(e))
            self.logger.exception(f"Failed to generate ConfigMap: {e}")

        return result

    def generate_persistent_volume_claim(
        self,
        container: ContainerInfo,
        output_dir: Path,
        namespace: str = "default",
        storage_class: str = "standard",
    ) -> dict[str, Any]:
        """
        Generate PersistentVolumeClaim for container volumes.

        Args:
            container: Container with volumes
            output_dir: Directory to save manifest
            namespace: Kubernetes namespace
            storage_class: Storage class name

        Returns:
            Generation result dict
        """
        result = {"success": False, "manifest_files": [], "errors": []}

        if not container.volumes:
            result["errors"].append("Container has no volumes")
            return result

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            for volume in container.volumes:
                vol_name = volume.get("name")
                if not vol_name:
                    continue

                pvc_name = f"{container.name}-{vol_name}-pvc"
                manifest_file = output_dir / f"pvc-{pvc_name}.yaml"

                # Build PVC
                pvc = {
                    "apiVersion": "v1",
                    "kind": "PersistentVolumeClaim",
                    "metadata": {"name": pvc_name, "namespace": namespace},
                    "spec": {
                        "accessModes": ["ReadWriteOnce"],
                        "storageClassName": storage_class,
                        "resources": {
                            "requests": {
                                "storage": "1Gi"  # Default size
                            }
                        },
                    },
                }

                # Convert to YAML
                yaml_content = self._dict_to_yaml(pvc)

                # Write manifest
                manifest_file.write_text(yaml_content)

                result["manifest_files"].append(str(manifest_file))

                self.logger.info(f"Generated PersistentVolumeClaim: {manifest_file}")

            result["success"] = True

        except Exception as e:
            result["errors"].append(str(e))
            self.logger.exception(f"Failed to generate PVC: {e}")

        return result

    def _convert_container_to_k8s(self, container: ContainerInfo) -> dict[str, Any]:
        """
        Convert ContainerInfo to Kubernetes container spec.

        Args:
            container: Container configuration

        Returns:
            Kubernetes container spec dict
        """
        k8s_container = {"name": container.name, "image": f"{container.image}:{container.image_tag}"}

        # Command
        if container.command:
            k8s_container["command"] = container.command

        # Args (from entrypoint)
        if container.entrypoint:
            k8s_container["args"] = container.entrypoint

        # Working directory
        if container.working_dir:
            k8s_container["workingDir"] = container.working_dir

        # Environment variables
        if container.env_vars:
            k8s_container["env"] = [
                {"name": key, "value": value} for key, value in container.env_vars.items()
            ]

        # Ports
        if container.ports:
            k8s_container["ports"] = []
            for port_config in container.ports:
                container_port_str = port_config.get("container_port", "")
                if container_port_str:
                    container_port = int(container_port_str.split("/")[0])
                    k8s_container["ports"].append({"containerPort": container_port, "protocol": "TCP"})

        # Volume mounts
        if container.volumes:
            k8s_container["volumeMounts"] = []
            for volume in container.volumes:
                vol_name = volume.get("name")
                mount_path = volume.get("mount_path")
                if vol_name and mount_path:
                    k8s_container["volumeMounts"].append({"name": vol_name, "mountPath": mount_path})

        # Resources
        if container.memory_limit or container.cpu_shares:
            k8s_container["resources"] = {"limits": {}, "requests": {}}

            if container.memory_limit:
                k8s_container["resources"]["limits"]["memory"] = container.memory_limit
                k8s_container["resources"]["requests"]["memory"] = container.memory_limit

            if container.cpu_shares:
                # Convert Docker CPU shares to Kubernetes CPU units
                cpu_units = str(container.cpu_shares / 1024.0)
                k8s_container["resources"]["limits"]["cpu"] = cpu_units
                k8s_container["resources"]["requests"]["cpu"] = cpu_units

        return k8s_container

    def _dict_to_yaml(self, data: dict | list, indent: int = 0) -> str:
        """
        Simple dict/list to YAML converter.

        Args:
            data: Dictionary or list to convert
            indent: Current indentation level

        Returns:
            YAML string
        """
        lines = []
        indent_str = "  " * indent

        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, dict):
                    if value:  # Non-empty dict
                        lines.append(f"{indent_str}{key}:")
                        lines.append(self._dict_to_yaml(value, indent + 1))
                    else:
                        lines.append(f"{indent_str}{key}: {{}}")
                elif isinstance(value, list):
                    if value:  # Non-empty list
                        lines.append(f"{indent_str}{key}:")
                        lines.append(self._dict_to_yaml(value, indent + 1))
                    else:
                        lines.append(f"{indent_str}{key}: []")
                else:
                    # Escape and quote strings if needed
                    if isinstance(value, str):
                        if any(char in value for char in [":", "#", "@", "`", "|", ">"]):
                            value = f'"{value}"'
                    lines.append(f"{indent_str}{key}: {value}")

        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    # Dict item in list
                    first_key = next(iter(item.keys())) if item else None
                    if first_key:
                        lines.append(f"{indent_str}- {first_key}: {item[first_key]}")
                        for key in list(item.keys())[1:]:
                            lines.append(f"{indent_str}  {key}: {item[key]}")
                else:
                    lines.append(f"{indent_str}- {item}")

        return "\n".join(lines)
