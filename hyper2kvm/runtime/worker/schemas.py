# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/worker/schemas.py
"""
Worker Job Protocol Schemas.

Defines Pydantic models for job specifications, results, progress events,
and worker capabilities. All schemas are JSON-serializable for transport
over REST APIs, message queues, or file-based job submission.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JobState(str, Enum):
    """Job lifecycle states."""

    CREATED = "Created"
    VALIDATED = "Validated"
    QUEUED = "Queued"
    ASSIGNED = "Assigned"
    RUNNING = "Running"
    PROGRESSING = "Progressing"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"
    RETRYING = "Retrying"


class OperationType(str, Enum):
    """Supported operation types."""

    INSPECT = "inspect"
    CONVERT = "convert"
    OFFLINE_FIX = "offline_fix"
    BOOT_REPAIR = "boot_repair"
    SELINUX_PREP = "selinux_prep"
    LVM_REPAIR = "lvm_repair"
    FS_REPAIR = "fs_repair"
    INITRAMFS_REGEN = "initramfs_regenerate"


class ImageSpec(BaseModel):
    """Disk image specification."""

    path: str = Field(..., description="Absolute path to disk image")
    format: str | None = Field(None, description="Image format (qcow2, vmdk, raw, etc.)")
    checksum: str | None = Field(None, description="SHA-256 checksum for validation")
    size_bytes: int | None = Field(None, description="Image size in bytes", ge=0)

    @field_validator("format")
    @classmethod
    def validate_format(cls, v):
        if v is not None:
            valid_formats = ["qcow2", "vmdk", "raw", "vdi", "vhd", "vhdx"]
            if v not in valid_formats:
                raise ValueError(f"Format must be one of {valid_formats}")
        return v


class CapabilityRequirements(BaseModel):
    """Job capability requirements."""

    needs_nbd: bool = Field(False, description="Requires NBD device access")
    needs_lvm: bool = Field(False, description="Requires LVM tools and activation")
    needs_mount: bool = Field(False, description="Requires filesystem mount capability")
    needs_selinux_tools: bool = Field(False, description="Requires SELinux tools")
    min_memory_gb: int | None = Field(None, description="Minimum RAM in GB", ge=1)
    min_disk_space_gb: int | None = Field(None, description="Minimum free disk space in GB", ge=1)


class ExecutionPolicy(BaseModel):
    """Job execution policy."""

    retry_count: int = Field(0, description="Number of retries on failure", ge=0, le=5)
    timeout_seconds: int = Field(7200, description="Execution timeout in seconds", ge=60, le=86400)
    idempotent: bool = Field(True, description="Whether job can be safely retried")
    priority: int = Field(5, description="Job priority (1=highest, 10=lowest)", ge=1, le=10)


class ArtifactConfig(BaseModel):
    """Artifact storage configuration."""

    log_upload: bool = Field(True, description="Upload execution logs")
    store_fixed_image: bool = Field(True, description="Store repaired image")
    output_path: str = Field(..., description="Output directory path")
    keep_intermediates: bool = Field(False, description="Keep intermediate files for debugging")


class AuditInfo(BaseModel):
    """Audit trail information."""

    requested_by: str = Field(..., description="User or service requesting the job")
    ticket: str | None = Field(None, description="Associated ticket ID (e.g., INC-1234)")
    tags: dict[str, str] | None = Field(None, description="Custom tags for job categorization")


class JobSpec(BaseModel):
    """
    Complete job specification.

    This is the primary schema for submitting jobs to workers.
    """

    version: str = Field("1.0", description="Protocol version")
    job_id: str = Field(..., description="Unique job identifier (UUID)")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Job creation timestamp")

    operation: OperationType = Field(..., description="Operation to perform")
    image: ImageSpec = Field(..., description="Disk image specification")

    requested_actions: list[str] = Field(
        default_factory=list, description="Specific actions to perform (e.g., nbd_attach, lvm_activate)"
    )

    capability_requirements: CapabilityRequirements = Field(
        default_factory=CapabilityRequirements, description="Required worker capabilities"
    )

    execution_policy: ExecutionPolicy = Field(
        default_factory=ExecutionPolicy, description="Execution policy and constraints"
    )

    artifacts: ArtifactConfig = Field(..., description="Artifact storage configuration")
    audit: AuditInfo = Field(..., description="Audit trail information")

    parameters: dict[str, Any] | None = Field(None, description="Operation-specific parameters")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "version": "1.0",
                "job_id": "job-uuid-1234",
                "created_at": "2026-01-30T10:00:00Z",
                "operation": "offline_fix",
                "image": {
                    "path": "/images/rhel8.qcow2",
                    "format": "qcow2",
                    "checksum": "sha256:abc123...",
                    "size_bytes": 42949672960,
                },
                "requested_actions": ["nbd_attach", "lvm_activate", "fsck", "initramfs_regenerate"],
                "capability_requirements": {"needs_nbd": True, "needs_lvm": True, "needs_mount": True},
                "execution_policy": {
                    "retry_count": 2,
                    "timeout_seconds": 7200,
                    "idempotent": True,
                    "priority": 5,
                },
                "artifacts": {"log_upload": True, "store_fixed_image": True, "output_path": "/mnt/output"},
                "audit": {"requested_by": "api-service", "ticket": "INC-1234"},
            }
        }
    )


class ProgressEvent(BaseModel):
    """
    Progress event emitted during job execution.

    Workers stream these events to provide real-time status updates.
    """

    job_id: str = Field(..., description="Job identifier")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")
    phase: str = Field(..., description="Current execution phase")
    progress_percent: int = Field(..., description="Progress percentage", ge=0, le=100)
    message: str = Field(..., description="Human-readable progress message")

    details: dict[str, Any] | None = Field(None, description="Additional phase-specific details")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_id": "job-uuid-1234",
                "timestamp": "2026-01-30T10:10:00Z",
                "phase": "lvm_activate",
                "progress_percent": 40,
                "message": "Volume group rhel activated",
                "details": {"vg_name": "rhel", "lv_count": 3},
            }
        }
    )


class ErrorInfo(BaseModel):
    """Error information for failed jobs."""

    phase: str = Field(..., description="Phase where error occurred")
    code: str = Field(..., description="Error code (e.g., FS_CORRUPTION_UNRECOVERABLE)")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] | None = Field(None, description="Additional error context")
    stack_trace: str | None = Field(None, description="Stack trace for debugging")


class JobOutput(BaseModel):
    """Job output artifacts."""

    fixed_image: str | None = Field(None, description="Path to repaired image")
    logs: str | None = Field(None, description="Path to execution logs")
    report: str | None = Field(None, description="Path to detailed report")
    intermediates: list[str] | None = Field(None, description="Paths to intermediate files")


class JobMetrics(BaseModel):
    """Execution metrics."""

    execution_seconds: int = Field(..., description="Total execution time in seconds", ge=0)
    nbd_attach_seconds: int | None = Field(None, description="Time spent attaching NBD", ge=0)
    lvm_activate_seconds: int | None = Field(None, description="Time spent activating LVM", ge=0)
    fsck_seconds: int | None = Field(None, description="Time spent on filesystem check", ge=0)
    initramfs_seconds: int | None = Field(None, description="Time spent regenerating initramfs", ge=0)

    disk_read_bytes: int | None = Field(None, description="Bytes read from disk", ge=0)
    disk_write_bytes: int | None = Field(None, description="Bytes written to disk", ge=0)


class JobResult(BaseModel):
    """
    Job execution result.

    Produced by workers upon job completion (success or failure).
    """

    job_id: str = Field(..., description="Job identifier")
    status: JobState = Field(..., description="Final job status")
    completed_at: datetime = Field(default_factory=datetime.utcnow, description="Completion timestamp")

    outputs: JobOutput | None = Field(None, description="Output artifacts")
    metrics: JobMetrics | None = Field(None, description="Execution metrics")
    error: ErrorInfo | None = Field(None, description="Error information if failed")

    worker_id: str | None = Field(None, description="Worker that executed the job")
    retry_attempt: int = Field(0, description="Retry attempt number (0 = first attempt)", ge=0)

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "job_id": "job-uuid-1234",
                    "status": "completed",
                    "completed_at": "2026-01-30T11:00:00Z",
                    "outputs": {"fixed_image": "/mnt/output/vm-fixed.qcow2", "logs": "/mnt/output/job.log"},
                    "metrics": {"execution_seconds": 3200, "nbd_attach_seconds": 2, "fsck_seconds": 900},
                    "worker_id": "worker-01",
                },
                {
                    "job_id": "job-uuid-5678",
                    "status": "failed",
                    "completed_at": "2026-01-30T11:30:00Z",
                    "error": {
                        "phase": "fsck",
                        "code": "FS_CORRUPTION_UNRECOVERABLE",
                        "message": "Superblock invalid, cannot repair",
                    },
                    "worker_id": "worker-02",
                },
            ]
        }
    )


class WorkerCapabilities(BaseModel):
    """
    Worker capability advertisement.

    Workers register with these capabilities to enable job matching.
    """

    worker_id: str = Field(..., description="Unique worker identifier")
    hostname: str | None = Field(None, description="Worker hostname")

    capabilities: dict[str, bool] = Field(
        ..., description="Supported capabilities (nbd, lvm, mount, selinux, etc.)"
    )

    max_disk_size_tb: int = Field(10, description="Maximum supported disk size in TB", ge=1)
    max_concurrent_jobs: int = Field(1, description="Maximum concurrent jobs", ge=1, le=10)

    memory_gb: int = Field(..., description="Available RAM in GB", ge=1)
    disk_space_gb: int = Field(..., description="Available disk space in GB", ge=10)

    os_info: dict[str, str] | None = Field(None, description="OS information")
    kernel_version: str | None = Field(None, description="Kernel version")

    last_heartbeat: datetime = Field(default_factory=datetime.utcnow, description="Last heartbeat timestamp")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "worker_id": "worker-01",
                "hostname": "vm-worker-node1.example.com",
                "capabilities": {"nbd": True, "lvm": True, "mount": True, "selinux": True, "qemu_img": True},
                "max_disk_size_tb": 10,
                "max_concurrent_jobs": 2,
                "memory_gb": 64,
                "disk_space_gb": 500,
                "os_info": {"distribution": "Fedora", "version": "43"},
                "kernel_version": "6.18.6-200.fc43.x86_64",
                "last_heartbeat": "2026-01-30T10:00:00Z",
            }
        }
    )
