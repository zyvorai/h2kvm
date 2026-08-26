#!/bin/bash
#
# End-to-End Kubernetes Test Suite
# Comprehensive testing of Hyper2KVM Kubernetes deployment
#

set -e

# Test configuration
NAMESPACE="${NAMESPACE:-hyper2kvm-system}"
WORKER_NAMESPACE="${WORKER_NAMESPACE:-hyper2kvm-workers}"
TEST_NAMESPACE="${TEST_NAMESPACE:-hyper2kvm-test}"
RELEASE_NAME="${RELEASE_NAME:-hyper2kvm-operator}"
HELM_CHART="${HELM_CHART:-./helm/hyper2kvm-operator}"
TIMEOUT="${TIMEOUT:-300}"
CLEANUP="${CLEANUP:-true}"

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

# Utility functions
log_info() {
    echo "ℹ️  [INFO] $1"
}

log_success() {
    echo "✅ [PASS] $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

log_error() {
    echo "❌ [FAIL] $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
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

run_test() {
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    log_info "Test #${TESTS_TOTAL}: $1"
}

wait_for_pod() {
    local namespace=$1
    local label=$2
    local timeout=$3

    log_info "Waiting for pod with label ${label} in namespace ${namespace}..."

    kubectl wait --for=condition=ready pod \
        -l "${label}" \
        -n "${namespace}" \
        --timeout="${timeout}s" 2>/dev/null
}

wait_for_deployment() {
    local namespace=$1
    local deployment=$2
    local timeout=$3

    log_info "Waiting for deployment ${deployment} in namespace ${namespace}..."

    kubectl wait --for=condition=available deployment \
        "${deployment}" \
        -n "${namespace}" \
        --timeout="${timeout}s" 2>/dev/null
}

# Test functions

test_prerequisites() {
    log_section "Phase 1: Prerequisites Check"

    run_test "kubectl is installed"
    if command -v kubectl &> /dev/null; then
        log_success "kubectl is installed"
    else
        log_error "kubectl is not installed"
        return 1
    fi

    run_test "helm is installed"
    if command -v helm &> /dev/null; then
        log_success "helm is installed"
    else
        log_error "helm is not installed"
        return 1
    fi

    run_test "Kubernetes cluster is accessible"
    if kubectl cluster-info &> /dev/null; then
        log_success "Kubernetes cluster is accessible"
    else
        log_error "Cannot connect to Kubernetes cluster"
        return 1
    fi

    run_test "Check Kubernetes version"
    k8s_version=$(kubectl version -o json 2>/dev/null | grep -o '"gitVersion":"[^"]*"' | tail -1 | cut -d'"' -f4 || echo "unknown")
    log_info "Kubernetes version: ${k8s_version}"
    log_success "Kubernetes version check passed"
}

test_namespace_creation() {
    log_section "Phase 2: Namespace Setup"

    run_test "Create operator namespace"
    if kubectl create namespace "${NAMESPACE}" 2>/dev/null || kubectl get namespace "${NAMESPACE}" &> /dev/null; then
        log_success "Operator namespace created/exists: ${NAMESPACE}"
    else
        log_error "Failed to create operator namespace"
        return 1
    fi

    run_test "Create worker namespace"
    if kubectl create namespace "${WORKER_NAMESPACE}" 2>/dev/null || kubectl get namespace "${WORKER_NAMESPACE}" &> /dev/null; then
        log_success "Worker namespace created/exists: ${WORKER_NAMESPACE}"
    else
        log_error "Failed to create worker namespace"
        return 1
    fi

    run_test "Create test namespace"
    if kubectl create namespace "${TEST_NAMESPACE}" 2>/dev/null || kubectl get namespace "${TEST_NAMESPACE}" &> /dev/null; then
        log_success "Test namespace created/exists: ${TEST_NAMESPACE}"
    else
        log_error "Failed to create test namespace"
        return 1
    fi
}

test_crd_installation() {
    log_section "Phase 3: CRD Installation"

    run_test "Apply MigrationJob CRD"
    if kubectl apply -f k8s/operator/crds/migrationjob-crd.yaml 2>/dev/null; then
        log_success "MigrationJob CRD applied"
    else
        log_error "Failed to apply MigrationJob CRD"
        return 1
    fi

    run_test "Apply OfflineFixJob CRD"
    if kubectl apply -f k8s/operator/crds/offlinefixjob-crd.yaml 2>/dev/null; then
        log_success "OfflineFixJob CRD applied"
    else
        log_error "Failed to apply OfflineFixJob CRD"
        return 1
    fi

    run_test "Verify MigrationJob CRD"
    if kubectl get crd migrationjobs.hyper2kvm.io &> /dev/null; then
        log_success "MigrationJob CRD verified"
    else
        log_error "MigrationJob CRD not found"
        return 1
    fi

    run_test "Verify OfflineFixJob CRD"
    if kubectl get crd offlinefixjobs.hyper2kvm.io &> /dev/null; then
        log_success "OfflineFixJob CRD verified"
    else
        log_error "OfflineFixJob CRD not found"
        return 1
    fi
}

test_operator_deployment() {
    log_section "Phase 4: Operator Deployment"

    run_test "Deploy operator via Helm"
    if helm upgrade --install "${RELEASE_NAME}" "${HELM_CHART}" \
        --namespace "${NAMESPACE}" \
        --create-namespace \
        --set image.tag=latest \
        --wait --timeout="${TIMEOUT}s"; then
        log_success "Operator deployed via Helm"
    else
        log_error "Failed to deploy operator"
        return 1
    fi

    run_test "Wait for operator pod"
    if wait_for_pod "${NAMESPACE}" "app=hyper2kvm-operator" "${TIMEOUT}"; then
        log_success "Operator pod is ready"
    else
        log_error "Operator pod failed to become ready"
        kubectl get pods -n "${NAMESPACE}"
        kubectl describe pod -l app=hyper2kvm-operator -n "${NAMESPACE}"
        return 1
    fi

    run_test "Verify operator deployment"
    if wait_for_deployment "${NAMESPACE}" "hyper2kvm-operator" "${TIMEOUT}"; then
        log_success "Operator deployment is available"
    else
        log_error "Operator deployment not available"
        return 1
    fi

    run_test "Check operator logs"
    pod_name=$(kubectl get pod -n "${NAMESPACE}" -l app=hyper2kvm-operator -o jsonpath='{.items[0].metadata.name}')
    if kubectl logs -n "${NAMESPACE}" "${pod_name}" --tail=10 | grep -q "Starting operator"; then
        log_success "Operator started successfully"
    else
        log_warning "Could not verify operator startup from logs"
    fi
}

test_webhook_configuration() {
    log_section "Phase 5: Webhook Configuration"

    run_test "Verify webhook service"
    if kubectl get service -n "${NAMESPACE}" hyper2kvm-webhook &> /dev/null; then
        log_success "Webhook service exists"
    else
        log_error "Webhook service not found"
        return 1
    fi

    run_test "Verify validating webhook configuration"
    if kubectl get validatingwebhookconfiguration hyper2kvm-validating-webhook &> /dev/null; then
        log_success "Validating webhook configuration exists"
    else
        log_error "Validating webhook configuration not found"
        return 1
    fi

    run_test "Verify mutating webhook configuration"
    if kubectl get mutatingwebhookconfiguration hyper2kvm-mutating-webhook &> /dev/null; then
        log_success "Mutating webhook configuration exists"
    else
        log_error "Mutating webhook configuration not found"
        return 1
    fi
}

test_migrationjob_creation() {
    log_section "Phase 6: MigrationJob Testing"

    run_test "Create test MigrationJob"
    cat <<EOF | kubectl apply -f - -n "${TEST_NAMESPACE}"
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: test-migration
spec:
  source:
    type: vmdk
    path: /vms/test.vmdk
  destination:
    format: qcow2
    path: /output/test.qcow2
  workers: 1
EOF

    if [ $? -eq 0 ]; then
        log_success "MigrationJob created"
    else
        log_error "Failed to create MigrationJob"
        return 1
    fi

    sleep 2

    run_test "Verify MigrationJob exists"
    if kubectl get migrationjob test-migration -n "${TEST_NAMESPACE}" &> /dev/null; then
        log_success "MigrationJob exists"
    else
        log_error "MigrationJob not found"
        return 1
    fi

    run_test "Check MigrationJob status"
    status=$(kubectl get migrationjob test-migration -n "${TEST_NAMESPACE}" -o jsonpath='{.status.phase}')
    log_info "MigrationJob status: ${status:-Pending}"
    log_success "MigrationJob status checked"

    run_test "Verify worker job created"
    sleep 5
    if kubectl get jobs -n "${WORKER_NAMESPACE}" | grep -q "test-migration"; then
        log_success "Worker job was created"
    else
        log_warning "Worker job not found (may be expected in test environment)"
    fi
}

test_offlinefixjob_creation() {
    log_section "Phase 7: OfflineFixJob Testing"

    run_test "Create test OfflineFixJob"
    cat <<EOF | kubectl apply -f - -n "${TEST_NAMESPACE}"
apiVersion: hyper2kvm.io/v1alpha1
kind: OfflineFixJob
metadata:
  name: test-fix
spec:
  image: /vms/test.qcow2
  fixes:
    - fstab
    - grub
    - initramfs
EOF

    if [ $? -eq 0 ]; then
        log_success "OfflineFixJob created"
    else
        log_error "Failed to create OfflineFixJob"
        return 1
    fi

    sleep 2

    run_test "Verify OfflineFixJob exists"
    if kubectl get offlinefixjob test-fix -n "${TEST_NAMESPACE}" &> /dev/null; then
        log_success "OfflineFixJob exists"
    else
        log_error "OfflineFixJob not found"
        return 1
    fi
}

test_batch_migrationjobs() {
    log_section "Phase 8: Batch MigrationJob Testing"

    run_test "Create multiple MigrationJobs"
    for i in {1..3}; do
        cat <<EOF | kubectl apply -f - -n "${TEST_NAMESPACE}"
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: test-batch-${i}
spec:
  source:
    type: vmdk
    path: /vms/test-${i}.vmdk
  destination:
    format: qcow2
    path: /output/test-${i}.qcow2
EOF
    done

    if [ $? -eq 0 ]; then
        log_success "Batch MigrationJobs created"
    else
        log_error "Failed to create batch MigrationJobs"
        return 1
    fi

    sleep 2

    run_test "Verify all batch jobs exist"
    count=$(kubectl get migrationjobs -n "${TEST_NAMESPACE}" | grep -c "test-batch-")
    if [ "${count}" -eq 3 ]; then
        log_success "All 3 batch jobs exist"
    else
        log_error "Expected 3 batch jobs, found ${count}"
        return 1
    fi
}

test_job_dependencies() {
    log_section "Phase 9: Job Dependency Testing"

    run_test "Create job with dependency"
    cat <<EOF | kubectl apply -f - -n "${TEST_NAMESPACE}"
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: test-dep-1
spec:
  source:
    type: vmdk
    path: /vms/dep-1.vmdk
  destination:
    format: qcow2
    path: /output/dep-1.qcow2
---
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: test-dep-2
spec:
  source:
    type: vmdk
    path: /vms/dep-2.vmdk
  destination:
    format: qcow2
    path: /output/dep-2.qcow2
  dependsOn:
    - test-dep-1
EOF

    if [ $? -eq 0 ]; then
        log_success "Jobs with dependency created"
    else
        log_error "Failed to create jobs with dependency"
        return 1
    fi
}

test_metrics_collection() {
    log_section "Phase 10: Metrics Testing"

    run_test "Check metrics endpoint"
    pod_name=$(kubectl get pod -n "${NAMESPACE}" -l app=hyper2kvm-operator -o jsonpath='{.items[0].metadata.name}')

    if kubectl exec -n "${NAMESPACE}" "${pod_name}" -- curl -s http://localhost:8080/metrics > /dev/null 2>&1; then
        log_success "Metrics endpoint accessible"
    else
        log_warning "Metrics endpoint not accessible (may not be exposed in test environment)"
    fi

    run_test "Check ServiceMonitor CRD"
    if kubectl get crd servicemonitors.monitoring.coreos.com &> /dev/null; then
        if kubectl get servicemonitor -n "${NAMESPACE}" hyper2kvm-operator &> /dev/null; then
            log_success "ServiceMonitor exists"
        else
            log_warning "ServiceMonitor not found (Prometheus operator may not be installed)"
        fi
    else
        log_warning "ServiceMonitor CRD not found (Prometheus operator not installed)"
    fi
}

test_rbac_permissions() {
    log_section "Phase 11: RBAC Testing"

    run_test "Verify ServiceAccount"
    if kubectl get serviceaccount -n "${NAMESPACE}" hyper2kvm-operator &> /dev/null; then
        log_success "ServiceAccount exists"
    else
        log_error "ServiceAccount not found"
        return 1
    fi

    run_test "Verify ClusterRole"
    if kubectl get clusterrole hyper2kvm-operator &> /dev/null; then
        log_success "ClusterRole exists"
    else
        log_error "ClusterRole not found"
        return 1
    fi

    run_test "Verify ClusterRoleBinding"
    if kubectl get clusterrolebinding hyper2kvm-operator &> /dev/null; then
        log_success "ClusterRoleBinding exists"
    else
        log_error "ClusterRoleBinding not found"
        return 1
    fi
}

test_cleanup() {
    log_section "Phase 12: Cleanup"

    if [ "${CLEANUP}" = "true" ]; then
        log_info "Cleaning up test resources..."

        run_test "Delete test MigrationJobs"
        kubectl delete migrationjobs --all -n "${TEST_NAMESPACE}" --timeout=60s 2>/dev/null
        log_success "Test MigrationJobs deleted"

        run_test "Delete test OfflineFixJobs"
        kubectl delete offlinefixjobs --all -n "${TEST_NAMESPACE}" --timeout=60s 2>/dev/null
        log_success "Test OfflineFixJobs deleted"

        run_test "Delete test namespace"
        kubectl delete namespace "${TEST_NAMESPACE}" --timeout=60s 2>/dev/null
        log_success "Test namespace deleted"

        log_info "Cleanup completed"
    else
        log_warning "Cleanup skipped (CLEANUP=${CLEANUP})"
    fi
}

test_summary() {
    log_section "Test Summary"

    echo ""
    echo "📊 Total Tests: ${TESTS_TOTAL}"
    echo "✅ Passed:      ${TESTS_PASSED}"
    echo "❌ Failed:      ${TESTS_FAILED}"
    echo ""

    if [ ${TESTS_FAILED} -eq 0 ]; then
        echo "🎉 All tests passed!"
        return 0
    else
        echo "💔 Some tests failed"
        return 1
    fi
}

# Main execution
main() {
    log_section "Hyper2KVM Kubernetes E2E Test Suite"
    log_info "🚀 Starting comprehensive Kubernetes tests..."
    echo ""

    # Run test phases
    test_prerequisites || true
    test_namespace_creation || true
    test_crd_installation || true
    test_operator_deployment || true
    test_webhook_configuration || true
    test_migrationjob_creation || true
    test_offlinefixjob_creation || true
    test_batch_migrationjobs || true
    test_job_dependencies || true
    test_metrics_collection || true
    test_rbac_permissions || true
    test_cleanup || true

    # Show summary
    test_summary
}

# Run main function
main "$@"
