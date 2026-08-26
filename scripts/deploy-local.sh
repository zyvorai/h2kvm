#!/bin/bash
# ============================================================================
# deploy-local.sh — Build and deploy h2kvm on this machine
# ============================================================================
# One command to build + install + restart locally:
#   1. pip install h2kvm from source
#   2. Build h2kweb web dashboard (Go + React)
#   3. Install systemd services + config
#   4. Verify installation
#
# Usage:
#   ./scripts/deploy-local.sh              # full install (system deps + h2kvm)
#   ./scripts/deploy-local.sh --quick      # pip install + services only
#   ./scripts/deploy-local.sh --uninstall  # remove h2kvm
#
# Requires: sudo privileges, Python >= 3.10
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/deploy-common.sh
source "$SCRIPT_DIR/lib/deploy-common.sh"

info()  { deploy_ui_info "$@"; }
warn()  { deploy_ui_warn "$@"; }
error() { deploy_ui_error "$@"; }
step()  { deploy_ui_step_start "$*"; }

SUDO=""
[ "$(id -u)" -ne 0 ] && SUDO="sudo"

# ── Parse args ──
QUICK_MODE=false
UNINSTALL_MODE=false
for arg in "$@"; do
    case "$arg" in
        --quick)     QUICK_MODE=true ;;
        --uninstall) UNINSTALL_MODE=true ;;
        --help|-h)
            echo "Usage: $0 [--quick|--uninstall]"
            echo ""
            echo "  --quick      Skip system deps (pip install + services only)"
            echo "  --uninstall  Remove h2kvm from this machine"
            exit 0
            ;;
    esac
done

[ -f "$REPO_DIR/pyproject.toml" ] || error "Not in h2kvm repo: $REPO_DIR"
h2kvm_build_metadata "$REPO_DIR"

