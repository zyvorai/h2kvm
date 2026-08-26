#!/usr/bin/env bash
# run-demo-remote.sh — Convert a VMware VM and boot it on KVM
#
# Usage:
#   ./run-demo-remote.sh /root/hyper2kvm/RockyLinux_9.4_VMM_LinuxVMImages.COM.vmdk
#   ./run-demo-remote.sh /root/hyper2kvm/win10.ova
#
# Supports: .vmdk .ova .ovf .vhd .raw

set -euo pipefail

banner()  { echo ""; echo "━━━ 🔧 $* ━━━"; }
info()    { echo "✅ $*"; }
warn()    { echo "⚠️  $*"; }
err()     { echo "❌ $*" >&2; }
die()     { err "$@"; exit 1; }

# Cleanup noVNC processes on exit
cleanup() {
    for pf in /run/novnc-*.pid; do
        [[ -f "$pf" ]] || continue
        local pid
        pid=$(cat "$pf" 2>/dev/null) && [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
    done
}
trap cleanup EXIT

# ── Args ─────────────────────────────────────────────────────────────────
usage() {
    cat <<EOF
Usage: $0 [options] <path-to-vm-image> [vm-name]

Convert a VMware VM and boot it on KVM with optional noVNC console.

Arguments:
  path-to-vm-image   Path to .vmdk, .ova, .ovf, .vhd, or .raw file
  vm-name            Optional VM name (derived from filename if omitted)

Options:
  --dry-run          Show conversion plan without executing
  --cleanup          Remove previous demo VM and cleanup
  --help, -h         Show this help message

Examples:
  $0 /path/to/ubuntu.vmdk
  $0 /path/to/server.ova my-server
  $0 --dry-run /path/to/vm.vmdk
EOF
    exit 0
}

DRY_RUN=false
POSITIONAL=()
for arg in "$@"; do
    case "$arg" in
        --help|-h) usage ;;
        --dry-run) DRY_RUN=true ;;
        *) POSITIONAL+=("$arg") ;;
    esac
done
set -- "${POSITIONAL[@]}"

[[ $# -ge 1 ]] || usage

ORIG_SRC="$1"
[[ -f "$ORIG_SRC" ]] || die "File not found: $ORIG_SRC"

# Copy source to a safe working directory (avoids /root/* security restriction)
WORKDIR="/var/lib/hyper2kvm/input"
mkdir -p "$WORKDIR"
BASENAME_ORIG="$(basename "$ORIG_SRC")"
SRC="$WORKDIR/$BASENAME_ORIG"
if [[ "$ORIG_SRC" != "$SRC" ]]; then
    info "Copying source to $WORKDIR ..."
    cp -f "$ORIG_SRC" "$SRC"
fi

# Derive VM name from filename (strip path + extension)
BASENAME="$(basename "$SRC")"
VM_NAME="${2:-${BASENAME%.*}}"
# Sanitise for libvirt (keep alphanumeric, dot, dash, underscore)
VM_NAME="$(echo "$VM_NAME" | tr -c 'A-Za-z0-9._-' '-' | sed 's/^-//;s/-$//')"
[[ -n "$VM_NAME" ]] || VM_NAME="converted-vm"

# Use the login user's home directory (works under sudo)
if [[ -n "${SUDO_USER:-}" ]]; then
    _USER_HOME="$(eval echo ~"$SUDO_USER")"
else
    _USER_HOME="${HOME:-$(eval echo ~"$(whoami)")}"
fi
OUTPUT_DIR="${HYPER2KVM_OUTPUT:-${_USER_HOME}/hyper2kvm/output}/${VM_NAME}"

# Disk space check: need ~3x source size for conversion
SRC_SIZE_MB=$(( $(stat -c%s "$SRC" 2>/dev/null || echo 0) / 1048576 ))
NEEDED_MB=$(( SRC_SIZE_MB * 3 ))
AVAIL_MB=$(df -BM --output=avail "$(dirname "$OUTPUT_DIR")" 2>/dev/null | tail -1 | tr -d ' M' || echo 999999)
if (( AVAIL_MB < NEEDED_MB )); then
    die "Insufficient disk space: need ${NEEDED_MB}MB, have ${AVAIL_MB}MB"
fi

# Detect source format from extension
EXT="${BASENAME##*.}"
EXT_LOWER="$(echo "$EXT" | tr '[:upper:]' '[:lower:]')"

case "$EXT_LOWER" in
    vmdk) CMD="local"; SRC_FLAG="--vmdk" ;;
    ova)  CMD="ova";   SRC_FLAG="--ova"  ;;
    ovf)  CMD="ovf";   SRC_FLAG="--ovf"  ;;
    vhd|vhdx) CMD="vhd"; SRC_FLAG="--vhd" ;;
    raw|img)  CMD="raw"; SRC_FLAG="--raw" ;;
    qcow2)    CMD="local"; SRC_FLAG="--vmdk" ;;  # --vmdk is the generic input disk path; format is auto-detected
    *) die "Unsupported format: .$EXT_LOWER (expected vmdk/ova/ovf/vhd/raw)" ;;
