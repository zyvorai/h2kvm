# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Offline-Fix Worker Contract

Defines the API contract between Kubernetes workers (orchestrators) and
offline-fix workers (VM/bare-metal environments that perform dangerous
operations like NBD mounting, partition manipulation, and guest filesystem
modifications).

This contract enables:
- Clean separation between orchestration (K8s) and operation (VM)
- Testability via mock implementations
- Multiple backend support (libvirt, KubeVirt, external service)
- Predictable behavior and error handling
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class OSFamily(str, Enum):
    """Operating system family for hint-based optimization."""

    UNKNOWN = "unknown"
    CENTOS = "centos"
    RHEL = "rhel"
    FEDORA = "fedora"
    UBUNTU = "ubuntu"
    DEBIAN = "debian"
    WINDOWS = "windows"
    PHOTON = "photon"
    SLES = "sles"


class BootMode(str, Enum):
    """Boot mode detection."""

    UNKNOWN = "unknown"
    BIOS = "bios"
    UEFI = "uefi"


class FixOperation(str, Enum):
    """Individual offline fix operations."""

    # Bootloader fixes
    GRUB_REGENERATE = "grub_regenerate"
    GRUB_INSTALL = "grub_install"
    BOOTLOADER_DETECT = "bootloader_detect"

    # Filesystem fixes
    FSTAB_UUID = "fstab_uuid"
    FSTAB_LABEL = "fstab_label"
    FSTAB_VALIDATE = "fstab_validate"

    # Initramfs fixes
    INITRAMFS_REGENERATE = "initramfs_regenerate"
    INITRAMFS_VIRTIO = "initramfs_virtio"

    # Driver management
    VIRTIO_INJECT = "virtio_inject"
    VMWARE_TOOLS_REMOVE = "vmware_tools_remove"

    # SELinux
    SELINUX_RELABEL = "selinux_relabel"
    SELINUX_DISABLE = "selinux_disable"

    # Network
    NETWORK_STABILIZE = "network_stabilize"
    NETWORK_PREDICTABLE_NAMES = "network_predictable_names"

    # Cloud-init
    CLOUD_INIT_ENABLE = "cloud_init_enable"
    CLOUD_INIT_DISABLE = "cloud_init_disable"

    # Validation
    BOOT_VALIDATE = "boot_validate"
    FILESYSTEM_CHECK = "filesystem_check"


class FixResult(str, Enum):
    """Result status for individual fix operations."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    PARTIAL = "partial"
    NOT_APPLICABLE = "not_applicable"


class OfflineFixStatus(str, Enum):
    """Overall offline-fix job status."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    TIMEOUT = "timeout"


class ImageSpec(BaseModel):
    """Input image specification."""

    path: str = Field(..., description="Absolute path to input image file")
    format: str = Field(..., description="Image format (qcow2, vmdk, raw)")
    size_bytes: Optional[int] = Field(None, description="Image file size in bytes")
    virtual_size_bytes: Optional[int] = Field(None, description="Virtual disk size in bytes")

    class Config:
        schema_extra = {
            "example": {
                "path": "/work/input.qcow2",
                "format": "qcow2",
                "size_bytes": 2200000000,
                "virtual_size_bytes": 536870912000,
            }
        }


class OSHint(BaseModel):
    """Operating system detection hints to optimize fix operations."""

    family: OSFamily = Field(OSFamily.UNKNOWN, description="OS family")
    version: Optional[str] = Field(None, description="OS version (e.g., '9', '22.04')")
    architecture: Optional[str] = Field("x86_64", description="CPU architecture")
    boot_mode: BootMode = Field(BootMode.UNKNOWN, description="Boot mode")

    class Config:
        schema_extra = {
            "example": {"family": "centos", "version": "9", "architecture": "x86_64", "boot_mode": "bios"}
        }


