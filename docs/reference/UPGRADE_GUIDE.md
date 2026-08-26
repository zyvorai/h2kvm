# Upgrade Guide: Live Migration Features

This guide helps you upgrade from hyper2kvm v1.x to v2.0 with live migration features.

## Overview of Changes

hyper2kvm v2.0 introduces:
- **MigrationPolicy CRD** - New cluster-scoped CRD
- **Extended MigrationJob CRD** - New optional fields in `spec.createVM`
- **New Controllers** - Live migration, VM lifecycle, storage migration
- **Enhanced Metrics** - 11 new Prometheus metrics
- **Updated RBAC** - Additional permissions required

## Compatibility

✅ **Backward Compatible**: All changes are additive and opt-in.

- Existing MigrationJob resources work unchanged
- New fields have sensible defaults
- No breaking changes to existing APIs

## Upgrade Steps

### 1. Update CRDs

Apply the new CRDs in order:

```bash
# Apply new MigrationPolicy CRD
kubectl apply -f k8s/operator/crds/migrationpolicy.yaml

# Update MigrationJob CRD (backward compatible)
kubectl apply -f k8s/operator/migrationjob-crd.yaml

# Verify CRDs
kubectl get crd migrationpolicies.hyper2kvm.io
kubectl get crd migrationjobs.hyper2kvm.io
```

### 2. Update RBAC

The operator requires additional permissions:

```bash
# Update ClusterRole
kubectl apply -f k8s/operator/deployment.yaml

# Verify permissions
kubectl auth can-i create virtualmachineinstancemigrations --as=system:serviceaccount:hyper2kvm-system:hyper2kvm-operator
kubectl auth can-i get migrationpolicies --as=system:serviceaccount:hyper2kvm-system:hyper2kvm-operator
```

New permissions added:
- `kubevirt.io/virtualmachines` - Full access
- `kubevirt.io/virtualmachineinstances` - Full access
- `kubevirt.io/virtualmachineinstancemigrations` - Full access
- `hyper2kvm.io/migrationpolicies` - Read/write access
- `persistentvolumeclaims` - Full access

### 3. Deploy Updated Operator

```bash
# Update operator deployment
kubectl apply -f k8s/operator/deployment.yaml

# Wait for rollout
kubectl rollout status deployment/hyper2kvm-operator -n hyper2kvm-system

# Check logs
kubectl logs -n hyper2kvm-system deployment/hyper2kvm-operator -f
```

Expected log messages:
- `Operator metrics initialized`
- `Live migration controller loaded`
- `VM lifecycle controller loaded`
- `Migration policy controller loaded`

### 4. Create Default Migration Policy (Optional)

Create a cluster-wide default policy:

```bash
kubectl apply -f k8s/examples/migrationpolicy-default.yaml
```

Verify:
```bash
kubectl get migrationpolicy default-migration-policy
kubectl describe migrationpolicy default-migration-policy
```

### 5. Verify Metrics

Check that new metrics are exposed:

```bash
kubectl port-forward -n hyper2kvm-system deployment/hyper2kvm-operator 8080:8080

# In another terminal
curl http://localhost:8080/metrics | grep hyper2kvm_live_migration
```

Expected metrics:
- `hyper2kvm_live_migrations_total`
- `hyper2kvm_live_migrations_active`
- `hyper2kvm_migration_policy_violations_total`
- etc.

## Migrating Existing VMs

### Option 1: Recreate VMs with New Features

For new migrations, use the extended spec:

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: upgraded-vm
spec:
  source:
    type: vmdk-url
    vmdk:
      url: "https://storage.example.com/vm.vmdk"
  destination:
    pvcName: upgraded-vm-disk
    size: 50Gi
  createVM:
    enabled: true
    name: upgraded-vm
    cpu: "4"
    memory: 8Gi
    autoStart: true

    # NEW: Enable live migration
    evictionStrategy: LiveMigrate
    migrationPolicyRef: default-migration-policy

    # NEW: Advanced CPU topology
    cpuConfig:
      cores: 2
      sockets: 2
      threads: 1
```

### Option 2: Patch Existing VMs

Add `evictionStrategy` to existing VMs:

```bash
# For a single VM
kubectl patch vm my-existing-vm --type=merge -p '
{
  "spec": {
    "template": {
      "spec": {
        "evictionStrategy": "LiveMigrate"
      }
    }
  }
}'

