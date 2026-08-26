# Multi-Disk VM Support

The HyperConversion operator supports VMs with multiple disks beyond the root disk. This enables use cases like:

- Separate data volumes
- Database storage on dedicated disks
- Application data persistence
- Boot from multiple sources
- Disk migration scenarios

## Overview

Each HyperConversion can specify:
1. **Root disk** - Defined in `spec.source` and `spec.storage` (required)
2. **Additional disks** - Defined in `spec.vm.additionalDisks[]` (optional)

Additional disks are created as separate CDI DataVolumes and attached to the VirtualMachine with configurable boot order.

## Disk Source Types

Additional disks support three source types:

### 1. Blank Disk

Create an empty disk that will be formatted by the VM:

```yaml
additionalDisks:
  - name: data-disk
    source:
      blank: true
    size: 50Gi  # Required for blank disks
    bus: virtio
```

### 2. URL Source

Import disk from HTTP/HTTPS/S3 URL:

```yaml
additionalDisks:
  - name: database-disk
    source:
      url: "http://example.com/database.qcow2"
      format: qcow2
    size: 100Gi  # Optional, auto-detected if not specified
    storageClass: fast-ssd
```

### 3. Existing PVC

Clone or reference an existing PVC:

```yaml
additionalDisks:
  - name: backup-disk
    source:
      pvcName: existing-backup-pvc
```

## Boot Order

Control the boot sequence by setting `bootOrder` on disks:

```yaml
spec:
  source:
    url: "http://example.com/os.qcow2"
  # Root disk gets bootOrder: 1 automatically

  vm:
    additionalDisks:
      - name: recovery-disk
        bootOrder: 2  # Try this first if root fails
        source:
          url: "http://example.com/recovery.qcow2"

      - name: data-disk
        bootOrder: 3  # Lowest priority
        source:
          blank: true
        size: 100Gi
```

**Boot order rules:**
- Lower numbers boot first
- Root disk defaults to `bootOrder: 1`
- If not specified, additional disks auto-assign sequentially (2, 3, 4, ...)

## Bus Types

Disks support different bus types for compatibility:

```yaml
additionalDisks:
  - name: modern-disk
    bus: virtio      # Modern virtio (default, fastest)
    source:
      blank: true
    size: 50Gi

  - name: legacy-disk
    bus: sata        # Legacy SATA (older OS compatibility)
    source:
      url: "http://example.com/old-os.vmdk"

  - name: scsi-disk
    bus: scsi        # SCSI (database workloads)
    source:
      blank: true
    size: 200Gi
```

**Supported bus types:**
- `virtio` - Paravirtualized (default, best performance)
- `sata` - SATA compatibility mode
- `scsi` - SCSI compatibility mode

## Storage Classes

Each disk can use a different StorageClass:

```yaml
spec:
  storage:
    storageClass: standard  # Root disk uses standard

  vm:
    additionalDisks:
      - name: fast-db
        storageClass: nvme-ssd  # Database on fast storage
        source:
          blank: true
        size: 500Gi

      - name: cold-backup
        storageClass: hdd       # Backups on cheap storage
        source:
          blank: true
        size: 2Ti
```

If not specified, additional disks inherit the root disk's StorageClass.

## Complete Example

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: database-server
spec:
  # Root OS disk
  source:
    url: "http://cloud-images.ubuntu.com/focal/current/focal-server-cloudimg-amd64.img"
    format: qcow2

  storage:
    size: 20Gi
    storageClass: standard

  # VM configuration
  vm:
    name: postgres-server
    cpu:
      cores: 8
    memory: 32Gi

    # Additional disks
    additionalDisks:
      # PostgreSQL data directory
      - name: postgres-data
        source:
          blank: true
        size: 500Gi
        storageClass: nvme-ssd
        bus: virtio
        bootOrder: 3

      # PostgreSQL WAL directory (write-ahead logs)
      - name: postgres-wal
        source:
          blank: true
        size: 100Gi
        storageClass: fast-ssd
        bus: virtio
        bootOrder: 4

      # Backup volume
      - name: backups
        source:
          blank: true
        size: 1Ti
        storageClass: hdd
        bus: virtio
        bootOrder: 5

    # Cloud-init to format and mount disks
    cloudInit:
      userData: |
        #cloud-config
        hostname: postgres-server

        # Format and mount disks
        runcmd:
          # Data disk
          - mkfs.ext4 /dev/vdb
          - mkdir -p /var/lib/postgresql/data
          - mount /dev/vdb /var/lib/postgresql/data
          - echo '/dev/vdb /var/lib/postgresql/data ext4 defaults 0 2' >> /etc/fstab

          # WAL disk
          - mkfs.ext4 /dev/vdc
          - mkdir -p /var/lib/postgresql/wal
          - mount /dev/vdc /var/lib/postgresql/wal
          - echo '/dev/vdc /var/lib/postgresql/wal ext4 defaults 0 2' >> /etc/fstab

          # Backup disk
          - mkfs.ext4 /dev/vdd
          - mkdir -p /backups
          - mount /dev/vdd /backups
          - echo '/dev/vdd /backups ext4 defaults 0 2' >> /etc/fstab

          # Install PostgreSQL
          - apt-get update
          - apt-get install -y postgresql-14

          # Configure PostgreSQL to use custom data/WAL locations
          - systemctl stop postgresql
          - chown -R postgres:postgres /var/lib/postgresql
          - sudo -u postgres /usr/lib/postgresql/14/bin/initdb -D /var/lib/postgresql/data
          - systemctl start postgresql
