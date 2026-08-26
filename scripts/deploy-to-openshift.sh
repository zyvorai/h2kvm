#!/bin/bash
# Deploy hyper2kvm operator to OpenShift cluster
# Usage: ./scripts/deploy-to-openshift.sh [VERSION] [METHOD] [NAMESPACE]

set -euo pipefail

# Default values
VERSION="${1:-0.3.0}"
METHOD="${2:-helm}"  # helm, olm, or manual
NAMESPACE="${3:-hyper2kvm-system}"
REGISTRY="${REGISTRY:-ghcr.io/ssahani}"

# Color output

echo_info() {
    echo "ℹ $1"
}

echo_success() {
    echo "✓ $1"
}

echo_warning() {
    echo "⚠ $1"
}

echo_error() {
    echo "✗ $1"
}

# Check if oc is installed
if ! command -v oc &> /dev/null; then
    echo_error "OpenShift CLI 'oc' not found"
    echo_info "Install from: https://docs.openshift.com/container-platform/latest/cli_reference/openshift_cli/getting-started-cli.html"
    exit 1
fi

# Check if logged in to OpenShift
if ! oc whoami &> /dev/null; then
    echo_error "Not logged in to OpenShift cluster"
    echo_info "Login with: oc login <cluster-url>"
    exit 1
fi

CLUSTER_URL=$(oc whoami --show-server)
CURRENT_USER=$(oc whoami)

echo ""
echo_info "=== OpenShift Deployment ==="
echo_info "Cluster: ${CLUSTER_URL}"
echo_info "User: ${CURRENT_USER}"
echo_info "Version: ${VERSION}"
echo_info "Method: ${METHOD}"
echo_info "Namespace: ${NAMESPACE}"
echo_info "Registry: ${REGISTRY}"
echo ""

# Function to deploy via Helm
deploy_helm() {
    echo_info "Deploying via Helm..."

    # Check if helm is installed
    if ! command -v helm &> /dev/null; then
        echo_error "Helm not found"
        echo_info "Install from: https://helm.sh/docs/intro/install/"
        exit 1
    fi

    # Create namespace if it doesn't exist
    if ! oc get namespace ${NAMESPACE} &> /dev/null; then
        echo_info "Creating namespace ${NAMESPACE}..."
        oc new-project ${NAMESPACE}
        echo_success "Namespace created"
    else
        echo_info "Using existing namespace ${NAMESPACE}"
    fi

    # Add helm repo
    echo_info "Adding Helm repository..."
    helm repo add hyper2kvm https://ssahani.github.io/hyper2kvm || true
    helm repo update

    # Create values file for OpenShift
    cat > /tmp/hyper2kvm-openshift-values.yaml <<EOF
global:
  namespace: ${NAMESPACE}

# Enable OpenShift features
openshift:
  enabled: true
  autoDetect: true

  # Routes for external access
  route:
    enabled: true
    tls:
      termination: edge
      insecureEdgeTerminationPolicy: Redirect

  # SecurityContextConstraints
  scc:
    create: true
    name: hyper2kvm-worker-scc

  # OAuth proxy for authenticated metrics
  oauth:
    enabled: true

# Operator configuration
operator:
  image:
    repository: ${REGISTRY}/hyper2kvm
    tag: "${VERSION}-operator"
  replicaCount: 2  # HA deployment
  leaderElection:
    enabled: true

# Webhook configuration
webhook:
  enabled: true
  replicaCount: 2  # HA deployment
  image:
    repository: ${REGISTRY}/hyper2kvm
    tag: "${VERSION}-operator"

# Monitoring
monitoring:
  prometheus:
    enabled: true
  grafana:
    enabled: true
EOF

    echo_info "Installing operator with Helm..."
    helm upgrade --install hyper2kvm-operator hyper2kvm/hyper2kvm-operator \
        --namespace ${NAMESPACE} \
        --values /tmp/hyper2kvm-openshift-values.yaml \
        --wait \
        --timeout 10m

    echo_success "Operator installed via Helm"

    # Show routes
    echo ""
    echo_info "Getting Routes..."
    oc get routes -n ${NAMESPACE}
}

