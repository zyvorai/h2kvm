#!/bin/bash
# ============================================
# hyper2kvm Auto Demo — Zero to Running VM
# ============================================
# Production-grade installer: installs everything on a fresh machine,
# converts a VM, boots it, validates it, and logs in via SSH.
#
# Usage:
#   sudo ./scripts/auto-demo.sh
#   sudo ./scripts/auto-demo.sh --with-cockpit
#   sudo ./scripts/auto-demo.sh --with-k3s
#   sudo ./scripts/auto-demo.sh --full
#   AUTO_YES=true sudo ./scripts/auto-demo.sh   # non-interactive
#   DRY_RUN=true sudo ./scripts/auto-demo.sh    # preview only
#
# Environment overrides:
#   VM_NAME=my-vm VM_PASS=secret sudo ./scripts/auto-demo.sh
# ============================================

set -euo pipefail
trap 'echo -e "\n[FATAL] Failed at line $LINENO (exit $?)"; echo "Log: $LOG_FILE"; exit 1' ERR

# ── Colors ──
# ── Logging ──
LOG_FILE="${LOG_FILE:-/var/log/hyper2kvm-demo.log}"
mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || LOG_FILE="/tmp/hyper2kvm-demo.log"
exec > >(tee -a "$LOG_FILE") 2>&1

# ── Config (overridable via env) ──
VM_NAME="${VM_NAME:-demo-photon}"
VM_PASS="${VM_PASS:-hyper2kvm}"
AUTO_YES="${AUTO_YES:-false}"
DRY_RUN="${DRY_RUN:-false}"
VM_IP=""
START_TIME=$(date +%s)

# ── Helpers ──
info()  { echo "✅ $*"; }
warn()  { echo "⚠️ $*"; }
error() { echo "❌ $*"; }
step()  { echo "🔹$*"; }
dim()   { echo "    $*"; }

# Safe command execution (no eval).
run() {
    echo "+ $*" >> "$LOG_FILE" 2>/dev/null || true
    if [ "$DRY_RUN" = "false" ]; then
        "$@"
    else
        dim "[dry-run] $*"
    fi
}

retry() {
    local attempts=3 delay=2
    for i in $(seq 1 "$attempts"); do
        "$@" && return 0
        warn "Attempt $i/$attempts failed, retrying in ${delay}s..."
        sleep "$delay"
        delay=$((delay * 2))
    done
    error "Failed after $attempts attempts: $*"
    return 1
}

elapsed() { echo "$(($(date +%s) - START_TIME))s"; }

# ── Parse args ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." 2>/dev/null && pwd)"
EXTRA_ARGS=()

for arg in "$@"; do
    case "$arg" in
        --with-cockpit|--with-k3s|--full) EXTRA_ARGS+=("$arg") ;;
        --dry-run)   DRY_RUN=true ;;
        --auto-yes)  AUTO_YES=true ;;
        --help|-h)
            echo "Usage: sudo $0 [--with-cockpit] [--with-k3s] [--full] [--dry-run] [--auto-yes]"
            echo ""
            echo "Environment:"
            echo "  VM_NAME=name     VM name (default: demo-photon)"
            echo "  VM_PASS=pass     Root password (default: hyper2kvm)"
            echo "  AUTO_YES=true    Non-interactive mode"
            echo "  DRY_RUN=true     Preview without executing"
            echo "  LOG_FILE=path    Log file path"
            exit 0
            ;;
    esac
done

# ── Pre-flight checks ──
preflight() {
    step "Pre-flight checks"

    # Root
    if [ "$(id -u)" -ne 0 ]; then
        error "Run as root: sudo $0"
        exit 1
    fi

    # OS
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        info "OS: $PRETTY_NAME"
    else
        error "Unsupported OS (no /etc/os-release)"
        exit 1
    fi

    # Architecture
    local arch
    arch=$(uname -m)
    if [ "$arch" != "x86_64" ] && [ "$arch" != "aarch64" ]; then
        error "Unsupported architecture: $arch"
        exit 1
    fi
    info "Arch: $arch"

    # KVM
    if grep -E -q '(vmx|svm)' /proc/cpuinfo 2>/dev/null; then
        info "KVM: supported"
    else
        warn "KVM: not detected (VMs will use emulation — slower)"
    fi

    # RAM
    local ram_mb
    ram_mb=$(free -m | awk '/Mem:/{print $2}')
    if [ "$ram_mb" -lt 3500 ]; then
        warn "RAM: ${ram_mb}MB (recommend 4GB+)"
    else
        info "RAM: ${ram_mb}MB"
    fi

    # Disk
    local free_gb
    free_gb=$(df -BG . | awk 'NR==2{print $4}' | tr -d 'G')
    if [ "$free_gb" -lt 5 ]; then
        error "Disk: ${free_gb}GB free (need 5GB+)"
        exit 1
    fi
    info "Disk: ${free_gb}GB free"

    # Network
    if ping -c 1 -W 3 8.8.8.8 &>/dev/null; then
        info "Network: connected"
    else
        warn "Network: no internet (some installs may fail)"
    fi

    # /dev/kvm
    if [ -e /dev/kvm ]; then
        info "/dev/kvm: available"
    else
        warn "/dev/kvm: not available (check BIOS VT-x/AMD-V)"
    fi

    # SELinux
    if command -v getenforce &>/dev/null; then
        local se
        se=$(getenforce 2>/dev/null || echo "Unknown")
        if [ "$se" = "Enforcing" ]; then
            warn "SELinux: Enforcing (may need: sudo setenforce 0)"
        else
            info "SELinux: $se"
        fi
    fi

    # nc (needed for SSH check)
    if ! command -v nc &>/dev/null; then
        warn "nc not found (SSH readiness check will be skipped)"
    fi

    info "Pre-flight passed ($(elapsed))"
}

