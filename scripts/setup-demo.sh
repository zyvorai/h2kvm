#!/bin/bash
set -euo pipefail
# ============================================
# hyper2kvm Demo Setup
# ============================================
# Sets up a remote/baremetal machine for demonstrating
# VMware → KVM migration with visible results.
#
# Installs:
#   - All hyper2kvm dependencies
#   - Cockpit web UI (port 9090) for viewing VMs
#   - VNC tools for console access
#
# Usage:
#   sudo ./scripts/setup-demo.sh
#
# After setup:
#   1. Access Cockpit: https://<machine-ip>:9090
#   2. Run a migration: sudo h2kvmctl --config govc-to-libvirt.yaml
#   3. See the VM running in Cockpit → Virtual Machines
# ============================================





info()  { echo -e "[INFO] $*"; }
warn()  { echo -e "[WARN] $*"; }
error() { echo -e "[ERROR] $*"; }

if [ "$(id -u)" -ne 0 ]; then
    error "Run as root: sudo $0"
    exit 1
fi

# Detect distro
if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO_ID="${ID}"
else
    error "Cannot detect distribution"
    exit 1
fi

info "Setting up demo on $DISTRO_ID..."

# ── Step 1: Install all hyper2kvm dependencies ──
info "Step 1/4: Installing hyper2kvm and dependencies..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$SCRIPT_DIR/quickstart.sh"

# ── Step 2: Install Cockpit web UI ──
info "Step 2/4: Installing Cockpit web UI..."
case "$DISTRO_ID" in
    fedora|rhel|centos|rocky|almalinux)
        dnf install -y cockpit cockpit-machines 2>/dev/null || true
        ;;
    ubuntu|debian|pop)
        apt-get update -qq && apt-get install -y -qq cockpit cockpit-machines 2>/dev/null || true
        ;;
    opensuse*|sles)
        zypper install -y cockpit cockpit-machines 2>/dev/null || true
        ;;
esac
systemctl enable --now cockpit.socket 2>/dev/null || true

# ── Step 3: Install VNC tools ──
info "Step 3/4: Installing VNC tools..."
case "$DISTRO_ID" in
    fedora|rhel|centos|rocky|almalinux)
        dnf install -y tigervnc 2>/dev/null || true
        ;;
    ubuntu|debian|pop)
        apt-get install -y -qq tigervnc-viewer 2>/dev/null || true
        ;;
    opensuse*|sles)
        zypper install -y tigervnc 2>/dev/null || true
        ;;
esac

# ── Step 4: Enable and start libvirt ──
info "Step 4/4: Enabling libvirt..."
systemctl enable --now libvirtd 2>/dev/null || true

# Ensure default network is active
virsh net-start default 2>/dev/null || true
virsh net-autostart default 2>/dev/null || true

# ── Open firewall ports ──
if command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-service=ssh 2>/dev/null || true
    firewall-cmd --permanent --add-service=cockpit 2>/dev/null || true
    firewall-cmd --permanent --add-service=libvirt 2>/dev/null || true
    firewall-cmd --permanent --add-port=5900-5999/tcp 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
    info "Firewall: SSH, Cockpit, libvirt, VNC opened"
elif command -v ufw &>/dev/null; then
    ufw allow ssh 2>/dev/null || true
    ufw allow 9090/tcp 2>/dev/null || true
    ufw allow 16509/tcp 2>/dev/null || true
    ufw allow 5900:5999/tcp 2>/dev/null || true
    info "Firewall: SSH, Cockpit, libvirt, VNC opened"
fi

# ── Verify ──
info "=== Demo Setup Complete ==="
"$SCRIPT_DIR/doctor.sh"

MACHINE_IP=$(hostname -I 2>/dev/null | awk '{print $1}')

echo ""
info "=== How to Demo ==="
echo ""
echo "  1. Cockpit Web UI (see VMs running):"
echo "     https://${MACHINE_IP:-<machine-ip>}:9090"
echo "     Login with your system credentials"
echo ""
echo "  2. Run a local migration (fast, uses photon.vmdk):"
echo "     sudo h2kvmctl --config photon-to-libvirt.yaml"
echo ""
echo "  3. Run a vCenter migration (govc export → libvirt):"
echo "     sudo h2kvmctl --config govc-to-libvirt.yaml"
echo ""
echo "  4. Check running VMs:"
echo "     virsh list"
echo ""
echo "  5. Connect to VM console:"
echo "     virsh console <vm-name>"
echo "     # Or VNC: vncviewer localhost:\$(virsh vncdisplay <vm-name>)"
echo ""
