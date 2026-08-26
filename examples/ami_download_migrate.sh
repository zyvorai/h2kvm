#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# ============================================================================
# AMI Download & Migrate Demo
# ============================================================================
# Downloads a public cloud AMI image, migrates it to KVM with offline fixes,
# and boots it on libvirt. Works without AWS credentials.
#
# Usage:
#   sudo ./examples/ami_download_migrate.sh                    # Photon OS 5.0
#   sudo ./examples/ami_download_migrate.sh --ubuntu           # Ubuntu 24.04
#   sudo ./examples/ami_download_migrate.sh --fedora           # Fedora Cloud
#   sudo ./examples/ami_download_migrate.sh --keep             # Keep VM running
#   sudo ./examples/ami_download_migrate.sh --cleanup          # Remove demo VMs
# ============================================================================

set -euo pipefail

info()  { echo -e "\033[32m[OK]\033[0m $*"; }
warn()  { echo -e "\033[33m[!!]\033[0m $*"; }
error() { echo -e "\033[31m[ERR]\033[0m $*"; }
step()  { echo -e "\n\033[1m>>> $*\033[0m"; }

OUTDIR="./out/ami-demo"
KEEP_VM=false
IMAGE="photon"

# Parse args
for arg in "$@"; do
    case "$arg" in
        --photon)  IMAGE="photon" ;;
        --ubuntu)  IMAGE="ubuntu" ;;
        --fedora)  IMAGE="fedora" ;;
        --keep)    KEEP_VM=true ;;
        --cleanup)
            echo "Cleaning up AMI demo VMs..."
            for name in ami-demo-photon ami-demo-ubuntu ami-demo-fedora; do
                virsh destroy "$name" 2>/dev/null || true
                virsh undefine "$name" --nvram 2>/dev/null || true
            done
            rm -rf "$OUTDIR"
            info "Cleaned up"
            exit 0
            ;;
        --help|-h)
            head -16 "$0" | tail -12
            exit 0
            ;;
    esac
done

if [ "$(id -u)" -ne 0 ]; then
    error "Run as root: sudo $0 $*"
    exit 1
fi

# Check deps
for tool in h2kvmctl qemu-img virsh; do
    command -v "$tool" &>/dev/null || { error "$tool not found — run: sudo ./scripts/quickstart.sh"; exit 1; }
done

mkdir -p "$OUTDIR"

# ── Download ──
step "Step 1/4: Downloading $IMAGE AMI"

case "$IMAGE" in
    photon)
        VM_NAME="ami-demo-photon"
        URL="https://packages.vmware.com/photon/5.0/GA/ami/photon-ami-5.0-dde71ec57.x86_64.tar.gz"
        TARBALL="$OUTDIR/photon-ami.tar.gz"
        RAW_DISK="$OUTDIR/photon-ami-5.0-dde71ec57.x86_64.raw"
        if [ ! -f "$RAW_DISK" ]; then
            if [ ! -f "$TARBALL" ]; then
                info "Downloading Photon OS 5.0 AMI (~310MB)..."
                curl -fSL -o "$TARBALL" "$URL"
            fi
            info "Extracting..."
            tar xzf "$TARBALL" -C "$OUTDIR"
        fi
        DISK="$RAW_DISK"
        ;;
    ubuntu)
        VM_NAME="ami-demo-ubuntu"
        URL="https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img"
        DISK="$OUTDIR/ubuntu-noble.img"
        if [ ! -f "$DISK" ]; then
            info "Downloading Ubuntu 24.04 Cloud Image (~600MB)..."
            curl -fSL -o "$DISK" "$URL"
        fi
        ;;
    fedora)
        VM_NAME="ami-demo-fedora"
        URL="https://download.fedoraproject.org/pub/fedora/linux/releases/41/Cloud/x86_64/images/Fedora-Cloud-Base-Generic-41-1.4.x86_64.qcow2"
        DISK="$OUTDIR/fedora-cloud.qcow2"
        if [ ! -f "$DISK" ]; then
            info "Downloading Fedora 41 Cloud Image (~400MB)..."
            curl -fSL -o "$DISK" "$URL"
        fi
        ;;
esac

info "Source: $DISK ($(du -h "$DISK" | awk '{print $1}'))"

# ── Remove existing VM ──
virsh destroy "$VM_NAME" 2>/dev/null || true
virsh undefine "$VM_NAME" --nvram 2>/dev/null || true

# ── Migrate ──
step "Step 2/4: Migrating with h2kvmctl"

h2kvmctl \
    --cmd local \
    --vmdk "$DISK" \
    --output-dir "$OUTDIR" \
    --to-output "${VM_NAME}.qcow2" \
    --out-format qcow2 \
    --compress \
    --fstab-mode stabilize-all \
    --regen-initramfs \
    --emit-domain-xml \
    --vm-name "$VM_NAME" \
    --memory 2048 \
    --vcpus 2 \
    --headless

# ── Deploy ──
step "Step 3/4: Deploying to libvirt"

XML="$OUTDIR/libvirt/${VM_NAME}.xml"
if [ ! -f "$XML" ]; then
    error "Domain XML not generated: $XML"
    exit 1
fi

virsh define "$XML"
virsh start "$VM_NAME"
info "VM started: $VM_NAME"

# ── Wait for IP ──
step "Step 4/4: Waiting for network"

for i in $(seq 1 30); do
    IP=$(virsh domifaddr "$VM_NAME" 2>/dev/null | awk '/ipv4/{print $4}' | cut -d/ -f1)
    if [ -n "$IP" ]; then
        break
    fi
    sleep 2
done

echo ""
echo "============================================"
echo "  AMI Migration Complete"
echo "============================================"
echo ""
echo "  VM Name:   $VM_NAME"
echo "  Image:     $IMAGE"
echo "  Status:    $(virsh domstate "$VM_NAME" 2>/dev/null)"
if [ -n "${IP:-}" ]; then
    echo "  IP:        $IP"
    echo "  SSH:       ssh root@$IP"
fi
echo "  Console:   sudo virsh console $VM_NAME"
echo "  VNC:       virt-viewer $VM_NAME"
echo "  Output:    $OUTDIR/${VM_NAME}.qcow2"
echo ""

if [ "$KEEP_VM" = false ]; then
    echo "  VM is running. To remove later: sudo $0 --cleanup"
fi

echo ""
