# GuestKit in h2kvm

How h2kvm uses GuestKit for offline inspect and repair. See also [architecture/GUESTKIT.md](architecture/GUESTKIT.md).

[Back to the README](../README.md) · [Documentation index](README.md)

---

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

**Debian/Ubuntu libvirt:** after convert, `chown libvirt-qemu:kvm` on the output qcow2 before `virsh start`. See [troubleshooting](guides/troubleshooting.md#permissions-and-ownership).

More: [GUESTKIT.md](architecture/GUESTKIT.md) · [API](reference/api/guestkit.md) · [GuestKit repo](https://github.com/zyvorai/guestkit) · [Zorvia](https://github.com/zyvorai/zorvia)
