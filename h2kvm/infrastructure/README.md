# Infrastructure - Supporting Services Layer

This package contains supporting infrastructure services used across h2kvm.

## Components

### 1. **Systemd Integration** (`systemd/`)
Integration with systemd for service management and boot configuration:

**Key modules:**
- `boot.py` (1,141 LOC) - Systemd boot integration and firstboot
- `manager.py` - Systemd service manager wrapper
- `unit_generator.py` - Generate systemd unit files

**Features:**
- Firstboot service creation
- Service enable/disable/mask
- Boot target configuration
- Unit file templating
- systemd-nspawn integration

**Example:**
```python
from h2kvm.infrastructure.systemd import SystemdManager

mgr = SystemdManager(guest_handle)
mgr.enable_service("sshd")
mgr.create_firstboot_service(script="/usr/local/bin/setup.sh")
```

### 2. **SSH Utilities** (`ssh/`)
SSH client and key management:

**Key modules:**
- `ssh_client.py` - SSH client wrapper
- `key_manager.py` - SSH key generation and injection

**Features:**
- SSH key injection into authorized_keys
- SSH config file manipulation
- Known_hosts management
- SSHD config updates (disable password auth, etc.)

**Example:**
```python
from h2kvm.infrastructure.ssh import inject_ssh_keys

inject_ssh_keys(
    guest_handle,
    username="admin",
    keys=["ssh-rsa AAAAB3..."]
)
```

### 3. **Hook System** (`hooks/`)
Extensible hook system for custom actions at migration stages:

**Hook types:**
- `pre-migration` - Before migration starts
- `post-conversion` - After disk conversion
- `pre-fixing` - Before offline fixing
- `post-fixing` - After offline fixing
- `post-migration` - After full migration

**Key modules:**
- `hook_types.py` - Hook type definitions
- `hook_runner.py` - Hook execution engine

**Configuration:**
```yaml
hooks:
  post-fixing:
    - type: script
      path: /usr/local/bin/custom-setup.sh
      timeout: 300
    - type: ansible
      playbook: /etc/h2kvm/playbooks/setup.yml
```

**Example:**
```python
from h2kvm.infrastructure.hooks import HookRunner, HookType

runner = HookRunner(logger)
runner.run_hooks(
    hook_type=HookType.POST_FIXING,
    context={"vm_name": "webserver", "disk_path": "/path/to/disk"}
)
```

### 4. **Rollback Support** (`rollback/`)
Snapshot and rollback functionality for safe migrations:

**Features:**
- Pre-migration snapshots
- Incremental checkpoints during migration
- Rollback to previous state on failure
- Snapshot cleanup after successful migration

**Key modules:**
- `snapshot_manager.py` - Snapshot creation/restoration
- `checkpoint.py` - Migration checkpoint tracking

**Example:**
```python
from h2kvm.infrastructure.rollback import SnapshotManager

mgr = SnapshotManager("/path/to/disk.qcow2")

# Create snapshot before risky operation
snapshot_id = mgr.create_snapshot("pre-fixing")

try:
    # Risky operation
    perform_offline_fix()
except Exception:
    # Rollback on error
    mgr.rollback(snapshot_id)
    raise
else:
    # Success - delete snapshot
    mgr.delete_snapshot(snapshot_id)
```

### 5. **Deployers** (`deployers/`)
Deployment tooling for migrated VMs:

**Deployment targets:**
- Libvirt/KVM
- OpenStack
- oVirt/RHV
- Proxmox

**Key module:**
- `libvirt_deployer.py` - Deploy to local libvirt

**Example:**
```python
from h2kvm.infrastructure.deployers import LibvirtDeployer

deployer = LibvirtDeployer(connection_uri="qemu:///system")
deployer.deploy(
    disk_path="/path/to/disk.qcow2",
    vm_name="webserver",
    memory_mb=4096,
    vcpus=2,
    network="default"
)
```

## Common Patterns

### Pattern 1: Systemd Firstboot

```python
from h2kvm.infrastructure.systemd.boot import create_firstboot_service

create_firstboot_service(
    guest_handle,
    service_name="initial-setup",
    exec_start="/usr/local/bin/setup.sh",
    description="Initial VM setup"
)
```

