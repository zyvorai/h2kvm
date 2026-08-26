# Test Scripts

Test and validation scripts for h2kvm development.

## Testing Scripts

### Distribution Testing

- **`test-all-distros.sh`** - Test migration on all supported distributions
- **`test-extended-distros.sh`** - Extended distribution testing
- **`test-vmware-vms.sh`** - Test with VMware VMs

### Feature Testing

- **`test_photon_workflow.sh`** - Test Photon OS migration workflow
- **`test_photon_sudo.sh`** - Test Photon OS with sudo
- **`test_back_button.sh`** - Test back button feature in TUI
- **`test_hypersdk_integration.sh`** - Test HyperSDK integration
- **`demo_hypersdk_integration.sh`** - Demo HyperSDK integration

### Validation Scripts

- **`verify-libvirt-export.sh`** - Verify libvirt export functionality
- **`check-firstboot-log.sh`** - Check first boot logs

### General

- **`run.sh`** - General test runner

## Usage

Most scripts expect to be run from the repository root:

```bash
# From repo root
./scripts/test/test-all-distros.sh

# Or
cd scripts/test
./test-all-distros.sh
```

## Test Configurations

Test YAML configurations are in `test-confs/` directory at repo root.

## See Also

- [Testing Guide](../../docs/development/testing-guide.md)
- [Test Configurations](../../test-confs/)
