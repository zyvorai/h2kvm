#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Test Enterprise Parallel Manager with RHEL 8.8 VMDK

Tests the new enterprise-grade parallel conversion manager with
persistent namespaces and process-based parallelism.
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

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
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def convert_rhel88_vm(
    job: ConversionJob,
    nbd_device: str,
    namespace: Namespace,
) -> ConversionResult:
    """
    Convert RHEL 8.8 VM from VMware to KVM.

    Args:
        job: Conversion job specification
        nbd_device: Allocated NBD device
        namespace: Persistent namespace for execution

    Returns:
        Conversion result
    """
    try:
        logger.info("=" * 60)
        logger.info("Converting RHEL 8.8 VM: %s", job.input_image)
        logger.info("NBD Device: %s", nbd_device)
        logger.info("Namespace PID: %s", namespace.ns_pid)
        logger.info("=" * 60)

        # Detect OS version
        logger.info("\n[1/6] Detecting OS version...")
        try:
            os_release = namespace.run("cat /etc/os-release | grep PRETTY_NAME")
            logger.info("OS: %s", os_release)
        except Exception as e:
            logger.warning("Could not detect OS: %s", e)

        # Check kernel version
        logger.info("\n[2/6] Checking kernel version...")
        try:
            kernel = namespace.run("uname -r")
            logger.info("Kernel: %s", kernel)
        except Exception as e:
            logger.warning("Could not detect kernel: %s", e)

        # List installed kernels
        logger.info("\n[3/6] Listing installed kernels...")
        try:
            kernels = namespace.run("ls /boot/vmlinuz-* 2>/dev/null")
            logger.info("Installed kernels:\n%s", kernels)
        except Exception as e:
            logger.warning("Could not list kernels: %s", e)

        # Remove VMware tools
        logger.info("\n[4/6] Removing VMware tools...")
        try:
            namespace.run("""
                systemctl stop vmtoolsd 2>/dev/null || true
                systemctl disable vmtoolsd 2>/dev/null || true
                yum remove -y open-vm-tools vmware-tools 2>/dev/null || true
            """)
            logger.info("VMware tools removed")
        except Exception as e:
            logger.warning("VMware tools removal failed (may not be installed): %s", e)

        # Regenerate initramfs with virtio drivers
        logger.info("\n[5/6] Regenerating initramfs with virtio drivers...")
        logger.info("This may take 1-2 minutes...")

        namespace.run(
            "dracut --force --no-hostonly "
            "--add-drivers 'virtio_blk virtio_scsi virtio_net virtio_pci ahci sd_mod' "
            "--add lvm --add dm"
        )
        logger.info("✅ Initramfs regenerated successfully")

        # Verify virtio drivers
        logger.info("\n[6/6] Verifying virtio drivers in initramfs...")
        try:
            virtio_check = namespace.run("lsinitrd | grep virtio | head -10")
            logger.info("Virtio drivers found:\n%s", virtio_check)
        except Exception as e:
            logger.warning("Could not verify virtio drivers: %s", e)

        # Update GRUB configuration
        logger.info("\n[6/6] Updating GRUB configuration...")
        namespace.run("grub2-mkconfig -o /boot/grub2/grub.cfg")
        logger.info("✅ GRUB configuration updated")

        logger.info("\n" + "=" * 60)
        logger.info("✅ VM conversion completed successfully!")
        logger.info("=" * 60)

        return ConversionResult(
            job_id=job.job_id,
            status=JobStatus.SUCCESS,
            output_path=job.output_image,
            metadata={
                "source": str(job.input_image),
                "nbd_device": nbd_device,
                "namespace_pid": namespace.ns_pid,
            },
        )

    except Exception as e:
        logger.exception("VM conversion failed: %s", e)
        return ConversionResult(
            job_id=job.job_id,
            status=JobStatus.FAILED,
            error=str(e),
        )


def main():
    """Run enterprise parallel manager test."""
    logger.info("=" * 60)
    logger.info("Enterprise Parallel Manager - RHEL 8.8 Test")
    logger.info("=" * 60)

    # Check if VMDK exists
    vmdk_path = Path("./esx8.0-rhel8.8-with-thin-provision-disk1.vmdk")
    if not vmdk_path.exists():
        logger.error("VMDK file not found: %s", vmdk_path)
        logger.error("Please ensure the VMDK file is in the current directory")
        return 1

    # Create output directory
    output_dir = Path("./output")
    output_dir.mkdir(exist_ok=True)

    # Define conversion job
    output_image = output_dir / "rhel8.8-enterprise-test.qcow2"

    logger.info("\nConversion Details:")
    logger.info("  Source: %s", vmdk_path)
    logger.info("  Output: %s", output_image)
    logger.info("  Backend: Enterprise Parallel Manager")
    logger.info("  Workers: 1 (single conversion test)")
    logger.info("")

    # Create single job (testing with one VM)
    jobs = [
        ConversionJob(
            input_image=vmdk_path,
            output_image=output_image,
            backend="namespace",
            flatten=True,
            compress=True,
            fstab_mode="stabilize-all",
            regen_initramfs=True,
        )
    ]

    # Create enterprise parallel manager
    logger.info("Initializing Enterprise Parallel Manager...")
    manager = EnterpriseParallelManager(
        max_workers=1,  # Single worker for this test
        max_nbd_devices=2,  # Minimal NBD allocation
    )

    # Run conversion
    logger.info("Starting conversion...\n")

    results = manager.run(jobs, convert_rhel88_vm)

    # Display results
    logger.info("\n" + "=" * 60)
    logger.info("Conversion Results")
    logger.info("=" * 60)

    for job_id, result in results.items():
        if result.status == JobStatus.SUCCESS:
            logger.info("✅ SUCCESS")
            logger.info("   Job ID: %s", job_id[:8])
            logger.info("   Output: %s", result.output_path)
            logger.info("   Duration: %.1f seconds", result.duration or 0)
            logger.info("   NBD Device: %s", result.nbd_device)
            logger.info("   Namespace PID: %s", result.namespace_pid)

            # Check output file
            if result.output_path and Path(result.output_path).exists():
                size_mb = Path(result.output_path).stat().st_size / (1024 * 1024)
                logger.info("   File Size: %.2f MB", size_mb)

        else:
            logger.error("❌ FAILED")
            logger.error("   Job ID: %s", job_id[:8])
            logger.error("   Error: %s", result.error)

    logger.info("=" * 60)

    # Manager status
    status = manager.status()
    logger.info("\nManager Status:")
    logger.info("  Workers: %d", status["max_workers"])
    logger.info("  NBD Pool:")
    logger.info("    Total: %d", status["nbd_pool"]["total"])
    logger.info("    Available: %d", status["nbd_pool"]["available"])
    logger.info("    In Use: %d", status["nbd_pool"]["in_use"])

    return 0 if all(r.status == JobStatus.SUCCESS for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
