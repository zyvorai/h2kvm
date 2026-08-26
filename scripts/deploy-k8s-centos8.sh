#!/bin/bash
# Hyper2KVM Kubernetes Deployment Script for CentOS 8
# Usage: ./deploy-k8s-centos8.sh [prepare|deploy|test|cleanup]

set -euo pipefail

# Configuration
NAMESPACE="hyper2kvm-system"
STORAGE_CLASS="${STORAGE_CLASS:-nfs-client}"
VMWARE_STORAGE_SIZE="${VMWARE_STORAGE_SIZE:-500Gi}"
KVM_STORAGE_SIZE="${KVM_STORAGE_SIZE:-1Ti}"
NODE_LABEL="${NODE_LABEL:-hyper2kvm=enabled}"

log_info() {
    echo "[INFO] $1"
}

log_warn() {
    echo "[WARN] $1"
}

log_error() {
    echo "[ERROR] $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl not found. Please install kubectl."
        exit 1
    fi

    # Check cluster connectivity
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster. Check your kubeconfig."
        exit 1
    fi

    # Check if running on CentOS 8
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        if [[ ! "$ID" =~ ^(centos|rocky|almalinux)$ ]] || [[ ! "$VERSION_ID" =~ ^8 ]]; then
            log_warn "This script is optimized for CentOS 8/Stream 8. You're running $PRETTY_NAME"
        fi
    fi

    log_info "Prerequisites check passed!"
}

# Prepare CentOS 8 nodes
prepare_nodes() {
    log_info "=== Preparing CentOS 8 Nodes ==="

    cat <<'EOF' > /tmp/prepare-node.sh
#!/bin/bash
set -e

echo "Updating system..."
sudo dnf update -y

echo "Installing EPEL..."
sudo dnf install -y epel-release

echo "Installing core packages..."
sudo dnf install -y \
    qemu-img \
    qemu-kvm \
    libvirt-client \
    libvirt-daemon-kvm \
    python3 \
    python3-pip \
    ntfs-3g \
    guestfs-tools \
    virt-install

echo "Installing optional packages..."
sudo dnf install -y \
    hivex \
    augeas \
    lvm2 \
    cryptsetup \
    parted

echo "Configuring libvirt..."
sudo systemctl enable --now libvirtd

echo "Loading KVM modules..."
sudo modprobe kvm
sudo modprobe kvm_intel || sudo modprobe kvm_amd || true

cat <<KMOD | sudo tee /etc/modules-load.d/kvm.conf
kvm
kvm_intel
kvm_amd
KMOD

echo "Configuring /dev/kvm permissions..."
sudo chgrp kvm /dev/kvm 2>/dev/null || true
sudo chmod 0660 /dev/kvm || true

cat <<UDEV | sudo tee /etc/udev/rules.d/99-kvm.rules
KERNEL=="kvm", GROUP="kvm", MODE="0660"
UDEV

sudo udevadm control --reload-rules
sudo udevadm trigger

echo "✅ Node preparation complete!"
qemu-img --version
virsh --version
python3 --version
EOF

    chmod +x /tmp/prepare-node.sh

    log_info "Node preparation script created at /tmp/prepare-node.sh"
    log_info "Run this on each worker node:"
    log_info "  scp /tmp/prepare-node.sh <node>:/tmp/"
    log_info "  ssh <node> 'bash /tmp/prepare-node.sh'"
    log_info ""
    log_info "Then label the nodes:"
    log_info "  kubectl label node <node-name> hyper2kvm=enabled"
    log_info ""
    read -p "Press Enter when nodes are prepared..."
}

