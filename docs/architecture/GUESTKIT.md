# GuestKit Integration

GuestKit is the default disk inspection and offline repair backend for h2kvm. It replaces the removed VMCraft package. Offline fstab, GRUB, initramfs, and hypervisor-aware fixes run through **`guestkit.run_migrate_repair()`** (Rust/PyO3), not a pure-Python fix engine.

## Installation

```bash
# PyPI (recommended) — 1.1.0+ includes assurance + migrate_repair bindings
pip install "hypersdk-guestkit>=1.1.0"

# From source (development only)
cd /path/to/guestkit
pip install maturin
PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 maturin build \
  --release --features python-bindings --out dist
pip install dist/hypersdk_guestkit-*.whl
```

**Host tools required:** `qemu-nbd`, `qemu-img`, `losetup`

**Optional:** `python3-libguestfs` when using `backend: guestfs` or `backend: auto` fallback.

**Deploy both projects to a lab host:** see [deploy-remote.md](../deployment/deploy-remote.md).

## Architecture

```
h2kvm pipeline
    │
    ├─ guestfs_factory.create_guestfs(backend="guestkit")
    │       └─ guestkit.Guestfs()          # GuestFS-compatible handle
    │
    └─ guestkit_client.*                   # High-level operations
            ├─ doctor()
            ├─ boot_inspect()
            ├─ migrate_plan()
            ├─ migrate_repair()  ◄── offline_fixer delegates here
            └─ convert_disk()
```

| Module | Purpose |
|--------|---------|
| `h2kvm/core/guestfs_factory.py` | Backend factory; legacy `vmcraft`/`namespace` → `guestkit` |
| `h2kvm/core/guestkit_client.py` | Facade over GuestKit Python API |
| `h2kvm/fixers/offline_fixer.py` | Migration repair via `migrate_repair()`; injectors for cloud-init, network, firstboot |
| `scripts/guestkit_inspect.py` | Standalone inspect CLI |

## Configuration

```yaml
# /etc/h2kvm/config.yaml or per-migration YAML
backend: guestkit
```

```bash
# CLI
h2kvmctl --config migration.yaml --backend guestkit

# Environment
export H2KVM_GUESTFS_BACKEND=guestkit
```

## Python API

```python
from h2kvm.core import guestkit_client

# Bootability doctor
report = guestkit_client.doctor("/path/to/disk.qcow2", target="kvm", explain=True)
print(report["bootability"]["score"], report["bootability"]["blockers"])

# Boot state summary
boot = guestkit_client.boot_inspect("/path/to/disk.qcow2", target="kvm")

# Migration plan (dry-run)
plan = guestkit_client.migrate_plan("/path/to/disk.qcow2", target="kvm", export_fix_plan=True)

# Apply repairs (used by offline fixer)
result = guestkit_client.migrate_repair(
    "/path/to/disk.qcow2",
    target="kvm",
    apply=True,
    verbose=True,
)
print(result["message"], result.get("applied"))

# Low-level GuestFS-compatible handle
g = guestkit_client.open_guest("/path/to/disk.qcow2")
roots = g.inspect_os()
g.shutdown()
```

Direct module access (same engine):

```python
import guestkit
guestkit.run_migrate_repair("disk.qcow2", target="kvm", apply=True)
```

Full API reference: [docs/reference/api/guestkit.md](../reference/api/guestkit.md).

## CLI Inspection

```bash
# Full doctor report
python3 scripts/guestkit_inspect.py guest.qcow2

# Boot-focused summary
python3 scripts/guestkit_inspect.py guest.qcow2 --boot

# JSON output
python3 scripts/guestkit_inspect.py guest.qcow2 --json

# Standalone GuestKit CLI (deploy separately)
guestkit doctor guest.qcow2 --target kvm --explain
```

## Pipeline Integration

