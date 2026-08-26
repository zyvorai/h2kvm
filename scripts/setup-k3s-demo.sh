#!/bin/bash
set -euo pipefail
# ============================================
# K3s + KubeVirt Demo for hyper2kvm
# ============================================
# Production-grade installer for K3s, KubeVirt, CDI, and virtctl.
# Demonstrates exporting a VM with hyper2kvm and importing it
# as a KubeVirt VirtualMachine.
#
# Architecture:
#   hyper2kvm export → qcow2 → PVC (CDI upload) → KubeVirt VM
#
# Prerequisites:
#   - Linux x86_64 with 4GB+ RAM
#   - Root access
#   - hyper2kvm installed (run quickstart.sh first)
#
# Usage:
#   sudo ./scripts/setup-k3s-demo.sh           # install k3s + kubevirt
#   sudo ./scripts/setup-k3s-demo.sh --demo    # install + run demo
#   sudo ./scripts/setup-k3s-demo.sh --verify  # check status
#   sudo ./scripts/setup-k3s-demo.sh --cleanup # remove everything
#   DRY_RUN=true sudo ./scripts/setup-k3s-demo.sh  # preview
# ============================================

trap 'echo -e "\n[FATAL] Failed at line $LINENO (exit $?)"; exit 1' ERR

# ── Config ──
KUBEVIRT_VERSION="${KUBEVIRT_VERSION:-v1.4.0}"
CDI_VERSION="${CDI_VERSION:-v1.60.3}"
DRY_RUN="${DRY_RUN:-false}"
DEMO_NAME="${DEMO_NAME:-hyper2kvm-demo}"
START_TIME=$(date +%s)

# ── Helpers ──
info()  { echo "✅ $*"; }
warn()  { echo "⚠️ $*"; }
error() { echo "❌ $*"; }
step()  { echo "🔹$*"; }
dim()   { echo "    $*"; }

elapsed() { echo "$(($(date +%s) - START_TIME))s"; }

run() {
    echo "+ $*" >> /tmp/hyper2kvm-k3s.log 2>/dev/null || true
    if [ "$DRY_RUN" = "false" ]; then
        "$@"
    else
        dim "[dry-run] $*"
    fi
}

retry() {
    local attempts=3 delay=2
    for i in $(seq 1 "$attempts"); do
        "$@" && return 0
        warn "Attempt $i/$attempts failed, retrying in ${delay}s..."
        sleep "$delay"
        delay=$((delay * 2))
    done
    error "Failed after $attempts attempts: $*"
    return 1
}

# ── Pre-flight ──
preflight() {
    step "Pre-flight checks"

    if [ "$(id -u)" -ne 0 ]; then
        error "Run as root: sudo $0"
        exit 1
    fi

    # Architecture
    local arch
    arch=$(uname -m)
    if [ "$arch" != "x86_64" ] && [ "$arch" != "aarch64" ]; then
        error "Unsupported architecture: $arch"
        exit 1
    fi
    info "Arch: $arch"

    # RAM
    local ram_mb
    ram_mb=$(free -m | awk '/Mem:/{print $2}')
    if [ "$ram_mb" -lt 3500 ]; then
        warn "RAM: ${ram_mb}MB (recommend 4GB+ for KubeVirt)"
    else
        info "RAM: ${ram_mb}MB"
    fi

    # Disk
    local free_gb
    free_gb=$(df -BG . | awk 'NR==2{print $4}' | tr -d 'G')
    if [ "$free_gb" -lt 10 ]; then
        error "Disk: ${free_gb}GB free (need 10GB+ for K3s + images)"
        exit 1
    fi
    info "Disk: ${free_gb}GB free"

    # Network
    if ping -c 1 -W 3 github.com &>/dev/null; then
        info "Network: connected"
    else
        warn "Network: no internet (K3s/KubeVirt install will fail)"
    fi

    # Nested virt
    if grep -q hypervisor /proc/cpuinfo 2>/dev/null; then
        warn "Running inside VM — KubeVirt will use software emulation"
    fi

    info "Pre-flight passed ($(elapsed))"
}

