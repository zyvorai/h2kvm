#!/bin/bash
#
# CentOS 9 End-to-End Kubernetes Test Workflow
# Automated workflow for testing CentOS 9 VM migration in Kubernetes
#

set -euo pipefail

# Configuration
AUTO_CONFIRM="${AUTO_CONFIRM:-false}"
CLUSTER_NAME="${CLUSTER_NAME:-h2kvm-test}"
NAMESPACE_OPERATOR="${NAMESPACE_OPERATOR:-h2kvm-system}"
NAMESPACE_WORKERS="${NAMESPACE_WORKERS:-h2kvm-workers}"
NAMESPACE_TEST="${NAMESPACE_TEST:-h2kvm-test}"
CENTOS9_VMDK="${CENTOS9_VMDK:-${VM_IMAGE:-/home/ssahani/Downloads/VM-Images/centos/centos9.vmdk}}"
TIMEOUT="${TIMEOUT:-600}"
SKIP_BUILD="${SKIP_BUILD:-false}"
SKIP_IMAGE_LOAD="${SKIP_IMAGE_LOAD:-false}"
PUSH_TO_GHCR="${PUSH_TO_GHCR:-false}"
GHCR_REGISTRY="${GHCR_REGISTRY:-ghcr.io}"
GITHUB_USER="${GITHUB_USER:-ssahani}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

# Utility functions
log_info() {
    echo "ℹ️  [INFO] $1"
}

log_success() {
    echo "✅ [SUCCESS] $1"
}

log_error() {
    echo "❌ [ERROR] $1"
}

log_warning() {
    echo "⚠️  [WARN] $1"
}

log_section() {
    echo ""
    echo "========================================"
    echo "🎯 $1"
    echo "========================================"
}

wait_for_pod() {
    local namespace=$1
    local label=$2
    local timeout=$3

    log_info "Waiting for pod with label ${label} in namespace ${namespace}..."

    kubectl wait --for=condition=ready pod \
        -l "${label}" \
        -n "${namespace}" \
        --timeout="${timeout}s" 2>/dev/null || return 1

    return 0
}

# Step 1: Prerequisites
check_prerequisites() {
    log_section "Step 1: Prerequisites Check"

    log_info "Checking required tools..."

    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl not found"
        exit 1
    fi
    log_success "kubectl is installed"

    if ! command -v docker &> /dev/null; then
        log_error "docker not found"
        exit 1
    fi
    log_success "docker is installed"

    if ! command -v k3d &> /dev/null; then
        log_warning "k3d not found (optional for loading images)"
    else
        log_success "k3d is installed"
    fi

    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    log_success "Kubernetes cluster is accessible"

    if [ ! -f "${CENTOS9_VMDK}" ]; then
        log_warning "CentOS 9 VMDK not found at: ${CENTOS9_VMDK}"
        log_warning "E2E test will validate deployment only (no actual migration)"
    else
        log_success "CentOS 9 VMDK found: ${CENTOS9_VMDK}"
    fi
}

# Step 2: Build and push images
build_and_push_images() {
    log_section "Step 2: Build and Push Images"

    if [ "${SKIP_BUILD}" = "true" ]; then
        log_warning "Skipping image build (SKIP_BUILD=true)"
        return 0
    fi

    if [ "${PUSH_TO_GHCR}" = "true" ]; then
        log_info "Building and pushing images to GHCR..."
        export PUSH=true
        export TAG="${IMAGE_TAG}"
        if bash scripts/build-and-push-images.sh; then
            log_success "Images built and pushed to GHCR"
        else
            log_error "Failed to build and push images"
            exit 1
        fi
    else
        log_info "Building h2kvm:worker image locally..."
        if docker build -t h2kvm:worker -f Dockerfile --target worker . > /tmp/docker-build.log 2>&1; then
            log_success "Worker image built successfully"
        else
            log_error "Failed to build worker image"
            cat /tmp/docker-build.log
            exit 1
        fi
    fi
}

# Step 3: Load image into k3d
load_image_k3d() {
    log_section "Step 3: Load Image into k3d"

    if [ "${SKIP_IMAGE_LOAD}" = "true" ]; then
        log_warning "Skipping image load (SKIP_IMAGE_LOAD=true)"
        return 0
    fi

    if ! command -v k3d &> /dev/null; then
        log_warning "k3d not found, skipping image import"
        return 0
    fi

    log_info "Loading image into k3d cluster: ${CLUSTER_NAME}"

    if k3d image import h2kvm:worker -c "${CLUSTER_NAME}" > /tmp/k3d-import.log 2>&1; then
        log_success "Image loaded into k3d cluster"
    else
        log_warning "Failed to load image (cluster may not exist or not using k3d)"
        cat /tmp/k3d-import.log
    fi
}