# Function to deploy via OLM
deploy_olm() {
    echo_info "Deploying via OLM (Operator Lifecycle Manager)..."

    # Check if operator-sdk is installed
    if ! command -v operator-sdk &> /dev/null; then
        echo_error "operator-sdk not found"
        echo_info "Install from: https://sdk.operatorframework.io/docs/installation/"
        exit 1
    fi

    # Run bundle
    echo_info "Running OLM bundle..."
    operator-sdk run bundle ${REGISTRY}/hyper2kvm-operator-bundle:v${VERSION} \
        --namespace ${NAMESPACE}

    echo_success "Operator installed via OLM"
}

# Function to deploy manually
deploy_manual() {
    echo_info "Deploying manually with manifests..."

    # Create namespace if it doesn't exist
    if ! oc get namespace ${NAMESPACE} &> /dev/null; then
        echo_info "Creating namespace ${NAMESPACE}..."
        oc new-project ${NAMESPACE}
        echo_success "Namespace created"
    fi

    # Apply CRDs
    echo_info "Applying CRDs..."
    oc apply -f k8s/operator/crds/

    # Apply SCC (render Helm template first, raw templates contain Go syntax)
    echo_info "Applying SecurityContextConstraints..."
    if command -v helm &> /dev/null && [ -d helm/hyper2kvm-operator ]; then
        helm template hyper2kvm-operator helm/hyper2kvm-operator \
            --set openshift.scc.create=true \
            --show-only templates/openshift-scc.yaml 2>/dev/null | oc apply -f -
    else
        echo_warning "Helm not available — skipping SCC template rendering"
        echo_info "Apply SCC manually: helm template ... | oc apply -f -"
    fi

    # Apply operator manifests (only CRDs and non-template files)
    echo_info "Applying operator manifests..."
    oc apply -f k8s/operator/ -n ${NAMESPACE}

    echo_success "Operator installed manually"
}

# Deploy based on method
case ${METHOD} in
    helm)
        deploy_helm
        ;;
    olm)
        deploy_olm
        ;;
    manual)
        deploy_manual
        ;;
    *)
        echo_error "Invalid deployment method: ${METHOD}"
        echo_info "Valid methods: helm, olm, manual"
        exit 1
        ;;
esac

echo ""
echo_success "=== Deployment Complete ==="
echo ""

# Verify deployment
echo_info "Verifying deployment..."
echo ""

echo "Operator pods:"
oc get pods -n ${NAMESPACE} -l app.kubernetes.io/name=hyper2kvm-operator

echo ""
echo "Webhook pods:"
oc get pods -n ${NAMESPACE} -l app.kubernetes.io/component=webhook

echo ""
echo "Routes:"
oc get routes -n ${NAMESPACE}

echo ""
echo "CRDs:"
oc get crd | grep hyper2kvm

echo ""
echo_info "Next steps:"
echo ""
echo "  1. Check operator logs:"
echo "     oc logs -n ${NAMESPACE} -l app.kubernetes.io/name=hyper2kvm-operator -f"
echo ""
echo "  2. Create a test migration job:"
echo "     oc apply -f k8s/operator/examples/convert-job.yaml"
echo ""
echo "  3. Watch job status:"
echo "     oc get migrationjobs --watch"
echo ""
echo "  4. Access metrics (if OAuth enabled):"
echo "     ROUTE=\$(oc get route hyper2kvm-operator-metrics -n ${NAMESPACE} -o jsonpath='{.spec.host}')"
echo "     curl -k -H \"Authorization: Bearer \$(oc whoami -t)\" https://\$ROUTE/metrics"
echo ""
echo "  5. View in OpenShift Console:"
echo "     Navigate to: Workloads → MigrationJobs"