class FixParameters(BaseModel):
    """Parameters controlling offline fix behavior."""

    # Bootloader
    update_grub: bool = Field(True, description="Regenerate GRUB configuration")
    grub_timeout: Optional[int] = Field(None, description="GRUB timeout in seconds")
    kernel_args: Optional[list[str]] = Field(None, description="Additional kernel arguments")

    # Initramfs
    regen_initramfs: bool = Field(True, description="Regenerate initramfs with virtio")
    extra_modules: Optional[list[str]] = Field(None, description="Extra kernel modules to include")

    # Filesystem
    fstab_mode: str = Field("uuid", description="fstab mode: uuid, label, or device")
    validate_filesystems: bool = Field(True, description="Run filesystem checks")

    # Drivers
    inject_virtio: bool = Field(True, description="Inject virtio drivers")
    remove_vmware_tools: bool = Field(True, description="Remove VMware tools")

    # SELinux
    selinux_relabel: bool = Field(True, description="Relabel SELinux contexts")
    selinux_mode: Optional[str] = Field(None, description="SELinux mode: enforcing, permissive, disabled")

    # Network
    network_config: Optional[str] = Field(None, description="Network configuration mode")
    enable_serial_console: bool = Field(False, description="Enable serial console")

    # Cloud-init
    disable_cloud_init: bool = Field(False, description="Disable cloud-init")
    preserve_cloud_init_config: bool = Field(True, description="Preserve existing cloud-init config")

    # Safety
    dry_run: bool = Field(False, description="Perform dry run without modifications")
    create_backup: bool = Field(True, description="Create backup before modifications")

    class Config:
        schema_extra = {
            "example": {
                "update_grub": True,
                "regen_initramfs": True,
                "fstab_mode": "uuid",
                "inject_virtio": True,
                "remove_vmware_tools": True,
                "selinux_relabel": True,
            }
        }


class OfflineFixRequest(BaseModel):
    """
    Request to perform offline fixes on a VM image.

    This is the input contract sent from K8s worker to offline-fix environment.
    """

    version: str = Field("1.0", description="Contract version")
    job_id: str = Field(..., description="Unique job identifier")

    # Input
    image: ImageSpec = Field(..., description="Input image specification")
    os_hint: Optional[OSHint] = Field(None, description="OS detection hints")

    # Configuration
    parameters: FixParameters = Field(default_factory=FixParameters, description="Fix parameters")
    operations: list[FixOperation] = Field(
        default_factory=lambda: [
            FixOperation.GRUB_REGENERATE,
            FixOperation.INITRAMFS_REGENERATE,
            FixOperation.FSTAB_UUID,
            FixOperation.VIRTIO_INJECT,
            FixOperation.SELINUX_RELABEL,
        ],
        description="Requested fix operations",
    )

    # Execution control
    timeout_seconds: int = Field(3600, description="Maximum execution time")
    output_path: str = Field("/work/output.qcow2", description="Output image path")

    # Metadata
    requested_by: Optional[str] = Field(None, description="Requester identifier")
    tags: Optional[dict[str, str]] = Field(None, description="Custom tags")

    class Config:
        schema_extra = {
            "example": {
                "version": "1.0",
                "job_id": "migrate-centos9-001",
                "image": {"path": "/work/input.qcow2", "format": "qcow2"},
                "os_hint": {"family": "centos", "version": "9"},
                "parameters": {"update_grub": True, "regen_initramfs": True, "fstab_mode": "uuid"},
                "output_path": "/work/output.qcow2",
                "timeout_seconds": 3600,
            }
        }


class FixOperationResult(BaseModel):
    """Result of a single fix operation."""

    operation: FixOperation = Field(..., description="Operation performed")
    result: FixResult = Field(..., description="Operation result")
    message: Optional[str] = Field(None, description="Human-readable message")
    duration_seconds: Optional[float] = Field(None, description="Operation duration")
    details: Optional[dict[str, Any]] = Field(None, description="Additional details")

    class Config:
        schema_extra = {
            "example": {
                "operation": "grub_regenerate",
                "result": "success",
                "message": "GRUB configuration regenerated successfully",
                "duration_seconds": 5.2,
                "details": {"grub_version": "2.06", "kernel_count": 3},
            }
        }


