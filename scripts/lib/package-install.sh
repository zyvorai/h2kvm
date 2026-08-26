#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export PKG_INSTALL_ROOT="${ROOT}"
# shellcheck source=/dev/null
[[ -f "${ROOT}/.package-lib/package-ui.sh" ]] && source "${ROOT}/.package-lib/package-ui.sh"

pkg_parse_install_args "$@"

_PKG_SESSION_START=${SECONDS}
pkg_install_welcome "H2KVM"
pkg_banner "H2KVM" "vSphere / libvirt conversion · Python venv bundle"
pkg_step_init 4

pkg_step "System dependencies"
[[ -x ./install-client-deps.sh ]] && { ./install-client-deps.sh || pkg_warn "deps issues"; pkg_step_done; } || { pkg_fail "install-client-deps.sh missing"; exit 1; }

pkg_step "Configuration"
pkg_env_bootstrap h2kweb.env.example h2kweb.env
pkg_step_done

pkg_step "Verify binaries"
[[ -x ./bin/h2kvm ]] && [[ -x ./bin/h2kweb ]] && pkg_ok "venv wrappers: h2kvm + h2kweb" || { pkg_fail "bin/h2kvm or bin/h2kweb missing"; exit 1; }
[[ -d ./venv ]] && pkg_ok "Python venv bundled" || pkg_warn "venv/ missing"
pkg_step_done

pkg_step "Smoke test"
[[ -x ./test-package.sh ]] && ./test-package.sh || pkg_warn "test-package.sh"
pkg_step_done

pkg_install_finish "H2KVM" http 5070 "" \
  "Web UI: ./bin/h2kweb --addr 0.0.0.0:5070 --static-dir \$(pwd)/web/dashboard" \
  "CLI: ./bin/h2kvm --help" \
  "Help: cat HELP.txt · ./install.sh --help" \
  "Remove: ./uninstall.sh --yes [--remove-dir]"
