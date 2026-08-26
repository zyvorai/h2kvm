#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Worker Job Protocol Example.

Demonstrates the complete worker job lifecycle:
1. Capability detection
2. Job specification creation
3. Job execution with progress tracking
4. Result handling
"""

import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from hyper2kvm.runtime.worker import JobSpec, OperationType, WorkerCapabilities
from hyper2kvm.runtime.worker.capabilities import get_detector
from hyper2kvm.runtime.worker.engine import WorkerEngine, create_sample_job_spec
from hyper2kvm.runtime.worker.schemas import ArtifactConfig, AuditInfo, ImageSpec


def print_banner(text: str):
    """Print a formatted banner."""
    print(f"\n{'=' * 70}")
    print(f"  {text}")
    print(f"{'=' * 70}\n")


def detect_environment():
    """Detect and display execution environment."""
    print_banner("🔍 Environment Detection")

    detector = get_detector()

    # Detect execution mode
    mode = detector.detect_execution_mode()
    print(f"Execution Mode: {mode}")

    # Detect capabilities
    capabilities = detector.detect_capabilities()
    print("\nAvailable Capabilities:")
    for cap, available in capabilities.items():
        status = "✅" if available else "❌"
        print(f"  {status} {cap}: {available}")

    # Get system info
    sys_info = detector.get_system_info()
    print("\nSystem Information:")
    print(f"  Hostname: {sys_info.get('hostname', 'unknown')}")
    print(f"  OS: {sys_info.get('os', 'unknown')} {sys_info.get('os_release', '')}")
    print(f"  Memory: {sys_info.get('memory_gb', 0)} GB")
    print(f"  Disk Space: {sys_info.get('disk_space_gb', 0)} GB")

    return mode, capabilities, sys_info


def create_job_example():
    """Create an example job specification."""
    print_banner("📝 Job Specification Example")

    job_spec = JobSpec(
        job_id="example-job-001",
        operation=OperationType.INSPECT,
        image=ImageSpec(path="/tmp/test.qcow2", format="qcow2"),
        artifacts=ArtifactConfig(log_upload=True, store_fixed_image=False, output_path="/tmp/worker-output"),
        audit=AuditInfo(
            requested_by="example-script",
            ticket="DEMO-001",
            tags={"environment": "development", "priority": "normal"},
        ),
    )

    # Print as JSON
    job_json = job_spec.model_dump_json(indent=2)
    print("Job Specification (JSON):")
    print(job_json)

    # Save to file
    output_file = Path("/tmp/example-job.json")
    output_file.write_text(job_json)
    print(f"\n✅ Saved to: {output_file}")

    return job_spec


def execute_job_example(job_spec: JobSpec):
    """Execute a job with the worker engine."""
    print_banner("🚀 Job Execution")

    # Progress event callback
    def on_progress(event):
        print(f"[{event.phase}] {event.progress_percent}%: {event.message}")

    # Create worker engine
    engine = WorkerEngine(worker_id="example-worker-01", event_callback=on_progress)

    print(f"Worker ID: {engine.worker_id}")
    print(f"Job ID: {job_spec.job_id}")
    print(f"Operation: {job_spec.operation.value}\n")

    # Execute job
    try:
        result = engine.execute_job(job_spec)

        print_banner("📊 Execution Result")

        print(f"Status: {result.status.value}")
        print(f"Worker: {result.worker_id}")
        print(f"Execution Time: {result.metrics.execution_seconds}s")

        if result.status.value == "completed":
            print("\n✅ Job Completed Successfully!")
            if result.outputs:
                if result.outputs.fixed_image:
                    print(f"   Output Image: {result.outputs.fixed_image}")
                if result.outputs.report:
                    print(f"   Report: {result.outputs.report}")
                if result.outputs.logs:
                    print(f"   Logs: {result.outputs.logs}")
        else:
            print(f"\n❌ Job Failed!")
            if result.error:
                print(f"   Phase: {result.error.phase}")
                print(f"   Code: {result.error.code}")
                print(f"   Message: {result.error.message}")

        # Save result
        result_file = Path("/tmp/example-result.json")
        result_file.write_text(result.model_dump_json(indent=2))
        print(f"\n✅ Result saved to: {result_file}")

        return result

    except Exception as e:
        print(f"\n💥 Execution failed with exception: {e}")
        import traceback

        traceback.print_exc()
        return None


def demonstrate_worker_registration():
    """Demonstrate worker capability advertisement."""
    print_banner("📡 Worker Registration Example")

    detector = get_detector()
    sys_info = detector.get_system_info()
    capabilities = detector.detect_capabilities()

    worker_caps = WorkerCapabilities(
        worker_id="example-worker-01",
        hostname=sys_info.get("hostname"),
        capabilities=capabilities,
        max_disk_size_tb=10,
        max_concurrent_jobs=2,
        memory_gb=sys_info.get("memory_gb", 0),
        disk_space_gb=sys_info.get("disk_space_gb", 0),
        os_info={
            "distribution": sys_info.get("os", "unknown"),
            "version": sys_info.get("os_release", "unknown"),
        },
        kernel_version=sys_info.get("kernel_version", "unknown"),
    )

    # Print as JSON
    caps_json = worker_caps.model_dump_json(indent=2)
    print("Worker Capabilities (for registration):")
    print(caps_json)

    # Save to file
    caps_file = Path("/tmp/worker-capabilities.json")
    caps_file.write_text(caps_json)
    print(f"\n✅ Saved to: {caps_file}")

    return worker_caps


def main():
    """Run complete example workflow."""
    print_banner("🎯 hyper2kvm Worker Job Protocol - Example")

    print("This example demonstrates the Worker Job Protocol v1.")
    print("It will:")
    print("  1. Detect execution environment and capabilities")
    print("  2. Create a sample job specification")
    print("  3. Execute the job with progress tracking")
    print("  4. Display results")
    print("  5. Show worker registration format")

    # Step 1: Detect environment
    mode, capabilities, sys_info = detect_environment()

    # Step 2: Create job
    job_spec = create_job_example()

    # Step 3: Execute job (only if in appropriate mode)
    if mode == "host" or capabilities.get("qemu_img", False):
        result = execute_job_example(job_spec)
    else:
        print("\n⚠️  Skipping job execution (missing capabilities)")
        print("   This environment cannot execute disk operations.")
        print("   Try running on a host or in a privileged container.")

    # Step 4: Worker registration
    worker_caps = demonstrate_worker_registration()

    # Summary
    print_banner("✅ Example Complete")
    print("Generated files:")
    print("  - /tmp/example-job.json")
    print("  - /tmp/example-result.json")
    print("  - /tmp/worker-capabilities.json")
    print("\nFor more information, see:")
    print("  docs/worker-protocol-v1.md")


if __name__ == "__main__":
    main()
