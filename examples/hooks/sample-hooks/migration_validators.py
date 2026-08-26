# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Example Python hooks for h2kvm migration validation.

These functions can be called as Python hooks in Artifact Manifest v1.

Hook functions should return:
- bool: True for success, False for failure
- dict: {"success": True/False, "output": "message"}
- Any other value is treated as success
"""

import os
import subprocess
from pathlib import Path


def verify_boot_config(disk_path: str, vm_name: str) -> dict:
    """
    Verify boot configuration after offline fixes.

    Args:
        disk_path: Path to the boot disk
        vm_name: VM name for logging

    Returns:
        dict: {"success": bool, "output": str}
    """
    print(f"🔍 Verifying boot configuration for {vm_name}...")
    print(f"   Disk: {disk_path}")

    disk = Path(disk_path)

    # Check disk exists
    if not disk.exists():
        return {"success": False, "output": f"Disk not found: {disk_path}"}

    # Check disk is readable
    if not os.access(disk, os.R_OK):
        return {"success": False, "output": f"Disk not readable: {disk_path}"}

    # Example: Use guestfish to verify /boot exists
    try:
        result = subprocess.run(
            ["guestfish", "-a", str(disk), "-i", "exists", "/boot"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            print("✅ Boot configuration verified")
            return {"success": True, "output": "Boot partition exists and is accessible"}
        else:
            return {"success": False, "output": "/boot partition not found or not accessible"}

    except subprocess.TimeoutExpired:
        return {"success": False, "output": "Verification timed out"}
    except FileNotFoundError:
        # guestfish not installed, skip verification
        print("⚠️  guestfish not installed, skipping verification")
        return {"success": True, "output": "Verification skipped (guestfish not available)"}
    except Exception as e:
        return {"success": False, "output": f"Verification failed: {e}"}


def verify_qcow2_integrity(disk_path: str, expected_format: str = "qcow2") -> bool:
    """
    Verify qcow2 disk integrity after conversion.

    Args:
        disk_path: Path to the converted disk
        expected_format: Expected disk format

    Returns:
        bool: True if valid, False otherwise
    """
    print(f"🔍 Verifying QCOW2 integrity...")
    print(f"   Disk: {disk_path}")
    print(f"   Expected format: {expected_format}")

    disk = Path(disk_path)

    # Check disk exists
    if not disk.exists():
        print(f"❌ Disk not found: {disk_path}")
        return False

    # Use qemu-img check
    try:
        result = subprocess.run(
            ["qemu-img", "check", str(disk)], capture_output=True, text=True, timeout=300
        )

        if result.returncode == 0:
            print("✅ QCOW2 integrity check passed")
            print(result.stdout)
            return True
        else:
            print("❌ QCOW2 integrity check failed")
            print(result.stderr)
            return False

    except subprocess.TimeoutExpired:
        print("❌ Integrity check timed out")
        return False
    except FileNotFoundError:
        print("⚠️  qemu-img not found, skipping integrity check")
        return True  # Don't fail if tool is missing
    except Exception as e:
        print(f"❌ Integrity check error: {e}")
        return False


def send_migration_metrics(vm_name: str, metrics: dict) -> dict:
    """
    Send migration metrics to monitoring system.

    Args:
        vm_name: VM name
        metrics: Dictionary of metrics

    Returns:
        dict: {"success": bool, "output": str}
    """
    print(f"📊 Sending migration metrics for {vm_name}...")

    # Example: Send to Prometheus pushgateway
    # In production, use actual monitoring endpoint
    print(f"   Metrics: {metrics}")

    # Simulate success
    return {"success": True, "output": f"Metrics sent for {vm_name}"}


if __name__ == "__main__":
    # Example test
    print("Testing migration validators...")

    # Test verify_boot_config (will fail if no test disk)
    result = verify_boot_config("/nonexistent/disk.qcow2", "test-vm")
    print(f"verify_boot_config result: {result}")

    # Test verify_qcow2_integrity (will fail if no test disk)
    result = verify_qcow2_integrity("/nonexistent/disk.qcow2")
    print(f"verify_qcow2_integrity result: {result}")
