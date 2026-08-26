#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Example: Export VM using hyperctl (hypersdk)

This example shows how to use the Go-based hypersdk daemon
for high-performance VM exports instead of govc or pyvmomi.

Prerequisites:
    1. Install hypersdk:
       https://github.com/ssahani/hypersdk/releases

    2. Start the daemon:
       sudo systemctl start hypervisord

    3. Or manually:
       export GOVC_URL='https://vcenter.example.com/sdk'
       export GOVC_USERNAME='administrator@vsphere.local'
       export GOVC_PASSWORD='your-password'
       export GOVC_INSECURE=1
       hypervisord
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path for development
sys.path.insert(0, str(Path(__file__).parent.parent))

from h2kvm.providers.vmware.transports import (
    HYPERCTL_AVAILABLE,
    create_hyperctl_runner,
    export_vm_hyperctl,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    """Export VM using hyperctl."""

    if not HYPERCTL_AVAILABLE:
        logger.error("hyperctl not available. Install hypersdk from https://github.com/ssahani/hypersdk")
        sys.exit(1)

    # VM to export
    vm_path = "/datacenter/vm/my-test-vm"
    output_path = "/tmp/hyperctl-export"

    logger.info(f"Exporting VM: {vm_path}")
    logger.info(f"Output path: {output_path}")

    # Progress callback
    def show_progress(status):
        """Show progress updates."""
        logger.info(f"Progress: {status.get('output', 'Working...')}")

    try:
        # Method 1: Simple one-liner
        result = export_vm_hyperctl(
            vm_path=vm_path,
            output_path=output_path,
            parallel_downloads=4,
            remove_cdrom=True,
            progress_callback=show_progress,
        )

        logger.info("✅ Export completed!")
        logger.info(f"Job ID: {result.get('job_id')}")

    except Exception as e:
        logger.error(f"❌ Export failed: {e}")
        sys.exit(1)


def advanced_example():
    """Advanced usage with HyperCtlRunner."""

    # Create runner
    runner = create_hyperctl_runner(
        daemon_url="http://localhost:8080",
    )

    # Check daemon status
    try:
        status = runner.check_daemon_status()
        logger.info(f"Daemon status: {status}")
    except Exception as e:
        logger.error(f"Daemon not running: {e}")
        return

    # Submit export job
    job_id = runner.submit_export_job(
        vm_path="/datacenter/vm/my-vm",
        output_path="/tmp/export",
        parallel_downloads=4,
        remove_cdrom=True,
    )

    logger.info(f"Job submitted: {job_id}")

    # Wait for completion with progress callback
    def progress(status):
        print(".", end="", flush=True)

    result = runner.wait_for_job_completion(
        job_id=job_id,
        poll_interval=5,
        timeout=3600,
        progress_callback=progress,
    )

    logger.info(f"\n✅ Job completed: {result}")


if __name__ == "__main__":
    # Run simple example
    main()

    # Uncomment for advanced example
    # advanced_example()
