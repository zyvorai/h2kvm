#!/usr/bin/env bash
# setup-almalinux.sh — Set up hyper2kvm on AlmaLinux 9 / RHEL 9
#
# Installs all required packages for:
#   - VM conversion (qemu-img, qemu-nbd, libguestfs)
#   - Libvirt (KVM host)
#   - Windows migration (ntfs-3g, hivex)
#   - KubeVirt deployment (k3s, virtctl)
#   - Remote console (noVNC)
#
# Usage:
#   curl -sL <url> | bash
#   ./setup-almalinux.sh [--with-k3s] [--with-novnc]

set -euo pipefail

banner()  { echo ""; echo "━━━ 🔧 $* ━━━"; }
info()    { echo "✅ $*"; }
warn()    { echo "⚠️  $*"; }
die()     { echo "❌ $*" >&2; exit 1; }

usage() {
    cat <<EOF
Usage: $0 [options]

Set up hyper2kvm on AlmaLinux 9 / RHEL 9.

Options:
  --with-k3s     Install K3s + KubeVirt + CDI + virtctl
  --with-novnc   Install noVNC web console
  --all          Install everything (K3s + noVNC)
  --help, -h     Show this help message

Examples:
  sudo $0                    # Base install only
  sudo $0 --with-k3s        # Base + Kubernetes
  sudo $0 --all             # Everything
EOF
    exit 0
}

WITH_K3S=false
WITH_NOVNC=false
for arg in "$@"; do
    case "$arg" in
        --help|-h)    usage ;;
        --with-k3s)   WITH_K3S=true ;;
        --with-novnc) WITH_NOVNC=true ;;
        --all)        WITH_K3S=true; WITH_NOVNC=true ;;
    esac
done

[[ "$(id -u)" -eq 0 ]] || die "This script must be run as root: sudo $0 $*"

# ── 1. Enable repos ──────────────────────────────────────────────────────
banner "Enable EPEL + CRB repos"
dnf install -y epel-release
/usr/bin/crb enable
info "Repos enabled"

# ── 2. Core packages ─────────────────────────────────────────────────────
banner "Install core packages"
dnf install -y \
    qemu-kvm qemu-img \
    libvirt virt-install \
    libguestfs libguestfs-tools python3-libguestfs guestfs-tools \
    git python3-pip rsync wget curl \
    p7zip p7zip-plugins \
    nbdkit

info "Core packages installed"

# ── 3. Python 3.11 (hyper2kvm needs >= 3.10) ─────────────────────────────
banner "Install Python 3.11"
dnf install -y python3.11 python3.11-pip python3.11-devel
info "Python 3.11 installed"

# ── 4. Windows migration tools + VirtIO drivers ─────────────────────────
banner "Install Windows migration tools"
dnf install -y ntfsprogs ntfs-3g hivex python3-hivex
info "NTFS + hivex installed"

# Runtime directory (NBD locking, daemon sockets)
mkdir -p /run/hyper2kvm
info "Runtime dir: /run/hyper2kvm"

# VirtIO Windows drivers — download + pre-extract
iso="/var/lib/hyper2kvm/virtio-win.iso"
cache="/var/lib/hyper2kvm/virtio-win-extracted"
if [ -f "$iso" ]; then
    info "virtio-win.iso: $iso"
else
    mkdir -p /var/lib/hyper2kvm
    info "Downloading virtio-win.iso..."
    curl -fSL "https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso" \
        -o "$iso" && info "virtio-win.iso installed" || \
        warn "Download failed — Windows VirtIO migration will use SATA fallback"
fi

# Pre-extract ISO for faster Windows migrations
if [ -d "$cache/viostor" ]; then
    info "VirtIO ISO cache: $cache (already extracted)"
elif command -v bsdtar &>/dev/null && [ -f "$iso" ]; then
    info "Pre-extracting VirtIO ISO..."
    rm -rf "$cache"
    mkdir -p "$cache"
    bsdtar xf "$iso" -C "$cache" 2>/dev/null || true
    if [ -d "$cache/viostor" ]; then
        stat -c %Y "$iso" > "$cache/.iso_mtime"
        info "VirtIO ISO extracted: $cache"
    else
        warn "bsdtar extraction incomplete — hyper2kvm will extract on first Windows migration"
    fi
fi

# ── 5. Start libvirtd ────────────────────────────────────────────────────
banner "Enable libvirtd"
systemctl enable --now libvirtd
virsh net-start default 2>/dev/null || true
virsh net-autostart default 2>/dev/null || true
info "Libvirtd running, default network active"

