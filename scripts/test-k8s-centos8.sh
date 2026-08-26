#!/bin/bash
# Hyper2KVM Kubernetes CentOS 8 Test Suite
# Comprehensive testing and validation script
# Usage: ./test-k8s-centos8.sh [all|prereq|deploy|migrate|cleanup]

set -e

# Configuration
NAMESPACE="hyper2kvm-test"
TEST_VM_SIZE="100M"  # Small test VM
STORAGE_CLASS="${STORAGE_CLASS:-nfs-client}"

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
    log_info "=== Testing Prerequisites ==="

    # Test 1: kubectl installed
    log_test "kubectl is installed"
    if command -v kubectl &> /dev/null; then
        KUBECTL_VERSION=$(kubectl version --client -o json 2>/dev/null | grep -o '"gitVersion":"[^"]*"' | head -1 | cut -d'"' -f4 || kubectl version --client 2>/dev/null | head -1)
        log_success "kubectl found: $KUBECTL_VERSION"
    else
        log_fail "kubectl not found"
        return 1
    fi

    # Test 2: Cluster connectivity
    log_test "Kubernetes cluster is accessible"
    if kubectl cluster-info &> /dev/null; then
        log_success "Cluster is accessible"
    else
        log_fail "Cannot connect to Kubernetes cluster"
        return 1
    fi

    # Test 3: Cluster version
    log_test "Kubernetes version compatibility"
    K8S_VERSION=$(kubectl version -o json 2>/dev/null | grep -o '"gitVersion":"[^"]*"' | tail -1 | cut -d'"' -f4 || echo "unknown")
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
        return 1
    fi

    # Test 5: Check for CentOS 8 nodes
    log_test "CentOS 8 worker nodes available"
    CENTOS_NODES=$(kubectl get nodes -o json | jq -r '.items[] | select(.status.nodeInfo.osImage | test("CentOS.*8|Rocky.*8|AlmaLinux.*8")) | .metadata.name' 2>/dev/null || echo "")
    if [ -n "$CENTOS_NODES" ]; then
        log_success "Found CentOS 8-compatible nodes:"
        echo "$CENTOS_NODES" | while read node; do
            echo "  - $node"
        done
    else
        log_warn "No CentOS 8 nodes detected (may be running on other OS)"
        # Check node OS
        log_info "Available nodes:"
        kubectl get nodes -o custom-columns=NAME:.metadata.name,OS:.status.nodeInfo.osImage
    fi

    # Test 6: Check node resources
    log_test "Node resources sufficient"
    TOTAL_CPU=$(kubectl get nodes -o json | jq '[.items[].status.capacity.cpu | tonumber] | add' 2>/dev/null || echo "0")
    TOTAL_MEM=$(kubectl get nodes -o json | jq '[.items[].status.capacity.memory | gsub("Ki";"") | tonumber] | add' 2>/dev/null || echo "0")
    TOTAL_MEM_GB=$((TOTAL_MEM / 1024 / 1024))

    log_info "Total cluster resources: ${TOTAL_CPU} CPUs, ${TOTAL_MEM_GB}GB RAM"
    if [ "$TOTAL_CPU" -ge 4 ] && [ "$TOTAL_MEM_GB" -ge 8 ]; then
        log_success "Cluster has sufficient resources"
    else
        log_warn "Cluster may have insufficient resources (recommended: 4+ CPUs, 8+ GB RAM)"
    fi
}

