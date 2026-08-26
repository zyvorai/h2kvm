#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
#
# Hyper2KVM LUKS Auto-Unlock - dracut module
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

    # Install hyper2kvm Python package
    # Note: This assumes hyper2kvm is installed in the host system
    inst_simple /usr/bin/python3 /usr/bin/python3

    # Install hyper2kvm LUKS module
    if [ -d "/usr/lib/python3.*/site-packages/hyper2kvm/luks" ]; then
        inst_dir /usr/lib/python3.*/site-packages/hyper2kvm/luks
    fi

    # Install unlock script
    inst_simple "$moddir/hyper2kvm-luks-unlock.sh" \
        /usr/bin/hyper2kvm-luks-unlock

    # Install config
    if [ -f "/etc/hyper2kvm/luks.json" ]; then
        inst_simple /etc/hyper2kvm/luks.json /etc/hyper2kvm/luks.json
    fi

    # Hook into pre-mount phase
    # This runs before systemd tries to mount filesystems
    inst_hook pre-mount 90 "$moddir/hyper2kvm-luks-unlock.sh"

    # Also install systemd service for parallel unlock
    inst_simple "$moddir/hyper2kvm-luks-unlock.service" \
        "$systemdsystemunitdir/hyper2kvm-luks-unlock.service"

    # Enable the service
    $SYSTEMCTL -q --root "$initdir" enable hyper2kvm-luks-unlock.service
}

installkernel() {
    # Install TPM drivers if available
    hostonly='' instmods =drivers/char/tpm
}