# ── Find Python >= 3.10 ──
PYTHON=""
for py in python3.12 python3.11 python3.10 python3; do
    if command -v "$py" &>/dev/null; then
        ver=$($py -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$py"
            break
        fi
    fi
done
[ -z "$PYTHON" ] && error "No Python >= 3.10 found. Install python3.12+"

# ── Uninstall mode ──
if $UNINSTALL_MODE; then
    deploy_ui_uninstall_banner
    deploy_ui_kv "📂" "Repo" "$REPO_DIR"
    echo ""

    step "Uninstalling h2kvm"
    $SUDO systemctl stop h2kvm.service 2>/dev/null || true
    $SUDO systemctl stop h2kweb.service 2>/dev/null || true
    $SUDO systemctl disable h2kvm.service h2kweb.service 2>/dev/null || true
    $SUDO rm -f /etc/systemd/system/h2kvm.service /etc/systemd/system/h2kweb.service

    $SUDO $PYTHON -m pip uninstall h2kvm -y 2>/dev/null || true
    $SUDO rm -f /usr/local/bin/h2kvmctl /usr/local/bin/h2kweb 2>/dev/null || true
    $SUDO rm -rf /usr/local/share/h2kweb/dashboard 2>/dev/null || true
    $SUDO rm -rf /var/lib/h2kvm/conversions /var/lib/h2kvm/virtio-win-extracted 2>/dev/null || true
    $SUDO rm -rf /var/cache/h2kvm ~/.cache/h2kvm 2>/dev/null || true
    $SUDO systemctl daemon-reload

    info "h2kvm removed"
    echo ""
    echo "  📁 Kept: /etc/h2kvm/daemon.yaml"
    echo "  📁 Kept: /var/lib/h2kvm/virtio-win.iso"
    echo "  📁 Kept: /var/lib/h2kvm/output"
    echo ""
    exit 0
fi

TOTAL_STEPS=6
$QUICK_MODE && TOTAL_STEPS=4
CURRENT_STEP=0

deploy_ui_banner "Local Deploy" "${H2KVM_VERSION} (${H2KVM_COMMIT})" "🔄"
deploy_ui_kv "📂" "Repo" "$REPO_DIR"
deploy_ui_kv "🐍" "Python" "$PYTHON ($($PYTHON --version 2>&1))"
deploy_ui_kv "⚡" "Mode" "$($QUICK_MODE && echo 'quick' || echo 'full')"
echo ""

# ── System deps (full mode only) ──
if ! $QUICK_MODE; then
    CURRENT_STEP=$((CURRENT_STEP + 1))
    step "Step ${CURRENT_STEP}/${TOTAL_STEPS}: 📦 Installing system dependencies"

    if command -v dnf &>/dev/null; then
        PKG="$SUDO dnf -y install"
    elif command -v yum &>/dev/null; then
        PKG="$SUDO yum -y install"
    elif command -v apt-get &>/dev/null; then
        $SUDO apt-get update -qq
        PKG="$SUDO apt-get -y install"
    else
        warn "No package manager found — skipping"
        PKG="true"
    fi

    $PKG qemu-kvm qemu-img libvirt virt-install 2>&1 | tail -3
    $PKG libguestfs-tools 2>&1 | tail -1 || true
    # Full supermin appliance stack for LVM/LUKS (guestfs backend auto-switch)
    if command -v dnf &>/dev/null || command -v yum &>/dev/null; then
        $PKG libguestfs supermin python3-libguestfs 2>&1 | tail -2 || true
    elif command -v apt-get &>/dev/null; then
        $PKG supermin python3-guestfs 2>&1 | tail -2 || true
    fi
    $PKG libguestfs-winsupport 2>&1 | tail -1 || true
    $PKG edk2-ovmf 2>&1 | tail -1 || $PKG ovmf 2>&1 | tail -1 || true
    $PKG python3-hivex augeas-libs augeas 2>&1 | tail -1 || true
    # Windows disk offline fixes need NTFS userspace (mount types ntfs / ntfs-3g) + ntfsfix.
    if command -v dnf &>/dev/null || command -v yum &>/dev/null; then
        $PKG ntfs-3g ntfsprogs 2>&1 | tail -2 || true
    elif command -v apt-get &>/dev/null; then
        $PKG ntfs-3g 2>&1 | tail -1 || true
    fi

    $SUDO systemctl enable libvirtd 2>/dev/null || true
    $SUDO systemctl start libvirtd 2>/dev/null || true
    $SUDO modprobe kvm 2>/dev/null || true
    $SUDO modprobe kvm_intel 2>/dev/null || $SUDO modprobe kvm_amd 2>/dev/null || true
    $SUDO modprobe nbd max_part=16 2>/dev/null || true

    info "System dependencies installed"

    CURRENT_STEP=$((CURRENT_STEP + 1))
    step "Step ${CURRENT_STEP}/${TOTAL_STEPS}: 🔌 Installing extras (hivex, boto3, virtio-win)"

    if [ -f "$REPO_DIR/scripts/install-deps.sh" ]; then
        $SUDO env H2KVM_PYTHON="$PYTHON" bash "$REPO_DIR/scripts/install-deps.sh" --hivex --boto3 --virtio-win 2>&1 | tail -5
    fi
    $SUDO $PYTHON -m pip install python-augeas 2>&1 | tail -1
    info "Extras installed"
fi

# ── Ensure libvirtd is active (covers --quick when deps were skipped) ──
CURRENT_STEP=$((CURRENT_STEP + 1))
step "Step ${CURRENT_STEP}/${TOTAL_STEPS}: 🖥️  Ensuring libvirtd is active"
$SUDO systemctl daemon-reload 2>/dev/null || true
$SUDO systemctl enable libvirtd 2>/dev/null || true
$SUDO systemctl reset-failed libvirtd 2>/dev/null || true
$SUDO systemctl start libvirtd 2>/dev/null || true
if systemctl list-unit-files 2>/dev/null | grep -q '^libvirtd.socket'; then
    $SUDO systemctl enable --now libvirtd.socket 2>/dev/null || true
fi
_lv=30
while [ "$_lv" -gt 0 ]; do
    $SUDO systemctl is-active libvirtd &>/dev/null && break
    sleep 1
    _lv=$((_lv - 1))
done
if ! $SUDO systemctl is-active libvirtd &>/dev/null; then
    $SUDO systemctl restart libvirtd 2>/dev/null || true
    sleep 2
    _lv=15
    while [ "$_lv" -gt 0 ]; do
        $SUDO systemctl is-active libvirtd &>/dev/null && break
        sleep 1
        _lv=$((_lv - 1))
    done
fi
if $SUDO systemctl is-active libvirtd &>/dev/null; then
    info "libvirtd: active"
else
    warn "libvirtd still inactive — check: systemctl status libvirtd; journalctl -u libvirtd -b"
fi

# ── pip install h2kvm ──
CURRENT_STEP=$((CURRENT_STEP + 1))
step "Step ${CURRENT_STEP}/${TOTAL_STEPS}: 🐍 Installing h2kvm from source"

cd "$REPO_DIR"
# Uninstall old version (may be RPM-managed, ignore errors)
set +e
$SUDO $PYTHON -m pip uninstall h2kvm -y &>/dev/null
set -e
rm -rf build/ dist/ *.egg-info 2>/dev/null || true

# Optional disk introspection — full deploy installs this; --quick does not.
if ! PATH="${PATH:+$PATH:}/usr/sbin:/sbin" command -v virt-filesystems &>/dev/null \
    && ! [ -x /usr/bin/virt-filesystems ] && ! [ -x /usr/sbin/virt-filesystems ]; then
    info "Installing libguestfs-tools (provides virt-filesystems)..."
    if command -v dnf &>/dev/null; then
        $SUDO dnf install -y libguestfs-tools 2>&1 | tail -3 || true
    elif command -v yum &>/dev/null; then
        $SUDO yum install -y libguestfs-tools 2>&1 | tail -3 || true
    elif command -v apt-get &>/dev/null; then
        $SUDO apt-get update -qq && $SUDO apt-get install -y -qq libguestfs-tools 2>&1 | tail -3 || true
    elif command -v zypper &>/dev/null; then
        $SUDO zypper install -y libguestfs-tools 2>&1 | tail -3 || true
    fi
fi

# Install h2kvm
set +e
INSTALL_OUT=$($SUDO $PYTHON -m pip install --no-cache-dir --break-system-packages . 2>&1)
if [ $? -ne 0 ]; then
    INSTALL_OUT=$($PYTHON -m pip install --no-cache-dir . 2>&1)
fi
set -e
echo "$INSTALL_OUT" | tail -3

# Ensure h2kvmctl is at /usr/local/bin
H2K_ACTUAL=$(which h2kvmctl 2>/dev/null || find ~/.local/bin /usr/bin -name h2kvmctl -type f 2>/dev/null | head -1)
if [ -n "$H2K_ACTUAL" ] && [ "$H2K_ACTUAL" != "/usr/local/bin/h2kvmctl" ]; then
    $SUDO cp "$H2K_ACTUAL" /usr/local/bin/h2kvmctl
    $SUDO chmod 755 /usr/local/bin/h2kvmctl
    info "h2kvmctl installed to /usr/local/bin"
elif [ -f "/usr/local/bin/h2kvmctl" ]; then
    info "h2kvmctl already at /usr/local/bin"
else
    warn "h2kvmctl not found after install"
fi

# python-hivex must match this interpreter (covers --quick when install-deps was skipped).
if ! $PYTHON -c 'import hivex' 2>/dev/null && [ -f "$REPO_DIR/scripts/install-deps.sh" ]; then
    info "Installing hivex bindings for $PYTHON..."
    $SUDO env H2KVM_PYTHON="$PYTHON" bash "$REPO_DIR/scripts/install-deps.sh" --hivex 2>&1 | tail -12 || true
fi
$PYTHON -c 'import hivex; print("  ✅ hivex: OK")' 2>/dev/null || warn "hivex: not importable — offline Windows registry steps may fail"

# Runtime dirs
$SUDO mkdir -p /run/h2kvm
if [ -f "$REPO_DIR/etc/tmpfiles.d/h2kvm.conf" ]; then
    $SUDO cp "$REPO_DIR/etc/tmpfiles.d/h2kvm.conf" /etc/tmpfiles.d/h2kvm.conf
    $SUDO systemd-tmpfiles --create /etc/tmpfiles.d/h2kvm.conf 2>/dev/null || true
fi

# Libguestfs linking
if ! $PYTHON -c 'import guestfs' 2>/dev/null; then
    TARGET_SITE=$($PYTHON -c 'import site; print(site.getsitepackages()[0])' 2>/dev/null)
    for search_dir in /usr/lib64/python*/site-packages /usr/lib/python*/site-packages /usr/local/lib*/python*/site-packages; do
        [ -f "$search_dir/guestfs.py" ] && $SUDO ln -sf "$search_dir/guestfs.py" "$TARGET_SITE/guestfs.py" 2>/dev/null || true
        for so in "$search_dir"/libguestfsmod*.so; do
            [ -f "$so" ] && $SUDO ln -sf "$so" "$TARGET_SITE/$(basename "$so")" 2>/dev/null || true
        done
    done
fi
$PYTHON -c 'import guestfs; print("  ✅ libguestfs: OK")' 2>/dev/null || warn "libguestfs: not available"

# ── Build h2kweb ──
CURRENT_STEP=$((CURRENT_STEP + 1))
step "Step ${CURRENT_STEP}/${TOTAL_STEPS}: 🌐 Building h2kweb dashboard"

H2KWEB_BUILT=false
WEB_DIR="$REPO_DIR/web"
if [ -f "$WEB_DIR/main.go" ]; then
    cd "$WEB_DIR"

    # Build React dashboard
    if [ -f "$WEB_DIR/dashboard/package.json" ]; then
        cd "$WEB_DIR/dashboard"
        set +e
        npm install --silent 2>&1 | tail -1
        npm run build 2>&1 | tail -3
        set -e
        cd "$WEB_DIR"
        if [ -d "$WEB_DIR/dashboard/dist" ]; then
            info "React dashboard built"
        else
            warn "React dashboard build failed — continuing without it"
        fi
    fi

    # Build Go binary
    mkdir -p "$REPO_DIR/build"
    if go build -o "$REPO_DIR/build/h2kweb" . 2>&1; then
        H2KWEB_BUILT=true
        info "h2kweb binary built"
    else
        warn "h2kweb build failed"
    fi
    cd "$REPO_DIR"
else
    warn "h2kweb source not found — skipping"
fi

# ── Install services ──
CURRENT_STEP=$((CURRENT_STEP + 1))
step "Step ${CURRENT_STEP}/${TOTAL_STEPS}: ⚙️  Installing services"

# h2kvm daemon
$SUDO mkdir -p /etc/h2kvm /var/lib/h2kvm/queue /var/lib/h2kvm/output /var/log/h2kvm
$SUDO chmod 755 /var/lib/h2kvm /var/lib/h2kvm/output

if [ ! -f /etc/h2kvm/daemon.yaml ]; then
    $SUDO tee /etc/h2kvm/daemon.yaml > /dev/null << 'EOF'
cmd: daemon
watch_dir: /var/lib/h2kvm/queue
output_dir: /var/lib/h2kvm/output
flatten: true
out_format: qcow2
compress: true
fstab_mode: stabilize-all
regen_initramfs: true
remove_vmware_tools: true
emit_domain_xml: true
verbose: 1
EOF
    info "Created /etc/h2kvm/daemon.yaml"
else
    info "/etc/h2kvm/daemon.yaml already exists"
fi

$SUDO tee /etc/systemd/system/h2kvm.service > /dev/null << 'EOF'
[Unit]
Description=h2kvm VM Conversion Daemon
Documentation=https://github.com/ssahani/h2kvm
After=network.target libvirtd.service

[Service]
Type=simple
# virt-filesystems and other host tools are often in /usr/sbin
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
WorkingDirectory=/var/lib/h2kvm
RuntimeDirectory=h2kvm
RuntimeDirectoryMode=0755
ExecStart=/usr/local/bin/h2kvmctl --config /etc/h2kvm/daemon.yaml
Restart=on-failure
RestartSec=10s
TimeoutStartSec=30s
TimeoutStopSec=30s

[Install]
WantedBy=multi-user.target
EOF

$SUDO systemctl daemon-reload
$SUDO systemctl enable --now h2kvm.service 2>/dev/null || true
$SUDO systemctl restart h2kvm.service
sleep 2
if $SUDO systemctl is-active h2kvm &>/dev/null; then
    info "h2kvm daemon: running"
else
    warn "h2kvm daemon: not running (check: journalctl -u h2kvm -n 10)"
fi

# h2kweb dashboard
if $H2KWEB_BUILT && [ -f "$REPO_DIR/build/h2kweb" ]; then
    $SUDO systemctl stop h2kweb.service 2>/dev/null || true
    $SUDO install -m 755 "$REPO_DIR/build/h2kweb" /usr/local/bin/h2kweb

    # Dashboard static files
    H2KWEB_DIST="$REPO_DIR/web/dashboard/dist"
    if [ -d "$H2KWEB_DIST" ]; then
        $SUDO mkdir -p /usr/local/share/h2kweb
        $SUDO rm -rf /usr/local/share/h2kweb/dashboard
        $SUDO cp -r "$H2KWEB_DIST" /usr/local/share/h2kweb/dashboard
        info "Dashboard files deployed"
    fi

    # Service file
    if [ -f "$REPO_DIR/web/h2kweb.service" ]; then
        $SUDO install -m 644 "$REPO_DIR/web/h2kweb.service" /etc/systemd/system/h2kweb.service
        $SUDO install -m 644 "$REPO_DIR/web/h2kweb.default" /etc/default/h2kweb 2>/dev/null || true
        $SUDO sed -i 's|ExecStart=.*|ExecStart=/usr/local/bin/h2kweb --addr ${H2KWEB_ADDR} --static-dir /usr/local/share/h2kweb/dashboard --tls-cert auto|' /etc/systemd/system/h2kweb.service
    fi

    $SUDO systemctl daemon-reload
    $SUDO systemctl enable --now h2kweb.service 2>/dev/null || true
    $SUDO systemctl restart h2kweb.service
    sleep 1
    if $SUDO systemctl is-active h2kweb &>/dev/null; then
        info "h2kweb: running on port 5070"
    else
        warn "h2kweb: not running (check: journalctl -u h2kweb -n 10)"
    fi
fi

# ── Verify ──
echo ""
echo "  ── Tools ──"
H2KVMCTL=$(which h2kvmctl 2>/dev/null || echo 'NOT FOUND')
echo "  📍 h2kvmctl: $H2KVMCTL"
echo "  📍 version:  $(h2kvmctl --version 2>/dev/null || echo 'N/A')"

# Minimal shells omit /usr/sbin — virt-filesystems (libguestfs-tools) may live there.
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH}"
if ! command -v virt-filesystems &>/dev/null && ! [ -x /usr/bin/virt-filesystems ] && ! [ -x /usr/sbin/virt-filesystems ]; then
    info "Verify: installing libguestfs-tools (virt-filesystems missing)..."
    if command -v dnf &>/dev/null; then
        $SUDO dnf install -y libguestfs-tools 2>&1 | tail -5 || true
    elif command -v yum &>/dev/null; then
        $SUDO yum install -y libguestfs-tools 2>&1 | tail -5 || true
    elif command -v apt-get &>/dev/null; then
        $SUDO apt-get update -qq && $SUDO apt-get install -y -qq libguestfs-tools 2>&1 | tail -5 || true
    elif command -v zypper &>/dev/null; then
        $SUDO zypper install -y libguestfs-tools 2>&1 | tail -5 || true
    fi
