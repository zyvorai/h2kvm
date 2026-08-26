# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for hyper2kvm.platforms.containers.detector module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, call

import pytest

from hyper2kvm.platforms.containers.detector import (
    ContainerDetector,
    ContainerInfo,
    ContainerRuntime,
)


# ---------------------------------------------------------------------------
# ContainerRuntime enum
# ---------------------------------------------------------------------------


class TestContainerRuntime:
    """Tests for the ContainerRuntime enum."""

    def test_docker_value(self):
        assert ContainerRuntime.DOCKER.value == "docker"

    def test_podman_value(self):
        assert ContainerRuntime.PODMAN.value == "podman"

    def test_containerd_value(self):
        assert ContainerRuntime.CONTAINERD.value == "containerd"

    def test_cri_o_value(self):
        assert ContainerRuntime.CRI_O.value == "crio"

    def test_unknown_value(self):
        assert ContainerRuntime.UNKNOWN.value == "unknown"

    def test_all_members_present(self):
        members = {m.name for m in ContainerRuntime}
        assert members == {"DOCKER", "PODMAN", "CONTAINERD", "CRI_O", "UNKNOWN"}

    def test_unknown_is_a_member(self):
        assert ContainerRuntime.UNKNOWN in ContainerRuntime


# ---------------------------------------------------------------------------
# ContainerInfo dataclass
# ---------------------------------------------------------------------------


class TestContainerInfo:
    """Tests for the ContainerInfo dataclass."""

    def test_required_fields_only(self):
        info = ContainerInfo(
            container_id="abc123",
            name="mycontainer",
            runtime=ContainerRuntime.DOCKER,
            image="nginx",
        )
        assert info.container_id == "abc123"
        assert info.name == "mycontainer"
        assert info.runtime is ContainerRuntime.DOCKER
        assert info.image == "nginx"

    def test_defaults(self):
        info = ContainerInfo(
            container_id="abc",
            name="c",
            runtime=ContainerRuntime.PODMAN,
            image="redis",
        )
        assert info.image_tag == "latest"
        assert info.running is False
        assert info.created_at is None
        assert info.command == []
        assert info.entrypoint == []
        assert info.env_vars == {}
        assert info.working_dir is None
        assert info.network_mode is None
        assert info.networks == []
        assert info.volumes == []
        assert info.mounts == []
        assert info.memory_limit is None
        assert info.cpu_shares is None
        assert info.cpu_quota is None
        assert info.labels == {}
        assert info.metadata == {}

    def test_ports_default_empty(self):
        info = ContainerInfo(
            container_id="x",
            name="x",
            runtime=ContainerRuntime.DOCKER,
            image="x",
        )
        assert info.ports == []

    def test_full_construction(self):
        info = ContainerInfo(
            container_id="abc123456789",
            name="webapp",
            runtime=ContainerRuntime.DOCKER,
            image="myapp",
            image_tag="v2.1",
            running=True,
            created_at="2024-01-01T00:00:00Z",
            command=["python", "app.py"],
            entrypoint=["/entrypoint.sh"],
            env_vars={"DB_HOST": "localhost"},
            working_dir="/app",
            ports=[{"container_port": "8080/tcp", "host_port": "80"}],
            network_mode="bridge",
            networks=["frontend"],
            volumes=[{"name": "data", "mount_path": "/data"}],
            mounts=[{"type": "bind", "source": "/host", "destination": "/cnt"}],
            memory_limit="512m",
            cpu_shares=1024,
            cpu_quota=50000,
            labels={"maintainer": "ops"},
            metadata={"extra": True},
        )
        assert info.image_tag == "v2.1"
        assert info.running is True
        assert info.env_vars == {"DB_HOST": "localhost"}
        assert len(info.ports) == 1
        assert info.memory_limit == "512m"
        assert info.cpu_shares == 1024
        assert info.metadata == {"extra": True}


# ---------------------------------------------------------------------------
# ContainerDetector.detect_containers
# ---------------------------------------------------------------------------