```

## Device Names

Disks appear as block devices in the VM:

| Bus Type | Device Pattern | Example |
|----------|---------------|---------|
| virtio   | /dev/vd*      | /dev/vda (root), /dev/vdb, /dev/vdc |
| sata     | /dev/sd*      | /dev/sda (root), /dev/sdb, /dev/sdc |
| scsi     | /dev/sd*      | /dev/sda (root), /dev/sdb, /dev/sdc |

**Order:**
- Root disk is always first (vda or sda)
- Additional disks follow in the order defined
- Cloud-init scripts should use device names consistently

## DataVolume Management

Each additional disk creates a CDI DataVolume:

```bash
# List all DataVolumes for a HyperConversion
kubectl get datavolume -l app.kubernetes.io/instance=database-server

NAME                         PHASE       PROGRESS
database-server-dv           Succeeded   100%
database-server-postgres-data   Succeeded   100%
database-server-postgres-wal    Succeeded   100%
database-server-backups         Succeeded   100%

# Check status
kubectl describe hyperconversion database-server

Status:
  Additional Disk Data Volumes:
    postgres-data: database-server-postgres-data
    postgres-wal:  database-server-postgres-wal
    backups:       database-server-backups
  Data Volume Name:    database-server-dv
  Phase:               Ready
  Virtual Machine Name: postgres-server
```

## Lifecycle

1. **Creation**: HyperConversion controller creates DataVolumes for root + additional disks in parallel
2. **Upload**: All DataVolumes import/provision concurrently
3. **VM Creation**: Once all DataVolumes are Ready, VirtualMachine is created with all disks attached
4. **Deletion**: Deleting HyperConversion cascades to all DataVolumes and the VM (via owner references)

## Disk Limits

- **Maximum disks**: Limited by KubeVirt (typically 26 disks per VM due to device naming)
- **Minimum disks**: 1 (root disk is always required)
- **Recommended**: Keep under 10 disks per VM for manageability

## CLI Support

Create multi-disk VMs with h2kctl:

```bash
# Coming soon - CLI support for additional disks
h2kctl migrate disk.vmdk --vm-name my-vm \
  --additional-disk name=data,blank=true,size=100Gi \
  --additional-disk name=backup,url=http://example.com/backup.qcow2
```

## Troubleshooting

### DataVolume Not Created

Check HyperConversion status:

```bash
kubectl describe hyperconversion <name>

Events:
  Type     Reason                   Message
  ----     ------                   -------
  Warning  AdditionalDiskCreateFailed  Failed to create DataVolume for disk data: size is required for blank disks
```

**Solution**: Ensure blank disks have `size` specified.

### Disk Not Appearing in VM

Check VirtualMachine spec:

```bash
kubectl get vm <vm-name> -o yaml

spec:
  template:
    spec:
      domain:
        devices:
          disks:
            - name: rootdisk
              bootOrder: 1
            - name: data-disk
              bootOrder: 2
      volumes:
        - name: rootdisk
          dataVolume:
            name: <root-dv-name>
        - name: data-disk
          dataVolume:
            name: <data-dv-name>
```

**Solution**: Verify DataVolume exists and is in Succeeded phase.

### Wrong Device Names

If disks appear at unexpected device names:

1. Check bus type matches expectations (virtio=vd*, sata/scsi=sd*)
2. Verify boot order is set correctly
3. Use `lsblk` in the VM to see actual device mapping

## Best Practices

1. **Separate Concerns**: Use different disks for OS, data, and logs
2. **Storage Classes**: Match workload to storage performance (NVMe for databases, HDD for backups)
3. **Boot Order**: Set explicit boot order for predictable behavior
4. **Size Planning**: Provision adequate size upfront (resizing is possible but complex)
5. **Cloud-Init**: Automate disk formatting and mounting in cloud-init
6. **Bus Selection**: Use virtio for best performance unless compatibility requires otherwise
7. **Naming**: Use descriptive disk names (postgres-data vs disk1)

## References

- [KubeVirt Disks Documentation](https://kubevirt.io/user-guide/virtual_machines/disks_and_volumes/)
- [CDI DataVolume Documentation](https://github.com/kubevirt/containerized-data-importer/blob/main/doc/datavolumes.md)
- [Cloud-Init Disk Configuration](https://cloudinit.readthedocs.io/en/latest/topics/examples.html#configure-instances-disks)
