# H2KVM Implementation Status

## Disk / Inspect / Repair Layer (GuestKit)

### GuestKit Backend (Default — Production)
- **Status:** Production-ready
- **Package:** `hypersdk-guestkit>=1.1.0`
- **Integration:**
  - `h2kvm/core/guestfs_factory.py` — backend selection (`guestkit`, `guestfs`, `auto`)
  - `h2kvm/core/guestkit_client.py` — facade over GuestKit Python bindings
  - `h2kvm/fixers/offline_fixer.py` — delegates to `guestkit.run_migrate_repair()`
  - `scripts/guestkit_inspect.py` — CLI inspection (replaces `vmcraft_inspect.py`)
- **Capabilities:** doctor, boot_inspect, migrate_plan, migrate_repair, disk conversion
- **Legacy aliases:** `vmcraft`, `namespace` YAML/CLI values map to `guestkit`

### libguestfs Backend (Optional)
- **Status:** Production-ready (compatibility)
- **Use case:** Environments standardized on libguestfs supermin appliance
- **Selection:** `backend: guestfs` or `backend: auto` fallback

### Removed: VMCraft (~96 files)
- Pure-Python disk engine, namespace/LVM subsystems, and parallel managers **removed**
- Functionality superseded by GuestKit

---

## Backend Summary

| Backend | Startup | Memory | Guest Commands | Status |
|---------|---------|--------|----------------|--------|
| **guestkit** (default) | <1s | ~50MB | Via migrate_repair | Production |
| **guestfs** | 3-6s | ~200MB+ | Limited | Optional |
| **auto** | — | — | — | Production |

---

## Migration Pipeline Status

| Stage | Component | Status |
|-------|-----------|--------|
| FETCH | vSphere, AWS, local disk sources | Production |
| FLATTEN | VMDK/OVA flattening | Production |
| INSPECT | GuestKit doctor / boot_inspect | Production |
| PLAN | GuestKit migrate_plan | Production |
| FIX | GuestKit migrate_repair + h2kvm fixers | Production |
| CONVERT | qemu-img / GuestKit DiskConverter | Production |
| VALIDATE | Post-migration validation suite | Production |
| DEPLOY | libvirt, KubeVirt, OpenStack | Production |

---

## Recent Architecture Change (August 2026)

- Deleted VMCraft package and namespace engine subsystems
- GuestKit is the sole disk/inspect/repair backend for new work
- CLI backends: `guestkit`, `guestfs`, `auto`
- Documentation updated across `docs/architecture/`, getting-started, API reference

---

## See Also

- [ARCHITECTURE_SUMMARY.md](../architecture/ARCHITECTURE_SUMMARY.md)
- [GUESTKIT.md](../architecture/GUESTKIT.md)
- [BACKENDS.md](../architecture/BACKENDS.md)
- [PROJECT_STATUS.md](PROJECT_STATUS.md)
