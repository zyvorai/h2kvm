#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
H2KVM Backend Comparison Example

Demonstrates the two backend options for offline guest fixes:
1. VMCraft (default) - Fast pure-Python with native LVM
2. Namespace (experimental) - Unshare-based isolation for maximum security

Usage:
    python3 examples/backend_comparison.py <image.qcow2>
"""

import logging
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("backend_comparison")


def demo_vmcraft_backend(image_path: Path):
    """Demonstrate VMCraft backend (fast pure-Python)"""
    from h2kvm.fixers.offline_fixer import OfflineFixConfig, OfflineFSFix

    logger.info("=" * 70)
    logger.info("BACKEND 1: VMCraft (Pure-Python)")
    logger.info("=" * 70)
    logger.info("Pros: Fast startup, native LVM support")
    logger.info("Cons: Newer code, less battle-tested")
    logger.info("")

    config = OfflineFixConfig(
        image=image_path,
        dry_run=True,
        backend="vmcraft",  # Use fast pure-Python backend
        print_fstab=True,
    )

    fixer = OfflineFSFix(logger, config)

    try:
        result = fixer.fix()
        logger.info(f"VMCraft backend completed: {result.get('status')}")
    except Exception as e:
        logger.error(f"VMCraft backend failed: {e}")


def demo_namespace_backend(image_path: Path):
    """Demonstrate Namespace backend (maximum isolation)"""
    from h2kvm.vmcraft.storage import LVMActivator

    logger.info("")
    logger.info("=" * 70)
    logger.info("BACKEND 2: Namespace (Unshare-based Isolation)")
    logger.info("=" * 70)
    logger.info("Pros: Maximum security, isolated namespaces")
    logger.info("Cons: Requires unshare, experimental")
    logger.info("")

    try:
        # Direct namespace LVM activation
        audit = LVMActivator.activate_namespace(logger, str(image_path))

        if audit["ok"]:
            logger.info(f"Namespace backend found {len(audit['volumes'])} volume(s)")
            for vol in audit["volumes"]:
                logger.info(f"   - {vol}")
        else:
            logger.warning(f"Namespace backend: {audit.get('error', 'unknown error')}")

    except Exception as e:
        logger.error(f"Namespace backend failed: {e}")


def demo_performance_comparison(image_path: Path):
    """Measure VMCraft backend performance"""
    import time

    logger.info("")
    logger.info("=" * 70)
    logger.info("PERFORMANCE MEASUREMENT")
    logger.info("=" * 70)

    from h2kvm.fixers.offline_fixer import OfflineFixConfig, OfflineFSFix

    config = OfflineFixConfig(image=image_path, dry_run=True, backend="vmcraft", print_fstab=False)

    fixer = OfflineFSFix(logger, config)

    start = time.time()
    try:
        fixer.fix()
        elapsed = time.time() - start
        logger.info(f"VMCraft: {elapsed:.2f}s")
    except Exception as e:
        logger.error(f"VMCraft: failed - {e}")


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <image.qcow2>")
        print("")
        print("Examples:")
        print(f"  {sys.argv[0]} /path/to/guest.qcow2")
        print(f"  {sys.argv[0]} /var/lib/libvirt/images/rhel8.qcow2")
        sys.exit(1)

    image_path = Path(sys.argv[1])

    if not image_path.exists():
        logger.error(f"Image not found: {image_path}")
        sys.exit(1)

    logger.info(f"Testing backends with image: {image_path}")
    logger.info(f"Image size: {image_path.stat().st_size / (1024**3):.2f} GB")
    logger.info("")

    # Demo each backend
    demo_vmcraft_backend(image_path)
    demo_namespace_backend(image_path)

    # Performance measurement
    demo_performance_comparison(image_path)

    logger.info("")
    logger.info("=" * 70)
    logger.info("RECOMMENDATION")
    logger.info("=" * 70)
    logger.info("* Default: vmcraft (fast, pure-Python)")
    logger.info("* Security: namespace (isolated, experimental)")


if __name__ == "__main__":
    main()