# Test: Node preparation
test_node_preparation() {
    log_info "=== Testing Node Preparation ==="

    # Get a test node (preferably CentOS 8)
    TEST_NODE=$(kubectl get nodes -o json | jq -r '.items[0].metadata.name')
    log_info "Testing node: $TEST_NODE"

    # Test 1: KVM availability
    log_test "KVM is available on node"
    KVM_CHECK=$(kubectl run kvm-check-$RANDOM --image=alpine --rm -i --restart=Never \
        --overrides='{
            "spec": {
                "nodeSelector": {"kubernetes.io/hostname": "'$TEST_NODE'"},
                "containers": [{
                    "name": "kvm-check",
                    "image": "alpine",
                    "command": ["sh", "-c", "ls -l /dev/kvm 2>/dev/null && echo OK || echo MISSING"],
                    "securityContext": {"privileged": true},
                    "volumeMounts": [{
                        "name": "dev",
                        "mountPath": "/dev"
                    }]
                }],
                "volumes": [{
                    "name": "dev",
                    "hostPath": {"path": "/dev"}
                }]
            }
        }' 2>/dev/null || echo "MISSING")

    if echo "$KVM_CHECK" | grep -q "OK"; then
        log_success "KVM device is available"
    else
        log_fail "KVM device not found - node preparation needed"
        log_info "Run: ./scripts/deploy-k8s-centos8.sh prepare"
    fi

    # Test 2: qemu-img availability
    log_test "qemu-img is installed on node"
    QEMU_CHECK=$(kubectl run qemu-check-$RANDOM --image=ghcr.io/ssahani/hyper2kvm:latest --rm -i --restart=Never \
        --overrides='{
            "spec": {
                "nodeSelector": {"kubernetes.io/hostname": "'$TEST_NODE'"},
                "containers": [{
                    "name": "qemu-check",
                    "image": "ghcr.io/ssahani/hyper2kvm:latest",
                    "command": ["sh", "-c", "qemu-img --version && echo OK || echo MISSING"]
                }]
            }
        }' 2>/dev/null || echo "MISSING")

    if echo "$QEMU_CHECK" | grep -q "OK"; then
        log_success "qemu-img is available in container"
    else
        log_fail "qemu-img not available"
    fi
}