# ── 6. Install hyper2kvm ─────────────────────────────────────────────────
banner "Install hyper2kvm"
if [[ -d /opt/hyper2kvm ]]; then
    info "hyper2kvm already at /opt/hyper2kvm"
    cd /opt/hyper2kvm && python3.11 -m pip install -e . 2>&1 | tail -3
else
    warn "/opt/hyper2kvm not found — clone repo first:"
    echo "  git clone https://github.com/ssahani/hyper2kvm /opt/hyper2kvm"
    echo "  cd /opt/hyper2kvm && python3.11 -m pip install -e ."
fi

# ── 7. K3s + KubeVirt (optional) ─────────────────────────────────────────
if $WITH_K3S; then
    banner "Install K3s"
    if which kubectl &>/dev/null && kubectl get nodes &>/dev/null 2>&1; then
        info "K3s already running"
    else
        curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--disable traefik" sh -
        info "K3s installed"
    fi

    # Wait for K3s to be ready
    for i in $(seq 1 12); do
        kubectl get nodes &>/dev/null 2>&1 && break
        sleep 5
    done

    banner "Install KubeVirt"
    KUBEVIRT_VERSION=$(curl -s https://api.github.com/repos/kubevirt/kubevirt/releases/latest | grep tag_name | cut -d'"' -f4)
    kubectl create -f "https://github.com/kubevirt/kubevirt/releases/download/${KUBEVIRT_VERSION}/kubevirt-operator.yaml" 2>/dev/null || true
    kubectl create -f "https://github.com/kubevirt/kubevirt/releases/download/${KUBEVIRT_VERSION}/kubevirt-cr.yaml" 2>/dev/null || true
    info "KubeVirt $KUBEVIRT_VERSION deploying..."

    # Install virtctl
    curl -sL -o /usr/local/bin/virtctl "https://github.com/kubevirt/kubevirt/releases/download/${KUBEVIRT_VERSION}/virtctl-${KUBEVIRT_VERSION}-linux-amd64"
    chmod +x /usr/local/bin/virtctl
    virtctl version --client >/dev/null 2>&1 || { echo "ERROR: virtctl download failed or binary is corrupt"; exit 1; }
    info "virtctl installed"

    # Install kubernetes Python package
    python3.11 -m pip install kubernetes 2>&1 | tail -3
    info "kubernetes Python package installed"
fi

# ── 8. noVNC (optional) ──────────────────────────────────────────────────
if $WITH_NOVNC; then
    banner "Install noVNC"
    dnf install -y novnc python3-websockify
    firewall-cmd --add-port=6080/tcp --permanent 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
    info "noVNC installed (start with: websockify --web /usr/share/novnc/ 6080 127.0.0.1:5900)"
fi

# ── 9. Verify ────────────────────────────────────────────────────────────
banner "Verification"
echo ""
printf "  %-25s %s\n" "QEMU:" "$(qemu-img --version | head -1)"
printf "  %-25s %s\n" "Libvirt:" "$(virsh version --daemon 2>/dev/null | grep 'Running hypervisor' || echo 'active')"
printf "  %-25s %s\n" "Python:" "$(python3.11 --version)"
printf "  %-25s %s\n" "h2kvmctl:" "$(h2kvmctl --version 2>/dev/null || echo 'not installed yet')"
printf "  %-25s %s\n" "KVM:" "$(lsmod | grep -q kvm && echo 'loaded' || echo 'not loaded')"
printf "  %-25s %s\n" "Default network:" "$(virsh net-list | grep -q default && echo 'active' || echo 'inactive')"
if $WITH_K3S; then
    printf "  %-25s %s\n" "K3s:" "$(kubectl get nodes -o jsonpath='{.items[0].status.nodeInfo.kubeletVersion}' 2>/dev/null || echo 'not ready')"
    printf "  %-25s %s\n" "KubeVirt:" "$(kubectl get kubevirt kubevirt -n kubevirt -o jsonpath='{.status.observedKubeVirtVersion}' 2>/dev/null || echo 'deploying...')"
fi
echo ""

info "Setup complete! Run migrations with:"
echo "  run-demo.sh <vmdk-path>           # Libvirt"
echo "  demo-k3s.sh <vmdk-path> <name>    # KubeVirt"
echo "  vm-ips.sh                          # Show running VMs"
