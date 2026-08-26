# Migration Decision Tree

Interactive decision tree to help you choose the right migration approach and configuration.

---

## Quick Start Decision

**Answer these 3 questions to get started:**

```
1. How many VMs do you need to migrate?
   └─ 1 VM      → [Single VM Migration](#single-vm-migration)
   └─ 2-10 VMs  → [Small Batch Migration](#small-batch-migration)
   └─ 10+ VMs   → [Large Scale Migration](#large-scale-migration)

2. What's your acceptable downtime?
   └─ Full downtime OK     → [Cold Migration](#cold-migration)
   └─ < 5 seconds          → [Live Fix](#live-fix-migration)
   └─ Scheduled window     → [Scheduled Migration](#scheduled-migration)

3. Where is your source?
   └─ Local VMDK file      → [Local Migration](#local-migration)
   └─ Remote ESXi/vCenter  → [Remote Migration](#remote-migration)
   └─ Cloud (AWS/Azure)    → [Cloud Import](#cloud-import)
```

---

## Single VM Migration

### Simple Linux VM (Most Common)

```
Your Linux VM → Choose Migration Method
│
├─ Local VMDK file available?
│  │
│  └─ YES → Use local migration
│     │
│     └─→ Configuration:
│        ```yaml
│        command: local
│        vmdk: /path/to/linux-vm.vmdk
│        output_dir: /kvm/vms
│        to_output: linux-vm.qcow2
│
│        # Essential options (always recommended)
│        fstab_mode: stabilize-all
│        regen_initramfs: true
│        # grub is auto-handled
│
│        # Optional but recommended
│        compress: true
│        libvirt_test: true
│        ```
│
│        Time: 10-30 min
│        Success Rate: 97%
│
│        → [Quick Start Guide](getting-started/02-Quick-Start.md)
│
└─ NO → VM is on ESXi/vCenter?
   │
   └─ YES → Use remote fetch
      │
      └─→ Configuration:
         ```yaml
         command: fetch-and-fix
         host: 192.168.1.100
         user: root
         identity: ~/.ssh/id_rsa
         remote: /vmfs/volumes/datastore1/vm/vm.vmdk
         output_dir: /kvm/vms
         to_output: linux-vm.qcow2

         fstab_mode: stabilize-all
         regen_initramfs: true
         ```

         Time: 15-45 min (includes transfer)
         Success Rate: 96%

         → [Remote Migration Guide](guides/migration/playbooks.md)
```

---

### Windows VM

```
Your Windows VM → Check Version
│
├─ Windows Server (2012-2025)?
│  │
│  └─→ Configuration:
│     ```yaml
│     command: local
│     vmdk: /path/to/windows.vmdk
│     output_dir: /kvm/vms
│     to_output: windows-server.qcow2
│
│     # Critical for Windows
│     inject_virtio_drivers: true
│     windows_version: 2019  # or 2012, 2016, 2022, 2025
│
│     # Optional
│     compress: true
│     ```
│
│     Time: 20-40 min
│     Success Rate: 94%
│
│     → [Windows Migration Guide](os-support/windows/guide.md)
│
└─ Windows Desktop (7-11)?
   │
   └─→ Configuration:
      ```yaml
      command: local
      vmdk: /path/to/windows.vmdk
      output_dir: /kvm/vms
      to_output: windows-desktop.qcow2

      inject_virtio_drivers: true
      windows_version: 10  # or 7, 8.1, 11
      ```

      Time: 20-35 min
      Success Rate: 93%

      → [Windows Migration Guide](os-support/windows/guide.md)
```

---

### VMware Cloned VM (Duplicate UUIDs)

```
Cloned from VMware? → Special handling needed
│
└─→ Configuration:
   ```yaml
   command: local
   vmdk: /path/to/cloned-vm.vmdk
   output_dir: /kvm/vms
   to_output: fixed-clone.qcow2

   # CRITICAL for clones
   xfs_regenerate_uuid: true
   fstab_mode: stabilize-all

   # Standard options
   regen_initramfs: true
   # grub is auto-handled
   ```

   Why? Cloned VMs have duplicate filesystem UUIDs
   Result: 98% success rate after UUID regeneration

   → [XFS UUID Regeneration](features/xfs-uuid-regeneration.md)
```

