# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Comprehensive exception hierarchy for h2kvm.

Provides subsystem-specific exceptions with context, redaction, and user-friendly
error messages. All exceptions inherit from H2KvmError base class.

Includes :class:`ErrorCode` enum for structured, machine-readable error
classification and the ``format_error()`` method on every exception.
"""

# h2kvm/core/exceptions.py
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

# ============================================================================
# Structured Error Codes
# ============================================================================


class ErrorCode(enum.Enum):
    """
    Machine-readable error codes for h2kvm operations.

    Codes are grouped by subsystem prefix:
        - GENERAL_*       : General / uncategorized errors
        - VMDK_*          : VMDK / disk image errors
        - NBD_*           : Network Block Device errors
        - FSTAB_*         : Filesystem table / mount errors
        - BOOT_*          : Bootloader errors
        - NET_*           : Network configuration errors
        - WIN_*           : Windows guest errors
        - LVM_*           : LVM errors
        - LUKS_*          : LUKS encryption errors
        - PART_*          : Partition errors
        - PROVIDER_*      : Provider (VMware, Azure) errors
        - MANIFEST_*      : Manifest / config errors
        - WORKER_*        : Worker / runtime errors
        - HOOK_*          : Lifecycle hook errors
    """

    # General
    GENERAL_UNKNOWN = "E0001"
    GENERAL_FATAL = "E0002"
    GENERAL_TIMEOUT = "E0003"
    GENERAL_PERMISSION_DENIED = "E0004"
    GENERAL_NOT_IMPLEMENTED = "E0005"

    # VMDK / disk image
    VMDK_NOT_FOUND = "E1001"
    VMDK_CORRUPT = "E1002"
    VMDK_UNSUPPORTED_FORMAT = "E1003"
    VMDK_CONVERSION_FAILED = "E1004"
    VMDK_SIZE_MISMATCH = "E1005"

    # NBD
    NBD_CONNECT_FAILED = "E1101"
    NBD_DEVICE_BUSY = "E1102"
    NBD_MODULE_LOAD_FAILED = "E1103"
    NBD_DISCONNECT_FAILED = "E1104"
    NBD_NO_FREE_DEVICE = "E1105"

    # Filesystem / fstab
    FSTAB_PARSE_ERROR = "E1201"
    FSTAB_INVALID_ENTRY = "E1202"
    FSTAB_MOUNT_FAILED = "E1203"
    FSTAB_UUID_NOT_FOUND = "E1204"

    # Bootloader
    BOOT_GRUB_INSTALL_FAILED = "E1301"
    BOOT_GRUB_CONFIG_FAILED = "E1302"
    BOOT_BCD_REPAIR_FAILED = "E1303"
    BOOT_UNSUPPORTED_LOADER = "E1304"

    # Network
    NET_CONFIG_FAILED = "E1401"
    NET_INTERFACE_NOT_FOUND = "E1402"

    # Windows guest
    WIN_VIRTIO_INJECT_FAILED = "E1501"
    WIN_REGISTRY_FAILED = "E1502"
    WIN_BITLOCKER_DETECTED = "E1503"

    # LVM
    LVM_ACTIVATION_FAILED = "E1601"
    LVM_VG_NOT_FOUND = "E1602"

    # LUKS
    LUKS_UNLOCK_FAILED = "E1701"
    LUKS_KEY_MISSING = "E1702"

    # Partition
    PART_NOT_FOUND = "E1801"
    PART_MOUNT_FAILED = "E1802"

    # Provider (VMware / Azure)
    PROVIDER_AUTH_FAILED = "E2001"
    PROVIDER_CONNECTION_FAILED = "E2002"
    PROVIDER_VM_NOT_FOUND = "E2003"
    PROVIDER_DOWNLOAD_FAILED = "E2004"
    PROVIDER_RATE_LIMITED = "E2005"

    # Manifest / config
    MANIFEST_VALIDATION_FAILED = "E3001"
    MANIFEST_NOT_FOUND = "E3002"
    MANIFEST_SCHEMA_ERROR = "E3003"

    # Worker / runtime
    WORKER_REGISTRATION_FAILED = "E4001"
    WORKER_JOB_FAILED = "E4002"
    WORKER_QUEUE_FULL = "E4003"

    # Hook
    HOOK_EXECUTION_FAILED = "E5001"
    HOOK_TIMEOUT = "E5002"


# Default hint messages per error code
_ERROR_HINTS: dict[ErrorCode, str] = {
    ErrorCode.VMDK_NOT_FOUND: "Verify the VMDK path exists and is accessible.",
    ErrorCode.VMDK_CORRUPT: "Re-download the VMDK or check disk integrity with qemu-img check.",
    ErrorCode.VMDK_UNSUPPORTED_FORMAT: "Convert to a supported format (qcow2, vmdk, vdi, vhd, raw).",
    ErrorCode.VMDK_CONVERSION_FAILED: "Check disk space and qemu-img availability.",
    ErrorCode.NBD_CONNECT_FAILED: "Ensure qemu-nbd is installed and the nbd kernel module is loaded.",
    ErrorCode.NBD_DEVICE_BUSY: "Another process may be using this NBD device. Run: cleanup_orphaned_devices().",
    ErrorCode.NBD_MODULE_LOAD_FAILED: "Try: sudo modprobe nbd max_part=16",
    ErrorCode.NBD_NO_FREE_DEVICE: "All NBD devices are in use. Disconnect unused devices or increase NBD_MAX_DEVICE.",
    ErrorCode.FSTAB_PARSE_ERROR: "The guest fstab contains syntax errors. Review the file manually.",
    ErrorCode.FSTAB_UUID_NOT_FOUND: "The filesystem UUID in fstab does not match any partition.",
    ErrorCode.BOOT_GRUB_INSTALL_FAILED: "Ensure grub2-install is available in the guest chroot.",
    ErrorCode.PROVIDER_AUTH_FAILED: "Check credentials (username, password, token) and network connectivity.",
    ErrorCode.PROVIDER_CONNECTION_FAILED: "Verify the host is reachable and firewall rules allow the connection.",
    ErrorCode.PROVIDER_VM_NOT_FOUND: "Verify the VM name or ID. Use list_vms to see available VMs.",
    ErrorCode.PROVIDER_DOWNLOAD_FAILED: "Check network connectivity and available disk space.",
    ErrorCode.PROVIDER_RATE_LIMITED: "Reduce concurrency or wait before retrying.",
    ErrorCode.MANIFEST_VALIDATION_FAILED: "Review the manifest against the schema documentation.",
    ErrorCode.WIN_BITLOCKER_DETECTED: "Decrypt the disk before migration (manage-bde -off C:).",
    ErrorCode.LUKS_KEY_MISSING: "Provide the LUKS passphrase via --luks-key or H2KVM_LUKS_KEY env var.",
    ErrorCode.HOOK_TIMEOUT: "Increase the hook timeout or check why the hook script is hanging.",
}


def _safe_int(x: Any, default: int = 1) -> int:
    try:
        return int(x)
    except Exception:  # pylint: disable=broad-exception-caught
        # int() may raise many error types depending on input; must never crash error handling.
        return default


def _clamp_exit_code(code: int) -> int:
    # Exit codes must be 0..255
    try:
        if code < 0 or code > 255:
            raise ValueError(f"Exit code must be in range 0-255, got {code}")
        return code
    except TypeError:
        raise ValueError(f"Exit code must be an integer, got {type(code).__name__}") from None


def _one_line(s: str, limit: int = 600) -> str:
    s = (s or "").strip().replace("\r", " ").replace("\n", " ")
    s = " ".join(s.split())
    return s if len(s) <= limit else (s[: limit - 3] + "...")


_SECRET_KEY_PARTS = (
    "pass",
    "password",
    "passwd",
    "secret",
    "token",
    "apikey",
    "api_key",
    "auth",
    "cookie",
    "session",
    "bearer",
    "private",
    "key",
)


def _is_secret_key(k: str) -> bool:
    ks = (k or "").lower()
    return any(p in ks for p in _SECRET_KEY_PARTS)


def _format_context_compact(ctx: dict[str, Any]) -> str:
    # Stable order, redaction, single-line.
    parts = []
    for k in sorted(ctx.keys()):
        v = ctx.get(k)
        if _is_secret_key(str(k)):
            parts.append(f"{k}=<redacted>")
        else:
            parts.append(f"{k}={v!r}")
    return ", ".join(parts)


def _redact_secrets(obj: Any) -> Any:
    """
    Recursively redact secrets in dictionaries.
    Returns a new object with secrets replaced by '***REDACTED***'.
    """
    if isinstance(obj, dict):
        return {
            k: "***REDACTED***" if _is_secret_key(str(k)) else _redact_secrets(v) for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        return type(obj)(_redact_secrets(item) for item in obj)
    return obj


@dataclass(eq=False)
class H2KvmError(Exception):
    """
    Base project error with:
      - stable fields for reporting/JSON
      - readable __str__ (what users see)
      - safe code handling (never crashes on int())
      - structured error_code (:class:`ErrorCode`) for machine-readable classification
      - human-friendly hint text for actionable guidance
    """

    code: int = 1
    msg: str = "error"
    cause: BaseException | None = None
    context: dict[str, Any] | None = None
    error_code: ErrorCode | None = None
    hint: str | None = None

    def __post_init__(self) -> None:
        self.code = _clamp_exit_code(_safe_int(self.code, default=1))
        self.msg = _one_line(self.msg) or self.__class__.__name__
        if self.context is None:
            self.context = {}

        # Auto-populate hint from the error code default table if not provided
        if self.hint is None and self.error_code is not None:
            self.hint = _ERROR_HINTS.get(self.error_code)

        super().__init__(self.msg)
        # Some tooling inspects Exception.args directly.
        self.args = (self.msg,)

    def format_error(self) -> str:
        """
        Return a user-friendly formatted error message.

        Includes the error code (if set), the main message, and an actionable
        hint when available.

        Returns:
            Formatted multi-line string suitable for CLI/log output.

        Example:
            >>> err = H2KvmError(
            ...     msg="Cannot connect to /dev/nbd0",
            ...     error_code=ErrorCode.NBD_CONNECT_FAILED,
            ... )
            >>> print(err.format_error())
            [E1101] Cannot connect to /dev/nbd0
            Hint: Ensure qemu-nbd is installed and the nbd kernel module is loaded.
        """
        parts: list[str] = []

        # Error code prefix
        if self.error_code is not None:
            parts.append(f"[{self.error_code.value}] {self.msg}")
        else:
            parts.append(self.msg)

        # Hint line
        if self.hint:
            parts.append(f"Hint: {self.hint}")

        return "\n".join(parts)

    def with_context(self, **ctx: Any) -> H2KvmError:
        """Merge additional key-value pairs into this error's context and return self."""
        if self.context is None:
            self.context = {}
        self.context.update(ctx)
        return self

    def user_message(self, *, include_context: bool = False, include_cause: bool = False) -> str:
        """
        Human-friendly message for CLI output/logs.

        If context contains 'solutions', 'causes', or 'doc_link', they are formatted
        as helpful guidance rather than as compact key=value pairs.
        """
        base = self.msg or self.__class__.__name__
        parts = [base]

        if include_context and self.context:
            # Extract helpful fields for special formatting
            solutions = self.context.get("solutions")
            causes = self.context.get("causes")
            doc_link = self.context.get("doc_link")

            # Remaining context (excluding helpful fields)
            remaining_ctx = {
                k: v for k, v in self.context.items() if k not in ("solutions", "causes", "doc_link")
            }

            # Add solutions if present
            if solutions:
                parts.append("\n\nSolutions:")
                for i, solution in enumerate(solutions, 1):
                    parts.append(f"\n  {i}. {solution}")

            # Add common causes if present
            if causes:
                parts.append("\n\nCommon causes:")
                for i, cause in enumerate(causes, 1):
                    parts.append(f"\n  {i}. {cause}")

            # Add documentation link if present
            if doc_link:
                parts.append(f"\n\nDocumentation: {doc_link}")

            # Add remaining context as compact format
            if remaining_ctx:
                parts.append(f"\n[{_one_line(_format_context_compact(remaining_ctx), limit=600)}]")

        if include_cause and self.cause is not None:
            parts.append(f"\n(cause: {type(self.cause).__name__}: {_one_line(str(self.cause))})")

        return "".join(parts)

    def __str__(self) -> str:
        # Default string should be clean and user-facing
        return self.user_message(include_context=False, include_cause=False)

    def to_dict(self, *, include_cause: bool = False) -> dict[str, Any]:
        """Return a JSON-serializable dict representation of this error."""
        d: dict[str, Any] = {
            "type": self.__class__.__name__,
            "code": self.code,
            "message": self.msg,
            "context": _redact_secrets(self.context or {}),
        }
        if self.error_code is not None:
            d["error_code"] = self.error_code.value
        if self.hint:
            d["hint"] = self.hint
        if include_cause and self.cause is not None:
            d["cause"] = {"type": type(self.cause).__name__, "message": _one_line(str(self.cause))}
        return d