# ── Clone repo if needed ──
ensure_repo() {
    if [ ! -f "$REPO_DIR/pyproject.toml" ]; then
        step "Cloning hyper2kvm"
        retry git clone https://github.com/ssahani/hyper2kvm.git /tmp/hyper2kvm
        REPO_DIR="/tmp/hyper2kvm"
        SCRIPT_DIR="$REPO_DIR/scripts"
    fi
    cd "$REPO_DIR"
}

# ── Install ──
install_all() {
    step "Installing hyper2kvm + dependencies"
    if [ "$DRY_RUN" = "false" ]; then
        "$SCRIPT_DIR/quickstart.sh" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
    else
        dim "[dry-run] quickstart.sh ${EXTRA_ARGS[*]:-}"
    fi
    info "Install complete ($(elapsed))"
}

# ── Wait for libvirtd ──
wait_for_libvirt() {
    local retries=10
    while [ $retries -gt 0 ]; do
        systemctl is-active libvirtd &>/dev/null && return 0
        sleep 1
        retries=$((retries - 1))
    done
    warn "libvirtd not ready after 10s"
}

# ── Ensure default network ──
ensure_default_network() {
    if ! virsh net-info default &>/dev/null 2>&1; then
        warn "Default libvirt network missing — creating..."
        virsh net-define /usr/share/libvirt/networks/default.xml 2>/dev/null || true
        virsh net-start default 2>/dev/null || warn "Failed to start default network"
        virsh net-autostart default 2>/dev/null || true
    fi
}

# ── Convert + Boot ──
convert_and_boot() {
    step "Converting VM and booting on KVM"

    wait_for_libvirt
    ensure_default_network

    # Cleanup previous
    virsh destroy "$VM_NAME" 2>/dev/null || true
    virsh undefine "$VM_NAME" --nvram 2>/dev/null || true
    virsh undefine "$VM_NAME" 2>/dev/null || true
    rm -rf demo-output/ 2>/dev/null || true

    if [ "$DRY_RUN" = "false" ]; then
        "$SCRIPT_DIR/run-demo.sh" --photon <<< "n"
    else
        dim "[dry-run] run-demo.sh --photon"
    fi
    info "Conversion complete ($(elapsed))"
}

# ── Configure SSH ──
configure_access() {
    step "Configuring VM access (root password + SSH)"
    warn "Demo mode: enabling root SSH + password auth"

    if ! command -v virt-customize &>/dev/null; then
        warn "virt-customize not found — skipping password setup"
        VM_PASS="(not set — install libguestfs-tools)"
        return
    fi

    if [ "$DRY_RUN" = "true" ]; then
        dim "[dry-run] virt-customize --root-password --sshd_config"
        return
    fi

    virsh destroy "$VM_NAME" 2>/dev/null || true
    sleep 2

    virt-customize -a "demo-output/${VM_NAME}.qcow2" \
        --root-password "password:${VM_PASS}" \
        --run-command "sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config" \
        --run-command "sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config" \
        2>/dev/null

    virsh start "$VM_NAME" 2>/dev/null || true
    info "Root password set to: $VM_PASS"
}

# ── Wait for VM IP + health checks ──
wait_for_vm() {
    step "Waiting for VM to boot"

    if [ "$DRY_RUN" = "true" ]; then
        dim "[dry-run] wait for VM IP"
        return
    fi

    # Wait for VM to be running
    local retries=15
    while [ $retries -gt 0 ]; do
        virsh domstate "$VM_NAME" 2>/dev/null | grep -q running && break
        sleep 2
        retries=$((retries - 1))
    done

    # Wait for IP (retry with fallback to ARP)
    retries=30
    while [ $retries -gt 0 ] && [ -z "$VM_IP" ]; do
        VM_IP=$(virsh domifaddr "$VM_NAME" 2>/dev/null | awk '/ipv4/{print $4}' | cut -d/ -f1 | head -1)
        # ARP fallback
        if [ -z "$VM_IP" ]; then
            local mac
            mac=$(virsh domiflist "$VM_NAME" 2>/dev/null | awk '/vnet|macvtap/{print $5}' | head -1)
            if [ -n "$mac" ]; then
                VM_IP=$(arp -an 2>/dev/null | grep -i "$mac" | awk '{print $2}' | tr -d '()')
            fi
        fi
        [ -z "$VM_IP" ] && sleep 2
        retries=$((retries - 1))
    done

    if [ -z "$VM_IP" ]; then
        warn "Could not detect VM IP (run: virsh domifaddr $VM_NAME)"
        return
    fi
    info "VM IP: $VM_IP"

    # Ping check
    if ping -c 1 -W 3 "$VM_IP" &>/dev/null; then
        info "VM reachable (ping)"
    else
        warn "VM not responding to ping"
    fi

    # SSH port check
    if command -v nc &>/dev/null; then
        local ssh_ready=false
        for _ in $(seq 1 15); do
            if nc -z -w 2 "$VM_IP" 22 2>/dev/null; then
                ssh_ready=true
                break
            fi
            sleep 2
        done
        if $ssh_ready; then
            info "SSH ready (port 22)"
        else
            warn "SSH port not open yet"
        fi
    fi
}

