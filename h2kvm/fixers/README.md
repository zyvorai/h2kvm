# Fixers - Post-Migration Customization

This package contains modules for fixing and customizing VMs after migration from source platforms (VMware, Hyper-V, Azure) to KVM/libvirt.

## Architecture (August 2026)

**Primary offline repair path:** GuestKit `run_migrate_repair()` via `h2kvm.core.guestkit_client` — called from `offline_fixer.OfflineFSFix`.

h2kvm retains specialized Python submodules for injectors, Windows, and legacy fallback when GuestKit is unavailable.

```
OfflineFSFix.run()
  ├─ guestkit_client.migrate_repair(apply=True)   # fstab, GRUB, initramfs, hypervisor-aware fixes
  └─ h2kvm injectors (if configured)                # cloud-init, network, firstboot, users, services
```

See [GUESTKIT.md](../../docs/architecture/GUESTKIT.md) for permissions, deployment, and troubleshooting.

## Subsystems

### 1. **Offline Fixing** (`offline_fixer.py`)
Main orchestrator — delegates disk repair to GuestKit; runs configuration injectors when present.

**Workflow stages:**
1. Pre-migration analysis (GuestKit doctor / boot_inspect)
2. GuestKit migrate_repair (apply=True)
3. Configuration injection (cloud-init, network, firstboot, users)
4. Post-migration validation
5. Report generation

### 2. **Configuration Injectors** (`injectors/`)
Customize the migrated VM with user-provided configuration:

- **cloud_init_injector** — cloud-init metadata and user-data
- **firstboot_injector** — one-time firstboot scripts via systemd
- **hostname_config_injector** — hostname and /etc/hosts
- **network_config_injector** — static/DHCP network configuration
- **service_config_injector** — enable/disable/mask systemd services
- **user_config_injector** — users, passwords, SSH keys

### 3. **Bootloader Fixing** (`bootloader/`)
Legacy/fallback path when GuestKit repair is disabled:

- GRUB/GRUB2 menu.lst and grub.cfg fixing
- Root device detection, MBR→GPT, legacy→UEFI

### 4. **Filesystem Fixing** (`filesystem/`)
Legacy/fallback fstab and mount-point handling.

### 5. **Windows Fixing** (`windows/`)
Windows-specific fixes:

- VirtIO driver injection (storage, network, balloon)
- Registry hive manipulation
- Hyper-V/VMware device removal

### 6. **Live Migration** (`live/`)
Fixes applied during live migration (network reconnection, service coordination).

## Configuration

```yaml
backend: guestkit   # default — use GuestKit for offline repair
```

```python
from h2kvm.fixers.offline_fixer import OfflineFSFix

fixer = OfflineFSFix(
    disk_path="/var/lib/h2kvm/out.qcow2",
    target="kvm",
    # optional injectors: network_config, firstboot_config, etc.
)
fixer.run()
```

## See Also

- [GUESTKIT.md](../../docs/architecture/GUESTKIT.md)
- [GuestKit API](../../docs/reference/api/guestkit.md)
- [Troubleshooting](../../docs/guides/troubleshooting.md#permissions-and-ownership)
