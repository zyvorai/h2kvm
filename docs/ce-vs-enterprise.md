# Community vs Enterprise — h2kvm

**Community / public eval (this repo) proves convert + offline guest fix.**  
**Enterprise is what you buy for cutover night.**

CE is for labs. The moment you need HA operators, Windows war-room runbooks, SAN/Ceph pipelines, GuestKit fleet risk scoring, or LTS/CVE under contract — that is Enterprise. Day-2 lands on **Zeus OS**. One failed first-boot wave usually costs more than the license.

Enterprise tree: commercial h2kvm builds. Product: [zyvor.dev/h2kvm](https://zyvor.dev/h2kvm?utm_source=github&utm_medium=h2kvm) · [Book an Enterprise demo](https://zyvor.dev/contact?intent=demo) · [30-day PoC](https://zyvor.dev/poc) · [sales@zyvor.dev](mailto:sales@zyvor.dev)

Pairs with: **[HyperSDK](https://github.com/hypersdk/hypersdk)** (export) → **h2kvm** (convert) → **[GuestKit](https://github.com/hypersdk/guestkit)** (assure) → **[Zeus OS](https://zyvor.dev/zeus-os)** (operate)

---

## Full capability matrix

### Positioning

| Capability | Community / public CE | Enterprise |
| --- | --- | --- |
| What you get | Conversion engine + h2kweb + operator (eval) | Fleet conversion **operating system** + PS |
| Who it is for | Labs, single-cluster PoC | Platform / migration leads · wave cutovers |
| Success metric | One VM converts and boots in a lab | Wave first-boot % · HA uptime · attributable cutovers |
| Cost of staying on CE | No war-room · no SAN contracts · Issues | Avoided: failed Windows nights, storage tickets, unowned bridges |
| Support | Community / self-serve | **SLA** · LTS · CVE response · war-room |
| License | Eval / proprietary CE terms | Commercial |

### Source connectors

| Capability | Community | Enterprise |
| --- | --- | --- |
| vSphere (govc / ovftool / VDDK) | ✅ | ✅ |
| Hyper-V VHD/VHDX | ✅ | ✅ |
| AWS · Azure disk export paths | ✅ | ✅ |
| Proxmox / Veeam backup vaults | ✅ / limited | ✅ Hardened playbooks |
| HyperSDK-driven multi-provider orchestration | DIY glue | ✅ Integrated |

### Disk conversion engine

| Capability | Community | Enterprise |
| --- | --- | --- |
| Formats → qcow2 / raw | ✅ | ✅ |
| OVF parse · split-VMDK flatten · resize | ✅ | ✅ |
| NBD stream conversion | ✅ | ✅ |
| 8+ input formats · 35+ guest OS | ✅ | ✅ Validated matrices |
| Custom SAN / Ceph / NetApp pipelines | — | ✅ |

### Offline guest-fix engine (VMCraft)

| Capability | Community | Enterprise |
| --- | --- | --- |
| VirtIO inject · fstab · XFS UUID · GRUB/initramfs | ✅ | ✅ |
| Remove VMware Tools · network fixups | ✅ | ✅ |
| LVM-aware repair · OS detect · planner | ✅ | ✅ |
| Compliance scans · dependency map · Augeas | ✅ | ✅ |
| GuestKit fleet risk scoring + remediation playbooks | Pair yourself | ✅ |

### Windows migration path

| Capability | Community | Enterprise |
| --- | --- | --- |
| Multi-stage VirtIO · hivex registry | ✅ | ✅ |
| RDP / firewall · Hyper-V enlightenments | ✅ | ✅ |
| AD / SQL awareness | ✅ | ✅ |
| Windows cutover / war-room runbooks | Docs | ✅ Professional services |

### Deployment targets

| Capability | Community | Enterprise |
| --- | --- | --- |
| libvirt / bare KVM | ✅ | ✅ |
| KubeVirt / OpenShift | ✅ | ✅ Fleet HA · multi-namespace |
| OpenStack Glance / Nova | ✅ | ✅ |
| noVNC · cloud-init · UEFI / Secure Boot | ✅ | ✅ |
| Health validation after deploy | ✅ | ✅ SLO reporting |

### Encryption & security

| Capability | Community | Enterprise |
| --- | --- | --- |
| LUKS · Clevis/Tang · TPM seal | ✅ | ✅ |
| Vault secrets integration | ✅ / limited | ✅ Production hardened |
| Air-gap / regulated packaging | DIY | ✅ |

### Automation & control surfaces

| Capability | Community | Enterprise |
| --- | --- | --- |
| `h2kvmctl` CLI · YAML · daemon / watch-dir | ✅ | ✅ |
| zkvm TUI | ✅ | ✅ |
| h2kweb dashboard | ✅ | ✅ Production themes · RBAC |
| K8s / OLM operator | ✅ Single-cluster | ✅ HA · tenancy · webhooks |
| Manifest batch · rollback · DB-aware migrate | ✅ | ✅ |
| Parallel enterprise manager | Eval | ✅ Fleet-scale |
| Optional AI ops | ✅ / flag | ✅ Supported |

### Suite

| Capability | Community | Enterprise |
| --- | --- | --- |
| Hand off to **Zeus OS** day-2 | ✅ | ✅ Licensed path |
| HyperSDK export upstream | Pair | ✅ Orchestrated |
| First-boot success (published) | Strong offline fix | **96.8%** automated path + PS |

---

## Why buy Enterprise

1. **A lab operator is not a multi-wave cutover fabric** — Enterprise is HA, tenancy, and production hardening  
2. **Windows estates need war-room playbooks** — VirtIO injection alone does not survive AD/SQL cutovers  
3. **Storage teams need SAN/Ceph pipelines under contract** — DIY glue fails when the ticket is already late  
4. **Published first-boot outcomes + PS** — 96.8% automated path; the rest is a named owner, not Issues  
5. **You want Zyvor accountable for cutover night** — LTS, CVE trains, and hypervisor-exit programs  

**CE proves the science. Buy Enterprise when the estate must move.**

**→ [Book an Enterprise demo](https://zyvor.dev/contact?intent=demo)** · **[30-day PoC](https://zyvor.dev/poc)** · **[Pricing](https://zyvor.dev/pricing)** · **[h2kvm product](https://zyvor.dev/h2kvm)**
