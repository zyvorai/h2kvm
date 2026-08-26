#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# Hyper2KVM LUKS Auto-Unlock - Initramfs Script
#
# Runs in initramfs to unlock LUKS devices before root mount.
# This is initramfs-safe (minimal dependencies, robust error handling).

set -e

# Logging helpers
log_info() {
    echo "hyper2kvm-luks: $*" >&2
}

log_error() {
    echo "hyper2kvm-luks ERROR: $*" >&2
}

# Check if we should run
if [ -f /.noluks ]; then
    log_info "LUKS unlock disabled (/.noluks exists)"
    exit 0
fi

# Find LUKS devices
find_luks_devices() {
    blkid -t TYPE=crypto_LUKS -o device 2>/dev/null || true
}

# Generate mapper name from device
mapper_name() {
    device="$1"
    # Use device name hash for consistency
    echo "hyper2kvm-$(echo "$device" | sha256sum | cut -c1-12)"
}

# Check if device is already unlocked
is_unlocked() {
    mapper="$1"
    [ -e "/dev/mapper/$mapper" ]
}

# Try TPM unlock
try_tpm_unlock() {
    device="$1"
    mapper="$2"
    handle="${HYPER2KVM_TPM_HANDLE:-0x81000010}"

    if [ ! -e /dev/tpm0 ] && [ ! -e /dev/tpmrm0 ]; then
        return 1
    fi

    if ! command -v tpm2_unseal >/dev/null 2>&1; then
        return 1
    fi

    log_info "Trying TPM2 unlock for $device (handle $handle)"

    # Unseal key from TPM
    if ! key=$(tpm2_unseal -c "$handle" 2>/dev/null); then
        log_info "TPM2 unseal failed"
        return 1
    fi

    # Try to unlock with key
    if echo "$key" | cryptsetup open --type luks "$device" "$mapper" --key-file=- 2>/dev/null; then
        log_info "✓ Unlocked $device via TPM2"
        return 0
    else
        log_error "TPM2 key invalid for $device"
        return 1
    fi
}

# Try keyfile unlock
try_keyfile_unlock() {
    device="$1"
    mapper="$2"
    keyfile="${HYPER2KVM_LUKS_KEYFILE:-/etc/hyper2kvm/luks.key}"

    if [ ! -f "$keyfile" ]; then
        return 1
    fi

    log_info "Trying keyfile unlock for $device"

    if cryptsetup open --type luks --key-file "$keyfile" "$device" "$mapper" 2>/dev/null; then
        log_info "✓ Unlocked $device via keyfile"
        return 0
    else
        log_error "Keyfile invalid for $device"
        return 1
    fi
}

# Main unlock logic
unlock_device() {
    device="$1"
    mapper=$(mapper_name "$device")

    # Check if already unlocked
    if is_unlocked "$mapper"; then
        log_info "Device $device already unlocked"
        return 0
    fi

    # Try unlock methods in priority order
    # 1. TPM2 (automatic, hardware-backed)
    if try_tpm_unlock "$device" "$mapper"; then
        return 0
    fi

    # 2. Keyfile (semi-automatic)
    if try_keyfile_unlock "$device" "$mapper"; then
        return 0
    fi

    # 3. Fall through to systemd password prompt
    log_info "Automatic unlock failed for $device - will prompt for password"
    return 1
}

# Main execution
main() {
    log_info "Starting LUKS auto-unlock"

    devices=$(find_luks_devices)

    if [ -z "$devices" ]; then
        log_info "No LUKS devices found"
        exit 0
    fi

    unlocked=0
    failed=0

    for device in $devices; do
        log_info "Processing $device"
        if unlock_device "$device"; then
            unlocked=$((unlocked + 1))
        else
            failed=$((failed + 1))
        fi
    done

    log_info "Unlock complete: $unlocked successful, $failed failed"

    # Always exit 0 to not block boot
    # Failed devices will fall back to systemd password prompt
    exit 0
}

# Run if executed directly (not sourced)
if [ "${0##*/}" = "hyper2kvm-luks-unlock.sh" ]; then
    main
fi
