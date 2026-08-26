# OpenShift Photon VMDK Test Plan

**Date:** 2026-01-31
**Cluster:** CodeReady Containers (CRC) OpenShift 4.20.5
**Operator Version:** v0.3.1
**Test Image:** photon.vmdk (974MB)

---

## Environment Status

### CRC Cluster
```
CRC VM:          Running
OpenShift:       v4.20.5
RAM Usage:       3.519GB of 10.95GB
Disk Usage:      24.84GB of 32.68GB (76% full)
Status:          ⚠️ Disk Pressure (blocking pod scheduling)
```

### Current Deployment Status

**CRDs Installed:**
- ✅ `migrationjobs.h2kvm.io`
- ✅ `jobtemplates.h2kvm.io`

**RBAC Configured:**
- ✅ ClusterRole: `h2kvm-operator`
- ✅ ClusterRoleBinding: `h2kvm-operator`
- ✅ ServiceAccount: `h2kvm-operator` (namespace: h2kvm-test)

**Operator Deployment:**
- ⚠️ **Status:** Pending (blocked by disk pressure)
- **Image:** `ghcr.io/ssahani/h2kvm:2.1.0-operator`
- **Namespace:** `h2kvm-test`
- **Issue:** `0/1 nodes available: 1 node(s) had untolerated taint {node.kubernetes.io/disk-pressure}`

---

## Test Plan

### Test Case 1: Inspect Photon VMDK

**Objective:** Validate VMDK inspection capabilities

**MigrationJob Manifest:**
```yaml
apiVersion: h2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: photon-inspect
  namespace: h2kvm-test
spec:
  operation: inspect
  image:
    path: /data/photon.vmdk
    format: vmdk
    checksum: sha256:auto
  artifacts:
    output_path: /data/output
    output_format: json
  priority: 75
  timeout: 30m
  retryPolicy:
    maxRetries: 2
    backoff: exponential
```

**Expected Output:**
```json
{
  "disk_info": {
    "format": "VMDK",
    "virtual_size": "974MB",
    "disk_size": "974MB",
    "cluster_size": "512"
  },
  "partitions": [...],
  "bootloader": "GRUB2",
  "os_type": "Linux",
  "risks": []
}
```

### Test Case 2: Convert Photon VMDK to QCOW2

**Objective:** Convert VMDK to QCOW2 format for KVM

**MigrationJob Manifest:**
```yaml
apiVersion: h2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: photon-convert
  namespace: h2kvm-test
spec:
  operation: convert
  image:
    path: /data/photon.vmdk
    format: vmdk
  artifacts:
    output_path: /data/output
    output_format: qcow2
    compress: true
  priority: 80
  timeout: 1h
  retryPolicy:
    maxRetries: 3
    backoff: exponential
```

**Expected Artifacts:**
- `photon.qcow2` - Converted QCOW2 image
- `photon-conversion-report.json` - Conversion metadata

### Test Case 3: Offline Fix for Photon (If Needed)

**Objective:** Apply offline fixes for KVM boot

**MigrationJob Manifest:**
```yaml
apiVersion: h2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: photon-offline-fix
  namespace: h2kvm-test
spec:
  operation: offline_fix
  image:
    path: /data/photon.vmdk
    format: vmdk
  artifacts:
    output_path: /data/output
    output_format: qcow2
  fixes:
    - fstab_stabilization
    - grub_regeneration
    - initramfs_rebuild
  priority: 90
  timeout: 2h
  retryPolicy:
    maxRetries: 3
    backoff: exponential
```

**Expected Fixes:**
- fstab UUID conversion
- GRUB bootloader configuration for KVM
- initramfs regeneration with virtio drivers
- Network interface configuration

---

## Deployment Instructions

### Option 1: Manual Manifest Deployment (Recommended for Testing)

```bash
# Set kubeconfig
export KUBECONFIG=$HOME/.crc/machines/crc/kubeconfig

# Apply CRDs
kubectl apply -f k8s/operator/crds/

# Deploy operator (when disk space available)
kubectl apply -f /tmp/simple-operator-deploy.yaml

# Wait for operator to be ready
kubectl wait --for=condition=ready pod \
  -l app=h2kvm-operator \
  -n h2kvm-test \
  --timeout=5m

# Create test migration job
kubectl apply -f - <<EOF
apiVersion: h2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: photon-inspect
  namespace: h2kvm-test
spec:
  operation: inspect
  image:
    path: /data/photon.vmdk
    format: vmdk
  artifacts:
    output_path: /data/output
    output_format: json
  priority: 75
  timeout: 30m
EOF

# Monitor job
kubectl get migrationjob photon-inspect -n h2kvm-test -w
kubectl describe migrationjob photon-inspect -n h2kvm-test
```

### Option 2: Helm Deployment (Production)

```bash
export KUBECONFIG=$HOME/.crc/machines/crc/kubeconfig

# Install operator with Helm
helm install h2kvm-operator ./helm/h2kvm-operator \
  --namespace h2kvm-test \
  --create-namespace \
  --set openshift.enabled=true \
  --set webhook.enabled=false \
  --set image.tag=2.1.0-operator \
  --wait

# Apply test job
kubectl apply -f k8s/operator/examples/inspect-job.yaml
```

---

## Troubleshooting

### Issue 1: Disk Pressure Prevents Pod Scheduling

**Symptom:**
```
Warning  FailedScheduling  0/1 nodes available: 1 node(s) had untolerated taint {node.kubernetes.io/disk-pressure}
```