# ── Install K3s ──
install_k3s() {
    step "Installing K3s"

    if command -v kubectl &>/dev/null && kubectl get nodes &>/dev/null 2>&1; then
        info "K3s already installed and running"
        kubectl get nodes
        return
    fi

    retry curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--disable=traefik" sh -

    # Wait for K3s ready
    info "Waiting for K3s to be ready..."
    local retries=30
    while [ $retries -gt 0 ]; do
        kubectl get nodes 2>/dev/null | grep -q " Ready" && break
        sleep 5
        retries=$((retries - 1))
    done

    if [ $retries -eq 0 ]; then
        error "K3s failed to start after 150s"
        exit 1
    fi

    # Setup kubeconfig
    mkdir -p ~/.kube
    cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
    chmod 600 ~/.kube/config

    # Also for SUDO_USER
    local target_user="${SUDO_USER:-}"
    if [ -n "$target_user" ] && [ "$target_user" != "root" ]; then
        local user_home
        user_home=$(getent passwd "$target_user" | cut -d: -f6)
        mkdir -p "$user_home/.kube"
        cp /etc/rancher/k3s/k3s.yaml "$user_home/.kube/config"
        chown -R "$target_user":"$target_user" "$user_home/.kube"
        chmod 600 "$user_home/.kube/config"
    fi

    info "K3s installed ($(elapsed)):"
    kubectl get nodes
}

# ── Install KubeVirt ──
install_kubevirt() {
    step "Installing KubeVirt ${KUBEVIRT_VERSION}"

    if kubectl get namespace kubevirt &>/dev/null 2>&1; then
        info "KubeVirt already installed"
        kubectl get pods -n kubevirt --no-headers 2>/dev/null | head -3
        return
    fi

    run kubectl create -f "https://github.com/kubevirt/kubevirt/releases/download/${KUBEVIRT_VERSION}/kubevirt-operator.yaml"
    run kubectl create -f "https://github.com/kubevirt/kubevirt/releases/download/${KUBEVIRT_VERSION}/kubevirt-cr.yaml"

    # Enable software emulation if no /dev/kvm
    if [ ! -e /dev/kvm ]; then
        warn "No /dev/kvm — enabling software emulation (slower)"
        kubectl -n kubevirt patch kubevirt kubevirt --type=merge \
            -p '{"spec":{"configuration":{"developerConfiguration":{"useEmulation":true}}}}' 2>/dev/null || true
    fi

    # Wait for ready
    info "Waiting for KubeVirt pods (2-5 minutes)..."
    kubectl wait --for=condition=Available kubevirt kubevirt \
        -n kubevirt --timeout=300s 2>/dev/null || warn "KubeVirt still starting"

    info "KubeVirt installed ($(elapsed))"
}

# ── Install CDI ──
install_cdi() {
    step "Installing CDI ${CDI_VERSION}"

    if kubectl get namespace cdi &>/dev/null 2>&1; then
        info "CDI already installed"
        return
    fi

    run kubectl create -f "https://github.com/kubevirt/containerized-data-importer/releases/download/${CDI_VERSION}/cdi-operator.yaml"
    run kubectl create -f "https://github.com/kubevirt/containerized-data-importer/releases/download/${CDI_VERSION}/cdi-cr.yaml"

    info "Waiting for CDI..."
    kubectl wait --for=condition=Available cdi cdi \
        -n cdi --timeout=300s 2>/dev/null || warn "CDI still starting"

    info "CDI installed ($(elapsed))"
}

# ── Install virtctl ──
install_virtctl() {
    step "Installing virtctl"

    if command -v virtctl &>/dev/null; then
        info "virtctl already installed: $(virtctl version --client --short 2>/dev/null || echo 'ok')"
        return
    fi

    local arch
    case "$(uname -m)" in
        x86_64)  arch="amd64" ;;
        aarch64) arch="arm64" ;;
        *)       warn "Unsupported arch for virtctl"; return ;;
    esac

    local tmpfile
    tmpfile=$(mktemp)
    retry curl -fsSL -o "$tmpfile" \
        "https://github.com/kubevirt/kubevirt/releases/download/${KUBEVIRT_VERSION}/virtctl-${KUBEVIRT_VERSION}-linux-${arch}"
    install -m 755 "$tmpfile" /usr/local/bin/virtctl
    rm -f "$tmpfile"
    info "virtctl installed"
}

