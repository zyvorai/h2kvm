#!/bin/bash
#
# Master E2E Test Runner - Fully Automated
# Intelligently runs only necessary steps, skipping what's already done
#

set -e

# Configuration
CLUSTER_NAME="${CLUSTER_NAME:-h2kvm-test}"
NAMESPACE_OPERATOR="${NAMESPACE_OPERATOR:-h2kvm-system}"
NAMESPACE_WORKERS="${NAMESPACE_WORKERS:-h2kvm-workers}"
NAMESPACE_TEST="${NAMESPACE_TEST:-h2kvm-test}"
CENTOS9_VMDK="${CENTOS9_VMDK:-/home/ssahani/Downloads/VM-Images/centos/centos9.vmdk}"
PUSH_TO_GHCR="${PUSH_TO_GHCR:-false}"
FORCE_REBUILD="${FORCE_REBUILD:-false}"
AUTO_CLEANUP="${AUTO_CLEANUP:-false}"

# Source the detailed workflow script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/test-centos9-e2e-k8s.sh"

# Override functions for intelligent checking

# Smart image build - only if needed
smart_build_images() {
    log_section "Smart Image Build Check"

    if [ "${FORCE_REBUILD}" = "true" ]; then
        log_info "Force rebuild enabled"
        build_and_push_images
        return 0
    fi

    # Check if image exists locally
    if docker image inspect h2kvm:worker &> /dev/null; then
        log_success "Worker image already exists locally"

        # Check age of image
        IMAGE_AGE=$(docker image inspect h2kvm:worker --format '{{.Created}}')
        log_info "Image created: ${IMAGE_AGE}"

        read -p "Rebuild image? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            build_and_push_images
        else
            log_info "Using existing image"
        fi
    else
        log_info "Worker image not found, building..."
        build_and_push_images
    fi
}

# Smart deployment - only deploy what's missing
smart_deploy() {
    log_section "Smart Deployment Check"

    # Check CRDs
    if ! kubectl get crd migrationjobs.h2kvm.io &> /dev/null; then
        log_info "CRDs not found, deploying..."
        deploy_crds
    else
        log_success "CRDs already installed"
    fi

    # Check namespaces
    local need_ns=false
    for ns in "${NAMESPACE_OPERATOR}" "${NAMESPACE_WORKERS}" "${NAMESPACE_TEST}"; do
        if ! kubectl get namespace "${ns}" &> /dev/null; then
            need_ns=true
            break
        fi
    done

    if [ "${need_ns}" = "true" ]; then
        create_namespaces
    else
        log_success "All namespaces already exist"
    fi

    # Check node labels
    local unlabeled=$(kubectl get nodes -o json | jq -r '.items[] | select(.metadata.labels["h2kvm.io/worker-enabled"] != "true") | .metadata.name' | wc -l)
    if [ "${unlabeled}" -gt 0 ]; then
        log_info "${unlabeled} nodes need labeling"
        label_nodes
    else
        log_success "All nodes already labeled"
    fi

    # Check worker deployment
    if ! kubectl get daemonset h2kvm-worker -n "${NAMESPACE_WORKERS}" &> /dev/null; then
        log_info "Worker DaemonSet not found, deploying..."
        deploy_workers
    else
        log_success "Worker DaemonSet already exists"

        # Check if pods are running
        RUNNING_WORKERS=$(kubectl get pods -n "${NAMESPACE_WORKERS}" -l app=h2kvm-worker --field-selector status.phase=Running --no-headers 2>/dev/null | wc -l)
        if [ "${RUNNING_WORKERS}" -eq 0 ]; then
            log_warning "Worker pods exist but not running, redeploying..."
            kubectl delete daemonset h2kvm-worker -n "${NAMESPACE_WORKERS}" --ignore-not-found=true
            deploy_workers
        else
            log_success "${RUNNING_WORKERS} worker pod(s) running"
        fi
    fi
}

