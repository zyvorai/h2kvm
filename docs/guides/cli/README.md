# CLI Guides

Complete command-line interface documentation for H2KVM CLI tools.

---

## Quick Links

### 🎯 CLI Tools
- **[h2kvmctl Guide](h2kvmctl-guide.md)** - Primary CLI for interactive workflows (kubectl-style)
- **[CLI Reference](reference.md)** - Complete h2kvm command reference (config-driven)
- **[YAML Examples](yaml-examples.md)** - Configuration file examples

---

## CLI Tools Overview

H2KVM provides two complementary CLI commands serving different use cases:

### h2kvmctl - Interactive CLI Tool
**File**: [h2kvmctl-guide.md](h2kvmctl-guide.md)

**Purpose**: Primary command for **interactive CLI workflows**

**Features**:
- Command-line migrations and scripting
- Interactive operations and testing
- Developer-friendly for quick tasks
- kubectl-style naming pattern
- Modern, concise interface

**Use when**:
- Running migrations from command line
- Testing and development
- Quick ad-hoc operations
- Interactive scripting

**Example**:
```bash
h2kvmctl convert \
  --vmdk /vms/source.vmdk \
  --output /vms/output.qcow2
```

---

### h2kvm - Daemon and Service CLI
**File**: [reference.md](reference.md)

**Purpose**: Primary for **daemon mode and services**

**Features**:
- Config-driven automation
- Systemd service integration
- Background processing
- YAML/JSON configuration
- Enterprise automation

**Use when**:
- Running as systemd service
- Automation and orchestration
- Batch processing
- Configuration-driven workflows

**Example**:
```bash
h2kvm --config migration.yaml
```

---

## CLI Tool Comparison

| Feature | h2kvmctl | h2kvm |
|---------|----------|-----------|
| **Primary Use** | Interactive CLI | Daemon/Service |
| **Style** | Flag-based | Config-driven |
| **Naming** | kubectl pattern | Traditional daemon |
| **Best For** | Quick tasks | Automation |
| **Config** | Optional | Required |
| **Flags** | Extensive | Minimal |
| **Verbosity** | Developer-friendly | Production-ready |
| **Use Case** | Development | Production |

**Both commands are actively maintained and serve complementary purposes.**

---

## YAML Configuration Examples
**File**: [yaml-examples.md](yaml-examples.md)

**Configuration examples for**:
- Local VMDK conversion
- Remote ESXi fetch
- OVA/OVF extraction
- Batch migrations
- Custom workflows
- Advanced configurations

**Use when**: Need complete configuration file examples

---

## Quick Start Paths

### Path 1: Quick Interactive Migration (15 minutes)

**Goal**: Migrate a single VM using command-line flags

**Tool**: h2kvmctl

```bash
# 1. Read h2kvmctl guide
docs/guides/cli/h2kvmctl-guide.md

# 2. Run migration
h2kvmctl convert \
  --vmdk /vms/source.vmdk \
  --output /vms/output.qcow2 \
  --format qcow2 \
  --compress

# 3. Verify
virsh define /vms/output.xml
virsh start vm
```

**Documentation**: [h2kvmctl Guide](h2kvmctl-guide.md)

---

### Path 2: Config-Driven Automation (30 minutes)

**Goal**: Set up repeatable, automated migrations

**Tool**: h2kvm

```bash
# 1. Read CLI reference
docs/guides/cli/reference.md

# 2. Create config file (use YAML examples)
docs/guides/cli/yaml-examples.md

cat > migration.yaml <<EOF
command: local
vmdk: /vms/source.vmdk
output_dir: /vms/migrated
to_output: output.qcow2
out_format: qcow2
regen_initramfs: true
fstab_mode: stabilize-all
compress: true
libvirt_test: true
EOF

# 3. Run migration
h2kvm --config migration.yaml

# 4. Setup as systemd service (optional)
sudo systemctl enable h2kvm-daemon
sudo systemctl start h2kvm-daemon
```

**Documentation**: [CLI Reference](reference.md) + [YAML Examples](yaml-examples.md)

---

## Use Case Guide

### Use Case 1: Development and Testing
**Recommended Tool**: h2kvmctl

**Workflow**:
1. Use command-line flags for quick iterations
2. Test different configurations easily
3. Interactive debugging
4. Fast feedback loop

**Documentation**: [h2kvmctl Guide](h2kvmctl-guide.md)

