# Deployment & Operations

This directory contains guides for deploying H2KVM in various environments, from standalone installations to enterprise Kubernetes/OpenShift deployments.

## Performance Highlights

**Enterprise LVM Improvements** (v2.2.0+)
- ✅ **7x Faster LVM Activation** - 0.71s (enterprise-grade performance)
- ✅ **100% Host Protection** - Device-filtered activation prevents host VG corruption
- ✅ **Production Validated** - RHEL 8.8 and openSUSE Leap 15.4 tested
- 📖 **[Technical Details](../LVM_AND_ENTERPRISE_IMPROVEMENTS.md)** - Architecture and implementation
- 📊 **[Test Results](../test-results/LVM_ENTERPRISE_IMPROVEMENTS_TEST_RESULTS.md)** - Comprehensive validation

## Quick Links

### 🚀 Getting Started
- **[Production Deployment Guide](PRODUCTION_DEPLOYMENT_GUIDE.md)** - Comprehensive production deployment
- **[Deployment Quickref](DEPLOYMENT_QUICKREF.md)** - Quick reference card
- **[Deployment Status](DEPLOYMENT_STATUS.md)** - Current deployment capabilities

### 🌐 Web Dashboard (h2kweb)
- **Install**: `cd web && sudo make install` → https://localhost:5070
- **9 pages**: Dashboard, Providers, Migrate, Jobs, VMs, KubeVirt, Networks, Settings, Login
- **55+ API endpoints** with PAM authentication and audit logging
- **VM Management** — start/stop/reboot/delete, snapshots, autostart
- **Embedded VNC Console** — browser-based VNC for libvirt + KubeVirt (react-vnc)
- **KubeVirt** — VM/VMI list, start/stop/restart/pause/migrate/delete, VNC, IP display
- **Migration wizard** — 4 sources (local/vSphere/Azure/EC2), batch, all YAML options
- **Live logs** — real-time h2kvmctl output via WebSocket, progress tracking
- **Auto-deploy** — libvirt (virsh define+start) + KubeVirt (CDI upload+VM)
- **Dashboard** — CPU/RAM/disk/load, all partitions, K3s/K8s/KubeVirt, pipeline, health
- **Settings** — storage relocate, user management (sudo operators), dark/light theme
- **Toast notifications** — WebSocket alerts for job events
- **Remote deploy**: `./scripts/deploy-remote.sh` auto-installs h2kweb
- **PDF**: [Dashboard UX](../client-presentations/61-web-dashboard-ux.pdf) • [Live Demo](../client-presentations/62-live-migration-demo.pdf) • [Screenshots](../client-presentations/63-web-dashboard-screenshots.pdf)

### ☁️ Kubernetes & OpenShift
- **[Kubernetes on CentOS 8 - Quick Start](KUBERNETES_CENTOS8_QUICKSTART.md)** ⭐ - Deploy on CentOS 8 in 10 minutes
- **[Kubernetes on CentOS 8 - Full Guide](kubernetes-centos8-guide.md)** ⭐ - Complete CentOS 8 deployment guide
- **[OpenShift Deployment Guide](openshift-deployment-guide.md)** - Complete OpenShift Container Platform guide
- **[OpenShift Quickstart](openshift/OPENSHIFT_QUICKSTART.md)** - Get started on OpenShift in 5 minutes
- **[OpenShift Features Summary](OPENSHIFT_FEATURES_SUMMARY.md)** - OpenShift-specific features
- **[Kubernetes Integration](KUBERNETES_INTEGRATION.md)** - Native Kubernetes deployment
- **[KubeVirt Integration](KUBEVIRT_INTEGRATION.md)** - KubeVirt virtual machine support

### 🐳 Container Deployments
- **[Container Deployment Guide](container-deployment-guide.md)** - Docker/Podman deployment
- **[K3d Test Report](k3d-test-report.md)** - K3d lightweight Kubernetes testing

### 🔄 Worker Protocol & API
- **[Phase 4 Deployment](phase4-deployment.md)** - OfflineFixJob CRD and orchestration
- **[Phase 6 REST API](PHASE6_REST_API_COMPLETE.md)** - Complete REST API documentation
- **[Worker Protocol Summary](WORKER_PROTOCOL_SUMMARY.md)** - Worker protocol overview
- **[Production Enhancements](production-enhancements.md)** - Production-grade features

### 📦 Version History

#### Release Notes
- **[v2.1.0 Release Checklist](releases/RELEASE_CHECKLIST_v2.1.0.md)**
- **[v2.1.0 Release Complete](releases/RELEASE_COMPLETE_v2.1.0.md)**
- **[v1.3.0 Release Notes](releases/RELEASE_NOTES_v1.3.0.md)**

#### Version Enhancements
- **[v1.2.0 - Enhancements](v1.2.0-enhancements.md)** - Initial production features
- **[v1.3.0 - CI/CD & Ops](v1.3.0-cicd-ops.md)** - CI/CD integration
- **[v1.4.0 - Kubernetes Operator](v1.4.0-operator.md)** - Operator framework
- **[v1.5.0 - Webhooks & Metrics](v1.5.0-webhooks-metrics.md)** - Admission webhooks, Prometheus metrics
- **[v1.6.0 - Helm Chart](v1.6.0-helm-chart.md)** - Official Helm charts
- **[v1.7.0 - Helm Repository](v1.7.0-helm-repository.md)** - Helm repository hosting
- **[v1.8.0 - Operator HA](v1.8.0-operator-ha.md)** - High availability features
- **[v1.9.0 - Advanced Job Scheduling](v1.9.0-advanced-job-scheduling.md)** - DAG dependencies, priorities
- **[v2.0.0 - Comprehensive Features](v2.0.0-comprehensive-features.md)** - Complete feature set

