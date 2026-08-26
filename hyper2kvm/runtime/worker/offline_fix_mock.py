# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Mock Offline-Fix Runner

Simulates an offline-fix VM worker for testing purposes without requiring
actual VM infrastructure, NBD, or partition mounting.

This mock runner:
- Validates the contract (request/response schemas)
- Simulates fix operations with realistic timing
- Generates realistic boot confidence scores
- Useful for CI/CD, unit tests, and development
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from .offline_fix_contract import (
    BootConfidence,
    BootMode,
    DetectedOS,
    FixOperation,
    FixOperationResult,
    FixResult,
    OfflineFixRequest,
    OfflineFixResponse,
    OfflineFixStatus,
    OSFamily,
)


class MockOfflineFixRunner:
    """
    Mock implementation of an offline-fix worker.

    Simulates the behavior of a real offline-fix VM without requiring
    actual NBD devices, partition mounting, or VM infrastructure.
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize mock runner.

        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.simulate_failures = False  # Set to True to test error handling
        self.simulated_duration_multiplier = 0.01  # Speed up for tests

    def run(self, request: OfflineFixRequest) -> OfflineFixResponse:
        """
        Execute offline fixes (mocked).

        Args:
            request: Offline fix request

        Returns:
            OfflineFixResponse: Simulated fix results
        """
        self.logger.info(f"🧪 Mock offline-fix runner starting job {request.job_id}")
        started_at = datetime.now(timezone.utc)

        # Simulate OS detection
        detected_os = self._simulate_os_detection(request)

        # Simulate fix operations
        operations_performed = []
        for operation in request.operations:
            op_result = self._simulate_operation(operation, request, detected_os)
            operations_performed.append(op_result)

            # Simulate operation duration
            if op_result.duration_seconds:
                time.sleep(op_result.duration_seconds * self.simulated_duration_multiplier)

        # Determine overall status
        status = self._determine_status(operations_performed)

        # Generate boot confidence
        boot_confidence = self._calculate_boot_confidence(operations_performed)

        # Collect applied/skipped fixes
        fixes_applied = [
            f"{op.operation.replace('_', ' ').title()}: {op.message}"
            for op in operations_performed
            if op.result == FixResult.SUCCESS
        ]
        fixes_skipped = [
            f"{op.operation.replace('_', ' ').title()}: {op.message}"
            for op in operations_performed
            if op.result == FixResult.SKIPPED
        ]

        # Generate warnings
        warnings = self._generate_warnings(operations_performed, detected_os)

        # Generate errors if simulating failures
        errors = []
        if self.simulate_failures:
            errors = ["Simulated failure for testing purposes"]
            status = OfflineFixStatus.PARTIAL

        # Generate recommendations
        recommended_actions = self._generate_recommendations(boot_confidence, status)

        completed_at = datetime.now(timezone.utc)
        duration_seconds = (completed_at - started_at).total_seconds()

        response = OfflineFixResponse(
            version="1.0",
            job_id=request.job_id,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration_seconds,
            detected_os=detected_os,
            operations_performed=operations_performed,
            fixes_applied=fixes_applied,
            fixes_skipped=fixes_skipped,
            output_image=request.output_path,
            output_size_bytes=self._estimate_output_size(request),
            backup_image=f"{request.image.path}.backup" if request.parameters.create_backup else None,
            boot_confidence=boot_confidence,
            warnings=warnings,
            errors=errors,
            recommended_actions=recommended_actions,
            worker_id="mock-offline-fix-runner",
            environment={
                "mode": "mock",
                "kernel": "6.6.8-200.fc39.x86_64",
                "qemu_version": "8.1.0 (mocked)",
                "simulation": True,
            },
        )

        self.logger.info(
            f"✅ Mock offline-fix job {request.job_id} completed: "
            f"status={status.value}, confidence={boot_confidence.score:.2f}"
        )

        return response

    def _simulate_os_detection(self, request: OfflineFixRequest) -> DetectedOS:
        """Simulate OS detection."""
        if request.os_hint:
            # Use hint if provided
            return DetectedOS(
                family=request.os_hint.family,
                name=f"{request.os_hint.family.title()} Linux",
                version=request.os_hint.version or "unknown",
                architecture=request.os_hint.architecture,
                boot_mode=request.os_hint.boot_mode,
                root_filesystem="xfs" if request.os_hint.family == OSFamily.CENTOS else "ext4",
                has_lvm=True,
                has_selinux=request.os_hint.family in [OSFamily.CENTOS, OSFamily.RHEL, OSFamily.FEDORA],
            )
        # Simulate detection
        return DetectedOS(
            family=OSFamily.CENTOS,
            name="CentOS Stream",
            version="9",
            version_id="9",
            architecture="x86_64",
            boot_mode=BootMode.BIOS,
            root_filesystem="xfs",
            has_lvm=True,
            has_selinux=True,
        )

    def _simulate_operation(
        self, operation: FixOperation, request: OfflineFixRequest, detected_os: DetectedOS
    ) -> FixOperationResult:
        """Simulate a single fix operation."""

        # Simulate dry-run mode
        if request.parameters.dry_run:
            return FixOperationResult(
                operation=operation,
                result=FixResult.SKIPPED,
                message="Skipped (dry-run mode)",
                duration_seconds=0.1,
            )

        # Operation-specific simulation
        if operation == FixOperation.GRUB_REGENERATE:
            if not request.parameters.update_grub:
                return self._skipped_result(operation, "disabled by parameters")
            return FixOperationResult(
                operation=operation,
                result=FixResult.SUCCESS,
                message="GRUB configuration regenerated successfully",
                duration_seconds=5.2,
                details={"grub_version": "2.06", "kernel_count": 3, "default_kernel": "6.1.0-13-amd64"},
            )

        if operation == FixOperation.INITRAMFS_REGENERATE:
            if not request.parameters.regen_initramfs:
                return self._skipped_result(operation, "disabled by parameters")
            return FixOperationResult(
                operation=operation,
                result=FixResult.SUCCESS,
                message="Initramfs rebuilt with virtio drivers",
                duration_seconds=45.8,
                details={
                    "tool": "dracut"
                    if detected_os.family in [OSFamily.CENTOS, OSFamily.FEDORA]
                    else "mkinitramfs",
                    "modules_added": ["virtio_blk", "virtio_scsi", "virtio_net", "virtio_pci"],
                },
            )

        if operation == FixOperation.FSTAB_UUID:
            return FixOperationResult(
                operation=operation,
                result=FixResult.SUCCESS,
                message="fstab converted to UUID",
                duration_seconds=1.3,
                details={"entries_updated": 3, "mode": request.parameters.fstab_mode},
            )

        if operation == FixOperation.VIRTIO_INJECT:
            if not request.parameters.inject_virtio:
                return self._skipped_result(operation, "disabled by parameters")
            return FixOperationResult(
                operation=operation,
                result=FixResult.SUCCESS,
                message="Virtio drivers injected",
                duration_seconds=8.5,
                details={"drivers": ["virtio_blk", "virtio_scsi", "virtio_net"], "method": "kernel_modules"},
            )

        if operation == FixOperation.VMWARE_TOOLS_REMOVE:
            if not request.parameters.remove_vmware_tools:
                return self._skipped_result(operation, "disabled by parameters")
            # Simulate partial success (common scenario)
            return FixOperationResult(
                operation=operation,
                result=FixResult.PARTIAL,
                message="VMware tools packages removed (some files remain)",
                duration_seconds=12.3,
                details={
                    "packages_removed": ["open-vm-tools", "vmware-tools"],
                    "remaining_files": ["/etc/vmware-tools"],
                },
            )

        if operation == FixOperation.SELINUX_RELABEL:
            if not request.parameters.selinux_relabel:
                return self._skipped_result(operation, "disabled by parameters")
            if not detected_os.has_selinux:
                return self._skipped_result(operation, "SELinux not installed")
            return FixOperationResult(
                operation=operation,
                result=FixResult.SUCCESS,
                message="SELinux contexts relabeled",
                duration_seconds=120.5,
                details={"files_relabeled": 15234, "policy": "targeted"},
            )

        if operation == FixOperation.NETWORK_STABILIZE:
            return FixOperationResult(
                operation=operation,
                result=FixResult.SUCCESS,
                message="Network configuration stabilized",
                duration_seconds=3.2,
                details={"interfaces_updated": 1, "naming_scheme": "predictable"},
            )

        # Default for unimplemented operations
        return FixOperationResult(
            operation=operation,
            result=FixResult.SKIPPED,
            message="Operation not implemented in mock runner",
            duration_seconds=0.1,
        )

    def _skipped_result(self, operation: FixOperation, reason: str) -> FixOperationResult:
        """Create a skipped operation result."""
        return FixOperationResult(
            operation=operation, result=FixResult.SKIPPED, message=f"Skipped: {reason}", duration_seconds=0.1
        )

    def _determine_status(self, operations: list[FixOperationResult]) -> OfflineFixStatus:
        """Determine overall job status from operation results."""
        if not operations:
            return OfflineFixStatus.FAILED

        results = [op.result for op in operations]

        if FixResult.FAILED in results:
            # Any failed operation = partial or failed
            success_count = results.count(FixResult.SUCCESS)
            if success_count > 0:
                return OfflineFixStatus.PARTIAL
            return OfflineFixStatus.FAILED

        if all(r == FixResult.SKIPPED for r in results):
            return OfflineFixStatus.PARTIAL

        if FixResult.PARTIAL in results:
            return OfflineFixStatus.PARTIAL

        return OfflineFixStatus.SUCCESS

    def _calculate_boot_confidence(self, operations: list[FixOperationResult]) -> BootConfidence:
        """Calculate boot confidence score based on operation results."""
        factors = {}

        # Check each critical operation
        for op in operations:
            if op.operation == FixOperation.GRUB_REGENERATE:
                factors["bootloader_valid"] = 1.0 if op.result == FixResult.SUCCESS else 0.0
            elif op.operation == FixOperation.INITRAMFS_REGENERATE:
                factors["initramfs_valid"] = 1.0 if op.result == FixResult.SUCCESS else 0.5
            elif op.operation == FixOperation.FSTAB_UUID:
                factors["fstab_valid"] = 1.0 if op.result == FixResult.SUCCESS else 0.3
            elif op.operation == FixOperation.VIRTIO_INJECT:
                if op.result == FixResult.SUCCESS:
                    factors["virtio_drivers"] = 0.95
                elif op.result == FixResult.PARTIAL:
                    factors["virtio_drivers"] = 0.75
                else:
                    factors["virtio_drivers"] = 0.5
            elif op.operation == FixOperation.SELINUX_RELABEL:
                if op.result == FixResult.SUCCESS:
                    factors["selinux_context"] = 0.90
                elif op.result == FixResult.SKIPPED:
                    factors["selinux_context"] = 1.0  # Not applicable
                else:
                    factors["selinux_context"] = 0.7

        # Set defaults for missing factors
        factors.setdefault("bootloader_valid", 0.8)
        factors.setdefault("initramfs_valid", 0.8)
        factors.setdefault("fstab_valid", 0.9)
        factors.setdefault("virtio_drivers", 0.85)
        factors.setdefault("selinux_context", 0.9)
        factors.setdefault("filesystem_clean", 1.0)

        # Calculate weighted average
        weights = {
            "bootloader_valid": 0.25,
            "initramfs_valid": 0.25,
            "fstab_valid": 0.20,
            "virtio_drivers": 0.15,
            "selinux_context": 0.10,
            "filesystem_clean": 0.05,
        }

        score = sum(factors[k] * weights[k] for k in factors)

        # Generate warnings
        warnings = []
        if factors["selinux_context"] < 0.95:
            warnings.append("SELinux relabel may trigger on first boot")
        if factors["virtio_drivers"] < 0.9:
            warnings.append("Some virtio drivers may not be present")

        return BootConfidence(score=round(score, 2), factors=factors, warnings=warnings)

    def _generate_warnings(self, operations: list[FixOperationResult], detected_os: DetectedOS) -> list[str]:
        """Generate warnings based on operation results."""
        warnings = []

        # Check for partial results
        for op in operations:
            if op.result == FixResult.PARTIAL:
                warnings.append(f"{op.operation}: {op.message}")

        # OS-specific warnings
        if detected_os.family == OSFamily.CENTOS and detected_os.version == "9":
            warnings.append("CentOS Stream 9: Ensure system is up-to-date before boot")

        return warnings

    def _generate_recommendations(
        self, boot_confidence: BootConfidence, status: OfflineFixStatus
    ) -> list[str]:
        """Generate recommended next steps."""
        recommendations = []

        if status == OfflineFixStatus.SUCCESS:
            if boot_confidence.score >= 0.95:
                recommendations.append("boot-test")
                recommendations.append("validate-guest-configuration")
            elif boot_confidence.score >= 0.85:
                recommendations.append("boot-test-required")
                recommendations.append("monitor-first-boot-closely")
            else:
                recommendations.append("review-fix-results-before-boot")
                recommendations.append("manual-intervention-may-be-needed")
        elif status == OfflineFixStatus.PARTIAL:
            recommendations.append("review-failed-operations")
            recommendations.append("consider-manual-fixes")
            recommendations.append("boot-test-with-caution")
        else:
            recommendations.append("investigate-failures")
            recommendations.append("do-not-boot")

        return recommendations

    def _estimate_output_size(self, request: OfflineFixRequest) -> Optional[int]:
        """Estimate output image size."""
        if request.image.size_bytes:
            # Simulate slight compression
            return int(request.image.size_bytes * 0.95)
        return None


# Convenience function for testing
def run_mock_offline_fix(request: OfflineFixRequest) -> OfflineFixResponse:
    """
    Run mock offline fix.

    Args:
        request: Offline fix request

    Returns:
        OfflineFixResponse: Simulated results
    """
    runner = MockOfflineFixRunner()
    return runner.run(request)
