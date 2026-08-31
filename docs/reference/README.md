# Reference Documentation

Technical reference materials including API documentation, architecture, installation guides, and specifications.

## Quick Navigation

### 📖 API Reference
- **[API Reference](api/API-Reference.md)** - Complete API documentation
- **[GuestKit API](api/guestkit.md)** - GuestKit Python assurance + Guestfs API (h2kvm facade)
- **[Library API](api/library-api.md)** - Python library usage
- **[Quick Reference](api/quick-reference.md)** - Essential API patterns

### 🏗️ Architecture & Design
- **[Architecture](architecture.md)** - System architecture and design
- **[Integration Contract](Integration-Contract.md)** - Integration requirements
- **[Failure Modes](failure-modes.md)** - Error handling and failure scenarios

### 📦 Installation & Dependencies
- **[Installation Guide](INSTALLATION.md)** - Fedora-specific installation
- **[Dependencies](dependencies.md)** - System and Python dependencies
- **[Optional Dependencies](optional-dependencies.md)** - Optional packages and features

### 🔌 Integrations
- **[HyperCtl Integration](HYPERCTL_INTEGRATION.md)** - hyperctl/hypersdk integration
- **[Native GuestFS](native-guestfs.md)** - GuestFS backend options

### 📋 Specifications & Schemas
- **[Manifest Workflow](manifest-workflow.md)** - Artifact manifest specification
- **[Artifact Manifest Schema](artifact-manifest-v1.0.schema.json)** - JSON schema v1.0

### 🌐 Network & Resilience
- **[Network Resilience](network-resilience.md)** - Network failure handling
- **[Quick Reference](quick-reference.md)** - Command quick reference

---

## Reference Categories

### By Type

| Type | Documents | Purpose |
|------|-----------|---------|
| **API** | 4 docs | Complete API reference |
| **Architecture** | 3 docs | Design and patterns |
| **Installation** | 3 docs | Setup and dependencies |
| **Integration** | 2 docs | External integrations |
| **Specifications** | 2 docs | Schemas and contracts |
| **Network** | 1 doc | Network handling |

### By Audience

| Audience | Recommended Reading |
|----------|-------------------|
| **Developers** | API Reference, Architecture, Integration Contract |
| **Operators** | Installation, Dependencies, Failure Modes |
| **Integrators** | Integration Contract, Manifest Workflow, HyperCtl Integration |
| **Users** | Quick Reference, Dependencies |

---

## API Documentation

### Complete API Reference

**[API Reference](api/API-Reference.md)** - Comprehensive API documentation covering:
- Core migration APIs
- GuestKit filesystem APIs
- Configuration APIs
- Validation APIs
- Rollback APIs

**Audience**: Developers building with H2KVM
**Complexity**: ⭐⭐⭐ Advanced

---

### GuestKit Python API

**[GuestKit API](api/guestkit.md)** - GuestKit assurance bindings and h2kvm facade:
- `run_doctor`, `run_boot_inspect`, `run_migrate_plan`, `run_migrate_repair`
- GuestFS-compatible handle for custom inspection
- Offline fstab, GRUB, initramfs repair (Rust engine via PyO3)

**Audience**: Migration automation, custom pipelines, h2kvm integrators
**Complexity**: ⭐⭐ Intermediate

---

### Library API

**[Library API](api/library-api.md)** - Using H2KVM as a Python library:

```python
from h2kvm import Migration

# Create migration
migration = Migration(
    vmdk="/path/to/vm.vmdk",
    output_dir="/output/path"
)

# Execute
result = migration.run()
```

**Audience**: Python developers
**Complexity**: ⭐⭐ Intermediate

---

### Quick API Reference

**[Quick Reference](api/quick-reference.md)** - Essential API patterns and examples

**Audience**: All developers
**Complexity**: ⭐ Easy

---

## Architecture Documentation

### System Architecture

**[Architecture](architecture.md)** - Complete system architecture covering:
- Component architecture
- Data flow diagrams
- Module organization
- GuestKit engine design
- Daemon architecture
- Worker protocol design
- Integration points

