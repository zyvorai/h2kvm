# Operator and Worker Upgrade

## Scenario
Upgrading h2kvm operator, worker images, or dependencies (KubeVirt, CDI) to new versions.

**Upgrade types:**
- Patch upgrade (0.3.0 → 0.3.1): bug fixes, minimal risk
- Minor upgrade (0.3.x → 0.4.0): new features, backward compatible
- Major upgrade (0.x → 1.0): breaking changes, requires migration
- Dependency upgrades: KubeVirt, CDI, Kubernetes version

## Pre-Upgrade Planning

### 1. Review release notes
```bash
# Check changelog
cat CHANGELOG.md

# Review GitHub release notes
# https://github.com/ssahani/h2kvm/releases

# Check for breaking changes
grep -i "breaking" CHANGELOG.md
```

### 2. Identify current versions
```bash
# Operator version
kubectl get deployment hyperconversion-operator -n h2kvm-system \
  -o jsonpath='{.spec.template.spec.containers[0].image}'

# Worker version
kubectl get daemonset h2kvm-worker -n h2kvm-workers \
  -o jsonpath='{.spec.template.spec.containers[0].image}'

# KubeVirt version
kubectl get kubevirt kubevirt -n kubevirt -o yaml | grep "kubevirt.io/version"

# CDI version
kubectl get cdi cdi -o yaml | grep "cdi.kubevirt.io/version"

# CLI version (if installed)
h2kvmctl --version
```

### 3. Plan maintenance window
```bash
# Check for active migrations
kubectl get hc -A
kubectl get jobs -n h2kvm-migration | grep -v Complete

# Estimate downtime
# - Operator upgrade: 2-5 minutes (no downtime for running VMs)
# - Worker upgrade: 5-15 minutes (rolling update)
# - KubeVirt upgrade: 10-20 minutes (rolling update)
# - Total: 15-30 minutes typical
```

## Pre-Upgrade Checklist

### 1. Backup current state
```bash
# Backup operator resources
kubectl get deployment,configmap,secret,serviceaccount \
  -n h2kvm-system -o yaml > operator-backup-$(date +%Y%m%d).yaml

# Backup CRDs
kubectl get crd -o yaml | grep -A9999 "h2kvm.io" > crds-backup-$(date +%Y%m%d).yaml

# Backup HyperConversion resources
kubectl get hc -A -o yaml > hyperconversions-backup-$(date +%Y%m%d).yaml

# Collect full debug bundle
./scripts/collect-debug-bundle.sh /var/backups/h2kvm-pre-upgrade-$(date +%Y%m%d)
```

### 2. Check for active migrations
```bash
# List active HyperConversions
kubectl get hc -A | grep -vE "Ready|Succeeded"

# List running jobs
kubectl get jobs -n h2kvm-migration | grep -v Complete

# Option A: Wait for completion
kubectl get hc -A --watch

# Option B: Pause/cancel active migrations (if acceptable)
kubectl delete hc <active-migration> -n h2kvm-migration
```

### 3. Run health check
```bash
./scripts/health-check.sh

# Verify all components healthy
kubectl get pods -n h2kvm-system
kubectl get pods -n h2kvm-workers
kubectl get pods -n kubevirt
kubectl get pods -n cdi

# Check for pod restarts or errors
kubectl get events -A --field-selector type=Warning --sort-by=.lastTimestamp | tail -20
```

### 4. Verify disk space
```bash
# Check node disk space (need room for new images)
kubectl top nodes
kubectl debug node/<node-name> -it --image=ubuntu -- chroot /host df -h

# Estimate image sizes
# Operator: ~200 MB
# Worker: ~500 MB
# Total per node: ~700 MB
```

### 5. Test upgrade in non-production
```bash
# If available, test in staging/dev cluster first
# Use same procedure documented here
```

## Upgrade Procedure

### Step 1: Update CRDs (Backward Compatible)

