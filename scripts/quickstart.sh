#!/bin/bash
set -euo pipefail
# ============================================
# hyper2kvm Quickstart — Fresh Machine Setup
# ============================================
# Production-grade installer: one command installs everything
# on a fresh Fedora, RHEL, Ubuntu, Debian, or openSUSE machine.
#
# Usage:
#   sudo ./scripts/quickstart.sh
#   sudo ./scripts/quickstart.sh --with-cockpit
#   sudo ./scripts/quickstart.sh --with-h2kweb    # web dashboard on :5070
#   sudo ./scripts/quickstart.sh --with-k3s
#   sudo ./scripts/quickstart.sh --full
#   sudo ./scripts/quickstart.sh --minimal    # qemu + govc only
#   sudo ./scripts/quickstart.sh --verify     # check only
#   DRY_RUN=true sudo ./scripts/quickstart.sh # preview
#
# Environment:
#   VM_NAME, VM_PASS, DRY_RUN, LOG_FILE
#   HYPER2KVM_INSTALL_BUNDLE_ID, HYPER2KVM_GOVC_DOWNLOAD_PREFIX, HYPER2KVM_VIRTIO_WIN_ISO_URL
# ============================================

trap 'echo -e "\n[FATAL] quickstart failed at line $LINENO (exit $?)"; echo "Log: $LOG_FILE"; exit 1' ERR

# shellcheck source=install-versions.inc.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/install-versions.inc.sh"

# ── Config ──
DRY_RUN="${DRY_RUN:-false}"
LOG_FILE="${LOG_FILE:-/var/log/hyper2kvm-quickstart.log}"
START_TIME=$(date +%s)
APT_UPDATED=false

# ── Helpers ──
info()  { echo "✅ $*"; }
warn()  { echo "⚠️ $*"; }
error() { echo "❌ $*"; }
step()  { echo "🔹$*"; }
dim()   { echo "    $*"; }

elapsed() { echo "$(($(date +%s) - START_TIME))s"; }

# Safe execution — no eval.
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

# PEP 668: modern distros block bare pip install.
# Detect and add --break-system-packages when running as root installer.
PIP_EXTRA_ARGS=""
pip_setup() {
    if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
        local stdlib_path
        stdlib_path="$(python3 -c 'import sysconfig; print(sysconfig.get_path("stdlib"))' 2>/dev/null)"
        if [ -f "${stdlib_path}/../EXTERNALLY-MANAGED" ] 2>/dev/null; then
            PIP_EXTRA_ARGS="--break-system-packages"
        fi
    fi
}

pip_install() {
    pip3 install $PIP_EXTRA_ARGS --quiet "$@" 2>/dev/null || \
        pip3 install $PIP_EXTRA_ARGS --user --quiet "$@" 2>/dev/null
}

# Avoid repeated apt-get update.
apt_update_once() {
    if [ "$APT_UPDATED" = "false" ] && [ "$DRY_RUN" = "false" ]; then
        retry apt-get update -qq
        APT_UPDATED=true
    fi
}

# ── Logging ──
setup_logging() {
    mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || LOG_FILE="/tmp/hyper2kvm-quickstart.log"
    touch "$LOG_FILE" 2>/dev/null || LOG_FILE="/tmp/hyper2kvm-quickstart.log"
    # deploy-remote.sh sets HYPER2KVM_REMOTE_INSTALL=1: skip exec>(tee) — process substitution
    # over SSH can close the session ("Shared connection closed"). Output still streams to SSH.
    if [ "${HYPER2KVM_REMOTE_INSTALL:-}" = 1 ]; then
        return 0
    fi
    exec 3>&1
    exec > >(tee -a "$LOG_FILE" >&3) 2>&1
}

# ── Parse args ──
WITH_COCKPIT=false
WITH_K3S=false
WITH_H2KWEB=false
MINIMAL=false
VERIFY_ONLY=false

