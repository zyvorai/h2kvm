# Worker Protocol & Job Management

The Hyper2KVM Worker Job Protocol provides a REST API and job management system for running VM migration tasks in Kubernetes and OpenShift environments.

## Quick Links

### 🚀 Getting Started
- **[Quickstart Guide](QUICKSTART.md)** ⭐ **START HERE** - Get up and running in 5 minutes
- **[Protocol Specification](PROTOCOL_SPEC.md)** - Complete technical specification
- **[REST API Documentation](REST_API.md)** - HTTP API reference
- **[Complete Index](INDEX.md)** - Comprehensive documentation index

### 📊 Status & Overview
- **[Worker Protocol Status](WORKER_PROTOCOL_STATUS.md)** - Current implementation status
- **[Worker Protocol Summary](../deployment/WORKER_PROTOCOL_SUMMARY.md)** - Architecture and features

## What is the Worker Protocol?

The Worker Job Protocol is a production-ready system for:

- **Job Submission**: Submit VM migration jobs via REST API or Kubernetes CRDs
- **State Management**: Track job progress through queued → running → completed states
- **Event Streaming**: Real-time progress updates via Server-Sent Events (SSE)
- **Capability System**: Workers advertise capabilities (inspect, convert, offline-fix, etc.)
- **Kubernetes Native**: Full integration with Kubernetes operators and CRDs

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   REST API Server                    │
│              (Port 8000, /api/v1/jobs)              │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│              Job Queue (SQLite/Redis)                │
│         (Priority, Dependencies, Retry Logic)        │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│                  Worker Pool                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ Worker 1 │  │ Worker 2 │  │ Worker N │          │
│  │ (inspect)│  │ (convert)│  │ (offline)│          │
│  └──────────┘  └──────────┘  └──────────┘          │
└─────────────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│          Storage (PVC/PV or Local Disks)            │
│    /data/input  /data/output  /data/working         │
└─────────────────────────────────────────────────────┘
```

## Key Features

### ✅ Production-Ready
- **REST API** - Submit and monitor jobs via HTTP
- **CLI Tool** - `h2kvmctl` command-line interface
- **Kubernetes CRDs** - Native `MigrationJob` custom resources
- **State Machine** - Robust job lifecycle management
- **Event Streaming** - Real-time progress via SSE
- **Retry Logic** - Automatic retries with exponential backoff
- **Priority Queue** - High-priority jobs execute first
- **DAG Dependencies** - Jobs can depend on other jobs
- **Capabilities** - Worker specialization and auto-selection

### 📊 Monitoring & Operations
- **Prometheus Metrics** - Full observability
- **Grafana Dashboards** - Pre-built visualization
- **Health Checks** - Liveness and readiness probes
- **Structured Logging** - JSON logs with correlation IDs
- **Alert Rules** - PrometheusRule for critical events

### 🔧 Deployment Options
- **Kubernetes** - DaemonSet or Deployment
- **OpenShift** - Full SCCRoutes, OAuth integration
- **Helm Charts** - One-command installation
- **OLM Bundle** - OperatorHub integration
- **Docker/Podman** - Container deployment

## Quick Start

### Option 1: Kubernetes with Helm

```bash
# Install worker
helm install hyper2kvm-worker ./helm/hyper2kvm-worker \
  --namespace hyper2kvm-system \
  --create-namespace

# Submit a job
cat <<EOF | kubectl apply -f -
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: convert-vm
spec:
  operation: convert
  image:
    path: /data/input/vm.vmdk
    format: vmdk
  artifacts:
    output_path: /data/output
    output_format: qcow2
    compress: true
EOF

# Check status
kubectl get migrationjobs
kubectl logs -l app=hyper2kvm-worker -f
```

### Option 2: REST API

```bash
# Submit job
curl -X POST http://worker:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "convert",
    "image": {
      "path": "/data/input/vm.vmdk",
      "format": "vmdk"
    },
    "artifacts": {
      "output_path": "/data/output",
      "output_format": "qcow2"
    }
  }'

# Check status
curl http://worker:8000/api/v1/jobs/{job_id}

# Stream events
curl -N http://worker:8000/api/v1/jobs/{job_id}/events
```

### Option 3: CLI Tool

```bash
# Submit job
h2kvmctl submit migration.yaml

# Check status
h2kvmctl status job-123

# Query jobs
h2kvmctl query --status running

# Cancel job
h2kvmctl cancel job-123
```

**See**: [Quickstart Guide](QUICKSTART.md)

## Job Types

### Inspect
Analyze VMDK files without modification:
```yaml
operation: inspect
image:
  path: /data/input/vm.vmdk
  format: vmdk
```

### Convert
Convert disk formats:
```yaml
operation: convert
image:
  path: /data/input/vm.vmdk
  format: vmdk
artifacts:
  output_path: /data/output
  output_format: qcow2
  compress: true
```

### Offline Fix
Apply boot fixes to converted images:
```yaml
operation: offline-fix
image:
  path: /data/output/vm.qcow2
  format: qcow2
fixes:
  fstab_mode: stabilize-all
  regen_initramfs: true
  # grub is auto-handled
