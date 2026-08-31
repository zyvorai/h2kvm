<div align="center">

# h2kvm

### Any hypervisor → KVM. Convert offline. Fix the guest. Deploy with confidence.

Export, convert, and deploy VMs from **VMware, Hyper-V, Nutanix, AWS, Azure, GCP** and more —  
with offline guest fixes, a web control plane, and a Kubernetes-native operator.

**First-boot science for hypervisor exit** · day-2 on **[Zeus OS](https://zyvor.dev/zeus-os)** · part of the [Zyvor](https://zyvor.dev/?utm_source=github&utm_medium=h2kvm&utm_campaign=readme_hero) suite

<br/>

[![Release](https://img.shields.io/github/v/release/zyvorai/h2kvm?color=F97316)](https://github.com/zyvorai/h2kvm/releases/tag/v1.1.0)
[![GuestKit](https://img.shields.io/pypi/v/hypersdk-guestkit.svg)](https://pypi.org/project/hypersdk-guestkit/)
[![Python](https://img.shields.io/badge/python-3.10+-3776AB.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-see_LICENSE-111827.svg)](LICENSE)

<br/>

[![Book an Enterprise demo](https://img.shields.io/badge/Book_an_Enterprise_demo-F97316?style=for-the-badge)](https://zyvor.dev/contact?intent=demo&utm_source=github&utm_medium=h2kvm&utm_campaign=readme_hero)
[![30-day PoC](https://img.shields.io/badge/30--day_PoC-111827?style=for-the-badge)](https://zyvor.dev/poc?utm_source=github&utm_medium=h2kvm&utm_campaign=readme_hero)
[![Watch the demo](https://img.shields.io/badge/Watch_the_demo-22C55E?style=for-the-badge)](https://www.youtube.com/watch?v=lQP1sd5Ftkc)

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

## The cutover problem — fixed before power-on

Hypervisor exit fails when VirtIO is missing, GRUB is wrong, or Windows still points at the old hypervisor — **after** you cut over.

**h2kvm** converts the disk offline, runs GuestKit repair, and deploys to libvirt / KubeVirt / OpenStack so first boot is planned, not guessed.

```text
  VMware · Hyper-V · cloud disks · …
              │
              ▼
     ┌──────────────────────────┐
     │  h2kvm                   │──►  convert → qcow2 / raw
     │  h2kvmctl · h2kweb       │──►  GuestKit inspect + repair
     │  K8s / OLM operator      │──►  deploy · validate · rollback
     └──────────────────────────┘
              │
              ▼
       libvirt · KubeVirt · Glance/Nova
              │
              ▼
            Zeus OS (day-2)
```

| GuestKit offline fix | 8+ disk formats | 35+ guest OS | CLI · web · operator |
|:---:|:---:|:---:|:---:|

**Suite path:** [HyperSDK](https://github.com/hypersdk/hypersdk) export → [GuestKit](https://github.com/hypersdk/guestkit) assure → **h2kvm** convert & deploy → [Zeus OS](https://zyvor.dev/zeus-os) day-2.

---

## Install

**v1.1.0** — GuestKit from PyPI; h2kvm from the GitHub Release wheel.

```bash
pip install "hypersdk-guestkit>=1.1.0"
pip install https://github.com/zyvorai/h2kvm/releases/download/v1.1.0/h2kvm-1.1.0-py3-none-any.whl
```

From source (extras / development):

```bash
git clone https://github.com/zyvorai/h2kvm.git
cd h2kvm
pip install -e ".[full]"
```

Host needs Linux with `qemu-img`, `qemu-nbd`, and `losetup`. Repair and NBD mounts often need root or `H2KVM_USE_SUDO=1`.

| Artifact | Where |
|----------|--------|
| **h2kvm 1.1.0** | [GitHub Release](https://github.com/zyvorai/h2kvm/releases/tag/v1.1.0) (wheel + sdist) |
| **hypersdk-guestkit ≥ 1.1.0** | [PyPI](https://pypi.org/project/hypersdk-guestkit/) |
| **Operator image** | `ghcr.io/zyvorai/h2kvm/operator:v1.1.0` |

---

## Quick start

```bash
# Local VMDK → qcow2 (GuestKit repair is the default backend)
h2kvmctl local --vmdk ubuntu.vmdk --to-output ubuntu.qcow2 --backend guestkit

# Live migration from vSphere
h2kvmctl migrate --source vmware --vm web-prod-01 --target kvm

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
| **TUI** | zkvm terminal UI |
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

Offline inspect and repair run through **[GuestKit](https://github.com/hypersdk/guestkit)** — fstab, GRUB, initramfs, and hypervisor-aware fixes via `guestkit.run_migrate_repair()`. h2kvm does not re-implement that engine in pure Python.

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

More: [GUESTKIT.md](docs/architecture/GUESTKIT.md) · [API](docs/reference/api/guestkit.md) · [GuestKit repo](https://github.com/hypersdk/guestkit)

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
| **CLI · h2kweb · zkvm · operator** | ✅ Eval / single-cluster | ✅ **HA** · multi-namespace tenancy |
| **Windows path** | Automated VirtIO / registry | ✅ + **war-room / PS runbooks** |
| **Storage pipelines** | Local / libvirt / KubeVirt / Glance | ✅ + **SAN / Ceph / NetApp** |
| **Pre-flight** | GuestKit planner | ✅ + **GuestKit fleet risk scoring** |
| **First-boot** | Strong offline fix | **96.8%** automated path + PS |
| **Support** | Community | **SLA · LTS · CVE** · hypervisor-exit programs |
| **Day-2** | Hand off to **Zeus OS** | ✅ Licensed suite path |

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

```mermaid
flowchart LR
    H["HyperSDK<br/>export"] --> G["GuestKit<br/>assure"]
    G --> K["<b>h2kvm</b><br/>convert · fix · deploy"]
    K --> T["KVM · KubeVirt"]
    T --> Z["Zeus OS<br/>day-2"]

    classDef accent fill:#F97316,stroke:#EA580C,color:#fff;
    classDef muted fill:#F3F4F6,stroke:#D1D5DB,color:#111827;
    class K accent;
    class Z muted;
```

| Product | Role |
|---------|------|
| [HyperSDK](https://github.com/hypersdk/hypersdk) | Multi-cloud / vSphere · Nutanix export |
| [GuestKit](https://github.com/hypersdk/guestkit) | Offline disk doctor + Passport + `run_migrate_repair` |
| **h2kvm** *(this repo)* | Convert + GuestKit offline fix + libvirt/KubeVirt deploy |
| [Zeus OS](https://zyvor.dev/zeus-os) | Day-2 KubeVirt / cloud control plane |
| [Machina](https://zyvor.dev/machina) | Physical hypervisor OS (libvirt/KVM) |
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

See [LICENSE](LICENSE) and `docs/legal/` for terms. Community / eval builds are for labs and integration — production fleets and SLAs are **Enterprise**.

<div align="center">
<sub>Built by <a href="https://zyvor.dev?utm_source=github&utm_medium=h2kvm&utm_campaign=readme_colophon">Zyvor AI Labs</a> · Hypervisor exit without the 2 a.m. surprise</sub>
</div>
