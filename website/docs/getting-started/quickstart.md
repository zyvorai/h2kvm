---
sidebar_position: 1
---

# Quickstart

h2kvm converts a VM from another hypervisor onto KVM. GuestKit is installed with it and repairs the guest before the VM is powered on.

```bash
pip install "h2kvm==1.3.0"
h2kvmctl --help
```

The host needs Linux with `qemu-img`. Repair and disk mounts often need root, or `H2KVM_USE_SUDO=1`.

## A disk you already have

```bash
h2kvmctl --cmd local --vmdk ubuntu.vmdk --to-output ubuntu.qcow2 --backend guestkit
```

That converts the disk and runs GuestKit repair. On Debian or Ubuntu, `chown libvirt-qemu:kvm` the qcow2 before `virsh start`.

## From source

```bash
git clone https://github.com/zyvorai/h2kvm.git
cd h2kvm
pip install -e ".[full]"
```

## Where to go next

| You want | Go here |
|---|---|
| Where disks come from, and where the VM lands | [How it works](../how-it-works) |
| Product page | [zyvor.dev/h2kvm](https://zyvor.dev/h2kvm) |
| Source | [github.com/zyvorai/h2kvm](https://github.com/zyvorai/h2kvm) |
| Package | [PyPI](https://pypi.org/project/h2kvm/1.3.0/) |
