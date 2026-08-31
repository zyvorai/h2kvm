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

## Remote Deployment (August 2026)

- **Script:** `scripts/deploy-remote.sh` — rsync checkout, pip install, h2kweb, systemd daemon
- **GuestKit dependency:** `hypersdk-guestkit>=1.1.0` on [PyPI](https://pypi.org/project/hypersdk-guestkit/1.1.0/)
- **h2kvm 1.1.0:** [GitHub Release](https://github.com/zyvorai/h2kvm/releases/tag/v1.1.0) (wheel + sdist); PyPI project pending trusted publisher
- **Docs:** [deploy-remote.md](../deployment/deploy-remote.md), [GUESTKIT.md](../architecture/GUESTKIT.md)
- **Validated:** Ubuntu 24.04 lab host — osboxes VMDK → qcow2 → libvirt (`ubuntu-test`)

## Known Deployment Notes

| Topic | Status | Notes |
|-------|--------|-------|
| PyPI `hypersdk-guestkit` 1.1.0 | **Published** | `pip install "hypersdk-guestkit>=1.1.0"` |
| h2kvm 1.1.0 install | GitHub Release wheel | See README; PyPI `h2kvm` not yet configured |
| libvirt qcow2 ownership | Documented | Debian/Ubuntu: `libvirt-qemu:kvm`; RHEL: `qemu:qemu` |
| NBD permissions | Documented | `H2KVM_USE_SUDO=1` or run as root |
| offline_fixer injectors | Fixed | `_has_injectors()` uses correct injector attribute names |

---

## See Also

- [ARCHITECTURE_SUMMARY.md](../architecture/ARCHITECTURE_SUMMARY.md)
- [GUESTKIT.md](../architecture/GUESTKIT.md)
- [BACKENDS.md](../architecture/BACKENDS.md)
- [PROJECT_STATUS.md](PROJECT_STATUS.md)