class TestDetectContainers:
    """Tests for ContainerDetector.detect_containers."""

    def test_no_runtime_detected(self, mock_logger, mock_vmcraft):
        """When neither docker nor podman binaries exist, return (None, [])."""
        mock_vmcraft.exists.return_value = False
        detector = ContainerDetector(mock_logger)

        runtime, containers = detector.detect_containers(mock_vmcraft)

        assert runtime is None
        assert containers == []
        mock_logger.info.assert_any_call("No container runtime detected")

    def test_docker_found(self, mock_logger, mock_vmcraft):
        """Docker binary + data dir + one container config."""
        container_id = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6"
        config = {
            "Name": "/myapp",
            "Config": {"Image": "nginx:1.21"},
            "State": {"Running": True},
        }

        def exists_side_effect(path):
            return path in {
                "/usr/bin/docker",
                "/var/lib/docker",
                "/var/lib/docker/containers",
                f"/var/lib/docker/containers/{container_id}/config.v2.json",
            }

        mock_vmcraft.exists.side_effect = exists_side_effect
        mock_vmcraft.is_dir.return_value = True
        mock_vmcraft.ls.return_value = [container_id]
        mock_vmcraft.read_file.return_value = json.dumps(config)

        detector = ContainerDetector(mock_logger)
        runtime, containers = detector.detect_containers(mock_vmcraft)

        assert runtime is ContainerRuntime.DOCKER
        assert len(containers) == 1
        assert containers[0].name == "myapp"
        mock_logger.info.assert_any_call("Detected 1 Docker containers")

    def test_podman_found(self, mock_logger, mock_vmcraft):
        """Podman binary and storage, no Docker."""
        container_id = "f1e2d3c4b5a6f1e2d3c4b5a6"
        config = {
            "name": "redis-server",
            "process": {"args": ["redis-server"], "env": [], "cwd": "/data"},
            "annotations": {},
        }

        def exists_side_effect(path):
            existing = {
                "/usr/bin/podman",
                "/var/lib/containers",
                "/var/lib/containers/overlay-containers",
                f"/var/lib/containers/overlay-containers/{container_id}/userdata/config.json",
            }
            return path in existing

        mock_vmcraft.exists.side_effect = exists_side_effect
        mock_vmcraft.is_dir.return_value = True
        mock_vmcraft.ls.return_value = [container_id]
        mock_vmcraft.read_file.return_value = json.dumps(config)

        detector = ContainerDetector(mock_logger)
        runtime, containers = detector.detect_containers(mock_vmcraft)

        assert runtime is ContainerRuntime.PODMAN
        assert len(containers) == 1
        mock_logger.info.assert_any_call("Detected 1 Podman containers")

    def test_docker_priority_over_podman(self, mock_logger, mock_vmcraft):
        """If Docker is detected, Podman detection is skipped."""
        container_id = "aabbccddee112233"
        config = {
            "Name": "/app",
            "Config": {"Image": "alpine"},
            "State": {"Running": False},
        }

        def exists_side_effect(path):
            return path in {
                "/usr/bin/docker",
                "/usr/bin/podman",
                "/var/lib/docker",
                "/var/lib/docker/containers",
                f"/var/lib/docker/containers/{container_id}/config.v2.json",
            }

        mock_vmcraft.exists.side_effect = exists_side_effect
        mock_vmcraft.is_dir.return_value = True
        mock_vmcraft.ls.return_value = [container_id]
        mock_vmcraft.read_file.return_value = json.dumps(config)

        detector = ContainerDetector(mock_logger)
        runtime, containers = detector.detect_containers(mock_vmcraft)

        assert runtime is ContainerRuntime.DOCKER
        # Podman paths should never be queried for containers
        assert containers[0].runtime is ContainerRuntime.DOCKER

    def test_logging_runtime_value(self, mock_logger, mock_vmcraft):
        """After detecting a runtime, the runtime value is logged."""
        container_id = "0123456789ab"
        config = {
            "Name": "/x",
            "Config": {"Image": "busybox"},
            "State": {},
        }

        def exists_side_effect(path):
            return path in {
                "/usr/bin/docker",
                "/var/lib/docker",
                "/var/lib/docker/containers",
                f"/var/lib/docker/containers/{container_id}/config.v2.json",
            }

        mock_vmcraft.exists.side_effect = exists_side_effect
        mock_vmcraft.is_dir.return_value = True
        mock_vmcraft.ls.return_value = [container_id]
        mock_vmcraft.read_file.return_value = json.dumps(config)

        detector = ContainerDetector(mock_logger)
        detector.detect_containers(mock_vmcraft)

        mock_logger.info.assert_any_call("Detected runtime: docker")


# ---------------------------------------------------------------------------
# ContainerDetector._parse_docker_config
# ---------------------------------------------------------------------------


