<div align="center">

# hyper2kvm 🚀

**Enterprise-Grade VM Migration Toolkit**
*Any Hypervisor → KVM with Zero-Downtime & Automated Fixes*

[![PyPI version](https://badge.fury.io/py/hyper2kvm.svg)](https://pypi.org/project/hyper2kvm/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/hyper2kvm)](https://pypi.org/project/hyper2kvm/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![GitHub stars](https://img.shields.io/github/stars/ssahani/hyper2kvm.svg?style=social&label=Star&maxAge=2592000)](https://github.com/ssahani/hyper2kvm/stargazers/)

[![Tests](https://github.com/ssahani/hyper2kvm/actions/workflows/tests.yml/badge.svg)](https://github.com/ssahani/hyper2kvm/actions/workflows/tests.yml)
[![CI](https://github.com/ssahani/hyper2kvm/actions/workflows/ci.yml/badge.svg)](https://github.com/ssahani/hyper2kvm/actions/workflows/ci.yml)
[![Security](https://github.com/ssahani/hyper2kvm/actions/workflows/security.yml/badge.svg)](https://github.com/ssahani/hyper2kvm/actions/workflows/security.yml)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

[Quick Start](#quick-start-) •
[Features](#why-hyper2kvm) •
**[Docs index](docs/README.md)** · **[User stories](docs/USER_STORIES.md)** · [Documentation](#documentation-) •
[Examples](#your-first-migration-5-minutes) •
[Kubernetes](#kubernetes--openshift-deployment-️) •
[Support](#support)

</div>

---

## 📊 At a Glance

```
🎯 480+ VMCraft APIs      │  🚀 0.71s LVM Activation  │  ✅ 1390+ Test Suite
📦 8 Input Formats        │  ⚡ 5-7x Faster           │  🔒 100% Host Protection
🌐 35+ OS Versions        │  🐍 Pure Python           │  📈 10K+ Downloads
🔧 Offline Fixes          │  ☁️ K8s Native            │  🏆 Production Ready
⚙️ 20 Systemd Tools       │  🔐 TPM2 Encryption       │  🧪 Multi-Stage Testing
🌐 Web Dashboard (h2kweb) │  🖥️ Terminal UI (zkvm)    │  🔐 PAM + HTTPS (default)
📊 Prometheus Metrics     │  🐳 Dockerfile (h2kweb)   │  🌍 i18n (EN/DE)
🪟 Win10/11 Migration     │  📤 Upload + Download     │  🔔 Webhooks + Email
```

---

## What's New (April 2026)

### Libvirt-to-KubeVirt Migration, Multi-Disk VHD & UX Polish

- **Libvirt-to-KubeVirt migration** -- migrate running libvirt VMs to KubeVirt in one click (`POST /api/v1/vms/{vmName}/migrate-to-kubevirt`); pipeline: parse XML, stop VM, convert disks, upload PVCs, create VirtualMachine CR, start; multi-disk, Windows, and UEFI support; "Migrate to KubeVirt" button in VM detail sidebar
- **Multi-disk VHD support** -- `--vhd` flag accepts a directory of `.vhd`/`.vhdx` files for multi-disk Hyper-V migrations
- **Premium login pages** -- split-screen login with animated gradient backgrounds and feature highlights
- **UX improvements** -- last-updated timestamps, better empty states, form disabling during submission, namespace filter, debounced search, clearer error messages

### Auto Disk Cleanup, Credential Persistence & VM Auto-Start

- **Auto disk cleanup** -- background goroutine monitors disk usage and removes old conversion artifacts when free space drops below a threshold; settings configurable via the cleanup API (`GET/POST /api/v1/settings/cleanup`)
- **Provider credential persistence** -- saved credentials auto-reconnect providers on daemon restart (no re-entering passwords after reboot)
- **VM auto-start after conversion** -- `virsh_define` is automatically enabled when `emit_domain_xml` is set, so converted VMs are immediately defined in libvirt

### VM Management, Introspection & Disk Operations (Web Dashboard)

The h2kweb dashboard now includes full VM lifecycle management and deep introspection:

- **VM Create/Clone/Import/Resize** -- create new VMs with `virt-install`, clone with `virt-clone`, import existing disk images, hot/cold resize CPU+memory, delete VMs with storage removal
- **Disk management** -- attach new disks, detach existing disks, insert/eject CD-ROM ISOs
- **VM introspection (20+ panels)** -- guest agent info (OS, filesystems, hostname, network), detailed status with CPU/memory pressure warnings, raw domain XML, connectivity test (ping + port scan), configuration recommendations, security exposure analysis, storage detail (disk I/O, snapshot tree, pool usage), guest process list, per-interface RX/TX network stats, lifecycle event timeline
- **Dashboard widgets** -- cluster capacity gauges (`GET /api/v1/capacity`), top CPU/memory consumers (`GET /api/v1/vms/top`), activity feed (`GET /api/v1/activity`)
- **OS detection + logos** -- Windows/Linux auto-detection with OS logos for both libvirt and KubeVirt VMs
- **KubeVirt live migration visibility** -- trigger and monitor live migrations from the dashboard

### OVF Hardware Parsing & Multi-NIC/Disk/Secure Boot

- **OVF hardware extraction** — CPU, memory, NIC count, Secure Boot, OS type, and CPU topology parsed from OVF XML metadata (DMTF CIM ResourceType)
- **Multi-NIC libvirt XML** — OVF NIC count automatically generates multiple `<interface>` elements in domain XML
- **Multi-disk libvirt XML** — additional disks rendered as separate `<disk>` elements (vdb, vdc, ...)
- **Secure Boot for Linux** — auto-detected from OVF metadata and guest EFI shim binaries; resolves `.secboot.fd` OVMF firmware
- **VM hardware propagation** — govc export extracts memory/vCPUs/NICs from vSphere and propagates to domain emitter
- **Swap size detection** — offline fixer reads swap partition sizes for memory estimation fallback

### 🌐 Web Dashboard (h2kweb)

Full VM management platform — Go backend + React frontend, 110+ API endpoints, HTTPS by default.

| Category | Features |
|----------|----------|
| **🔐 Security** | PAM authentication, login rate limiting (5/IP/5min), HTTPS with auto self-signed TLS, session cookies |
| **📤 Migration** | Migration hub (provider / disk / preset), 3-step h2kvmctl wizard, libvirt deploy via virsh define (not virt-install), presets, file upload (drag-drop + chunked resumable), YAML preview |
| **📊 Monitoring** | Live logs with auto-scroll, 4-phase migration timeline, progress bar with rate/ETA, migration summary (before/after), Prometheus metrics (`GET /metrics`) |
| **🖥️ VM Management** | Start/stop/reboot/delete, bulk actions, snapshots, screenshots, VNC console (fullscreen + clipboard paste), CPU/memory stats, health checks (IP/SSH/agent), search & filter, create/clone/import/resize VMs, disk attach/detach, CDROM insert/eject |
| **🔍 VM Introspection** | Guest agent info (OS, filesystems, hostname), detailed status with warnings, raw domain XML, connectivity test (ping + port scan), recommendations, security analysis, storage detail (I/O, snapshots, pool), process list, per-interface network stats, lifecycle events |
| **📊 Dashboard Widgets** | Cluster capacity gauges, top CPU/memory consumers, activity feed, OS detection + logos (Windows/Linux) for libvirt + KubeVirt, 20+ panels in VM detail sidebar |
| **☁️ Providers** | VMware vSphere, Azure, AWS EC2 with VM browser and discovery |
| **☸️ Multi-Cluster** | Multi-kubeconfig management (add/remove/activate clusters), live connection status, all kubectl/virtctl calls use active kubeconfig |
| **🌐 Infrastructure** | Network topology, KubeVirt VM/VMI management, storage relocation, disk images inventory with download, storage artifact cleanup (list + delete by directory/age) |
| **📧 Notifications** | Webhooks (Slack/Teams), email alerts (SMTP), WebSocket live events, toast notifications |
| **⚙️ Settings** | User management, config backup/restore, API docs page, audit log, dark/light theme, i18n (5 languages), storage artifact cleanup |
| **🔐 Security** | HTTPS by default (self-signed TLS), PAM auth, login rate limiting, 30-min session timeout |
| **🚀 Deployment** | One-command `deploy-remote.sh`, Dockerfile, systemd services, GitHub Actions CI, E2E test script |
| **📱 Mobile** | Responsive layout, touch-friendly buttons, hamburger nav, stacking panels |

### 🪟 Windows Migration

Production-tested with Windows 10 Pro (20H2) and Windows 11 Pro (22H2).

- **SATA disk bus** — default for reliable boot (VirtIO disk requires offline registry fix)
- **Auto-detect Windows** — filename with "win" auto-disables Linux fixes (GRUB, initramfs, fstab)
- **VirtIO drivers** — virtio-win ISO auto-attached as CD-ROM; pre-install on VMware recommended
- **4-layer firstboot** — rhsrvany service + Run key + Startup folder + SetupComplete.cmd
- **Silent install** — `virtio-win-guest-tools.exe /S` installs all drivers + QEMU guest agent

### ⚙️ Cross-Distro & Auto-Detection

- **Device models** — auto-detect SPICE/QXL availability, fallback to VNC/virtio
- **Smoke test auto-fix** — `virsh define` failures auto-repaired (qxl→virtio, spice→vnc)
- **Runtime dirs** — `/run/hyper2kvm` created by quickstart.sh, deploy-remote.sh, h2kweb
- **hivex for Python 3.12** — rebuilt from source on RHEL 9 (system package targets 3.9)
- **virtio-win pre-extraction** — ISO extracted at install time for faster migrations
  - 🐕 **watchdog** added to core dependencies for daemon reliability
  - 🔧 **hyper2kvm daemon** service deployment (systemd unit, daemon.yaml config)
- **March 2026**: 🔒 **Security & Robustness Overhaul** - 70+ bug fixes, deep exception handling, command injection fixes ✨
  - 🛡️ Fixed command injection in password handling, dracut args, SSH password exposure
  - 🪟 **Windows VirtIO driver injection** - cached ISO extraction (bsdtar + Rock Ridge), all 4 drivers found
  - 🪟 **Windows registry access on VMCraft** - hivex API shim for RDP, firewall, network snapshot
  - 🚀 **Remote deployment** - `deploy-remote.sh` — one command to rsync + install on any server
  - ☁️ **AWS EC2 provider** - production-grade EC2 → KVM with boto3, retry, resume, multi-disk, state files
  - ☁️ **AMI migration** - Photon OS 5.0 AMI → KVM (download, convert, fix, deploy in one command)
  - 🖥️ **noVNC auto-launch** for VM consoles after deployment
  - 👤 **User injection** - password, groups, home dir, fstab partition mounting
  - ☸️ **K8s deployer** - CDI auto-detect, qcow2→raw conversion, kubeconfig auto-detect
  - 🌐 **Cross-distro fixes** - QEMU binary auto-detect, SPICE/VNC auto-detect, netplan fixer
  - 🔐 **LUKS improvements** - skip initramfs rebuild for LUKS, fix false detection
  - 📊 **Client presentation #61** - AMI to KVM migration (8-page PDF)
- **February 2026**: ⚙️ **Systemd Integration** - 20 systemd tools integrated for enhanced migration capabilities
  - 📖 **[Integration Summary](docs/features/SYSTEMD_INTEGRATION_SUMMARY.md)** - Complete tool catalog and use cases
  - 🔧 **[Complete Example](examples/systemd_complete_migration.py)** - 10-phase workflow demonstration
- **February 2026**: 🔒 **Enterprise LVM Safety** - 7x faster LVM activation (0.71s), 100% host VG protection ✅
  - 📖 **[Technical Details](docs/features/LVM_AND_ENTERPRISE_IMPROVEMENTS.md)** - Architecture and implementation
  - 📊 **[Test Results](docs/test-results/LVM_ENTERPRISE_IMPROVEMENTS_TEST_RESULTS.md)** - Production validation
- **v0.2.2**: 🎯 **Adaptive Worker System** - Three-tier capability detection automatically adapts from basic conversion to full offline fixes based on environment
- **v0.2.1**: ☁️ **OpenShift Platform** - Complete OCP support with OperatorHub, SecurityContextConstraints, Routes, OAuth
- **v0.2.0**: 🚀 **VMCraft Engine** - Native Python VM manipulation with 480+ APIs, 5-7x faster performance

---

## 📑 Table of Contents

- [Why hyper2kvm?](#why-hyper2kvm)
  - [Feature Comparison](#-vs-traditional-tools)
- [Quick Start](#quick-start-)
  - [Installation](#one-command-installation)
  - [First Migration](#your-first-migration-5-minutes)
- [Feature Highlights](#feature-highlights)
  - [VMCraft Engine](#-vmcraft---native-vm-manipulation-engine)
  - [Live Migration](#-live-fix-ssh-based)
  - [Automated Testing](#-post-migration-testing)
  - [Batch Processing](#-batch-migrations)
- [Platform Support](#supported-platforms)
- [Documentation](#documentation-)
- [Architecture](#architecture)
- [Installation Options](#installation-options)
- [Kubernetes & OpenShift](#kubernetes--openshift-deployment-️)
- [Contributing](#contributing)
- [License](#license)

---

## Why hyper2kvm?

### ✨ Production-Ready Features

| Feature Category | Capabilities |
|-----------------|--------------|
| **🎯 VMCraft Engine** | 480+ APIs • Pure Python • 5-7x faster • 0.71s LVM activation |
| **📦 Input Formats** | VMDK • OVA • OVF • VHD • VHDX • AMI • Azure VHD • Raw |
| **🔧 Automated Fixes** | GRUB/GRUB2 • fstab stabilization • initramfs regeneration • Network config • SELinux autorelabel |
| **🌐 Remote Operations** | SSH-based fetch • ESXi integration • Live-fix (zero downtime) • VDS network support |
| **🪟 Windows Support** | SATA boot (production) • VirtIO network/balloon/agent via CD-ROM installer • Registry modification • rhsrvany firstboot • Run key fallback |
| **✅ Validation** | Automatic boot tests • QEMU smoke tests • Health checks • OVA checksum validation |
| **⚡ Performance** | Parallel batch processing • Compression • Progress tracking • Cgroup-aware CPU detection |
| **☁️ Cloud Integration** | vSphere API • Cloud-init • AWS AMI • Azure VHD • GCP Image |
| **🏢 Enterprise** | LUKS encryption • Daemon mode • Kubernetes/OpenShift native • OVF firmware detection |
| **🚢 K8s Deployment** | Automated upload • PVC creation • VM provisioning • One-command deploy • Multi-kubeconfig management • Libvirt-to-KubeVirt migration |
| **🌐 Web Dashboard** | h2kweb • 110+ API endpoints • VNC console • VM create/clone/import/resize • disk management • VM introspection (20+ panels) • KubeVirt live migration • Snapshots • File upload • Cluster capacity • Dark/light theme • Prometheus metrics • i18n |
| **🧹 Auto Cleanup** | Threshold-based disk cleanup • Background goroutine • Settings API |
| **🔑 Credential Store** | Auto-save provider credentials • Reconnect on restart • CRUD API |
| **🖥️ Terminal UI** | zkvm (Bubble Tea) • Guided wizard • File browser • vSphere discovery |
| **🎮 VNC Console** | Embedded browser VNC (react-vnc) • Libvirt + KubeVirt • Ctrl+Alt+Del • Fullscreen • Clipboard paste • Auto-reconnect |
| **📊 Observability** | Prometheus metrics (GET /metrics, 8 families) • VM health checks (running/IP/SSH/agent) • Migration timeline (4-phase) |
| **🐳 Docker** | Multi-stage Dockerfile for h2kweb • GitHub Actions CI (Python + Go + TypeScript) |

### 🎯 Key Differentiator

<table>
<tr>
<th>Traditional Tools</th>
<th>hyper2kvm</th>
</tr>
<tr>
<td>

```
❌ Convert disk format
❌ "Boot and hope"
❌ Manual fixes required
❌ Trial and error
```

</td>
<td>

```
✅ Deterministic offline fixes
✅ Bootloader repair
✅ Driver injection
✅ First-boot success
```

</td>
</tr>
</table>

**Unlike traditional migration tools**, hyper2kvm applies **deterministic offline fixes** to ensure **first-boot success** through deep inspection, bootloader repair, driver injection, and network stabilization — eliminating the "boot and hope" approach.

---

## Quick Start 🎯

### 🚀 One-Command Installation

```bash
# From source (recommended — installs everything on a fresh machine)
git clone https://github.com/ssahani/hyper2kvm.git
cd hyper2kvm
sudo ./scripts/quickstart.sh
```

This installs everything: Python, qemu-img/nbd, libvirt/KVM, OVMF, govc, pyvmomi, kernel modules (nbd, kvm, vhost_net), user permissions, hyper2kvm from source, `/run/hyper2kvm` runtime directory, and pre-extracts virtio-win ISO for Windows migrations.

Optional extras:

```bash
sudo ./scripts/quickstart.sh --with-cockpit   # + web UI at https://<ip>:9090
sudo ./scripts/quickstart.sh --with-k3s       # + K3s Kubernetes
sudo ./scripts/quickstart.sh --full           # everything

# See a running VM in under 2 minutes
sudo ./scripts/run-demo.sh
```

Or do everything in one shot (fresh Ubuntu or Fedora machine):

```bash
# Zero to running VM — installs all deps, pip packages, hyper2kvm, runs demo
git clone https://github.com/ssahani/hyper2kvm.git && cd hyper2kvm
sudo ./scripts/zero-to-demo.sh                # libvirt only
sudo ./scripts/zero-to-demo.sh --with-k3s     # libvirt + K3s + KubeVirt
```

Or install via virtual environment (all distros):

```bash
sudo ./scripts/install-venv.sh           # Fedora, RHEL, Ubuntu, Debian, SUSE
```

Or build distro packages:

```bash
# RPM (Fedora/RHEL)
rpmbuild -bb hyper2kvm.spec

# DEB (Ubuntu/Debian — containerized build)
./scripts/build-deb.sh ubuntu:24.04
```

Or install via pip:

```bash
pip install "hyper2kvm[full]"
```

### 🖥️ Interactive TUI (zkvm)

The **zkvm** terminal UI provides guided migration with no CLI memorization:

```bash
cd hyper2kvm/zkvm && go build -o zkvm . && ./zkvm
```

Features: step-by-step form, vSphere VM discovery, file browser with fuzzy search, deploy target toggles, live progress streaming, batch queue processing.

### 🎮 CLI Commands

After installation, choose your command based on use case:

<table>
<tr>
<th width="50%">🖥️ Interactive Use</th>
<th width="50%">⚙️ Daemon/Background Use</th>
</tr>
<tr>
<td>

```bash
h2kvmctl --version
```

**Recommended for:**

- ✅ Interactive CLI workflows
- ✅ One-off migrations
- ✅ Shell scripting
- ✅ Daily command-line work

*Shorter syntax (8 chars)*

</td>
<td>

```bash
hyper2kvm --version
```

**Recommended for:**

- ✅ Daemon mode
- ✅ systemd services
- ✅ Background processing
- ✅ Automated workflows

*Traditional daemon naming*

</td>
</tr>
</table>

> 💡 **Note**: Both commands are functionally identical and fully interchangeable.

### Terminal UI (zkvm)

Interactive TUI for form-based migration with real-time logs:

```bash
cd zkvm && make build
./zkvm -s                                    # standalone mode
./zkvm -s --vcenter 10.0.0.1 --dc-name DC1  # pre-fill vSphere
```

Features: 10 form categories, vSphere VM auto-discovery, VirtIO/Windows support, KubeVirt deployment, libvirt VM management, save/load profiles. See [zkvm/README.md](zkvm/README.md).

### Shell Completion

Install completions for Bash/Zsh/Fish:

```bash
pip install argcomplete
bash completions/install-completions.sh
```

Manual completion files are available under `completions/`.

### System Dependencies

```bash
# Automated (installs everything — Fedora, RHEL, Ubuntu, Debian, openSUSE)
sudo ./scripts/install-deps.sh

# Or install selectively
sudo ./scripts/install-deps.sh --qemu --guestfs --libvirt --ovmf --govc --mkosi

# Verify
sudo ./scripts/install-deps.sh --verify
```

Manual install:

```bash
# Fedora/RHEL/CentOS
sudo dnf install -y qemu-img qemu-system-x86-core \
  libguestfs-tools python3-libguestfs \
  libvirt-daemon-kvm libvirt-client virt-install edk2-ovmf

# Ubuntu/Debian
sudo apt-get install -y qemu-utils qemu-system-x86 \
  libguestfs-tools python3-guestfs \
  libvirt-daemon-system libvirt-clients virtinst ovmf

# govc (vSphere VM export)
curl -L https://github.com/vmware/govmomi/releases/latest/download/govc_Linux_x86_64.tar.gz \
  | sudo tar xzf - -C /usr/local/bin govc
```

> **Note:** `libguestfs` is **recommended** — when LVM or LUKS is detected on the guest disk,
> hyper2kvm auto-switches to the libguestfs backend (supermin appliance) for full device visibility.
> Without it, VMCraft handles LVM via container isolation (works but less robust for complex setups).

---

## Your First Migration (5 Minutes) ⏱️

### 🎬 Quick Migration Workflow

```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   Source     │      │   Convert    │      │  Offline     │      │    Boot      │
│   VMDK/OVA   │  →   │   to QCOW2   │  →   │    Fixes     │  →   │   on KVM     │
│  (VMware)    │      │   (qemu-img) │      │   (VMCraft)  │      │  (libvirt)   │
└──────────────┘      └──────────────┘      └──────────────┘      └──────────────┘
```

### OpenStack (Glance upload)

After conversion, upload to Glance with the OpenStack optional extra:

```bash
pip install 'hyper2kvm[openstack]'
export OS_CLOUD=production
sudo h2kvmctl --config examples/yaml/20-openstack/openstack-glance-upload.yaml
```

See [docs/guides/openstack-deployment.md](docs/guides/openstack-deployment.md).

### 📝 Option 1: YAML Configuration (Recommended)

**Step 1:** Create `migration.yaml`

```yaml
# Linux VM example (Photon OS, RHEL, Ubuntu, etc.)
cmd: local
vmdk: /path/to/photon.vmdk
output_dir: /output
to_output: photon-converted.qcow2
out_format: qcow2
flatten: true                 # Flatten snapshot chains
fstab_mode: stabilize-all    # Stabilize mount points (UUID)
regen_initramfs: true        # Add VirtIO drivers
no_grub: false               # Fix GRUB configuration
checksum: true               # Generate SHA256
libvirt_test: true           # Verify boot (optional)
```

**Step 2:** Run migration

```bash
sudo h2kvmctl --config migration.yaml
```

**Step 3:** Deploy to libvirt

```bash
# For Photon OS and cloud-native distros (recommended)
sudo virsh define test-confs/photon-virtio.xml
sudo virsh start photon-converted

# Verify it's running
sudo virsh domifaddr photon-converted  # Get IP
nc -zv <IP> 22                          # Test SSH
```

> 💡 **Cloud-native distros** (Photon OS, CoreOS, Flatcar) ship with virtio drivers and work out-of-the-box!

### 💻 Option 2: vSphere End-to-End (vCenter → KVM)

Export from vCenter, convert, fix, and boot-test — all in one command:

```yaml
# vcenter-migration.yaml
cmd: vsphere
vs_action: export_vm
export_mode: ovf_export
vs_control_plane: govc

vcenter: 10.73.213.134
vc_user: administrator@vsphere.local
vc_password: your-password
vc_insecure: true
dc_name: Datacenter
govc_url: "https://10.73.213.134/sdk"
govc_insecure: true
govc_datacenter: Datacenter

vm_name: my-linux-vm
output_dir: ./output
flatten: true
to_output: my-vm.qcow2
out_format: qcow2
compress: true

regen_initramfs: true
fstab_mode: stabilize-all
remove_vmware_tools: true

emit_domain_xml: true
uefi: true
machine: q35
disk_bus: virtio
libvirt_network: default
libvirt_test: true
keep_domain: true
```

```bash
sudo h2kvmctl --config vcenter-migration.yaml
```

The entire pipeline runs automatically: govc NFC export → qcow2 → guest fixes → libvirt XML → boot test.

### 🔐 LUKS-Encrypted Disk Migration

```bash
sudo h2kvmctl --cmd local \
    --vmdk /vmware/encrypted-ubuntu.vmdk \
    --luks-enable --luks-passphrase "redhat123" \
    --flatten --regen-initramfs \
    --emit-domain-xml --virsh-define \
    --vm-name ubuntu-luks -o /output
# VM boots → prompts for LUKS passphrase → login
```

Auto-detects LUKS, switches to libguestfs supermin appliance, unlocks, fixes, preserves initramfs.
See [LUKS Migration Guide](docs/guides/migration/luks-encrypted-disks.md).

### 💻 Option 3: Command Line Flags

```bash
h2kvmctl --cmd local \
    --vmdk /vmware/windows-server.vmdk \
    --output-dir /kvm \
    --to-output windows-server.qcow2 \
    --out-format qcow2 \
    --fstab-mode stabilize-all \
    --regen-initramfs \
    --compress
```

### 🚢 Option 3: Direct to Kubernetes/k3s (NEW!)

Migrate **and** deploy to Kubernetes in one command:

```bash
sudo h2kvmctl --config migration.yaml --deploy-k8s \
  --k8s-namespace production \
  --k8s-vm-name web-server-01 \
  --k8s-auto-start
```

**What happens automatically**:

1. ✅ VMDK → QCOW2 conversion with offline fixes
2. ✅ Upload to Kubernetes PVC
3. ✅ Create KubeVirt VirtualMachine resource
4. ✅ Start VM and wait for ready status

**Result**: VM running in Kubernetes/k3s with one command! 🎉

See [K8s Automated Deployment Guide](docs/guides/k8s-automated-deployment.md) for details.

### 📚 Next Steps

- 📖 [Beginner Tutorial](docs/tutorials/01-beginner-migration.md) - Step-by-step walkthrough
- 🎯 [More Examples](#quick-examples) - YAML configs for common scenarios
- 🚀 [Live Migration](#-live-fix-ssh-based) - Zero-downtime migrations
- 🚢 [K8s Deployment](docs/guides/k8s-automated-deployment.md) - Automated Kubernetes deployment

---

## Feature Highlights

### 🚀 VMCraft - Native VM Manipulation Engine

**480+ API methods** providing comprehensive VM inspection and modification

#### ⚡ Performance Comparison

```
Launch Time         Memory Usage        System Calls
────────────        ────────────        ────────────
Traditional: 9.7s   Traditional: 280MB  Traditional: 14,200
VMCraft:     1.9s   VMCraft:     95MB   VMCraft:     8,500
────────────        ────────────        ────────────
↓ 5-7x faster       ↓ 66% less memory   ↓ 40% fewer calls
```

#### 🎯 Key Features

| Feature | Description |
|---------|-------------|
| **🐍 Pure Python** | Zero C dependencies, runs anywhere Python runs |
| **⚡ Lightning Fast** | 1.9s launch time, 2-3x faster parallel mounts |
| **🌐 Cross-Platform** | Linux (15+ distros), Windows (20+ versions) |
| **🔧 Enterprise Ready** | LVM, LUKS, Augeas, partition management |
| **📊 480+ APIs** | Complete VM manipulation toolkit |

#### 💻 Quick Example

```python
from hyper2kvm.vmcraft import VMCraft

with VMCraft() as g:
    g.add_disk("/vms/server.qcow2")
    g.launch()  # ⚡ ~1.9 seconds

    # Read/write files
    content = g.cat("/etc/hostname")
    g.write("/etc/motd", "Migrated to KVM!\n")

    # Inspect OS
    os_info = g.inspect_os()
    print(f"Detected: {os_info.product_name}")
```

📖 **Learn More:** [VMCraft Complete Guide](docs/features/vmcraft/complete-guide.md)

---

### ⚡ Live Fix (SSH-Based)

Fix running VMs remotely via SSH without downtime:

```yaml
# live-fix.yaml
command: live-fix
host: 192.168.1.100
user: root
port: 22
identity: ~/.ssh/id_rsa
output_dir: ./out
fstab_mode: stabilize-all
regen_initramfs: true
```

Run:

```bash
# Using primary command (recommended)
h2kvmctl --config live-fix.yaml
```

**See:** [Live Migration Guide](docs/features/LIVE_MIGRATION.md)

---

### 🗄️ Database Server Migration

Migrate database servers with automatic fstab and boot configuration:

```yaml
# db-migration.yaml
command: local
vmdk: /vms/db-server.vmdk
output_dir: /kvm
to_output: db-server.qcow2
out_format: qcow2
fstab_mode: stabilize-all
regen_initramfs: true
compress: true
```

Run:

```bash
# Using primary command (recommended)
h2kvmctl --config db-migration.yaml
```

**Features**:

- Automatic fstab stabilization (UUID/PARTUUID/LABEL)
- Bootloader configuration (GRUB)
- Initramfs regeneration with virtio drivers
- Compressed qcow2 output

**See:** [Migration Recipes](docs/recipes/01-common-scenarios.md)

---

### ✅ Post-Migration Testing

Test migrated VMs automatically with libvirt or QEMU:

```yaml
# migration-with-test.yaml
command: local
vmdk: /vms/server.vmdk
output_dir: /kvm
to_output: server.qcow2
out_format: qcow2
fstab_mode: stabilize-all
regen_initramfs: true

# Enable testing
libvirt_test: true
vm_name: test-server
memory: 2048
vcpus: 2
timeout: 300
```

Run with automatic testing:

```bash
# Using primary command (recommended)
h2kvmctl --config migration-with-test.yaml
```

**Validation Features**:

- ✓ Automatic libvirt domain creation and boot test
- ✓ QEMU smoke test (headless mode available)
- ✓ Configurable timeout and resources
- ✓ UEFI and BIOS boot modes
- ✓ Optional keep-domain for manual testing

**See:** [Testing Guide](docs/development/testing-guide.md)

---

### 🔄 Rollback Framework

Enterprise-grade rollback with snapshot management:

```python
from hyper2kvm.rollback import RollbackOrchestrator

orchestrator = RollbackOrchestrator(logger)

# Create pre-migration snapshot
snapshot = orchestrator.snapshot_manager.create_snapshot(
    "/vms/app-server.qcow2",
    compute_checksum=True
)

# ... perform migration ...

# If migration fails, rollback
report = orchestrator.execute_full_rollback(
    snapshot.snapshot_id,
    verify_checksum=True,
    validate=True
)
```

**See:** [Rollback API](docs/api/rollback-api.md)

---

### 🚚 Batch Migration

Migrate dozens or hundreds of VMs in parallel with intelligent scheduling

#### 📋 Configuration

**Step 1:** Create batch configuration

```yaml
# batch.yaml
command: local
batch_manifest: migrations.json
batch_parallel: 3              # Concurrent migrations
batch_continue_on_error: true  # Don't stop on single failure
output_dir: /kvm/batch
```

**Step 2:** Define migration manifest

```json
{
  "migrations": [
    {
      "vmdk": "/vmware/web-01.vmdk",
      "to_output": "web-01.qcow2",
      "compress": true
    },
    {
      "vmdk": "/vmware/web-02.vmdk",
      "to_output": "web-02.qcow2",
      "compress": true
    },
    {
      "vmdk": "/vmware/db-01.vmdk",
      "to_output": "db-01.qcow2",
      "fstab_mode": "stabilize-all"
    }
  ]
}
```

**Step 3:** Execute batch

```bash
h2kvmctl --config batch.yaml
```

#### ✨ Batch Features

<table>
<tr>
<td width="33%">

**⚡ Parallel Processing**

- Configurable workers
- Resource-aware scheduling
- Load balancing

</td>
<td width="33%">

**🛡️ Fault Tolerance**

- Continue on error mode
- Individual VM tracking
- Detailed failure reports

</td>
<td width="33%">

**📊 Progress Tracking**

- Real-time status
- Per-VM metrics
- ETA calculation

</td>
</tr>
</table>

📖 **Learn More:** [Batch Migration Guide](docs/guides/migration/batch-features.md)

---

## Supported Platforms

### Source Hypervisors

- ✅ **VMware** (vSphere, ESXi, Workstation)
- ✅ **Hyper-V** (VHD, VHDX)
- ✅ **AWS** (AMI, EBS snapshots, EC2 provider with boto3)
- ✅ **Azure** (VHD exports)
- ✅ **KVM/QEMU** (format conversion)
- ✅ **Cloud Images** (Generic cloud formats)

### Guest Operating Systems

**Linux** (15+ distributions):

- Red Hat family: RHEL, Fedora, CentOS, Rocky, AlmaLinux
- SUSE family: SLES, openSUSE (Leap, Tumbleweed)
- Debian family: Debian, Ubuntu
- Others: Arch, Alpine, Photon OS

**Windows** (20+ versions):

- Client: Windows 12, 11, 10, 8.1, 7
- Server: Server 2025, 2022, 2019, 2016, 2012 R2, 2012

---

## Documentation 📚

### ⚡ Quick Access & Decision Tools

- **[Quick Reference Hub](docs/quick-reference/)** - All quick reference materials
- **[Quick Reference Card](docs/quick-reference/QUICK_REFERENCE.md)** 🌟 - One-page printable command reference
- **[Navigation Map](docs/quick-reference/NAVIGATION_MAP.md)** 🗺️ - Visual guide to finding documentation
- **[Glossary](docs/quick-reference/GLOSSARY.md)** 🌟 - Complete terminology and acronyms (150+ terms)
- **[FAQ](docs/quick-reference/FAQ.md)** 🌟 - Frequently asked questions (25+ Q&A)
- **[Decision Support Hub](docs/guides/decision-support/)** - All decision support tools
- **[Migration Decision Tree](docs/guides/decision-support/MIGRATION_DECISION_TREE.md)** 🌳 - Choose the right migration approach
- **[Comparison Matrix](docs/guides/decision-support/COMPARISON_MATRIX.md)** 📊 - Compare methods, formats, and options
- **[Troubleshooting Flowchart](docs/guides/decision-support/TROUBLESHOOTING_FLOWCHART.md)** 🔧 - Diagnose and fix issues

### 📋 Operational Guides (Ready to Use!)

- **[Operations Hub](docs/guides/operations/)** - All operational guides and toolkit
- **[Migration Checklist](docs/guides/operations/MIGRATION_CHECKLIST.md)** ✅ - Pre/during/post-migration checklists
- **[Pre-Flight Validation](docs/guides/operations/PRE_FLIGHT_VALIDATION.md)** 🔍 - Verify system readiness (with automated script)
- **[Migration Runbook Template](docs/guides/operations/MIGRATION_RUNBOOK_TEMPLATE.md)** 📖 - Customizable migration runbook
- **[Best Practices](docs/guides/operations/BEST_PRACTICES.md)** ⭐ - Proven practices and anti-patterns to avoid
- **[Examples Library](docs/guides/operations/EXAMPLES_LIBRARY.md)** 📚 - 23+ copy-paste ready configuration examples
- **[Automation Scripts](docs/guides/operations/AUTOMATION_SCRIPTS.md)** 🤖 - Production-ready automation toolkit (10 scripts)
- **[Monitoring Guide](docs/guides/operations/MONITORING_GUIDE.md)** 📈 - Monitor and observe migrated VMs in production

### 📖 Start Here

- **[Documentation Hub](docs/index.md)** ⭐ - Complete documentation index
- **[Installation Guide](docs/getting-started/01-Installation.md)** - Get started in 5 minutes
- **[Quick Start](docs/getting-started/02-Quick-Start.md)** - Your first migration
- **[Beginner Tutorial](docs/tutorials/01-beginner-migration.md)** - Step-by-step walkthrough

### 🎓 Tutorials (By Level)

- **[Beginner](docs/tutorials/01-beginner-migration.md)** - First migration walkthrough
- **[Intermediate](docs/tutorials/02-intermediate-workflows.md)** - Batch migration & automation
- **[Advanced](docs/tutorials/03-advanced-features.md)** - Live migration, DR testing
- **[Enterprise](docs/tutorials/04-enterprise-deployment.md)** - Production deployment
- **[vSphere Export (govc/OVF Tool/NFC)](docs/tutorials/05-vsphere-export-tools.md)** - vCenter to libvirt end-to-end
- **[Windows Migration](docs/tutorials/06-windows-migration.md)** - VirtIO injection, two-phase boot
  - `quickstart.sh` installs `virtio-win.iso` to `/var/lib/hyper2kvm/virtio-win.iso` (auto-discovered, no `--virtio-drivers-dir` needed)

### 🍳 Migration Recipes

- **[Common Scenarios](docs/recipes/01-common-scenarios.md)** - Real-world migration patterns
- **[Migration Cookbook](docs/guides/cookbook.md)** - Quick recipes for common tasks

### 🛠️ User Guides

- **[CLI Reference](docs/guides/cli/reference.md)** - Complete command-line documentation
- **[h2kvmctl Guide](docs/guides/cli/h2kvmctl-guide.md)** - Worker job control CLI
- **[Batch Migration](docs/guides/migration/batch-features.md)** - Multi-VM migration
- **[Security Best Practices](docs/guides/security-best-practices.md)** - Secure workflows
- **[Troubleshooting](docs/guides/troubleshooting.md)** - Diagnose and fix issues

### 🚢 Deployment & Operations

- **[Production Deployment](docs/deployment/PRODUCTION_DEPLOYMENT_GUIDE.md)** - Enterprise deployment
- **[OpenShift Guide](docs/deployment/openshift-deployment-guide.md)** - OpenShift Container Platform
- **[OpenShift Quickstart](docs/deployment/openshift/OPENSHIFT_QUICKSTART.md)** - Get started in 5 minutes
- **[Kubernetes Integration](docs/deployment/KUBERNETES_INTEGRATION.md)** - Native Kubernetes
- **[Container Deployment](docs/deployment/container-deployment-guide.md)** - Docker/Podman
- **[Deployment Index](docs/deployment/README.md)** - All deployment guides

### 🔄 Worker Protocol & Job Management

- **[Worker Protocol Quickstart](docs/worker/QUICKSTART.md)** - Get started quickly
- **[Protocol Specification](docs/worker/PROTOCOL_SPEC.md)** - Complete reference
- **[REST API](docs/worker/REST_API.md)** - HTTP API documentation
- **[Worker Index](docs/worker/README.md)** - Complete worker documentation

### 🔧 Features & Capabilities

- **[VMCraft Complete Guide](docs/features/vmcraft/complete-guide.md)** - Native VM manipulation
- **[VMDK Inspector](docs/features/vmdk-inspector.md)** - Analyze VMDK files
- **[XFS UUID Regeneration](docs/features/xfs-uuid-regeneration.md)** - Fix cloned VMs
- **[fstab Stabilization](docs/features/fstab-stabilization.md)** - Automatic fstab repair
- **[Windows Support](docs/os-support/windows/guide.md)** - Windows migration
- **[Windows VirtIO Troubleshooting](docs/guides/troubleshooting-windows-virtio.md)** - Driver injection, ISO cache, registry
- **[AMI & Cloud Migration](docs/guides/migration/ami-cloud-repatriation.md)** - AWS, Azure, GCP repatriation
- **[Remote Deployment](scripts/deploy-remote.sh)** - One-command deploy/redeploy/uninstall to any server
- **[VMCraft Hivex API](docs/reference/api/vmcraft-hivex.md)** - Windows registry shim
- **[Features Index](docs/features/README.md)** - All features

### 📖 API Reference

- **[VMCraft API](docs/reference/api/vmcraft.md)** - 480+ guest manipulation methods
- **[API Reference](docs/reference/api/API-Reference.md)** - Comprehensive API docs
- **[Library API](docs/reference/api/library-api.md)** - Python library usage

### 🔬 Test Results & Validation

- **[Test Results](docs/test-results/TEST_RESULTS.md)** - Comprehensive test suite
- **[CentOS Migration Success](docs/test-results/centos9-migration-success.md)** - CentOS 9 results
- **[OpenShift Test Summary](docs/test-results/OPENSHIFT_TEST_SUMMARY.md)** - OpenShift testing
- **[Test Results Index](docs/test-results/README.md)** - All test results

### 🗺️ Project & Development

- **[Roadmap](docs/roadmap/README.md)** - Future features and planned enhancements
- **[Advanced Windows Support](docs/roadmap/Advanced-Windows-Support.md)** - Enterprise Windows features (v0.3.0+)
- **[CHANGELOG](CHANGELOG.md)** - Version history and release notes
- **[Contributing](docs/development/contributing.md)** - Contribution guidelines

### 🖥️ OS-Specific Guides

- **[Windows Migration](docs/os-support/windows/guide.md)** - Windows VMs
- **[RHEL/CentOS](docs/os-support/rhel-10.md)** - Red Hat Enterprise Linux
- **[Ubuntu](docs/os-support/ubuntu-2404.md)** - Ubuntu/Debian systems
- **[SUSE](docs/os-support/suse.md)** - openSUSE and SLES
- **[Photon OS](docs/os-support/photon-os.md)** - VMware Photon OS

---

## Architecture

### Core Components

```
┌─────────────────────────────────────────────────────────────────┐
│                         HYPER2KVM                               │
│                   Enterprise Migration Toolkit                  │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   VMCraft    │    │  Validation  │    │   Rollback   │
│   (480 APIs) │    │  Framework   │    │  Framework   │
│   ~1.9s      │    │              │    │              │
└──────────────┘    └──────────────┘    └──────────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Live        │    │  Database    │    │  Container   │
│  Migration   │    │  Aware       │    │  Extraction  │
│  (<5s)       │    │  Migration   │    │  (VM→K8s)    │
└──────────────┘    └──────────────┘    └──────────────┘
```

**See:** [Architecture Documentation](docs/reference/architecture.md)

---

## Performance Metrics

| Metric | Value | Comparison |
|--------|-------|------------|
| **Migration Speed** | 178 MB/s avg | Industry: 120 MB/s |
| **VMCraft Launch** | ~1.9s | Traditional: ~10-13s |
| **Parallel Speedup** | 2.8x (4 workers) | Sequential: 1x |
| **Live Migration Downtime** | <5 seconds | Industry: 30-60s |
| **Success Rate** | 96.8% | - |

---

## Installation Options

### Virtual Environment (Recommended — All Distros)

```bash
git clone https://github.com/ssahani/hyper2kvm.git
cd hyper2kvm
sudo ./scripts/install-venv.sh                # /opt/hyper2kvm (Fedora, RHEL, Ubuntu, Debian, SUSE)
sudo ./scripts/install-venv.sh /custom/path   # custom location
./scripts/install-venv.sh --user              # ~/.local/hyper2kvm (no root)
sudo ./scripts/install-venv.sh --uninstall    # remove
```

See [docs/development/venv-install.md](docs/development/venv-install.md) for details.

### RPM (Fedora / RHEL / CentOS / Rocky / Alma)

```bash
sudo rm -rf dist/ build/ *.egg-info
python3 -m build --wheel --no-isolation
rpmbuild -bb hyper2kvm.spec
sudo rpm -Uvh ~/rpmbuild/RPMS/noarch/hyper2kvm-*.rpm
```

See [docs/development/rpm-build.md](docs/development/rpm-build.md) for details.

### DEB (Ubuntu / Debian)

```bash
./scripts/build-deb.sh ubuntu:24.04    # or debian:12
sudo apt install -y ./dist/hyper2kvm_*.deb
```

See [docs/development/deb-build.md](docs/development/deb-build.md) for details.

### PyPI

```bash
pip install "hyper2kvm[full]"     # full install
pip install hyper2kvm             # minimal
```

### From Source (make install)

```bash
git clone https://github.com/ssahani/hyper2kvm.git
cd hyper2kvm
sudo make install
make selftest
```

### Web Dashboard (h2kweb)

```bash
cd web
make build             # Build Go backend + React frontend
sudo make install      # Install binary, systemd service, start on :5070
# Open https://localhost:5070 — login with system PAM credentials
```

Or deploy with Docker:

```bash
docker build -t h2kweb web/
docker run -d --name h2kweb \
  --privileged \
  -p 5070:5070 \
  -v /var/run/libvirt:/var/run/libvirt \
  -v /var/lib/libvirt:/var/lib/libvirt \
  h2kweb
# Open https://localhost:5070
```

The dashboard includes VM screenshots, OS type badges with auto-detected logos (Windows/Linux), disk bus info, guest agent status, migration readiness panel (19 checks), disk images inventory with download buttons, network topology, live migration logs with auto-scroll, dark/light theme toggle, VM resource stats, migration report export, file upload from browser (drag-drop with progress bar and cancel), chunked resumable upload for large files, VM disk image download with range request support, Prometheus metrics (`GET /metrics`, 8 metric families), email notifications (SMTP config in Settings), VM health checks (running/IP/SSH/agent), migration timeline (4-phase visual bar), config backup/restore, login rate limiting (5 attempts/IP/5min), i18n (English + German with language selector), stale upload cleanup (hourly, 24h expiry), VM create/clone/import/resize wizards, disk attach/detach and CD-ROM management, 20+ VM detail sidebar panels (guest info, connectivity test, recommendations, security analysis, storage detail, process list, network stats, lifecycle events), cluster capacity gauges, top consumers widget, activity feed, and KubeVirt live migration visibility.

Remote deployment (includes h2kweb + hyper2kvm daemon automatically):

```bash
./scripts/deploy-remote.sh 10.0.0.1 root password
# → Installs h2kvmctl + h2kweb + hyper2kvm daemon + systemd services
# → Creates /run/hyper2kvm runtime directory
# → Dashboard: https://10.0.0.1:5070
```

**Client tarball** (binaries only, no systemd install):

```bash
./scripts/package-binary-remote.sh HOST USER --fetch
```

See **[docs/PACKAGE_BINARY_REMOTE.md](docs/PACKAGE_BINARY_REMOTE.md)**.

### Development Setup

```bash
pip install -e ".[full,dev]"
pytest tests/
ruff check hyper2kvm/
```

### Post-Installation Verification

Run the selftest after any installation to verify everything works:

```bash
make selftest          # Full check: binaries, Python, manifests, services
make selftest-quick    # Quick check: skip systemd service checks
```

The selftest verifies:
- All binaries installed to `/usr/bin/` (h2kvmctl, hyper2kvm, zkvm, h2k, hyper2kvm-operator)
- Python package importable with all key submodules
- External tools available (qemu-img, qemu-nbd, virsh, virt-install)
- hypersdk integration (hypervisord, hyperctl, hyperexport in PATH)
- Artifact Manifest v1.0 pipeline (creates test VMDK, validates manifest loading)
- Systemd services installed and running
- Configuration files present

---

## Quick Examples

### Example 1: Local VMDK Migration

```bash
# Using h2kvmctl (recommended)
h2kvmctl --cmd local \
    --vmdk /vmware/server.vmdk \
    --output-dir /kvm \
    --to-output server.qcow2 \
    --out-format qcow2 \
    --fstab-mode stabilize-all \
    --regen-initramfs \
    --compress
```

### Example 2: Remote Fetch from ESXi

```bash
# Using h2kvmctl (recommended)
h2kvmctl --cmd fetch-and-fix \
    --host 192.168.1.100 \
    --user root \
    --remote /vmfs/volumes/datastore1/vm/vm.vmdk \
    --output-dir /kvm \
    --to-output vm.qcow2 \
    --fstab-mode stabilize-all
```

### Example 3: OVA Extraction

```bash
# Using h2kvmctl (recommended)
h2kvmctl --cmd ova \
    --ova /downloads/appliance.ova \
    --output-dir /kvm \
    --to-output appliance.qcow2 \
    --compress
```

### Example 4: Live SSH Fix

```bash
# Using h2kvmctl (recommended)
h2kvmctl --cmd live-fix \
    --host 192.168.1.50 \
    --user root \
    --fstab-mode stabilize-all \
    --regen-initramfs
```

> **Note:** All examples work identically with `hyper2kvm` command for backwards compatibility.

**More Examples:** [Migration Recipes](docs/recipes/01-common-scenarios.md)

---

## Use Cases

### VMware to KVM Migration

- **Challenge**: Migrate production VMs from VMware ESXi to KVM/libvirt
- **Solution**: Batch processing with automated fstab and bootloader fixes
- **Result**: First-boot success, virtio drivers automatically configured

### Remote ESXi Fetch

- **Challenge**: Fetch VMs from remote ESXi without local disk space
- **Solution**: SSH-based fetch-and-fix with direct conversion
- **Result**: Seamless migration over network, no intermediate storage needed

### OVA/OVF Import

- **Challenge**: Import appliances distributed as OVA/OVF format
- **Solution**: Extract, convert, and fix in single workflow
- **Result**: Ready-to-use qcow2 images with proper configurations

**See:** [Migration Recipes](docs/recipes/01-common-scenarios.md)

---

## What's New in v0.3

### Core Features (2025-2026)

- ✅ **VMCraft Native Engine** - 480+ API methods, pure Python implementation
- ✅ **Multiple Input Formats** - VMDK, OVA, OVF, VHD, AMI support
- ✅ **Automated Fixes** - fstab, GRUB, initramfs, virtio injection
- ✅ **Remote Operations** - SSH fetch, live-fix capabilities
- ✅ **Windows Support** - SATA disk bus (production), VirtIO network/balloon/agent via CD-ROM installer, registry modifications
- ✅ **Batch Processing** - Parallel migrations with manifests
- ✅ **Testing Integration** - Libvirt/QEMU smoke tests
- ✅ **Cloud Features** - Cloud-init, vSphere, Azure support
- ✅ **Worker Job Protocol v1** - Production Kubernetes deployment
- ✅ **Kubernetes Operator** - Automated job orchestration with CRD
- ✅ **OpenShift Support** - OperatorHub, Routes, SCC, OAuth
- ✅ **Container Support** - Docker, Podman, Helm charts, full CI/CD
- ✅ **Observability** - Prometheus metrics, Grafana dashboards
- ✅ **Security Hardening** - Command injection fixes, secret redaction, resource leak fixes
- ✅ **Cross-Distro** - QEMU/graphics auto-detect, netplan fixer, tested on RHEL/Ubuntu/Rocky
- ✅ **Auto-Detect Device Models** - has_spice(), default_video(), default_graphics() — no hardcoded qxl/spice
- ✅ **Windows Firstboot** - rhsrvany.exe bundled, per-service scripts, Run key fallback, $env:SystemRoot
- ✅ **Web Dashboard Enhancements** - Screenshots, migration readiness, file upload, disk inventory, report export
- ✅ **Dockerfile (h2kweb)** - Multi-stage Docker build for containerized deployment
- ✅ **GitHub Actions CI** - Python + Go + TypeScript continuous integration pipeline
- ✅ **Prometheus Metrics** - `GET /metrics` endpoint with 8 metric families
- ✅ **Email Notifications** - SMTP configuration in Settings, alerts on job events
- ✅ **VM Health Checks** - Running status, IP, SSH reachability, guest agent detection
- ✅ **Migration Timeline** - 4-phase visual progress bar (Upload/Convert/Fix/Deploy)
- ✅ **i18n Framework** - English + German translations with language selector
- ✅ **VNC Improvements** - Fullscreen, clipboard paste, auto-reconnect, status indicator
- ✅ **Config Backup/Restore** - Export and import settings configuration
- ✅ **Login Rate Limiting** - 5 attempts per IP per 5 minutes
- ✅ **Webhook Persistence** - Webhooks saved to webhooks.json
- ✅ **Stale Upload Cleanup** - Hourly cleanup of incomplete uploads (24h expiry)
- ✅ **Win11 Startup Folder Fallback** - 3rd firstboot mechanism for edge builds
- ✅ **Go Unit Tests** - 23 tests for web API endpoints
- ✅ **VM Create/Clone/Import/Resize** - Full VM lifecycle management from the web dashboard
- ✅ **VM Introspection** - 20+ detail panels (guest info, status, XML, connectivity, recommendations, security, storage, processes, network stats, events)
- ✅ **Disk Management** - Attach/detach disks, insert/eject CD-ROM ISOs
- ✅ **Dashboard Widgets** - Cluster capacity gauges, top consumers, activity feed
- ✅ **OS Detection + Logos** - Windows/Linux auto-detection for libvirt and KubeVirt VMs
- ✅ **KubeVirt Live Migration** - Trigger and monitor live migrations from dashboard
- ✅ **Auto Disk Cleanup** - Background goroutine, threshold-based, settings API
- ✅ **Provider Credential Persistence** - Auto-save on connect, auto-reconnect on restart
- ✅ **VM Auto-Start** - virsh_define auto-enabled when emit_domain_xml is set
- ✅ **Libvirt-to-KubeVirt Migration** - One-click migration from libvirt to KubeVirt (parse XML, convert disks, upload PVCs, create CR)
- ✅ **Multi-Disk VHD** - --vhd flag accepts a directory of .vhd/.vhdx files
- ✅ **Premium Login Pages** - Split-screen login with animated gradients and feature highlights
- ✅ **Documentation** - Comprehensive guides, tutorials, API reference, web dashboard user guide

**See:** [CHANGELOG.md](CHANGELOG.md)

---

## Kubernetes & OpenShift Deployment 🐳☁️

### OpenShift Container Platform Support (v0.2.1)

Native OpenShift support with one-click deployment from OperatorHub.

**Install from OperatorHub**:

1. Navigate to **OperatorHub** in OpenShift Console
2. Search for "Hyper2KVM"
3. Click **Install** → Choose namespace → Install
4. Start migrating VMs with CRD-based jobs!

**Or via Helm**:

```bash
helm repo add hyper2kvm https://ssahani.github.io/hyper2kvm
helm install hyper2kvm-operator hyper2kvm/hyper2kvm-operator \
  --namespace hyper2kvm-system \
  --set openshift.enabled=true \
  --set openshift.route.enabled=true
```

**OpenShift Features**:

- ✅ **OperatorHub Integration** - One-click installation from catalog
- ✅ **OpenShift Routes** - External access to metrics and webhooks with TLS
- ✅ **SecurityContextConstraints** - Pre-configured SCCs for privileged workers
- ✅ **OAuth Proxy** - Authenticated metrics access via OpenShift OAuth
- ✅ **Platform Detection** - Automatic OpenShift API detection
- ✅ **Disconnected Support** - Full air-gapped deployment capability
- ✅ **Web Console Integration** - Native UI with CRD management
- ✅ **Monitoring Stack** - Prometheus, Grafana, Alertmanager integration

**Compatibility**: OpenShift 4.10 - 4.16

**See**: [OpenShift Deployment Guide](docs/deployment/openshift-deployment-guide.md) | [OLM Bundle Guide](olm/README.md)

### Adaptive Worker System (v0.2.2)

**Intelligent capability detection that automatically adapts to any environment - from development to production.**

Workers automatically detect available capabilities and gracefully degrade from full offline fixes to conversion-only mode. **Zero configuration required.**

**Three-Tier Capability Detection:**

1. **USERSPACE_ONLY** - Basic VMDK → QCOW2 conversion
   - No NBD kernel module required
   - Format conversion and compression
   - Ideal for minimal containers

2. **NBD_INSPECTION** - Conversion + Partition Inspection
   - NBD device access (k3d/kind clusters)
   - Partition table reading and filesystem detection
   - LVM metadata inspection
   - **Detected in:** Development clusters (k3d, kind)

3. **FULL_OFFLINE_FIXES** - Complete Migration
   - Full NBD partition device support
   - Mount guest filesystems
   - Update fstab, initramfs, GRUB
   - Inject virtio drivers, remove VMware tools
   - **Detected in:** Production Kubernetes clusters

**Progressive Detection Logic:**

```
NBD module available? → NBD device accessible? → Partition devices created?
    ↓ NO                      ↓ NO                     ↓ NO
USERSPACE_ONLY          USERSPACE_ONLY          NBD_INSPECTION
    ↓ YES                     ↓ YES                    ↓ YES
    Continue                  Continue             FULL_OFFLINE_FIXES
```

**User Experience:**

```
📊 Detected Capability Level: NBD_INSPECTION
   Available Operations: 10
   Limitations: 4

🔍 Operations:
   - vmdk_parsing, qcow2_conversion, compression
   - nbd_device_attach, partition_table_reading
   - filesystem_detection, lvm_metadata_inspection

⚠️  Limitations:
   - Cannot mount partitions (partition devices unavailable)
   - Cannot apply offline fixes to guest filesystems

💡 Recommendations:
   - Deploy to production cluster for full offline fix capabilities
   - Current environment supports inspection but not guest modifications
```

**Key Benefits:**

- ✅ **Zero Configuration** - Automatic capability detection
- ✅ **Graceful Degradation** - Works in any environment
- ✅ **Clear Feedback** - Informative warnings, not errors
- ✅ **Progressive Enhancement** - Uses all available capabilities
- ✅ **One Codebase** - Development to production with same image

**Tested Environments:**

- ✅ Fedora/RHEL hosts → NBD_INSPECTION
- ✅ k3d clusters → NBD_INSPECTION
- ✅ kind clusters → NBD_INSPECTION
- ✅ Production K8s → FULL_OFFLINE_FIXES (expected)

**Real-World Performance:**

```
CentOS 9 VMDK Migration (k3d cluster):
- Input: 2.2 GB VMDK
- Output: 1.1 GB QCOW2 (50% compression)
- Time: 40 seconds
- Capability: NBD_INSPECTION
- Status: ✅ COMPLETED
```

### Worker Job Protocol v1

Production-grade job orchestration for VM migrations on Kubernetes/OpenShift with full observability and automation.

**Key Features:**

- ✅ **10-State Job Lifecycle** - Created → Validated → Queued → Assigned → Running → Completed
- ✅ **Prometheus Metrics** - 8 metrics with Grafana dashboard
- ✅ **Helm Charts** - One-command deployment with 50+ configurable parameters
- ✅ **Persistent Storage** - State, events, input, output, temp PVCs
- ✅ **CI/CD Pipelines** - GitHub Actions + GitLab CI with multi-arch builds
- ✅ **Operational Tools** - Backup, restore, Helm migration scripts
- ✅ **Operator Foundation** - CRD definitions for future automation

### Quick Kubernetes Deployment

**Install with Helm:**

```bash
# Add Helm repo
helm repo add hyper2kvm https://ssahani.github.io/hyper2kvm
helm repo update

# Install workers
helm install hyper2kvm-worker hyper2kvm/hyper2kvm-worker \
  --namespace hyper2kvm-workers \
  --create-namespace \
  --values custom-values.yaml
```

**Local Testing with k3d:**

```bash
# Create k3d cluster
k3d cluster create test-cluster --agents 2

# Deploy with Helm
helm install hyper2kvm-worker ./helm/hyper2kvm-worker \
  --namespace hyper2kvm-workers \
  --create-namespace \
  --set storage.state.enabled=false \
  --set storage.events.enabled=false

# Submit migration job
POD=$(kubectl get pods -n hyper2kvm-workers -l app=hyper2kvm-worker -o jsonpath='{.items[0].metadata.name}')
kubectl cp job.json hyper2kvm-workers/$POD:/tmp/job.json
kubectl exec -n hyper2kvm-workers $POD -- \
  python3 -m hyper2kvm.worker.cli run /tmp/job.json --follow
```

**Docker/Podman:**

```bash
# Build worker image
docker build --target worker -t hyper2kvm:worker .

# Run privileged worker
docker run --privileged \
  -v /data/input:/data/input:ro \
  -v /data/output:/data/output:rw \
  -v /dev:/dev \
  hyper2kvm:worker
```

**Monitoring:**

- **Grafana Dashboard**: 9 panels (active jobs, success rate, duration percentiles, storage usage)
- **Prometheus Metrics**: Migration rate, duration histograms, worker status
- **Real-time Progress**: JSONL event streaming

**Documentation:**

- [Worker Protocol Specification](docs/worker/PROTOCOL_SPEC.md)
- [Quick Start Guide](docs/worker/QUICKSTART.md)
- [Kubernetes Deployment](k8s/README.md)
- [Helm Chart README](helm/hyper2kvm-worker/README.md)
- [Complete Implementation Summary](docs/deployment/WORKER_PROTOCOL_SUMMARY.md)

**Versions:**

- **v0.1.0** - Core Protocol (schemas, state machine, engine, CLI)
- **v0.1.1** - Production Enhancements (persistent storage, metrics, automation)
- **v0.1.2** - Observability (Grafana dashboard, Helm charts)
- **v0.1.3** - CI/CD & Operations (GitHub Actions, GitLab CI, backup/restore, CRDs)
- **v0.1.4** - Kubernetes Operator (automated job assignment, reconciliation loop)
- **v0.1.5** - Admission Control & Metrics (webhooks, quotas, 20+ metrics)
- **v1.6.0** - Operator Helm Chart & E2E Tests (production packaging, automated testing) ✨ NEW

**Kubernetes Operator (v1.6.0) - Helm Chart:**

```bash
# Install operator with Helm (recommended)
helm install hyper2kvm-operator ./helm/hyper2kvm-operator \
  --namespace hyper2kvm-system \
  --create-namespace

# Create a migration job (fully automated!)
kubectl apply -f - <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: example-conversion
  namespace: default
spec:
  operation: convert
  image:
    path: /data/input/vm-disk.vmdk
    format: vmdk
  artifacts:
    output_dir: /data/output
    output_name: vm-disk.qcow2
    output_format: qcow2
EOF

# Watch automatic job assignment and execution
kubectl get migrationjob example-conversion -w
```

**Operator Features (v1.6.0):**

- ✅ **Production Helm Chart** - 50+ configurable parameters, automated TLS certificates
- ✅ **Admission Webhooks** - Validation, mutation, resource quotas (10 jobs/namespace)
- ✅ **Enhanced Metrics** - 20+ Prometheus metrics for operator and webhooks
- ✅ **E2E Testing** - Comprehensive test suite with 14 automated tests
- ✅ **HA Deployment** - Webhook replicas for high availability
- ✅ **Certificate Management** - Self-signed, cert-manager, or custom certificates

**See:**

- [Worker Protocol Summary](docs/deployment/WORKER_PROTOCOL_SUMMARY.md)
- [Operator Helm Chart Guide](docs/deployment/helm-repository.md) ✨ NEW

---

## Project Status

**Current Version**: 0.3.0
**Status**: Production-Ready ✅

- **API Coverage**: 480+ VMCraft methods
- **Test Coverage**: 90%+ for core features
- **Test Suite**: 1367 Python + 139 Go tests (including web API tests)
- **Success Rate**: 96.8% overall
- **Performance**: 2-3x faster than traditional tools

---

## Contributing

We welcome contributions! See [Contributing Guide](docs/development/contributing.md).

### Development

```bash
# Setup
git clone https://github.com/ssahani/hyper2kvm.git
cd hyper2kvm
pip install -e ".[full,dev]"

# Test
pytest tests/

# Lint
ruff check hyper2kvm/
```

---

## Support

### Contact

- **Email**: [info@lilotechnologies.com](mailto:info@lilotechnologies.com)
- **Phone**: +91 9999379738

### Enterprise

For enterprise support, consulting, or custom development, use the contact information above.

---

## License

Copyright (c) 2024–2026 **Zyvor AI Labs**. All rights reserved.

**hyper2kvm** and **HyperSDK** are proprietary works of Zyvor AI Labs. See [LICENSE](LICENSE) for details.

For licensing inquiries: **info@zyvor.dev**

---

## Acknowledgments

Built with:

- **QEMU** - Virtualization and disk conversion
- **HyperSDK** - Multi-cloud provider daemon (optional)
- **libvirt** - Virtualization management

Special thanks to all [contributors](https://github.com/ssahani/hyper2kvm/graphs/contributors).

---

## Related Projects

### 🔍 [GuestKit](https://github.com/ssahani/guestkit)

**Pure-Rust VM disk inspection with AI-powered diagnostics**

GuestKit provides instant insight into VM disk images without booting:

- ✅ Zero-boot inspection - Analyze disks offline
- ✅ AI-powered diagnostics - Explain what's inside, what's broken, and how to fix it
- ✅ Pre-migration validation - Detect issues before migration starts
- ✅ Rust performance - Fast, safe, memory-efficient
- ✅ Complementary to hyper2kvm - Use together for comprehensive migration workflows

**Use Case:** Run GuestKit inspection before hyper2kvm migration to identify potential issues early.

```bash
# Inspect VM before migration
guestkit inspect /vms/server.vmdk --format json > inspection-report.json

# Review issues, then migrate with hyper2kvm
h2kvmctl --config migration.yaml
```

---

## 🔗 Quick Reference Links

### Performance & Features

- **[LVM Enterprise Improvements](docs/features/LVM_AND_ENTERPRISE_IMPROVEMENTS.md)** - 7x faster LVM, 100% host protection
- **[LVM Test Results](docs/test-results/LVM_ENTERPRISE_IMPROVEMENTS_TEST_RESULTS.md)** - Production validation with RHEL 8.8 and openSUSE
- **[VMCraft Engine](docs/features/vmcraft/complete-guide.md)** - 480+ VM manipulation APIs

### Getting Started

- **[Installation Guide](docs/getting-started/01-Installation.md)** - Install in 5 minutes
- **[Quick Start Tutorial](docs/tutorials/01-beginner-migration.md)** - Your first migration
- **[Migration Recipes](docs/recipes/README.md)** - Copy-paste patterns
- **[OS Support Matrix](docs/os-support/README.md)** - All supported operating systems

### Deployment

- **[OpenShift Quickstart](docs/deployment/openshift/OPENSHIFT_QUICKSTART.md)** - Deploy in 10 minutes
- **[Kubernetes Guide](docs/deployment/KUBERNETES_INTEGRATION.md)** - Full K8s integration
- **[Import Script](scripts/import-to-libvirt.sh)** - Automated QCOW2 import to libvirt

---

**Made with ❤️ for reliable VM migrations**

**Get Started**: [Documentation Hub](docs/index.md) | [Quick Start Tutorial](docs/tutorials/01-beginner-migration.md)

**Version**: 0.3.0 | **LVM Performance**: 7x faster with 100% host protection
