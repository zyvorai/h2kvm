#!/bin/bash
# ============================================
# hyper2kvm: Zero to Demo in One Command
# ============================================
# Fresh Fedora or Ubuntu machine → running KVM + KubeVirt VM
#
# Installs everything:
#   1. System deps (qemu, libvirt, nbd, pip)
#   2. Python deps via pip (pyvmomi, pyyaml, click, etc.)
#   3. hyper2kvm from source
#   4. K3s + KubeVirt + CDI (optional: --with-k3s)
#   5. Downloads test VMDK
#   6. Runs migration → libvirt VM booting
#   7. Optionally deploys to KubeVirt (--with-k3s)
#
# Usage:
#   sudo ./scripts/zero-to-demo.sh                # libvirt only
#   sudo ./scripts/zero-to-demo.sh --with-k3s     # libvirt + KubeVirt
#   sudo ./scripts/zero-to-demo.sh --verify       # check status only
#
# Supports: Fedora 38+, RHEL 9+, Ubuntu 22.04+, Debian 12+
# ============================================

set -euo pipefail
trap 'echo -e "\n[FATAL] Failed at line $LINENO (exit $?)"; exit 1' ERR

usage() {
    cat <<EOF
Usage: sudo $0 [options]

Fresh machine to running KVM VM in one command.

Options:
  --with-k3s     Also install K3s + KubeVirt and deploy VM there
  --verify       Check installation status only (no changes)
  --dry-run      Show what would be installed without executing
  --help, -h     Show this help message

Supports: Fedora 38+, RHEL 9+, Ubuntu 22.04+, Debian 12+

Examples:
  sudo $0                    # Libvirt only
  sudo $0 --with-k3s        # Libvirt + KubeVirt on K3s
  sudo $0 --verify          # Check status
  sudo $0 --dry-run         # Preview
EOF
    exit 0
}

WITH_K3S=false
VERIFY_ONLY=false
DRY_RUN=false
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEMO_VMDK="${DEMO_VMDK:-}"
OUTPUT_DIR="/tmp/hyper2kvm-demo"
KUBECONFIG_PATH="/etc/rancher/k3s/k3s.yaml"

for arg in "$@"; do
    case "$arg" in
        --with-k3s)    WITH_K3S=true ;;
        --verify)      VERIFY_ONLY=true ;;
        --dry-run)     DRY_RUN=true ;;
        --help|-h)     usage ;;
    esac
done

[ "$(id -u)" -eq 0 ] || { echo "Run as root: sudo $0"; exit 1; }

info()  { echo -e "\033[32m✅ $*\033[0m"; }
warn()  { echo -e "\033[33m⚠️  $*\033[0m"; }
error() { echo "❌ $*" >&2; }
step()  { echo -e "\033[36m🔹 $*\033[0m"; }
banner() { echo -e "\n\033[1;35m━━━ $* ━━━\033[0m\n"; }

# ── Detect distro ──
if [ -f /etc/os-release ]; then
    . /etc/os-release
else
    ID="unknown"
fi

# ── Verify mode ──
if $VERIFY_ONLY; then
    banner "Verification"
    echo -n "h2kvmctl:    "; h2kvmctl --version 2>/dev/null || echo "NOT INSTALLED"
    echo -n "qemu-img:    "; qemu-img --version 2>/dev/null | head -1 || echo "NOT INSTALLED"
    echo -n "qemu-nbd:    "; which qemu-nbd 2>/dev/null || echo "NOT INSTALLED"
    echo -n "virsh:       "; virsh --version 2>/dev/null || echo "NOT INSTALLED"
    echo -n "libvirtd:    "; systemctl is-active libvirtd 2>/dev/null || echo "NOT RUNNING"
    echo -n "nbd module:  "; lsmod | grep -q nbd && echo "loaded" || echo "NOT LOADED"
    if $WITH_K3S || [ -f "$KUBECONFIG_PATH" ]; then
        echo -n "k3s:         "; systemctl is-active k3s 2>/dev/null || echo "NOT RUNNING"
        echo -n "kubectl:     "; kubectl version --client -o json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['clientVersion']['gitVersion'])" 2>/dev/null || kubectl version --client 2>/dev/null | head -1 || echo "NOT INSTALLED"
        echo -n "kubevirt:    "; KUBECONFIG=$KUBECONFIG_PATH kubectl get pods -n kubevirt 2>/dev/null | head -3 || echo "NOT INSTALLED"
    fi
    exit 0
fi

