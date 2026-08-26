#!/bin/bash
# =============================================================================
# Full-stack health check for h2kvm deployment
# =============================================================================
# Validates all components are healthy and functioning.
#
# Usage:
#   ./scripts/health-check.sh
# =============================================================================

set -euo pipefail

PASS=0; FAIL=0; WARN=0

ok()   { echo -e "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo -e "  ✗ $1"; FAIL=$((FAIL+1)); }
warn() { echo -e "  ! $1"; WARN=$((WARN+1)); }
hdr()  { echo -e "\n$1"; }

hdr "=== Cluster ==="
while read -r line; do
    NODE=$(echo "$line" | awk '{print $1}')
    STATUS=$(echo "$line" | awk '{print $2}')
    [ "$STATUS" = "Ready" ] && ok "Node $NODE: Ready" || fail "Node $NODE: $STATUS"
done < <(kubectl get nodes --no-headers 2>/dev/null)

hdr "=== KubeVirt ==="
KV_PHASE=$(kubectl get kubevirt kubevirt -n kubevirt -o jsonpath='{.status.phase}' 2>/dev/null || echo "")
[ "$KV_PHASE" = "Deployed" ] && ok "KubeVirt: $KV_PHASE" || fail "KubeVirt: ${KV_PHASE:-not installed}"
for comp in virt-operator virt-api virt-controller virt-handler; do
    COUNT=$(kubectl get pods -n kubevirt -l kubevirt.io=$comp --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
    [ "$COUNT" -gt 0 ] && ok "$comp: $COUNT Running" || fail "$comp: not running"
done

hdr "=== CDI ==="
CDI_PHASE=$(kubectl get cdi cdi -o jsonpath='{.status.phase}' 2>/dev/null || echo "")
[ "$CDI_PHASE" = "Deployed" ] && ok "CDI: $CDI_PHASE" || warn "CDI: ${CDI_PHASE:-not installed}"
for comp in cdi-operator cdi-apiserver cdi-deployment cdi-uploadproxy; do
    COUNT=$(kubectl get pods -n cdi -l app.kubernetes.io/component=$comp --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
    if [ "$COUNT" -eq 0 ]; then
        COUNT=$(kubectl get pods -n cdi --no-headers 2>/dev/null | grep "^${comp}" | grep -c Running || echo "0")
    fi
    [ "$COUNT" -gt 0 ] && ok "$comp: Running" || warn "$comp: not running"
done

hdr "=== Operator ==="
OP_PODS=$(kubectl get pods -n h2kvm-system -l control-plane=controller-manager --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
[ "$OP_PODS" -gt 0 ] && ok "Operator: $OP_PODS pod(s) Running" || warn "Operator: not running"
# Check health endpoint
OP_POD=$(kubectl get pods -n h2kvm-system -l control-plane=controller-manager -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [ -n "$OP_POD" ]; then
    HEALTH=$(kubectl exec -n h2kvm-system "$OP_POD" -- wget -q -O- http://localhost:8081/healthz 2>/dev/null || echo "")
    [ "$HEALTH" = "ok" ] && ok "Operator health: ok" || warn "Operator health probe: $HEALTH"
fi

hdr "=== Workers ==="
W_PODS=$(kubectl get pods -n h2kvm-workers --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
[ "$W_PODS" -gt 0 ] && ok "Workers: $W_PODS Running" || warn "Workers: none deployed"

hdr "=== CRDs ==="
kubectl get crd hyperconversions.h2kvm.io >/dev/null 2>&1 && ok "HyperConversion CRD" || warn "HyperConversion CRD missing"
kubectl get crd validations.h2kvm.io >/dev/null 2>&1 && ok "Validation CRD" || warn "Validation CRD missing"

hdr "=== HyperConversions ==="
HC_COUNT=$(kubectl get hc -A --no-headers 2>/dev/null | wc -l)
if [ "$HC_COUNT" -gt 0 ]; then
    ok "$HC_COUNT HyperConversion(s) found"
    while read -r line; do
        NS=$(echo "$line" | awk '{print $1}')
        NAME=$(echo "$line" | awk '{print $2}')
        PHASE=$(echo "$line" | awk '{print $3}')
        case "$PHASE" in
            Ready)     ok "  $NS/$NAME: $PHASE" ;;
            Failed)    fail "  $NS/$NAME: $PHASE" ;;
            *)         warn "  $NS/$NAME: $PHASE" ;;
        esac
    done < <(kubectl get hc -A --no-headers 2>/dev/null)
else
    warn "No HyperConversions"
fi

hdr "=== VMs ==="
VM_TOTAL=$(kubectl get vm -A --no-headers 2>/dev/null | wc -l)
VM_RUNNING=$(kubectl get vm -A --no-headers 2>/dev/null | grep -c "Running" || echo "0")
if [ "$VM_RUNNING" -eq 0 ] && [ "$VM_TOTAL" -gt 0 ]; then
    warn "$VM_RUNNING/$VM_TOTAL VMs Running"
else
    ok "$VM_RUNNING/$VM_TOTAL VMs Running"
fi

hdr "=== Storage ==="
SC_COUNT=$(kubectl get sc --no-headers 2>/dev/null | wc -l)
ok "$SC_COUNT StorageClass(es)"
PVC_PENDING=$(kubectl get pvc -A --no-headers 2>/dev/null | grep -c "Pending" || true)
PVC_PENDING=${PVC_PENDING:-0}
[ "$PVC_PENDING" -eq 0 ] && ok "No pending PVCs" || warn "$PVC_PENDING PVC(s) pending"

hdr "=== Webhooks ==="
MWH=$(kubectl get mutatingwebhookconfiguration --no-headers 2>/dev/null | wc -l)
VWH=$(kubectl get validatingwebhookconfiguration --no-headers 2>/dev/null | wc -l)
ok "$MWH mutating, $VWH validating webhook(s)"

# --- Summary ---
echo ""
echo "=== Summary ==="
echo -e "  Pass: $PASS  Fail: $FAIL  Warn: $WARN"
[ "$FAIL" -eq 0 ] && echo "✅ All critical checks passed" || echo "❌ $FAIL failure(s) detected"
exit $(( FAIL > 0 ? 1 : 0 ))
