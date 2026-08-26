#!/bin/bash
set -euo pipefail

# run-fixer.sh — Entrypoint for the h2kvm fixer Job pod.
# Runs offline fixes (LVM activation, initramfs regen, fstab rewrite)
# on a disk image stored in a PVC.
#
# Environment variables (set by the operator):
#   DISK_PATH       — Path to disk image file inside the mounted PVC (required)
#   DISK_FORMAT     — Disk format: qcow2, vmdk, raw, etc. (default: qcow2)
#   SOURCE_FORMAT   — Original source format for detection (default: same as DISK_FORMAT)
#
# The PVC is mounted at /data by the Job spec.

DISK_PATH="${DISK_PATH:?DISK_PATH is required}"
DISK_FORMAT="${DISK_FORMAT:-qcow2}"

echo "[fixer] Starting offline fixes"
echo "[fixer] Disk: ${DISK_PATH}"
echo "[fixer] Format: ${DISK_FORMAT}"

# Verify the disk image exists
if [ ! -f "${DISK_PATH}" ]; then
    # CDI imports to /data/disk.img by default
    if [ -f "/data/disk.img" ]; then
        DISK_PATH="/data/disk.img"
        echo "[fixer] Auto-detected CDI disk at ${DISK_PATH}"
    else
        echo "[fixer] ERROR: Disk image not found at ${DISK_PATH}"
        echo "[fixer] Contents of /data:"
        ls -la /data/ || true
        exit 1
    fi
fi

# Load nbd kernel module if not loaded
if ! lsmod | grep -q '^nbd '; then
    echo "[fixer] Loading nbd kernel module"
    modprobe nbd max_part=16 || echo "[fixer] WARNING: Could not load nbd module (may already be loaded on host)"
fi

# Run h2kvmctl offline fixes
echo "[fixer] Running h2kvmctl offline-fix"
h2kvmctl offline-fix \
    --input "${DISK_PATH}" \
    --format "${DISK_FORMAT}" \
    --regen-initramfs \
    --fix-fstab \
    --fix-network \
    --verbose

echo "[fixer] Offline fixes completed successfully"
