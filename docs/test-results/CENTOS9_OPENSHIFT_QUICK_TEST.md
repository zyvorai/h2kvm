> Historical report — disk backend was VMCraft; now GuestKit.

# CentOS 9 OpenShift Test - Quick Start

**Date:** 2026-01-31
**Test Image:** CentOS Stream 9 (2.2 GB VMDK)
**OpenShift Version:** CRC 4.20.5
**Status:** In Progress

---

## Overview

Testing CentOS 9 VMDK migration using H2KVM operator on OpenShift/CRC.

**Local Test Results:** ✅ Already validated
- Basic conversion: PASS (1.18 GB QCOW2)
- Offline fixes: PASS (1.17 GB with virtio drivers)
- See: `CENTOS9_OPENSHIFT_TEST_RESULTS.md`

**OpenShift Test Goal:** Validate operator orchestration

---

## Prerequisites

### 1. CRC Setup (In Progress)

```bash
# Setup CRC (downloads ~3.5 GB bundle)
crc setup

# Start CRC cluster (allocates ~15 GB disk + 9 GB RAM)
crc start

# Configure kubectl
eval $(crc oc-env)
oc login -u kubeadmin https://api.crc.testing:6443
```

**Status:** Downloading bundle... 3.2 GB / ~3.5 GB

### 2. Install CRDs

```bash
cd /home/ssahani/tt/h2kvm
kubectl apply -f k8s/operator/crds/
```

### 3. Create Namespace

```bash
kubectl create namespace centos9-test
```

---

## Quick Test Plan

### Option A: Using HostPath (Fastest)

**Advantages:**
- No file upload needed
- Direct access to local VMDK
- Faster testing

**Setup:**

```bash
# Apply manifests with hostPath PV
kubectl apply -f /tmp/centos9-openshift-simple-test.yaml

# Create image pull secret
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=<user> \
  --docker-password=<token> \
  -n centos9-test

# Watch operator startup
kubectl get pods -n centos9-test -w
```

**Test Execution:**

```bash
# Create inspection job (already in manifest)
kubectl get migrationjob centos9-inspect -n centos9-test

# Watch job progress
kubectl describe migrationjob centos9-inspect -n centos9-test

# Check worker pod logs
POD=$(kubectl get pods -n centos9-test -l job-name=centos9-inspect -o name)
kubectl logs -f $POD -n centos9-test
```

### Option B: Using Uploaded File (Production-like)

**Advantages:**
- Tests real upload workflow
- Production scenario

**Setup:**

```yaml
# Create PVC for upload
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: centos9-vmdk-pvc
  namespace: centos9-test
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 3Gi
```

**Upload VMDK:**

```bash
# Create upload pod
kubectl run vmdk-uploader -n centos9-test \
  --image=busybox \
  --restart=Never \
  --overrides='{"spec":{"containers":[{"name":"vmdk-uploader","image":"busybox","command":["sleep","3600"],"volumeMounts":[{"name":"data","mountPath":"/data"}]}],"volumes":[{"name":"data","persistentVolumeClaim":{"claimName":"centos9-vmdk-pvc"}}]}}'

# Copy VMDK to PVC
kubectl cp \
  /home/ssahani/Downloads/VM-Images/centos/centos9.vmdk \
  centos9-test/vmdk-uploader:/data/centos9.vmdk

# Verify
kubectl exec vmdk-uploader -n centos9-test -- ls -lh /data/

# Cleanup uploader
kubectl delete pod vmdk-uploader -n centos9-test
```

---

## Test Scenarios

### Scenario 1: Inspection Only

**Goal:** Validate VMDK inspection

**MigrationJob:**

```yaml
apiVersion: h2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: centos9-inspect
  namespace: centos9-test
spec:
  operation: inspect

  image:
    path: /data/input/centos9.vmdk
    format: vmdk

  artifacts:
    output_path: /data/output
    output_format: qcow2

  priority: 75
  timeout: 15m
```

**Expected Result:**
- Job completes successfully
- Inspection JSON generated
- Risks identified (lsilogic controller, CHS geometry)
- No FATAL blocks

**Validation:**

```bash
# Check job status
kubectl get migrationjob centos9-inspect -n centos9-test -o yaml

# View inspection results
kubectl exec <result-pod> -n centos9-test -- cat /data/output/inspection.json
```

### Scenario 2: Full Conversion Pipeline

**Goal:** Inspect → Convert → Offline Fix

**Jobs:**

