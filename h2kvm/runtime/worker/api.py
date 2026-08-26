# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
REST API for h2kvm Worker Job Protocol v1.

This module provides a production-grade REST API for job submission,
worker registration, progress monitoring, and queue management.

Architecture:
    - FastAPI framework with async support
    - Pydantic schema validation (auto OpenAPI/Swagger docs)
    - Server-Sent Events (SSE) for real-time progress
    - Prometheus metrics integration
    - Graceful shutdown handling

Usage:
    # Development
    uvicorn h2kvm.worker.api:app --reload --host 0.0.0.0 --port 8000

    # Production
    gunicorn h2kvm.worker.api:app -w 4 -k uvicorn.workers.UvicornWorker

    # Docker
    docker run -p 8000:8000 h2kvm/worker-api:latest

API Documentation:
    - Swagger UI: http://localhost:8000/docs
    - ReDoc: http://localhost:8000/redoc
    - OpenAPI JSON: http://localhost:8000/openapi.json
"""

import asyncio
import hmac
import logging
import os
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from .events import EventStore, EventStream
from .metrics import WorkerMetrics
from .scheduler import JobQueue, WorkerRegistry
from .schemas import (
    JobResult,
    JobSpec,
    JobState,
    ProgressEvent,
    WorkerCapabilities,
)
from .state_machine import JobRegistry, JobStateMachine

# ============================================================================
# Configuration
# ============================================================================

logger = logging.getLogger(__name__)

# ============================================================================
# Token-based Authentication
# ============================================================================

_TOKEN_FILE = Path("/var/run/secrets/h2kvm/token")
_bearer_scheme = HTTPBearer(auto_error=False)


def _load_api_token() -> str | None:
    """
    Load API token from environment or file.

    Resolution order:
        1. H2KVM_API_TOKEN environment variable
        2. /var/run/secrets/h2kvm/token file
        3. None (auth disabled — backward compatible)
    """
    token = os.environ.get("H2KVM_API_TOKEN")
    if token:
        return token.strip()

    try:
        if _TOKEN_FILE.exists():
            token = _TOKEN_FILE.read_text().strip()
            if token:
                return token
    except Exception as e:
        logger.warning(f"Failed to read token file {_TOKEN_FILE}: {e}")

    return None


# Resolved once at import time; reloaded on lifespan startup
_api_token: str | None = _load_api_token()


def reload_api_token() -> None:
    """Reload the API token (e.g., after secret rotation)."""
    global _api_token
    _api_token = _load_api_token()
    if _api_token:
        logger.info("API token loaded — authentication enabled")
    else:
        logger.info("No API token configured — authentication disabled (open access)")


async def require_auth(
    # FastAPI's dependency-injection mechanism requires Depends(...) to be the
    # literal parameter default so it can be introspected at route registration.
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),  # noqa: B008
) -> None:
    """
    FastAPI dependency that enforces Bearer token authentication.

    If no token is configured (env var or file), authentication is disabled
    for backward compatibility. When a token IS configured, every request
    (except /healthz and /readyz) must present ``Authorization: Bearer <token>``.

    Raises:
        HTTPException 401: Missing or invalid token
    """
    if _api_token is None:
        # No token configured — auth disabled
        return

    if credentials is None or not hmac.compare_digest(credentials.credentials, _api_token):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )


API_VERSION = "v1"
API_TITLE = "h2kvm Worker Job Protocol API"
API_DESCRIPTION = """
Production REST API for VM migration job orchestration.

## Features

- **Job Submission** - Submit conversion/migration jobs via JSON
- **Worker Management** - Register workers with capability advertisement
- **Real-time Progress** - Server-Sent Events (SSE) for live progress
- **Queue Management** - Priority-based job scheduling
- **Metrics** - Prometheus metrics for monitoring
- **Type Safety** - Full Pydantic validation with OpenAPI docs

## Job Lifecycle

```
CREATED → VALIDATED → QUEUED → ASSIGNED → RUNNING → PROGRESSING → COMPLETED/FAILED
```

## Capability Levels