for arg in "$@"; do
    case "$arg" in
        --with-cockpit) WITH_COCKPIT=true ;;
        --with-k3s)     WITH_K3S=true ;;
        --with-h2kweb)  WITH_H2KWEB=true ;;
        --full)         WITH_COCKPIT=true; WITH_K3S=true; WITH_H2KWEB=true ;;
        --minimal)      MINIMAL=true ;;
        --verify)       VERIFY_ONLY=true ;;
        --dry-run)      DRY_RUN=true ;;
        --help|-h)
            echo "Usage: sudo $0 [--with-cockpit] [--with-h2kweb] [--with-k3s] [--full] [--minimal] [--verify] [--dry-run]"
            exit 0
            ;;
    esac
done

if [ "$(id -u)" -ne 0 ] && [ "$VERIFY_ONLY" = "false" ]; then
    error "Run as root: sudo $0 $*"
    exit 1
fi

# ── Detect distro ──
detect_distro() {
    if [ -f /etc/os-release ]; then
        # shellcheck source=/dev/null
        . /etc/os-release
        DISTRO="${ID:-unknown}"
        DISTRO_PRETTY="${PRETTY_NAME:-$DISTRO}"
        ID_LIKE="${ID_LIKE:-}"
    else
        error "Cannot detect distribution (/etc/os-release missing)"
        exit 1
    fi

    PKG=""
    case "$DISTRO" in
        fedora) PKG="dnf" ;;
        rhel|centos|almalinux|rocky|eurolinux|oraclelinux|miraclelinux|virtuozzo|opencloudos|anolis)
            PKG="dnf" ;;
        amzn)
            # Amazon Linux 2 (yum) vs 2023+ (dnf): pick by what is installed
            if command -v dnf &>/dev/null; then
                PKG="dnf"
            elif command -v yum &>/dev/null; then
                PKG="yum"
            fi
            ;;
        ubuntu|debian|linuxmint|pop|zorin|kali|raspbian|elementary)
            PKG="apt" ;;
        opensuse-tumbleweed|opensuse-leap|opensuse|sles|sle-micro|sle_hpc)
            PKG="zypper" ;;
        *)
            case " ${ID_LIKE} " in
                *" rhel "*|*" fedora "*|*" centos "*)
                    PKG="dnf" ;;
                *" debian "*|*" ubuntu "*)
                    PKG="apt" ;;
                *" suse "*|*" sles "*)
                    PKG="zypper" ;;
                *)
                    if command -v dnf &>/dev/null; then
                        PKG="dnf"
                    elif command -v yum &>/dev/null; then
                        PKG="yum"
                    elif command -v apt-get &>/dev/null; then
                        PKG="apt"
                    elif command -v zypper &>/dev/null; then
                        PKG="zypper"
                    else
                        error "Unsupported distro: $DISTRO (ID_LIKE=${ID_LIKE:-none})"
                        exit 1
                    fi
                    ;;
            esac
            ;;
    esac

    if [ -z "$PKG" ]; then
        error "Could not select package manager for: $DISTRO"
        exit 1
    fi

    return 0
}

# True if dnf/yum can install this RPM name from enabled repos (or it is already installed).
# Works across AlmaLinux 9, Rocky 9, CentOS Stream 9, RHEL 9 — dnf output/repo layouts differ slightly,
# so we try list + repoquery instead of assuming one `dnf list` spelling.
_rpm_family_pkg_available() {
    local name="$1"
    rpm -q "$name" &>/dev/null && return 0
    if command -v dnf &>/dev/null; then
        if dnf list --available "$name" 2>/dev/null | grep -q "^${name}\\."; then
            return 0
        fi
        if dnf list available "$name" 2>/dev/null | grep -q "^${name}\\."; then
            return 0
        fi
        # EL9 dnf has no --match-exact; use queryformat to match the RPM name.
        if dnf -q repoquery --available "$name" --qf '%{name}' 2>/dev/null | grep -qx "$name"; then
            return 0
        fi
        return 1
    fi
    if command -v yum &>/dev/null; then
        yum list available "$name" 2>/dev/null | grep -q "^${name}\\."
        return $?
    fi
    return 1
}

# True if apt can install this package (already installed or listed in apt indexes).
# Works on Ubuntu 22.04/24.04 LTS and Debian 11/12 — optional/universe packages may be absent on minimal images.
_apt_pkg_available() {
    local name="$1"
    dpkg -s "$name" &>/dev/null && return 0
    if command -v apt-cache &>/dev/null; then
        apt-cache show "$name" &>/dev/null && return 0
    fi
    return 1
}

