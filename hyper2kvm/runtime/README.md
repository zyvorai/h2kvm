# Runtime - Job Management and Execution Layer

This package contains the runtime components for executing migration jobs across different deployment models.

## Architecture

The runtime tier consists of three subsystems for different deployment scenarios:

### 1. **Daemon** (`daemon/`)
Background service for local/server deployments:

- **Manifest workflow processing**: Process YAML/JSON migration manifests
- **NBD preparation**: Prepare NBD devices for disk access
- **Job scheduling**: Queue and execute migration jobs
- **Progress tracking**: Monitor job progress and report status

**Key modules:**
- `manifest_workflow_daemon.py` - Manifest-based workflow orchestration
- `nbd_prep_daemon.py` - NBD device preparation service

**Use case:** Single-server or small-scale deployments

### 2. **Worker** (`worker/`)
Distributed worker processes for scalable deployments:

- **Job execution**: Execute migration tasks from work queue
- **Engine**: Core migration execution logic
- **Schemas**: Job specification and result schemas (Pydantic)
- **CLI**: Worker management commands

**Architecture:**
```
┌─────────┐      ┌─────────┐      ┌─────────┐
│ Worker  │      │ Worker  │      │ Worker  │
│ Node 1  │      │ Node 2  │      │ Node N  │
└────┬────┘      └────┬────┘      └────┬────┘
     │                │                │
     └────────────────┴────────────────┘
                      │
                ┌─────▼─────┐
                │   Queue   │
                │  (Redis)  │
                └───────────┘
```

**Key modules:**
- `engine.py` - Migration execution engine
- `schemas.py` - Job/task schemas (OperationType enum here)
- `cli.py` - Worker CLI commands

**Use case:** Large-scale, distributed migrations with work queue (Redis/RabbitMQ)

### 3. **Operator** (`operator/`)
Kubernetes operator for cloud-native deployments:

#### Controllers
- **migrationjob_controller.py**: Manages MigrationJob custom resources
- **offlinefixjob_controller.py**: Manages offline fix jobs
- **live_migration_controller.py**: Live migration orchestration
- **vm_lifecycle_controller.py**: VM lifecycle management
- **migration_policy_controller.py**: Migration policy enforcement
- **storage_migration_controller.py**: Storage migration controller

#### Support Components
- **webhook.py**: Admission webhook for validation/mutation
- **leader_election.py**: Leader election for HA
- **metrics.py**: Prometheus metrics
- **job_assigner.py**: Job-to-worker assignment
- **worker_registry.py**: Worker node registry

**Architecture:**
```
┌──────────────────────────────────────┐
│         Kubernetes Cluster           │
│                                      │
│  ┌────────────────┐                 │
│  │ Operator Pod   │                 │
│  │ - Controllers  │                 │
│  │ - Webhooks     │                 │
│  │ - Leader Elect │                 │
│  └───────┬────────┘                 │
│          │                          │
│  ┌───────▼────────┐                 │
│  │ MigrationJob   │ (CRD)          │
│  │ OfflineFixJob  │ (CRD)          │
│  └────────────────┘                 │
│                                      │
│  ┌─────────┐  ┌─────────┐          │
│  │ Worker  │  │ Worker  │          │
│  │  Pod 1  │  │  Pod N  │          │
│  └─────────┘  └─────────┘          │
└──────────────────────────────────────┘
```

**Use case:** Cloud-native, Kubernetes-based deployments with CRDs

## Deployment Models

### Model 1: Standalone Daemon

```bash
# Start manifest workflow daemon
hyper2kvm daemon --manifest /path/to/manifest.yaml

# Or NBD preparation daemon
hyper2kvm daemon --nbd-prep --device /dev/nbd0
```

**Pros:**
- Simple deployment
- No external dependencies
- Good for single-server use

**Cons:**
- No horizontal scaling
- Single point of failure

### Model 2: Worker Pool

```bash
# Start multiple workers
hyper2kvm worker start --queue redis://localhost:6379

# Submit jobs via API/CLI
hyper2kvm submit-job --disk /path/to/disk.qcow2
```

**Pros:**
- Horizontal scaling
- Fault tolerance (workers can fail)
- Work queue decoupling

**Cons:**
- Requires queue infrastructure (Redis/RabbitMQ)
- More complex deployment

### Model 3: Kubernetes Operator

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: migrate-vm-001
spec:
  sourceDisk: s3://bucket/disk.vmdk
  targetStorage: nfs-pvc
  offlineFix:
    enabled: true
    injectors:
      - hostname: webserver
```

```bash
# Deploy operator
kubectl apply -f k8s/operator/deployment.yaml

# Create migration job
kubectl apply -f migration-job.yaml

# Watch progress
kubectl get migrationjob migrate-vm-001 -w
```

**Pros:**
- Cloud-native deployment
- Kubernetes-native scaling/HA
- Declarative job specification
- Built-in monitoring (Prometheus)

**Cons:**
- Requires Kubernetes cluster
- More complex setup

## Common Patterns

### Pattern 1: Daemon with Manifest

```python
from hyper2kvm.runtime.daemon import ManifestWorkflowDaemon

daemon = ManifestWorkflowDaemon(
    manifest_path="/path/to/manifest.yaml",
    logger=logger
)

# Run daemon (blocks)
daemon.run()
```

### Pattern 2: Worker Job Execution

```python
from hyper2kvm.runtime.worker.engine import WorkerEngine
from hyper2kvm.runtime.worker.schemas import JobSpec, OperationType