- **Level 1 (USERSPACE_ONLY)** - Basic conversion (qcow2, vmdk)
- **Level 2 (NBD_INSPECTION)** - Partition inspection via NBD
- **Level 3 (FULL_OFFLINE_FIXES)** - Complete guest OS modifications
"""

# Global registries (production would use external state store like Redis)
job_registry = JobRegistry()
worker_registry = WorkerRegistry()
job_queue = JobQueue()
event_store = EventStore()


# ============================================================================
# Application Lifecycle
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager.

    Startup:
        - Initialize registries
        - Load persisted state
        - Start background cleanup tasks

    Shutdown:
        - Persist in-flight jobs
        - Close connections gracefully
    """
    logger.info("Starting h2kvm Worker API...")

    # Startup: Reload API token (pick up runtime secret changes)
    reload_api_token()

    # Startup: Load persisted state
    try:
        job_registry.load_all()
        job_queue.load()
        logger.info("Loaded persisted job state")
    except Exception as e:
        logger.warning(f"Could not load persisted state: {e}")

    # Startup: Launch background cleanup task
    cleanup_task = asyncio.create_task(cleanup_stale_workers())

    yield

    # Shutdown: Save state
    logger.info("Shutting down h2kvm Worker API...")
    cleanup_task.cancel()
    with suppress(asyncio.CancelledError):
        await cleanup_task

    job_queue.save()
    logger.info("Saved job queue state")