# QEMU userland RPMs: RHEL/Alma/Rocky use qemu-kvm; Fedora also publishes qemu-system-x86-core.
_qemu_rpms_rpm_family() {
    local pkgs=(qemu-img qemu-kvm)
    if _rpm_family_pkg_available qemu-system-x86-core; then
        pkgs+=(qemu-system-x86-core)
    fi
    printf '%s\n' "${pkgs[@]}"
}

# ── Pre-flight ──
preflight() {
    step "Pre-flight checks"

    detect_distro
    info "OS: $DISTRO_PRETTY (id=${DISTRO}, pkg=${PKG}) — $(uname -m)"

    # KVM support
    if grep -E -q '(vmx|svm)' /proc/cpuinfo 2>/dev/null; then
        info "KVM: supported"
    else
        warn "KVM: not detected (VMs will use emulation)"
    fi

    # Nested virt
    if grep -q hypervisor /proc/cpuinfo 2>/dev/null; then
        warn "Running inside VM — nested virtualization may not work"
    fi

    # RAM
    local ram_mb
    ram_mb=$(free -m | awk '/Mem:/{print $2}')
    [ "$ram_mb" -lt 3500 ] && warn "RAM: ${ram_mb}MB (recommend 4GB+)" || info "RAM: ${ram_mb}MB"

    # Disk
    local free_gb
    free_gb=$(df -BG . | awk 'NR==2{print $4}' | tr -d 'G')
    [ "$free_gb" -lt 5 ] && { error "Disk: ${free_gb}GB free (need 5GB+)"; exit 1; }
    info "Disk: ${free_gb}GB free"

    # Network
    if ping -c 1 -W 3 8.8.8.8 &>/dev/null; then
        info "Network: connected"
    else
        warn "Network: no internet (installs may fail)"
    fi

    info "Pre-flight passed ($(elapsed))"
}

