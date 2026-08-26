#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# hyper2kvm doctor — system readiness check
#
# Usage: ./scripts/doctor.sh
#   or:  h2kvmctl doctor (if wired into CLI)
#
# Checks everything needed for VM migration:
#   KVM, qemu-img, libvirt, govc, Python, disk space, permissions

set -euo pipefail

usage() {
    cat <<EOF
Usage: $0 [options]

Check system readiness for hyper2kvm VM migrations.

Checks: KVM, qemu-img, libvirt, govc, Python, disk space, permissions.

Options:
  --help, -h     Show this help message

Examples:
  $0              # Run all checks
  sudo $0         # Run all checks (some need root for full info)
EOF
    exit 0
}

[[ "${1:-}" == "--help" || "${1:-}" == "-h" ]] && usage

G='\033[1;32m'  # green (pass)
R='\033[1;31m'  # red (fail)
Y='\033[1;33m'  # yellow (warn)
C='\033[1;36m'  # cyan (info)
W='\033[1;37m'  # white
N='\033[0m'     # reset

PASS=0
WARN=0
FAIL=0

pass()  { echo -e "  ${G}✓${N} $1"; PASS=$((PASS+1)); }
warn()  { echo -e "  ${Y}⚠${N} $1"; WARN=$((WARN+1)); }
fail()  { echo -e "  ${R}✗${N} $1"; FAIL=$((FAIL+1)); }
info()  { echo -e "  ${C}ℹ${N} $1"; }
header(){ echo -e "\n${W}━━━ $1 ━━━${N}"; }

echo -e "${W}"
echo "  hyper2kvm doctor"
echo "  System readiness check"
echo -e "${N}"

# --- SECTION 1: Virtualization ---
header "Virtualization"

if grep -qE '(vmx|svm)' /proc/cpuinfo 2>/dev/null; then
    pass "CPU virtualization extensions (vmx/svm) available"
else
    fail "CPU virtualization extensions NOT found — KVM won't work"
    info "Enable VT-x/AMD-V in BIOS, or check nested virt if in a VM"
fi

if lsmod | grep -q '^kvm' 2>/dev/null; then
    pass "KVM kernel module loaded"
else
    warn "KVM module not loaded — try: sudo modprobe kvm_intel (or kvm_amd)"
fi

if [ -e /dev/kvm ]; then
    pass "/dev/kvm exists"
    if [ -w /dev/kvm ] || [ "$(id -u)" = "0" ]; then
        pass "/dev/kvm is accessible"
    else
        warn "/dev/kvm not writable — add user to 'kvm' group or run as root"
    fi
else
    fail "/dev/kvm does not exist — KVM not available"
fi

# --- SECTION 2: Required Tools ---
header "Required Tools"

for tool in qemu-img qemu-nbd python3 pip3; do
    if command -v "$tool" &>/dev/null; then
        ver=$($tool --version 2>&1 | head -1 | grep -oE '[0-9]+\.[0-9]+[.0-9]*' | head -1)
        pass "$tool ${ver:+($ver)}"
    else
        fail "$tool not found — install it"
    fi
done

if command -v h2kvmctl &>/dev/null; then
    ver=$(h2kvmctl --version 2>&1 | grep -oE '[0-9]+\.[0-9]+[.0-9]*' | head -1)
    pass "h2kvmctl ${ver:+($ver)}"
else
    fail "h2kvmctl not found — install: pip install -e . (from repo root)"
fi

# --- SECTION 3: Optional Tools ---
header "Optional Tools"

for tool in govc virsh virtctl; do
    if command -v "$tool" &>/dev/null; then
        ver=$(timeout 5 "$tool" version 2>&1 | head -1 | grep -oE '[0-9]+\.[0-9]+[.0-9]*' | head -1)
        pass "$tool ${ver:+($ver)}"
    else
        warn "$tool not found (optional)"
    fi
done
if command -v virt-inspector &>/dev/null; then
    pass "virt-inspector"
else
    warn "virt-inspector not found (optional — for boot mode detection)"
