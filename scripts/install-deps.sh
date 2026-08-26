#!/bin/bash
set -euo pipefail
# ============================================
# h2kvm — Install all dependencies
# ============================================
# Production-grade installer for govc, OVF Tool, pyvmomi,
# qemu-img, libguestfs, libvirt, OVMF, and h2kvm.
#
# Supports: Fedora, RHEL/CentOS, Ubuntu/Debian, openSUSE
#
# Usage:
#   sudo ./scripts/install-deps.sh          # install everything
#   sudo ./scripts/install-deps.sh --govc   # install only govc
#   sudo ./scripts/install-deps.sh --verify # check all tools
#   sudo ./scripts/install-deps.sh --all    # install everything
#
# Individual components:
#   --python   --govc    --ovftool  --pyvmomi
#   --qemu     --guestfs --libvirt  --ovmf
#   --h2kvm --verify
#
# Environment:
#   DRY_RUN=true    Preview without installing
#   LOG_FILE=path   Custom log path
#   H2KVM_INSTALL_BUNDLE_ID, H2KVM_GOVC_DOWNLOAD_PREFIX, H2KVM_VIRTIO_WIN_ISO_URL
#   H2KVM_PYTHON=/usr/bin/python3.12  Force hivex bindings for the same interpreter as h2kvmctl/pip
# ============================================

trap 'echo -e "\n[FATAL] install-deps failed at line $LINENO"; exit 1' ERR

# shellcheck source=install-versions.inc.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/install-versions.inc.sh"

# ── Config ──
DRY_RUN="${DRY_RUN:-false}"
LOG_FILE="${LOG_FILE:-/var/log/h2kvm-install.log}"
START_TIME=$(date +%s)

# ── Helpers ──
info()  { echo "✅ $*"; }
warn()  { echo "⚠️ $*"; }
error() { echo "❌ $*"; }
step()  { echo "🔹$*"; }

run() {
    if [ "$DRY_RUN" = "true" ]; then
        echo "    [dry-run] $*"
    else
        "$@"
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

elapsed() {
    echo "$(($(date +%s) - START_TIME))s"
}

# PEP 668: modern distros block bare pip install.
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
    run pip3 install $PIP_EXTRA_ARGS --quiet "$@"
}

# ── Logging ──
setup_logging() {
    mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || LOG_FILE="/tmp/h2kvm-install.log"
    touch "$LOG_FILE" 2>/dev/null || LOG_FILE="/tmp/h2kvm-install.log"
    if [ "${H2KVM_REMOTE_INSTALL:-}" = 1 ]; then
        return 0
    fi
    exec > >(tee -a "$LOG_FILE") 2>&1
}

# ── Detect distro ──
detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        DISTRO_ID="${ID}"
        DISTRO_FAMILY="${ID_LIKE:-$ID}"
    else
        error "Cannot detect distribution"
        exit 1
    fi

    case "$DISTRO_ID" in
        fedora)                 PKG_MGR="dnf" ;;
        rhel|centos|rocky|alma) PKG_MGR="dnf" ;;
        ubuntu|debian|pop)      PKG_MGR="apt" ;;
        opensuse*|sles)         PKG_MGR="zypper" ;;
        *)
            if echo "$DISTRO_FAMILY" | grep -q "rhel\|fedora"; then
                PKG_MGR="dnf"
            elif echo "$DISTRO_FAMILY" | grep -q "debian"; then
                PKG_MGR="apt"
            elif echo "$DISTRO_FAMILY" | grep -q "suse"; then
                PKG_MGR="zypper"
            else
                error "Unsupported distribution: $DISTRO_ID"
                exit 1
            fi
            ;;
    esac

    info "Detected: ${DISTRO_ID} (${PKG_MGR}) — $(uname -m)"
}

# ── Python3 + pip ──
install_python() {
    if command -v python3 &>/dev/null && command -v pip3 &>/dev/null; then
        info "Python3 already installed: $(python3 --version)"
        return
    fi

    step "Installing Python3 and pip"
    case "$PKG_MGR" in
        dnf)    run dnf install -y python3 python3-pip python3-virtualenv ;;
        apt)    run apt-get update -qq && run apt-get install -y -qq python3 python3-pip python3-venv ;;
        zypper) run zypper install -y python3 python3-pip python3-virtualenv ;;
    esac
    info "Python3 installed: $(python3 --version)"
}

