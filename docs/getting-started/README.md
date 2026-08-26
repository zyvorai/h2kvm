# Getting Started with H2KVM

Welcome to H2KVM! This section will guide you through installation and your first VM migration.

## Quick Navigation

### 📖 Essential Guides
- **[Installation Guide](01-Installation.md)** ⭐ **START HERE** - Install H2KVM in 5 minutes
- **[Quick Start](02-Quick-Start.md)** - Your first migration in 10 minutes
- **[Getting Started](03-Getting-Started.md)** - Comprehensive introduction and concepts

## Learning Path

### Step 1: Installation (5 minutes)
Install H2KVM and verify your setup.

**[→ Go to Installation Guide](01-Installation.md)**

**What you'll learn:**
- Installing via pip
- System dependencies
- Optional components
- Verifying installation

### Step 2: Quick Start (10 minutes)
Run your first VM migration with a simple example.

**[→ Go to Quick Start](02-Quick-Start.md)**

**What you'll learn:**
- Creating a YAML config
- Running a migration
- Understanding the output
- Importing to libvirt

### Step 3: Comprehensive Guide (30 minutes)
Deep dive into H2KVM concepts and workflows.

**[→ Go to Getting Started Guide](03-Getting-Started.md)**

**What you'll learn:**
- Architecture overview
- Key concepts
- Common workflows
- Best practices

## Quick Installation

### Option 1: Full Installation (Recommended)

```bash
# Install with all features
pip install "h2kvm[full]"

# Verify installation
h2kvmctl --version
h2kvm --version
```

### Option 2: Minimal Installation

```bash
# Core features only
pip install h2kvm

# Verify installation
h2kvmctl --version
```

### Option 3: From Source

```bash
# Clone repository
git clone https://github.com/ssahani/h2kvm.git
cd h2kvm

# Install in development mode
pip install -e ".[full]"
```

**See**: [Complete Installation Guide](01-Installation.md)

## Your First Migration

### 1. Create Configuration

Create `migration.yaml`:

```yaml
command: local
vmdk: /path/to/your/vm.vmdk
output_dir: /output/directory
to_output: converted-vm.qcow2
out_format: qcow2

# Automatic fixes
fstab_mode: stabilize-all
regen_initramfs: true
# grub is auto-handled
compress: true
```

### 2. Run Migration

```bash
# Using h2kvmctl (recommended for CLI)
sudo h2kvmctl --config migration.yaml

# Or using h2kvm
sudo h2kvmctl --config migration.yaml
```

### 3. Import to Libvirt

```bash
# Import the converted VM
virsh define /output/directory/converted-vm.xml
virsh start converted-vm
```

**See**: [Quick Start Guide](02-Quick-Start.md) for detailed examples

## Common First-Time Scenarios

### Scenario 1: Migrate Windows VM from VMware

```yaml
command: local
vmdk: /vmware/windows-server-2019.vmdk
output_dir: /kvm/vms
to_output: windows-server-2019.qcow2
out_format: qcow2

# Windows-specific fixes
windows_drivers: true
fstab_mode: stabilize-all
# grub is auto-handled
compress: true
```

**Expected time**: 10-15 minutes for a 40GB VM

### Scenario 2: Migrate Linux VM from VMware

```yaml
command: local
vmdk: /vmware/centos9-web.vmdk
output_dir: /kvm/vms
to_output: centos9-web.qcow2
out_format: qcow2

# Linux-specific fixes
fstab_mode: stabilize-all
regen_initramfs: true
initramfs_add_drivers:
  - virtio
  - virtio_blk
  - virtio_net
# grub is auto-handled
compress: true
```

**Expected time**: 5-10 minutes for a 20GB VM

### Scenario 3: Remote Fetch from ESXi

```yaml
command: fetch-and-fix
host: 192.168.1.100
user: root
identity: ~/.ssh/id_rsa
remote: /vmfs/volumes/datastore1/vm/vm.vmdk
output_dir: /kvm/vms
to_output: migrated-vm.qcow2
fstab_mode: stabilize-all
regen_initramfs: true
```

**Expected time**: 15-30 minutes depending on network speed

## Prerequisites

### System Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| **Python** | 3.10+ | 3.11+ |
| **RAM** | 4 GB | 8 GB+ |
| **CPU** | 2 cores | 4 cores+ |
| **Disk Space** | 2x VM size | 3x VM size |
| **OS** | Linux | RHEL 9, Ubuntu 22.04+ |

### Required Tools

```bash
# Core tools (automatically handled by pip)
- Python 3.10+
- qemu-img (for conversion)

# Optional tools
- qemu-nbd, qemu-img (used by VMCraft, the default backend)
- ntfs-3g (for Windows support)
- libhivex (for Windows registry)
```

### Permissions

Most operations require **root/sudo** access for:
- Mounting filesystems
- Modifying disk images
- Accessing guest filesystems
- Installing bootloaders

```bash
# Run with sudo
sudo h2kvmctl --config migration.yaml
```

## Next Steps

### After Your First Migration

1. **Verify the Result**
   - Boot the converted VM
   - Check network connectivity
   - Verify services are running
   - Test application functionality

2. **Learn More**
   - [Troubleshooting Guide](../guides/troubleshooting.md) - Fix common issues

3. **Explore Features**
   - [Windows Support](../os-support/windows/guide.md) - Windows-specific features
   - [VMCraft Guide](../features/vmcraft/complete-guide.md) - Advanced VM manipulation

## Common Installation Issues

### Issue 1: Permission Denied

```bash
# Problem
ERROR: Could not install packages due to an EnvironmentError: [Errno 13] Permission denied

# Solution
pip install --user "h2kvm[full]"
# Or use virtual environment
python -m venv venv
source venv/bin/activate
pip install "h2kvm[full]"
```

### Issue 2: Missing System Dependencies

```bash
# Problem
ERROR: qemu-img not found

# Solution (Fedora/RHEL)
sudo dnf install -y qemu-img qemu-system-x86

# Solution (Ubuntu/Debian)
sudo apt-get install -y qemu-utils qemu-system-x86
```

### Issue 3: Python Version Too Old

```bash
# Problem
ERROR: h2kvm requires Python >=3.10

# Solution
# Install Python 3.11+ from your distribution
# Or use pyenv to manage Python versions
```

**See**: [Installation Guide](01-Installation.md#troubleshooting) for more solutions

## Getting Help

### Documentation
- **[Main Documentation Hub](../index.md)** - Complete documentation index
- **[Troubleshooting Guide](../guides/troubleshooting.md)** - Common issues and solutions
- **[FAQ](../FAQ.md)** - Frequently asked questions

### Community Support
- **GitHub Issues**: [Report bugs](https://github.com/ssahani/h2kvm/issues)
- **GitHub Discussions**: [Ask questions](https://github.com/ssahani/h2kvm/discussions)

### Examples
- **[Migration Recipes](../recipes/)** - Real-world examples
- **[Tutorial Examples](../tutorials/)** - Step-by-step guides
- **[Config Examples](../../examples/)** - Sample configurations

## What's Next?

Choose your path:

### 🚀 I want to deploy to production
→ [Enterprise Tutorial](../tutorials/04-enterprise-deployment.md)

### 🔧 I want to explore features
→ [Features Index](../features/README.md)

### 📖 I want complete reference
→ [API Reference](../reference/api/API-Reference.md)

---

**Ready?** Start with [Installation](01-Installation.md) →

---

**Last Updated**: March 2026
**Difficulty**: Beginner
**Time to Complete**: 45 minutes (all guides)
