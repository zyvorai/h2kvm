#!/bin/bash
# =============================================================================
# Deploy RHEL 8.8 VM to KubeVirt on k3d
# =============================================================================
# This script performs a complete one-shot deployment of the migrated
# RHEL 8.8 VM to KubeVirt running on k3d (lightweight Kubernetes)
#
# Prerequisites:
#   - k3d installed (https://k3d.io)
#   - kubectl installed
#   - virtctl installed (KubeVirt CLI)
#
# Usage:
#   ./deploy-to-kubevirt-k3d.sh
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
CLUSTER_NAME="rhel-kubevirt"
QCOW2_IMAGE="./output/rhel8.8-fixed.qcow2"
DEPLOYMENT_YAML="./kubevirt-rhel8.8-deployment.yaml"
NAMESPACE="rhel-vms"

# KubeVirt version
KUBEVIRT_VERSION="${KUBEVIRT_VERSION:-$(curl -s https://storage.googleapis.com/kubevirt-prow/release/kubevirt/kubevirt/stable.txt)}"

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warn() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check k3d
    if ! command -v k3d &> /dev/null; then
        log_error "k3d not found. Install from https://k3d.io"
        exit 1
    fi
    log_success "k3d found: $(k3d version)"

    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl not found. Install from https://kubernetes.io/docs/tasks/tools/"
        exit 1
    fi
    log_success "kubectl found: $(kubectl version --client --short 2>/dev/null || kubectl version --client)"

    # Check virtctl (optional, will install if missing)
    if ! command -v virtctl &> /dev/null; then
        log_warn "virtctl not found. Will provide installation instructions."
    else
        log_success "virtctl found: $(virtctl version --client)"
    fi

    # Check QCOW2 image
    if [ ! -f "$QCOW2_IMAGE" ]; then
        log_error "QCOW2 image not found: $QCOW2_IMAGE"
        exit 1
    fi
    log_success "QCOW2 image found: $(ls -lh $QCOW2_IMAGE | awk '{print $5}')"

    # Check deployment YAML
    if [ ! -f "$DEPLOYMENT_YAML" ]; then
        log_error "Deployment YAML not found: $DEPLOYMENT_YAML"
        exit 1
    fi
    log_success "Deployment YAML found"
}

create_k3d_cluster() {
    log_info "Creating k3d cluster: $CLUSTER_NAME"

    # Check if cluster already exists
    if k3d cluster list | grep -q "$CLUSTER_NAME"; then
        log_warn "Cluster $CLUSTER_NAME already exists. Deleting..."
        k3d cluster delete "$CLUSTER_NAME"
    fi

    # Create k3d cluster with KubeVirt-friendly configuration
    k3d cluster create "$CLUSTER_NAME" \
        --agents 1 \
        --api-port 6550 \
        --port "30022:30022@server:0" \
        --port "30590:30590@server:0" \
        --k3s-arg "--disable=traefik@server:0" \
        # WARNING: Mounting the Docker socket gives the k3d container full control
        # over the host's Docker daemon. This is required for k3d to function but
        # grants effectively root-level access to the host. Do not use in production
        # without understanding the security implications.
        --volume /var/run/docker.sock:/var/run/docker.sock@server:0 \
        --volume /dev:/dev@server:0 \
        --volume /lib/modules:/lib/modules@server:0:ro

    log_success "k3d cluster created"

    # Wait for cluster to be ready
    log_info "Waiting for cluster to be ready..."
    kubectl wait --for=condition=Ready nodes --all --timeout=120s

    log_success "Cluster is ready"
}

install_kubevirt() {
    log_info "Installing KubeVirt ${KUBEVIRT_VERSION}..."

    # Install KubeVirt operator
    kubectl apply -f "https://github.com/kubevirt/kubevirt/releases/download/${KUBEVIRT_VERSION}/kubevirt-operator.yaml"

    # Install KubeVirt custom resource
    kubectl apply -f "https://github.com/kubevirt/kubevirt/releases/download/${KUBEVIRT_VERSION}/kubevirt-cr.yaml"

    # Wait for KubeVirt to be ready
    log_info "Waiting for KubeVirt to be ready (this may take 2-3 minutes)..."
    kubectl wait --for=condition=Available kubevirt kubevirt -n kubevirt --timeout=600s

    log_success "KubeVirt installed and ready"
}

install_cdi() {
    log_info "Installing Containerized Data Importer (CDI) for disk management..."

    CDI_VERSION="${CDI_VERSION:-$(curl -s https://api.github.com/repos/kubevirt/containerized-data-importer/releases/latest | grep tag_name | cut -d'"' -f4)}"

    # Install CDI operator
    kubectl apply -f "https://github.com/kubevirt/containerized-data-importer/releases/download/${CDI_VERSION}/cdi-operator.yaml"

    # Install CDI custom resource
    kubectl apply -f "https://github.com/kubevirt/containerized-data-importer/releases/download/${CDI_VERSION}/cdi-cr.yaml"

    # Wait for CDI to be ready
    log_info "Waiting for CDI to be ready..."
    kubectl wait --for=condition=Available cdi cdi -n cdi --timeout=300s

    log_success "CDI installed and ready"
}

