#!/bin/bash
# =============================================================================
# Backup operator state before upgrade
# =============================================================================
# Backs up CRDs, CRs, RBAC, webhooks, secrets, and operator config.
#
# Usage:
#   ./scripts/ops/backup-operator-state.sh [output-dir]
# =============================================================================

set -euo pipefail

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTPUT="${1:-/tmp/h2kvm-operator-backup-$TIMESTAMP}"
ARCHIVE="$OUTPUT.tar.gz"

mkdir -p "$OUTPUT"

log() { echo "[$(date +%H:%M:%S)] Backing up: $1"; }

log "CRDs"
kubectl get crd -o yaml | grep -A 1000 "h2kvm" > "$OUTPUT/crds.yaml" 2>/dev/null || true

log "HyperConversion CRs"
kubectl get hc -A -o yaml > "$OUTPUT/hyperconversions.yaml" 2>/dev/null || true

log "Validation CRs"
kubectl get validations -A -o yaml > "$OUTPUT/validations.yaml" 2>/dev/null || true

log "Operator deployment"
kubectl get deployment -n h2kvm-system -o yaml > "$OUTPUT/operator-deployment.yaml" 2>/dev/null || true

log "RBAC"
kubectl get clusterrole h2kvm-operator-role -o yaml > "$OUTPUT/clusterrole.yaml" 2>/dev/null || true
kubectl get clusterrolebinding h2kvm-operator-rolebinding -o yaml > "$OUTPUT/clusterrolebinding.yaml" 2>/dev/null || true
kubectl get serviceaccount hyperconversion-operator -n h2kvm-system -o yaml > "$OUTPUT/serviceaccount.yaml" 2>/dev/null || true

log "Webhooks"
kubectl get mutatingwebhookconfiguration -o yaml > "$OUTPUT/mutating-webhooks.yaml" 2>/dev/null || true
kubectl get validatingwebhookconfiguration -o yaml > "$OUTPUT/validating-webhooks.yaml" 2>/dev/null || true

log "Secrets (names only)"
kubectl get secrets -n h2kvm-system -o name > "$OUTPUT/secrets-list.txt" 2>/dev/null || true

log "ConfigMaps"
kubectl get configmaps -n h2kvm-system -o yaml > "$OUTPUT/configmaps.yaml" 2>/dev/null || true

log "Operator version"
kubectl get deployment hyperconversion-operator -n h2kvm-system -o jsonpath='{.spec.template.spec.containers[0].image}' > "$OUTPUT/operator-image.txt" 2>/dev/null || true

log "Leases"
kubectl get lease -n h2kvm-system -o yaml > "$OUTPUT/leases.yaml" 2>/dev/null || true

# Create archive
tar czf "$ARCHIVE" -C "$(dirname "$OUTPUT")" "$(basename "$OUTPUT")"
rm -rf "$OUTPUT"

echo ""
echo "Backup: $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
echo ""
echo "Restore: tar xzf $ARCHIVE && kubectl apply -f $(basename "$OUTPUT")/"
