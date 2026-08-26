# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/worker/cli.py
"""
Worker CLI Interface.

Provides command-line interface for worker job management:
- worker run <job.json>      - Execute job immediately
- worker submit <job.json>   - Submit job to queue
- worker status <job-id>     - Check job status
- worker events <job-id>     - Stream job events
- worker capabilities        - Show worker capabilities
- worker list                - List jobs
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import click

from .capabilities import CapabilityLevel, get_detector
from .engine import WorkerEngine
from .events import EventStream, get_event_store
from .schemas import JobSpec, JobState
from .state_machine import JobRegistry

logger = logging.getLogger(__name__)


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def worker_cli(verbose: bool):
    """hyper2kvm Worker Job Protocol CLI."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)


@worker_cli.command("run")
@click.argument("job_file", type=click.Path(exists=True))
@click.option("--worker-id", default="cli-worker", help="Worker identifier")
@click.option("--follow", is_flag=True, help="Follow progress in real-time")
def run_job(job_file: str, worker_id: str, follow: bool):
    """Execute a job immediately from job specification file."""
    print(f"Loading job specification from: {job_file}")

    try:
        with open(job_file) as f:
            job_data = json.load(f)

        job_spec = JobSpec(**job_data)
        print(f"  Loaded job: {job_spec.job_id}")
        print(f"  Operation: {job_spec.operation.value}")
        print(f"  Image: {job_spec.image.path}")

    except Exception as e:
        print(f"ERROR: Failed to load job specification: {e}", file=sys.stderr)
        sys.exit(1)

    def on_progress(event):
        timestamp = event.timestamp.strftime("%H:%M:%S")
        print(f"  {timestamp} {event.phase} {event.progress_percent}% - {event.message}")

    engine = WorkerEngine(worker_id=worker_id, event_callback=on_progress)
    result = engine.execute_job(job_spec)

    print()
    if result.status == JobState.COMPLETED:
        print("✓ Job completed successfully!")
        print(f"  Execution time: {result.metrics.execution_seconds}s")

        if result.outputs:
            if result.outputs.fixed_image:
                print(f"  Output image: {result.outputs.fixed_image}")
            if result.outputs.report:
                print(f"  Report: {result.outputs.report}")
            if result.outputs.logs:
                print(f"  Logs: {result.outputs.logs}")
    else:
        print("✗ Job failed!", file=sys.stderr)
        if result.error:
            print(f"  Phase: {result.error.phase}")
            print(f"  Error: {result.error.message}")

    result_file = Path(job_file).parent / f"{job_spec.job_id}_result.json"
    with open(result_file, "w") as f:
        f.write(result.model_dump_json(indent=2))
    print(f"\nResult saved to: {result_file}")


@worker_cli.command("status")
@click.argument("job_id")
def job_status(job_id: str):
    """Check status of a job."""
    registry = JobRegistry()
    sm = registry.get(job_id)

    if not sm:
        print(f"✗ Job not found: {job_id}", file=sys.stderr)
        sys.exit(1)

    print(f"Job Status: {job_id}")
    print(f"  {'Current State':<20} {sm.current_state.value}")
    print(f"  {'Is Terminal':<20} {'Yes' if sm.is_terminal() else 'No'}")

    event_store = get_event_store()
    latest_event = event_store.get_latest_event(job_id)

    if latest_event:
        print(f"  {'Latest Phase':<20} {latest_event.phase}")
        print(f"  {'Progress':<20} {latest_event.progress_percent}%")
        print(f"  {'Latest Message':<20} {latest_event.message}")
        print(f"  {'Last Update':<20} {latest_event.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")

    print("\nState History:")
    for entry in sm.state_history:
        timestamp = entry.get("timestamp", "unknown")
        if isinstance(timestamp, str):
            try:
                dt = datetime.fromisoformat(timestamp)
                timestamp = dt.strftime("%H:%M:%S")
            except (ValueError, TypeError):
                pass

        from_state = entry.get("from_state", "-")
        to_state = entry.get("to_state", entry.get("state", "-"))
        reason = entry.get("reason", "")

        if from_state != "-":
            print(f"  {timestamp} {from_state} -> {to_state} ({reason})")
        else:
            print(f"  {timestamp} {to_state} ({reason})")