**Solutions:**

**A. Free Disk Space in CRC:**
```bash
# SSH into CRC VM
crc ssh

# Clean up unused containers and images
sudo podman system prune -a --force

# Check disk usage
df -h

# Exit CRC
exit

# Restart CRC
crc stop
crc start
```

**B. Fresh CRC Installation:**
```bash
# Delete and recreate CRC
crc delete
crc setup
crc start

# Redeploy operator
kubectl apply -f /tmp/simple-operator-deploy.yaml
```

**C. Use Real OpenShift Cluster:**
Deploy to a production OpenShift cluster with adequate resources (40GB+ disk per node).

### Issue 2: Image Pull Failures

**Symptom:**
```
Failed to pull image "ghcr.io/ssahani/h2kvm:2.1.0-operator"
```

**Solution:**
```bash
# Verify images are public
# Visit: https://github.com/ssahani?tab=packages

# Or load image locally
docker pull ghcr.io/ssahani/h2kvm:2.1.0-operator
crc podman load -i <(docker save ghcr.io/ssahani/h2kvm:2.1.0-operator)
```

### Issue 3: SecurityContextConstraints Violations

**Symptom:**
```
unable to validate against any security context constraint
```

**Solution:**
```bash
# Apply SCC
kubectl apply -f - <<EOF
apiVersion: security.openshift.io/v1
kind: SecurityContextConstraints
metadata:
  name: h2kvm-operator-scc
allowPrivilegedContainer: false
allowHostNetwork: false
allowHostPorts: false
allowHostPID: false
allowHostIPC: false
requiredDropCapabilities:
  - ALL
runAsUser:
  type: MustRunAsRange
fsGroup:
  type: MustRunAs
seLinuxContext:
  type: MustRunAs
readOnlyRootFilesystem: true
volumes:
  - configMap
  - downwardAPI
  - emptyDir
  - secret
users:
  - system:serviceaccount:h2kvm-test:h2kvm-operator
EOF
```

---

## Local Testing Alternative

While resolving cluster issues, test locally with CLI:

```bash
# Inspect photon.vmdk
h2kvmctl inspect /home/ssahani/tt/h2kvm/photon.vmdk \
  --output-format json > photon-inspection.json

# Convert to QCOW2
h2kvmctl convert \
  --vmdk /home/ssahani/tt/h2kvm/photon.vmdk \
  --output-dir /tmp/photon-output \
  --to-output photon.qcow2 \
  --out-format qcow2

# Apply offline fixes
h2kvmctl offline-fix \
  --vmdk /home/ssahani/tt/h2kvm/photon.vmdk \
  --output-dir /tmp/photon-fixed \
  --to-output photon-fixed.qcow2 \
  --fstab-mode stabilize-all \
  --regenerate-grub \
  --rebuild-initramfs
```

---

## Success Criteria

**Operator Deployment:**
- ✅ Operator pod running (STATUS: Running)
- ✅ No CrashLoopBackOff errors
- ✅ Operator logs showing "Started operator" message
- ✅ CRDs accessible and validating

**Migration Job Execution:**
- ✅ MigrationJob created successfully
- ✅ Job status transitions: Pending → Running → Completed
- ✅ Output artifacts generated
- ✅ No errors in job status conditions

**Output Validation:**
- ✅ Inspection JSON contains disk_info, partitions, bootloader
- ✅ Converted QCOW2 file exists and is valid
- ✅ Fixed image boots successfully in KVM/QEMU

---

## Current Status

**As of 2026-01-31 00:15 UTC:**

✅ **Completed:**
- Container images built and pushed to ghcr.io
- CRDs installed on OpenShift
- RBAC configured
- Operator deployment manifest created
- Test manifests prepared

⚠️ **Blocked:**
- Operator pod scheduling (disk pressure on CRC node)
- End-to-end OpenShift testing

📋 **Next Steps:**
1. Free up disk space on CRC VM or use fresh cluster
2. Deploy operator
3. Create photon-inspect MigrationJob
4. Validate inspection results
5. Create photon-convert MigrationJob
6. Test converted QCOW2 in libvirt/QEMU

---

## Files Created

**Test Manifests:**
- `/tmp/simple-operator-deploy.yaml` - Simplified operator deployment
- `/tmp/test-photon-local.sh` - Local CLI test script

**Location of photon.vmdk:**
```
/home/ssahani/tt/h2kvm/photon.vmdk (974MB)
```

**Expected Output Location:**
```
/data/output/photon.qcow2 (in worker pod)
/tmp/photon-test-* (local testing)
```

---

## Documentation References

- **Production Deployment Guide:** `PRODUCTION_DEPLOYMENT_GUIDE.md`
- **OpenShift Quick Start:** `OPENSHIFT_QUICKSTART.md`
- **Test Results:** `TEST_RESULTS.md`
- **Local Test Report:** `LOCAL_TEST_REPORT.md`

---

**Test Status:** ⚠️ Ready (waiting for cluster disk space)
**Operator Version:** v0.3.1
**Images Available:** ✅ ghcr.io/ssahani/h2kvm:2.1.0-operator
**CRDs Installed:** ✅ migrationjobs.h2kvm.io, jobtemplates.h2kvm.io

When disk space is available, run:
```bash
kubectl apply -f /tmp/simple-operator-deploy.yaml
kubectl apply -f k8s/operator/examples/inspect-job.yaml
```
