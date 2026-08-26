# hyper2kvm Worker Job Protocol - REST API Documentation

**Version:** 1.0
**Status:** Production-Ready
**OpenAPI Spec:** Available at `/openapi.json`

---

## Overview

The hyper2kvm Worker REST API provides a production-grade HTTP interface for VM migration job orchestration. Built with FastAPI, it offers automatic OpenAPI/Swagger documentation, type-safe request validation, and real-time progress streaming via Server-Sent Events (SSE).

### Key Features

- **Type-Safe** - Full Pydantic validation with auto-generated docs
- **Real-Time Progress** - Server-Sent Events (SSE) for live updates
- **OpenAPI/Swagger** - Interactive API documentation at `/docs`
- **Prometheus Metrics** - Built-in monitoring support
- **CORS Enabled** - Browser-compatible for web dashboards
- **Async/Await** - High-performance async I/O throughout

---

## Quick Start

### Installation

```bash
# Install API dependencies
pip install -r requirements-api.txt

# Or install individual packages
pip install fastapi uvicorn sse-starlette
```

### Start Server

```bash
# Development mode (auto-reload)
uvicorn hyper2kvm.worker.api:app --reload --host 0.0.0.0 --port 8000

# Production mode (with Gunicorn)
gunicorn hyper2kvm.worker.api:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# Using Docker
docker run -p 8000:8000 ghcr.io/ssahani/hyper2kvm-worker-api:latest
```

### Access Documentation

- **Swagger UI:** http://localhost:8000/docs (interactive)
- **ReDoc:** http://localhost:8000/redoc (reference)
- **OpenAPI JSON:** http://localhost:8000/openapi.json (machine-readable)

---

## API Reference

### Base URL

```
http://localhost:8000
```

All endpoints return JSON except `/metrics` (Prometheus text format) and `/jobs/{id}/events/stream` (Server-Sent Events).

---

## Job Endpoints

### Submit Job

**POST** `/jobs`

Submit a new VM migration job.

**Query Parameters:**
- `queue` (boolean, optional) - If `true`, add to job queue for worker assignment

**Request Body:**
```json
{
  "job_id": "convert-vm-123",
  "operation": "convert",
  "image": {
    "path": "/data/vm.vmdk",
    "format": "vmdk"
  },
  "parameters": {
    "output_format": "qcow2",
    "compress": true
  },
  "execution_policy": {
    "timeout_seconds": 3600,
    "retry_count": 3,
    "priority": 75,
    "idempotent": true
  },
  "audit_info": {
    "requested_by": "admin@example.com",
    "ticket_id": "TICKET-456",
    "tags": ["production", "critical"]
  }
}
```

**Response (201 Created):**
```json
{
  "job_id": "convert-vm-123",
  "state": "QUEUED",
  "message": "Job queued successfully",
  "queue_position": 5
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d @job_spec.json
```

---

### Get Job Status

**GET** `/jobs/{job_id}`

Retrieve current job status and history.

**Response (200 OK):**
```json
{
  "job_id": "convert-vm-123",
  "spec": { /* JobSpec object */ },
  "state": "RUNNING",
  "state_history": [
    {
      "state": "CREATED",
      "timestamp": "2026-01-31T10:00:00Z",
      "reason": "Job submitted via REST API"
    },
    {
      "state": "VALIDATED",
      "timestamp": "2026-01-31T10:00:01Z",
      "reason": "Job spec validated successfully"
    },
    {
      "state": "QUEUED",
      "timestamp": "2026-01-31T10:00:02Z",
      "reason": "Added to queue with priority 75"
    },
    {
      "state": "ASSIGNED",
      "timestamp": "2026-01-31T10:01:00Z",
      "reason": "Assigned to worker worker-1"
    },
    {
      "state": "RUNNING",
      "timestamp": "2026-01-31T10:01:05Z",
      "reason": "Worker started execution"
    }
  ],
  "result": null,
  "latest_event": {
    "job_id": "convert-vm-123",
    "timestamp": "2026-01-31T10:02:30Z",
    "phase": "conversion",
    "percentage": 45,
    "message": "Converting disk format: 45% complete",
    "details": {}
  }
}
```

**cURL Example:**
```bash
curl http://localhost:8000/jobs/convert-vm-123
```

---

### List Jobs

**GET** `/jobs`

List all jobs with optional filtering.