---

## Small Batch Migration

**2-10 VMs → Batch Processing**

```
Small Batch → Choose Approach
│
├─ All VMs similar (same OS/config)?
│  │
│  └─ YES → Use batch manifest
│     │
│     └─→ Create migrations.json:
│        ```json
│        {
│          "migrations": [
│            {"vmdk": "/vms/web-01.vmdk", "to_output": "web-01.qcow2"},
│            {"vmdk": "/vms/web-02.vmdk", "to_output": "web-02.qcow2"},
│            {"vmdk": "/vms/web-03.vmdk", "to_output": "web-03.qcow2"}
│          ]
│        }
│        ```
│
│        Configuration (batch.yaml):
│        ```yaml
│        command: local
│        batch_manifest: migrations.json
│        batch_parallel: 3  # Parallel workers
│        batch_continue_on_error: true
│        output_dir: /kvm/batch
│
│        # Common options for all
│        fstab_mode: stabilize-all
│        regen_initramfs: true
│        compress: true
│        ```
│
│        Run: h2kvmctl --config batch.yaml
│
│        Time: ~Same as single VM (parallel processing)
│
│        → [Batch Migration Guide](guides/migration/batch-features.md)
│
└─ NO → VMs have different configs?
   │
   └─→ Create separate YAML for each VM
      │
      └─→ Run sequentially or use daemon mode
         ```bash
         # Option 1: Sequential
         for config in vm*.yaml; do
           h2kvmctl --config $config
         done

         # Option 2: Daemon mode (recommended)
         h2kvm daemon start
         for config in vm*.yaml; do
           h2kvm daemon submit $config
         done
         h2kvm daemon status
         ```

         → [Daemon User Guide](features/daemon-user-guide.md)
```

---

## Large Scale Migration

**10+ VMs → Enterprise Approach**

