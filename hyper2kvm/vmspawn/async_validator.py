# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Async validation engine for high-scale VM testing."""

import logging

from .async_machine import AsyncMachine

logger = logging.getLogger(__name__)


class AsyncValidator:
    """
    Async VM validator.

    Validates:
    - systemd running
    - Network up
    - Boot complete
    - cloud-init finished
    """

    # pylint: disable=duplicate-code
    # reason: mirrors validator.VMValidator's constructor/validate-loop shape
    # -- the sync twin raises VMValidationError on failure while this async
    # version returns False, so the two are kept independent rather than
    # merged into one shared implementation.
    def __init__(self, machine: AsyncMachine):
        """
        Initialize validator.

        Args:
            machine: Machine to validate
        """
        self.machine = machine

    async def validate(self) -> bool:
        """
        Run all validation checks.

        Returns:
            True if all checks pass
        """
        checks = [
            ("systemd", self.check_systemd),
            ("network", self.check_network),
            ("boot_complete", self.check_boot_complete),
            ("cloud_init", self.check_cloud_init),
        ]
        # pylint: enable=duplicate-code

        for name, check in checks:
            logger.debug("Running validation check: %s", name)

            try:
                if not await check():
                    logger.error("❌ %s check failed", name)
                    return False

                logger.debug("✅ %s check passed", name)

            # pylint: disable-next=broad-exception-caught  # a single check's failure must not abort validation reporting
            except Exception as e:
                logger.exception("❌ %s check error: %s", name, e)
                return False

        return True

    async def check_systemd(self) -> bool:
        """
        Check systemd status.

        Returns:
            True if systemd is running
        """
        result = await self.machine.exec("systemctl is-system-running || true")

        return "running" in result.lower() or "degraded" in result.lower()

    async def check_network(self) -> bool:
        """
        Check network configuration.

        Returns:
            True if network is up
        """
        result = await self.machine.exec("ip addr show | grep inet")

        return "inet" in result

    async def check_boot_complete(self) -> bool:
        """
        Check boot completion.

        Returns:
            True if boot is complete
        """
        result = await self.machine.exec("test -f /run/systemd/system && echo OK")

        return "OK" in result

    async def check_cloud_init(self) -> bool:
        """
        Check cloud-init status.

        Returns:
            True if cloud-init finished (or not installed)
        """
        result = await self.machine.exec("cloud-init status 2>/dev/null || echo OK")

        return "done" in result or "OK" in result


class AsyncKubernetesValidator:
    """
    Async Kubernetes node validator.

    Validates:
    - kubelet running
    - Container runtime active
    - CNI configured
    """

    # pylint: disable=duplicate-code
    # reason: mirrors validator.KubernetesNodeValidator's constructor/validate-
    # loop shape -- the sync twin raises VMValidationError on failure while
    # this async version returns False, so the two are kept independent
    # rather than merged into one shared implementation.
    def __init__(self, machine: AsyncMachine):
        """
        Initialize K8s validator.

        Args:
            machine: Machine to validate
        """
        self.machine = machine

    async def validate(self) -> bool:
        """
        Run all K8s validation checks.

        Returns:
            True if all checks pass
        """
        checks = [
            ("kubelet", self.check_kubelet),
            ("container_runtime", self.check_container_runtime),
            ("cni", self.check_cni),
        ]
        # pylint: enable=duplicate-code

        for name, check in checks:
            logger.debug("Running K8s validation check: %s", name)

            try:
                if not await check():
                    logger.error("❌ %s check failed", name)
                    return False

                logger.debug("✅ %s check passed", name)

            # pylint: disable-next=broad-exception-caught  # a single check's failure must not abort validation reporting
            except Exception as e:
                logger.exception("❌ %s check error: %s", name, e)
                return False

        return True

    async def check_kubelet(self) -> bool:
        """Check kubelet service."""
        result = await self.machine.exec("systemctl is-active kubelet || true")

        return "active" in result.lower()

    async def check_container_runtime(self) -> bool:
        """Check container runtime (containerd/docker)."""
        # Try containerd
        result = await self.machine.exec("systemctl is-active containerd || true")

        if "active" in result.lower():
            return True

        # Fallback to docker
        result = await self.machine.exec("systemctl is-active docker || true")

        return "active" in result.lower()

    async def check_cni(self) -> bool:
        """Check CNI configuration."""
        result = await self.machine.exec("ls /etc/cni/net.d 2>/dev/null || true")

        return len(result.strip()) > 0