**Query Parameters:**
- `state` (JobState, optional) - Filter by job state
- `limit` (integer, optional, default=100, max=1000) - Maximum jobs to return

**Response (200 OK):**
```json
{
  "total": 3,
  "jobs": [
    {
      "job_id": "convert-vm-123",
      "state": "RUNNING",
      "created_at": "2026-01-31T10:00:00Z",
      "is_terminal": false
    },
    {
      "job_id": "convert-vm-124",
      "state": "COMPLETED",
      "created_at": "2026-01-31T09:00:00Z",
      "is_terminal": true
    },
    {
      "job_id": "convert-vm-125",
      "state": "QUEUED",
      "created_at": "2026-01-31T10:05:00Z",
      "is_terminal": false
    }
  ]
}
```

**cURL Examples:**
```bash
# List all jobs
curl http://localhost:8000/jobs

# List only running jobs
curl "http://localhost:8000/jobs?state=RUNNING"

# List with limit
curl "http://localhost:8000/jobs?limit=10"
```

---

### Cancel Job

**DELETE** `/jobs/{job_id}`

Cancel a running or queued job.

**Response (200 OK):**
```json
{
  "job_id": "convert-vm-123",
  "state": "CANCELLED",
  "message": "Job cancelled successfully"
}
```

**Error Response (400 Bad Request):**
```json
{
  "error": {
    "code": 400,
    "message": "Job convert-vm-123 is already in terminal state COMPLETED",
    "path": "/jobs/convert-vm-123",
    "timestamp": "2026-01-31T10:15:00Z"
  }
}
```

**cURL Example:**
```bash
curl -X DELETE http://localhost:8000/jobs/convert-vm-123
```

---

### Get Job Events (Polling)

**GET** `/jobs/{job_id}/events`

Retrieve all progress events for a job (polling mode).

**Query Parameters:**
- `since` (ISO 8601 timestamp, optional) - Only return events after this time

**Response (200 OK):**
```json
[
  {
    "job_id": "convert-vm-123",
    "timestamp": "2026-01-31T10:01:05Z",
    "phase": "initialization",
    "percentage": 0,
    "message": "Starting job execution",
    "details": {}
  },
  {
    "job_id": "convert-vm-123",
    "timestamp": "2026-01-31T10:01:30Z",
    "phase": "conversion",
    "percentage": 25,
    "message": "Converting disk format: 25% complete",
    "details": {
      "bytes_processed": "536870912",
      "total_bytes": "2147483648"
    }
  },
  {
    "job_id": "convert-vm-123",
    "timestamp": "2026-01-31T10:02:30Z",
    "phase": "conversion",
    "percentage": 50,
    "message": "Converting disk format: 50% complete",
    "details": {
      "bytes_processed": "1073741824",
      "total_bytes": "2147483648"
    }
  }
]
```

**cURL Examples:**
```bash
# Get all events
curl http://localhost:8000/jobs/convert-vm-123/events

# Get events since timestamp
curl "http://localhost:8000/jobs/convert-vm-123/events?since=2026-01-31T10:02:00Z"
```

---

### Stream Job Events (Real-Time)

**GET** `/jobs/{job_id}/events/stream`

Stream job progress events in real-time using Server-Sent Events (SSE).

**Response:** Server-Sent Events (text/event-stream)

**Event Types:**
- `progress` - Progress update event
- `complete` - Job reached terminal state
- `error` - Error occurred

**Example SSE Stream:**
```
event: progress
data: {"job_id":"convert-vm-123","timestamp":"2026-01-31T10:01:05Z","phase":"initialization","percentage":0,"message":"Starting job execution","details":{}}

event: progress
data: {"job_id":"convert-vm-123","timestamp":"2026-01-31T10:01:30Z","phase":"conversion","percentage":25,"message":"Converting disk format: 25% complete","details":{"bytes_processed":"536870912"}}

event: progress
data: {"job_id":"convert-vm-123","timestamp":"2026-01-31T10:02:30Z","phase":"conversion","percentage":50,"message":"Converting disk format: 50% complete","details":{"bytes_processed":"1073741824"}}

event: complete
data: {"state":"COMPLETED"}
```

**cURL Example:**
```bash
# Stream events to terminal
curl -N http://localhost:8000/jobs/convert-vm-123/events/stream
```

