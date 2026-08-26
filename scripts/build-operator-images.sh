#!/bin/bash
# Build and push operator images for OpenShift/Kubernetes deployment
# Usage: ./scripts/build-operator-images.sh [VERSION] [REGISTRY]

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
    echo_info "Install Docker or Podman, or set CONTAINER_TOOL environment variable"
    exit 1
fi

echo_info "Using container tool: ${CONTAINER_TOOL}"
echo_info "Version: ${VERSION}"
echo_info "Registry: ${REGISTRY}"

# Check if buildx is available for multi-platform builds
PLATFORM_ARG=""
if ${CONTAINER_TOOL} buildx version &>/dev/null; then
    PLATFORM_ARG="--platform linux/amd64,linux/arm64"
    echo_info "Multi-platform build enabled (buildx available)"
else
    echo_warning "buildx not available, building for local architecture only"
fi
echo ""

# Build operator image
echo_info "Building operator image..."
if ${CONTAINER_TOOL} build \
    --target operator \
    ${PLATFORM_ARG} \
    -t ${REGISTRY}/h2kvm:${VERSION}-operator \
    -t ${REGISTRY}/h2kvm:latest-operator \
    -f Dockerfile \
    .; then
    echo_success "Operator image built successfully"
else
    echo_error "Failed to build operator image"
    exit 1
fi

# Build worker image
echo_info "Building worker image..."
if ${CONTAINER_TOOL} build \
    --target worker \
    ${PLATFORM_ARG} \
    -t ${REGISTRY}/h2kvm:${VERSION}-worker \
    -t ${REGISTRY}/h2kvm:latest-worker \
    -f Dockerfile \
    .; then
    echo_success "Worker image built successfully"
else
    echo_error "Failed to build worker image"
    exit 1
fi

# Build CLI image
echo_info "Building CLI image..."
if ${CONTAINER_TOOL} build \
    --target cli \
    ${PLATFORM_ARG} \
    -t ${REGISTRY}/h2kvm:${VERSION}-cli \
    -t ${REGISTRY}/h2kvm:latest-cli \
    -f Dockerfile \
    .; then
    echo_success "CLI image built successfully"
else
    echo_error "Failed to build CLI image"
    exit 1
fi

# Build daemon image
echo_info "Building daemon image..."
if ${CONTAINER_TOOL} build \
    --target daemon \
    ${PLATFORM_ARG} \
    -t ${REGISTRY}/h2kvm:${VERSION}-daemon \
    -t ${REGISTRY}/h2kvm:latest-daemon \
    -f Dockerfile \
    .; then
    echo_success "Daemon image built successfully"
else
    echo_error "Failed to build daemon image"
    exit 1
fi

echo ""
echo_success "All images built successfully!"
echo ""
echo_info "Built images:"
echo "  - ${REGISTRY}/h2kvm:${VERSION}-operator"
echo "  - ${REGISTRY}/h2kvm:${VERSION}-worker"
echo "  - ${REGISTRY}/h2kvm:${VERSION}-cli"
echo "  - ${REGISTRY}/h2kvm:${VERSION}-daemon"
echo ""

# Ask to push
read -p "Push images to registry? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo_info "Pushing images to ${REGISTRY}..."

    ${CONTAINER_TOOL} push ${REGISTRY}/h2kvm:${VERSION}-operator
    ${CONTAINER_TOOL} push ${REGISTRY}/h2kvm:latest-operator

    ${CONTAINER_TOOL} push ${REGISTRY}/h2kvm:${VERSION}-worker
    ${CONTAINER_TOOL} push ${REGISTRY}/h2kvm:latest-worker

    ${CONTAINER_TOOL} push ${REGISTRY}/h2kvm:${VERSION}-cli
    ${CONTAINER_TOOL} push ${REGISTRY}/h2kvm:latest-cli

    ${CONTAINER_TOOL} push ${REGISTRY}/h2kvm:${VERSION}-daemon
    ${CONTAINER_TOOL} push ${REGISTRY}/h2kvm:latest-daemon

    echo_success "All images pushed successfully!"
else
    echo_warning "Images not pushed. Push manually with:"
    echo "  ${CONTAINER_TOOL} push ${REGISTRY}/h2kvm:${VERSION}-operator"
    echo "  ${CONTAINER_TOOL} push ${REGISTRY}/h2kvm:${VERSION}-worker"
fi

echo ""
echo_info "Next steps:"
echo "  1. Build OLM bundle: ./scripts/build-olm-bundle.sh ${VERSION}"
echo "  2. Test on OpenShift: ./scripts/deploy-to-openshift.sh ${VERSION}"
