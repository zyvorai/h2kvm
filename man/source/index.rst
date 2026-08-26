========
hyper2kvm
========

-------------------------------------------------------------
Production-Grade Hypervisor to KVM/QEMU Migration Toolkit
-------------------------------------------------------------

:Manual section: 1
:Manual group: User Commands
:Date: January 2026
:Version: 2.0

SYNOPSIS
========

**hyper2kvm** [*OPTIONS*] *COMMAND* [*COMMAND_OPTIONS*]

**hyper2kvm** **--config** *FILE* *COMMAND*

**hyper2kvm** **local** [*--vmdk* *FILE*] [*OPTIONS*]

**hyper2kvm** **vsphere** [*--vm* *NAME*] [*OPTIONS*]

**hyper2kvm** **hyperv** [*--vm* *NAME*] [*OPTIONS*]

**hyper2kvm** **azure** [*--vm* *NAME*] [*OPTIONS*]

DESCRIPTION
===========

**hyper2kvm** is a comprehensive toolkit for migrating virtual machines from multiple
hypervisors and disk ecosystems (VMware vSphere, Hyper-V, Azure, AWS, local disks)
into reliable, bootable KVM/QEMU systems.

The tool handles the complete migration pipeline:

* **FETCH** - Download or access source VM disks from various hypervisors
* **FLATTEN** - Consolidate snapshot chains and differencing disks
* **INSPECT** - Analyze guest OS, bootloader, and filesystem configuration
* **FIX** - Repair boot configuration, regenerate initramfs, stabilize device paths
* **CONVERT** - Transform disk formats (VMDK/VHD/VHDx → QCOW2/RAW)
* **VALIDATE** - Test boot and verify functionality

Key features include:

* **Offline Guest Fixes** - Modify guest filesystems without booting using guestfs
* **Windows VirtIO Injection** - Inject VirtIO drivers into Windows VMs offline
* **Network Reconfiguration** - Adapt network configs across 7+ distro backends
* **Bootloader Repair** - Fix GRUB/GRUB2 for BIOS and UEFI systems
* **Multi-Format Support** - VMDK, VHD, VHDx, OVA, OVF, AMI, RAW

COMMANDS
========

**local**
    Convert local VMDK, VHD, or VHDx files to QCOW2 format.
    See **hyper2kvm-local**\(1).

**vsphere**
    Migrate VMs from VMware vSphere/ESXi environments.
    See **hyper2kvm-vsphere**\(1).

**hyperv**
    Migrate VMs from Microsoft Hyper-V hosts.
    See **hyper2kvm-hyperv**\(1).

**azure**
    Download and convert VMs from Microsoft Azure.
    See **hyper2kvm-azure**\(1).

**vhd**
    Convert VHD/VHDx disk images (Azure, Hyper-V).

**ami**
    Extract and convert AWS AMI tarball images.

**ova**
    Extract and convert OVA/OVF virtual appliances.

GLOBAL OPTIONS
==============

**--config** *FILE*
    Load configuration from YAML or JSON file.
    See **hyper2kvm.conf**\(5) for format details.

**--verbose** *LEVEL*, **-v** *LEVEL*
    Set logging verbosity (0-2):

    * 0 = INFO (default)
    * 1 = Verbose
    * 2 = DEBUG

**--log-file** *FILE*
    Write logs to specified file.

**--report** *FILE*
    Generate migration report in Markdown format.

**--dry-run**
    Preview changes without applying them.

**--version**
    Show version information and exit.

**--help**, **-h**
    Show help message and exit.

COMMON OPTIONS
==============

These options are available across most commands:

**--output-dir** *DIR*
    Directory for output files (default: ./output).

**--out-format** *FORMAT*
    Output disk format: qcow2 (default), raw, vmdk, vdi, vhdx.

**--compress**
    Enable compression for QCOW2 output.

**--checksum**
    Generate SHA256 checksums for output files.