# ── govc ──
install_govc() {
    if command -v govc &>/dev/null; then
        info "govc already installed: $(govc version)"
        return
    fi

    step "Installing govc"
    local arch
    case "$(uname -m)" in
        x86_64)  arch="x86_64" ;;
        aarch64) arch="arm64" ;;
        *)       error "Unsupported arch: $(uname -m)"; return 1 ;;
    esac

    local url
    url="$(h2kvm_govc_download_url "$arch")"
    local tmpfile
    tmpfile=$(mktemp)
    retry curl -fsSL "$url" -o "$tmpfile"
    tar xzf "$tmpfile" -C /usr/local/bin govc
    rm -f "$tmpfile"
    chmod +x /usr/local/bin/govc
    info "govc installed: $(govc version)"
}

# ── OVF Tool ──
install_ovftool() {
    if command -v ovftool &>/dev/null; then
        info "OVF Tool already installed: $(ovftool --version 2>/dev/null | head -1)"
        return
    fi

    # Check if zip or bundle exists in current dir
    local installer
    installer=$(ls VMware-ovftool-*.zip 2>/dev/null | head -1)
    if [ -n "$installer" ]; then
        step "Installing OVF Tool from $installer"
        run mkdir -p /opt/ovftool
        run unzip -o "$installer" -d /opt/ovftool
        run ln -sf /opt/ovftool/ovftool /usr/local/bin/ovftool 2>/dev/null || true
        info "OVF Tool installed: $(ovftool --version 2>/dev/null | head -1)"
        return
    fi

    # Legacy bundle installer (OVF Tool 4.x)
    installer=$(ls VMware-ovftool-*.bundle 2>/dev/null | head -1)
    if [ -n "$installer" ]; then
        step "Installing OVF Tool from $installer"
        run chmod +x "$installer"
        run ./"$installer" --eulas-agreed --required
        if [ -d /opt/ovftool ]; then
            run ln -sf /opt/ovftool/ovftool /usr/local/bin/ovftool 2>/dev/null || true
            info "OVF Tool installed: $(ovftool --version 2>/dev/null | head -1)"
        fi
        return
    fi

    warn "OVF Tool: download from https://developer.broadcom.com/tools/open-virtualization-format-ovf-tool/latest"
}

# ── pyvmomi ──
install_pyvmomi() {
    if python3 -c "import pyVmomi" 2>/dev/null; then
        info "pyvmomi already installed"
        return
    fi

    step "Installing pyvmomi"
    pip_install pyvmomi
    info "pyvmomi installed"
}

# ── qemu-img ──
install_qemu() {
    if command -v qemu-img &>/dev/null; then
        info "qemu-img already installed: $(qemu-img --version | head -1)"
        return
    fi

    step "Installing qemu-img"
    case "$PKG_MGR" in
        dnf)    run dnf install -y qemu-img ;;
        apt)    run apt-get update -qq && run apt-get install -y -qq qemu-utils ;;
        zypper) run zypper install -y qemu-tools ;;
    esac
    info "qemu-img installed"
}

# ── libguestfs (recommended — auto-used for LVM/LUKS disks) ──
install_guestfs() {
    if command -v guestfish &>/dev/null && python3 -c "import guestfs" 2>/dev/null; then
        info "libguestfs + Python bindings already installed"
        return
    fi

    step "Installing libguestfs + Python bindings (recommended — auto-used for LVM/LUKS)"
    case "$PKG_MGR" in
        dnf)    run dnf install -y libguestfs libguestfs-tools python3-libguestfs supermin ;;
        apt)    run apt-get update -qq && run apt-get install -y -qq libguestfs-tools python3-guestfs supermin ;;
        zypper) run zypper install -y libguestfs0 guestfs-tools python3-libguestfs supermin ;;
    esac
    info "libguestfs installed"
}

