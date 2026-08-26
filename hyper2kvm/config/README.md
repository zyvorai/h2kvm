# Configuration Schema Documentation

This directory contains configuration file loaders and schemas for hyper2kvm.

## Configuration File Formats

Hyper2kvm supports YAML and JSON configuration files for:
1. **Migration configuration** - VM migration parameters
2. **Manifest files** - Batch migration workflows
3. **Mapping configuration** - Resource mapping (network, storage)
4. **Systemd templates** - Service unit file templates

## Migration Configuration Schema

### Basic Configuration

```yaml
# Output and Working Directories
output_dir: ./out              # Output directory for converted images
workdir: ./out/work            # Working directory for temporary files

# Logging
verbose: 1                     # Verbosity level (0=quiet, 1=info, 2=debug)
dry_run: false                 # Preview mode - no actual changes
log_file: /path/to/log.txt     # Log file path (null = no log file)

# Checksums and Reporting
checksum: true                 # Generate checksums for output files
report: report.md              # Migration report filename

# Recovery and Safety
enable_recovery: true          # Enable recovery checkpoints
no_backup: false               # Skip backup creation

# Parallel Processing
parallel_processing: false     # Enable parallel disk processing
```

### Disk Conversion

```yaml
# Format Conversion
flatten: true                  # Flatten VMDK snapshots
flatten_format: qcow2          # Format for flattened disk (qcow2, raw)
out_format: qcow2              # Output format (qcow2, raw, vmdk)

# Compression
compress: true                 # Enable compression
compress_level: 6              # Compression level (0-9, 6=default)
```

### Filesystem Fixing

```yaml
# Fstab Configuration
fstab_mode: stabilize-all      # Fstab handling mode
  # Options:
  #   - stabilize-all: Convert all entries to UUID
  #   - stabilize-root: Only convert root filesystem
  #   - preserve: Keep existing entries
  #   - regenerate: Rebuild from scratch

print_fstab: true              # Print fstab to console

# Bootloader
no_grub: false                 # Skip GRUB configuration
regen_initramfs: true          # Regenerate initramfs

# Cleanup
remove_vmware_tools: true      # Remove VMware Tools
```

### Testing

```yaml
# VM Testing
libvirt_test: false            # Test with libvirt after conversion
qemu_test: false               # Test with qemu-kvm after conversion

# VM Configuration for Testing
vm_name: converted-vm          # VM name for testing
memory: 2048                   # Memory in MB
vcpus: 2                       # Number of vCPUs
uefi: false                    # Use UEFI boot
timeout: 60                    # Test timeout in seconds
keep_domain: false             # Keep libvirt domain after test
headless: true                 # Run VM headless (no graphics)
```

### Source Configuration

```yaml
# VMware vSphere Source
source:
  type: vmware
  vcenter: vcenter.example.com
  username: administrator@vsphere.local
  password: ${VCENTER_PASSWORD}  # Environment variable
  datacenter: DC1
  vm_name: web-server-01
  insecure: false              # Allow self-signed certificates

# Azure Source
source:
  type: azure
  subscription_id: xxx-xxx-xxx
  resource_group: rg-vms
  vm_name: web-server-01
  storage_account: mystorageaccount
  container: vhds

# Local Disk Source
source:
  type: local
  disk: /path/to/disk.vmdk
```

### Offline Fixing

```yaml
# Hostname Configuration
hostname_config_inject:
  hostname: webserver
  domain: example.com
  hosts:
    "192.168.1.10": "db.example.com db"
    "192.168.1.20": "app.example.com app"

# Network Configuration
network_config_inject:
  - interface: eth0
    type: static                # static or dhcp
    address: 192.168.1.100/24
    gateway: 192.168.1.1
    dns: [8.8.8.8, 8.8.4.4]
  - interface: eth1
    type: dhcp

# User Configuration
user_config_inject:
  - username: admin
    password: ${ADMIN_PASSWORD}
    ssh_keys:
      - ssh-rsa AAAAB3NzaC1yc2E...
    sudo: true
  - username: deploy
    ssh_keys:
      - ssh-ed25519 AAAAC3NzaC1lZD...
    groups: [docker, sudo]

# Service Configuration
service_config_inject:
  enable: [sshd, docker, nginx]
  disable: [bluetooth, avahi-daemon]
  mask: [cups]

# Firstboot Script
firstboot_inject:
  - name: initial-setup
    script: |
      #!/bin/bash
      apt-get update
      apt-get upgrade -y
    run_once: true
```

### Windows Configuration

```yaml
# Windows VirtIO Drivers
virtio_drivers_dir: /path/to/virtio-win
force_virtio_overwrite: false
enable_virtio_gpu: false
enable_virtio_input: true
enable_virtio_fs: false
enable_virtio_serial: false
enable_virtio_rng: true

# Windows License
preserve_activation: true
reactivation_method: kms      # kms, mak, retail
```

## Manifest File Schema

