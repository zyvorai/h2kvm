# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/worker/engine.py
"""
Worker Execution Engine.

Executes disk operation jobs with progress tracking, error handling, and
artifact generation.
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from ...core.guestfs_factory import create_guestfs
from .capabilities import CapabilityDetector, CapabilityLevel, get_detector
from .schemas import (
    ErrorInfo,
    JobMetrics,
    JobOutput,
    JobResult,
    JobSpec,
    JobState,
    OperationType,
    ProgressEvent,
)
from .state_machine import InvalidStateTransition, JobRegistry, JobStateMachine

if TYPE_CHECKING:
    from .metrics import WorkerMetrics

try:
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Health / readiness HTTP server (stdlib only)
# ---------------------------------------------------------------------------


class _HealthHandler(BaseHTTPRequestHandler):
    """
    Minimal HTTP request handler for health and readiness probes.

    Endpoints:
        GET /healthz  -- liveness probe.  Always returns 200 when the
                         server is running.  Response body is JSON with
                         ``status`` and ``active_jobs``.
        GET /readyz   -- readiness probe.  Returns 200 when the worker is
                         ready to accept new jobs, 503 otherwise.

    The handler is configured via ``server.health_server`` which must be
    a :class:`HealthServer` instance attached to the underlying
    :class:`HTTPServer`.
    """

    # Suppress default stderr request logging
    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        hs: HealthServer = self.server.health_server  # type: ignore[attr-defined]

        if self.path == "/healthz":
            body = json.dumps(
                {
                    "status": "healthy",
                    "active_jobs": hs.active_jobs,
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/readyz":
            if hs.ready:
                body = json.dumps(
                    {
                        "status": "ready",
                        "active_jobs": hs.active_jobs,
                    }
                ).encode("utf-8")
                self.send_response(200)
            else:
                body = json.dumps(
                    {
                        "status": "not_ready",
                    }
                ).encode("utf-8")
                self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        else:
            self.send_error(404, "Not Found")


class HealthServer:
    """
    Lightweight HTTP health/readiness server for the worker engine.

    Runs in a daemon thread so it does not prevent process exit.  The
    server exposes two endpoints consumed by container orchestrators,
    load-balancers, or monitoring systems:

    * ``GET /healthz`` -- liveness.  Returns ``200`` with JSON payload
      ``{"status": "healthy", "active_jobs": N}``.
    * ``GET /readyz`` -- readiness.  Returns ``200`` when the worker is
      ready to accept jobs, ``503`` otherwise.

    Args:
        port: TCP port to bind (default ``8081``).
        host: Bind address (default ``"0.0.0.0"``).

    Example::

        hs = HealthServer(port=8081)
        hs.ready = True
        hs.start()
        # ... later ...
        hs.active_jobs = 3
        # ... on shutdown ...
        hs.stop()
    """

    def __init__(self, port: int = 8081, host: str = "0.0.0.0"):
        self.port = port
        self.host = host
        self._active_jobs: int = 0
        self._active_jobs_lock: threading.Lock = threading.Lock()
        self.ready: bool = False

    @property
    def active_jobs(self) -> int:
        with self._active_jobs_lock:
            return self._active_jobs

    @active_jobs.setter
    def active_jobs(self, value: int) -> None:
        with self._active_jobs_lock:
            self._active_jobs = value

    def increment_active_jobs(self) -> None:
        with self._active_jobs_lock:
            self._active_jobs += 1

    def decrement_active_jobs(self) -> None:
        with self._active_jobs_lock:
            self._active_jobs = max(0, self._active_jobs - 1)

        self._httpd: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._logger = logging.getLogger(f"{__name__}.health")

    def start(self) -> None:
        """Start serving health endpoints in a background daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            return  # already running

        try:
            self._httpd = HTTPServer((self.host, self.port), _HealthHandler)
            self._httpd.health_server = self  # type: ignore[attr-defined]
        except OSError as exc:
            self._logger.warning("Failed to start health server on %s:%d: %s", self.host, self.port, exc)
            return

        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="health-server",
            daemon=True,
        )
        self._thread.start()
        self._logger.info("Health server listening on %s:%d", self.host, self.port)

    def stop(self) -> None:
        """Shutdown the HTTP server and join the background thread."""
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        self._logger.debug("Health server stopped")


