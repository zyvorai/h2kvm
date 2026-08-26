# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""AWS EC2 provider exceptions."""

from __future__ import annotations


class AWSProviderError(Exception):
    """Base exception for AWS EC2 provider operations."""


class AWSAuthError(AWSProviderError):
    """AWS authentication or credential error."""


class ExportFailed(AWSProviderError):
    """EC2 image export task failed or was cancelled."""

    def __init__(self, task_id: str, status: str, message: str = ""):
        self.task_id = task_id
        self.status = status
        super().__init__(f"Export {task_id} failed: status={status} {message}")


class DownloadFailed(AWSProviderError):
    """S3 download failed after all retries."""


class SnapshotFailed(AWSProviderError):
    """EBS snapshot creation or wait failed."""


class InstanceNotFound(AWSProviderError):
    """EC2 instance not found."""


class VolumeNotFound(AWSProviderError):
    """EBS volume not found on instance."""
