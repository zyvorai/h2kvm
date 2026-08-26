#!/bin/bash
# =============================================================================
# Collect debug bundle for troubleshooting
# =============================================================================
# Gathers logs, events, resource states, and metrics into a timestamped archive.
#
# Usage:
#   ./scripts/collect-debug-bundle.sh
#   ./scripts/collect-debug-bundle.sh /path/to/output
# =============================================================================

set -euo pipefail

warn() { echo "WARNING: $1"; }
warn "This bundle may contain sensitive information (pod logs, events, resource specs). Review before sharing."
echo ""

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTPUT_DIR="${1:-/tmp/hyper2kvm-debug-$TIMESTAMP}"
ARCHIVE="$OUTPUT_DIR.tar.gz"

mkdir -p "$OUTPUT_DIR"

log() { echo "[$(date +%H:%M:%S)] $1"; }
collect() { log "Collecting: $1..."; }

collect "cluster info"
kubectl cluster-info > "$OUTPUT_DIR/cluster-info.txt" 2>&1 || true
kubectl version -o yaml > "$OUTPUT_DIR/k8s-version.yaml" 2>&1 || true
kubectl get nodes -o wide > "$OUTPUT_DIR/nodes.txt" 2>&1 || true

collect "namespace resources"
for NS in hyper2kvm-system hyper2kvm-workers hyper2kvm-migration kubevirt cdi; do
    mkdir -p "$OUTPUT_DIR/$NS"
    kubectl get all -n "$NS" -o wide > "$OUTPUT_DIR/$NS/all-resources.txt" 2>&1 || true
    kubectl get events -n "$NS" --sort-by=.lastTimestamp > "$OUTPUT_DIR/$NS/events.txt" 2>&1 || true
    kubectl get pvc -n "$NS" -o wide > "$OUTPUT_DIR/$NS/pvcs.txt" 2>&1 || true
done

collect "operator logs"
kubectl logs -n hyper2kvm-system -l control-plane=controller-manager --tail=500 > "$OUTPUT_DIR/hyper2kvm-system/operator.log" 2>&1 || true

collect "worker logs"
for POD in $(kubectl get pods -n hyper2kvm-workers -o jsonpath='{.items[*].metadata.name}' 2>/dev/null); do
    kubectl logs -n hyper2kvm-workers "$POD" --tail=200 > "$OUTPUT_DIR/hyper2kvm-workers/$POD.log" 2>&1 || true
done

collect "migration job logs"
for POD in $(kubectl get pods -n hyper2kvm-migration -o jsonpath='{.items[*].metadata.name}' 2>/dev/null); do
    kubectl logs -n hyper2kvm-migration "$POD" --all-containers --tail=200 > "$OUTPUT_DIR/hyper2kvm-migration/$POD.log" 2>&1 || true
done

collect "KubeVirt status"
kubectl get kubevirts -A -o yaml > "$OUTPUT_DIR/kubevirt-status.yaml" 2>&1 || true
kubectl get vm,vmi -A -o wide > "$OUTPUT_DIR/vms.txt" 2>&1 || true
kubectl get vmim -A -o wide > "$OUTPUT_DIR/migrations.txt" 2>&1 || true

collect "CDI status"
kubectl get cdis -o yaml > "$OUTPUT_DIR/cdi-status.yaml" 2>&1 || true
kubectl get dv -A -o wide > "$OUTPUT_DIR/datavolumes.txt" 2>&1 || true

collect "HyperConversion CRs"
kubectl get hc -A -o yaml > "$OUTPUT_DIR/hyperconversions.yaml" 2>&1 || true

collect "CRDs"
kubectl get crd -o name | grep hyper2kvm > "$OUTPUT_DIR/crds.txt" 2>&1 || true

collect "RBAC"
kubectl get clusterrole,clusterrolebinding -o name | grep hyper2kvm > "$OUTPUT_DIR/rbac.txt" 2>&1 || true

collect "storage classes"
kubectl get sc -o wide > "$OUTPUT_DIR/storageclasses.txt" 2>&1 || true

collect "webhooks"
kubectl get mutatingwebhookconfiguration,validatingwebhookconfiguration -o name > "$OUTPUT_DIR/webhooks.txt" 2>&1 || true

collect "pod describes (failed/error)"
for NS in hyper2kvm-system hyper2kvm-workers hyper2kvm-migration; do
    for POD in $(kubectl get pods -n "$NS" --field-selector=status.phase!=Running,status.phase!=Succeeded -o jsonpath='{.items[*].metadata.name}' 2>/dev/null); do
        kubectl describe pod "$POD" -n "$NS" > "$OUTPUT_DIR/$NS/$POD-describe.txt" 2>&1 || true
    done
done

# Create archive
if tar czf "$ARCHIVE" -C "$(dirname "$OUTPUT_DIR")" "$(basename "$OUTPUT_DIR")" 2>/dev/null; then
    rm -rf "$OUTPUT_DIR"
else
    warn "Archive creation failed, raw data preserved in $OUTPUT_DIR"
fi

echo ""
if [ -f "$ARCHIVE" ]; then
    echo "Debug bundle: $ARCHIVE"
    echo "Size: $(du -h "$ARCHIVE" | cut -f1)"
    echo ""
    echo "Share this file when reporting issues."
fi
