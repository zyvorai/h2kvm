#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
[[ -f "${ROOT}/.package-lib/package-ui.sh" ]] && source "${ROOT}/.package-lib/package-ui.sh"
if [[ -f "${ROOT}/.package-lib/package-uninstall-lib.sh" ]]; then
  # shellcheck source=/dev/null
  source "${ROOT}/.package-lib/package-uninstall-lib.sh"
else
  # shellcheck source=package-uninstall-lib.sh
  source "$(dirname "$0")/package-uninstall-lib.sh"
fi

PRODUCT="h2kvm"
BINARIES=(h2kvmctl)
BINARIES_SUBPATH=(bin/h2kvm bin/h2kweb venv/bin/python)
PORTS=(5070)
LOCAL_CONFIGS=(h2kweb.env)

package_uninstall_main "${PRODUCT}" "${ROOT}" "$@"
