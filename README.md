<div align="center">

# h2kvm

### Any hypervisor → KVM. Convert offline. Fix the guest. Deploy with confidence.

Pick up VMs from **vSphere, ESXi, Azure**, or any disk you already have (**VMDK, VHDX, VDI, raw, OVA/OVF**) —  
fix the guest offline, then land it on **KubeVirt, libvirt, or OpenStack**. Web control plane and Kubernetes operator included.

**First-boot science for hypervisor exit** · lands on KubeVirt (**[Zorvia](https://zyvor.dev/zorvia)** · **[Zeus OS](https://zyvor.dev/zeus-os)**), libvirt (**[Machina](https://zyvor.dev/machina)**) or OpenStack · part of the [Zyvor](https://zyvor.dev/?utm_source=github&utm_medium=h2kvm&utm_campaign=readme_hero) suite

![h2kvm — any hypervisor to KVM. Convert offline.](docs/social/h2kvm-share-card.png)

<br/>

[![Release](https://img.shields.io/github/v/release/zyvorai/h2kvm?color=F97316)](https://github.com/zyvorai/h2kvm/releases/latest)
[![GuestKit](https://img.shields.io/pypi/v/hypersdk-guestkit.svg)](https://pypi.org/project/hypersdk-guestkit/)
[![Python](https://img.shields.io/badge/python-3.10+-3776AB.svg)](https://www.python.org/)
[![License: Zyvor Production v1.0](https://img.shields.io/badge/License-Zyvor%20Production%20v1.0-blue.svg)](LICENSE)

<br/>

[![Book an Enterprise demo](https://img.shields.io/badge/Book_an_Enterprise_demo-F97316?style=for-the-badge)](https://zyvor.dev/contact?intent=demo&utm_source=github&utm_medium=h2kvm&utm_campaign=readme_hero)
[![30-day PoC](https://img.shields.io/badge/30--day_PoC-111827?style=for-the-badge)](https://zyvor.dev/poc?utm_source=github&utm_medium=h2kvm&utm_campaign=readme_hero)
[![Watch the demo](https://img.shields.io/badge/Watch_the_demo-22C55E?style=for-the-badge)](https://www.youtube.com/watch?v=lQP1sd5Ftkc)

**[How it works](#how-it-works)** ·
**[Install](#install)** ·
**[Quick start](#quick-start)** ·
**[GuestKit](#guestkit)** ·
**[Remote deploy](#remote-lab-deploy)** ·
**[Demos](#see-it-in-action)** ·
**[CE vs Enterprise](#community-vs-enterprise)** ·
**[Docs](docs/README.md)** ·
**[Product](https://zyvor.dev/h2kvm?utm_source=github&utm_medium=h2kvm)**

</div>

---

## How it works

h2kvm picks up a disk from wherever the VM lives today, repairs the guest **offline** so it boots on KVM the first time, converts it to qcow2, and hands it to **one** deploy target. Nothing is powered on until the disk is fixed.

![h2kvm picks up disks from vSphere, ESXi, Azure and local files, repairs them offline with GuestKit, converts to qcow2, then deploys to a KubeVirt cluster (Zorvia, Zeus OS), a libvirt host (Machina) or OpenStack.](docs/social/h2kvm-flow.svg)

```mermaid
flowchart LR
  subgraph SRC["Sources · pick up"]
    VS["vSphere<br/>govc · datastore HTTPS"]
    ESX["ESXi host<br/>ssh stream"]
    AZ["Azure<br/>az snapshot"]
    FILES["Files<br/>VMDK · VHD(X) · OVA/OVF · raw"]
    NTX["Nutanix AHV<br/>via Transiva"]
  end
  P["h2kvm<br/>pick up → inspect, flatten → GuestKit repair → qemu-img convert + check"]
  subgraph KV["KubeVirt cluster · --deploy-k8s"]
    ZV["Zorvia · Zeus OS"]
  end
  subgraph LV["libvirt host · --emit-domain-xml"]
    MA["Machina"]
  end
  subgraph OS["OpenStack · --deploy-openstack"]
    GN["Glance · Nova"]
  end
  VS --> P
  ESX --> P
  AZ --> P
  FILES --> P
  NTX -.->|"exported file"| P
  P -->|"k8s API"| KV
  P -->|"virsh"| LV
  P -->|"Glance, Nova"| OS
```

### Where disks come from

There are no subcommands and no `--source` flag. Pick the mode with `--cmd` (or `cmd:` in a YAML config passed with `--config`).

| Source | How h2kvm picks it up | Entry point | Status |
|--------|-----------------------|-------------|--------|
| **vSphere** (govc) | `govc export.ovf` pulls the OVF and disks over an HTTPS NFC lease. h2kvm packs the OVA itself | `--cmd vsphere --vcenter … --vs-vm …` | Implemented |
| **vSphere** (datastore) | `GET /folder/…` over HTTPS with the vCenter session, resumable | `--cmd vsphere --vs-download-only` | Implemented |
| **vSphere** (ovftool) | VMware's `ovftool`, if you have it installed | `--cmd vsphere --ovftool-path …` | Implemented, external binary |
| **ESXi over SSH** | Streams the disk with `ssh … cat`, with progress | `--cmd fetch-and-fix --host … --remote …` | Implemented |
| **Azure** | `az` CLI: snapshot, SAS URL, ranged HTTPS download | `--cmd azure --azure-resource-group …` | Implemented |
| **Files you already have** | Disk on the machine running h2kvm. The qemu-img format comes from the suffix | `--cmd local --vmdk FILE` (any format), or `ova`, `ovf`, `vhd`, `raw`, `ami` | Implemented |
| **Folder or manifest** | The daemon watches a folder. `--manifest` runs a declarative 8-stage pipeline | `--cmd daemon`, `--manifest FILE` | Implemented |
| **Nutanix AHV** | Not in this repo. [Transiva](https://github.com/zyvorai/transiva) does the NFS pickup, then you feed the file to `--cmd local` | — | Via Transiva |
| **AWS, Proxmox Backup Server** | Library modules only, not reachable from the CLI | — | Not exposed |
| **GCP, Xen, VirtualBox, remote Hyper-V** | No pickup code. Their disk files (VDI, VHDX) work as local files | — | Not implemented |

### What happens to the disk

1. **Pick up.** Extract an OVA or VHD, or download the disk, then discover the disk files.
2. **Inspect and flatten.** VMDKs are inspected first. `--flatten` merges a snapshot chain into one working image.
3. **Repair offline.** [GuestKit](#guestkit) runs `run_migrate_repair` on the disk image, then h2kvm injects cloud-init, first-boot, network, user, service and hostname config.
4. **Convert and check.** `qemu-img convert` to qcow2, then `qemu-img check` on the result.
5. **Deploy, or stop.** Hand the qcow2 to one target below, or keep the file.

### Where the VM lands

| Target | What h2kvm does | Enable with | Zyvor product on top |
|--------|-----------------|-------------|----------------------|
| **KubeVirt cluster** | Uploads the disk (containerDisk, CDI `virtctl image-upload`, or a PVC copy), then creates a `kubevirt.io/v1` VirtualMachine on whatever cluster your kubeconfig points at | `--deploy-k8s` | [Zorvia](https://zyvor.dev/zorvia) crafts and watches KubeVirt VMs. [Zeus OS](https://zyvor.dev/zeus-os) is the visual OS for the cluster |
| **libvirt host** | Emits the domain XML and runs `virsh define`, optionally start, on the host h2kvm runs on | `--emit-domain-xml` | [Machina](https://zyvor.dev/machina) is the control plane for libvirt hosts |
| **OpenStack** | openstacksdk uploads the qcow2 to Glance and can boot a Nova server. Endpoints come from the Keystone catalog | `--deploy-openstack` | None. Third-party cloud |

- **One target per run.** The CLI and web API reject combining them. See [OpenStack deployment](docs/guides/openstack-deployment.md).
- **h2kvm has no API link to Zorvia, Zeus OS or Machina.** It deploys to the cluster or host. Those products are what run or manage that endpoint afterwards.
- **OpenStack failures are non-fatal by default.** A failed Glance or Nova step is logged, and the run still succeeds.

| Product | What zyvor.dev says | Site | Repo |
|---------|---------------------|------|------|
| [GuestKit](https://zyvor.dev/guestkit) | Inspects the disk offline so you know it is safe before power-on | [zyvor.dev/guestkit](https://zyvor.dev/guestkit) | [zyvorai/guestkit](https://github.com/zyvorai/guestkit) |
| [h2kvm](https://zyvor.dev/h2kvm) | Any hypervisor to KVM. The guest is fixed so the VM boots the first time | [zyvor.dev/h2kvm](https://zyvor.dev/h2kvm) | [zyvorai/h2kvm](https://github.com/zyvorai/h2kvm) |
| [Zorvia](https://zyvor.dev/zorvia) | Craft and run KubeVirt VMs without hand-written CRDs | [zyvor.dev/zorvia](https://zyvor.dev/zorvia) | [zyvorai/zorvia](https://github.com/zyvorai/zorvia) |
| [Zeus OS](https://zyvor.dev/zeus-os) | The visual infrastructure OS for KubeVirt | [zyvor.dev/zeus-os](https://zyvor.dev/zeus-os) | [zyvorai/zeus-os](https://github.com/zyvorai/zeus-os) |
| [Machina](https://zyvor.dev/machina) | One control plane for the libvirt hosts you already run | [zyvor.dev/machina](https://zyvor.dev/machina) | [zyvorai/machina](https://github.com/zyvorai/machina) |

Hypervisor exit fails when the bootloader is wrong, or Windows still points at the old hypervisor, **after** you cut over. GuestKit and h2kvm do that work before power-on. Zorvia and Zeus OS are where you keep running the VM on KubeVirt, and Machina is where you keep running it on libvirt hosts.

---

## Install

**v1.4.0** — on PyPI. GuestKit, the offline repair engine, is the `guestkit` extra.

```bash
pip install "h2kvm[guestkit]==1.4.0"
```

From source (extras / development):

```bash
git clone https://github.com/zyvorai/h2kvm.git
cd h2kvm
pip install -e ".[full]"
```

Host needs Linux with `qemu-img`, `qemu-nbd`, and `losetup`. Repair and NBD mounts often need root or `H2KVM_USE_SUDO=1`.

Shell Completion is optional. Install argcomplete, then see [docs/getting-started/01-Installation.md](docs/getting-started/01-Installation.md#shell-completion-optional).

| Artifact | Where |
|----------|--------|
| **h2kvm 1.4.0** | [PyPI](https://pypi.org/project/h2kvm/1.4.0/) |
| **hypersdk-guestkit ≥ 1.1.0** | [PyPI](https://pypi.org/project/hypersdk-guestkit/) |
| **Operator image** | `ghcr.io/zyvorai/h2kvm/operator:v1.4.0` |

---

## Quick start

```bash
# Local VMDK → qcow2 (GuestKit repair is the default backend)
h2kvmctl --cmd local --vmdk ubuntu.vmdk --to-output ubuntu.qcow2 --backend guestkit

# vSphere → repair → KubeVirt (there are no subcommands; --cmd picks the mode)
h2kvmctl --cmd vsphere --vcenter vc.example.com --vc-user admin \
  --vc-password-env VC_PASSWORD --vs-vm web-prod-01 \
  --output-dir ./out --to-output web-prod-01.qcow2 --flatten \
  --deploy-k8s --k8s-namespace vms

# Web dashboard
h2kweb
# → https://localhost:5070

# Kubernetes operator
kubectl apply -f operator/deploy/
```

| Surface | What you get |
|---------|----------------|
| **CLI** | `h2kvmctl` / `h2k` |
| **Web** | h2kweb dashboard — `web/` |
| **Operator** | K8s / OpenShift — `operator/`, `olm/` |
| **Helm** | Production charts — `helm/` |
| **Fix engine** | GuestKit `run_migrate_repair` + h2kvm injectors |

| You want… | Go here |
|-----------|---------|
| Full docs | [docs/README.md](docs/README.md) |
| Remote SSH deploy | [docs/deployment/deploy-remote.md](docs/deployment/deploy-remote.md) |
| GuestKit wiring | [docs/architecture/GUESTKIT.md](docs/architecture/GUESTKIT.md) |
| Examples | [examples/](examples/) |
| CE vs Enterprise | [docs/ce-vs-enterprise.md](docs/ce-vs-enterprise.md) |

---

## GuestKit

Offline inspect and repair run through **[GuestKit](https://github.com/zyvorai/guestkit)** — fstab, bootloader, initramfs, and hypervisor-aware fixes via `guestkit.run_migrate_repair()`. h2kvm does not re-implement that engine in pure Python.

```python
from h2kvm.core import guestkit_client

report = guestkit_client.doctor("ubuntu.qcow2", target="kvm", explain=True)
result = guestkit_client.migrate_repair("ubuntu.qcow2", target="kvm", apply=True)
```

```bash
# Pre-flight with the GuestKit CLI
guestkit doctor ubuntu.vmdk --target kvm --explain
```

**Debian/Ubuntu libvirt:** after convert, `chown libvirt-qemu:kvm` on the output qcow2 before `virsh start`. See [troubleshooting](docs/guides/troubleshooting.md#permissions-and-ownership).

More: [GUESTKIT.md](docs/architecture/GUESTKIT.md) · [API](docs/reference/api/guestkit.md) · [GuestKit repo](https://github.com/zyvorai/guestkit) · [Zorvia](https://github.com/zyvorai/zorvia)

---

## Remote lab deploy

One SSH command installs system deps, h2kvm, GuestKit (from PyPI), and optionally h2kweb:

```bash
./scripts/deploy-remote.sh 175.110.122.71 sus --keep-sources

# GuestKit CLI binary (separate repo)
cd /path/to/guestkit
GUESTKIT_ZYVOR_ACCEPT=1 ./scripts/deploy-remote.sh 175.110.122.71 sus --quick --key
```

End-to-end demo on the target (osboxes Ubuntu VMDK):

```bash
sudo bash ~/.deployments/h2kvm/scripts/demo-libvirt.sh \
  ~/demo/ubuntu2404.vmdk ubuntu-test --memory 4096 --vcpus 2
```

Full guide: **[docs/deployment/deploy-remote.md](docs/deployment/deploy-remote.md)**

---

## See it in action

<table>
<tr>
<td width="50%" align="center">
<a href="https://www.youtube.com/watch?v=lQP1sd5Ftkc">
<img src="https://img.youtube.com/vi/lQP1sd5Ftkc/hqdefault.jpg" alt="h2kvm live console tour" width="100%">
<br><b>▶ Live console tour</b>
</a>
<br><sub>h2kweb — progress, migrate, deploy</sub>
</td>
<td width="50%" align="center">
<a href="https://www.youtube.com/watch?v=SF8N7gFPS0Q">
<img src="https://img.youtube.com/vi/SF8N7gFPS0Q/hqdefault.jpg" alt="h2kvm full tutorial" width="100%">
<br><b>▶ Full tutorial</b>
</a>
<br><sub>End-to-end conversion walkthrough</sub>
</td>
</tr>
<tr>
<td width="50%" align="center">
<a href="https://www.youtube.com/watch?v=etel7HPgm-U">
<img src="https://img.youtube.com/vi/etel7HPgm-U/hqdefault.jpg" alt="h2kvm feature demo" width="100%">
<br><b>▶ Feature deep dive</b>
</a>
<br><sub>Offline fix · Windows · targets</sub>
</td>
<td width="50%" align="center">
<a href="https://zyvor.dev/h2kvm?utm_source=github&utm_medium=h2kvm&utm_campaign=readme_demos">
<img src="https://img.youtube.com/vi/lQP1sd5Ftkc/mqdefault.jpg" alt="h2kvm product" width="100%">
<br><b>▶ Product page</b>
</a>
<br><sub>Architecture · editions · PoC</sub>
</td>
</tr>
</table>

<p align="center">
  Recorded against real deployments — <a href="https://zyvor.dev/demo?utm_source=github&utm_medium=h2kvm"><b>more demos →</b></a>
</p>

---

## Why teams switch

| Before h2kvm | With h2kvm |
|--------------|------------|
| 18-month “migration project” | One pipeline: browse → migrate → deploy |
| Guest drivers break on first KVM boot | **GuestKit** offline fix for 35+ OS versions |
| Windows needs a war room of tribal scripts | Automated VirtIO / hivex / RDP path |
| No visibility mid-conversion | **h2kweb** progress · webhooks · email |
| K8s teams stuck on libvirt YAML | Libvirt → **KubeVirt** one-click path |
| Cutover outcomes unowned | Enterprise: **96.8%** automated first-boot + PS |

---

## Community vs Enterprise

**Community proves convert. Enterprise owns cutover night.**

CE is for labs and single-cluster PoC. Moving a Windows estate, SAN-backed waves, or multi-site fleets? No war-room, no HA fabric, no LTS/CVE contract on CE. **Buy Enterprise.**

| | Community / public CE *(this repo)* | **[Enterprise](https://zyvor.dev/h2kvm?utm_source=github&utm_medium=h2kvm)** |
|---|---|---|
| **Who it is for** | Labs · DIY pipelines | Migration leads · **multi-wave cutovers** |
| **Convert + GuestKit offline fix** | ✅ | ✅ + validated fleet playbooks |
| **CLI · h2kweb · operator** | ✅ Eval / single-cluster | ✅ **HA** · multi-namespace tenancy |
| **Windows path** | Automated VirtIO / registry | ✅ + **war-room / PS runbooks** |
| **Storage pipelines** | Local / libvirt / KubeVirt / Glance | ✅ + **SAN / Ceph / NetApp** |
| **Pre-flight** | GuestKit planner | ✅ + **GuestKit fleet risk scoring** |
| **First-boot** | Strong offline fix | **96.8%** automated path + PS |
| **Support** | Community | **SLA · LTS · CVE** · hypervisor-exit programs |
| **Day-2** | Hand off to **Zorvia · Zeus OS** (KubeVirt) or **Machina** (libvirt) | ✅ Licensed suite path |

### Why teams upgrade

1. A lab operator is not a multi-wave cutover fabric  
2. Windows estates need war-room playbooks — VirtIO alone is not enough  
3. Production needs HA, tenancy, and CVE/LTS under contract  
4. Storage teams need SAN/Ceph pipelines with a named owner  
5. You want Zyvor accountable for first-boot — not Issues at 2 a.m.  

**[Full feature matrix →](docs/ce-vs-enterprise.md)**

<div align="center">
<br/>

**Bring us your worst wave.** 30-day PoC on your estate.

[![Start a proof of concept](https://img.shields.io/badge/Start_a_proof_of_concept-F97316?style=for-the-badge)](https://zyvor.dev/poc?utm_source=github&utm_medium=h2kvm&utm_campaign=readme_footer)
[![Book an Enterprise demo](https://img.shields.io/badge/Book_an_Enterprise_demo-111827?style=for-the-badge)](https://zyvor.dev/contact?intent=demo&utm_source=github&utm_medium=h2kvm&utm_campaign=readme_footer)
[![Pricing](https://img.shields.io/badge/Pricing-22C55E?style=for-the-badge)](https://zyvor.dev/pricing?utm_source=github&utm_medium=h2kvm&utm_campaign=readme_footer)

</div>

---

## Where this fits: the Zyvor suite

[GuestKit](https://zyvor.dev/guestkit) and [h2kvm](https://zyvor.dev/h2kvm) fix the disk and land the VM. Where it lands decides the Zyvor product you run it on: KubeVirt is [Zorvia](https://zyvor.dev/zorvia) and [Zeus OS](https://zyvor.dev/zeus-os), libvirt hosts are [Machina](https://zyvor.dev/machina). See [How it works](#how-it-works).

| Product | Role |
|---------|------|
| [GuestKit](https://github.com/zyvorai/guestkit) | Offline disk repair before power-on |
| **h2kvm** *(this repo)* | Pick up, repair, convert, and land the VM on KubeVirt, libvirt or OpenStack |
| [Zorvia](https://github.com/zyvorai/zorvia) | KubeVirt endpoint: craft and watch VMs |
| [Transiva](https://github.com/zyvorai/transiva) | vSphere · Nutanix export (separate repo) |
| [Zeus OS](https://zyvor.dev/zeus-os) | KubeVirt endpoint: visual infrastructure OS |
| [Machina](https://zyvor.dev/machina) | libvirt endpoint: control plane for the hosts you already run |
| [PacketWolf](https://zyvor.dev/packetwolf) | Kernel-native network intelligence |

→ [zyvor.dev](https://zyvor.dev) · [hypervisor exit program](https://zyvor.dev/hypervisor-exit)

---

## Support

| | |
|---|---|
| **Enterprise / PoC** | [Book a demo](https://zyvor.dev/contact?intent=demo) · [sales@zyvor.dev](mailto:sales@zyvor.dev) |
| **Community** | [GitHub Issues](https://github.com/zyvorai/h2kvm/issues) |
| **Product** | [zyvor.dev/h2kvm](https://zyvor.dev/h2kvm) |

## License

Licensed under the **[Zyvor Production License v1.0](LICENSE)**.

- **Free** for development, testing, evaluation, research, education, and non-production labs
- **Paid commercial license required** for production, customer workloads, SaaS, managed services, OEM, redistribution, and other revenue-generating use

Commercial terms are issued separately: [https://zyvor.dev](https://zyvor.dev). Published prices: **$100 per VM, one-time** (N × $100), or Enterprise at a fixed price — **$25,000/year**, **$2,500/month**, **$25,000** for one major version, or **$15,000** for one minor version. Contact [sales@zyvor.dev](mailto:sales@zyvor.dev) for custom pricing. See [COMMERCIAL_LICENSE.md](COMMERCIAL_LICENSE.md) and [docs/LICENSING.md](docs/LICENSING.md).

Contributions: [CLA.md](CLA.md) + [DCO.md](DCO.md) (`git commit -s`). New source files need the `LicenseRef-Zyvor-Production-1.0` SPDX header.

<div align="center">
<sub>Built by <a href="https://zyvor.dev?utm_source=github&utm_medium=h2kvm&utm_campaign=readme_colophon">Zyvor AI Labs</a> · Hypervisor exit without the 2 a.m. surprise</sub>
</div>
