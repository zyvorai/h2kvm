# HyperConversion Operator - Installation Guide

**Version**: v1.2.0
**Status**: Production Ready (96%)

## Quick Start

### Prerequisites

- Kubernetes cluster (v1.24+)
- kubectl configured with cluster access
- KubeVirt installed (v1.0.0+)
- CDI installed (v1.58.0+)

### Option 1: Install via OperatorHub (Recommended)

**From OperatorHub.io**:
```bash
kubectl create -f https://operatorhub.io/install/hyperconversion-operator.yaml
```

**From OpenShift Console**:
1. Navigate to Operators → OperatorHub
2. Search for "HyperConversion"
3. Click Install
4. Select installation namespace
5. Choose update approval strategy

### Option 2: Install via operator-sdk

```bash
# Install operator-sdk (if not already installed)
brew install operator-sdk  # macOS
# OR
curl -LO https://github.com/operator-framework/operator-sdk/releases/download/v1.34.1/operator-sdk_linux_amd64
chmod +x operator-sdk_linux_amd64 && sudo mv operator-sdk_linux_amd64 /usr/local/bin/operator-sdk

# Run bundle
operator-sdk run bundle ghcr.io/ssahani/h2kvm-operator-bundle:v1.2.0

# Verify installation
kubectl get csv -n operators | grep hyperconversion
kubectl get pods -n operators | grep hyperconversion
```

### Option 3: Install from Source

```bash
# Clone repository
git clone https://github.com/ssahani/h2kvm.git
cd h2kvm/operator

# Install CRDs
make install

# Build operator image
make docker-build IMG=h2kvm-operator:v1.2.0

# Load to cluster (for local k3d/kind)
k3d image import h2kvm-operator:v1.2.0
# OR
kind load docker-image h2kvm-operator:v1.2.0

# Deploy operator
make deploy IMG=h2kvm-operator:v1.2.0

# Verify
kubectl get pods -n h2kvm-system
kubectl logs -n h2kvm-system -l control-plane=controller-manager -f
```

### Option 4: Direct YAML Installation

```bash
# Install CRDs and operator in one step
kubectl apply -f https://github.com/ssahani/h2kvm/releases/download/operator/v1.2.0/install.yaml

# Verify
kubectl get crds | grep hyperconversions
kubectl get deployment -n h2kvm-system
```

## Installing h2kctl CLI

### From Source

```bash
cd h2kvm/operator

# Build and install
make install-h2kctl

# Verify
h2kctl version
```

### From GitHub Release

```bash
# Download binary (replace with your architecture)
curl -LO https://github.com/ssahani/h2kvm/releases/download/operator/v1.2.0/h2kctl-linux-amd64
chmod +x h2kctl-linux-amd64
sudo mv h2kctl-linux-amd64 /usr/local/bin/h2kctl

# Verify
h2kctl version
```

## Post-Installation

### 1. Verify Operator is Running

```bash
# Check operator pod
kubectl get pods -n h2kvm-system

# Expected output:
# NAME                                              READY   STATUS    RESTARTS   AGE
# hyperconversion-operator-controller-manager-xxx   2/2     Running   0          2m

# Check logs
kubectl logs -n h2kvm-system -l control-plane=controller-manager -f
```

### 2. Install Cloud-Init Templates (Optional)

```bash
cd h2kvm/operator/templates/cloud-init

# Ubuntu template
kubectl create configmap ubuntu-init \
  --from-file=userdata=ubuntu-server.yaml \
  -n default

# CentOS template
kubectl create configmap centos-init \
  --from-file=userdata=centos-server.yaml \
  -n default

# Kubernetes node template
kubectl create configmap k8s-init \
  --from-file=userdata=kubernetes-node.yaml \
  -n default
```

### 3. Test with Sample HyperConversion

```bash
# Create test migration
cat <<EOF | kubectl apply -f -
apiVersion: h2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: test-migration
spec:
  source:
    url: "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
    format: qcow2
  storage:
    storageClass: local-path
    size: 10Gi
  vm:
    name: test-vm
    cpu:
      cores: 2
    memory: 2Gi
    firmware: bios
    cloudInit:
      userData: |
        #cloud-config
        hostname: test-vm
        users:
          - name: ubuntu
            sudo: ALL=(ALL) NOPASSWD:ALL
            ssh_authorized_keys:
              - ssh-rsa AAAAB3NzaC1yc2E... # Add your SSH key
EOF

# Monitor progress
kubectl get hyperconversion test-migration -w

# Check details
kubectl describe hyperconversion test-migration

# Expected phases: Pending → Uploading → CreatingVM → Ready
```

### 4. Test with h2kctl CLI

```bash
# Create migration via CLI
h2kctl migrate https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img \
  --vm-name ubuntu-vm \
  --cpu 2 \
  --memory 4Gi \
  --storage-class local-path

# List migrations
h2kctl list

# View details
h2kctl describe ubuntu-vm

# Stream logs
h2kctl logs ubuntu-vm -f

# Delete when done
h2kctl delete ubuntu-vm
```

## Multi-Architecture Deployment

### Build Multi-Arch Images

