# Kubernetes End-to-End Testing Guide

This guide explains how to run automated end-to-end tests for h2kvm in Kubernetes, specifically testing CentOS 9 VM migration.

## Quick Start

The easiest way to run E2E tests is using the automated script:

```bash
# Run fully automated E2E test (recommended)
make e2e-k8s

# Or run directly
bash scripts/run-e2e-test.sh
```

The script intelligently:
- ✅ Checks what's already deployed
- ✅ Only runs necessary steps
- ✅ Skips redundant operations
- ✅ Can be run multiple times safely

## Prerequisites

### Required Tools
- `kubectl` - Kubernetes CLI
- `docker` - Container runtime
- Running Kubernetes cluster (k3d, minikube, or production)

### Optional Tools
- `k3d` - For local cluster testing
- `jq` - For JSON parsing in smart checks

### Test Data
- CentOS 9 VMDK file (optional, for full migration test)
- Default location: `/home/ssahani/Downloads/VM-Images/centos/centos9.vmdk`
- Override: `CENTOS9_VMDK=/path/to/centos9.vmdk make e2e-k8s`

## Testing Modes

### 1. Automated Mode (Recommended)

Runs intelligent checks and only executes needed steps:

```bash
make e2e-k8s
```

Features:
- Detects existing deployments
- Reuses built images
- Uploads data only if needed
- Interactive prompts for rebuilds
- Continuous monitoring option

### 2. Detailed Workflow Mode

Runs all steps with detailed logging:

```bash
make e2e-k8s-detailed
```

Useful for:
- First-time setup
- Troubleshooting
- Understanding the workflow

### 3. CI/CD Mode

Automated testing without prompts:

```bash
# Via GitHub Actions (automatic on push)
# See .github/workflows/e2e-k8s-test.yml

# Manual CI-style run
SKIP_BUILD=false \
CENTOS9_VMDK="" \
bash scripts/test-centos9-e2e-k8s.sh
```

## Configuration Options

### Environment Variables

```bash
# Cluster configuration
CLUSTER_NAME=h2kvm-test          # k3d cluster name
NAMESPACE_OPERATOR=h2kvm-system  # Operator namespace
NAMESPACE_WORKERS=h2kvm-workers  # Worker namespace
NAMESPACE_TEST=h2kvm-test        # Test namespace

# Test data
CENTOS9_VMDK=/path/to/centos9.vmdk  # CentOS 9 VMDK file

# Build options
SKIP_BUILD=false                     # Skip image build
SKIP_IMAGE_LOAD=false                # Skip loading image to k3d
FORCE_REBUILD=false                  # Force image rebuild
PUSH_TO_GHCR=false                   # Push to GitHub Container Registry

# GitHub Container Registry
GHCR_REGISTRY=ghcr.io
GITHUB_USER=ssahani
IMAGE_TAG=latest
GITHUB_TOKEN=<your-token>            # For pushing to GHCR

# Execution options
TIMEOUT=600                          # Pod ready timeout (seconds)
AUTO_CLEANUP=false                   # Auto cleanup after test
```

### Example: Custom Configuration

```bash
# Run with custom VMDK and push to GHCR
CENTOS9_VMDK=/data/vms/centos9.vmdk \
PUSH_TO_GHCR=true \
GITHUB_TOKEN=$GITHUB_TOKEN \
make e2e-k8s
```

## Workflow Steps

The E2E test performs these steps:

1. **Prerequisites Check** ✓
   - Verify kubectl, docker, k3d
   - Check cluster connectivity
   - Validate test data availability

2. **Build & Push Images** 🐳
   - Build operator and worker images
   - Optionally push to GHCR
   - Tag with `latest`

3. **Load Images** 📦
   - Import images into k3d cluster
   - Skip for cloud Kubernetes

4. **Deploy CRDs** 📋
   - Install MigrationJob CRD
   - Install OfflineFixJob CRD
   - Install JobTemplate CRD

5. **Create Namespaces** 📁
   - h2kvm-system (operator)
   - h2kvm-workers (workers)
   - h2kvm-test (test jobs)

6. **Label Nodes** 🏷️
   - Mark nodes as worker-enabled
   - `h2kvm.io/worker-enabled=true`

7. **Deploy Workers** ⚙️
   - Create PVCs (local-path for k3d)
   - Deploy RBAC resources
   - Deploy DaemonSet

8. **Upload Test Data** 📤
   - Copy VMDK to worker pod
   - `/data/input/centos9.vmdk`

9. **Create MigrationJob** 🚀
   - Apply CentOS 9 E2E test job
   - Configure VirtIO drivers
   - Enable all fixes

10. **Monitor Progress** 📊
    - Watch job status
    - Stream logs
    - Report results

## Test Artifacts

### Created Resources

```bash
# View all E2E resources
kubectl get all -n h2kvm-test
kubectl get migrationjobs -n h2kvm-test
kubectl get pods -n h2kvm-workers

# Check CRDs
kubectl get crds | grep h2kvm
```

### MigrationJob Specification

The test creates a MigrationJob with:

```yaml
apiVersion: h2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: centos9-e2e-test
spec:
  operation: convert
  image:
    path: /data/input/centos9.vmdk
    format: vmdk
  parameters:
    # VirtIO drivers for CentOS 9
    initramfs_modules:
      - virtio_blk
      - virtio_scsi
      - virtio_net
      - virtio_pci
    # Filesystem fixes
    fstab_mode: stabilize-all
    grub_fixes: true
    regen_initramfs: true
    # Network configuration
    network_fixes: true
    network_config:
      mode: dhcp
    # Output
    output_format: qcow2
    compress: true
    compression_type: zstd
```

