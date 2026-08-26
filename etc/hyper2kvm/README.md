# Hyper2KVM Configuration Directory

This directory contains sample configuration files for hyper2kvm.

## Installation

During package installation, these files are copied to `/etc/hyper2kvm/`:

```bash
# RPM/DNF
sudo dnf install hyper2kvm

# Debian/Ubuntu
sudo apt install hyper2kvm
```

## Configuration Files

### System-Wide Configuration

**`/etc/hyper2kvm/config.yaml`** - Main system configuration

This file contains:

- **Container isolation** (`container_isolation: true` by default) -- runs LVM activation inside Podman/Docker for safe VG scanning without touching host LVM metadata
- **Allowed directories** for VM image access (security)
- **Conversion settings** (cache directory, size limits)
- **Offline fix backend** (`backend: vmcraft` by default) -- pure Python engine for VM manipulation
- **Default libvirt settings** (network, machine type, resources)
- **Logging configuration**
- **Daemon mode settings** (future feature)

Example:

```yaml
# Container isolation for LVM operations (default: true)
# Runs LVM discovery inside a hardened Podman/Docker container
container_isolation: true

# Offline fix backend (default: vmcraft)
backend: vmcraft

allowed_dirs:
  - /var/lib/libvirt/images
  - /home/user/VMs
  - /data/vms

conversion:
  cache_dir: /var/lib/hyper2kvm/conversions
  keep_cache: true
  max_cache_size_gb: 100

libvirt:
  default_network: default
  default_machine: q35
  default_vcpus: 2
  default_memory_mb: 2048
```

To disable container isolation (falls back to host-only LVM with device filter):

```yaml
container_isolation: false
```

Or use the CLI flag: `--no-container-isolation`

### Migration Configurations

**`/etc/hyper2kvm/migrations/`** - Migration YAML files

Store your VM migration configurations here for easy reuse:

```bash
# Run a migration
sudo h2kvmctl --config /etc/hyper2kvm/migrations/my-vm.yaml

# Or copy system config
cp /etc/hyper2kvm/migrations/photon-example.yaml /etc/hyper2kvm/migrations/my-photon.yaml
# Edit and run
sudo h2kvmctl --config /etc/hyper2kvm/migrations/my-photon.yaml
```

## Directory Structure

```text
/etc/hyper2kvm/
├── config.yaml              # System-wide configuration
├── migrations/              # Migration YAML files
│   ├── photon-example.yaml
│   ├── ubuntu-example.yaml
│   └── your-vm.yaml
└── README.md                # This file

/var/lib/hyper2kvm/          # Runtime data
├── conversions/             # Temporary conversion cache
└── logs/                    # Migration logs (optional)
```

## Configuration Precedence

Hyper2kvm loads configurations in this order:

1. **System config**: `/etc/hyper2kvm/config.yaml` (defaults)
2. **User config**: Migration YAML specified with `--config`
3. **CLI arguments**: Command-line flags (highest priority)

User configs can override system defaults. CLI arguments override everything.

## Security

The `allowed_dirs` setting restricts which directories hyper2kvm can access.
This prevents accidental access to sensitive system directories.

Add directories where your VM images are stored:

```yaml
allowed_dirs:
  - /var/lib/libvirt/images
  - /mnt/vmware-exports
  - /home/user/VMs
```

## Example Usage

### Basic Migration

```bash
# Create migration config
cat > /etc/hyper2kvm/migrations/my-vm.yaml << EOF
command: local
vmdk: /data/exports/myvm.vmdk
output_dir: /var/lib/libvirt/images
to_output: myvm.qcow2
out_format: qcow2
emit_domain_xml: true
virsh_define: true
vm_name: myvm
EOF

# Run migration
sudo h2kvmctl --config /etc/hyper2kvm/migrations/my-vm.yaml
```

### Batch Migration

```bash
# Migrate multiple VMs
for vm in vm1 vm2 vm3; do
  sudo h2kvmctl --config /etc/hyper2kvm/migrations/${vm}.yaml
done
```

### Daemon Mode (Future)

```yaml
daemon:
  enabled: true
  watch_dirs:
    - /var/lib/hyper2kvm/incoming
  auto_migrate: true
```

When enabled, hyper2kvm will automatically migrate VMs placed in watch directories.

## Logs

Configure logging in `/etc/hyper2kvm/config.yaml`:

```yaml
logging:
  level: INFO
  log_file: /var/log/hyper2kvm/migrations.log
  log_retention_days: 30
```

View logs:

```bash
sudo tail -f /var/log/hyper2kvm/migrations.log
```

## Support

- Documentation: <https://github.com/ssahani/hyper2kvm>
- Issues: <https://github.com/ssahani/hyper2kvm/issues>
- Examples: `/etc/hyper2kvm/migrations/*.yaml`
