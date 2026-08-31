# GuestKit Python API (h2kvm facade)

h2kvm does not re-implement GuestKit disk logic. It delegates offline inspect and repair to the **`hypersdk-guestkit`** PyPI package via `h2kvm.core.guestkit_client`.

For the full GuestKit API (CLI, Rust, assurance types), see the [GuestKit repository](https://github.com/hypersdk/guestkit) and [GuestKit Python bindings](https://github.com/hypersdk/guestkit/blob/main/docs/user-guides/python-bindings.md).

## Installation

```bash
pip install "hypersdk-guestkit>=1.1.0"
```

## h2kvm facade (`guestkit_client`)

```python
from h2kvm.core import guestkit_client

# Bootability assessment
report = guestkit_client.doctor("/path/to/disk.qcow2", target="kvm", explain=True)
score = report["bootability"]["score"]

# Boot-focused summary
boot = guestkit_client.boot_inspect("/path/to/disk.qcow2", target="kvm")

# Dry-run migration plan
plan = guestkit_client.migrate_plan(
    "/path/to/disk.qcow2",
    target="kvm",
    export_fix_plan=True,
)

# Apply offline repairs (used by OfflineFSFix)
result = guestkit_client.migrate_repair(
    "/path/to/disk.qcow2",
    target="kvm",
    apply=True,
    verbose=True,
)
print(result["message"], result.get("applied"))
```

## Direct GuestKit module (v1.1.0+)

When not going through h2kvm:

```python
import guestkit

guestkit.run_doctor("disk.qcow2", target="kvm")
guestkit.run_migrate_repair("disk.qcow2", target="kvm", apply=False)  # dry-run
guestkit.run_migrate_repair("disk.qcow2", target="kvm", apply=True)    # apply fixes
```

| Function | CLI equivalent | Purpose |
|----------|------------------|---------|
| `run_doctor` | `guestkit doctor` | Bootability score, blockers, evidence |
| `run_boot_inspect` | boot-inspect | OS release, fstab, bootloader summary |
| `run_migrate_plan` | `guestkit migrate-plan` | Hypervisor-aware fix plan |
| `run_repair_plan` | `guestkit repair --fix boot` | Repair plan with before/after scores |
| `run_migrate_repair` | `guestkit migrate-repair` | **Primary h2kvm offline fix path** |

Valid `target` values: `kvm`, `proxmox`, `qemu`, `hyperv`, `aws`, `azure`, `gcp`, `cloud`, `kubevirt`.

## Low-level GuestFS handle

```python
g = guestkit_client.open_guest("/path/to/disk.qcow2")
roots = g.inspect_os()
g.shutdown()
```

## Configuration in h2kvm

```yaml
backend: guestkit   # default
```

Legacy aliases `vmcraft` and `namespace` map to `guestkit`.

Environment: `H2KVM_GUESTFS_BACKEND=guestkit`

## Pipeline wiring

```
offline_fixer.OfflineFSFix.run()
  └─ _uses_guestkit_repair() → guestkit_client.migrate_repair(apply=True)
       └─ guestkit.run_migrate_repair()   # PyO3 / Rust engine
```

If GuestKit is unavailable, h2kvm falls back to legacy Python fixers (fstab, GRUB, initramfs submodules).

## See also

- [GUESTKIT.md](../../architecture/GUESTKIT.md) — architecture and troubleshooting
- [BACKENDS.md](../../architecture/BACKENDS.md) — backend comparison
- [GuestKit h2kvm integration](https://github.com/hypersdk/guestkit/blob/main/docs/features/hyper2kvm-integration.md)