esac

# ── 1. Teardown previous run ────────────────────────────────────────────
banner "Cleanup: $VM_NAME"

if virsh domstate "$VM_NAME" &>/dev/null; then
    info "Destroying running VM: $VM_NAME"
    virsh destroy "$VM_NAME" 2>/dev/null || true
    info "Undefining VM: $VM_NAME"
    virsh undefine "$VM_NAME" --nvram 2>/dev/null || \
    virsh undefine "$VM_NAME" 2>/dev/null || true
    info "Previous VM removed"
else
    info "No existing VM named '$VM_NAME'"
fi

rm -rf "$OUTPUT_DIR" /var/lib/hyper2kvm/conversions/*
info "Cleaned output directories"

# ── 2. Convert ──────────────────────────────────────────────────────────
banner "Convert: $BASENAME → KVM"
info "Source:  $SRC"
info "Format:  $EXT_LOWER (cmd=$CMD)"
info "VM name: $VM_NAME"
info "Output:  $OUTPUT_DIR"
echo

SRC_DIR="$(dirname "$SRC")"

if "$DRY_RUN"; then
    info "[DRY RUN] Source: $SRC ($SRC_SIZE_MB MB)"
    info "[DRY RUN] Output: $OUTPUT_DIR/$VM_NAME.qcow2"
    info "[DRY RUN] VM name: $VM_NAME"
    info "[DRY RUN] Would convert with: h2kvmctl --cmd $CMD $SRC_FLAG $SRC --output-dir $OUTPUT_DIR --vm-name $VM_NAME"
    exit 0
fi

h2kvmctl \
    --cmd "$CMD" \
    $SRC_FLAG "$SRC" \
    --output-dir "$OUTPUT_DIR" \
    --vm-name "$VM_NAME" \
    --allowed-dir "$SRC_DIR" \
    --emit-domain-xml \
    --virsh-define \
    --regen-initramfs \
    --verbose

# ── 3. Start VM ─────────────────────────────────────────────────────────
banner "Boot: $VM_NAME"

if ! (virsh domstate "$VM_NAME" 2>/dev/null | grep -q running); then
    virsh start "$VM_NAME" 2>/dev/null || true
fi

info "VM state: $(virsh domstate "$VM_NAME" 2>/dev/null || echo 'unknown')"

# ── 4. Domain info ──────────────────────────────────────────────────────
banner "Domain info: $VM_NAME"
virsh dominfo "$VM_NAME" 2>/dev/null || true
echo
virsh domblklist "$VM_NAME" 2>/dev/null || true
echo
virsh domiflist "$VM_NAME" 2>/dev/null || true

# ── 5. Wait for IP ──────────────────────────────────────────────────────
banner "Waiting for IP (up to 2 minutes)"

wait_for_vm_ip() {
    local vm="$1" timeout="${2:-120}" interval=5
    local elapsed=0
    while (( elapsed < timeout )); do
        local ip
        ip=$(virsh domifaddr "$vm" 2>/dev/null | awk '/ipv4/ {split($4,a,"/"); print a[1]}' | head -1)
        if [[ -n "$ip" ]]; then
            echo "$ip"
            return 0
        fi
        sleep "$interval"
        elapsed=$(( elapsed + interval ))
    done
    return 1
}

VM_IP=$(wait_for_vm_ip "$VM_NAME" 120) || VM_IP=""

if [[ -z "$VM_IP" ]]; then
    # Try ARP as fallback
    VM_IP=$(virsh domifaddr "$VM_NAME" --source arp 2>/dev/null \
        | awk '/ipv4/ {split($4,a,"/"); print a[1]}' | head -1 || true)
fi

# ── 6. Summary ──────────────────────────────────────────────────────────
banner "Result"

# ── 6a. Start noVNC remote console ─────────────────────────────────────
# (run in a subshell so pipefail failures don't kill the main script)
NOVNC_OK=false
NOVNC_URL=""
if _novnc_result=$(
    set +e  # disable errexit in subshell
    VNC_DISPLAY=$(virsh vncdisplay "$VM_NAME" 2>/dev/null | sed 's/.*://')
    if [[ -n "$VNC_DISPLAY" && "$VNC_DISPLAY" =~ ^[0-9]+$ ]]; then
        VNC_PORT=$((5900 + VNC_DISPLAY))
        NOVNC_PORT=$((6080 + VNC_DISPLAY))
    else
        VNC_PORT=5900
        NOVNC_PORT=6080
    fi
    PUBLIC_IP=$(ip -4 route get 1 2>/dev/null | awk '{print $7; exit}')
    [[ -z "$PUBLIC_IP" ]] && PUBLIC_IP=$(hostname -I | awk '{print $1}')

    # Kill previous instance via PID file
    NOVNC_PIDFILE="/run/novnc-${NOVNC_PORT}.pid"
    if [[ -f "$NOVNC_PIDFILE" ]]; then
        OLD_PID=$(cat "$NOVNC_PIDFILE" 2>/dev/null)
        [[ -n "$OLD_PID" ]] && kill "$OLD_PID" 2>/dev/null
        rm -f "$NOVNC_PIDFILE"
        sleep 1
    fi

    # Auto-install if missing
    if ! command -v websockify &>/dev/null || [[ ! -d /usr/share/novnc ]]; then
        if command -v dnf &>/dev/null; then
            dnf install -y novnc python3-websockify &>/dev/null
        elif command -v apt-get &>/dev/null; then
            apt-get install -y novnc python3-websockify &>/dev/null
        fi
    fi

    # Start websockify
    if command -v websockify &>/dev/null && [[ -d /usr/share/novnc ]]; then
        websockify --web /usr/share/novnc/ --daemon "${NOVNC_PORT}" "127.0.0.1:${VNC_PORT}" 2>/dev/null
        sleep 1
        if ss -tlnp 2>/dev/null | grep -q ":${NOVNC_PORT}"; then
            PID=$(ss -tlnp 2>/dev/null | grep ":${NOVNC_PORT}" | grep -oP 'pid=\K[0-9]+' | head -1)
            [[ -n "$PID" ]] && echo "$PID" > "$NOVNC_PIDFILE"
            # Open firewall
            if command -v firewall-cmd &>/dev/null; then
                firewall-cmd --add-port="${NOVNC_PORT}/tcp" &>/dev/null
            elif command -v iptables &>/dev/null; then
                iptables -C INPUT -p tcp --dport "${NOVNC_PORT}" -j ACCEPT 2>/dev/null || \
                    iptables -I INPUT -p tcp --dport "${NOVNC_PORT}" -j ACCEPT 2>/dev/null
            fi
            echo "OK:http://${PUBLIC_IP}:${NOVNC_PORT}/vnc.html"
            exit 0
        fi
    fi
    exit 1
) 2>/dev/null; then
    NOVNC_OK=true
    NOVNC_URL="${_novnc_result#OK:}"
fi

if [[ -n "$VM_IP" ]]; then
    echo ""
    echo "  ┌─────────────────────────────────────────┐"
    echo "  │  Migration complete!                     │"
    echo "  ├─────────────────────────────────────────┤"
    printf "  │  VM name : %-28s│\n" "$VM_NAME"
    printf "  │  IP addr : %-28s│\n" "$VM_IP"
    printf "  │  Source  : %-28s│\n" "$EXT_LOWER"
    echo "  │  State   : running                      │"
    echo "  ├─────────────────────────────────────────┤"
    echo "  │  ssh user@$VM_IP"
    if $NOVNC_OK; then
        echo "  │  🖥️  $NOVNC_URL"
    fi
    echo "  └─────────────────────────────────────────┘"
    echo ""
else
    warn "VM is running but no IP address detected yet."
    warn "Check manually: virsh domifaddr $VM_NAME --source lease"
    if $NOVNC_OK; then
        info "noVNC console: $NOVNC_URL"
    fi
fi
