==================
h2kvm-vsphere
==================

-------------------------------------------
Migrate VMs from VMware vSphere/ESXi
-------------------------------------------

:Manual section: 1
:Manual group: User Commands

SYNOPSIS
========

**h2kvm vsphere** [*OPTIONS*]

**h2kvm** **--config** *FILE* **vsphere**

DESCRIPTION
===========

The **vsphere** command migrates virtual machines from VMware vSphere/ESXi
environments to KVM/QEMU.

Supports multiple methods:

* **govc CLI** - NFC export of OVF/OVA (recommended)
* **HTTP download** - Direct VMDK download via /folder API
* **OVF Tool** - Export via VMware OVF Tool

OPTIONS
=======

Connection Options
------------------

**--vcenter** *HOST*
    vCenter or ESXi hostname/IP.

**--vc-user** *USER*
    vCenter username (e.g., administrator@vsphere.local).

**--vc-password** *PASSWORD*
    vCenter password (use --vc-password-env instead).

**--vc-password-env** *VAR*
    Environment variable containing password (recommended).

**--vc-insecure**
    Skip SSL certificate verification.

**--vc-port** *PORT*
    vCenter port (default: 443).

**--dc-name** *NAME*
    Datacenter name in vCenter inventory.

VM Selection
------------

**--vm-name** *NAME*
    VM name to migrate (supports wildcards).

**--vs-datacenter** *NAME*
    Datacenter name (alternative to --dc-name).

Export Method
-------------

**--vs-action** *ACTION*
    Export action:

    * **export_vm** - Export with govc (OVF/OVA) or HTTPS /folder
    * **download_only_vm** - Download VMDK files only

Download Options
----------------

**--vs-concurrency** *N*
    Parallel downloads (default: 4).

**--vs-use-async-http**
    Use async HTTP for large files.

**--vs-include-glob** *PATTERN*
    File patterns to include (e.g., "*.vmdk").

**--vs-exclude-glob** *PATTERN*
    File patterns to exclude (e.g., "*.log").

**--vs-max-files** *N*
    Maximum files to download (default: 5000).

EXAMPLES
========

Export with govc
----------------

Recommended path. govc handles the HTTP NFC lease itself::

    export VC_PASSWORD='your-password'

    h2kvm vsphere \
      --vcenter vcenter.example.com \
      --vc-user administrator@vsphere.local \
      --vc-password-env VC_PASSWORD \
      --dc-name production-dc \
      --vm-name webserver-01 \
      --vs-action export_vm \
      --output-dir ./migrated-vms

Download-only mode with govc
-----------------------------

Download VMDK files for offline conversion::

    h2kvm vsphere \
      --vcenter esxi-host.example.com \
      --vc-user root \
      --vc-password-env ESXi_PASSWORD \
      --vm-name test-vm \
      --vs-action download_only_vm \
      --output-dir ./downloads

Configuration file example
--------------------------

::

    cat > vsphere-migration.yaml <<EOF
    command: vsphere

    # vCenter connection
    vcenter: vcenter.corp.local
    vc_user: migration-user@vsphere.local
    vc_password_env: VC_PASSWORD
    vc_insecure: true
    dc_name: production-dc

    # VM selection
    vm_name: app-server-*

    # Export method
    vs_action: export_vm

    # Output
    output_dir: ./migrated-vms
    out_format: qcow2
    compress: true

    # Guest fixes
    fstab_mode: stabilize-all
    regen_initramfs: true

    # Validation
    libvirt_test: true
    memory: 4096
    vcpus: 2
    EOF

    export VC_PASSWORD='secure-password'
    h2kvm --config vsphere-migration.yaml vsphere

PREREQUISITES
=============

For govc (recommended):

* Install govc: ``curl -L https://github.com/vmware/govmomi/releases/latest/download/govc_Linux_x86_64.tar.gz | sudo tar xzf - -C /usr/local/bin govc``
* Install pyvmomi: ``pip install pyvmomi``

For OVF Tool method:

* Download from: ``https://developer.broadcom.com/tools/open-virtualization-format-ovf-tool/latest``
* Install: ``sudo mkdir -p /opt/ovftool && sudo unzip VMware-ovftool-*.zip -d /opt/ovftool``

Or install everything at once::

    sudo ./scripts/quickstart.sh

govc Export (End-to-End)
------------------------

Export VM via govc NFC and convert to libvirt::

    cat > govc-export.yaml <<EOF
    cmd: vsphere
    vs_action: export_vm
    export_mode: ovf_export
    vs_control_plane: govc

    vcenter: 10.73.213.134
    vc_user: administrator@vsphere.local
    vc_password_env: VC_PASSWORD
    vc_insecure: true
    dc_name: data
    govc_url: "https://10.73.213.134/sdk"
    govc_insecure: true
    govc_datacenter: data
    govc_export_remove_cdroms: true

    vm_name: my-linux-vm
    output_dir: ./output
    flatten: true
    to_output: my-vm.qcow2
    out_format: qcow2
    compress: true

    fstab_mode: stabilize-all
    regen_initramfs: true
    remove_vmware_tools: true

    emit_domain_xml: true
    uefi: true
    machine: q35
    disk_bus: virtio
    libvirt_network: default
    libvirt_test: true
    EOF

    export VC_PASSWORD='password'
    sudo h2kvmctl --config govc-export.yaml

OVF Tool Export
---------------

Export VM via OVF Tool::

    cat > ovftool-export.yaml <<EOF
    cmd: vsphere
    vs_action: ovftool_export

    vcenter: 10.73.213.134
    vc_user: administrator@vsphere.local
    vc_password_env: VC_PASSWORD
    vc_insecure: true
    dc_name: data

    ovftool_no_ssl_verify: true
    ovftool_accept_all_eulas: true

    vm_name: my-linux-vm
    output_dir: ./output
    flatten: true
    to_output: my-vm.qcow2
    out_format: qcow2
    compress: true

    fstab_mode: stabilize-all
    regen_initramfs: true

    emit_domain_xml: true
    uefi: true
    machine: q35
    libvirt_test: true
    EOF

    export VC_PASSWORD='password'
    sudo h2kvmctl --config ovftool-export.yaml

ENVIRONMENT
===========

**VC_PASSWORD**
    vCenter password (recommended over command-line).

FILES
=====

See **h2kvm**\(1) and **h2kvm.conf**\(5).

SEE ALSO
========

**h2kvm**\(1),
**h2kvm.conf**\(5),
**govc**\(1)

AUTHOR
======

ZyvorAI Labs Private Limited <ssahani@zyvor.dev>
