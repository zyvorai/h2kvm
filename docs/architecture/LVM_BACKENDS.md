# LVM Backend Architecture

H2KVM provides three backend options for LVM operations during offline guest fixes, each with different trade-offs between speed, security, and reliability.

All backends support **container isolation** (enabled by default), which runs LVM discovery inside a hardened podman/docker container for safe VG scanning without touching host LVM metadata.

## Container-Isolated LVM Activation

Container isolation is the default LVM activation strategy. It uses a two-phase approach that separates discovery (container) from activation (host), ensuring device-mapper tables and udev events are always processed natively.

### How It Works

```
┌──────────────────────────────────────────────────────────────────┐
│                     h2kvmctl CLI Pipeline                        │
│                                                                  │
│  1. qemu-nbd connects disk image to /dev/nbdX                   │
│  2. Container isolation activates LVM (two-phase)                │
│  3. Host mounts filesystems                                      │
│  4. Offline fixes (fstab, grub, initramfs)                       │
│  5. Unmount + deactivate + disconnect                            │
└──────────────────────────────────────────────────────────────────┘
```

#### Phase 1: Container-Isolated VG Discovery

A hardened container (podman or docker, auto-detected) scans the NBD device for LVM volume groups. The container has a strict device filter baked into `/etc/lvm/lvm.conf` that only permits the assigned NBD device — host disks are invisible.

```
┌─────────────────────────────────────────────┐
│  Container (podman/docker)                  │
│                                             │
│  /etc/lvm/lvm.conf:                         │
│    filter = ["a|^/dev/nbd1|", "r|.*|"]      │
│    global_filter = ["a|^/dev/nbd1|","r|.*|"]│
│    udev_sync = 0                            │
│    locking_type = 0                         │
│                                             │
│  Commands:                                  │
│    pvscan --cache    → prime LVM cache      │
│    vgscan --cache    → scan for VGs         │
│    vgs --noheadings  → output VG names      │
│                                             │
│  Capabilities (no --privileged):            │
│    --cap-add=SYS_ADMIN   (DM ioctls)       │
│    --cap-add=SYS_RAWIO   (block I/O)       │
│    --cap-add=MKNOD       (device nodes)    │
│    --network=none        (no network)       │
│                                             │
│  Devices passed through:                    │
│    --device=/dev/nbdX                       │
│    --device=/dev/nbdXp*  (partitions)       │
│    --device=/dev/mapper/control             │
│                                             │
│  Private tmpfs mounts:                      │
│    /etc/lvm, /var/lib/lvm, /run/lvm         │
│                                             │
│  Output: "rhel" (VG name on stdout)         │
└─────────────────────────────────────────────┘
```

The container performs **discovery only** — no `vgchange -ay` runs inside the container. This avoids cross-namespace device-mapper mismatches where DM tables created inside a container reference device contexts that the host cannot access.

#### Phase 2: Host-Side VG Activation

The discovered VG names are activated on the host using the same strict device filter. This ensures device-mapper tables, udev events, and `/dev/mapper/` nodes are all created natively in the host context.

```
┌─────────────────────────────────────────────┐
│  Host                                       │
│                                             │
│  1. Create isolated LVM_SYSTEM_DIR          │
│     /tmp/h2kvm-lvm-<pid>/               │
│                                             │
│  2. Prime host LVM cache (filtered)         │
│     pvscan --cache --config '<filter>'      │
│                                             │
│  3. Deactivate stale VGs (from prior runs)  │
│     vgchange -an <vg>                       │
│                                             │
│  4. Activate VGs with strict device filter  │
│     vgchange -ay --config '<filter>' <vg>   │
│                                             │
│  5. Settle devices                          │
│     dmsetup mknodes                         │
│     udevadm settle                          │
│     200ms propagation delay                 │
│                                             │
│  Result:                                    │
│     /dev/mapper/rhel-root  → XFS            │
│     /dev/mapper/rhel-swap  → swap           │
└─────────────────────────────────────────────┘
```