class WorkerEngine:
    """
    Worker execution engine for disk operations.

    Responsible for:
    - Job validation against worker capabilities
    - Job execution with progress tracking
    - Error handling and retries
    - Artifact generation and cleanup
    - Progress event streaming
    """

    def __init__(
        self,
        worker_id: str,
        capability_detector: CapabilityDetector | None = None,
        job_registry: JobRegistry | None = None,
        event_callback: Callable[[ProgressEvent], None] | None = None,
        metrics: WorkerMetrics | None = None,
        health_port: int | None = 8081,
    ):
        """
        Initialize worker engine.

        Args:
            worker_id: Unique worker identifier
            capability_detector: Capability detector (default: global instance)
            job_registry: Job registry for state management
            event_callback: Optional callback for progress events
            metrics: Optional metrics collector for Prometheus
            health_port: TCP port for the HTTP health endpoint (default 8081).
                Set to ``None`` or ``0`` to disable.
        """
        self.worker_id = worker_id
        self.detector = capability_detector or get_detector()
        self.registry = job_registry or JobRegistry()
        self.event_callback = event_callback
        self.metrics = metrics

        self.logger = logging.getLogger(f"{__name__}.{worker_id}")
        self.current_job_id: str | None = None

        # Start the health/readiness HTTP server
        self._health_server: HealthServer | None = None
        if health_port:
            self._health_server = HealthServer(port=health_port)
            self._health_server.ready = True
            self._health_server.start()

    def _emit_event(self, event: ProgressEvent) -> None:
        """Emit progress event."""
        self.logger.info(f"[{event.job_id}] {event.phase}: {event.progress_percent}% - {event.message}")

        if self.event_callback:
            try:
                self.event_callback(event)
            except Exception as e:
                self.logger.exception(f"Event callback failed: {e}")

    def _validate_job(self, job_spec: JobSpec) -> tuple[bool, str | None]:
        """
        Validate job against worker capabilities.

        Args:
            job_spec: Job specification

        Returns:
            Tuple of (valid, error_message)
        """
        # Check capability requirements
        self.detector.detect_capabilities()
        requirements = {
            "nbd": job_spec.capability_requirements.needs_nbd,
            "lvm": job_spec.capability_requirements.needs_lvm,
            "mount": job_spec.capability_requirements.needs_mount,
            "selinux": job_spec.capability_requirements.needs_selinux_tools,
        }

        can_execute, reason = self.detector.can_execute_job(requirements)
        if not can_execute:
            return False, f"Worker cannot execute job: {reason}"

        # Check if image exists
        image_path = Path(job_spec.image.path)
        if not image_path.exists():
            return False, f"Image not found: {job_spec.image.path}"

        # Check output directory is writable
        output_path = Path(job_spec.artifacts.output_path)
        if not output_path.exists():
            try:
                output_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return False, f"Cannot create output directory: {e}"

        return True, None

    def execute_job(self, job_spec: JobSpec) -> JobResult:
        """
        Execute a job.

        Args:
            job_spec: Job specification

        Returns:
            JobResult with execution outcome
        """
        start_time = time.time()
        self.current_job_id = job_spec.job_id
        operation = job_spec.operation.value

        # Track active jobs for health endpoint
        if self._health_server:
            self._health_server.increment_active_jobs()

        # Record migration start in metrics
        if self.metrics:
            self.metrics.record_migration_start(operation)

        # Register job
        state_machine = self.registry.register(job_spec)

        try:
            # Validate job
            self._emit_event(
                ProgressEvent(
                    job_id=job_spec.job_id,
                    phase="validation",
                    progress_percent=0,
                    message="Validating job specification",
                )
            )

            valid, error_msg = self._validate_job(job_spec)
            if not valid:
                state_machine.transition(JobState.FAILED, error_msg)
                return self._create_error_result(
                    job_spec, "validation", "VALIDATION_FAILED", error_msg, start_time
                )

            state_machine.transition(JobState.VALIDATED, "Job validated")
            state_machine.transition(JobState.QUEUED, "Immediately queued for execution")
            state_machine.transition(JobState.ASSIGNED, f"Assigned to worker {self.worker_id}")
            state_machine.transition(JobState.RUNNING, "Execution started")

            # Execute operation based on type
            operation_result = self._execute_operation(job_spec, state_machine)

            # Mark as completed
            state_machine.transition(JobState.COMPLETED, "Job completed successfully")

            execution_time = int(time.time() - start_time)

            # Record successful migration in metrics
            if self.metrics:
                self.metrics.record_migration_complete(
                    operation=operation, duration=execution_time, success=True
                )

            self._emit_event(
                ProgressEvent(
                    job_id=job_spec.job_id,
                    phase="completed",
                    progress_percent=100,
                    message=f"Job completed in {execution_time}s",
                )
            )

            return JobResult(
                job_id=job_spec.job_id,
                status=JobState.COMPLETED,
                outputs=operation_result["outputs"],
                metrics=JobMetrics(execution_seconds=execution_time, **operation_result.get("metrics", {})),
                worker_id=self.worker_id,
            )

        except Exception as e:
            # Handle unexpected errors
            self.logger.exception(f"Job {job_spec.job_id} failed with exception: {e}")
            self.logger.debug(traceback.format_exc())

            execution_time = int(time.time() - start_time)
            error_type = type(e).__name__

            # Record failed migration in metrics
            if self.metrics:
                self.metrics.record_migration_complete(
                    operation=operation, duration=execution_time, success=False, error_type=error_type
                )

            try:
                state_machine.transition(JobState.FAILED, str(e))
            except InvalidStateTransition:
                pass  # Already in failed state

            return self._create_error_result(
                job_spec,
                "execution",
                "EXECUTION_FAILED",
                str(e),
                start_time,
                traceback=traceback.format_exc(),
            )

        finally:
            self.current_job_id = None
            if self._health_server:
                self._health_server.decrement_active_jobs()

    def _execute_operation(self, job_spec: JobSpec, state_machine: JobStateMachine) -> dict:
        """
        Execute job operation based on type.

        Args:
            job_spec: Job specification
            state_machine: Job state machine

        Returns:
            Dictionary with outputs and metrics
        """
        operation_map = {
            OperationType.INSPECT: self._op_inspect,
            OperationType.CONVERT: self._op_convert,
            OperationType.OFFLINE_FIX: self._op_offline_fix,
            OperationType.BOOT_REPAIR: self._op_boot_repair,
            OperationType.SELINUX_PREP: self._op_selinux_prep,
            OperationType.LVM_REPAIR: self._op_lvm_repair,
            OperationType.FS_REPAIR: self._op_fs_repair,
            OperationType.INITRAMFS_REGEN: self._op_initramfs_regen,
        }

        operation_func = operation_map.get(job_spec.operation)
        if not operation_func:
            raise ValueError(
                f"Unsupported operation '{job_spec.operation}'. "
                f"Supported operations: {', '.join(operation_map.keys())}."
            )

        return operation_func(job_spec, state_machine)

    def _op_inspect(self, job_spec: JobSpec, state_machine: JobStateMachine) -> dict:
        """Execute inspect operation."""
        state_machine.transition(JobState.PROGRESSING, "Starting inspection")

        self._emit_event(
            ProgressEvent(
                job_id=job_spec.job_id,
                phase="inspection",
                progress_percent=20,
                message=f"Inspecting {job_spec.image.path}",
            )
        )

        # Import here to avoid circular dependencies
        from ..inspector import DiskInspector

        inspector = DiskInspector()

        start_time = time.time()
        inspection_result = inspector.inspect(job_spec.image.path)
        inspect_time = int(time.time() - start_time)

        # Save inspection report
        output_path = Path(job_spec.artifacts.output_path)
        report_file = output_path / f"{job_spec.job_id}_inspection.json"

        with open(report_file, "w") as f:
            json.dump(inspection_result, f, indent=2, default=str)

        self._emit_event(
            ProgressEvent(
                job_id=job_spec.job_id,
                phase="inspection",
                progress_percent=100,
                message="Inspection completed",
            )
        )

        return {
            "outputs": JobOutput(report=str(report_file), logs=None),
            "metrics": {"inspection_seconds": inspect_time},
        }

    def _op_convert(self, job_spec: JobSpec, state_machine: JobStateMachine) -> dict:
        """Execute convert operation."""
        state_machine.transition(JobState.PROGRESSING, "Starting conversion")

        self._emit_event(
            ProgressEvent(
                job_id=job_spec.job_id,
                phase="conversion",
                progress_percent=10,
                message="Preparing for conversion",
            )
        )

        # Get conversion parameters
        output_format = job_spec.parameters.get("output_format", "qcow2")
        compress = job_spec.parameters.get("compress", True)

        # Import conversion utilities
        import subprocess

        input_path = job_spec.image.path
        output_path = Path(job_spec.artifacts.output_path)
        output_file = output_path / f"{Path(input_path).stem}.{output_format}"

        self._emit_event(
            ProgressEvent(
                job_id=job_spec.job_id,
                phase="conversion",
                progress_percent=20,
                message=f"Converting to {output_format}",
            )
        )

        # Build qemu-img convert command
        cmd = ["qemu-img", "convert", "-p", "-O", output_format]

        if compress and output_format == "qcow2":
            cmd.append("-c")  # Enable compression for qcow2

        cmd.extend([input_path, str(output_file)])

        start_time = time.time()

        try:
            from h2kvm.converters.qemu.converter import run_qemu_img_convert

            run_qemu_img_convert(
                self.logger,
                cmd,
                output_file,
                src=Path(input_path),
                task_label=f"Worker conversion ({output_format})",
                log_every_s=15.0,
            )
            convert_time = int(time.time() - start_time)

            self._emit_event(
                ProgressEvent(
                    job_id=job_spec.job_id,
                    phase="conversion",
                    progress_percent=100,
                    message=f"Conversion completed in {convert_time}s",
                )
            )

            return {
                "outputs": JobOutput(fixed_image=str(output_file), logs=None),
                "metrics": {"conversion_seconds": convert_time},
            }

        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"Disk conversion timed out after {job_spec.execution_policy.timeout_seconds}s. "
                f"The disk image may be very large or the system is under heavy I/O load. "
                f"Increase the timeout in execution_policy or use a faster storage backend."
            ) from e
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Disk conversion failed. Check that qemu-img is installed and the source "
                f"disk image is valid. Detail: {e.stderr}"
            ) from e

    def _op_offline_fix(self, job_spec: JobSpec, state_machine: JobStateMachine) -> dict:
        """Execute offline_fix operation with adaptive capability detection."""
        state_machine.transition(JobState.PROGRESSING, "Starting offline fix operation")

        # Detect capability level
        capability_level = self.detector.detect_capability_level()
        capability_report = self.detector.get_capability_level_report(capability_level)

        self.logger.info(f"Detected capability level: {capability_level.name}")
        self.logger.info(f"Available operations: {len(capability_report['operations'])}")

        # Execute based on detected capabilities
        if capability_level == CapabilityLevel.USERSPACE_ONLY:
            return self._execute_userspace_conversion(job_spec, state_machine, capability_report)
        if capability_level == CapabilityLevel.NBD_INSPECTION:
            return self._execute_with_inspection(job_spec, state_machine, capability_report)
        # FULL_OFFLINE_FIXES
        return self._execute_full_migration(job_spec, state_machine, capability_report)

    def _execute_userspace_conversion(
        self, job_spec: JobSpec, state_machine: JobStateMachine, capability_report: dict
    ) -> dict:
        """
        Execute basic VMDK→QCOW2 conversion without NBD (Level 1).

        Workflow:
        1. Parse VMDK descriptor
        2. Convert VMDK → QCOW2 using qemu-img
        3. Apply compression if requested
        4. Return success with warnings about skipped operations
        """
        self.logger.info("🔧 Executing USERSPACE-ONLY conversion")
        self.logger.info("   Strategy: Basic conversion, no guest modifications")

        self._emit_event(
            ProgressEvent(
                job_id=job_spec.job_id,
                phase="conversion",
                progress_percent=10,
                message="Preparing for conversion (userspace-only mode)",
            )
        )

        # Get conversion parameters
        output_format = job_spec.parameters.get("output_format", "qcow2")
        compress = job_spec.parameters.get("compress", True)

        input_path = job_spec.image.path
        output_path = Path(job_spec.artifacts.output_path)
        output_file = output_path / f"{Path(input_path).stem}.{output_format}"

        self._emit_event(
            ProgressEvent(
                job_id=job_spec.job_id,
                phase="conversion",
                progress_percent=20,
                message=f"Converting to {output_format}",
            )
        )

        # Build qemu-img convert command
        cmd = ["qemu-img", "convert", "-p", "-O", output_format]

        if compress and output_format == "qcow2":
            cmd.append("-c")  # Enable compression for qcow2

        cmd.extend([input_path, str(output_file)])

        start_time = time.time()

        try:
            from h2kvm.converters.qemu.converter import run_qemu_img_convert

            run_qemu_img_convert(
                self.logger,
                cmd,
                output_file,
                src=Path(input_path),
                task_label=f"Worker conversion ({output_format})",
                log_every_s=15.0,
            )
            convert_time = int(time.time() - start_time)

            self._emit_event(
                ProgressEvent(
                    job_id=job_spec.job_id,
                    phase="conversion",
                    progress_percent=100,
                    message=f"Conversion completed in {convert_time}s",
                )
            )

            self.logger.warning("⚠️  NOTE: Offline fixes skipped (NBD unavailable)")

            return {
                "outputs": JobOutput(fixed_image=str(output_file), logs=None),
                "metrics": {
                    "conversion_seconds": convert_time,
                    "offline_fixes_applied": False,
                    "capability_level": capability_report["level_name"],
                },
                "warnings": [
                    "Offline fixes skipped (NBD partition devices unavailable)",
                    "Guest may require manual configuration before first boot",
                    "Virtio drivers not injected - manual installation may be required",
                ],
                "capability_info": capability_report,
            }

        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"Disk conversion timed out after {job_spec.execution_policy.timeout_seconds}s. "
                f"The disk image may be very large or the system is under heavy I/O load. "
                f"Increase the timeout in execution_policy or use a faster storage backend."
            ) from e
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Disk conversion failed. Check that qemu-img is installed and the source "
                f"disk image is valid. Detail: {e.stderr}"
            ) from e

    def _execute_with_inspection(
        self, job_spec: JobSpec, state_machine: JobStateMachine, capability_report: dict
    ) -> dict:
        """
        Execute conversion with NBD inspection (Level 2).

        Workflow:
        1. Basic conversion (same as Level 1)
        2. Attach to NBD device for inspection
        3. Read partition table
        4. Detect filesystems
        5. Inspect LVM metadata
        6. Return with detailed disk information
        """
        self.logger.info("🔧 Executing NBD INSPECTION conversion")
        self.logger.info("   Strategy: Conversion + disk inspection (no mounting)")

        # First do basic conversion
        result = self._execute_userspace_conversion(job_spec, state_machine, capability_report)

        # Add inspection phase
        self._emit_event(
            ProgressEvent(
                job_id=job_spec.job_id,
                phase="inspection",
                progress_percent=25,
                message="Attaching to NBD for inspection",
            )
        )

        # Perform GuestKit/libguestfs disk inspection
        inspection_report = None
        try:
            output_image = Path(result["outputs"].fixed_image)

            self._emit_event(
                ProgressEvent(
                    job_id=job_spec.job_id,
                    phase="inspection",
                    progress_percent=50,
                    message="Analyzing disk structure...",
                )
            )

            inspection_report = self._inspect_disk_with_guestfs(output_image)

            self._emit_event(
                ProgressEvent(
                    job_id=job_spec.job_id,
                    phase="inspection",
                    progress_percent=100,
                    message=f"Inspection complete: {len(inspection_report['partitions'])} partitions found",
                )
            )

            # Log inspection summary
            self.logger.info("✓ Disk inspection completed:")
            self.logger.info(f"  Partitions: {len(inspection_report['partitions'])}")
            self.logger.info(f"  LVM PVs: {len(inspection_report['lvm']['physical_volumes'])}")
            self.logger.info(f"  LVM VGs: {len(inspection_report['lvm']['volume_groups'])}")
            self.logger.info(f"  LVM LVs: {len(inspection_report['lvm']['logical_volumes'])}")
            self.logger.info(f"  Filesystems: {len(inspection_report['filesystems'])}")

        except Exception as e:
            self.logger.warning(f"⚠️  Disk inspection failed: {e}")
            self.logger.debug(f"Inspection error details: {traceback.format_exc()}")
            result["warnings"].append(f"GuestFS inspection failed: {e!s}")

        # Add inspection report to result
        if inspection_report:
            result["inspection"] = inspection_report
            result["metrics"]["partitions_detected"] = len(inspection_report["partitions"])
            result["metrics"]["lvm_volumes_detected"] = len(inspection_report["lvm"]["logical_volumes"])
        else:
            result["warnings"].append("Disk inspection unavailable")

        return result

    def _inspect_disk_with_guestfs(self, image_path: Path) -> dict:
        """Inspect a disk image via GuestKit/libguestfs (replaces VMCraft NBD manager)."""
        g = create_guestfs(backend="guestkit")
        try:
            g.add_drive_ro(str(image_path))
            g.launch()
            partitions = list(g.list_partitions() or [])
            filesystems: list[dict] = []
            for part in partitions:
                entry: dict = {"device": part}
                try:
                    entry["fstype"] = g.vfs_type(part)
                except Exception:  # pylint: disable=broad-exception-caught
                    entry["fstype"] = None
                try:
                    entry["uuid"] = g.vfs_uuid(part)
                except Exception:  # pylint: disable=broad-exception-caught
                    entry["uuid"] = None
                filesystems.append(entry)

            lvm = {
                "physical_volumes": [],
                "volume_groups": [],
                "logical_volumes": [],
            }
            try:
                g.vgscan()
                lvm["physical_volumes"] = list(g.pvs() or [])
                lvm["volume_groups"] = list(g.vgs() or [])
                lvm["logical_volumes"] = list(g.lvs() or [])
            except Exception as e:  # pylint: disable=broad-exception-caught
                self.logger.debug("LVM probe skipped: %s", e)

            return {
                "partitions": [{"device": p} for p in partitions],
                "filesystems": filesystems,
                "lvm": lvm,
            }
        finally:
            try:
                g.shutdown()
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            try:
                g.close()
            except Exception:  # pylint: disable=broad-exception-caught
                pass

    def _execute_full_migration(
        self, job_spec: JobSpec, state_machine: JobStateMachine, capability_report: dict
    ) -> dict:
        """
        Execute full migration with offline fixes (Level 3).

        Workflow:
        1. Basic conversion
        2. GuestKit/libguestfs offline fixes (fstab, initramfs, GRUB, network, tools)
        3. Return KVM-ready image
        """
        self.logger.info("🔧 Executing FULL OFFLINE FIXES migration")
        self.logger.info("   Strategy: Complete migration with guest modifications")

        # First do conversion
        self._emit_event(
            ProgressEvent(
                job_id=job_spec.job_id,
                phase="conversion",
                progress_percent=10,
                message="Converting to QCOW2",
            )
        )

        # Execute conversion
        conversion_result = self._execute_userspace_conversion(job_spec, state_machine, capability_report)

        # Apply offline fixes
        self._emit_event(
            ProgressEvent(
                job_id=job_spec.job_id,
                phase="offline_fixes",
                progress_percent=30,
                message="Preparing offline fixes",
            )
        )

        # Get converted image path
        fixed_image_path = Path(conversion_result["outputs"].fixed_image)

        # Integrate with OfflineFSFix
        try:
            from ..fixers.offline_fixer import OfflineFSFix

            self._emit_event(
                ProgressEvent(
                    job_id=job_spec.job_id,
                    phase="offline_fixes",
                    progress_percent=40,
                    message="Mounting guest filesystem",
                )
            )

            # Create OfflineFSFix instance
            offline_fixer = OfflineFSFix(
                logger=self.logger,
                image=fixed_image_path,
                dry_run=job_spec.parameters.get("dry_run", False),
                no_backup=job_spec.parameters.get("no_backup", False),
                print_fstab=job_spec.parameters.get("print_fstab", False),
                update_grub=job_spec.parameters.get("update_grub", True),
                regen_initramfs=job_spec.parameters.get("regen_initramfs", True),
                fstab_mode=job_spec.parameters.get("fstab_mode", "uuid"),
                report_path=Path(job_spec.artifacts.output_path) / f"{job_spec.job_id}_offline_fixes.json",
                remove_vmware_tools=job_spec.parameters.get("remove_vmware_tools", True),
                enable_rdp=job_spec.parameters.get("enable_rdp"),
                inject_cloud_init=job_spec.parameters.get("inject_cloud_init"),
                firstboot_scripts=job_spec.parameters.get("firstboot_scripts"),
                network_config_inject=job_spec.parameters.get("network_config_inject"),
                user_config_inject=job_spec.parameters.get("user_config_inject"),
                service_config_inject=job_spec.parameters.get("service_config_inject"),
                hostname_config_inject=job_spec.parameters.get("hostname_config_inject"),
                recovery_manager=None,
                resize=job_spec.parameters.get("resize"),
                virtio_drivers_dir=job_spec.parameters.get("virtio_drivers_dir"),
                luks_enable=job_spec.parameters.get("luks_enable", False),
                luks_passphrase=job_spec.parameters.get("luks_passphrase"),
            )

            self._emit_event(
                ProgressEvent(
                    job_id=job_spec.job_id,
                    phase="offline_fixes",
                    progress_percent=60,
                    message="Running offline fixes",
                )
            )

            # Execute offline fixes
            offline_fixer.run()

            self._emit_event(
                ProgressEvent(
                    job_id=job_spec.job_id,
                    phase="offline_fixes",
                    progress_percent=100,
                    message="Offline fixes completed",
                )
            )

            self.logger.info("✅ Full migration completed successfully")
            self.logger.info("🎉 Guest is ready to boot in KVM/KubeVirt")

            # Parse fixes from report
            fixes_applied = []
            if offline_fixer.report:
                changes = offline_fixer.report.get("changes", {})
                if changes.get("fstab"):
                    fixes_applied.append("fstab stabilized with UUID-based mounts")
                if changes.get("grub"):
                    fixes_applied.append("GRUB configuration regenerated")
                if changes.get("initramfs"):
                    fixes_applied.append("Initramfs rebuilt with virtio drivers")
                if changes.get("network"):
                    fixes_applied.append("Network configuration updated")
                if changes.get("vmware_tools"):
                    fixes_applied.append("VMware tools removed")

            return {
                "outputs": JobOutput(
                    fixed_image=str(fixed_image_path),
                    logs=None,
                    report=str(offline_fixer.report_path)
                    if hasattr(offline_fixer, "report_path") and offline_fixer.report_path
                    else None,
                ),
                "metrics": {
                    **conversion_result.get("metrics", {}),
                    "offline_fixes_applied": True,
                    "capability_level": capability_report["level_name"],
                    "fixes_count": len(fixes_applied),
                },
                "warnings": [],
                "fixes_applied": fixes_applied
                if fixes_applied
                else ["Offline fixes applied (see report for details)"],
                "capability_info": capability_report,
                "offline_fixer_report": offline_fixer.report if hasattr(offline_fixer, "report") else None,
            }

        except ImportError as e:
            # OfflineFSFix not available - fall back to placeholder
            self.logger.warning(f"OfflineFSFix import failed: {e}")
            self.logger.warning("Falling back to conversion-only mode")

            self._emit_event(
                ProgressEvent(
                    job_id=job_spec.job_id,
                    phase="offline_fixes",
                    progress_percent=100,
                    message="Offline fixes skipped (OfflineFSFix not available)",
                )
            )

            return {
                "outputs": JobOutput(fixed_image=str(fixed_image_path), logs=None),
                "metrics": {
                    **conversion_result.get("metrics", {}),
                    "offline_fixes_applied": False,
                    "capability_level": capability_report["level_name"],
                },
                "warnings": [
                    "OfflineFSFix not available - offline fixes skipped",
                    "Image converted but may require manual configuration",
                ],
                "fixes_applied": [],
                "capability_info": capability_report,
            }

        except Exception as e:
            # Offline fixes failed - return partial result
            self.logger.exception(f"Offline fixes failed: {e}")
            self.logger.debug(f"Traceback: {traceback.format_exc()}")

            self._emit_event(
                ProgressEvent(
                    job_id=job_spec.job_id,
                    phase="offline_fixes",
                    progress_percent=0,
                    message=f"Offline fixes failed: {e!s}",
                )
            )

            return {
                "outputs": JobOutput(fixed_image=str(fixed_image_path), logs=None),
                "metrics": {
                    **conversion_result.get("metrics", {}),
                    "offline_fixes_applied": False,
                    "capability_level": capability_report["level_name"],
                },
                "warnings": [
                    f"Offline fixes failed: {e!s}",
                    "Image was converted but may not boot without manual intervention",
                ],
                "fixes_applied": [],
                "capability_info": capability_report,
                "error": str(e),
            }

    def _op_boot_repair(self, job_spec: JobSpec, state_machine: JobStateMachine) -> dict:
        """Execute boot_repair operation."""
        # Placeholder - would integrate with boot repair logic
        return {"outputs": JobOutput(), "metrics": {}}

    def _op_selinux_prep(self, job_spec: JobSpec, state_machine: JobStateMachine) -> dict:
        """Execute selinux_prep operation."""
        # Placeholder - would integrate with SELinux relabel logic
        return {"outputs": JobOutput(), "metrics": {}}

    def _op_lvm_repair(self, job_spec: JobSpec, state_machine: JobStateMachine) -> dict:
        """Execute lvm_repair operation."""
        # Placeholder - would integrate with LVM repair logic
        return {"outputs": JobOutput(), "metrics": {}}

    def _op_fs_repair(self, job_spec: JobSpec, state_machine: JobStateMachine) -> dict:
        """Execute fs_repair operation."""
        # Placeholder - would integrate with fsck logic
        return {"outputs": JobOutput(), "metrics": {}}

    def _op_initramfs_regen(self, job_spec: JobSpec, state_machine: JobStateMachine) -> dict:
        """Execute initramfs_regenerate operation."""
        # Placeholder - would integrate with initramfs regeneration
        return {"outputs": JobOutput(), "metrics": {}}

    def _create_error_result(
        self,
        job_spec: JobSpec,
        phase: str,
        error_code: str,
        error_message: str,
        start_time: float,
        traceback: str | None = None,
    ) -> JobResult:
        """Create error result for failed job."""
        execution_time = int(time.time() - start_time)

        self._emit_event(
            ProgressEvent(
                job_id=job_spec.job_id,
                phase="failed",
                progress_percent=0,
                message=f"Job failed: {error_message}",
            )
        )

        return JobResult(
            job_id=job_spec.job_id,
            status=JobState.FAILED,
            error=ErrorInfo(phase=phase, code=error_code, message=error_message, stack_trace=traceback),
            metrics=JobMetrics(execution_seconds=execution_time),
            worker_id=self.worker_id,
        )


def create_sample_job_spec(
    image_path: str, output_dir: str, operation: OperationType = OperationType.INSPECT
) -> JobSpec:
    """
    Create a sample job specification for testing.

    Args:
        image_path: Path to disk image
        output_dir: Output directory path
        operation: Operation type

    Returns:
        JobSpec instance
    """
    from .schemas import ArtifactConfig, AuditInfo, ImageSpec

    return JobSpec(
        job_id=str(uuid.uuid4()),
        operation=operation,
        image=ImageSpec(path=image_path, format="qcow2"),
        artifacts=ArtifactConfig(output_path=output_dir),
        audit=AuditInfo(requested_by="test-user"),
    )