**JavaScript EventSource Example:**
```javascript
const source = new EventSource('http://localhost:8000/jobs/convert-vm-123/events/stream');

source.addEventListener('progress', (event) => {
    const progress = JSON.parse(event.data);
    console.log(`Progress: ${progress.percentage}% - ${progress.message}`);
});

source.addEventListener('complete', (event) => {
    const result = JSON.parse(event.data);
    console.log(`Job completed with state: ${result.state}`);
    source.close();
});

source.addEventListener('error', (event) => {
    console.error('Stream error:', event);
    source.close();
});
```

**Python Example:**
```python
import httpx

async with httpx.AsyncClient() as client:
    async with client.stream('GET', 'http://localhost:8000/jobs/convert-vm-123/events/stream') as response:
        async for line in response.aiter_lines():
            if line.startswith('data: '):
                event_data = json.loads(line[6:])
                print(f"Progress: {event_data['percentage']}%")
```

---

## Worker Endpoints

### Register Worker

**POST** `/workers/register`

Register a new worker with its capabilities.

**Request Body:**
```json
{
  "worker_id": "worker-1",
  "capabilities": [
    "nbd_access",
    "lvm_tools",
    "mount_operations",
    "qemu_img"
  ],
  "system_info": {
    "hostname": "worker-node-1",
    "os": "Linux",
    "kernel": "6.1.0",
    "architecture": "x86_64",
    "memory_mb": 16384,
    "disk_space_mb": 512000
  },
  "execution_mode": "PRIVILEGED_CONTAINER"
}
```

**Response (201 Created):**
```json
{
  "worker_id": "worker-1",
  "message": "Worker registered successfully",
  "capabilities": [
    "nbd_access",
    "lvm_tools",
    "mount_operations",
    "qemu_img"
  ],
  "registered_at": "2026-01-31T09:00:00Z"
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:8000/workers/register \
  -H "Content-Type: application/json" \
  -d @worker_capabilities.json
```

---

### Worker Heartbeat

**POST** `/workers/{worker_id}/heartbeat`

Update worker heartbeat to indicate it's still alive.

**Response (200 OK):**
```json
{
  "worker_id": "worker-1",
  "message": "Heartbeat received",
  "timestamp": "2026-01-31T10:00:00Z"
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:8000/workers/worker-1/heartbeat
```

---

### List Workers

**GET** `/workers`

List all registered workers.

**Response (200 OK):**
```json
{
  "total": 3,
  "active": 2,
  "workers": [
    {
      "worker_id": "worker-1",
      "capabilities": ["nbd_access", "lvm_tools", "mount_operations", "qemu_img"],
      "system_info": {
        "hostname": "worker-node-1",
        "memory_mb": 16384,
        "disk_space_mb": 512000
      }
    },
    {
      "worker_id": "worker-2",
      "capabilities": ["qemu_img"],
      "system_info": {
        "hostname": "worker-node-2",
        "memory_mb": 8192,
        "disk_space_mb": 256000
      }
    }
  ]
}
```

**cURL Example:**
```bash
curl http://localhost:8000/workers
```

---

### Unregister Worker

**DELETE** `/workers/{worker_id}`

Unregister a worker.

**Response (200 OK):**
```json
{
  "worker_id": "worker-1",
  "message": "Worker unregistered successfully"
}
```

**cURL Example:**
```bash
curl -X DELETE http://localhost:8000/workers/worker-1
```

---

## Queue Endpoints

### Get Queue Status

**GET** `/queue`

Get job queue status and statistics.

**Response (200 OK):**
```json
{
  "total_jobs": 12,
  "by_priority": {
    "10": 1,
    "50": 4,
    "75": 5,
    "90": 2
  }
}
```

**cURL Example:**
```bash
curl http://localhost:8000/queue
```

---

### Dequeue Job (Worker Polling)

**POST** `/queue/dequeue`

Dequeue next job matching worker capabilities. Used by workers to poll for jobs.

**Request Body:**
```json
{
  "worker_id": "worker-1",
  "capabilities": ["nbd_access", "lvm_tools", "mount_operations", "qemu_img"],
  "execution_mode": "PRIVILEGED_CONTAINER"
}
```

**Response (200 OK):**
```json
{
  "job_id": "convert-vm-125",
  "operation": "convert",
  "image": {
    "path": "/data/vm.vmdk",
    "format": "vmdk"
  },
  "parameters": {
    "output_format": "qcow2"
  }
  /* ... full JobSpec ... */
}
```