Manifest files define batch migration workflows:

```yaml
# Manifest Metadata
version: "1.0"
name: "Production Web Servers Migration"
description: "Migrate all production web servers from VMware to KVM"

# Global Configuration
defaults:
  output_dir: /data/migrations
  out_format: qcow2
  compress: true
  fstab_mode: stabilize-all

# VM List
vms:
  - name: web-01
    source:
      type: vmware
      vcenter: vcenter.prod.local
      vm_name: WEB-01-PROD
    network_config_inject:
      - interface: eth0
        type: static
        address: 10.0.1.10/24
        gateway: 10.0.1.1

  - name: web-02
    source:
      type: vmware
      vcenter: vcenter.prod.local
      vm_name: WEB-02-PROD
    network_config_inject:
      - interface: eth0
        type: static
        address: 10.0.1.11/24
        gateway: 10.0.1.1

# Workflow Stages
workflow:
  - stage: validate
    parallel: false
  - stage: convert
    parallel: true
    max_concurrent: 4
  - stage: fix
    parallel: true
  - stage: test
    parallel: false
```

## Mapping Configuration Schema

Resource mapping for complex migrations:

```yaml
# Network Mapping
network_mapping:
  source_networks:
    - name: "VM Network"
      target: "br0"
    - name: "DMZ Network"
      target: "br-dmz"

# Storage Mapping
storage_mapping:
  source_datastores:
    - name: "datastore1"
      target: "/data/vms"
    - name: "SSD-Storage"
      target: "/data/ssd"

# MAC Address Policy
mac_address_policy: preserve    # preserve, regenerate, custom

# Custom MAC Mapping (if policy=custom)
mac_mapping:
  "00:50:56:12:34:56": "52:54:00:12:34:56"
```

## Environment Variables

Configuration files support environment variable substitution:

```yaml
vcenter_password: ${VCENTER_PASSWORD}
azure_client_secret: ${AZURE_CLIENT_SECRET}
ssh_key: ${SSH_PUBLIC_KEY}
```

Set environment variables before running:

```bash
export VCENTER_PASSWORD="secret"
export AZURE_CLIENT_SECRET="secret"
hyper2kvm --config migration.yaml
```

## Configuration Precedence

Configuration is loaded in this order (later overrides earlier):

1. Default values (hardcoded)
2. Config file (`--config`)
3. Environment variables
4. Command-line arguments

Example:

```bash
# Config file sets: verbose: 1
# Command-line overrides to: verbose: 2
hyper2kvm --config common.yaml --verbose 2
```

## Validation

Configuration files are validated before execution:

```bash
# Validate configuration
hyper2kvm --config migration.yaml --dry-run

# Validate manifest
hyper2kvm --manifest batch-migration.yaml --validate-only
```

## Common Patterns

### Pattern 1: Minimal Configuration

```yaml
# Minimal config for local disk conversion
source:
  type: local
  disk: /path/to/disk.vmdk

output_dir: ./output
out_format: qcow2
```

### Pattern 2: VMware with Offline Fixing

```yaml
source:
  type: vmware
  vcenter: vcenter.example.com
  vm_name: my-vm

output_dir: ./output

# Inject configuration
hostname_config_inject:
  hostname: new-hostname

network_config_inject:
  - interface: eth0
    type: dhcp

user_config_inject:
  - username: admin
    ssh_keys:
      - ssh-rsa AAAAB3...

service_config_inject:
  enable: [sshd]
  disable: [bluetooth]
```

### Pattern 3: Windows Migration

```yaml
source:
  type: vmware
  vcenter: vcenter.example.com
  vm_name: win-server-2019

output_dir: ./output

# Windows-specific
virtio_drivers_dir: /path/to/virtio-win
preserve_activation: true
enable_virtio_input: true
enable_virtio_rng: true
```

### Pattern 4: Batch Migration

```yaml
version: "1.0"
name: "Multi-VM Migration"

defaults:
  output_dir: /data/migrations
  compress: true

vms:
  - name: vm1
    source:
      type: vmware
      vm_name: VM-001

  - name: vm2
    source:
      type: vmware
      vm_name: VM-002

  - name: vm3
    source:
      type: vmware
      vm_name: VM-003

workflow:
  - stage: convert
    parallel: true
    max_concurrent: 2
```

## Schema Files

Python schema definitions:

- `config_loader.py` - Main configuration loader
- `mapping_config.py` - Resource mapping schemas
- `validation.py` - Configuration validation

## Examples

Complete examples in:
- `examples/yaml/00-common/` - Common configurations
- `examples/yaml/10-local/` - Local disk migrations
- `examples/yaml/20-vmware/` - VMware migrations
- `examples/yaml/30-azure/` - Azure migrations
- `examples/yaml/40-batch/` - Batch migration manifests

## See Also

- [CLI Documentation](../cli/README.md)
- [Fixer Documentation](../fixers/README.md)
- [Orchestration Documentation](../orchestration/README.md)
