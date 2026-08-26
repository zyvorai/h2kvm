# Library API Examples

This directory contains Python scripts demonstrating programmatic usage of hyper2kvm as a library.

## Available Examples

### Core Library Examples

- **`library_local_conversion.py`** - Convert local VMDK to qcow2
  ```bash
  python library_local_conversion.py /data/vm.vmdk /data/vm.qcow2
  ```

- **`library_vsphere_migration.py`** - Migrate from vCenter/ESXi
  ```bash
  export VCENTER_PASSWORD='your-password'
  python library_vsphere_migration.py vcenter.example.com vm-name
  ```

- **`library_azure_migration.py`** - Migrate from Azure
  ```bash
  export AZURE_SUBSCRIPTION_ID='...'
  export AZURE_TENANT_ID='...'
  export AZURE_CLIENT_ID='...'
  export AZURE_CLIENT_SECRET='...'
  python library_azure_migration.py my-rg my-vm
  ```

- **`library_guest_fixing.py`** - Apply offline fixes to converted VM
  ```bash
  sudo python library_guest_fixing.py /var/lib/libvirt/images/vm.qcow2
  ```

- **`library_boot_testing.py`** - Test VM boots correctly
  ```bash
  python library_boot_testing.py /var/lib/libvirt/images/vm.qcow2 auto
  ```

## Requirements

```bash
pip install -e .
```

For specific features:
```bash
pip install 'hyper2kvm[vsphere]'  # For vSphere examples
pip install 'hyper2kvm[azure]'    # For Azure examples
```

## Documentation

See [docs/08-Library-API.md](../../docs/08-Library-API.md) for complete API documentation.
