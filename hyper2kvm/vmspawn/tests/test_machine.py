# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Unit tests for vmspawn Machine class."""

import unittest
from unittest.mock import Mock, patch

import pytest

from hyper2kvm.vmspawn.exceptions import (
    VMStartError,
    VMStopError,
)
from hyper2kvm.vmspawn.machine import Machine
from hyper2kvm.vmspawn.models import VMConfig


class TestVMConfig(unittest.TestCase):
    """Test VMConfig validation and defaults."""

    def test_minimal_config(self):
        """Test creating config with minimal parameters."""
        config = VMConfig(name="test-vm", image="/path/to/image.qcow2")
        assert config.name == "test-vm"
        assert config.image == "/path/to/image.qcow2"
        assert config.memory_mb == 2048
        assert config.cpus == 2

    def test_full_config(self):
        """Test creating config with all parameters."""
        # pylint: disable=duplicate-code
        # reason: mirrors VMConfig(...) fixture literals in test_performance.py
        # (test_config_validation_performance, test_machine_start_command_generation)
        # -- coincidental shared test data, not shared logic; keeping independent
        # avoids coupling correctness tests to unrelated benchmark tests.
        config = VMConfig(
            name="test-vm",
            image="/path/to/image.qcow2",
            memory_mb=4096,
            cpus=4,
            tpm=True,
            vsock=True,
            vsock_cid=42,
        )
        assert config.memory_mb == 4096
        assert config.memory == 4096  # property alias
        assert config.cpus == 4
        assert config.tpm
        assert config.vsock
        assert config.vsock_cid == 42

    def test_invalid_memory(self):
        """Test that invalid memory raises error."""
        with pytest.raises(ValueError, match="VM memory must be a positive number"):
            VMConfig(name="test-vm", image="/path/to/image.qcow2", memory_mb=0)

    def test_invalid_cpus(self):
        """Test that invalid cpus raises error."""
        with pytest.raises(ValueError, match="VM CPU count must be a positive number"):
            VMConfig(name="test-vm", image="/path/to/image.qcow2", cpus=0)

    def test_memory_property(self):
        """Test memory property alias."""
        config = VMConfig(name="test", image="/tmp/test.qcow2", memory_mb=8192)
        assert config.memory == 8192
        config.memory = 16384
        assert config.memory_mb == 16384


class TestMachine(unittest.TestCase):
    """Test Machine class."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = VMConfig(
            name="test-vm",
            image="/path/to/image.qcow2",
            memory_mb=2048,
            cpus=2,
        )
        self.machine = Machine(self.config)

    @patch("subprocess.run")
    def test_start_success(self, mock_run):
        """Test successful VM start."""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        self.machine.start()

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "systemd-vmspawn" in args
        assert "--machine=test-vm" in args
        assert "--image=/path/to/image.qcow2" in args

    @patch("subprocess.run")
    def test_start_failure(self, mock_run):
        """Test VM start failure."""
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="Failed to start VM")

        with pytest.raises(VMStartError):
            self.machine.start()

    @patch("subprocess.run")
    def test_start_with_vsock(self, mock_run):
        """Test VM start with vsock enabled."""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        config = VMConfig(
            name="test-vm",
            image="/path/to/image.qcow2",
            vsock=True,
        )
        machine = Machine(config)
        machine.start()

        args = mock_run.call_args[0][0]
        assert "--vsock=yes" in args

    @patch("subprocess.run")
    def test_stop_success(self, mock_run):
        """Test successful VM stop."""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        self.machine.stop()

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "machinectl" in args
        assert "stop" in args
        assert "test-vm" in args

    @patch("subprocess.run")
    def test_stop_failure(self, mock_run):
        """Test VM stop failure."""
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="Machine not found")

        with pytest.raises(VMStopError):
            self.machine.stop()

    @patch("subprocess.run")
    def test_status_running(self, mock_run):
        """Test status returns running when VM is running."""
        mock_run.return_value = Mock(returncode=0, stdout="State=running\n", stderr="")

        status = self.machine.status()
        assert status.running

    @patch("subprocess.run")
    def test_status_not_running(self, mock_run):
        """Test status returns not running."""
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="")

        status = self.machine.status()
        assert not status.running

    @patch("subprocess.run")
    def test_exec_command(self, mock_run):
        """Test executing command in VM."""
        mock_run.return_value = Mock(returncode=0, stdout="Hello from VM\n", stderr="")

        result = self.machine.exec("echo 'Hello from VM'")

        assert result == "Hello from VM\n"
        args = mock_run.call_args[0][0]
        assert "machinectl" in args
        assert "shell" in args
        assert "test-vm" in args

    @patch("subprocess.run")
    def test_journal(self, mock_run):
        """Test getting VM journal logs."""
        mock_run.return_value = Mock(returncode=0, stdout="[  0.000] Linux version 5.15.0\n", stderr="")

        logs = self.machine.journal()

        assert "Linux version" in logs
        args = mock_run.call_args[0][0]
        assert "journalctl" in args
        assert "-M" in args
        assert "test-vm" in args

    @patch("subprocess.run")
    def test_terminate(self, mock_run):
        """Test force terminate VM."""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        self.machine.terminate()

        args = mock_run.call_args[0][0]
        assert "machinectl" in args
        assert "terminate" in args
        assert "test-vm" in args


if __name__ == "__main__":
    unittest.main()
