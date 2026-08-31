# GuestKit Integration

GuestKit is the default disk inspection and offline repair backend for h2kvm. It replaces the removed VMCraft package.

## Installation

```bash
# PyPI (recommended)
pip install "hypersdk-guestkit>=1.1.0"

# From source
pip install -e /path/to/guestkit
```

**Host tools required:** `qemu-nbd`, `qemu-img`

**Optional:** `python3-libguestfs` when using `backend: guestfs` or `backend: auto` fallback.

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
| `h2kvm/fixers/offline_fixer.py` | Migration repair via `migrate_repair()` |
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

# Low-level GuestFS-compatible handle
g = guestkit_client.open_guest("/path/to/disk.qcow2")
roots = g.inspect_os()
g.shutdown()
```

## CLI Inspection

```bash
# Full doctor report
python3 scripts/guestkit_inspect.py guest.qcow2

# Boot-focused summary
python3 scripts/guestkit_inspect.py guest.qcow2 --boot

# JSON output
python3 scripts/guestkit_inspect.py guest.qcow2 --json
```

## Pipeline Integration

1. **INSPECT** — GuestKit doctor / boot_inspect informs OS and boot analysis
2. **PLAN** — `migrate_plan()` produces hypervisor-aware fix plan
3. **FIX** — `offline_fixer` calls `guestkit.run_migrate_repair()` for fstab, GRUB, initramfs, and related changes

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
| `guestkit` import error | `pip install hypersdk-guestkit` |
| NBD permission denied | Run with `sudo` or grant block-device access |
| Need libguestfs | Set `backend: guestfs` or install supermin appliance |

## See Also

- [BACKENDS.md](BACKENDS.md)
- [GuestKit repository](https://github.com/hypersdk/guestkit)
- [Installation](../getting-started/01-Installation.md)