---

### Use Case 2: Production Automation
**Recommended Tool**: h2kvm

**Workflow**:
1. Create YAML configuration files
2. Version control configurations
3. Run as systemd service
4. Batch processing with manifests

**Documentation**: [CLI Reference](reference.md) + [YAML Examples](yaml-examples.md)

---

### Use Case 3: Batch Migration
**Recommended Tool**: h2kvm

**Workflow**:
1. Create batch manifest (JSON)
2. Configure parallel processing
3. Set up error handling
4. Monitor progress

**Documentation**: [CLI Reference](reference.md) + [Migration Guides](../migration/)

---

### Use Case 4: Quick One-Off Migration
**Recommended Tool**: h2kvmctl

**Workflow**:
1. Single command with all flags
2. No configuration file needed
3. Immediate execution
4. Quick verification

**Documentation**: [h2kvmctl Guide](h2kvmctl-guide.md)

---

## Command Reference

### h2kvmctl Commands

**Convert Operations**:
```bash
h2kvmctl convert --vmdk FILE --output FILE [OPTIONS]
h2kvmctl convert --ova FILE --output-dir DIR [OPTIONS]
h2kvmctl convert --vhd FILE --output FILE [OPTIONS]
```

**Remote Operations**:
```bash
h2kvmctl fetch --host HOST --remote PATH [OPTIONS]
h2kvmctl live-fix --host HOST [OPTIONS]
```

**Inspection**:
```bash
h2kvmctl inspect --vmdk FILE
h2kvmctl list --vsphere-host HOST
```

**Documentation**: [h2kvmctl Guide](h2kvmctl-guide.md)

---

### h2kvm Commands

**Config-Driven**:
```bash
h2kvm --config FILE
h2kvm --config base.yaml --config override.yaml
```

**Daemon Mode**:
```bash
h2kvm daemon [OPTIONS]
h2kvm --daemon --config FILE
```

**Inspection**:
```bash
h2kvm --show-config --config FILE
h2kvm --show-args --config FILE
```

**Documentation**: [CLI Reference](reference.md)

---

## Configuration Formats

### YAML Configuration

**Structure**:
```yaml
command: local  # or fetch-and-fix, ova, vhd, etc.
vmdk: /path/to/source.vmdk
output_dir: /path/to/output
to_output: output.qcow2
out_format: qcow2  # or raw, vdi

# Fixing options
regen_initramfs: true
fstab_mode: stabilize-all  # or uuid, label, device
# grub is auto-handled
fix_selinux: true

# Output options
compress: true
libvirt_test: true

# Batch options (optional)
batch_manifest: migrations.json
batch_parallel: 4
batch_continue_on_error: true
```

**Documentation**: [YAML Examples](yaml-examples.md)

---

### JSON Batch Manifest

**Structure**:
```json
{
  "migrations": [
    {
      "vmdk": "/vms/vm1.vmdk",
      "to_output": "vm1.qcow2",
      "compress": true
    },
    {
      "vmdk": "/vms/vm2.vmdk",
      "to_output": "vm2.qcow2",
      "compress": true
    }
  ]
}
```

**Documentation**: [CLI Reference](reference.md) - Batch section

---

## Common CLI Patterns

### Pattern 1: Simple Local Conversion
```bash
# h2kvmctl (interactive)
h2kvmctl convert --vmdk /vms/vm.vmdk --output /vms/vm.qcow2

# h2kvm (config-driven)
h2kvm --config <(cat <<EOF
command: local
vmdk: /vms/vm.vmdk
output_dir: /vms
to_output: vm.qcow2
EOF
)
```

---

### Pattern 2: Remote ESXi Fetch
```bash
# h2kvmctl (interactive)
h2kvmctl fetch \
  --host esxi.example.com \
  --user root \
  --identity ~/.ssh/id_rsa \
  --remote /vmfs/volumes/datastore1/vm/vm.vmdk

# h2kvm (config-driven)
cat > fetch.yaml <<EOF
command: fetch-and-fix
host: esxi.example.com
user: root
identity: ~/.ssh/id_rsa
remote: /vmfs/volumes/datastore1/vm/vm.vmdk
output_dir: /vms
EOF
h2kvm --config fetch.yaml
```

---