```bash
# CRDs must be updated BEFORE operator
# New operator expects updated CRD schemas

cd /path/to/h2kvm

# Apply new CRDs
kubectl apply -f operator/config/crd/bases/h2kvm.io_hyperconversions.yaml
kubectl apply -f operator/config/crd/bases/h2kvm.io_validations.yaml

# Verify CRD versions
kubectl get crd hyperconversions.h2kvm.io -o yaml | grep "version:"
```

### Step 2: Upgrade Operator

#### Option A: Using Helm (Recommended)
```bash
# Update Helm chart values if needed
vi operator/charts/hyperconversion-operator/values.yaml
# Update: image.tag to new version

# Upgrade via Helm
helm upgrade hyperconversion-operator \
  operator/charts/hyperconversion-operator/ \
  -n h2kvm-system \
  --wait --timeout 5m

# Verify upgrade
helm list -n h2kvm-system
kubectl rollout status deployment hyperconversion-operator -n h2kvm-system
```

#### Option B: Using Kubectl (Manual)
```bash
# Build new operator image
cd operator
docker build -t h2kvm-operator:v0.4.0 -f Dockerfile .

# For k3d/k3s development cluster
k3d image import h2kvm-operator:v0.4.0 -c <cluster-name>

# Update deployment image
kubectl set image deployment/hyperconversion-operator \
  manager=h2kvm-operator:v0.4.0 \
  -n h2kvm-system

# Or edit deployment directly
kubectl edit deployment hyperconversion-operator -n h2kvm-system
# Update: spec.template.spec.containers[0].image

# Wait for rollout
kubectl rollout status deployment hyperconversion-operator -n h2kvm-system

# Verify new version
kubectl get pods -n h2kvm-system -o wide
kubectl logs -n h2kvm-system -l control-plane=controller-manager | grep "version\|starting"
```

### Step 3: Upgrade Workers (Rolling Update)

```bash
# Build new worker image
cd /path/to/h2kvm
docker build -t h2kvm:worker-v0.4.0 -f Dockerfile --target worker .

# For k3d/k3s
k3d image import h2kvm:worker-v0.4.0 -c <cluster-name>

# Update DaemonSet image
kubectl set image daemonset/h2kvm-worker \
  worker=h2kvm:worker-v0.4.0 \
  -n h2kvm-workers

# Monitor rolling update (one node at a time)
kubectl rollout status daemonset h2kvm-worker -n h2kvm-workers

# Verify all workers updated
kubectl get pods -n h2kvm-workers -o custom-columns=\
NAME:.metadata.name,\
NODE:.spec.nodeName,\
IMAGE:.spec.containers[0].image,\
STATUS:.status.phase
```

### Step 4: Update CLI (if applicable)

```bash
# Pull latest code
cd /path/to/h2kvm
git pull origin main

# Uninstall old version
pip uninstall -y h2kvm

# Install new version (editable mode for development)
pip install -e .

# Or install from PyPI (when published)
pip install --upgrade h2kvm

# Verify version
h2kvmctl --version
```

### Step 5: Verify Upgrade

```bash
# Run health check
./scripts/health-check.sh

# Check operator logs for errors
kubectl logs -n h2kvm-system -l control-plane=controller-manager --tail=50

# Test migration (dry-run)
h2kvmctl --cmd local \
  --vmdk /path/to/test.vmdk \
  --output-dir /tmp/upgrade-test \
  --dry-run

# Or test HyperConversion CR
kubectl apply -f - <<EOF
apiVersion: h2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: upgrade-test
  namespace: h2kvm-migration
spec:
  sourceVmdk: "/path/to/test.vmdk"
  outputFormat: qcow2
  dryRun: true
EOF

# Wait and check status
kubectl get hc upgrade-test -n h2kvm-migration
kubectl describe hc upgrade-test -n h2kvm-migration

# Clean up test
kubectl delete hc upgrade-test -n h2kvm-migration
```

## Upgrading Dependencies

### KubeVirt Upgrade