class Fatal(H2KvmError):
    """
    User-facing fatal error (exit code should be honored by top-level main()).
    """


class VMwareError(H2KvmError):
    """
    vSphere/vCenter operation failed.
    Use for pyvmomi / SDK / ESXi errors.
    """


def wrap_fatal(msg: str, exc: BaseException | None = None, code: int = 1, **context: Any) -> Fatal:
    """Build a :class:`Fatal` error wrapping an underlying exception with a message and context."""
    return Fatal(code=code, msg=msg, cause=exc, context=context or None)


def wrap_vmware(msg: str, exc: BaseException | None = None, code: int = 50, **context: Any) -> VMwareError:
    """Build a :class:`VMwareError` wrapping an underlying exception with a message and context."""
    return VMwareError(code=code, msg=msg, cause=exc, context=context or None)


def format_exception_for_cli(e: BaseException, *, verbose: int = 0) -> str:
    """
    One-liner output for CLI.

    verbose=0: just message
    verbose=1: message + compact context (if any)
    verbose>=2: message + context + cause
    """
    if isinstance(e, H2KvmError):
        return e.user_message(
            include_context=(verbose >= 1),
            include_cause=(verbose >= 2),
        )

    # Non-project exceptions: keep them short unless verbose
    if verbose >= 2:
        return f"{type(e).__name__}: {_one_line(str(e))}"
    return _one_line(str(e)) or type(e).__name__


