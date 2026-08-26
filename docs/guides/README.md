# User Guides

Task-oriented guides for using Hyper2KVM effectively. Learn how to accomplish specific tasks and use various features.

## Performance Highlights (v2.2.0+)

**Enterprise LVM Improvements:**
- ✅ **7x Faster LVM Activation** - 0.71s vs 5-10s for traditional methods
- ✅ **100% Host Protection** - Device-filtered VG activation prevents corruption
- ✅ **Production Validated** - RHEL 8.8 and openSUSE Leap 15.4 tested

See [LVM Enterprise Improvements](../LVM_AND_ENTERPRISE_IMPROVEMENTS.md) and [Test Results](../test-results/LVM_ENTERPRISE_IMPROVEMENTS_TEST_RESULTS.md)

## Quick Navigation

### 🚀 Quick Start Guides
- **[Cookbook](cookbook.md)** - Quick recipes for common migration tasks
- **[HyperSDK Quickstart](hypersdk-quickstart.md)** - Get started with HyperSDK integration

### 📋 Command-Line Guides
- **[CLI Reference](cli/reference.md)** - Complete command-line documentation
- **[h2kvmctl Guide](cli/h2kvmctl-guide.md)** - Worker job control CLI
- **[YAML Examples](cli/yaml-examples.md)** - Configuration file examples
- **[YAML vs Manifests](yaml-vs-manifests.md)** - Choose the right configuration format

### 🔄 Migration Guides
- **[Migration Playbooks](migration/playbooks.md)** - Complete migration workflows
- **[Batch Migration Features](migration/batch-features.md)** - Multi-VM migration
- **[Batch Quick Reference](migration/batch-quick-reference.md)** - Quick batch operations
- **[Migration Quick Reference](migration/quick-reference.md)** - Essential migration commands

### 🎨 Terminal UI (TUI) Guides
- **[TUI Quickstart](tui/quickstart.md)** - Get started with the dashboard
- **[Dashboard Guide](tui/dashboard.md)** - Interactive terminal interface
- **[Run TUI](tui/run-tui.md)** - Launch and use the TUI

### ⚙️ Configuration Guides
- **[Conversion Directory](configuration/conversion-directory.md)** - Configure VMDK conversion temporary directory

### 🔒 Security & Operations
- **[Security Best Practices](security-best-practices.md)** - Secure migration workflows
- **[Troubleshooting Guide](troubleshooting.md)** - Diagnose and fix common issues

### ✨ Advanced Features
- **[Enhanced Features](enhanced-features.md)** - Advanced capabilities (retry, validation, metrics)

---

## Guide Categories

### By Difficulty

| Difficulty | Guides | Best For |
|------------|--------|----------|
| **⭐ Beginner** | Cookbook, CLI Reference, YAML Examples | Getting started |
| **⭐⭐ Intermediate** | Migration Playbooks, Batch Migration, TUI | Regular usage |
| **⭐⭐⭐ Advanced** | Enhanced Features, HyperSDK, Security | Power users |

### By Use Case

| Use Case | Recommended Guides |
|----------|-------------------|
| **First migration** | Cookbook → CLI Reference |
| **Multiple VMs** | Batch Migration Features → Batch Quick Reference |
| **Production deployment** | Security Best Practices → Migration Playbooks |
| **Automation** | YAML Examples → HyperSDK Quickstart |
| **Troubleshooting** | Troubleshooting Guide → Cookbook |
| **Interactive work** | TUI Quickstart → Dashboard Guide |

### By Task

| Task | Guide | Time |
|------|-------|------|
| **Migrate single VM** | [Cookbook](cookbook.md) | 10 min |
| **Migrate multiple VMs** | [Batch Migration](migration/batch-features.md) | 30 min |
| **Set up automation** | [HyperSDK Quickstart](hypersdk-quickstart.md) | 45 min |
| **Configure CLI** | [CLI Reference](cli/reference.md) | 15 min |
| **Use TUI** | [TUI Quickstart](tui/quickstart.md) | 10 min |
| **Troubleshoot issues** | [Troubleshooting](troubleshooting.md) | Varies |
| **Secure migrations** | [Security Best Practices](security-best-practices.md) | 30 min |

---

## Featured Guides