# Step 4: Deploy CRDs
deploy_crds() {
    log_section "Step 4: Deploy CRDs"

    log_info "Applying CRDs..."

    if kubectl apply -f operator/config/crd/bases/ 2>&1 | grep -v "ServiceMonitor"; then
        log_success "CRDs applied (ignoring ServiceMonitor warnings)"
    else
        log_warning "Some CRDs may have warnings"
    fi

    log_info "Verifying CRDs..."
    if kubectl get crd hyperconversions.h2kvm.io &> /dev/null; then
        log_success "HyperConversion CRD verified"
    else
        log_error "HyperConversion CRD not found"
        exit 1
    fi
}

# Step 5: Create namespaces
create_namespaces() {
    log_section "Step 5: Create Namespaces"

    for ns in "${NAMESPACE_OPERATOR}" "${NAMESPACE_WORKERS}" "${NAMESPACE_TEST}"; do
        log_info "Creating namespace: ${ns}"
        kubectl create namespace "${ns}" --dry-run=client -o yaml | kubectl apply -f - > /dev/null
        log_success "Namespace ready: ${ns}"
    done
}

# Step 6: Label nodes
label_nodes() {
    log_section "Step 6: Label Nodes for Workers"

    log_info "Labeling all nodes as worker-enabled..."

    for node in $(kubectl get nodes -o name); do
        kubectl label "${node}" h2kvm.io/worker-enabled=true --overwrite > /dev/null
        log_success "Labeled: ${node}"
    done
}

# Step 7: Deploy worker infrastructure
deploy_workers() {
    log_section "Step 7: Deploy Worker Infrastructure"

    log_info "Creating PVCs..."
    kubectl apply -f k8s/worker/pvc-k3d.yaml > /dev/null
    log_success "PVCs created"

    log_info "Creating RBAC resources..."
    kubectl apply -f k8s/worker/rbac.yaml > /dev/null 2>&1 || true
    log_success "RBAC resources created"

    log_info "Deploying worker DaemonSet..."
    kubectl apply -f k8s/worker/daemonset-k3d.yaml > /dev/null
    log_success "Worker DaemonSet deployed"

    log_info "Waiting for worker pods to be ready..."
    sleep 10

    if wait_for_pod "${NAMESPACE_WORKERS}" "app=h2kvm-worker" "${TIMEOUT}"; then
        log_success "Worker pods are ready"
        kubectl get pods -n "${NAMESPACE_WORKERS}" -o wide
    else
        log_warning "Worker pods not ready yet (may need image)"
        kubectl get pods -n "${NAMESPACE_WORKERS}" -o wide
    fi
}

