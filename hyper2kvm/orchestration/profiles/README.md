# Migration Profiles

## Overview

Migration profiles provide pre-configured settings for common VM conversion scenarios. Profiles allow you to avoid repeating the same configuration across multiple manifests and enable quick switching between different migration strategies.

## Built-in Profiles

### `production`
**Use Case**: Production migrations where data integrity and boot success are critical.

**Features**:
- Full offline fixes (GRUB, initramfs, fstab)
- Compression enabled (level 6)
- Complete validation
- Backups enabled
- Report generation

**Example**:
```json
{
  "manifest_version": "1.0",
  "profile": "production",
  "source": {...}
}
```

---

### `testing`
**Use Case**: Test/development environments where speed is more important than safety.

**Features**:
- Extends `production` but disables time-consuming operations
- No guest inspection
- No backups
- No initramfs regeneration
- No compression
- No validation

**Example**:
```json
{
  "manifest_version": "1.0",
  "profile": "testing",
  "source": {...}
}
```

---

### `minimal`
**Use Case**: Pre-prepared VMs or raw conversions requiring only critical fixes.

**Features**:
- Critical fixes only (GRUB, fstab)
- No format conversion
- No validation
- No backups
- No reporting

**Example**:
```json
{
  "manifest_version": "1.0",
  "profile": "minimal",
  "source": {...}
}
```

---

### `fast`
**Use Case**: Bulk migrations of non-critical VMs.

**Features**:
- Extends `minimal`
- Skips GRUB update
- Skips fstab modification
- Converts to qcow2 without compression

---

### `windows`
**Use Case**: Windows guest migrations.

**Features**:
- Extends `production`
- Disables Linux-specific fixes (GRUB, initramfs, fstab)
- Optimized for Windows driver injection

---

### `archive`
**Use Case**: Long-term storage and archival.

**Features**:
- Extends `production`
- Maximum compression (level 9)
- Full validation

---

### `debug`
**Use Case**: Troubleshooting migration issues.

**Features**:
- Extends `production`
- Verbose output (print_fstab enabled)
- No compression (faster for debugging)
- Detailed reporting

---

## Profile Inheritance

Profiles support inheritance using the `extends` field. This allows you to build on existing profiles without duplicating configuration.

**Example** (custom profile):
```yaml
# my_profile.yaml
description: "Custom profile for my organization"
extends: "production"

pipeline:
  convert:
    compress_level: 9  # Override to maximum compression

output:
  format: "raw"  # Override to raw format
```

**Inheritance Chain**:
```
testing -> production (base)
fast -> minimal (base)
windows -> production (base)
archive -> production (base)
debug -> production (base)
```

---

## Using Profiles in Manifests

### Basic Usage

```json
{
  "manifest_version": "1.0",
  "profile": "production",
  "source": {
    "type": "local",
    "path": "/data/vm.vmdk"
  },
  "disks": [...]
}
```

### With Profile Overrides

You can override specific profile settings:

```json
{
  "manifest_version": "1.0",
  "profile": "production",
  "profile_overrides": {
    "pipeline": {
      "convert": {
        "compress_level": 9
      }
    }
  },
  "source": {...}
}
```

---

## Custom Profiles

### Creating Custom Profiles

Create a YAML file in your profiles directory:

```yaml
# /etc/hyper2kvm/profiles/my_org.yaml
description: "Organization-specific profile"
extends: "production"

pipeline:
  fix:
    remove_vmware_tools: true  # Always remove VMware tools

  convert:
    compress: true
    compress_level: 8

network_mapping:
  source_networks:
    "VM Network": "br0"
    "DMZ Network": "br-dmz"
  mac_address_policy: "preserve"

storage_mapping:
  default_pool: "vms"
  format_override: "qcow2"
```

### Using Custom Profiles

Specify the custom profiles directory in your configuration:

```yaml
# config.yaml
profiles_directory: "/etc/hyper2kvm/profiles"
```

Then reference it in your manifest:

```json
{
  "manifest_version": "1.0",
  "profile": "my_org",
  "source": {...}
}
```

---

## Profile API

### Python API

```python
from hyper2kvm.profiles import ProfileLoader

loader = ProfileLoader(logger)

# List available profiles
profiles = loader.list_builtin_profiles()
print(profiles)  # ['production', 'testing', 'minimal', 'fast', ...]

# Load a profile
profile = loader.load_profile("production")

# Load custom profile
profile = loader.load_profile("my_org", custom_profile_path="/etc/hyper2kvm/profiles")

# Apply overrides
overridden = loader.apply_overrides(profile, {
    "pipeline": {
        "convert": {
            "compress_level": 9
        }
    }
})

# Get profile info
info = loader.get_profile_info("production")
print(info['description'])
```

---

## Configuration Priority

When using profiles, configuration merges in this order (highest priority last):

1. Built-in profile defaults
2. Parent profile (if using `extends`)
3. Current profile settings
4. Profile overrides from manifest (`profile_overrides`)
5. Direct manifest settings (always win)

**Example**:
```json
{
  "manifest_version": "1.0",
  "profile": "production",
  "profile_overrides": {
    "pipeline": {
      "convert": {
        "compress": false  // Overrides profile setting
      }
    }
  },
  "pipeline": {
    "convert": {
      "compress_level": 9  // Highest priority - always applied
    }
  }
}
```

---

## Best Practices

### 1. Use Profiles for Common Scenarios
Instead of repeating the same configuration:
```json
// Bad: Repeated configuration
{"manifest_version": "1.0", "pipeline": {"fix": {"enabled": true, "backup": true, ...}}}
{"manifest_version": "1.0", "pipeline": {"fix": {"enabled": true, "backup": true, ...}}}

// Good: Use profile
{"manifest_version": "1.0", "profile": "production"}
{"manifest_version": "1.0", "profile": "production"}
```

### 2. Create Organization Profiles
Create custom profiles for your organization's standards:
```yaml
# corp_standard.yaml
description: "Corporate standard migration profile"
extends: "production"

network_mapping:
  source_networks:
    "VM Network": "br-corp"
  default_bridge: "br-corp"

storage_mapping:
  default_pool: "corporate-vms"
  format_override: "qcow2"
```

### 3. Use Inheritance to Reduce Duplication
```yaml
# dev_profile.yaml
extends: "testing"

pipeline:
  fix:
    remove_vmware_tools: true  # Only override what's different
```

### 4. Test Profiles Before Production
```bash
# Test with testing profile first
hyper2kvm --config manifest-testing.json

# Then production migration
hyper2kvm --config manifest-production.json
```

---

## Troubleshooting

### Profile Not Found

**Error**: `ProfileLoadError: Profile 'myprofile' not found`

**Solution**:
- Check profile name spelling
- Ensure custom profile path is correct
- List available profiles: `loader.list_builtin_profiles()`

### Circular Inheritance

**Error**: `ProfileLoadError: Circular inheritance detected`

**Solution**:
- Check your `extends` chain
- Ensure no profile extends itself indirectly

### Profile Override Not Working

**Issue**: Profile settings not being applied

**Solution**:
- Check configuration priority (manifest settings override profiles)
- Use `profile_overrides` for selective changes
- Enable debug logging to see merge results

---

## Examples

See `examples/batch/` for complete examples:
- `batch-with-profiles.yaml` - Batch conversion using profiles
- `profile-custom.yaml` - Custom profile example

---

## See Also

- [Batch Migration Guide](../docs/14-Batch-Migration-Guide.md)
- [YAML Examples](../docs/05-YAML-Examples.md)
- [Library API](../docs/08-Library-API.md)