### 📖 Cookbook
**Perfect for**: Quick solutions to common tasks

The cookbook provides ready-to-use recipes for:
- Basic VM migration
- Windows VM migration
- Batch migration
- Remote fetch from ESXi
- OVA/OVF import
- Database server migration
- And more...

**[→ Open Cookbook](cookbook.md)**

---

### 🔄 Migration Playbooks
**Perfect for**: Step-by-step migration workflows

Complete playbooks covering:
- Pre-migration planning
- Standard migration workflow
- Live migration (minimal downtime)
- Remote fetch workflow
- Batch migration workflow
- Post-migration validation
- Rollback procedures

**[→ Open Migration Playbooks](migration/playbooks.md)**

---

### 🔒 Security Best Practices
**Perfect for**: Securing your migration process

Security guidelines for:
- Access control
- Credential management
- Network security
- Data protection
- Audit logging
- Compliance requirements

**[→ Open Security Guide](security-best-practices.md)**

---

### 🛠️ Troubleshooting Guide
**Perfect for**: Fixing common issues

Solutions for:
- Boot failures
- Network problems
- Driver issues
- Permission errors
- Conversion failures
- Performance problems

**[→ Open Troubleshooting Guide](troubleshooting.md)**

---

## CLI Reference

### Command Categories

**Migration Commands:**
- `hyper2kvm --cmd local` - Local VMDK migration
- `hyper2kvm --cmd fetch-and-fix` - Remote ESXi fetch
- `hyper2kvm --cmd ova` - OVA file import
- `hyper2kvm --cmd vhd` - VHD file import
- `hyper2kvm --cmd live-fix` - Live SSH-based fixing

**Worker Commands:**
- `h2kvmctl submit` - Submit migration job to worker
- `h2kvmctl status` - Check job status
- `h2kvmctl query` - Query jobs
- `h2kvmctl cancel` - Cancel job

**[→ Complete CLI Reference](cli/reference.md)**

---

## Configuration Formats

### YAML Configuration (Recommended)

```yaml
command: local
vmdk: /path/to/vm.vmdk
output_dir: /output/path
to_output: converted-vm.qcow2
out_format: qcow2
fstab_mode: stabilize-all
regen_initramfs: true
# grub is auto-handled
```

**Best for**: Most use cases, easy to read and maintain

**[→ YAML Examples](cli/yaml-examples.md)**

---

### JSON Manifests

```json
{
  "command": "local",
  "vmdk": "/path/to/vm.vmdk",
  "output_dir": "/output/path",
  "to_output": "converted-vm.qcow2"
}
```

**Best for**: Automation, programmatic generation

**[→ YAML vs Manifests Guide](yaml-vs-manifests.md)**

---

## Quick Start Paths

### Path 1: First-Time User (30 minutes)
1. Read [Cookbook](cookbook.md) (10 min)
2. Try basic migration recipe (15 min)
3. Review [CLI Reference](cli/reference.md) (5 min)

### Path 2: Batch Migration (1 hour)
1. Read [Batch Migration Features](migration/batch-features.md) (20 min)
2. Create batch manifest (15 min)
3. Run batch migration (20 min)
4. Review [Batch Quick Reference](migration/batch-quick-reference.md) (5 min)

### Path 3: Production Deployment (2 hours)
1. Review [Security Best Practices](security-best-practices.md) (30 min)
2. Read [Migration Playbooks](migration/playbooks.md) (30 min)
3. Plan migration strategy (30 min)
4. Execute migrations (30 min)

### Path 4: Interactive User (20 minutes)
1. Read [TUI Quickstart](tui/quickstart.md) (10 min)
2. Launch TUI dashboard (2 min)
3. Explore [Dashboard Guide](tui/dashboard.md) (8 min)

---

## Advanced Topics

### Automation with HyperSDK

```python
from hypersdk import MigrationClient

client = MigrationClient()
result = client.migrate_vm(
    vmdk="/path/to/vm.vmdk",
    output_dir="/output/path"
)
```

**[→ HyperSDK Quickstart](hypersdk-quickstart.md)**

---

### Enhanced Features

- **Retry Logic**: Automatic retry with exponential backoff
- **Validation Framework**: Post-migration validation
- **Metrics Collection**: Prometheus-compatible metrics
- **Checkpoint/Resume**: Resume failed migrations