## Deployment Methods

### Method 1: Helm Chart (Recommended for Kubernetes/OpenShift)

```bash
# Install on OpenShift
helm install h2kvm-operator ./helm/h2kvm-operator \
  --namespace h2kvm-system \
  --create-namespace \
  --set openshift.enabled=true

# Install on Kubernetes
helm install h2kvm-operator ./helm/h2kvm-operator \
  --namespace h2kvm-system \
  --create-namespace \
  --set openshift.enabled=false
```

**Documentation**: [v1.6.0 Helm Chart](v1.6.0-helm-chart.md)

### Method 2: OLM Bundle (OperatorHub)

```bash
# Install via operator-sdk
operator-sdk run bundle ghcr.io/ssahani/h2kvm-operator-bundle:v2.1.0 \
  --namespace h2kvm-system

# Or install from OperatorHub UI
```

**Documentation**: [v1.4.0 Operator](v1.4.0-operator.md)

### Method 3: Container Deployment

```bash
# Run operator container
podman run -d --name h2kvm-operator \
  ghcr.io/ssahani/h2kvm:2.1.0-operator

# Run worker container
podman run -d --name h2kvm-worker \
  -v /data:/data \
  ghcr.io/ssahani/h2kvm:2.1.0-worker
```

**Documentation**: [Container Deployment Guide](container-deployment-guide.md)

### Method 4: Standalone Installation

```bash
# Install via pip
pip install "h2kvm[full]"

# Run migration
h2kvm --config migration.yaml
```

**Documentation**: [Installation Guide](../getting-started/01-Installation.md)

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                OpenShift/Kubernetes                  │
│  ┌─────────────────┐         ┌──────────────────┐   │
│  │  H2KVM      │────────▶│  Custom          │   │
│  │  Operator       │         │  Resources       │   │
│  │  (Kopf)         │◀────────│  (CRDs)          │   │
│  └─────────────────┘         └──────────────────┘   │
│         │                             │              │
│         │                             │              │
│         ▼                             ▼              │
│  ┌─────────────────┐         ┌──────────────────┐   │
│  │  Worker Pods    │────────▶│  Storage         │   │
│  │  (Migration)    │         │  (PVC/PV)        │   │
│  └─────────────────┘         └──────────────────┘   │
│         │                                            │
│         │                                            │
│         ▼                                            │
│  ┌─────────────────────────────────────────────┐    │
│  │         Prometheus/Grafana Metrics          │    │
│  └─────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

## Key Features by Deployment Method

| Feature | Standalone | Container | Helm | OLM |
|---------|-----------|-----------|------|-----|
| **VM Migration** | ✅ | ✅ | ✅ | ✅ |
| **Batch Processing** | ✅ | ✅ | ✅ | ✅ |
| **Worker Protocol** | ❌ | ✅ | ✅ | ✅ |
| **Kubernetes CRDs** | ❌ | ❌ | ✅ | ✅ |
| **Admission Webhooks** | ❌ | ❌ | ✅ | ✅ |
| **Prometheus Metrics** | ❌ | ✅ | ✅ | ✅ |
| **High Availability** | ❌ | ❌ | ✅ | ✅ |
| **Auto-scaling** | ❌ | ❌ | ✅ | ✅ |
| **OpenShift Routes** | ❌ | ❌ | ✅ | ✅ |
| **OLM Lifecycle** | ❌ | ❌ | ❌ | ✅ |

## Platform Support

- ✅ **OpenShift Container Platform** 4.10-4.16
- ✅ **Kubernetes** 1.24-1.33
- ✅ **K3s/K3d** - Lightweight Kubernetes
- ✅ **MicroShift** - Edge computing
- ✅ **Docker/Podman** - Container runtime
- ✅ **KubeVirt** - Kubernetes virtualization

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/ssahani/h2kvm/issues)
- **Documentation**: [Main Index](../index.md)
- **Troubleshooting**: [Troubleshooting Guide](../guides/troubleshooting.md)

## What's Next?

### 🎯 I want to deploy on Kubernetes
→ Start with [Kubernetes CentOS 8 Quick Start](KUBERNETES_CENTOS8_QUICKSTART.md)

### 🔴 I want to deploy on OpenShift
→ See [OpenShift Quickstart](openshift/OPENSHIFT_QUICKSTART.md)

### 🐳 I want container deployment
→ Check [Container Deployment Guide](container-deployment-guide.md)

### 📦 I want Helm charts
→ Read [v1.6.0 Helm Chart](v1.6.0-helm-chart.md)

### 🚀 I want performance optimization
→ Review [LVM Enterprise Improvements](../LVM_AND_ENTERPRISE_IMPROVEMENTS.md)

## Contributing

See [Contributing Guide](../development/contributing.md) for development and deployment contributions.

---

**Last Updated**: March 29, 2026
**Version**: 0.3.0
**Platform Support**: Kubernetes 1.24-1.33, OpenShift 4.10-4.16
**LVM Performance**: 7x faster with 100% host protection
