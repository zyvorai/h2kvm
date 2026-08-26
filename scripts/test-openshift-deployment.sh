#!/bin/bash
# Test hyper2kvm operator deployment on OpenShift
# This script validates the deployment and runs basic tests
# Usage: ./scripts/test-openshift-deployment.sh [NAMESPACE]

set -e

NAMESPACE="${1:-hyper2kvm-system}"

# Color output

echo_info() {
    echo "ℹ $1"
}

echo_success() {
    echo "✓ $1"
}

echo_warning() {
    echo "⚠ $1"
}

echo_error() {
    echo "✗ $1"
}

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

run_test() {
    local test_name="$1"
    local test_command="$2"

    echo_info "Testing: ${test_name}"

    if bash -c "${test_command}" &> /dev/null; then
        echo_success "PASS: ${test_name}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        echo_error "FAIL: ${test_name}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

echo ""
echo_info "=== OpenShift Deployment Test Suite ==="
echo_info "Namespace: ${NAMESPACE}"
echo ""

# Test 1: Check if oc is available
run_test "OpenShift CLI (oc) installed" "command -v oc"

# Test 2: Check if logged in
run_test "Logged in to OpenShift" "oc whoami"

# Test 3: Check namespace exists
run_test "Namespace '${NAMESPACE}' exists" "oc get namespace ${NAMESPACE}"

# Test 4: Check CRDs are installed
echo ""
echo_info "=== CRD Tests ==="
run_test "MigrationJob CRD installed" "oc get crd migrationjobs.hyper2kvm.io"
run_test "JobTemplate CRD installed" "oc get crd jobtemplates.hyper2kvm.io"

# Test 5: Check operator pod
echo ""
echo_info "=== Operator Pod Tests ==="
run_test "Operator pod exists" "oc get pods -n ${NAMESPACE} -l app.kubernetes.io/name=hyper2kvm-operator"
run_test "Operator pod is running" "oc get pods -n ${NAMESPACE} -l app.kubernetes.io/name=hyper2kvm-operator -o jsonpath='{.items[0].status.phase}' | grep -q Running"

# Test 6: Check webhook pod (if enabled)
echo ""
echo_info "=== Webhook Pod Tests ==="
if oc get pods -n ${NAMESPACE} -l app.kubernetes.io/component=webhook &> /dev/null; then
    run_test "Webhook pod exists" "oc get pods -n ${NAMESPACE} -l app.kubernetes.io/component=webhook"
    run_test "Webhook pod is running" "oc get pods -n ${NAMESPACE} -l app.kubernetes.io/component=webhook -o jsonpath='{.items[0].status.phase}' | grep -q Running"
else
    echo_warning "Webhook pods not found (may not be enabled)"
fi

# Test 7: Check services
echo ""
echo_info "=== Service Tests ==="
run_test "Operator service exists" "oc get svc -n ${NAMESPACE} -l app.kubernetes.io/name=hyper2kvm-operator"

# Test 8: Check routes (OpenShift specific)
echo ""
echo_info "=== Route Tests ==="
if oc get route -n ${NAMESPACE} &> /dev/null; then
    run_test "Routes exist" "oc get route -n ${NAMESPACE}"

    # Test metrics route
    if oc get route hyper2kvm-operator-metrics -n ${NAMESPACE} &> /dev/null; then
        METRICS_ROUTE=$(oc get route hyper2kvm-operator-metrics -n ${NAMESPACE} -o jsonpath='{.spec.host}')
        echo_info "Metrics route: https://${METRICS_ROUTE}"
        run_test "Metrics route accessible" "curl -k -s -o /dev/null -w '%{http_code}' https://${METRICS_ROUTE}/healthz | grep -q 200"
    fi
else
    echo_warning "Routes not found (may not be enabled)"
fi

# Test 9: Check SecurityContextConstraints
echo ""
echo_info "=== SecurityContextConstraints Tests ==="
if oc get scc hyper2kvm-worker-scc &> /dev/null; then
    run_test "Worker SCC exists" "oc get scc hyper2kvm-worker-scc"
else
    echo_warning "Worker SCC not found (may need manual creation)"
fi

# Test 10: Check RBAC
echo ""
echo_info "=== RBAC Tests ==="
run_test "ServiceAccount exists" "oc get sa -n ${NAMESPACE} hyper2kvm-operator"
run_test "ClusterRole exists" "oc get clusterrole | grep -q hyper2kvm-operator"
run_test "ClusterRoleBinding exists" "oc get clusterrolebinding | grep -q hyper2kvm-operator"

# Test 11: Create a test MigrationJob
echo ""
echo_info "=== MigrationJob CRD Test ==="
echo_info "Creating test MigrationJob..."

cat > /tmp/test-migrationjob.yaml <<EOF
apiVersion: hyper2kvm.io/v1alpha1
kind: MigrationJob
metadata:
  name: test-job-$(date +%s)
  namespace: ${NAMESPACE}
spec:
  operation: inspect
  image:
    path: /data/test.vmdk
    format: vmdk
  priority: 50
EOF

if oc apply -f /tmp/test-migrationjob.yaml &> /dev/null; then
    echo_success "Test MigrationJob created"
    TESTS_PASSED=$((TESTS_PASSED + 1))

    # Wait a bit and check status
    sleep 2
    JOB_NAME=$(oc get migrationjobs -n ${NAMESPACE} -o jsonpath='{.items[0].metadata.name}' --sort-by=.metadata.creationTimestamp 2>/dev/null | tail -1)

    if oc get migrationjob ${JOB_NAME} -n ${NAMESPACE} &> /dev/null; then
        echo_success "Test MigrationJob exists and is tracked"
        TESTS_PASSED=$((TESTS_PASSED + 1))

        # Cleanup
        oc delete migrationjob ${JOB_NAME} -n ${NAMESPACE} &> /dev/null
        echo_info "Test MigrationJob cleaned up"
    else
        echo_error "Test MigrationJob not found"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
else
    echo_error "Failed to create test MigrationJob"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Test 12: Check operator logs for errors
echo ""
echo_info "=== Operator Logs Test ==="
OPERATOR_POD=$(oc get pods -n ${NAMESPACE} -l app.kubernetes.io/name=hyper2kvm-operator -o jsonpath='{.items[0].metadata.name}')

if [ -n "${OPERATOR_POD}" ]; then
    echo_info "Checking operator logs for errors..."
    ERROR_COUNT=$(oc logs -n ${NAMESPACE} ${OPERATOR_POD} --tail=100 | grep -i error | wc -l)

    if [ ${ERROR_COUNT} -eq 0 ]; then
        echo_success "No errors in operator logs"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        echo_warning "Found ${ERROR_COUNT} error(s) in operator logs"
        echo_info "Recent errors:"
        oc logs -n ${NAMESPACE} ${OPERATOR_POD} --tail=100 | grep -i error | tail -5
    fi
fi

# Test 13: Check resource usage
echo ""
echo_info "=== Resource Usage Test ==="
echo_info "Operator pod resource usage:"
oc top pod -n ${NAMESPACE} -l app.kubernetes.io/name=hyper2kvm-operator 2>/dev/null || echo_warning "Metrics server not available"

# Summary
echo ""
echo_info "=== Test Summary ==="
echo_success "Tests passed: ${TESTS_PASSED}"
if [ ${TESTS_FAILED} -gt 0 ]; then
    echo_error "Tests failed: ${TESTS_FAILED}"
else
    echo_success "Tests failed: ${TESTS_FAILED}"
fi

TOTAL_TESTS=$((TESTS_PASSED + TESTS_FAILED))
if [ "$TOTAL_TESTS" -gt 0 ]; then
    SUCCESS_RATE=$((TESTS_PASSED * 100 / TOTAL_TESTS))
else
    SUCCESS_RATE=0
fi

echo ""
echo_info "Success rate: ${SUCCESS_RATE}%"

if [ ${TESTS_FAILED} -eq 0 ]; then
    echo ""
    echo_success "=== All Tests Passed! ==="
    echo_info "Operator is deployed and functioning correctly"
    exit 0
else
    echo ""
    echo_error "=== Some Tests Failed ==="
    echo_info "Review the failures above and check:"
    echo "  - Operator logs: oc logs -n ${NAMESPACE} -l app.kubernetes.io/name=hyper2kvm-operator"
    echo "  - Pod status: oc describe pod -n ${NAMESPACE} -l app.kubernetes.io/name=hyper2kvm-operator"
    echo "  - Events: oc get events -n ${NAMESPACE} --sort-by='.lastTimestamp'"
    exit 1
fi