# ── Step 1: System packages ──
install_system_packages() {
    step "Step 1/7: Installing system packages"

    export DEBIAN_FRONTEND=noninteractive

    case "$PKG" in
        dnf)
            # EL9+: augeas-devel (and other -devel) packages are in CRB/PowerTools — enable before resolving RPM names.
            # Repo id is first column (e.g. "crb    AlmaLinux 9 - CRB"), not "crb/..."
            if ! dnf repolist --enabled 2>/dev/null | grep -qiE '^(crb|powertools)[[:space:]]'; then
                run dnf install -y "dnf-command(config-manager)" 2>/dev/null || true
                run dnf config-manager --set-enabled crb 2>/dev/null || run dnf config-manager --set-enabled powertools 2>/dev/null || true
                run dnf makecache -y 2>/dev/null || true
            fi
            local -a _qemu_rpms
            mapfile -t _qemu_rpms < <(_qemu_rpms_rpm_family)
            # Core set must exist on RHEL-family (AlmaLinux 9, Rocky 9, CentOS Stream 9, RHEL 9).
            # Optional RPM names vary by compose/repo — if absent, skip (venv/pip + install-deps cover gaps).
            local -a _dnf_pkgs=(
                python3 python3-pip
                "${_qemu_rpms[@]}"
                libvirt-daemon-kvm libvirt-client virt-install
                edk2-ovmf
                libguestfs libguestfs-tools python3-libguestfs supermin
                bsdtar
                openssh-clients sshpass rsync curl tar unzip
            )
            _rpm_family_pkg_available python3-virtualenv && _dnf_pkgs+=(python3-virtualenv)
            _rpm_family_pkg_available python3-hivex && _dnf_pkgs+=(python3-hivex)
            # Pip-installed h2kvmctl on EL often uses Python 3.12 — bindings are separate from python3-hivex.
            _rpm_family_pkg_available python3.12-hivex && _dnf_pkgs+=(python3.12-hivex)
            _rpm_family_pkg_available hivex && _dnf_pkgs+=(hivex)
            _rpm_family_pkg_available nbd && _dnf_pkgs+=(nbd)
            _rpm_family_pkg_available nbdkit && _dnf_pkgs+=(nbdkit)
            # hyper2kvm needs Python >= 3.10; EL 8/9 default python3 is often 3.9 — add 3.12 + pip + devel when listed.
            _rpm_family_pkg_available python3.12 && _dnf_pkgs+=(python3.12)
            _rpm_family_pkg_available python3.12-pip && _dnf_pkgs+=(python3.12-pip)
            _rpm_family_pkg_available python3.12-devel && _dnf_pkgs+=(python3.12-devel)
            # Headers for `pip install python-augeas` (augeas.h).
            _rpm_family_pkg_available augeas-devel && _dnf_pkgs+=(augeas-devel)
            # Windows offline fixes: NBD + NTFS (mount.ntfs / ntfs-3g, ntfsfix for dirty volumes).
            _rpm_family_pkg_available ntfs-3g && _dnf_pkgs+=(ntfs-3g)
            _rpm_family_pkg_available ntfsprogs && _dnf_pkgs+=(ntfsprogs)
            run dnf install -y --setopt=install_weak_deps=False "${_dnf_pkgs[@]}"
            ;;
        yum)
            local -a _qemu_rpms
            mapfile -t _qemu_rpms < <(_qemu_rpms_rpm_family)
            local -a _yum_pkgs=(
                python3 python3-pip
                "${_qemu_rpms[@]}"
                libvirt-daemon-kvm libvirt-client virt-install
                edk2-ovmf
                libguestfs libguestfs-tools python3-libguestfs supermin
                bsdtar
                openssh-clients sshpass rsync curl tar unzip
            )
            _rpm_family_pkg_available python3-virtualenv && _yum_pkgs+=(python3-virtualenv)
            _rpm_family_pkg_available python3-hivex && _yum_pkgs+=(python3-hivex)
            _rpm_family_pkg_available python3.12-hivex && _yum_pkgs+=(python3.12-hivex)
            _rpm_family_pkg_available hivex && _yum_pkgs+=(hivex)
            _rpm_family_pkg_available nbd && _yum_pkgs+=(nbd)
            _rpm_family_pkg_available nbdkit && _yum_pkgs+=(nbdkit)
            _rpm_family_pkg_available python3.12 && _yum_pkgs+=(python3.12)
            _rpm_family_pkg_available python3.12-pip && _yum_pkgs+=(python3.12-pip)
            _rpm_family_pkg_available python3.12-devel && _yum_pkgs+=(python3.12-devel)
            _rpm_family_pkg_available augeas-devel && _yum_pkgs+=(augeas-devel)
            _rpm_family_pkg_available ntfs-3g && _yum_pkgs+=(ntfs-3g)
            _rpm_family_pkg_available ntfsprogs && _yum_pkgs+=(ntfsprogs)
            run yum install -y "${_yum_pkgs[@]}"
            ;;
        apt)
            apt_update_once
            # Core set for Ubuntu Server 22.04/24.04 and Debian — optional entries skip if repo has no index entry.
            local -a _apt_pkgs=(
                python3 python3-pip python3-venv
                qemu-utils qemu-system-x86
                libvirt-daemon-system libvirt-clients virtinst
                libguestfs-tools supermin
                openssh-client sshpass rsync curl tar unzip
            )
            if _apt_pkg_available ovmf; then
                _apt_pkgs+=(ovmf)
            elif _apt_pkg_available qemu-ovmf-x86; then
                _apt_pkgs+=(qemu-ovmf-x86)
            elif _apt_pkg_available edk2-ovmf; then
                _apt_pkgs+=(edk2-ovmf)
            fi
            _apt_pkg_available python3-guestfs && _apt_pkgs+=(python3-guestfs)
            _apt_pkg_available supermin && _apt_pkgs+=(supermin)
            _apt_pkg_available python3-hivex && _apt_pkgs+=(python3-hivex)
            _apt_pkg_available libarchive-tools && _apt_pkgs+=(libarchive-tools)
            _apt_pkg_available nbd-client && _apt_pkgs+=(nbd-client)
            _apt_pkg_available nbdkit && _apt_pkgs+=(nbdkit)
            _apt_pkg_available libaugeas-dev && _apt_pkgs+=(libaugeas-dev)
            _apt_pkg_available ntfs-3g && _apt_pkgs+=(ntfs-3g)
            run apt-get install -y -qq "${_apt_pkgs[@]}"
            ;;
        zypper)
            run zypper install -y \
                python3 python3-pip python3-virtualenv \
                qemu-tools qemu-kvm \
                libvirt libvirt-client virt-install \
                qemu-ovmf-x86_64 \
                libguestfs0 guestfs-tools python3-libguestfs supermin \
                openssh sshpass rsync curl tar unzip \
                2>/dev/null
            ;;
    esac
    info "System packages installed ($(elapsed))"
}

