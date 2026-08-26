==================
hyper2kvm-hyperv
==================

-------------------------------------------
Migrate VMs from Microsoft Hyper-V
-------------------------------------------

:Manual section: 1
:Manual group: User Commands

SYNOPSIS
========

**hyper2kvm hyperv** [*OPTIONS*]

**hyper2kvm** **--config** *FILE* **hyperv**

DESCRIPTION
===========

The **hyperv** command migrates virtual machines from Microsoft Hyper-V hosts to
KVM/QEMU. Supports both local VHD/VHDx files and remote Hyper-V host access via
PowerShell remoting (WinRM).

MODES
=====

Local VHD conversion
--------------------

Convert locally available VHD/VHDx files::

    hyper2kvm local --vmdk /path/to/vm.vhdx --output-dir ./output

Remote Hyper-V host
-------------------

Connect to Hyper-V host via PowerShell remoting to discover, export,
and convert VMs::

    hyper2kvm hyperv \
      --host hyperv-server.example.com \
      --user Administrator \
      --password-env HYPERV_PASSWORD \
      --vm production-db-01

OPTIONS
=======

**--host** *HOSTNAME*
    Hyper-V host hostname or IP address.

**--user** *USER*
    Windows username (e.g., Administrator or DOMAIN\\user).

**--password** *PASSWORD*
    Password (use --password-env instead).

**--password-env** *VAR*
    Environment variable containing password (recommended).

**--transport** *METHOD*
    Authentication transport: ntlm (default), kerberos, basic.

**--use-https**
    Use HTTPS for WinRM (port 5986 instead of 5985).

**--vm** *NAME*
    VM name to migrate (supports wildcards).

**--resource-group** *NAME*
    Resource group filter (Hyper-V clusters).

**--export-path** *PATH*
    Export path on Hyper-V host (default: C:\\HyperV-Export).

**--include-snapshots**
    Include VM checkpoints in export.

**--cleanup-after-export**
    Remove exported files from Hyper-V host after download.

**--transfer-method** *METHOD*
    File transfer method: smb (default), winrm, ssh.

**--smb-share** *UNC*
    SMB share path (e.g., \\\\hyperv-server\\HyperV-Export).

EXAMPLES
========

Convert local VHD file
----------------------

::

    hyper2kvm local --vmdk /vms/windows-server.vhdx --output-dir ./output

Migrate from remote Hyper-V host
---------------------------------

::

    export HYPERV_PASSWORD='secure-password'

    hyper2kvm hyperv \
      --host hyperv-prod.corp.local \
      --user CORP\\migration-user \
      --password-env HYPERV_PASSWORD \
      --transport kerberos \
      --use-https \
      --vm webapp-prod-01 \
      --output-dir ./migrated-vms

Configuration file
------------------

::

    cat > hyperv-migration.yaml <<EOF
    command: hyperv

    # Connection
    hyperv:
      host: hyperv-server.example.com
      user: Administrator
      password_env: HYPERV_PASSWORD
      transport: ntlm
      use_https: true

      # VM selection
      vms:
        - production-sql-01
        - webserver-*

      # Export settings
      export:
        path: C:\\HyperV-Export
        include_snapshots: true
        cleanup_after_export: true

      # Transfer
      transfer:
        method: smb
        smb_share: \\\\hyperv-server\\HyperV-Export

    # Output
    output_dir: ./migrated-vms
    out_format: qcow2
    compress: true

    # Guest fixes
    fstab_mode: stabilize-all
    regen_initramfs: true
    virtio_drivers_dir: /opt/virtio-win-extracted
    EOF

    hyper2kvm --config hyperv-migration.yaml hyperv

PREREQUISITES
=============

For remote Hyper-V access:

* WinRM enabled on Hyper-V host
* Python pywinrm package: ``pip install pywinrm``
* Appropriate network access and credentials

Enable WinRM on Hyper-V host (PowerShell as Administrator)::

    Enable-PSRemoting -Force
    Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value "*" -Force
    Restart-Service WinRM

ENVIRONMENT
===========

**HYPERV_PASSWORD**
    Hyper-V host password (recommended).

FILES
=====

See **hyper2kvm**\(1) and **hyper2kvm.conf**\(5).

SEE ALSO
========

**hyper2kvm**\(1),
**hyper2kvm-local**\(1)

AUTHOR
======

ZyvorAI Labs Private Limited <ssahani@zyvor.dev>
