#!/bin/bash
# ============================================================================
# deploy-remote.sh — Full h2kvm deployment to a remote server
# ============================================================================
# AlmaLinux 9 and CentOS Stream 9 use the same DNF/AppStream layout (CRB, Python 3.12,
# Node 20, firewall). On EL9 (RHEL/Alma/Rocky/CentOS Stream 9), virt-filesystems is in the
# guestfs-tools RPM — same package name across that family (not a different name on CS9).
#
# Debian/Ubuntu: use libguestfs-tools (provides virt-filesystems there).
#
# One command to fully set up a remote server for VM migrations:
#   1. Rsync repo to remote
#   2. Run quickstart.sh (system packages, libvirt, KVM, OVMF, govc, etc)
#   3. Run install-deps.sh (hivex, bsdtar, boto3, virtio-win ISO)
#   4. pip install h2kvm from source
#   5. Build h2kweb dashboard locally (npm), compile Go on remote (linux/PAM), start service
#   6. Verify everything works
#
# Usage:
#   ./scripts/deploy-remote.sh <host> [user] [password]
#   ./scripts/deploy-remote.sh 185.165.240.5 sus                  # AlmaLinux 9 / CentOS Stream 9 (SSH key)
#   ./scripts/deploy-remote.sh 10.0.0.50 sus                      # Ubuntu 22.04/24.04 Server
#   ./scripts/deploy-remote.sh 185.165.240.194 sus mypassword
#   ./scripts/deploy-remote.sh 10.0.0.1 root                  # SSH key auth
#   ./scripts/deploy-remote.sh 10.0.0.1 root pass --quick     # skip quickstart
#   ./scripts/deploy-remote.sh 10.0.0.1 root pass --uninstall # remove h2kvm
#
# Environment variables:
#   DEPLOY_HOST=185.165.240.194
#   DEPLOY_USER=root
#   DEPLOY_PASS=mypassword
#   DEPLOY_DIR=/home/user/.deployments  (auto-detected from login user)
#
# Remote install-deps uses H2KVM_PYTHON (same interpreter as pip/h2kvmctl), set automatically.
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/deploy-common.sh
source "$SCRIPT_DIR/lib/deploy-common.sh"

info()  { deploy_ui_info "$@"; }
warn()  { deploy_ui_warn "$@"; }
error() { deploy_ui_error "$@"; }
step()  {
    LAST_ACTION="$*"
    deploy_ui_step_start "$*"
}
finish_last_step_timer() { deploy_ui_step_finish; }

# ── Parse args ──
QUICK_MODE=false
UNINSTALL_MODE=false
KEEP_SOURCES=false
VERBOSE=false
DRY_RUN=false
SKIP_DASHBOARD=false
SKIP_SMOKE=false
POSITIONAL=()
for arg in "$@"; do
    case "$arg" in
        --quick)          QUICK_MODE=true ;;
        --uninstall)      UNINSTALL_MODE=true ;;
        --keep-sources)   KEEP_SOURCES=true ;;
        --verbose)        VERBOSE=true ;;
        --dry-run)        DRY_RUN=true ;;
        --skip-dashboard) SKIP_DASHBOARD=true ;;
        --skip-smoke)     SKIP_SMOKE=true ;;
        --help|-h)
            echo "Usage: $0 <host> [user] [password] [options]"
            echo "       $0 sus@host [--quick]  |  ./scripts/deploy remote --quick"
            echo ""
            echo "  --quick      Skip quickstart.sh (only rsync + pip install)"
            echo "  --uninstall  Remove h2kvm from remote server"
            echo "  --keep-sources  Keep remote checkout in ~/.deployments/h2kvm"
            echo "  --verbose    Show full logs (skip highlights-only output)"
            echo ""
            echo "Full mode installs everything: Python, qemu, libvirt, KVM,"
            echo "OVMF, govc, hivex, bsdtar, boto3, virtio-win, h2kvm."
            exit 0
            ;;
        *)  POSITIONAL+=("$arg") ;;
    esac
done

HOST="${POSITIONAL[0]:-${DEPLOY_HOST:-}}"
USER="${POSITIONAL[1]:-${DEPLOY_USER:-root}}"
PASS="${POSITIONAL[2]:-${DEPLOY_PASS:-}}"

h2kvm_parse_target HOST USER
if [ -z "$HOST" ] && h2kvm_load_deploy_last "$REPO_DIR"; then
    info "Using .deploy-last → ${USER}@${HOST}"
fi

[ -z "$HOST" ] && error "Usage: $0 <host> [user] [password]  or  $0 --quick"

START_TS=$(date +%s)
LOG_FILE="/tmp/h2kvm-deploy-${HOST}-$(date +%Y%m%d-%H%M%S).log"
LAST_ACTION="initialization"
CURRENT_STEP_TITLE=""
CURRENT_STEP_TS=0

on_error() {
    local rc="$1"
    local line="$2"
    echo ""
    echo "  ❌ Deployment failed (exit ${rc})"
    echo "  📍 Last action: ${LAST_ACTION}"
    echo "  📍 Script line: ${line}"
    if [ -f "$LOG_FILE" ]; then
        echo "  📄 Log: $LOG_FILE"
        echo "  ── Last 40 log lines ──"
        tail -n 40 "$LOG_FILE" || true
    fi
    exit "$rc"
}
trap 'on_error $? $LINENO' ERR
exec > >(tee -a "$LOG_FILE") 2>&1

# Determine remote home directory based on login user (not hardcoded /root)
if [ "$USER" = "root" ]; then
    REMOTE_HOME="/root"
else
    REMOTE_HOME="/home/${USER}"
fi
REMOTE_DIR="${DEPLOY_DIR:-${REMOTE_HOME}/.deployments/h2kvm}"
# h2kweb listen port (see web/h2kweb.default H2KWEB_ADDR)
H2KWEB_PORT=5070

# Use sudo when not deploying as root
SUDO=""
[ "$USER" != "root" ] && SUDO="sudo"

[ -f "$REPO_DIR/pyproject.toml" ] || error "Not in h2kvm repo: $REPO_DIR"
h2kvm_build_metadata "$REPO_DIR"

# SSH options for all remote commands (including long pip installs).
# ControlMaster=no avoids stale master sockets; ServerAlive* prevents NAT idle drops mid-pip.
DEPLOY_SSH_OPTS=(
    -o StrictHostKeyChecking=no
    -o ConnectTimeout=30
    -o ServerAliveInterval=15
    -o ServerAliveCountMax=120
    -o TCPKeepAlive=yes
    -o ControlMaster=no
)
DEPLOY_SSH_STREAM_OPTS=("${DEPLOY_SSH_OPTS[@]}")

# Non-root deploy may need a TTY for sudo password once; long pip runs use -T when sudo -n works.
DEPLOY_SSH_TTY_OPTS=()
[ "$USER" != "root" ] && DEPLOY_SSH_TTY_OPTS=(-tt)

# ── SSH/rsync wrappers (SSHPASS env var — no password in ps) ──
# Non-interactive SSH uses a minimal PATH; virt-filesystems lives in /usr/sbin (guestfs-tools on EL9).
_remote_path_export='export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"'

# Run remote body under bash (not the user's login shell). zsh fails on unmatched globs
# (e.g. libguestfsmod*.so) that bash treats as a literal pattern when no files match.
_remote_bash_stdin() {
    printf '%s\n%s\n' "$_remote_path_export" "$*"
}

