#!/bin/bash
# Usage: v2v-luks-tpm-prepare.sh <vm-ip> <user> <new-luks-passphrase> [ssh-password]
#
# SSH into a running source VM on VMware and prepare LUKS for v2v conversion.
#
# Problem: LUKS may be sealed to TPM only (no passphrase keyslot).
#          After v2v, the KVM vTPM has different seeds so TPM unlock fails.
#
# Solution: While the VM is running on VMware (TPM is valid), detect
#           whether the guest uses clevis (Ubuntu 22.04) or
#           systemd-cryptenroll (Ubuntu 24.04+), recover the TPM-sealed
#           passphrase, add a new passphrase keyslot, and unbind TPM.
#
# Supports: Ubuntu 22.04 (clevis), Ubuntu 24.04+ (systemd-cryptenroll),
#           Fedora/RHEL (clevis or systemd-cryptenroll)
#
# After running this, convert with: h2kvmctl --key all:key:<passphrase>

set -euo pipefail

VM_IP="${1:?Usage: $0 <vm-ip> <user> <new-luks-passphrase> [ssh-password]}"
VM_USER="${2:?Usage: $0 <vm-ip> <user> <new-luks-passphrase> [ssh-password]}"
LUKS_PASS="${3:?Usage: $0 <vm-ip> <user> <new-luks-passphrase> [ssh-password]}"
SSH_PASS="${4:-}"

SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10"

do_ssh() {
    if [ -n "$SSH_PASS" ]; then
        sshpass -p "$SSH_PASS" ssh $SSH_OPTS "$@"
    else
        ssh $SSH_OPTS "$@"
    fi
}

do_scp() {
    if [ -n "$SSH_PASS" ]; then
        sshpass -p "$SSH_PASS" scp $SSH_OPTS "$@"
    else
        scp $SSH_OPTS "$@"
    fi
}

echo "=== v2v LUKS+TPM Preparation ==="
echo "  Target: ${VM_USER}@${VM_IP}"
echo ""

# Create the remote script
REMOTE_SCRIPT=$(mktemp /tmp/v2v-prepare-XXXXXX.sh)
cat > "$REMOTE_SCRIPT" <<'REMOTE_EOF'
#!/bin/bash
set -e
# Read passphrase from stdin (not command-line args, to avoid /proc exposure)
read -r LUKS_PASS

# Detect available tools
HAS_CLEVIS=false
HAS_CRYPTENROLL=false

if command -v clevis >/dev/null 2>&1; then
    HAS_CLEVIS=true
fi
if command -v systemd-cryptenroll >/dev/null 2>&1; then
    HAS_CRYPTENROLL=true
fi

echo "=== Guest OS ==="
if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo "  $PRETTY_NAME"
else
    echo "  Unknown"
fi
echo "  clevis: $HAS_CLEVIS"
echo "  systemd-cryptenroll: $HAS_CRYPTENROLL"
echo ""

DEVS=$(blkid -t TYPE=crypto_LUKS -o device 2>/dev/null || true)
if [ -z "$DEVS" ]; then
    echo "No LUKS devices found."
    exit 0
fi

# Detect TPM2 binding and recover passphrase for a given LUKS device.
# Returns: sets TPM_SLOT and RECOVERED_PASS, or leaves them empty.
detect_and_recover_tpm() {
    local dev="$1"
    TPM_SLOT=""
    RECOVERED_PASS=""

    if $HAS_CLEVIS; then
        # Ubuntu 22.04 / Fedora clevis style: clevis luks list / clevis luks pass
        TPM_SLOT=$(clevis luks list -d "$dev" 2>/dev/null | grep -i tpm2 | cut -d: -f1 | head -1 || true)
        if [ -n "$TPM_SLOT" ]; then
            echo "  Detected: clevis TPM2 binding in slot $TPM_SLOT"
            echo "  Recovering passphrase via clevis luks pass..."
            RECOVERED_PASS=$(clevis luks pass -d "$dev" -s "$TPM_SLOT" 2>/dev/null || true)
            if [ -n "$RECOVERED_PASS" ]; then
                echo "  Passphrase recovered (length: ${#RECOVERED_PASS})"
                return 0
            else
                echo "  WARNING: clevis luks pass failed"
            fi
        fi
    fi

    if $HAS_CRYPTENROLL; then
        # Ubuntu 24.04+ / Fedora 38+ style: systemd-cryptenroll uses LUKS2 tokens
        # Check for tpm2 tokens in luksDump
        TPM_SLOT=$(cryptsetup luksDump "$dev" 2>/dev/null | \
            grep -B2 "systemd-tpm2" | grep -oP '^\s+\K[0-9]+(?=:)' | head -1 || true)
        if [ -z "$TPM_SLOT" ]; then
            TPM_SLOT=$(cryptsetup luksDump "$dev" 2>/dev/null | \
                awk '/Tokens:/,/^$/' | grep -B1 "tpm2" | \
                grep -oP '^\s+\K[0-9]+(?=:)' | head -1 || true)
        fi
        if [ -n "$TPM_SLOT" ]; then
            echo "  Detected: systemd-cryptenroll TPM2 token $TPM_SLOT"
            echo "  Note: systemd-cryptenroll does not expose the sealed passphrase."
            echo "  Will use the provided passphrase to add recovery keyslot."
            return 1
        fi
    fi

    # No TPM binding found
    echo "  No TPM2 binding detected."
    return 1
}