```bash
# Check current version
kubectl get kubevirt kubevirt -n kubevirt -o yaml | grep "kubevirt.io/version"

# Check compatibility with h2kvm
# See: operator/go.mod for tested versions

# Set target version
export KV_VERSION=v1.2.0  # or latest compatible version

# Apply operator manifest
kubectl apply -f https://github.com/kubevirt/kubevirt/releases/download/${KV_VERSION}/kubevirt-operator.yaml

# Apply CR (triggers upgrade)
kubectl apply -f https://github.com/kubevirt/kubevirt/releases/download/${KV_VERSION}/kubevirt-cr.yaml

# Wait for rollout (takes 10-20 minutes)
kubectl wait --for=condition=Available kubevirt kubevirt -n kubevirt --timeout=1200s

# Verify components
kubectl get pods -n kubevirt
kubectl get kubevirt kubevirt -n kubevirt -o yaml | grep phase
# Should show: phase: Deployed
```

### CDI Upgrade

```bash
# Check current version
kubectl get cdi cdi -o yaml | grep "cdi.kubevirt.io/version"

# Set target version
export CDI_VERSION=v1.58.0

# Apply operator manifest
kubectl apply -f https://github.com/kubevirt/containerized-data-importer/releases/download/${CDI_VERSION}/cdi-operator.yaml

# Apply CR
kubectl apply -f https://github.com/kubevirt/containerized-data-importer/releases/download/${CDI_VERSION}/cdi-cr.yaml

# Wait for deployment
kubectl wait --for=condition=Available cdi cdi --timeout=600s

# Verify
kubectl get pods -n cdi
kubectl get cdi cdi -o yaml | grep phase
```

### Kubernetes Cluster Upgrade

**Important:** Upgrade Kubernetes BEFORE h2kvm to ensure compatibility.

```bash
# For k3s (example)
curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=v1.28.0+k3s1 sh -

# For k3d (recreate cluster with new version)
k3d cluster delete <cluster-name>
k3d cluster create <cluster-name> --image rancher/k3s:v1.28.0-k3s1

# For managed Kubernetes (EKS, GKE, AKS)
# Follow cloud provider's upgrade procedure
```

## Rollback Procedure

### Scenario A: Operator Rollback

```bash
# Rollback to previous version via kubectl
kubectl rollout undo deployment hyperconversion-operator -n h2kvm-system

# Verify rollback
kubectl rollout status deployment hyperconversion-operator -n h2kvm-system

# Or restore from backup
kubectl apply -f operator-backup-<date>.yaml

# Verify
./scripts/health-check.sh
```

### Scenario B: Worker Rollback

```bash
# Rollback DaemonSet
kubectl rollout undo daemonset h2kvm-worker -n h2kvm-workers

# Monitor rollback
kubectl rollout status daemonset h2kvm-worker -n h2kvm-workers
```

### Scenario C: CRD Rollback

**Warning:** CRD rollback can cause issues if new fields are in use.

```bash
# Restore old CRDs from backup
kubectl apply -f crds-backup-<date>.yaml

# Delete HyperConversions using new fields (if any)
kubectl delete hc <name-with-new-fields> -n h2kvm-migration

# Rollback operator to match old CRD version
kubectl rollout undo deployment hyperconversion-operator -n h2kvm-system
```

### Scenario D: Full Rollback (All Components)

```bash
# 1. Delete new HyperConversions (incompatible with old version)
kubectl delete hc --all -n h2kvm-migration

# 2. Rollback CRDs
kubectl apply -f crds-backup-<date>.yaml

# 3. Rollback operator
kubectl rollout undo deployment hyperconversion-operator -n h2kvm-system

# 4. Rollback workers
kubectl rollout undo daemonset h2kvm-worker -n h2kvm-workers

# 5. Verify all components back to old versions
kubectl get deployment hyperconversion-operator -n h2kvm-system \
  -o jsonpath='{.spec.template.spec.containers[0].image}'

# 6. Run health check
./scripts/health-check.sh
```