fi
# Binary is often in /usr/sbin; non-login shells may omit that from PATH.
_vff=""
for _p in /usr/bin/virt-filesystems /usr/sbin/virt-filesystems; do
    [ -x "$_p" ] && _vff=$_p && break
done
[ -z "$_vff" ] && _vff=$(PATH="${PATH:+$PATH:}/usr/sbin:/sbin" command -v virt-filesystems 2>/dev/null || true)
if [ -n "$_vff" ]; then
    pass "virt-filesystems @ $_vff (libguestfs-tools)"
else
    warn "virt-filesystems not found — install libguestfs-tools (dnf/apt: libguestfs-tools); full deploy installs it, --quick/pip-only does not"
fi
if command -v ntfs-3g &>/dev/null || command -v mount.ntfs-3g &>/dev/null; then
    pass "ntfs-3g (Windows NTFS mount — offline fixes / VirtIO staging)"
else
    warn "ntfs-3g not found — required for Windows NTFS offline work (dnf install ntfs-3g ntfsprogs; apt install ntfs-3g)"
fi
if command -v ntfsfix &>/dev/null; then
    pass "ntfsfix (dirty NTFS journal repair before mount)"
else
    warn "ntfsfix not found — install ntfsprogs (RPM) or ntfs-3g (Debian/Ubuntu) for unclean Windows disks"
fi
if command -v hivexget &>/dev/null; then
    pass "hivexget (hivex RPM — CLI registry probes)"
else
    warn "hivexget not found — install hivex (dnf install hivex; apt install hivex)"
fi
if command -v python3.12 &>/dev/null; then
    if python3.12 -c "import hivex" 2>/dev/null; then
        pass "python3.12 imports hivex (matches typical pip-installed h2kvmctl)"
    else
        warn "python3.12 cannot import hivex — install python3.12-hivex on EL9, or use OS python3 + python3-hivex for h2kvmctl"
    fi
fi
if command -v supermin &>/dev/null; then
    pass "supermin (libguestfs appliance builder)"
else
    warn "supermin not found — required for libguestfs/LVM/LUKS backend (dnf install supermin; apt install supermin)"
fi
if command -v libguestfs-test-tool &>/dev/null; then
    pass "libguestfs-test-tool present (run it if supermin/LVM diagnosis needed)"
else
    info "libguestfs-test-tool not in PATH (install libguestfs-tools — optional appliance check)"
fi

