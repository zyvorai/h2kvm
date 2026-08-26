# h2kvm Kubernetes Operator

Kubernetes operator for converting VM images from various formats (VMDK, VHD, VDI, OVA) to KubeVirt-compatible qcow2 and deploying them as VirtualMachines.

## Overview

The h2kvm operator automates the process of:
1. Downloading VM images from HTTP/HTTPS/S3 sources into DataVolumes
2. Converting disk formats using qemu-img (optional)
3. Applying offline fixes (fstab, grub, initramfs, LVM, network configuration) to migrated Linux VMs
4. Creating KubeVirt VirtualMachines from the converted disks

### Conversion Pipeline

The operator manages the full conversion lifecycle through these phases:

- **Pending**: Resource created, awaiting processing
- **Uploading**: Downloading source image into DataVolume via CDI
- **Converting**: Format conversion (if source format differs from qcow2)
- **Fixing**: Running offline fixes (if `spec.conversion.offlineFixes: true`)
- **CreatingVM**: Creating KubeVirt VirtualMachine resource
- **Ready**: VM is created and ready to start

### Offline Fixes

When `spec.conversion.offlineFixes: true` is set, the operator launches a fixer Job that runs `h2kvmctl` offline fixes on the converted disk. These fixes include:

- **LVM detection and activation**: Discovers LVM physical/logical volumes
- **initramfs regeneration**: Rebuilds initramfs with virtio drivers for KVM
- **fstab updates**: Converts VMware/Hyper-V disk paths to virtio device paths
- **Network configuration**: Updates netplan/NetworkManager for virtio NICs
- **GRUB updates**: Ensures bootloader can boot on KVM

The fixer runs as a Kubernetes Job with the converted DataVolume mounted. It uses the `h2kvmctl` CLI from the `FIXER_IMAGE` container (default: `quay.io/h2kvm/fixer:latest`).

## Architecture

```
┌──────────────────┐
│ HyperConversion  │ (Custom Resource)
│       CRD        │
└────────┬─────────┘
         │
         v
┌──────────────────┐
│ HyperConversion  │
│   Controller     │
└────────┬─────────┘
         │
         ├─────────> Creates DataVolume (CDI)
         │           Uploads/converts source image
         │
         ├─────────> Creates fixer Job (optional)
         │           Runs h2kvmctl offline fixes
         │
         └─────────> Creates VirtualMachine (KubeVirt)
                     Ready to boot
```

## Installation

### Prerequisites

- Kubernetes cluster (1.28+)
- KubeVirt installed (v0.59+)
- CDI (Containerized Data Importer) installed (v1.55+)
- StorageClass with ReadWriteOnce support
- (Optional) Nodes with privileged container support for offline fixes

### Deploy the operator

```bash
# Install CRDs
make install

# Deploy operator
make deploy

# Or deploy from manifests
kubectl apply -f config/crd/
kubectl apply -f config/rbac/
kubectl apply -f config/manager/
```

## Usage

### Basic VM Migration (HTTP source)

```yaml
apiVersion: h2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: ubuntu-migration
  namespace: default
spec:
  source:
    url: "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
    format: qcow2
  storage:
    size: 20Gi
  vm:
    cpu:
      cores: 2
    memory: 4Gi
```

### VMware VMDK Migration with Offline Fixes

```yaml
apiVersion: h2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: vmware-rhel-migration
  namespace: default
spec:
  source:
    url: "https://storage.example.com/rhel88.vmdk"
    format: vmdk
  storage:
    size: 40Gi
    storageClass: local-path
  conversion:
    offlineFixes: true   # Enable offline fixes for LVM, initramfs, fstab, network
    compression: zstd
    timeout: 120
  vm:
    name: rhel88-migrated
    cpu:
      cores: 4
    memory: 4Gi
    firmware: bios
```

### Disk-Only Conversion (No VM)

```yaml
apiVersion: h2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: disk-only
spec:
  source:
    url: "https://example.com/windows.vhd"
    format: vhd
  storage:
    size: 100Gi
  # No vm: section - creates DataVolume only
```

### Check conversion status

```bash
# List conversions
kubectl get hc

# Get detailed status
kubectl get hc ubuntu-migration -o yaml

# Watch conversion progress
kubectl get hc ubuntu-migration -w

# Check fixer Job logs (if offlineFixes enabled)
kubectl logs job/ubuntu-migration-fixer
```

## HyperConversion Spec

### Source Spec

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `url` | string | Yes | - | HTTP/HTTPS/S3 URL of source disk |
| `format` | string | No | qcow2 | Disk format: vmdk, vdi, vhd, vhdx, qcow2, raw |
| `checksum` | string | No | - | Checksum for validation (md5:xxx or sha256:xxx) |
| `secretRef` | object | No | - | Secret with auth credentials |
| `endpoint` | string | No | - | Custom S3 endpoint (for MinIO, Ceph RGW) |
| `region` | string | No | us-east-1 | S3 region |

