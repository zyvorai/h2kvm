# Where h2kvm fits in the Zyvor suite

How GuestKit, h2kvm, Zorvia, Zeus OS, Machina and the other Zyvor products relate. Moved from the README, wording unchanged.

[Back to the README](../README.md) · [Documentation index](README.md)

---

[GuestKit](https://zyvor.dev/guestkit) and [h2kvm](https://zyvor.dev/h2kvm) fix the disk and land the VM. Where it lands decides the Zyvor product you run it on: KubeVirt is [Zorvia](https://zyvor.dev/zorvia) and [Zeus OS](https://zyvor.dev/zeus-os), libvirt hosts are [Machina](https://zyvor.dev/machina). See [How it works](how-it-works.md).

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