fi

for tool in qemu-img qemu-nbd virsh virt-install virt-filesystems supermin; do
    if command -v "$tool" &>/dev/null; then
        echo "  📍 $tool: $(command -v "$tool")"
    elif [ "$tool" = virt-filesystems ] && { [ -x /usr/bin/virt-filesystems ] || [ -x /usr/sbin/virt-filesystems ]; }; then
        echo "  📍 $tool: $([ -x /usr/bin/virt-filesystems ] && echo /usr/bin/virt-filesystems || echo /usr/sbin/virt-filesystems)"
    else
        echo "  ⚠️  $tool: not found"
    fi
done

echo ""
echo "  ── Modules ──"
$PYTHON -c 'from h2kvm.providers.aws_ec2 import AWSConfig; print("  📍 AWS provider: OK")' 2>/dev/null || echo "  ⚠️  AWS provider: not available"
$PYTHON -c 'from h2kvm.providers.azure import AzureConfig; print("  📍 Azure provider: OK")' 2>/dev/null || echo "  ⚠️  Azure provider: not available"
$PYTHON -c 'from h2kvm.vmcraft.main import VMCraft; print("  📍 VMCraft: OK")' 2>/dev/null || echo "  ⚠️  VMCraft: not available"
$PYTHON -c 'import hivex; print("  📍 python-hivex: OK")' 2>/dev/null || echo "  ⚠️  python-hivex: not installed"
$PYTHON -c 'import boto3; print("  📍 boto3: OK")' 2>/dev/null || echo "  ⚠️  boto3: not installed"

echo ""
echo "  ── Services ──"
for svc in h2kvm h2kweb libvirtd; do
    if systemctl is-active "$svc" &>/dev/null; then
        echo "  📍 $svc: running"
    else
        echo "  ⚠️  $svc: not running"
    fi
done

echo ""
echo "  ── Storage ──"
[ -f /var/lib/h2kvm/virtio-win.iso ] && echo "  📍 virtio-win.iso: OK" || echo "  ⚠️  virtio-win.iso: not found"

h2kvm_print_success "localhost" "0"
deploy_ui_note "🚀 h2kvmctl --config migration.yaml"
deploy_ui_note "📋 journalctl -u h2kvm -f"
echo ""
