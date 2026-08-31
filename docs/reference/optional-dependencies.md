# Optional Dependencies

h2kvm is designed to work with minimal dependencies, making it suitable for enterprise Linux distributions like RHEL where some Python packages may not be available in official repositories.

## Installation Options

### Minimal Installation (RHEL/Enterprise Linux)

For systems where only official repositories are available:

```bash
pip install h2kvm
```

This installs only core dependencies:
- `click` - Command-line interface
- `pyyaml` - Configuration file support

**What works with minimal installation:**
- ✅ Local VMDK/VHD/QCOW2 conversion
- ✅ Offline guest OS fixes (using GuestKit via `hypersdk-guestkit`)
- ✅ All core migration functionality
- ❌ Progress bars (fallback to simple logging)
- ❌ vSphere integration (requires optional vsphere extras)
- ❌ Azure integration (requires optional azure extras)

### With UI Enhancements (Recommended)

Install with Rich library for better terminal UI:

```bash
pip install h2kvm[ui]
```

**Additional features:**
- ✅ Interactive progress bars
- ✅ Colored output
- ✅ Real-time transfer speed display

### With vSphere Support

For VMware vSphere/vCenter migrations:

```bash
pip install h2kvm[vsphere]
```

**Additional features:**
- ✅ Direct vSphere VM export
- ✅ VDDK disk downloads
- ✅ CBT (Changed Block Tracking)
- ✅ Snapshot management

**Note:** vSphere has a flexible architecture:
- **Primary (Recommended):** Use `govc` CLI tool (install separately, no Python deps needed)
- **Alternative:** Use `ovftool` CLI tool (install separately, no Python deps needed)
- **Fallback:** Use `pyvmomi` Python library (only if govc/ovftool not available)

If you have govc or ovftool installed, you don't need the `[vsphere]` extras!

### With Azure Support

For Microsoft Azure VM migrations:

```bash
pip install h2kvm[azure]
```

**Additional features:**
- ✅ Azure VM discovery and download
- ✅ Managed disk export (VHD/VHDX)
- ✅ Azure authentication (Service Principal, Managed Identity, Azure CLI)
- ✅ Snapshot management
- ✅ Resource group operations

**Note:** Azure has a flexible architecture:
- **Primary (Recommended):** Use Azure CLI (`az`) tool (install separately, no Python deps needed for auth)
- **Alternative:** Use Python SDK directly (included in `[azure]` extras)

If you have Azure CLI installed and authenticated (`az login`), h2kvm can use those credentials automatically without requiring the `[azure]` extras for authentication!

### With AWS Support

For AWS AMI/EBS extraction:

```bash
pip install h2kvm  # No extras needed - AMI extraction included in core
```

**Features:**
- ✅ AMI tarball extraction
- ✅ EBS snapshot extraction from AMI bundles
- ✅ Nested archive handling
- ✅ Automatic disk discovery

**Note:** Unlike Azure, AWS support is built-in for AMI extraction. Full AWS integration (EC2 instance export, snapshot downloads) is not yet implemented.

### Full Installation

Install all optional dependencies:

```bash
pip install h2kvm[full]
```

Or combine specific extras:

```bash
pip install h2kvm[ui,vsphere,azure]
```

## System Dependencies

h2kvm uses **GuestKit** (`hypersdk-guestkit>=1.1.0`) as the default guestfs backend.

### Required
- `qemu-img` - Disk format conversion (VMDK→QCOW2)
- `qemu-nbd` - NBD device access (included in `qemu-kvm-core` or `qemu-utils`)

### Recommended for Offline Fixes
- `dracut` - Initramfs regeneration (for boot fixes)
- `grub2-tools` - GRUB configuration updates
- `e2fsprogs`, `xfsprogs`, `btrfs-progs` - Filesystem tools
- `lvm2` - LVM support
- `cryptsetup` - LUKS encryption support

### Optional
- `libvirt` - For running smoke tests
- `govc` - **PRIMARY vSphere control plane (highly recommended for vSphere migrations)**
- `ovftool` - Alternative vSphere export method

## RHEL 10 Installation Example

