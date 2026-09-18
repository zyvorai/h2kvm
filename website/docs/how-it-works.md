---
sidebar_position: 2
---

# How it works

The disk is fixed before it is powered on. Then you watch it boot, and you can run it on Zeus OS or Machina.

```text
 source disk
   →  GuestKit     inspect the disk before power-on
   →  h2kvm        any hypervisor to KVM
   →  Zorvia       watch the VM boot
   →  Zeus OS      or Machina, where you keep running it
```

| Product | What it does | Site | Repo |
|---|---|---|---|
| GuestKit | Inspects the disk offline so you know it is safe before power-on | [zyvor.dev/guestkit](https://zyvor.dev/guestkit) | [zyvorai/guestkit](https://github.com/zyvorai/guestkit) |
| h2kvm | Any hypervisor to KVM. The guest is fixed so the VM boots the first time | [zyvor.dev/h2kvm](https://zyvor.dev/h2kvm) | [zyvorai/h2kvm](https://github.com/zyvorai/h2kvm) |
| Zorvia | Craft and run KubeVirt VMs without hand-written CRDs | [zyvor.dev/zorvia](https://zyvor.dev/zorvia) | [zyvorai/zorvia](https://github.com/zyvorai/zorvia) |
| Zeus OS | The visual infrastructure OS for KubeVirt | [zyvor.dev/zeus-os](https://zyvor.dev/zeus-os) | [zyvorai/zeus-os](https://github.com/zyvorai/zeus-os) |
| Machina | One control plane for the libvirt hosts you already run | [zyvor.dev/machina](https://zyvor.dev/machina) | [zyvorai/machina](https://github.com/zyvorai/machina) |

## No VDDK

On 10 September 2026 VMware told [The Register](https://www.theregister.com/virtualization/2026/09/10/vmware-defends-ending-downloads-of-sdk-that-helps-vm-backups-or-migrations-to-rivals/5295421) that the Virtual Disk Development Kit was never a customer entitlement, and that its licensed use was backup and recovery for select partners.

h2kvm does not use that kit. Disks leave through the vSphere API and NFS, then convert offline.

```text
  vSphere                          Nutanix AHV
     │                                  │
     ▼                                  ▼
  NFC lease (HTTPS)                 NFS pickup
  govc export.ovf / .ova            storage containers
  datastore /folder
     │                                  │
     └──────────────┬───────────────────┘
                    ▼
              h2kvm + GuestKit
           convert · repair · deploy
                    │
                    ▼
         libvirt · KubeVirt · Zeus OS

  VDDK  —  not on this path
```

| Path | How the disk moves | VDDK |
|---|---|:---:|
| Transiva NFC | govmomi HTTP NFC lease writes OVF plus disks | No |
| h2kvm `govc` | `export.ovf`, then `export.ova` — the same NFC lease | No |
| Datastore HTTPS | `/folder` download of datastore files | No |
| Nutanix | Transiva NFS pickup of storage containers | No |
| Disk already on disk | `h2kvmctl local` converts VMDK, VHDX, raw, and the other formats | No |

Copying the disk was never the hard part. First boot fails when the bootloader, VirtIO, or Windows still points at the old hypervisor. GuestKit does that work before power-on.

The longer version is [VDDK was never the exit](https://github.com/zyvorai/h2kvm/blob/main/docs/marketing/vddk-was-never-the-exit.md).
