#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
AWS EC2 to KVM Migration Example

Demonstrates the full EC2 → KVM migration pipeline:
  1. Describe EC2 instance (volumes, platform, architecture)
  2. Stop instance
  3. Create EBS snapshot
  4. Export snapshot to S3 as VMDK
  5. Download from S3 with progress
  6. Convert + offline fixes via h2kvmctl
  7. Deploy to libvirt

Prerequisites:
  - AWS credentials configured (aws configure)
  - S3 bucket for exports (with vmimport role)
  - pip install boto3

Usage:
  # Single instance
  python3 examples/aws_ec2_migration.py --instance-id i-0abc123 --bucket my-exports

  # Multiple instances
  python3 examples/aws_ec2_migration.py \
    --instance-id i-0abc123 i-0def456 \
    --bucket my-exports \
    --region us-west-2

  # Root disk only (skip data volumes)
  python3 examples/aws_ec2_migration.py \
    --instance-id i-0abc123 \
    --bucket my-exports \
    --disks root

  # Don't stop the instance (use existing snapshot)
  python3 examples/aws_ec2_migration.py \
    --instance-id i-0abc123 \
    --bucket my-exports \
    --no-stop
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)8s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("aws_migration")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate AWS EC2 instances to KVM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --instance-id i-0abc123 --bucket my-exports
  %(prog)s --instance-id i-0abc123 i-0def456 --region eu-west-1 --bucket exports
  %(prog)s --instance-id i-0abc123 --bucket exports --disks all --no-stop
        """,
    )
    parser.add_argument("--instance-id", nargs="+", required=True, help="EC2 instance ID(s)")
    parser.add_argument("--bucket", required=True, help="S3 bucket for exports")
    parser.add_argument("--region", default="us-east-1", help="AWS region (default: us-east-1)")
    parser.add_argument("--profile", default=None, help="AWS CLI profile name")
    parser.add_argument("--output-dir", default="./out", help="Output directory (default: ./out)")
    parser.add_argument("--disks", choices=["root", "all"], default="root", help="Export root or all disks")
    parser.add_argument("--format", choices=["vmdk", "vhd", "raw"], default="vmdk", help="Export format")
    parser.add_argument("--no-stop", action="store_true", help="Don't stop the instance")
    parser.add_argument("--keep-snapshots", action="store_true", help="Keep EBS snapshots after export")
    args = parser.parse_args()

    try:
        from hyper2kvm.providers.aws_ec2 import AWSConfig, AWSProvider
        from hyper2kvm.providers.aws_ec2.models import (
            AWSDownloadConfig,
            AWSExportConfig,
            AWSShutdownConfig,
        )
    except ImportError:
        logger.error("hyper2kvm not installed. Run: pip install hyper2kvm")
        logger.error("Also need: pip install boto3")
        sys.exit(1)

    # Build config
    config = AWSConfig(
        region=args.region,
        profile=args.profile,
        bucket=args.bucket,
        instance_ids=args.instance_id,
        output_dir=Path(args.output_dir),
        shutdown=AWSShutdownConfig(
            stop_instance=not args.no_stop,
        ),
        export=AWSExportConfig(
            disk_format=args.format,
            disks=args.disks,
            keep_snapshots=args.keep_snapshots,
        ),
        download=AWSDownloadConfig(
            retries=5,
            resume=True,
        ),
    )

    # Progress callback
    def on_progress(phase: str, message: str, pct: float):
        bar = "=" * int(pct * 40) + " " * (40 - int(pct * 40))
        print(f"\r  [{bar}] {pct:.0%} {phase}: {message}", end="", flush=True)
        if pct >= 1.0:
            print()

    # Run migration
    provider = AWSProvider(config, log=logger, progress_cb=on_progress)

    print(f"\nMigrating {len(args.instance_id)} instance(s) from AWS EC2 to KVM\n")
    print(f"  Region:     {args.region}")
    print(f"  Bucket:     {args.bucket}")
    print(f"  Disks:      {args.disks}")
    print(f"  Format:     {args.format}")
    print(f"  Output:     {args.output_dir}")
    print(f"  Stop:       {'yes' if not args.no_stop else 'no'}")
    print()

    reports = provider.pull_all()

    # Summary
    print("\n" + "=" * 60)
    print("Migration Summary")
    print("=" * 60)

    for report in reports:
        status = "OK" if not report.errors else "FAILED"
        print(f"\n  {report.instance_id} ({report.instance_name}): {status}")
        print(f"    Platform: {report.platform} / {report.architecture}")

        for disk in report.disks:
            disk_status = "OK" if disk.ok else "FAILED"
            print(f"    Disk {disk.volume_id} ({disk.device}): {disk_status}")
            if disk.qcow2_path:
                print(f"      Output: {disk.qcow2_path}")
            for err in disk.errors:
                print(f"      Error: {err}")

        for err in report.errors:
            print(f"    Error: {err}")

    # Exit code
    failed = sum(1 for r in reports if r.errors)
    if failed:
        print(f"\n{failed}/{len(reports)} instance(s) failed")
        sys.exit(1)
    else:
        print(f"\nAll {len(reports)} instance(s) migrated successfully")


if __name__ == "__main__":
    main()