@worker_cli.command("events")
@click.argument("job_id")
@click.option("--follow", "-f", is_flag=True, help="Follow events in real-time")
@click.option("--phase", help="Filter by phase")
def job_events(job_id: str, follow: bool, phase: str | None):
    """Stream progress events for a job."""
    event_store = get_event_store()

    print(f"Events for job: {job_id}")

    if follow:
        print("Following new events (Ctrl+C to stop)...\n")

    stream = EventStream(job_id=job_id, event_store=event_store, follow=follow)

    try:
        for event in stream:
            if phase and event.phase != phase:
                continue

            timestamp = event.timestamp.strftime("%H:%M:%S.%f")[:-3]
            print(f"  {timestamp} {event.phase:20} {event.progress_percent:3}% - {event.message}")

            if event.details:
                for key, value in event.details.items():
                    print(f"    {key}: {value}")

    except KeyboardInterrupt:
        print("\nStopped following events")
        stream.stop()


@worker_cli.command("capabilities")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--detailed", "-d", is_flag=True, help="Show detailed capability level report")
def show_capabilities(json_output: bool, detailed: bool):
    """Show worker capabilities."""
    detector = get_detector()

    mode = detector.detect_execution_mode()
    capabilities = detector.detect_capabilities()
    sys_info = detector.get_system_info()

    capability_level = detector.detect_capability_level()
    capability_report = detector.get_capability_level_report(capability_level)

    if json_output:
        output = {
            "execution_mode": mode,
            "capabilities": capabilities,
            "system_info": sys_info,
            "migration_capability_level": capability_report,
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        level_name = capability_report["level_name"]
        level_desc = capability_report["level_description"]

        if capability_level == CapabilityLevel.FULL_OFFLINE_FIXES:
            level_icon = "[OK]"
        elif capability_level == CapabilityLevel.NBD_INSPECTION:
            level_icon = "[WARN]"
        else:
            level_icon = "[ERR]"

        print("Migration Capability Level")
        print(f"  Detected Level:       {level_icon} {level_name}")
        print(f"  Description:          {level_desc}")
        print(f"  Available Operations: {len(capability_report['operations'])} operations")
        print()

        if detailed:
            print("Available Operations:")
            for op in capability_report["operations"]:
                print(f"  + {op}")
            print()

            if capability_report["limitations"]:
                print("Limitations:")
                for limitation in capability_report["limitations"]:
                    print(f"  ! {limitation}")
                print()

            if capability_report["recommendations"]:
                print("Recommendations:")
                for rec in capability_report["recommendations"]:
                    print(f"  * {rec}")
                print()

        print("Worker Capabilities:")
        print(f"  {'Execution Mode':<25} {mode}")
        for cap, available in capabilities.items():
            status = "Yes" if available else "No"
            print(f"  {cap:<25} {status}")

        print()
        print("System Information:")
        print(f"  {'Hostname':<15} {sys_info.get('hostname', 'unknown')}")
        print(f"  {'OS':<15} {sys_info.get('os', '')} {sys_info.get('os_release', '')}")
        print(f"  {'Kernel':<15} {sys_info.get('kernel_version', 'unknown')}")
        print(f"  {'Memory':<15} {sys_info.get('memory_gb', 0)} GB")
        print(f"  {'Disk Space':<15} {sys_info.get('disk_space_gb', 0)} GB")


@worker_cli.command("list")
@click.option("--state", type=click.Choice([s.value for s in JobState]), help="Filter by state")
def list_jobs(state: str | None):
    """List jobs."""
    registry = JobRegistry()
    state_filter = JobState(state) if state else None

    job_ids = registry.list_jobs(state_filter=state_filter)

    if not job_ids:
        print("No jobs found")
        return

    header = f"Jobs{' (filtered by state: ' + state + ')' if state else ''}"
    print(header)
    print(f"  {'Job ID':<40} {'State':<15} {'Progress':<10} {'Last Update':<12}")
    print(f"  {'-' * 40} {'-' * 15} {'-' * 10} {'-' * 12}")

    event_store = get_event_store()

    for job_id in sorted(job_ids):
        sm = registry.get(job_id)
        if not sm:
            continue

        latest_event = event_store.get_latest_event(job_id)

        progress = f"{latest_event.progress_percent}%" if latest_event else "-"
        last_update = latest_event.timestamp.strftime("%H:%M:%S") if latest_event else "-"

        print(f"  {job_id:<40} {sm.current_state.value:<15} {progress:<10} {last_update:<12}")


@worker_cli.command("submit")
@click.argument("job_file", type=click.Path(exists=True))
def submit_job(job_file: str):
    """Submit a job to the queue (placeholder - requires scheduler)."""
    print("⚠ Job queue not yet implemented")
    print("Use 'worker run' to execute jobs immediately")
    print("\nPlanned implementation:")
    print("  1. Load job specification")
    print("  2. Validate against worker capabilities")
    print("  3. Submit to queue (Redis/Kafka)")
    print("  4. Return job ID for tracking")


def main():
    """Entry point for worker CLI."""
    worker_cli()


if __name__ == "__main__":
    main()
