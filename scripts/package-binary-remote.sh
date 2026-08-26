#!/usr/bin/env bash
# ============================================================================
# package-binary-remote.sh — Build h2kvm on a remote Linux host and tarball it
# ============================================================================
# Rsync sources, `pip install` + `web` dashboard build on the server, tarball
# Python CLI, h2kvmctl, h2kweb + UI for client handoff (no deploy-remote install).
#
# Usage:
#   ./scripts/package-binary-remote.sh <host> [user] [--fetch] [--reuse-build]
#
# Prerequisites on remote: python3, go, npm, libvirt build deps (install.sh --deps-only)
#
# See: docs/PACKAGE_BINARY_REMOTE.md
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

FETCH=false
REUSE_BUILD=false
SKIP_DEPS=false
POSITIONAL=()

for arg in "$@"; do
    case "$arg" in
        --fetch) FETCH=true ;;
        --reuse-build) REUSE_BUILD=true ;;
        --skip-deps) SKIP_DEPS=true ;;
        -h|--help)
            sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) POSITIONAL+=("$arg") ;;
    esac
done

HOST="${POSITIONAL[0]:-${DEPLOY_HOST:-}}"
USER="${POSITIONAL[1]:-${DEPLOY_USER:-sus}}"
SSH_TIMEOUT="${DEPLOY_SSH_TIMEOUT:-20}"

if [[ -z "${HOST}" ]]; then
    echo "Usage: $0 <host> [user] [--fetch] [--reuse-build]" >&2
    exit 1
fi

VERSION="${H2KVM_PACKAGE_VERSION:-$(sed -n 's/^version = "\(.*\)"/\1/p' "${REPO_DIR}/pyproject.toml" | head -1)}"
VERSION="${VERSION:-0.3.0}"
ARCH="linux-amd64"
REMOTE="${USER}@${HOST}"
REMOTE_HOME=$(ssh -o BatchMode=yes -o ConnectTimeout="${SSH_TIMEOUT}" "${REMOTE}" 'echo "$HOME"')
BUILD_DIR="${REMOTE_HOME}/.deployment/h2kvm-package"
OUT_DIR="${H2KVM_PACKAGE_DIR:-${REMOTE_HOME}/h2kvm-dist}"
ARTIFACT="h2kvm-${VERSION}-${ARCH}"
LOCAL_DIST="${REPO_DIR}/dist"

RSYNC_EXCLUDES=(
    --exclude='.git/'
    --exclude='.venv/'
    --exclude='.pkg-venv/'
    --exclude='venv/'
    --exclude='**/__pycache__/'
    --exclude='web/dashboard/node_modules/'
    --exclude='.pytest_cache/'
)

# shellcheck source=lib/package-remote-ui.sh
source "${SCRIPT_DIR}/lib/package-remote-ui.sh"

pkg_remote_banner "H2KVM" "${VERSION}" "${REMOTE}" "${ARCH}"

_ensure_h2kweb_local() {
    if [[ -f "${REPO_DIR}/web/h2kweb" && -d "${REPO_DIR}/web/dashboard/dist" ]]; then
        return 0
    fi
    if ! command -v go &>/dev/null || ! command -v npm &>/dev/null; then
        echo "h2kweb missing; install go + npm locally or build: cd web && make build" >&2
        exit 1
    fi
    pkg_remote_phase "Building h2kweb locally (Go + dashboard)"
    (cd "${REPO_DIR}/web" && make build)
}

_ensure_h2kweb_local

if [[ "${H2KVM_REMOTE_SKIP_SSH_CHECK:-}" != "1" ]]; then
    pkg_remote_phase "Preflight"
    ssh -o BatchMode=yes -o ConnectTimeout="${SSH_TIMEOUT}" -o StrictHostKeyChecking=accept-new \
        "${REMOTE}" "true"
    pkg_ok "SSH ${REMOTE}"
fi

pkg_remote_phase "Sync source"
pkg_remote_kv "Build dir" "${BUILD_DIR}"
ssh "${REMOTE}" "mkdir -p '${BUILD_DIR}'"
rsync -az --delete "${RSYNC_EXCLUDES[@]}" \
    -e "ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=15 -o ServerAliveCountMax=120" \
    "${REPO_DIR}/" "${REMOTE}:${BUILD_DIR}/"

if ! $SKIP_DEPS; then
    pkg_remote_phase "Build dependencies"
    ssh "${REMOTE}" bash -s <<REMOTE_DEPS
set -euo pipefail
SUDO=""
[ "\$(id -u)" -ne 0 ] && command -v sudo &>/dev/null && SUDO=sudo
if command -v dnf &>/dev/null; then
  \$SUDO dnf install -y python3.11 golang nodejs npm git make gcc 2>&1 | tail -8 || \
    \$SUDO dnf install -y python3.12 golang nodejs npm git make gcc 2>&1 | tail -8
elif command -v apt-get &>/dev/null; then
  \$SUDO apt-get update -qq
  \$SUDO apt-get install -y python3 python3-venv golang-go nodejs npm git build-essential 2>&1 | tail -8
