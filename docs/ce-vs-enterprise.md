# Community vs Enterprise — h2kvm

**Community / public eval (this repo) proves convert + offline guest fix.**  
**Enterprise is what you buy for cutover night.**

CE is for labs. The moment you need HA operators, Windows war-room runbooks, SAN/Ceph pipelines, GuestKit fleet risk scoring, or LTS/CVE under contract — that is Enterprise. Day-2 lands on **Zeus OS**. One failed first-boot wave usually costs more than the license.

Enterprise tree: commercial h2kvm builds. Product: [zyvor.dev/h2kvm](https://zyvor.dev/h2kvm?utm_source=github&utm_medium=h2kvm&utm_campaign=readme_edition) · [Book a demo](https://zyvor.dev/schedule?utm_source=github&utm_medium=h2kvm&utm_campaign=readme_edition) · [30-day PoC](https://zyvor.dev/poc?utm_source=github&utm_medium=h2kvm&utm_campaign=readme_edition) · [sales@zyvor.dev](mailto:sales@zyvor.dev)

Pairs with: **[Transiva](https://github.com/zyvorai/transiva)** (export) → **h2kvm** (convert and deploy) → **[GuestKit](https://github.com/zyvorai/guestkit)** (assure) → **[Zorvia](https://github.com/zyvorai/zorvia)** or **[Zeus OS](https://zyvor.dev/zeus-os?utm_source=github&utm_medium=h2kvm&utm_campaign=readme_edition)** (operate)

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
| License | Zyvor Production License; free for non-production | $100 × N VMs, or Enterprise fixed |

### Source connectors

| Capability | Community | Enterprise |
| --- | --- | --- |
| vSphere (govc / ovftool) | ✅ | ✅ |
| Hyper-V VHD/VHDX | ✅ | ✅ |
| AWS · Azure disk export paths | ✅ | ✅ |
| Proxmox / Veeam backup vaults | ✅ / limited | ✅ Hardened playbooks |
| Transiva-driven multi-provider orchestration | DIY glue | ✅ Integrated |

### Disk conversion engine

| Capability | Community | Enterprise |
| --- | --- | --- |
| Formats → qcow2 / raw | ✅ | ✅ |
| OVF parse · split-VMDK flatten · resize | ✅ | ✅ |
| NBD stream conversion | ✅ | ✅ |
| 8+ input formats · 35+ guest OS | ✅ | ✅ Validated matrices |
| Custom SAN / Ceph / NetApp pipelines | — | ✅ |

### Offline guest-fix engine (GuestKit)

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
| h2kweb dashboard | ✅ | ✅ Production themes · RBAC |
| K8s / OLM operator | ✅ Single-cluster | ✅ HA · tenancy · webhooks |
| Manifest batch · rollback · DB-aware migrate | ✅ | ✅ |
| Parallel enterprise manager | Eval | ✅ Fleet-scale |
| Optional AI ops | ✅ / flag | ✅ Supported |

### Suite

| Capability | Community | Enterprise |
| --- | --- | --- |
| Hand off to **Zeus OS** day-2 | ✅ | ✅ Licensed path |
| Transiva export upstream | Pair | ✅ Orchestrated |
| First-boot ownership | Strong offline fix | Automated path + PS runbooks, named owner |

---

## Why buy Enterprise

1. **A lab operator is not a multi-wave cutover fabric** — Enterprise is HA, tenancy, and production hardening  
2. **Windows estates need war-room playbooks** — VirtIO injection alone does not survive AD/SQL cutovers  
3. **Storage teams need SAN/Ceph pipelines under contract** — DIY glue fails when the ticket is already late  
4. **First-boot ownership + PS** — automated path plus runbooks; the rest is a named owner, not Issues  
5. **You want Zyvor accountable for cutover night** — LTS, CVE trains, and hypervisor-exit programs  

**CE proves the science. Buy Enterprise when the estate must move.**

Commercial prices: **$100 per VM, one-time** (N × $100), or Enterprise at a fixed price — **$25,000/year**, **$2,500/month**, **$25,000** for one major version, or **$15,000** for one minor version. Contact [sales@zyvor.dev](mailto:sales@zyvor.dev) for custom pricing. See [COMMERCIAL_LICENSE.md](../COMMERCIAL_LICENSE.md) and [LICENSING.md](LICENSING.md).

**→ [Book a demo](https://zyvor.dev/schedule?utm_source=github&utm_medium=h2kvm&utm_campaign=readme_edition)** · **[30-day PoC](https://zyvor.dev/poc?utm_source=github&utm_medium=h2kvm&utm_campaign=readme_edition)** · **[Pricing](https://zyvor.dev/pricing?utm_source=github&utm_medium=h2kvm&utm_campaign=readme_edition)** · **[h2kvm product](https://zyvor.dev/h2kvm?utm_source=github&utm_medium=h2kvm&utm_campaign=readme_edition)**
