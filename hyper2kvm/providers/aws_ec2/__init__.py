# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""AWS EC2 migration provider for hyper2kvm.

Exports EC2 instances (EBS snapshots → S3 → local download → qcow2)
with retry logic, progress tracking, resumability, and multi-disk support.

Usage:
    from hyper2kvm.providers.aws_ec2 import AWSConfig, AWSProvider

    config = AWSConfig(
        region="us-east-1",
        bucket="my-export-bucket",
        instance_ids=["i-0abc123def456"],
    )
    provider = AWSProvider(config)
    reports = provider.pull_all()
"""

from __future__ import annotations

from .models import (
    AWSConfig,
    AWSDownloadConfig,
    AWSExportConfig,
    AWSShutdownConfig,
    DiskExport,
    ExportReport,
    ExportTask,
    InstanceInfo,
    VolumeInfo,
)
from .provider import AWSProvider

__all__ = [
    "AWSConfig",
    "AWSDownloadConfig",
    "AWSExportConfig",
    "AWSProvider",
    "AWSShutdownConfig",
    "DiskExport",
    "ExportReport",
    "ExportTask",
    "InstanceInfo",
    "VolumeInfo",
]