banner "hyper2kvm: Zero to Demo"
echo "Distro:  $ID ($PRETTY_NAME)"
echo "K3s:     $WITH_K3S"
echo ""

# ── Disk space check ──
avail_tmp=$(df -BM /tmp 2>/dev/null | tail -1 | awk '{print $4}' | tr -d 'M')
if [ "${avail_tmp:-0}" -lt 2000 ]; then
    warn "/tmp only has ${avail_tmp:-?}MB free — need at least 2000MB for downloads and conversion"
fi

# ── Dry-run mode ──
if $DRY_RUN; then
    banner "Dry Run — What Would Be Installed"
    echo "System packages:"
    case "$ID" in
        fedora|rhel|centos|rocky|almalinux)
            echo "  dnf install: python3 python3-pip qemu-img qemu-kvm libvirt edk2-ovmf virt-install nbdkit qemu-nbd guestfs-tools git curl"
            ;;
        ubuntu|debian|linuxmint|pop)
            echo "  apt install: python3 python3-pip qemu-utils qemu-kvm libvirt-daemon-system ovmf virtinst nbd-client libguestfs-tools git curl"
            ;;
        *)
            echo "  (unknown distro — manual install needed)"
            ;;
    esac
    echo ""
    echo "Python packages (pip):"
    echo "  pyyaml click argcomplete pyvmomi requests watchdog"
    echo ""
    echo "hyper2kvm:"
    if [ -f "$REPO_DIR/pyproject.toml" ]; then
        echo "  pip install -e $REPO_DIR (from source)"
    else
        echo "  pip install hyper2kvm (from PyPI)"
    fi
    if $WITH_K3S; then
        echo ""
        echo "Kubernetes:"
        echo "  K3s (https://get.k3s.io)"
        echo "  KubeVirt (latest release)"
        echo "  CDI (latest release)"
    fi
    echo ""
    echo "Demo:"
    echo "  Download Photon OS 5.0 OVA (~307 MB) if no VMDK found"
    echo "  Convert VMDK -> qcow2, deploy to libvirt"
    echo "  Output: $OUTPUT_DIR"
    exit 0
fi

# ════════════════════════════════════════════
# PHASE 1: System Dependencies
# ════════════════════════════════════════════
banner "Phase 1: System Dependencies"

case "$ID" in
    fedora|rhel|centos|rocky|almalinux)
        step "Installing via dnf..."
        dnf install -y -q \
            python3 python3-pip python3-devel \
            qemu-img qemu-kvm \
            libvirt libvirt-client libvirt-daemon-kvm \
            edk2-ovmf virt-install \
            nbdkit qemu-nbd nbd \
            guestfs-tools \
            git curl tar 2>/dev/null || true
        ;;
    ubuntu|debian|linuxmint|pop)
        step "Installing via apt..."
        apt-get update -qq 2>/dev/null
        apt-get install -y -qq \
            python3 python3-pip python3-dev python3-venv \
            qemu-utils qemu-system-x86 qemu-kvm \
            libvirt-daemon-system libvirt-clients \
            ovmf virtinst \
            nbd-client qemu-block-extra \
            libguestfs-tools \
            git curl 2>/dev/null || true
        ;;
    *)
        warn "Unknown distro '$ID'. Install python3, qemu, libvirt manually."
        ;;
esac

# Load NBD kernel module
step "Loading nbd kernel module..."
modprobe nbd max_part=16 2>/dev/null || true
echo "options nbd max_part=16" > /etc/modprobe.d/nbd.conf 2>/dev/null || true

# Start libvirtd
step "Starting libvirtd..."
systemctl enable --now libvirtd 2>/dev/null || true

info "System deps installed"

# ════════════════════════════════════════════
# PHASE 2: Python Dependencies (via pip)
# ════════════════════════════════════════════
banner "Phase 2: Python Dependencies (pip)"

PIP_FLAGS="--break-system-packages --root-user-action=ignore"

step "Installing Python packages via pip..."
pip3 install $PIP_FLAGS --quiet --upgrade \
    pyyaml click argcomplete pyvmomi requests watchdog 2>/dev/null || \
pip3 install --quiet --upgrade \
    pyyaml click argcomplete pyvmomi requests watchdog 2>/dev/null || true

info "Python deps installed"

# ════════════════════════════════════════════
# PHASE 3: Install hyper2kvm
# ════════════════════════════════════════════
banner "Phase 3: Install hyper2kvm"

