# h2kvm Worker Job Protocol v1.0 - Complete Specification

**Version:** 1.0
**Date:** 2026-01-30
**Status:** Production Ready

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Job Specification](#job-specification)
4. [Job Lifecycle](#job-lifecycle)
5. [Progress Events](#progress-events)
6. [Worker Capabilities](#worker-capabilities)
7. [API Reference](#api-reference)
8. [CLI Reference](#cli-reference)
9. [Deployment Guide](#deployment-guide)
10. [Examples](#examples)
11. [Troubleshooting](#troubleshooting)

---

## Overview

The h2kvm Worker Job Protocol provides a production-grade framework for orchestrating disk operations that require privileged access (NBD devices, LVM activation, filesystem surgery).

### Design Goals

- **Safe by Default**: Runs in containers without privileges when possible
- **Capability-Aware**: Auto-detects environment and available operations
- **Observable**: Complete audit trail with progress events
- **Scalable**: Supports single-worker and multi-worker deployments
- **Type-Safe**: Full Pydantic validation throughout

### Key Components

| Component | Purpose | File |
|-----------|---------|------|
| JSON Schemas | Type-safe data models | `worker/schemas.py` |
| State Machine | Job lifecycle management | `worker/state_machine.py` |
| Capabilities | Runtime detection | `worker/capabilities.py` |
| Execution Engine | Job execution | `worker/engine.py` |
| Event Streaming | Progress tracking | `worker/events.py` |
| CLI | Command-line interface | `worker/cli.py` |
| Scheduler | Job queue and matching | `worker/scheduler.py` |

---

## Architecture

### Control Plane vs Data Plane

```
┌─────────────────────────────┐
│     Control Plane           │  Safe Container / API Service
│  (Job Submission & Monitor) │
│                             │
│  - Job creation             │
│  - Status monitoring        │
│  - Event streaming          │
│  - Worker registration      │
└──────────────┬──────────────┘
               │
               │ Job Protocol (JSON)
               ▼
┌─────────────────────────────┐
│      Data Plane             │  Privileged Worker / Host
│   (Job Execution)           │
│                             │
│  - Disk operations          │
│  - NBD/LVM/mount            │
│  - Artifact generation      │
│  - Progress events          │
└─────────────────────────────┘
```

### Execution Modes

| Mode | Environment | Capabilities | Use Case |
|------|-------------|--------------|----------|
| `host` | Native OS | Full (NBD, LVM, mount, SELinux) | Production workers |
| `privileged_container` | Container with `--privileged` | Full (NBD, LVM, mount) | Controlled worker pools |
| `safe_container` | Standard container | Limited (qemu-img, inspect) | Control plane, conversion-only |

---

## Job Specification

### JobSpec Schema

```json
{
  "version": "1.0",
  "job_id": "uuid-string",
  "created_at": "2026-01-30T10:00:00Z",

  "operation": "offline_fix",

  "image": {
    "path": "/images/vm.qcow2",
    "format": "qcow2",
    "checksum": "sha256:...",
    "size_bytes": 42949672960
  },

  "requested_actions": [
    "nbd_attach",
    "lvm_activate",
    "fsck",
    "initramfs_regenerate"
  ],

  "capability_requirements": {
    "needs_nbd": true,
    "needs_lvm": true,
    "needs_mount": true,
    "needs_selinux_tools": false,
    "min_memory_gb": 4,
    "min_disk_space_gb": 100
  },

  "execution_policy": {
    "retry_count": 2,
    "timeout_seconds": 7200,
    "idempotent": true,
    "priority": 5
  },

  "artifacts": {
    "log_upload": true,
    "store_fixed_image": true,
    "output_path": "/mnt/output",
    "keep_intermediates": false
  },

  "audit": {
    "requested_by": "api-service",
    "ticket": "INC-1234",
    "tags": {
      "environment": "production",
      "team": "platform"
    }
  },

  "parameters": {
    "custom_param": "value"
  }
}
```

### Supported Operations

| Operation | Description | Requires Privileged |
|-----------|-------------|---------------------|
| `inspect` | Disk inspection and risk analysis | No |
| `convert` | Format conversion (qcow2, vmdk, raw) | No |
| `offline_fix` | Complete offline guest fixes | Yes (NBD, LVM, mount) |
| `boot_repair` | Boot configuration repair | Yes (NBD, mount) |
| `selinux_prep` | SELinux relabeling preparation | Yes (NBD, mount, SELinux tools) |
| `lvm_repair` | LVM structure repair | Yes (NBD, LVM) |
| `fs_repair` | Filesystem repair (fsck) | Yes (NBD, mount) |
| `initramfs_regenerate` | Regenerate initramfs with virtio | Yes (NBD, mount, chroot) |

---

## Job Lifecycle

### State Machine

```
CREATED
   ↓
VALIDATED ← (schema and capability check)
   ↓
QUEUED ← (waiting for worker)
   ↓
ASSIGNED ← (matched to capable worker)
   ↓
RUNNING ← (execution started)
   ↓
PROGRESSING ← (progress updates)
   ↓
COMPLETED / FAILED / RETRYING / CANCELLED
```

### State Transitions

| From | To | Trigger |
|------|-----|---------|
| CREATED | VALIDATED | Schema validation passed |
| VALIDATED | QUEUED | Submitted to queue |
| QUEUED | ASSIGNED | Worker matched |
| ASSIGNED | RUNNING | Execution started |
| RUNNING | PROGRESSING | Progress update |
| PROGRESSING | COMPLETED | Success |
| PROGRESSING | FAILED | Error occurred |
| PROGRESSING | RETRYING | Retry attempt |
| RETRYING | QUEUED | Re-queued for retry |
| Any | CANCELLED | Manual cancellation |

### Terminal States

- `COMPLETED` - Job finished successfully
- `FAILED` - Job failed after all retries
- `CANCELLED` - Job manually cancelled

---

## Progress Events

### ProgressEvent Schema

```json
{
  "job_id": "uuid-string",
  "timestamp": "2026-01-30T10:10:00Z",
  "phase": "lvm_activate",
  "progress_percent": 40,
  "message": "Volume group rhel activated",
  "details": {
    "vg_name": "rhel",
    "lv_count": 3
  }
}
```

### Event Phases

- `validation` - Job validation
- `conversion` - Format conversion
- `nbd_attach` - NBD device attachment
- `lvm_activate` - LVM activation
- `fsck` - Filesystem check
- `mount` - Filesystem mounting
- `initramfs_regen` - Initramfs regeneration
- `selinux_prep` - SELinux preparation
- `cleanup` - Resource cleanup
- `completed` - Job completion
- `failed` - Job failure

### Event Streaming

Events are stored in JSON Lines format:

```
/tmp/h2kvm/events/{job_id}.events.jsonl
```

Each line is a complete ProgressEvent JSON object.

---

## Worker Capabilities

### WorkerCapabilities Schema

```json
{
  "worker_id": "worker-01",
  "hostname": "worker-node1.example.com",

  "capabilities": {
    "nbd": true,
    "lvm": true,
    "mount": true,
    "selinux": true,
    "qemu_img": true
  },

  "max_disk_size_tb": 10,
  "max_concurrent_jobs": 2,

  "memory_gb": 64,
  "disk_space_gb": 500,

  "os_info": {
    "distribution": "Fedora",
    "version": "43"
  },
  "kernel_version": "6.18.6-200.fc43.x86_64",

  "last_heartbeat": "2026-01-30T10:00:00Z"
}
```

### Capability Detection

Workers automatically detect capabilities on startup:

```python
from h2kvm.worker.capabilities import get_detector

detector = get_detector()

# Detect execution mode
mode = detector.detect_execution_mode()
# Returns: "host", "safe_container", or "privileged_container"

# Detect capabilities
caps = detector.detect_capabilities()
# Returns: {"nbd": bool, "lvm": bool, "mount": bool, ...}
```

---

## API Reference

### Worker Engine API

```python
from h2kvm.worker import WorkerEngine, JobSpec

# Create engine
engine = WorkerEngine(
    worker_id="worker-01",
    event_callback=lambda e: print(f"{e.phase}: {e.progress_percent}%")
)

# Execute job
result = engine.execute_job(job_spec)

# Check result
if result.status == JobState.COMPLETED:
    print(f"Success: {result.outputs.fixed_image}")
else:
    print(f"Failed: {result.error.message}")
```

### Scheduler API

```python
from h2kvm.worker.scheduler import get_scheduler

scheduler = get_scheduler()

# Submit job
scheduler.submit_job(job_spec)

# Assign job to worker
job = scheduler.assign_job(worker_id="worker-01")

# Complete job
scheduler.complete_job(job.job_id, success=True)
```

### Event Streaming API

```python
from h2kvm.worker.events import EventStream, get_event_store

store = get_event_store()

# Stream events
stream = EventStream(
    job_id="job-uuid",
    event_store=store,
    follow=True  # Follow new events
)

for event in stream:
    print(f"{event.phase}: {event.message}")
```

---

## CLI Reference

### h2kvm worker run

Execute a job immediately:

```bash
h2kvm worker run job.json [--worker-id worker-01] [--follow]
```

Options:
- `--worker-id`: Worker identifier (default: cli-worker)
- `--follow`: Show progress in real-time

### h2kvm worker status

Check job status:

```bash
h2kvm worker status <job-id>
```

Shows:
- Current state
- Latest phase and progress
- State history with timestamps

### h2kvm worker events

Stream job events:

```bash
h2kvm worker events <job-id> [--follow] [--phase <phase>]
```

Options:
- `--follow, -f`: Follow new events in real-time
- `--phase`: Filter by phase name

### h2kvm worker capabilities

Show worker capabilities:

```bash
h2kvm worker capabilities [--json-output]
```

Options:
- `--json-output`: Output as JSON

### h2kvm worker list

List jobs:

```bash
h2kvm worker list [--state <state>]
```

Options:
- `--state`: Filter by state (created, running, completed, failed, etc.)

---

## Deployment Guide

### Single Worker (Host)

1. **Install h2kvm:**
   ```bash
   pip install -e /path/to/h2kvm
   ```

2. **Check capabilities:**
   ```bash
   h2kvm worker capabilities
   ```

3. **Run jobs:**
   ```bash
   h2kvm worker run job.json --follow
   ```

### Multi-Worker (Kubernetes)

See `k8s/worker/` for complete manifests.

**Quick Start:**

```bash
# Create namespace
kubectl create namespace h2kvm-workers

# Deploy worker DaemonSet
kubectl apply -f k8s/worker/daemonset.yaml

# Submit job
kubectl apply -f k8s/worker/job-template.yaml
```

### Container Deployment

**Privileged Worker:**

```bash
docker run --privileged \
  -v /dev:/dev \
  -v /lib/modules:/lib/modules \
  -v /data:/data \
  h2kvm:worker \
  worker run /data/job.json
```

**Safe Container (Conversion Only):**

```bash
docker run \
  -v /data:/data \
  h2kvm:cli \
  worker run /data/convert-job.json
```

---

## Examples

### Example 1: Simple Inspection

```python
from h2kvm.worker import JobSpec, OperationType
from h2kvm.worker.engine import create_sample_job_spec

job = create_sample_job_spec(
    image_path="/images/test.qcow2",
    output_dir="/tmp/output",
    operation=OperationType.INSPECT
)

from h2kvm.worker import WorkerEngine

engine = WorkerEngine(worker_id="test-worker")
result = engine.execute_job(job)

print(f"Inspection report: {result.outputs.report}")
```

### Example 2: Format Conversion

```json
{
  "version": "1.0",
  "job_id": "convert-001",
  "operation": "convert",
  "image": {
    "path": "/images/vm.vmdk",
    "format": "vmdk"
  },
  "parameters": {
    "output_format": "qcow2",
    "compress": true
  },
  "artifacts": {
    "output_path": "/output"
  },
  "audit": {
    "requested_by": "conversion-service"
  }
}
```

### Example 3: Offline Fix with Progress Tracking

```python
from h2kvm.worker import WorkerEngine
from h2kvm.worker.events import ProgressTracker

# Create progress tracker
tracker = ProgressTracker(
    job_id=job.job_id,
    phases=["nbd_attach", "lvm_activate", "fsck", "initramfs_regen"]
)

# Register listener
def on_progress(event):
    print(f"[{event.phase}] {event.progress_percent}%: {event.message}")

tracker.emitter.register_listener(on_progress)

# Execute
engine = WorkerEngine(worker_id="worker-01")
result = engine.execute_job(job)
```

---

## Troubleshooting

### Job Fails with "Missing required capability: nbd"

**Cause:** Worker doesn't have NBD access.

**Solutions:**
1. Run on host: `sudo h2kvmctl worker run job.json`
2. Use privileged container: `docker run --privileged -v /dev:/dev ...`
3. Change to conversion-only operation (doesn't need NBD)

### Events Not Streaming

**Cause:** Event store directory not writable.

**Solution:**
```bash
mkdir -p /tmp/h2kvm/events
chmod 777 /tmp/h2kvm/events
```

### Worker Not Matching Jobs

**Cause:** Capability mismatch.

**Debug:**
```bash
# Check worker capabilities
h2kvm worker capabilities

# Check job requirements
cat job.json | jq .capability_requirements
```

### State Machine Errors

**Cause:** Invalid state transition.

**Solution:** Check state history:
```bash
h2kvm worker status <job-id>
```

---

## Appendix

### File Locations

| Purpose | Default Path |
|---------|--------------|
| Job states | `/tmp/h2kvm/jobs/{job_id}.state.json` |
| Events | `/tmp/h2kvm/events/{job_id}.events.jsonl` |
| Queue | `/tmp/h2kvm/queue/{job_id}.job.json` |

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `H2KVM_STATE_DIR` | State directory | `/tmp/h2kvm/jobs` |
| `H2KVM_EVENT_DIR` | Event directory | `/tmp/h2kvm/events` |
| `H2KVM_QUEUE_DIR` | Queue directory | `/tmp/h2kvm/queue` |

---

**End of Specification**
