================
h2kvm-azure
================

-------------------------------------------
Download and convert VMs from Azure
-------------------------------------------

:Manual section: 1
:Manual group: User Commands

SYNOPSIS
========

**h2kvm azure** [*OPTIONS*]

**h2kvm** **--config** *FILE* **azure**

DESCRIPTION
===========

The **azure** command downloads virtual machines from Microsoft Azure and converts
them to KVM/QCOW2 format. Supports zero-downtime migration using snapshots.

PREREQUISITES
=============

* Azure CLI installed: ``curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash``
* Logged in to Azure: ``az login``
* Appropriate subscription selected: ``az account set --subscription NAME``

OPTIONS
=======

**--subscription** *ID*
    Azure subscription ID or name.

**--resource-group** *NAME*
    Azure resource group name.

**--vm** *NAME*
    VM name to migrate (supports wildcards: vm-prod-*).

**--use-snapshot**
    Create snapshot before export (zero downtime, recommended).

**--snapshot-prefix** *PREFIX*
    Prefix for snapshot names (default: h2kvm).

**--keep-snapshots**
    Keep snapshots after download (default: delete).

**--sas-duration** *SECONDS*
    SAS token validity duration (default: 86400 = 24 hours).

**--parallel** *N*
    Number of parallel downloads (default: 2).

**--resume**
    Resume interrupted downloads (default: enabled).

**--cleanup-vhd**
    Delete VHD files after conversion to QCOW2.

EXAMPLES
========

Download and convert single VM
-------------------------------

::

    # Login to Azure
    az login
    az account set --subscription "Production"

    # Migrate VM
    h2kvm azure \
      --subscription "Production" \
      --resource-group production-rg \
      --vm webapp-prod-01 \
      --use-snapshot \
      --output-dir ./azure-vms

Zero-downtime migration with snapshots
---------------------------------------

::

    h2kvm azure \
      --subscription "12345678-1234-1234-1234-123456789012" \
      --resource-group prod-rg \
      --vm database-prod-01 \
      --use-snapshot \
      --keep-snapshots \
      --output-dir ./migrated-vms \
      --compress

Batch migration
---------------

::

    cat > azure-migration.yaml <<EOF
    command: azure

    azure:
      subscription: "Production Subscription"
      resource_group: production-rg

      # VM selection (supports wildcards)
      vms:
        - webapp-prod-*
        - db-prod-01

      # Export with snapshots (zero downtime)
      export:
        use_snapshots: true
        snapshot_template: "{vm_name}-migration-{timestamp}"
        keep_snapshots: false
        sas_duration: 3600  # 1 hour

      # Download settings
      download:
        parallel: 4
        resume: true
        cleanup_vhd: true

    # Output configuration
    output_dir: ./azure-vms
    out_format: qcow2
    compress: true
    checksum: true

    # Guest fixes
    fstab_mode: stabilize-all
    regen_initramfs: true
    azure_cleanup: true  # Remove Azure-specific configs
    EOF

    h2kvm --config azure-migration.yaml azure

List VMs (discovery mode)
--------------------------

::

    h2kvm azure \
      --subscription "Production" \
      --resource-group prod-rg \
      --list-only

WORKFLOW
========

The Azure migration follows these steps:

1. **Discover VMs** - List VMs in resource group
2. **Create Snapshots** - Snapshot OS and data disks (VM keeps running!)
3. **Grant SAS Access** - Generate time-limited download URLs
4. **Download VHDs** - Download disk images via HTTPS (resumable)
5. **Convert to QCOW2** - Convert VHD to QCOW2 format
6. **Fix Guest OS** - Remove Azure configs, fix boot
7. **Cleanup** - Revoke SAS access, delete temporary snapshots

COST OPTIMIZATION
=================

Azure charges for:

* **Snapshots**: ~$0.05/GB/month (delete after migration)
* **Egress**: ~$0.09/GB (download charges)
* **SAS tokens**: Free

Tips to minimize costs:

* Use short SAS duration (``--sas-duration 3600`` = 1 hour)
* Delete snapshots immediately (``--no-keep-snapshots``)
* Download from same Azure region if possible (lower egress)
* Clean up VHD files after conversion (``--cleanup-vhd``)

Example cost for 10 VMs × 100GB each:

* Snapshots (1 hour): ~$0.10
* Egress: ~$90.00
* **Total**: ~$90 one-time (vs. $700/month to run in Azure!)

ENVIRONMENT
===========

Authentication is handled by Azure CLI. Ensure you're logged in::

    az login
    az account show  # Verify current subscription

FILES
=====

See **h2kvm**\(1) and **h2kvm.conf**\(5).

SEE ALSO
========

**h2kvm**\(1),
**az**\(1),
**az-vm**\(1),
**az-disk**\(1),
**az-snapshot**\(1)

AUTHOR
======

ZyvorAI Labs Private Limited <ssahani@zyvor.dev>
