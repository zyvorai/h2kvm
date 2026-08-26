#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export PKG_INSTALL_ROOT="${ROOT}"
# shellcheck source=/dev/null
[[ -f "${ROOT}/.package-lib/package-ui.sh" ]] && source "${ROOT}/.package-lib/package-ui.sh"

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && {
  pkg_script_help "test-package.sh"
  exit 0
}

pkg_counters_reset
pkg_banner "Hyper2KVM package test" "hyper2kvm · h2kweb · optional UI"

[[ -x ./bin/hyper2kvm ]] && pkg_ok "bin/hyper2kvm" || pkg_fail "bin/hyper2kvm"
[[ -x ./bin/h2kweb ]] && pkg_ok "bin/h2kweb" || pkg_fail "bin/h2kweb"
[[ -d ./web/dashboard ]] && pkg_ok "web/dashboard" || pkg_warn "web/dashboard missing"

if curl -sf http://127.0.0.1:5070/ >/dev/null 2>&1; then
  pkg_ok "h2kweb http://127.0.0.1:5070"
else
  pkg_skip "h2kweb not listening — start with install QUICKSTART"
fi

pkg_summary "Package test"
[[ "${_PKG_COUNTERS_FAIL}" -eq 0 ]]
