#!/bin/bash
#
# backup-worker-state.sh - Backup worker state and events from Kubernetes
#
# Usage:
#   ./backup-worker-state.sh [namespace] [output-dir]
#
# Example:
#   ./backup-worker-state.sh h2kvm-workers /backup/2026-01-30
#

set -euo pipefail

NAMESPACE="${1:-h2kvm-workers}"
OUTPUT_DIR="${2:-./worker-backup-$(date +%Y%m%d-%H%M%S)}"
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)

echo "=== H2KVM Worker State Backup ==="
echo "Namespace: $NAMESPACE"
echo "Output: $OUTPUT_DIR"
echo "Timestamp: $TIMESTAMP"
echo ""

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Get all worker pods
PODS=$(kubectl get pods -n "$NAMESPACE" -l app=h2kvm-worker -o jsonpath='{.items[*].metadata.name}')

if [ -z "$PODS" ]; then
    echo "ERROR: No worker pods found in namespace $NAMESPACE"
    exit 1
fi

echo "Found worker pods: $PODS"
echo ""

# Backup each pod's state
for POD in $PODS; do
    echo "Backing up pod: $POD"
    POD_DIR="$OUTPUT_DIR/$POD"
    mkdir -p "$POD_DIR"

    # Backup job state
    echo "  - Job state..."
    kubectl exec -n "$NAMESPACE" "$POD" -- \
        tar czf - -C /var/lib/h2kvm/jobs . 2>/dev/null | \
        tar xzf - -C "$POD_DIR" || echo "    No job state found"

    # Backup events
    echo "  - Events..."
    mkdir -p "$POD_DIR/events"
    kubectl exec -n "$NAMESPACE" "$POD" -- \
        tar czf - -C /var/lib/h2kvm/events . 2>/dev/null | \
        tar xzf - -C "$POD_DIR/events" || echo "    No events found"

    # Backup worker capabilities
    echo "  - Capabilities..."
    kubectl exec -n "$NAMESPACE" "$POD" -- \
        python3 -m h2kvm.worker.cli capabilities --format json \
        > "$POD_DIR/capabilities.json" 2>/dev/null || echo "    Failed to get capabilities"

    # Get pod metadata
    echo "  - Metadata..."
    kubectl get pod -n "$NAMESPACE" "$POD" -o yaml > "$POD_DIR/pod.yaml"

    echo "  Done."
    echo ""
done

# Backup ConfigMaps
echo "Backing up ConfigMaps..."
kubectl get configmap -n "$NAMESPACE" -o yaml > "$OUTPUT_DIR/configmaps.yaml"

# Backup PVCs
echo "Backing up PVC manifests..."
kubectl get pvc -n "$NAMESPACE" -o yaml > "$OUTPUT_DIR/pvcs.yaml"

# Backup DaemonSet
echo "Backing up DaemonSet..."
kubectl get daemonset -n "$NAMESPACE" -o yaml > "$OUTPUT_DIR/daemonset.yaml"

# Create backup metadata
cat > "$OUTPUT_DIR/backup-metadata.json" <<EOF
{
  "timestamp": "$TIMESTAMP",
  "namespace": "$NAMESPACE",
  "pod_count": $(echo $PODS | wc -w),
  "pods": [$(echo $PODS | sed 's/ /", "/g' | sed 's/^/"/' | sed 's/$/"/')],
  "backup_tool": "backup-worker-state.sh",
  "kubernetes_version": "$(kubectl version -o json 2>/dev/null | grep -o '"gitVersion":"[^"]*"' | head -1 | cut -d'"' -f4 || echo 'unknown')"
}
EOF

# Create archive
echo ""
echo "Creating backup archive..."
ARCHIVE_NAME="h2kvm-worker-backup-$TIMESTAMP.tar.gz"
tar czf "$ARCHIVE_NAME" -C "$(dirname "$OUTPUT_DIR")" "$(basename "$OUTPUT_DIR")"

echo ""
echo "=== Backup Complete ==="
echo "Directory: $OUTPUT_DIR"
echo "Archive: $ARCHIVE_NAME"
echo "Size: $(du -h "$ARCHIVE_NAME" | cut -f1)"
echo ""
echo "To restore, use: ./restore-worker-state.sh $ARCHIVE_NAME"