**Response (200 OK - No Jobs):**
```json
null
```

**cURL Example:**
```bash
curl -X POST http://localhost:8000/queue/dequeue \
  -H "Content-Type: application/json" \
  -d @worker_capabilities.json
```

---

## Monitoring Endpoints

### Health Check

**GET** `/health`

Health check endpoint for load balancers and monitoring.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "version": "v1",
  "timestamp": "2026-01-31T10:00:00Z",
  "workers": 3,
  "active_jobs": 5
}
```

**cURL Example:**
```bash
curl http://localhost:8000/health
```

---

### Prometheus Metrics

**GET** `/metrics`

Prometheus metrics endpoint.

**Response (200 OK):**
```
# HELP hyper2kvm_migration_total Total number of migrations
# TYPE hyper2kvm_migration_total counter
hyper2kvm_migration_total{status="completed"} 125
hyper2kvm_migration_total{status="failed"} 3

# HELP hyper2kvm_migration_duration_seconds Migration duration
# TYPE hyper2kvm_migration_duration_seconds histogram
hyper2kvm_migration_duration_seconds_bucket{le="60.0"} 45
hyper2kvm_migration_duration_seconds_bucket{le="300.0"} 98
hyper2kvm_migration_duration_seconds_bucket{le="600.0"} 120
hyper2kvm_migration_duration_seconds_bucket{le="+Inf"} 128
hyper2kvm_migration_duration_seconds_sum 23456.78
hyper2kvm_migration_duration_seconds_count 128

# HELP hyper2kvm_worker_jobs_active Current number of active jobs
# TYPE hyper2kvm_worker_jobs_active gauge
hyper2kvm_worker_jobs_active 5
```

**Prometheus Configuration:**
```yaml
scrape_configs:
  - job_name: 'hyper2kvm'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: /metrics
    scrape_interval: 15s
```

**cURL Example:**
```bash
curl http://localhost:8000/metrics
```

---

## Error Responses

All error responses follow this format:

```json
{
  "error": {
    "code": 404,
    "message": "Job convert-vm-999 not found",
    "path": "/jobs/convert-vm-999",
    "timestamp": "2026-01-31T10:00:00Z"
  }
}
```

**HTTP Status Codes:**
- `200` - Success
- `201` - Created
- `400` - Bad Request (invalid input)
- `404` - Not Found
- `500` - Internal Server Error

---

## Deployment

### Development

```bash
# Install dependencies
pip install -r requirements-api.txt

# Run with auto-reload
uvicorn hyper2kvm.worker.api:app --reload --host 0.0.0.0 --port 8000
```

### Production

```bash
# Using Gunicorn with multiple workers
gunicorn hyper2kvm.worker.api:app \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --access-logfile - \
  --error-logfile - \
  --log-level info
```

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-api.txt

COPY hyper2kvm/ ./hyper2kvm/
EXPOSE 8000

CMD ["uvicorn", "hyper2kvm.worker.api:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hyper2kvm-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: hyper2kvm-api
  template:
    metadata:
      labels:
        app: hyper2kvm-api
    spec:
      containers:
      - name: api
        image: ghcr.io/ssahani/hyper2kvm-worker-api:latest
        ports:
        - containerPort: 8000
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: hyper2kvm-api
spec:
  selector:
    app: hyper2kvm-api
  ports:
  - port: 80
    targetPort: 8000
  type: LoadBalancer
```

---

## SDK Examples

### Python

```python
import httpx
import asyncio

async def submit_and_monitor():
    async with httpx.AsyncClient() as client:
        # Submit job
        response = await client.post(
            "http://localhost:8000/jobs",
            json={
                "job_id": "demo-123",
                "operation": "convert",
                "image": {"path": "/data/vm.vmdk", "format": "vmdk"},
                "parameters": {"output_format": "qcow2"}
            },
            params={"queue": True}
        )
        job_id = response.json()["job_id"]

        # Monitor progress (polling)
        while True:
            status = await client.get(f"http://localhost:8000/jobs/{job_id}")
            state = status.json()["state"]
            print(f"State: {state}")

            if state in ["COMPLETED", "FAILED", "CANCELLED"]:
                break

            await asyncio.sleep(2)

asyncio.run(submit_and_monitor())
```

### JavaScript

