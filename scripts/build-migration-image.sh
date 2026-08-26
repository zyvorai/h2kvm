#!/bin/bash
# Build h2kvm migration container image
# This image is used by MigrationJob to run migrations inside Kubernetes

set -euo pipefail

# Configuration
IMAGE_NAME="${IMAGE_NAME:-ghcr.io/h2kvm/migration}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
DOCKERFILE="h2kvm/daemon/Dockerfile.migration"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"
PUSH="${PUSH:-false}"


echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🐳 Building h2kvm Migration Container"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo -e "  Image: ${IMAGE_NAME}:${IMAGE_TAG}"
echo -e "  Platforms: ${PLATFORMS}"
echo ""

# Check if buildx is available
if ! docker buildx version &>/dev/null; then
    echo "⚠️ ⚠️  Docker buildx not found, using regular build"
    BUILD_CMD="docker build"
    PLATFORM_ARG=""
else
    echo "✅ ✅ Using docker buildx for multi-platform build"
    if [ "$PUSH" = "true" ]; then
        BUILD_CMD="docker buildx build --push"
        PLATFORM_ARG="--platform ${PLATFORMS}"
    else
        BUILD_CMD="docker buildx build --load"
        PLATFORM_ARG=""  # --load only supports single platform
    fi
fi

# Build image
echo ""
echo "Building..."
if $BUILD_CMD \
    -f "${DOCKERFILE}" \
    -t "${IMAGE_NAME}:${IMAGE_TAG}" \
    $PLATFORM_ARG \
    .; then
    echo ""
    echo "✅ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "✅ ✅ Build successful!"
    echo "✅ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo -e "  Image: ${IMAGE_NAME}:${IMAGE_TAG}"
    echo ""
    echo -e "Usage in MigrationJob:"
    echo ""
    echo -e "  Update h2kvm/operator/migrationjob_controller.py:"
    echo -e "  MIGRATION_IMAGE = \"${IMAGE_NAME}:${IMAGE_TAG}\""
    echo ""
else
    echo ""
    echo "⚠️ ❌ Build failed"
    exit 1
fi