# ── Step 2: Services + kernel modules ──
setup_services() {
    step "Step 2/7: Enabling services and kernel modules"

    # Load kernel modules
    for mod in nbd kvm vhost_net; do
        if modprobe "$mod" 2>/dev/null; then
            info "Loaded: $mod"
        else
            warn "Failed to load: $mod"
        fi
    done

    # CPU-specific KVM
    if grep -q "GenuineIntel" /proc/cpuinfo 2>/dev/null; then
        modprobe kvm_intel 2>/dev/null && info "Loaded: kvm_intel" || warn "kvm_intel failed (check BIOS VT-x)"
    elif grep -q "AuthenticAMD" /proc/cpuinfo 2>/dev/null; then
        modprobe kvm_amd 2>/dev/null && info "Loaded: kvm_amd" || warn "kvm_amd failed (check BIOS SVM)"
    fi

    # Persist modules
    cat > /etc/modules-load.d/hyper2kvm.conf << 'EOF'
nbd
kvm
vhost_net
EOF
    cat > /etc/modprobe.d/hyper2kvm-nbd.conf << 'EOF'
options nbd nbds_max=128 max_part=16
EOF

    # libvirtd must be *active* (not just enabled) for virsh/VMs
    run systemctl daemon-reload 2>/dev/null || true
    run systemctl enable libvirtd 2>/dev/null || true
    run systemctl reset-failed libvirtd 2>/dev/null || true
    run systemctl start libvirtd 2>/dev/null || true
    if systemctl list-unit-files 2>/dev/null | grep -q '^libvirtd.socket'; then
        run systemctl enable --now libvirtd.socket 2>/dev/null || true
    fi
    local retries=30
    while [ $retries -gt 0 ]; do
        systemctl is-active libvirtd &>/dev/null && break
        sleep 1
        retries=$((retries - 1))
    done
    if ! systemctl is-active libvirtd &>/dev/null; then
        warn "libvirtd not yet active — restart and re-wait"
        run systemctl restart libvirtd 2>/dev/null || true
        sleep 2
        retries=20
        while [ $retries -gt 0 ]; do
            systemctl is-active libvirtd &>/dev/null && break
            sleep 1
            retries=$((retries - 1))
        done
    fi
    if systemctl is-active libvirtd &>/dev/null; then
        info "libvirtd: active"
    else
        warn "libvirtd is still inactive — run: systemctl status libvirtd; journalctl -u libvirtd -b"
    fi

    # Ensure default network
    if ! virsh net-info default &>/dev/null; then
        warn "Default network missing — creating..."
        virsh net-define /usr/share/libvirt/networks/default.xml 2>/dev/null || true
    fi
    virsh net-start default 2>/dev/null || true
    virsh net-autostart default 2>/dev/null || true

    # Create runtime directories (needed by VMCraft NBD locking)
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
    if [ -f "$REPO_DIR/etc/tmpfiles.d/hyper2kvm.conf" ]; then
        cp "$REPO_DIR/etc/tmpfiles.d/hyper2kvm.conf" /etc/tmpfiles.d/hyper2kvm.conf
        systemd-tmpfiles --create /etc/tmpfiles.d/hyper2kvm.conf 2>/dev/null || true
        info "Runtime dirs: /run/hyper2kvm (via tmpfiles.d)"
    else
        mkdir -p /run/hyper2kvm
        info "Runtime dirs: /run/hyper2kvm"
    fi

    info "Services ready ($(elapsed))"
}

