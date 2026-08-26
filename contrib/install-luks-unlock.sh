#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
#
# Hyper2KVM LUKS Auto-Unlock Installation Script
#
# This script installs and configures LUKS auto-unlock with TPM2.
#
# Usage:
#   sudo ./contrib/install-luks-unlock.sh [--tpm-handle HANDLE] [--vault-addr ADDR]
#
# Options:
#   --tpm-handle HANDLE    TPM2 persistent handle (default: 0x81000010)
#   --vault-addr ADDR      Vault server address (optional)
#   --vault-token TOKEN    Vault token (optional)
#   --vault-path PATH      Vault secret path (default: secret/hyper2kvm/luks)
#   --keyfile PATH         Path to existing LUKS keyfile
#   --device DEVICE        LUKS device to unlock (e.g., /dev/sda1)
#   --skip-seal            Skip sealing key to TPM
#   --skip-dracut          Skip dracut module installation

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Defaults
TPM_HANDLE="0x81000010"
VAULT_PATH="secret/hyper2kvm/luks"
SKIP_SEAL=false
SKIP_DRACUT=false

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run as root"
        exit 1
    fi
}

check_dependencies() {
    log_info "Checking dependencies..."

    local missing=()

    if ! command -v cryptsetup >/dev/null 2>&1; then
        missing+=("cryptsetup")
    fi

    if ! command -v python3 >/dev/null 2>&1; then
        missing+=("python3")
    fi

    if ! command -v pip3 >/dev/null 2>&1; then
        missing+=("python3-pip")
    fi

    if [ ${#missing[@]} -ne 0 ]; then
        log_error "Missing dependencies: ${missing[*]}"
        log_info "Install with: apt-get install ${missing[*]} # (Debian/Ubuntu)"
        log_info "           or: dnf install ${missing[*]}     # (Fedora/RHEL)"
        exit 1
    fi

    log_info "✓ All dependencies met"
}

check_tpm() {
    log_info "Checking TPM2 availability..."

    if [ ! -e /dev/tpm0 ] && [ ! -e /dev/tpmrm0 ]; then
        log_warn "TPM2 device not found - TPM unlock will not be available"
        return 1
    fi

    if ! command -v tpm2_pcrread >/dev/null 2>&1; then
        log_warn "tpm2-tools not installed - install for TPM unlock"
        log_info "  apt-get install tpm2-tools  # (Debian/Ubuntu)"
        log_info "  dnf install tpm2-tools      # (Fedora/RHEL)"
        return 1
    fi

    log_info "✓ TPM2 available"
    return 0
}

install_hyper2kvm() {
    log_info "Installing hyper2kvm LUKS module..."

    # Install Python dependencies
    pip3 install --upgrade cryptography hvac

    # Install hyper2kvm
    if [ -f setup.py ]; then
        pip3 install -e .
    else
        log_error "setup.py not found - run from hyper2kvm repository root"
        exit 1
    fi

    # Make CLI executable
    chmod +x bin/hyper2kvm-luks

    # Copy to /usr/bin if not already there
    if [ ! -L /usr/bin/hyper2kvm-luks ]; then
        ln -sf "$(pwd)/bin/hyper2kvm-luks" /usr/bin/hyper2kvm-luks
    fi

    log_info "✓ Hyper2KVM LUKS module installed"
}

create_config() {
    log_info "Creating configuration..."

    mkdir -p /etc/hyper2kvm

    local config="/etc/hyper2kvm/luks.json"

    # Build config
    cat > "$config" <<EOF
{
  "tpm_handle": "$TPM_HANDLE"
EOF

    if [ -n "$VAULT_ADDR" ]; then
        cat >> "$config" <<EOF
,
  "vault": {
    "addr": "$VAULT_ADDR",
    "token": "$VAULT_TOKEN",
    "path": "$VAULT_PATH"
  }
EOF
    fi

    if [ -n "$KEYFILE" ]; then
        cat >> "$config" <<EOF
,
  "keyfile": "$KEYFILE"
EOF
    fi

    cat >> "$config" <<EOF

}
EOF

    log_info "✓ Configuration created: $config"
}

seal_key_to_tpm() {
    if [ "$SKIP_SEAL" = true ]; then
        log_info "Skipping TPM sealing (--skip-seal)"
        return
    fi

    if ! check_tpm; then
        log_warn "Skipping TPM sealing (TPM not available)"
        return
    fi

    log_info "Sealing LUKS key to TPM2..."

    # Check if keyfile exists
    if [ -z "$KEYFILE" ] || [ ! -f "$KEYFILE" ]; then
        log_error "Keyfile not specified or not found"
        log_info "Specify with: --keyfile /path/to/luks.key"
        exit 1
    fi

    # Seal to TPM
    hyper2kvm-luks seal "$KEYFILE" --handle "$TPM_HANDLE" --pcr 0 1 2 3 7

    log_info "✓ Key sealed to TPM2 handle $TPM_HANDLE"
}

install_dracut_module() {
    if [ "$SKIP_DRACUT" = true ]; then
        log_info "Skipping dracut module installation (--skip-dracut)"
        return
    fi

    log_info "Installing dracut module..."

    if ! command -v dracut >/dev/null 2>&1; then
        log_warn "dracut not found - skipping initramfs integration"
        log_info "Install dracut for boot-time unlock:"
        log_info "  apt-get install dracut-core  # (Debian/Ubuntu)"
        log_info "  dnf install dracut           # (Fedora/RHEL)"
        return
    fi

    # Copy dracut module
    local dracut_dir="/usr/lib/dracut/modules.d/90hyper2kvm-luks"
    mkdir -p "$dracut_dir"

    cp -r contrib/dracut/90hyper2kvm-luks/* "$dracut_dir/"
    chmod +x "$dracut_dir"/*.sh

    log_info "✓ dracut module installed"

    # Rebuild initramfs
    log_info "Rebuilding initramfs..."
    dracut -f

    log_info "✓ Initramfs rebuilt"
}

add_key_to_luks() {
    if [ -z "$DEVICE" ]; then
        log_warn "No device specified - skipping LUKS key addition"
        log_info "Specify with: --device /dev/sda1"
        return
    fi

    if [ -z "$KEYFILE" ] || [ ! -f "$KEYFILE" ]; then
        log_error "Keyfile required for adding to LUKS device"
        exit 1
    fi

    log_info "Adding key to LUKS device $DEVICE..."

    if cryptsetup luksDump "$DEVICE" >/dev/null 2>&1; then
        cryptsetup luksAddKey "$DEVICE" "$KEYFILE"
        log_info "✓ Key added to $DEVICE"
    else
        log_error "$DEVICE is not a LUKS device"
        exit 1
    fi
}

print_summary() {
    echo ""
    echo "=================================="
    echo "  LUKS Auto-Unlock Installation"
    echo "=================================="
    echo ""
    echo "✓ Installation complete!"
    echo ""
    echo "Configuration: /etc/hyper2kvm/luks.json"
    echo "TPM Handle:    $TPM_HANDLE"
    echo ""
    echo "Next steps:"
    echo "1. Verify configuration: cat /etc/hyper2kvm/luks.json"
    echo "2. Test unlock:         hyper2kvm-luks unlock -v"
    echo "3. Check status:        hyper2kvm-luks status"
    echo "4. Reboot to test automatic unlock"
    echo ""
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --tpm-handle)
            TPM_HANDLE="$2"
            shift 2
            ;;
        --vault-addr)
            VAULT_ADDR="$2"
            shift 2
            ;;
        --vault-token)
            VAULT_TOKEN="$2"
            shift 2
            ;;
        --vault-path)
            VAULT_PATH="$2"
            shift 2
            ;;
        --keyfile)
            KEYFILE="$2"
            shift 2
            ;;
        --device)
            DEVICE="$2"
            shift 2
            ;;
        --skip-seal)
            SKIP_SEAL=true
            shift
            ;;
        --skip-dracut)
            SKIP_DRACUT=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --tpm-handle HANDLE    TPM2 persistent handle (default: 0x81000010)"
            echo "  --vault-addr ADDR      Vault server address"
            echo "  --vault-token TOKEN    Vault token"
            echo "  --vault-path PATH      Vault secret path (default: secret/hyper2kvm/luks)"
            echo "  --keyfile PATH         Path to LUKS keyfile"
            echo "  --device DEVICE        LUKS device (e.g., /dev/sda1)"
            echo "  --skip-seal            Skip sealing key to TPM"
            echo "  --skip-dracut          Skip dracut module installation"
            echo "  -h, --help             Show this help"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Main installation
main() {
    log_info "Starting Hyper2KVM LUKS Auto-Unlock installation"
    echo ""

    check_root
    check_dependencies
    check_tpm
    install_hyper2kvm
    create_config
    add_key_to_luks
    seal_key_to_tpm
    install_dracut_module
    print_summary
}

main