1. **INSPECT** — GuestKit doctor / boot_inspect informs OS and boot analysis
2. **PLAN** — `migrate_plan()` produces hypervisor-aware fix plan
3. **FIX** — `offline_fixer` calls `guestkit.run_migrate_repair()` for fstab, GRUB, initramfs, and related changes
4. **CONVERT** — qemu-img flatten/compress; optional GuestKit `DiskConverter`
5. **DEPLOY** — libvirt / KubeVirt import

## Permissions and ownership

GuestKit and h2kvm need to attach disk images via NBD or loop devices. On most Linux hosts this requires **root** or **passwordless sudo**.

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Permission denied` on `/dev/nbd*` | Non-root user | Run with `sudo`, or set `H2KVM_USE_SUDO=1` |
| `Operation not permitted` on loop mount | Missing `CAP_SYS_ADMIN` | Use sudo / add user to appropriate groups |
| QEMU cannot read output qcow2 | Directory mode too restrictive | Ensure `/var/lib/h2kvm` is **755** (deploy script sets this) |
| libvirt import fails after convert | Wrong qcow2 owner | Use **`libvirt-qemu:kvm`** on Debian/Ubuntu, **`qemu:qemu`** on RHEL-family |

### libvirt qcow2 ownership (Debian / Ubuntu)

After conversion, libvirt expects the image owned by the hypervisor user:

```bash
sudo chown libvirt-qemu:kvm /var/lib/h2kvm/demo/ubuntu-test/ubuntu-test.qcow2
sudo virsh define /path/to/domain.xml
sudo virsh start ubuntu-test
```

On RHEL / Alma / Rocky, the user is typically `qemu:qemu`.

### Runtime directories

| Path | Purpose | Recommended mode |
|------|---------|------------------|
| `/var/lib/h2kvm` | Output disks, virtio-win ISO | `755` (world-readable for QEMU) |
| `/run/h2kvm` | PID files, sockets | `755` |
| `~/.deployments/h2kvm` | Remote deploy checkout | user-owned |

### Sudo wrapper

When running h2kvm as a non-root operator:

```bash
export H2KVM_USE_SUDO=1
h2kvmctl local --vmdk vm.vmdk --to-output /var/lib/h2kvm/out.qcow2
```

## Backends

| Value | Behavior |
|-------|----------|
| `guestkit` | GuestKit only (default) |
| `guestfs` | Native libguestfs |
| `auto` | GuestKit, then libguestfs |
| `vmcraft`, `namespace` | Deprecated aliases → `guestkit` |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `guestkit` import error | `pip install "hypersdk-guestkit>=1.1.0"` |
| Wrong / old wheel | `pip install -U "hypersdk-guestkit>=1.1.0"`; verify `guestkit.__version__` |
| NBD permission denied | Run with `sudo` or `H2KVM_USE_SUDO=1` |
| Need libguestfs | Set `backend: guestfs` or install supermin appliance |
| `'OfflineFSFix' object has no attribute ...` | Upgrade h2kvm (injector attribute fix in offline_fixer) |
| VM defined but won't start | Check qcow2 ownership (`libvirt-qemu:kvm` vs `qemu:qemu`) |

## Validated lab workflow

Tested on Ubuntu 24.04 host (`175.110.122.71`):

1. Deploy GuestKit CLI + h2kvm via `deploy-remote.sh`
2. Download osboxes.org Ubuntu 24.04 VMDK
3. `scripts/demo-libvirt.sh ubuntu2404.vmdk ubuntu-test`
4. GuestKit repair applies 4+ offline operations
5. libvirt domain `ubuntu-test` boots at `192.168.122.x` (default login: `osboxes` / `osboxes.org`)

## See Also

- [BACKENDS.md](BACKENDS.md)
- [deploy-remote.md](../deployment/deploy-remote.md)
- [GuestKit API reference](../reference/api/guestkit.md)
- [Troubleshooting — permissions](../guides/troubleshooting.md#permissions-and-ownership)
- [GuestKit repository](https://github.com/hypersdk/guestkit)
- [GuestKit h2kvm integration](https://github.com/hypersdk/guestkit/blob/main/docs/features/hyper2kvm-integration.md)