# ── Step 3: govc ──
install_govc() {
    step "Step 3/7: Installing govc"
    local govc_bin="/usr/local/bin/govc"

    if [ -x "$govc_bin" ]; then
        info "govc already installed: $("$govc_bin" version)"
        return
    fi
    if command -v govc &>/dev/null; then
        info "govc already installed: $(govc version)"
        return
    fi

    local arch
    case "$(uname -m)" in
        x86_64)  arch="x86_64" ;;
        aarch64) arch="arm64" ;;
        *)       warn "Unsupported arch for govc: $(uname -m)"; return ;;
    esac

    local url
    url="$(hyper2kvm_govc_download_url "$arch")"
    local tmpfile
    tmpfile=$(mktemp)
    # RETURN cleans up on any function exit; EXIT would re-fire at script end with `tmpfile` out of scope (`set -u`).
    trap 'rm -f "${tmpfile:-}"' RETURN
    retry curl -fsSL "$url" -o "$tmpfile"
    tar xzf "$tmpfile" -C /usr/local/bin govc
    chmod +x "$govc_bin"
    rm -f "$tmpfile"
    trap - RETURN
    if ! "$govc_bin" version >/dev/null 2>&1; then
        if ! command -v govc &>/dev/null || ! govc version >/dev/null 2>&1; then
            echo "ERROR: govc download failed or binary is corrupt"
            exit 1
        fi
    fi
    info "govc installed: $("$govc_bin" version)"
}

# ── Step 4: Python deps ──
install_python_deps() {
    step "Step 4/7: Installing Python dependencies"

    pip_install pyvmomi click pyyaml argcomplete boto3 pycdlib || \
        warn "pip install failed — try: pip3 install --user pyvmomi click pyyaml argcomplete boto3 pycdlib"
    info "Python deps installed ($(elapsed))"
}

# ── Step 5: hyper2kvm ──
install_hyper2kvm() {
    step "Step 5/7: Installing hyper2kvm"

    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local repo_dir
    repo_dir="$(cd "$SCRIPT_DIR/.." 2>/dev/null && pwd)"

    if [ -f "$repo_dir/pyproject.toml" ] && grep -q "hyper2kvm" "$repo_dir/pyproject.toml" 2>/dev/null; then
        info "Installing from source: $repo_dir"
        pip_install -e "$repo_dir" || true
    else
        pip_install hyper2kvm || true
    fi
    info "hyper2kvm installed: $(h2kvmctl --version 2>/dev/null || echo 'check PATH')"
}

# ── Step 6: User permissions ──
setup_user_perms() {
    step "Step 6/7: Setting up user permissions"

    local target_user="${SUDO_USER:-$(logname 2>/dev/null || echo "")}"
    if [ -n "$target_user" ] && [ "$target_user" != "root" ]; then
        for group in libvirt kvm qemu disk; do
            if getent group "$group" &>/dev/null; then
                usermod -aG "$group" "$target_user" 2>/dev/null || true
            fi
        done
        info "User $target_user added to libvirt/kvm/qemu/disk groups"
    else
        info "Running as root — skipping user setup"
    fi
}

# ── Step 7: VirtIO Windows drivers ──
install_virtio_win() {
    step "Step 7/8: VirtIO Windows drivers"

    local iso="/var/lib/hyper2kvm/virtio-win.iso"
    local cache="/var/lib/hyper2kvm/virtio-win-extracted"
    local url="$HYPER2KVM_VIRTIO_WIN_ISO_URL"

    if [ -f "$iso" ]; then
        info "virtio-win.iso: $iso"
    else
        mkdir -p /var/lib/hyper2kvm
        info "Downloading virtio-win.iso..."
        if retry curl -fSL "$url" -o "$iso"; then
            info "virtio-win.iso installed: $iso"
        else
            warn "Download failed — Windows migrations will use SATA/e1000 fallback"
            warn "Manual: curl -fSL $url -o $iso"
            rm -f "$iso"
            return
        fi
    fi

    # Pre-extract ISO for faster Windows migrations (cached, one-time)
    if [ -d "$cache/viostor" ]; then
        info "VirtIO ISO cache: $cache (already extracted)"
    elif command -v bsdtar &>/dev/null && [ -f "$iso" ]; then
        info "Pre-extracting VirtIO ISO..."
        rm -rf "$cache"
        mkdir -p "$cache"
        bsdtar xf "$iso" -C "$cache" 2>/dev/null || true
        if [ -d "$cache/viostor" ]; then
            stat -c %Y "$iso" > "$cache/.iso_mtime"
            info "VirtIO ISO extracted: $cache"
        else
            warn "bsdtar extraction incomplete — hyper2kvm will extract on first Windows migration"
        fi
    elif [ -f "$iso" ]; then
        warn "bsdtar not found — install bsdtar for pre-extraction, or hyper2kvm will extract on first Windows migration"
    fi
}

