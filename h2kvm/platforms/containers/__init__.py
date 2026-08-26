# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/containers/__init__.py
"""
Container extraction from VMs.

Extracts containerized workloads from VMs for migration to:
- Kubernetes clusters
- Docker environments
- Podman
- Container registries

Features:
- Docker container detection and extraction
- Podman container detection
- Kubernetes manifest generation
- Docker Compose to Kubernetes conversion
- Container image export
- Volume mapping for persistent data
- Network configuration translation
"""

from .detector import ContainerDetector, ContainerInfo, ContainerRuntime
from .docker_extractor import DockerExtractor
from .kubernetes_generator import KubernetesManifestGenerator
from .orchestrator import ContainerExtractionOrchestrator
from .podman_extractor import PodmanExtractor

__all__ = [
    "ContainerDetector",
    "ContainerExtractionOrchestrator",
    "ContainerInfo",
    "ContainerRuntime",
    "DockerExtractor",
    "KubernetesManifestGenerator",
    "PodmanExtractor",
]
