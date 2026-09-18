VMware told The Register the Virtual Disk Development Kit was never for moving VMs.

On 10 September 2026 the company said public downloads are over, access stays with select partners, and the licensed use was always backup and recovery. The kit is not a customer entitlement. It was never included with a Broadcom software purchase.

Most VMware-to-KVM tools still open disks with that kit. The download page is a 404.

h2kvm does not use it. The disk leaves through the vSphere API: an NFC lease, `govc export.ovf`, or a datastore download. Nutanix disks leave over NFS. If the file is already on disk, convert it there.

Copying the disk was never the hard part. The guest fails when the bootloader, VirtIO, or Windows still points at the old hypervisor. GuestKit fixes that before power-on. h2kvm lands the VM. Zorvia is where you watch the boot.

You do not need a developer kit Broadcom says you were never entitled to.

pip install "h2kvm==1.2.1"

Product: https://zyvor.dev/h2kvm?utm_source=linkedin&utm_medium=article&utm_campaign=vddk_2026
GitHub: https://github.com/zyvorai/h2kvm?utm_source=linkedin&utm_medium=article&utm_campaign=vddk_2026
PyPI: https://pypi.org/project/h2kvm/1.2.1/
GuestKit: https://zyvor.dev/guestkit?utm_source=linkedin&utm_medium=article&utm_campaign=vddk_2026
Zorvia: https://zyvor.dev/zorvia?utm_source=linkedin&utm_medium=article&utm_campaign=vddk_2026
Zeus OS: https://zyvor.dev/zeus-os?utm_source=linkedin&utm_medium=article&utm_campaign=vddk_2026
Machina: https://zyvor.dev/machina?utm_source=linkedin&utm_medium=article&utm_campaign=vddk_2026
Demo: https://zyvor.dev/contact?intent=demo&utm_source=linkedin&utm_medium=article&utm_campaign=vddk_2026
30-day PoC: https://zyvor.dev/poc?utm_source=linkedin&utm_medium=article&utm_campaign=vddk_2026

The Register story: https://www.theregister.com/virtualization/2026/09/10/vmware-defends-ending-downloads-of-sdk-that-helps-vm-backups-or-migrations-to-rivals/5295421

#VMware #KVM #Virtualization #HypervisorExit #h2kvm