The strict device filter used on both phases:

```
devices {
  filter=["a|^/dev/nbd1|","r|.*|"]
}
global {
  locking_type=0
}
```

This regex accepts only `/dev/nbd1` and its partitions (`/dev/nbd1p1`, `/dev/nbd1p2`, etc.) and rejects everything else, including host disks.

#### Why Two Phases?

Running `vgchange -ay` inside the container creates device-mapper table entries at the kernel level, but the host's udev never processes them. The result: `/dev/mapper/rhel-root` exists on the host but the DM mapping references a container-side device context, causing "can't read superblock" errors on mount.

The two-phase design eliminates this class of bugs entirely:

| Step | Where | Why |
|------|-------|-----|
| pvscan + vgs | Container | Isolated scan, no host LVM pollution |
| vgchange -ay | Host | Native DM tables, native udev, native device nodes |
| mount | Host | DM mapping is correct, superblock readable |

### Container Image

On first use, a container image `localhost/h2kvm-lvm:latest` is automatically built and cached:

```dockerfile
FROM registry.fedoraproject.org/fedora-minimal:latest
RUN microdnf install -y --nodocs --setopt=install_weak_deps=0 \
    lvm2 device-mapper && microdnf clean all
```

The image is ~50MB and reused for all subsequent runs. Builds are triggered only once per host.

### Container Runtime Detection

The runtime is auto-detected at startup:

1. Check for `podman` in PATH (preferred)
2. Fall back to `docker` if podman is not available
3. Raise an error if neither is found

This makes the tool universal across environments — works on Fedora/RHEL (podman) and Ubuntu/Debian (docker) without configuration.

### Configuration

Container isolation is enabled by default. To configure:

**YAML config:**
```yaml
# Enable (default)
container_isolation: true

# Disable (fall back to host-only LVM with device filter)
container_isolation: false
```

**CLI flags:**
```bash
# Enable (default)
sudo ./h2kvmctl --config migration.yaml --container-isolation

# Disable
sudo ./h2kvmctl --config migration.yaml --no-container-isolation
```

### Example Log Output

```
INFO  Scanning LVM via container (podman) on /dev/nbd1
INFO  Container scan found 1 VG(s): rhel
INFO  Activated VG on host: rhel
INFO  Storage stack activated (1.21s)
INFO  Found 2 LVs on /dev/nbd1: ['/dev/mapper/rhel-root', '/dev/mapper/rhel-swap']
INFO  Mounted root at / using /dev/mapper/rhel-root
```

### Stale VG Handling

If a VG name (e.g., `rhel`) was activated in a previous run on a different NBD device, the DM mapping becomes stale. Before activation, the pipeline runs `vgchange -an <vg>` to deactivate stale mappings, then re-activates with the current device filter. This ensures the DM table always maps to the correct NBD device.

---

## Offline Guest Fixes

After LVM activation and root filesystem mount, the pipeline applies offline fixes to prepare the guest for KVM:

### 1. fstab Stabilization

Converts unstable device references (`/dev/mapper/rhel-root`, `/dev/sda1`) to stable UUID-based references:

```
Before: /dev/mapper/rhel-root   /    xfs  defaults  0 0
After:  UUID=c8dc0e34-c26b-...  /    xfs  defaults  0 0
```

Modes: `stabilize-all` (default), `bypath-only`, `noop`

### 2. GRUB Bootloader Repair

- Updates `root=` in `/etc/default/grub` and `/boot/grub2/grub.cfg` to match the new UUID
- Runs `grub2-mkconfig` to regenerate boot configuration
- Injects serial console (`console=ttyS0,115200`) for `virsh console` access

### 3. initramfs Rebuild

Rebuilds the initramfs with virtio drivers required for KVM:

```bash
dracut -f --kver <kernel-version> \
  --add-drivers "virtio_blk virtio_scsi virtio_net nvme ahci sd_mod xts" \
  --add "lvm dm"
```