## Post-Upgrade Tasks

### 1. Monitor for Issues
```bash
# Watch operator logs for errors
kubectl logs -n h2kvm-system -l control-plane=controller-manager --follow

# Monitor pod restarts
kubectl get events -A --watch --field-selector type=Warning

# Check for CrashLoopBackOff
kubectl get pods -A | grep -E "Error|CrashLoop|ImagePull"
```

### 2. Run Test Migration
```bash
# Test full migration workflow
h2kvmctl --cmd local \
  --vmdk /path/to/test-vm.vmdk \
  --output-dir /tmp/post-upgrade-test \
  --output-format qcow2 \
  --fstab-mode stabilize-all \
  --regen-initramfs

# Or test via HyperConversion CR
kubectl apply -f operator/config/samples/migration-test.yaml
kubectl get hc -A --watch
```

### 3. Update Documentation
```bash
# Update version in README
vi README.md

# Commit changes
git add README.md
git commit -m "docs: update to version 0.4.0"
```

### 4. Clean Up Old Images (Optional)
```bash
# List old images
docker images | grep h2kvm

# Remove old tags
docker rmi h2kvm-operator:v0.3.0
docker rmi h2kvm:worker-v0.3.0

# Or prune all unused images
docker image prune -a -f
```

## Prevention / Best Practices

### Version Pinning
```yaml
# Pin versions in Helm values.yaml
image:
  repository: h2kvm-operator
  tag: "v0.4.0"  # explicit version, not "latest"
  pullPolicy: IfNotPresent
```

### Canary Deployments
```bash
# Deploy new version to subset of nodes first
kubectl label nodes worker-1 h2kvm-canary=true

# Update DaemonSet with nodeSelector
kubectl patch daemonset h2kvm-worker -n h2kvm-workers -p '
spec:
  template:
    spec:
      nodeSelector:
        h2kvm-canary: "true"
'

# Run test migrations on canary nodes
# If successful, remove nodeSelector and rollout to all nodes
```

### Automated Testing
```bash
# Run test suite before upgrade
cd /path/to/h2kvm
python3 -m pytest tests/unit/ -x -q
cd zkvm && go test ./...

# Integration test
./scripts/run-demo.sh  # ensure full workflow works
```

### Monitoring and Alerting
```yaml
# Prometheus alerts for upgrade issues
groups:
- name: h2kvm-upgrade
  rules:
  - alert: OperatorCrashLoop
    expr: rate(kube_pod_container_status_restarts_total{namespace="h2kvm-system"}[5m]) > 0
    annotations:
      summary: "Operator pod restarting after upgrade"

  - alert: WorkerImagePullFail
    expr: kube_pod_container_status_waiting_reason{namespace="h2kvm-workers",reason="ImagePullBackOff"} > 0
    annotations:
      summary: "Worker pods failing to pull new image"
```

## Escalation Path

**Escalate if:**
- Upgrade fails and rollback also fails
- Data loss in existing HyperConversions
- Cluster-wide issues after upgrade (multiple components down)
- New version incompatible with Kubernetes version

**Escalation steps:**
1. Collect debug bundle: `./scripts/collect-debug-bundle.sh`
2. Save upgrade timeline and steps taken
3. Document current state vs expected state
4. Check GitHub issues: https://github.com/ssahani/h2kvm/issues
5. Contact platform team or file GitHub issue with:
   - Old version → new version
   - Kubernetes version
   - Error logs from operator/workers
   - Steps to reproduce

## Version Compatibility Matrix

| h2kvm | KubeVirt | CDI | Kubernetes | Notes |
|-----------|----------|-----|------------|-------|
| 0.3.x | v1.0.0+ | v1.57.0+ | 1.25-1.28 | Current stable |
| 0.4.x | v1.2.0+ | v1.58.0+ | 1.26-1.29 | Latest features |

**Always check:**
- `operator/go.mod` for tested dependency versions
- Release notes for specific compatibility requirements