# ── Open firewall ──
setup_firewall() {
    if command -v firewall-cmd &>/dev/null; then
        warn "Opening K3s API port 6443"
        firewall-cmd --permanent --add-port=6443/tcp 2>/dev/null || true
        firewall-cmd --permanent --add-port=10250/tcp 2>/dev/null || true
        firewall-cmd --reload 2>/dev/null || true
        info "Firewall: K3s ports opened"
    fi
}

# ── Run Demo ──
run_demo() {
    step "hyper2kvm → KubeVirt Demo"

    local demo_image=""

    # Find a qcow2
    if [ -f photon.vmdk ]; then
        info "Converting local photon.vmdk..."
        h2kvmctl --cmd local \
            --vmdk ./photon.vmdk \
            --output-dir ./output-k3s-demo \
            --to-output demo-vm.qcow2 \
            --out-format qcow2 \
            --flatten --compress \
            --fstab-mode stabilize-all \
            --regen-initramfs \
            -v 2>&1 | tail -5
        demo_image="./output-k3s-demo/demo-vm.qcow2"
    elif [ -f output-photon/photon-os.qcow2 ]; then
        demo_image="output-photon/photon-os.qcow2"
    elif [ -f output-govc-e2e/govc-vm.qcow2 ]; then
        demo_image="output-govc-e2e/govc-vm.qcow2"
    fi

    if [ -z "$demo_image" ] || [ ! -f "$demo_image" ]; then
        warn "No qcow2 image found. Convert one first:"
        echo "  sudo h2kvmctl --config photon-to-libvirt.yaml"
        return
    fi

    local image_size pvc_size
    image_size=$(qemu-img info --output=json "$demo_image" | python3 -c "import sys,json; print(json.load(sys.stdin)['virtual-size'])")
    pvc_size=$(( (image_size / 1073741824) + 2 ))

    info "Image: $demo_image (PVC: ${pvc_size}Gi)"

    # Cleanup previous
    kubectl delete vm "$DEMO_NAME" --ignore-not-found 2>/dev/null || true
    kubectl delete pvc "${DEMO_NAME}-disk" --ignore-not-found 2>/dev/null || true
    sleep 3

    # Create PVC
    step "Creating PVC"
    cat <<PVCEOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ${DEMO_NAME}-disk
  namespace: default
  annotations:
    cdi.kubevirt.io/storage.upload.target: ""
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: ${pvc_size}Gi
PVCEOF
    sleep 5

    # Upload image
    step "Uploading disk image to PVC"
    local upload_proxy
    upload_proxy=$(kubectl get svc -n cdi cdi-uploadproxy -o jsonpath='{.spec.clusterIP}' 2>/dev/null || echo "")
    if [ -n "$upload_proxy" ]; then
        virtctl image-upload pvc "${DEMO_NAME}-disk" \
            --size="${pvc_size}Gi" \
            --image-path="$demo_image" \
            --uploadproxy-url="${upload_proxy}:443" \
            --insecure \
            --force-bind 2>/dev/null || warn "CDI upload failed"
    else
        warn "CDI upload proxy not found — skipping upload"
    fi

    # Create VM
    step "Creating KubeVirt VirtualMachine"
    cat <<VMEOF | kubectl apply -f -
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: ${DEMO_NAME}
  namespace: default
spec:
  running: true
  template:
    metadata:
      labels:
        kubevirt.io/vm: ${DEMO_NAME}
    spec:
      domain:
        cpu:
          cores: 2
        devices:
          disks:
            - name: disk0
              disk:
                bus: virtio
          interfaces:
            - name: default
              masquerade: {}
        machine:
          type: q35
        resources:
          requests:
            memory: 2Gi
      networks:
        - name: default
          pod: {}
      volumes:
        - name: disk0
          persistentVolumeClaim:
            claimName: ${DEMO_NAME}-disk
VMEOF

    # Wait for VM
    info "Waiting for VM to start..."
    local retries=30
    while [ $retries -gt 0 ]; do
        kubectl get vmi "$DEMO_NAME" 2>/dev/null | grep -q Running && break
        sleep 5
        retries=$((retries - 1))
    done

    # Results
    echo ""
    echo "╔══════════════════════════════════════════════════╗"
    echo "║  KubeVirt Demo Results                           ║"
    echo "╠══════════════════════════════════════════════════╣"

    local vm_phase
    vm_phase=$(kubectl get vmi "$DEMO_NAME" -o jsonpath='{.status.phase}' 2>/dev/null || echo "Unknown")
    local vm_ip
    vm_ip=$(kubectl get vmi "$DEMO_NAME" -o jsonpath='{.status.interfaces[0].ipAddress}' 2>/dev/null || echo "")

    if [ "$vm_phase" = "Running" ]; then
        printf "  ║  ✔ %-10s %-38s ║\n" "Status:" "RUNNING"
    else
        printf "  ║  ⚠ %-10s %-38s ║\n" "Status:" "$vm_phase"
    fi

    printf "  ║  ✔ %-10s %-38s ║\n" "VM:" "$DEMO_NAME"
    [ -n "$vm_ip" ] && printf "  ║  ✔ %-10s %-38s ║\n" "IP:" "$vm_ip"
    printf "  ║  ✔ %-10s %-38s ║\n" "Time:" "$(elapsed)"

    echo "╠══════════════════════════════════════════════════╣"
    printf "  ║  %-10s %-38s ║\n" "Console:" "virtctl console $DEMO_NAME"
    printf "  ║  %-10s %-38s ║\n" "VNC:" "virtctl vnc $DEMO_NAME"
    printf "  ║  %-10s %-38s ║\n" "Status:" "kubectl get vm,vmi"
    printf "  ║  %-10s %-38s ║\n" "Stop:" "virtctl stop $DEMO_NAME"
    echo "╠══════════════════════════════════════════════════╣"
    printf "  ║  %-48s ║\n" "Cleanup: sudo $0 --cleanup"
    echo "╚══════════════════════════════════════════════════╝"
    echo ""
}

