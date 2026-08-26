# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/constants.py
"""
Global constants and configuration defaults for hyper2kvm.

This module centralizes magic numbers and default values used throughout
the codebase, making them easier to maintain and configure.
"""

from __future__ import annotations

# ============================================================================
# Timeouts (in seconds)
# ============================================================================

# Default timeout for network operations
DEFAULT_NETWORK_TIMEOUT = 30

# Default timeout for SSH connections
DEFAULT_SSH_TIMEOUT = 60

# Default timeout for short operations (1 minute)
DEFAULT_SHORT_TIMEOUT = 60

# Default timeout for VM boot tests
DEFAULT_BOOT_TIMEOUT = 300  # 5 minutes

# Default timeout for libvirt domain operations
DEFAULT_LIBVIRT_TIMEOUT = 30

# Default timeout for QEMU operations
DEFAULT_QEMU_TIMEOUT = 120

# Timeout for vSphere operations
DEFAULT_VSPHERE_TIMEOUT = 300  # 5 minutes

# ============================================================================
# Retry Limits
# ============================================================================

# Maximum retry attempts for network operations
MAX_NETWORK_RETRIES = 5

# Maximum retry attempts for file operations
MAX_FILE_RETRIES = 3

# Maximum retry attempts for API calls
MAX_API_RETRIES = 4

# ============================================================================
# Network Ports
# ============================================================================

# RDP (Remote Desktop Protocol)
PORT_RDP = 3389

# VNC (Virtual Network Computing)
PORT_VNC = 5900

# SSH (Secure Shell)
PORT_SSH = 22

# vSphere API (HTTPS)
PORT_VSPHERE_API = 443

# ============================================================================
# File Sizes and Limits
# ============================================================================

# Size constants
SIZE_1_KIB = 1024
SIZE_1_MIB = 1024 * 1024
SIZE_1_GIB = 1024 * 1024 * 1024

# Default chunk size for file operations (5MB)
DEFAULT_CHUNK_SIZE = 5 * SIZE_1_MIB

# Maximum safe stage name length for recovery checkpoints
MAX_SAFE_STAGE_NAME_LENGTH = 120

# Maximum error message length for checkpoint annotations
MAX_ERROR_MESSAGE_LENGTH = 2000

# Seconds per day (for TTL calculations)
SECONDS_PER_DAY = 86400

# Maximum log message size
MAX_LOG_MESSAGE_SIZE = SIZE_1_KIB

# Maximum error message size for annotations
MAX_ERROR_MESSAGE_SIZE = 200

# Maximum command output size for error context (increased from 200)
MAX_COMMAND_OUTPUT_CAPTURE = 500

# Default buffer size for streaming operations (16KB)
DEFAULT_BUFFER_SIZE = 16 * SIZE_1_KIB

# ============================================================================
# Paths
# ============================================================================

# NBD device base path
NBD_BASE_PATH = "/dev/nbd"

# Maximum NBD device number (0-15, i.e. 16 devices total)
NBD_MAX_DEVICE = 15

# Mount base path for offline fixes
MOUNT_BASE_PATH = "/var/lib/kubevirt-offline"

# Import path for disk images
IMPORTS_PATH = "/var/lib/imports"

# Default libvirt images directory
LIBVIRT_IMAGES_DIR = "/var/lib/libvirt/images"

# Temporary directory for operations
TEMP_DIR = "/tmp"

# ============================================================================
# Kubernetes Annotations
# ============================================================================

# OfflineFix job annotation
ANNOTATION_OFFLINE_FIX_JOB = "offlinefix.hyper2kvm.io/job"

# NBD ready status annotation
ANNOTATION_NBD_READY = "offlinefix.hyper2kvm.io/nbd-ready"

# NBD device path annotation
ANNOTATION_NBD_DEVICE = "offlinefix.hyper2kvm.io/nbd-device"

# Mount path annotation
ANNOTATION_MOUNT_PATH = "offlinefix.hyper2kvm.io/mount-path"

# Cleanup request annotation
ANNOTATION_CLEANUP = "offlinefix.hyper2kvm.io/cleanup"

# ============================================================================
# Refresh Rates (in Hz or seconds)
# ============================================================================

# Maximum refresh rate for progress updates
MAX_REFRESH_HZ = 4.0

# Default refresh interval for status checks
DEFAULT_REFRESH_INTERVAL = 1.0

# ============================================================================
# Operation Delays (in seconds)
# ============================================================================

# Delay for NBD module loading
DELAY_NBD_MODULE_LOAD = 0.5

# Delay for kernel device creation and stabilization
DELAY_KERNEL_DEVICE_CREATION = 0.1

# Delay for partition detection after device creation
DELAY_PARTITION_DETECTION = 0.5

# Small delay to reduce CPU usage in polling loops
DELAY_CPU_USAGE_REDUCTION = 0.1

# Delay for libvirt domain operations
DELAY_LIBVIRT_OPERATION = 1.0

# Delay for device node settlement after udev (matches GuestKit timing)
DELAY_DEVICE_SETTLE = 0.2

# Delay for status polling loops (1 second)
DELAY_STATUS_POLL = 1.0