```bash
# Install minimal system dependencies (all available in RHEL 10 base repos)
sudo dnf install -y \
    qemu-img \
    qemu-kvm-core \
    dracut \
    grub2-tools \
    e2fsprogs \
    xfsprogs \
    btrfs-progs \
    lvm2 \
    python3-pyyaml

# Install h2kvm (minimal - only click from PyPI)
pip install --user h2kvm

# Or with UI enhancements (requires rich from PyPI)
pip install --user h2kvm[ui]

# With vSphere support (requires pyvmomi from PyPI)
pip install --user h2kvm[vsphere]
```

### What's NOT in RHEL 10 Base Repos

The following packages require PyPI or external repos:

**UI Libraries:**
- `rich` - Progress bars and colored output (optional)

**Cloud/Virtualization SDKs:**
- `pyvmomi` - VMware vSphere SDK (OPTIONAL - only if not using govc/ovftool)
- `azure-identity`, `azure-mgmt-*`, `azure-storage-blob` - Azure SDK (only for Azure)
- `paramiko` - SSH client (only for SSH operations)

**Utility Libraries:**
- `click` - CLI framework (required, but small - from PyPI)
- `pycdlib` - ISO extraction (optional, can use system isoinfo instead)

**External CLI Tools (NOT Python packages):**
- `govc` - VMware govc CLI (primary control plane for vSphere) - install from binary
- `ovftool` - VMware OVF Tool (alternative for vSphere) - install from binary

All core migration functionality works with only system packages + click from PyPI.

## Behavior Without Rich

When Rich library is not available, h2kvm automatically falls back to:

### Progress Indicators
**With Rich:**
```
Flattening ━━━━━━━━━━━━━━━━━━━━ 45% 0:00:12 0:00:15
```

**Without Rich:**
```
20:03:02 INFO Flattening progress: 45.0%
```

### File Downloads
**With Rich:**
```
Downloading ━━━━━━━━━━━━━━━━━━ 512 MB/1 GB 150 MB/s
```

**Without Rich:**
```
20:03:05 INFO Download: 512 MB / 1024 MB (50%)
```

### Configuration Loading
**With Rich:**
```
Loading configs ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:01
```

**Without Rich:**
```
20:03:01 INFO Loading configuration files...
20:03:02 INFO Loaded 5 configuration files
```

## Checking What's Available

You can check which optional dependencies are installed:

```bash
python3 -c "from h2kvm.core.optional_imports import *; print(f'Rich: {RICH_AVAILABLE}, Requests: {REQUESTS_AVAILABLE}, PyVmomi: {PYVMOMI_AVAILABLE}')"
```

Or use the built-in diagnostic:

```bash
h2kvm --version --verbose
```

## Feature Matrix

| Feature | Minimal | +UI | +govc | +vSphere (pyvmomi) | +Azure | +Full |
|---------|---------|-----|-------|-------------------|--------|-------|
| Local disk conversion | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Offline guest fixes | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| AMI/EBS extraction | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Progress bars | ❌ | ✅ | ❌ | ✅ | ✅ | ✅ |
| vSphere export | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ |
| Azure VM export | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| HTTP downloads | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| **Python packages from PyPI** | click, pyyaml | +rich | **none** | +pyvmomi, requests | +azure-* | all |

**Notes:**
- The "+govc" column shows using the govc binary (no Python packages needed beyond minimal).
- AMI/EBS extraction is built into core - no extras needed.

## Troubleshooting

### Import Errors

If you see import errors for optional dependencies:

```python
ImportError: cannot import name 'Progress' from 'rich.progress'
```

This usually means:
1. You're using a feature that requires optional dependencies
2. Install the appropriate extras: `pip install h2kvm[ui]`

### RHEL/CentOS Compatibility

Rich is not available in RHEL 10 base repositories. Options:

1. **Use minimal installation** (recommended for production):
   ```bash
   pip install h2kvm  # Works without Rich
   ```

2. **Install Rich from PyPI** (if external packages allowed):
   ```bash
   pip install --user rich
   pip install --user h2kvm
   ```

3. **Build RPM with vendored dependencies** (for air-gapped systems):
   See `PACKAGING.md` for RPM build instructions.

## See Also

- [Installation Guide](01-Installation.md)
- [Configuration](02-Configuration.md)
- [Library API](08-Library-API.md)