# Enhanced error creation helpers


# Constructs an error with many independent optional guidance fields (solutions/causes/doc_link/context).
def create_helpful_error(  # pylint: disable=too-many-arguments
    error_type: type[H2KvmError],
    message: str,
    *,
    code: int = 1,
    solutions: list[str] | None = None,
    causes: list[str] | None = None,
    doc_link: str | None = None,
    **context: Any,
) -> H2KvmError:
    """
    Create an error with helpful context including solutions and documentation links.

    Args:
        error_type: The exception class (Fatal, VMwareError, etc.)
        message: The main error message
        code: Exit code
        solutions: List of actionable solutions
        causes: List of common causes
        doc_link: Documentation link (relative to docs/)
        **context: Additional context key-value pairs

    Returns:
        Enhanced error instance

    Example:
        >>> err = create_helpful_error(
        ...     Fatal,
        ...     "VM not found: my-vm",
        ...     solutions=["Verify VM name with: govc ls /DC/vm/"],
        ...     doc_link="30-vSphere-Export.md#troubleshooting",
        ... )
    """
    # Add enhanced context
    if solutions:
        context["solutions"] = solutions
    if causes:
        context["causes"] = causes
    if doc_link:
        context["doc_link"] = f"https://github.com/ssahani/h2kvm/blob/main/docs/{doc_link}"

    return error_type(code=code, msg=message, context=context or None)