_ssh_invoke() {
    local use_tty="$1"
    shift
    local -a ssh_args=("${DEPLOY_SSH_OPTS[@]}")
    if [ "$use_tty" = "1" ] && [ "${#DEPLOY_SSH_TTY_OPTS[@]}" -gt 0 ]; then
        ssh_args+=("${DEPLOY_SSH_TTY_OPTS[@]}")
    fi
    if [ -n "$PASS" ]; then
        _remote_bash_stdin "$@" | SSHPASS="$PASS" sshpass -e ssh "${ssh_args[@]}" "${USER}@${HOST}" "exec bash -s"
    else
        _remote_bash_stdin "$@" | ssh "${ssh_args[@]}" "${USER}@${HOST}" "exec bash -s"
    fi
}

_ssh() {
    _ssh_invoke 1 "$@"
}

# Short probes — no TTY (avoids spurious "Connection closed" between quick commands).
_ssh_batch() {
    _ssh_invoke 0 "$@"
}

_scp() {
    local -a scp_args=("${DEPLOY_SSH_OPTS[@]}")
    if [ -n "$PASS" ]; then
        SSHPASS="$PASS" sshpass -e scp "${scp_args[@]}" "$@"
    else
        scp "${scp_args[@]}" "$@"
    fi
}

_rsync() {
    local ssh_cmd="ssh ${DEPLOY_SSH_OPTS[*]}"
    if [ -n "$PASS" ]; then
        ssh_cmd="sshpass -e $ssh_cmd"
    fi
    local common_args=(
        --exclude='*.vmdk' --exclude='*.qcow2' --exclude='*.raw' \
        --exclude='*.ova' --exclude='*.iso' --exclude='*.tar.gz' \
        --exclude='*.vhd' --exclude='*.vhdx' --exclude='*.img' \
        --exclude='output*' --exclude='out/' \
        --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
        --exclude='dist/' --exclude='build/' --exclude='*.egg-info' \
        --exclude='.pytest_cache' --exclude='.ruff_cache' \
        --exclude='node_modules' \
        -e "$ssh_cmd"
    )

    # Attempt 1: compressed sync (faster over WAN).
    SSHPASS="$PASS" rsync -azv "${common_args[@]}" "$@"
    local rc=$?
    if [ "$rc" -eq 0 ]; then
        return 0
    fi
    warn "rsync attempt 1 failed (exit ${rc}); retrying with compatibility mode (no compression, whole-file)."

    # Attempt 2: compatibility mode for flaky/older rsync combinations.
    SSHPASS="$PASS" rsync -avW "${common_args[@]}" "$@"
}

# Stream remote output to the terminal (so long quickstart/install-deps runs never look "stuck"),
# then optionally print matching lines from the saved log (grep on a file avoids SIGPIPE vs `grep|head`).
# With ControlMaster=no (above), -tt is safe for non-root sudo prompts; omit for root (no sudo).
_ssh_stream_and_preview() {
    local remote_cmd="$1"
    local pattern="$2"
    local max_lines="${3:-30}"
    local use_tty="${4:-1}"
    local tmp rc
    tmp=$(mktemp) || return 1
    set +e
    if [ "$use_tty" = "1" ] && [ "${#DEPLOY_SSH_TTY_OPTS[@]}" -gt 0 ]; then
        if [ -n "$PASS" ]; then
            _remote_bash_stdin "$remote_cmd" | SSHPASS="$PASS" sshpass -e ssh "${DEPLOY_SSH_STREAM_OPTS[@]}" "${DEPLOY_SSH_TTY_OPTS[@]}" "${USER}@${HOST}" "exec bash -s" 2>&1 | tee "$tmp"
        else
            _remote_bash_stdin "$remote_cmd" | ssh "${DEPLOY_SSH_STREAM_OPTS[@]}" "${DEPLOY_SSH_TTY_OPTS[@]}" "${USER}@${HOST}" "exec bash -s" 2>&1 | tee "$tmp"
        fi
    else
        if [ -n "$PASS" ]; then
            _remote_bash_stdin "$remote_cmd" | SSHPASS="$PASS" sshpass -e ssh "${DEPLOY_SSH_STREAM_OPTS[@]}" "${USER}@${HOST}" "exec bash -s" 2>&1 | tee "$tmp"
        else
            _remote_bash_stdin "$remote_cmd" | ssh "${DEPLOY_SSH_STREAM_OPTS[@]}" "${USER}@${HOST}" "exec bash -s" 2>&1 | tee "$tmp"
        fi
    fi
    # Pipeline is: _remote_bash_stdin | ssh | tee  →  remote exit is PIPESTATUS[1]
    rc=${PIPESTATUS[1]:-${PIPESTATUS[0]}}
    set -e
    if [ "$rc" -ne 0 ]; then
        if [ -s "$tmp" ]; then
            echo ""
            echo "  ── last remote output (ssh exit ${rc}) ──"
            tail -n 40 "$tmp" || true
        fi
        rm -f "$tmp"
        return "$rc"
    fi
    if [ -n "$pattern" ] && ! $VERBOSE; then
        echo ""
        echo "  ── highlights (last ${max_lines} matching lines) ──"
        grep -E "$pattern" "$tmp" 2>/dev/null | tail -n "$max_lines" || true
    fi
    rm -f "$tmp"
    return 0
}

