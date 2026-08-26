# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""AWS EC2 provider data models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VolumeInfo:
    """EBS volume attached to an instance."""

    volume_id: str
    device: str
    size_gb: int
    volume_type: str = ""
    is_root: bool = False
    encrypted: bool = False


@dataclass(frozen=True)
class InstanceInfo:  # pylint: disable=too-many-instance-attributes
    # reason: models the full set of independent EC2 instance metadata fields
    # needed to plan a migration (identity, platform, storage layout, tags).
    """EC2 instance metadata."""

    instance_id: str
    name: str
    state: str
    instance_type: str
    platform: str  # "linux" or "windows"
    architecture: str  # "x86_64" or "arm64"
    root_device_name: str
    root_device_type: str  # "ebs" or "instance-store"
    volumes: list[VolumeInfo] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class ExportTask:
    """Tracks an EC2 image/snapshot export to S3."""

    task_id: str
    status: str  # active, completed, deleted, deleting
    status_message: str = ""
    progress: str = ""  # e.g. "50%"
    s3_bucket: str = ""
    s3_key: str = ""
    disk_format: str = "vmdk"


@dataclass
class DiskExport:  # pylint: disable=too-many-instance-attributes
    # reason: tracks one disk's state across every stage of the export/download/
    # convert pipeline (snapshot, S3 export, local download, qcow2 conversion, results).
    """Tracks a single disk through the export pipeline."""

    volume_id: str
    device: str
    is_root: bool
    size_gb: int

    # pylint: disable=duplicate-code
    # reason: the expected_bytes/bytes_downloaded/ok/warnings/errors progress-tracking
    # fields below mirror hyper2kvm/providers/azure/models.py's AzureExportItem, but the
    # provider-specific identity/artifact fields above and below differ -- coincidental
    # convergent shape between independent per-provider export models.
    snapshot_id: str | None = None
    export_task_id: str | None = None
    s3_bucket: str | None = None
    s3_key: str | None = None
    local_path: str | None = None
    qcow2_path: str | None = None

    expected_bytes: int | None = None
    bytes_downloaded: int | None = None

    ok: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class ExportReport:  # pylint: disable=too-many-instance-attributes
    # reason: aggregates the full set of independent identity, disk, and
    # warning/error fields for one instance's migration report.
    """Full report for an instance migration."""

    instance_id: str
    instance_name: str = ""
    region: str = ""
    platform: str = ""
    architecture: str = ""

    disks: list[DiskExport] = field(default_factory=list)
    state_file: str | None = None

    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_jsonable(self) -> dict[str, Any]:
        """Return this report as a plain JSON-serializable dict."""
        return asdict(self)


@dataclass
class AWSExportConfig:
    """Export-phase settings."""

    disk_format: str = "vmdk"  # vmdk, vhd, raw
    s3_prefix: str = "hyper2kvm"
    role_name: str = "vmimport"
    create_snapshot: bool = True
    keep_snapshots: bool = False
    disks: str = "root"  # root, all


@dataclass
class AWSDownloadConfig:  # pylint: disable=too-many-instance-attributes
    # reason: models the full set of independent download-tuning knobs (parallelism,
    # resume, retry/backoff, timeouts, verification) as a flat config record.
    """Download-phase settings."""

    parallel: int = 2
    resume: bool = True
    chunk_mb: int = 8
    retries: int = 5
    backoff_base_s: float = 1.0
    backoff_cap_s: float = 30.0
    verify_size: bool = True
    temp_suffix: str = ".part"
    connect_timeout_s: int = 15
    read_timeout_s: int = 300


@dataclass
class AWSShutdownConfig:
    """Instance shutdown settings."""

    stop_instance: bool = True
    wait: bool = True


@dataclass
class AWSConfig:  # pylint: disable=too-many-instance-attributes
    # reason: top-level config aggregating the independent connection, export,
    # download, and shutdown sub-configs plus output paths.
    """Top-level AWS EC2 provider configuration."""

    region: str = "us-east-1"
    profile: str | None = None  # AWS CLI profile name
    bucket: str = ""  # S3 bucket for exports (required)

    instance_ids: list[str] = field(default_factory=list)

    shutdown: AWSShutdownConfig = field(default_factory=AWSShutdownConfig)
    export: AWSExportConfig = field(default_factory=AWSExportConfig)
    download: AWSDownloadConfig = field(default_factory=AWSDownloadConfig)

    output_dir: Path = Path("./out")
    workdir: Path | None = None  # temp workspace, defaults to output_dir/work