This ensures the guest can boot with virtio disk and network controllers.

### 4. Additional Fixes

- XFS UUID regeneration (prevents duplicate UUIDs from cloned VMs)
- Network config sanitization (removes VMware-specific MAC bindings)
- VMware tools masking (`vmtoolsd.service`, `vgauthd.service`)
- Machine-ID reset for firstboot regeneration
- LVM filter fix (removes restrictive host-side filter from guest)
- Auto-grow configuration for root filesystem

---

## Backend Options

LVM activation during offline fixes runs through the selected disk backend. **GuestKit** is the default.

### 1. **guestkit** (Default)

```yaml
backend: guestkit
```

GuestKit (`hypersdk-guestkit`) provides GuestFS-compatible disk access via Rust + PyO3. LVM discovery and activation use GuestKit's storage stack with optional container-isolated VG scanning (see above).

**Performance:**
- Startup: < 1 second
- LVM activation: 1-2 seconds (with container isolation)
- Mount operations: < 1 second

---

### 2. **guestfs** (Optional)

```yaml
backend: guestfs
```

Native libguestfs backend. Use when GuestKit is unavailable or libguestfs is required for compatibility.

---

### 3. **auto**

```yaml
backend: auto
```

Try GuestKit first; fall back to libguestfs when the appliance is available.

---

## Backend Comparison Matrix

| Feature | guestkit | guestfs |
|---------|----------|---------|
| **Reliability** | Production | Production |
| **Speed** | < 1s startup | 3-6s startup (appliance) |
| **Security** | Container + device filter | libguestfs isolation |
| **Memory** | ~50 MB | ~200+ MB |
| **Container Isolation** | Podman/Docker (LVM scan) | N/A |
| **Host Isolation** | Strict device filter | Appliance-based |

---

## Configuration

### Per-Migration YAML

```yaml
cmd: local
vmdk: ./disk.vmdk
output_dir: ./output
to_output: migrated.qcow2

backend: guestkit
container_isolation: true   # default; set false to disable

fstab_mode: stabilize-all
regen_initramfs: true
compress: true
```

### Python API

```python
from h2kvm.fixers.offline_fixer import OfflineFixConfig, OfflineFSFix

config = OfflineFixConfig(
    image=Path("disk.qcow2"),
    backend="guestkit",
    container_isolation=True,
    fstab_mode="stabilize-all",
    regen_initramfs=True,
)

fixer = OfflineFSFix(logger, config)
fixer.run()
```

---

## Troubleshooting

### Container Isolation Not Working

```bash
# Check container runtime
which podman docker

# Test container image
podman image exists localhost/h2kvm-lvm:latest
# or
docker image inspect localhost/h2kvm-lvm:latest

# Rebuild image manually
podman build -t localhost/h2kvm-lvm:latest -f - <<'EOF'
FROM registry.fedoraproject.org/fedora-minimal:latest
RUN microdnf install -y --nodocs lvm2 device-mapper && microdnf clean all
EOF
```

### Superblock Errors After Mount

If you see "can't read superblock on /dev/mapper/...":
1. Stale DM mappings from a prior run — the pipeline handles this automatically with `vgchange -an` before activation
2. If persistent, manually clean up: `sudo vgchange -an <vg> && sudo dmsetup remove_all`

### LVM Tools Not Available

```bash
# Check host LVM tools (needed for Phase 2)
which vgscan vgchange pvscan dmsetup udevadm

# Check NBD module
lsmod | grep nbd
sudo modprobe nbd max_part=16
```

---

## See Also

- [GUESTKIT.md](GUESTKIT.md) - GuestKit integration guide
- [BACKENDS.md](BACKENDS.md) - Backend selection
- [guestfs_factory.py](../../h2kvm/core/guestfs_factory.py) - Backend factory
- [guestkit_client.py](../../h2kvm/core/guestkit_client.py) - GuestKit facade