# Same interpreter selection as local deploy-local.sh (Python ≥ 3.10 for h2kvm).
_remote_resolve_python() {
    local out
    out=$(_ssh_batch "
        for py in python3.12 python3.11 python3.10 python3; do
            if command -v \$py &>/dev/null; then
                if \$py -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
                    echo \$py
                    exit 0
                fi
            fi
        done
        echo ''
    " 2>/dev/null | tr -d '\r')
    out="${out%%$'\n'*}"
    out="${out#"${out%%[![:space:]]*}"}"
    out="${out%"${out##*[![:space:]]}"}"
    printf '%s\n' "$out"
}

# Build the React dashboard locally; Go binary is compiled on the remote Linux host (CGO/PAM).
_ensure_h2kweb_frontend() {
    H2KWEB_DIST="$REPO_DIR/web/dashboard/dist"
    if [ -f "$H2KWEB_DIST/index.html" ]; then
        return 0
    fi
    if [ ! -f "$REPO_DIR/web/dashboard/package.json" ]; then
        warn "h2kweb dashboard sources missing under web/dashboard/"
        return 1
    fi
    if ! command -v npm &>/dev/null; then
        warn "npm required to build h2kweb dashboard locally"
        return 1
    fi

    step "Building h2kweb dashboard locally (npm)"
    (cd "$REPO_DIR/web/dashboard" && npm ci --legacy-peer-deps --silent && npm run build) || {
        warn "h2kweb dashboard build failed — run: cd web/dashboard && npm ci && npm run build"
        return 1
    }
    [ -f "$H2KWEB_DIST/index.html" ]
}

# Sync prebuilt dashboard + Go sources to remote (independent of full repo checkout).
_sync_h2kweb_artifacts() {
    local remote_web="$REMOTE_DIR/web"
    _ssh_batch "mkdir -p \"${remote_web}/dashboard/dist\" \"${remote_web}/internal\""
    deploy_ui_note "📤 h2kweb dashboard/dist → ${HOST}"
    _rsync "$REPO_DIR/web/dashboard/dist/" "${USER}@${HOST}:${remote_web}/dashboard/dist/"
    deploy_ui_note "📤 h2kweb Go sources → ${HOST}"
    _rsync \
        --exclude='dashboard/node_modules' --exclude='dashboard/src' --exclude='dashboard/e2e' \
        --exclude='dashboard/test-results' --exclude='h2kweb' \
        "$REPO_DIR/web/" "${USER}@${HOST}:${remote_web}/"
}

# ── Preflight ──
if [ -n "$PASS" ] && ! command -v sshpass &>/dev/null; then
    error "sshpass required for password auth. Install: dnf install sshpass"
fi

# ── Uninstall mode ──
if $UNINSTALL_MODE; then
    deploy_ui_uninstall_banner
    deploy_ui_kv "🎯" "Host" "${USER}@${HOST}"
    echo ""

    step "Uninstalling h2kvm"
    _ssh "
        # Uninstall pip package
        for py in python3.12 python3.11 python3.10; do
            if command -v \$py &>/dev/null; then
                $SUDO \$py -m pip uninstall h2kvm -y 2>/dev/null && break
            fi
        done
        $SUDO pip3 uninstall h2kvm -y 2>/dev/null || true

        # Remove binaries
        $SUDO rm -f /usr/local/bin/h2kvmctl /usr/local/bin/h2kvm /usr/bin/h2kvmctl /usr/bin/h2kvm 2>/dev/null || true

        # Remove repo
        rm -rf $REMOTE_DIR

        # Remove caches and data (optional — keep VirtIO ISO)
        $SUDO rm -rf /var/lib/h2kvm/conversions 2>/dev/null || true
        $SUDO rm -rf /var/lib/h2kvm/virtio-win-extracted 2>/dev/null || true
        $SUDO rm -rf /var/cache/h2kvm 2>/dev/null || true
        $SUDO rm -rf ${REMOTE_HOME}/.cache/h2kvm 2>/dev/null || true

        echo 'Done'
    " 2>&1

    info "h2kvm removed from ${HOST}"
    echo ""
    echo "  📁 Kept: /var/lib/h2kvm/virtio-win.iso (reusable)"
    echo "  📁 Kept: system packages (qemu, libvirt, etc)"
    echo ""
    exit 0
fi

TOTAL_STEPS=8
$QUICK_MODE && TOTAL_STEPS=6

deploy_ui_banner "Remote Deploy" "${H2KVM_VERSION} (${H2KVM_COMMIT}) → ${USER}@${HOST}" "🔄"
deploy_ui_kv "🎯" "Target" "${USER}@${HOST}"
deploy_ui_kv "🔐" "Auth" "$([ -n "$PASS" ] && echo 'password' || echo 'SSH key')"
deploy_ui_kv "🛡️" "Sudo" "$([ "$USER" != "root" ] && echo 'prompt when needed' || echo 'root')"
deploy_ui_kv "📂" "Local" "$REPO_DIR"
deploy_ui_kv "📁" "Remote" "$REMOTE_DIR"
deploy_ui_kv "🌐" "h2kweb" "port ${H2KWEB_PORT}"
deploy_ui_kv "⚡" "Mode" "$($QUICK_MODE && echo 'quick' || echo 'full')"
deploy_ui_kv "📄" "Log" "$LOG_FILE"
echo ""

if $DRY_RUN; then
    deploy_ui_dry_run "$HOST" "$USER" "$REMOTE_DIR" "$QUICK_MODE"
    exit 0
fi

# ── Step 1: Rsync repo ──
step "Step 1/${TOTAL_STEPS}: Syncing repository to ${HOST}"

# Ensure parent exists because rsync won't create missing intermediate dirs.
_ssh_batch "mkdir -p \"$(dirname "$REMOTE_DIR")\""
deploy_ui_note "📤 Rsync → ${HOST}:${REMOTE_DIR} (WAN first run may take a few minutes)"
_rsync "$REPO_DIR/" "${USER}@${HOST}:${REMOTE_DIR}/"
info "Synced to ${HOST}:${REMOTE_DIR}"

# Long pip installs are more stable without a forced PTY when sudo does not need a password.
if [ "$USER" != "root" ]; then
    if _ssh_batch "$SUDO -n true" 2>/dev/null; then
        DEPLOY_SSH_TTY_OPTS=()
        info "Passwordless sudo — using non-TTY SSH for long installs"
    fi
fi

# ── Step 2: Auto-detect container/orchestration runtime ──
step "Step 2/${TOTAL_STEPS}: 🔍 Detecting container runtime on ${HOST}"

REMOTE_RUNTIME=$(_ssh_batch "
    runtimes=''

    # Kubernetes distributions
    if command -v k3s &>/dev/null || systemctl is-active k3s &>/dev/null 2>&1; then
        ver=\$(k3s --version 2>/dev/null | head -1 || echo 'unknown')
        runtimes=\"\${runtimes}k3s:\${ver}\n\"
    fi
    if command -v kubeadm &>/dev/null || systemctl is-active kubelet &>/dev/null 2>&1; then
        ver=\$(kubectl version --client --short 2>/dev/null | head -1 || echo 'unknown')
        runtimes=\"\${runtimes}k8s:\${ver}\n\"
    elif command -v kubectl &>/dev/null; then
        ver=\$(kubectl version --client --short 2>/dev/null | head -1 || echo 'unknown')
        runtimes=\"\${runtimes}kubectl:\${ver}\n\"
    fi
    if command -v oc &>/dev/null; then
        ver=\$(oc version --client 2>/dev/null | head -1 || echo 'unknown')
        runtimes=\"\${runtimes}openshift:\${ver}\n\"
    fi

    # Container runtimes
    if command -v docker &>/dev/null; then
        ver=\$(docker --version 2>/dev/null || echo 'unknown')
        runtimes=\"\${runtimes}docker:\${ver}\n\"
    fi
    if command -v podman &>/dev/null; then
        ver=\$(podman --version 2>/dev/null || echo 'unknown')
        runtimes=\"\${runtimes}podman:\${ver}\n\"
    fi
    if command -v containerd &>/dev/null || systemctl is-active containerd &>/dev/null 2>&1; then
        ver=\$(containerd --version 2>/dev/null | head -1 || echo 'unknown')
        runtimes=\"\${runtimes}containerd:\${ver}\n\"
    fi
    if command -v crio &>/dev/null || systemctl is-active crio &>/dev/null 2>&1; then
        ver=\$(crio --version 2>/dev/null | head -1 || echo 'unknown')
        runtimes=\"\${runtimes}cri-o:\${ver}\n\"
    fi

    # Virtualization
    if command -v virsh &>/dev/null; then
        ver=\$(virsh --version 2>/dev/null || echo 'unknown')
        runtimes=\"\${runtimes}libvirt:\${ver}\n\"
    fi

    if [ -z \"\$runtimes\" ]; then
        echo 'none'
    else
        printf \"\$runtimes\"
    fi
" 2>/dev/null | tr -d '\r')

# Strip CRLF/whitespace so we match 'none' reliably (SSH/API quirks).
RUNTIME_FIRST="${REMOTE_RUNTIME%%$'\n'*}"
RUNTIME_FIRST="${RUNTIME_FIRST#"${RUNTIME_FIRST%%[![:space:]]*}"}"
RUNTIME_FIRST="${RUNTIME_FIRST%"${RUNTIME_FIRST##*[![:space:]]}"}"

if [ "$RUNTIME_FIRST" = "none" ]; then
    warn "No container/orchestration runtime detected — will install libvirt"
else
    echo "  Detected runtimes:"
    echo "$REMOTE_RUNTIME" | while IFS=: read -r name ver; do
        name="${name#"${name%%[![:space:]]*}"}"
        [ -n "$name" ] && echo "    📍 ${name}: ${ver}"
    done
fi

if ! $QUICK_MODE; then
    # ── Step 3: Uninstall old version ──
    step "Step 3/${TOTAL_STEPS}: 🗑️  Uninstalling old h2kvm"
    [ "$USER" != "root" ] && echo "  💬 If prompted, enter your sudo password for the remote user ($USER)."

    # Do not pipe this ssh through grep: line-buffering can hide the sudo prompt until newline.
    _ssh "
        # Find the right pip for Python >= 3.10
        for py in python3.12 python3.11 python3.10; do
            if command -v \$py &>/dev/null; then
                $SUDO \$py -m pip uninstall h2kvm -y 2>/dev/null || true
                break
            fi
        done
        $SUDO pip3 uninstall h2kvm -y 2>/dev/null || true
        $SUDO rm -f /usr/local/bin/h2kvmctl /usr/local/bin/h2kvm 2>/dev/null || true
    " 2>&1
    info "Old version removed"

    # ── Step 4: Run quickstart.sh (system packages, services, kernel modules) ──
    step "Step 4/${TOTAL_STEPS}: 📦 Running quickstart.sh (system deps, libvirt, KVM, OVMF, govc)"

    _ssh_stream_and_preview "
        cd $REMOTE_DIR
        $SUDO env H2KVM_REMOTE_INSTALL=1 bash scripts/quickstart.sh
    " '^\[|Step|installed|enabled|loaded|govc' 30
    info "System dependencies installed"

    REMOTE_PY="$(_remote_resolve_python)"
    [ -z "$REMOTE_PY" ] && error "No Python >= 3.10 on remote after quickstart. Install e.g. python3.12 + pip."
    info "Target Python for hivex + pip: $REMOTE_PY"

    # ── Step 5: Run install-deps.sh extras (hivex, bsdtar, boto3, virtio-win, augeas) ──
    step "Step 5/${TOTAL_STEPS}: 🔌 Installing extras (hivex, bsdtar, boto3, virtio-win, augeas)"

    _ssh_stream_and_preview "
        cd $REMOTE_DIR
        $SUDO env H2KVM_REMOTE_INSTALL=1 H2KVM_PYTHON=$REMOTE_PY bash scripts/install-deps.sh --hivex --boto3 --virtio-win
        if command -v dnf &>/dev/null; then
            $SUDO dnf install -y augeas-libs augeas 2>&1 | tail -1
        elif command -v apt-get &>/dev/null; then
            $SUDO apt-get install -y -qq augeas-tools 2>&1 | tail -1 || true
        fi
    " '^\[|installed|virtio|hivex|boto3|bsdtar|extracted' 15
    info "Extras installed"

    # ── Step 6: pip install h2kvm ──
    step "Step 6/${TOTAL_STEPS}: 🐍 Installing h2kvm from source"
else
    # Quick mode: just uninstall + install
    step "Step 3/${TOTAL_STEPS}: 🗑️  Uninstalling old h2kvm"
    [ "$USER" != "root" ] && echo "  💬 If prompted, enter your sudo password for the remote user ($USER)."

    _ssh "
        for py in python3.12 python3.11 python3.10; do
            if command -v \$py &>/dev/null; then
                $SUDO \$py -m pip uninstall h2kvm -y 2>/dev/null || true
                break
            fi
        done
        $SUDO rm -f /usr/local/bin/h2kvmctl /usr/local/bin/h2kvm 2>/dev/null || true
    " 2>&1
    info "Old version removed"

    step "Step 4/${TOTAL_STEPS}: 🐍 Installing h2kvm from source"
fi

# Resolve interpreter for pip (full mode already set REMOTE_PY before install-deps).
if [ -z "${REMOTE_PY:-}" ]; then
    REMOTE_PY="$(_remote_resolve_python)"
fi

[ -z "$REMOTE_PY" ] && error "No Python >= 3.10 found on remote. Install Python 3.10+: e.g. sudo dnf install -y python3.12 python3.12-pip (Alma/RHEL/Rocky/CentOS) or sudo apt install -y python3 python3-venv python3-pip (Ubuntu 22.04+)."
info "Python: $REMOTE_PY"

_ssh_pip_tty=1
[ "${#DEPLOY_SSH_TTY_OPTS[@]}" -eq 0 ] && _ssh_pip_tty=0

set +e
_ssh_stream_and_preview "
    set -e
    cd $REMOTE_DIR
    PIP_LOG=/tmp/h2kvm-pip-install.log
    : >\"\$PIP_LOG\"
    echo \"📄 pip log: \$PIP_LOG\"

    # EL9: virt-filesystems is in guestfs-tools (with libguestfs-tools); --quick skips quickstart dnf.
    if ! PATH=\"/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:\${PATH}\" command -v virt-filesystems &>/dev/null \\
        && ! [ -x /usr/bin/virt-filesystems ] && ! [ -x /usr/sbin/virt-filesystems ]; then
        echo '📦 Installing guestfs-tools + libguestfs-tools (virt-filesystems on EL9 is in guestfs-tools)...'
        if command -v dnf &>/dev/null; then $SUDO dnf install -y guestfs-tools libguestfs-tools || true; \\
        elif command -v yum &>/dev/null; then $SUDO yum install -y guestfs-tools libguestfs-tools || true; \\
        elif command -v apt-get &>/dev/null; then $SUDO apt-get update -qq && $SUDO apt-get install -y -qq libguestfs-tools || true; \\
        elif command -v zypper &>/dev/null; then $SUDO zypper install -y guestfs-tools libguestfs-tools || $SUDO zypper install -y libguestfs-tools || true; \\
        else echo 'No dnf/yum/apt/zypper — install guestfs-tools / libguestfs-tools manually'; fi
    fi
    rm -rf build/ dist/ *.egg-info 2>/dev/null || true

    # Headers for python-augeas (optional — pip wheel may work without devel on some distros).
    if command -v dnf &>/dev/null; then
        if ! $SUDO dnf repolist --enabled 2>/dev/null | grep -qiE '^(crb|powertools)[[:space:]]'; then
            $SUDO dnf install -y \"dnf-command(config-manager)\" 2>/dev/null || true
            $SUDO dnf config-manager --set-enabled crb 2>/dev/null || $SUDO dnf config-manager --set-enabled powertools 2>/dev/null || true
            $SUDO dnf makecache -y 2>/dev/null || true
        fi
        rpm -q augeas-devel &>/dev/null || $SUDO dnf install -y augeas-devel 2>&1 || echo '⚠️  augeas-devel optional install failed (continuing)'
    elif command -v apt-get &>/dev/null; then
        dpkg -s libaugeas-dev &>/dev/null || { $SUDO apt-get update -qq && $SUDO apt-get install -y -qq libaugeas-dev; } 2>&1 || true
    fi

    export PATH=\"/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin\${PATH:+:\$PATH}\"
    # PEP 668: env var works on older pip; CLI flags added only when supported (must be separate argv words).
    PIP_ENV='PIP_BREAK_SYSTEM_PACKAGES=1'
    PIP_ARGS=(--no-cache-dir --ignore-installed)
    if $REMOTE_PY -m pip install --help 2>/dev/null | grep -qF -- '--break-system-packages'; then
        PIP_ARGS+=(--break-system-packages)
    fi
    if $REMOTE_PY -m pip install --help 2>/dev/null | grep -qF -- '--root-user-action'; then
        PIP_ARGS+=(--root-user-action=ignore)
    fi
    echo '🐍 pip install .[full] (may take several minutes on first deploy)...'
    set +e
    $SUDO env PATH=\"\$PATH\" \$PIP_ENV $REMOTE_PY -m pip install \"\${PIP_ARGS[@]}\" --force-reinstall '.[full]' 2>&1 | tee -a \"\$PIP_LOG\"
    pip_rc=\${PIPESTATUS[0]}
    set -e
    if [ \"\$pip_rc\" -ne 0 ]; then
        echo \"❌ pip install .[full] failed (exit \$pip_rc)\" >&2
        tail -n 30 \"\$PIP_LOG\" >&2 || true
        exit \"\$pip_rc\"
    fi
    $SUDO env PATH=\"\$PATH\" \$PIP_ENV $REMOTE_PY -m pip install \"\${PIP_ARGS[@]}\" python-augeas 2>&1 | tee -a \"\$PIP_LOG\" || echo '⚠️  python-augeas install failed (optional)'

    H2K=''
    for candidate in /usr/local/bin/h2kvmctl /usr/bin/h2kvmctl \"\$HOME/.local/bin/h2kvmctl\"; do
        [ -x \"\$candidate\" ] && H2K=\"\$candidate\" && break
    done
    if [ -z \"\$H2K\" ]; then
        H2K=\$(command -v h2kvmctl 2>/dev/null || true)
    fi
    if [ -z \"\$H2K\" ]; then
        H2K=\$(find /usr/local/bin /usr/bin \"\$HOME/.local/bin\" -name h2kvmctl -type f 2>/dev/null | head -1)
    fi
    if [ -n \"\$H2K\" ] && [ \"\$H2K\" != '/usr/local/bin/h2kvmctl' ]; then
        $SUDO install -m 755 \"\$H2K\" /usr/local/bin/h2kvmctl
    fi
    if [ ! -x /usr/local/bin/h2kvmctl ]; then
        echo 'h2kvmctl: not found or not in /usr/local/bin after pip install' >&2
        tail -n 30 \"\$PIP_LOG\" >&2 || true
        exit 1
    fi
    echo '✅ h2kvm pip install complete'
" 'pip|Installing|Successfully|Collecting|Building|error:|ERROR|externally-managed|augeas|h2kvmctl|complete' 40 "$_ssh_pip_tty"
_pip_rc=$?
set -e
if [ "$_pip_rc" -ne 0 ]; then
    warn "Fetching remote pip log tail..."
    _ssh_batch "tail -n 50 /tmp/h2kvm-pip-install.log 2>/dev/null || true" 2>/dev/null || true
    error "pip install failed on ${HOST} (ssh exit ${_pip_rc}). Re-run with --verbose or inspect /tmp/h2kvm-pip-install.log on the server."
fi
info "h2kvm installed to /usr/local/bin"

_ssh_batch "
    cd $REMOTE_DIR || exit 0
    if ! $REMOTE_PY -c 'import hivex' 2>/dev/null; then
        echo '🔄 hivex: bindings missing for $REMOTE_PY — running install-deps.sh --hivex'
        $SUDO env H2KVM_REMOTE_INSTALL=1 H2KVM_PYTHON=$REMOTE_PY bash scripts/install-deps.sh --hivex || true
    fi
    $REMOTE_PY -c 'import hivex; print(\"hivex:\", \"OK\")' 2>/dev/null || echo '⚠️  hivex: import still failing — check install-deps logs'
" 2>&1 | tail -12 || true
info "hivex interpreter check ($REMOTE_PY)"

# ── Create runtime directories (NBD locking needs /run/h2kvm) ──
_ssh "
    if [ -f $REMOTE_DIR/etc/tmpfiles.d/h2kvm.conf ]; then
        $SUDO cp $REMOTE_DIR/etc/tmpfiles.d/h2kvm.conf /etc/tmpfiles.d/h2kvm.conf
        $SUDO systemd-tmpfiles --create /etc/tmpfiles.d/h2kvm.conf 2>/dev/null || $SUDO mkdir -p /run/h2kvm
    else
        $SUDO mkdir -p /run/h2kvm
    fi
" 2>&1
info "Runtime dirs: /run/h2kvm"

# ── Auto-link libguestfs for the active Python version ──
step "Linking libguestfs for $REMOTE_PY"
_ssh "
    # Check if guestfs already importable
    if $REMOTE_PY -c 'import guestfs' 2>/dev/null; then
        echo 'guestfs: already available'
        exit 0
    fi

    TARGET_SITE=\$($REMOTE_PY -c 'import site; print(site.getsitepackages()[0])' 2>/dev/null)
    [ -z \"\$TARGET_SITE\" ] && { echo 'guestfs: cannot determine site-packages'; exit 0; }

    SOABI=\$($REMOTE_PY -c 'import sysconfig; print(sysconfig.get_config_var(\"SOABI\") or \"\")' 2>/dev/null)
    PY_MM=\$($REMOTE_PY -c 'import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}\")')

    GUESTFS_PY=''
    GUESTFS_SO=''
    # Prefer same Python minor as the interpreter (EL9 ships libguestfs for 3.9; do not link cpython-39 .so into 3.12).
    for search_dir in /usr/lib64/python\${PY_MM}/site-packages /usr/lib/python\${PY_MM}/site-packages \
                      /opt/h2kvm-venv/lib/python\${PY_MM}/site-packages \
                      /usr/lib64/python*/site-packages /usr/lib/python*/site-packages \
                      /usr/local/lib/python*/site-packages /usr/local/lib64/python*/site-packages; do
        [ -d \"\$search_dir\" ] || continue
        if [ -f \"\$search_dir/guestfs.py\" ] && [ -z \"\$GUESTFS_PY\" ]; then
            GUESTFS_PY=\"\$search_dir/guestfs.py\"
        fi
    done
    for search_dir in /usr/lib64/python\${PY_MM}/site-packages /usr/lib/python\${PY_MM}/site-packages \
                      /usr/lib64/python*/site-packages /usr/lib/python*/site-packages; do
        [ -d \"\$search_dir\" ] || continue
        if [ -n \"\$SOABI\" ]; then
            while IFS= read -r -d '' so; do
                case \"\$so\" in *\"\${SOABI}\"*) GUESTFS_SO=\"\$so\"; break 2 ;; esac
            done < <(find \"\$search_dir\" -maxdepth 1 -name 'libguestfsmod*.so' -print0 2>/dev/null)
        fi
    done

    if [ -n \"\$GUESTFS_PY\" ] && [ -n \"\$GUESTFS_SO\" ]; then
        $SUDO mkdir -p \"\$TARGET_SITE\"
        $SUDO ln -sf \"\$GUESTFS_PY\" \"\$TARGET_SITE/guestfs.py\"
        $SUDO ln -sf \"\$GUESTFS_SO\" \"\$TARGET_SITE/\$(basename \$GUESTFS_SO)\"
        echo \"guestfs: linked \$GUESTFS_PY + \$GUESTFS_SO -> \$TARGET_SITE\"
        $REMOTE_PY -c 'import guestfs; print(\"guestfs: import OK\")' 2>&1 || echo 'guestfs: import failed after linking'
    elif [ -n \"\$GUESTFS_PY\" ]; then
        echo \"guestfs: found guestfs.py for Python \${PY_MM} but no libguestfsmod.*so matching SOABI=\${SOABI:-unknown} (EL9 RPM is often 3.9-only) — use guestfish; Python guestfs import may be unavailable\"
    else
        echo 'guestfs: not found on system — install python3-libguestfs'
    fi
" 2>&1
info "libguestfs linking done"

# ── Ensure libvirtd is active (--quick skips quickstart; service may still be inactive) ──
if $QUICK_MODE; then
    _LV_STEP=5
else
    _LV_STEP=7
fi
step "Step ${_LV_STEP}/${TOTAL_STEPS}: 🖥️  Ensuring libvirtd is active"
_ssh_stream_and_preview "
    if ! command -v nbdkit &>/dev/null; then
        if command -v dnf &>/dev/null; then
            $SUDO dnf install -y nbdkit 2>&1 | tail -2 || true
        elif command -v apt-get &>/dev/null; then
            $SUDO apt-get install -y -qq nbdkit 2>&1 | tail -2 || true
        elif command -v zypper &>/dev/null; then
            $SUDO zypper --non-interactive install -y nbdkit 2>&1 | tail -2 || true
        fi
    fi
    if command -v nbdkit &>/dev/null; then
        echo \"nbdkit: \$(command -v nbdkit)\"
    else
        echo 'nbdkit: not installed (optional for h2kvm; recommended for migration tooling)'
    fi

    $SUDO systemctl daemon-reload 2>/dev/null || true
    $SUDO systemctl enable libvirtd 2>/dev/null || true
    $SUDO systemctl reset-failed libvirtd 2>/dev/null || true
    $SUDO systemctl start libvirtd 2>/dev/null || true
    if systemctl list-unit-files 2>/dev/null | grep -q '^libvirtd.socket'; then
        $SUDO systemctl enable --now libvirtd.socket 2>/dev/null || true
    fi
    i=0
    while [ \$i -lt 30 ]; do
        if $SUDO systemctl is-active libvirtd &>/dev/null; then
            echo 'libvirtd: active'
            exit 0
        fi
        i=\$((i + 1))
        sleep 1
    done
    $SUDO systemctl restart libvirtd 2>/dev/null || true
    sleep 2
    i=0
    while [ \$i -lt 15 ]; do
        if $SUDO systemctl is-active libvirtd &>/dev/null; then
            echo 'libvirtd: active (after restart)'
            exit 0
        fi
        i=\$((i + 1))
        sleep 1
    done
    echo 'libvirtd: still inactive after start/restart'
    $SUDO systemctl status libvirtd --no-pager -l 2>/dev/null | tail -20 || true
" 'libvirtd|active|inactive|nbdkit' 25
info "libvirtd ensure step completed"

# ── Verify ──
if $QUICK_MODE; then
    VERIFY_STEP=6
else
    VERIFY_STEP=8
fi
step "Step ${VERIFY_STEP}/${TOTAL_STEPS}: ✅ Verifying installation"

_ssh "
    echo \"📍 h2kvmctl: \$(which h2kvmctl 2>/dev/null || echo NOT_FOUND)\"
    echo \"📍 version:  \$(h2kvmctl --version 2>/dev/null || echo FAILED)\"
    cd /tmp
    $REMOTE_PY -c 'from h2kvm.providers.aws_ec2 import AWSConfig; print(\"📍 AWS EC2 provider: OK\")'
    $REMOTE_PY -c 'from h2kvm.providers.azure import AzureConfig; print(\"📍 Azure provider:   OK\")'
    $REMOTE_PY -c 'import guestkit; print(\"📍 GuestKit:         OK\")' 2>/dev/null || echo "  ⚠️  GuestKit: not available"
    $REMOTE_PY -c 'from h2kvm.fixers.windows.virtio.core import _VIRTIO_CACHE_DIR; print(\"📍 VirtIO cache:     OK\")'
    $REMOTE_PY -c 'from h2kvm.fixers.offline_fixer import OfflineFSFix; print(\"📍 Offline fixer:    OK\")'

    # EL 9+: virt-filesystems is in guestfs-tools RPM (/usr/sbin), not always pulled by libguestfs-tools alone.
    export PATH=\"/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:\${PATH}\"
    if ! command -v virt-filesystems &>/dev/null && ! [ -x /usr/bin/virt-filesystems ] && ! [ -x /usr/sbin/virt-filesystems ]; then
        echo '📦 verify: installing guestfs-tools + libguestfs-tools (provides virt-filesystems on EL9)...'
        if command -v dnf &>/dev/null; then $SUDO dnf install -y guestfs-tools libguestfs-tools 2>&1 | tail -8; \\
        elif command -v yum &>/dev/null; then $SUDO yum install -y guestfs-tools libguestfs-tools 2>&1 | tail -8; \\
        elif command -v apt-get &>/dev/null; then $SUDO apt-get update -qq && $SUDO apt-get install -y -qq libguestfs-tools 2>&1 | tail -8; \\
        elif command -v zypper &>/dev/null; then $SUDO zypper install -y guestfs-tools libguestfs-tools 2>&1 | tail -8 || $SUDO zypper install -y libguestfs-tools 2>&1 | tail -8; \\
        fi
    fi

    # Check system tools
    for tool in qemu-img qemu-nbd nbdkit virsh virt-install govc supermin; do
        if command -v \$tool &>/dev/null; then
            echo \"📍 \$tool: \$(command -v \$tool)\"
        else
            echo \"⚠️  \$tool: not found\"
        fi
    done
    vf_fs=\"\"
    for _cand in /usr/sbin/virt-filesystems /usr/bin/virt-filesystems; do
        if [ -f \"\$_cand\" ] && [ -x \"\$_cand\" ]; then
            vf_fs=\"\$_cand\"
            break
        fi
    done
    if [ -z \"\$vf_fs\" ]; then
        vf_fs=\$(PATH=\"/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\" command -v virt-filesystems 2>/dev/null || true)
    fi
    if [ -n \"\$vf_fs\" ]; then
        echo \"📍 virt-filesystems: \$vf_fs\"
    else
        echo \"⚠️  virt-filesystems: not found — on EL9 run: sudo dnf install -y guestfs-tools\"
    fi

    # Check optional deps
    $REMOTE_PY -c 'import hivex; print(\"📍 python-hivex:     OK\")' 2>/dev/null || echo '⚠️  python-hivex: not installed'
    $REMOTE_PY -c 'import boto3; print(\"📍 boto3:            OK\")' 2>/dev/null || echo '⚠️  boto3: not installed'
    command -v bsdtar &>/dev/null && echo '📍 bsdtar:           OK' || echo '⚠️  bsdtar: not installed'

    # Check virtio-win
    [ -f /var/lib/h2kvm/virtio-win.iso ] && echo '📍 virtio-win.iso:   OK' || echo '⚠️  virtio-win.iso: not found'
    [ -d /var/lib/h2kvm/virtio-win-extracted/viostor ] && echo '📍 VirtIO ISO cache: OK (pre-extracted)' || echo '📍 VirtIO ISO cache: will extract on first Windows migration'
" 2>&1

# ── Deploy h2kvm daemon service ──
step "Deploying h2kvm daemon service"
_ssh "
    $SUDO mkdir -p /etc/h2kvm /var/lib/h2kvm/queue /var/lib/h2kvm/output /var/log/h2kvm
    $SUDO chmod 755 /var/lib/h2kvm /var/lib/h2kvm/output

    # Create daemon config if not present
    if [ ! -f /etc/h2kvm/daemon.yaml ]; then
        $SUDO tee /etc/h2kvm/daemon.yaml > /dev/null << 'DCEOF'
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
DCEOF
    fi

    # Install systemd service (fix: run as root, use h2kvmctl)
    $SUDO tee /etc/systemd/system/h2kvm.service > /dev/null << 'SVCEOF'
[Unit]
Description=h2kvm VM Conversion Daemon
Documentation=https://github.com/ssahani/h2kvm
After=network.target libvirtd.service

[Service]
Type=simple
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
SVCEOF

    $SUDO systemctl daemon-reload
    $SUDO systemctl enable --now h2kvm.service 2>/dev/null
    $SUDO systemctl restart h2kvm.service
    sleep 2
    if $SUDO systemctl is-active h2kvm &>/dev/null; then
        echo 'h2kvm daemon: running'
        echo 'h2kvm daemon: systemctl status'
        $SUDO systemctl status h2kvm --no-pager
    else
        echo 'h2kvm daemon: FAILED TO START'
        $SUDO journalctl -u h2kvm --no-pager -n 3
    fi
" 2>&1
info "Daemon service deployed"

# ── Deploy h2kweb (web dashboard) ──
H2KWEB_DEPLOYED=false
if $SKIP_DASHBOARD; then
    step "h2kweb dashboard skipped (--skip-dashboard)"
    info "Skipped h2kweb deploy"
else
    step "Building and deploying h2kweb"
    if _ensure_h2kweb_frontend && _sync_h2kweb_artifacts; then
        if _ssh_stream_and_preview "
            set -euo pipefail
            WEB_DIR='$REMOTE_DIR/web'
            if [ ! -f \"\$WEB_DIR/dashboard/dist/index.html\" ]; then
                echo 'h2kweb: prebuilt dashboard missing at '\$WEB_DIR/dashboard/dist
                exit 1
            fi
            if [ ! -f \"\$WEB_DIR/main.go\" ]; then
                echo 'h2kweb: Go sources missing at '\$WEB_DIR
                exit 1
            fi
            cd \"\$WEB_DIR\"

            # Detect OS family from os-release — dnf may exist on Ubuntu (k3s/snap) but have no repos.
            if [ -f /etc/debian_version ] || grep -qiE '^ID(_LIKE)?=.*(debian|ubuntu)' /etc/os-release 2>/dev/null; then
                _pkg=apt
            elif command -v dnf &>/dev/null && dnf repolist 2>/dev/null | grep -q .; then
                _pkg=dnf
            elif command -v yum &>/dev/null; then
                _pkg=yum
            elif command -v zypper &>/dev/null; then
                _pkg=zypper
            else
                _pkg=unknown
            fi
            echo \"h2kweb: package manager: \$_pkg\"

            # Go binary must be built on the remote host (linux/amd64 + PAM/CGO).
            if ! command -v go &>/dev/null; then
                case \$_pkg in
                    apt)    $SUDO apt-get update -qq || true; $SUDO apt-get install -y -qq golang-go ;;
                    dnf)    $SUDO dnf install -y golang ;;
                    yum)    $SUDO yum install -y golang ;;
                    zypper) $SUDO zypper --non-interactive install -y go ;;
                esac
            fi
            case \$_pkg in
                apt)    dpkg -s libpam0g-dev &>/dev/null || { $SUDO apt-get update -qq || true; $SUDO apt-get install -y -qq libpam0g-dev; } ;;
                dnf)    rpm -q pam-devel &>/dev/null || $SUDO dnf install -y pam-devel ;;
                yum)    rpm -q pam-devel &>/dev/null || $SUDO yum install -y pam-devel ;;
            esac

            command -v go >/dev/null 2>&1 || { echo 'h2kweb: go missing on remote'; exit 1; }

            go mod tidy
            export CGO_CFLAGS=-D_GNU_SOURCE
            export CGO_LDFLAGS=-ldl
            go build -o /tmp/h2kweb .

            $SUDO systemctl stop h2kweb.service 2>/dev/null || true
            $SUDO rm -f /usr/local/bin/h2kweb
            $SUDO rm -rf /usr/local/share/h2kweb/dashboard

            $SUDO install -m 755 /tmp/h2kweb /usr/local/bin/h2kweb
            rm -f /tmp/h2kweb
            $SUDO mkdir -p /usr/local/share/h2kweb/dashboard
            $SUDO cp -r dashboard/dist/. /usr/local/share/h2kweb/dashboard/

            $SUDO install -m 644 h2kweb.service /etc/systemd/system/h2kweb.service
            $SUDO install -m 644 h2kweb.default /etc/default/h2kweb
            $SUDO sed -i 's|ExecStart=.*|ExecStart=/usr/local/bin/h2kweb --addr \${H2KWEB_ADDR} --static-dir /usr/local/share/h2kweb/dashboard --tls-cert auto|' /etc/systemd/system/h2kweb.service

            $SUDO systemctl daemon-reload
            $SUDO systemctl enable --now h2kweb.service 2>/dev/null
            $SUDO systemctl restart h2kweb.service
            if command -v firewall-cmd &>/dev/null; then
                $SUDO firewall-cmd --permanent --add-port=5070/tcp 2>/dev/null || true
                $SUDO firewall-cmd --reload 2>/dev/null || true
            elif command -v ufw &>/dev/null; then
                $SUDO ufw allow 5070/tcp 2>/dev/null || true
            fi
            sleep 1
            if $SUDO systemctl is-active h2kweb &>/dev/null; then
                echo 'h2kweb: running'
                echo 'h2kweb: systemctl status'
                $SUDO systemctl status h2kweb --no-pager
                grep -o 'liquid-glass-app' /usr/local/share/h2kweb/dashboard/index.html && echo 'h2kweb: tahoe dashboard confirmed'
            else
                echo 'h2kweb: FAILED TO START'
                $SUDO journalctl -u h2kweb --no-pager -n 10
                exit 1
            fi
        " 'h2kweb|go build|tahoe|installed|running|FAILED|missing|prebuilt' 35; then
            info "h2kweb deployed on port ${H2KWEB_PORT}"
            H2KWEB_DEPLOYED=true
        else
            warn "h2kweb deployment failed (build/start)"
        fi
    else
        warn "Skipping h2kweb — local dashboard build or artifact sync failed"
    fi
fi

# ── Smoke tests: verify endpoints are reachable ──
step "Smoke testing endpoints"
_ssh "
    pass=0
    fail=0
    failed_labels=''
    test_endpoint() {
        local label=\"\$1\" url=\"\$2\" expect=\"\$3\"
        body=\$(mktemp)
        code=\$(curl -sk -o \"\$body\" -w '%{http_code}' --max-time 5 \"\$url\" 2>/dev/null)
        if [ \"\$code\" = \"\$expect\" ]; then
            printf '  ✅ %-28s %s -> %s\n' \"\$label\" \"\$url\" \"\$code\"
            pass=\$((pass + 1))
        else
            printf '  ❌ %-28s %s -> %s (expected %s)\n' \"\$label\" \"\$url\" \"\$code\" \"\$expect\"
            # Show response body hint for diagnosis
            resp=\$(head -c 200 \"\$body\" 2>/dev/null | tr '\n' ' ')
            [ -n \"\$resp\" ] && printf '     Response: %s\n' \"\$resp\"
            fail=\$((fail + 1))
            failed_labels=\"\${failed_labels} \${label}\"
        fi
        rm -f \"\$body\"
    }

    echo ''
    echo '  ── h2kvm endpoints ──'
    test_endpoint 'Dashboard'       'https://localhost:5070/'                200
    test_endpoint 'Health'          'https://localhost:5070/api/v1/health'   200
    test_endpoint 'API Docs'        'https://localhost:5070/api/v1/docs'    401
    test_endpoint 'Auth (no creds)' 'https://localhost:5070/api/v1/status'  401

    echo ''
    echo \"  Results: \${pass} passed, \${fail} failed\"

    # ── Auto-diagnostics on failure ──
    if [ \"\$fail\" -gt 0 ]; then
        echo ''
        echo '  ── 🔍 Diagnostics ──'

        # Service state
        for svc in h2kweb h2kvm; do
            state=\$(systemctl is-active \$svc 2>/dev/null || echo 'not-found')
            if [ \"\$state\" != 'active' ]; then
                echo \"  ⚠️  Service \$svc: \$state\"
                journalctl -u \$svc --no-pager -n 5 2>/dev/null | sed 's/^/     /'
            else
                echo \"  📍 Service \$svc: running (pid \$(systemctl show \$svc -p MainPID --value))\"
            fi
        done

        # Port binding
        echo ''
        listening=\$(ss -tlnp 2>/dev/null | grep ':5070' || echo 'NONE')
        if [ \"\$listening\" = 'NONE' ]; then
            echo '  ❌ Port 5070: nothing listening'
            echo '     → h2kweb binary may have crashed or failed to bind'
        else
            echo \"  📍 Port 5070: \$listening\"
        fi

        # Binary exists
        if [ ! -f /usr/local/bin/h2kweb ]; then
            echo '  ❌ /usr/local/bin/h2kweb: missing'
        fi

        # Dashboard files
        if [ ! -f /usr/local/share/h2kweb/dashboard/index.html ]; then
            echo '  ❌ Dashboard index.html: missing'
            echo '     → Dashboard files not deployed correctly'
            echo \"     → Contents: \$(ls /usr/local/share/h2kweb/dashboard/ 2>/dev/null || echo 'dir missing')\"
        else
            fcount=\$(find /usr/local/share/h2kweb/dashboard -type f | wc -l)
            echo \"  📍 Dashboard files: \$fcount files present\"
        fi

        # TLS cert
        if [ ! -f /var/lib/h2kvm/tls/server.crt ]; then
            echo '  ❌ TLS cert missing: /var/lib/h2kvm/tls/server.crt'
        fi

        # Disk space
        avail=\$(df -h /var/lib/h2kvm 2>/dev/null | awk 'NR==2{print \$4}')
        echo \"  📍 Disk available: \$avail\"

        # Firewall
        if command -v firewall-cmd &>/dev/null; then
            if ! firewall-cmd --query-port=5070/tcp &>/dev/null 2>&1; then
                echo '  ⚠️  Firewall: port 5070/tcp not open'
                echo '     → Run: firewall-cmd --add-port=5070/tcp --permanent && firewall-cmd --reload'
            fi
        elif command -v ufw &>/dev/null; then
            if ! ufw status 2>/dev/null | grep -qE '^5070.*ALLOW'; then
                echo '  ⚠️  Firewall (ufw): port 5070/tcp not open'
                echo '     → Run: ufw allow 5070/tcp'
            fi
        fi

        echo ''
    fi
" 2>&1

# Detect live dashboard reachability for final URL output.
H2KWEB_ONLINE=false
if [ "$(_ssh "curl -sk -o /dev/null -w '%{http_code}' --max-time 5 https://localhost:${H2KWEB_PORT}/api/v1/health 2>/dev/null || true")" = "200" ]; then
    H2KWEB_ONLINE=true
fi

# Optional cleanup: remove remote source checkout once services are installed.
if ! $KEEP_SOURCES; then
    step "Cleaning remote sources"
    if _ssh "$SUDO rm -rf \"$REMOTE_DIR\""; then
        info "Removed remote source checkout: $REMOTE_DIR"
    else
        warn "Could not fully remove $REMOTE_DIR (permissions). Keeping checkout."
        KEEP_SOURCES=true
    fi
fi

finish_last_step_timer
TOTAL_SECS=$(( $(date +%s) - START_TS ))

# Final checklist (live checks from remote).
DAEMON_STATE=$(_ssh_batch "systemctl is-active h2kvm 2>/dev/null || echo inactive" | tr -d '\r')
if [ "$DAEMON_STATE" = "active" ]; then
    DAEMON_STATUS="OK"
else
    DAEMON_STATUS="WARN (${DAEMON_STATE})"
fi
if $H2KWEB_ONLINE; then
    DASHBOARD_STATUS="OK"
    HEALTH_STATUS="OK"
else
    DASHBOARD_STATUS="WARN"
    HEALTH_STATUS="WARN"
fi
if $KEEP_SOURCES; then
    SOURCES_STATUS="kept"
else
    SOURCES_STATUS="removed"
fi

MODE_LABEL=$($QUICK_MODE && echo quick || echo full)
h2kvm_save_deploy_last "$REPO_DIR" "$HOST" "$USER" "$MODE_LABEL"

deploy_ui_highlight "📋 Final checklist"
deploy_ui_checklist "daemon" "${DAEMON_STATUS}"
deploy_ui_checklist "dashboard" "${DASHBOARD_STATUS}"
deploy_ui_checklist "health API" "${HEALTH_STATUS}"
deploy_ui_checklist "sources" "${SOURCES_STATUS}"

h2kvm_print_success "$HOST" "$TOTAL_SECS"
deploy_ui_kv "🔗" "SSH" "ssh ${USER}@${HOST}"
echo ""
if $KEEP_SOURCES; then
    echo "  📁 Deploy dir: $REMOTE_DIR"
else
    echo "  📁 Deploy dir: removed after install (use --keep-sources to retain)"
fi
echo ""
if [ -n "$REMOTE_RUNTIME" ] && [ "$REMOTE_RUNTIME" != "none" ]; then
    echo "  🐳 Detected runtimes:"
    echo "$REMOTE_RUNTIME" | while IFS=: read -r name ver; do
        [ -n "$name" ] && echo "    - ${name}: ${ver}"
    done
    echo ""
fi
if $H2KWEB_DEPLOYED || $H2KWEB_ONLINE; then
    deploy_ui_kv "🌐" "Dashboard" "https://${HOST}:${H2KWEB_PORT}/"
    deploy_ui_kv "💚" "Health" "https://${HOST}:${H2KWEB_PORT}/api/v1/health"
else
    deploy_ui_warn "Dashboard not reachable — systemctl status h2kweb"
fi
echo ""
deploy_ui_note "🚀 h2kvmctl --config migration.yaml"
deploy_ui_note "🩺 doctor / selftest:"
echo ""
if $KEEP_SOURCES; then
    echo "    cd $REMOTE_DIR && bash scripts/doctor.sh"
    echo "    bash scripts/selftest.sh"
else
    echo "    (sources removed) re-run with --keep-sources for doctor/selftest scripts"
fi
echo ""
