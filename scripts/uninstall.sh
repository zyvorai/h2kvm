#!/bin/bash
# =============================================================================
# Uninstall h2kvm components from Kubernetes
# =============================================================================
# Removes operator, workers, CRDs, migrations, and optionally KubeVirt/CDI.
#
# Usage:
#   ./scripts/uninstall.sh                  # Remove h2kvm only
#   ./scripts/uninstall.sh --all            # Remove h2kvm + KubeVirt + CDI
#   ./scripts/uninstall.sh --operator       # Remove operator only
#   ./scripts/uninstall.sh --workers        # Remove workers only
#   ./scripts/uninstall.sh --migrations     # Remove migration resources only
#   ./scripts/uninstall.sh --k3d            # Delete entire k3d cluster
# =============================================================================

set -euo pipefail


log()  { echo "[$(date +%H:%M:%S)] $1"; }
ok()   { echo "✅ [$(date +%H:%M:%S)] ✓ $1"; }
warn() { echo "⚠️ [$(date +%H:%M:%S)] ! $1"; }
err()  { echo "❌ [$(date +%H:%M:%S)] ✗ $1"; }

MODE="${1:---h2kvm}"
CLUSTER_NAME="${K3D_CLUSTER:-h2kvm-test}"

remove_operator() {
    log "Removing operator..."

    # Stop VMs managed by operator
    for hc in $(kubectl get hc -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}{"\n"}{end}' 2>/dev/null); do
        NS="${hc%%/*}"; NAME="${hc##*/}"
        log "  Deleting HyperConversion $NS/$NAME..."
        kubectl delete hc "$NAME" -n "$NS" --timeout=60s 2>/dev/null || true
    done

    # Delete operator deployment
    kubectl delete deployment hyperconversion-operator -n h2kvm-system 2>/dev/null && ok "Operator deployment deleted" || true

    # Delete RBAC
    kubectl delete clusterrolebinding h2kvm-operator-rolebinding 2>/dev/null || true
    kubectl delete clusterrole h2kvm-operator-role 2>/dev/null || true
    kubectl delete serviceaccount hyperconversion-operator -n h2kvm-system 2>/dev/null || true
    ok "Operator RBAC removed"

    # Delete CRDs (this deletes ALL CRs too)
    kubectl delete crd hyperconversions.h2kvm.io 2>/dev/null && ok "HyperConversion CRD deleted" || true
    kubectl delete crd validations.h2kvm.io 2>/dev/null && ok "Validation CRD deleted" || true

    # Delete namespace
    kubectl delete namespace h2kvm-system --timeout=120s 2>/dev/null && ok "h2kvm-system namespace deleted" || true

    # Delete webhooks
    kubectl delete mutatingwebhookconfiguration h2kvm-mutating-webhook 2>/dev/null || true
    kubectl delete validatingwebhookconfiguration h2kvm-validating-webhook 2>/dev/null || true
    ok "Operator removed"
}

remove_workers() {
    log "Removing workers..."
    kubectl delete namespace h2kvm-workers --timeout=120s 2>/dev/null && ok "Workers namespace deleted" || true
    kubectl delete clusterrole h2kvm:privileged 2>/dev/null || true
    kubectl delete clusterrolebinding h2kvm:privileged 2>/dev/null || true
    ok "Workers removed"
}

remove_migrations() {
    log "Removing migration resources..."

    # Stop VMs in migration namespace
    for vm in $(kubectl get vm -n h2kvm-migration -o jsonpath='{.items[*].metadata.name}' 2>/dev/null); do
        kubectl delete vm "$vm" -n h2kvm-migration --timeout=60s 2>/dev/null || true
    done

    # Delete DataVolumes
    kubectl delete dv --all -n h2kvm-migration 2>/dev/null || true

    # Delete jobs
    kubectl delete jobs --all -n h2kvm-migration 2>/dev/null || true

    # Delete PVCs
    kubectl delete pvc --all -n h2kvm-migration 2>/dev/null || true

    # Delete namespace
    kubectl delete namespace h2kvm-migration --timeout=120s 2>/dev/null && ok "Migration namespace deleted" || true
    ok "Migration resources removed"
}

remove_monitoring() {
    log "Removing monitoring..."
    kubectl delete servicemonitor h2kvm-worker -n h2kvm-workers 2>/dev/null || true
    kubectl delete prometheusrule h2kvm-alerts -n h2kvm-workers 2>/dev/null || true
    kubectl delete configmap h2kvm-grafana-dashboard -n h2kvm-workers 2>/dev/null || true
    ok "Monitoring removed"
}

remove_kubevirt() {
    log "Removing KubeVirt..."
    warn "This will stop ALL KubeVirt VMs in the cluster!"
    read -p "Continue? (yes/no): " CONFIRM
    [ "$CONFIRM" = "yes" ] || { warn "Aborted"; return; }

    # Delete all VMs first
    kubectl delete vm --all -A 2>/dev/null || true
    kubectl delete vmi --all -A 2>/dev/null || true

    # Delete KubeVirt CR and operator
    KV_VER=$(kubectl get kubevirt kubevirt -n kubevirt -o jsonpath='{.status.observedKubeVirtVersion}' 2>/dev/null || echo "v1.7.0")
    kubectl delete kubevirt kubevirt -n kubevirt --timeout=300s 2>/dev/null || true
    kubectl delete -f "https://github.com/kubevirt/kubevirt/releases/download/${KV_VER}/kubevirt-operator.yaml" 2>/dev/null || true
    kubectl delete namespace kubevirt --timeout=120s 2>/dev/null || true
    ok "KubeVirt removed"
}

remove_cdi() {
    log "Removing CDI..."
    CDI_VER=$(kubectl get cdi cdi -o jsonpath='{.status.observedVersion}' 2>/dev/null || echo "1.64.0")
    kubectl delete cdi cdi --timeout=300s 2>/dev/null || true
    CDI_VER="${CDI_VER#v}"
    kubectl delete -f "https://github.com/kubevirt/containerized-data-importer/releases/download/v${CDI_VER}/cdi-operator.yaml" 2>/dev/null || true
    kubectl delete namespace cdi --timeout=120s 2>/dev/null || true
    ok "CDI removed"
}

remove_k3d() {
    log "Deleting k3d cluster '$CLUSTER_NAME'..."
    k3d cluster delete "$CLUSTER_NAME" 2>/dev/null && ok "k3d cluster deleted" || err "Cluster not found"
    # Clean up only h2kvm-related Docker volumes
    docker volume ls -q --filter name=h2kvm --filter name=k3d-${CLUSTER_NAME} 2>/dev/null | xargs -r docker volume rm 2>/dev/null || true
    ok "k3d cleanup complete"
}

# --- Main ---
echo ""
echo "=== h2kvm Uninstall ==="
echo ""

case "$MODE" in
    --operator)
        remove_operator
        ;;
    --workers)
        remove_workers
        ;;
    --migrations)
        remove_migrations
        ;;
    --all)
        remove_migrations
        remove_operator
        remove_workers
        remove_monitoring
        remove_cdi
        remove_kubevirt
        ;;
    --k3d)
        remove_k3d
        ;;
    --h2kvm|*)
        remove_migrations
        remove_operator
        remove_workers
        remove_monitoring
        ;;
esac

echo ""
echo "✅ === Uninstall complete ==="
