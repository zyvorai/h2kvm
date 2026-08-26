#!/bin/bash
#
# migrate-to-helm.sh - Migrate existing kubectl deployment to Helm
#
# This script helps migrate from manual kubectl deployment to Helm-managed deployment
# while preserving worker state and configuration.
#
# Usage:
#   ./migrate-to-helm.sh [namespace]
#
# Example:
#   ./migrate-to-helm.sh hyper2kvm-workers
#

set -euo pipefail

NAMESPACE="${1:-hyper2kvm-workers}"
BACKUP_DIR="./migration-backup-$(date +%Y%m%d-%H%M%S)"

echo "=== Hyper2KVM Migration to Helm ==="
echo "Namespace: $NAMESPACE"
echo "Backup directory: $BACKUP_DIR"
echo ""

# Check if namespace exists
if ! kubectl get namespace "$NAMESPACE" &>/dev/null; then
    echo "ERROR: Namespace $NAMESPACE does not exist"
    exit 1
fi

# Check for existing resources
echo "Checking existing resources..."
EXISTING_DAEMONSET=$(kubectl get daemonset -n "$NAMESPACE" -l app=hyper2kvm-worker -o name 2>/dev/null || echo "")
EXISTING_CONFIGMAP=$(kubectl get configmap -n "$NAMESPACE" -l app=hyper2kvm-worker -o name 2>/dev/null || echo "")
EXISTING_PVCS=$(kubectl get pvc -n "$NAMESPACE" -o name 2>/dev/null || echo "")

if [ -z "$EXISTING_DAEMONSET" ]; then
    echo "No existing DaemonSet found. Nothing to migrate."
    exit 0
fi

echo "Found resources to migrate:"
echo "  DaemonSet: $EXISTING_DAEMONSET"
echo "  ConfigMap: $EXISTING_CONFIGMAP"
echo "  PVCs: $(echo $EXISTING_PVCS | wc -w) found"
echo ""

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Step 1: Backup current state
echo "Step 1: Backing up current state..."
./scripts/ops/backup-worker-state.sh "$NAMESPACE" "$BACKUP_DIR/worker-state" || {
    echo "WARNING: Failed to backup worker state"
}

# Step 2: Export current configuration
echo ""
echo "Step 2: Exporting current configuration..."
kubectl get daemonset -n "$NAMESPACE" -o yaml > "$BACKUP_DIR/daemonset.yaml"
kubectl get configmap -n "$NAMESPACE" -o yaml > "$BACKUP_DIR/configmaps.yaml"
kubectl get pvc -n "$NAMESPACE" -o yaml > "$BACKUP_DIR/pvcs.yaml"
kubectl get service -n "$NAMESPACE" -o yaml > "$BACKUP_DIR/services.yaml" 2>/dev/null || true
kubectl get servicemonitor -n "$NAMESPACE" -o yaml > "$BACKUP_DIR/servicemonitor.yaml" 2>/dev/null || true

echo "Configuration exported to $BACKUP_DIR/"

# Step 3: Generate Helm values from existing config
echo ""
echo "Step 3: Generating Helm values..."

# Extract resource limits from DaemonSet
CPU_REQUEST=$(kubectl get daemonset -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].resources.requests.cpu}' 2>/dev/null || echo "2")
MEM_REQUEST=$(kubectl get daemonset -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].resources.requests.memory}' 2>/dev/null || echo "4Gi")
CPU_LIMIT=$(kubectl get daemonset -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].resources.limits.cpu}' 2>/dev/null || echo "8")
MEM_LIMIT=$(kubectl get daemonset -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}' 2>/dev/null || echo "16Gi")

# Extract image
IMAGE_REPO=$(kubectl get daemonset -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].image}' | cut -d: -f1)
IMAGE_TAG=$(kubectl get daemonset -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].image}' | cut -d: -f2)

# Extract node selector
NODE_SELECTOR=$(kubectl get daemonset -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.nodeSelector}' 2>/dev/null || echo "{}")

# Create Helm values file
cat > "$BACKUP_DIR/helm-values.yaml" <<EOF
# Generated Helm values from existing deployment
# Date: $(date)
# Source namespace: $NAMESPACE

worker:
  image:
    repository: ${IMAGE_REPO:-hyper2kvm}
    tag: ${IMAGE_TAG:-worker}

  resources:
    requests:
      cpu: "$CPU_REQUEST"
      memory: "$MEM_REQUEST"
    limits:
      cpu: "$CPU_LIMIT"
      memory: "$MEM_LIMIT"

  nodeSelector:
    # Extracted from existing DaemonSet
    # Edit as needed
$(echo "$NODE_SELECTOR" | sed 's/^/    /')

storage:
  # PVCs will be preserved and adopted by Helm
  state:
    enabled: true
  events:
    enabled: true
  input:
    enabled: true
  output:
    enabled: true
  temp:
    enabled: true

monitoring:
  metrics:
    enabled: true
  serviceMonitor:
    enabled: $(kubectl get servicemonitor -n "$NAMESPACE" &>/dev/null && echo "true" || echo "false")
EOF

echo "Generated Helm values: $BACKUP_DIR/helm-values.yaml"
echo ""
echo "Please review and edit $BACKUP_DIR/helm-values.yaml as needed."
echo ""

# Step 4: Confirm migration
read -p "Ready to migrate to Helm? This will delete the existing DaemonSet. (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Migration cancelled."
    echo "Backup preserved at: $BACKUP_DIR"
    exit 0
fi

# Step 5: Delete existing DaemonSet (but preserve PVCs)
echo ""
echo "Step 5: Removing existing DaemonSet..."
kubectl delete daemonset -n "$NAMESPACE" -l app=hyper2kvm-worker --cascade=orphan

echo "DaemonSet deleted (pods orphaned, will be replaced by Helm)"

# Give pods time to start terminating
sleep 5

# Step 6: Install Helm chart
echo ""
echo "Step 6: Installing Helm chart..."
echo ""
echo "Running Helm install command..."
echo "helm install hyper2kvm-worker ./helm/hyper2kvm-worker \\"
echo "  --namespace $NAMESPACE \\"
echo "  --values $BACKUP_DIR/helm-values.yaml \\"
echo "  --wait"
echo ""

helm install hyper2kvm-worker ./helm/hyper2kvm-worker \
  --namespace "$NAMESPACE" \
  --values "$BACKUP_DIR/helm-values.yaml" \
  --wait

# Step 7: Verify deployment
echo ""
echo "Step 7: Verifying deployment..."
echo ""

kubectl get pods -n "$NAMESPACE" -l app=hyper2kvm-worker

echo ""
helm list -n "$NAMESPACE"

echo ""
echo "=== Migration Complete ==="
echo ""
echo "Backup preserved at: $BACKUP_DIR"
echo ""
echo "Next steps:"
echo "  1. Verify pods are running:"
echo "     kubectl get pods -n $NAMESPACE -l app=hyper2kvm-worker"
echo ""
echo "  2. Check logs:"
echo "     kubectl logs -n $NAMESPACE -l app=hyper2kvm-worker --tail=50"
echo ""
echo "  3. Restore worker state if needed:"
echo "     ./scripts/ops/restore-worker-state.sh $BACKUP_DIR/worker-state-*.tar.gz"
echo ""
echo "  4. Manage with Helm:"
echo "     helm upgrade hyper2kvm-worker ./helm/hyper2kvm-worker \\"
echo "       --namespace $NAMESPACE \\"
echo "       --values $BACKUP_DIR/helm-values.yaml"
