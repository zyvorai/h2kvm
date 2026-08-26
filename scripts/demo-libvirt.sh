#!/usr/bin/env bash
# ============================================
# demo-libvirt.sh — Migrate VM images to KVM + Libvirt
# ============================================
# One-command VMware VMDK/OVA/VHD to running KVM VM.
#
# Supports: .vmdk .ova .ovf .vhd .vhdx .raw .img .qcow2
# Default credentials (osboxes.org images): osboxes / osboxes.org
# ============================================

set -euo pipefail

info()  { echo "  ✅ $*"; }
warn()  { echo "  ⚠️  $*"; }
error() { echo "  ❌ $*"; }
step()  { echo "  🔧 $*"; }
die()   { error "$@"; exit 1; }

OUTPUT_BASE="/var/lib/hyper2kvm/demo"
LOGDIR="/var/log/hyper2kvm"
# Use the login user's home directory (works under sudo)
if [[ -n "${SUDO_USER:-}" ]]; then
    _USER_HOME="$(eval echo ~"$SUDO_USER")"
else
    _USER_HOME="${HOME:-$(eval echo ~"$(whoami)")}"
fi
DEMO_DIR="${HYPER2KVM_DEMO_DIR:-${_USER_HOME}/demo}"

# Defaults (overridable via flags)
OPT_MEMORY=2048
OPT_VCPUS=2
OPT_NO_FIXES=false
OPT_DRY_RUN=false

# ── Usage / Help ──
usage() {
    echo ""
    echo "  demo-libvirt.sh — Migrate VMware images to KVM + Libvirt"
    echo ""
    echo "  Usage:"
    echo "    $0 <image> [vm-name]         Migrate a VM image"
    echo "    $0 --all                     Migrate ALL VMDKs in ${DEMO_DIR}/"
    echo "    $0 --list                    Show migrated VMs with IPs"
    echo "    $0 --cleanup [vm-name]       Remove one or all migrated VMs"
    echo "    $0 --status                  Show all libvirt VMs"
    echo "    $0 --help                    Show this help"
    echo ""
    echo "  Options:"
    echo "    --memory <MB>                VM memory (default: 2048)"
    echo "    --vcpus <N>                  VM CPUs (default: 2)"
    echo "    --no-fixes                   Skip offline guest fixes (for cloud images)"
    echo "    --dry-run                    Show what would happen, don't migrate"
    echo ""
    echo "  Examples:"
    echo "    $0 centos9.vmdk                          # auto-finds in ${DEMO_DIR}/"
    echo "    $0 ubuntu2404.vmdk my-ubuntu             # custom VM name"
    echo "    $0 debian12.vmdk --memory 4096 --vcpus 4 # custom resources"
    echo "    $0 centos9.vmdk --no-fixes               # skip offline fixes"
    echo "    $0 centos9.vmdk --dry-run                # dry run"
    echo "    $0 --all                                 # migrate everything"
    echo "    $0 --cleanup centos9                     # remove one VM"
    echo "    $0 --cleanup                             # remove ALL migrated VMs"
    echo ""
    echo "  Supported formats: .vmdk .ova .ovf .vhd .vhdx .raw .img .qcow2"
    echo ""
    if ls "${DEMO_DIR}"/*.vmdk &>/dev/null; then
        echo "  Available VMDKs in ${DEMO_DIR}/:"
        ls "${DEMO_DIR}"/*.vmdk 2>/dev/null | while read -r f; do
            printf "    %-30s %s\n" "$(basename "$f")" "$(du -h "$f" | awk '{print $1}')"
        done
        echo ""
    fi
    exit 1
}

# ── Timer helpers ──
timer_start() { TIMER_START=$(date +%s); }
timer_elapsed() {
    local now elapsed mins secs
    now=$(date +%s)
    elapsed=$((now - TIMER_START))
    mins=$((elapsed / 60))
    secs=$((elapsed % 60))
    if [ "$mins" -gt 0 ]; then
        echo "${mins}m ${secs}s"
    else
        echo "${secs}s"
    fi
}

# ── Disk space check ──
check_disk_space() {
    local src_size_kb free_kb needed_kb
    src_size_kb=$(du -k "$1" | awk '{print $1}')
    free_kb=$(df -k /var/lib 2>/dev/null | awk 'NR==2{print $4}')
    # Need ~3.5x source size (input copy + flatten + convert + output)
    needed_kb=$((src_size_kb * 7 / 2))
    if [ "$free_kb" -lt "$needed_kb" ]; then
        local free_h needed_h
        free_h=$(awk "BEGIN{printf \"%.1fG\", $free_kb/1048576}")
        needed_h=$(awk "BEGIN{printf \"%.1fG\", $needed_kb/1048576}")
        warn "Low disk space: ${free_h} free, estimated ${needed_h} needed"
        warn "Run: $0 --cleanup  to free space"
        return 1
    fi
    return 0
}

# ── List migrated VMs ──
show_list() {
    local host_ip
    host_ip=$(hostname -I 2>/dev/null | awk '{print $1}')

    echo ""
    echo "  📋 Migrated VMs"
    echo "  ════════════════════════════════════════"
    echo ""
    printf "  %-20s %-12s %-18s %s\n" "VM Name" "State" "IP Address" "Disk"
    printf "  %-20s %-12s %-18s %s\n" "───────" "─────" "──────────" "────"

    local count=0
    for dir in "${OUTPUT_BASE}"/*/; do
        [ -d "$dir" ] || continue
        local name state ip disk_size
        name="$(basename "$dir")"
        state=$(virsh domstate "$name" 2>/dev/null || echo "undefined")
        ip=""
        if [ "$state" = "running" ]; then
            ip=$(virsh domifaddr "$name" --source lease 2>/dev/null \
                | awk '/ipv4/{print $4}' | cut -d/ -f1 | head -1)
        fi
        disk_size=$(du -h "${dir}/${name}.qcow2" 2>/dev/null | awk '{print $1}')
        printf "  %-20s %-12s %-18s %s\n" "$name" "[$state]" "${ip:---}" "${disk_size:---}"
        count=$((count + 1))
    done

    if [ "$count" -eq 0 ]; then
        echo "  (no migrated VMs found)"
    fi

    echo ""
    if systemctl is-active cockpit.socket &>/dev/null; then
        echo "  🌐 Cockpit: https://${host_ip}:9090 → Virtual Machines"
    fi
    echo ""
}