# ============================================================================
# Subsystem-Specific Exception Hierarchy
# ============================================================================

# Provider Errors
# ============================================================================


class ProviderError(H2KvmError):
    """Base class for source provider errors (VMware, Azure, backup sources)."""


class AzureError(ProviderError):
    """Azure provider operation failed (authentication, download, etc.)."""


class BackupSourceError(ProviderError):
    """Backup source operation failed (OVA, tar, backup file issues)."""


# Fixer Errors
# ============================================================================


class FixerError(H2KvmError):
    """Base class for fixer subsystem errors."""


class BootloaderFixerError(FixerError):
    """Bootloader fixing failed (GRUB, BCD, boot configuration)."""


class FilesystemFixerError(FixerError):
    """Filesystem fixing failed (fstab, mount points, UUID regeneration)."""


class NetworkFixerError(FixerError):
    """Network configuration fixing failed."""


class WindowsFixerError(FixerError):
    """Windows-specific fixing failed (VirtIO, registry, drivers)."""


class BitLockerDetectionError(WindowsFixerError):
    """BitLocker encryption detected - cannot migrate encrypted disk."""


# Storage Errors
# ============================================================================


class StorageError(H2KvmError):
    """Base class for storage and disk operation errors."""


class DiskConversionError(StorageError):
    """Disk format conversion failed (qcow2, vmdk, raw)."""


