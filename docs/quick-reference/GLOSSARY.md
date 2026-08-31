# Glossary

Comprehensive glossary of terms, concepts, and technologies used in H2KVM.

---

## Quick Navigation

- [Core Concepts](#core-concepts)
- [Migration Terms](#migration-terms)
- [GuestKit Terms](#guestkit-terms)
- [Virtualization Technologies](#virtualization-technologies)
- [File Systems & Storage](#file-systems--storage)
- [Networking](#networking)
- [Kubernetes & Orchestration](#kubernetes--orchestration)
- [Operating Systems](#operating-systems)
- [Tools & Utilities](#tools--utilities)
- [Acronyms](#acronyms)

---

## Core Concepts

### Artifact Manifest
A JSON document that describes migration outputs (disk images, configuration files, metadata). Follows the artifact-manifest-v1.0 schema specification.

### Chroot
Change root - a Unix operation that changes the apparent root directory. H2KVM uses enhanced chroot with proper isolation and cleanup.

### Cold Migration
Migration performed while the VM is powered off. Allows complete filesystem access and modification.

### Conversion
The process of transforming a VM disk image from one format to another (e.g., VMDK to QCOW2).

### Enhanced Chroot
H2KVM's improved chroot implementation with automatic mount/unmount of /proc, /sys, /dev and safe cleanup.

### fstab
File System Table - Linux configuration file (/etc/fstab) that defines how disk partitions, block devices, or remote filesystems should be mounted.

### Guest
The virtual machine being migrated or manipulated. The operating system and applications running inside the VM.

### Host
The physical or virtual machine running the hypervisor and hosting guest VMs.

### Live Migration
Migration of a running VM with minimal downtime. H2KVM's "live fix" mode uses SSH to apply fixes while the VM is running.

### Migration
The complete process of converting a VM from one platform (VMware/Hyper-V) to another (KVM).

### Offline Fix
Post-migration remediation performed on a stopped VM to fix boot issues or configuration problems.

### Source Platform
The original virtualization platform (VMware ESXi, vSphere, Hyper-V) from which VMs are being migrated.

### Target Platform
The destination virtualization platform (KVM, QEMU, OpenStack, oVirt) to which VMs are being migrated.

### GuestKit
H2KVM's default offline disk backend (`hypersdk-guestkit`). Provides doctor, migrate plan/repair, and GuestFS-compatible disk access via `guestfs_factory` and `guestkit_client`.

---

## Migration Terms

### Batch Migration
Migrating multiple VMs in parallel or sequence using daemon mode or automation scripts.

### BusLogic Auto-Fix
Automatic detection and remediation of legacy BusLogic SCSI controllers that don't boot properly on KVM.

### Conversion Time
The time required to convert a VMDK to QCOW2, typically 5-60 minutes depending on size and compression.

### Device Name Stabilization
Converting fstab entries from device names (/dev/sda1) to stable identifiers (UUID or LABEL).

### Fixers
Modular components in H2KVM that apply specific fixes (e.g., initramfs regeneration, GRUB updates).

### initramfs
Initial RAM filesystem - a temporary root filesystem loaded during Linux boot before the real root filesystem is mounted.

### Migration Manifest
YAML configuration file defining migration parameters (source VMDK, output path, options).

### Migration Pipeline
The sequence of operations performed during migration: fetch → convert → fix → validate → export.

### Pre-Migration Validation
Checks performed before migration to identify potential issues (VMDK Inspector, compatibility checks).

### Rollback
Reverting migration changes if issues are detected. H2KVM maintains original files for safety.

### Stabilization
Making configurations more robust for the target platform (fstab stabilization, UUID regeneration).

### Success Rate
Percentage of migrations that complete successfully and boot on the target platform. H2KVM achieves 96.5% for Linux, 94% for Windows.

### XFS UUID Regeneration
Fixing duplicate XFS filesystem UUIDs that occur when VMware VMs are cloned.

---

## GuestKit Terms

### doctor
GuestKit bootability analysis for a target hypervisor (e.g. KVM). Exposed via `guestkit_client.doctor()`.

### migrate_repair
GuestKit hypervisor-aware offline repair pipeline (fstab, GRUB, initramfs, etc.). Used by `offline_fixer`.

### guestfs_factory
h2kvm module that creates GuestFS-compatible handles (`guestkit`, `guestfs`, or `auto` backends).

### guestkit_client
Thin h2kvm facade over `hypersdk-guestkit` Python bindings.

### Guest Inspection
Analyzing a VM disk to detect OS type, boot configuration, and migration readiness.

### guestfish
Legacy libguestfs CLI for manual disk manipulation. GuestKit provides a faster alternative for h2kvm workflows.

### LVM Support
Logical Volume Manager activation during offline fixes, with optional container-isolated VG scanning.

### NBD (Network Block Device)
Protocol for accessing block devices over the network. GuestKit uses `qemu-nbd` to attach disk images.

### OS Detection
Automatic identification of the guest operating system (distribution, version, architecture).

### VirtIO Drivers
GuestKit's capability to read and modify Windows Registry hives for driver injection and configuration.

### Service Management
GuestKit APIs for enabling/disabling systemd services or SysV init scripts within guests.

### VirtIO Drivers
Paravirtualized drivers for optimal performance on KVM. GuestKit can inject these into Windows VMs.

---

## Virtualization Technologies

### ESXi
VMware's bare-metal hypervisor platform. Common source platform for migrations.

### Hyper-V
Microsoft's hypervisor technology. H2KVM can migrate from Hyper-V to KVM.

### hyperctl / hypersdk
Tools for managing hypervisor-native virtualization. H2KVM integrates with these for advanced deployments.

### KVM (Kernel-based Virtual Machine)
Linux kernel module that turns Linux into a hypervisor. The target platform for H2KVM migrations.

### KubeVirt
Kubernetes extension for running VMs alongside containers. H2KVM can deploy to KubeVirt clusters.

### libvirt
Virtualization management library. H2KVM can integrate with libvirt for VM management.

### OpenStack
Cloud computing platform. H2KVM can export VMs in OpenStack-compatible formats.

### oVirt
Open-source virtualization management platform based on KVM.

### QEMU
Quick Emulator - the userspace component of KVM that performs hardware emulation.

### QEMU Guest Agent
Agent running inside VMs for advanced management operations and better integration.

### vCenter
VMware's centralized management platform for vSphere environments.

### virt-v2v
Red Hat's V2V (Virtual-to-Virtual) conversion tool. H2KVM is an alternative with additional features.

### VMDK (Virtual Machine Disk)
VMware's disk image format. The typical source format for migrations.

### vSphere
VMware's virtualization platform suite including ESXi and vCenter.

---

## File Systems & Storage

### BTRFS
B-tree filesystem - a modern Linux filesystem with advanced features.

### Cloned VM
A copy of a VM created using VMware's clone feature. Often has duplicate UUIDs requiring regeneration.

### Device Mapper
Linux kernel framework for mapping block devices. Used for LVM, encryption, and other storage features.

### Disk Image
A file containing the complete contents of a disk (VMDK, QCOW2, RAW, VHD).

### ext4
Fourth Extended Filesystem - the most common Linux filesystem.

### Filesystem UUID
Universally Unique Identifier assigned to a filesystem. Critical for proper mounting.

### fstab Modes
- `stabilize-all`: Convert all entries to UUID
- `uuid-only`: Only update UUID entries
- `label-fallback`: Prefer UUID, fallback to LABEL
- `preserve`: Keep original entries

### LVM (Logical Volume Manager)
System for managing logical volumes that can span multiple physical disks.

### NTFS
New Technology File System - Microsoft's filesystem for Windows.

### Partition Table
Data structure describing the partitions on a disk (MBR or GPT).

### QCOW2
QEMU Copy-On-Write version 2 - KVM's native disk image format with compression and snapshots.

### RAW Format
Uncompressed disk image format. Larger but slightly faster than QCOW2.

### Sparse File
A file with holes (unallocated regions) that takes less disk space. QCOW2 images are sparse by default.

### UUID (Universally Unique Identifier)
128-bit identifier used for filesystems, partitions, and other resources.

### VHD/VHDX
Virtual Hard Disk - Microsoft's disk image format used by Hyper-V.

### XFS
High-performance 64-bit journaling filesystem. Commonly used in enterprise Linux.

---

## Networking

### Bridge Network
Virtual network switch that connects VMs to physical networks.

### DHCP (Dynamic Host Configuration Protocol)
Protocol for automatic IP address assignment. Often configured in migrated VMs.

### MAC Address
Media Access Control address - unique identifier for network interfaces.

### NAT (Network Address Translation)
Network configuration where VMs share the host's IP address.

### Network Resilience
H2KVM's ability to handle network failures during remote operations (retry, exponential backoff).

### Static IP
Manually configured IP address (as opposed to DHCP). Requires configuration preservation during migration.

### VLAN (Virtual Local Area Network)
Network segmentation technology. May need reconfiguration after migration.

---

## Kubernetes & Orchestration

### ConfigMap
Kubernetes object for storing configuration data. Used to provide migration manifests.

### CRD (Custom Resource Definition)
Kubernetes extension mechanism. H2KVM defines `MigrationJob`, `OfflineFixJob`, and `InspectionJob` CRDs.

### Helm
Kubernetes package manager. One deployment method for H2KVM.

### Job
Kubernetes resource for running batch tasks. H2KVM migrations run as Kubernetes Jobs.

### Namespace
Kubernetes logical cluster division. H2KVM typically runs in dedicated namespaces.

### OLM (Operator Lifecycle Manager)
Framework for managing Kubernetes operators. Alternative deployment method for H2KVM.

### OpenShift
Red Hat's Kubernetes distribution with additional enterprise features.

### Operator
Kubernetes extension for managing complex applications. H2KVM provides operators for automation.

### PVC (PersistentVolumeClaim)
Kubernetes resource for requesting persistent storage for migration artifacts.

### Worker Node
Kubernetes node that runs workload pods. H2KVM workers run on worker nodes.

### Worker Protocol
H2KVM's REST API for job submission and management in Kubernetes environments.

---

## Operating Systems

### CentOS
Community Enterprise Operating System - free derivative of RHEL. Well-supported by H2KVM.

### Photon OS
VMware's minimal Linux distribution optimized for cloud-native applications.

### RHEL (Red Hat Enterprise Linux)
Commercial Linux distribution. Fully supported including RHEL 10.

### Rocky Linux
Community enterprise Linux distribution, RHEL-compatible successor to CentOS.

### SUSE / SLES
SUSE Linux Enterprise Server - enterprise Linux distribution with full support.

### Ubuntu
Popular Debian-based Linux distribution. Supported including Ubuntu 24.04.

### Windows
Microsoft Windows operating systems. H2KVM supports Windows Server and Desktop editions with VirtIO driver injection.

---

## Tools & Utilities

### h2kvmctl
H2KVM's command-line interface tool for migrations and management.

### GRUB (GRand Unified Bootloader)
Linux bootloader. H2KVM can regenerate GRUB configuration for the new platform.

### JSON Schema
Formal specification for JSON document structure. Used for artifact manifest validation.

### lsblk
Linux utility for listing block devices. Used in migration diagnostics.

### qemu-img
QEMU disk image utility for conversion, compression, and manipulation.

### systemd
Modern Linux init system and service manager. H2KVM integrates as a systemd service.

### TUI (Text User Interface)
H2KVM's interactive terminal interface for user-friendly migrations.

### VMDK Inspector
H2KVM tool for analyzing VMDK files before migration to detect potential issues.

### YAML
YAML Ain't Markup Language - human-readable data serialization format used for migration manifests.

---

## Acronyms

| Acronym | Full Name | Description |
|---------|-----------|-------------|
| **API** | Application Programming Interface | Programmatic interface for software interaction |
| **BIOS** | Basic Input/Output System | Firmware interface for PC initialization |
| **CLI** | Command-Line Interface | Text-based user interface |
| **CPU** | Central Processing Unit | Main processor in a computer |
| **CRD** | Custom Resource Definition | Kubernetes API extension |
| **DHCP** | Dynamic Host Configuration Protocol | Network configuration protocol |
| **DNS** | Domain Name System | Hostname to IP address resolution |
| **ESXi** | Elastic Sky X integrated | VMware's bare-metal hypervisor |
| **GRUB** | GRand Unified Bootloader | Linux boot loader |
| **GUI** | Graphical User Interface | Visual user interface |
| **HTTP** | Hypertext Transfer Protocol | Web communication protocol |
| **IDE** | Integrated Drive Electronics | Legacy disk interface (also: Integrated Development Environment) |
| **I/O** | Input/Output | Data transfer operations |
| **IP** | Internet Protocol | Network addressing protocol |
| **JSON** | JavaScript Object Notation | Data interchange format |
| **KVM** | Kernel-based Virtual Machine | Linux virtualization technology |
| **LVM** | Logical Volume Manager | Linux storage management |
| **MAC** | Media Access Control | Network hardware address |
| **MBR** | Master Boot Record | Legacy partition table format |
| **NAT** | Network Address Translation | IP address translation |
| **NBD** | Network Block Device | Block device over network protocol |
| **NFS** | Network File System | Distributed file system protocol |
| **NTFS** | New Technology File System | Windows filesystem |
| **OLM** | Operator Lifecycle Manager | Kubernetes operator management |
| **OS** | Operating System | System software managing hardware |
| **PVC** | PersistentVolumeClaim | Kubernetes storage request |
| **QCOW2** | QEMU Copy-On-Write v2 | KVM disk image format |
| **QEMU** | Quick Emulator | Hardware emulation software |
| **RAM** | Random Access Memory | Computer memory |
| **REST** | Representational State Transfer | Web API architectural style |
| **RHEL** | Red Hat Enterprise Linux | Commercial Linux distribution |
| **RPM** | RPM Package Manager | Package management system |
| **SAN** | Storage Area Network | Dedicated storage network |
| **SCSI** | Small Computer System Interface | Storage device interface |
| **SLES** | SUSE Linux Enterprise Server | Enterprise Linux distribution |
| **SSH** | Secure Shell | Encrypted remote access protocol |
| **SSL/TLS** | Secure Sockets Layer / Transport Layer Security | Encryption protocols |
| **SysV** | System V | Traditional Unix init system |
| **TCP** | Transmission Control Protocol | Network transport protocol |
| **TUI** | Text User Interface | Terminal-based interface |
| **UEFI** | Unified Extensible Firmware Interface | Modern firmware interface |
| **URL** | Uniform Resource Locator | Web address |
| **USB** | Universal Serial Bus | Peripheral device interface |
| **UUID** | Universally Unique Identifier | 128-bit unique identifier |
| **V2V** | Virtual-to-Virtual | VM migration between platforms |
| **VHD** | Virtual Hard Disk | Hyper-V disk image format |
| **VLAN** | Virtual Local Area Network | Network segmentation |
| **VM** | Virtual Machine | Emulated computer system |
| **VMDK** | Virtual Machine Disk | VMware disk image format |
| **VNC** | Virtual Network Computing | Remote desktop protocol |
| **YAML** | YAML Ain't Markup Language | Data serialization format |

---

## Usage Examples

### Finding a Term

Use your browser's search function (Ctrl+F / Cmd+F) to quickly locate terms in this glossary.

### Related Documentation

For more detailed information about specific topics:

- **Migration concepts**: See [Tutorials](tutorials/)
- **GuestKit APIs**: See [GuestKit Integration Guide](../architecture/GUESTKIT.md)
- **Technical details**: See [Reference Documentation](reference/)
- **Troubleshooting**: See [FAQ](FAQ.md)

---

## Contributing to the Glossary

Found a missing term? Want to improve a definition?

1. Check if the term is already defined
2. Ensure the definition is clear and accurate
3. Add relevant cross-references
4. Submit a pull request

**See**: [Contributing Guide](development/contributing.md)

---

## Version Information

**Last Updated**: March 2026
**H2KVM Version**: 0.3.0
**Total Terms**: 150+
**Categories**: 10

---

**Need more help?** Check the [FAQ](FAQ.md) or [Getting Started Guide](getting-started/)