**Key Topics**:
- Pipeline architecture
- Plugin system
- Event system
- State management
- Error handling

**Audience**: Architects, senior developers
**Complexity**: ⭐⭐⭐ Advanced

---

### Integration Contract

**[Integration Contract](Integration-Contract.md)** - Requirements for integrating with H2KVM:
- API contracts
- Data formats
- Error handling
- Version compatibility
- Testing requirements

**Audience**: Integration developers
**Complexity**: ⭐⭐⭐ Advanced

---

### Failure Modes

**[Failure Modes](failure-modes.md)** - Comprehensive failure scenario documentation:
- Boot failures
- Network failures
- Conversion failures
- Permission errors
- Resource exhaustion
- Recovery procedures

**Audience**: Operators, SREs
**Complexity**: ⭐⭐ Intermediate

---

## Installation & Dependencies

### Installation Guide

**[Installation Guide](INSTALLATION.md)** - Fedora-specific installation:
- System preparation
- Package installation
- Configuration
- Verification

**Platform**: Fedora, RHEL, CentOS
**Audience**: System administrators
**Complexity**: ⭐ Easy

**See Also**: [General Installation Guide](../getting-started/01-Installation.md)

---

### Dependencies

**[Dependencies](dependencies.md)** - Complete dependency documentation:

**Required Dependencies**:
- Python 3.10+
- qemu-img
- qemu-system-x86

**Optional Dependencies**:
- GuestKit (default guestfs backend)
- ntfs-3g (Windows support)
- libhivex (Windows registry)

**Audience**: System administrators, developers
**Complexity**: ⭐ Easy

---

### Optional Dependencies

**[Optional Dependencies](optional-dependencies.md)** - Detailed optional package guide:
- Purpose of each package
- Installation instructions
- Feature enablement
- Platform availability

**Audience**: System administrators
**Complexity**: ⭐⭐ Intermediate

---

## Integration Documentation

### HyperCtl Integration

**[HyperCtl Integration](HYPERCTL_INTEGRATION.md)** - Integration with hyperctl/hypersdk:
- Setup and configuration
- API usage
- Live migration
- Remote operations
- Error handling

**Audience**: Integration developers
**Complexity**: ⭐⭐⭐ Advanced

---

### Native GuestFS

**[Native GuestFS](native-guestfs.md)** - GuestFS backend guide:
- GuestKit as the default backend
- Backend comparison and selection
- Hybrid approach
- Performance considerations

**Audience**: Advanced users
**Complexity**: ⭐⭐⭐ Advanced

---

## Specifications

### Manifest Workflow

**[Manifest Workflow](manifest-workflow.md)** - Artifact manifest specification:
- JSON manifest format
- Workflow definition
- Artifact tracking
- State management

**Example**:
```json
{
  "version": "1.0",
  "artifacts": [
    {
      "type": "disk",
      "path": "/output/vm.qcow2",
      "format": "qcow2"
    }
  ]
}
```

**Audience**: Integration developers
**Complexity**: ⭐⭐ Intermediate

---

### Artifact Manifest Schema

**[artifact-manifest-v1.0.schema.json](artifact-manifest-v1.0.schema.json)** - JSON Schema v1.0:
- Formal schema definition
- Validation rules
- Required fields
- Optional fields

**Usage**:
```bash
# Validate manifest
jsonschema -i manifest.json artifact-manifest-v1.0.schema.json
```

**Audience**: Integration developers
**Complexity**: ⭐⭐⭐ Advanced

---

## Network & Resilience

### Network Resilience

**[Network Resilience](network-resilience.md)** - Network failure handling:
- Retry mechanisms
- Exponential backoff
- Timeout handling
- Connection pooling
- Error recovery

**Scenarios Covered**:
- Remote ESXi fetch failures
- vSphere connection issues
- SSH connection drops
- Download interruptions

**Audience**: Operators, developers
**Complexity**: ⭐⭐ Intermediate

---

## Quick References

### Command Quick Reference

**[Quick Reference](quick-reference.md)** - Essential command patterns:
- Common CLI commands
- YAML configurations
- Troubleshooting commands
- Performance tips

