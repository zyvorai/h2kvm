#!/bin/bash
# Hyper2KVM K3s CentOS 9 Test Suite
# Tests migration of CentOS 9 VM to k3s cluster
#
# ⚠️  NOTE: This test script demonstrates MANUAL steps for educational purposes.
#
# 🚀 For production, use hyper2kvm's BUILT-IN automated deployment:
#     sudo ./h2kvmctl --config centos9.yaml --deploy-k8s
#
# The --deploy-k8s flag does ALL these steps automatically!
# See: docs/guides/k8s-automated-deployment.md
#
# Usage: ./test-k3s-centos9.sh [all|prereq|deploy|migrate|kubevirt|cleanup]

set -euo pipefail

# Configuration
AUTO_CONFIRM="${AUTO_CONFIRM:-false}"
NAMESPACE="hyper2kvm-test"
STORAGE_CLASS="${STORAGE_CLASS:-local-path}"  # k3s default
VM_NAME="centos9-test"
CONFIG_FILE="${CONFIG_FILE:-test-confs/test-centos9-k3s.yaml}"

# Test results tracking
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

# Helper functions
log_info() {
    echo "[INFO] $1"
}

log_success() {
    echo "[SUCCESS] $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

log_fail() {
    echo "[FAIL] $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

log_warn() {
    echo "[WARN] $1"
}

log_test() {
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    echo "[TEST $TESTS_TOTAL] $1"
}

# Test: Prerequisites
test_prerequisites() {
    log_info "=== Testing K3s Prerequisites ==="

    # Test 1: kubectl installed
    log_test "kubectl is installed"
    if command -v kubectl &> /dev/null; then
        KUBECTL_VERSION=$(kubectl version --client 2>&1 | head -1)
        log_success "kubectl found: $KUBECTL_VERSION"
    else
        log_fail "kubectl not found"
        return 1
    fi

    # Test 2: K3s cluster connectivity
    log_test "K3s cluster is accessible"
    if kubectl cluster-info &> /dev/null; then
        log_success "K3s cluster is accessible"
    else
        log_fail "Cannot connect to K3s cluster"
        log_info "Is k3s running? Try: sudo systemctl status k3s"
        return 1
    fi

    # Test 3: Cluster version
    log_test "Kubernetes version compatibility"
    K8S_VERSION=$(kubectl version -o json 2>/dev/null | grep gitVersion | head -1 | awk -F'"' '{print $4}')
    log_info "Kubernetes version: $K8S_VERSION"
    if [[ "$K8S_VERSION" =~ v1\.(2[4-9]|[3-9][0-9]) ]]; then
        log_success "Kubernetes version is compatible (>= 1.24)"
    else
        log_warn "Kubernetes version may not be tested: $K8S_VERSION"
    fi

    # Test 4: Admin permissions
    log_test "Cluster admin permissions"
    if kubectl auth can-i create namespace &> /dev/null; then
        log_success "User has cluster admin permissions"
    else
        log_fail "User does not have sufficient permissions"
        log_info "Try: export KUBECONFIG=/etc/rancher/k3s/k3s.yaml"
        return 1
    fi

    # Test 5: Check storage class
    log_test "StorageClass '$STORAGE_CLASS' exists"
    if kubectl get storageclass "$STORAGE_CLASS" &> /dev/null; then
        log_success "StorageClass found: $STORAGE_CLASS"
    else
        log_fail "StorageClass not found: $STORAGE_CLASS"
        log_info "Available StorageClasses:"
        kubectl get storageclass
        return 1
    fi

    # Test 6: Check for hyper2kvm CLI
    log_test "hyper2kvm CLI is available"
    # Prefer local development build
    if [ -x "./h2kvmctl" ]; then
        H2KVM_CMD="./h2kvmctl"
        H2KVM_VERSION=$(./h2kvmctl --version 2>&1 | grep -i version || echo "local build")
        log_success "h2kvmctl found (local): $H2KVM_VERSION"
    elif command -v h2kvmctl &> /dev/null; then
        H2KVM_CMD="h2kvmctl"
        H2KVM_VERSION=$(h2kvmctl --version 2>&1 | grep -i version || echo "installed")
        log_success "h2kvmctl found: $H2KVM_VERSION"
    else
        log_fail "h2kvmctl not found"
        log_info "Install with: pip install -e ."
        return 1
    fi

    # Test 7: Check for source VMDK
    log_test "Source CentOS 9 VMDK exists"
    VMDK_PATH="${VM_IMAGE:-/home/ssahani/Downloads/VM-Images/centos/centos9.vmdk}"
    if [ -f "$VMDK_PATH" ]; then
        VMDK_SIZE=$(du -h "$VMDK_PATH" | cut -f1)
        log_success "Source VMDK found: $VMDK_SIZE"
    else
        log_fail "Source VMDK not found: $VMDK_PATH"
        return 1
    fi

    # Test 8: Check node resources
    log_test "Node resources sufficient"
    TOTAL_CPU=$(kubectl get nodes -o json | jq '[.items[].status.capacity.cpu | tonumber] | add' 2>/dev/null || echo "0")
    TOTAL_MEM=$(kubectl get nodes -o json | jq '[.items[].status.capacity.memory | gsub("Ki";"") | tonumber] | add' 2>/dev/null || echo "0")
    TOTAL_MEM_GB=$((TOTAL_MEM / 1024 / 1024))

    log_info "Total cluster resources: ${TOTAL_CPU} CPUs, ${TOTAL_MEM_GB}GB RAM"
    if [ "$TOTAL_CPU" -ge 2 ] && [ "$TOTAL_MEM_GB" -ge 4 ]; then
        log_success "Cluster has sufficient resources"
    else
        log_warn "Cluster may have insufficient resources (recommended: 2+ CPUs, 4+ GB RAM)"
    fi
}

# Test: Deployment
test_deployment() {
    log_info "=== Testing Namespace and RBAC Setup ==="

    # Test 1: Create namespace
    log_test "Create test namespace"
    if kubectl create namespace $NAMESPACE &> /dev/null; then
        log_success "Namespace created: $NAMESPACE"
    else
        log_warn "Namespace already exists (cleaning up first)"
        kubectl delete namespace $NAMESPACE --wait=true &> /dev/null || true
        sleep 2
        kubectl create namespace $NAMESPACE
        log_success "Namespace recreated: $NAMESPACE"
    fi

    # Test 2: Create PVC for output
    log_test "Create PVC for migrated VM"
    cat <<EOF | kubectl apply -f - &> /dev/null
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: centos9-disk
  namespace: $NAMESPACE
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: $STORAGE_CLASS
  resources:
    requests:
      storage: 10Gi
EOF

    if [ $? -eq 0 ]; then
        log_success "PVC created"

        # Note: local-path uses WaitForFirstConsumer, so PVC won't bind until a pod uses it
        log_info "PVC created (will bind when first pod uses it - this is normal for local-path)"
    else
        log_fail "Failed to create PVC"
        return 1
    fi
}

# Test: Migration
test_migration() {
    log_info "=== Testing CentOS 9 VM Migration ==="

    log_test "Run local migration with hyper2kvm"

    # Run migration locally (requires root for mounting disk images)
    log_info "Running migration (this may take a few minutes)..."
    log_info "Using CLI: $H2KVM_CMD"
    log_warn "Migration requires root permissions for disk mounting"
    if sudo $H2KVM_CMD --config "$CONFIG_FILE"; then
        log_success "Migration completed successfully!"

        # Show output
        if [ -f "out/centos9-k3s-test/centos9.qcow2" ]; then
            OUTPUT_SIZE=$(du -h "out/centos9-k3s-test/centos9.qcow2" | cut -f1)
            log_info "Output QCOW2 size: $OUTPUT_SIZE"
        fi

        # Show report
        if [ -f "out/centos9-k3s-test/migration-report.md" ]; then
            log_info "Migration report generated:"
            echo ""
            head -30 "out/centos9-k3s-test/migration-report.md"
            echo ""
        fi
    else
        log_fail "Migration failed"
        log_info "Check logs: out/centos9-k3s-test/migration.log"
        return 1
    fi
}

# Test: Upload to K3s
test_upload() {
    log_info "=== Uploading to K3s Cluster ==="

    log_test "Upload QCOW2 to PVC"

    # Create a temporary upload pod
    cat <<EOF | kubectl apply -f - &> /dev/null
apiVersion: v1
kind: Pod
metadata:
  name: disk-uploader
  namespace: $NAMESPACE
spec:
  restartPolicy: Never
  containers:
  - name: uploader
    image: alpine
    command: ["sleep", "3600"]
    volumeMounts:
    - name: disk
      mountPath: /disk
  volumes:
  - name: disk
    persistentVolumeClaim:
      claimName: centos9-disk
EOF

    if [ $? -ne 0 ]; then
        log_fail "Failed to create uploader pod"
        return 1
    fi

    # Wait for pod to be ready (this will also trigger PVC binding)
    log_info "Waiting for uploader pod (this will bind the PVC)..."
    if kubectl wait --for=condition=Ready pod/disk-uploader -n $NAMESPACE --timeout=120s &> /dev/null; then
        log_success "Uploader pod ready and PVC bound"
    else
        log_fail "Uploader pod failed to become ready"
        kubectl get pod disk-uploader -n $NAMESPACE
        kubectl get pvc -n $NAMESPACE
        kubectl delete pod disk-uploader -n $NAMESPACE &> /dev/null || true
        return 1
    fi

    # Copy QCOW2 to PVC
    log_info "Copying QCOW2 to PVC (this may take a while)..."
    if kubectl cp out/centos9-k3s-test/centos9.qcow2 $NAMESPACE/disk-uploader:/disk/disk.img &> /dev/null; then
        log_success "QCOW2 uploaded to PVC"
    else
        log_fail "Failed to upload QCOW2"
        kubectl delete pod disk-uploader -n $NAMESPACE &> /dev/null || true
        return 1
    fi

    # Cleanup uploader pod
    kubectl delete pod disk-uploader -n $NAMESPACE &> /dev/null || true
}

# Test: KubeVirt VM Creation
test_kubevirt() {
    log_info "=== Testing KubeVirt VM Creation ==="

    # Check if KubeVirt is installed
    log_test "KubeVirt is installed"
    if kubectl get crd virtualmachineinstances.kubevirt.io &> /dev/null; then
        log_success "KubeVirt CRDs found"
    else
        log_warn "KubeVirt not installed - skipping VM creation"
        log_info "To install KubeVirt on k3s:"
        log_info "  kubectl apply -f https://github.com/kubevirt/kubevirt/releases/download/v1.1.0/kubevirt-operator.yaml"
        log_info "  kubectl apply -f https://github.com/kubevirt/kubevirt/releases/download/v1.1.0/kubevirt-cr.yaml"
        return 0
    fi

    log_test "Create VirtualMachine resource"
    cat <<EOF | kubectl apply -f - &> /dev/null
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: $VM_NAME
  namespace: $NAMESPACE
spec:
  running: false
  template:
    metadata:
      labels:
        kubevirt.io/vm: $VM_NAME
    spec:
      domain:
        devices:
          disks:
          - name: rootdisk
            disk:
              bus: virtio
          interfaces:
          - name: default
            masquerade: {}
        resources:
          requests:
            memory: 2Gi
            cpu: 2
      networks:
      - name: default
        pod: {}
      volumes:
      - name: rootdisk
        persistentVolumeClaim:
          claimName: centos9-disk
EOF

    if [ $? -eq 0 ]; then
        log_success "VirtualMachine resource created"
        log_info "To start the VM: kubectl virt start $VM_NAME -n $NAMESPACE"
        log_info "To access console: kubectl virt console $VM_NAME -n $NAMESPACE"
    else
        log_fail "Failed to create VirtualMachine resource"
        return 1
    fi
}

# Test: Cleanup
test_cleanup() {
    log_info "=== Cleaning Up Test Resources ==="

    log_test "Delete test namespace"
    if kubectl delete namespace $NAMESPACE --wait=true --timeout=300s &> /dev/null; then
        log_success "Test namespace deleted"
    else
        log_warn "Failed to delete namespace (may require manual cleanup)"
    fi

    log_test "Remove local output directory"
    if [ -d "out/centos9-k3s-test" ]; then
        if [ "$AUTO_CONFIRM" = "true" ]; then
            remove="y"
        else
            read -p "Remove local output directory out/centos9-k3s-test? (y/n): " remove
        fi
        if [ "$remove" = "y" ]; then
            rm -rf out/centos9-k3s-test
            log_success "Local output directory removed"
        fi
    fi
}

# Generate test report
generate_report() {
    echo ""
    echo "=========================================="
    echo "   HYPER2KVM K3S CENTOS 9 TEST REPORT"
    echo "=========================================="
    echo ""
    echo "Date: $(date)"
    echo "K3s Version: $(kubectl version -o json 2>/dev/null | grep gitVersion | head -1 | awk -F'"' '{print $4}')"
    echo ""
    echo "Test Results:"
    echo "  Total Tests: $TESTS_TOTAL"
    echo "  Passed: $TESTS_PASSED"
    echo "  Failed: $TESTS_FAILED"
    echo ""

    if [ $TESTS_FAILED -eq 0 ]; then
        echo "✅ ALL TESTS PASSED!"
        echo ""
        echo "CentOS 9 migration to K3s successful!"
        echo ""
        echo "Next steps:"
        echo "1. Start the VM: kubectl virt start $VM_NAME -n $NAMESPACE"
        echo "2. Access console: kubectl virt console $VM_NAME -n $NAMESPACE"
        echo "3. Check VM status: kubectl get vmi -n $NAMESPACE"
        return 0
    else
        echo "❌ SOME TESTS FAILED"
        echo ""
        echo "Please review the failures above."
        return 1
    fi
}

# Main test runner
run_all_tests() {
    log_info "Starting Hyper2KVM K3s CentOS 9 Test Suite"
    echo ""

    test_prerequisites || return 1
    echo ""

    test_deployment || return 1
    echo ""

    test_migration || return 1
    echo ""

    test_upload || return 1
    echo ""

    test_kubevirt || true
    echo ""

    generate_report
}

# Command handlers
case "${1:-all}" in
    all)
        run_all_tests
        RESULT=$?
        if [ "$AUTO_CONFIRM" = "true" ]; then
            cleanup="y"
        else
            read -p "Clean up test resources? (y/n): " cleanup
        fi
        if [ "$cleanup" = "y" ]; then
            test_cleanup
        fi
        exit $RESULT
        ;;
    prereq)
        test_prerequisites
        ;;
    deploy)
        test_deployment
        ;;
    migrate)
        test_migration
        ;;
    upload)
        test_upload
        ;;
    kubevirt)
        test_kubevirt
        ;;
    cleanup)
        test_cleanup
        ;;
    *)
        echo "Hyper2KVM K3s CentOS 9 Test Suite"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  all       - Run all tests (default)"
        echo "  prereq    - Test prerequisites only"
        echo "  deploy    - Test K3s deployment setup only"
        echo "  migrate   - Run local migration only"
        echo "  upload    - Upload to K3s PVC only"
        echo "  kubevirt  - Create KubeVirt VM only"
        echo "  cleanup   - Clean up test resources"
        echo ""
        echo "Environment variables:"
        echo "  STORAGE_CLASS  - Kubernetes StorageClass (default: local-path)"
        echo "  CONFIG_FILE    - Migration config file (default: test-confs/test-centos9-k3s.yaml)"
        echo ""
        echo "Example:"
        echo "  $0 all"
        echo "  STORAGE_CLASS=longhorn $0 all"
        ;;
esac