if command -v mkosi &>/dev/null; then
    ver=$(mkosi --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+' | head -1)
    pass "mkosi ${ver:+($ver)}"
else
    warn "mkosi not found (optional — for appliance VM builder)"
    info "Install: pip3 install git+https://github.com/systemd/mkosi.git"
fi

# h2kweb (web dashboard)
if command -v h2kweb &>/dev/null; then
    pass "h2kweb ($(h2kweb --version 2>/dev/null || echo 'installed'))"
    if systemctl is-active h2kweb &>/dev/null; then
        port=$(grep H2KWEB_ADDR /etc/default/h2kweb 2>/dev/null | cut -d: -f2 || echo "5070")
        pass "h2kweb service running (port ${port:-5070})"
    else
        warn "h2kweb service not running (start: systemctl start h2kweb)"
    fi
else
    warn "h2kweb not found (optional — web dashboard, install: cd web && make install)"
fi

# zkvm (terminal UI)
if command -v zkvm &>/dev/null; then
    pass "zkvm (terminal UI)"
else
    warn "zkvm not found (optional — terminal UI, build: cd zkvm && go build)"
fi

if command -v kubectl &>/dev/null; then
    ver=$(timeout 5 kubectl version --client 2>/dev/null | grep -oE '[0-9]+\.[0-9]+[.0-9]*' | head -1)
    pass "kubectl ${ver:+($ver)}"
    if timeout 5 kubectl cluster-info &>/dev/null 2>&1; then
        pass "Kubernetes cluster reachable"
        if timeout 5 kubectl get crd virtualmachines.kubevirt.io &>/dev/null 2>&1; then
            pass "KubeVirt CRDs found"
        else
            warn "KubeVirt not installed on cluster"
        fi
    else
        warn "Kubernetes cluster not reachable"
    fi
else
    warn "kubectl not found (optional — needed for KubeVirt)"
fi

# --- SECTION 4: Libvirt ---
header "Libvirt"

if command -v virsh &>/dev/null; then
    if timeout 5 virsh uri &>/dev/null 2>&1; then
        pass "libvirt connection OK ($(timeout 5 virsh uri 2>/dev/null))"
    elif timeout 5 sudo virsh uri &>/dev/null 2>&1; then
        pass "libvirt connection OK with sudo ($(timeout 5 sudo virsh uri 2>/dev/null))"
    else
        warn "libvirt not responding — is libvirtd running?"
    fi

    if timeout 5 virsh net-info default &>/dev/null 2>&1 || timeout 5 sudo virsh net-info default &>/dev/null 2>&1; then
        pass "Default network available"
    else
        warn "No 'default' network — VMs may lack connectivity"
        info "Fix: sudo virsh net-start default"
    fi
else
    warn "virsh not found — libvirt not installed"
fi

# --- SECTION 4b: VirtIO Windows Drivers ---
header "VirtIO Windows Drivers"

if [ -f /var/lib/hyper2kvm/virtio-win.iso ]; then
    pass "virtio-win.iso: /var/lib/hyper2kvm/virtio-win.iso ($(du -h /var/lib/hyper2kvm/virtio-win.iso | awk '{print $1}'))"
elif [ -f /usr/share/virtio-win/virtio-win.iso ]; then
    pass "virtio-win.iso: /usr/share/virtio-win/virtio-win.iso (RPM, $(du -h /usr/share/virtio-win/virtio-win.iso | awk '{print $1}'))"
else
    warn "virtio-win.iso not found — Windows migrations will use SATA/e1000 fallback"
    info "Install: sudo dnf install virtio-win  OR  sudo ./scripts/install-deps.sh --virtio-win"
fi

if [ -d /var/lib/hyper2kvm/virtio-win-extracted/viostor ]; then
    pass "VirtIO ISO cache: /var/lib/hyper2kvm/virtio-win-extracted/ (pre-extracted)"
elif [ -f /var/lib/hyper2kvm/virtio-win.iso ]; then
    info "VirtIO ISO cache not yet extracted — will be created on first Windows migration"
fi

# --- SECTION 4c: Windows Registry + AWS Support ---
header "Windows Registry & Cloud Providers"

if timeout 5 python3 -c "import hivex" 2>/dev/null; then
    pass "python3-hivex available (Windows registry access)"
else
    warn "python3-hivex not installed — Windows RDP/firewall/network checks limited"
    info "Install: sudo dnf install python3-hivex  (or apt install python3-hivex)"
fi

if command -v bsdtar &>/dev/null; then
    pass "bsdtar available (Rock Ridge ISO extraction)"
else
    warn "bsdtar not installed — VirtIO ISO extraction will fall back to pycdlib"
    info "Install: sudo dnf install bsdtar  (or apt install libarchive-tools)"
fi

if timeout 5 python3 -c "import boto3" 2>/dev/null; then
    pass "boto3 available (AWS EC2 provider)"
else
    info "boto3 not installed — AWS EC2 provider not available (optional)"
    info "Install: pip3 install boto3"
fi

# --- SECTION 5: Kernel Modules ---
header "Kernel Modules"

for mod in nbd vhost_net; do
    if lsmod | grep -q "^${mod}" 2>/dev/null; then
        pass "$mod module loaded"
    else
        warn "$mod module not loaded — try: sudo modprobe $mod"
    fi
done

# --- SECTION 6: Disk Space ---
header "Disk Space"

avail_tmp=$(df -BG /tmp 2>/dev/null | tail -1 | awk '{print $4}' | tr -d 'G')
avail_home=$(df -BG "$HOME" 2>/dev/null | tail -1 | awk '{print $4}' | tr -d 'G')

if [ "${avail_tmp:-0}" -ge 10 ]; then
    pass "/tmp has ${avail_tmp}G free"
else
    warn "/tmp only has ${avail_tmp:-?}G free — need 10G+ for conversion"
fi

if [ "${avail_home:-0}" -ge 20 ]; then
    pass "$HOME has ${avail_home}G free"
else
    warn "$HOME only has ${avail_home:-?}G free — need 20G+ for output"
fi

# --- SECTION 7: Python Packages ---
header "Python Packages"

if python3 -c "import guestfs" 2>/dev/null; then
    pass "python3-libguestfs (recommended — auto-used for LVM/LUKS)"
else
    warn "python3-libguestfs not installed — install for LVM/LUKS support"
    info "Install: sudo dnf install python3-libguestfs  (or apt: python3-guestfs)"
fi

for pkg in pyvmomi libvirt-python; do
    # Map package names to Python import names
    case "$pkg" in
        pyvmomi)        mod="pyVmomi" ;;
        libvirt-python) mod="libvirt" ;;
        *)              mod=$(echo "$pkg" | tr '-' '_') ;;
    esac
    if python3 -c "import $mod" 2>/dev/null; then
        pass "$pkg installed"
    else
        warn "$pkg not installed (optional)"
    fi
