# HyperConversion CRD API Reference

Complete reference for the HyperConversion Custom Resource Definition.

## API Group

- **Group**: `hyper2kvm.io`
- **Version**: `v1alpha1`
- **Kind**: `HyperConversion`

## Resource Scope

- **Namespaced**: Yes
- **Short Names**: `hc`, `hconv`

## HyperConversion

A HyperConversion represents an end-to-end VM disk conversion and KubeVirt VirtualMachine creation workflow.

### Metadata

Standard Kubernetes metadata fields:

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: my-conversion      # Required: unique name
  namespace: default       # Required: target namespace
  labels:                  # Optional: custom labels
    app: my-app
  annotations:             # Optional: custom annotations
    description: "Production VM migration"
```

### Spec

The desired state of the HyperConversion.

#### HyperConversionSpec

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source` | [SourceSpec](#sourcespec) | Yes | Source disk configuration |
| `storage` | [StorageSpec](#storagespec) | Yes | Target storage configuration |
| `vm` | [VMSpec](#vmspec) | No | VirtualMachine specification (omit for disk-only conversion) |
| `conversion` | [ConversionOptions](#conversionoptions) | No | Conversion behavior options |

#### SourceSpec

Defines the source disk image location and format.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `url` | string | Yes | - | HTTP/HTTPS/S3 URL of source disk |
| `format` | string | No | `qcow2` | Disk format: `vmdk`, `vdi`, `vhd`, `vhdx`, `qcow2`, `raw` |
| `checksum` | string | No | - | Checksum for validation: `sha256:xxx` or `md5:xxx` |
| `secretRef` | LocalObjectReference | No | - | Secret containing authentication credentials |

**URL Formats**:
- HTTP/HTTPS: `https://example.com/disk.vmdk`
- S3: `s3://bucket-name/path/to/disk.vhdx`

**Authentication Secret Format**:

For HTTP Basic Auth:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: http-credentials
type: Opaque
stringData:
  vc_user: myuser
  password: mypassword
```

For S3:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: s3-credentials
type: Opaque
stringData:
  accessKeyID: AKIAIOSFODNN7EXAMPLE
  secretAccessKey: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

#### StorageSpec

Defines target storage configuration.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `storageClass` | string | No | Cluster default | StorageClass name for PVC |
| `size` | resource.Quantity | No | Auto-detect | Requested storage size (e.g., `20Gi`) |
| `accessMode` | PersistentVolumeAccessMode | No | `ReadWriteOnce` | PVC access mode |
| `volumeMode` | PersistentVolumeMode | No | `Filesystem` | Volume mode: `Filesystem` or `Block` |

**Access Modes**:
- `ReadWriteOnce` (RWO): Single node read-write
- `ReadWriteMany` (RWX): Multi-node read-write
- `ReadOnlyMany` (ROX): Multi-node read-only

**Size Auto-Detection**:
If `size` is omitted, the operator attempts to detect size via HTTP HEAD request. If detection fails, defaults to `20Gi`.

#### VMSpec

Defines the KubeVirt VirtualMachine configuration. Omit this field for disk-only conversion.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | No | HyperConversion name | VirtualMachine name |
| `cpu` | [CPUSpec](#cpuspec) | Yes | - | CPU configuration |
| `memory` | resource.Quantity | Yes | - | Memory allocation (e.g., `4Gi`) |
| `firmware` | string | No | `bios` | Firmware type: `bios`, `uefi`, `uefi-secure` |
| `networks` | [][NetworkSpec](#networkspec) | No | Pod network | Network interfaces |
| `evictionStrategy` | string | No | `LiveMigrateIfPossible` | Eviction strategy |
| `runStrategy` | string | No | `Always` | Run strategy |
| `cloudInit` | [CloudInitSpec](#cloudinitspec) | No | - | Cloud-init configuration |

**Firmware Types**:
- `bios`: Legacy BIOS boot
- `uefi`: UEFI boot
- `uefi-secure`: UEFI with Secure Boot (required for Windows 11, Windows Server 2022)

**Eviction Strategies**:
- `LiveMigrate`: Always live migrate on node drain
- `LiveMigrateIfPossible`: Live migrate if possible, otherwise block eviction
- `None`: Do not migrate (VM is shut down on node drain)

**Run Strategies**:
- `Always`: Always keep VM running
- `RerunOnFailure`: Restart on crash
- `Manual`: Manual start/stop
- `Halted`: Keep VM stopped

#### CPUSpec

Defines CPU topology.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `cores` | int32 | Yes | - | Number of CPU cores (1-128) |
| `sockets` | int32 | No | 1 | Number of CPU sockets |
| `threads` | int32 | No | 1 | Number of threads per core |

**Example**:
```yaml
cpu:
  cores: 4      # 4 cores
  sockets: 2    # 2 sockets
  threads: 2    # Hyperthreading
# Total vCPUs: 4 * 2 * 2 = 16
```

#### NetworkSpec

Defines a network interface.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | - | Interface name |
| `type` | string | No | `pod` | Network type: `pod`, `bridge`, `sriov`, `multus` |
| `networkName` | string | No | - | NetworkAttachmentDefinition name (for `bridge`/`multus`) |
| `macAddress` | string | No | Auto-generated | MAC address |
| `model` | string | No | `virtio` | NIC model: `virtio`, `e1000`, `e1000e`, `rtl8139` |

**Network Types**:
- `pod`: Default pod network with masquerade
- `bridge`: Bridge network (requires Multus NetworkAttachmentDefinition)
- `multus`: Multus network (requires NetworkAttachmentDefinition)
- `sriov`: SR-IOV network

**NIC Models**:
- `virtio`: Paravirtualized (best performance)
- `e1000`/`e1000e`: Intel emulation (Windows compatibility)
- `rtl8139`: Realtek emulation (legacy support)

#### CloudInitSpec

Defines cloud-init configuration.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `userData` | string | No | Inline cloud-init user data |
| `userDataSecretRef` | LocalObjectReference | No | Secret containing user data |
| `networkData` | string | No | Inline cloud-init network data |
| `networkDataSecretRef` | LocalObjectReference | No | Secret containing network data |

**Example Inline User Data**:
```yaml
cloudInit:
  userData: |
    #cloud-config
    hostname: my-vm
    users:
      - name: admin
        sudo: ALL=(ALL) NOPASSWD:ALL
        ssh_authorized_keys:
          - ssh-rsa AAAAB3...
```

**Example Secret Reference**:
```yaml
cloudInit:
  userDataSecretRef:
    name: my-cloudinit-secret
```

Secret format:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: my-cloudinit-secret
type: Opaque
stringData:
  userdata: |
    #cloud-config
    ...
```

#### ConversionOptions

Defines conversion behavior (optional, for advanced use cases).

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `compression` | string | No | `zstd` | Compression type: `zstd`, `zlib`, `none` |
| `offlineFixes` | bool | No | `false` | Enable offline disk fixes (requires Python worker) |
| `timeout` | int32 | No | 60 | Timeout in minutes (5-1440) |

**Compression Types**:
- `zstd`: Modern, fast compression (recommended)
- `zlib`: Compatible compression
- `none`: No compression (larger disk size)

### Status

The observed state of the HyperConversion.

#### HyperConversionStatus

| Field | Type | Description |
|-------|------|-------------|
| `phase` | string | Current phase: `Pending`, `Uploading`, `Converting`, `CreatingVM`, `Ready`, `Failed` |
| `progress` | int32 | Completion percentage (0-100) |
| `dataVolumeName` | string | Name of created DataVolume |
| `virtualMachineName` | string | Name of created VirtualMachine |
| `uploadProgress` | [UploadProgressStatus](#uploadprogressstatus) | Detailed upload progress |
| `startTime` | metav1.Time | Conversion start timestamp |
| `completionTime` | metav1.Time | Conversion completion timestamp |
| `conditions` | []metav1.Condition | Status conditions |
| `message` | string | Human-readable status message |

#### UploadProgressStatus

| Field | Type | Description |
|-------|------|-------------|
| `bytesUploaded` | int64 | Bytes uploaded so far |
| `totalBytes` | int64 | Total size in bytes |
| `speed` | int64 | Current upload speed (bytes/sec) |
| `lastUpdateTime` | metav1.Time | Last progress update |

#### Conditions

Standard Kubernetes conditions:

| Type | Status | Reason | Description |
|------|--------|--------|-------------|
| `DataVolumeReady` | True/False | `UploadComplete`/`UploadFailed` | DataVolume is ready |
| `VMReady` | True/False | `VMCreated`/`VMCreateFailed` | VirtualMachine is ready |
| `ConversionComplete` | True/False | `ConversionComplete`/`ConversionFailed` | Overall conversion status |

## Examples

### Minimal Example

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: minimal
spec:
  source:
    url: "https://example.com/disk.qcow2"
  storage:
    size: 20Gi
  vm:
    cpu:
      cores: 2
    memory: 4Gi
```

### Complete Example

```yaml
apiVersion: hyper2kvm.io/v1alpha1
kind: HyperConversion
metadata:
  name: complete-example
  namespace: production
  labels:
    app: web-server
    environment: production
spec:
  source:
    url: "s3://my-bucket/ubuntu-22.04.vmdk"
    format: vmdk
    checksum: "sha256:abc123..."
    secretRef:
      name: s3-credentials

  storage:
    storageClass: fast-ssd
    size: 100Gi
    accessMode: ReadWriteOnce
    volumeMode: Filesystem

  vm:
    name: web-server-01

    cpu:
      cores: 8
      sockets: 2
      threads: 1

    memory: 32Gi
    firmware: uefi
    runStrategy: Always
    evictionStrategy: LiveMigrate

    networks:
    - name: default
      type: pod
      model: virtio

    - name: management
      type: multus
      networkName: mgmt-network
      model: virtio
      macAddress: "52:54:00:12:34:56"

    cloudInit:
      userData: |
        #cloud-config
        hostname: web-server-01
        users:
          - name: admin
            sudo: ALL=(ALL) NOPASSWD:ALL
            ssh_authorized_keys:
              - ssh-rsa AAAAB3...

  conversion:
    compression: zstd
    offlineFixes: false
    timeout: 120
```

## See Also

- [Getting Started Guide](getting-started.md)
- [Examples](examples.md)
- [Operator README](../../operator/README.md)
