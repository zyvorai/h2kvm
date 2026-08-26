#!/bin/bash
set -euo pipefail
# Extract firstboot log from Windows VM to verify driver installation

QCOW2="/home/ssahani/tt/h2kvm/out/win10-virtio-test/win10-virtio.qcow2"
LOG_PATH="/Windows/Temp/h2kvm-firstboot.log"

echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║       EXTRACTING FIRSTBOOT LOG FROM WINDOWS VM                    ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""

# Check if VM is running
if sudo virsh list --state-running | grep -q "win10-virtio-test"; then
    echo "⚠️  WARNING: VM is currently RUNNING"
    echo "   The VM must be shut down to read the log safely."
    echo ""
    echo "   Options:"
    echo "   1. Shut down Windows normally from inside the VM"
    echo "   2. Run: sudo virsh shutdown win10-virtio-test"
    echo "   3. Force stop: sudo virsh destroy win10-virtio-test"
    echo ""
    echo "   Then run this script again."
    exit 1
fi

echo "✓ VM is shut down, safe to read disk"
echo ""

# Extract the log
echo "Extracting: $LOG_PATH"
echo "From disk:  $QCOW2"
echo ""

if sudo guestfish --ro -a "$QCOW2" -m /dev/sda3 -- is-file "$LOG_PATH" 2>/dev/null; then
    echo "═══════════════════════════════════════════════════════════════════"
    echo "FIRSTBOOT LOG CONTENTS:"
    echo "═══════════════════════════════════════════════════════════════════"
    echo ""

    sudo guestfish --ro -a "$QCOW2" -m /dev/sda3 <<'GUESTFISH'
cat /Windows/Temp/h2kvm-firstboot.log
GUESTFISH

    echo ""
    echo "═══════════════════════════════════════════════════════════════════"
    echo ""

    # Check for key success indicators
    echo "ANALYSIS:"
    echo "─────────"

    TMPLOG=$(mktemp)
    sudo guestfish --ro -a "$QCOW2" -m /dev/sda3 cat "$LOG_PATH" > "$TMPLOG" 2>/dev/null

    if grep -q "pnputil rc=0" "$TMPLOG"; then
        echo "✅ VirtIO drivers installed successfully (pnputil rc=0)"
    else
        echo "⚠️  VirtIO driver installation may have issues"
    fi

    if grep -qi "vmware" "$TMPLOG"; then
        echo "✅ VMware removal attempted"
    fi

    if grep -q "Marker written" "$TMPLOG"; then
        echo "✅ Firstboot completed successfully (marker written)"
    fi

    if grep -q "Service delete attempted" "$TMPLOG"; then
        echo "✅ Firstboot service self-deleted"
    fi

    rm -f "$TMPLOG"

else
    echo "❌ ERROR: Firstboot log not found!"
    echo ""
    echo "Possible reasons:"
    echo "  1. Firstboot service hasn't run yet (VM never booted)"
    echo "  2. Wrong partition (trying /dev/sda3)"
    echo "  3. Log file in different location"
    echo ""
    echo "Available files in /Windows/Temp:"
    sudo guestfish --ro -a "$QCOW2" -m /dev/sda3 ls /Windows/Temp | head -20
fi

echo ""
echo "═══════════════════════════════════════════════════════════════════"