# ── libvirt + KVM + kernel modules ──
install_libvirt() {
    if command -v virsh &>/dev/null; then
        info "libvirt already installed: $(virsh --version)"
        return
    fi

    step "Installing libvirt + KVM"
    case "$PKG_MGR" in
        dnf)
            run dnf install -y libvirt-daemon libvirt-client \
                libvirt-daemon-kvm qemu-kvm virt-install
            ;;
        apt)
            run apt-get update -qq && run apt-get install -y -qq \
                libvirt-daemon-system libvirt-clients \
                qemu-kvm virtinst
            ;;
        zypper)
            run zypper install -y libvirt libvirt-client \
                qemu-kvm virt-install
            ;;
    esac

    # Enable services — libvirtd must be running, not just enabled
    run systemctl enable libvirtd 2>/dev/null || true
    run systemctl reset-failed libvirtd 2>/dev/null || true
    run systemctl start libvirtd 2>/dev/null || true
    if systemctl list-unit-files 2>/dev/null | grep -q '^libvirtd.socket'; then
        run systemctl enable --now libvirtd.socket 2>/dev/null || true
    fi
    local _lvr=30
    while [ $_lvr -gt 0 ]; do
        systemctl is-active libvirtd &>/dev/null && break
        sleep 1
        _lvr=$((_lvr - 1))
    done
    if ! systemctl is-active libvirtd &>/dev/null; then
        run systemctl restart libvirtd 2>/dev/null || true
        sleep 2
        _lvr=15
        while [ $_lvr -gt 0 ]; do
            systemctl is-active libvirtd &>/dev/null && break
            sleep 1
            _lvr=$((_lvr - 1))
        done
    fi
    systemctl is-active libvirtd &>/dev/null && info "libvirtd: active" || warn "libvirtd: still inactive"
    run virsh net-start default 2>/dev/null || true
    run virsh net-autostart default 2>/dev/null || true

    # Load kernel modules
    step "Loading kernel modules"
    for mod in nbd kvm vhost_net; do
        if modprobe "$mod" 2>/dev/null; then
            info "Loaded: $mod"
        else
            warn "Failed to load: $mod"
        fi
    done

    # CPU-specific KVM module
    if grep -q "GenuineIntel" /proc/cpuinfo 2>/dev/null; then
        modprobe kvm_intel 2>/dev/null && info "Loaded: kvm_intel" || warn "kvm_intel failed (check BIOS VT-x)"
    elif grep -q "AuthenticAMD" /proc/cpuinfo 2>/dev/null; then
        modprobe kvm_amd 2>/dev/null && info "Loaded: kvm_amd" || warn "kvm_amd failed (check BIOS SVM)"
    fi

    # Persist modules across reboots
    cat > /etc/modules-load.d/h2kvm.conf << 'MODEOF'
nbd
kvm
vhost_net
MODEOF
    cat > /etc/modprobe.d/h2kvm-nbd.conf << 'MODEOF'
options nbd nbds_max=128 max_part=16
MODEOF

    info "libvirt + kernel modules installed"
}

# ── OVMF (UEFI firmware) ──
install_ovmf() {
    for p in /usr/share/OVMF/OVMF_CODE.fd \
             /usr/share/edk2/ovmf/OVMF_CODE.fd \
             /usr/share/qemu/ovmf-x86_64-code.bin; do
        if [ -f "$p" ]; then
            info "OVMF already installed: $p"
            return
        fi
    done

    step "Installing OVMF"
    case "$PKG_MGR" in
        dnf)    run dnf install -y edk2-ovmf ;;
        apt)    run apt-get update -qq && run apt-get install -y -qq ovmf ;;
        zypper) run zypper install -y qemu-ovmf-x86_64 ;;
    esac
    info "OVMF installed"
}

# ── mkosi (appliance VM builder) ──
install_mkosi() {
    if command -v mkosi &>/dev/null; then
        info "mkosi already installed: $(mkosi --version 2>/dev/null)"
        return
    fi

    step "Installing mkosi (from git for latest version)"
    # Install runtime deps first
    case "$PKG_MGR" in
        dnf)    run dnf install -y systemd-container bubblewrap 2>/dev/null || true ;;
        apt)    run apt-get update -qq; run apt-get install -y -qq systemd-container bubblewrap 2>/dev/null || true ;;
        zypper) run zypper install -y systemd-container 2>/dev/null || true ;;
    esac
    # Always install mkosi from git (distro packages are often too old)
    pip_install git+https://github.com/systemd/mkosi.git
    info "mkosi installed: $(mkosi --version 2>/dev/null || echo 'check PATH')"
}