# ── Cleanup ──
cleanup() {
    step "Cleaning up K3s + KubeVirt"

    kubectl delete vm "$DEMO_NAME" --ignore-not-found 2>/dev/null || true
    kubectl delete pvc "${DEMO_NAME}-disk" --ignore-not-found 2>/dev/null || true

    if [ -f /usr/local/bin/k3s-uninstall.sh ]; then
        /usr/local/bin/k3s-uninstall.sh
        info "K3s uninstalled"
    fi

    rm -rf ./output-k3s-demo 2>/dev/null || true
    info "Cleanup complete"
}

# ── Verify ──
verify() {
    step "Verification"

    for tool in kubectl virtctl h2kvmctl; do
        if command -v "$tool" &>/dev/null; then
            info "$tool: $(which $tool)"
        else
            warn "$tool: NOT FOUND"
        fi
    done

    echo ""
    info "K3s:"
    kubectl get nodes 2>/dev/null || warn "  Not running"
    echo ""
    info "KubeVirt:"
    kubectl get kubevirt -n kubevirt 2>/dev/null || warn "  Not installed"
    echo ""
    info "CDI:"
    kubectl get cdi -n cdi 2>/dev/null || warn "  Not installed"
    echo ""
    info "VMs:"
    kubectl get vm,vmi 2>/dev/null || warn "  None"
}

# ── Main ──
main() {
    echo ""
    echo "hyper2kvm K3s + KubeVirt Setup"
    echo ""

    [ "$DRY_RUN" = "true" ] && warn "DRY RUN — no changes will be made"

    case "${1:-}" in
        --cleanup)
            cleanup
            ;;
        --verify)
            verify
            ;;
        --demo)
            preflight
            install_k3s
            install_kubevirt
            install_cdi
            install_virtctl
            setup_firewall
            run_demo
            ;;
        ""|--all)
            preflight
            install_k3s
            install_kubevirt
            install_cdi
            install_virtctl
            setup_firewall
            verify
            echo ""
            info "K3s + KubeVirt ready! ($(elapsed))"
            echo ""
            echo "  Next:"
            echo "    sudo $0 --demo            # run demo migration"
            echo "    kubectl get nodes          # check cluster"
            echo "    kubectl get vm,vmi         # check VMs"
            echo ""
            ;;
        --help|-h)
            echo "Usage: sudo $0 [--demo|--cleanup|--verify|--help]"
            echo ""
            echo "Env: KUBEVIRT_VERSION  CDI_VERSION  DEMO_NAME  DRY_RUN"
            exit 0
            ;;
        *)
            echo "Usage: sudo $0 [--demo|--cleanup|--verify]"
            exit 1
            ;;
    esac
}

main "$@"
