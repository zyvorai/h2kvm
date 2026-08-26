# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for hyper2kvm.vmcraft.container_analyzer.ContainerAnalyzer."""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from hyper2kvm.vmcraft.container_analyzer import ContainerAnalyzer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_analyzer(mock_logger, mock_file_ops, mock_mount_root):
    """Convenience: build a ContainerAnalyzer with the given mocks."""
    return ContainerAnalyzer(mock_logger, mock_file_ops, mock_mount_root)


def _docker_config(name="myapp", image="nginx:latest", status="running", created="2024-01-01"):
    """Return a JSON string representing a minimal Docker container config."""
    return json.dumps(
        {
            "Name": f"/{name}",
            "Config": {"Image": image},
            "State": {"Status": status},
            "Created": created,
        }
    )


# ===========================================================================
# analyze_containers
# ===========================================================================


class TestAnalyzeContainers:
    """Top-level analyze_containers() entry point."""

    def test_no_containers_all_false(self, mock_logger, mock_file_ops, mock_mount_root):
        """When no runtime dirs exist the result should have all None / zero."""
        mock_file_ops.is_dir.return_value = False
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        result = ca.analyze_containers()
        assert result["docker"] is None
        assert result["podman"] is None
        assert result["containerd"] is None
        assert result["total_containers"] == 0
        assert result["total_images"] == 0
        assert result["total_volumes"] == 0

    def test_docker_installed(self, mock_logger, mock_file_ops, mock_mount_root):
        """Docker detected when /var/lib/docker exists."""
        mock_file_ops.is_dir.side_effect = lambda p: p == "/var/lib/docker"
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        result = ca.analyze_containers()
        assert result["docker"] is not None
        assert result["docker"]["installed"] is True
        assert result["podman"] is None

    def test_podman_installed(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.is_dir.side_effect = lambda p: p == "/var/lib/containers/storage"
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        result = ca.analyze_containers()
        assert result["podman"] is not None
        assert result["podman"]["installed"] is True

    def test_containerd_installed(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.is_dir.side_effect = lambda p: p == "/var/lib/containerd"
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        result = ca.analyze_containers()
        assert result["containerd"] is not None
        assert result["containerd"]["installed"] is True

    def test_docker_with_containers_updates_totals(self, mock_logger, mock_file_ops, mock_mount_root):
        cid = "a" * 64
        dirs_that_exist = {
            "/var/lib/docker",
            "/var/lib/docker/containers",
        }
        mock_file_ops.is_dir.side_effect = lambda p: p in dirs_that_exist
        mock_file_ops.ls.return_value = [cid]
        mock_file_ops.exists.return_value = True
        mock_file_ops.cat.return_value = _docker_config()
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        result = ca.analyze_containers()
        assert result["total_containers"] == 1

    def test_multiple_runtimes_detected(self, mock_logger, mock_file_ops, mock_mount_root):
        dirs = {"/var/lib/docker", "/var/lib/containers/storage", "/var/lib/containerd"}
        mock_file_ops.is_dir.side_effect = lambda p: p in dirs
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        result = ca.analyze_containers()
        assert result["docker"] is not None
        assert result["podman"] is not None
        assert result["containerd"] is not None


# ===========================================================================
# _analyze_docker
# ===========================================================================


class TestAnalyzeDocker:
    def test_not_installed(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.is_dir.return_value = False
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        result = ca._analyze_docker()
        assert result["installed"] is False
        assert result["containers"] == []

    def test_installed_with_containers_parsed(self, mock_logger, mock_file_ops, mock_mount_root):
        cid = "abc123def456" + "0" * 52
        dirs_ok = {
            "/var/lib/docker",
            "/var/lib/docker/containers",
        }
        mock_file_ops.is_dir.side_effect = lambda p: p in dirs_ok
        mock_file_ops.ls.return_value = [cid]
        mock_file_ops.exists.return_value = True
        mock_file_ops.cat.return_value = _docker_config(name="web", image="nginx:1.25", status="running")
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        result = ca._analyze_docker()
        assert result["installed"] is True
        assert len(result["containers"]) == 1
        c = result["containers"][0]
        assert c["id"] == cid[:12]
        assert c["name"] == "web"
        assert c["image"] == "nginx:1.25"
        assert c["state"] == "running"

    def test_images_parsed(self, mock_logger, mock_file_ops, mock_mount_root):
        repos_json = json.dumps(
            {
                "Repositories": {
                    "nginx": {"latest": "sha256:abcdef1234567890"},
                    "redis": {"7.0": "sha256:fedcba0987654321"},
                }
            }
        )
        dirs_ok = {
            "/var/lib/docker",
            "/var/lib/docker/image",
        }
        mock_file_ops.is_dir.side_effect = lambda p: p in dirs_ok
        mock_file_ops.exists.side_effect = lambda p: "repositories.json" in p
        mock_file_ops.cat.return_value = repos_json
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        result = ca._analyze_docker()
        assert result["installed"] is True
        assert len(result["images"]) == 2
        repos = {img["repository"] for img in result["images"]}
        assert "nginx" in repos
        assert "redis" in repos

    def test_volumes_parsed(self, mock_logger, mock_file_ops, mock_mount_root):
        dirs_ok = {
            "/var/lib/docker",
            "/var/lib/docker/volumes",
            "/var/lib/docker/volumes/myvol",
            "/var/lib/docker/volumes/myvol/_data",
        }
        mock_file_ops.is_dir.side_effect = lambda p: p in dirs_ok
        mock_file_ops.ls.return_value = ["myvol"]
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        result = ca._analyze_docker()
        assert len(result["volumes"]) == 1
        assert result["volumes"][0]["name"] == "myvol"

    def test_networks_parsed(self, mock_logger, mock_file_ops, mock_mount_root):
        net_json = json.dumps(
            {
                "Name": "bridge",
                "Id": "abc123def456abc123",
                "Driver": "bridge",
                "Scope": "local",
            }
        )
        dirs_ok = {
            "/var/lib/docker",
            "/var/lib/docker/network/files",
        }
        mock_file_ops.is_dir.side_effect = lambda p: p in dirs_ok
        mock_file_ops.ls.return_value = ["bridge.json"]
        mock_file_ops.cat.return_value = net_json
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        result = ca._analyze_docker()
        assert len(result["networks"]) == 1
        assert result["networks"][0]["name"] == "bridge"
        assert result["networks"][0]["driver"] == "bridge"

    def test_invalid_json_skipped(self, mock_logger, mock_file_ops, mock_mount_root):
        cid = "b" * 64
        dirs_ok = {"/var/lib/docker", "/var/lib/docker/containers"}
        mock_file_ops.is_dir.side_effect = lambda p: p in dirs_ok
        mock_file_ops.ls.return_value = [cid]
        mock_file_ops.exists.return_value = True
        mock_file_ops.cat.return_value = "NOT VALID JSON{"
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        result = ca._analyze_docker()
        assert result["containers"] == []

    def test_dotfile_containers_skipped(self, mock_logger, mock_file_ops, mock_mount_root):
        dirs_ok = {"/var/lib/docker", "/var/lib/docker/containers"}
        mock_file_ops.is_dir.side_effect = lambda p: p in dirs_ok
        mock_file_ops.ls.return_value = [".hidden"]
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        result = ca._analyze_docker()
        assert result["containers"] == []


# ===========================================================================
# _analyze_podman
# ===========================================================================


class TestAnalyzePodman:
    def test_not_installed(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.is_dir.return_value = False
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        result = ca._analyze_podman()
        assert result["installed"] is False
        assert result["containers"] == []

    def test_installed_with_containers(self, mock_logger, mock_file_ops, mock_mount_root):
        cid = "c" * 64
        dirs_ok = {
            "/var/lib/containers/storage",
            "/var/lib/containers/storage/overlay-containers",
        }
        mock_file_ops.is_dir.side_effect = lambda p: p in dirs_ok
        mock_file_ops.ls.return_value = [cid]
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        result = ca._analyze_podman()
        assert result["installed"] is True
        assert len(result["containers"]) == 1
        assert result["containers"][0]["id"] == cid[:12]

    def test_dotfile_containers_skipped(self, mock_logger, mock_file_ops, mock_mount_root):
        dirs_ok = {
            "/var/lib/containers/storage",
            "/var/lib/containers/storage/overlay-containers",
        }
        mock_file_ops.is_dir.side_effect = lambda p: p in dirs_ok
        mock_file_ops.ls.return_value = [".wh.something"]
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        result = ca._analyze_podman()
        assert result["containers"] == []

    def test_storage_path_recorded(self, mock_logger, mock_file_ops, mock_mount_root):
        dirs_ok = {"/var/lib/containers/storage"}
        mock_file_ops.is_dir.side_effect = lambda p: p in dirs_ok
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        result = ca._analyze_podman()
        assert result["storage_path"] == "/var/lib/containers/storage"


# ===========================================================================
# _analyze_containerd
# ===========================================================================


class TestAnalyzeContainerd:
    def test_not_installed(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.is_dir.return_value = False
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        result = ca._analyze_containerd()
        assert result["installed"] is False

    def test_installed_via_var_lib(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.is_dir.side_effect = lambda p: p == "/var/lib/containerd"
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        result = ca._analyze_containerd()
        assert result["installed"] is True
        assert result["data_root"] == "/var/lib/containerd"

    def test_installed_via_run(self, mock_logger, mock_file_ops, mock_mount_root):
        mock_file_ops.is_dir.side_effect = lambda p: p == "/run/containerd"
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        result = ca._analyze_containerd()
        assert result["installed"] is True
        assert result["data_root"] == "/run/containerd"


# ===========================================================================
# get_container_summary
# ===========================================================================


class TestGetContainerSummary:
    def test_empty_analysis(self, mock_logger, mock_file_ops, mock_mount_root):
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        summary = ca.get_container_summary({})
        assert summary["docker_installed"] is False
        assert summary["podman_installed"] is False
        assert summary["containerd_installed"] is False
        assert summary["total_containers"] == 0

    def test_docker_only(self, mock_logger, mock_file_ops, mock_mount_root):
        analysis = {
            "docker": {"installed": True, "containers": [{"id": "abc"}]},
            "total_containers": 1,
            "total_images": 0,
            "total_volumes": 0,
        }
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        summary = ca.get_container_summary(analysis)
        assert summary["docker_installed"] is True
        assert summary["podman_installed"] is False
        assert summary["total_containers"] == 1

    def test_full_analysis(self, mock_logger, mock_file_ops, mock_mount_root):
        analysis = {
            "docker": {"installed": True},
            "podman": {"installed": True},
            "containerd": {"installed": True},
            "total_containers": 5,
            "total_images": 10,
            "total_volumes": 3,
        }
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        summary = ca.get_container_summary(analysis)
        assert summary["docker_installed"] is True
        assert summary["podman_installed"] is True
        assert summary["containerd_installed"] is True
        assert summary["total_containers"] == 5
        assert summary["total_images"] == 10
        assert summary["total_volumes"] == 3

    def test_handles_none_docker_value_raises(self, mock_logger, mock_file_ops, mock_mount_root):
        """When docker is explicitly None, .get on None raises AttributeError."""
        analysis = {"docker": None}
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        with pytest.raises(AttributeError):
            ca.get_container_summary(analysis)

    def test_handles_missing_docker_key(self, mock_logger, mock_file_ops, mock_mount_root):
        """When docker key is absent, summary defaults work correctly."""
        analysis = {"total_containers": 0, "total_images": 0, "total_volumes": 0}
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        summary = ca.get_container_summary(analysis)
        assert summary["docker_installed"] is False


# ===========================================================================
# list_container_images
# ===========================================================================


class TestListContainerImages:
    def test_empty_analysis(self, mock_logger, mock_file_ops, mock_mount_root):
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert ca.list_container_images({}) == []

    def test_docker_images_formatted(self, mock_logger, mock_file_ops, mock_mount_root):
        analysis = {
            "docker": {
                "images": [
                    {"repository": "nginx", "tag": "latest"},
                    {"repository": "redis", "tag": "7.0"},
                ]
            }
        }
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        images = ca.list_container_images(analysis)
        assert images == ["nginx:latest", "redis:7.0"]

    def test_no_docker_key(self, mock_logger, mock_file_ops, mock_mount_root):
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert ca.list_container_images({"podman": {}}) == []

    def test_docker_none(self, mock_logger, mock_file_ops, mock_mount_root):
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert ca.list_container_images({"docker": None}) == []


# ===========================================================================
# find_sensitive_mounts
# ===========================================================================


class TestFindSensitiveMounts:
    def test_returns_empty_list(self, mock_logger, mock_file_ops, mock_mount_root):
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert ca.find_sensitive_mounts({}) == []

    def test_returns_empty_with_docker(self, mock_logger, mock_file_ops, mock_mount_root):
        analysis = {"docker": {"installed": True, "containers": [{"id": "abc"}]}}
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert ca.find_sensitive_mounts(analysis) == []


# ===========================================================================
# check_container_security
# ===========================================================================


class TestCheckContainerSecurity:
    def test_returns_empty_when_no_docker(self, mock_logger, mock_file_ops, mock_mount_root):
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert ca.check_container_security({}) == []

    def test_returns_empty_when_docker_none(self, mock_logger, mock_file_ops, mock_mount_root):
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert ca.check_container_security({"docker": None}) == []

    def test_returns_issues_when_docker_installed(self, mock_logger, mock_file_ops, mock_mount_root):
        analysis = {"docker": {"installed": True}}
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        issues = ca.check_container_security(analysis)
        assert len(issues) == 1
        assert issues[0]["severity"] == "info"
        assert "Docker" in issues[0]["issue"]

    def test_docker_not_installed_flag(self, mock_logger, mock_file_ops, mock_mount_root):
        analysis = {"docker": {"installed": False}}
        ca = _make_analyzer(mock_logger, mock_file_ops, mock_mount_root)
        assert ca.check_container_security(analysis) == []