# Create job
job = JobSpec(
    operation=OperationType.MIGRATE,
    source_disk="/path/to/source.vmdk",
    target_disk="/path/to/target.qcow2",
)

# Execute
engine = WorkerEngine(logger=logger)
result = engine.execute_job(job)
```

### Pattern 3: Kubernetes Operator

```python
# Operator runs via kopf framework
# See operator controllers for CRD handling

import kopf

@kopf.on.create('hyper2kvm.io', 'v1alpha1', 'migrationjobs')
def create_migration_job(spec, name, namespace, logger, **kwargs):
    # Create migration pod
    # Update status
    pass
```

## Job Schemas

### MigrationJob (Kubernetes CRD)
```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: example-migration
spec:
  # Source configuration
  source:
    type: vmware  # vmware, azure, backup
    disk: /path/to/disk.vmdk

  # Target configuration
  target:
    storage: nfs-pvc
    format: qcow2

  # Offline fixing
  offlineFix:
    enabled: true
    hostname: webserver
    network:
      - interface: eth0
        type: static
        address: 192.168.1.10/24
    users:
      - username: admin
        ssh_keys: [...]
    services:
      enable: [sshd]
      disable: [bluetooth]

status:
  phase: Running  # Pending, Running, Succeeded, Failed
  progress: 45
  message: "Applying offline fixes..."
```

### WorkerJob (Worker Queue)
```json
{
  "job_id": "uuid",
  "operation": "migrate",
  "source": {
    "type": "vmware",
    "disk": "/path/to/disk.vmdk"
  },
  "target": {
    "format": "qcow2",
    "path": "/output/disk.qcow2"
  },
  "fixes": {
    "offline": true,
    "injectors": {...}
  }
}
```

## Metrics and Monitoring

### Prometheus Metrics (Operator)

Available at `http://operator:8080/metrics`:

```
# Migration job metrics
hyper2kvm_migration_jobs_total
hyper2kvm_migration_jobs_running
hyper2kvm_migration_jobs_succeeded
hyper2kvm_migration_jobs_failed

# Performance metrics
hyper2kvm_migration_duration_seconds
hyper2kvm_disk_conversion_bytes_total

# Worker metrics
hyper2kvm_worker_nodes_total
hyper2kvm_worker_jobs_assigned
```

### Logging

All runtime components use structured logging:

```python
logger.info(
    "Migration started",
    extra={
        "job_id": job_id,
        "source": source_disk,
        "phase": "conversion"
    }
)
```

## Configuration

### Daemon Configuration

```yaml
# /etc/hyper2kvm/daemon.yaml
daemon:
  manifest_dir: /var/lib/hyper2kvm/manifests
  work_dir: /var/lib/hyper2kvm/work
  log_level: INFO

nbd:
  device_pool: [/dev/nbd0, /dev/nbd1, /dev/nbd2]
  timeout: 300
```

### Worker Configuration

```yaml
# /etc/hyper2kvm/worker.yaml
worker:
  queue_url: redis://localhost:6379
  concurrency: 4
  log_level: INFO

resources:
  cpu_limit: 8
  memory_limit: 16G
  disk_cache: /var/cache/hyper2kvm
```

### Operator Configuration

```yaml
# k8s/operator/config.yaml
operator:
  namespace: hyper2kvm-system
  workers_per_node: 2
  leader_election: true

monitoring:
  prometheus: true
  metrics_port: 8080
```

## Testing

### Daemon Tests
```bash
pytest tests/unit/test_daemon/
pytest tests/integration/test_daemon/
```

### Worker Tests
```bash
pytest tests/unit/test_worker/
pytest tests/integration/test_worker_queue.py
```

### Operator Tests
```bash
# Unit tests
pytest tests/unit/test_operator/

# Integration tests (requires k8s)
pytest tests/integration/test_operator_integration.py

# E2E tests
./tests/e2e/e2e_operator_test.sh
```

## Security

### Daemon
- Runs as non-root user
- Systemd hardening (PrivateTmp, NoNewPrivileges)
- Manifest validation before execution

### Worker
- Isolated execution (containers)
- Resource limits (cgroups)
- Job signature verification

### Operator
- RBAC for CRD access
- Webhook for admission control
- Pod security policies
- Network policies for isolation

## Troubleshooting

### Daemon Not Starting
```bash
# Check systemd status
systemctl status hyper2kvm-daemon

# Check logs
journalctl -u hyper2kvm-daemon -f

# Validate manifest
hyper2kvm validate-manifest /path/to/manifest.yaml
```

### Worker Not Processing Jobs
```bash
# Check worker logs
hyper2kvm worker logs

# Check queue connection
hyper2kvm worker status

# Verify job schema
hyper2kvm validate-job job.json
```

### Operator CRD Issues
```bash
# Check operator logs
kubectl logs -n hyper2kvm-system deployment/operator

# Check CRD status
kubectl get migrationjob -A

# Describe job
kubectl describe migrationjob <name>

# Check events
kubectl get events -n <namespace>
```

## Known Issues

1. **Leader election timeout**: Operator may take 30s to elect leader
   - Mitigation: Adjust `--lease-duration` flag

2. **Worker queue backpressure**: Large jobs can block queue
   - Mitigation: Use priority queues, job size limits

3. **Daemon resource exhaustion**: Multiple NBD devices
   - Mitigation: Limit concurrent jobs via config

## Future Improvements

- [ ] Add job priority support
- [ ] Implement job checkpointing/resume
- [ ] Add worker autoscaling (HPA for operator)
- [ ] Improve progress reporting granularity
- [ ] Add job dependency graph (DAG) support
- [ ] Implement job templates/presets
