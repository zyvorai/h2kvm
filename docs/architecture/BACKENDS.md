# H2KVM Backend Options

H2KVM supports multiple backends for offline guest inspection, disk repair, and filesystem access. **GuestKit** is the default; **libguestfs** remains available for compatibility.

## Overview

| Backend | Speed | Maturity | Use Case |
|---------|-------|----------|----------|
| **guestkit** | Fast (Rust + PyO3) | Production | Default — inspect, plan, repair |
| **guestfs** | Moderate (appliance) | Battle-tested | Maximum libguestfs compatibility |
| **auto** | — | — | Try GuestKit first, fall back to libguestfs |

Legacy YAML/CLI values `vmcraft` and `namespace` map to `guestkit` with a deprecation warning.

## Backend Descriptions

### 1. GuestKit (Default)

**Architecture:**
- Rust Guestfs implementation via `hypersdk-guestkit` PyO3 bindings
- Selected by `h2kvm/core/guestfs_factory.py`
- Facade in `h2kvm/core/guestkit_client.py`
- Offline fixer delegates migration repair to `guestkit.run_migrate_repair()`

**Pros:**
- Fast startup, low memory footprint
- GuestFS-compatible API for existing h2kvm call sites
- Integrated doctor, boot inspect, migrate plan, and repair pipelines
- No libguestfs supermin appliance required

**Cons:**
- Requires `hypersdk-guestkit>=1.1.0` and host tools (`qemu-nbd`, `qemu-img`)
- Linux guests are the primary focus for offline repair

**When to use:**
- All new migrations (default)
- Production offline inspect and repair
- When you want GuestKit doctor/migrate-plan output

**Configuration:**
```yaml
backend: guestkit
```

**Example:**
```python
from pathlib import Path
from h2kvm.fixers.offline_fixer import OfflineFixConfig, OfflineFSFix

config = OfflineFixConfig(
    image=Path("guest.qcow2"),
    backend="guestkit",
    fstab_mode="stabilize-all",
    regen_initramfs=True,
)

fixer = OfflineFSFix(logger, config)
result = fixer.fix()
```

**CLI inspection:**
```bash
python3 scripts/guestkit_inspect.py guest.qcow2
python3 scripts/guestkit_inspect.py guest.qcow2 --boot
```

---

### 2. libguestfs (Optional)

**Architecture:**
- Native `python3-guestfs` bindings
- libguestfs supermin appliance on the host

**Pros:**
- Long track record in virt-v2v-style workflows
- Broad filesystem and guest format support

**Cons:**
- Slower startup (appliance build/load)
- Higher memory use than GuestKit

**When to use:**
- Environments that already standardize on libguestfs
- Troubleshooting GuestKit compatibility issues

**Configuration:**
```yaml
backend: guestfs
```

**Environment override:**
```bash
export H2KVM_GUESTFS_BACKEND=guestfs
```

---

### 3. auto

Tries GuestKit first; falls back to libguestfs when GuestKit is not installed but the libguestfs appliance is available.

```yaml
backend: auto
```

---

## Backend Selection Guide

### Decision Tree

```
Need libguestfs-specific behavior or appliance already deployed?
├─ YES → guestfs
└─ NO  → guestkit (default)
```

### CLI

```bash
h2kvmctl --config migration.yaml --backend guestkit
h2kvmctl --config migration.yaml --backend guestfs
h2kvmctl --config migration.yaml --backend auto
```

---

## Configuration Examples

### Production Migration
```yaml
backend: guestkit
fstab_mode: stabilize-all
regen_initramfs: true
filesystem_repair_enable: true
```

### libguestfs Fallback
```yaml
backend: guestfs
fstab_mode: stabilize-all
regen_initramfs: true
```

---

## Troubleshooting

### GuestKit Not Installed

```
ImportError: GuestKit backend requested but the 'guestkit' Python module is not installed.
```

**Solution:**
```bash
pip install hypersdk-guestkit
# or from source:
pip install -e /path/to/guestkit
```

Ensure `qemu-nbd` and `qemu-img` are on `PATH`.

### libguestfs Appliance Missing

**Solution:**
```bash
# Fedora/RHEL
sudo dnf install libguestfs python3-libguestfs

# Debian/Ubuntu
sudo apt install libguestfs-tools python3-guestfs
```

### Permission Denied on NBD

**Solution:** Run with appropriate privileges for block-device access:
```bash
sudo h2kvmctl --config config.yaml
```

---

## See Also

- [GuestKit Integration Guide](GUESTKIT.md)
- [Architecture Summary](ARCHITECTURE_SUMMARY.md)
- [LVM Backends](LVM_BACKENDS.md)
- [guestfs_factory.py](../../h2kvm/core/guestfs_factory.py)
- [guestkit_client.py](../../h2kvm/core/guestkit_client.py)