class TestParseDockerConfig:
    """Tests for ContainerDetector._parse_docker_config."""

    @pytest.fixture()
    def detector(self, mock_logger):
        return ContainerDetector(mock_logger)

    def test_basic_minimal_config(self, detector):
        config = {
            "Name": "/webapp",
            "Config": {"Image": "myapp"},
        }
        info = detector._parse_docker_config("a1b2c3d4e5f6", config)
        assert info.container_id == "a1b2c3d4e5f6"
        assert info.name == "webapp"
        assert info.image == "myapp"
        assert info.runtime is ContainerRuntime.DOCKER

    def test_image_with_tag(self, detector):
        config = {
            "Name": "/web",
            "Config": {"Image": "nginx:1.21"},
        }
        info = detector._parse_docker_config("aabbccddee11", config)
        assert info.image == "nginx"
        assert info.image_tag == "1.21"

    def test_image_no_tag_defaults_latest(self, detector):
        config = {
            "Name": "/web",
            "Config": {"Image": "nginx"},
        }
        info = detector._parse_docker_config("aabbccddee11", config)
        assert info.image == "nginx"
        assert info.image_tag == "latest"

    def test_env_vars_parsed(self, detector):
        config = {
            "Name": "/app",
            "Config": {
                "Image": "app",
                "Env": ["DB_HOST=postgres", "DB_PORT=5432", "NOEQUAL"],
            },
        }
        info = detector._parse_docker_config("aabbccddee11", config)
        assert info.env_vars == {"DB_HOST": "postgres", "DB_PORT": "5432"}

    def test_ports_parsed(self, detector):
        config = {
            "Name": "/app",
            "Config": {"Image": "app"},
            "NetworkSettings": {
                "Ports": {
                    "80/tcp": [{"HostPort": "8080", "HostIp": "0.0.0.0"}],
                    "443/tcp": None,
                }
            },
        }
        info = detector._parse_docker_config("aabbccddee11", config)
        assert len(info.ports) == 1
        assert info.ports[0]["container_port"] == "80/tcp"
        assert info.ports[0]["host_port"] == "8080"
        assert info.ports[0]["host_ip"] == "0.0.0.0"

    def test_volumes_and_mounts_parsed(self, detector):
        config = {
            "Name": "/app",
            "Config": {"Image": "app"},
            "Mounts": [
                {
                    "Type": "volume",
                    "Source": "/var/lib/docker/volumes/data/_data",
                    "Destination": "/data",
                    "Mode": "rw",
                    "RW": True,
                },
                {
                    "Type": "bind",
                    "Source": "/host/path",
                    "Destination": "/container/path",
                    "Mode": "ro",
                    "RW": False,
                },
            ],
        }
        info = detector._parse_docker_config("aabbccddee11", config)
        assert len(info.mounts) == 2
        assert len(info.volumes) == 1
        assert info.volumes[0]["name"] == "_data"
        assert info.volumes[0]["mount_path"] == "/data"

    def test_resources_parsed(self, detector):
        config = {
            "Name": "/app",
            "Config": {"Image": "app"},
            "HostConfig": {
                "Memory": 536870912,
                "CpuShares": 512,
                "CpuQuota": 50000,
            },
        }
        info = detector._parse_docker_config("aabbccddee11", config)
        assert info.memory_limit == "536870912"
        assert info.cpu_shares == 512
        assert info.cpu_quota == 50000

    def test_running_state(self, detector):
        config = {
            "Name": "/app",
            "Config": {"Image": "app"},
            "State": {"Running": True},
        }
        info = detector._parse_docker_config("aabbccddee11", config)
        assert info.running is True

    def test_stopped_state(self, detector):
        config = {
            "Name": "/app",
            "Config": {"Image": "app"},
            "State": {"Running": False},
        }
        info = detector._parse_docker_config("aabbccddee11", config)
        assert info.running is False

    def test_container_id_truncated(self, detector):
        long_id = "a" * 64
        config = {"Name": "/x", "Config": {"Image": "img"}}
        info = detector._parse_docker_config(long_id, config)
        assert info.container_id == "a" * 12

    def test_name_leading_slash_stripped(self, detector):
        config = {"Name": "/leading-slash", "Config": {"Image": "img"}}
        info = detector._parse_docker_config("aabbccddee11", config)
        assert info.name == "leading-slash"

    def test_networks_parsed(self, detector):
        config = {
            "Name": "/app",
            "Config": {"Image": "app"},
            "NetworkSettings": {
                "Networks": {"bridge": {}, "custom_net": {}},
            },
        }
        info = detector._parse_docker_config("aabbccddee11", config)
        assert set(info.networks) == {"bridge", "custom_net"}

    def test_labels_parsed(self, detector):
        config = {
            "Name": "/app",
            "Config": {
                "Image": "app",
                "Labels": {"com.example.version": "1.0"},
            },
        }
        info = detector._parse_docker_config("aabbccddee11", config)
        assert info.labels == {"com.example.version": "1.0"}

    def test_created_at(self, detector):
        config = {
            "Name": "/app",
            "Config": {"Image": "app"},
            "Created": "2024-06-15T10:30:00Z",
        }
        info = detector._parse_docker_config("aabbccddee11", config)
        assert info.created_at == "2024-06-15T10:30:00Z"