# ── h2kvm itself ──
install_h2kvm() {
    if command -v h2kvmctl &>/dev/null; then
        info "h2kvm already installed: $(h2kvmctl --version 2>/dev/null | head -1)"
        return
    fi

    step "Installing h2kvm"

    # If we're inside the repo, install from source
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    if [ -f "$script_dir/pyproject.toml" ] && grep -q "h2kvm" "$script_dir/pyproject.toml" 2>/dev/null; then
        info "Installing from source: $script_dir"
        pip_install -e "$script_dir"
    else
        pip_install h2kvm
    fi
    # KubeVirt/k3s deploy (--deploy-k8s) requires the kubernetes Python package
    pip_install kubernetes || warn "kubernetes pip package failed — KubeVirt deploy will not work until: pip install kubernetes"
    info "h2kvm installed: $(h2kvmctl --version 2>/dev/null | head -1)"
}

# ── hivex + bsdtar (Windows registry access + ISO extraction) ──
# Bindings must match the interpreter that runs h2kvmctl (often pip → Python 3.12 on EL9).
resolve_hivex_target_python() {
    if [ -n "${H2KVM_PYTHON:-}" ] && [ -x "${H2KVM_PYTHON}" ]; then
        echo "${H2KVM_PYTHON}"
        return 0
    fi
    local h2 line1 she
    h2=$(command -v h2kvmctl 2>/dev/null || true)
    if [ -n "$h2" ] && [ -r "$h2" ]; then
        line1=$(head -n1 "$h2" 2>/dev/null || true)
        case "$line1" in
            \#!*)
                she="${line1#\#!}"
                she="${she%% *}"
                she="${she//$'\r'/}"
                if [ -x "$she" ]; then
                    echo "$she"
                    return 0
                fi
                ;;
        esac
    fi
    local py
    for py in python3.12 python3.11 python3.10 python3; do
        if command -v "$py" &>/dev/null && "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
            echo "$py"
            return 0
        fi
    done
    echo "python3"
}

hivex_try_install_distro_pkgs() {
    local active_py="$1"
    local mm
    mm=$("$active_py" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')

    case "$PKG_MGR" in
        dnf|yum)
            # CLI tools (hivexget) + C library/headers + compressor for virtio-win ISO cache
            if command -v dnf &>/dev/null; then
                run dnf install -y hivex hivex-devel bsdtar 2>/dev/null || true
                run dnf install -y "python${mm}-hivex" 2>/dev/null || true
                run dnf install -y python3-hivex 2>/dev/null || true
            elif command -v yum &>/dev/null; then
                run yum install -y hivex hivex-devel bsdtar 2>/dev/null || true
                run yum install -y "python${mm}-hivex" 2>/dev/null || true
                run yum install -y python3-hivex 2>/dev/null || true
            fi
            ;;
        apt)
            run apt-get update -qq 2>/dev/null || true
            # Debian/Ubuntu: libhivex-bin = hivexget; libarchive-tools = bsdtar on some releases
            run apt-get install -y -qq libhivex-bin libhivex-dev python3-hivex libarchive-tools 2>/dev/null || true
            run apt-get install -y -qq bsdtar 2>/dev/null || true
            if apt-cache show --no-all-versions "python${mm}-hivex" &>/dev/null 2>&1; then
                run apt-get install -y -qq "python${mm}-hivex" 2>/dev/null || true
            fi
            ;;
        zypper)
            run zypper install -y hivex hivex-devel python3-hivex bsdtar 2>/dev/null || true
            ;;
        *)
            warn "hivex: unknown PKG_MGR=$PKG_MGR"
            ;;
    esac
}