# ── Status ──
show_status() {
    local host_ip
    host_ip=$(hostname -I 2>/dev/null | awk '{print $1}')

    echo ""
    echo "  📋 hyper2kvm Demo — Libvirt VM Status"
    echo "  ════════════════════════════════════════"
    echo ""

    virsh list --all 2>/dev/null || true

    echo ""
    if systemctl is-active cockpit.socket &>/dev/null; then
        echo "  🌐 Cockpit: https://${host_ip}:9090 → Virtual Machines"
    fi
    echo ""
}

# ── Cleanup ──
do_cleanup_one() {
    local vm_name="$1"
    step "Cleaning up: $vm_name"
    virsh destroy "$vm_name" 2>/dev/null || true
    virsh undefine "$vm_name" --nvram 2>/dev/null || true
    virsh undefine "$vm_name" 2>/dev/null || true
    rm -rf "${OUTPUT_BASE}/${vm_name}"
    rm -f /var/lib/hyper2kvm/input/${vm_name}.*
    info "Removed: $vm_name"
}

do_cleanup() {
    local vm_name="${1:-}"
    if [ -z "$vm_name" ]; then
        step "Cleaning up all migrated VMs..."
        local found=0
        for dir in "${OUTPUT_BASE}"/*/; do
            [ -d "$dir" ] || continue
            local name
            name="$(basename "$dir")"
            do_cleanup_one "$name"
            found=$((found + 1))
        done
        [ "$found" -eq 0 ] && info "No VMs to clean up"
        info "All done ($found VMs removed)"
    else
        do_cleanup_one "$vm_name"
    fi
}

# ── Detect guest credentials ──
detect_guest_creds() {
    local name_lower
    name_lower="$(echo "$BASENAME $VM_NAME" | tr '[:upper:]' '[:lower:]')"

    case "$name_lower" in
        *cirros*)
            GUEST_USER="cirros"; GUEST_PASS="gocubsgo"; GUEST_ROOT_PASS="" ;;
        *photon*)
            GUEST_USER="root"; GUEST_PASS="changeme"; GUEST_ROOT_PASS="changeme" ;;
        *windows*|*win10*|*win11*)
            GUEST_USER="IEUser"; GUEST_PASS="Passw0rd!"; GUEST_ROOT_PASS="" ;;
        *centos*|*ubuntu*|*debian*|*fedora*|*kali*|*mint*|*opensuse*|*suse*|*arch*|*manjaro*|*pop*|*zorin*|*elementary*|*mx*|*sparky*|*lmde*|*kubuntu*|*xubuntu*|*lubuntu*|*kde*neon*|*peppermint*|*bodhi*|*q4os*|*linux*lite*|*deepin*|*solus*|*parrot*|*backbox*|*dietpi*|*devuan*|*bunsenlabs*|*calculate*|*mageia*|*pclinuxos*|*nitrux*|*feren*|*makulu*|*rocky*|*alma*|*rhel*|*osboxes*)
            GUEST_USER="osboxes"; GUEST_PASS="osboxes.org"; GUEST_ROOT_PASS="osboxes.org" ;;
        *)
            GUEST_USER="root"; GUEST_PASS="(check image source)"; GUEST_ROOT_PASS="" ;;
    esac
}

# ── noVNC setup ──
setup_novnc() {
    local vm_name="$1" host_ip="$2"
    NOVNC_URL=""

    local vnc_display vnc_port novnc_port
    vnc_display=$(virsh vncdisplay "$vm_name" 2>/dev/null | sed 's/.*://' || echo "")
    [ -z "$vnc_display" ] && return
    [[ "$vnc_display" =~ ^[0-9]+$ ]] || return

    vnc_port=$((5900 + vnc_display))
    novnc_port=$((6080 + vnc_display))

    # Check if websockify + novnc are available
    command -v websockify &>/dev/null || return
    [ -d /usr/share/novnc ] || return

    # Kill previous instance on this port
    local pid_file="/run/novnc-${novnc_port}.pid"
    if [ -f "$pid_file" ]; then
        kill "$(cat "$pid_file" 2>/dev/null)" 2>/dev/null || true
        rm -f "$pid_file"
        sleep 1
    fi

    # Start websockify
    websockify --web /usr/share/novnc/ --daemon "${novnc_port}" "127.0.0.1:${vnc_port}" 2>/dev/null || return
    sleep 1

    if ss -tlnp 2>/dev/null | grep -q ":${novnc_port}"; then
        local pid
        pid=$(ss -tlnp 2>/dev/null | grep ":${novnc_port}" | grep -oP 'pid=\K[0-9]+' | head -1)
        [ -n "$pid" ] && echo "$pid" > "$pid_file"
        # Open firewall
        if command -v firewall-cmd &>/dev/null; then
            firewall-cmd --add-port="${novnc_port}/tcp" &>/dev/null || true
        fi
        NOVNC_URL="http://${host_ip}:${novnc_port}/vnc.html"
    fi
}

# ── Migrate one VM ──
migrate_one() {
    local src="$1"
    local vm_name="$2"

    local basename ext_lower cmd input_key
    basename="$(basename "$src")"
    BASENAME="$basename"
    VM_NAME="$vm_name"
    ext_lower="$(echo "${basename##*.}" | tr '[:upper:]' '[:lower:]')"

    case "$ext_lower" in
        vmdk)       cmd="local"; input_key="vmdk" ;;
        ova)        cmd="ova";   input_key="ova"  ;;
        ovf)        cmd="ovf";   input_key="ovf"  ;;
        vhd|vhdx)   cmd="vhd";   input_key="vhd"  ;;
        raw|img)    cmd="raw";   input_key="raw"  ;;
        qcow2)     cmd="local";  input_key="vmdk" ;;
        *) die "Unsupported format: .$ext_lower" ;;
    esac

    local output_dir="${OUTPUT_BASE}/${vm_name}"
    local logfile="${LOGDIR}/${vm_name}.log"
    mkdir -p "$LOGDIR"

    # ── Disk space check ──
    if ! check_disk_space "$src"; then
        if $OPT_DRY_RUN; then
            warn "Would fail: insufficient disk space"
        else
            die "Not enough disk space. Run: $0 --cleanup"
        fi
    fi

    # ── Dry run ──
    if $OPT_DRY_RUN; then
        echo ""
        echo "  ════════════════════════════════════════"
        echo "  🧪 Dry Run: $vm_name"
        echo "  ════════════════════════════════════════"
        echo ""
        echo "  📥 Source:  $src ($(du -h "$src" | awk '{print $1}'))"
        echo "  📦 Format:  $ext_lower (cmd=$cmd)"
        echo "  🏷️  VM name: $vm_name"
        echo "  📂 Output:  $output_dir"
        echo "  🧠 Memory:  ${OPT_MEMORY} MB"
        echo "  💻 vCPUs:   ${OPT_VCPUS}"
        echo "  🔧 Fixes:   $($OPT_NO_FIXES && echo "skipped" || echo "fstab + initramfs + network + vmware-tools")"
        echo "  📝 Log:     $logfile"
        echo ""
        detect_guest_creds
        echo "  🔐 Login: $GUEST_USER / $GUEST_PASS"
        [ -n "$GUEST_ROOT_PASS" ] && echo "  🔐 Root:  root / $GUEST_ROOT_PASS"
        echo ""
        return 0
    fi

    timer_start
    banner

    # ── Pre-flight ──
    step "Pre-flight checks"
    for tool in h2kvmctl qemu-img virsh; do
        command -v "$tool" &>/dev/null || die "$tool not found"
    done
    [ -e /dev/kvm ] || warn "/dev/kvm not available — VMs will use emulation (slow)"
    if ! lsmod | grep -q "^nbd "; then
        modprobe nbd max_part=16 2>/dev/null || warn "Cannot load nbd module"
    fi
    virsh net-start default 2>/dev/null || true
    info "Pre-flight passed"

    # ── Copy source ──
    local workdir="/var/lib/hyper2kvm/input"
    mkdir -p "$workdir"
    local safe_src="$workdir/${vm_name}.${ext_lower}"
    if [ ! -f "$safe_src" ] || [ "$src" -nt "$safe_src" ]; then
        step "Copying source to working directory..."
        cp -f "$src" "$safe_src"
    fi

    # ── Teardown previous ──
    echo ""
    step "Cleanup previous: $vm_name"
    virsh destroy "$vm_name" 2>/dev/null || true
    virsh undefine "$vm_name" --nvram 2>/dev/null || true
    virsh undefine "$vm_name" 2>/dev/null || true
    rm -rf "$output_dir"
    mkdir -p "$output_dir"
    info "Clean slate"

    # ── Migrate ──
    echo ""
    echo "  ════════════════════════════════════════"
    echo "  🚀 Migrating: $vm_name"
    echo "  ════════════════════════════════════════"
    echo ""
    echo "  📥 Source:  $src ($(du -h "$src" | awk '{print $1}'))"
    echo "  📦 Format:  $ext_lower (cmd=$cmd)"
    echo "  🏷️  VM name: $vm_name"
    echo "  📂 Output:  $output_dir"
    echo "  🧠 Memory:  ${OPT_MEMORY} MB  💻 vCPUs: ${OPT_VCPUS}"
    echo "  📝 Log:     $logfile"
    echo ""

    # YAML config
    local config="${output_dir}/${vm_name}.yaml"
    local regen_initramfs="true"
    local fstab_mode="stabilize-all"
    local remove_vmware="true"
    if $OPT_NO_FIXES; then
        regen_initramfs="false"
        fstab_mode="noop"
        remove_vmware="false"
    fi

    # Write user config for demo user
    local user_config_file="${output_dir}/demo-user.yaml"
    cat > "$user_config_file" << UCEOF
users:
  - name: test
    password: test
    groups:
      - wheel
      - sudo
    sudo: "NOPASSWD:ALL"
    shell: /bin/bash
UCEOF

    cat > "$config" << YAMLEOF
cmd: ${cmd}
${input_key}: ${safe_src}
output_dir: ${output_dir}
to_output: ${vm_name}.qcow2
out_format: qcow2
flatten: true
compress: true

fstab_mode: ${fstab_mode}
regen_initramfs: ${regen_initramfs}
remove_vmware_tools: ${remove_vmware}

emit_domain_xml: true
virsh_define: true
vm_name: ${vm_name}
memory: ${OPT_MEMORY}
vcpus: ${OPT_VCPUS}
uefi: false
machine: q35
disk_bus: virtio
disk_cache: writeback
net_model: virtio
libvirt_network: default
serial_console: true
graphics: vnc
guest_os: linux

keep_domain: true
timeout: 300

user_config_inject: ${user_config_file}

verbose: 1
YAMLEOF

    # Run h2kvmctl — full output to log, progress to screen
    step "Running h2kvmctl (log: $logfile)..."
    /usr/local/bin/h2kvmctl --config "$config" --allowed-dir "$output_dir" --allowed-dir "$workdir" 2>&1 \
        | tee "$logfile" \
        | grep -E "^[0-9]{2}:[0-9]{2}:[0-9]{2} ✅|^[0-9]{2}:[0-9]{2}:[0-9]{2} 💥|^[0-9]{2}:[0-9]{2}:[0-9]{2} ⚠️|Flatten|Convert|Offline|network|initramfs|Domain|progress" \
        || true

    # ── Start VM ──
    step "Starting VM: $vm_name"
    virsh start "$vm_name" 2>/dev/null || true
    info "State: $(virsh domstate "$vm_name" 2>/dev/null || echo 'unknown')"

    # ── Wait for IP ──
    echo ""
    step "Waiting for IP (up to 2 minutes)..."
    local vm_ip=""
    for i in $(seq 1 12); do
        sleep 10
        vm_ip=$(virsh domifaddr "$vm_name" --source lease 2>/dev/null \
            | awk '/ipv4/{print $4}' | cut -d/ -f1 | head -1)
        [ -n "$vm_ip" ] && break
        echo "    ⏳ attempt $i/12 — no IP yet..."
    done
    if [ -z "$vm_ip" ]; then
        vm_ip=$(virsh domifaddr "$vm_name" --source arp 2>/dev/null \
            | awk '/ipv4/{print $4}' | cut -d/ -f1 | head -1)
    fi

    # ── Credentials ──
    detect_guest_creds

    # ── noVNC ──
    local host_ip
    host_ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    setup_novnc "$vm_name" "$host_ip"

    # ── Summary ──
    local elapsed
    elapsed=$(timer_elapsed)

    echo ""
    echo "  ════════════════════════════════════════"
    echo "  🎉 Migration Complete (${elapsed})"
    echo "  ════════════════════════════════════════"
    echo ""
    printf "  🏷️  VM name : %s\n" "$vm_name"
    printf "  ⚡ State   : %s\n" "$(virsh domstate "$vm_name" 2>/dev/null || echo 'unknown')"
    [ -n "$vm_ip" ] && printf "  🌐 IP addr : %s\n" "$vm_ip"
    printf "  🧠 Memory  : %s MB  💻 vCPUs: %s\n" "$OPT_MEMORY" "$OPT_VCPUS"
    printf "  📥 Source  : %s\n" "$ext_lower"
    printf "  💾 Output  : %s\n" "$output_dir/${vm_name}.qcow2"
    printf "  ⏱️  Time    : %s\n" "$elapsed"
    printf "  📝 Log     : %s\n" "$logfile"
    echo ""
    echo "  🔐 Login: $GUEST_USER / $GUEST_PASS"
    [ -n "$GUEST_ROOT_PASS" ] && echo "  🔐 Root:  root / $GUEST_ROOT_PASS"
    echo "  🔐 Demo:  test / test  (sudo, created by demo script)"
    echo ""
    echo "  Access:"
    echo "    🖥️  virsh console $vm_name"
    if [ -n "$vm_ip" ]; then
        echo "    🔑 ssh $GUEST_USER@$vm_ip  (password: $GUEST_PASS)"
        [ -n "$GUEST_ROOT_PASS" ] && echo "    🔑 ssh root@$vm_ip  (password: $GUEST_ROOT_PASS)"
    fi
    echo "    📺 virsh vncdisplay $vm_name"
    [ -n "$NOVNC_URL" ] && echo "    🌐 noVNC: $NOVNC_URL"
    echo ""
    if systemctl is-active cockpit.socket &>/dev/null; then
        echo "  🌐 Cockpit: https://${host_ip}:9090/machines#/vm/${vm_name}"
        echo ""
    fi
    echo "  🗑️  Cleanup: sudo $0 --cleanup $vm_name"
    echo ""

    # Auto SSH login with demo user test/test
    if [ -n "$vm_ip" ] && command -v sshpass &>/dev/null; then
        echo ""
        read -p "  🔑 Connect via SSH as test@$vm_ip? [Y/n] " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            SSHPASS="test" sshpass -e ssh -o StrictHostKeyChecking=no "test@$vm_ip"
        fi
    fi
}

# ── Migrate all VMDKs ──
migrate_all() {
    local vmdk_files=()
    for f in ${DEMO_DIR}/*.vmdk; do
        [ -f "$f" ] && vmdk_files+=("$f")
    done

    if [ ${#vmdk_files[@]} -eq 0 ]; then
        die "No VMDKs found in ${DEMO_DIR}/"
    fi

    echo ""
    echo "  ════════════════════════════════════════"
    echo "  🚀 Batch Migration: ${#vmdk_files[@]} VMDKs"
    echo "  ════════════════════════════════════════"
    echo ""
    for f in "${vmdk_files[@]}"; do
        local name
        name="$(basename "$f" .vmdk)"
        printf "    %-25s %s\n" "$name" "$(du -h "$f" | awk '{print $1}')"
    done
    echo ""

    local succeeded=0 failed=0 skipped=0
    timer_start

    for f in "${vmdk_files[@]}"; do
        local name
        name="$(basename "$f" .vmdk)"
        # Sanitise
        name="$(echo "$name" | tr -c 'A-Za-z0-9._-' '-' | sed 's/^-//;s/-$//')"

        echo ""
        echo "  ────────────────────────────────────────"
        echo "  📦 [$((succeeded + failed + skipped + 1))/${#vmdk_files[@]}] $name"
        echo "  ────────────────────────────────────────"

        if $OPT_DRY_RUN; then
            SRC="$f"
            BASENAME="$(basename "$f")"
            VM_NAME="$name"
            migrate_one "$f" "$name"
            skipped=$((skipped + 1))
            continue
        fi

        if migrate_one "$f" "$name" </dev/null; then
            succeeded=$((succeeded + 1))
        else
            failed=$((failed + 1))
            warn "Failed: $name (continuing...)"
        fi
    done

    local total_elapsed
    total_elapsed=$(timer_elapsed)

    echo ""
    echo "  ════════════════════════════════════════"
    echo "  📊 Batch Summary (${total_elapsed})"
    echo "  ════════════════════════════════════════"
    echo ""
    echo "  ╔══════════════════════════════════════════════════╗"
    echo "  ║     Batch Migration Complete                     ║"
    echo "  ╚══════════════════════════════════════════════════╝"
    echo ""
    echo "  Total:     ${#vmdk_files[@]}"
    echo "  Succeeded: $succeeded"
    [ "$failed" -gt 0 ] && echo "  Failed:    $failed"
    [ "$skipped" -gt 0 ] && echo "  Skipped:   $skipped (dry run)"
    echo "  Time:      $total_elapsed"
    echo ""
    show_list
}

# ── Find source file ──
find_source() {
    local src="$1"
    if [[ -f "$src" ]]; then
        echo "$src"
        return
    fi
    for search_dir in ${DEMO_DIR} ${DEMO_DIR}/archives /var/lib/hyper2kvm/input; do
        if [[ -f "$search_dir/$src" ]]; then
            echo "$search_dir/$src"
            return
        fi
    done
    echo ""
}

# ── Main ──

# Ensure /usr/local/bin is in PATH (sudo may strip it)
export PATH="/usr/local/bin:/usr/local/sbin:$PATH"

# ── Banner ──
banner() {
    echo ""
    echo "  ╔══════════════════════════════════════════════════╗"
    echo "  ║                                                  ║"
    echo "  ║     hyper2kvm — VM Migration Demo                ║"
    echo "  ║     VMware VMDK → KVM/Libvirt in one command     ║"
    echo "  ║                                                  ║"
    echo "  ╚══════════════════════════════════════════════════╝"
    echo ""
}

# No args
[[ $# -ge 1 ]] || { banner; usage; }

# Parse args
SRC=""
VM_NAME_ARG=""
POSITIONAL=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)      usage ;;
        --status)       show_status; exit 0 ;;
        --list)         show_list; exit 0 ;;
        --cleanup)      do_cleanup "${2:-}"; exit 0 ;;
        --all)          shift; migrate_all; exit 0 ;;
        --memory)       OPT_MEMORY="$2"; shift 2 ;;
        --vcpus)        OPT_VCPUS="$2"; shift 2 ;;
        --no-fixes)     OPT_NO_FIXES=true; shift ;;
        --dry-run)      OPT_DRY_RUN=true; shift ;;
        -*)             die "Unknown option: $1" ;;
        *)              POSITIONAL+=("$1"); shift ;;
    esac
done

# Need at least a source file
[ ${#POSITIONAL[@]} -eq 0 ] && usage

SRC_INPUT="${POSITIONAL[0]}"
VM_NAME_ARG="${POSITIONAL[1]:-}"

# Find source
SRC=$(find_source "$SRC_INPUT")
[[ -n "$SRC" ]] || die "File not found: $SRC_INPUT"

if [ "$(id -u)" -ne 0 ]; then
    die "Run as root: sudo $0 $*"
fi

# Derive VM name
BASENAME="$(basename "$SRC")"
VM_NAME="${VM_NAME_ARG:-${BASENAME%.*}}"
VM_NAME="$(echo "$VM_NAME" | tr -c 'A-Za-z0-9._-' '-' | sed 's/^-//;s/-$//')"
[[ -n "$VM_NAME" ]] || VM_NAME="converted-vm"

migrate_one "$SRC" "$VM_NAME"