### Storage Spec

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `storageClass` | string | No | (cluster default) | StorageClass for DataVolume PVC |
| `size` | quantity | No | (auto-detect) | Requested storage size |
| `accessMode` | string | No | ReadWriteOnce | PVC access mode |
| `volumeMode` | string | No | Filesystem | Block or Filesystem |

### Conversion Options

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `compression` | string | No | zstd | Compression type: zstd, zlib, none |
| `offlineFixes` | bool | No | false | Enable offline fixes (LVM, initramfs, fstab, network) |
| `timeout` | int | No | 60 | Conversion timeout in minutes |

### VM Spec (Optional)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | No | (HyperConversion name) | VirtualMachine name |
| `cpu.cores` | int | Yes | - | Number of CPU cores |
| `cpu.sockets` | int | No | 1 | Number of CPU sockets |
| `cpu.threads` | int | No | 1 | Threads per core |
| `memory` | quantity | Yes | - | Memory size (e.g., 4Gi) |
| `firmware` | string | No | bios | Firmware: bios, uefi, uefi-secure |
| `networks` | array | No | - | Network interfaces |
| `runStrategy` | string | No | Always | Run strategy: Always, Manual, Halted, RerunOnFailure |

## HyperConversion Status

| Field | Type | Description |
|-------|------|-------------|
| `phase` | string | Current phase: Pending, Uploading, Converting, Fixing, CreatingVM, Ready, Failed |
| `progress` | int | Progress percentage (0-100) |
| `dataVolumeName` | string | Name of created DataVolume |
| `fixerJobName` | string | Name of offline fixer Job (if offlineFixes enabled) |
| `virtualMachineName` | string | Name of created VirtualMachine |
| `uploadProgress` | object | Detailed upload progress (bytes, speed) |
| `startTime` | time | Conversion start time |
| `completionTime` | time | Conversion completion time |
| `conditions` | array | Conditions: DataVolumeReady, FixesComplete, VMReady |
| `message` | string | Human-readable status message |

### Conditions

| Type | Description |
|------|-------------|
| `DataVolumeReady` | DataVolume import completed successfully |
| `FixesComplete` | Offline fixes completed (if enabled) |
| `VMReady` | VirtualMachine created and ready |
| `ConversionComplete` | Full conversion pipeline complete |

## Development

### Build the operator

```bash
# Build binary
make build

# Run tests
make test

# Build container image
make docker-build IMG=myregistry/h2kvm-operator:latest

# Push container image
make docker-push IMG=myregistry/h2kvm-operator:latest
```

### Run locally

```bash
# Install CRDs
make install

# Set environment variables for local development
export FIXER_IMAGE=quay.io/h2kvm/fixer:latest

# Run controller locally
make run
```

### Environment Variables

The operator supports these environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `FIXER_IMAGE` | `quay.io/h2kvm/fixer:latest` | Container image for offline fixer Job |
| `FIXER_PULL_POLICY` | `IfNotPresent` | Image pull policy for fixer |

These can be set in the operator deployment or via Helm values.

### Generate manifests and code

```bash
# Generate CRD manifests
make manifests

# Generate DeepCopy methods
make generate
```

## RBAC Requirements

The operator requires these permissions:

- **DataVolumes** (cdi.kubevirt.io/v1beta1): create, get, list, watch, update, patch
- **VirtualMachines** (kubevirt.io/v1): create, get, list, watch, update, patch, delete
- **Jobs** (batch/v1): create, get, list, watch, update, patch, delete
- **PersistentVolumeClaims** (v1): get, list, watch
- **Events** (v1): create, patch

The fixer Job runs with:
- Privileged: true (for device access)
- HostPath volume: DataVolume PVC mounted
- ServiceAccount with minimal permissions

## Troubleshooting

### Conversion stuck in Uploading phase

```bash
# Check DataVolume status
kubectl describe datavolume <name>-dv

# Check CDI upload pod logs
kubectl logs -n cdi -l app=cdi-uploadproxy
```

### Fixes not running

```bash
# Check if fixer Job was created
kubectl get job <name>-fixer

# Check fixer Job logs
kubectl logs job/<name>-fixer

# Verify FIXER_IMAGE is set
kubectl get deployment -n h2kvm-system -o yaml | grep FIXER_IMAGE
```

### VirtualMachine not created

```bash
# Check conditions
kubectl get hc <name> -o jsonpath='{.status.conditions}'

# Check events
kubectl get events --field-selector involvedObject.name=<name>
```

## License

Apache License 2.0
