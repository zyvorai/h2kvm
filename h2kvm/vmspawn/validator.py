# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""VM validation engine."""

import logging

from .exceptions import VMValidationError
from .machine import Machine

logger = logging.getLogger(__name__)


class VMValidator:
    """
    Automatic VM validation engine.

    Validates:
    - VM boots successfully
    - systemd is running
    - Network is up
    - Boot completed
    """

    # pylint: disable=duplicate-code
    # reason: mirrors async_validator.AsyncValidator's constructor/validate-
    # loop shape -- this sync version raises VMValidationError on failure
    # while the async twin returns False, so the two are kept independent
    # rather than merged into one shared implementation.
    def __init__(self, machine: Machine):
        """
        Initialize validator.

        Args:
            machine: Machine to validate
        """
        self.machine = machine

    def validate(self) -> bool:
        """
        Run all validation checks.

        Returns:
            True if all checks pass

        Raises:
            VMValidationError: If any check fails
        """
        checks = [
            ("systemd", self.check_systemd),
            ("network", self.check_network),
            ("boot_complete", self.check_boot_complete),
        ]
        # pylint: enable=duplicate-code

        for name, check in checks:
            logger.info("Running validation check: %s", name)

            try:
                if not check():
                    raise VMValidationError(f"Validation failed: {name}")

                logger.info("✅ %s check passed", name)

            except Exception as e:
                logger.exception("❌ %s check failed: %s", name, e)
                raise VMValidationError(f"Validation check '{name}' failed: {e}") from e

        return True

    def check_systemd(self) -> bool:
        """
        Check if systemd is running.

        Returns:
            True if systemd is running or degraded
        """
        result = self.machine.exec("systemctl is-system-running || true", timeout=10)

        return "running" in result.lower() or "degraded" in result.lower()

    def check_network(self) -> bool:
        """
        Check if network is configured.

        Returns:
            True if network interface has IP address
        """
        result = self.machine.exec("ip addr show | grep inet", timeout=10)

        return "inet" in result

    def check_boot_complete(self) -> bool:
        """
        Check if boot is complete.

        Returns:
            True if systemd boot is complete
        """
        result = self.machine.exec("test -f /run/systemd/system && echo OK", timeout=10)

        return "OK" in result


class KubernetesNodeValidator:
    """
    Kubernetes node validation.

    Validates converted nodes before joining cluster:
    - kubelet service
    - container runtime
    - CNI configuration
    """

    # pylint: disable=duplicate-code
    # reason: mirrors async_validator.AsyncKubernetesValidator's constructor/
    # validate-loop shape -- this sync version raises VMValidationError on
    # failure while the async twin returns False, so the two are kept
    # independent rather than merged into one shared implementation.
    def __init__(self, machine: Machine):
        """
        Initialize Kubernetes validator.

        Args:
            machine: Machine to validate
        """
        self.machine = machine

    def validate(self) -> bool:
        """
        Run all Kubernetes validation checks.

        Returns:
            True if all checks pass

        Raises:
            VMValidationError: If any check fails
        """
        checks = [
            ("kubelet", self.check_kubelet),
            ("container_runtime", self.check_container_runtime),
            ("cni", self.check_cni),
        ]
        # pylint: enable=duplicate-code

        for name, check in checks:
            logger.info("Running K8s validation check: %s", name)

            try:
                if not check():
                    raise VMValidationError(f"K8s validation failed: {name}")

                logger.info("✅ %s check passed", name)

            except Exception as e:
                logger.exception("❌ %s check failed: %s", name, e)
                raise VMValidationError(f"K8s check '{name}' failed: {e}") from e

        return True

    def check_kubelet(self) -> bool:
        """
        Check if kubelet is active.

        Returns:
            True if kubelet service is active
        """
        result = self.machine.exec("systemctl is-active kubelet || true", timeout=10)

        return result.strip().lower() == "active"

    def check_container_runtime(self) -> bool:
        """
        Check if container runtime is active.

        Returns:
            True if containerd/docker is active
        """
        # Try containerd first
        result = self.machine.exec("systemctl is-active containerd || true", timeout=10)

        if result.strip().lower() == "active":
            return True

        # Fallback to docker
        result = self.machine.exec("systemctl is-active docker || true", timeout=10)

        return result.strip().lower() == "active"

    def check_cni(self) -> bool:
        """
        Check if CNI is configured.

        Returns:
            True if CNI configuration exists
        """
        result = self.machine.exec("ls /etc/cni/net.d 2>/dev/null || true", timeout=10)

        return len(result.strip()) > 0
