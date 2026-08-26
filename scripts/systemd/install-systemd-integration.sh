#!/bin/bash
set -euo pipefail
#
# H2KVM Systemd Integration Installation Script
# ==================================================
#
# This script installs systemd units, creates necessary directories,
# and sets up the systemd integration for h2kvm.
#
# Usage: sudo ./install-systemd-integration.sh [options]
#
# Options:
#   --enable-all      Enable and start all services
#   --enable-socket   Enable socket activation only
#   --enable-timer    Enable timer for scheduled repairs
#   --enable-path     Enable path monitoring
#   --uninstall       Remove all systemd integration
#   --dry-run         Show what would be done without doing it
#   --help            Show this help message
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SYSTEMD_UNIT_DIR="/etc/systemd/system"
RUNTIME_DIR="/run/h2kvm"
STATE_DIR="/var/lib/h2kvm"
LOG_DIR="/var/log/h2kvm"
CONFIG_DIR="/etc/h2kvm"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
UNITS_DIR="${PROJECT_ROOT}/systemd/units"

# Options
DRY_RUN=false
ENABLE_ALL=false
ENABLE_SOCKET=false
ENABLE_TIMER=false
ENABLE_PATH=false
UNINSTALL=false

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi
}

# Check dependencies
check_dependencies() {
    log_info "Checking dependencies..."

    local missing_deps=()

    # Check for systemd
    if ! command -v systemctl &> /dev/null; then
        missing_deps+=("systemd")
    fi

    # Check for Python
    if ! command -v python3 &> /dev/null; then
        missing_deps+=("python3")
    fi

    # Check for pip
    if ! command -v pip3 &> /dev/null; then
        log_warning "pip3 not found - systemd Python bindings may not be installed"
    fi

    # Check Python packages
    if ! python3 -c "import systemd.daemon" 2>/dev/null; then
        log_warning "systemd-python not installed. Install with: pip install systemd-python"
    fi

    if ! python3 -c "import dbus" 2>/dev/null; then
        log_warning "dbus-python not installed. Install with: pip install dbus-python"
    fi

    if ! python3 -c "import psutil" 2>/dev/null; then
        log_warning "psutil not installed. Install with: pip install psutil"
    fi

    if ! python3 -c "import inotify.adapters" 2>/dev/null; then
        log_warning "inotify not installed. Install with: pip install inotify"
    fi

    if [ ${#missing_deps[@]} -ne 0 ]; then
        log_error "Missing required dependencies: ${missing_deps[*]}"
        exit 1
    fi

    log_success "All required dependencies found"
}

# Create necessary directories
create_directories() {
    log_info "Creating directories..."

    local dirs=(
        "$RUNTIME_DIR"
        "$STATE_DIR"
        "$LOG_DIR"
        "$CONFIG_DIR"
    )

    for dir in "${dirs[@]}"; do
        if [[ $DRY_RUN == true ]]; then
            log_info "Would create: $dir"
        else
            mkdir -p "$dir"
            log_success "Created: $dir"
        fi
    done

    # Set permissions
    if [[ $DRY_RUN == false ]]; then
        chmod 755 "$STATE_DIR"
        chmod 755 "$LOG_DIR"
        chmod 755 "$CONFIG_DIR"
        chmod 755 "$RUNTIME_DIR"
        log_success "Set directory permissions"
    fi
}

# Install systemd unit files
install_units() {
    log_info "Installing systemd unit files..."

    if [[ ! -d "$UNITS_DIR" ]]; then
        log_error "Units directory not found: $UNITS_DIR"
        exit 1
    fi

    local units=(
        "h2kvm.service"
        "h2kvm.socket"
        "h2kvm.timer"
        "h2kvm-scheduled.service"
        "h2kvm.path"
        "h2kvm-path-trigger.service"
        "h2kvm.target"
        "h2kvm@.service"
    )

    for unit in "${units[@]}"; do
        local src="${UNITS_DIR}/${unit}"
        local dst="${SYSTEMD_UNIT_DIR}/${unit}"

        if [[ ! -f "$src" ]]; then
            log_warning "Unit file not found: $src"
            continue
        fi

        if [[ $DRY_RUN == true ]]; then
            log_info "Would install: $unit"
        else
            cp "$src" "$dst"
            chmod 644 "$dst"
            log_success "Installed: $unit"
        fi
    done
}

# Create default configuration
create_config() {
    log_info "Creating default configuration..."

    local config_file="${CONFIG_DIR}/h2kvm.conf"

    if [[ -f "$config_file" ]]; then
        log_warning "Configuration file already exists: $config_file"
        return
    fi

    if [[ $DRY_RUN == true ]]; then
        log_info "Would create: $config_file"
        return
    fi

    cat > "$config_file" << 'EOF'
# H2KVM Systemd Integration Configuration
# ============================================

# VM image directories to monitor (comma-separated)
WATCH_PATHS=/var/lib/libvirt/images

# Resource limits
CPU_QUOTA=75%
MEMORY_MAX=4G

# Path monitoring
ENABLE_PATH_MONITOR=false
PATH_MONITOR_DEBOUNCE=5

# Auto-repair settings
AUTO_REPAIR_ENABLED=false
AUTO_REPAIR_COOLDOWN=30

# Logging
LOG_LEVEL=INFO
JOURNAL_LOGGING=true

# Socket settings
SOCKET_PATH=/run/h2kvm/repair.sock
SOCKET_TIMEOUT=30

# Timer settings
TIMER_SCHEDULE=daily
TIMER_RANDOM_DELAY=30min
EOF

    chmod 644 "$config_file"
    log_success "Created configuration: $config_file"
}

# Reload systemd daemon
reload_systemd() {
    log_info "Reloading systemd daemon..."

    if [[ $DRY_RUN == true ]]; then
        log_info "Would reload systemd daemon"
    else
        systemctl daemon-reload
        log_success "Systemd daemon reloaded"
    fi
}

# Enable and start services
enable_services() {
    if [[ $ENABLE_ALL == false && $ENABLE_SOCKET == false && $ENABLE_TIMER == false && $ENABLE_PATH == false ]]; then
        log_info "No services will be enabled (use --enable-* options)"
        return
    fi

    log_info "Enabling services..."

    if [[ $ENABLE_ALL == true || $ENABLE_SOCKET == true ]]; then
        enable_unit "h2kvm.socket"
    fi

    if [[ $ENABLE_ALL == true || $ENABLE_TIMER == true ]]; then
        enable_unit "h2kvm.timer"
    fi

    if [[ $ENABLE_ALL == true || $ENABLE_PATH == true ]]; then
        enable_unit "h2kvm.path"
    fi

    if [[ $ENABLE_ALL == true ]]; then
        enable_unit "h2kvm.target"
    fi
}

# Enable a single unit
enable_unit() {
    local unit=$1

    if [[ $DRY_RUN == true ]]; then
        log_info "Would enable: $unit"
    else
        if systemctl enable "$unit" 2>/dev/null; then
            log_success "Enabled: $unit"

            # Start socket and timer units
            if [[ "$unit" == *.socket ]] || [[ "$unit" == *.timer ]] || [[ "$unit" == *.path ]]; then
                if systemctl start "$unit" 2>/dev/null; then
                    log_success "Started: $unit"
                fi
            fi
        else
            log_warning "Failed to enable: $unit"
        fi
    fi
}

# Uninstall systemd integration
uninstall() {
    log_info "Uninstalling systemd integration..."

    # Stop and disable services
    local units=(
        "h2kvm.socket"
        "h2kvm.service"
        "h2kvm.timer"
        "h2kvm-scheduled.service"
        "h2kvm.path"
        "h2kvm-path-trigger.service"
        "h2kvm.target"
    )

    for unit in "${units[@]}"; do
        if [[ $DRY_RUN == true ]]; then
            log_info "Would stop and disable: $unit"
        else
            systemctl stop "$unit" 2>/dev/null || true
            systemctl disable "$unit" 2>/dev/null || true
            log_success "Stopped and disabled: $unit"
        fi
    done

    # Remove unit files
    for unit in "${units[@]}" "h2kvm@.service"; do
        local unit_file="${SYSTEMD_UNIT_DIR}/${unit}"
        if [[ -f "$unit_file" ]]; then
            if [[ $DRY_RUN == true ]]; then
                log_info "Would remove: $unit_file"
            else
                rm -f "$unit_file"
                log_success "Removed: $unit_file"
            fi
        fi
    done

    # Reload daemon
    reload_systemd

    # Optionally remove directories
    log_warning "The following directories were NOT removed (remove manually if desired):"
    log_warning "  - $STATE_DIR"
    log_warning "  - $LOG_DIR"
    log_warning "  - $CONFIG_DIR"
    log_warning "  - $RUNTIME_DIR"
}

# Show status
show_status() {
    log_info "Systemd integration status:"
    echo ""

    local units=(
        "h2kvm.socket"
        "h2kvm.service"
        "h2kvm.timer"
        "h2kvm.path"
        "h2kvm.target"
    )

    for unit in "${units[@]}"; do
        if systemctl is-enabled "$unit" &>/dev/null; then
            local status=$(systemctl is-active "$unit" 2>/dev/null || echo "inactive")
            echo -e "  ${GREEN}●${NC} $unit - $status"
        else
            echo -e "  ${RED}○${NC} $unit - disabled"
        fi
    done

    echo ""
}

# Show help
show_help() {
    cat << EOF
H2KVM Systemd Integration Installation Script

Usage: sudo $0 [options]

Options:
    --enable-all      Enable and start all services
    --enable-socket   Enable socket activation only
    --enable-timer    Enable timer for scheduled repairs
    --enable-path     Enable path monitoring
    --uninstall       Remove all systemd integration
    --dry-run         Show what would be done without doing it
    --status          Show status of systemd units
    --help            Show this help message

Examples:
    # Install with all features
    sudo $0 --enable-all

    # Install with socket activation only
    sudo $0 --enable-socket

    # Install with timer and path monitoring
    sudo $0 --enable-timer --enable-path

    # Dry run to see what would happen
    sudo $0 --enable-all --dry-run

    # Uninstall
    sudo $0 --uninstall

Dependencies:
    - systemd
    - python3
    - systemd-python (pip install systemd-python)
    - dbus-python (pip install dbus-python)
    - psutil (pip install psutil)
    - inotify (pip install inotify)

EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --enable-all)
                ENABLE_ALL=true
                shift
                ;;
            --enable-socket)
                ENABLE_SOCKET=true
                shift
                ;;
            --enable-timer)
                ENABLE_TIMER=true
                shift
                ;;
            --enable-path)
                ENABLE_PATH=true
                shift
                ;;
            --uninstall)
                UNINSTALL=true
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --status)
                show_status
                exit 0
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

# Main installation flow
main() {
    parse_args "$@"

    echo ""
    echo "╔════════════════════════════════════════════════════════╗"
    echo "║  H2KVM Systemd Integration Installation Script    ║"
    echo "╚════════════════════════════════════════════════════════╝"
    echo ""

    if [[ $DRY_RUN == true ]]; then
        log_warning "DRY RUN MODE - No changes will be made"
        echo ""
    fi

    check_root

    if [[ $UNINSTALL == true ]]; then
        uninstall
        log_success "Uninstallation complete"
        exit 0
    fi

    check_dependencies
    create_directories
    install_units
    create_config
    reload_systemd
    enable_services

    echo ""
    log_success "Installation complete!"
    echo ""

    # Show status
    show_status

    # Show next steps
    echo ""
    log_info "Next steps:"
    echo "  1. Review configuration: $CONFIG_DIR/h2kvm.conf"
    echo "  2. Check service status: systemctl status h2kvm.target"
    echo "  3. View logs: journalctl -u h2kvm.service -f"
    echo "  4. Test socket: h2kvm-client health-check"
    echo ""
}

# Run main function
main "$@"
