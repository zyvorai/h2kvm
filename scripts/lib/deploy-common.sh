# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# hyper2kvm deploy library (self-contained under scripts/lib/).

_DEPLOY_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DEPLOY_UI_PROJECT="hyper2kvm"
DEPLOY_UI_ICON="🔄"
DEPLOY_UI_ICON_UNINSTALL="🗑️"
DEPLOY_UI_ICON_MAGIC="✨"
DEPLOY_UI_PORT="5070"
DEPLOY_UI_SCHEME="https"
DEPLOY_UI_DASH_PATH="/"
DEPLOY_UI_HEALTH_PATH="/api/v1/health"

# shellcheck source=deploy-ui.sh
source "$_DEPLOY_LIB_DIR/deploy-ui.sh"

hyper2kvm_build_metadata() {
    local repo_dir="$1"
    HYPER2KVM_VERSION=$(git -C "$repo_dir" describe --tags --always --dirty 2>/dev/null || echo 'dev')
    HYPER2KVM_COMMIT=$(git -C "$repo_dir" rev-parse --short HEAD 2>/dev/null || echo 'unknown')
    export HYPER2KVM_VERSION HYPER2KVM_COMMIT
}

hyper2kvm_parse_target() { deploy_ui_parse_target "$@"; }
hyper2kvm_deploy_state_file() { deploy_ui_deploy_state_file "$1"; }
hyper2kvm_save_deploy_last() {
    deploy_ui_save_deploy_last "$1" "$2" "$3" "$4" "${HYPER2KVM_VERSION:-}" "${HYPER2KVM_COMMIT:-}"
}
hyper2kvm_load_deploy_last() { deploy_ui_load_deploy_last "$1"; }

hyper2kvm_smoke_tests_script() {
    cat <<SMOKE
pass=0
fail=0
test_endpoint() {
    local label="\$1" url="\$2" expect="\$3"
    body=\$(mktemp)
    code=\$(curl -sk -o "\$body" -w '%{http_code}' --max-time 5 "\$url" 2>/dev/null)
    if [ "\$code" = "\$expect" ]; then
        printf '  ✅ %-28s %s -> %s\n' "\$label" "\$url" "\$code"
        pass=\$((pass + 1))
    else
        printf '  ❌ %-28s %s -> %s (expected %s)\n' "\$label" "\$url" "\$code" "\$expect"
        fail=\$((fail + 1))
    fi
    rm -f "\$body"
}
echo ''
echo '  🩺 hyper2kvm endpoints ──'
test_endpoint 'Health'    'https://localhost:${DEPLOY_UI_PORT}${DEPLOY_UI_HEALTH_PATH}' 200
test_endpoint 'Dashboard' 'https://localhost:${DEPLOY_UI_PORT}/' 200
echo ''
echo "  Results: \${pass} passed, \${fail} failed"
SMOKE
}

hyper2kvm_print_success() {
    deploy_ui_success "$1" "$2" "./scripts/deploy remote --quick"
}

# Optional aliases for deploy scripts
hyper2kvm_info()  { deploy_ui_info "$@"; }
hyper2kvm_warn()  { deploy_ui_warn "$@"; }
hyper2kvm_error() { deploy_ui_error "$@"; }
