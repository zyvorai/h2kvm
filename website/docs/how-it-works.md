---
sidebar_position: 2
---

# How it works

![h2kvm talks to vSphere over HTTPS. vCenter SOAP, ESXi NFC lease, then the disk.](/h2kvm-vsphere-path.jpg)

The disk is fixed before it is powered on. h2kvm picks a disk up from wherever the VM lives today, repairs the guest offline, converts it to qcow2, and hands it to one deploy target.

![h2kvm picks up disks from vSphere, ESXi, Azure and local files, repairs them offline with GuestKit, converts to qcow2, then deploys to a KubeVirt cluster (Zorvia, Zeus OS), a libvirt host (Machina) or OpenStack.](/h2kvm-flow.svg)

## Where disks come from

There are no subcommands and no `--source` flag. Pick the mode with `--cmd`, or `cmd:` in a YAML config passed with `--config`.

| Source | How h2kvm picks it up | Entry point | Status |
|---|---|---|---|
| vSphere (govc) | `govc export.ovf` pulls the OVF and disks over an HTTPS NFC lease. h2kvm packs the OVA itself | `--cmd vsphere --vcenter … --vs-vm …` | Implemented |
| vSphere (datastore) | `GET /folder/…` over HTTPS with the vCenter session, resumable | `--cmd vsphere --vs-download-only` | Implemented |
| vSphere (ovftool) | VMware's `ovftool`, if you have it installed | `--cmd vsphere --ovftool-path …` | Implemented, external binary |
| ESXi over SSH | Streams the disk with `ssh … cat`, with progress | `--cmd fetch-and-fix --host … --remote …` | Implemented |
| Azure | `az` CLI: snapshot, SAS URL, ranged HTTPS download | `--cmd azure --azure-resource-group …` | Implemented |
| Files you already have | Disk on the machine running h2kvm. The qemu-img format comes from the suffix | `--cmd local --vmdk FILE` (any format), or `ova`, `ovf`, `vhd`, `raw`, `ami` | Implemented |
| Folder or manifest | The daemon watches a folder. `--manifest` runs a declarative 8-stage pipeline | `--cmd daemon`, `--manifest FILE` | Implemented |
| Nutanix AHV | Not in this repo. Transiva does the NFS pickup, then you feed the file to `--cmd local` | — | Via Transiva |
| AWS, Proxmox Backup Server | Library modules only, not reachable from the CLI | — | Not exposed |
| GCP, Xen, VirtualBox, remote Hyper-V | No pickup code. Their disk files (VDI, VHDX) work as local files | — | Not implemented |

## What happens to the disk

1. **Pick up.** Extract an OVA or VHD, or download the disk, then discover the disk files.
2. **Inspect and flatten.** VMDKs are inspected first. `--flatten` merges a snapshot chain into one working image.
3. **Repair offline.** GuestKit runs `run_migrate_repair` on the disk image, then h2kvm injects cloud-init, first-boot, network, user, service and hostname config.
4. **Convert and check.** `qemu-img convert` to qcow2, then `qemu-img check` on the result.
5. **Deploy, or stop.** Hand the qcow2 to one target below, or keep the file.

## Where the VM lands

| Target | What h2kvm does | Enable with | Zyvor product on top |
|---|---|---|---|
| KubeVirt cluster | Uploads the disk (containerDisk, CDI `virtctl image-upload`, or a PVC copy), then creates a `kubevirt.io/v1` VirtualMachine on whatever cluster your kubeconfig points at | `--deploy-k8s` | Zorvia crafts and watches KubeVirt VMs. Zeus OS is the visual OS for the cluster |
| libvirt host | Emits the domain XML and runs `virsh define`, optionally start, on the host h2kvm runs on | `--emit-domain-xml` | Machina is the control plane for libvirt hosts |
| OpenStack | openstacksdk uploads the qcow2 to Glance and can boot a Nova server. Endpoints come from the Keystone catalog | `--deploy-openstack` | None. Third-party cloud |

- **One target per run.** The CLI and web API reject combining them.
- **h2kvm has no API link to Zorvia, Zeus OS or Machina.** It deploys to the cluster or host. Those products are what run or manage that endpoint afterwards.
- **OpenStack failures are non-fatal by default.** A failed Glance or Nova step is logged, and the run still succeeds.

## The Zyvor products

| Product | What it does | Site | Repo |
|---|---|---|---|
| GuestKit | Inspects the disk offline so you know it is safe before power-on | [zyvor.dev/guestkit](https://zyvor.dev/guestkit) | [zyvorai/guestkit](https://github.com/zyvorai/guestkit) |
| h2kvm | Any hypervisor to KVM. The guest is fixed so the VM boots the first time | [zyvor.dev/h2kvm](https://zyvor.dev/h2kvm) | [zyvorai/h2kvm](https://github.com/zyvorai/h2kvm) |
| Zorvia | Craft and run KubeVirt VMs without hand-written CRDs | [zyvor.dev/zorvia](https://zyvor.dev/zorvia) | [zyvorai/zorvia](https://github.com/zyvorai/zorvia) |
| Zeus OS | The visual infrastructure OS for KubeVirt | [zyvor.dev/zeus-os](https://zyvor.dev/zeus-os) | [zyvorai/zeus-os](https://github.com/zyvorai/zeus-os) |
| Machina | One control plane for the libvirt hosts you already run | [zyvor.dev/machina](https://zyvor.dev/machina) | [zyvorai/machina](https://github.com/zyvorai/machina) |

First boot fails when the bootloader, VirtIO, or Windows still points at the old hypervisor. GuestKit does that work before power-on.
