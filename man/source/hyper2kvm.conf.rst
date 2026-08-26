===============
hyper2kvm.conf
===============

-------------------------------------------
hyper2kvm configuration file format
-------------------------------------------

:Manual section: 5
:Manual group: File Formats

SYNOPSIS
========

**/etc/hyper2kvm/hyper2kvm.conf**

**~/.config/hyper2kvm/config.yaml**

**./hyper2kvm.yaml**

DESCRIPTION
===========

**hyper2kvm** uses YAML or JSON configuration files to define migration workflows.
Configuration files eliminate the need for long command-line arguments and enable
reproducible migrations.

FILE FORMAT
===========

hyper2kvm supports both YAML and JSON formats. YAML is recommended for its
readability and support for comments.

STRUCTURE
=========

All configuration files share a common top-level structure::

    command: <mode>         # Required: local, vsphere, hyperv, azure
    <mode-specific-options>
    <common-options>

COMMON FIELDS
=============

These fields are available across all modes:

**command** (*string*, required)
    Migration mode: ``local``, ``vsphere``, ``hyperv``, ``azure``, ``vhd``, ``ami``, ``ova``.

**output_dir** (*string*)
    Output directory for converted files (default: ``./output``).

**to_output** (*string*)
    Output filename template. Supports variables: ``{vm_name}``, ``{timestamp}``.

**out_format** (*string*)
    Output disk format: ``qcow2`` (default), ``raw``, ``vmdk``, ``vdi``, ``vhdx``.

**compress** (*boolean*)
    Enable QCOW2 compression (default: ``false``).

**checksum** (*boolean*)
    Generate SHA256 checksum files (default: ``false``).

**workdir** (*string*)
    Temporary working directory (default: ``/tmp/hyper2kvm-<random>``).

**fstab_mode** (*string*)
    Filesystem table fixes:

    * ``stabilize-all`` - Convert all entries to UUID (recommended)
    * ``fix-root`` - Fix only root filesystem
    * ``uuid`` - Force UUID everywhere
    * ``none`` - No changes

**regen_initramfs** (*boolean*)
    Regenerate initramfs with KVM drivers (default: ``false``).

**no_grub** (*boolean*)
    Skip GRUB bootloader fixes (default: ``false``).

**print_fstab** (*boolean*)
    Display /etc/fstab before and after (default: ``false``).

**no_backup** (*boolean*)
    Don't create backup files inside guest (default: ``false``).

**dry_run** (*boolean*)
    Preview changes without applying (default: ``false``).

**container_isolation** (*boolean*)
    Run LVM volume group discovery inside a hardened Podman/Docker container
    for isolation. The container uses a strict device filter that only permits
    the assigned NBD device, keeping host LVM metadata untouched. When disabled,
    falls back to host-only LVM with a device filter (default: ``true``).

    CLI equivalent: ``--container-isolation`` / ``--no-container-isolation``

**backend** (*string*)
    Offline fix backend engine: ``vmcraft`` (pure Python, fast, no C dependencies)
    or ``guestfs`` (libguestfs-based) (default: ``vmcraft``).

**verbose** (*integer*)
    Logging level: 0 (INFO), 1 (verbose), 2 (DEBUG) (default: ``0``).

**log_file** (*string*)
    Write logs to file.

**report** (*string*)
    Generate Markdown migration report.

VALIDATION OPTIONS
==================

**libvirt_test** (*boolean*)
    Perform smoke test boot using libvirt (default: ``false``).

**qemu_test** (*boolean*)
    Use direct QEMU for testing (default: ``false``).

**vm_name** (*string*)
    VM name for testing (default: auto-generated).

**memory** (*integer*)
    RAM in MB for test VM (default: ``2048``).

**vcpus** (*integer*)
    vCPU count for test VM (default: ``2``).

**uefi** (*boolean*)
    Use UEFI firmware for test (default: ``false``).

**timeout** (*integer*)
    Boot timeout in seconds (default: ``60``).

**keep_domain** (*boolean*)
    Keep libvirt domain after test (default: ``false``).

**headless** (*boolean*)
    Run test without graphics (default: ``true``).

WINDOWS OPTIONS
===============

**virtio_drivers_dir** (*string*)
    Path to virtio-win.iso or extracted VirtIO driver directory for Windows guests.
    If not specified, hyper2kvm auto-discovers the ISO at the standard location
    ``/var/lib/hyper2kvm/virtio-win.iso``. Install the standard ISO with::

        ./scripts/install-deps.sh --virtio-win