### Pattern 3: Batch Migration
```bash
# Only h2kvm supports batch (config-driven)
cat > batch.yaml <<EOF
command: local
batch_manifest: migrations.json
batch_parallel: 4
batch_continue_on_error: true
output_dir: /vms
EOF
h2kvm --config batch.yaml
```

---

### Pattern 4: OVA Extraction
```bash
# h2kvmctl (interactive)
h2kvmctl convert --ova /vms/vm.ova --output-dir /vms

# h2kvm (config-driven)
cat > ova.yaml <<EOF
command: ova
ova: /vms/vm.ova
output_dir: /vms
EOF
h2kvm --config ova.yaml
```

---

## Tool Selection Guide

| Scenario | Use h2kvmctl | Use h2kvm |
|----------|-------------|---------------|
| **Quick test** | ✅ Yes | ❌ No |
| **One-off migration** | ✅ Yes | ⚠️ Optional |
| **Scripting** | ✅ Yes | ✅ Yes |
| **Batch migration** | ❌ No | ✅ Yes |
| **Daemon service** | ❌ No | ✅ Yes |
| **Config-driven** | ⚠️ Optional | ✅ Yes |
| **Development** | ✅ Yes | ⚠️ Optional |
| **Production** | ⚠️ Optional | ✅ Yes |

---

## Integration with Other Documentation

### Before Using CLI
- **[Installation Guide](../../getting-started/01-Installation.md)** - Install H2KVM
- **[Quick Start](../../getting-started/02-Quick-Start.md)** - First migration
- **[Migration Decision Tree](../decision-support/MIGRATION_DECISION_TREE.md)** - Choose approach

### While Using CLI
- **[CLI Reference](reference.md)** - Complete command documentation
- **[h2kvmctl Guide](h2kvmctl-guide.md)** - Interactive CLI usage
- **[YAML Examples](yaml-examples.md)** - Configuration examples
- **[Quick Reference](../../quick-reference/QUICK_REFERENCE.md)** - Command cheat sheet

### After Migration
- **[Best Practices](../operations/BEST_PRACTICES.md)** - Proven practices
- **[Monitoring Guide](../operations/MONITORING_GUIDE.md)** - Production monitoring
- **[Troubleshooting](../decision-support/TROUBLESHOOTING_FLOWCHART.md)** - Issue resolution

---

## Advanced Topics

### Daemon Mode Setup

**Using h2kvm as systemd service**:
```bash
# 1. Create service config
cat > /etc/h2kvm/daemon.yaml <<EOF
command: daemon
daemon_port: 8080
daemon_workers: 4
EOF

# 2. Enable and start service
sudo systemctl enable h2kvm-daemon
sudo systemctl start h2kvm-daemon

# 3. Check status
sudo systemctl status h2kvm-daemon
```

**Documentation**: [CLI Reference](reference.md) - Daemon section

---

### Config Merging

**Override configs for different environments**:
```bash
# Base configuration
cat > base.yaml <<EOF
regen_initramfs: true
fstab_mode: stabilize-all
compress: true
EOF

# Environment-specific override
cat > prod.yaml <<EOF
output_dir: /vms/production
libvirt_test: true
EOF

# Merge configs
h2kvm --config base.yaml --config prod.yaml --config migration.yaml
```

**Documentation**: [CLI Reference](reference.md) - Config merging section

---

## Related Documentation

### CLI Documentation
- **[h2kvmctl Guide](h2kvmctl-guide.md)** - Interactive CLI tool
- **[CLI Reference](reference.md)** - Complete command reference
- **[YAML Examples](yaml-examples.md)** - Configuration examples

### Migration Workflows
- **[Migration Guides](../migration/)** - Migration workflows and playbooks
- **[Batch Features](../migration/batch-features.md)** - Batch migration features

### API Documentation
- **[API Reference](../../reference/api/README.md)** - Programmatic usage
- **[Library API](../../reference/api/library-api.md)** - Python library API

---

## Summary

**3 comprehensive CLI guides** covering:
- ✅ h2kvmctl - Modern interactive CLI (kubectl-style)
- ✅ h2kvm - Config-driven daemon/service CLI
- ✅ YAML configuration examples

**Both CLI tools actively maintained for complementary use cases**

---

**Last Updated**: March 2026
**Documentation Version**: 0.3.0
**CLI Tools**: 2 (h2kvmctl + h2kvm)

**Quick Navigation**: [Guides Hub](../README.md) | [Documentation Hub](../../index.md) | [Migration Guides](../migration/)
