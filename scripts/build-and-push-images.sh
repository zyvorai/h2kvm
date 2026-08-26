#!/bin/bash
#
# Build and Push h2kvm Images to GitHub Container Registry
# Builds operator and worker images and pushes them to ghcr.io
#

set -eo pipefail

# Configuration
GHCR_REGISTRY="${GHCR_REGISTRY:-ghcr.io}"
GITHUB_USER="${GITHUB_USER:-ssahani}"
IMAGE_NAME="${IMAGE_NAME:-h2kvm}"
TAG="${TAG:-latest}"
PUSH="${PUSH:-true}"
BUILD_OPERATOR="${BUILD_OPERATOR:-true}"
BUILD_WORKER="${BUILD_WORKER:-true}"

log_info() {
    echo "ℹ️  [INFO] $1"
}

log_success() {
    echo "✅ [SUCCESS] $1"
}

log_error() {
    echo "❌ [ERROR] $1"
}

log_section() {
    echo ""
    echo "========================================"
    echo "🎯 $1"
    echo "========================================"
}

# Check prerequisites
check_prerequisites() {
    log_section "Prerequisites Check"

    if ! command -v docker &> /dev/null; then
        log_error "docker not found"
        exit 1
    fi
    log_success "docker is installed"

    if ! docker info &> /dev/null; then
        log_error "Cannot connect to docker daemon"
        exit 1
    fi
    log_success "docker daemon is accessible"
}

# Docker login to GHCR
docker_login() {
    log_section "Docker Login to GHCR"

    if [ -z "${GITHUB_TOKEN}" ]; then
        log_error "GITHUB_TOKEN not set. Please set it as an environment variable"
        log_info "Create token at: https://github.com/settings/tokens/new"
        log_info "Required scopes: write:packages, read:packages"
        exit 1
    else
        log_info "Logging in to ${GHCR_REGISTRY} as ${GITHUB_USER}..."
        echo "${GITHUB_TOKEN}" | docker login "${GHCR_REGISTRY}" -u "${GITHUB_USER}" --password-stdin
        log_success "Logged in to GHCR"
    fi
}

# Build operator image
build_operator() {
    log_section "Build Operator Image"

    local image_full="${GHCR_REGISTRY}/${GITHUB_USER}/${IMAGE_NAME}-operator:${TAG}"

    log_info "Building operator image: ${image_full}"

    if docker build -t "${image_full}" -f Dockerfile --target operator . ; then
        log_success "Operator image built: ${image_full}"

        # Also tag as latest locally
        docker tag "${image_full}" "${IMAGE_NAME}-operator:latest"
        log_success "Tagged locally as: ${IMAGE_NAME}-operator:latest"
    else
        log_error "Failed to build operator image"
        exit 1
    fi

    OPERATOR_IMAGE="${image_full}"
}

# Build worker image
build_worker() {
    log_section "Build Worker Image"

    local image_full="${GHCR_REGISTRY}/${GITHUB_USER}/${IMAGE_NAME}-worker:${TAG}"

    log_info "Building worker image: ${image_full}"

    if docker build -t "${image_full}" -f Dockerfile --target worker . ; then
        log_success "Worker image built: ${image_full}"

        # Also tag as latest locally
        docker tag "${image_full}" "${IMAGE_NAME}-worker:latest"
        docker tag "${image_full}" "h2kvm:worker"  # For k3d compatibility
        log_success "Tagged locally as: ${IMAGE_NAME}-worker:latest, h2kvm:worker"
    else
        log_error "Failed to build worker image"
        exit 1
    fi

    WORKER_IMAGE="${image_full}"
}

# Push images to GHCR
push_images() {
    log_section "Push Images to GHCR"

    if [ "${PUSH}" != "true" ]; then
        log_info "Skipping push (PUSH=${PUSH})"
        return 0
    fi

    if [ "${BUILD_OPERATOR}" = "true" ] && [ -n "${OPERATOR_IMAGE}" ]; then
        log_info "Pushing operator image: ${OPERATOR_IMAGE}"
        if docker push "${OPERATOR_IMAGE}"; then
            log_success "Operator image pushed successfully"
        else
            log_error "Failed to push operator image"
            exit 1
        fi
    fi

    if [ "${BUILD_WORKER}" = "true" ] && [ -n "${WORKER_IMAGE}" ]; then
        log_info "Pushing worker image: ${WORKER_IMAGE}"
        if docker push "${WORKER_IMAGE}"; then
            log_success "Worker image pushed successfully"
        else
            log_error "Failed to push worker image"
            exit 1
        fi
    fi
}

# Generate summary
generate_summary() {
    log_section "Build Summary"

    echo ""
    echo "📦 Images Built:"
    if [ "${BUILD_OPERATOR}" = "true" ]; then
        echo "  • Operator: ${OPERATOR_IMAGE}"
    fi
    if [ "${BUILD_WORKER}" = "true" ]; then
        echo "  • Worker:   ${WORKER_IMAGE}"
    fi

    echo ""
    if [ "${PUSH}" = "true" ]; then
        echo "✅ Images pushed to GHCR"
        echo ""
        echo "📝 To use in Kubernetes:"
        if [ "${BUILD_OPERATOR}" = "true" ]; then
            echo "  kubectl set image deployment/h2kvm-operator \\"
            echo "    operator=${OPERATOR_IMAGE} -n h2kvm-system"
        fi
        if [ "${BUILD_WORKER}" = "true" ]; then
            echo "  kubectl set image daemonset/h2kvm-worker \\"
            echo "    worker=${WORKER_IMAGE} -n h2kvm-workers"
        fi
    else
        echo "ℹ️  Images built locally only"
        echo ""
        echo "📝 To push manually:"
        if [ "${BUILD_OPERATOR}" = "true" ]; then
            echo "  docker push ${OPERATOR_IMAGE}"
        fi
        if [ "${BUILD_WORKER}" = "true" ]; then
            echo "  docker push ${WORKER_IMAGE}"
        fi
    fi

    echo ""
    echo "🔗 View packages at:"
    echo "  https://github.com/${GITHUB_USER}?tab=packages"
    echo ""
}

# Main execution
main() {
    log_section "Build and Push h2kvm Images"
    log_info "Registry: ${GHCR_REGISTRY}"
    log_info "User: ${GITHUB_USER}"
    log_info "Tag: ${TAG}"
    echo ""

    check_prerequisites

    if [ "${PUSH}" = "true" ]; then
        docker_login
    fi

    if [ "${BUILD_OPERATOR}" = "true" ]; then
        build_operator
    fi

    if [ "${BUILD_WORKER}" = "true" ]; then
        build_worker
    fi

    if [ "${PUSH}" = "true" ]; then
        push_images
    fi

    generate_summary

    log_success "All done!"
}

# Run main
main "$@"