# Smart job creation - only if not exists
smart_create_job() {
    log_section "Smart Job Creation Check"

    if kubectl get migrationjob centos9-e2e-test -n "${NAMESPACE_TEST}" &> /dev/null; then
        log_success "MigrationJob already exists"

        JOB_STATE=$(kubectl get migrationjob centos9-e2e-test -n "${NAMESPACE_TEST}" -o jsonpath='{.status.state}' 2>/dev/null || echo 'Unknown')
        log_info "Current state: ${JOB_STATE}"

        if [ "${JOB_STATE}" = "Completed" ] || [ "${JOB_STATE}" = "Failed" ]; then
            read -p "Job ${JOB_STATE}. Recreate? [y/N] " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                kubectl delete migrationjob centos9-e2e-test -n "${NAMESPACE_TEST}"
                create_migration_job
            fi
        fi
    else
        log_info "MigrationJob not found, creating..."
        create_migration_job
    fi
}

# Smart data upload - only if VMDK exists and not uploaded
smart_upload_data() {
    log_section "Smart Data Upload Check"

    if [ ! -f "${CENTOS9_VMDK}" ]; then
        log_warning "CentOS 9 VMDK not found, skipping upload"
        return 0
    fi

    WORKER_POD=$(kubectl get pods -n "${NAMESPACE_WORKERS}" -l app=h2kvm-worker --field-selector status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [ -z "${WORKER_POD}" ]; then
        log_warning "No running worker pod found, skipping data upload"
        return 0
    fi

    # Check if file already exists in pod
    if kubectl exec -n "${NAMESPACE_WORKERS}" "${WORKER_POD}" -- test -f /data/input/centos9.vmdk 2>/dev/null; then
        REMOTE_SIZE=$(kubectl exec -n "${NAMESPACE_WORKERS}" "${WORKER_POD}" -- stat -c %s /data/input/centos9.vmdk 2>/dev/null || echo "0")
        LOCAL_SIZE=$(stat -c %s "${CENTOS9_VMDK}" 2>/dev/null || echo "0")

        if [ "${REMOTE_SIZE}" = "${LOCAL_SIZE}" ]; then
            log_success "Test data already uploaded (${REMOTE_SIZE} bytes)"
            return 0
        else
            log_info "File exists but size mismatch, re-uploading..."
        fi
    fi

    upload_test_data
}

# Continuous monitoring
monitor_until_complete() {
    log_section "Continuous Monitoring"

    log_info "Monitoring job progress (Ctrl+C to exit)..."

    while true; do
        JOB_STATE=$(kubectl get migrationjob centos9-e2e-test -n "${NAMESPACE_TEST}" -o jsonpath='{.status.state}' 2>/dev/null || echo 'NotFound')

        echo -ne "\r⏱️  Job State: ${JOB_STATE}    "

        if [ "${JOB_STATE}" = "Completed" ]; then
            echo ""
            log_success "Migration completed successfully!"
            break
        elif [ "${JOB_STATE}" = "Failed" ]; then
            echo ""
            log_error "Migration failed!"
            kubectl describe migrationjob centos9-e2e-test -n "${NAMESPACE_TEST}"
            break
        elif [ "${JOB_STATE}" = "NotFound" ]; then
            echo ""
            log_error "Job not found!"
            break
        fi

        sleep 5
    done
}

# Auto cleanup
auto_cleanup() {
    if [ "${AUTO_CLEANUP}" = "true" ]; then
        log_section "Auto Cleanup"
        log_info "Cleaning up test resources..."
        kubectl delete migrationjob centos9-e2e-test -n "${NAMESPACE_TEST}" --timeout=30s 2>/dev/null || true
        log_success "Cleanup completed"
    fi
}

# Main execution with intelligence
main() {
    log_section "Intelligent E2E Test Runner"
    log_info "Checking existing infrastructure and running only necessary steps..."
    echo ""

    check_prerequisites
    smart_build_images
    load_image_k3d
    smart_deploy
    smart_upload_data
    smart_create_job
    monitor_job

    # Ask for continuous monitoring
    echo ""
    read -p "Start continuous monitoring? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        monitor_until_complete
    fi

    generate_report
    auto_cleanup

    echo ""
    log_success "All done! Run this script again anytime - it will only do what's needed."
}

# Handle interrupts gracefully
trap 'echo ""; log_warning "Interrupted by user"; exit 130' INT TERM

# Run main
main "$@"
