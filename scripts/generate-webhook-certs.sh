#!/bin/bash
#
# generate-webhook-certs.sh - Generate TLS certificates for admission webhook
#
# This script generates:
# - CA certificate
# - Webhook server certificate (signed by CA)
# - Kubernetes Secret with certificates
# - Updated webhook configuration with CA bundle
#
# Usage:
#   ./generate-webhook-certs.sh [namespace] [service-name]
#
# Example:
#   ./generate-webhook-certs.sh h2kvm-system h2kvm-webhook
#

set -euo pipefail

NAMESPACE="${1:-h2kvm-system}"
SERVICE_NAME="${2:-h2kvm-webhook}"
SECRET_NAME="h2kvm-webhook-certs"
WEBHOOK_CONFIG="k8s/operator/webhook-config.yaml"

echo "=== Generating Webhook TLS Certificates ==="
echo "Namespace: $NAMESPACE"
echo "Service: $SERVICE_NAME"
echo ""

# Create temporary directory
ORIG_DIR="$(pwd)"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

cd "$TMP_DIR"

# Generate CA private key
echo "Generating CA private key..."
openssl genrsa -out ca.key 2048

# Generate CA certificate
echo "Generating CA certificate..."
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 \
  -out ca.crt \
  -subj "/CN=h2kvm-webhook-ca"

# Generate server private key
echo "Generating server private key..."
openssl genrsa -out server.key 2048

# Create certificate signing request config
cat > csr.conf << EOF
[req]
req_extensions = v3_req
distinguished_name = req_distinguished_name

[req_distinguished_name]

[v3_req]
basicConstraints = CA:FALSE
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = ${SERVICE_NAME}
DNS.2 = ${SERVICE_NAME}.${NAMESPACE}
DNS.3 = ${SERVICE_NAME}.${NAMESPACE}.svc
DNS.4 = ${SERVICE_NAME}.${NAMESPACE}.svc.cluster.local
EOF

# Generate certificate signing request
echo "Generating CSR..."
openssl req -new -key server.key -out server.csr \
  -subj "/CN=${SERVICE_NAME}.${NAMESPACE}.svc" \
  -config csr.conf

# Sign server certificate with CA
echo "Signing server certificate..."
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key \
  -CAcreateserial -out server.crt -days 3650 \
  -extensions v3_req -extfile csr.conf

echo ""
echo "=== Certificates Generated ==="
echo "CA certificate: ca.crt"
echo "Server certificate: server.crt"
echo "Server key: server.key"
echo ""

# Verify certificate
echo "Verifying certificate..."
openssl verify -CAfile ca.crt server.crt

# Encode CA bundle for webhook config
CA_BUNDLE=$(cat ca.crt | base64 | tr -d '\n')

echo ""
echo "=== Creating Kubernetes Secret ==="

# Create or update secret
kubectl create secret generic "$SECRET_NAME" \
  --from-file=tls.crt=server.crt \
  --from-file=tls.key=server.key \
  --from-file=ca.crt=ca.crt \
  --namespace="$NAMESPACE" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Secret created: $SECRET_NAME in namespace $NAMESPACE"
echo ""

# Update webhook configuration with CA bundle
echo "=== Updating Webhook Configuration ==="

if [ -f "$ORIG_DIR/$WEBHOOK_CONFIG" ]; then
    # Create updated webhook config
    WEBHOOK_OUTPUT="$ORIG_DIR/webhook-config-updated.yaml"
    sed "s|\${CA_BUNDLE}|$CA_BUNDLE|g" "$ORIG_DIR/$WEBHOOK_CONFIG" > "$WEBHOOK_OUTPUT"

    echo "Updated webhook configuration saved to: $WEBHOOK_OUTPUT"
    echo ""
    echo "To apply the webhook configuration:"
    echo "  kubectl apply -f $WEBHOOK_OUTPUT"
    echo ""

    # Optionally apply directly
    read -p "Apply webhook configuration now? (yes/no): " APPLY
    if [ "$APPLY" == "yes" ]; then
        kubectl apply -f "$WEBHOOK_OUTPUT"
        echo "Webhook configuration applied!"
    fi
else
    echo "WARNING: Webhook config file not found: $ORIG_DIR/$WEBHOOK_CONFIG"
    echo "CA Bundle (copy this to webhook config caBundle field):"
    echo "$CA_BUNDLE"
fi

echo ""
echo "=== Certificate Generation Complete ==="
echo ""
echo "Verify webhook is running:"
echo "  kubectl get pods -n $NAMESPACE -l app=h2kvm-webhook"
echo ""
echo "Test webhook:"
echo "  kubectl apply -f k8s/operator/examples/convert-job.yaml"
echo ""
echo "View webhook logs:"
echo "  kubectl logs -n $NAMESPACE -l app=h2kvm-webhook -f"
