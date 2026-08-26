#!/usr/bin/env bash
# demo-k3s.sh — Convert VMware VM and deploy to KubeVirt on K3s
#
# Usage:
#   ./demo-k3s.sh /root/hyper2kvm/UbuntuServer_22.04_VM_LinuxVMImages.COM.vmdk
#   ./demo-k3s.sh /root/hyper2kvm/some-vm.vmdk [vm-name]

set -euo pipefail

banner()  { echo ""; echo "━━━ 🔧 $* ━━━"; }
info()    { echo "✅ $*"; }
warn()    { echo "⚠️  $*"; }
die()     { echo "❌ $*" >&2; exit 1; }

# Cleanup background processes on exit
cleanup() {
    local pids=()
    for pf in /run/novnc-*.pid /run/virtctl-vnc-*.pid; do
        [[ -f "$pf" ]] || continue
        local pid
        pid=$(cat "$pf" 2>/dev/null) && [[ -n "$pid" ]] && pids+=("$pid")
    done
    for pid in "${pids[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    pkill -f "virtctl.*vnc" 2>/dev/null || true
}
trap cleanup EXIT

# ── Help ─────────────────────────────────────────────────────────────────
usage() {
    cat <<EOF
Usage: $0 [options] <path-to-vm-image> [vm-name]

Convert a VMware VM and deploy to KubeVirt on K3s.

Arguments:
  path-to-vm-image   Path to .vmdk, .ova, .ovf, .vhd, or .raw file
  vm-name            Optional VM name (derived from filename if omitted)

Options:
  --dry-run          Show what would happen without executing
  --cleanup          Remove previous demo VMs and PVCs
  --help, -h         Show this help message

Examples:
  $0 /path/to/ubuntu.vmdk
  $0 /path/to/server.ova my-server
  $0 --dry-run /path/to/vm.vmdk
  $0 --cleanup
EOF
    exit 0
}

# ── Args ─────────────────────────────────────────────────────────────────
DRY_RUN=false
DO_CLEANUP=false
POSITIONAL=()
for arg in "$@"; do
    case "$arg" in
        --help|-h) usage ;;
        --dry-run) DRY_RUN=true ;;
        --cleanup) DO_CLEANUP=true ;;
        *) POSITIONAL+=("$arg") ;;
    esac
done

if "$DO_CLEANUP"; then
    banner "Cleaning up demo resources"
    VM_NAME="${POSITIONAL[0]:-migrated-vm}"
    VM_NAME="$(echo "$VM_NAME" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9-' '-' | sed 's/^-//;s/-$//' | cut -c1-63)"
    kubectl delete vm "$VM_NAME" --ignore-not-found 2>/dev/null || true
    kubectl delete pvc "$VM_NAME" --ignore-not-found 2>/dev/null || true
    info "Cleanup complete"
    exit 0
fi

[[ ${#POSITIONAL[@]} -ge 1 ]] || usage

ORIG_SRC="${POSITIONAL[0]}"
[[ -f "$ORIG_SRC" ]] || die "File not found: $ORIG_SRC"

BASENAME="$(basename "$ORIG_SRC")"
VM_NAME="${POSITIONAL[1]:-${BASENAME%.*}}"
# Sanitise for k8s (lowercase, alphanumeric + dash only)
VM_NAME="$(echo "$VM_NAME" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9-' '-' | sed 's/^-//;s/-$//' | cut -c1-63)"
[[ -n "$VM_NAME" ]] || VM_NAME="migrated-vm"

# Check disk space (need ~3x source size for conversion + upload)
SRC_SIZE_MB=$(( $(stat -c%s "$ORIG_SRC" 2>/dev/null || echo 0) / 1048576 ))
NEEDED_MB=$(( SRC_SIZE_MB * 3 ))
AVAIL_MB=$(df -BM --output=avail /var/lib 2>/dev/null | tail -1 | tr -d ' M' || echo 999999)
if (( AVAIL_MB < NEEDED_MB )); then
    die "Insufficient disk space: need ${NEEDED_MB}MB, have ${AVAIL_MB}MB in /var/lib"
fi

# Copy to safe working directory
WORKDIR="/var/lib/hyper2kvm/input"
mkdir -p "$WORKDIR"
SRC="$WORKDIR/$BASENAME"
if [[ "$ORIG_SRC" != "$SRC" ]]; then
    info "Copying source to $WORKDIR ..."
    cp -f "$ORIG_SRC" "$SRC"
fi

# Detect format
EXT="${BASENAME##*.}"
EXT_LOWER="$(echo "$EXT" | tr '[:upper:]' '[:lower:]')"
case "$EXT_LOWER" in
    vmdk) CMD="local"; SRC_FLAG="--vmdk" ;;
    ova)  CMD="ova";   SRC_FLAG="--ova"  ;;
    ovf)  CMD="ovf";   SRC_FLAG="--ovf"  ;;
    vhd|vhdx) CMD="vhd"; SRC_FLAG="--vhd" ;;
    raw|img)  CMD="raw"; SRC_FLAG="--raw" ;;
    qcow2)    CMD="local"; SRC_FLAG="--vmdk" ;;  # --vmdk is the generic input disk path; format is auto-detected
    *) die "Unsupported format: .$EXT_LOWER" ;;