# Test: Deployment
test_deployment() {
    log_info "=== Testing Deployment ==="

    # Test 1: Create namespace
    log_test "Create test namespace"
    if kubectl create namespace $NAMESPACE &> /dev/null; then
        log_success "Namespace created: $NAMESPACE"
    else
        log_warn "Namespace already exists (cleaning up first)"
        kubectl delete namespace $NAMESPACE --wait=true &> /dev/null || true
        kubectl create namespace $NAMESPACE
        log_success "Namespace recreated: $NAMESPACE"
    fi

    # Test 2: Create RBAC
    log_test "Create RBAC resources"
    cat <<EOF | kubectl apply -f - &> /dev/null
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
  resources: ["pods", "pods/log"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["batch"]
  resources: ["jobs"]
  verbs: ["get", "list", "watch", "create"]

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

    if [ $? -eq 0 ]; then
        log_success "RBAC resources created"
    else
        log_fail "Failed to create RBAC resources"
        return 1
    fi

    # Test 3: Create storage
    log_test "Create test storage PVCs"
    cat <<EOF | kubectl apply -f - &> /dev/null
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: test-vmware-storage
  namespace: $NAMESPACE
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: $STORAGE_CLASS
  resources:
    requests:
      storage: 1Gi

---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: test-kvm-storage
  namespace: $NAMESPACE
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: $STORAGE_CLASS
  resources:
    requests:
      storage: 2Gi
EOF

    if [ $? -eq 0 ]; then
        log_success "PVCs created"

        # Wait for PVCs to bind
        log_info "Waiting for PVCs to bind (timeout: 60s)..."
        if kubectl wait --for=condition=Bound pvc/test-vmware-storage -n $NAMESPACE --timeout=60s &> /dev/null && \
           kubectl wait --for=condition=Bound pvc/test-kvm-storage -n $NAMESPACE --timeout=60s &> /dev/null; then
            log_success "PVCs bound successfully"
        else
            log_fail "PVCs failed to bind"
            kubectl get pvc -n $NAMESPACE
            return 1
        fi
    else
        log_fail "Failed to create PVCs"
        return 1
    fi
}

# Test: Create test VMDK
test_create_vmdk() {
    log_info "=== Creating Test VMDK ==="

    log_test "Generate test VMDK file"
    cat <<EOF | kubectl apply -f - &> /dev/null
apiVersion: batch/v1
kind: Job
metadata:
  name: create-test-vmdk
  namespace: $NAMESPACE
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: create-vmdk
        image: ghcr.io/ssahani/hyper2kvm:latest
        command:
          - /bin/bash
          - -c
          - |
            set -e
            cd /mnt/vmware

            # Create a small ext4 filesystem image
            echo "Creating test disk image..."
            dd if=/dev/zero of=test-disk.raw bs=1M count=100 status=progress

            # Format as ext4
            mkfs.ext4 -F test-disk.raw

            # Convert to VMDK
            echo "Converting to VMDK..."
            qemu-img convert -f raw -O vmdk test-disk.raw test-vm.vmdk

            # Verify
            qemu-img info test-vm.vmdk
            ls -lh test-vm.vmdk

            echo "Test VMDK created successfully!"
        volumeMounts:
        - name: vmware-storage
          mountPath: /mnt/vmware
        securityContext:
          privileged: true
          capabilities:
            add:
              - SYS_ADMIN
      volumes:
      - name: vmware-storage
        persistentVolumeClaim:
          claimName: test-vmware-storage
EOF

    if [ $? -eq 0 ]; then
        log_info "Waiting for VMDK creation job..."
        if kubectl wait --for=condition=complete job/create-test-vmdk -n $NAMESPACE --timeout=300s &> /dev/null; then
            log_success "Test VMDK created"

            # Show logs
            log_info "Job logs:"
            kubectl logs -n $NAMESPACE job/create-test-vmdk | tail -10
        else
            log_fail "VMDK creation job failed"
            kubectl logs -n $NAMESPACE job/create-test-vmdk
            return 1
        fi
    else
        log_fail "Failed to create VMDK creation job"
        return 1
    fi
}

# Test: Migration
test_migration() {
    log_info "=== Testing VM Migration ==="

    log_test "Run migration job"
    cat <<EOF | kubectl apply -f - &> /dev/null
apiVersion: batch/v1
kind: Job
metadata:
  name: test-migration
  namespace: $NAMESPACE
spec:
  backoffLimit: 1
  template:
    metadata:
      labels:
        app: hyper2kvm-test
    spec:
      serviceAccountName: hyper2kvm-worker
      restartPolicy: Never
      containers:
      - name: hyper2kvm
        image: ghcr.io/ssahani/hyper2kvm:latest
        command:
          - h2kvmctl
          - --cmd
          - local
          - --vmdk
          - /mnt/vmware/test-vm.vmdk
          - --output-dir
          - /mnt/kvm
          - --to-output
          - test-vm.qcow2
          - --fstab-mode
          - stabilize-all
          - --regen-initramfs
          - --compress
          - --log-level
          - DEBUG
        volumeMounts:
        - name: vmware-storage
          mountPath: /mnt/vmware
          readOnly: true
        - name: kvm-storage
          mountPath: /mnt/kvm
        resources:
          requests:
            memory: "2Gi"
            cpu: "1"
          limits:
            memory: "4Gi"
            cpu: "2"
        securityContext:
          privileged: true
          capabilities:
            add:
              - SYS_ADMIN
              - MKNOD
        env:
        - name: PYTHONUNBUFFERED
          value: "1"
      volumes:
      - name: vmware-storage
        persistentVolumeClaim:
          claimName: test-vmware-storage
      - name: kvm-storage
        persistentVolumeClaim:
          claimName: test-kvm-storage
EOF

    if [ $? -ne 0 ]; then
        log_fail "Failed to create migration job"
        return 1
    fi

    log_info "Waiting for migration to complete (timeout: 600s)..."
    log_info "You can watch logs in another terminal:"
    log_info "  kubectl logs -n $NAMESPACE -f job/test-migration"

    # Wait with progress indicator
    if kubectl wait --for=condition=complete job/test-migration -n $NAMESPACE --timeout=600s &> /dev/null; then
        log_success "Migration completed successfully!"

        # Show migration logs
        echo ""
        log_info "=== Migration Logs ==="
        kubectl logs -n $NAMESPACE job/test-migration | tail -30
        echo ""

    else
        log_fail "Migration failed or timed out"

        # Show pod status
        echo ""
        log_info "=== Pod Status ==="
        kubectl get pods -n $NAMESPACE -l app=hyper2kvm-test

        # Show logs
        echo ""
        log_info "=== Migration Logs ==="
        kubectl logs -n $NAMESPACE job/test-migration

        # Show events
        echo ""
        log_info "=== Recent Events ==="
        kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp' | tail -20

        return 1
    fi
}

# Test: Validation
test_validation() {
    log_info "=== Validating Migration Results ==="

    log_test "Verify output file exists"
    VERIFY=$(kubectl run verify-$RANDOM --image=alpine --rm -i --restart=Never \
        --namespace=$NAMESPACE \
        --overrides='{
            "spec": {
                "containers": [{
                    "name": "verify",
                    "image": "alpine",
                    "command": ["sh", "-c", "ls -lh /mnt/kvm/test-vm.qcow2 && echo OK || echo MISSING"],
                    "volumeMounts": [{
                        "name": "kvm-storage",
                        "mountPath": "/mnt/kvm"
                    }]
                }],
                "volumes": [{
                    "name": "kvm-storage",
                    "persistentVolumeClaim": {
                        "claimName": "test-kvm-storage"
                    }
                }]
            }
        }' 2>/dev/null)

    if echo "$VERIFY" | grep -q "OK"; then
        log_success "Output QCOW2 file exists"
        echo "$VERIFY" | grep "test-vm.qcow2"
    else
        log_fail "Output file not found"
        return 1
    fi

    log_test "Verify QCOW2 file integrity"
    INTEGRITY=$(kubectl run integrity-check-$RANDOM --image=ghcr.io/ssahani/hyper2kvm:latest --rm -i --restart=Never \
        --namespace=$NAMESPACE \
        --overrides='{
            "spec": {
                "containers": [{
                    "name": "integrity",
                    "image": "ghcr.io/ssahani/hyper2kvm:latest",
                    "command": ["sh", "-c", "qemu-img check /mnt/kvm/test-vm.qcow2 && echo OK || echo FAILED"],
                    "volumeMounts": [{
                        "name": "kvm-storage",
                        "mountPath": "/mnt/kvm"
                    }]
                }],
                "volumes": [{
                    "name": "kvm-storage",
                    "persistentVolumeClaim": {
                        "claimName": "test-kvm-storage"
                    }
                }]
            }
        }' 2>/dev/null)

    if echo "$INTEGRITY" | grep -q "OK"; then
        log_success "QCOW2 file integrity check passed"
    else
        log_fail "QCOW2 file integrity check failed"
        echo "$INTEGRITY"
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
}

# Generate test report
generate_report() {
    echo ""
    echo "=========================================="
    echo "      HYPER2KVM CENTOS 8 TEST REPORT"
    echo "=========================================="
    echo ""
    echo "Date: $(date)"
    echo "Kubernetes Version: $(kubectl version -o json 2>/dev/null | grep -o '"gitVersion":"[^"]*"' | tail -1 | cut -d'"' -f4 || echo 'Unknown')"
    echo ""
    echo "Test Results:"
    echo "  Total Tests: $TESTS_TOTAL"
    echo "  Passed: $TESTS_PASSED"
    echo "  Failed: $TESTS_FAILED"
    echo ""

    if [ $TESTS_FAILED -eq 0 ]; then
        echo "✅ ALL TESTS PASSED!"
        echo ""
        echo "Hyper2KVM is ready for production use on this cluster!"
        return 0
    else
        echo "❌ SOME TESTS FAILED"
        echo ""
        echo "Please review the failures above and:"
        echo "1. Check node preparation: ./scripts/deploy-k8s-centos8.sh prepare"
        echo "2. Verify storage class: $STORAGE_CLASS"
        echo "3. Check cluster resources"
        echo "4. Review logs: kubectl logs -n $NAMESPACE"
        return 1
    fi
}

# Main test runner
run_all_tests() {
    log_info "Starting Hyper2KVM CentOS 8 Test Suite"
    echo ""

    test_prerequisites || true
    echo ""

    test_node_preparation || true
    echo ""

    test_deployment || return 1
    echo ""

    test_create_vmdk || return 1
    echo ""

    test_migration || return 1
    echo ""

    test_validation || true
    echo ""

    generate_report
}

# Command handlers
case "${1:-all}" in
    all)
        run_all_tests
        RESULT=$?
        read -p "Clean up test resources? (y/n): " cleanup
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
    vmdk)
        test_create_vmdk
        ;;
    migrate)
        test_migration
        ;;
    validate)
        test_validation
        ;;
    cleanup)
        test_cleanup
        ;;
    *)
        echo "Hyper2KVM Kubernetes CentOS 8 Test Suite"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  all       - Run all tests (default)"
        echo "  prereq    - Test prerequisites only"
        echo "  deploy    - Test deployment only"
        echo "  vmdk      - Create test VMDK only"
        echo "  migrate   - Run migration test only"
        echo "  validate  - Validate results only"
        echo "  cleanup   - Clean up test resources"
        echo ""
        echo "Environment variables:"
        echo "  STORAGE_CLASS  - Kubernetes StorageClass (default: nfs-client)"
        echo ""
        echo "Example:"
        echo "  $0 all"
        echo "  STORAGE_CLASS=local-path $0 all"
        ;;
esac