# ---------------------------------------------------------------------------
# ContainerDetector._parse_podman_config
# ---------------------------------------------------------------------------


class TestParsePodmanConfig:
    """Tests for ContainerDetector._parse_podman_config."""

    @pytest.fixture()
    def detector(self, mock_logger):
        return ContainerDetector(mock_logger)

    def test_basic_oci_format(self, detector):
        config = {
            "name": "myredis",
            "process": {"args": ["redis-server"], "env": [], "cwd": "/data"},
            "annotations": {},
        }
        info = detector._parse_podman_config("f1e2d3c4b5a6", config)
        assert info.container_id == "f1e2d3c4b5a6"
        assert info.name == "myredis"
        assert info.runtime is ContainerRuntime.PODMAN
        assert info.command == ["redis-server"]

    def test_env_vars_parsed(self, detector):
        config = {
            "name": "app",
            "process": {
                "args": [],
                "env": ["HOME=/root", "PATH=/usr/bin"],
                "cwd": "/",
            },
            "annotations": {},
        }
        info = detector._parse_podman_config("aabbccddee11", config)
        assert info.env_vars == {"HOME": "/root", "PATH": "/usr/bin"}

    def test_mounts_parsed(self, detector):
        config = {
            "name": "app",
            "process": {"args": [], "env": [], "cwd": "/"},
            "annotations": {},
            "mounts": [
                {
                    "type": "bind",
                    "source": "/host/data",
                    "destination": "/data",
                    "options": ["rw", "rbind"],
                },
            ],
        }
        info = detector._parse_podman_config("aabbccddee11", config)
        assert len(info.mounts) == 1
        assert info.mounts[0]["source"] == "/host/data"
        assert info.mounts[0]["rw"] is True

    def test_resources_from_linux_section(self, detector):
        config = {
            "name": "app",
            "process": {"args": [], "env": [], "cwd": "/"},
            "annotations": {},
            "linux": {
                "resources": {
                    "memory": {"limit": 268435456},
                    "cpu": {"shares": 256, "quota": 100000},
                }
            },
        }
        info = detector._parse_podman_config("aabbccddee11", config)
        assert info.memory_limit == "268435456"
        assert info.cpu_shares == 256
        assert info.cpu_quota == 100000

    def test_name_strips_leading_slash(self, detector):
        config = {
            "name": "/slashed-name",
            "process": {"args": [], "env": [], "cwd": "/"},
            "annotations": {},
        }
        info = detector._parse_podman_config("aabbccddee11", config)
        assert info.name == "slashed-name"

    def test_entrypoint_empty_for_podman(self, detector):
        config = {
            "name": "app",
            "process": {"args": ["sh"], "env": [], "cwd": "/"},
            "annotations": {},
        }
        info = detector._parse_podman_config("aabbccddee11", config)
        assert info.entrypoint == []


# ---------------------------------------------------------------------------
# ContainerDetector.detect_docker_compose
# ---------------------------------------------------------------------------


class TestDetectDockerCompose:
    """Tests for ContainerDetector.detect_docker_compose."""

    @pytest.fixture()
    def detector(self, mock_logger):
        return ContainerDetector(mock_logger)

    def test_compose_found(self, detector, mock_vmcraft):
        def exists_side_effect(path):
            return path in {"/opt", "/opt/docker-compose.yml"}

        mock_vmcraft.exists.side_effect = exists_side_effect

        result = detector.detect_docker_compose(mock_vmcraft)

        assert len(result) == 1
        assert result[0] == Path("/opt/docker-compose.yml")

    def test_compose_not_found(self, detector, mock_vmcraft):
        mock_vmcraft.exists.return_value = False

        result = detector.detect_docker_compose(mock_vmcraft)

        assert result == []

    def test_multiple_compose_filenames_checked(self, detector, mock_vmcraft):
        """All canonical compose filenames are searched."""
        found_paths = {
            "/srv",
            "/srv/docker-compose.yml",
            "/srv/compose.yaml",
        }

        def exists_side_effect(path):
            return path in found_paths

        mock_vmcraft.exists.side_effect = exists_side_effect

        result = detector.detect_docker_compose(mock_vmcraft)

        assert len(result) == 2
        paths = {str(p) for p in result}
        assert "/srv/docker-compose.yml" in paths
        assert "/srv/compose.yaml" in paths

    def test_compose_across_multiple_directories(self, detector, mock_vmcraft):
        found_paths = {
            "/opt",
            "/opt/docker-compose.yml",
            "/home",
            "/home/compose.yml",
        }

        def exists_side_effect(path):
            return path in found_paths

        mock_vmcraft.exists.side_effect = exists_side_effect

        result = detector.detect_docker_compose(mock_vmcraft)

        assert len(result) == 2


