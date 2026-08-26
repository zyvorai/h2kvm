#!/bin/bash
# =============================================================================
# Upload QCOW2 Image to Existing KubeVirt Cluster
# =============================================================================
# Quick upload script for when you already have KubeVirt running
#
# Usage:
#   ./upload-to-kubevirt.sh [namespace]
# =============================================================================

set -euo pipefail

NAMESPACE="${1:-rhel-vms}"
QCOW2_IMAGE="${QCOW2_IMAGE:-./output/rhel8.8-fixed.qcow2}"
PVC_NAME="${PVC_NAME:-rhel8-disk}"
PVC_SIZE="${PVC_SIZE:-20Gi}"

echo "📤 Uploading QCOW2 image to KubeVirt..."
echo "   Image: $QCOW2_IMAGE"
echo "   Namespace: $NAMESPACE"
echo "   PVC: $PVC_NAME"
echo ""

# Ensure namespace exists
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# Check if virtctl is available
if ! command -v virtctl &> /dev/null; then
    echo "❌ virtctl not found!"
    echo ""
    echo "Install virtctl:"
    echo "  VERSION=v1.2.0"
    echo "  wget https://github.com/kubevirt/kubevirt/releases/download/\${VERSION}/virtctl-\${VERSION}-linux-amd64"
    echo "  chmod +x virtctl-\${VERSION}-linux-amd64"
    echo "  sudo mv virtctl-\${VERSION}-linux-amd64 /usr/local/bin/virtctl"
    exit 1
fi

# Upload the image
echo "⏳ Uploading image (this may take several minutes)..."
virtctl image-upload pvc "$PVC_NAME" \
    --namespace="$NAMESPACE" \
    --image-path="$QCOW2_IMAGE" \
    --size="$PVC_SIZE" \
    --insecure \
    --force-bind \
    --uploadproxy-url=https://$(kubectl get service -n cdi cdi-uploadproxy -o jsonpath='{.spec.clusterIP}'):443

echo ""
echo "✅ Upload complete!"
echo ""
echo "Deploy the VM:"
echo "  kubectl apply -f kubevirt-rhel8.8-deployment.yaml"
