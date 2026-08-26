# API Reference Documentation

Complete API reference for using H2KVM programmatically as a Python library.

---

## Quick Links

### 🚀 Start Here
- **[Quick Reference](quick-reference.md)** - Most commonly used APIs (one-page reference)
- **[Library API](library-api.md)** - Complete library usage guide (high/mid/low-level APIs)

### 📚 Complete References
- **[API Reference](API-Reference.md)** - Full API documentation (core, converters, fixers, orchestrator)
- **[VMCraft API](vmcraft.md)** - Advanced disk manipulation (395+ methods, 62 modules)

---

## API Documentation Overview

### Quick Reference
**File**: [quick-reference.md](quick-reference.md)

**Best for**: Quick lookups, copy-paste examples, frequently used APIs

**Content**:
- VMCraft disk image analysis (8 OS detection APIs, 4 filesystem APIs)
- File operations (70+ methods)
- Package management (RPM, DEB, Zypper)
- System configuration (systemd, network, users)
- Boot management (GRUB, initramfs)
- Common usage patterns

**Use when**: You know what you want to do and need syntax quickly

---

### Library API Guide
**File**: [library-api.md](library-api.md)

**Best for**: Understanding API levels, choosing the right abstraction, complete workflows

**Content**:
- **Level 1: High-Level API** (Recommended) - Simple orchestration
- **Level 2: Mid-Level API** - Component-level control
- **Level 3: Low-Level API** - Direct VMCraft access
- Usage examples (local VMDK, vSphere, Azure, guest fixing, boot testing)
- Batch migration APIs
- Hook system and validation framework
- Error handling and best practices
- Migration from CLI to library

**Use when**: Starting a new project, designing workflows, choosing abstraction level

---

### Complete API Reference
**File**: [API-Reference.md](API-Reference.md)

**Best for**: Detailed parameter documentation, advanced usage, all available methods

**Content**:
- Core API (`convert_vm()`, `create_manifest()`)
- Converters (VMDK, OVA, VHD, Azure, AMI)
- Fixers (bootloader, fstab, initramfs, network, drivers)
- Orchestrator (batch processing, parallel execution)
- Manifest API (JSON-based workflows)
- VMware integration (vSphere operations)
- Configuration management
- Error handling and exceptions

**Use when**: Need complete parameter details, advanced features, error handling

---

### VMCraft Platform API
**File**: [vmcraft.md](vmcraft.md)

**Best for**: Advanced disk manipulation, low-level operations, maximum control

**Content**:
- **395+ methods** across 62 specialized modules
- Architecture overview (NBD, storage, mount, file operations)
- OS detection and inspection (62 APIs)
- Filesystem operations (45+ APIs)
- Package management (50+ APIs for RPM/DEB/Zypper)
- Systemd management (52 enterprise APIs)
- Boot management (GRUB, initramfs, bootloader)
- Network configuration (interface, routing, DNS)
- Security (SELinux, firewall, users, SSH)
- Storage activation (LVM, LUKS, RAID, ZFS)
- Performance optimizations (parallel mounts, intelligent caching)

**Use when**: Need direct disk access, custom fixers, advanced automation

---

## API Level Comparison

| Feature | Quick Reference | Library API | API Reference | VMCraft API |
|---------|----------------|-------------|---------------|-------------|
| **Audience** | All users | Library users | Library users | Advanced users |
| **Depth** | Essential only | Complete | Complete | Deep technical |
| **Format** | Code snippets | Guide + examples | Full docs | Full docs |
| **Use Case** | Quick lookup | Learning | Development | Advanced dev |
| **Size** | 1 page | Complete guide | Full reference | 30,000+ lines |

---

## Getting Started Paths

### Path 1: Quick Task (5 minutes)
**Goal**: Convert a VMDK file to qcow2

1. Check **[Quick Reference](quick-reference.md)** for basic usage
2. Copy-paste example code
3. Run conversion

---

### Path 2: Build an Application (1-2 hours)
**Goal**: Integrate H2KVM into your application

1. Read **[Library API](library-api.md)** introduction
2. Choose API level (high/mid/low)
3. Review usage examples for your scenario
4. Consult **[API Reference](API-Reference.md)** for parameter details
5. Implement with error handling

---

### Path 3: Advanced Automation (4-8 hours)
**Goal**: Build custom VM manipulation workflows

1. Read **[Library API](library-api.md)** for architecture
2. Study **[VMCraft API](vmcraft.md)** for available methods
3. Design custom workflow using low-level APIs
4. Use **[API Reference](API-Reference.md)** for integration points
5. Refer to **[Quick Reference](quick-reference.md)** for common patterns

---

## Common API Use Cases

### Single VM Conversion
**Recommended**: [Library API](library-api.md) - Level 1 (High-Level API)

```python
from h2kvm.core import convert_vm

result = convert_vm(
    input_path="/path/to/vm.vmdk",
    output_path="/path/to/output.qcow2",
    os_type="linux"
)
```

**Reference**: [API Reference](API-Reference.md) - Core API section

---

### Batch Migration
**Recommended**: [Library API](library-api.md) - Batch Migration APIs

```python
from h2kvm.orchestrator import BatchOrchestrator

orchestrator = BatchOrchestrator(
    manifest="migrations.json",
    parallel=4
)
orchestrator.execute()
```

**Reference**: [API Reference](API-Reference.md) - Orchestrator section

---

### Custom VM Inspection
**Recommended**: [VMCraft API](vmcraft.md) - OS Detection