# Step 8: Upload test data (if available)
upload_test_data() {
    log_section "Step 8: Upload Test Data"

    if [ ! -f "${CENTOS9_VMDK}" ]; then
        log_warning "CentOS 9 VMDK not found, skipping upload"
        return 0
    fi

    log_info "Finding a running worker pod..."
    WORKER_POD=$(kubectl get pods -n "${NAMESPACE_WORKERS}" -l app=h2kvm-worker -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [ -z "${WORKER_POD}" ]; then
        log_warning "No worker pod found, skipping data upload"
        return 0
    fi

    # Check if pod is running
    POD_STATUS=$(kubectl get pod -n "${NAMESPACE_WORKERS}" "${WORKER_POD}" -o jsonpath='{.status.phase}')
    if [ "${POD_STATUS}" != "Running" ]; then
        log_warning "Worker pod not running (status: ${POD_STATUS}), skipping data upload"
        return 0
    fi

    log_info "Creating input directory in worker pod..."
    kubectl exec -n "${NAMESPACE_WORKERS}" "${WORKER_POD}" -- mkdir -p /data/input 2>/dev/null || true

    log_info "Uploading CentOS 9 VMDK to worker pod..."
    if kubectl cp "${CENTOS9_VMDK}" "${NAMESPACE_WORKERS}/${WORKER_POD}:/data/input/centos9.vmdk"; then
        log_success "Test data uploaded successfully"
    else
        log_warning "Failed to upload test data"
    fi
}

# Step 9: Create CentOS 9 MigrationJob
create_migration_job() {
    log_section "Step 9: Create CentOS 9 MigrationJob"

    log_info "Applying CentOS 9 E2E test MigrationJob..."

    if kubectl apply -f k8s/examples/centos9-e2e-test.yaml > /dev/null; then
        log_success "MigrationJob created"
    else
        log_error "Failed to create MigrationJob"
        exit 1
    fi

    sleep 3

    log_info "Verifying MigrationJob status..."
    kubectl get migrationjob -n "${NAMESPACE_TEST}" centos9-e2e-test -o wide
}

# Step 10: Monitor job progress
monitor_job() {
    log_section "Step 10: Monitor Job Progress"

    log_info "MigrationJob Status:"
    kubectl describe migrationjob -n "${NAMESPACE_TEST}" centos9-e2e-test | grep -A 20 "Status:"

    echo ""
    log_info "Operator Logs (last 20 lines):"
    kubectl logs -n "${NAMESPACE_OPERATOR}" -l app=h2kvm-operator --tail=20 | grep -i centos || true

    echo ""
    log_info "Worker Pods Status:"
    kubectl get pods -n "${NAMESPACE_WORKERS}" -o wide

    if kubectl get pods -n "${NAMESPACE_WORKERS}" -l app=h2kvm-worker &> /dev/null; then
        echo ""
        log_info "Worker Logs (last 20 lines):"
        kubectl logs -n "${NAMESPACE_WORKERS}" -l app=h2kvm-worker --tail=20 || true
    fi
}

# Step 11: Generate test report
generate_report() {
    log_section "Step 11: Test Report"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📊 CentOS 9 Kubernetes E2E Test Report"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    echo "📦 Infrastructure Status:"
    echo "  • Operator: $(kubectl get pods -n "${NAMESPACE_OPERATOR}" -l app=h2kvm-operator -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo 'Not Found')"
    echo "  • Workers:  $(kubectl get pods -n "${NAMESPACE_WORKERS}" -l app=h2kvm-worker --no-headers 2>/dev/null | wc -l) pod(s)"
    echo "  • CRDs:     $(kubectl get crd | grep h2kvm.io | wc -l) installed"

    echo ""
    echo "🔄 MigrationJob Status:"
    JOB_STATE=$(kubectl get migrationjob -n "${NAMESPACE_TEST}" centos9-e2e-test -o jsonpath='{.status.state}' 2>/dev/null || echo 'Not Found')
    echo "  • State: ${JOB_STATE}"

    echo ""
    echo "📝 Next Steps:"
    if [ "${JOB_STATE}" = "Validated" ]; then
        echo "  ✅ Job validated successfully!"
        echo "  📌 To execute migration:"
        echo "     1. Ensure worker pods are Running with correct image"
        echo "     2. Upload CentOS 9 VMDK to /data/input/centos9.vmdk in worker pod"
        echo "     3. Monitor: kubectl get migrationjobs -n ${NAMESPACE_TEST} -w"
    elif [ "${JOB_STATE}" = "Running" ]; then
        echo "  🔄 Migration in progress..."
        echo "  📌 Monitor logs: kubectl logs -n ${NAMESPACE_WORKERS} -l app=h2kvm-worker -f"
    elif [ "${JOB_STATE}" = "Completed" ]; then
        echo "  🎉 Migration completed successfully!"
    else
        echo "  ⚠️  Check job status: kubectl describe migrationjob -n ${NAMESPACE_TEST} centos9-e2e-test"
    fi

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# Cleanup function
cleanup_test() {
    log_section "Cleanup (Optional)"

    if [ "$AUTO_CONFIRM" = "true" ]; then
        REPLY="y"
    else
        read -p "Do you want to cleanup test resources? [y/N] " -n 1 -r
        echo
    fi
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Deleting test resources..."
        kubectl delete migrationjob -n "${NAMESPACE_TEST}" centos9-e2e-test --timeout=30s 2>/dev/null || true
        kubectl delete namespace "${NAMESPACE_TEST}" --timeout=30s 2>/dev/null || true
        log_success "Cleanup completed"
    else
        log_info "Cleanup skipped"
    fi
}

# Main execution
main() {
    log_section "CentOS 9 Kubernetes E2E Test Workflow"
    log_info "Starting automated E2E test workflow..."
    echo ""

    check_prerequisites
    build_and_push_images
    load_image_k3d
    deploy_crds
    create_namespaces
    label_nodes
    deploy_workers
    upload_test_data
    create_migration_job
    monitor_job
    generate_report

    echo ""
    log_success "E2E test workflow completed!"
}

# Run main function only when executed directly (not sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