```

**See**: [Protocol Specification](PROTOCOL_SPEC.md) for complete schema

## Documentation Structure

```
docs/worker/
├── README.md (this file)       # Overview and quick links
├── INDEX.md                    # Comprehensive documentation index
├── QUICKSTART.md               # 5-minute getting started
├── PROTOCOL_SPEC.md            # Complete technical specification
├── REST_API.md                 # HTTP API reference
└── WORKER_PROTOCOL_STATUS.md   # Implementation status
```

## Related Documentation

### Deployment
- [Worker Protocol Summary](../deployment/WORKER_PROTOCOL_SUMMARY.md)
- [Kubernetes Integration](../deployment/KUBERNETES_INTEGRATION.md)
- [OpenShift Deployment](../deployment/openshift-deployment-guide.md)
- [Container Deployment](../deployment/container-deployment-guide.md)

### Features
- [Phase 4 Deployment](../deployment/phase4-deployment.md) - OfflineFixJob CRD
- [Phase 6 REST API](../deployment/PHASE6_REST_API_COMPLETE.md) - API details
- [Production Enhancements](../deployment/production-enhancements.md) - v1.1.0 features

### Guides
- [h2kvmctl Guide](../guides/cli/h2kvmctl-guide.md) - CLI tool documentation
- [Batch Migration](../guides/migration/batch-features.md) - Batch processing

## Versions & Releases

| Version | Status | Features | Documentation |
|---------|--------|----------|---------------|
| **v2.1.0** | ✅ Current | OpenShift support, SCCs, Routes | [Release](../deployment/releases/RELEASE_COMPLETE_v2.1.0.md) |
| **v2.0.0** | ✅ Stable | Full operator features | [v2.0.0](../deployment/v2.0.0-comprehensive-features.md) |
| **v1.9.0** | ✅ Stable | Advanced job scheduling | [v1.9.0](../deployment/v1.9.0-advanced-job-scheduling.md) |
| **v1.8.0** | ✅ Stable | Operator HA | [v1.8.0](../deployment/v1.8.0-operator-ha.md) |
| **v1.6.0** | ✅ Stable | Helm charts | [v1.6.0](../deployment/v1.6.0-helm-chart.md) |
| **v1.4.0** | ✅ Stable | Kubernetes operator | [v1.4.0](../deployment/v1.4.0-operator.md) |

## API Endpoints

### Job Management
```
POST   /api/v1/jobs              # Submit job
GET    /api/v1/jobs              # List jobs
GET    /api/v1/jobs/{id}         # Get job status
DELETE /api/v1/jobs/{id}         # Cancel job
GET    /api/v1/jobs/{id}/events  # Stream events (SSE)
```

### Worker Management
```
GET    /api/v1/workers           # List workers
GET    /api/v1/capabilities      # Get capabilities
```

### Health & Metrics
```
GET    /health                   # Health check
GET    /metrics                  # Prometheus metrics
```

**See**: [REST API Documentation](REST_API.md)

## Examples

### Example Job Files
- [Inspect Job](../../k8s/operator/examples/inspect-job.yaml)
- [Convert Job](../../k8s/operator/examples/convert-job.yaml)
- [Offline Fix Job](../../k8s/operator/examples/offline-fix-job.yaml)
- [Batch Jobs](../../examples/batch/)

### Example Helm Values
- See [Helm Chart README](../../helm/hyper2kvm-worker/README.md)

## Monitoring

### Prometheus Metrics
```
# Job metrics
hyper2kvm_jobs_total{status="completed|failed|cancelled"}
hyper2kvm_job_duration_seconds{operation="inspect|convert|offline-fix"}
hyper2kvm_queue_size{priority="high|normal|low"}

# Worker metrics
hyper2kvm_worker_pool_size
hyper2kvm_worker_utilization_percent
hyper2kvm_worker_active_jobs

# System metrics
hyper2kvm_api_requests_total{endpoint="/api/v1/jobs",method="POST"}
hyper2kvm_api_request_duration_seconds
```

### Grafana Dashboard
Pre-built dashboard with 9 panels:
- Job throughput
- Success/failure rates
- Queue depth
- Worker utilization
- API latency
- Error rates

**See**: [v1.2.0 Enhancements](../deployment/v1.2.0-enhancements.md)

## Testing

### Unit Tests
```bash
pytest tests/test_worker_protocol.py
pytest tests/test_rest_api.py
```

### Integration Tests
```bash
# Deploy to k3d
k3d cluster create hyper2kvm-test
helm install hyper2kvm-worker ./helm/hyper2kvm-worker

# Run tests
./scripts/test-worker-integration.sh
```

**See**: [Testing Guide](../development/testing-guide.md)

## Support

- **Issues**: [GitHub Issues](https://github.com/ssahani/hyper2kvm/issues)
- **Discussions**: [GitHub Discussions](https://github.com/ssahani/hyper2kvm/discussions)
- **Documentation**: [Main Index](../index.md)

## Contributing

See [Contributing Guide](../development/contributing.md) for development setup and contribution guidelines.

---

**Last Updated**: March 2026
**Protocol Version**: v1
**Status**: ✅ Production Ready
