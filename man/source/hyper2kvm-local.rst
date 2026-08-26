===============
hyper2kvm-local
===============

-------------------------------------------
Convert local VMDK/VHD files to QCOW2/RAW
-------------------------------------------

:Manual section: 1
:Manual group: User Commands

SYNOPSIS
========

**hyper2kvm local** [*OPTIONS*]

**hyper2kvm** **--vmdk** *FILE* **--output-dir** *DIR* **local**

DESCRIPTION
===========

The **local** command converts local virtual disk files (VMDK, VHD, VHDx) to
KVM-compatible formats (QCOW2 or RAW) with automatic guest OS fixes.

This mode performs offline fixes to ensure the converted VM boots reliably on KVM:

* Stabilizes /etc/fstab with UUID-based device references
* Regenerates initramfs with KVM drivers
* Fixes GRUB bootloader configuration
* Removes VMware/Hyper-V/Azure specific tools and configs
* Injects VirtIO drivers (Windows only)

OPTIONS
=======

**--vmdk** *FILE*
    Source VMDK, VHD, or VHDx file to convert.

**--output-dir** *DIR*
    Output directory for converted files (default: ./output).

**--to-output** *FILE*
    Custom output filename (default: auto-generated).

**--out-format** *FORMAT*
    Output format: qcow2 (default), raw, vmdk, vdi, vhdx.

**--compress**
    Enable QCOW2 compression (reduces size, slower conversion).

**--checksum**
    Generate SHA256 checksum file.

**--flatten**
    Flatten VMDK snapshot chain before conversion.

**--flatten-format** *FORMAT*
    Intermediate format for flattening (default: qcow2).

**--fstab-mode** *MODE*
    How to fix /etc/fstab:

    * **stabilize-all** - Convert all entries to UUID (recommended)
    * **fix-root** - Fix only root filesystem
    * **none** - No changes

**--regen-initramfs**
    Regenerate initramfs/initrd with KVM drivers.

**--no-grub**
    Skip GRUB configuration updates.

**--print-fstab**
    Display /etc/fstab before and after fixes.

**--no-backup**
    Don't create backup files inside guest.

**--virtio-drivers-dir** *DIR*
    Path to extracted VirtIO drivers (Windows VMs only).
    Required for Windows migrations.

**--libvirt-test**
    Perform smoke test boot after conversion.

**--qemu-test**
    Use direct QEMU for testing (alternative to libvirt).

**--vm-name** *NAME*
    VM name for testing (default: auto-generated).

**--memory** *MB*
    RAM for test VM (default: 2048).

**--vcpus** *N*
    vCPU count for test VM (default: 2).

**--uefi**
    Use UEFI firmware for test (default: BIOS).

**--timeout** *SECONDS*
    Boot timeout for test (default: 60).

**--keep-domain**
    Keep libvirt domain after test.

**--headless**
    Run test without graphics.

**--dry-run**
    Preview changes without applying them.

**--verbose** *LEVEL*
    Logging level (0-2).

**--log-file** *FILE*
    Log output to file.

**--report** *FILE*
    Generate Markdown migration report.

EXAMPLES
========

Basic conversion
----------------

Convert a VMDK to compressed QCOW2::

    hyper2kvm local --vmdk /vms/ubuntu.vmdk --output-dir ./output --compress

Windows VM with VirtIO drivers
-------------------------------

Convert Windows VM and inject VirtIO drivers::

    # First, extract VirtIO ISO
    mkdir /tmp/virtio-extracted
    sudo mount -o loop virtio-win.iso /mnt
    cp -r /mnt/* /tmp/virtio-extracted/
    sudo umount /mnt

    # Convert with driver injection
    hyper2kvm local \
      --vmdk /vms/windows10.vmdk \
      --output-dir ./output \
      --virtio-drivers-dir /tmp/virtio-extracted \
      --libvirt-test \
      --memory 4096 \
      --vcpus 2

Linux VM with validation
-------------------------

Convert and validate boot::

    hyper2kvm local \
      --vmdk /vms/rhel9.vmdk \
      --output-dir ./output \
      --fstab-mode stabilize-all \
      --regen-initramfs \
      --libvirt-test \
      --timeout 120

Using configuration file
-------------------------

Create config file::

    cat > local-migration.yaml <<EOF
    command: local
    vmdk: /vms/debian.vmdk
    output_dir: ./output
    out_format: qcow2
    compress: true
    checksum: true
    fstab_mode: stabilize-all
    regen_initramfs: true
    print_fstab: true
    libvirt_test: true
    vm_name: debian-converted
    memory: 2048
    vcpus: 2
    EOF

    hyper2kvm --config local-migration.yaml local

FILES
=====

See **hyper2kvm**\(1) for configuration file locations.

SEE ALSO
========

**hyper2kvm**\(1),
**hyper2kvm.conf**\(5),
**qemu-img**\(1),
**virt-v2v**\(1)

AUTHOR
======

ZyvorAI Labs Private Limited <ssahani@zyvor.dev>