hivex_build_from_source() {
    local active_py="$1"
    local mm ver tarball_url build_dir topdir hivex_ver src_rpm
    mm=$("$active_py" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    ver="${HIVEX_UPSTREAM_VERSION:-1.3.24}"
    tarball_url="${HIVEX_UPSTREAM_TARBALL_URL}"

    case "$PKG_MGR" in
        dnf|yum)
            if command -v dnf &>/dev/null; then
                run dnf install -y "dnf-command(download)" 2>/dev/null || true
                # hivex configure requires pod2man/pod2text; lib/ needs libxml2 + gettext; optional bindings often break — skip ocaml/perl/ruby via configure flags.
                run dnf install -y hivex-devel "python${mm}-devel" gcc gcc-c++ make autoconf automake libtool pkgconf-pkg-config patch \
                    rpm-build curl cpio gettext-devel perl \
                    libxml2-devel readline-devel libffi-devel 2>/dev/null || true
            elif command -v yum &>/dev/null; then
                run yum install -y hivex-devel "python${mm}-devel" gcc gcc-c++ make autoconf automake libtool pkgconfig patch \
                    rpm-build curl cpio gettext-devel perl \
                    libxml2-devel readline-devel libffi-devel 2>/dev/null || true
            fi
            ;;
        apt)
            run apt-get install -y -qq libhivex-dev "python${mm}-dev" gcc g++ make autoconf automake libtool pkg-config patch curl ca-certificates \
                gettext perl libxml2-dev libreadline-dev 2>/dev/null || true
            ;;
        zypper)
            run zypper install -y hivex-devel python3-devel gcc make autoconf automake libtool pkg-config patch curl 2>/dev/null || true
            ;;
    esac

    build_dir="/tmp/hivex-build-$$"
    mkdir -p "$build_dir" || return 1
    (
        cd "$build_dir" || exit 1
        topdir=""
        # Prefer distro source RPM (matches libhivex soname on this OS)
        if command -v rpm &>/dev/null && { command -v dnf &>/dev/null || command -v yum &>/dev/null; }; then
            if run dnf download --source hivex 2>/dev/null || run yumdownloader --source hivex 2>/dev/null; then
                src_rpm=""
                for f in hivex-*.src.rpm; do
                    [ -f "$f" ] && src_rpm="$f" && break
                done
                if [ -n "$src_rpm" ] && [ -f "$src_rpm" ]; then
                    rpm2cpio "$src_rpm" | cpio -idm 2>/dev/null || true
                    hivex_ver=$(rpm -q --qf '%{VERSION}' hivex 2>/dev/null || echo "")
                    hivex_ver="${hivex_ver:-$ver}"
                    if [ -f "hivex-${hivex_ver}.tar.gz" ]; then
                        tar xf "hivex-${hivex_ver}.tar.gz"
                        topdir=$(find . -maxdepth 1 -type d -name 'hivex-*' | head -1)
                    fi
                fi
            fi
        fi
        if [ -z "$topdir" ] || [ ! -d "$topdir" ]; then
            info "hivex: fetching upstream ${tarball_url}"
            if retry curl -fSL "$tarball_url" -o "hivex-upstream.tar.gz"; then
                tar xf hivex-upstream.tar.gz
                topdir=$(find . -maxdepth 1 -type d -name 'hivex-*' | head -1)
            fi
        fi
        if [ -z "$topdir" ] || [ ! -d "$topdir" ]; then
            warn "hivex: could not unpack source"
            exit 1
        fi
        cd "$topdir" || exit 1
        if [ -x ./autogen.sh ]; then
            run ./autogen.sh || exit 1
        elif [ ! -f ./configure ]; then
            run autoreconf -fi || exit 1
        fi
        if [ ! -f ./configure ]; then
            warn "hivex: no configure script"
            exit 1
        fi

        # configure.ac probes a program named "python" — symlink our target interpreter (may be python3.12 only).
        pywrap="$(mktemp -d "${TMPDIR:-/tmp}/hivex-pywrap.XXXXXX")"
        ln -sf "$(command -v "$active_py")" "$pywrap/python"
        export PATH="$pywrap:${PATH}"

        # Disable optional language bindings that routinely fail on migration hosts (OCaml stack, Perl XS, Ruby).
        # Keep only C library + Python extension.
        cfg_rc=0
        run ./configure --prefix=/usr \
            PYTHON="$active_py" \
            --disable-ocaml --disable-perl --disable-ruby \
            --without-readline \
            || cfg_rc=$?
        if [ "$cfg_rc" -ne 0 ]; then
            warn "hivex: configure with --prefix=/usr failed (rc=$cfg_rc); retrying --prefix=/usr/local"
            run ./configure --prefix=/usr/local \
                PYTHON="$active_py" \
                --disable-ocaml --disable-perl --disable-ruby \
                --without-readline \
                || exit 1
        fi

        rm -rf "$pywrap"

        # Full tree must build before python/ (otherwise ../lib/libhivex.la is missing).
        njobs="$(nproc 2>/dev/null || echo 4)"
        if ! run make -j"$njobs"; then
            warn "hivex: parallel make failed — retrying single-threaded (see errors above)"
            run make clean 2>/dev/null || true
            run make || exit 1
        fi

        if [ ! -f lib/libhivex.la ]; then
            warn "hivex: lib/libhivex.la missing after make — cannot build Python module"
            exit 1
        fi

        run make -C python install || exit 1
    )
    local rc=$?
    rm -rf "$build_dir"
    return "$rc"
}

