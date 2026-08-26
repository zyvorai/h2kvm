# Getting Started with HyperConversion Operator

This guide walks you through installing and using the HyperConversion operator for the first time.

## Prerequisites

Before you begin, ensure you have:

1. **Kubernetes Cluster** (v1.24 or later)
   - Local development: k3d, minikube, or kind
   - Production: Any Kubernetes distribution

2. **CDI Installed** (v1.58.0 or later)
   ```bash
   export CDI_VERSION=v1.58.0
   kubectl apply -f https://github.com/kubevirt/containerized-data-importer/releases/download/${CDI_VERSION}/cdi-operator.yaml
   kubectl apply -f https://github.com/kubevirt/containerized-data-importer/releases/download/${CDI_VERSION}/cdi-cr.yaml
   ```

3. **KubeVirt Installed** (v1.0.0 or later)
   ```bash
   export KUBEVIRT_VERSION=v1.1.0
   kubectl apply -f https://github.com/kubevirt/kubevirt/releases/download/${KUBEVIRT_VERSION}/kubevirt-operator.yaml
   kubectl apply -f https://github.com/kubevirt/kubevirt/releases/download/${KUBEVIRT_VERSION}/kubevirt-cr.yaml
   ```

4. **kubectl** configured to access your cluster

5. **Go 1.21+** (only if building from source)

## Installation

### Option 1: Install from Pre-built Image (Recommended)

```bash
# Navigate to operator directory
cd hyper2kvm/operator

# Install CRDs
make install

# Deploy operator with pre-built image
make deploy IMG=ghcr.io/ssahani/hyper2kvm-operator:latest
```

### Option 2: Build and Install from Source

```bash
# Clone repository
git clone https://github.com/ssahani/hyper2kvm.git
cd hyper2kvm/operator

# Download Go dependencies
go mod download

# Run tests
make test

# Build operator image
make docker-build IMG=hyper2kvm-operator:dev

# Load image to local cluster (k3d example)
k3d image import hyper2kvm-operator:dev

# Install CRDs
make install

# Deploy operator
make deploy IMG=hyper2kvm-operator:dev
```

## Verify Installation

Check that the operator is running:

```bash
# Check operator pod
kubectl get pods -n hyper2kvm-system

# Expected output:
# NAME                                        READY   STATUS    RESTARTS   AGE
# hyperconversion-operator-xxxxxxxxxx-xxxxx   1/1     Running   0          30s

# Check operator logs
kubectl logs -n hyper2kvm-system -l control-plane=controller-manager -f

# Verify CRD installed
kubectl get crd hyperconversions.hyper2kvm.io
```

## Your First HyperConversion

### Step 1: Create a HyperConversion Resource

Create a file `my-first-conversion.yaml`:

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: my-first-conversion
  namespace: default
spec:
  source:
    url: "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
    format: qcow2

  storage:
    storageClass: local-path  # Change to your StorageClass
    size: 20Gi
    accessMode: ReadWriteOnce

  vm:
    cpu:
      cores: 2
    memory: 4Gi
    firmware: bios

    cloudInit:
      userData: |
        #cloud-config
        hostname: my-first-vm
        users:
          - name: ubuntu
            sudo: ALL=(ALL) NOPASSWD:ALL
            password: ubuntu
            chpasswd: { expire: False }
            ssh_authorized_keys:
              - ssh-rsa AAAAB3... # Add your SSH public key
```

### Step 2: Apply the Resource

```bash
kubectl apply -f my-first-conversion.yaml
```

### Step 3: Monitor Progress

Watch the conversion progress:

```bash
# Watch HyperConversion status
kubectl get hyperconversion my-first-conversion -w

# View detailed status
kubectl describe hyperconversion my-first-conversion

# Check events
kubectl get events --sort-by='.lastTimestamp' | grep my-first-conversion
```

You should see the phase transition:
```
NAME                  PHASE       PROGRESS   DATAVOLUME              VM
my-first-conversion   Pending     0
my-first-conversion   Uploading   5          my-first-conversion-dv
my-first-conversion   Uploading   25         my-first-conversion-dv
my-first-conversion   Uploading   75         my-first-conversion-dv
my-first-conversion   CreatingVM  75         my-first-conversion-dv
my-first-conversion   Ready       100        my-first-conversion-dv  my-first-conversion
```

### Step 4: Verify Resources Created

```bash
# Check DataVolume
kubectl get datavolume

# Check VirtualMachine
kubectl get vm

# Check VirtualMachineInstance (if VM is running)
kubectl get vmi
```

### Step 5: Access the VM

```bash
# Start the VM (if not auto-started)
virtctl start my-first-conversion

# Access via console
virtctl console my-first-conversion

# SSH to the VM (requires service/ingress setup)
# ... configure networking based on your setup
```

## Common Workflows

### Disk-Only Conversion (No VM)

Convert a disk without creating a VM:

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: disk-only
spec:
  source:
    url: "https://example.com/disk.vmdk"
    format: vmdk

  storage:
    storageClass: ceph-rbd
    size: 50Gi

  # No vm: section - only creates DataVolume
```

The created DataVolume can be used later to manually create a VM.

### Windows VM with UEFI Secure Boot

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: windows-server
spec:
  source:
    url: "https://example.com/windows-server-2022.vhdx"
    format: vhdx

  storage:
    size: 100Gi

  vm:
    cpu:
      cores: 4
    memory: 8Gi
    firmware: uefi-secure  # Required for Windows 11/Server 2022

    networks:
    - name: default
      type: pod
      model: e1000e  # Windows compatibility
```

### Multi-Network VM

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: multi-net-vm
spec:
  source:
    url: "https://example.com/ubuntu.qcow2"
    format: qcow2

  storage:
    size: 20Gi

  vm:
    cpu:
      cores: 2
    memory: 4Gi

    networks:
    - name: default
      type: pod

    - name: management
      type: multus
      networkName: management-network

    - name: data
      type: bridge
      networkName: data-bridge
```

## Cleanup

Delete a HyperConversion (automatically cleans up DataVolume and VM):

```bash
kubectl delete hyperconversion my-first-conversion
```

Uninstall the operator:

```bash
# Undeploy operator
make undeploy

# Uninstall CRDs (WARNING: deletes all HyperConversion resources)
make uninstall
```

## Next Steps

- Read [API Reference](hyperconversion-crd.md) for complete field documentation
- See [Examples](examples.md) for more complex use cases
- Check [Troubleshooting](troubleshooting.md) if you encounter issues
- Review operator [README](../../operator/README.md) for development information

## Getting Help

- **Documentation**: See [docs/operator/](.)
- **Issues**: https://github.com/ssahani/hyper2kvm/issues
- **Examples**: [operator/config/samples/](../../operator/config/samples/)
