#!/usr/bin/env bash
# ============================================================================
# e2e-migration-test.sh — End-to-end migration test
# ============================================================================
# Automated: migrate VMDK → verify VM boots → check network → cleanup
#
# Usage:
#   ./scripts/test/e2e-migration-test.sh <vmdk-path> [vm-name]
#   ./scripts/test/e2e-migration-test.sh /data/demo/ubuntu2404.vmdk
#   ./scripts/test/e2e-migration-test.sh /data/demo/centos9.vmdk centos-test
#
# Exit codes:
#   0 = all checks passed
#   1 = migration failed
#   2 = VM did not boot
#   3 = network not available
# ============================================================================

set -euo pipefail

info()  { echo "  ✅ $*"; }
warn()  { echo "  ⚠️  $*"; }
error() { echo "  ❌ $*"; }
step()  { echo "  🔧 $*"; }

KEEP_VM=false
POSITIONAL=()
for arg in "$@"; do
    case "$arg" in
        --keep) KEEP_VM=true ;;
        *) POSITIONAL+=("$arg") ;;
    esac
done

VMDK="${POSITIONAL[0]:?Usage: $0 <vmdk-path> [vm-name] [--keep]}"
VM_NAME="${POSITIONAL[1]:-e2e-test-$(date +%s)}"
OUTPUT_DIR="/var/lib/h2kvm/e2e-test/${VM_NAME}"
TIMEOUT_BOOT=180   # seconds to wait for boot
TIMEOUT_IP=120     # seconds to wait for IP

[ -f "$VMDK" ] || { error "File not found: $VMDK"; exit 1; }
[ "$(id -u)" -eq 0 ] || { error "Run as root"; exit 1; }

echo ""
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║     h2kvm E2E Migration Test                 ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo ""
echo "  Source:  $VMDK"
echo "  VM:     $VM_NAME"
echo "  Output: $OUTPUT_DIR"
echo ""

cleanup() {
    step "Cleanup: $VM_NAME"
    virsh destroy "$VM_NAME" 2>/dev/null || true
    virsh undefine "$VM_NAME" 2>/dev/null || true
    # Also clean any UUID-suffixed variants
    for vm in $(virsh list --all --name 2>/dev/null | grep "^${ORIG_VM_NAME}" 2>/dev/null); do
        virsh destroy "$vm" 2>/dev/null || true
        virsh undefine "$vm" 2>/dev/null || true
    done
    rm -rf "$OUTPUT_DIR"
    rm -f "/var/lib/h2kvm/input/${VM_NAME}.*"
}
ORIG_VM_NAME="$VM_NAME"

# Cleanup previous run
cleanup 2>/dev/null || true
mkdir -p "$OUTPUT_DIR"

# ── Step 1: Detect guest OS ──
step "Step 1: Detect guest OS"
BASENAME="$(basename "$VMDK")"
BASENAME_LOWER="$(echo "$BASENAME" | tr '[:upper:]' '[:lower:]')"
IS_WINDOWS=false
GUEST_OS="linux"
FSTAB_MODE="stabilize-all"
REGEN_INITRAMFS="true"
if [[ "$BASENAME_LOWER" == *win* ]]; then
    IS_WINDOWS=true
    GUEST_OS="windows"
    FSTAB_MODE="noop"
    REGEN_INITRAMFS="false"
fi
info "Guest OS: $GUEST_OS (windows=$IS_WINDOWS)"

# ── Step 2: Generate config ──
step "Step 2: Generate migration config"
CONFIG="${OUTPUT_DIR}/${VM_NAME}.yaml"
MEMORY=2048
VCPUS=2
if $IS_WINDOWS; then
    MEMORY=8192
    VCPUS=4
fi
cat > "$CONFIG" << YAML
cmd: local
vmdk: ${VMDK}
output_dir: ${OUTPUT_DIR}
to_output: ${VM_NAME}.qcow2
out_format: qcow2
flatten: true
compress: true
fstab_mode: ${FSTAB_MODE}
regen_initramfs: ${REGEN_INITRAMFS}
remove_vmware_tools: true
emit_domain_xml: true
virsh_define: true
vm_name: ${VM_NAME}
memory: ${MEMORY}
vcpus: ${VCPUS}
guest_os: ${GUEST_OS}
machine: q35
disk_bus: sata
net_model: virtio
graphics: vnc
keep_domain: true
timeout: 300
verbose: 1
YAML
info "Config: $CONFIG"