## Complete Package Availability Matrix

### Available in RHEL 10 Base Repositories

| Package | RHEL Package Name | Purpose | Required |
|---------|-------------------|---------|----------|
| qemu-img | qemu-img | Disk conversion (VMDK→QCOW2) | ✅ Yes |
| qemu-kvm | qemu-kvm-core | NBD client (qemu-nbd) | ✅ Yes |
| PyYAML | python3-pyyaml | YAML config parsing | ✅ Yes |
| dracut | dracut | Initramfs regeneration | ⚡ Recommended |
| grub2-tools | grub2-tools | GRUB configuration | ⚡ Recommended |
| e2fsprogs | e2fsprogs | ext2/ext3/ext4 filesystem tools | ⚡ Recommended |
| xfsprogs | xfsprogs | XFS filesystem tools | ⚡ Recommended |
| lvm2 | lvm2 | LVM support | ⚡ Recommended |
| btrfs-progs | btrfs-progs | Btrfs filesystem tools | ⚡ Recommended |
| cryptsetup | cryptsetup | LUKS encryption support | ⚡ Recommended |
| requests | python3-requests | HTTP client | ⭕ Optional |
| urllib3 | python3-urllib3 | HTTP utilities | ⭕ Optional |

### NOT in RHEL 10 - Require PyPI

| Package | Purpose | When Needed | Install Extra |
|---------|---------|-------------|---------------|
| rich | Progress bars, UI | Optional (recommended) | `[ui]` |
| click | CLI framework | Always | Core dependency |
| pyvmomi | VMware vSphere SDK (fallback) | vSphere without govc/ovftool | `[vsphere]` |
| requests | HTTP client | vSphere/Azure | `[vsphere]` or `[azure]` |
| azure-identity | Azure auth | Azure migrations | `[azure]` |
| azure-mgmt-compute | Azure VM management | Azure migrations | `[azure]` |
| azure-mgmt-network | Azure network | Azure migrations | `[azure]` |
| azure-mgmt-resource | Azure resources | Azure migrations | `[azure]` |
| azure-storage-blob | Azure storage | Azure migrations | `[azure]` |
| paramiko | SSH client | SSH operations | Optional |
| pycdlib | ISO extraction | VirtIO ISO sources | Optional |

### External CLI Tools (NOT Python Packages)

These are installed separately as binaries, not via pip:

| Tool | Purpose | When Needed | Install Method |
|------|---------|-------------|----------------|
| **govc** | vSphere control plane (PRIMARY) | vSphere migrations (recommended) | Download binary from [GitHub releases](https://github.com/vmware/govmomi/releases) → /usr/local/bin |
| **ovftool** | OVF/OVA export/import | vSphere migrations (alternative) | Download ZIP from [Broadcom](https://developer.broadcom.com/tools/open-virtualization-format-ovf-tool/latest) (v5.0.0) |
| **az** (Azure CLI) | Azure authentication & operations | Azure migrations (recommended) | [Install via package manager](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) or dnf install azure-cli |
| libvirt | VM testing and validation | Optional smoke tests | dnf install libvirt |

### vSphere Architecture: Control Plane Options

h2kvm supports **three control plane options** for vSphere, in order of preference:

#### Option 1: govc (PRIMARY - Recommended)

```bash
# Download govc binary from GitHub releases
# Get latest version from: https://github.com/vmware/govmomi/releases
VERSION=v0.33.0
curl -L https://github.com/vmware/govmomi/releases/download/${VERSION}/govc_Linux_x86_64.tar.gz | \
  sudo tar -C /usr/local/bin -xvzf - govc

# Verify installation
govc version

# No pip install needed for vSphere!
pip install h2kvm  # Just core
```

**Advantages:**
- ✅ No Python dependencies
- ✅ Faster and more stable
- ✅ Official VMware open-source tool
- ✅ Works on RHEL without any PyPI packages
- ✅ Easy to update (just download new binary)

#### Option 2: ovftool (Alternative)

```bash
# Download OVF Tool from Broadcom (VMware) - requires free account
# URL: https://developer.broadcom.com/tools/open-virtualization-format-ovf-tool/latest
#
# Available downloads (version 5.0.0):
# - Linux Zip:   24.79 MB (MD5: f64f2f40581a28f08ac86fc94020d206)
# - macOS Zip:   19.77 MB (MD5: ea90568cdd08f90be22cac20b595b82a)
# - Windows Zip: 27.03 MB (MD5: 108af3416ff81dde6d9a6e9f477989bf)
# - Windows MSI: 28.77 MB (MD5: 4ae8ec7a24fa06048221d91a6aaeb492)

# Download "OVF Tool for Linux Zip" and verify checksum
md5sum ovftool-*.zip
# Should match: f64f2f40581a28f08ac86fc94020d206

# Extract and install
unzip ovftool-*.zip
sudo mv ovftool /usr/local/
sudo ln -sf /usr/local/ovftool/ovftool /usr/local/bin/ovftool

# Verify installation
ovftool --version
# Expected: VMware ovftool 5.0.0 (build-...)

# No pip install needed for vSphere!
pip install h2kvm  # Just core
```

**Advantages:**
- ✅ No Python dependencies
- ✅ Official VMware/Broadcom tool
- ✅ OVF/OVA export/import
- ✅ Advanced features (compression, validation)
- ✅ Latest version: 5.0.0
- ✅ Cross-platform (Linux, macOS, Windows)

#### Option 3: pyvmomi (Fallback)

```bash
# ONLY if you cannot install govc or ovftool
pip install h2kvm[vsphere]  # Includes pyvmomi
```

**When to use:**
- ❌ govc not available
- ❌ ovftool not available
- ✅ Need pure Python solution (air-gapped, restricted environments)

**Summary:** If you have govc or ovftool, skip the `[vsphere]` extra entirely!

### Azure Architecture: Authentication Options

h2kvm supports **two authentication options** for Azure, in order of preference:

#### Option 1: Azure CLI (PRIMARY - Recommended)

```bash
# Install Azure CLI
# For RHEL/Fedora:
sudo rpm --import https://packages.microsoft.com/keys/microsoft.asc
echo -e "[azure-cli]
name=Azure CLI
baseurl=https://packages.microsoft.com/yumrepos/azure-cli
enabled=1
gpgcheck=1
gpgkey=https://packages.microsoft.com/keys/microsoft.asc" | sudo tee /etc/yum.repos.d/azure-cli.repo
sudo dnf install -y azure-cli

# Or download directly:
# https://learn.microsoft.com/en-us/cli/azure/install-azure-cli

# Authenticate
az login

# Install h2kvm minimal (no [azure] extras needed for auth!)
pip install h2kvm
```

**Advantages:**
- ✅ No Python dependencies for authentication
- ✅ Official Microsoft tool
- ✅ Credentials shared with other Azure tools
- ✅ Supports all Azure auth methods (browser, device code, service principal)
- ✅ Automatic token refresh
- ✅ Works on RHEL without PyPI packages

**How it works:**
- h2kvm uses `DefaultAzureCredential` which checks for Azure CLI credentials first
- If `az login` was run, credentials are available at `~/.azure/`
- You still need `[azure]` extras for Azure SDK (VM operations), but NOT for authentication

#### Option 2: Python SDK Only (Fallback)

```bash
# ONLY if you cannot install Azure CLI
pip install h2kvm[azure]  # Includes all Azure SDKs
```

**When to use:**
- ❌ Azure CLI not available
- ✅ Need pure Python solution (air-gapped, restricted environments)
- ✅ Using Service Principal or Managed Identity directly in code

**Authentication methods available:**
- Environment variables (`AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`)
- Managed Identity (when running on Azure VMs)
- Interactive browser (fallback)

**Summary:** If you have Azure CLI installed and authenticated, you only need the `[azure]` extra for Azure SDK operations, not for authentication!

### Installation Strategy for RHEL 10

**Option 1: Minimal (Most Restrictive Environment)**
```bash
# System packages only (GuestKit backend)
sudo dnf install -y \
    qemu-img \
    qemu-kvm-core \
    dracut \
    grub2-tools \
    e2fsprogs \
    xfsprogs \
    lvm2 \
    python3-pyyaml

# Minimal pip install (only click)
pip install --user h2kvm

# Works for:
# ✅ Local VMDK/VHD/QCOW2 conversion
# ✅ All offline guest fixes (GuestKit backend)
# ✅ All core functionality
# ❌ No progress bars (logs instead)
# ❌ No vSphere direct integration
# ❌ No Azure integration
```

**Option 2: With UI (Recommended)**
```bash
# System packages (GuestKit backend)
sudo dnf install -y \
    qemu-img \
    qemu-kvm-core \
    dracut \
    grub2-tools \
    e2fsprogs \
    xfsprogs \
    lvm2 \
    python3-pyyaml

# With Rich for better UX
pip install --user h2kvm[ui]

# Adds:
# ✅ Interactive progress bars
# ✅ Colored output
# ✅ Real-time speed display
```

**Option 3: With vSphere (Using govc - Recommended)**
```bash
# Install govc binary from GitHub releases (no Python deps)
VERSION=v0.33.0
curl -L https://github.com/vmware/govmomi/releases/download/${VERSION}/govc_Linux_x86_64.tar.gz | \
  sudo tar -C /usr/local/bin -xvzf - govc

# Install h2kvm minimal
pip install --user h2kvm

# You're done! No [vsphere] extra needed with govc
```

**Option 3b: With vSphere (Using pyvmomi - Fallback)**
```bash
# ONLY if govc/ovftool not available
pip install --user h2kvm[vsphere]

# Adds:
# ✅ Direct vSphere VM export (via pyvmomi)
# ✅ VDDK support
# ✅ Snapshot management
# ✅ CBT (Changed Block Tracking)
```

**Option 3c: With Azure (Using Azure CLI - Recommended)**
```bash
# Install Azure CLI (from Microsoft repo)
sudo dnf install -y azure-cli

# Authenticate
az login

# Install h2kvm with Azure SDK
pip install --user h2kvm[azure]

# Adds:
# ✅ Azure VM discovery and export
# ✅ Managed disk download (VHD/VHDX)
# ✅ Snapshot operations
# ✅ Resource group management
# ✅ Authentication via Azure CLI (no extra config needed)
```

**Option 3d: With Azure (Python SDK only - Fallback)**
```bash
# ONLY if Azure CLI not available
pip install --user h2kvm[azure]

# Configure authentication via environment variables:
export AZURE_CLIENT_ID="your-client-id"
export AZURE_CLIENT_SECRET="your-client-secret"
export AZURE_TENANT_ID="your-tenant-id"
```

**Option 4: Full Featured**
```bash
# Everything including Azure
pip install --user h2kvm[full]
```

### Alternative: Using RPM Build

For air-gapped or strictly controlled RHEL environments, build an RPM with bundled dependencies:

```bash
# On build system (with internet)
git clone https://github.com/ssahani/h2kvm.git
cd h2kvm
make rpm  # or rpmbuild -ba h2kvm.spec

# Transfer RPM to target system
sudo dnf install ./h2kvm-*.rpm
```

The RPM includes all Python dependencies bundled, requiring only system packages like qemu-img and dracut.

### Checking Available Features

To see what features are available in your installation:

```bash
python3 << 'PYEOF'
from h2kvm.core.optional_imports import (
    RICH_AVAILABLE,
    REQUESTS_AVAILABLE, 
    PYVMOMI_AVAILABLE,
    PARAMIKO_AVAILABLE
)

print(f"""
h2kvm Feature Availability
==============================
✅ Core Migration: Always available
{'✅' if RICH_AVAILABLE else '❌'} Progress Bars: {RICH_AVAILABLE}
{'✅' if PYVMOMI_AVAILABLE else '❌'} vSphere Integration: {PYVMOMI_AVAILABLE}
{'✅' if REQUESTS_AVAILABLE else '❌'} HTTP Downloads: {REQUESTS_AVAILABLE}
{'✅' if PARAMIKO_AVAILABLE else '❌'} SSH Operations: {PARAMIKO_AVAILABLE}
""")
PYEOF
```

### Performance Impact

**Without Rich (minimal install):**
- No performance impact on actual migration
- Slightly less frequent progress updates (every 2-5% vs real-time)
- No visual overhead from terminal rendering

**With Rich:**
- Real-time progress bars (~60 FPS updates)
- Colored output
- Minimal CPU overhead (<0.1%)