done

if python3 -c "import hyper2kvm" 2>/dev/null; then
    pass "hyper2kvm Python package importable"
else
    fail "hyper2kvm Python package not importable"
fi

# --- SECTION 8: vSphere Connectivity ---
header "vSphere (optional)"

if [ -n "${GOVC_URL:-}" ]; then
    pass "GOVC_URL set: ${GOVC_URL}"
    [ -n "${GOVC_USERNAME:-}" ] && pass "GOVC_USERNAME set" || warn "GOVC_USERNAME not set"
    [ -n "${GOVC_PASSWORD:-}" ] && pass "GOVC_PASSWORD set" || warn "GOVC_PASSWORD not set"
    [ -n "${GOVC_DATACENTER:-}" ] && pass "GOVC_DATACENTER set: ${GOVC_DATACENTER}" || warn "GOVC_DATACENTER not set"

    if command -v govc &>/dev/null && timeout 10 govc about &>/dev/null 2>&1; then
        pass "vCenter connection OK"
        vm_count=$(timeout 15 govc ls "/${GOVC_DATACENTER:-ha-datacenter}/vm/" 2>/dev/null | wc -l)
        info "Found $vm_count VMs"
    else
        warn "Cannot connect to vCenter (timeout or unreachable)"
    fi
else
    info "GOVC_URL not set — vSphere features disabled"
    info "Set: export GOVC_URL=https://vcenter/sdk"
fi

# --- SECTION 9: zkvm TUI ---
header "zkvm TUI"

if [ -f "zkvm/zkvm" ]; then
    pass "zkvm binary found: zkvm/zkvm"
elif command -v zkvm &>/dev/null; then
    pass "zkvm installed: $(which zkvm)"
else
    warn "zkvm not built — run: cd zkvm && go build -o zkvm ."
fi

if command -v go &>/dev/null; then
    ver=$(go version | grep -oE '[0-9]+\.[0-9]+[.0-9]*' | head -1)
    pass "Go compiler ($ver)"
else
    warn "Go not installed — needed to build zkvm TUI"
fi

# --- SUMMARY ---
echo
echo -e "${W}━━━ Summary ━━━${N}"
echo
echo -e "  ${G}✓ $PASS passed${N}"
[ $WARN -gt 0 ] && echo -e "  ${Y}⚠ $WARN warnings${N}"
[ $FAIL -gt 0 ] && echo -e "  ${R}✗ $FAIL failed${N}"
echo

if [ $FAIL -eq 0 ] && [ $WARN -eq 0 ]; then
    echo -e "  ${G}All checks passed — ready to migrate!${N}"
elif [ $FAIL -eq 0 ]; then
    echo -e "  ${Y}Ready with warnings — core features work, optional tools missing${N}"
else
    echo -e "  ${R}Issues found — fix failures before migrating${N}"
fi
echo

exit $FAIL