### Pattern 2: Hook Integration

```python
from h2kvm.fixers.offline_fixer import OfflineFSFix
from h2kvm.infrastructure.hooks import HookRunner

# Fixer with hooks
fixer = OfflineFSFix(
    disk_path="/path/to/disk.qcow2",
    hook_runner=HookRunner(logger)
)

# Hooks run automatically at appropriate stages
fixer.run()
```

### Pattern 3: Rollback-Safe Migration

```python
from h2kvm.infrastructure.rollback import with_rollback

@with_rollback("/path/to/disk.qcow2")
def risky_migration():
    # If this raises, disk is automatically rolled back
    convert_disk()
    apply_fixes()
    # Success - snapshot auto-deleted
```

## Configuration

### Hooks Configuration

```yaml
# /etc/h2kvm/hooks.yaml
hooks:
  post-fixing:
    - name: custom-setup
      type: script
      path: /usr/local/bin/setup.sh
      run_as: root
      timeout: 600

  post-migration:
    - name: ansible-configure
      type: ansible
      playbook: /etc/ansible/configure.yml
      inventory: /etc/ansible/hosts
```

### Systemd Templates

```yaml
# /etc/h2kvm/systemd.yaml
systemd:
  firstboot_template: |
    [Unit]
    Description={{ description }}
    After=network.target
    ConditionPathExists=!/var/lib/h2kvm/firstboot-complete

    [Service]
    Type=oneshot
    ExecStart={{ exec_start }}
    ExecStartPost=/usr/bin/touch /var/lib/h2kvm/firstboot-complete

    [Install]
    WantedBy=multi-user.target
```

## Architecture Decisions

### Why Separate Infrastructure Layer?
- **Reusability**: SSH, systemd, hooks used across fixers, operators
- **Testing**: Test infrastructure independently
- **Modularity**: Swap implementations (e.g., cloud-init instead of systemd)
- **Clean separation**: Infrastructure concerns separated from domain logic

### Why Hook System?
- **Extensibility**: Users add custom logic without code changes
- **Integration**: Integrate with external systems (Ansible, Terraform)
- **Flexibility**: Different workflows need different hooks

### Why Rollback Support?
- **Safety**: Migrations can fail; need recovery
- **Testing**: Test risky changes safely
- **Production**: Zero-downtime rollback

## Testing

### Unit Tests
```bash
pytest tests/unit/test_infrastructure/
```

### Integration Tests
```bash
# Systemd integration (requires systemd)
pytest tests/integration/systemd/

# SSH integration (requires SSH daemon)
pytest tests/integration/ssh/

# Hooks integration
pytest tests/integration/test_hook_system.py
```

### E2E Tests
```bash
# Full migration with hooks
./tests/e2e/test_migration_with_hooks.sh
```

## Security Considerations

### SSH Key Injection
- Keys injected with proper permissions (0600)
- authorized_keys file properly secured
- No password authentication enabled by default

### Systemd Services
- Firstboot services run once and disable themselves
- Unit files validated before installation
- Services run with minimal privileges (User=, NoNewPrivileges=)

### Hooks
- Hook scripts validated (checksum, signature)
- Timeout enforcement to prevent hanging
- Sandboxed execution (cgroups, namespaces optional)

## Known Issues

1. **Systemd boot.py size**: 1,141 lines - complex firstboot logic
   - Needs refactoring into smaller modules

2. **Hook timeout handling**: Long-running hooks may be killed
   - Mitigation: Increase timeout, use async hooks

3. **Rollback snapshot size**: Full disk snapshots consume space
   - Mitigation: Use incremental snapshots, cleanup policy

## Future Improvements

- [ ] Add cloud-init integration as alternative to systemd firstboot
- [ ] Implement async hook execution for parallel operations
- [ ] Add hook dependency graph (DAG)
- [ ] Improve rollback with incremental snapshots
- [x] OpenStack Glance deploy (`--deploy-openstack`, `h2kvm/infrastructure/deployers/openstack.py`)
- [ ] Add remote deployers (Proxmox)
- [ ] Implement hook retry logic with exponential backoff