# Delay for progress reporting updates
DELAY_PROGRESS_UPDATE = 0.02

# ============================================================================
# Compression Levels
# ============================================================================

# Default compression level (1-9)
DEFAULT_COMPRESSION_LEVEL = 6

# Minimum compression level
MIN_COMPRESSION_LEVEL = 1

# Maximum compression level
MAX_COMPRESSION_LEVEL = 9

# ============================================================================
# VM Resource Defaults
# ============================================================================

# Default VM memory (MB)
DEFAULT_VM_MEMORY = 2048

# Default VM vCPUs
DEFAULT_VM_VCPUS = 2

# Default VM boot timeout (seconds)
DEFAULT_VM_BOOT_TIMEOUT = 60

# ============================================================================
# Conversion Defaults
# ============================================================================

# Default output format for conversions
DEFAULT_OUTPUT_FORMAT = "qcow2"

# Supported input formats
SUPPORTED_INPUT_FORMATS = {
    "vmdk",
    "ova",
    "ovf",
    "vhd",
    "vhdx",
    "raw",
    "qcow2",
}

# Supported output formats
SUPPORTED_OUTPUT_FORMATS = {
    "qcow2",
    "raw",
    "vdi",
}

# ============================================================================
# Virtio Driver Constants
# ============================================================================

# List of virtio drivers to add to initramfs
VIRTIO_DRIVERS = [
    "virtio_blk",
    "virtio_scsi",
    "virtio_net",
    "nvme",
]

# Additional drivers for specific scenarios
VIRTIO_OPTIONAL_DRIVERS = [
    "virtio_pci",
    "virtio_ring",
    "virtio_balloon",
]

# ============================================================================
# Registry Constants (Windows)
# ============================================================================

# Registry value type for DWORD
REG_DWORD = 4

# Registry value type for SZ (string)
REG_SZ = 1

# Registry value type for MULTI_SZ
REG_MULTI_SZ = 7

# ============================================================================
# Error Codes
# ============================================================================

# Success
EXIT_SUCCESS = 0

# General failure
EXIT_FAILURE = 1

# Configuration error
EXIT_CONFIG_ERROR = 2

# Permission error
EXIT_PERMISSION_ERROR = 13

# File not found
EXIT_FILE_NOT_FOUND = 2

# ============================================================================
# Environment Variables
# ============================================================================

# Environment variable for vCenter password
ENV_VC_PASSWORD = "VC_PASSWORD"

# Environment variable for LUKS passphrase
ENV_LUKS_PASSPHRASE = "LUKS_PASSPHRASE"

# Environment variable for verbose mode
ENV_VERBOSE = "HYPER2KVM_VERBOSE"

# Environment variable for debug mode
ENV_DEBUG = "HYPER2KVM_DEBUG"

# ============================================================================
# Logging Configuration
# ============================================================================

# Default log level (INFO)
DEFAULT_LOG_LEVEL = "INFO"

# Verbose log level (DEBUG)
VERBOSE_LOG_LEVEL = "DEBUG"

# Maximum number of log files to retain
MAX_LOG_FILES = 10

# Maximum log file size (MB)
MAX_LOG_FILE_SIZE_MB = 100

# ============================================================================
# Feature Flags (can be overridden via config)
# ============================================================================

# Enable recovery mode by default
DEFAULT_ENABLE_RECOVERY = False

# Enable compression by default
DEFAULT_ENABLE_COMPRESSION = False

# Enable checksums by default
DEFAULT_ENABLE_CHECKSUMS = True

# Enable backups by default
DEFAULT_ENABLE_BACKUPS = True

# Enable container isolation for LVM operations by default
# Runs LVM activation inside a Podman/Docker container for stronger isolation
DEFAULT_CONTAINER_ISOLATION = True

# ============================================================================
# Cloud Provider Specific
# ============================================================================

# Azure SAS token duration (hours)
AZURE_SAS_DURATION_HOURS = 24

# Azure default chunk size (MB)
AZURE_CHUNK_SIZE_MB = 4

# Azure maximum retries
AZURE_MAX_RETRIES = 5

# Azure backoff base (seconds)
AZURE_BACKOFF_BASE = 2

# Azure backoff cap (seconds)
AZURE_BACKOFF_CAP = 60

# ============================================================================
# Version Information
# ============================================================================

# API version
API_VERSION = "v1"

# Minimum Python version required
MIN_PYTHON_VERSION = (3, 10)

# ============================================================================
# Migration Specific
# ============================================================================

# Default fstab stabilization mode
DEFAULT_FSTAB_MODE = "stabilize-all"

# Default disk bus for VMs
DEFAULT_DISK_BUS = "virtio"

# Fallback disk bus
FALLBACK_DISK_BUS = "sata"

# Default network model
DEFAULT_NETWORK_MODEL = "virtio"

# Default video model
DEFAULT_VIDEO_MODEL = "vga"

# Default machine type
DEFAULT_MACHINE_TYPE = "pc-q35"

# Legacy machine type (SeaBIOS)
LEGACY_MACHINE_TYPE = "pc"