class DetectedOS(BaseModel):
    """Detected operating system information."""

    family: OSFamily = Field(..., description="Detected OS family")
    name: Optional[str] = Field(None, description="OS name (e.g., 'CentOS Linux')")
    version: Optional[str] = Field(None, description="OS version")
    version_id: Optional[str] = Field(None, description="Version ID")
    architecture: str = Field("x86_64", description="Architecture")
    boot_mode: BootMode = Field(BootMode.UNKNOWN, description="Detected boot mode")

    # Filesystem info
    root_filesystem: Optional[str] = Field(None, description="Root filesystem type (ext4, xfs)")
    has_lvm: bool = Field(False, description="Uses LVM")
    has_selinux: bool = Field(False, description="Has SELinux")

    class Config:
        schema_extra = {
            "example": {
                "family": "centos",
                "name": "CentOS Stream",
                "version": "9",
                "architecture": "x86_64",
                "boot_mode": "bios",
                "root_filesystem": "xfs",
                "has_lvm": True,
                "has_selinux": True,
            }
        }


class BootConfidence(BaseModel):
    """Boot confidence scoring."""

    score: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0.0-1.0)")
    factors: dict[str, float] = Field(default_factory=dict, description="Score factors")
    warnings: list[str] = Field(default_factory=list, description="Warnings affecting score")

    class Config:
        schema_extra = {
            "example": {
                "score": 0.95,
                "factors": {
                    "bootloader_valid": 1.0,
                    "initramfs_valid": 1.0,
                    "fstab_valid": 1.0,
                    "virtio_drivers": 0.9,
                    "selinux_context": 0.85,
                },
                "warnings": ["SELinux relabel may be needed on first boot"],
            }
        }


class OfflineFixResponse(BaseModel):
    """
    Response from offline-fix worker after completing (or failing) the job.

    This is the output contract returned to K8s worker.
    """

    version: str = Field("1.0", description="Contract version")
    job_id: str = Field(..., description="Job identifier (matches request)")

    # Status
    status: OfflineFixStatus = Field(..., description="Overall job status")
    started_at: datetime = Field(..., description="Job start time")
    completed_at: datetime = Field(..., description="Job completion time")
    duration_seconds: float = Field(..., description="Total duration")

    # Detection results
    detected_os: Optional[DetectedOS] = Field(None, description="Detected OS information")

    # Fix results
    operations_performed: list[FixOperationResult] = Field(
        default_factory=list, description="Results of all operations"
    )
    fixes_applied: list[str] = Field(default_factory=list, description="Summary of applied fixes")
    fixes_skipped: list[str] = Field(default_factory=list, description="Summary of skipped fixes")

    # Output
    output_image: Optional[str] = Field(None, description="Path to fixed image")
    output_size_bytes: Optional[int] = Field(None, description="Output image size")
    backup_image: Optional[str] = Field(None, description="Path to backup image")

    # Quality metrics
    boot_confidence: Optional[BootConfidence] = Field(None, description="Boot confidence score")

    # Diagnostics
    warnings: list[str] = Field(default_factory=list, description="Warnings (non-fatal)")
    errors: list[str] = Field(default_factory=list, description="Errors encountered")

    # Recommendations
    recommended_actions: list[str] = Field(default_factory=list, description="Recommended next steps")

    # Metadata
    worker_id: Optional[str] = Field(None, description="Worker that performed fixes")
    environment: Optional[dict[str, Any]] = Field(None, description="Worker environment info")

    class Config:
        schema_extra = {
            "example": {
                "version": "1.0",
                "job_id": "migrate-centos9-001",
                "status": "success",
                "started_at": "2026-01-31T10:00:00Z",
                "completed_at": "2026-01-31T10:05:30Z",
                "duration_seconds": 330.5,
                "detected_os": {"family": "centos", "version": "9", "boot_mode": "bios", "has_lvm": True},
                "fixes_applied": [
                    "GRUB regenerated",
                    "initramfs rebuilt with virtio",
                    "fstab converted to UUID",
                    "SELinux relabeled",
                ],
                "output_image": "/work/output.qcow2",
                "boot_confidence": {"score": 0.95, "warnings": []},
                "recommended_actions": ["boot-test", "validate-guest-configuration"],
            }
        }


# Type aliases for convenience
OfflineFixJob = OfflineFixRequest
OfflineFixResult = OfflineFixResponse