**win_hyperv** (*boolean*)
    Enable Hyper-V enlightenments in libvirt domain (default: ``true``).

MODE-SPECIFIC CONFIGURATION
============================

local mode
----------

::

    command: local
    vmdk: /path/to/vm.vmdk
    output_dir: ./output
    flatten: true
    flatten_format: qcow2

vsphere mode
------------

::

    command: vsphere

    # Connection
    vcenter: vcenter.example.com
    vc_user: administrator@vsphere.local
    vc_password_env: VC_PASSWORD
    vc_insecure: true
    dc_name: datacenter-name

    # VM selection
    vm_name: production-vm-01

    # Export method
    vs_action: export_vm
    vs_transport: vddk
    vs_vddk_libdir: /opt/vmware-vix-disklib-distrib

hyperv mode
-----------

::

    command: hyperv

    hyperv:
      host: hyperv-server.example.com
      user: Administrator
      password_env: HYPERV_PASSWORD
      transport: ntlm
      use_https: true

      vms:
        - production-vm-01

      export:
        path: C:\\HyperV-Export
        include_snapshots: true

azure mode
----------

::

    command: azure

    azure:
      subscription: "Production Subscription"
      resource_group: production-rg

      vms:
        - webapp-prod-01

      export:
        use_snapshots: true
        keep_snapshots: false
        sas_duration: 3600

      download:
        parallel: 2
        resume: true

COMPLETE EXAMPLES
=================

Linux VM Migration
------------------

::

    command: local
    vmdk: /vms/ubuntu-server.vmdk
    output_dir: ./output
    out_format: qcow2
    compress: true
    checksum: true
    fstab_mode: stabilize-all
    regen_initramfs: true
    no_grub: false
    print_fstab: true
    libvirt_test: true
    vm_name: ubuntu-converted
    memory: 2048
    vcpus: 2
    timeout: 120
    verbose: 2
    log_file: ./migration.log
    report: ./migration-report.md

Windows VM Migration
--------------------

::

    command: local
    vmdk: /vms/windows-server-2022.vmdk
    output_dir: ./output
    out_format: qcow2
    compress: true
    # virtio_drivers_dir auto-discovered at /var/lib/hyper2kvm/virtio-win.iso
    # Override: virtio_drivers_dir: /opt/virtio-win-extracted
    libvirt_test: true
    vm_name: windows-server-converted
    memory: 4096
    vcpus: 4
    uefi: true
    timeout: 180
    verbose: 2

vSphere Migration with virt-v2v
-------------------------------

::

    command: vsphere
    vcenter: vcenter.corp.local
    vc_user: migration-user@vsphere.local
    vc_password_env: VC_PASSWORD
    vc_insecure: true
    dc_name: production-dc
    vm_name: app-server-prod
    vs_action: export_vm
    vs_transport: vddk
    vs_vddk_libdir: /opt/vmware-vix-disklib-distrib
    vs_v2v: true
    output_dir: ./migrated-vms
    out_format: qcow2
    compress: true
    fstab_mode: stabilize-all
    regen_initramfs: true
    libvirt_test: true
    memory: 8192
    vcpus: 4

Azure Zero-Downtime Migration
------------------------------

::

    command: azure

    azure:
      subscription: "Production"
      resource_group: prod-rg

      vms:
        - webapp-prod-01
        - db-prod-*

      export:
        use_snapshots: true
        keep_snapshots: false
        sas_duration: 3600

      download:
        parallel: 4
        resume: true
        cleanup_vhd: true

    output_dir: ./azure-vms
    out_format: qcow2
    compress: true
    checksum: true
    fstab_mode: stabilize-all
    regen_initramfs: true
    azure_cleanup: true
    verbose: 2
    log_file: ./azure-migration.log
    report: ./azure-migration-report.md

FILES
=====

**/etc/hyper2kvm/hyper2kvm.conf**
    System-wide configuration.

**~/.config/hyper2kvm/config.yaml**
    User-specific configuration.

**./hyper2kvm.yaml**
    Project-specific configuration (current directory).

Configuration files are loaded in order, with later files overriding earlier ones.

SEE ALSO
========

**hyper2kvm**\(1),
**hyper2kvm-local**\(1),
**hyper2kvm-vsphere**\(1),
**hyper2kvm-hyperv**\(1),
**hyper2kvm-azure**\(1)

AUTHOR
======

ZyvorAI Labs Private Limited <ssahani@zyvor.dev>
