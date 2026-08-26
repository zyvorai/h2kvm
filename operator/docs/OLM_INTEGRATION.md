# OLM Bundle Integration

The HyperConversion Operator can be installed via OperatorHub using the Operator Lifecycle Manager (OLM).

## Overview

The OLM bundle provides:
- **OperatorHub Integration**: Install directly from OperatorHub.io or OpenShift Console
- **Automated Updates**: Managed upgrades via OLM subscription
- **Dependency Management**: Automatic handling of prerequisites
- **Multi-Architecture**: AMD64, ARM64, s390x, ppc64le support
- **Enterprise Ready**: Compatible with disconnected/air-gapped environments

## Bundle Contents

```
bundle/
├── manifests/
│   ├── hyperconversion-operator.clusterserviceversion.yaml  # Operator metadata
│   └── h2kvm.io_hyperconversions.yaml                   # CRD
├── metadata/
│   └── annotations.yaml                                      # Bundle annotations
└── tests/
    └── scorecard/
        └── config.yaml                                       # Scorecard tests
```

## Installation Methods

### Method 1: OperatorHub.io (Public Catalogs)

For community Kubernetes clusters:

```bash
# Install from OperatorHub.io
kubectl create -f https://operatorhub.io/install/hyperconversion-operator.yaml

# Verify installation
kubectl get csv -n operators

# Create a HyperConversion resource
kubectl apply -f config/samples/h2kvm_v1alpha1_hyperconversion.yaml
```

### Method 2: OpenShift OperatorHub

For OpenShift clusters:

1. Open the OpenShift Console
2. Navigate to **Operators → OperatorHub**
3. Search for "HyperConversion"
4. Click **Install**
5. Choose installation mode:
   - All namespaces (recommended)
   - Specific namespace
6. Select update channel: **stable** or **alpha**
7. Choose approval strategy: **Automatic** or **Manual**
8. Click **Install**

### Method 3: CLI Installation (operator-sdk)

Using operator-sdk directly:

```bash
# Install the bundle
operator-sdk run bundle ghcr.io/ssahani/h2kvm-operator-bundle:v1.2.0

# Verify
kubectl get csv -A | grep hyperconversion

# Cleanup when done
operator-sdk cleanup hyperconversion-operator
```

### Method 4: Private Catalog (Air-Gapped)

For disconnected/air-gapped environments:

```bash
# 1. Build and push bundle to your registry
export BUNDLE_IMG=registry.example.com/hyperconversion-operator-bundle:v1.2.0
make bundle-build bundle-push BUNDLE_IMG=$BUNDLE_IMG

# 2. Create a catalog image
export CATALOG_IMG=registry.example.com/hyperconversion-operator-catalog:v1.2.0
make catalog-build catalog-push CATALOG_IMG=$CATALOG_IMG

# 3. Create CatalogSource
cat <<EOF | kubectl apply -f -
apiVersion: operators.coreos.com/v1alpha1
kind: CatalogSource
metadata:
  name: hyperconversion-catalog
  namespace: olm
spec:
  sourceType: grpc
  image: $CATALOG_IMG
  displayName: HyperConversion Operator
  updateStrategy:
    registryPoll:
      interval: 30m
EOF

# 4. Create Subscription
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
  installPlanApproval: Automatic
EOF
```

## Building the Bundle

### Prerequisites

```bash
# Install operator-sdk
curl -LO https://github.com/operator-framework/operator-sdk/releases/download/v1.34.1/operator-sdk_linux_amd64
chmod +x operator-sdk_linux_amd64
sudo mv operator-sdk_linux_amd64 /usr/local/bin/operator-sdk

# Install opm (Operator Package Manager)
curl -LO https://github.com/operator-framework/operator-registry/releases/download/v1.38.0/linux-amd64-opm
chmod +x linux-amd64-opm
sudo mv linux-amd64-opm /usr/local/bin/opm
```

### Build Bundle

```bash
# 1. Generate bundle manifests
make bundle

# 2. Validate bundle
operator-sdk bundle validate ./bundle

# 3. Build bundle image
export BUNDLE_IMG=ghcr.io/ssahani/h2kvm-operator-bundle:v1.2.0
make bundle-build BUNDLE_IMG=$BUNDLE_IMG

# 4. Push to registry
make bundle-push BUNDLE_IMG=$BUNDLE_IMG

# 5. Test bundle
operator-sdk run bundle $BUNDLE_IMG
```

### Build Multi-Architecture Bundle

```bash
# Build for multiple architectures
docker buildx build \
  --platform linux/amd64,linux/arm64,linux/s390x,linux/ppc64le \
  --push \
  --tag ghcr.io/ssahani/h2kvm-operator-bundle:v1.2.0 \
  -f bundle.Dockerfile .
```

## Channels

The operator is published on two channels:

- **stable**: Production-ready releases (recommended)
- **alpha**: Early access to new features

```yaml
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
spec:
  channel: stable  # or alpha
  name: hyperconversion-operator
```

## Update Strategy

### Automatic Updates

Default behavior - operator auto-updates to latest version in channel:

```yaml
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
spec:
  installPlanApproval: Automatic
```

### Manual Updates

Require approval before upgrading:

```yaml
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
spec:
  installPlanApproval: Manual
```

Approve pending updates:

```bash
# List pending install plans
kubectl get installplan -n operators

# Approve an install plan
kubectl patch installplan <install-plan-name> \
  -n operators \
  --type merge \
  --patch '{"spec":{"approved":true}}'
```

## Version Skipping

The operator supports version skipping:

```
v1.0.0 → v1.2.0 (skip v1.1.0)
```

No need to upgrade sequentially.

## Uninstallation

### Via OpenShift Console

1. Navigate to **Operators → Installed Operators**
2. Find "HyperConversion Operator"
3. Click the kebab menu (⋮)
4. Select **Uninstall Operator**

### Via CLI

```bash
# Delete subscription
kubectl delete subscription hyperconversion-operator -n operators

# Delete CSV
kubectl delete csv hyperconversion-operator.v1.2.0 -n operators

# Clean up CRDs (optional, deletes all HyperConversion resources)
kubectl delete crd hyperconversions.h2kvm.io
```

### Using operator-sdk

```bash
operator-sdk cleanup hyperconversion-operator
```

## Troubleshooting

### Bundle Validation Errors

```bash
# Validate bundle
operator-sdk bundle validate ./bundle

# Common fixes:
# - Update CSV with correct image references
# - Ensure CRD has proper validation schemas
# - Check RBAC permissions are complete
```

### Installation Stuck

Check install plan status:

```bash
# View install plans
kubectl get installplan -n operators

# Describe for details
kubectl describe installplan <name> -n operators

# Check operator pod logs
kubectl logs -n operators -l app.kubernetes.io/name=hyperconversion-operator
```

### Operator Not Starting

Check prerequisites:

```bash
# Verify KubeVirt is installed
kubectl get kubevirt -A

# Verify CDI is installed
kubectl get cdi -A

# Check operator logs
kubectl logs -n operators deployment/hyperconversion-operator-controller-manager
```

## Scorecard Tests

Run OLM scorecard tests:

```bash
# Run all tests
operator-sdk scorecard bundle

# Run specific suite
operator-sdk scorecard bundle --selector=suite=basic
operator-sdk scorecard bundle --selector=suite=olm

# Output in JSON
operator-sdk scorecard bundle --output=json
```

## Publishing to OperatorHub

To publish to community OperatorHub:

1. Fork https://github.com/k8s-operatorhub/community-operators
2. Add bundle under `operators/hyperconversion-operator/`
3. Create pull request
4. Pass CI checks
5. Wait for review and approval

For Red Hat Certified Operators:

1. Apply for Red Hat Partner Program
2. Submit to https://github.com/redhat-openshift-ecosystem/certified-operators
3. Pass certification tests
4. Commercial support required

## Bundle Metadata

Key fields in ClusterServiceVersion:

```yaml
metadata:
  name: hyperconversion-operator.v1.2.0
spec:
  displayName: HyperConversion Operator
  version: 1.2.0
  replaces: hyperconversion-operator.v1.1.0
  minKubeVersion: 1.24.0

  # Installation modes
  installModes:
  - type: AllNamespaces
    supported: true

  # Channels
  channels:
  - name: stable
  - name: alpha
  defaultChannel: stable
```

## Related Images

All container images must be declared:

```yaml
relatedImages:
- name: manager
  image: ghcr.io/ssahani/h2kvm-operator:v1.2.0
- name: kube-rbac-proxy
  image: gcr.io/kubebuilder/kube-rbac-proxy:v0.15.0
```

This enables:
- Air-gapped deployments
- Image mirroring
- Security scanning

## Best Practices

1. **Version All Resources**: Include version in all image tags
2. **Test Bundle**: Run scorecard tests before publishing
3. **Document Dependencies**: Clearly state KubeVirt/CDI requirements
4. **Multi-Arch**: Build bundles for all supported architectures
5. **Security**: Use minimal base images and security contexts
6. **Upgrade Path**: Test upgrades from previous versions
7. **Rollback**: Ensure downgrades are possible if needed

## References

- [OLM Documentation](https://olm.operatorframework.io/)
- [Operator SDK](https://sdk.operatorframework.io/)
- [OperatorHub.io](https://operatorhub.io/)
- [Bundle Format](https://olm.operatorframework.io/docs/tasks/creating-operator-bundle/)
- [Scorecard](https://sdk.operatorframework.io/docs/testing-operators/scorecard/)