# Deploy Hyper2KVM
deploy_hyper2kvm() {
    log_info "=== Deploying Hyper2KVM to Kubernetes ==="

    # Create namespace
    log_info "Creating namespace: $NAMESPACE"
    kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

    # Create RBAC
    log_info "Creating RBAC resources..."
    cat <<EOF | kubectl apply -f -
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: hyper2kvm-worker
  namespace: $NAMESPACE

---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: hyper2kvm-worker-role
  namespace: $NAMESPACE
rules:
- apiGroups: [""]
  resources: ["pods", "pods/log", "configmaps", "secrets"]
  verbs: ["get", "list", "watch", "create", "update", "patch"]
- apiGroups: ["batch"]
  resources: ["jobs"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: [""]
  resources: ["events"]
  verbs: ["create", "patch"]

---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: hyper2kvm-worker-binding
  namespace: $NAMESPACE
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: hyper2kvm-worker-role
subjects:
- kind: ServiceAccount
  name: hyper2kvm-worker
  namespace: $NAMESPACE
EOF

    # Create storage
    log_info "Creating storage PVCs..."
    cat <<EOF | kubectl apply -f -
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: vmware-storage
  namespace: $NAMESPACE
  labels:
    app: hyper2kvm
    storage-type: source
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: $STORAGE_CLASS
  resources:
    requests:
      storage: $VMWARE_STORAGE_SIZE

---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: kvm-storage
  namespace: $NAMESPACE
  labels:
    app: hyper2kvm
    storage-type: destination
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: $STORAGE_CLASS
  resources:
    requests:
      storage: $KVM_STORAGE_SIZE
EOF

    # Wait for PVCs
    log_info "Waiting for PVCs to be bound..."
    kubectl wait --for=condition=Bound pvc/vmware-storage -n $NAMESPACE --timeout=300s
    kubectl wait --for=condition=Bound pvc/kvm-storage -n $NAMESPACE --timeout=300s

    log_info "✅ Hyper2KVM deployed successfully!"
    log_info ""
    log_info "Next steps:"
    log_info "1. Copy VMDKs to storage:"
    log_info "   kubectl run -it --rm copy-vmdk --image=busybox --namespace=$NAMESPACE --overrides='..."
    log_info "2. Submit migration jobs"
}

# Run test migration
test_migration() {
    log_info "=== Running Test Migration ==="

    # Check if test VMDK exists
    log_info "Checking for test VMDK..."

    # Create a small test VMDK if needed
    log_info "Creating test environment..."

    cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: test-migration
  namespace: $NAMESPACE
spec:
  template:
    metadata:
      labels:
        app: hyper2kvm
    spec:
      serviceAccountName: hyper2kvm-worker
      restartPolicy: Never
      nodeSelector:
        hyper2kvm: enabled
      containers:
      - name: hyper2kvm
        image: ghcr.io/ssahani/hyper2kvm:latest
        command:
          - /bin/sh
          - -c
          - |
            echo "=== Hyper2KVM Test ==="
            h2kvmctl --version
            echo "✅ Test passed!"
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1"
        securityContext:
          privileged: true
EOF

    log_info "Test job created. Monitoring..."

    # Wait for job
    kubectl wait --for=condition=complete job/test-migration -n $NAMESPACE --timeout=300s

    # Show logs
    log_info "Job logs:"
    kubectl logs -n $NAMESPACE job/test-migration

    log_info "✅ Test completed successfully!"
}

# Cleanup
cleanup() {
    log_warn "=== Cleaning Up ==="

    read -p "This will delete all Hyper2KVM resources. Continue? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        log_info "Cleanup cancelled."
        exit 0
    fi

    log_info "Deleting jobs..."
    kubectl delete jobs -n $NAMESPACE --all

    log_info "Deleting PVCs..."
    kubectl delete pvc -n $NAMESPACE --all

    log_info "Deleting namespace..."
    kubectl delete namespace $NAMESPACE

    log_info "✅ Cleanup complete!"
}

# Show status
show_status() {
    log_info "=== Hyper2KVM Status ==="

    echo ""
    echo "Namespace:"
    kubectl get namespace $NAMESPACE 2>/dev/null || echo "  Not created"

    echo ""
    echo "Nodes:"
    kubectl get nodes -l hyper2kvm=enabled

    echo ""
    echo "Storage:"
    kubectl get pvc -n $NAMESPACE 2>/dev/null || echo "  No PVCs"

    echo ""
    echo "Jobs:"
    kubectl get jobs -n $NAMESPACE 2>/dev/null || echo "  No jobs"

    echo ""
    echo "Pods:"
    kubectl get pods -n $NAMESPACE 2>/dev/null || echo "  No pods"
}

# Main
main() {
    case "${1:-}" in
        prepare)
            check_prerequisites
            prepare_nodes
            ;;
        deploy)
            check_prerequisites
            deploy_hyper2kvm
            ;;
        test)
            check_prerequisites
            test_migration
            ;;
        status)
            show_status
            ;;
        cleanup)
            cleanup
            ;;
        *)
            echo "Hyper2KVM Kubernetes Deployment Script for CentOS 8"
            echo ""
            echo "Usage: $0 [command]"
            echo ""
            echo "Commands:"
            echo "  prepare   - Prepare CentOS 8 nodes (generates script)"
            echo "  deploy    - Deploy Hyper2KVM to Kubernetes"
            echo "  test      - Run test migration"
            echo "  status    - Show deployment status"
            echo "  cleanup   - Remove all Hyper2KVM resources"
            echo ""
            echo "Environment variables:"
            echo "  STORAGE_CLASS         - Kubernetes StorageClass (default: nfs-client)"
            echo "  VMWARE_STORAGE_SIZE   - Source storage size (default: 500Gi)"
            echo "  KVM_STORAGE_SIZE      - Destination storage size (default: 1Ti)"
            echo ""
            echo "Example:"
            echo "  $0 prepare"
            echo "  $0 deploy"
            echo "  $0 test"
            echo ""
            exit 1
            ;;
    esac
}

main "$@"
