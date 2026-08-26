# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for h2kvm.platforms.containers.orchestrator module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from h2kvm.platforms.containers.detector import (
    ContainerInfo,
    ContainerRuntime,
)
from h2kvm.platforms.containers.orchestrator import (
    ContainerExtractionOrchestrator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_container(**overrides) -> ContainerInfo:
    """Build a ContainerInfo with sensible defaults; override any field."""
    defaults = dict(
        container_id="abc123",
        name="webapp",
        runtime=ContainerRuntime.DOCKER,
        image="nginx",
        image_tag="1.21",
        running=True,
        ports=[{"container_port": "80/tcp", "host_port": "8080"}],
        volumes=[{"name": "data", "mount_path": "/data"}],
        env_vars={"APP_ENV": "production"},
    )
    defaults.update(overrides)
    return ContainerInfo(**defaults)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_detector():
    return MagicMock()


@pytest.fixture()
def mock_docker_extractor():
    return MagicMock()


@pytest.fixture()
def mock_podman_extractor():
    return MagicMock()


@pytest.fixture()
def mock_k8s_generator():
    return MagicMock()


@pytest.fixture()
def orchestrator(
    mock_logger,
    mock_detector,
    mock_docker_extractor,
    mock_podman_extractor,
    mock_k8s_generator,
):
    """Build an orchestrator with all collaborators mocked out."""
    orch = ContainerExtractionOrchestrator.__new__(ContainerExtractionOrchestrator)
    orch.logger = mock_logger
    orch.detector = mock_detector
    orch.docker_extractor = mock_docker_extractor
    orch.podman_extractor = mock_podman_extractor
    orch.k8s_generator = mock_k8s_generator
    return orch


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    """Tests for ContainerExtractionOrchestrator initialisation."""

    @patch("h2kvm.platforms.containers.orchestrator.KubernetesManifestGenerator")
    @patch("h2kvm.platforms.containers.orchestrator.PodmanExtractor")
    @patch("h2kvm.platforms.containers.orchestrator.DockerExtractor")
    @patch("h2kvm.platforms.containers.orchestrator.ContainerDetector")
    def test_init_creates_collaborators(self, MockDetector, MockDocker, MockPodman, MockK8s, mock_logger):
        orch = ContainerExtractionOrchestrator(mock_logger)
        MockDetector.assert_called_once_with(mock_logger)
        MockDocker.assert_called_once_with(mock_logger)
        MockPodman.assert_called_once_with(mock_logger)
        MockK8s.assert_called_once_with(mock_logger)
        assert orch.logger is mock_logger


# ---------------------------------------------------------------------------
# extract_containers
# ---------------------------------------------------------------------------


class TestExtractContainers:
    """Tests for ContainerExtractionOrchestrator.extract_containers."""

    def test_no_runtime_detected(self, orchestrator, mock_detector, mock_vmcraft, tmp_path):
        mock_detector.detect_containers.return_value = (None, [])

        result = orchestrator.extract_containers(mock_vmcraft, tmp_path)

        assert result["success"] is True
        assert any("No container runtime" in w for w in result["warnings"])
        assert result["containers_found"] == 0

    def test_no_containers_found(self, orchestrator, mock_detector, mock_vmcraft, tmp_path):
        mock_detector.detect_containers.return_value = (ContainerRuntime.DOCKER, [])

        result = orchestrator.extract_containers(mock_vmcraft, tmp_path)

        assert result["success"] is True
        assert result["runtime_detected"] == "docker"
        assert result["containers_found"] == 0
        assert any("no containers found" in w.lower() for w in result["warnings"])

    def test_kubernetes_target_calls_extract_for_kubernetes(
        self, orchestrator, mock_detector, mock_vmcraft, tmp_path
    ):
        container = _make_container()
        mock_detector.detect_containers.return_value = (ContainerRuntime.DOCKER, [container])

        # Stub internal method
        orchestrator._extract_for_kubernetes = Mock(
            return_value={"success": True, "containers_extracted": 1, "manifests_generated": []}
        )

        result = orchestrator.extract_containers(mock_vmcraft, tmp_path, target_platform="kubernetes")

        orchestrator._extract_for_kubernetes.assert_called_once()
        assert result["success"] is True

    def test_docker_target_calls_extract_for_docker(
        self, orchestrator, mock_detector, mock_vmcraft, tmp_path
    ):
        container = _make_container()
        mock_detector.detect_containers.return_value = (ContainerRuntime.DOCKER, [container])

        orchestrator._extract_for_docker = Mock(
            return_value={"success": True, "containers_extracted": 1, "manifests_generated": []}
        )

        result = orchestrator.extract_containers(mock_vmcraft, tmp_path, target_platform="docker")

        orchestrator._extract_for_docker.assert_called_once()
        assert result["success"] is True

    def test_unsupported_platform(self, orchestrator, mock_detector, mock_vmcraft, tmp_path):
        container = _make_container()
        mock_detector.detect_containers.return_value = (ContainerRuntime.DOCKER, [container])

        result = orchestrator.extract_containers(mock_vmcraft, tmp_path, target_platform="lxd")

        assert result["success"] is False
        assert any("Unsupported target platform" in e for e in result["errors"])

    def test_exception_handled(self, orchestrator, mock_detector, mock_vmcraft, tmp_path):
        mock_detector.detect_containers.side_effect = RuntimeError("disk read error")

        result = orchestrator.extract_containers(mock_vmcraft, tmp_path)

        assert result["success"] is False
        assert any("disk read error" in e for e in result["errors"])

    def test_result_structure_has_expected_keys(self, orchestrator, mock_detector, mock_vmcraft, tmp_path):
        mock_detector.detect_containers.return_value = (None, [])

        result = orchestrator.extract_containers(mock_vmcraft, tmp_path)

        expected_keys = {
            "success",
            "runtime_detected",
            "containers_found",
            "containers_extracted",
            "manifests_generated",
            "errors",
            "warnings",
        }
        assert expected_keys.issubset(result.keys())

    def test_output_dir_created(self, orchestrator, mock_detector, mock_vmcraft, tmp_path):
        output_dir = tmp_path / "nested" / "output"
        mock_detector.detect_containers.return_value = (None, [])

        orchestrator.extract_containers(mock_vmcraft, output_dir)

        assert output_dir.is_dir()

    def test_default_target_platform_is_kubernetes(
        self, orchestrator, mock_detector, mock_vmcraft, tmp_path
    ):
        container = _make_container()
        mock_detector.detect_containers.return_value = (ContainerRuntime.DOCKER, [container])

        orchestrator._extract_for_kubernetes = Mock(
            return_value={"success": True, "containers_extracted": 1, "manifests_generated": []}
        )

        orchestrator.extract_containers(mock_vmcraft, tmp_path)

        orchestrator._extract_for_kubernetes.assert_called_once()


# ---------------------------------------------------------------------------
# generate_migration_guide
# ---------------------------------------------------------------------------


class TestGenerateMigrationGuide:
    """Tests for ContainerExtractionOrchestrator.generate_migration_guide."""

    def test_kubernetes_target_has_migration_steps(self, orchestrator, tmp_path):
        container = _make_container()
        guide = orchestrator.generate_migration_guide(
            [container], ContainerRuntime.DOCKER, "kubernetes", tmp_path
        )
        assert "Kubernetes Migration Steps" in guide

    def test_docker_target_has_migration_steps(self, orchestrator, tmp_path):
        container = _make_container()
        guide = orchestrator.generate_migration_guide(
            [container], ContainerRuntime.DOCKER, "docker", tmp_path
        )
        assert "Docker Migration Steps" in guide

    def test_container_details_section(self, orchestrator, tmp_path):
        container = _make_container(name="my-service")
        guide = orchestrator.generate_migration_guide(
            [container], ContainerRuntime.DOCKER, "kubernetes", tmp_path
        )
        assert "Container Details" in guide
        assert "my-service" in guide

    def test_ports_listed(self, orchestrator, tmp_path):
        container = _make_container(ports=[{"container_port": "80/tcp", "host_port": "8080"}])
        guide = orchestrator.generate_migration_guide(
            [container], ContainerRuntime.DOCKER, "kubernetes", tmp_path
        )
        assert "Exposed Ports" in guide
        assert "8080" in guide
        assert "80/tcp" in guide

    def test_volumes_listed(self, orchestrator, tmp_path):
        container = _make_container(volumes=[{"name": "dbdata", "mount_path": "/var/lib/mysql"}])
        guide = orchestrator.generate_migration_guide(
            [container], ContainerRuntime.DOCKER, "kubernetes", tmp_path
        )
        assert "Volumes" in guide
        assert "dbdata" in guide
        assert "/var/lib/mysql" in guide

    def test_env_vars_mentioned(self, orchestrator, tmp_path):
        container = _make_container(env_vars={"A": "1", "B": "2"})
        guide = orchestrator.generate_migration_guide(
            [container], ContainerRuntime.DOCKER, "kubernetes", tmp_path
        )
        assert "Environment Variables" in guide
        assert "2 configured" in guide

    def test_runtime_mentioned(self, orchestrator, tmp_path):
        container = _make_container(runtime=ContainerRuntime.PODMAN)
        guide = orchestrator.generate_migration_guide(
            [container], ContainerRuntime.PODMAN, "kubernetes", tmp_path
        )
        assert "podman" in guide

    def test_returns_string(self, orchestrator, tmp_path):
        container = _make_container()
        guide = orchestrator.generate_migration_guide(
            [container], ContainerRuntime.DOCKER, "kubernetes", tmp_path
        )
        assert isinstance(guide, str)

    def test_no_ports_section_when_empty(self, orchestrator, tmp_path):
        container = _make_container(ports=[])
        guide = orchestrator.generate_migration_guide(
            [container], ContainerRuntime.DOCKER, "kubernetes", tmp_path
        )
        assert "Exposed Ports" not in guide

    def test_no_volumes_section_when_empty(self, orchestrator, tmp_path):
        container = _make_container(volumes=[])
        guide = orchestrator.generate_migration_guide(
            [container], ContainerRuntime.DOCKER, "kubernetes", tmp_path
        )
        # "Volumes" appears only in the volumes subsection, not elsewhere
        # Ensure the dedicated **Volumes**: label is absent
        assert "**Volumes**:" not in guide