```python
from h2kvm.vmcraft.main import VMCraft

g = VMCraft()
g.add_drive_opts('/path/to/disk.vmdk', readonly=True)
g.launch()

roots = g.inspect_os()
for root in roots:
    os_type = g.inspect_get_type(root)
    distro = g.inspect_get_distro(root)
    print(f"Found: {os_type} - {distro}")

g.shutdown()
```

**Reference**: [Quick Reference](quick-reference.md) - OS Detection

---

### Custom Fixer Implementation
**Recommended**: [VMCraft API](vmcraft.md) - File Operations + Boot Management

```python
from h2kvm.vmcraft.main import VMCraft

g = VMCraft()
g.add_drive_opts('/path/to/disk.vmdk', readonly=False)
g.launch()

# Custom fstab modification
fstab = g.cat('/etc/fstab')
# ... modify fstab ...
g.write('/etc/fstab', new_fstab)

# Regenerate initramfs
g.command(['dracut', '-f'])

g.shutdown()
```

**Reference**: [VMCraft API](vmcraft.md) - File Operations, Boot Management

---

## API Feature Matrix

| Capability | Quick Ref | Library API | API Ref | VMCraft |
|------------|-----------|-------------|---------|---------|
| **VM Conversion** | ✅ Basic | ✅ Complete | ✅ Complete | ❌ N/A |
| **Batch Migration** | ❌ | ✅ Complete | ✅ Complete | ❌ N/A |
| **OS Detection** | ✅ Common | ✅ Complete | ✅ Complete | ✅ All 62 APIs |
| **File Operations** | ✅ Common | ✅ Complete | ✅ Complete | ✅ All 70+ methods |
| **Package Mgmt** | ✅ Common | ✅ Complete | ✅ Complete | ✅ All 50+ methods |
| **Systemd Mgmt** | ✅ Common | ✅ Complete | ✅ Complete | ✅ All 52 APIs |
| **Boot Fixing** | ✅ Common | ✅ Complete | ✅ Complete | ✅ All methods |
| **Network Config** | ✅ Common | ✅ Complete | ✅ Complete | ✅ All methods |
| **Storage Activation** | ❌ | ❌ | ❌ | ✅ Complete |
| **Custom Workflows** | ❌ | ✅ Hooks | ✅ Hooks | ✅ Full control |

---

## Documentation Organization

### By User Experience Level

**Beginner** (First time using H2KVM as library):
1. Start with [Library API](library-api.md) - Overview and Quick Start
2. Review Level 1 High-Level API examples
3. Use [Quick Reference](quick-reference.md) for syntax

**Intermediate** (Building production applications):
1. Read [Library API](library-api.md) - All three API levels
2. Consult [API Reference](API-Reference.md) for detailed parameters
3. Implement error handling and validation

**Advanced** (Custom automation and workflows):
1. Study [VMCraft API](vmcraft.md) - Architecture and all modules
2. Use [API Reference](API-Reference.md) for integration
3. Design custom fixers and workflows

---

### By Task Type

**Simple Conversion**:
- [Quick Reference](quick-reference.md) - Basic usage
- [Library API](library-api.md) - Level 1 examples

**Production Migration**:
- [Library API](library-api.md) - Batch APIs, hooks, validation
- [API Reference](API-Reference.md) - Orchestrator, error handling

**Custom Automation**:
- [VMCraft API](vmcraft.md) - All available methods
- [API Reference](API-Reference.md) - Integration points

**Troubleshooting**:
- [API Reference](API-Reference.md) - Error handling section
- [VMCraft API](vmcraft.md) - Debugging and logging

---

## Related Documentation

### Getting Started
- **[Installation Guide](../../getting-started/01-Installation.md)** - Install H2KVM
- **[Quick Start](../../getting-started/02-Quick-Start.md)** - First migration
- **[Beginner Tutorial](../../tutorials/01-beginner-migration.md)** - Step-by-step walkthrough

### Guides
- **[CLI Reference](../../guides/cli/reference.md)** - Command-line usage
- **[Migration Playbooks](../../guides/migration/playbooks.md)** - Migration workflows
- **[Best Practices](../../guides/operations/BEST_PRACTICES.md)** - Proven practices

### Features
- **[VMCraft Complete Guide](../../features/vmcraft/complete-guide.md)** - VMCraft platform overview
- **[Windows Support](../../os-support/windows/guide.md)** - Windows migration APIs

### Examples
- **[Examples Library](../../guides/operations/EXAMPLES_LIBRARY.md)** - 23+ configuration examples
- **[Common Scenarios](../../recipes/01-common-scenarios.md)** - Real-world patterns

---

## API Statistics

**Total API Surface**:
- **Core API**: 15+ high-level methods
- **Converters**: 8 platform-specific converters
- **Fixers**: 12 automated fix operations
- **VMCraft**: 395+ low-level methods across 62 modules
- **Batch APIs**: 10+ orchestration methods

**Code Size**:
- Core library: ~15,000 lines
- VMCraft platform: ~30,000 lines
- Total: ~45,000 lines of Python code

**Test Coverage**: 100% (114 systemd tests, comprehensive integration tests)

---

## Version Information

**API Version**: v1.0
**VMCraft Version**: v9.2
**H2KVM Version**: v0.3.1
**Last Updated**: March 2026

---

**Quick Navigation**: [Documentation Hub](../../index.md) | [Reference Documentation](../README.md) | [Features](../../features/README.md)