# ── Step 8: Firewall + optional ──
setup_firewall_and_extras() {
    step "Step 8/8: Firewall and optional components"

    # Firewall
    if command -v firewall-cmd &>/dev/null; then
        run firewall-cmd --permanent --add-service=ssh 2>/dev/null || true
        run firewall-cmd --permanent --add-service=libvirt 2>/dev/null || true
        warn "Opening VNC ports 5900-5999 (VM console access)"
        run firewall-cmd --permanent --add-port=5900-5999/tcp 2>/dev/null || true
        run firewall-cmd --reload 2>/dev/null || true
        info "Firewall: SSH, libvirt, VNC opened"
    elif command -v ufw &>/dev/null; then
        run ufw allow ssh 2>/dev/null || true
        run ufw allow 16509/tcp 2>/dev/null || true
        run ufw allow 5900:5999/tcp 2>/dev/null || true
        info "Firewall: SSH, libvirt, VNC opened"
    fi

    # Cockpit
    if $WITH_COCKPIT; then
        step "Installing Cockpit web UI"
        case "$PKG" in
            dnf)    run dnf install -y cockpit cockpit-machines 2>/dev/null || true ;;
            yum)    run yum install -y cockpit cockpit-machines 2>/dev/null || true ;;
            apt)    apt_update_once; run apt-get install -y -qq cockpit cockpit-machines 2>/dev/null || true ;;
            zypper) run zypper install -y cockpit cockpit-machines 2>/dev/null || true ;;
        esac
        run systemctl enable --now cockpit.socket 2>/dev/null || true
        if command -v firewall-cmd &>/dev/null; then
            run firewall-cmd --permanent --add-service=cockpit 2>/dev/null || true
            run firewall-cmd --reload 2>/dev/null || true
        elif command -v ufw &>/dev/null; then
            run ufw allow 9090/tcp 2>/dev/null || true
        fi
        info "Cockpit installed (https://$(hostname -I | awk '{print $1}'):9090)"
    fi

    # h2kweb (web dashboard)
    if $WITH_H2KWEB; then
        step "Installing h2kweb web dashboard"
        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
        if [ -f "$REPO_DIR/web/Makefile" ]; then
            (cd "$REPO_DIR/web" && make install) 2>&1 | tail -5
            if command -v firewall-cmd &>/dev/null; then
                run firewall-cmd --permanent --add-port=5070/tcp 2>/dev/null || true
                run firewall-cmd --reload 2>/dev/null || true
            elif command -v ufw &>/dev/null; then
                run ufw allow 5070/tcp 2>/dev/null || true
            fi
            info "h2kweb installed (https://$(hostname -I | awk '{print $1}'):5070)"
        else
            warn "h2kweb: web/ directory not found — build with: cd web && make build"
        fi
    fi

    # K3s
    if $WITH_K3S; then
        step "Installing K3s"
        if ! command -v kubectl &>/dev/null; then
            retry curl -sfL https://get.k3s.io -o /tmp/k3s-install.sh && INSTALL_K3S_EXEC="--disable=traefik" sh /tmp/k3s-install.sh && rm -f /tmp/k3s-install.sh
            mkdir -p ~/.kube
            cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
            chmod 600 ~/.kube/config
        fi
        if command -v firewall-cmd &>/dev/null; then
            run firewall-cmd --permanent --add-port=6443/tcp 2>/dev/null || true
            run firewall-cmd --reload 2>/dev/null || true
        fi
        info "K3s installed"
    fi
}