```bash
cd h2kvm/operator

# Build for AMD64 and ARM64 (primary platforms)
make docker-buildx IMG=myregistry.io/h2kvm-operator:v1.2.0

# Build for all platforms (AMD64, ARM64, s390x, ppc64le)
make docker-buildx-extended IMG=myregistry.io/h2kvm-operator:v1.2.0

# Deploy to ARM cluster (automatic platform detection)
make deploy IMG=myregistry.io/h2kvm-operator:v1.2.0
```

## Air-Gapped / Private Registry Installation

### 1. Push Images to Private Registry

```bash
# Tag operator image
docker tag h2kvm-operator:v1.2.0 registry.example.com/h2kvm-operator:v1.2.0
docker push registry.example.com/h2kvm-operator:v1.2.0

# Build and push bundle
make bundle-build BUNDLE_IMG=registry.example.com/h2kvm-bundle:v1.2.0
make bundle-push BUNDLE_IMG=registry.example.com/h2kvm-bundle:v1.2.0

# Build and push catalog
make catalog-build CATALOG_IMG=registry.example.com/h2kvm-catalog:v1.2.0
make catalog-push CATALOG_IMG=registry.example.com/h2kvm-catalog:v1.2.0
```

### 2. Create CatalogSource

```yaml
apiVersion: operators.coreos.com/v1alpha1
kind: CatalogSource
metadata:
  name: hyperconversion-catalog
  namespace: olm
spec:
  sourceType: grpc
  image: registry.example.com/h2kvm-catalog:v1.2.0
  displayName: HyperConversion Operator Catalog
  publisher: VisionCodex
  updateStrategy:
    registryPoll:
      interval: 30m
```

### 3. Install from Private Catalog

```bash
kubectl apply -f catalog-source.yaml

# Wait for catalog to be ready
kubectl get catalogsource -n olm

# Install via Subscription
cat <<EOF | kubectl apply -f -
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: hyperconversion-operator
  namespace: operators
spec:
  channel: stable
  name: hyperconversion-operator
  source: hyperconversion-catalog
  sourceNamespace: olm
EOF
```

## Upgrading

### From v1.1.x to v1.2.0

No migration required. The operator is fully backward compatible.

**Via OLM** (automatic):
```bash
# Check current version
kubectl get csv -n operators | grep hyperconversion

# OLM will automatically upgrade if approval strategy is Automatic
# For Manual approval:
kubectl patch installplan <installplan-name> -n operators \
  --type merge --patch '{"spec":{"approved":true}}'
```

**Via Direct Install**:
```bash
# Update CRDs
make install

# Update operator image
kubectl set image deployment/hyperconversion-operator-controller-manager \
  manager=ghcr.io/ssahani/h2kvm-operator:v1.2.0 \
  -n h2kvm-system
```

## Uninstalling

### Via operator-sdk

```bash
operator-sdk cleanup hyperconversion-operator
```

### Via Direct Install

```bash
# Remove operator
make undeploy

# Remove CRDs (this will delete all HyperConversion resources!)
make uninstall
```

### Via OLM

```bash
# Delete subscription
kubectl delete subscription hyperconversion-operator -n operators

# Delete CSV
kubectl delete csv hyperconversion-operator.v1.2.0 -n operators

# Delete CatalogSource (if custom)
kubectl delete catalogsource hyperconversion-catalog -n olm
```

## Troubleshooting

### Operator Not Starting

```bash
# Check pod status
kubectl get pods -n h2kvm-system

# View logs
kubectl logs -n h2kvm-system -l control-plane=controller-manager

# Check events
kubectl get events -n h2kvm-system --sort-by='.lastTimestamp'

# Verify RBAC
kubectl auth can-i '*' '*' --as=system:serviceaccount:h2kvm-system:hyperconversion-operator-controller-manager
```

### HyperConversion Stuck in Pending

```bash
# Check resource details
kubectl describe hyperconversion <name>

# Check DataVolume status
kubectl get datavolume

# Check CDI pods
kubectl get pods -n cdi

# Check events
kubectl get events --sort-by='.lastTimestamp'
```

### VM Creation Failed

```bash
# Check VM status
kubectl get vm

# Describe VM
kubectl describe vm <vm-name>

# Check KubeVirt pods
kubectl get pods -n kubevirt

# Check virt-launcher logs
kubectl logs <virt-launcher-pod> -n <namespace>
```

### Enable Debug Logging

```bash
# Edit operator deployment
kubectl edit deployment hyperconversion-operator-controller-manager -n h2kvm-system

# Add/modify args:
# - --zap-log-level=debug
# - --zap-development=true

# Restart operator
kubectl rollout restart deployment/hyperconversion-operator-controller-manager -n h2kvm-system
```

## Support

- **Documentation**: https://github.com/ssahani/h2kvm
- **Issues**: https://github.com/ssahani/h2kvm/issues
- **Email**: susant@visioncodex.com
- **Slack**: #h2kvm (Kubernetes Slack)

## Next Steps

1. Read the [User Guide](./docs/operator/getting-started.md)
2. Review [Examples](./config/samples/)
3. Check [Cloud-Init Templates](./templates/cloud-init/README.md)
4. Learn about [Multi-Disk VMs](./docs/MULTI_DISK.md)
5. Explore [OLM Integration](./docs/OLM_INTEGRATION.md)