**[→ Enhanced Features Guide](enhanced-features.md)**

---

## Common Tasks

### Task: Migrate a Windows VM

```yaml
# windows-migration.yaml
command: local
vmdk: /vmware/windows-server-2019.vmdk
output_dir: /kvm/vms
to_output: windows-server-2019.qcow2
windows_drivers: true
fstab_mode: stabilize-all
compress: true
```

```bash
sudo h2kvmctl --config windows-migration.yaml
```

**See**: [Cookbook](cookbook.md#windows-migration)

---

### Task: Migrate Multiple VMs

```yaml
# batch.yaml
command: local
batch_manifest: migrations.json
batch_parallel: 3
output_dir: /kvm/batch
```

```json
{
  "migrations": [
    {"vmdk": "/vmware/vm1.vmdk", "to_output": "vm1.qcow2"},
    {"vmdk": "/vmware/vm2.vmdk", "to_output": "vm2.qcow2"}
  ]
}
```

```bash
sudo h2kvmctl --config batch.yaml
```

**See**: [Batch Migration Guide](migration/batch-features.md)

---

### Task: Fetch from ESXi

```yaml
# fetch.yaml
command: fetch-and-fix
host: esxi-host.example.com
user: root
identity: ~/.ssh/id_rsa
remote: /vmfs/volumes/datastore1/vm/vm.vmdk
output_dir: /kvm/vms
to_output: migrated-vm.qcow2
```

```bash
sudo h2kvmctl --config fetch.yaml
```

**See**: [Migration Playbooks](migration/playbooks.md#remote-fetch)

---

## Troubleshooting Quick Links

### Common Issues

| Issue | Solution | Guide |
|-------|----------|-------|
| **Boot failure** | Check bootloader and initramfs | [Troubleshooting](troubleshooting.md#boot-failures) |
| **No network** | Verify VirtIO drivers | [Troubleshooting](troubleshooting.md#network-issues) |
| **Permission denied** | Run with sudo | [Troubleshooting](troubleshooting.md#permissions) |
| **Conversion fails** | Check disk space | [Troubleshooting](troubleshooting.md#conversion) |
| **Windows drivers** | Use --windows-drivers | [Cookbook](cookbook.md#windows-migration) |

---

## Related Documentation

### Before Reading Guides
- **[Getting Started](../getting-started/)** - Installation and setup
- **[Tutorials](../tutorials/)** - Step-by-step learning

### While Using Guides
- **[Migration Recipes](../recipes/)** - Quick solutions
- **[OS Support](../os-support/)** - OS-specific guides
- **[FAQ](../FAQ.md)** - Common questions

### After Using Guides
- **[API Reference](../reference/api/)** - Complete API docs
- **[Features](../features/)** - Detailed feature documentation

---

## Contributing to Guides

Help improve the guides:

1. **Found an issue?** [Open an issue](https://github.com/ssahani/hyper2kvm/issues)
2. **Have a recipe?** Share it in the [Cookbook](cookbook.md)
3. **Found a workaround?** Add to [Troubleshooting](troubleshooting.md)

**See**: [Contributing Guide](../development/contributing.md)

---

## What's Next?

Choose your path:

### 🍳 I want quick recipes
→ Start with [Cookbook](cookbook.md)

### 📋 I want complete reference
→ Read [CLI Reference](cli/reference.md)

### 🔄 I want migration workflows
→ See [Migration Playbooks](migration/playbooks.md)

### 🎨 I want interactive UI
→ Try [TUI Quickstart](tui/quickstart.md)

### 🔒 I want security guidance
→ Review [Security Best Practices](security-best-practices.md)

### 🛠️ I have a problem
→ Check [Troubleshooting Guide](troubleshooting.md)

### 🚀 I want performance tips
→ Read [LVM Enterprise Improvements](../LVM_AND_ENTERPRISE_IMPROVEMENTS.md)

---

**Last Updated**: March 29, 2026
**Version**: 0.3.0
**Total Guides**: 15+
**Coverage**: CLI, Migration, TUI, Security, Troubleshooting
**LVM Performance**: 7x faster with 100% host protection