# ── Verify ──
verify_install() {
    echo ""
    step "Verification"
    local ok=0 fail=0 opt=0

    # pip/govc install to /usr/local/bin — minimal root PATH on EL misses it.
    export PATH="/usr/local/bin:/usr/local/sbin:/usr/bin:/bin:${PATH:-}"

    detect_distro 2>/dev/null || true

    for tool in h2kvmctl qemu-img qemu-nbd nbdkit virsh govc virt-filesystems supermin; do
        if command -v "$tool" &>/dev/null; then
            info "$tool: $(which $tool)"
            ok=$((ok + 1))
        else
            error "$tool: MISSING"
            fail=$((fail + 1))
        fi
    done

    for tool in guestfish ovftool virt-install kubectl; do
        if command -v "$tool" &>/dev/null; then
            info "$tool: $(which $tool)"
            ok=$((ok + 1))
        else
            warn "$tool: not installed (optional)"
            opt=$((opt + 1))
        fi
    done

    if python3 -c "import pyVmomi" 2>/dev/null; then
        info "pyvmomi: OK"; ok=$((ok + 1))
    else
        warn "pyvmomi: not installed (optional)"; opt=$((opt + 1))
    fi

    local ovmf=""
    for p in /usr/share/OVMF/OVMF_CODE.fd /usr/share/edk2/ovmf/OVMF_CODE.fd /usr/share/qemu/ovmf-x86_64-code.bin; do
        [ -f "$p" ] && ovmf="$p" && break
    done
    if [ -n "$ovmf" ]; then
        info "OVMF: $ovmf"; ok=$((ok + 1))
    else
        warn "OVMF: not found"; fail=$((fail + 1))
    fi

    # VirtIO Windows drivers
    if [ -f /var/lib/hyper2kvm/virtio-win.iso ]; then
        info "virtio-win: /var/lib/hyper2kvm/virtio-win.iso"; ok=$((ok + 1))
    else
        warn "virtio-win: not found (needed for Windows VirtIO migration)"; opt=$((opt + 1))
    fi

    if lsmod | grep -q "^nbd " || [ -e /dev/nbd0 ]; then
        info "nbd module: loaded"; ok=$((ok + 1))
    else
        warn "nbd: not loaded (run: sudo modprobe nbd)"; fail=$((fail + 1))
    fi

    if [ -e /dev/kvm ]; then
        info "/dev/kvm: available"; ok=$((ok + 1))
    else
        warn "/dev/kvm: not available"
    fi

    echo ""
    info "$ok components ready, $fail missing, $opt optional skipped ($(elapsed))"

    # Quick test
    h2kvmctl --version &>/dev/null && info "h2kvmctl works" || warn "h2kvmctl not in PATH"

    echo ""
    echo "Next:"
    echo "    sudo h2kvmctl --config photon-to-libvirt.yaml"
    echo "    sudo ./scripts/run-demo.sh"
    echo ""

    local target_user="${SUDO_USER:-}"
    if [ -n "$target_user" ] && [ "$target_user" != "root" ]; then
        dim "Log out and back in for group changes (or: newgrp libvirt)"
    fi
}

# ── Main ──
main() {
    if [ "$VERIFY_ONLY" = "true" ]; then
        verify_install
        return
    fi

    setup_logging

    echo ""
    echo "hyper2kvm Quickstart"
    echo "$(date)"
    dim "Installer bundle: ${HYPER2KVM_INSTALL_BUNDLE_ID}"
    echo ""

    [ "$DRY_RUN" = "true" ] && warn "DRY RUN — no changes will be made"

    preflight
    pip_setup

    if $MINIMAL; then
        install_system_packages
        install_govc
        install_python_deps
        install_hyper2kvm
    else
        install_system_packages
        setup_services
        install_govc
        install_python_deps
        install_hyper2kvm
        setup_user_perms
        install_virtio_win
        setup_firewall_and_extras
    fi

    verify_install
}

main
