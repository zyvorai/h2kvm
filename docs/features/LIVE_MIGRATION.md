# Live Migration Features Guide

## Overview

hyper2kvm now supports comprehensive VM migration capabilities:

1. **Cold Migration** (Hypervisor → KubeVirt): Convert VMware/Hyper-V VMs to KubeVirt
2. **Live Migration** (KubeVirt → KubeVirt): Zero-downtime VM migration between nodes
3. **Storage Migration**: Change storage classes while VM is running

## Table of Contents

- [Eviction Strategies](#eviction-strategies)
- [Migration Policies](#migration-policies)
- [Advanced VM Configuration](#advanced-vm-configuration)
- [Live Migration Workflow](#live-migration-workflow)
- [Monitoring and Metrics](#monitoring-and-metrics)
- [Troubleshooting](#troubleshooting)

## Eviction Strategies

Eviction strategies control what happens when a node needs to be drained or goes into maintenance.

### Available Strategies

| Strategy | Behavior | Use Case |
|----------|----------|----------|
| `LiveMigrate` | Automatically migrate VM to another node | Production VMs requiring high availability |
| `LiveMigrateIfPossible` | Try live migration, fall back to shutdown | VMs that can tolerate brief downtime |
| `None` | Shutdown VM (no migration) | Development/test VMs |
| `External` | Wait for external orchestration | Custom migration logic |

### Example: VM with LiveMigrate

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: production-vm
spec:
  source:
    type: vmdk-url
    vmdk:
      url: "https://storage.example.com/vm.vmdk"
  destination:
    pvcName: prod-vm-disk
    storageClass: fast-ssd
    size: 50Gi
  createVM:
    enabled: true
    name: prod-vm
    cpu: "4"
    memory: 8Gi
    autoStart: true
    evictionStrategy: LiveMigrate  # Enable automatic live migration
    migrationPolicyRef: production-policy
```

## Migration Policies

MigrationPolicy CRDs define cluster-wide or VM-specific migration behavior.

### Creating a Migration Policy

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationPolicy
metadata:
  name: production-policy
spec:
  # Network bandwidth limit per migration
  bandwidthPerMigration: "1Gi"

  # Enable auto-convergence for slow migrations
  allowAutoConverge: true

  # Enable post-copy as fallback (use with caution)
  allowPostCopy: false

  # Timeout per GiB of VM memory (seconds)
  completionTimeoutPerGiB: 800

  # Progress timeout (seconds)
  progressTimeout: 150

  # Parallelism controls
  maxParallelMigrationsPerCluster: 5
  maxParallelMigrationsPerNode: 2

  # Apply to VMs with priority: high label
  vmSelector:
    matchLabels:
      priority: "high"
```

### Policy Application

Policies are applied in order:
1. MigrationJob specifies `migrationPolicyRef`
2. VM has annotation `hyper2kvm.io/migration-policy`
3. VM labels match policy `vmSelector`
4. Default policy (no selector)

### Bandwidth Control

Bandwidth limits prevent network saturation during migrations:

- `"0"` - Unlimited (default)
- `"100Mi"` - 100 MiB/s
- `"1Gi"` - 1 GiB/s

The BandwidthManager ensures fair sharing across active migrations.

### Parallelism Limits

Prevent resource exhaustion:

```yaml
spec:
  maxParallelMigrationsPerCluster: 5  # Max across entire cluster
  maxParallelMigrationsPerNode: 2     # Max per source node
```

Migrations exceeding limits are queued and emit policy violation metrics.

## Advanced VM Configuration

### Multi-Disk VMs

```yaml
spec:
  source:
    type: multi-disk
    disks:
      - name: os-disk
        type: vmdk-url
        vmdk:
          url: "https://storage.example.com/os.vmdk"
        bootOrder: 1
        bus: virtio

      - name: data-disk
        type: vmdk-url
        vmdk:
          url: "https://storage.example.com/data.vmdk"
        bootOrder: 2
        bus: virtio

  destination:
    pvcs:
      - name: vm-os-pvc
        diskName: os-disk
        storageClass: fast-ssd
        size: 50Gi

      - name: vm-data-pvc
        diskName: data-disk
        storageClass: standard
        size: 100Gi

  createVM:
    enabled: true
    disks:
      - name: data-disk
        pvcName: vm-data-pvc
        bootOrder: 2
        bus: virtio
```

### UEFI Firmware

```yaml
createVM:
  enabled: true
  firmware:
    bootloader: uefi          # bios, uefi, uefi-secure
    secureBoot: false         # Requires UEFI
```

### CPU Topology

Configure CPU topology for licensing or performance:

```yaml
createVM:
  enabled: true
  cpuConfig:
    cores: 4                  # Cores per socket
    sockets: 2                # Number of sockets
    threads: 1                # Threads per core
    dedicatedCpuPlacement: true
    features:
      - "hyperv"              # Hyper-V enlightenments
      - "acpi"
```

**Total vCPUs** = cores × sockets × threads (e.g., 4 × 2 × 1 = 8 vCPUs)

### Resource Limits

```yaml
createVM:
  enabled: true
  resources:
    requests:
      cpu: "2"
      memory: 4Gi
    limits:
      cpu: "8"
      memory: 16Gi
```

### Multiple Network Interfaces

```yaml
createVM:
  enabled: true
  interfaces:
    - name: eth1
      type: bridge
      networkName: br0
      macAddress: "52:54:00:12:34:56"

    - name: eth2
      type: sriov
      networkName: sriov-net
```

## Live Migration Workflow

### Automatic Migration (Node Eviction)

When a node is cordoned for maintenance:

```bash
kubectl cordon node-1
```

VMs with `evictionStrategy: LiveMigrate` automatically migrate to other nodes.

**Process:**
1. VM Lifecycle Controller detects cordoned node
2. Checks MigrationPolicy parallelism limits
3. Creates VirtualMachineInstanceMigration
4. Live Migration Controller tracks progress
5. Emits events and updates metrics

### Manual Migration

Trigger live migration manually:

```bash
# Using kubectl
kubectl create -f - <<EOF
apiVersion: kubevirt.io/v1
kind: VirtualMachineInstanceMigration
metadata:
  name: my-vm-migration
spec:
  vmiName: my-vm
EOF

# Check status
kubectl get virtualmachineinstancemigrations
kubectl get vmim my-vm-migration -o yaml
```

### Migration Phases

| Phase | Description |
|-------|-------------|
| `Pending` | Migration queued, waiting to start |
| `Scheduling` | Finding target node |
| `Running` | Actively migrating memory/state |
| `Succeeded` | Migration completed successfully |
| `Failed` | Migration failed (see reason) |

### Aborting a Migration

```bash
# Delete the VMIM resource
kubectl delete vmim my-vm-migration
```

The VM remains on the source node.

## Monitoring and Metrics

### Prometheus Metrics

**Migration Counts:**
- `hyper2kvm_live_migrations_total` - Total migrations (by namespace, nodes)
- `hyper2kvm_live_migrations_succeeded_total` - Successful migrations
- `hyper2kvm_live_migrations_failed_total` - Failed migrations (by reason)

**Migration Performance:**
- `hyper2kvm_live_migration_duration_seconds` - Migration duration histogram
- `hyper2kvm_live_migration_data_transferred_bytes` - Data transferred histogram
- `hyper2kvm_live_migration_downtime_ms` - VM downtime histogram

**Active Migrations:**
- `hyper2kvm_live_migrations_active` - Currently active migrations (by phase)
- `hyper2kvm_migration_bandwidth_bytes_per_second` - Current bandwidth
- `hyper2kvm_migration_dirty_rate_bytes_per_second` - Memory dirty rate

**Policy Enforcement:**
- `hyper2kvm_migration_policy_violations_total` - Policy violations
- `hyper2kvm_post_copy_activations_total` - Post-copy activations
- `hyper2kvm_auto_converge_activations_total` - Auto-converge activations

### Example Queries

```promql
# Average migration duration
avg(hyper2kvm_live_migration_duration_seconds)

# Migration success rate
sum(rate(hyper2kvm_live_migrations_succeeded_total[5m])) /
sum(rate(hyper2kvm_live_migrations_total[5m]))

# Active migrations by phase
sum by (phase) (hyper2kvm_live_migrations_active)

# Policy violations
rate(hyper2kvm_migration_policy_violations_total[5m])
```

### Kubernetes Events

Watch migration events:

```bash
kubectl get events --sort-by='.lastTimestamp' | grep -i migration
```

Events emitted:
- `MigrationStarted` - Migration initiated
- `MigrationRunning` - Migration in progress
- `MigrationSucceeded` - Migration completed
- `MigrationFailed` - Migration failed
- `MigrationAborted` - Migration cancelled
- `AutoMigrationTriggered` - Automatic migration started
- `MigrationPolicyViolation` - Policy limit exceeded

## Troubleshooting

### Migration Stuck in Running

**Symptoms:** Migration stays in `Running` phase for extended time.

**Causes:**
- High memory dirty rate (VM writing memory faster than migration)
- Insufficient network bandwidth
- Large VM memory

**Solutions:**
1. Check dirty rate:
   ```bash
   kubectl get vmim <name> -o jsonpath='{.status.migrationState.memoryDirtyRate}'
   ```

2. Enable auto-converge in MigrationPolicy:
   ```yaml
   spec:
     allowAutoConverge: true
   ```

3. Increase bandwidth limit:
   ```yaml
   spec:
     bandwidthPerMigration: "2Gi"
   ```

4. Enable post-copy (last resort):
   ```yaml
   spec:
     allowPostCopy: true
   ```

### Migration Failed: "InsufficientResourcesForMigration"

**Cause:** Target node lacks CPU/memory resources.

**Solution:**
- Check node resources: `kubectl describe nodes`
- Reduce VM resource requests
- Free up resources on other nodes

### Policy Violation: "max_parallel_cluster"

**Cause:** Too many simultaneous migrations.

**Solution:**
- Wait for active migrations to complete
- Increase cluster limit:
  ```yaml
  spec:
    maxParallelMigrationsPerCluster: 10
  ```

### VM Not Migrating on Node Cordon

**Cause:** `evictionStrategy` not set to `LiveMigrate`.

**Solution:**
Check VM eviction strategy:
```bash
kubectl get vm <name> -o jsonpath='{.spec.template.spec.evictionStrategy}'
```

Should return `LiveMigrate`.

### High Bandwidth Usage

**Cause:** Multiple concurrent migrations without bandwidth limits.

**Solution:**
Set bandwidth limits in MigrationPolicy:
```yaml
spec:
  bandwidthPerMigration: "500Mi"
```

## Best Practices

### Production VMs

```yaml
createVM:
  evictionStrategy: LiveMigrate
  migrationPolicyRef: production-policy
  firmware:
    bootloader: uefi
  cpuConfig:
    cores: 4
    sockets: 1
    threads: 1
  resources:
    requests:
      cpu: "2"
      memory: 8Gi
    limits:
      cpu: "4"
      memory: 16Gi
```

### Testing/Development VMs

```yaml
createVM:
  evictionStrategy: None  # No automatic migration
  autoStart: false
```

### High-Priority Workloads

Create dedicated policy:

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationPolicy
metadata:
  name: critical-workload-policy
spec:
  bandwidthPerMigration: "2Gi"
  allowAutoConverge: true
  allowPostCopy: true
  maxParallelMigrationsPerCluster: 10
  vmSelector:
    matchLabels:
      tier: critical
```

### Node Maintenance Windows

1. Cordon node:
   ```bash
   kubectl cordon node-1
   ```

2. Monitor migrations:
   ```bash
   kubectl get vmim -w
   ```

3. Wait for migrations to complete

4. Drain node:
   ```bash
   kubectl drain node-1 --ignore-daemonsets
   ```

## API Reference

### MigrationJob.spec.createVM

| Field | Type | Description | Default |
|-------|------|-------------|---------|
| `evictionStrategy` | string | LiveMigrate, None, LiveMigrateIfPossible, External | LiveMigrate |
| `migrationPolicyRef` | string | MigrationPolicy name | - |
| `firmware.bootloader` | string | bios, uefi, uefi-secure | bios |
| `firmware.secureBoot` | bool | Enable UEFI secure boot | false |
| `cpuConfig.cores` | int | Cores per socket | 1 |
| `cpuConfig.sockets` | int | Number of sockets | 1 |
| `cpuConfig.threads` | int | Threads per core | 1 |
| `cpuConfig.dedicatedCpuPlacement` | bool | Request dedicated CPUs | false |
| `cpuConfig.features` | []string | CPU features to enable | [] |
| `resources.requests` | object | Resource requests | - |
| `resources.limits` | object | Resource limits | - |
| `disks` | []object | Additional disks | [] |
| `interfaces` | []object | Network interfaces | [] |

### MigrationPolicy.spec

| Field | Type | Description | Default |
|-------|------|-------------|---------|
| `bandwidthPerMigration` | string | Bandwidth limit (e.g., "100Mi") | "0" (unlimited) |
| `allowAutoConverge` | bool | Enable auto-convergence | true |
| `allowPostCopy` | bool | Enable post-copy migration | false |
| `completionTimeoutPerGiB` | int | Timeout per GiB (seconds) | 800 |
| `progressTimeout` | int | Progress timeout (seconds) | 150 |
| `maxParallelMigrationsPerCluster` | int | Max cluster-wide migrations | 5 |
| `maxParallelMigrationsPerNode` | int | Max per-node migrations | 2 |
| `vmSelector` | object | VM label selector | {} (all VMs) |

## Migration Strategy Decision Tree

```
Start: Need to migrate a VM?
│
├─ Offline migration acceptable?
│  ├─ Yes → Use MigrationJob (cold migration)
│  │        Convert from VMware/Hyper-V
│  │
│  └─ No → Need zero downtime?
│     └─ Yes → Use Live Migration
│              Set evictionStrategy: LiveMigrate
│
├─ Storage change needed?
│  └─ Yes → Storage Migration
│           Create new PVC, update VM volumes
│
└─ Node maintenance planned?
   └─ Yes → Configure evictionStrategy
            Create MigrationPolicy
            Cordon node
            Automatic migration triggered
```

## See Also

- [KubeVirt Live Migration Documentation](https://kubevirt.io/user-guide/operations/live_migration/)
- [MigrationJob CRD Reference](../k8s/operator/migrationjob-crd.yaml)
- [MigrationPolicy CRD Reference](../k8s/operator/crds/migrationpolicy.yaml)
- [Example YAMLs](../k8s/examples/)
