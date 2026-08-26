#!/bin/bash
#
# Ubuntu End-to-End Kubernetes Test Workflow
# Automated workflow for testing Ubuntu VM migration in Kubernetes
#

set -euo pipefail

# Configuration
AUTO_CONFIRM="${AUTO_CONFIRM:-false}"
CLUSTER_NAME="${CLUSTER_NAME:-h2kvm-test}"
NAMESPACE_OPERATOR="${NAMESPACE_OPERATOR:-h2kvm-system}"
NAMESPACE_WORKERS="${NAMESPACE_WORKERS:-h2kvm-workers}"
NAMESPACE_TEST="${NAMESPACE_TEST:-h2kvm-test}"
UBUNTU_VMDK="${UBUNTU_VMDK:-${VM_IMAGE:-/home/ssahani/Downloads/VM-Images/ubuntu/ubuntu.vmdk}}"
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

# Source common functions from CentOS script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/test-centos9-e2e-k8s.sh" ]; then
    source "${SCRIPT_DIR}/test-centos9-e2e-k8s.sh"
fi

# Override VMDK path for Ubuntu
CENTOS9_VMDK="${UBUNTU_VMDK}"

# Override migration job creation for Ubuntu
create_migration_job() {
    log_section "Step 9: Create Ubuntu MigrationJob"

    log_info "Applying Ubuntu E2E test MigrationJob..."

    if kubectl apply -f k8s/examples/ubuntu-e2e-test.yaml > /dev/null; then
        log_success "MigrationJob created"
    else
        log_error "Failed to create MigrationJob"
        exit 1
    fi

    sleep 3

    log_info "Verifying MigrationJob status..."
    kubectl get migrationjob -n "${NAMESPACE_TEST}" ubuntu-e2e-test -o wide
}

# Override upload function for Ubuntu
upload_test_data() {
    log_section "Step 8: Upload Ubuntu Test Data"

    if [ ! -f "${UBUNTU_VMDK}" ]; then
        log_warning "Ubuntu VMDK not found at: ${UBUNTU_VMDK}"
        log_warning "E2E test will validate deployment only (no actual migration)"
        return 0
    fi

    log_info "Finding a running worker pod..."
    WORKER_POD=$(kubectl get pods -n "${NAMESPACE_WORKERS}" -l app=h2kvm-worker --field-selector status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [ -z "${WORKER_POD}" ]; then
        log_warning "No worker pod found, skipping data upload"
        return 0
    fi

    log_info "Creating input directory in worker pod..."
    kubectl exec -n "${NAMESPACE_WORKERS}" "${WORKER_POD}" -- sudo mkdir -p /data/input 2>/dev/null || true
    kubectl exec -n "${NAMESPACE_WORKERS}" "${WORKER_POD}" -- sudo chmod 777 /data/input 2>/dev/null || true

    log_info "Uploading Ubuntu VMDK to worker pod..."
    if kubectl cp "${UBUNTU_VMDK}" "${NAMESPACE_WORKERS}/${WORKER_POD}:/data/input/ubuntu.vmdk"; then
        log_success "Test data uploaded successfully"
        kubectl exec -n "${NAMESPACE_WORKERS}" "${WORKER_POD}" -- ls -lh /data/input/
    else
        log_warning "Failed to upload test data"
    fi
}

# Override monitor function for Ubuntu
monitor_job() {
    log_section "Step 10: Monitor Ubuntu Job Progress"

    log_info "MigrationJob Status:"
    kubectl describe migrationjob -n "${NAMESPACE_TEST}" ubuntu-e2e-test | grep -A 20 "Status:"

    echo ""
    log_info "Operator Logs (last 20 lines):"
    kubectl logs -n "${NAMESPACE_OPERATOR}" -l app=h2kvm-operator --tail=20 | grep -i ubuntu || true

    echo ""
    log_info "Worker Pods Status:"
    kubectl get pods -n "${NAMESPACE_WORKERS}" -o wide

    if kubectl get pods -n "${NAMESPACE_WORKERS}" -l app=h2kvm-worker &> /dev/null; then
        echo ""
        log_info "Worker Logs (last 20 lines):"
        kubectl logs -n "${NAMESPACE_WORKERS}" -l app=h2kvm-worker --tail=20 || true
    fi
}

# Override report function for Ubuntu
generate_report() {
    log_section "Step 11: Test Report"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📊 Ubuntu Kubernetes E2E Test Report"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    echo "📦 Infrastructure Status:"
    echo "  • Operator: $(kubectl get pods -n "${NAMESPACE_OPERATOR}" -l app=h2kvm-operator -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo 'Not Found')"
    echo "  • Workers:  $(kubectl get pods -n "${NAMESPACE_WORKERS}" -l app=h2kvm-worker --no-headers 2>/dev/null | wc -l) pod(s)"
    echo "  • CRDs:     $(kubectl get crd | grep h2kvm.io | wc -l) installed"

    echo ""
    echo "🔄 MigrationJob Status:"
    JOB_STATE=$(kubectl get migrationjob -n "${NAMESPACE_TEST}" ubuntu-e2e-test -o jsonpath='{.status.state}' 2>/dev/null || echo 'Not Found')
    echo "  • State: ${JOB_STATE}"

    echo ""
    echo "📝 Next Steps:"
    if [ "${JOB_STATE}" = "Validated" ]; then
        echo "  ✅ Job validated successfully!"
        echo "  📌 To execute migration:"
        echo "     1. Ensure worker pods are Running with correct image"
        echo "     2. Upload Ubuntu VMDK to /data/input/ubuntu.vmdk in worker pod"
        echo "     3. Monitor: kubectl get migrationjobs -n ${NAMESPACE_TEST} -w"
    elif [ "${JOB_STATE}" = "Running" ]; then
        echo "  🔄 Migration in progress..."
        echo "  📌 Monitor logs: kubectl logs -n ${NAMESPACE_WORKERS} -l app=h2kvm-worker -f"
    elif [ "${JOB_STATE}" = "Completed" ]; then
        echo "  🎉 Migration completed successfully!"
    else
        echo "  ⚠️  Check job status: kubectl describe migrationjob -n ${NAMESPACE_TEST} ubuntu-e2e-test"
    fi

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# Override cleanup for Ubuntu
cleanup_test() {
    log_section "Cleanup (Optional)"

    read -p "Do you want to cleanup test resources? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Deleting test resources..."
        kubectl delete migrationjob -n "${NAMESPACE_TEST}" ubuntu-e2e-test --timeout=30s 2>/dev/null || true
        log_success "Cleanup completed"
    else
        log_info "Cleanup skipped"
    fi
}

# Main execution
main() {
    log_section "Ubuntu Kubernetes E2E Test Workflow"
    log_info "Starting automated E2E test workflow for Ubuntu..."
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
    log_success "Ubuntu E2E test workflow completed!"
}

# Run main function
main "$@"
