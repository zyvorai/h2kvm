#!/bin/bash
# Build Phase 4 Docker images
#
# This script builds both the NBD prep daemon and offline-fix VM images
# for the Phase 4 OfflineFixJob system.

set -euo pipefail

REGISTRY="${REGISTRY:-ghcr.io/h2kvm}"
VERSION="${VERSION:-v1.0.0}"

echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║         Building Phase 4 Docker Images                           ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""
echo "Registry: $REGISTRY"
echo "Version: $VERSION"
echo ""

# Change to repo root
cd "$(dirname "$0")/.."

# Build NBD prep daemon
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1. Building NBD Prep Daemon"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

docker build \
  -t "${REGISTRY}/nbd-prep:${VERSION}" \
  -t "${REGISTRY}/nbd-prep:latest" \
  -f h2kvm/daemon/Dockerfile \
  h2kvm/daemon/

echo "✅ NBD prep daemon image built"
echo ""

# Build offline-fix VM
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2. Building Offline-Fix VM"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

docker build \
  -t "${REGISTRY}/offline-fix-vm:${VERSION}" \
  -t "${REGISTRY}/offline-fix-vm:latest" \
  -f images/offline-fix-vm/Dockerfile \
  .

echo "✅ Offline-fix VM image built"
echo ""

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Build Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Images built:"
echo "  - ${REGISTRY}/nbd-prep:${VERSION}"
echo "  - ${REGISTRY}/nbd-prep:latest"
echo "  - ${REGISTRY}/offline-fix-vm:${VERSION}"
echo "  - ${REGISTRY}/offline-fix-vm:latest"
echo ""
echo "To push images:"
echo "  docker push ${REGISTRY}/nbd-prep:${VERSION}"
echo "  docker push ${REGISTRY}/offline-fix-vm:${VERSION}"
echo ""
echo "Or push all with latest:"
echo "  docker push ${REGISTRY}/nbd-prep:${VERSION}"
echo "  docker push ${REGISTRY}/nbd-prep:latest"
echo "  docker push ${REGISTRY}/offline-fix-vm:${VERSION}"
echo "  docker push ${REGISTRY}/offline-fix-vm:latest"