fi
command -v go &>/dev/null && command -v npm &>/dev/null || { echo "go/npm missing" >&2; exit 1; }
echo "build deps OK"
REMOTE_DEPS
fi

BUILD_NEEDED=true
if $REUSE_BUILD; then
    if ssh "${REMOTE}" "test -x '${BUILD_DIR}/.pkg-venv/bin/h2kvmctl' && test -x '${BUILD_DIR}/web/h2kweb'"; then
        BUILD_NEEDED=false
        pkg_ok "Reusing .pkg-venv (--reuse-build)"
    fi
fi

if $BUILD_NEEDED; then
    pkg_remote_phase "Compile"
    pkg_info "pip + local h2kweb…"
    ssh "${REMOTE}" bash -s <<REMOTE_BUILD
set -euo pipefail
cd '${BUILD_DIR}'
export PATH="\${HOME}/go/bin:/usr/local/go/bin:\${PATH}"
pick_python() {
  for c in python3.12 python3.11 python3.10 python3; do
    if command -v "\${c}" &>/dev/null && "\${c}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
      echo "\${c}"
      return 0
    fi
  done
  if command -v dnf &>/dev/null; then
    sudo dnf install -y python3.11 2>/dev/null || sudo dnf install -y python3.12 2>/dev/null || true
    for c in python3.12 python3.11; do
      if command -v "\${c}" &>/dev/null && "\${c}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
        echo "\${c}"
        return 0
      fi
    done
  fi
  return 1
}
PY=\$(pick_python) || { echo 'Python 3.10+ required (dnf install python3.11)' >&2; exit 1; }
echo "Using \${PY}"
rm -rf .pkg-venv
"\${PY}" -m venv .pkg-venv
.pkg-venv/bin/pip install -U pip wheel
.pkg-venv/bin/pip install .
test -x web/h2kweb && test -d web/dashboard/dist || { echo 'h2kweb/dashboard missing — rebuild locally' >&2; exit 1; }
echo 'Build OK'
REMOTE_BUILD
fi

pkg_remote_phase "Assemble customer bundle"
pkg_remote_kv "Output" "${OUT_DIR}/${ARTIFACT}"
ssh "${REMOTE}" bash -s <<REMOTE_PACK
set -euo pipefail
OUT_DIR='${OUT_DIR}'
BUILD_DIR='${BUILD_DIR}'
ARTIFACT='${ARTIFACT}'
VERSION='${VERSION}'

STAGE="\${OUT_DIR}/\${ARTIFACT}"
rm -rf "\${STAGE}"
mkdir -p "\${STAGE}/bin" "\${STAGE}/web/dashboard"
cp -a "\${BUILD_DIR}/.pkg-venv" "\${STAGE}/venv"
cp "\${BUILD_DIR}/.pkg-venv/bin/h2kvmctl" "\${STAGE}/bin/"
cp "\${BUILD_DIR}/.pkg-venv/bin/h2kvm-luks" "\${STAGE}/bin/" 2>/dev/null || true
cp "\${BUILD_DIR}/.pkg-venv/bin/h2kvm-encrypt" "\${STAGE}/bin/" 2>/dev/null || true
cp "\${BUILD_DIR}/web/h2kweb" "\${STAGE}/bin/"
chmod +x "\${STAGE}/bin/"*
cat > "\${STAGE}/bin/h2kvm" <<'WRAP'
#!/usr/bin/env bash
ROOT="\$(cd "\$(dirname "\$0")/.." && pwd)"
exec "\${ROOT}/venv/bin/python" -m h2kvm "\$@"
WRAP
chmod +x "\${STAGE}/bin/h2kvm"
cp -a "\${BUILD_DIR}/web/dashboard/dist/." "\${STAGE}/web/dashboard/"
cp "\${BUILD_DIR}/examples/h2kvm-tools.yaml.example" "\${STAGE}/config.example.yaml" 2>/dev/null || true
cp "\${BUILD_DIR}/web/h2kweb.default" "\${STAGE}/h2kweb.env.example" 2>/dev/null || true
mkdir -p "\${STAGE}/scripts"
cp "\${BUILD_DIR}/scripts/install-deps.sh" "\${STAGE}/scripts/" 2>/dev/null || true
cp "\${BUILD_DIR}/scripts/install-versions.inc.sh" "\${STAGE}/scripts/" 2>/dev/null || true
LIB="\${BUILD_DIR}/scripts/lib"
for f in package-install.sh package-client-install.sh package-client-test.sh; do
  test -f "\${LIB}/\${f}" || { echo "missing \${LIB}/\${f}" >&2; exit 1; }
done
cp "\${LIB}/package-install.sh" "\${STAGE}/install.sh"
cp "\${LIB}/package-client-install.sh" "\${STAGE}/install-client-deps.sh"
cp "\${LIB}/package-client-test.sh" "\${STAGE}/test-package.sh"
mkdir -p "\${STAGE}/.package-lib"
cp "\${LIB}/package-ui.sh" "\${STAGE}/.package-lib/"
cp "\${LIB}/package-auth-bootstrap.sh" "\${STAGE}/.package-lib/"
cp "\${LIB}/install-everything.sh" "\${STAGE}/"
cp "\${LIB}/package-uninstall-lib.sh" "\${STAGE}/.package-lib/"
cp "\${LIB}/package-uninstall.sh" "\${STAGE}/uninstall.sh"
chmod +x "\${STAGE}/install.sh" "\${STAGE}/install-client-deps.sh" "\${STAGE}/test-package.sh" \
  "\${STAGE}/install-everything.sh" "\${STAGE}/uninstall.sh"
