# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Unit tests for vmspawn Validator classes."""

import unittest
from unittest.mock import Mock

import pytest

from hyper2kvm.vmspawn.exceptions import VMValidationError
from hyper2kvm.vmspawn.models import ValidationResult
from hyper2kvm.vmspawn.validator import KubernetesNodeValidator, VMValidator


class TestVMValidator(unittest.TestCase):
    """Test VMValidator class."""

    def setUp(self):
        """Set up test fixtures."""
        self.machine = Mock()

    def test_validate_basic_success(self):
        """Test basic validation success."""
        self.machine.exec.side_effect = [
            "running",  # systemd check
            "inet 10.0.0.5/24 scope global eth0",  # network check
            "OK",  # boot complete check
        ]

        validator = VMValidator(self.machine)

        assert validator.validate() is True

    def test_validate_systemd_failure(self):
        """Test validation fails when systemd is not running."""
        self.machine.exec.side_effect = [
            "inactive",  # systemd check fails
        ]

        validator = VMValidator(self.machine)

        with pytest.raises(VMValidationError):
            validator.validate()

    def test_validate_network_failure(self):
        """Test validation fails when network is not configured."""
        self.machine.exec.side_effect = [
            "running",  # systemd check
            "",  # network check fails (no interfaces)
        ]

        validator = VMValidator(self.machine)

        with pytest.raises(VMValidationError):
            validator.validate()

    def test_validate_boot_incomplete(self):
        """Test validation fails when boot has not completed."""
        self.machine.exec.side_effect = [
            "running",  # systemd check
            "inet 10.0.0.5/24",  # network check
            "",  # boot complete check fails
        ]

        validator = VMValidator(self.machine)

        with pytest.raises(VMValidationError, match="boot_complete"):
            validator.validate()

    def test_validate_wraps_check_exception(self):
        """Test that an error raised by a check is wrapped in VMValidationError."""
        self.machine.exec.side_effect = Exception("Command failed")

        validator = VMValidator(self.machine)

        with pytest.raises(VMValidationError, match="systemd"):
            validator.validate()


class TestKubernetesNodeValidator(unittest.TestCase):
    """Test KubernetesNodeValidator class."""

    def setUp(self):
        """Set up test fixtures."""
        self.machine = Mock()

    def test_validate_k8s_success(self):
        """Test Kubernetes validation success."""
        self.machine.exec.side_effect = [
            "active",  # kubelet
            "active",  # containerd
            "/opt/cni",  # CNI
        ]

        validator = KubernetesNodeValidator(self.machine)

        assert validator.validate() is True

    def test_validate_kubelet_failure(self):
        """Test validation fails when kubelet is not running."""
        self.machine.exec.side_effect = [
            "inactive",  # kubelet fails
        ]

        validator = KubernetesNodeValidator(self.machine)

        with pytest.raises(VMValidationError):
            validator.validate()

    def test_validate_cni_failure(self):
        """Test validation fails when CNI is not configured."""
        self.machine.exec.side_effect = [
            "active",  # kubelet
            "active",  # containerd
            "",  # CNI fails (no plugins)
        ]

        validator = KubernetesNodeValidator(self.machine)

        with pytest.raises(VMValidationError, match="cni"):
            validator.validate()


class TestValidationResult(unittest.TestCase):
    """Test ValidationResult class."""

    def test_success_result(self):
        """Test creating success result."""
        result = ValidationResult(
            success=True,
            checks={
                "systemd": True,
                "network": True,
                "boot_complete": True,
            },
        )
        assert result.success
        assert result.error is None

    def test_failure_result(self):
        """Test creating failure result."""
        result = ValidationResult(
            success=False,
            checks={
                "systemd": True,
                "network": False,
            },
            error="Network not configured",
        )
        assert not result.success
        assert result.error == "Network not configured"

    def test_to_json(self):
        """Test converting result to JSON."""
        result = ValidationResult(
            success=True,
            checks={
                "systemd": True,
                "network": True,
            },
        )
        json_data = result.to_json()
        assert "success" in json_data
        assert "checks" in json_data
        assert json_data["success"]


if __name__ == "__main__":
    unittest.main()