```javascript
// Submit job
const response = await fetch('http://localhost:8000/jobs?queue=true', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        job_id: 'demo-123',
        operation: 'convert',
        image: {path: '/data/vm.vmdk', format: 'vmdk'},
        parameters: {output_format: 'qcow2'}
    })
});

const {job_id} = await response.json();

// Monitor via SSE
const source = new EventSource(`http://localhost:8000/jobs/${job_id}/events/stream`);

source.addEventListener('progress', (event) => {
    const data = JSON.parse(event.data);
    console.log(`${data.percentage}%: ${data.message}`);
});

source.addEventListener('complete', (event) => {
    console.log('Job complete!');
    source.close();
});
```

### cURL

```bash
# Submit and capture job ID
JOB_ID=$(curl -s -X POST http://localhost:8000/jobs?queue=true \
  -H "Content-Type: application/json" \
  -d '{"job_id":"demo-123","operation":"convert","image":{"path":"/data/vm.vmdk","format":"vmdk"},"parameters":{"output_format":"qcow2"}}' \
  | jq -r '.job_id')

echo "Job ID: $JOB_ID"

# Monitor progress
while true; do
  STATE=$(curl -s http://localhost:8000/jobs/$JOB_ID | jq -r '.state')
  echo "State: $STATE"
  [[ "$STATE" == "COMPLETED" || "$STATE" == "FAILED" ]] && break
  sleep 2
done
```

---

## Authentication & Security

### Recommendations

1. **API Key Authentication**
   ```python
   from fastapi import Security, HTTPException
   from fastapi.security import APIKeyHeader

   api_key_header = APIKeyHeader(name="X-API-Key")

   async def verify_api_key(api_key: str = Security(api_key_header)):
       if api_key != "your-secret-key":
           raise HTTPException(status_code=403, detail="Invalid API key")

   # Apply to endpoints
   @app.post("/jobs", dependencies=[Depends(verify_api_key)])
   ```

2. **HTTPS/TLS**
   - Use reverse proxy (nginx, Traefik) for TLS termination
   - Configure cert-manager in Kubernetes

3. **Rate Limiting**
   ```python
   from slowapi import Limiter
   from slowapi.util import get_remote_address

   limiter = Limiter(key_func=get_remote_address)
   app.state.limiter = limiter

   @app.post("/jobs")
   @limiter.limit("10/minute")
   async def submit_job(...):
       ...
   ```

4. **CORS Configuration**
   ```python
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["https://yourdomain.com"],  # Specific domains
       allow_credentials=True,
       allow_methods=["GET", "POST", "DELETE"],
       allow_headers=["*"],
   )
   ```

---

## Troubleshooting

### API Won't Start

```bash
# Check if port is in use
lsof -i :8000

# Use different port
uvicorn hyper2kvm.worker.api:app --port 8001
```

### Jobs Not Appearing

```bash
# Check job registry
curl http://localhost:8000/jobs

# Check logs
uvicorn hyper2kvm.worker.api:app --log-level debug
```

### Workers Not Registering

```bash
# List workers
curl http://localhost:8000/workers

# Check worker heartbeats (stale after 300s)
```

### SSE Stream Not Working

```bash
# Test with curl
curl -N -H "Accept: text/event-stream" http://localhost:8000/jobs/demo-123/events/stream

# Check browser CORS settings
```

---

## Performance Tuning

### Worker Count

```bash
# Calculate optimal workers: (2 × CPU cores) + 1
NUM_WORKERS=$((2 * $(nproc) + 1))

gunicorn hyper2kvm.worker.api:app -w $NUM_WORKERS -k uvicorn.workers.UvicornWorker
```

### Database/State Storage

For production, replace in-memory registries with:
- **Redis** - Job queue, worker registry
- **PostgreSQL** - Job state, audit history
- **S3/MinIO** - Event storage, artifacts

### Caching

```python
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend

@app.on_event("startup")
async def startup():
    redis = aioredis.from_url("redis://localhost")
    FastAPICache.init(RedisBackend(redis), prefix="api-cache")

@app.get("/workers")
@cache(expire=60)  # Cache for 60 seconds
async def list_workers():
    ...
```

---

## See Also

- [Worker Protocol Specification](PROTOCOL_SPEC.md)
- [Quick Start Guide](QUICKSTART.md)
- [Kubernetes Deployment](../../k8s/README.md)
- [CLI Reference](../../hyper2kvm/worker/cli.py)

---

**Last Updated:** 2026-03-29
**Maintainer:** hyper2kvm team
