#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Example: Using the hyper2kvm Worker Job Protocol REST API.

This demonstrates:
1. Starting the API server
2. Submitting jobs via HTTP
3. Monitoring progress via SSE
4. Worker registration
5. Job queue management

Requirements:
    pip install -r requirements-api.txt

Usage:
    # Terminal 1: Start API server
    python examples/api_example.py server

    # Terminal 2: Submit a job
    python examples/api_example.py submit

    # Terminal 3: Monitor progress
    python examples/api_example.py monitor <job-id>
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import httpx

API_BASE_URL = "http://localhost:8000"


# ============================================================================
# Server Mode - Start API Server
# ============================================================================


def start_server():
    """Start the FastAPI server."""
    import uvicorn

    print("🚀 Starting hyper2kvm Worker API server...")
    print(f"📖 API Documentation: {API_BASE_URL}/docs")
    print(f"📖 ReDoc: {API_BASE_URL}/redoc")
    print()

    uvicorn.run(
        "hyper2kvm.worker.api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )


# ============================================================================
# Client Mode - Submit Job
# ============================================================================


async def submit_job(job_file: Optional[str] = None):
    """Submit a job to the API."""
    # Create example job spec if no file provided
    if job_file:
        with open(job_file) as f:
            job_spec = json.load(f)
    else:
        job_spec = {
            "job_id": f"demo-job-{asyncio.get_event_loop().time():.0f}",
            "operation": "convert",
            "image": {
                "path": "/tmp/example.vmdk",
                "format": "vmdk",
            },
            "parameters": {
                "output_format": "qcow2",
                "compress": True,
            },
            "execution_policy": {
                "timeout_seconds": 3600,
                "retry_count": 3,
                "priority": 75,
                "idempotent": True,
            },
            "audit_info": {
                "requested_by": "api_example",
                "tags": ["demo", "example"],
            },
        }

    print("📤 Submitting job...")
    print(f"Job ID: {job_spec['job_id']}")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{API_BASE_URL}/jobs",
                json=job_spec,
                params={"queue": True},
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.json()

            print(f"\n✓ Job submitted successfully!")
            print(f"Job ID: {result['job_id']}")
            print(f"State: {result['state']}")
            print(f"Queue Position: {result.get('queue_position', 'N/A')}")

            return result["job_id"]

        except httpx.HTTPError as e:
            print(f"✗ Error submitting job: {e}")
            return None


# ============================================================================
# Client Mode - Monitor Progress
# ============================================================================


async def monitor_job(job_id: str):
    """Monitor job progress using SSE streaming."""
    print(f"📡 Monitoring job: {job_id}")
    print("Press Ctrl+C to stop\n")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_BASE_URL}/jobs/{job_id}")
            if response.status_code == 404:
                print(f"✗ Job {job_id} not found")
                return

            status = response.json()
            print(f"Current State: {status['state']}")
            print()

            last_timestamp = None

            while True:
                params = {}
                if last_timestamp:
                    params["since"] = last_timestamp

                response = await client.get(
                    f"{API_BASE_URL}/jobs/{job_id}/events",
                    params=params,
                )

                events = response.json()

                if events:
                    for event in events:
                        timestamp = event.get("timestamp", "")
                        phase = event.get("phase", "unknown")
                        percentage = event.get("percentage", 0)
                        message = event.get("message", "")

                        print(f"  {timestamp[:19]} {phase:12} {percentage:3d}% {message}")

                        last_timestamp = timestamp

                response = await client.get(f"{API_BASE_URL}/jobs/{job_id}")
                status = response.json()
                state = status["state"]

                if state in ["COMPLETED", "FAILED", "CANCELLED"]:
                    print(f"\nJob finished with state: {state}")
                    break

                await asyncio.sleep(2)

        except KeyboardInterrupt:
            print("\n⏹ Monitoring stopped")
        except httpx.HTTPError as e:
            print(f"✗ Error monitoring job: {e}")


# ============================================================================
# Client Mode - Register Worker
# ============================================================================


async def register_worker():
    """Register a worker with the API."""
    print("📝 Registering worker...")

    from hyper2kvm.runtime.worker.capabilities import CapabilityDetector

    detector = CapabilityDetector()
    capabilities = detector.detect()

    caps_dict = capabilities.model_dump()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{API_BASE_URL}/workers/register",
                json=caps_dict,
                timeout=10.0,
            )
            response.raise_for_status()
            result = response.json()

            print(f"\n✓ Worker registered successfully!")
            print(f"Worker ID: {result['worker_id']}")
            print(f"Capabilities: {', '.join(result['capabilities'])}")

            return result["worker_id"]

        except httpx.HTTPError as e:
            print(f"✗ Error registering worker: {e}")
            return None


# ============================================================================
# Client Mode - List Jobs
# ============================================================================


async def list_jobs():
    """List all jobs."""
    print("📋 Listing jobs...")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_BASE_URL}/jobs")
            response.raise_for_status()
            result = response.json()

            if result["total"] == 0:
                print("No jobs found")
                return

            print(f"\nJobs ({result['total']} total)")
            print(f"  {'Job ID':<40} {'State':<15} {'Created At':<20}")
            print(f"  {'-' * 40} {'-' * 15} {'-' * 20}")

            for job in result["jobs"]:
                created = job.get("created_at", "N/A")[:19] if job.get("created_at") else "N/A"
                print(f"  {job['job_id']:<40} {job['state']:<15} {created:<20}")

        except httpx.HTTPError as e:
            print(f"✗ Error listing jobs: {e}")


# ============================================================================
# Client Mode - Health Check
# ============================================================================


async def health_check():
    """Check API health."""
    print("🏥 Checking API health...")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_BASE_URL}/health", timeout=5.0)
            response.raise_for_status()
            health = response.json()

            print(f"\n✓ API is healthy")
            print(f"Version: {health['version']}")
            print(f"Workers: {health['workers']}")
            print(f"Active Jobs: {health['active_jobs']}")

        except httpx.ConnectError:
            print("✗ API server is not running")
            print(f"Start the server with: python {__file__} server")
        except httpx.HTTPError as e:
            print(f"✗ Error checking health: {e}")


# ============================================================================
# Main CLI
# ============================================================================


async def async_main():
    """Main async entry point."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python api_example.py server              - Start API server")
        print("  python api_example.py health              - Check API health")
        print("  python api_example.py submit [job.json]   - Submit a job")
        print("  python api_example.py monitor <job-id>    - Monitor job progress")
        print("  python api_example.py register            - Register worker")
        print("  python api_example.py list                - List all jobs")
        sys.exit(1)

    command = sys.argv[1]

    if command == "server":
        start_server()
    elif command == "health":
        await health_check()
    elif command == "submit":
        job_file = sys.argv[2] if len(sys.argv) > 2 else None
        job_id = await submit_job(job_file)
        if job_id:
            print(f"\nMonitor with: python {__file__} monitor {job_id}")
    elif command == "monitor":
        if len(sys.argv) < 3:
            print("✗ Please provide job ID")
            sys.exit(1)
        await monitor_job(sys.argv[2])
    elif command == "register":
        worker_id = await register_worker()
        if worker_id:
            print("\n✓ Worker registered successfully")
    elif command == "list":
        await list_jobs()
    else:
        print(f"✗ Unknown command: {command}")
        sys.exit(1)


def main():
    """Main entry point."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