async def cleanup_stale_workers():
    """Background task to remove stale workers."""
    while True:
        try:
            await asyncio.sleep(60)  # Check every minute
            stale = worker_registry.cleanup_stale()
            if stale:
                logger.info(f"Removed {len(stale)} stale workers: {stale}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception(f"Error in cleanup task: {e}")


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS middleware for browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Response Models
# ============================================================================


class JobSubmitResponse(BaseModel):
    """Response when submitting a new job."""

    job_id: str = Field(..., description="Unique job identifier")
    state: JobState = Field(..., description="Initial job state")
    message: str = Field(..., description="Human-readable message")
    queue_position: Optional[int] = Field(None, description="Position in queue (if queued)")


class JobStatusResponse(BaseModel):
    """Response for job status query."""

    job_id: str
    spec: JobSpec
    state: JobState
    state_history: list[dict[str, Any]] = Field(..., description="State transitions with timestamps")
    result: Optional[JobResult] = Field(None, description="Final result if completed")
    latest_event: Optional[ProgressEvent] = Field(None, description="Most recent progress event")


class JobListResponse(BaseModel):
    """Response for listing jobs."""

    total: int = Field(..., description="Total number of jobs")
    jobs: list[dict[str, Any]] = Field(..., description="Job summaries")


class WorkerListResponse(BaseModel):
    """Response for listing workers."""

    total: int = Field(..., description="Total number of registered workers")
    active: int = Field(..., description="Number of active workers")
    workers: list[dict[str, Any]] = Field(..., description="Worker details")


class QueueStatusResponse(BaseModel):
    """Response for queue status."""

    total_jobs: int = Field(..., description="Total jobs in queue")
    by_priority: dict[int, int] = Field(..., description="Jobs per priority level")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Service health status")
    version: str = Field(..., description="API version")
    timestamp: str = Field(..., description="Current server time (ISO 8601)")
    workers: int = Field(..., description="Registered workers")
    active_jobs: int = Field(..., description="Jobs in progress")


# ============================================================================
# Job Endpoints
# ============================================================================


@app.post("/jobs", response_model=JobSubmitResponse, status_code=201, dependencies=[Depends(require_auth)])
async def submit_job(
    job_spec: JobSpec,
    background_tasks: BackgroundTasks,
    queue: bool = Query(False, description="Queue job for worker assignment"),
) -> JobSubmitResponse:
    """
    Submit a new migration job.

    Args:
        job_spec: Complete job specification (validated via Pydantic)
        queue: If True, add to queue for worker assignment; if False, requires manual execution

    Returns:
        Job ID, initial state, and queue position (if queued)

    Example:
        ```bash
        curl -X POST http://localhost:8000/jobs \\
          -H "Content-Type: application/json" \\
          -d @job_spec.json
        ```
    """
    try:
        # Create state machine
        sm = JobStateMachine(job_spec.job_id)
        sm.transition(JobState.CREATED, "Job submitted via REST API")

        # Validate job spec
        sm.transition(JobState.VALIDATED, "Job spec validated successfully")

        # Register job in registry (state machine is created internally)
        job_registry.jobs[job_spec.job_id] = sm
        sm.save(job_registry.state_dir)

        # Optionally queue for worker assignment
        queue_position = None
        if queue:
            job_queue.enqueue(job_spec)
            sm.transition(
                JobState.QUEUED, f"Added to queue with priority {job_spec.execution_policy.priority}"
            )
            queue_position = job_queue.size()
            logger.info(f"Job {job_spec.job_id} queued at position {queue_position}")

        return JobSubmitResponse(
            job_id=job_spec.job_id,
            state=sm.current_state,
            message=f"Job {'queued' if queue else 'submitted'} successfully",
            queue_position=queue_position,
        )

    except Exception as e:
        logger.error(f"Error submitting job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to submit job") from e


@app.get("/jobs/{job_id}", response_model=JobStatusResponse, dependencies=[Depends(require_auth)])
async def get_job_status(job_id: str) -> JobStatusResponse:
    """
    Get current job status and history.

    Args:
        job_id: Job identifier

    Returns:
        Complete job status including state history and latest progress

    Example:
        ```bash
        curl http://localhost:8000/jobs/job-123
        ```
    """
    sm = job_registry.get(job_id)
    if not sm:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    # Get job spec (would be stored separately in production)
    # For now, create minimal spec
    from .schemas import ExecutionPolicy, ImageSpec

    job_spec = JobSpec(
        job_id=job_id,
        operation=sm.job_id.split("-")[0] if "-" in sm.job_id else "convert",
        image=ImageSpec(path="/tmp/placeholder", format="qcow2"),
        execution_policy=ExecutionPolicy(),
    )

    # Get latest event if available
    latest_event = None
    with suppress(Exception):
        latest_event = event_store.get_latest_event(job_id)

    # Get result if terminal state
    result = None
    if sm.is_terminal():
        # Result would be loaded from storage in production
        pass

    return JobStatusResponse(
        job_id=job_id,
        spec=job_spec,
        state=sm.current_state,
        state_history=[
            {
                "state": h.get("to_state", h.get("state", "")),
                "timestamp": h.get("timestamp", ""),
                "reason": h.get("reason", ""),
            }
            for h in sm.state_history
        ],
        result=result,
        latest_event=latest_event,
    )


@app.get("/jobs", response_model=JobListResponse, dependencies=[Depends(require_auth)])
async def list_jobs(
    # FastAPI's dependency-injection mechanism requires Query(...) to be the
    # literal parameter default so it can be introspected at route registration.
    state: Optional[JobState] = Query(None, description="Filter by state"),  # noqa: B008
    limit: int = Query(100, ge=1, le=1000, description="Maximum jobs to return"),
) -> JobListResponse:
    """
    List all jobs with optional filtering.

    Args:
        state: Filter by job state (optional)
        limit: Maximum number of jobs to return (1-1000)

    Returns:
        List of jobs with summary information
    """
    all_jobs = job_registry.list_jobs()

    # Filter by state if requested
    if state:
        all_jobs = [job_id for job_id in all_jobs if job_registry.get(job_id).current_state == state]

    # Apply limit
    all_jobs = all_jobs[:limit]

    # Build summary for each job
    jobs = []
    for job_id in all_jobs:
        sm = job_registry.get(job_id)
        jobs.append(
            {
                "job_id": job_id,
                "state": sm.current_state.value,
                "created_at": sm.state_history[0].get("timestamp") if sm.state_history else None,
                "is_terminal": sm.is_terminal(),
            }
        )

    return JobListResponse(total=len(jobs), jobs=jobs)


@app.delete("/jobs/{job_id}", status_code=200, dependencies=[Depends(require_auth)])
async def cancel_job(job_id: str) -> dict[str, Any]:
    """
    Cancel a running or queued job.

    Args:
        job_id: Job identifier

    Returns:
        Cancellation confirmation

    Example:
        ```bash
        curl -X DELETE http://localhost:8000/jobs/job-123
        ```
    """
    sm = job_registry.get(job_id)
    if not sm:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if sm.is_terminal():
        raise HTTPException(
            status_code=400,
            detail=f"Job {job_id} is already in terminal state {sm.current_state.value}",
        )

    try:
        sm.transition(JobState.CANCELLED, "Cancelled via REST API")
        logger.info(f"Job {job_id} cancelled")
        return {"job_id": job_id, "state": JobState.CANCELLED.value, "message": "Job cancelled successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to cancel job") from e


@app.get("/jobs/{job_id}/events", dependencies=[Depends(require_auth)])
async def get_job_events(
    job_id: str,
    since: Optional[str] = Query(None, description="ISO 8601 timestamp - only events after this time"),
) -> list[ProgressEvent]:
    """
    Get all progress events for a job (polling mode).

    Args:
        job_id: Job identifier
        since: Only return events after this timestamp (ISO 8601 format)

    Returns:
        List of progress events

    Example:
        ```bash
        # Get all events
        curl http://localhost:8000/jobs/job-123/events

        # Get recent events
        curl "http://localhost:8000/jobs/job-123/events?since=2026-01-31T12:00:00Z"
        ```
    """
    sm = job_registry.get(job_id)
    if not sm:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    try:
        # Parse since timestamp if provided
        since_dt = None
        if since:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))

        # Get events from store
        return event_store.get_events(job_id, since=since_dt)

    except Exception as e:
        logger.exception(f"Error retrieving events for {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve job events") from e


