#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Example: Post-migration VM validation using vmspawn SDK.

This demonstrates how to validate migrated VMs using systemd-vmspawn.
"""

import asyncio
import logging
from pathlib import Path

from hyper2kvm.vmspawn import VMSpawnManager, VMValidator
from hyper2kvm.vmspawn.async_manager import AsyncVMManager
from hyper2kvm.vmspawn.async_validator import AsyncValidator
from hyper2kvm.vmspawn.cloudinit import create_cloud_init_config
from hyper2kvm.vmspawn.cleanup import CleanupEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def example_sync_validation():
    """
    Example 1: Synchronous single VM validation.

    Use this for simple, single VM testing.
    """
    logger.info("=== Example 1: Sync Validation ===")

    manager = VMSpawnManager()

    # Create VM from migrated disk
    machine = manager.create(
        name="test-vm",
        image=Path("/var/lib/hyper2kvm/migrated-vm.qcow2"),
        memory_mb=2048,
        cpus=2,
    )

    try:
        # Start and wait for boot
        logger.info("Starting VM...")
        manager.start("test-vm")

        # Validate
        logger.info("Running validation...")
        validator = VMValidator(machine)

        if validator.validate():
            logger.info("✅ VM validation passed!")
        else:
            logger.error("❌ VM validation failed!")

    finally:
        # Cleanup
        logger.info("Cleaning up...")
        manager.stop("test-vm")


async def example_async_validation():
    """
    Example 2: Async single VM validation.

    Use this for better performance and async workflows.
    """
    logger.info("=== Example 2: Async Validation ===")

    from hyper2kvm.vmspawn.async_machine import AsyncMachine

    # Create cloud-init config
    cloud_init = create_cloud_init_config(
        hostname="test-vm",
        users=["root"],
        ssh_authorized_keys=["ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ..."],
        runcmd=["echo 'VM ready' > /tmp/ready"],
    )

    machine = AsyncMachine(
        name="test-async-vm",
        image=Path("/var/lib/hyper2kvm/migrated-vm.qcow2"),
        memory_mb=2048,
        cpus=2,
        tpm=True,  # Enable TPM for testing
        cloud_init=cloud_init,
    )

    try:
        logger.info("Starting VM...")
        await machine.start()
        await machine.wait_running()

        logger.info("Running validation...")
        validator = AsyncValidator(machine)

        if await validator.validate():
            logger.info("✅ VM validation passed!")
        else:
            logger.error("❌ VM validation failed!")

    finally:
        logger.info("Stopping VM...")
        await machine.stop()


async def example_batch_validation():
    """
    Example 3: Batch VM validation (10 VMs in parallel).

    Use this for CI/CD pipelines or batch testing.
    """
    logger.info("=== Example 3: Batch Validation ===")

    from hyper2kvm.vmspawn.async_machine import AsyncMachine

    # Create multiple VMs
    machines = [
        AsyncMachine(
            name=f"vm-{i}",
            image=Path(f"/var/lib/hyper2kvm/vm-{i}.qcow2"),
            memory_mb=1024,
            cpus=1,
        )
        for i in range(10)
    ]

    manager = AsyncVMManager(max_parallel=5)  # Limit to 5 concurrent

    try:
        logger.info("Starting 10 VMs in parallel...")
        await manager.start_all(machines)

        logger.info("Validating all VMs...")
        results = await manager.validate_batch(machines, AsyncValidator)

        # Print results
        passed = sum(1 for r in results.values() if r)
        logger.info(f"Results: {passed}/{len(machines)} passed")

        for vm_name, result in results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            logger.info(f"  {vm_name}: {status}")

    finally:
        logger.info("Cleaning up...")
        cleanup = CleanupEngine(machines)
        await cleanup.cleanup_all(graceful=True)


async def example_massive_validation():
    """
    Example 4: Massive scale validation (1000 VMs).

    Use this for large-scale testing with rate limiting.
    """
    logger.info("=== Example 4: Massive Scale (1000 VMs) ===")

    from hyper2kvm.vmspawn.async_machine import AsyncMachine

    # Simulate 1000 VMs (in production, these would be different images)
    machines = [
        AsyncMachine(
            name=f"scale-test-{i}",
            image=Path("/var/lib/hyper2kvm/base-vm.qcow2"),
            memory_mb=512,  # Smaller for scale testing
            cpus=1,
        )
        for i in range(1000)
    ]

    # Limit to 100 concurrent VMs
    manager = AsyncVMManager(max_parallel=100)

    logger.info("Starting 1000 VMs with rate limiting...")
    start = asyncio.get_event_loop().time()

    try:
        await manager.start_all(machines)

        logger.info("Validating all VMs...")
        results = await manager.validate_batch(machines, AsyncValidator)

        elapsed = asyncio.get_event_loop().time() - start

        passed = sum(1 for r in results.values() if r)
        logger.info(f"Completed in {elapsed:.1f}s: {passed}/{len(machines)} passed")

    finally:
        logger.info("Cleanup...")
        cleanup = CleanupEngine(machines)
        await cleanup.cleanup_all(graceful=False)  # Force terminate for speed


async def example_kubernetes_validation():
    """
    Example 5: Kubernetes node validation.

    Use this to validate converted Kubernetes nodes.
    """
    logger.info("=== Example 5: Kubernetes Node Validation ===")

    from hyper2kvm.vmspawn.async_machine import AsyncMachine
    from hyper2kvm.vmspawn.validator import KubernetesNodeValidator

    machine = AsyncMachine(
        name="k8s-node-1",
        image=Path("/var/lib/hyper2kvm/k8s-node.qcow2"),
        memory_mb=4096,
        cpus=4,
    )

    try:
        logger.info("Starting Kubernetes node...")
        await machine.start()
        await machine.wait_running()

        logger.info("Validating Kubernetes components...")
        validator = KubernetesNodeValidator(machine)

        if await validator.validate():
            logger.info("✅ Kubernetes node ready!")
        else:
            logger.error("❌ Kubernetes validation failed!")

    finally:
        await machine.stop()


async def example_vsock_communication():
    """
    Example 6: vsock host-guest communication.

    Use this for advanced validation with vsock agent.
    """
    logger.info("=== Example 6: vsock Communication ===")

    from hyper2kvm.vmspawn.async_machine import AsyncMachine
    from hyper2kvm.vmspawn.vsock import VsockClient

    machine = AsyncMachine(
        name="vsock-test",
        image=Path("/var/lib/hyper2kvm/vm.qcow2"),
        vsock=True,  # Enable vsock
        memory_mb=2048,
        cpus=2,
    )

    try:
        await machine.start()
        await machine.wait_running()

        # Wait for vsock agent in VM
        await asyncio.sleep(10)

        # Communicate via vsock (CID 3 is typical for first VM)
        logger.info("Testing vsock communication...")
        client = VsockClient(cid=3, port=9000)

        if client.health_check():
            logger.info("✅ vsock communication working!")
        else:
            logger.warning("❌ vsock health check failed")

    finally:
        await machine.stop()


if __name__ == "__main__":
    # Run examples
    print("\n" + "=" * 80)
    print("Hyper2KVM vmspawn Validation Examples")
    print("=" * 80 + "\n")

    # Sync example
    try:
        example_sync_validation()
    except Exception as e:
        logger.error(f"Sync example failed: {e}")

    # Async examples
    asyncio.run(example_async_validation())
    asyncio.run(example_batch_validation())

    # Uncomment for large scale testing
    # asyncio.run(example_massive_validation())

    # K8s validation
    asyncio.run(example_kubernetes_validation())

    # vsock example
    asyncio.run(example_vsock_communication())

    print("\n✅ Examples complete!\n")
