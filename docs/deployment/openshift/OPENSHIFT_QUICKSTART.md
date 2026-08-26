# OpenShift Quick Start Guide

**Get h2kvm operator running on OpenShift in 5 minutes!**

---

## Prerequisites

- OpenShift cluster (4.10-4.16)
- `oc` CLI installed and logged in
- `cluster-admin` role (for installation)

---

## Option 1: One-Click OperatorHub Installation (Recommended) 🚀

### Step 1: Access OperatorHub

1. Log in to OpenShift Console
2. Navigate to **Operators** → **OperatorHub**
3. Search for **"H2KVM"**

### Step 2: Install

1. Click **H2KVM Operator**
2. Click **Install**
3. Configure:
   - **Update Channel**: `stable`
   - **Installation Mode**: `A specific namespace`
   - **Installed Namespace**: `h2kvm-system`
   - **Update Approval**: `Automatic`
4. Click **Install**

### Step 3: Verify

```bash
# Check installation
oc get csv -n h2kvm-system

# Check operator pod
oc get pods -n h2kvm-system
```

### Step 4: Create Your First Job

```bash
oc apply -f - <<EOF
apiVersion: h2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: my-first-migration
  namespace: h2kvm-system
spec:
  operation: inspect
  image:
    path: /data/input/vm-disk.vmdk
    format: vmdk
  artifacts:
    output_path: /data/output
EOF
```

**Done!** 🎉

---

## Option 2: Helm Installation (For Advanced Users)

### Step 1: Install via Helm

```bash
# Login to OpenShift
oc login <cluster-url>

# Add Helm repo
helm repo add h2kvm https://ssahani.github.io/h2kvm
helm repo update

# Install operator
helm install h2kvm-operator h2kvm/h2kvm-operator \
  --namespace h2kvm-system \
  --create-namespace \
  --set openshift.enabled=true \
  --set openshift.route.enabled=true \
  --set openshift.oauth.enabled=true
```

### Step 2: Verify

```bash
# Check all resources
oc get all -n h2kvm-system

# Check routes
oc get routes -n h2kvm-system
```

---

## Option 3: Build and Deploy from Source

### Step 1: Clone Repository

```bash
git clone https://github.com/ssahani/h2kvm.git
cd h2kvm
```

### Step 2: Build Images

```bash
# Build operator and worker images
./scripts/build-operator-images.sh 2.1.0

# Build OLM bundle
./scripts/build-olm-bundle.sh 2.1.0
```

### Step 3: Deploy to OpenShift

```bash
# Login to OpenShift
oc login <cluster-url>

# Deploy via Helm
./scripts/deploy-to-openshift.sh 2.1.0 helm

# OR deploy via OLM
./scripts/deploy-to-openshift.sh 2.1.0 olm
```

### Step 4: Test Deployment

```bash
./scripts/test-openshift-deployment.sh h2kvm-system
```

---

## Accessing the Operator

### Metrics Endpoint

```bash
# Get metrics route
METRICS_ROUTE=$(oc get route h2kvm-operator-metrics -n h2kvm-system -o jsonpath='{.spec.host}')

# Access with OpenShift OAuth token
curl -k -H "Authorization: Bearer $(oc whoami -t)" https://$METRICS_ROUTE/metrics
```

### Operator Logs

```bash
oc logs -n h2kvm-system -l app.kubernetes.io/name=h2kvm-operator -f
```

### Web Console

Navigate to: **Workloads** → **MigrationJobs**

---

## Creating Migration Jobs

### Example 1: Inspect VMDK

```bash
oc apply -f - <<EOF
apiVersion: h2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: inspect-vmdk
  namespace: default
spec:
  operation: inspect
  image:
    path: /data/vm-disk.vmdk
    format: vmdk
  priority: 50
EOF
```

### Example 2: Convert VMDK to QCOW2

```bash
oc apply -f - <<EOF
apiVersion: h2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: convert-vmdk
  namespace: default
spec:
  operation: convert
  image:
    path: /data/vm-disk.vmdk
    format: vmdk
    checksum: sha256:abc123...
  artifacts:
    output_path: /data/output
    output_format: qcow2
    compress: true
  priority: 75
  timeout: 2h
EOF
```

### Example 3: Offline Windows Fix

