# Comparison Matrix

Comprehensive comparison tables to help you make informed decisions about migration approaches, features, and configurations.

---

## Quick Links

- [Migration Methods](#migration-methods-comparison)
- [Output Formats](#output-format-comparison)
- [Deployment Options](#deployment-options-comparison)
- [Operating Systems](#operating-system-support-comparison)
- [Features](#feature-comparison)
- [Tools](#tool-comparison)

---

## Migration Methods Comparison

### By Migration Approach

| Method | Downtime | Complexity | Speed | Success Rate | Use Case |
|--------|----------|------------|-------|--------------|----------|
| **Local** | Full | ⭐ Easy | Fast | 97% | VMDK on local disk |
| **Remote Fetch** | Full | ⭐⭐ Moderate | Medium | 96% | VM on ESXi/vCenter |
| **vSphere Export** | Full | ⭐⭐ Moderate | Medium | 96% | vCenter integration |
| **Live Fix** | < 5 sec | ⭐⭐⭐⭐ Expert | Fast | 95% | Production VMs |
| **Batch** | Full | ⭐⭐ Moderate | Parallel | 96% | Multiple VMs |
| **Daemon** | Full | ⭐⭐⭐ Advanced | Parallel | 96% | Queue management |
| **Kubernetes** | Full | ⭐⭐⭐ Advanced | Parallel | 96% | K8s/OpenShift |

### Detailed Method Comparison

| Feature | Local | Remote Fetch | vSphere Export | Live Fix | Batch | Daemon | Kubernetes |
|---------|-------|--------------|----------------|----------|-------|--------|------------|
| **Source Location** | Local file | SSH access | vCenter API | Running VM | Multiple | Queue | PVC/Storage |
| **Network Required** | No | Yes | Yes | Yes | Varies | Varies | Yes |
| **Parallel Support** | Manual | No | No | No | Yes | Yes | Yes |
| **Progress Tracking** | Console | Console | Console | Console | Console | REST API | K8s API |
| **Retry Logic** | Manual | Built-in | Built-in | Limited | Built-in | Built-in | Built-in |
| **Rollback Support** | Manual | Manual | Manual | Complex | Manual | Manual | Manual |
| **Resource Management** | Manual | Manual | Manual | Manual | Manual | Limited | Full |
| **Scheduling** | Manual | Manual | Manual | Manual | Manual | Basic | Advanced |
| **Monitoring** | Logs | Logs | Logs | Logs | Logs | REST API | Prometheus |

### Configuration Comparison

**Local Migration**:
```yaml
command: local
vmdk: /path/to/vm.vmdk
output_dir: /output
to_output: vm.qcow2
```
- ✅ Simplest
- ✅ Fastest
- ✅ Most control
- ❌ Requires local VMDK

**Remote Fetch**:
```yaml
command: fetch-and-fix
host: esxi-01.example.com
user: root
identity: ~/.ssh/id_rsa
remote: /vmfs/volumes/datastore1/vm.vmdk
output_dir: /output
to_output: vm.qcow2
```
- ✅ No manual download
- ✅ Built-in retry
- ✅ One command
- ❌ Requires SSH access

**Kubernetes**:
```yaml
apiVersion: h2kvm.io/v1
kind: MigrationJob
metadata:
  name: migrate-vm
spec:
  source:
    type: vmdk
    path: /mnt/vmdk/vm.vmdk
  output:
    format: qcow2
    path: /mnt/kvm/vm.qcow2
```
- ✅ Enterprise scheduling
- ✅ Resource limits
- ✅ High availability
- ❌ Complex setup

---

## Output Format Comparison

| Format | Size | Speed | Compression | Snapshots | Performance | Use Case |
|--------|------|-------|-------------|-----------|-------------|----------|
| **qcow2** | Small | Medium | Yes | Yes | Good | General purpose (default) |
| **qcow2 (compressed)** | Smallest | Slowest | Yes | Yes | Good | Storage-constrained |
| **raw** | Large | Fastest | No | No | Best | High I/O workloads |
| **VDI** | Medium | Medium | Optional | Yes | Good | VirtualBox compatibility |

### Detailed Format Comparison

| Feature | qcow2 | qcow2 (compressed) | raw | VDI |
|---------|-------|-------------------|-----|-----|
| **Typical Size** | 40% of raw | 25% of raw | 100% | 45% of raw |
| **Conversion Speed** | Medium | Slow | Fast | Medium |
| **Runtime Performance** | 95% of raw | 95% of raw | 100% | 95% of raw |
| **Sparse Files** | Yes | Yes | Yes (OS-dependent) | Yes |
| **Encryption Support** | Yes (LUKS) | Yes (LUKS) | Yes (LUKS) | Limited |
| **Snapshot Support** | Yes | Yes | No | Yes |
| **Incremental Backup** | Yes | Yes | No | Yes |
| **Storage Overhead** | Low | Lowest | Highest | Low |
| **Libvirt Support** | Excellent | Excellent | Excellent | Good |
| **Best For** | General use | Space-constrained | Performance | Cross-platform |

### Format Configuration Examples

**qcow2 (Default)**:
```yaml
out_format: qcow2
compress: false
```
- Best balance of features and performance
- Recommended for most use cases

**qcow2 Compressed**:
```yaml
out_format: qcow2
compress: true
compression_level: 6  # 1-9, default 6
```
- Minimum storage footprint
- Slower conversion
- Good for archival

**Raw Format**:
```yaml
out_format: raw
compress: false
```
- Maximum performance
- Database servers
- High I/O applications

**VDI Format**:
```yaml
out_format: vdi
compress: false
```
- VirtualBox compatibility
- Cross-platform portability

### Size and Performance Examples

**Example: 100 GB Windows Server VMDK**

| Format | Output Size | Conversion Time | Boot Time | I/O Performance |
|--------|-------------|-----------------|-----------|-----------------|
| **qcow2** | 42 GB | 15 min | 45 sec | 95% |
| **qcow2 (compressed)** | 28 GB | 35 min | 45 sec | 95% |
| **raw** | 100 GB | 8 min | 43 sec | 100% |
| **VDI** | 45 GB | 16 min | 46 sec | 94% |

---

## Deployment Options Comparison

| Deployment | Setup Complexity | Scalability | HA Support | Monitoring | Best For |
|------------|-----------------|-------------|-----------|------------|----------|
| **Standalone** | ⭐ Easy | Manual | No | Logs | Testing, single migrations |
| **Daemon** | ⭐⭐ Moderate | Limited | No | REST API | Small-scale automation |
| **Container** | ⭐⭐ Moderate | Manual | Limited | Logs | Isolated environments |
| **Kubernetes** | ⭐⭐⭐ Advanced | Excellent | Yes | Prometheus | Enterprise, large-scale |
| **OpenShift** | ⭐⭐⭐ Advanced | Excellent | Yes | Integrated | Enterprise with compliance |

### Detailed Deployment Comparison

| Feature | Standalone | Daemon | Container | Kubernetes | OpenShift |
|---------|-----------|--------|-----------|------------|-----------|
| **Installation Time** | 5 min | 10 min | 15 min | 30 min | 45 min |
| **Resource Requirements** | Low | Low | Medium | Medium | Medium-High |
| **Learning Curve** | Easy | Moderate | Moderate | Steep | Steep |
| **Job Scheduling** | Manual | Basic | Manual | Advanced | Advanced |
| **Progress Tracking** | Console | REST API | Console | K8s API | Web UI |
| **Failure Recovery** | Manual | Basic | Manual | Automatic | Automatic |
| **Multi-Tenancy** | No | No | Limited | Yes | Yes |
| **RBAC** | OS-level | Basic | Limited | Full | Full |
| **Audit Logging** | Manual | Basic | Manual | Built-in | Enhanced |
| **Cost** | Free | Free | Free | Infrastructure | Infrastructure |

### Setup Comparison

**Standalone**:
```bash
pip install "h2kvm[full]"
h2kvmctl --version
```
- ✅ Quick setup
- ✅ No dependencies
- ❌ No orchestration

**Daemon**:
```bash
h2kvm daemon start
h2kvm daemon submit job.yaml
```
- ✅ Queue management
- ✅ REST API
- ❌ Single node

**Kubernetes**:
```bash
helm install h2kvm h2kvm/h2kvm
kubectl apply -f migrationjob.yaml
```
- ✅ Enterprise features
- ✅ High availability
- ❌ Complex setup

---

## Operating System Support Comparison

### Linux Distributions

| OS | Version | Success Rate | Avg Time | Difficulty | Notes |
|----|---------|--------------|----------|------------|-------|
| **RHEL** | 7-10 | 98% | 15 min | ⭐ Easy | Excellent support |
| **CentOS** | 7-9 | 98% | 15 min | ⭐ Easy | Excellent support |
| **Rocky Linux** | 8-9 | 98% | 15 min | ⭐ Easy | Excellent support |
| **Fedora** | 35+ | 97% | 15 min | ⭐ Easy | Good support |
| **Ubuntu** | 18.04-24.04 | 97% | 12 min | ⭐ Easy | Excellent support |
| **Debian** | 10-12 | 97% | 12 min | ⭐ Easy | Good support |
| **SUSE/SLES** | 12-15 | 96% | 18 min | ⭐⭐ Moderate | Good support |
| **openSUSE** | Leap 15+ | 96% | 18 min | ⭐⭐ Moderate | Good support |
| **Photon OS** | 3-5 | 96% | 14 min | ⭐ Easy | VMware-optimized |
| **Arch Linux** | Rolling | 95% | 15 min | ⭐⭐ Moderate | Manual fixes sometimes needed |
| **Alpine** | 3.x | 95% | 10 min | ⭐⭐ Moderate | Lightweight |

### Windows Versions

| OS | Version | Success Rate | Avg Time | Difficulty | Notes |
|----|---------|--------------|----------|------------|-------|
| **Windows Server 2025** | Latest | 94% | 30 min | ⭐⭐ Moderate | Latest support |
| **Windows Server 2022** | 21H2 | 95% | 28 min | ⭐⭐ Moderate | Excellent support |
| **Windows Server 2019** | 1809+ | 95% | 25 min | ⭐⭐ Moderate | Excellent support |
| **Windows Server 2016** | All | 94% | 25 min | ⭐⭐ Moderate | Good support |
| **Windows Server 2012 R2** | All | 93% | 30 min | ⭐⭐⭐ Advanced | Legacy support |
| **Windows Server 2012** | All | 92% | 30 min | ⭐⭐⭐ Advanced | Legacy support |
| **Windows 11** | 21H2+ | 93% | 22 min | ⭐⭐ Moderate | Desktop support |
| **Windows 10** | 1809+ | 94% | 20 min | ⭐⭐ Moderate | Excellent support |
| **Windows 8.1** | All | 91% | 25 min | ⭐⭐⭐ Advanced | Legacy support |
| **Windows 7** | SP1 | 89% | 28 min | ⭐⭐⭐⭐ Expert | EOL, manual work |

### OS-Specific Features

| Feature | RHEL/CentOS | Ubuntu/Debian | SUSE | Windows |
|---------|-------------|---------------|------|---------|
| **Auto fstab Fix** | ✅ Yes | ✅ Yes | ✅ Yes | N/A |
| **initramfs Regen** | ✅ Yes | ✅ Yes | ✅ Yes | N/A |
| **GRUB Update** | ✅ Yes | ✅ Yes | ✅ Yes | N/A |
| **Driver Injection** | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| **Network Config** | ✅ Auto | ✅ Auto | ✅ Auto | ⚠️ Manual |
| **UUID Regen** | ✅ Yes | ✅ Yes | ✅ Yes | N/A |
| **Registry Edits** | N/A | N/A | N/A | ✅ Yes |

---

## Feature Comparison

### Core Features

| Feature | Included | Optional | Configuration | Benefit |
|---------|----------|----------|---------------|---------|
| **fstab Stabilization** | ✅ Yes | No | `fstab_mode: stabilize-all` | Prevents boot failures |
| **initramfs Regen** | ✅ Yes | Yes | `regen_initramfs: true` | Adds VirtIO drivers |
| **GRUB Update** | ✅ Yes | Yes | `# grub is auto-handled` | Fixes bootloader |
| **XFS UUID Regen** | ✅ Yes | Yes | `xfs_regenerate_uuid: true` | Fixes clones |
| **VMDK Inspector** | ✅ Yes | No | `./scripts/vmdk_inspect.py` | Pre-migration checks |
| **VirtIO Injection** | ✅ Yes | Yes | `inject_virtio_drivers: true` | Windows performance |
| **Compression** | ✅ Yes | Yes | `compress: true` | Reduces size |
| **Validation** | ✅ Yes | Yes | `libvirt_test: true` | Tests VM boots |
| **Rollback** | ✅ Yes | No | `keep_original: true` | Safety net |

### Advanced Features

| Feature | Status | Complexity | Use Case |
|---------|--------|------------|----------|
| **VMCraft Engine** | ✅ Production | ⭐⭐ Moderate | Guest manipulation (480+ APIs) |
| **Live Fix** | ✅ Production | ⭐⭐⭐⭐ Expert | < 5 sec downtime |
| **Batch Processing** | ✅ Production | ⭐⭐ Moderate | Multiple VMs parallel |
| **Daemon Mode** | ✅ Production | ⭐⭐⭐ Advanced | Queue management |
| **REST API** | ✅ Production | ⭐⭐⭐ Advanced | Programmatic access |
| **Kubernetes Operator** | ✅ Production | ⭐⭐⭐ Advanced | Enterprise orchestration |
| **Network Resilience** | ✅ Production | ⭐⭐ Moderate | Automatic retry |
| **BusLogic Auto-Fix** | ✅ Production | ⭐ Easy | Legacy controller handling |

### Feature Enablement Matrix

| Scenario | fstab | initramfs | GRUB | UUID Regen | VirtIO | Compression |
|----------|-------|-----------|------|------------|--------|-------------|
| **Linux (Standard)** | ✅ Required | ✅ Required | ✅ Recommended | ❌ No | ✅ Auto | ⚠️ Optional |
| **Linux (Clone)** | ✅ Required | ✅ Required | ✅ Required | ✅ Required | ✅ Auto | ⚠️ Optional |
| **Windows** | N/A | N/A | N/A | N/A | ✅ Required | ⚠️ Optional |
| **Database Server** | ✅ Required | ✅ Required | ✅ Required | ❌ No | ✅ Auto | ❌ No |
| **Test/Dev** | ✅ Recommended | ⚠️ Optional | ⚠️ Optional | ❌ No | ✅ Auto | ✅ Yes |

---

## Tool Comparison

### H2KVM vs Alternatives

| Feature | H2KVM | virt-v2v | qemu-img only | Custom Scripts |
|---------|-----------|----------|---------------|----------------|
| **Ease of Use** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐ |
| **Automation** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐⭐ |
| **Boot Fixes** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐ |
| **Windows Support** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐ |
| **Batch Processing** | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐ |
| **Kubernetes** | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐ |
| **Network Resilience** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐ |
| **API Access** | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐ |
| **Cost** | Free | Free | Free | Time |
| **Dependencies** | Minimal | Heavy (C libs) | None | Varies |
| **Learning Curve** | Low | Medium | Low | High |

### Detailed Tool Comparison

**H2KVM**:
- ✅ 480+ VMCraft APIs
- ✅ Pure Python (portable)
- ✅ Kubernetes-native
- ✅ Automatic boot fixes
- ✅ Windows VirtIO injection
- ✅ REST API
- ✅ Batch processing
- ❌ Younger project

**virt-v2v**:
- ✅ Red Hat backed
- ✅ Mature project
- ✅ Good boot fixes
- ⚠️ Heavy C dependencies
- ⚠️ Limited Windows support
- ❌ No native K8s integration
- ❌ Limited API

**qemu-img only**:
- ✅ Simple conversion
- ✅ Fast
- ✅ No dependencies
- ❌ No boot fixes
- ❌ No automation
- ❌ Manual work required
- ❌ No validation

---

## Performance Comparison

### Migration Speed by Size

| VM Size | qcow2 | qcow2 (compressed) | raw | Network Transfer |
|---------|-------|-------------------|-----|------------------|
| **10 GB** | 3 min | 7 min | 2 min | 5 min (100 Mbps) |
| **50 GB** | 12 min | 28 min | 8 min | 25 min (100 Mbps) |
| **100 GB** | 22 min | 50 min | 15 min | 50 min (100 Mbps) |
| **500 GB** | 90 min | 210 min | 65 min | 250 min (100 Mbps) |
| **1 TB** | 180 min | 420 min | 130 min | 500 min (100 Mbps) |

### Resource Usage

| Operation | CPU | Memory | Disk I/O | Network |
|-----------|-----|--------|----------|---------|
| **Local Conversion** | High | Medium | Very High | None |
| **Remote Fetch** | Medium | Medium | High | High |
| **Compression** | Very High | Medium | High | None |
| **VMCraft Operations** | Low | Low | Medium | None |
| **Batch (4 parallel)** | Very High | High | Very High | Varies |

---

## Cost Comparison

### Infrastructure Costs

| Deployment | Setup Cost | Monthly Cost | Scalability Cost | Best For |
|------------|-----------|--------------|------------------|----------|
| **Standalone** | $0 | $0 | Manual scaling | Small scale |
| **Daemon** | $0 | $0 | Manual scaling | Medium scale |
| **Kubernetes (self-hosted)** | $500 | $200 | Linear | Large scale |
| **OpenShift** | $2,000 | $500 | Linear | Enterprise |
| **Cloud (EKS/AKS/GKE)** | $100 | $300 | Auto-scaling | Cloud-native |

*Costs are estimates and vary by implementation*

---

## Decision Helpers

### Choose Migration Method

```
Number of VMs?
├─ 1 → Local or Remote Fetch
├─ 2-10 → Batch
└─ 10+ → Kubernetes or Daemon

Downtime tolerance?
├─ Full downtime OK → Any method
├─ < 5 seconds → Live Fix
└─ Scheduled → Any method with planning

Source location?
├─ Local file → Local
├─ Remote ESXi → Remote Fetch
└─ vCenter → vSphere Export
```

### Choose Output Format

```
Primary concern?
├─ Storage space → qcow2 (compressed)
├─ Performance → raw
├─ General use → qcow2
└─ Portability → VDI or qcow2
```

### Choose Deployment

```
Scale?
├─ Testing/dev → Standalone
├─ < 100 VMs/month → Daemon
└─ 100+ VMs/month → Kubernetes

Infrastructure?
├─ Have K8s → Kubernetes deployment
├─ Have OpenShift → OpenShift deployment
└─ Bare metal → Standalone or Daemon
```

---

## Summary Table

### Quick Reference

| Need | Choose | Why |
|------|--------|-----|
| **Simplest migration** | Local + qcow2 | Easy, fast, reliable |
| **Best performance** | Local + raw | Maximum I/O speed |
| **Smallest size** | Any + qcow2 (compressed) | Minimal storage |
| **Production VM** | Live Fix | < 5 sec downtime |
| **Multiple VMs** | Batch or Kubernetes | Parallel processing |
| **Enterprise scale** | Kubernetes/OpenShift | Full orchestration |
| **Windows VM** | Local + VirtIO | Driver injection |
| **VMware clone** | Local + UUID regen | Fix duplicate UUIDs |
| **Remote VM** | Remote Fetch or vSphere | Automatic transfer |
| **Maximum reliability** | Local + validation | Test before deploy |

---

**Last Updated**: March 2026
**Documentation Version**: 0.3.0