esac

SRC_DIR="$(dirname "$SRC")"
# Use the login user's home directory (works under sudo)
if [[ -n "${SUDO_USER:-}" ]]; then
    _USER_HOME="$(eval echo ~"$SUDO_USER")"
else
    _USER_HOME="${HOME:-$(eval echo ~"$(whoami)")}"
fi
OUTPUT_DIR="${HYPER2KVM_OUTPUT:-${_USER_HOME}/hyper2kvm/output}/${VM_NAME}-k3s"

# Unique ports per VM: hash VM name to a stable offset (0-99)
VM_PORT_OFFSET=$(( $(echo -n "$VM_NAME" | cksum | awk '{print $1}') % 100 ))
VNC_PORT=$((5901 + VM_PORT_OFFSET))
NOVNC_PORT=$((6080 + VM_PORT_OFFSET))

# ── 1. Pre-checks ────────────────────────────────────────────────────────
banner "Pre-checks"

# Auto-detect kubeconfig
export KUBECONFIG="${KUBECONFIG:-}"
for kc in /etc/rancher/k3s/k3s.yaml "$HOME/.kube/config" /etc/kubernetes/admin.conf; do
    [[ -f "$kc" ]] && export KUBECONFIG="$kc" && break
done

# Install K3s if not running
if ! kubectl get nodes &>/dev/null; then
    info "Installing K3s (with Cilium CNI)..."
    curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--flannel-backend=none --disable-network-policy --disable traefik" sh -
    export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
    sleep 5

    info "Installing Cilium..."
    if ! command -v cilium &>/dev/null; then
        CILIUM_CLI_VERSION=$(curl -s https://raw.githubusercontent.com/cilium/cilium-cli/main/stable.txt)
        curl -sL "https://github.com/cilium/cilium-cli/releases/download/${CILIUM_CLI_VERSION}/cilium-linux-amd64.tar.gz" | tar xz -C /usr/local/bin
        cilium version --client >/dev/null 2>&1 || { echo "ERROR: cilium CLI download failed or binary is corrupt"; exit 1; }
    fi
    cilium install
    info "Waiting for node to be Ready..."
    for i in $(seq 1 30); do
        STATUS=$(kubectl get nodes -o jsonpath='{.items[0].status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || true)
        [[ "$STATUS" == "True" ]] && break
        sleep 10
    done
fi
info "K3s: $(kubectl get nodes -o jsonpath='{.items[0].status.nodeInfo.kubeletVersion}')"

# Install KubeVirt if not present
if ! kubectl get kubevirt kubevirt -n kubevirt &>/dev/null; then
    RELEASE=$(curl -s https://storage.googleapis.com/kubevirt-prow/release/kubevirt/kubevirt/stable.txt)
    info "Installing KubeVirt $RELEASE..."
    kubectl apply -f "https://github.com/kubevirt/kubevirt/releases/download/${RELEASE}/kubevirt-operator.yaml" &>/dev/null
    kubectl apply -f "https://github.com/kubevirt/kubevirt/releases/download/${RELEASE}/kubevirt-cr.yaml" &>/dev/null
    kubectl -n kubevirt wait kv kubevirt --for condition=Available --timeout=300s &>/dev/null
    info "KubeVirt $RELEASE installed"
fi
info "KubeVirt: $(kubectl get kubevirt kubevirt -n kubevirt -o jsonpath='{.status.observedKubeVirtVersion}')"

# Install virtctl if not present
if ! command -v virtctl &>/dev/null; then
    RELEASE=$(kubectl get kubevirt kubevirt -n kubevirt -o jsonpath='{.status.observedKubeVirtVersion}')
    curl -sL -o /usr/local/bin/virtctl "https://github.com/kubevirt/kubevirt/releases/download/${RELEASE}/virtctl-${RELEASE}-linux-amd64"
    chmod +x /usr/local/bin/virtctl
    virtctl version --client >/dev/null 2>&1 || { echo "ERROR: virtctl download failed or binary is corrupt"; exit 1; }
    info "virtctl installed"
fi

# Install CDI if not present
if ! kubectl get cdi cdi &>/dev/null 2>&1; then
    CDI_VERSION=$(curl -s https://api.github.com/repos/kubevirt/containerized-data-importer/releases/latest | grep tag_name | cut -d'"' -f4 || true)
    [[ -z "$CDI_VERSION" ]] && die "Failed to fetch CDI version from GitHub API"
    info "Installing CDI $CDI_VERSION..."
    kubectl apply -f "https://github.com/kubevirt/containerized-data-importer/releases/download/${CDI_VERSION}/cdi-operator.yaml" &>/dev/null
    kubectl apply -f "https://github.com/kubevirt/containerized-data-importer/releases/download/${CDI_VERSION}/cdi-cr.yaml" &>/dev/null
    for i in $(seq 1 18); do
        PHASE=$(kubectl get cdi cdi -o jsonpath="{.status.phase}" 2>/dev/null || true)
        [[ "$PHASE" == "Deployed" ]] && break
        sleep 10
    done
    info "CDI $CDI_VERSION installed"
fi

command -v h2kvmctl &>/dev/null || die "h2kvmctl not found"

# ── 2. Cleanup previous run ──────────────────────────────────────────────
banner "Cleanup: $VM_NAME"

# Kill any existing noVNC and VNC proxy for this VM (by PID file)
for pf in "/run/novnc-${NOVNC_PORT}.pid" "/run/virtctl-vnc-${VM_NAME}.pid"; do
    if [[ -f "$pf" ]]; then
        OLD_PID=$(cat "$pf" 2>/dev/null)
        [[ -n "$OLD_PID" ]] && kill "$OLD_PID" 2>/dev/null || true
        rm -f "$pf"
    fi
done
pkill -f "virtctl.*vnc.*${VM_NAME}" 2>/dev/null || true

# Delete KubeVirt VM if exists
if kubectl get vm "$VM_NAME" &>/dev/null; then
    info "Deleting existing KubeVirt VM: $VM_NAME"
    virtctl stop "$VM_NAME" 2>/dev/null || true
    sleep 3
    kubectl delete vm "$VM_NAME" --wait=true --timeout=30s 2>/dev/null || true
fi

# Delete PVC if exists
if kubectl get pvc "$VM_NAME" &>/dev/null; then
    info "Deleting existing PVC: $VM_NAME"
    kubectl delete pvc "$VM_NAME" --wait=true --timeout=30s 2>/dev/null || true
fi

# Also remove any libvirt VM with same name
virsh destroy "$VM_NAME" 2>/dev/null || true
virsh undefine "$VM_NAME" --nvram 2>/dev/null || virsh undefine "$VM_NAME" 2>/dev/null || true

rm -rf "$OUTPUT_DIR" /var/lib/hyper2kvm/conversions/*
info "Cleaned up"

# ── 3. Convert + Deploy to KubeVirt ──────────────────────────────────────
banner "Convert: $BASENAME → KubeVirt"
info "Source:  $SRC"
info "Format:  $EXT_LOWER (cmd=$CMD)"
info "VM name: $VM_NAME"
echo

if "$DRY_RUN"; then
    info "[DRY RUN] Would convert $SRC to qcow2"
    info "[DRY RUN] Would upload to KubeVirt PVC: $VM_NAME"
    info "[DRY RUN] Would start VM: $VM_NAME"
    exit 0
fi

h2kvmctl \
    --cmd "$CMD" \
    $SRC_FLAG "$SRC" \
    --output-dir "$OUTPUT_DIR" \
    --vm-name "$VM_NAME" \
    --allowed-dir "$SRC_DIR" \
    --emit-domain-xml \
    --regen-initramfs \
    --deploy-k8s \
    --k8s-vm-name "$VM_NAME" \
    --k8s-auto-start \
    --k8s-wait-ready \
    --verbose

# ── 4. Wait for VMI to be Running ────────────────────────────────────────
banner "Wait for KubeVirt VM"

for i in $(seq 1 30); do
    PHASE=$(kubectl get vmi "$VM_NAME" -o jsonpath='{.status.phase}' 2>/dev/null || echo "Pending")
    if [[ "$PHASE" == "Running" ]]; then
        info "VMI is Running!"
        break
    fi
    echo "  attempt $i/30 — phase: $PHASE"
    sleep 10
done
if [[ "$PHASE" != "Running" ]]; then
    warn "VMI did not reach Running state after 5 minutes"
fi

# Wait for VM IP address
wait_for_vm_ip() {
    local vm="$1" timeout="${2:-120}" interval=5
    local elapsed=0
    while (( elapsed < timeout )); do
        local ip
        ip=$(kubectl get vmi "$vm" -o jsonpath='{.status.interfaces[0].ipAddress}' 2>/dev/null || true)
        if [[ -n "$ip" && "$ip" != "null" ]]; then
            echo "$ip"
            return 0
        fi
        sleep "$interval"
        elapsed=$(( elapsed + interval ))
    done
    return 1
}

if [[ "$PHASE" == "Running" ]]; then
    VM_IP=$(wait_for_vm_ip "$VM_NAME" 120) && info "VM IP: $VM_IP" || warn "Could not determine VM IP within 120s"
fi

# ── 5. Show VM info ──────────────────────────────────────────────────────
banner "KubeVirt VM Info"
kubectl get vm "$VM_NAME" -o wide 2>/dev/null || true
echo
kubectl get vmi "$VM_NAME" -o wide 2>/dev/null || true
echo
kubectl get pvc -l "vm.kubevirt.io/name=$VM_NAME" 2>/dev/null || kubectl get pvc "$VM_NAME" 2>/dev/null || true

# ── 6. Start noVNC for remote console ────────────────────────────────────
banner "VNC Console"

PUBLIC_IP=$(ip -4 route get 1 2>/dev/null | awk '{print $7; exit}' || true)
[[ -z "$PUBLIC_IP" ]] && PUBLIC_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || true)

# Auto-detect kubeconfig for virtctl
export KUBECONFIG="${KUBECONFIG:-}"
if [[ -z "$KUBECONFIG" ]]; then
    for kc in /etc/rancher/k3s/k3s.yaml "$HOME/.kube/config" /etc/kubernetes/admin.conf; do
        [[ -f "$kc" ]] && export KUBECONFIG="$kc" && break
    done
fi

# Kill any previous VNC proxy and noVNC for this VM (by PID file to avoid killing SSH)
pkill -f "virtctl.*vnc.*${VM_NAME}" 2>/dev/null || true
NOVNC_PIDFILE="/run/novnc-${NOVNC_PORT}.pid"
VNC_PIDFILE="/run/virtctl-vnc-${VNC_PORT}.pid"
for pf in "$NOVNC_PIDFILE" "$VNC_PIDFILE"; do
    if [[ -f "$pf" ]]; then
        OLD_PID=$(cat "$pf" 2>/dev/null)
        [[ -n "$OLD_PID" ]] && kill "$OLD_PID" 2>/dev/null || true
        rm -f "$pf"
    fi
done
sleep 1

# Start virtctl VNC proxy (bridges k8s API to local TCP)
virtctl vnc "$VM_NAME" --proxy-only --port=${VNC_PORT} &>/var/log/virtctl-vnc.log &
VIRTCTL_PID=$!
echo "$VIRTCTL_PID" > "/run/virtctl-vnc-${VM_NAME}.pid"
sleep 3

VNC_OK=false
if kill -0 "$VIRTCTL_PID" 2>/dev/null && (ss -tlnp | grep -q ":${VNC_PORT}"); then
    info "VNC proxy on 127.0.0.1:${VNC_PORT} (PID: $VIRTCTL_PID)"
    VNC_OK=true
fi

if $VNC_OK; then
    # Auto-install noVNC + websockify if missing
    if ! command -v websockify &>/dev/null || [[ ! -d /usr/share/novnc ]]; then
        info "Installing noVNC and websockify..."
        if command -v dnf &>/dev/null; then
            dnf install -y novnc python3-websockify &>/dev/null
        elif command -v apt-get &>/dev/null; then
            apt-get install -y novnc python3-websockify &>/dev/null
        fi
    fi

    # Start noVNC web proxy
    if command -v websockify &>/dev/null && [[ -d /usr/share/novnc ]]; then
        websockify --web /usr/share/novnc/ --daemon "$NOVNC_PORT" "127.0.0.1:${VNC_PORT}" 2>/dev/null
        sleep 1
        # Save PID and open firewall
        if (ss -tlnp | grep -q ":${NOVNC_PORT}"); then
            PID=$(ss -tlnp 2>/dev/null | grep ":${NOVNC_PORT}" | grep -oP 'pid=\K[0-9]+' | head -1 || true)
            [[ -n "$PID" ]] && echo "$PID" > "$NOVNC_PIDFILE"
            if command -v firewall-cmd &>/dev/null; then
                firewall-cmd --add-port="${NOVNC_PORT}/tcp" &>/dev/null || true
                firewall-cmd --add-port="${NOVNC_PORT}/tcp" --permanent &>/dev/null || true
            elif command -v iptables &>/dev/null; then
                iptables -C INPUT -p tcp --dport "${NOVNC_PORT}" -j ACCEPT 2>/dev/null || \
                    iptables -I INPUT -p tcp --dport "${NOVNC_PORT}" -j ACCEPT 2>/dev/null || true
            fi
        fi
        info "noVNC ready at http://${PUBLIC_IP}:${NOVNC_PORT}/vnc.html"
    else
        warn "noVNC not installed — install with: dnf install -y novnc python3-websockify"
        info "VNC available at 127.0.0.1:${VNC_PORT} (use SSH tunnel)"
    fi
else
    warn "Could not start VNC proxy"
    info "Try manually: KUBECONFIG=$KUBECONFIG virtctl vnc $VM_NAME"
fi

# ── 7. Summary ───────────────────────────────────────────────────────────
banner "Result"

PHASE=$(kubectl get vmi "$VM_NAME" -o jsonpath='{.status.phase}' 2>/dev/null || echo "unknown")
NODE=$(kubectl get vmi "$VM_NAME" -o jsonpath='{.status.nodeName}' 2>/dev/null || echo "")

echo ""
echo "  ┌──────────────────────────────────────────────────┐"
echo "  │  🚀 KubeVirt Migration Complete!                 │"
echo "  ├──────────────────────────────────────────────────┤"
printf "  │  VM name : %-37s│\n" "$VM_NAME"
printf "  │  Phase   : %-37s│\n" "$PHASE"
printf "  │  Node    : %-37s│\n" "$NODE"
printf "  │  Source  : %-37s│\n" "$EXT_LOWER"
if [[ -n "${VM_IP:-}" ]]; then
    printf "  │  IP      : %-37s│\n" "$VM_IP"
fi
echo "  ├──────────────────────────────────────────────────┤"
if $VNC_OK; then
    echo "  │  🖥️  http://${PUBLIC_IP}:${NOVNC_PORT}/vnc.html"
fi
echo "  │  📋 kubectl get vmi $VM_NAME"
echo "  │  🔌 virtctl console $VM_NAME"
echo "  │  🖥️  virtctl vnc $VM_NAME"
echo "  └──────────────────────────────────────────────────┘"
echo ""