install_hivex() {
    step "Installing python-hivex + hivex CLI + bsdtar (Windows registry + VirtIO ISO)"

    local active_py
    active_py="$(resolve_hivex_target_python)"
    info "hivex: target interpreter → $active_py ($("$active_py" --version 2>&1))"

    hivex_try_install_distro_pkgs "$active_py"

    if "$active_py" -c "import hivex" 2>/dev/null; then
        info "hivex: Python bindings OK ($active_py)"
        command -v hivexget &>/dev/null || warn "hivexget not in PATH — install hivex (RPM) or libhivex-bin (deb)"
        return 0
    fi

    warn "hivex: no pre-built bindings for $active_py — compiling from source (may take a minute)"
    if hivex_build_from_source "$active_py"; then
        if "$active_py" -c "import hivex" 2>/dev/null; then
            info "hivex: built and import OK ($active_py)"
            return 0
        fi
    fi

    warn "hivex: still not importable for $active_py — set H2KVM_PYTHON to match pip/h2kvmctl, or install python\$(X).\$(Y)-hivex for that interpreter"
}

# ── boto3 (AWS EC2 provider) ──
install_boto3() {
    if python3 -c "import boto3" 2>/dev/null; then
        info "boto3 already installed"
        return
    fi

    step "Installing boto3 (AWS EC2 provider)"
    pip_install boto3 || warn "boto3 install failed — AWS EC2 provider will not be available"
    info "boto3 installed"
}

# ── VirtIO Windows drivers ──
install_virtio_win() {
    step "Installing VirtIO Windows drivers"

    local iso="/var/lib/h2kvm/virtio-win.iso"
    local cache="/var/lib/h2kvm/virtio-win-extracted"
    local url="$H2KVM_VIRTIO_WIN_ISO_URL"

    if [ -f "$iso" ]; then
        info "virtio-win.iso: $iso"
    else
        mkdir -p /var/lib/h2kvm
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
        info "Pre-extracting VirtIO ISO (one-time, cached for all future runs)..."
        rm -rf "$cache"
        mkdir -p "$cache"
        bsdtar xf "$iso" -C "$cache" 2>/dev/null || true
        if [ -d "$cache/viostor" ]; then
            stat -c %Y "$iso" > "$cache/.iso_mtime"
            info "VirtIO ISO extracted: $cache"
        else
            warn "bsdtar extraction incomplete — h2kvm will extract on first Windows migration"
        fi
    fi
}