**--fstab-mode** *MODE*
    Filesystem table stabilization mode:

    * **none** - No changes
    * **stabilize-all** - Convert all entries to UUID (recommended)
    * **fix-root** - Fix only root filesystem
    * **uuid** - Force UUID entries

**--regen-initramfs**
    Regenerate initramfs/initrd (automatically detects dracut/update-initramfs).

**--no-grub**
    Skip GRUB bootloader configuration updates.

**--virtio-drivers-dir** *DIR*
    Path to extracted VirtIO driver directory (Windows migrations).

**--libvirt-test**
    Perform smoke test boot using libvirt after conversion.

**--vm-name** *NAME*
    VM name for testing (default: auto-generated).

**--memory** *MB*
    RAM allocation for test VM (default: 2048).

**--vcpus** *N*
    CPU count for test VM (default: 2).

**--uefi**
    Use UEFI firmware for test boot (default: BIOS).

**--timeout** *SECONDS*
    Boot test timeout (default: 60).

EXAMPLES
========

Convert a local VMDK file
--------------------------

::

    hyper2kvm local --vmdk /path/to/vm.vmdk --output-dir ./output --compress

Migrate from vSphere with config file
--------------------------------------

::

    cat > vsphere-migration.yaml <<EOF
    command: vsphere
    vcenter: vcenter.example.com
    vc_user: administrator@vsphere.local
    vc_password_env: VCENTER_PASSWORD
    vm_name: production-web-01
    output_dir: ./migrated-vms
    out_format: qcow2
    compress: true
    fstab_mode: stabilize-all
    regen_initramfs: true
    EOF

    export VCENTER_PASSWORD='your-password'
    hyper2kvm --config vsphere-migration.yaml vsphere

Convert Windows VM with VirtIO drivers
---------------------------------------

::

    hyper2kvm local \
      --vmdk /vms/windows10.vmdk \
      --output-dir ./output \
      --virtio-drivers-dir /opt/virtio-win-extracted \
      --libvirt-test \
      --memory 4096

Download and convert Azure VM
------------------------------

::

    az login
    hyper2kvm azure \
      --subscription "Production" \
      --resource-group prod-rg \
      --vm webapp-prod-01 \
      --output-dir ./azure-vms \
      --compress

FILES
=====

**/etc/hyper2kvm/hyper2kvm.conf**
    System-wide configuration file.

**~/.config/hyper2kvm/config.yaml**
    User-specific configuration file.

**./hyper2kvm.yaml**
    Project-specific configuration file (searched in current directory).

See **hyper2kvm.conf**\(5) for configuration file format.

ENVIRONMENT
===========

**VCENTER_PASSWORD**
    vCenter password for vSphere migrations.

**HYPERV_PASSWORD**
    Hyper-V host password.

**AZURE_SUBSCRIPTION_ID**
    Azure subscription ID.

**VM_PASSWORD**
    VM password for post-migration validation.

EXIT STATUS
===========

**0**
    Success.

**1**
    General error.

**2**
    Configuration error.

**3**
    Source disk not found or inaccessible.

**4**
    Conversion failed.

**5**
    Guest OS fix failed.

**6**
    Validation failed.

SEE ALSO
========

**hyper2kvm-local**\(1),
**hyper2kvm-vsphere**\(1),
**hyper2kvm-hyperv**\(1),
**hyper2kvm-azure**\(1),
**hyper2kvm.conf**\(5),
**qemu-img**\(1),
**virt-v2v**\(1),
**guestfs**\(3)

BUGS
====

Report bugs to: https://github.com/ssahani/hyper2kvm/issues

Project documentation: https://github.com/ssahani/hyper2kvm

AUTHOR
======

ZyvorAI Labs Private Limited <ssahani@zyvor.dev>

COPYRIGHT
=========

Copyright (C) 2026 ZyvorAI Labs Private Limited.

License: Apache-2.0

This is free software: you are free to change and redistribute it.
There is NO WARRANTY, to the extent permitted by law.