# ---------------------------------------------------------------------------
# ContainerDetector.get_container_summary
# ---------------------------------------------------------------------------


class TestGetContainerSummary:
    """Tests for ContainerDetector.get_container_summary."""

    @pytest.fixture()
    def detector(self, mock_logger):
        return ContainerDetector(mock_logger)

    def test_empty_list(self, detector):
        summary = detector.get_container_summary([])
        assert summary["total_containers"] == 0
        assert summary["by_runtime"] == {}
        assert summary["by_image"] == {}
        assert summary["running_count"] == 0
        assert summary["stopped_count"] == 0
        assert summary["exposed_ports"] == []

    def test_counts_by_runtime(self, detector):
        containers = [
            ContainerInfo(container_id="a", name="a", runtime=ContainerRuntime.DOCKER, image="nginx"),
            ContainerInfo(container_id="b", name="b", runtime=ContainerRuntime.DOCKER, image="redis"),
            ContainerInfo(container_id="c", name="c", runtime=ContainerRuntime.PODMAN, image="postgres"),
        ]
        summary = detector.get_container_summary(containers)
        assert summary["by_runtime"]["docker"] == 2
        assert summary["by_runtime"]["podman"] == 1

    def test_counts_by_image(self, detector):
        containers = [
            ContainerInfo(
                container_id="a",
                name="a",
                runtime=ContainerRuntime.DOCKER,
                image="nginx",
                image_tag="1.21",
            ),
            ContainerInfo(
                container_id="b",
                name="b",
                runtime=ContainerRuntime.DOCKER,
                image="nginx",
                image_tag="1.21",
            ),
            ContainerInfo(
                container_id="c",
                name="c",
                runtime=ContainerRuntime.DOCKER,
                image="redis",
                image_tag="7",
            ),
        ]
        summary = detector.get_container_summary(containers)
        assert summary["by_image"]["nginx:1.21"] == 2
        assert summary["by_image"]["redis:7"] == 1

    def test_ports_collected(self, detector):
        containers = [
            ContainerInfo(
                container_id="a",
                name="a",
                runtime=ContainerRuntime.DOCKER,
                image="nginx",
                ports=[{"host_port": "8080", "container_port": "80/tcp"}],
            ),
        ]
        summary = detector.get_container_summary(containers)
        assert "8080:80/tcp" in summary["exposed_ports"]

    def test_running_and_stopped_counts(self, detector):
        containers = [
            ContainerInfo(
                container_id="a",
                name="a",
                runtime=ContainerRuntime.DOCKER,
                image="nginx",
                running=True,
            ),
            ContainerInfo(
                container_id="b",
                name="b",
                runtime=ContainerRuntime.DOCKER,
                image="redis",
                running=False,
            ),
            ContainerInfo(
                container_id="c",
                name="c",
                runtime=ContainerRuntime.DOCKER,
                image="postgres",
                running=True,
            ),
        ]
        summary = detector.get_container_summary(containers)
        assert summary["running_count"] == 2
        assert summary["stopped_count"] == 1

    def test_total_volumes(self, detector):
        containers = [
            ContainerInfo(
                container_id="a",
                name="a",
                runtime=ContainerRuntime.DOCKER,
                image="app",
                volumes=[
                    {"name": "v1", "mount_path": "/v1"},
                    {"name": "v2", "mount_path": "/v2"},
                ],
            ),
            ContainerInfo(
                container_id="b",
                name="b",
                runtime=ContainerRuntime.DOCKER,
                image="db",
                volumes=[{"name": "v3", "mount_path": "/v3"}],
            ),
        ]
        summary = detector.get_container_summary(containers)
        assert summary["total_volumes"] == 3

    def test_total_containers(self, detector):
        containers = [
            ContainerInfo(container_id="a", name="a", runtime=ContainerRuntime.DOCKER, image="x"),
            ContainerInfo(container_id="b", name="b", runtime=ContainerRuntime.DOCKER, image="y"),
        ]
        summary = detector.get_container_summary(containers)
        assert summary["total_containers"] == 2