# ── Step 3: Run migration ──
step "Step 3: Running migration"
LOGFILE="${OUTPUT_DIR}/${VM_NAME}.log"
if ! h2kvmctl --config "$CONFIG" --allowed-dir "$OUTPUT_DIR" --allowed-dir "$(dirname "$VMDK")" > "$LOGFILE" 2>&1; then
    error "Migration failed! Log: $LOGFILE"
    tail -10 "$LOGFILE"
    cleanup
    exit 1
fi
info "Migration complete"

# ── Step 4: Verify VM defined ──
step "Step 4: Verify VM defined in libvirt"
# Domain name may have a UUID suffix appended by the emitter.
# Find the actual name from the emitted XML or virsh list.
ACTUAL_VM=$(virsh list --all --name 2>/dev/null | grep "^${VM_NAME}" | head -1)
if [ -z "$ACTUAL_VM" ]; then
    # Try from emitted XML
    ACTUAL_VM=$(grep -oP '<name>\K[^<]+' "${OUTPUT_DIR}/libvirt/"*.xml 2>/dev/null | head -1)
fi
if [ -n "$ACTUAL_VM" ] && [ "$ACTUAL_VM" != "$VM_NAME" ]; then
    info "Domain name has UUID suffix: $ACTUAL_VM"
    VM_NAME="$ACTUAL_VM"
fi
if ! virsh dominfo "$VM_NAME" &>/dev/null; then
    error "VM not defined in libvirt"
    cleanup
    exit 1
fi
info "VM defined: $VM_NAME"

# ── Step 5: Start VM ──
step "Step 5: Start VM"
virsh start "$VM_NAME" 2>/dev/null || true
sleep 5

STATE=$(virsh domstate "$VM_NAME" 2>/dev/null || echo "unknown")
if [ "$STATE" != "running" ]; then
    error "VM not running (state: $STATE)"
    cleanup
    exit 2
fi
info "VM running"

# ── Step 6: Wait for IP (skip for Windows) ──
if $IS_WINDOWS; then
    step "Step 6: Skipping network check (Windows — needs manual driver install)"
    info "Windows VM booted on SATA — install VirtIO drivers from CD-ROM (D:)"
else
    step "Step 6: Wait for IP address (${TIMEOUT_IP}s timeout)"
    VM_IP=""
    for i in $(seq 1 $((TIMEOUT_IP / 10))); do
        VM_IP=$(virsh domifaddr "$VM_NAME" --source lease 2>/dev/null \
            | awk '/ipv4/{print $4}' | cut -d/ -f1 | head -1)
        [ -n "$VM_IP" ] && break
        echo "    ⏳ attempt $i — no IP yet..."
        sleep 10
    done

    if [ -z "$VM_IP" ]; then
        warn "No IP address after ${TIMEOUT_IP}s"
        # Try ARP fallback
        VM_IP=$(virsh domifaddr "$VM_NAME" --source arp 2>/dev/null \
            | awk '/ipv4/{print $4}' | cut -d/ -f1 | head -1)
    fi

    if [ -n "$VM_IP" ]; then
        info "IP: $VM_IP"

        # ── Step 7: Test SSH ──
        step "Step 7: Test SSH connectivity"
        if timeout 10 bash -c "echo > /dev/tcp/$VM_IP/22" 2>/dev/null; then
            info "SSH port 22 reachable"
        else
            warn "SSH port 22 not reachable (firewall or SSH not running)"
        fi
    else
        error "No IP address — network may not be working"
        cleanup
        exit 3
    fi
fi

# ── Step 8: Take screenshot ──
step "Step 8: Take screenshot"
SCREENSHOT="${OUTPUT_DIR}/${VM_NAME}-screenshot.ppm"
virsh screenshot "$VM_NAME" "$SCREENSHOT" 2>/dev/null && \
    info "Screenshot: $SCREENSHOT" || \
    warn "Screenshot failed (non-fatal)"

# ── Summary ──
echo ""
echo "  ════════════════════════════════════════════════════"
echo "  ✅ E2E Test PASSED: $VM_NAME"
echo "  ════════════════════════════════════════════════════"
echo ""
echo "  VM:     $VM_NAME ($(virsh domstate "$VM_NAME" 2>/dev/null))"
[ -n "${VM_IP:-}" ] && echo "  IP:     $VM_IP"
echo "  Disk:   ${OUTPUT_DIR}/${VM_NAME}.qcow2"
echo "  Log:    $LOGFILE"
echo ""

# ── Cleanup (unless --keep) ──
if [ "${KEEP_VM:-false}" = "true" ]; then
    info "VM kept running: $VM_NAME (use virsh destroy/undefine to remove)"
else
    step "Cleanup"
    cleanup
fi
info "All cleaned up"

exit 0
