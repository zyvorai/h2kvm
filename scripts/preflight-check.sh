#!/bin/bash
# =============================================================================
# Pre-flight cluster readiness check
# =============================================================================
# Validates all prerequisites before deploying hyper2kvm components.
#
# Usage:
#   ./scripts/preflight-check.sh [--fix]
#
# Exit codes:
#   0 = All checks passed
#   1 = Critical check failed
#   2 = Warning (non-blocking)
# =============================================================================

set -euo pipefail

ERRORS=0; WARNINGS=0
FIX="${1:-}"

pass()  { echo -e "  [PASS] $1"; }
fail()  { echo -e "  [FAIL] $1"; ERRORS=$((ERRORS+1)); }
warn()  { echo -e "  [WARN] $1"; WARNINGS=$((WARNINGS+1)); }
info()  { echo -e "  [INFO] $1"; }

echo "=== hyper2kvm Pre-flight Check ==="
echo ""

# --- Tools ---
echo "Checking required tools..."
for cmd in kubectl docker; do
    command -v "$cmd" >/dev/null 2>&1 && pass "$cmd found" || fail "$cmd not found"
done
for cmd in k3d virtctl h2kvmctl helm; do
    command -v "$cmd" >/dev/null 2>&1 && pass "$cmd found" || warn "$cmd not found (optional)"
done

# --- Cluster connectivity ---
echo ""
echo "Checking cluster connectivity..."
if kubectl cluster-info >/dev/null 2>&1; then
    pass "Cluster reachable"
    SERVER=$(kubectl cluster-info 2>&1 | head -1 | grep -oE 'https?://[^ ]+' || echo "unknown")
    info "API server: $SERVER"
else
    fail "Cannot connect to cluster"
    echo "❌ Fix: Ensure kubeconfig is set and cluster is running"
    exit 1
fi

# --- Kubernetes version ---
echo ""
echo "Checking Kubernetes version..."
K8S_VER=$(kubectl version --client -o json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['clientVersion']['minor'])" 2>/dev/null || echo "0")
if [ "$K8S_VER" -ge 24 ] 2>/dev/null; then
    pass "Kubernetes v1.$K8S_VER (>= v1.24 required)"
else
    warn "Kubernetes version could not be verified"
fi

# --- Nodes ---
echo ""
echo "Checking nodes..."
NODE_COUNT=$(kubectl get nodes --no-headers 2>/dev/null | wc -l)
if [ "$NODE_COUNT" -gt 0 ]; then
    pass "$NODE_COUNT node(s) found"
    READY=$(kubectl get nodes --no-headers 2>/dev/null | grep -c " Ready" || echo "0")
    [ "$READY" -eq "$NODE_COUNT" ] && pass "All nodes Ready" || warn "$READY/$NODE_COUNT nodes Ready"
else
    fail "No nodes found"
fi

# --- KubeVirt ---
echo ""
echo "Checking KubeVirt..."
if kubectl get kubevirts -n kubevirt >/dev/null 2>&1; then
    KV_PHASE=$(kubectl get kubevirt kubevirt -n kubevirt -o jsonpath='{.status.phase}' 2>/dev/null || echo "")
    KV_VER=$(kubectl get kubevirt kubevirt -n kubevirt -o jsonpath='{.status.observedKubeVirtVersion}' 2>/dev/null || echo "")
    if [ "$KV_PHASE" = "Deployed" ]; then
        pass "KubeVirt $KV_VER ($KV_PHASE)"
    else
        warn "KubeVirt phase: $KV_PHASE (expected: Deployed)"
    fi
    # Check virt-api, virt-controller, virt-handler
    for comp in virt-api virt-controller virt-handler; do
        COUNT=$(kubectl get pods -n kubevirt -l kubevirt.io=$comp --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
        [ "$COUNT" -gt 0 ] && pass "$comp: $COUNT pod(s) Running" || warn "$comp: no running pods"
    done
else
    warn "KubeVirt not installed"
    info "Install: kubectl apply -f https://github.com/kubevirt/kubevirt/releases/download/<version>/kubevirt-operator.yaml"
fi

# --- CDI ---
echo ""
echo "Checking CDI..."
if kubectl get cdis >/dev/null 2>&1; then
    CDI_PHASE=$(kubectl get cdi cdi -o jsonpath='{.status.phase}' 2>/dev/null || echo "")
    CDI_VER=$(kubectl get cdi cdi -o jsonpath='{.status.observedVersion}' 2>/dev/null || echo "")
    if [ "$CDI_PHASE" = "Deployed" ]; then
        pass "CDI $CDI_VER ($CDI_PHASE)"
    else
        warn "CDI phase: $CDI_PHASE"
    fi
else
    warn "CDI not installed"
fi

# --- Storage ---
echo ""
echo "Checking storage..."
SC_COUNT=$(kubectl get sc --no-headers 2>/dev/null | wc -l)
[ "$SC_COUNT" -gt 0 ] && pass "$SC_COUNT StorageClass(es) found" || fail "No StorageClass found"
DEFAULT_SC=$(kubectl get sc -o jsonpath='{.items[?(@.metadata.annotations.storageclass\.kubernetes\.io/is-default-class=="true")].metadata.name}' 2>/dev/null || echo "")
[ -n "$DEFAULT_SC" ] && pass "Default StorageClass: $DEFAULT_SC" || warn "No default StorageClass"

# Immediate binding check for CDI
if kubectl get sc local-path-immediate >/dev/null 2>&1; then
    pass "local-path-immediate StorageClass exists (CDI-compatible)"
else
    warn "No Immediate-binding StorageClass for CDI"
    if [ "$FIX" = "--fix" ]; then
        info "Creating local-path-immediate StorageClass..."
        kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: local-path-immediate
provisioner: rancher.io/local-path
reclaimPolicy: Delete
volumeBindingMode: Immediate
EOF
        pass "Created local-path-immediate"
    fi
fi

# --- RBAC ---
echo ""
echo "Checking RBAC..."
if kubectl auth can-i create deployments --all-namespaces 2>/dev/null | grep -q "yes"; then
    pass "Current user can create deployments"
else
    warn "Current user may lack cluster-admin permissions"
fi

# --- CRDs ---
echo ""
echo "Checking CRDs..."
if kubectl get crd hyperconversions.hyper2kvm.io >/dev/null 2>&1; then
    pass "HyperConversion CRD installed"
else
    warn "HyperConversion CRD not installed"
    info "Install: kubectl apply -f operator/config/crd/bases/hyper2kvm.io_hyperconversions.yaml"
fi

# --- NBD module ---
echo ""
echo "Checking kernel modules..."
if lsmod 2>/dev/null | grep -q nbd; then
    pass "NBD kernel module loaded"
else
    warn "NBD module not loaded (required for VMCraft backend)"
    info "Load: sudo modprobe nbd max_part=16"
fi

# --- Disk space ---
echo ""
echo "Checking disk space..."
AVAIL_GB=$(df -BG / 2>/dev/null | tail -1 | awk '{print $4}' | tr -d 'G')
if [ "${AVAIL_GB:-0}" -ge 20 ]; then
    pass "Disk space: ${AVAIL_GB}G available"
else
    warn "Low disk space: ${AVAIL_GB}G (20G+ recommended)"
fi

# --- Summary ---
echo ""
echo "=== Summary ==="
if [ "$ERRORS" -eq 0 ]; then
    echo "✅ All critical checks passed ($WARNINGS warning(s))"
    exit 0
else
    echo "❌ $ERRORS critical failure(s), $WARNINGS warning(s)"
    exit 1
fi
