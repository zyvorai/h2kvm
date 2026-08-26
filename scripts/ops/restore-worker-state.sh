#!/bin/bash
#
# restore-worker-state.sh - Restore worker state and events to Kubernetes
#
# Usage:
#   ./restore-worker-state.sh <backup-archive> [namespace]
#
# Example:
#   ./restore-worker-state.sh h2kvm-worker-backup-2026-01-30_14-30-00.tar.gz h2kvm-workers
#

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <backup-archive> [namespace]"
    echo ""
    echo "Example:"
    echo "  $0 h2kvm-worker-backup-2026-01-30_14-30-00.tar.gz h2kvm-workers"
    exit 1
fi

BACKUP_ARCHIVE="$1"
NAMESPACE="${2:-h2kvm-workers}"

if [ ! -f "$BACKUP_ARCHIVE" ]; then
    echo "ERROR: Backup archive not found: $BACKUP_ARCHIVE"
    exit 1
fi

echo "=== H2KVM Worker State Restore ==="
echo "Archive: $BACKUP_ARCHIVE"
echo "Namespace: $NAMESPACE"
echo ""

# Extract backup
RESTORE_DIR="restore-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RESTORE_DIR"
tar xzf "$BACKUP_ARCHIVE" -C "$RESTORE_DIR"

# Find the backup directory
BACKUP_DIR=$(find "$RESTORE_DIR" -maxdepth 1 -type d -name 'worker-backup-*' | head -n 1)

if [ -z "$BACKUP_DIR" ]; then
    echo "ERROR: Could not find backup directory in archive"
    exit 1
fi

echo "Extracted to: $BACKUP_DIR"
echo ""

# Read metadata
if [ -f "$BACKUP_DIR/backup-metadata.json" ]; then
    echo "Backup metadata:"
    cat "$BACKUP_DIR/backup-metadata.json"
    echo ""
fi

# Get current worker pods
CURRENT_PODS=$(kubectl get pods -n "$NAMESPACE" -l app=h2kvm-worker -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")

if [ -z "$CURRENT_PODS" ]; then
    echo "WARNING: No worker pods found in namespace $NAMESPACE"
    echo "Please deploy workers first using:"
    echo "  helm install h2kvm-worker ./helm/h2kvm-worker -n $NAMESPACE"
    exit 1
fi

echo "Current worker pods: $CURRENT_PODS"
echo ""

# Confirm restore
read -p "Restore backup to namespace $NAMESPACE? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Restore cancelled."
    exit 0
fi

echo ""
echo "Restoring state..."

# Restore to each pod
for POD_DIR in "$BACKUP_DIR"/*; do
    if [ ! -d "$POD_DIR" ]; then
        continue
    fi

    POD_NAME=$(basename "$POD_DIR")

    # Skip metadata files
    if [[ "$POD_NAME" == *.yaml ]] || [[ "$POD_NAME" == *.json ]]; then
        continue
    fi

    echo "Restoring pod: $POD_NAME"

    # Get the first available pod (round-robin)
    TARGET_POD=$(echo $CURRENT_PODS | awk '{print $1}')
    CURRENT_PODS=$(echo $CURRENT_PODS | awk '{$1=""; print $0}' | xargs)

    if [ -z "$TARGET_POD" ]; then
        echo "  WARNING: No more pods available, reusing pods..."
        TARGET_POD=$(kubectl get pods -n "$NAMESPACE" -l app=h2kvm-worker -o jsonpath='{.items[0].metadata.name}')
    fi

    echo "  Target pod: $TARGET_POD"

    # Restore job state
    if [ -d "$POD_DIR" ] && [ "$(ls -A "$POD_DIR" 2>/dev/null | grep -v -E '(events|capabilities\.json|pod\.yaml)' || true)" ]; then
        echo "  - Restoring job state..."
        tar czf - -C "$POD_DIR" $(ls -A "$POD_DIR" | grep -v -E '(events|capabilities\.json|pod\.yaml)') 2>/dev/null | \
            kubectl exec -n "$NAMESPACE" "$TARGET_POD" -i -- \
            tar xzf - -C /var/lib/h2kvm/jobs || echo "    Failed to restore job state"
    fi

    # Restore events
    if [ -d "$POD_DIR/events" ] && [ "$(ls -A "$POD_DIR/events" 2>/dev/null || true)" ]; then
        echo "  - Restoring events..."
        tar czf - -C "$POD_DIR/events" . 2>/dev/null | \
            kubectl exec -n "$NAMESPACE" "$TARGET_POD" -i -- \
            tar xzf - -C /var/lib/h2kvm/events || echo "    Failed to restore events"
    fi

    echo "  Done."
    echo ""
done

# Restore ConfigMaps (optional)
if [ -f "$BACKUP_DIR/configmaps.yaml" ]; then
    echo "ConfigMap backup found at $BACKUP_DIR/configmaps.yaml"
    read -p "Restore ConfigMaps? (yes/no): " RESTORE_CM
    if [ "$RESTORE_CM" == "yes" ]; then
        kubectl apply -f "$BACKUP_DIR/configmaps.yaml" -n "$NAMESPACE"
        echo "ConfigMaps restored."
    fi
    echo ""
fi

echo "=== Restore Complete ==="
echo ""
echo "Verify restored state:"
echo "  kubectl exec -n $NAMESPACE <pod-name> -- ls -la /var/lib/h2kvm/jobs"
echo "  kubectl exec -n $NAMESPACE <pod-name> -- ls -la /var/lib/h2kvm/events"
echo ""
echo "Check worker status:"
echo "  kubectl logs -n $NAMESPACE -l app=h2kvm-worker --tail=50"
