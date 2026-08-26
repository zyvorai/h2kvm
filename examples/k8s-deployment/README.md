# Kubernetes Deployment Examples

This directory contains example configurations for automated Kubernetes/k3s deployment.

## Quick Start

### Basic Deployment

```bash
# 1. Copy and edit the basic config
cp basic-k8s-deployment.yaml my-migration.yaml
nano my-migration.yaml  # Update vmdk path and settings

# 2. Run migration + deployment
sudo h2kvmctl --config my-migration.yaml
```

### Production Deployment

```bash
# Use the production template for full features
sudo h2kvmctl --config production-deployment.yaml
```

## Examples

### 1. basic-k8s-deployment.yaml
Simple configuration for getting started with K8s deployment.
- Uses local-path storage (k3s default)
- 2 CPU cores, 4GB RAM
- Manual VM start

### 2. production-deployment.yaml
Complete production configuration with all features.
- Uses Longhorn replicated storage
- 8 CPU cores, 16GB RAM
- Auto-start and wait for ready
- Comprehensive logging

### 3. multi-namespace-deployment.yaml
Deploy multiple VMs to different namespaces.
- Demonstrates namespace organization
- Different resource allocations
- Mixed auto-start settings

## Configuration Options

### Required Settings

```yaml
cmd: local
vmdk: /path/to/vm.vmdk
deploy_k8s: true
```

### Storage Settings

```yaml
k8s_storage_class: local-path  # k3s default
# or
k8s_storage_class: longhorn    # replicated storage
# or
k8s_storage_class: nfs-client  # NFS storage
```

### VM Resources

```yaml
k8s_cpu: "4"        # CPU cores (string!)
k8s_memory: 8Gi     # Memory with unit
k8s_pvc_size: 50Gi  # Disk size
```

### Lifecycle

```yaml
k8s_auto_start: true   # Start VM immediately
k8s_wait_ready: true   # Wait for boot
```

## Storage Class Guide

### k3s (local-path)
- **Best for**: Development, testing, single-node
- **Features**: Built-in, no setup
- **Limitations**: No live migration (ReadWriteOnce)

### Longhorn
- **Best for**: Production, multi-node
- **Features**: Replication, snapshots, ReadWriteMany
- **Setup**: https://longhorn.io/docs/

### NFS
- **Best for**: Shared storage, legacy systems
- **Features**: ReadWriteMany, external storage
- **Setup**: Requires NFS server

### Rook/Ceph
- **Best for**: Enterprise, large scale
- **Features**: Distributed storage, high availability
- **Setup**: https://rook.io/docs/

## Troubleshooting

### PVC Not Binding

If PVC stays in "Pending" with local-path storage, this is normal. It uses "WaitForFirstConsumer" binding mode and will bind when the uploader pod starts.

### kubectl cp Permission Denied

Ensure you're using the correct kubeconfig:
```bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
```

### VM Won't Start

If k8s_auto_start is false, start manually:
```bash
kubectl patch vm <vm-name> -n <namespace> \\
  --type merge -p '{"spec":{"running":true}}'
```

## See Also

- [K8s Automated Deployment Guide](../../docs/guides/k8s-automated-deployment.md)
- [KubeVirt Documentation](https://kubevirt.io/)
- [k3s Documentation](https://docs.k3s.io/)