# ── Verify all ──
verify_all() {
    echo ""
    step "Verification"
    local ok=0 fail=0 opt=0

    # Required tools
    for tool in h2kvmctl qemu-img qemu-nbd virsh govc; do
        if command -v "$tool" &>/dev/null; then
            info "$tool: $(command -v "$tool")"
            ok=$((ok + 1))
        else
            error "$tool: NOT FOUND"
            fail=$((fail + 1))
        fi
    done

    # Optional tools
    for tool in guestfish virt-filesystems ovftool virt-install kubectl; do
        if command -v "$tool" &>/dev/null; then
            info "$tool: $(command -v "$tool")"
            ok=$((ok + 1))
        else
            warn "$tool: not installed (optional)"
            opt=$((opt + 1))
        fi
    done

    # pyvmomi
    if python3 -c "import pyVmomi" 2>/dev/null; then
        info "pyvmomi: OK"
        ok=$((ok + 1))
    else
        warn "pyvmomi: not installed (optional)"
        opt=$((opt + 1))
    fi

    # OVMF
    local ovmf_path=""
    for p in /usr/share/OVMF/OVMF_CODE.fd \
             /usr/share/edk2/ovmf/OVMF_CODE.fd \
             /usr/share/qemu/ovmf-x86_64-code.bin; do
        [ -f "$p" ] && ovmf_path="$p" && break
    done
    if [ -n "$ovmf_path" ]; then
        info "OVMF: $ovmf_path"
        ok=$((ok + 1))
    else
        warn "OVMF: not found"
        fail=$((fail + 1))
    fi

    # VirtIO Windows drivers
    if [ -f /var/lib/h2kvm/virtio-win.iso ]; then
        info "virtio-win: /var/lib/h2kvm/virtio-win.iso"; ok=$((ok + 1))
    else
        warn "virtio-win: not found (install with --virtio-win)"; opt=$((opt + 1))
    fi

    # nbd module
    if lsmod | grep -q "^nbd " || [ -e /dev/nbd0 ]; then
        info "nbd module: loaded"
        ok=$((ok + 1))
    else
        warn "nbd module: not loaded (run: sudo modprobe nbd)"
        fail=$((fail + 1))
    fi

    # KVM
    if [ -e /dev/kvm ]; then
        info "/dev/kvm: available"
        ok=$((ok + 1))
    else
        warn "/dev/kvm: not available (emulation only)"
    fi

    echo ""
    info "$ok components ready, $fail missing, $opt optional skipped ($(elapsed))"
}

# ── Main ──
main() {
    if [ "$(id -u)" -ne 0 ] && [ "${1:-}" != "--pyvmomi" ] && [ "${1:-}" != "--verify" ]; then
        error "Run as root: sudo $0 $*"
        exit 1
    fi

    # Setup logging (only for full installs)
    if [ $# -eq 0 ] || [ "${1:-}" = "--all" ]; then
        setup_logging
    fi

    if [ "$DRY_RUN" = "true" ]; then
        warn "DRY RUN — no changes will be made"
    fi

    detect_distro
    pip_setup

    if [ $# -eq 0 ] || [ "${1:-}" = "--all" ]; then
        echo ""
        echo "h2kvm Dependency Installer"
        info "Installer bundle: ${H2KVM_INSTALL_BUNDLE_ID}"
        echo ""
        install_python
        install_qemu
        install_guestfs
        install_libvirt
        install_ovmf
        install_govc
        install_pyvmomi
        install_ovftool
        install_hivex
        install_boto3
        install_h2kvm
        install_virtio_win
        verify_all
        return
    fi

    for arg in "$@"; do
        case "$arg" in
            --python)    install_python ;;
            --govc)      install_govc ;;
            --ovftool)   install_ovftool ;;
            --pyvmomi)   install_pyvmomi ;;
            --qemu)      install_qemu ;;
            --guestfs)   install_guestfs ;;
            --libvirt)   install_libvirt ;;
            --ovmf)      install_ovmf ;;
            --mkosi)     install_mkosi ;;
            --hivex)     install_hivex ;;
            --boto3)     install_boto3 ;;
            --h2kvm)   install_h2kvm ;;
            --virtio-win)  install_virtio_win ;;
            --verify)      verify_all ;;
            --all)         ;; # handled above
            --help|-h)
                echo "Usage: sudo $0 [--all|--verify|--govc|--qemu|--libvirt|...]"
                echo ""
                echo "Flags: --python --govc --ovftool --pyvmomi --qemu --hivex --boto3"
                echo "       --guestfs --libvirt --ovmf --mkosi --h2kvm --virtio-win --verify"
                echo ""
                echo "Env:   DRY_RUN=true  LOG_FILE=/path/to/log"
                echo "       H2KVM_INSTALL_BUNDLE_ID  H2KVM_GOVC_DOWNLOAD_PREFIX  H2KVM_VIRTIO_WIN_ISO_URL"
                echo "       H2KVM_PYTHON=/usr/bin/python3.12  (hivex bindings must match h2kvmctl interpreter)"
                exit 0
                ;;
            *)           error "Unknown option: $arg (try --help)"; exit 1 ;;
        esac
    done
}

main "$@"
