# H2KVM Architecture Summary

## Disk / Inspect / Repair Layer

Offline disk access is provided by **GuestKit** (`hypersdk-guestkit>=1.1.0`), integrated through:

| Component | Role |
|-----------|------|
| `h2kvm/core/guestfs_factory.py` | Backend selection (`guestkit`, `guestfs`, `auto`) |
| `h2kvm/core/guestkit_client.py` | Thin facade over GuestKit Python bindings |
| `h2kvm/fixers/offline_fixer.py` | Delegates repair to `guestkit.run_migrate_repair()` |
| `scripts/guestkit_inspect.py` | CLI disk inspection (replaces `vmcraft_inspect.py`) |

Legacy backend names `vmcraft` and `namespace` in YAML or `H2KVM_GUESTFS_BACKEND` map to `guestkit`.

### Backend Options

| Backend | Role | Status |
|---------|------|--------|
| **guestkit** | Default offline inspect + repair | Production |
| **guestfs** | libguestfs compatibility | Optional |
| **auto** | GuestKit → libguestfs fallback | Production |

---

## Migration Pipeline

```
FETCH → FLATTEN → INSPECT → PLAN → FIX → CONVERT → VALIDATE
                         ↑              ↑
                    GuestKit        GuestKit
                    doctor/         migrate_repair
                    boot_inspect
```

### INSPECT / FIX (GuestKit)

- **doctor** — bootability analysis for target hypervisor
- **boot_inspect** — boot-related guest state summary
- **migrate_plan** — hypervisor-aware migration plan
- **migrate_repair** — apply fstab, GRUB, initramfs, and related fixes

```python
from h2kvm.core import guestkit_client

report = guestkit_client.doctor("guest.qcow2", target="kvm")
plan = guestkit_client.migrate_plan("guest.qcow2", target="kvm")
result = guestkit_client.migrate_repair("guest.qcow2", target="kvm", apply=True)
```

---

## OVF Hardware Parsing & Domain XML Generation

The pipeline extracts hardware resources from OVF/OVA metadata and vSphere VM info, propagating them to libvirt domain XML:

### Data Flow
```
OVF XML → OVF._parse_hardware() → OVF.last_hardware
govc vm.info -json → _fetch_vm_hardware_info() → spec.vm_hardware_info
                                                       ↓
                                              Domain Emitter
                                                       ↓
                                          LinuxDomainConfig/Spec
                                                       ↓
                                            Libvirt Domain XML
```

### Extracted Resources
| Source | Fields |
|--------|--------|
| **OVF XML** | vcpus, memory_mib, nic_count, cpu_topology, secure_boot, os_type, os_description |
| **govc vm.info** | memory_mib, vcpus, nic_count, total_disk_bytes |
| **Guest EFI scan** | Secure Boot shim detection (shimx64.efi) |
| **Guest fstab** | Swap partition size (memory estimation fallback) |

---

## Recommended Defaults

### Production Migrations
```yaml
backend: guestkit
fstab_mode: stabilize-all
regen_initramfs: true
```

### libguestfs Environments
```yaml
backend: guestfs
```

---

## Architecture Evolution

### Previous: VMCraft (removed)
Pure-Python disk engine with namespace/LVM subsystems — **removed** (~96 files). Capabilities moved to GuestKit.

### Current: GuestKit
Rust Guestfs + repair pipelines exposed to h2kvm via PyO3. h2kvm orchestrates migration; GuestKit owns disk inspect/repair semantics.

---

## See Also

- [BACKENDS.md](BACKENDS.md) — Backend comparison and configuration
- [GUESTKIT.md](GUESTKIT.md) — Integration guide
- [LVM_BACKENDS.md](LVM_BACKENDS.md) — LVM activation during offline fixes
- [Full Architecture](../reference/architecture.md)