**Audience**: All users
**Complexity**: ⭐ Easy

---

## Reference by Use Case

### For New Developers

**Start Here**:
1. [Quick Reference](quick-reference.md) - Learn basic patterns
2. [Library API](api/library-api.md) - Python library usage
3. [Architecture](architecture.md) - Understand design

### For Integration Work

**Start Here**:
1. [Integration Contract](Integration-Contract.md) - Understand requirements
2. [API Reference](api/API-Reference.md) - Complete API docs
3. [Manifest Workflow](manifest-workflow.md) - Data formats

### For System Administration

**Start Here**:
1. [Installation Guide](INSTALLATION.md) - Install system
2. [Dependencies](dependencies.md) - Understand requirements
3. [Failure Modes](failure-modes.md) - Handle errors

### For Advanced Development

**Start Here**:
1. [GuestKit API](api/guestkit.md) - Deep filesystem access
2. [Architecture](architecture.md) - System internals
3. [HyperCtl Integration](HYPERCTL_INTEGRATION.md) - Advanced integration

---

## Version Compatibility

### API Versions

| API Version | H2KVM Version | Status |
|-------------|-------------------|--------|
| **v1.0** | 1.0 - 2.1.0+ | ✅ Current |

### Schema Versions

| Schema | Version | Status |
|--------|---------|--------|
| **Artifact Manifest** | 1.0 | ✅ Current |
| **Migration Config** | 1.0 | ✅ Current |

### Compatibility Matrix

| Component | Python | qemu-img |
|-----------|--------|----------|
| **Core** | 3.10+ | 6.0+ |
| **GuestKit** | 3.10+ | 6.0+ |
| **Windows** | 3.10+ | 6.0+ |

---

## Documentation Standards

### API Documentation Format

All API documentation follows this structure:
1. **Overview** - Purpose and use cases
2. **Parameters** - Input parameters with types
3. **Returns** - Return values and types
4. **Examples** - Code examples
5. **Errors** - Possible exceptions
6. **See Also** - Related APIs

### Code Examples

All code examples are:
- ✅ Tested and verified
- ✅ Copy-paste ready
- ✅ Include error handling
- ✅ Follow best practices

---

## Contributing to Reference Docs

### Adding API Documentation

1. Document all public APIs
2. Include type hints
3. Provide examples
4. List exceptions
5. Add to API reference index

### Updating Specifications

1. Version all schema changes
2. Maintain backward compatibility
3. Document breaking changes
4. Provide migration guide

**See**: [Contributing Guide](../development/contributing.md)

---

## Related Documentation

### Before Reading Reference
- **[Getting Started](../getting-started/)** - Installation and setup
- **[Tutorials](../tutorials/)** - Learn by doing

### While Using Reference
- **[User Guides](../guides/)** - Task-oriented guides
- **[Features](../features/)** - Feature documentation
- **[FAQ](../FAQ.md)** - Common questions

### After Using Reference
- **[Development](../development/)** - Development guides
- **[Testing](../development/testing-guide.md)** - Testing docs

---

## External References

### Standards & Specifications
- **JSON Schema**: https://json-schema.org/
- **YAML Specification**: https://yaml.org/spec/
- **REST API Design**: https://restfulapi.net/

### Related Projects
- **GuestKit**: See [GuestKit API](api/guestkit.md)
- **qemu**: https://www.qemu.org/
- **libvirt**: https://libvirt.org/

---

## What's Next?

Choose your reference area:

### 📖 I need API documentation
→ Start with [API Reference](api/API-Reference.md)

### 🏗️ I need architecture details
→ Read [Architecture](architecture.md)

### 📦 I need installation help
→ See [Installation Guide](INSTALLATION.md)

### 🔌 I need integration info
→ Check [Integration Contract](Integration-Contract.md)

### 📋 I need specifications
→ Review [Manifest Workflow](manifest-workflow.md)

### 🔍 I need quick reference
→ Use [Quick Reference](quick-reference.md)

---

**Last Updated**: March 2026
**API Version**: v1.0
**Schema Version**: v1.0
**Status**: ✅ Production Ready