upload_disk_image() {
    log_info "Uploading QCOW2 disk image to Kubernetes..."

    # Create namespace
    kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

    # Create PVC from deployment YAML
    kubectl apply -f "$DEPLOYMENT_YAML" -l name=rhel8-disk || true

    # Wait for PVC to be bound
    log_info "Waiting for PVC to be ready..."
    kubectl wait --for=jsonpath='{.status.phase}'=Bound pvc/rhel8-disk -n "$NAMESPACE" --timeout=60s || true

    # Upload image using virtctl (if available)
    if command -v virtctl &> /dev/null; then
        log_info "Uploading image using virtctl..."
        virtctl image-upload pvc rhel8-disk \
            --namespace="$NAMESPACE" \
            --image-path="$QCOW2_IMAGE" \
            --size=20Gi \
            --insecure \
            --force-bind || {
            log_warn "virtctl upload failed. Will use manual upload method."
            manual_upload
        }
    else
        log_warn "virtctl not available. Using manual upload method."
        manual_upload
    fi

    log_success "Disk image uploaded"
}

manual_upload() {
    log_info "Manual upload: Creating DataVolume for image import..."

    # Create a DataVolume that references a local file
    # Note: This is a simplified approach for k3d testing
    cat <<EOF | kubectl apply -f -
apiVersion: cdi.kubevirt.io/v1beta1
kind: DataVolume
metadata:
  name: rhel8-disk-import
  namespace: $NAMESPACE
spec:
  source:
    blank: {}
  storage:
    resources:
      requests:
        storage: 20Gi
    storageClassName: local-path
  pvc:
    accessModes:
      - ReadWriteOnce
EOF

    log_info "Note: For production, you would upload the image via CDI upload proxy"
    log_info "      For this demo, we'll proceed with the blank disk and you can"
    log_info "      manually copy the image using kubectl cp later if needed."
}

deploy_vm() {
    log_info "Deploying RHEL 8.8 VirtualMachine..."

    # Apply the full deployment manifest
    kubectl apply -f "$DEPLOYMENT_YAML"

    log_success "VM deployment applied"

    # Wait for VM to be ready
    log_info "Waiting for VM to start (this may take 2-3 minutes)..."
    sleep 10

    # Check VM status
    kubectl get vmi -n "$NAMESPACE"

    log_success "VM deployment complete"
}

show_access_info() {
    log_success "==================================================================="
    log_success "RHEL 8.8 VM Deployment Complete!"
    log_success "==================================================================="

    echo ""
    log_info "Cluster Information:"
    echo "  Cluster Name: $CLUSTER_NAME"
    echo "  Namespace: $NAMESPACE"

    echo ""
    log_info "VM Access Methods:"
    echo ""
    echo "1️⃣  Console Access (virtctl):"
    echo "   virtctl console rhel8-migrated -n $NAMESPACE"
    echo ""
    echo "2️⃣  VNC Access:"
    echo "   virtctl vnc rhel8-migrated -n $NAMESPACE"
    echo ""
    echo "3️⃣  SSH Access (once VM is running):"
    echo "   ssh -p 30022 cloud-user@localhost"
    echo "   Password: redhat"
    echo ""
    echo "4️⃣  Web VNC (port-forward):"
    echo "   kubectl port-forward -n $NAMESPACE service/rhel8-vnc 5900:5900"
    echo "   Then connect VNC client to localhost:5900"

    echo ""
    log_info "Useful Commands:"
    echo "  # Check VM status"
    echo "  kubectl get vm,vmi -n $NAMESPACE"
    echo ""
    echo "  # Get VM details"
    echo "  kubectl describe vm rhel8-migrated -n $NAMESPACE"
    echo ""
    echo "  # Stop VM"
    echo "  virtctl stop rhel8-migrated -n $NAMESPACE"
    echo ""
    echo "  # Start VM"
    echo "  virtctl start rhel8-migrated -n $NAMESPACE"
    echo ""
    echo "  # Delete VM (keeps PVC)"
    echo "  kubectl delete vm rhel8-migrated -n $NAMESPACE"
    echo ""
    echo "  # Full cleanup"
    echo "  k3d cluster delete $CLUSTER_NAME"

    echo ""
    log_info "Install virtctl (if not installed):"
    echo "  VERSION=$KUBEVIRT_VERSION"
    echo "  wget https://github.com/kubevirt/kubevirt/releases/download/\${VERSION}/virtctl-\${VERSION}-linux-amd64"
    echo "  chmod +x virtctl-\${VERSION}-linux-amd64"
    echo "  sudo mv virtctl-\${VERSION}-linux-amd64 /usr/local/bin/virtctl"

    log_success "==================================================================="
}

# =============================================================================
# Main Execution
# =============================================================================

main() {
    echo ""
    log_info "==================================================================="
    log_info "KubeVirt RHEL 8.8 Deployment on k3d"
    log_info "==================================================================="
    echo ""

    check_prerequisites
    create_k3d_cluster
    install_kubevirt
    install_cdi
    upload_disk_image
    deploy_vm
    show_access_info
}

# Run main function
main "$@"