chmod +x "\${LIB}/write-customer-help.sh"
"\${LIB}/write-customer-help.sh" "\${STAGE}" "H2KVM" platform
cp "\${LIB}/START_HERE.txt" "\${STAGE}/"
cat > "\${STAGE}/.package-lib/product.meta" <<'META'
PRODUCT_NAME=H2KVM
ACCESS_SCHEME=http
ACCESS_PORT=5070
ACCESS_PATH=
AUTO_FULL_INSTALL=0
FINISH_EXTRA_1='Web: ./bin/h2kweb --addr 0.0.0.0:5070 --static-dir $(pwd)/web/dashboard'
FINISH_EXTRA_2='CLI: ./bin/h2kvm --help'
FINISH_EXTRA_3=
META

cat > "\${STAGE}/QUICKSTART.txt" <<'QEOF'
h2kvm — 5-minute install
=============================

1. tar xzf h2kvm-*-linux-amd64.tar.gz && cd h2kvm-*-linux-amd64
2. ./install.sh
3. ./bin/h2kweb --addr 0.0.0.0:5070 --static-dir "$(pwd)/web/dashboard"
4. Open http://<server-ip>:5070
5. ./test-package.sh

CLI: ./bin/h2kvm --help

More: README.txt

Packaged by Zyvor — zyvor.dev · HyperSDK · © 2026
QEOF

cp "\${BUILD_DIR}/scripts/zyvor-branding/ZYVOR_INSTALL.txt" "\${STAGE}/ZYVOR_INSTALL.txt" 2>/dev/null || true

cat > "\${STAGE}/README.txt" <<README_EOF
h2kvm ${VERSION} — Linux amd64 client bundle
================================================

START: cat START_HERE.txt  |  full help: cat HELP.txt

WHAT IS IN THIS ARCHIVE (no git clone — not a single static binary)
  bin/h2kvm     wrapper -> venv (Python 3.10+)
  bin/h2kvmctl, bin/h2kweb (native Go)
  venv/             pre-built Python env (pip already run on pack host)
  web/dashboard/    static UI
  install.sh, uninstall.sh, test-package.sh

REQUIREMENTS: Linux x86_64, libvirt/KVM, vSphere or libvirt as migration source
  Python runtime is bundled in venv/ — do not delete venv when moving the folder.

CUSTOMER INSTALL
  tar xzf h2kvm-*-linux-amd64.tar.gz
  cd h2kvm-*-linux-amd64
  ./install.sh
  ./bin/h2kweb --addr 0.0.0.0:5070 --static-dir "\$(pwd)/web/dashboard"

Web UI: http://<your-server>:5070

TEST: ./test-package.sh
UNINSTALL: ./uninstall.sh --yes [--remove-dir]
README_EOF

for req in HELP.txt START_HERE.txt install.sh uninstall.sh README.txt QUICKSTART.txt install-client-deps.sh test-package.sh bin/h2kvm bin/h2kweb; do
  test -e "\${STAGE}/\${req}" || { echo "bundle missing \${req}" >&2; exit 1; }
done
chmod +x "\${LIB}/finalize-customer-bundle.sh"
"\${LIB}/finalize-customer-bundle.sh" "\${STAGE}" "\${BUILD_DIR}" "H2KVM" "${VERSION}"
echo "Customer bundle OK"

cd "\${OUT_DIR}"
tar czf "\${ARTIFACT}.tar.gz" "\${ARTIFACT}"
sha256sum "\${ARTIFACT}.tar.gz" | tee "\${ARTIFACT}.tar.gz.sha256"
ls -lh "\${ARTIFACT}.tar.gz"
"\${STAGE}/bin/h2kvm" --version 2>&1 | head -3 || "\${STAGE}/bin/h2kvmctl" --version 2>&1 | head -3 || true
REMOTE_PACK

TARBALL="${ARTIFACT}.tar.gz"
REMOTE_TARBALL="${OUT_DIR}/${TARBALL}"

if $FETCH; then
    pkg_remote_phase "Fetch to laptop"
    mkdir -p "${LOCAL_DIST}"
    scp -o StrictHostKeyChecking=no \
        "${REMOTE}:${REMOTE_TARBALL}" \
        "${REMOTE}:${OUT_DIR}/${TARBALL}.sha256" \
        "${LOCAL_DIST}/"
    (cd "${LOCAL_DIST}" && shasum -a 256 -c "${TARBALL}.sha256" 2>/dev/null || sha256sum -c "${TARBALL}.sha256") && pkg_ok "Checksum verified"
fi

pkg_remote_done "H2KVM" "${REMOTE}:${REMOTE_TARBALL}" "${REMOTE}:${OUT_DIR}/${TARBALL}.sha256"