# Remove TPM binding for a given LUKS device.
unbind_tpm() {
    local dev="$1"

    if $HAS_CLEVIS; then
        local clevis_slot
        clevis_slot=$(clevis luks list -d "$dev" 2>/dev/null | grep -i tpm2 | cut -d: -f1 | head -1 || true)
        if [ -n "$clevis_slot" ]; then
            echo "  Unbinding clevis TPM2 slot $clevis_slot..."
            clevis luks unbind -d "$dev" -s "$clevis_slot" -f 2>&1 || true
            echo "  Clevis TPM2 unbound."
            return 0
        fi
    fi

    if $HAS_CRYPTENROLL; then
        echo "  Wiping systemd-cryptenroll TPM2 slot..."
        systemd-cryptenroll --wipe-slot=tpm2 "$dev" 2>&1 \
            && echo "  TPM2 slot wiped." \
            || echo "  WARNING: Could not wipe TPM2 slot (may need passphrase)."
        return 0
    fi

    return 1
}

SUCCESS=0
TOTAL=0

for dev in $DEVS; do
    TOTAL=$((TOTAL + 1))
    echo "=== Processing $dev ==="

    # Show current keyslots
    echo "  Current LUKS keyslots:"
    cryptsetup luksDump "$dev" 2>/dev/null | grep -E "^\s+[0-9]+:" | head -10 || true
    echo ""

    if detect_and_recover_tpm "$dev"; then
        # TPM binding found and passphrase recovered (clevis path)
        echo "  Adding passphrase keyslot 7 using recovered passphrase..."
        printf '%s' "$RECOVERED_PASS" > /tmp/.v2v_oldkey
        printf '%s' "$LUKS_PASS" > /tmp/.v2v_newkey
        if cryptsetup luksAddKey "$dev" --key-file /tmp/.v2v_oldkey --key-slot 7 /tmp/.v2v_newkey 2>&1; then
            echo "  Passphrase keyslot 7 added."
            SUCCESS=$((SUCCESS + 1))
        else
            echo "  WARNING: Failed to add keyslot with recovered passphrase."
        fi
        shred -u /tmp/.v2v_oldkey /tmp/.v2v_newkey 2>/dev/null || true

        # Unbind TPM
        unbind_tpm "$dev"
    else
        # No clevis recovery available. Try adding keyslot with the provided passphrase.
        echo "  Adding passphrase keyslot 7 with provided passphrase..."
        printf '%s' "$LUKS_PASS" > /tmp/.v2v_newkey
        printf '%s' "$LUKS_PASS" > /tmp/.v2v_existkey
        if cryptsetup luksAddKey "$dev" --key-file /tmp/.v2v_existkey --key-slot 7 /tmp/.v2v_newkey 2>/dev/null; then
            echo "  Passphrase keyslot 7 added."
            SUCCESS=$((SUCCESS + 1))
        else
            echo "  WARNING: Could not add keyslot. The provided passphrase may be wrong,"
            echo "  or the LUKS volume may only have TPM-sealed keyslots."
            echo "  For TPM-only volumes, use clevis to recover the passphrase first."
            shred -u /tmp/.v2v_newkey /tmp/.v2v_existkey 2>/dev/null || true
            continue
        fi
        shred -u /tmp/.v2v_newkey /tmp/.v2v_existkey 2>/dev/null || true

        # Unbind TPM if detected
        unbind_tpm "$dev" 2>/dev/null || true
    fi

    # Verify
    echo ""
    echo "  Updated keyslots:"
    cryptsetup luksDump "$dev" 2>/dev/null | grep -E "^\s+[0-9]+:" | head -10 || true
    echo ""
done

echo ""
echo "=== Summary ==="
echo "  LUKS devices: $TOTAL"
echo "  Prepared:     $SUCCESS"
if [ "$SUCCESS" -gt 0 ]; then
    echo ""
    echo "  Ready for v2v conversion with: --key all:key:<passphrase>"
    echo "  Or with h2kvmctl: --luks-passphrase <passphrase>"
fi
REMOTE_EOF

# Copy script to remote and execute as root
echo "Copying preparation script to ${VM_IP}..."
do_scp "$REMOTE_SCRIPT" "${VM_USER}@${VM_IP}:/tmp/.v2v_prepare.sh"
echo "Executing on remote host (requires root)..."
echo ""
# Pass passphrase via stdin to avoid exposing it in process args (/proc/*/cmdline)
printf '%s' "$LUKS_PASS" | do_ssh "${VM_USER}@${VM_IP}" "sudo bash /tmp/.v2v_prepare.sh; rm -f /tmp/.v2v_prepare.sh"
rm -f "$REMOTE_SCRIPT"

echo ""
echo "=== Done ==="