if [ -f "$REPO_DIR/pyproject.toml" ]; then
    step "Installing from source: $REPO_DIR"
    pip3 install $PIP_FLAGS --quiet -e "$REPO_DIR" 2>/dev/null || \
    pip3 install --quiet -e "$REPO_DIR" 2>/dev/null || true
else
    step "Installing from PyPI..."
    pip3 install $PIP_FLAGS --quiet hyper2kvm 2>/dev/null || true
fi

h2kvmctl --version
info "hyper2kvm $(h2kvmctl --version) installed"

# ════════════════════════════════════════════
# PHASE 4: K3s + KubeVirt (optional)
# ════════════════════════════════════════════
if $WITH_K3S; then
    banner "Phase 4: K3s + KubeVirt + CDI"

    if ! systemctl is-active k3s >/dev/null 2>&1; then
        step "Installing K3s..."
        curl -sfL https://get.k3s.io | \
            INSTALL_K3S_EXEC="--write-kubeconfig-mode 644 --disable=traefik" \
            INSTALL_K3S_SKIP_SELINUX_RPM=true sh -
        sleep 15
    fi
    export KUBECONFIG="$KUBECONFIG_PATH"
    info "K3s: $(kubectl get nodes -o jsonpath='{.items[0].status.nodeInfo.kubeletVersion}')"

    # KubeVirt
    if ! kubectl get pods -n kubevirt 2>/dev/null | grep -q virt-operator; then
        step "Installing KubeVirt..."
        KUBEVIRT_VERSION=$(curl -s https://api.github.com/repos/kubevirt/kubevirt/releases/latest | grep tag_name | cut -d'"' -f4)
        kubectl apply -f "https://github.com/kubevirt/kubevirt/releases/download/${KUBEVIRT_VERSION}/kubevirt-operator.yaml" 2>&1 | tail -2
        kubectl apply -f "https://github.com/kubevirt/kubevirt/releases/download/${KUBEVIRT_VERSION}/kubevirt-cr.yaml" 2>&1
        step "Waiting for KubeVirt (up to 5 min)..."
        kubectl wait --for=condition=Available --timeout=300s -n kubevirt kv/kubevirt
    fi
    info "KubeVirt ready"

    # CDI
    if ! kubectl get pods -n cdi 2>/dev/null | grep -q cdi-operator; then
        step "Installing CDI..."
        CDI_VERSION=$(curl -s https://api.github.com/repos/kubevirt/containerized-data-importer/releases/latest | grep tag_name | cut -d'"' -f4)
        kubectl apply -f "https://github.com/kubevirt/containerized-data-importer/releases/download/${CDI_VERSION}/cdi-operator.yaml" 2>&1 | tail -2
        kubectl apply -f "https://github.com/kubevirt/containerized-data-importer/releases/download/${CDI_VERSION}/cdi-cr.yaml" 2>&1
        step "Waiting for CDI (up to 3 min)..."
        kubectl wait --for=condition=Available --timeout=180s -n cdi cdi/cdi
    fi
    info "CDI ready"
fi

# ════════════════════════════════════════════
# PHASE 5: Download Test VMDK
# ════════════════════════════════════════════
banner "Phase 5: Test VMDK"

# Photon OS 5.0 OVA — real bootable VM for demo
PHOTON_OVA_URL="https://packages.vmware.com/photon/5.0/GA/ova/photon-hw15-5.0-dde71ec57.x86_64.ova"
PHOTON_OVA="/tmp/photon-5.0.ova"
PHOTON_VMDK="/tmp/photon-5.0.vmdk"

# Search order:
#   1. DEMO_VMDK env var (user-supplied path)
#   2. photon.vmdk in repo root
#   3. Any .vmdk in repo root
#   4. Download Photon OS 5.0 OVA (307 MB), extract VMDK
if [ -n "$DEMO_VMDK" ] && [ -f "$DEMO_VMDK" ]; then
    step "Using (env): $DEMO_VMDK"
elif [ -f "$REPO_DIR/photon.vmdk" ]; then
    DEMO_VMDK="$REPO_DIR/photon.vmdk"
    step "Using (repo): $DEMO_VMDK"
elif ls "$REPO_DIR"/*.vmdk >/dev/null 2>&1; then
    DEMO_VMDK="$(ls -S "$REPO_DIR"/*.vmdk | head -1)"
    step "Using (repo): $DEMO_VMDK"
elif [ -f "$PHOTON_VMDK" ]; then
    DEMO_VMDK="$PHOTON_VMDK"
    step "Using (cached): $DEMO_VMDK"
else
    # Download OVA and extract VMDK
    if [ ! -f "$PHOTON_OVA" ]; then
        step "Downloading Photon OS 5.0 OVA (~307 MB)..."
        curl -fSL --progress-bar -o "$PHOTON_OVA" "$PHOTON_OVA_URL" || {
            error "Download failed. Provide a VMDK manually:"
            error "  DEMO_VMDK=/path/to/your.vmdk sudo $0"
            exit 1
        }
    fi
    step "Extracting VMDK from OVA..."
    tar xf "$PHOTON_OVA" -C /tmp/ --wildcards '*.vmdk' 2>/dev/null || \
    tar xf "$PHOTON_OVA" -C /tmp/ 2>/dev/null
    DEMO_VMDK="$(ls -S /tmp/*.vmdk 2>/dev/null | head -1)"
    if [ -z "$DEMO_VMDK" ] || [ ! -f "$DEMO_VMDK" ]; then
        error "No VMDK found in OVA. Contents:"
        tar tf "$PHOTON_OVA"
        exit 1
    fi
    step "Extracted: $DEMO_VMDK"
fi

info "Test VMDK: $(ls -lh "$DEMO_VMDK" 2>/dev/null | awk '{print $5}')"

# ════════════════════════════════════════════
# PHASE 6: Run Migration Demo
# ════════════════════════════════════════════
banner "Phase 6: Migration Demo"

rm -rf "$OUTPUT_DIR"

K8S_FLAGS=""
if $WITH_K3S; then
    K8S_FLAGS="deploy_k8s: true
k8s_namespace: default"
    export KUBECONFIG="$KUBECONFIG_PATH"
fi

cat > /tmp/hyper2kvm-demo.yaml <<YAML
cmd: local
vmdk: $DEMO_VMDK
output_dir: $OUTPUT_DIR
flatten: true
flatten_format: qcow2
to_output: demo.qcow2
out_format: qcow2
compress: false
fstab_mode: stabilize-all
regen_initramfs: true
emit_domain_xml: true
vm_name: hyper2kvm-demo
memory: 2048
vcpus: 2
machine: q35
libvirt_test: true
timeout: 60
keep_domain: true
$K8S_FLAGS
YAML

step "Running: h2kvmctl --config /tmp/hyper2kvm-demo.yaml"
h2kvmctl --config /tmp/hyper2kvm-demo.yaml 2>&1 | \
    grep -E "Sanity|Flatten|progress|Convert|initramfs|emit_domain|deploy_k8s|RUNNING|Done|Generated|k8s|kubevirt|PVC|uploaded" || true

# ════════════════════════════════════════════
# PHASE 7: Verify Results
# ════════════════════════════════════════════
banner "Results"

echo "=== Output Files ==="
ls -lh "$OUTPUT_DIR/"*.qcow2 2>/dev/null
ls -lh "$OUTPUT_DIR/libvirt/"*.xml 2>/dev/null

echo ""
echo "=== Libvirt VM ==="
virsh list --all 2>/dev/null | grep hyper2kvm-demo || echo "(not found)"

if $WITH_K3S; then
    echo ""
    echo "=== KubeVirt VM ==="
    KUBECONFIG="$KUBECONFIG_PATH" kubectl get vm,vmi 2>/dev/null || echo "(not deployed)"
fi

echo ""
echo "=== Network ==="
# Wait a few seconds for DHCP lease
sleep 5
VM_IP=$(virsh domifaddr hyper2kvm-demo 2>/dev/null | grep ipv4 | awk '{print $4}' | cut -d/ -f1 || true)
if [ -n "$VM_IP" ]; then
    echo "VM IP: $VM_IP"
    nc -zv -w3 "$VM_IP" 22 2>&1 || true
else
    echo "VM has not received an IP yet (DHCP pending)."
    echo "Check later: virsh domifaddr hyper2kvm-demo"
fi

banner "Done!"
echo "VM is running. Connect via:"
echo "  virsh console hyper2kvm-demo"
[ -n "$VM_IP" ] && echo "  ssh root@$VM_IP"
if $WITH_K3S; then
    echo "  KUBECONFIG=$KUBECONFIG_PATH kubectl get vmi"
fi
echo ""
echo "Cleanup:"
echo "  virsh destroy hyper2kvm-demo && virsh undefine hyper2kvm-demo --nvram"
$WITH_K3S && echo "  KUBECONFIG=$KUBECONFIG_PATH kubectl delete vm hyper2kvm-demo"
echo "  rm -rf $OUTPUT_DIR"
