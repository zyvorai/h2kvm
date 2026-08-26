# Configuration Guide

Advanced configuration options for Hyper2KVM.

---

## Configuration Documentation

- **[Advanced Configuration](advanced-config.md)** - Complete configuration reference

---

## Configuration Sources

Hyper2KVM can be configured via:

1. **YAML Files** - Primary configuration method
2. **JSON Files** - Alternative format
3. **Environment Variables** - Runtime overrides
4. **CLI Flags** - Command-line overrides

---

## Configuration Priority

```
CLI Flags > Environment Variables > Config Files > Defaults
```

---

## Quick Reference

### YAML Configuration
```yaml
command: local
vmdk: /path/to/source.vmdk
output_dir: /output
to_output: output.qcow2
out_format: qcow2
regen_initramfs: true
fstab_mode: stabilize-all
compress: true
```

### Environment Variables
```bash
export H2K_OUTPUT_DIR=/vms
export H2K_OUTPUT_FORMAT=qcow2
export H2K_COMPRESS=true
```

---

## Related Documentation

- **[CLI Reference](../cli/reference.md)** - Command-line configuration
- **[YAML Examples](../cli/yaml-examples.md)** - Configuration examples
- **[Best Practices](../operations/BEST_PRACTICES.md)** - Configuration best practices

---

**Last Updated**: March 2026