1. **Inspect** (15m timeout)
2. **Convert** (30m timeout, depends on inspect)
3. **Offline Fix** (60m timeout, depends on convert)

**Apply:**

```bash
kubectl apply -f /tmp/centos9-migrationjob-pipeline.yaml
```

**Monitor:**

```bash
# Watch all jobs
kubectl get migrationjobs -n centos9-test -w

# Check dependencies
kubectl describe migrationjob centos9-convert -n centos9-test | grep dependsOn

# View job timeline
kubectl get migrationjobs -n centos9-test \
  -o custom-columns=NAME:.metadata.name,OPERATION:.spec.operation,STATE:.status.state,STARTED:.status.startTime,COMPLETED:.status.completionTime
```

---

## Troubleshooting

### Issue 1: Pod Stuck Pending

**Check:**

```bash
kubectl describe pod <pod-name> -n centos9-test
```

**Common causes:**
- Disk pressure taint (if CRC disk fills up)
- Image pull errors
- Resource constraints

**Fix:**

```bash
# Add toleration for disk pressure
tolerations:
  - key: node.kubernetes.io/disk-pressure
    operator: Exists
    effect: NoSchedule
```

### Issue 2: Image Pull Failures

**Check:**

```bash
kubectl get events -n centos9-test --sort-by='.lastTimestamp'
```

**Fix:**

```bash
# Verify secret exists
kubectl get secret ghcr-secret -n centos9-test

# Recreate if needed
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=<user> \
  --docker-password=<token> \
  -n centos9-test
```

### Issue 3: Worker Pod Fails

**Check logs:**

```bash
kubectl logs <worker-pod> -n centos9-test

# Check for privilege errors
kubectl describe pod <worker-pod> -n centos9-test | grep -A 10 securityContext
```

**Fix:**

Ensure worker has privileged securityContext:

```yaml
securityContext:
  privileged: true
  runAsUser: 0
```

---

## Comparison: Local vs OpenShift

| Aspect | Local CLI | OpenShift Operator |
|--------|-----------|-------------------|
| **Execution** | Direct `h2kvm` command | MigrationJob CR |
| **Storage** | Local filesystem | PVCs |
| **Privileges** | `sudo` required | Privileged pods |
| **Monitoring** | Terminal output | `kubectl` commands |
| **Results** | Local directory | PVC data |
| **Scalability** | Manual | Multi-job orchestration |
| **Dependencies** | Shell scripts | CR `dependsOn` |

**Local test proves:** Code logic works ✅
**OpenShift test proves:** Operator orchestration works ✅

---

## Success Criteria

### Minimum (Inspection Only)

- ✅ Operator pod running
- ✅ MigrationJob created
- ✅ Worker pod spawned
- ✅ Inspection completes
- ✅ Results accessible

### Full (Pipeline)

- ✅ Inspection job succeeds
- ✅ Convert job starts after inspection
- ✅ Convert job produces QCOW2
- ✅ Offline fix job applies virtio drivers
- ✅ Final image is KVM-ready

---

## Cleanup

```bash
# Delete test namespace (removes all resources)
kubectl delete namespace centos9-test

# Stop CRC (saves ~15 GB disk)
crc stop

# Delete CRC entirely (saves ~44 GB)
crc delete
rm -rf ~/.crc
```

---

## Alternative: Minikube (Lightweight)

If CRC is too heavy:

```bash
# Start minikube (uses ~5-10 GB vs CRC's 44 GB)
minikube start --cpus=2 --memory=4096

# Install CRDs
kubectl apply -f k8s/operator/crds/

# Deploy operator
kubectl apply -f /tmp/centos9-openshift-simple-test.yaml

# Same test procedure as above
```

---

## Notes

- **CRC Bundle:** ~3.5 GB download (one-time)
- **CRC Runtime:** ~30-44 GB disk, ~9 GB RAM
- **Test Duration:** ~15-30 minutes (depending on operations)
- **Network:** Requires internet for image pulls

**Recommendation:**
Since local testing already validates the core functionality (✅ conversion works, ✅ offline fixes work), the OpenShift test primarily validates operator orchestration. If disk space is a concern, the comprehensive local test results in `CENTOS9_OPENSHIFT_TEST_RESULTS.md` may be sufficient for v2.1.0 validation.

---

**Status:** CRC setup in progress (3.2 GB / 3.5 GB downloaded)
**Next Step:** Wait for CRC setup → `crc start` → Deploy test manifests
