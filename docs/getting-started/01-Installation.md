## Installation

### Table of Contents

- [One-Command Quickstart](#one-command-quickstart)
- [Quick Start (Editable Install)](#quick-start-recommended-editable-install)
- [Helper Scripts](#helper-scripts)
- [Kernel Modules](#kernel-modules)
- [Shell Completion (Optional)](#shell-completion-optional)
- [System Dependencies by OS](#system-dependencies-by-os)
  - [Linux](#linux)
  - [macOS](#macos)
  - [Windows (WSL)](#windows-wsl)
- [Running](#running)
- [Developer Install](#developer-install)

---

### One-Command Quickstart

Install h2kvm and **all** dependencies on a fresh Fedora, RHEL, Ubuntu, Debian, or openSUSE machine:

```bash
git clone https://github.com/ssahani/h2kvm.git
cd h2kvm
sudo ./scripts/quickstart.sh
```

This single command installs:

| Component | What |
|-----------|------|
| Python 3, pip | Runtime |
| qemu-img, qemu-nbd | Disk conversion and GuestKit backend |
| libguestfs, python3-libguestfs | LVM/LUKS support (supermin appliance) |
| libvirt, KVM, virt-install | VM management and hypervisor |
| OVMF/edk2 | UEFI firmware |
| govc | vSphere VM export (NFC) |
| pyvmomi | vSphere Python SDK |
| nbd, kvm, vhost_net | Kernel modules (loaded + persisted) |
| h2kvm | Installed from source |
| User permissions | libvirt, kvm, qemu, disk groups |

Optional flags:

```bash
sudo ./scripts/quickstart.sh --with-cockpit   # + Cockpit web UI (port 9090)
sudo ./scripts/quickstart.sh --with-h2kweb    # + h2kweb web dashboard (port 5070)
sudo ./scripts/quickstart.sh --with-k3s       # + K3s Kubernetes
sudo ./scripts/quickstart.sh --full           # everything (cockpit + h2kweb + k3s)
```

After install, see a running VM in under 2 minutes:

```bash
sudo ./scripts/run-demo.sh                   # Photon OS (default)
sudo ./scripts/run-demo.sh --fedora          # Fedora Cloud
sudo ./scripts/run-demo.sh --ubuntu          # Ubuntu Cloud
sudo ./scripts/run-demo.sh --local vm.vmdk   # your own VMDK
sudo ./scripts/run-demo.sh --cleanup         # remove demo VMs
```

The demo script downloads a sample image, converts it with h2kvm,
applies guest fixes, boots on libvirt, and shows the result. It includes
pre-flight checks for RAM, disk space, tools, KVM, and SELinux.

---

### Helper Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `scripts/quickstart.sh` | Fresh machine setup (everything) | `sudo ./scripts/quickstart.sh` |
| `scripts/install-deps.sh` | Selective dependency install | `sudo ./scripts/install-deps.sh --govc --qemu` |
| `scripts/setup-demo.sh` | Demo setup (Cockpit + VNC) | `sudo ./scripts/setup-demo.sh` |
| `scripts/setup-user.sh` | User permissions | `sudo ./scripts/setup-user.sh username` |
| `scripts/setup-k3s-demo.sh` | K3s + KubeVirt demo | `sudo ./scripts/setup-k3s-demo.sh --demo` |
| `scripts/run-demo.sh` | Download + convert + boot a VM | `sudo ./scripts/run-demo.sh` |
| `zkvm` (Go TUI) | Interactive terminal UI | `cd zkvm && make build && ./zkvm -s` |

Individual install flags for `install-deps.sh`:

```bash
sudo ./scripts/install-deps.sh --python       # Python 3 + pip
sudo ./scripts/install-deps.sh --qemu         # qemu-img, qemu-nbd
sudo ./scripts/install-deps.sh --guestfs      # libguestfs (optional backend)
sudo ./scripts/install-deps.sh --libvirt      # libvirt + KVM + kernel modules
sudo ./scripts/install-deps.sh --ovmf         # UEFI firmware
sudo ./scripts/install-deps.sh --govc         # govc (vSphere export)
sudo ./scripts/install-deps.sh --ovftool      # VMware OVF Tool
sudo ./scripts/install-deps.sh --pyvmomi      # vSphere Python SDK
sudo ./scripts/install-deps.sh --h2kvm    # h2kvm itself
sudo ./scripts/install-deps.sh --verify       # check all tools
sudo ./scripts/install-deps.sh --all          # install everything
```

---

### Firewall Ports

The install scripts automatically open required firewall ports (supports both `firewall-cmd` and `ufw`):

| Port | Service | Opened by |
|------|---------|-----------|
| 22/tcp | SSH | Always |
| 16509/tcp | libvirt remote management | Always |
| 5900-5999/tcp | VNC (VM consoles) | Always |
| 9090/tcp | Cockpit web UI | `--with-cockpit` |
| 6443/tcp | K3s Kubernetes API | `--with-k3s` |

Manual setup (if not using install scripts):

```bash
# Fedora / RHEL (firewall-cmd)
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --permanent --add-service=libvirt
sudo firewall-cmd --permanent --add-port=5900-5999/tcp
sudo firewall-cmd --permanent --add-service=cockpit     # optional
sudo firewall-cmd --permanent --add-port=6443/tcp       # optional (K3s)
sudo firewall-cmd --reload

# Ubuntu / Debian (ufw)
sudo ufw allow ssh
sudo ufw allow 16509/tcp
sudo ufw allow 5900:5999/tcp
sudo ufw allow 9090/tcp      # optional (Cockpit)
sudo ufw allow 6443/tcp      # optional (K3s)
```

---

### Kernel Modules

h2kvm requires these kernel modules:

| Module | Purpose | Required |
|--------|---------|----------|
| `nbd` | Network Block Device — GuestKit mounts disks via qemu-nbd | **Yes** |
| `kvm` | KVM hypervisor | Yes (for libvirt_test/boot testing) |
| `kvm_intel` or `kvm_amd` | CPU-specific KVM acceleration | Yes (auto-detected) |
| `vhost_net` | Virtio network performance | Recommended |

The install scripts automatically:

1. **Load modules** immediately via `modprobe`
2. **Persist across reboots** via `/etc/modules-load.d/h2kvm.conf`
3. **Set NBD options** via `/etc/modprobe.d/h2kvm-nbd.conf`:
   - `nbds_max=128` — supports 128 concurrent conversions
   - `max_part=16` — supports GPT disks with up to 16 partitions

Manual setup (if not using install scripts):

```bash
# Load modules
sudo modprobe nbd max_part=16
sudo modprobe kvm
sudo modprobe kvm_intel    # Intel CPUs
# sudo modprobe kvm_amd    # AMD CPUs
sudo modprobe vhost_net

# Persist across reboots
echo -e "nbd\nkvm\nvhost_net" | sudo tee /etc/modules-load.d/h2kvm.conf
echo "options nbd nbds_max=128 max_part=16" | sudo tee /etc/modprobe.d/h2kvm-nbd.conf

# Verify
lsmod | grep -E "nbd|kvm|vhost"
ls /dev/nbd0    # Should exist after nbd is loaded
ls /dev/kvm     # Should exist if KVM is available
```

### Quick start (recommended: editable install)

```bash
git clone https://github.com/ssahani/h2kvm.git
cd h2kvm

python3 -m venv .venv
source .venv/bin/activate

python -m pip install -U pip wheel setuptools
python -m pip install -r requirements.txt
python -m pip install -e .

# sanity check
h2kvmctl --help
# or use the installed CLI:
h2kvmctl --help
```

### Shell Completion (Optional)

Enable intelligent tab completion for bash, zsh, or fish shells. This provides automatic completion for all command-line arguments and options.

**Prerequisites:**

```bash
# Install argcomplete (required for shell completion)
pip install argcomplete

# Or via system package manager
sudo dnf install python3-argcomplete  # Fedora/RHEL/CentOS
sudo apt install python3-argcomplete  # Debian/Ubuntu
sudo pacman -S python-argcomplete     # Arch Linux
brew install argcomplete              # macOS
```

**Installation:**

```bash
# Interactive installation (recommended)
./completions/install-completions.sh

# Or install for a specific shell
./completions/install-completions.sh bash
./completions/install-completions.sh zsh
./completions/install-completions.sh fish

# Install for all shells
./completions/install-completions.sh all
```

**Usage:**

After installation, you can use tab completion:

```bash
h2kvm --<TAB>              # Shows all available options
h2kvm --vm<TAB>            # Completes to --vmdk, --vm-name, etc.
h2kvm --vmdk /path/<TAB>   # Path completion
```

For detailed installation instructions and troubleshooting, see [completions/README.md](../completions/README.md).

### Automated Installation (Recommended)

The fastest way to install h2kvm and all dependencies:

```bash
# Install everything (govc, ovftool, pyvmomi, qemu-img, libguestfs, libvirt, OVMF)
sudo ./scripts/install-deps.sh

# Or install selectively
sudo ./scripts/install-deps.sh --govc --qemu --guestfs --libvirt --ovmf

# Check what's installed
sudo ./scripts/install-deps.sh --verify
```

The script auto-detects your distro (Fedora, RHEL, Ubuntu, Debian, openSUSE) and uses the right package manager.

Available flags:

| Flag | Component | Required for |
|------|-----------|-------------|
| `--qemu` | qemu-img | Disk conversion (VMDK → qcow2) |
| `--guestfs` | libguestfs-tools | Offline guest fixes (fstab, initramfs, grub) |
| `--libvirt` | libvirt + KVM | Running/testing converted VMs |
| `--ovmf` | OVMF/edk2 | UEFI boot support |
| `--govc` | govc (govmomi) | vSphere VM export via API |
| `--ovftool` | VMware OVF Tool | vSphere VM export (VMware official) |
| `--pyvmomi` | pyvmomi | vSphere Python SDK |
| `--h2kvm` | h2kvm | The tool itself |
| `--verify` | — | Check all tools |
| `--all` | Everything | Full install |

---

### System dependencies by OS

`h2kvm` is Python with **GuestKit** (`hypersdk-guestkit`) for offline disk inspect and repair.

**Core dependencies** (required):

| Tool | Purpose |
|------|---------|
| `qemu-img` | Disk format conversion (VMDK/VHD/RAW → qcow2) |
| `libguestfs-tools` | Offline guest filesystem fixes (fstab, initramfs, grub) |
| `openssh-client` | SSH access for `fetch-and-fix` and `live-fix` modes |

**VMware vSphere export** (for `cmd: vsphere`):

| Tool | Purpose |
|------|---------|
| `govc` | Open-source vSphere CLI for VM export via NFC (recommended) |
| `ovftool` | VMware official OVF/OVA export tool (optional) |
| `pyvmomi` | vSphere Python SDK for API access |

**libvirt/KVM** (for running converted VMs):

| Tool | Purpose |
|------|---------|
| `libvirt` | VM management daemon |
| `qemu-kvm` | KVM hypervisor |
| `OVMF/edk2` | UEFI firmware for UEFI-based VMs |
| `virt-install` | CLI for defining VMs (optional) |

---

## Linux

#### Fedora / RHEL / CentOS Stream

```bash
# Core + libvirt
sudo dnf install -y \
  python3 python3-pip python3-virtualenv \
  qemu-img qemu-kvm \
  libguestfs-tools \
  openssh-clients rsync \
  libvirt-client libvirt-daemon-kvm virt-install \
  edk2-ovmf

# vSphere tools
pip install pyvmomi

# govc (VM export from vCenter)
curl -L https://github.com/vmware/govmomi/releases/latest/download/govc_Linux_x86_64.tar.gz \
  | sudo tar xzf - -C /usr/local/bin govc

# Enable libvirt
sudo systemctl enable --now libvirtd
```

#### Ubuntu / Debian

```bash
# Core + libvirt
sudo apt-get update
sudo apt-get install -y \
  python3 python3-pip python3-venv \
  qemu-utils qemu-system-x86 \
  libguestfs-tools \
  openssh-client rsync \
  libvirt-clients libvirt-daemon-system virtinst \
  ovmf

# vSphere tools
pip install pyvmomi

# govc
curl -L https://github.com/vmware/govmomi/releases/latest/download/govc_Linux_x86_64.tar.gz \
  | sudo tar xzf - -C /usr/local/bin govc

# Enable libvirt
sudo systemctl enable --now libvirtd
```

#### openSUSE / SLES

```bash
# Core + libvirt
sudo zypper install -y \
  python3 python3-pip python3-virtualenv \
  qemu-tools qemu-kvm \
  guestfs-tools \
  openssh rsync \
  libvirt libvirt-client virt-install \
  qemu-ovmf-x86_64

# vSphere tools
pip install pyvmomi

# govc
curl -L https://github.com/vmware/govmomi/releases/latest/download/govc_Linux_x86_64.tar.gz \
  | sudo tar xzf - -C /usr/local/bin govc
```

#### Arch Linux / Manjaro

```bash
sudo pacman -Syu --noconfirm \
  python python-pip python-virtualenv \
  qemu-img qemu-system-x86 \
  openssh rsync \
  libvirt virt-manager edk2-ovmf

sudo systemctl enable --now libvirtd
pip install pyvmomi
```

#### Alpine Linux

```bash
sudo apk add --no-cache \
  python3 py3-pip py3-virtualenv \
  qemu-img qemu-system-x86_64 \
  openssh-client rsync \
  libvirt libvirt-daemon libvirt-client

sudo rc-service libvirtd start
sudo rc-update add libvirtd
```

---

### Installing govc (vSphere VM Export)

govc is the recommended tool for exporting VMs from vCenter/ESXi. It uses the vSphere API with NFC (Network File Copy) for disk streaming.

```bash
# Linux x86_64
curl -L https://github.com/vmware/govmomi/releases/latest/download/govc_Linux_x86_64.tar.gz \
  | sudo tar xzf - -C /usr/local/bin govc

# Linux ARM64
curl -L https://github.com/vmware/govmomi/releases/latest/download/govc_Linux_arm64.tar.gz \
  | sudo tar xzf - -C /usr/local/bin govc

# macOS
brew install govc

# Verify
govc version
```

Test connectivity:

```bash
export GOVC_URL='https://vcenter.example.com/sdk'
export GOVC_USERNAME='administrator@vsphere.local'
export GOVC_PASSWORD='your-password'
export GOVC_INSECURE=1
export GOVC_DATACENTER='Datacenter'

# List VMs
govc ls /Datacenter/vm/

# Get VM info
govc vm.info MyVM
```

### Installing OVF Tool (Optional)

VMware OVF Tool is an alternative export method. Download from:
https://developer.broadcom.com/tools/open-virtualization-format-ovf-tool/latest

```bash
# Install from zip (OVF Tool 5.0+)
sudo mkdir -p /opt/ovftool
sudo unzip VMware-ovftool-*.zip -d /opt/ovftool
sudo ln -sf /opt/ovftool/ovftool /usr/local/bin/ovftool

# Or install from legacy bundle (OVF Tool 4.x)
# chmod +x VMware-ovftool-*.bundle
# sudo ./VMware-ovftool-*.bundle

# Verify
ovftool --version
```

---

### VMware to libvirt: Complete Setup Verification

After installing everything, verify the full pipeline is ready:

```bash
# Run the verification script
sudo ./scripts/install-deps.sh --verify

# Expected output:
# [INFO] govc: /usr/local/bin/govc
# [INFO] ovftool: /usr/sbin/ovftool       (optional)
# [INFO] qemu-img: /usr/bin/qemu-img
# [INFO] guestfish: /usr/bin/guestfish
# [INFO] virsh: /usr/bin/virsh
# [INFO] h2kvmctl: /usr/local/bin/h2kvmctl
# [INFO] pyvmomi: OK
# [INFO] OVMF: /usr/share/OVMF/OVMF_CODE.fd
# [INFO] 8 tools found, 0 missing
```

Then run a test migration:

```bash
# Export from vCenter and convert to libvirt (end-to-end)
sudo ./h2kvmctl --config test-confs/photon-vcenter-to-libvirt.yaml

# Or convert a local VMDK
sudo ./h2kvmctl --config test-confs/photon-to-libvirt.yaml
```

See [vSphere Export Tutorial](../tutorials/05-vsphere-export-tools.md) for detailed usage.

---

## macOS

macOS support works with GuestKit. For best performance, use the Docker option below for a full Linux environment.

### Option 1: Using Homebrew

```bash
# Install Homebrew if not already installed
# /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install QEMU (qemu-img works natively)
brew install qemu

# Install Python dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```bash

**Note:** macOS support works with GuestKit. The Docker option below provides a full Linux environment.

### Option 2: Using Docker (Recommended for macOS)

Run h2kvm in a Linux container:

```bash
# Build container
docker build -t h2kvm .

# Run with volume mounts
docker run -it --rm \
  --privileged \
  -v $(pwd)/input:/input \
  -v $(pwd)/output:/output \
  h2kvm local --vmdk /input/disk.vmdk --to-output /output/disk.qcow2
```bash

### Option 3: Use a Linux VM

The most reliable option for macOS users:
1. Install UTM, Parallels, or VMware Fusion
2. Create an Ubuntu or Fedora VM
3. Follow Linux installation instructions inside the VM

---

## Windows (WSL)

h2kvm works in **Windows Subsystem for Linux (WSL2)** with some caveats.

### Prerequisites

1. **Install WSL2** (Windows 10/11):
   ```powershell
   # Run in PowerShell as Administrator
   wsl --install -d Ubuntu
   ```

2. **Enable nested virtualization** (required for KVM):
   ```powershell
   # Only works on Windows 11 or Windows 10 build 19044+
   # May require enabling in BIOS/UEFI
   ```

### Installation in WSL2

Once inside your WSL2 Ubuntu environment:

```bash
# Update package list
sudo apt-get update

# Install system dependencies
sudo apt-get install -y \
  python3 python3-pip python3-venv \
  qemu-utils qemu-system-x86 \
  openssh-client rsync \
  libvirt-clients libvirt-daemon-system

# Clone and install h2kvm
git clone https://github.com/ssahani/h2kvm.git
cd h2kvm

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```bash

### Known WSL2 Limitations

- **KVM acceleration** may not work (depends on Windows version and CPU)
- File I/O between Windows and WSL2 can be slow
- Use `/mnt/c/` to access Windows drives

### Workaround: Use Docker Desktop for Windows

```powershell
# In PowerShell (Windows side)
docker run -it --rm --privileged `
  -v C:\VMs\input:/input `
  -v C:\VMs\output:/output `
  h2kvm local --vmdk /input/disk.vmdk --to-output /output/disk.qcow2
```bash

---

## Container/Alternative Installation Methods

### Using Docker

Create a `Dockerfile`:

```dockerfile
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv \
    qemu-utils qemu-system-x86 \
    openssh-client rsync \
    libvirt-clients libvirt-daemon-system \
    git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN python3 -m pip install --no-cache-dir -r requirements.txt && \
    python3 -m pip install -e .

ENTRYPOINT ["python3", "-m", "h2kvm"]
```bash

Build and run:

```bash
docker build -t h2kvm .
docker run -it --rm --privileged \
  -v /path/to/input:/input \
  -v /path/to/output:/output \
  h2kvm local --vmdk /input/disk.vmdk --to-output /output/disk.qcow2
```bash

### Using Podman

Podman works the same as Docker:

```bash
podman build -t h2kvm .
podman run -it --rm --privileged \
  -v /path/to/input:/input:Z \
  -v /path/to/output:/output:Z \
  h2kvm local --vmdk /input/disk.vmdk --to-output /output/disk.qcow2
```bash

**Note:** The `:Z` suffix is required for SELinux systems (Fedora/RHEL).

### Using a Virtual Environment (Recommended for development)

This isolates h2kvm's dependencies from system Python:

```bash
# Create virtual environment
python3 -m venv ~/.venvs/h2kvm

# Activate it
source ~/.venvs/h2kvm/bin/activate

# Install
pip install -r requirements.txt
pip install -e .

# Use it
h2kvmctl --help

# Deactivate when done
deactivate
```bash

---

## Troubleshooting Installation

### "qemu-img: command not found"

**Problem:** QEMU not installed or not in PATH.

**Solution:**
```bash
# Fedora/RHEL
sudo dnf install qemu-img

# Ubuntu/Debian
sudo apt-get install qemu-utils

# Arch
sudo pacman -S qemu-img

# Verify
which qemu-img
qemu-img --version
```bash

### Python version too old

**Problem:** h2kvm requires Python 3.10+.

**Solution:**
```bash
# Check Python version
python3 --version

# Ubuntu: Use deadsnakes PPA for newer Python
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install python3.12 python3.12-venv

# Then use python3.12 explicitly
python3.12 -m venv .venv
```

# Re-enable SELinux
sudo setenforce 1

# Permanent fix: Use audit2allow to create policy
# (Advanced - consult SELinux documentation)
```bash

Or run in a container with `--privileged`.

---

### System Configuration

After installation, the system-wide configuration file is at `/etc/h2kvm/config.yaml`.

Key settings:
- `container_isolation: true` (default) -- runs LVM activation inside Podman/Docker for isolation
- `allowed_dirs` -- directories where VM images can be accessed
- `backend: guestkit` -- offline fix backend (guestkit is the fast default)

To disable container isolation:
```yaml
container_isolation: false
```
Or use the CLI flag: `--no-container-isolation`

---

## Running

After installation:

```bash
# module entrypoint
h2kvmctl --help

# or use the installed CLI (preferred)
h2kvmctl --help
```bash

Examples:

```bash
sudo h2kvmctl local --vmdk ./mtv-ubuntu22-4.vmdk --flatten --to-output ubuntu.qcow2 --compress
sudo h2kvmctl fetch-and-fix --host esxi.example.com --remote /vmfs/volumes/ds/vm/vm.vmdk --fetch-all --flatten --to-output vm.qcow2
sudo h2kvmctl live-fix --host 192.168.1.50 --sudo --print-fstab
```bash

---

## Developer install

### Run tests

```bash
# Install dependencies
python -m pip install -r requirements.txt
python -m pip install -e .

# Install test dependencies
pip install pytest pytest-cov pytest-xdist ruff mypy bandit

# Run unit tests
python -m pytest tests/unit/ -v

# Run with coverage
python -m pytest tests/unit/ --cov=h2kvm --cov-report=term-missing

# Run specific test file
python -m pytest tests/unit/test_core/test_utils.py -v

# Run linting
ruff check h2kvm/

# Run type checking
mypy h2kvm/ --ignore-missing-imports

# Run security scan
bandit -r h2kvm/
```bash

### Continuous Integration

Tests run automatically on GitHub Actions for every push and pull request:
- Unit tests on Python 3.10, 3.11, 3.12
- Code quality checks (ruff, mypy)
- Security scanning (Bandit, pip-audit)
- Documentation validation

See `.github/workflows/` for CI configuration.


