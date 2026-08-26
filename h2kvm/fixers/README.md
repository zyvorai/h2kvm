# Fixers - Post-Migration Customization System

This package contains modules for fixing and customizing VMs after migration from source platforms (VMware, Hyper-V, Azure) to KVM/libvirt.

## Architecture

The fixer system is organized into specialized subsystems:

### 1. **Bootloader Fixing** (`bootloader/`)
- **GRUB configuration**: Detect and fix GRUB/GRUB2 configurations
- **Root device detection**: Update kernel parameters with correct root device
- **Boot conversion**: Convert MBR to GPT, legacy to UEFI
- **Multi-boot support**: Handle dual/multi-boot configurations

**Key modules:**
- `grub.py` (1,376 LOC) - GRUB/GRUB2 menu.lst and grub.cfg fixing
- `fixer.py` - Multi-bootloader abstraction
- `post_conversion.py` - Post-conversion bootloader updates

### 2. **Filesystem Fixing** (`filesystem/`)
- **fstab regeneration**: Rebuild /etc/fstab with correct UUIDs
- **Mount point detection**: Discover and map filesystem mount points
- **XFS UUID fixing**: Handle XFS duplicate UUID issues
- **Partition table updates**: GPT/MBR conversion

**Key modules:**
- `fstab.py` - /etc/fstab parsing and rebuilding
- `fixer.py` - Filesystem abstraction layer

### 3. **Configuration Injectors** (`injectors/`)
Customize the migrated VM with user-provided configuration:

- **cloud_init_injector**: Cloud-init metadata and user-data
- **firstboot_injector**: One-time firstboot scripts via systemd
- **hostname_config_injector**: Set hostname and /etc/hosts entries
- **network_config_injector**: Static/DHCP network configuration
- **service_config_injector**: Enable/disable/mask systemd services
- **user_config_injector**: Create users, set passwords, inject SSH keys

### 4. **Live Migration** (`live/`)
- Fixes applied to running VMs during live migration
- Network reconnection after hypervisor switch
- Service restart coordination

### 5. **Offline Fixing** (`offline/`)
The main orchestrator for comprehensive offline fixing:

**Components:**
- `offline_fixer.py` (2,799 LOC) - Main orchestration class
- Storage stack activation (LUKS, LVM, mdraid, ZFS)
- XFS UUID regeneration with fstab rebuilding
- VMware tools removal
- Network configuration cleanup
- Recovery checkpoint management

**Workflow stages:**
1. Pre-migration analysis
2. Storage stack activation (LUKS/LVM)
3. Filesystem mounting
4. Bootloader fixing
5. Configuration injection
6. Network cleanup
7. Post-migration validation
8. Report generation

### 6. **Windows Fixing** (`windows/`)
Windows-specific fixes for migrations from Hyper-V or VMware:

**Subsystems:**
- `drivers/` - VirtIO driver injection (storage, network, balloon)
- `registry/` - Windows registry manipulation
- `licensing/` - Windows activation preservation
- `virtio/` - VirtIO device enablement
- `fixer.py` - Windows orchestrator

**Key features:**
- Registry hive mounting and editing
- Boot-critical driver injection
- HAL (Hardware Abstraction Layer) updates
- Hyper-V/VMware device removal
- Windows activation data preservation

## Usage Patterns

### Pattern 1: Offline Fixing (Most Common)

```python
from h2kvm.fixers.offline_fixer import OfflineFSFix

# Create fixer with config
fixer = OfflineFSFix(
    disk_path="/path/to/disk.qcow2",
    logger=logger,
    hostname_config_inject={"hostname": "webserver"},
    user_config_inject=[{"username": "admin", "ssh_keys": [...]}],
    service_config_inject={"enable": ["sshd"], "disable": ["bluetooth"]},
)

# Run full fixing workflow
result = fixer.run()
```

### Pattern 2: Individual Injectors

```python
from h2kvm.fixers.injectors import hostname_config_injector

# Use individual injector with launched VMCraft instance
result = hostname_config_injector.inject_hostname_config(
    vmcraft_instance,
    guestfs_instance
)
```

### Pattern 3: Bootloader Fixing

```python
from h2kvm.fixers.bootloader.grub import GrubFixer

fixer = GrubFixer(logger)
fixer.detect_bootloader(guestfs_instance, os_info)
fixer.regenerate_grub_config(guestfs_instance, root_device="/dev/vda1")
```

## Base Classes

### `BaseFixer` (Abstract)
All fixers should inherit from this base:

```python
from h2kvm.fixers.base import BaseFixer

class CustomFixer(BaseFixer):
    def run(self, vmcraft_instance):
        # Implementation
        pass
```

**Methods:**
- `run()` - Main entry point (abstract)
- `validate()` - Pre-flight validation
- `rollback()` - Undo changes on error

## Testing

**Test coverage:**
- Unit tests: `tests/unit/test_fixers/`
- Integration tests: `tests/integration/test_offline_fixer.py`

**Test fixtures:**
- `FakeGuestFS` for mocking guestfs operations
- `FakeLogger` for log capture

## Common Patterns

### Error Handling
All fixers use consistent error handling:

```python
try:
    # Fixer operation
    result = perform_fix()
except GuestFSError as e:
    logger.error(f"guestfs error: {e}")
    return {"success": False, "error": str(e)}
```

### Dry-Run Support
Most injectors support dry-run mode:

```python
fixer = OfflineFSFix(..., dry_run=True)
result = fixer.run()  # No actual changes made
```

### Logging
Structured logging with stage markers:

```python
self.logger.info("=== Stage 1: Storage Activation ===")
# ... operations
self.logger.info("=== Stage 1: Complete ===")
```

## Architecture Decisions

### Why Separate Injectors?
- **Modularity**: Each injector has single responsibility
- **Testing**: Unit test individual injectors independently
- **Reusability**: Use injectors in different workflows (offline/live)
- **Configuration**: User selects only needed injectors

### Why Offline Orchestrator?
- **Complexity**: 8+ stages require coordination
- **Dependencies**: LUKS before LVM, mounting before fixing
- **Recovery**: Checkpoint system needs central state
- **Reporting**: Unified report across all stages

## Known Issues

1. **offline_fixer.py size**: 2,799 lines - needs refactoring into:
   - `luks_manager.py` - LUKS/passphrase handling
   - `xfs_uuid_handler.py` - XFS UUID regeneration
   - `storage_stack.py` - LVM/mdraid/ZFS activation
   - `recovery_checkpoints.py` - Checkpoint management

2. **Duplicate WindowsFixer**: Three classes named `WindowsFixer` in different modules - consolidation needed

3. **BaseFixer not enforced**: Many fixers don't inherit from base class

## Future Improvements

- [ ] Extract LUKS manager from offline_fixer
- [ ] Consolidate Windows fixer classes
- [ ] Add async support for parallel fixing
- [ ] Improve checkpoint system with state machine
- [ ] Add fixer plugin system for custom fixers