## Monitoring & Debugging

### View Job Status

```bash
# Get job status
kubectl get migrationjob centos9-e2e-test -n h2kvm-test -o wide

# Describe job
kubectl describe migrationjob centos9-e2e-test -n h2kvm-test

# Watch for changes
kubectl get migrationjobs -n h2kvm-test -w
```

### View Logs

```bash
# Operator logs
kubectl logs -n h2kvm-system -l app=h2kvm-operator -f

# Worker logs
kubectl logs -n h2kvm-workers -l app=h2kvm-worker -f

# Specific pod logs
kubectl logs -n h2kvm-workers <pod-name> -f
```

### Debug Workers

```bash
# List worker pods
kubectl get pods -n h2kvm-workers -o wide

# Exec into worker
kubectl exec -it -n h2kvm-workers <pod-name> -- /bin/bash

# Check uploaded data
kubectl exec -n h2kvm-workers <pod-name> -- ls -lh /data/input/

# Check output
kubectl exec -n h2kvm-workers <pod-name> -- ls -lh /data/output/
```

## Cleanup

### Quick Cleanup

```bash
# Clean test resources only
make e2e-clean

# Or with script
AUTO_CLEANUP=true bash scripts/run-e2e-test.sh
```

### Full Cleanup

```bash
# Delete all h2kvm resources
kubectl delete namespace h2kvm-system h2kvm-workers h2kvm-test

# Delete CRDs
kubectl delete crd migrationjobs.h2kvm.io
kubectl delete crd offlinefixjobs.h2kvm.io
kubectl delete crd jobtemplates.h2kvm.io

# Remove node labels
kubectl label nodes --all h2kvm.io/worker-enabled-
```

## Building & Pushing Images

### Build Locally

```bash
# Build all images
make build-images

# Or directly
bash scripts/build-and-push-images.sh
```

### Push to GHCR

```bash
# Export GitHub token
export GITHUB_TOKEN=<your-token>

# Build and push
make push-images

# Or with options
PUSH=true \
TAG=v2.0.0 \
GITHUB_USER=ssahani \
bash scripts/build-and-push-images.sh
```

### Use GHCR Images in Kubernetes

```bash
# Update deployment to use GHCR images
kubectl set image deployment/h2kvm-operator \
  operator=ghcr.io/ssahani/h2kvm-operator:latest \
  -n h2kvm-system

kubectl set image daemonset/h2kvm-worker \
  worker=ghcr.io/ssahani/h2kvm-worker:latest \
  -n h2kvm-workers
```

## CI/CD Integration

### GitHub Actions

Two workflows are provided:

1. **Build and Push Images** (`.github/workflows/build-and-push-images.yml`)
   - Triggers on: push to main, tags, PRs
   - Builds: operator and worker images
   - Pushes to: ghcr.io (on main/tags)
   - Multi-arch: linux/amd64, linux/arm64

2. **E2E Tests** (`.github/workflows/e2e-k8s-test.yml`)
   - Triggers on: push to main, PRs
   - Creates: k3d cluster
   - Runs: Full E2E workflow
   - Collects: Logs on failure

### Local CI Testing

```bash
# Simulate CI environment
SKIP_BUILD=false \
CENTOS9_VMDK="" \
bash scripts/test-centos9-e2e-k8s.sh
```

## Troubleshooting

### Worker Pods Not Starting

```bash
# Check pod status
kubectl describe pod -n h2kvm-workers <pod-name>

# Common issues:
# 1. Image not found - run: make build-images
# 2. PVC pending - check storage class
# 3. Init container failed - check node capabilities
```

### MigrationJob Stuck in Validated

```bash
# Worker pods need to be Running
kubectl get pods -n h2kvm-workers

# Check if image exists in pod
kubectl describe pod -n h2kvm-workers <pod-name> | grep Image:
```

### VMDK Upload Failed

```bash
# Check pod is running
kubectl get pod -n h2kvm-workers <pod-name>

# Check available space
kubectl exec -n h2kvm-workers <pod-name> -- df -h /data/input

# Manual upload
kubectl cp /path/to/centos9.vmdk \
  h2kvm-workers/<pod-name>:/data/input/centos9.vmdk
```

## Advanced Usage

### Custom Test VMs

Create your own MigrationJob:

```yaml
apiVersion: h2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: my-custom-test
  namespace: h2kvm-test
spec:
  operation: convert
  image:
    path: /data/input/my-vm.vmdk
    format: vmdk
  parameters:
    output_format: qcow2
    # ... custom parameters
```

### Parallel Testing

Run multiple MigrationJobs:

```bash
# Apply multiple job specs
kubectl apply -f k8s/examples/

# Monitor all jobs
kubectl get migrationjobs -A -w
```

### Performance Testing

```bash
# Set resource limits
kubectl patch daemonset h2kvm-worker -n h2kvm-workers --type='json' \
  -p='[{"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/cpu", "value": "8"}]'
```

## Next Steps

- 📖 Read [LIVE_MIGRATION.md](LIVE_MIGRATION.md) for live migration features
- 🔧 Check [UPGRADE_GUIDE.md](UPGRADE_GUIDE.md) for version migration
- 📋 See [QUICK_REFERENCE.md](QUICK_REFERENCE.md) for command reference
- 🐛 Report issues at https://github.com/ssahani/h2kvm/issues

## Support

For questions and support:
- GitHub Issues: https://github.com/ssahani/h2kvm/issues
- Documentation: https://github.com/ssahani/h2kvm/docs