@app.get("/jobs/{job_id}/events/stream", dependencies=[Depends(require_auth)])
async def stream_job_events(job_id: str, request: Request):
    """
    Stream job progress events in real-time using Server-Sent Events (SSE).

    Args:
        job_id: Job identifier

    Returns:
        SSE stream of progress events

    Example:
        ```bash
        # Using curl
        curl -N http://localhost:8000/jobs/job-123/events/stream

        # Using EventSource in JavaScript
        const source = new EventSource('http://localhost:8000/jobs/job-123/events/stream');
        source.onmessage = (event) => {
            const progress = JSON.parse(event.data);
            console.log(progress);
        };
        ```
    """
    sm = job_registry.get(job_id)
    if not sm:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    async def event_generator():
        """Generate SSE events from EventStream."""
        stream = EventStream(event_store, job_id)

        try:
            for event in stream:
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.info(f"Client disconnected from event stream for {job_id}")
                    break

                # Yield SSE formatted event
                yield {
                    "event": "progress",
                    "data": event.model_dump_json(),
                }

                # Small delay to avoid hammering
                await asyncio.sleep(0.1)

                # Stop if job is in terminal state
                current_sm = job_registry.get(job_id)
                if current_sm and current_sm.is_terminal():
                    yield {
                        "event": "complete",
                        "data": '{"state": "' + current_sm.current_state.value + '"}',
                    }
                    break

        except Exception as e:
            logger.exception(f"Error in event stream for {job_id}: {e}")
            yield {
                "event": "error",
                "data": f'{{"error": "{e!s}"}}',
            }

    return EventSourceResponse(event_generator())


# ============================================================================
# Worker Endpoints
# ============================================================================


