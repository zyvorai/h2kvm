# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Azure resource models and data classes."""
# hyper2kvm/azure/models.py

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
# pylint: disable-next=too-many-instance-attributes  # models an Azure managed-disk reference's fields
class AzureDiskRef:
    """Reference to an Azure managed disk attached to a VM."""

    id: str
    name: str
    resource_group: str
    location: str
    size_gb: int
    sku: str = ""
    os_type: str | None = None
    is_os_disk: bool = False
    lun: int | None = None


@dataclass(frozen=True)
# pylint: disable-next=too-many-instance-attributes  # models an Azure VM reference's fields
class AzureVMRef:
    """Reference to an Azure VM, including its resolved managed disks."""

    id: str
    name: str
    resource_group: str
    location: str
    power_state: str = "unknown"
    os_type: str | None = None
    tags: dict[str, str] = field(default_factory=dict)
    disks: list[AzureDiskRef] = field(default_factory=list)


@dataclass(frozen=True)
class DiskArtifact:
    """A downloaded/staged disk artifact ready for local conversion."""

    role: str  # "os"|"data"
    lun: int | None
    src: str  # source disk id
    local_path: Path
    format: str  # "vhd"
    guest_hint: str | None = None


@dataclass
# pylint: disable-next=too-many-instance-attributes  # tracks one disk export's full lifecycle state
class AzureExportItem:
    """State and results of exporting one Azure managed disk."""

    vm_name: str
    vm_rg: str
    disk_id: str
    disk_name: str
    is_os: bool
    lun: int | None = None

    # pylint: disable=duplicate-code
    # reason: the expected_bytes/bytes_downloaded/ok/warnings/errors progress-tracking
    # fields below mirror hyper2kvm/providers/aws_ec2/models.py's DiskExport, but the
    # provider-specific identity/artifact fields above and below differ -- coincidental
    # convergent shape between independent per-provider export models.
    snapshot_id: str | None = None
    temp_disk_id: str | None = None

    sas_hash10: str | None = None
    local_path: str | None = None

    expected_bytes: int | None = None
    bytes_downloaded: int | None = None

    ok: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
# pylint: disable-next=too-many-instance-attributes  # aggregates a VM's export results and diagnostics
class AzureVMReport:
    """Aggregate export report for a single Azure VM."""

    name: str
    resource_group: str
    location: str
    power_state: str
    os_type: str | None
    tags: dict[str, str] = field(default_factory=dict)
    disks: list[dict[str, Any]] = field(default_factory=list)
    exports: list[AzureExportItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_jsonable(self) -> dict[str, Any]:
        """Return a JSON-serializable dict representation of this report."""
        return asdict(self)


@dataclass
# pylint: disable-next=too-many-instance-attributes  # aggregates a whole batch fetch run's state
class AzureFetchReport:
    """Aggregate report for a batch Azure VM fetch/export run."""

    subscription: str | None = None
    tenant: str | None = None
    run_tag: str = ""
    selection: dict[str, Any] = field(default_factory=dict)

    vms: list[AzureVMReport] = field(default_factory=list)

    created_resource_ids: list[str] = field(default_factory=list)
    deleted_resource_ids: list[str] = field(default_factory=list)

    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def sas_hash10(self, sas_url: str) -> str:
        """Return first 10 chars of SHA256 hash for audit preview (not cryptographically secure)."""
        return hashlib.sha256(sas_url.encode("utf-8")).hexdigest()[:10]

    def to_jsonable(self) -> dict[str, Any]:
        """Return a JSON-serializable dict representation of this report."""
        return asdict(self)


@dataclass
class AzureSelectConfig:
    """VM selection criteria for a batch Azure operation."""

    resource_group: str | None = None
    vm_names: list[str] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)
    power_state: str | None = None
    list_only: bool = False
    allow_all_rgs: bool = False


@dataclass
class AzureShutdownConfig:
    """Configuration for shutting down a VM before export/snapshot."""

    mode: str = "none"  # none|stop|deallocate
    wait: bool = True
    force: bool = False  # allow shutdown even when using snapshots


@dataclass
# pylint: disable-next=too-many-instance-attributes  # independent export policy toggles
class AzureExportConfig:
    """Configuration controlling how Azure disks are exported."""

    use_snapshots: bool = True
    stage_disk_from_snapshot: bool = False
    keep_snapshots: bool = False
    keep_temp_disks: bool = False
    sas_duration_s: int = 3600
    tag_resources: bool = True
    run_tag: str | None = None
    consistency: str = "crash_consistent"  # crash_consistent|best_effort_quiesce
    disks: str = "all"  # os|data|all


@dataclass
# pylint: disable-next=too-many-instance-attributes  # independent download tuning knobs (retries, timeouts, chunking)
class AzureDownloadConfig:
    """Configuration controlling how exported disk artifacts are downloaded."""

    parallel: int = 2
    resume: bool = True
    chunk_mb: int = 8
    verify_size: bool = True
    strict_verify: bool = False
    temp_suffix: str = ".part"
    connect_timeout_s: int = 15
    read_timeout_s: int = 60 * 5

    # NEW: retries for large downloads (real-world needed)
    retries: int = 5
    backoff_base_s: float = 1.0
    backoff_cap_s: float = 30.0


@dataclass
class AzureConfig:
    """Top-level configuration for an Azure export run."""

    subscription: str | None = None
    tenant: str | None = None
    select: AzureSelectConfig = field(default_factory=AzureSelectConfig)
    shutdown: AzureShutdownConfig = field(default_factory=AzureShutdownConfig)
    export: AzureExportConfig = field(default_factory=AzureExportConfig)
    download: AzureDownloadConfig = field(default_factory=AzureDownloadConfig)
    output_dir: Path = Path("./out")