# For all VMs in a namespace
kubectl get vms -n production -o name | while read vm; do
  kubectl patch $vm -n production --type=merge -p '
  {
    "spec": {
      "template": {
        "spec": {
          "evictionStrategy": "LiveMigrate"
        }
      }
    }
  }'
done
```

**Note**: This only affects the VM spec. Running VMIs won't be affected until next restart.

### Option 3: Annotate VMs with Migration Policy

Apply migration policy without recreating:

```bash
kubectl annotate vm my-vm hyper2kvm.io/migration-policy=default-migration-policy
```

## Testing the Upgrade

### Test 1: Create New VM with Eviction Strategy

```bash
# Create test migration job
kubectl apply -f k8s/examples/migrationjob-with-eviction.yaml

# Wait for completion
kubectl get migrationjob -w

# Verify VM has evictionStrategy
kubectl get vm <vm-name> -o jsonpath='{.spec.template.spec.evictionStrategy}'
# Should output: LiveMigrate
```

### Test 2: Trigger Live Migration

```bash
# Find a node with the VM
kubectl get vmi -o wide

# Cordon the node
kubectl cordon <node-name>

# Watch for automatic migration
kubectl get virtualmachineinstancemigrations -w

# Should see VMIM created automatically
```

### Test 3: Check Metrics

```bash
# Port forward to operator
kubectl port-forward -n hyper2kvm-system deployment/hyper2kvm-operator 8080:8080

# Query metrics
curl http://localhost:8080/metrics | grep -E 'hyper2kvm_(live_migrations|migration_policy)'
```

### Test 4: Policy Validation

```bash
# Try to create invalid policy
kubectl apply -f - <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationPolicy
metadata:
  name: invalid-policy
spec:
  maxParallelMigrationsPerCluster: 2
  maxParallelMigrationsPerNode: 5  # Invalid: node > cluster
EOF

# Should be rejected by validation webhook
```

## Rollback Procedure

If issues occur, rollback:

### 1. Revert Operator Deployment

```bash
# Rollback to previous version
kubectl rollout undo deployment/hyper2kvm-operator -n hyper2kvm-system

# Or deploy specific version
kubectl set image deployment/hyper2kvm-operator \
  hyper2kvm-operator=ghcr.io/your-org/hyper2kvm-operator:v1.5.0 \
  -n hyper2kvm-system
```

### 2. Keep CRDs (Recommended)

The new fields in MigrationJob CRD are optional, so keeping the updated CRD is safe:

```bash
# Existing MigrationJobs continue to work
kubectl get migrationjobs
```

### 3. Remove MigrationPolicies (If Needed)

```bash
# List policies
kubectl get migrationpolicies

# Delete all policies
kubectl delete migrationpolicies --all

# Remove CRD (optional)
kubectl delete crd migrationpolicies.hyper2kvm.io
```

## Common Issues

### Issue: Operator fails to start

**Symptoms:**
```
Error: failed to create client: forbidden
```

**Cause:** RBAC permissions not updated.

**Solution:**
```bash
kubectl apply -f k8s/operator/deployment.yaml
kubectl delete pod -n hyper2kvm-system -l app=hyper2kvm-operator
```

### Issue: MigrationPolicy not applied to VMs

**Symptoms:** VMs don't migrate automatically on node cordon.

**Cause:**
- VM missing `evictionStrategy: LiveMigrate`
- Policy selector not matching VM labels

**Solution:**
```bash
# Check VM eviction strategy
kubectl get vm <vm-name> -o jsonpath='{.spec.template.spec.evictionStrategy}'

# Check VM labels
kubectl get vm <vm-name> --show-labels

# Check policy selector
kubectl get migrationpolicy <policy-name> -o yaml | grep -A5 vmSelector
```

### Issue: Live migrations fail

**Symptoms:**
```
Phase: Failed
Reason: InsufficientResourcesForMigration
```

**Cause:** Target nodes lack resources.

**Solution:**
1. Check node resources: `kubectl describe nodes`
2. Reduce VM resource requests
3. Add more nodes or free up resources

### Issue: Metrics not appearing

**Symptoms:** No `hyper2kvm_live_migration_*` metrics.

**Cause:** Controllers not initialized.

**Solution:**
```bash
# Check operator logs
kubectl logs -n hyper2kvm-system deployment/hyper2kvm-operator | grep -i "controller\|metrics"

