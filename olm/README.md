# H2KVM Operator - OLM Bundle

This directory contains the Operator Lifecycle Manager (OLM) bundle for deploying h2kvm-operator on OpenShift via OperatorHub.

## Directory Structure

```
olm/
├── bundle/                          # OLM bundle
│   ├── manifests/                   # Manifests directory
│   │   ├── h2kvm-operator.clusterserviceversion.yaml  # CSV
│   │   ├── migrationjob.yaml        # MigrationJob CRD
│   │   └── jobtemplate.yaml         # JobTemplate CRD
│   ├── metadata/                    # Bundle metadata
│   │   └── annotations.yaml         # Bundle annotations
│   └── tests/                       # Scorecard tests
│       └── scorecard/
│           └── config.yaml
├── bundle.Dockerfile                # Bundle image Dockerfile
├── h2kvm-operator.package.yaml  # Package manifest
└── README.md                        # This file
```

## Building the Bundle Image

```bash
# Build bundle image
docker build -f olm/bundle.Dockerfile -t ghcr.io/ssahani/h2kvm-operator-bundle:v2.0.0 olm/

# Push to registry
docker push ghcr.io/ssahani/h2kvm-operator-bundle:v2.0.0
```

## Validating the Bundle

```bash
# Install operator-sdk (if not already installed)
# https://sdk.operatorframework.io/docs/installation/

# Validate bundle
operator-sdk bundle validate olm/bundle --select-optional suite=operatorframework

# Run scorecard tests
operator-sdk scorecard olm/bundle
```

## Installing on OpenShift

### Method 1: Via OperatorHub (Recommended for Production)

1. **Build and push catalog image**:

```bash
# Create catalog using opm
opm index add \
  --bundles ghcr.io/ssahani/h2kvm-operator-bundle:v2.0.0 \
  --tag ghcr.io/ssahani/h2kvm-operator-catalog:latest \
  --container-tool docker

# Push catalog
docker push ghcr.io/ssahani/h2kvm-operator-catalog:latest
```

2. **Create CatalogSource**:

```yaml
apiVersion: operators.coreos.com/v1alpha1
kind: CatalogSource
metadata:
  name: h2kvm-catalog
  namespace: openshift-marketplace
spec:
  sourceType: grpc
  image: ghcr.io/ssahani/h2kvm-operator-catalog:latest
  displayName: H2KVM Operators
  publisher: H2KVM Project
  updateStrategy:
    registryPoll:
      interval: 30m
```

3. **Install from OperatorHub UI**:
   - Navigate to **OperatorHub** in OpenShift Console
   - Search for "H2KVM"
   - Click **Install**
   - Select installation mode (namespace or all namespaces)
   - Choose update channel (stable or preview)
   - Click **Install**

### Method 2: Direct Bundle Install (Testing/Development)

```bash
# Install operator-sdk
curl -LO https://github.com/operator-framework/operator-sdk/releases/latest/download/operator-sdk_linux_amd64
chmod +x operator-sdk_linux_amd64
sudo mv operator-sdk_linux_amd64 /usr/local/bin/operator-sdk

# Run bundle directly
operator-sdk run bundle ghcr.io/ssahani/h2kvm-operator-bundle:v2.0.0 \
  --namespace h2kvm-system

# Cleanup
operator-sdk cleanup h2kvm-operator --namespace h2kvm-system
```

### Method 3: Manual Subscription

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: h2kvm-system
---
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: h2kvm-operatorgroup
  namespace: h2kvm-system
spec:
  targetNamespaces:
    - h2kvm-system
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: h2kvm-operator
  namespace: h2kvm-system
spec:
  channel: stable
  name: h2kvm-operator
  source: h2kvm-catalog
  sourceNamespace: openshift-marketplace
  installPlanApproval: Automatic
```

## Upgrade Strategy

The operator supports seamless upgrades:

- **Automatic**: OLM automatically upgrades to the latest version in the channel
- **Manual**: Requires approval before upgrading
- **Skip Range**: Can upgrade from any 1.x version to 2.0.0

## Channels

- **stable**: Production-ready releases (recommended)
- **preview**: Preview releases with new features

## Compatibility

- **OpenShift**: 4.10 - 4.16
- **Kubernetes**: 1.24+ (via generic OLM installation)

## Disconnected/Air-Gapped Environments

The bundle supports disconnected environments:

1. Mirror images to internal registry:

```bash
# Mirror operator images
oc image mirror \
  ghcr.io/ssahani/h2kvm:2.0.0-operator=internal-registry.example.com/h2kvm/operator:2.0.0 \
  ghcr.io/ssahani/h2kvm:2.0.0-worker=internal-registry.example.com/h2kvm/worker:2.0.0 \
  ghcr.io/ssahani/h2kvm-operator-bundle:v2.0.0=internal-registry.example.com/h2kvm/bundle:v2.0.0
```

2. Create ImageContentSourcePolicy:

```yaml
apiVersion: operator.openshift.io/v1alpha1
kind: ImageContentSourcePolicy
metadata:
  name: h2kvm-mirror
spec:
  repositoryDigestMirrors:
    - mirrors:
        - internal-registry.example.com/h2kvm
      source: ghcr.io/ssahani
```

## Uninstalling

### Via OperatorHub UI

1. Navigate to **Installed Operators**
2. Find **H2KVM Operator**
3. Click **Uninstall**

### Via CLI

```bash
# Delete subscription
oc delete subscription h2kvm-operator -n h2kvm-system

# Delete CSV
oc delete csv h2kvm-operator.v2.0.0 -n h2kvm-system

# Delete CRDs (optional - this deletes all MigrationJobs!)
oc delete crd migrationjobs.h2kvm.io
oc delete crd jobtemplates.h2kvm.io
```

## Troubleshooting

### Check operator status

```bash
# Check subscription
oc get subscription h2kvm-operator -n h2kvm-system -o yaml

# Check install plan
oc get installplan -n h2kvm-system

# Check CSV
oc get csv -n h2kvm-system

# Check operator pod
oc get pods -n h2kvm-system -l app.kubernetes.io/name=h2kvm-operator
```

### View operator logs

```bash
oc logs -n h2kvm-system -l app.kubernetes.io/name=h2kvm-operator -f
```

### Common issues

1. **Bundle validation errors**: Run `operator-sdk bundle validate olm/bundle`
2. **Image pull errors**: Ensure bundle image is accessible from cluster
3. **Permission errors**: Check ClusterRole bindings and ServiceAccount

## Resources

- [Operator SDK Documentation](https://sdk.operatorframework.io/docs/)
- [OLM Documentation](https://olm.operatorframework.io/)
- [OpenShift Operators](https://docs.openshift.com/container-platform/latest/operators/index.html)
- [H2KVM Documentation](https://github.com/ssahani/h2kvm/tree/main/docs)