```
Large Scale Migration → Choose Platform
│
├─ Have Kubernetes/OpenShift?
│  │
│  ├─ YES → Use Kubernetes Operator
│  │  │
│  │  └─→ Deployment:
│  │     ```bash
│  │     # Install operator
│  │     helm install h2kvm-operator \
│  │       https://ssahani.github.io/h2kvm-charts/h2kvm-operator \
│  │       -n h2kvm-system --create-namespace
│  │
│  │     # Submit migration jobs
│  │     kubectl apply -f - <<EOF
│  │     apiVersion: h2kvm.io/v1
│  │     kind: MigrationJob
│  │     metadata:
│  │       name: migrate-vm-001
│  │     spec:
│  │       source:
│  │         type: vmdk
│  │         path: /mnt/vmware/vm-001.vmdk
│  │       output:
│  │         format: qcow2
│  │         path: /mnt/kvm/vm-001.qcow2
│  │       options:
│  │         fstabMode: stabilize-all
│  │         regenInitramfs: true
│  │     EOF
│  │
│  │     # Monitor
│  │     kubectl get migrationjobs -w
│  │     ```
│  │
│  │     Benefits:
│  │     - Job scheduling
│  │     - Resource management
│  │     - Progress tracking
│  │     - Failure recovery
│  │
│  │     → [Kubernetes Integration](deployment/KUBERNETES_INTEGRATION.md)
│  │     → [OpenShift Guide](deployment/openshift-deployment-guide.md)
│  │
│  └─ NO → Use Daemon Mode
│     │
│     └─→ Setup:
│        ```bash
│        # Start daemon
│        h2kvm daemon start
│
│        # Configure workers
│        export H2KVM_WORKERS=4
│
│        # Submit jobs
│        for vmdk in /vmware/*.vmdk; do
│          cat > "job-$(basename $vmdk .vmdk).yaml" <<EOF
│        command: local
│        vmdk: $vmdk
│        output_dir: /kvm/migrated
│        to_output: $(basename $vmdk .vmdk).qcow2
│        fstab_mode: stabilize-all
│        regen_initramfs: true
│        EOF
│          h2kvm daemon submit "job-$(basename $vmdk .vmdk).yaml"
│        done
│
│        # Monitor progress
│        watch -n 5 'h2kvm daemon status'
│        ```
│
│        Benefits:
│        - Queue management
│        - Parallel processing
│        - REST API
│        - Progress tracking
│
│        → [Daemon User Guide](features/daemon-user-guide.md)
│
└─ Need migration planning?
   │
   └─→ Use inspection first
      ```bash
      # Inspect all VMs
      for vmdk in /vmware/*.vmdk; do
        ./scripts/vmdk_inspect.py "$vmdk" > \
          "report-$(basename $vmdk .vmdk).txt"
      done

      # Analyze reports
      grep -h "OS:" report-*.txt | sort | uniq -c
      grep -h "Issues:" report-*.txt

      # Plan migration order
      # 1. Test VMs first
      # 2. Non-critical VMs
      # 3. Critical VMs last
      ```

      → [VMDK Inspector](features/vmdk-inspector.md)
      → [Enterprise Tutorial](tutorials/04-enterprise-deployment.md)
```

---

## Migration by Downtime Tolerance

### Cold Migration (Full Downtime)

**Best for**: Development, test, non-critical systems

```
Cold Migration Flow:
│
1. Shutdown source VM
2. Export VMDK
3. Run H2KVM
4. Test on KVM
5. Switchover when ready
│
└─→ Configuration:
   ```yaml
   command: local
   vmdk: /path/to/vm.vmdk
   output_dir: /kvm/vms
   to_output: vm.qcow2

   # All fixes applied during migration
   fstab_mode: stabilize-all
   regen_initramfs: true
   # grub is auto-handled

   # Test before production
   libvirt_test: true
   ```

   Downtime: Duration of migration (10-60 min)
   Success Rate: 97%

   → [Quick Start Guide](getting-started/02-Quick-Start.md)
```

---

### Live Fix (< 5 Second Downtime)

**Best for**: Production VMs that can't be down long

```
Live Fix Flow:
│
1. VM runs on VMware (no downtime)
2. Export VMDK snapshot
3. Convert to KVM format
4. Prepare KVM VM
5. Stop source VM (start downtime timer)
6. Apply final fixes via SSH (< 5 seconds)
7. Start on KVM (end downtime timer)
│
└─→ Configuration:
   ```bash
   # Phase 1: Convert (while VM runs)
   h2kvmctl --config << EOF
   command: local
   vmdk: /snapshots/vm-snapshot.vmdk
   output_dir: /kvm/vms
   to_output: vm-prepared.qcow2
   fstab_mode: stabilize-all
   regen_initramfs: true
   EOF

   # Phase 2: Live fix (< 5 sec downtime)
   # Stop source VM
   # Start KVM VM
   h2kvmctl fix ssh 192.168.1.100 \
     --user root \
     --key ~/.ssh/id_rsa \
     --quick-fix
   ```

   Downtime: < 5 seconds
   Success Rate: 95%
   Complexity: High

   → [Live Migration Guide](guides/migration/playbooks.md#live-fix)
```

---

### Scheduled Migration

**Best for**: Planned maintenance windows

```
Scheduled Migration Strategy:
│
├─ Pre-Migration (days before)
│  ├─→ Inspect VMs
│  ├─→ Test conversions
│  └─→ Plan order
│
├─ Migration Window (scheduled)
│  ├─→ Shutdown source VMs
│  ├─→ Run migrations (parallel if possible)
│  ├─→ Test on KVM
│  └─→ Rollback if issues
│
└─ Post-Migration
   ├─→ Validate all VMs
   ├─→ Update DNS/monitoring
   └─→ Keep source VMs for rollback window
│
└─→ Example Timeline:
   ```
   Week -1: Inspection and testing
   Day -1:  Final preparation
   Day 0:   Migration window
     00:00 - Start migrations
     01:00 - Validate first batch
     02:00 - Continue with next batch
     04:00 - All migrations complete
     05:00 - Final validation
     06:00 - Update production routing
   Day +1:  Monitor for issues
   Week +1: Decommission source VMs
   ```

   → [Enterprise Tutorial](tutorials/04-enterprise-deployment.md)
```

---

## Migration by Source Location

### Local Migration

**Source**: VMDK file on local disk

```
Local Migration:
│
└─→ Simplest approach
   ```yaml
   command: local
   vmdk: /path/to/vm.vmdk
   output_dir: /kvm/vms
   to_output: vm.qcow2
   ```

   When to use:
   - VMDK already downloaded
   - OVA/OVF already extracted
   - Maximum control over process

   Speed: Fastest (no network transfer)

   → [Quick Start Guide](getting-started/02-Quick-Start.md)
```

---

### Remote Migration

**Source**: VM on ESXi/vCenter

```
Remote Migration Options:
│
├─ Option 1: Fetch and Convert
│  │
│  └─→ Configuration:
│     ```yaml
│     command: fetch-and-fix
│     host: esxi-01.example.com
│     user: root
│     identity: ~/.ssh/id_rsa
│     remote: /vmfs/volumes/datastore1/vm/vm.vmdk
│     output_dir: /kvm/vms
│     to_output: vm.qcow2
│
│     fstab_mode: stabilize-all
│     regen_initramfs: true
│     ```
│
│     Benefits:
│     - Single command
│     - Automatic transfer
│     - Built-in retry logic
│
├─ Option 2: vSphere Export
│  │
│  └─→ Configuration:
│     ```yaml
│     command: vsphere_export
│     vcenter_host: vcenter.example.com
│     vcenter_user: admin@vsphere.local
│     vcenter_password: secret
│     vm_name: production-web-01
│     output_dir: /kvm/vms
│     to_output: web-01.qcow2
│
│     fstab_mode: stabilize-all
│     regen_initramfs: true
│     ```
│
│     Benefits:
│     - Works with vCenter
│     - VM name instead of path
│     - Automatic VMDK location
│
└─ Option 3: Manual Download → Local Migration
   │
   └─→ Steps:
      ```bash
      # 1. Download VMDK
      scp root@esxi:/vmfs/volumes/datastore1/vm/*.vmdk /temp/

      # 2. Run local migration
      h2kvmctl --config local-migration.yaml
      ```

      When to use:
      - Better control over transfer
      - Can use faster tools (rsync, etc.)
      - Need to inspect VMDK first
```

---

### Cloud Import

**Source**: AWS AMI, Azure VHD, GCP image

```
Cloud Import:
│
├─ AWS AMI
│  │
│  └─→ Configuration:
│     ```yaml
│     command: ami
│     ami_file: /downloads/aws-vm.tar.gz
│     output_dir: /kvm/vms
│     to_output: aws-vm.qcow2
│
│     fstab_mode: stabilize-all
│     regen_initramfs: true
│     ```
│
├─ Azure VHD
│  │
│  └─→ Configuration:
│     ```yaml
│     command: vhd
│     vhd_file: /downloads/azure-vm.vhd
│     output_dir: /kvm/vms
│     to_output: azure-vm.qcow2
│
│     fstab_mode: stabilize-all
│     regen_initramfs: true
│     ```
│
└─ Process:
   1. Export from cloud provider
   2. Download to local storage
   3. Convert with H2KVM
   4. Deploy to KVM environment
```

---

## Special Scenarios

### Database Servers

```
Database Server Migration:
│
├─ Considerations
│  ├─ Stop DB before export
│  ├─ Ensure clean shutdown
│  ├─ Verify data consistency
│  └─ Plan for longer migration time
│
└─→ Configuration:
   ```yaml
   command: local
   vmdk: /vms/db-server.vmdk
   output_dir: /kvm/vms
   to_output: db-server.qcow2

   # Essential for DB servers
   fstab_mode: stabilize-all
   regen_initramfs: true
   # grub is auto-handled

   # Performance optimization
   compress: false  # Faster for large DBs
   out_format: raw  # Better I/O performance
   ```

   Post-migration:
   - Verify DB starts correctly
   - Run integrity checks
   - Test performance
   - Update connection strings

   → [Database Migration Best Practices](guides/migration/playbooks.md)
```

---

### High-Security VMs

```
High-Security Migration:
│
├─ Additional Requirements
│  ├─ Encrypted source
│  ├─ Encrypted transfer
│  ├─ Encrypted destination
│  └─ Audit logging
│
└─→ Configuration:
   ```yaml
   command: local
   vmdk: /secure/encrypted-vm.vmdk
   output_dir: /secure/kvm
   to_output: encrypted-vm.qcow2

   # Standard options
   fstab_mode: stabilize-all
   regen_initramfs: true

   # Security options
   out_format: qcow2
   compress: true

   # Enable detailed logging
   log_level: DEBUG
   log_file: /var/log/h2kvm/migration-audit.log
   ```

   Post-migration:
   - Encrypt QCOW2 with LUKS
   - Verify checksums
   - Review audit logs
   - Test security controls

   → [Security Best Practices](guides/security-best-practices.md)
```

---

### Multi-Disk VMs

```
Multi-Disk VM Migration:
│
└─→ Migrate each disk separately
   ```bash
   # Disk 1 (OS)
   h2kvmctl --config << EOF
   command: local
   vmdk: /vms/vm-disk1.vmdk
   output_dir: /kvm/multi-disk
   to_output: vm-os.qcow2
   fstab_mode: stabilize-all
   regen_initramfs: true
   EOF

   # Disk 2 (Data)
   h2kvmctl --config << EOF
   command: local
   vmdk: /vms/vm-disk2.vmdk
   output_dir: /kvm/multi-disk
   to_output: vm-data.qcow2
   EOF

   # Create libvirt XML with multiple disks
   virsh define vm-multi-disk.xml
   ```

   → [Multi-Disk Guide](guides/migration/playbooks.md#multi-disk)
```

---

## Decision Matrix

| Scenario | Approach | Config Priority | Time | Difficulty |
|----------|----------|-----------------|------|------------|
| **Single Linux VM** | Local | fstab, initramfs | 15 min | ⭐ Easy |
| **Single Windows VM** | Local | VirtIO drivers | 25 min | ⭐⭐ Moderate |
| **VMware Clone** | Local | UUID regen | 20 min | ⭐⭐ Moderate |
| **2-10 VMs** | Batch | Parallel workers | 30 min | ⭐⭐ Moderate |
| **10+ VMs** | Kubernetes/Daemon | Scheduling | Varies | ⭐⭐⭐ Advanced |
| **Production (< 5s down)** | Live Fix | Quick fixes | 20 min | ⭐⭐⭐⭐ Expert |
| **Remote ESXi** | Fetch | Network retry | 30 min | ⭐⭐ Moderate |
| **vCenter VMs** | vSphere Export | Auth config | 35 min | ⭐⭐ Moderate |
| **Cloud Import** | AMI/VHD | Cloud-init | 25 min | ⭐⭐ Moderate |
| **Database Server** | Local | Data integrity | 45 min | ⭐⭐⭐ Advanced |

---

## Next Steps

After choosing your approach:

1. **Review relevant documentation**
   - [Quick Start](getting-started/02-Quick-Start.md) - For beginners
   - [Tutorials](tutorials/) - For learning
   - [Recipes](recipes/) - For quick solutions

2. **Inspect your VMs** (recommended)
   ```bash
   ./scripts/vmdk_inspect.py /path/to/vm.vmdk
   ```

3. **Start with test VM**
   - Test your configuration first
   - Verify boot and functionality
   - Then migrate production VMs

4. **Get help if needed**
   - [FAQ](FAQ.md)
   - [Troubleshooting Flowchart](TROUBLESHOOTING_FLOWCHART.md)
   - [GitHub Issues](https://github.com/ssahani/h2kvm/issues)

---

**Last Updated**: March 2026
**Documentation Version**: 0.3.0