# Look for:
# - "Live migration controller loaded"
# - "Operator metrics initialized"
```

## Migration Checklist

Before upgrading to production:

- [ ] Test in staging environment
- [ ] Backup existing MigrationJob resources
- [ ] Review and update RBAC permissions
- [ ] Create default MigrationPolicy
- [ ] Update monitoring dashboards for new metrics
- [ ] Train operators on live migration procedures
- [ ] Test rollback procedure
- [ ] Document custom migration policies for your environment
- [ ] Update CI/CD pipelines if using MigrationJob
- [ ] Schedule maintenance window for CRD updates

## Post-Upgrade Configuration

### Recommended Policies

**Default (Conservative):**
```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationPolicy
metadata:
  name: default
spec:
  bandwidthPerMigration: "100Mi"
  allowAutoConverge: true
  allowPostCopy: false
  maxParallelMigrationsPerCluster: 5
  maxParallelMigrationsPerNode: 2
```

**Production (Balanced):**
```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationPolicy
metadata:
  name: production
spec:
  bandwidthPerMigration: "500Mi"
  allowAutoConverge: true
  allowPostCopy: false
  maxParallelMigrationsPerCluster: 10
  maxParallelMigrationsPerNode: 3
  vmSelector:
    matchLabels:
      tier: production
```

**Critical (Aggressive):**
```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationPolicy
metadata:
  name: critical
spec:
  bandwidthPerMigration: "2Gi"
  allowAutoConverge: true
  allowPostCopy: true
  completionTimeoutPerGiB: 1200
  maxParallelMigrationsPerCluster: 15
  maxParallelMigrationsPerNode: 5
  vmSelector:
    matchLabels:
      tier: critical
```

### Grafana Dashboard

Import the live migration dashboard:

```bash
# Import from k8s/monitoring/grafana-dashboard-live-migration.json
# (Create this file with queries for new metrics)
```

Key panels:
- Active migrations by phase
- Migration success rate
- Average migration duration
- Policy violations
- Bandwidth usage

### Alerting Rules

Example Prometheus alerts:

```yaml
groups:
- name: hyper2kvm-live-migration
  rules:
  - alert: HighMigrationFailureRate
    expr: |
      rate(hyper2kvm_live_migrations_failed_total[5m]) /
      rate(hyper2kvm_live_migrations_total[5m]) > 0.1
    for: 10m
    annotations:
      summary: "High migration failure rate (>10%)"

  - alert: MigrationPolicyViolations
    expr: rate(hyper2kvm_migration_policy_violations_total[5m]) > 0
    for: 5m
    annotations:
      summary: "Migration policy violations detected"

  - alert: MigrationStuck
    expr: |
      hyper2kvm_live_migrations_active{phase="Running"} > 0
      and
      increase(hyper2kvm_live_migration_duration_seconds[30m]) == 0
    for: 30m
    annotations:
      summary: "Migration stuck in Running phase for >30m"
```

## Version Compatibility

| Component | v1.x | v2.0 |
|-----------|------|------|
| MigrationJob CRD | v1alpha1 | v1alpha1 (extended) |
| MigrationPolicy CRD | N/A | v1alpha1 (new) |
| Kubernetes | 1.24+ | 1.24+ |
| KubeVirt | 0.59+ | 0.59+ (1.0+ recommended) |
| Prometheus | 2.x | 2.x |

## Getting Help

If you encounter issues:

1. Check logs: `kubectl logs -n hyper2kvm-system deployment/hyper2kvm-operator`
2. Review events: `kubectl get events --sort-by='.lastTimestamp' | grep -i migration`
3. Check metrics: `curl http://localhost:8080/metrics`
4. File issue: https://github.com/anthropics/hyper2kvm/issues

## Summary

The upgrade process is straightforward:
1. Apply new CRDs
2. Update RBAC
3. Deploy updated operator
4. Optionally create migration policies
5. Test with a sample VM

All existing functionality remains unchanged. New features are opt-in via the extended MigrationJob spec.