```bash
oc apply -f - <<EOF
apiVersion: h2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: fix-windows-vm
  namespace: default
spec:
  operation: offline_fix
  image:
    path: /data/windows-server.vmdk
    format: vmdk
  parameters:
    inject_virtio: true
    fix_network: true
  artifacts:
    output_path: /data/output
    output_format: qcow2
  priority: 100
EOF
```

### Watch Job Progress

```bash
# Watch all jobs
oc get migrationjobs --watch

# Get job details
oc describe migrationjob <job-name>

# Check job logs
oc logs -n h2kvm-workers -l job-name=<job-name>
```

---

## Advanced Configuration

### Enable HA (High Availability)

```bash
helm upgrade h2kvm-operator h2kvm/h2kvm-operator \
  --namespace h2kvm-system \
  --set operator.replicaCount=3 \
  --set operator.leaderElection.enabled=true \
  --set webhook.replicaCount=2
```

### Custom Routes

```bash
helm upgrade h2kvm-operator h2kvm/h2kvm-operator \
  --namespace h2kvm-system \
  --set openshift.route.host=h2kvm.apps.example.com \
  --set openshift.route.tls.termination=edge
```

### Air-Gapped Deployment

```bash
# Mirror images to internal registry
oc image mirror \
  ghcr.io/ssahani/h2kvm:2.1.0-operator=internal-registry.example.com/h2kvm/operator:2.1.0 \
  ghcr.io/ssahani/h2kvm:2.1.0-worker=internal-registry.example.com/h2kvm/worker:2.1.0

# Create ImageContentSourcePolicy
oc apply -f - <<EOF
apiVersion: operator.openshift.io/v1alpha1
kind: ImageContentSourcePolicy
metadata:
  name: h2kvm-mirror
spec:
  repositoryDigestMirrors:
    - mirrors:
        - internal-registry.example.com/h2kvm
      source: ghcr.io/ssahani
EOF

# Deploy with custom registry
helm install h2kvm-operator h2kvm/h2kvm-operator \
  --namespace h2kvm-system \
  --set operator.image.repository=internal-registry.example.com/h2kvm/operator \
  --set worker.image.repository=internal-registry.example.com/h2kvm/worker
```

---

## Troubleshooting

### Operator Pod Not Starting

```bash
# Check pod status
oc describe pod -n h2kvm-system -l app.kubernetes.io/name=h2kvm-operator

# Check logs
oc logs -n h2kvm-system -l app.kubernetes.io/name=h2kvm-operator

# Check events
oc get events -n h2kvm-system --sort-by='.lastTimestamp'
```

### Worker Pods Failing

```bash
# Check SCC assignment
oc get pod <worker-pod> -o yaml | grep openshift.io/scc

# Grant SCC manually
oc adm policy add-scc-to-user h2kvm-worker-scc \
  -z h2kvm-worker \
  -n h2kvm-workers
```

### Route Not Accessible

```bash
# Check route
oc get route -n h2kvm-system

# Check route status
oc describe route h2kvm-operator-metrics -n h2kvm-system

# Recreate route
oc delete route h2kvm-operator-metrics -n h2kvm-system
oc apply -f helm/h2kvm-operator/templates/openshift-route.yaml
```

---

## Uninstallation

### Via OperatorHub

1. Navigate to **Operators** → **Installed Operators**
2. Find **H2KVM Operator**
3. Click **Actions** → **Uninstall Operator**

### Via Helm

```bash
helm uninstall h2kvm-operator -n h2kvm-system
oc delete project h2kvm-system
```

### Cleanup CRDs (Optional)

```bash
# WARNING: This deletes all MigrationJobs!
oc delete crd migrationjobs.h2kvm.io
oc delete crd jobtemplates.h2kvm.io
```

---

## Next Steps

- **[Full Documentation](docs/deployment/openshift-deployment-guide.md)** - Complete deployment guide
- **[OLM Bundle Guide](olm/README.md)** - OperatorHub publishing
- **[Feature Summary](docs/deployment/OPENSHIFT_FEATURES_SUMMARY.md)** - All OpenShift features
- **[GitHub Repository](https://github.com/ssahani/h2kvm)** - Source code and issues

---

**Need Help?**

- GitHub Issues: https://github.com/ssahani/h2kvm/issues
- Documentation: https://github.com/ssahani/h2kvm/tree/main/docs