@app.post("/workers/register", status_code=201, dependencies=[Depends(require_auth)])
async def register_worker(capabilities: WorkerCapabilities) -> dict[str, Any]:
    """
    Register a new worker with its capabilities.

    Args:
        capabilities: Worker capability advertisement

    Returns:
        Worker ID and registration confirmation

    Example:
        ```bash
        curl -X POST http://localhost:8000/workers/register \\
          -H "Content-Type: application/json" \\
          -d @worker_capabilities.json
        ```
    """
    try:
        worker_registry.register(capabilities)
        logger.info(
            f"Registered worker {capabilities.worker_id} with capabilities: {capabilities.capabilities}"
        )

        return {
            "worker_id": capabilities.worker_id,
            "message": "Worker registered successfully",
            "capabilities": capabilities.capabilities,
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.exception(f"Error registering worker: {e}")
        raise HTTPException(status_code=500, detail="Failed to register worker") from e


@app.post("/workers/{worker_id}/heartbeat", status_code=200, dependencies=[Depends(require_auth)])
async def worker_heartbeat(worker_id: str) -> dict[str, Any]:
    """
    Update worker heartbeat to indicate it's still alive.

    Args:
        worker_id: Worker identifier

    Returns:
        Heartbeat acknowledgment

    Example:
        ```bash
        curl -X POST http://localhost:8000/workers/worker-1/heartbeat
        ```
    """
    if not worker_registry.heartbeat(worker_id):
        raise HTTPException(status_code=404, detail=f"Worker {worker_id} not found")

    return {
        "worker_id": worker_id,
        "message": "Heartbeat received",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/workers", response_model=WorkerListResponse, dependencies=[Depends(require_auth)])
async def list_workers() -> WorkerListResponse:
    """
    List all registered workers.

    Returns:
        List of workers with their capabilities and status
    """
    workers = worker_registry.list_workers()

    worker_details = []
    for worker_id in workers:
        caps = worker_registry.get_capabilities(worker_id)
        if caps:
            worker_details.append(
                {
                    "worker_id": worker_id,
                    "capabilities": caps.capabilities,
                    "system_info": caps.system_info.model_dump() if caps.system_info else None,
                }
            )

    active = len([w for w in workers if worker_registry.heartbeat(w)])

    return WorkerListResponse(
        total=len(workers),
        active=active,
        workers=worker_details,
    )


@app.delete("/workers/{worker_id}", status_code=200, dependencies=[Depends(require_auth)])
async def unregister_worker(worker_id: str) -> dict[str, Any]:
    """
    Unregister a worker.

    Args:
        worker_id: Worker identifier

    Returns:
        Unregistration confirmation
    """
    worker_registry.unregister(worker_id)
    logger.info(f"Unregistered worker {worker_id}")

    return {
        "worker_id": worker_id,
        "message": "Worker unregistered successfully",
    }


# ============================================================================
# Queue Endpoints
# ============================================================================


@app.get("/queue", response_model=QueueStatusResponse, dependencies=[Depends(require_auth)])
async def get_queue_status() -> QueueStatusResponse:
    """
    Get job queue status and statistics.

    Returns:
        Queue statistics including jobs per priority level
    """
    stats = job_queue.get_stats()

    return QueueStatusResponse(
        total_jobs=stats["total_jobs"],
        by_priority=stats["by_priority"],
    )


@app.post("/queue/dequeue", dependencies=[Depends(require_auth)])
async def dequeue_job(capabilities: WorkerCapabilities) -> Optional[JobSpec]:
    """
    Dequeue next job matching worker capabilities (for worker polling).

    Args:
        capabilities: Worker capabilities for job matching

    Returns:
        Next matching job spec, or None if no jobs available

    Example:
        ```bash
        curl -X POST http://localhost:8000/queue/dequeue \\
          -H "Content-Type: application/json" \\
          -d @worker_capabilities.json
        ```
    """
    try:
        job_spec = job_queue.dequeue(capabilities.capabilities)

        if job_spec:
            # Transition to ASSIGNED state
            sm = job_registry.get(job_spec.job_id)
            if sm:
                sm.transition(JobState.ASSIGNED, f"Assigned to worker {capabilities.worker_id}")

            logger.info(f"Dequeued job {job_spec.job_id} for worker {capabilities.worker_id}")

        return job_spec

    except Exception as e:
        logger.exception(f"Error dequeuing job: {e}")
        raise HTTPException(status_code=500, detail="Failed to dequeue job") from e


# ============================================================================
# Health & Metrics Endpoints
# ============================================================================


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """
    Kubernetes-style liveness probe (unauthenticated).

    Returns:
        Simple status object indicating the service is alive
    """
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    """
    Kubernetes-style readiness probe (unauthenticated).

    Returns:
        Simple status object indicating the service is ready to accept traffic
    """
    return {"status": "ok"}


@app.get("/health", response_model=HealthResponse, dependencies=[Depends(require_auth)])
async def health_check() -> HealthResponse:
    """
    Health check endpoint for load balancers and monitoring.

    Returns:
        Service health status and basic statistics
    """
    all_jobs = job_registry.list_jobs()
    active_jobs = len([j for j in all_jobs if not job_registry.get(j).is_terminal()])

    return HealthResponse(
        status="healthy",
        version=API_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
        workers=len(worker_registry.list_workers()),
        active_jobs=active_jobs,
    )


@app.get("/metrics", dependencies=[Depends(require_auth)])
async def metrics():
    """
    Prometheus metrics endpoint.

    Returns:
        Metrics in Prometheus text format

    Example:
        ```bash
        curl http://localhost:8000/metrics
        ```
    """
    # Would integrate with WorkerMetrics.get_registry()
    # For now, return basic metrics
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    try:
        metrics = WorkerMetrics()
        registry = metrics.get_registry()
        return JSONResponse(
            content=generate_latest(registry).decode("utf-8"),
            media_type=CONTENT_TYPE_LATEST,
        )
    except Exception as e:
        logger.exception(f"Error generating metrics: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


# ============================================================================
# Error Handlers
# ============================================================================


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Custom HTTP exception handler with structured error response."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.status_code,
                "message": exc.detail,
                "path": request.url.path,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catch-all exception handler for unhandled errors."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": 500,
                "message": "Internal server error",
                "path": request.url.path,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        },
    )


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "h2kvm.worker.api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
