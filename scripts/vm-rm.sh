#!/usr/bin/env bash
set -euo pipefail
# vm-rm.sh — Destroy and undefine a VM

if [[ $# -lt 1 ]]; then
    echo "❌ Usage: vm-rm.sh <vm-name> [--all]"
    echo
    virsh list --all
    exit 1
fi

if [[ "$1" == "--all" ]]; then
    if [[ "${2:-}" != "--force" ]]; then
        echo "This will destroy and undefine ALL VMs:"
        virsh list --name --all 2>/dev/null | grep -v '^$'
        echo ""
        read -p "Are you sure? (yes/no): " CONFIRM
        [[ "$CONFIRM" == "yes" ]] || { echo "Aborted."; exit 0; }
    fi
    for vm in $(virsh list --name --all 2>/dev/null); do
        [[ -z "$vm" ]] && continue
        echo "⚠️  Removing: $vm"
        virsh destroy "$vm" 2>/dev/null || true
        virsh undefine "$vm" --nvram 2>/dev/null || virsh undefine "$vm" 2>/dev/null || true
    done
    echo "✅ All VMs removed"
    exit 0
fi

VM="$1"

if ! virsh dominfo "$VM" &>/dev/null; then
    echo "❌ VM not found: $VM"
    echo
    virsh list --all
    exit 1
fi

STATE=$(virsh domstate "$VM" 2>/dev/null)
if [[ "$STATE" == "running" ]]; then
    echo "⚠️  Destroying: $VM"
    virsh destroy "$VM"
fi

echo "⚠️  Undefining: $VM"
virsh undefine "$VM" --nvram 2>/dev/null || virsh undefine "$VM"

echo "✅ Done: $VM removed"