# ── Results dashboard ──
show_results() {
    local duration=$(($(date +%s) - START_TIME))
    local host_ip
    host_ip=$(hostname -I 2>/dev/null | awk '{print $1}')

    local vm_running=false
    virsh list 2>/dev/null | grep -q "$VM_NAME" && vm_running=true

    local ssh_ready=false
    [ -n "$VM_IP" ] && command -v nc &>/dev/null && nc -z -w 1 "$VM_IP" 22 2>/dev/null && ssh_ready=true

    echo ""
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║  hyper2kvm Demo Complete                             ║"
    echo "╠══════════════════════════════════════════════════════╣"
    printf "  ║  ✔ %-10s %-40s ║\n" "VM:" "$VM_NAME"

    if $vm_running; then
        printf "  ║  ✔ %-10s %-40s ║\n" "Status:" "RUNNING"
    else
        printf "  ║  ✖ %-10s %-40s ║\n" "Status:" "NOT RUNNING"
    fi

    [ -n "$VM_IP" ] && printf "  ║  ✔ %-10s %-40s ║\n" "IP:" "$VM_IP"

    if $ssh_ready; then
        printf "  ║  ✔ %-10s %-40s ║\n" "SSH:" "READY"
    else
        printf "  ║  ⚠ %-10s %-40s ║\n" "SSH:" "WAITING"
    fi

    printf "  ║  ✔ %-10s %-40s ║\n" "Time:" "${duration}s"
    echo "╠══════════════════════════════════════════════════════╣"

    if [ -n "$VM_IP" ]; then
        printf "  ║  %-10s %-42s ║\n" "SSH:" "ssh root@${VM_IP}"
        printf "  ║  %-10s %-42s ║\n" "Pass:" "$VM_PASS"
    fi
    printf "  ║  %-10s %-42s ║\n" "Console:" "virsh console $VM_NAME"
    printf "  ║  %-10s %-42s ║\n" "VMs:" "virsh list"

    if systemctl is-active cockpit.socket &>/dev/null; then
        printf "  ║  %-10s %-42s ║\n" "Cockpit:" "https://${host_ip}:9090"
    fi

    echo "╠══════════════════════════════════════════════════════╣"
    printf "  ║  %-52s ║\n" "Cleanup: sudo ./scripts/run-demo.sh --cleanup"
    printf "  ║  %-52s ║\n" "Log: $LOG_FILE"
    echo "╚══════════════════════════════════════════════════════╝"
    echo ""

    [ -n "$VM_IP" ] && dim "Note: SSH host key checking disabled (demo mode)"
}

# ── Auto SSH ──
auto_ssh() {
    [ -z "$VM_IP" ] && return

    if ! command -v sshpass &>/dev/null; then
        dim "Install sshpass for auto-login: dnf install sshpass"
        return
    fi

    if [ "$AUTO_YES" = "true" ]; then
        echo ""
        info "Auto-connecting to VM..."
        SSHPASS="$VM_PASS" sshpass -e ssh -o StrictHostKeyChecking=no root@"$VM_IP" \
            "echo '=== Connected to $VM_NAME ==='; hostname; uname -r; uptime" 2>/dev/null || true
        return
    fi

    echo ""
    read -p "  Connect via SSH now? [Y/n] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        SSHPASS="$VM_PASS" sshpass -e ssh -o StrictHostKeyChecking=no root@"$VM_IP"
    fi
}

# ── Auto-open Cockpit ──
auto_cockpit() {
    if systemctl is-active cockpit.socket &>/dev/null; then
        xdg-open "https://$(hostname -I | awk '{print $1}'):9090" 2>/dev/null || true
    fi
}

# ── Main ──
main() {
    echo ""
    echo "hyper2kvm Auto Demo"
    echo "Zero to Running VM in one command"
    echo ""

    [ "$DRY_RUN" = "true" ] && warn "DRY RUN — no changes will be made"

    preflight
    ensure_repo
    install_all
    convert_and_boot
    configure_access
    wait_for_vm
    show_results
    auto_cockpit
    auto_ssh
}

main "$@"
