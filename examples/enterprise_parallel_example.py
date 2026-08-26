#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Enterprise Parallel Manager - Example Usage

Demonstrates production-grade parallel VM conversion with persistent namespaces.
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from h2kvm.vmcraft.enterprise_parallel_manager import (
    EnterpriseParallelManager,
    ConversionJob,
    ConversionResult,
    JobStatus,
    Namespace,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def example_basic_parallel_conversion():
    """Example 1: Basic parallel conversion."""
    logger.info("=" * 60)
    logger.info("Example 1: Basic Parallel Conversion")
    logger.info("=" * 60)

    # Define conversion jobs
    jobs = [
        ConversionJob("vm1.vmdk", "vm1.qcow2"),
        ConversionJob("vm2.vmdk", "vm2.qcow2"),
        ConversionJob("vm3.vmdk", "vm3.qcow2"),
        ConversionJob("vm4.vmdk", "vm4.qcow2"),
    ]

    # Create manager
    manager = EnterpriseParallelManager(max_workers=4)

    # Define conversion function
    def convert_vm(job: ConversionJob, nbd_device: str, namespace: Namespace) -> ConversionResult:
        """Perform VM conversion."""
        logger.info("Converting %s...", job.input_image)

        # Regenerate initramfs with virtio drivers
        logger.info("  → Regenerating initramfs...")
        namespace.run(
            "dracut --force --no-hostonly --add-drivers 'virtio_blk virtio_scsi virtio_net virtio_pci'"
        )

        # Update GRUB
        logger.info("  → Updating GRUB...")
        namespace.run("grub2-mkconfig -o /boot/grub2/grub.cfg")

        # Verify initramfs
        logger.info("  → Verifying initramfs...")
        result = namespace.run("lsinitrd | grep virtio | head -5")
        logger.info("Virtio drivers: %s", result)

        return ConversionResult(
            job_id=job.job_id,
            status=JobStatus.SUCCESS,
            output_path=job.output_image,
        )

    # Run parallel conversions
    results = manager.run(jobs, convert_vm)

    # Display results
    logger.info("\n" + "=" * 60)
    logger.info("Conversion Results:")
    logger.info("=" * 60)

    for job_id, result in results.items():
        if result.status == JobStatus.SUCCESS:
            logger.info(
                "✅ %s: %s (%.1fs, NBD: %s, NS PID: %d)",
                job_id[:8],
                result.output_path,
                result.duration or 0,
                result.nbd_device,
                result.namespace_pid or 0,
            )
        else:
            logger.error("❌ %s: %s", job_id[:8], result.error)

    logger.info("")


def example_custom_conversion():
    """Example 2: Custom conversion with OS detection."""
    logger.info("=" * 60)
    logger.info("Example 2: Custom Conversion Logic")
    logger.info("=" * 60)

    jobs = [
        ConversionJob("rhel8.vmdk", "rhel8.qcow2"),
        ConversionJob("ubuntu22.vmdk", "ubuntu22.qcow2"),
    ]

    manager = EnterpriseParallelManager(max_workers=2)

    def convert_with_detection(
        job: ConversionJob,
        nbd_device: str,
        namespace: Namespace,
    ) -> ConversionResult:
        """Custom conversion with OS detection."""
        metadata = {}

        # Detect OS
        try:
            os_info = namespace.run("cat /etc/os-release | grep PRETTY_NAME")
            metadata["os"] = os_info.split("=")[1].strip('"')
            logger.info("Detected OS: %s", metadata["os"])
        except Exception as e:
            logger.warning("OS detection failed: %s", e)
            metadata["os"] = "unknown"

        # Check kernel version
        try:
            kernel = namespace.run("uname -r")
            metadata["kernel"] = kernel
            logger.info("Kernel version: %s", kernel)
        except Exception as e:
            logger.warning("Kernel detection failed: %s", e)

        # List installed kernels
        try:
            kernels = namespace.run("ls /boot/vmlinuz-* 2>/dev/null")
            metadata["kernels"] = kernels.split("\n")
            logger.info("Installed kernels: %d", len(metadata["kernels"]))
        except Exception:
            pass

        # Regenerate initramfs
        logger.info("Regenerating initramfs...")
        namespace.run(
            "dracut --force --no-hostonly --add-drivers 'virtio_blk virtio_scsi virtio_net e1000e nvme'"
        )

        # Update bootloader (distro-specific)
        if "rhel" in metadata.get("os", "").lower() or "centos" in metadata.get("os", "").lower():
            logger.info("Updating GRUB (RHEL/CentOS)...")
            namespace.run("grub2-mkconfig -o /boot/grub2/grub.cfg")
        elif "ubuntu" in metadata.get("os", "").lower() or "debian" in metadata.get("os", "").lower():
            logger.info("Updating GRUB (Ubuntu/Debian)...")
            namespace.run("update-grub")
        else:
            logger.warning("Unknown OS, skipping bootloader update")

        return ConversionResult(
            job_id=job.job_id,
            status=JobStatus.SUCCESS,
            output_path=job.output_image,
            metadata=metadata,
        )

    # Run conversions
    results = manager.run(jobs, convert_with_detection)

    # Display results
    logger.info("\n" + "=" * 60)
    logger.info("Conversion Results:")
    logger.info("=" * 60)

    for job_id, result in results.items():
        if result.status == JobStatus.SUCCESS:
            logger.info("✅ %s:", job_id[:8])
            logger.info("   Output: %s", result.output_path)
            logger.info("   Duration: %.1fs", result.duration or 0)
            logger.info("   NBD Device: %s", result.nbd_device)
            logger.info("   Namespace PID: %d", result.namespace_pid or 0)
            logger.info("   OS: %s", result.metadata.get("os", "unknown"))
            logger.info("   Kernel: %s", result.metadata.get("kernel", "unknown"))
        else:
            logger.error("❌ %s: %s", job_id[:8], result.error)

    logger.info("")


def example_progress_tracking():
    """Example 3: Progress tracking with callback."""
    logger.info("=" * 60)
    logger.info("Example 3: Progress Tracking")
    logger.info("=" * 60)

    jobs = [ConversionJob(f"vm{i}.vmdk", f"vm{i}.qcow2") for i in range(1, 9)]

    manager = EnterpriseParallelManager(max_workers=4)

    # Track progress
    completed = {"count": 0}

    def progress_callback(job_id: str, status: JobStatus):
        """Track conversion progress."""
        if status == JobStatus.SUCCESS:
            completed["count"] += 1
            logger.info(
                "📊 Progress: %d/%d completed (%.1f%%)",
                completed["count"],
                len(jobs),
                (completed["count"] / len(jobs)) * 100,
            )

    def simple_convert(
        job: ConversionJob,
        nbd_device: str,
        namespace: Namespace,
    ) -> ConversionResult:
        """Simple conversion."""
        namespace.run("dracut --force --no-hostonly")
        namespace.run("grub2-mkconfig -o /boot/grub2/grub.cfg")

        return ConversionResult(
            job_id=job.job_id,
            status=JobStatus.SUCCESS,
            output_path=job.output_image,
        )

    # Run with progress callback
    results = manager.run(jobs, simple_convert, progress_callback=progress_callback)

    # Summary
    success = sum(1 for r in results.values() if r.status == JobStatus.SUCCESS)
    failed = sum(1 for r in results.values() if r.status == JobStatus.FAILED)

    logger.info("\n" + "=" * 60)
    logger.info("Summary:")
    logger.info("  Total: %d", len(jobs))
    logger.info("  ✅ Success: %d", success)
    logger.info("  ❌ Failed: %d", failed)
    logger.info("=" * 60)
    logger.info("")


def example_manager_status():
    """Example 4: Manager status monitoring."""
    logger.info("=" * 60)
    logger.info("Example 4: Manager Status Monitoring")
    logger.info("=" * 60)

    manager = EnterpriseParallelManager(max_workers=8, max_nbd_devices=16)

    # Display initial status
    status = manager.status()
    logger.info("Manager Status:")
    logger.info("  Max Workers: %d", status["max_workers"])
    logger.info("  NBD Pool:")
    logger.info("    Total: %d", status["nbd_pool"]["total"])
    logger.info("    Available: %d", status["nbd_pool"]["available"])
    logger.info("    In Use: %d", status["nbd_pool"]["in_use"])
    logger.info("  Jobs:")
    logger.info("    Total: %d", status["jobs"]["total"])
    logger.info("    Pending: %d", status["jobs"]["pending"])
    logger.info("    Running: %d", status["jobs"]["running"])
    logger.info("    Success: %d", status["jobs"]["success"])
    logger.info("    Failed: %d", status["jobs"]["failed"])

    logger.info("")


def example_error_handling():
    """Example 5: Error handling and recovery."""
    logger.info("=" * 60)
    logger.info("Example 5: Error Handling")
    logger.info("=" * 60)

    jobs = [
        ConversionJob("valid-vm.vmdk", "valid-vm.qcow2"),
        ConversionJob("nonexistent-vm.vmdk", "fail.qcow2"),  # Will fail
        ConversionJob("another-valid-vm.vmdk", "another.qcow2"),
    ]

    manager = EnterpriseParallelManager(max_workers=3)

    def convert_with_error_check(
        job: ConversionJob,
        nbd_device: str,
        namespace: Namespace,
    ) -> ConversionResult:
        """Conversion with error handling."""
        try:
            # Check if input exists
            if not job.input_image.exists():
                raise FileNotFoundError(f"Input image not found: {job.input_image}")

            # Perform conversion
            namespace.run("dracut --force --no-hostonly")
            namespace.run("grub2-mkconfig -o /boot/grub2/grub.cfg")

            return ConversionResult(
                job_id=job.job_id,
                status=JobStatus.SUCCESS,
                output_path=job.output_image,
            )

        except Exception as e:
            logger.exception("Conversion failed for %s", job.job_id)

            return ConversionResult(
                job_id=job.job_id,
                status=JobStatus.FAILED,
                error=str(e),
            )

    # Run conversions
    results = manager.run(jobs, convert_with_error_check)

    # Display results
    logger.info("\n" + "=" * 60)
    logger.info("Results (with errors):")
    logger.info("=" * 60)

    for job_id, result in results.items():
        if result.status == JobStatus.SUCCESS:
            logger.info("✅ %s: Success", job_id[:8])
        else:
            logger.error("❌ %s: %s", job_id[:8], result.error)

    logger.info("")


def main():
    """Run all examples."""
    logger.info("🚀 Enterprise Parallel Manager - Example Usage\n")

    examples = [
        ("Basic Parallel Conversion", example_basic_parallel_conversion),
        ("Custom Conversion Logic", example_custom_conversion),
        ("Progress Tracking", example_progress_tracking),
        ("Manager Status", example_manager_status),
        ("Error Handling", example_error_handling),
    ]

    for name, func in examples:
        try:
            func()
        except Exception as e:
            logger.exception("Example '%s' failed: %s", name, e)

    logger.info("=" * 60)
    logger.info("All examples completed!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
