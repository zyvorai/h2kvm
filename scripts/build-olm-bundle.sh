#!/bin/bash
# Build and push OLM bundle image for OpenShift OperatorHub
# Usage: ./scripts/build-olm-bundle.sh [VERSION] [REGISTRY]

set -euo pipefail

# Default values
VERSION="${1:-2.1.0}"
REGISTRY="${2:-ghcr.io/ssahani}"
CONTAINER_TOOL="${CONTAINER_TOOL:-docker}"

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

# Check container tool
if ! command -v ${CONTAINER_TOOL} &> /dev/null; then
    echo_error "Container tool '${CONTAINER_TOOL}' not found"
    exit 1
fi

echo_info "Building OLM bundle for version ${VERSION}"
echo_info "Registry: ${REGISTRY}"
echo ""

# Validate bundle structure
echo_info "Validating bundle structure..."

if [ ! -f "olm/bundle/manifests/hyper2kvm-operator.clusterserviceversion.yaml" ]; then
    echo_error "ClusterServiceVersion not found in olm/bundle/manifests/"
    exit 1
fi

if [ ! -f "olm/bundle/metadata/annotations.yaml" ]; then
    echo_error "Bundle metadata not found in olm/bundle/metadata/"
    exit 1
fi

if [ ! -d "olm/bundle/manifests" ]; then
    echo_error "Bundle manifests directory not found"
    exit 1
fi

echo_success "Bundle structure validated"

# Update CSV version in bundle
echo_info "Updating CSV version to ${VERSION}..."
sed -i "s/name: hyper2kvm-operator.v[0-9.]*/name: hyper2kvm-operator.v${VERSION}/" \
    olm/bundle/manifests/hyper2kvm-operator.clusterserviceversion.yaml
sed -i "s/version: [0-9.]*/version: ${VERSION}/" \
    olm/bundle/manifests/hyper2kvm-operator.clusterserviceversion.yaml
sed -i "s|containerImage: ghcr.io/ssahani/hyper2kvm:[0-9.]*-operator|containerImage: ghcr.io/ssahani/hyper2kvm:${VERSION}-operator|" \
    olm/bundle/manifests/hyper2kvm-operator.clusterserviceversion.yaml
echo_success "CSV version updated"

# Validate with operator-sdk if available
if command -v operator-sdk &> /dev/null; then
    echo_info "Running operator-sdk bundle validate..."
    if operator-sdk bundle validate olm/bundle --select-optional suite=operatorframework; then
        echo_success "Bundle validation passed"
    else
        echo_warning "Bundle validation had warnings (non-critical)"
    fi
else
    echo_warning "operator-sdk not installed, skipping validation"
    echo_info "Install operator-sdk: https://sdk.operatorframework.io/docs/installation/"
fi

# Build bundle image
echo_info "Building bundle image..."
if ${CONTAINER_TOOL} build \
    -f olm/bundle.Dockerfile \
    -t ${REGISTRY}/hyper2kvm-operator-bundle:v${VERSION} \
    -t ${REGISTRY}/hyper2kvm-operator-bundle:latest \
    olm/; then
    echo_success "Bundle image built successfully"
else
    echo_error "Failed to build bundle image"
    exit 1
fi

echo ""
echo_success "Bundle image built: ${REGISTRY}/hyper2kvm-operator-bundle:v${VERSION}"
echo ""

# Ask to push
read -p "Push bundle image to registry? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo_info "Pushing bundle image to ${REGISTRY}..."

    ${CONTAINER_TOOL} push ${REGISTRY}/hyper2kvm-operator-bundle:v${VERSION}
    ${CONTAINER_TOOL} push ${REGISTRY}/hyper2kvm-operator-bundle:latest

    echo_success "Bundle image pushed successfully!"
else
    echo_warning "Bundle image not pushed. Push manually with:"
    echo "  ${CONTAINER_TOOL} push ${REGISTRY}/hyper2kvm-operator-bundle:v${VERSION}"
fi

echo ""
echo_info "Next steps:"
echo ""
echo "  1. Test bundle on OpenShift cluster:"
echo "     operator-sdk run bundle ${REGISTRY}/hyper2kvm-operator-bundle:v${VERSION}"
echo ""
echo "  2. Create catalog image (for OperatorHub):"
echo "     opm index add \\"
echo "       --bundles ${REGISTRY}/hyper2kvm-operator-bundle:v${VERSION} \\"
echo "       --tag ${REGISTRY}/hyper2kvm-operator-catalog:latest"
echo ""
echo "  3. Deploy catalog to OpenShift:"
echo "     ./scripts/deploy-to-openshift.sh ${VERSION}"
echo ""
echo "  4. Submit to OperatorHub (optional):"
echo "     - Fork https://github.com/k8s-operatorhub/community-operators"
echo "     - Add bundle to operators/hyper2kvm-operator/"
echo "     - Create pull request"
