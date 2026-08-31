<div align="center">

# h2kvm

### Any hypervisor → KVM. Convert offline. Fix the guest. Deploy with confidence.

Export, convert, and deploy VMs from **VMware, Hyper-V, Nutanix, AWS, Azure, GCP** and more —  
with offline guest fixes, a web control plane, and a Kubernetes-native operator.

**First-boot science for hypervisor exit** · day-2 on **[Zeus OS](https://zyvor.dev/zeus-os)** · part of the [Zyvor](https://zyvor.dev/?utm_source=github&utm_medium=h2kvm&utm_campaign=readme_hero) suite

<br/>

[![PyPI](https://img.shields.io/pypi/v/h2kvm.svg?color=F97316)](https://pypi.org/project/h2kvm/)
[![PyPI downloads](https://img.shields.io/pypi/dm/h2kvm.svg)](https://pypi.org/project/h2kvm/)
[![Python](https://img.shields.io/badge/python-3.10+-3776AB.svg)](https://www.python.org/)
[![Stars](https://img.shields.io/github/stars/hypersdk/h2kvm?style=social)](https://github.com/hypersdk/h2kvm/stargazers)

<br/>

[![Book an Enterprise demo](https://img.shields.io/badge/Book_an_Enterprise_demo-F97316?style=for-the-badge)](https://zyvor.dev/contact?intent=demo&utm_source=github&utm_medium=h2kvm&utm_campaign=readme_hero)
[![30-day PoC](https://img.shields.io/badge/30--day_PoC-111827?style=for-the-badge)](https://zyvor.dev/poc?utm_source=github&utm_medium=h2kvm&utm_campaign=readme_hero)
[![Watch the demo](https://img.shields.io/badge/Watch_the_demo-22C55E?style=for-the-badge)](https://www.youtube.com/watch?v=lQP1sd5Ftkc)

**[Quick start](#60-second-quick-start)** ·
**[Demos](#see-it-in-action)** ·
**[CE vs Enterprise](#community-vs-enterprise)** ·
**[Docs](docs/README.md)** ·
**[Product](https://zyvor.dev/h2kvm?utm_source=github&utm_medium=h2kvm)**

</div>

---

## The cutover problem — fixed before power-on

Hypervisor exit fails when VirtIO is missing, GRUB is wrong, or Windows registry still points at the old hypervisor — **after** you cut over.

**h2kvm converts the disk offline, injects drivers, and deploys to libvirt / KubeVirt / OpenStack** so first boot is a plan, not a prayer.

```text
  VMware · Hyper-V · cloud disks · …
              │
              ▼
  ┌─────────────────────────────────┐
  │  h2kvm                      │──►  convert → qcow2 / raw
  │  h2kvmctl · h2kweb · zkvm       │──►  GuestKit offline inspect + repair
  │  K8s / OLM operator             │──►  deploy · validate · rollback
  └─────────────────────────────────┘
              │
              ▼
       libvirt · KubeVirt · OpenShift · Glance/Nova
              │
              ▼
            Zeus OS (day-2)
```

| | | | |
|:---:|:---:|:---:|:---:|
| **480+** APIs | **8+** input formats | **35+** guest OS | **1390+** tests |
| CLI · TUI · Web | K8s operator | Windows path | **10K+** PyPI downloads |

**Export with [HyperSDK](https://github.com/hypersdk/hypersdk) → convert with h2kvm → assure with [GuestKit](https://github.com/hypersdk/guestkit) → operate on [Zeus OS](https://zyvor.dev/zeus-os).**

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
|------------------|----------------|
| 18-month “migration project” | One pipeline: browse → migrate → deploy |
| Guest drivers break on first KVM boot | **GuestKit** offline fix for 35+ OS versions |
| Windows needs a war room of tribal scripts | Automated VirtIO / hivex / RDP path |
| No visibility mid-conversion | **h2kweb** progress · webhooks · email |
| K8s teams stuck on libvirt YAML | Libvirt → **KubeVirt** one-click path |
| Cutover outcomes unowned | Enterprise: **96.8%** automated first-boot + PS |

---

## 60-second quick start

```bash
pip install h2kvm

# CLI migration
h2kvmctl migrate --source vmware --vm web-prod-01 --target kvm

# Web dashboard
h2kweb
# → https://localhost:5070

# Kubernetes operator
kubectl apply -f operator/deploy/
```

| Surface | What you get |
|---------|----------------|
| **CLI** | `h2kvmctl` / `h2k` — `bin/`, `h2kvm/` |
| **Web** | h2kweb dashboard — `web/` |
| **TUI** | zkvm terminal UI |
| **Operator** | K8s / OpenShift — `operator/`, `olm/` |
| **Helm** | Production charts — `helm/` |
| **Fix engine** | Offline guest OS repairs — pure Python |

| You want… | Go here |
|-----------|---------|
| Full command reference | [docs/README.md](docs/README.md) |
| Examples | [examples/](examples/) |
| CE vs Enterprise matrix | [docs/ce-vs-enterprise.md](docs/ce-vs-enterprise.md) |
| User stories | [docs/USER_STORIES.md](docs/USER_STORIES.md) |

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
    H["HyperSDK<br/>export"] --> K["<b>h2kvm</b><br/>convert · fix"]
    K --> G["GuestKit<br/>assure"]
    G --> T["KVM · KubeVirt"]
    T --> Z["Zeus OS<br/>day-2"]

    classDef accent fill:#F97316,stroke:#EA580C,color:#fff;
    classDef muted fill:#F3F4F6,stroke:#D1D5DB,color:#111827;
    class K accent;
    class Z muted;
```

| Product | Role |
|---------|------|
| [HyperSDK](https://github.com/hypersdk/hypersdk) | Multi-cloud / vSphere · Nutanix export |
| **h2kvm** *(this repo)* | Convert + offline guest fix + deploy |
| [GuestKit](https://github.com/hypersdk/guestkit) | Offline disk doctor + Passport |
| [Zeus OS](https://zyvor.dev/zeus-os) | Day-2 KubeVirt / cloud control plane |
| [Machina](https://zyvor.dev/machina) | Physical hypervisor OS (libvirt/KVM) |
| [PacketWolf](https://zyvor.dev/packetwolf) | Kernel-native network intelligence |

→ [zyvor.dev](https://zyvor.dev) · [hypervisor exit program](https://zyvor.dev/hypervisor-exit)

---

## Support the project

If h2kvm saved a cutover weekend, a ⭐ helps more teams find it.

| | |
|---|---|
| **Enterprise / PoC** | [Book a demo](https://zyvor.dev/contact?intent=demo) · [sales@zyvor.dev](mailto:sales@zyvor.dev) |
| **Community** | [GitHub Issues](https://github.com/hypersdk/h2kvm/issues) |
| **Product** | [zyvor.dev/h2kvm](https://zyvor.dev/h2kvm) |

## License

See [LICENSE](LICENSE) and `docs/legal/` for terms. Community / eval builds are for labs and integration — production fleets and SLAs are **Enterprise**.

<div align="center">
<sub>Built by <a href="https://zyvor.dev?utm_source=github&utm_medium=h2kvm&utm_campaign=readme_colophon">Zyvor AI Labs</a> · Hypervisor exit without the 2 a.m. surprise</sub>
</div>
