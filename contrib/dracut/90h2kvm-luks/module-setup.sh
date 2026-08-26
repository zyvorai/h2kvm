#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
#
# H2KVM LUKS Auto-Unlock - dracut module
#
# Integrates with initramfs to unlock LUKS devices at boot time
# using TPM2, Vault, or keyfiles.

check() {
    # This module is optional
    return 255
}

depends() {
    # Require cryptsetup for LUKS
    echo crypt systemd
    return 0
}

install() {
    # Install cryptsetup and TPM tools
    inst_multiple \
        cryptsetup \
        blkid \
        tpm2_unseal

    # Install h2kvm Python package
    # Note: This assumes h2kvm is installed in the host system
    inst_simple /usr/bin/python3 /usr/bin/python3

    # Install h2kvm LUKS module
    if [ -d "/usr/lib/python3.*/site-packages/h2kvm/luks" ]; then
        inst_dir /usr/lib/python3.*/site-packages/h2kvm/luks
    fi

    # Install unlock script
    inst_simple "$moddir/h2kvm-luks-unlock.sh" \
        /usr/bin/h2kvm-luks-unlock

    # Install config
    if [ -f "/etc/h2kvm/luks.json" ]; then
        inst_simple /etc/h2kvm/luks.json /etc/h2kvm/luks.json
    fi

    # Hook into pre-mount phase
    # This runs before systemd tries to mount filesystems
    inst_hook pre-mount 90 "$moddir/h2kvm-luks-unlock.sh"

    # Also install systemd service for parallel unlock
    inst_simple "$moddir/h2kvm-luks-unlock.service" \
        "$systemdsystemunitdir/h2kvm-luks-unlock.service"

    # Enable the service
    $SYSTEMCTL -q --root "$initdir" enable h2kvm-luks-unlock.service
}

installkernel() {
    # Install TPM drivers if available
    hostonly='' instmods =drivers/char/tpm
}