class LVMError(StorageError):
    """LVM operation failed (activation, detection, volume groups)."""


class LUKSError(StorageError):
    """LUKS encryption operation failed (unlock, key management)."""


class PartitionError(StorageError):
    """Partition operation failed (detection, mounting, UUID)."""


class NBDError(StorageError):
    """Network Block Device operation failed (connection, mapping)."""


# Configuration Errors
# ============================================================================


class ConfigurationError(H2KvmError):
    """Base class for configuration and validation errors."""


class ManifestError(ConfigurationError):
    """Manifest file validation or loading failed."""


class ManifestValidationError(ManifestError):
    """Manifest validation failed (schema, required fields, etc)."""


class CheckpointError(ManifestError):
    """Checkpoint creation or restoration failed."""


class ProfileError(ConfigurationError):
    """Profile loading or validation failed."""


class MappingError(ConfigurationError):
    """Resource mapping configuration error (network, storage mapping)."""


# Validation and Compliance Errors
# ============================================================================


class ValidationError(H2KvmError):
    """Base class for validation and compliance errors."""


class ComplianceError(ValidationError):
    """Compliance check failed (CIS benchmark, STIG)."""


class SanityCheckError(ValidationError):
    """Pre-migration sanity check failed."""


# Runtime Errors
# ============================================================================


class H2KvmRuntimeError(H2KvmError):
    """Base class for runtime execution errors (daemon, worker, operator)."""


class DaemonError(H2KvmRuntimeError):
    """Daemon operation failed."""


class WorkerError(H2KvmRuntimeError):
    """Worker execution failed."""


class OperatorError(H2KvmRuntimeError):
    """Kubernetes operator operation failed."""


class CyclicDependencyError(OperatorError):
    """Cyclic dependency detected in DAG."""


class InvalidDependencyError(OperatorError):
    """Invalid dependency specification in DAG."""


class HookExecutionError(H2KvmRuntimeError):
    """Hook execution failed (lifecycle hook error)."""


class HookTimeoutError(HookExecutionError):
    """Hook execution timed out."""


# Guest disk backend errors
# ============================================================================


class GuestBackendError(H2KvmError):
    """Base class for guest-disk backend (GuestKit / libguestfs) errors."""


# Backward-compatible alias (VMCraft demoted to GuestKit)
VMCraftError = GuestBackendError


class DeviceError(GuestBackendError):
    """Block device / privileged host command failed."""


class MountError(GuestBackendError):
    """VM disk mounting failed."""


class InspectionError(GuestBackendError):
    """VM inspection/analysis failed."""


# Infrastructure Errors
# ============================================================================


class InfrastructureError(H2KvmError):
    """Base class for infrastructure service errors."""


class SystemdError(InfrastructureError):
    """Systemd operation failed."""


class SSHError(InfrastructureError):
    """SSH operation failed (key injection, config)."""


class RollbackError(InfrastructureError):
    """Rollback operation failed (snapshot, restore)."""


# Command Execution Errors
# ============================================================================


class CommandError(H2KvmError):
    """Command execution failed (subprocess, shell command)."""
