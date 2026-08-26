#!/bin/bash
# install-venv.sh — Install hyper2kvm in a Python virtual environment
#
# Works on: Fedora, RHEL, CentOS, Rocky, Alma, Ubuntu, Debian, SUSE
#
# Usage:
#   ./scripts/install-venv.sh                    # install to /opt/hyper2kvm
#   ./scripts/install-venv.sh /path/to/venv      # custom location
#   ./scripts/install-venv.sh --user              # install to ~/.local/hyper2kvm
#   ./scripts/install-venv.sh --uninstall         # remove installation
#
# After install:
#   sudo h2kvmctl --version
#   sudo h2kvmctl --config migration.yaml

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VERSION=$(grep '^version' "$REPO_ROOT/pyproject.toml" | head -1 | sed 's/.*"\(.*\)"/\1/')
DEFAULT_VENV="/opt/hyper2kvm"
SYMLINK_DIR="/usr/local/sbin"

# ---------- Parse args ----------
VENV_DIR="$DEFAULT_VENV"
UNINSTALL=false

for arg in "$@"; do
    case "$arg" in
        --user)
            VENV_DIR="$HOME/.local/hyper2kvm"
            SYMLINK_DIR="$HOME/.local/bin"
            ;;
        --uninstall|--remove)
            UNINSTALL=true
            ;;
        --help|-h)
            echo "Usage: $0 [VENV_PATH] [--user] [--uninstall]"
            echo ""
            echo "  VENV_PATH    Install location (default: /opt/hyper2kvm)"
            echo "  --user       Install to ~/.local/hyper2kvm"
            echo "  --uninstall  Remove hyper2kvm venv and symlinks"
            echo ""
            echo "Examples:"
            echo "  sudo $0                        # /opt/hyper2kvm"
            echo "  sudo $0 /srv/hyper2kvm         # custom path"
            echo "  $0 --user                      # ~/.local/hyper2kvm"
            echo "  sudo $0 --uninstall            # remove"
            exit 0
            ;;
        -*)
            echo "Unknown option: $arg" >&2
            exit 1
            ;;
        *)
            VENV_DIR="$arg"
            ;;
    esac
done

# ---------- Uninstall ----------
if $UNINSTALL; then
    echo "=== Uninstalling hyper2kvm ==="
    for link in h2kvmctl hyper2kvm hyper2kvm-encrypt hyper2kvm-luks; do
        for dir in /usr/local/sbin /usr/local/bin "$HOME/.local/bin"; do
            if [ -L "$dir/$link" ]; then
                rm -f "$dir/$link"
                echo "  Removed $dir/$link"
            fi
        done
    done
    if [ -d "$VENV_DIR" ]; then
        rm -rf "$VENV_DIR"
        echo "  Removed $VENV_DIR"
    fi
    echo "Done."
    exit 0
fi

echo "=== hyper2kvm venv installer ==="
echo "Version:  $VERSION"
echo "Source:   $REPO_ROOT"
echo "Venv:     $VENV_DIR"
echo "Symlinks: $SYMLINK_DIR"
echo ""

# ---------- Detect distro and install system deps ----------
install_system_deps() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
    else
        ID="unknown"
        PRETTY_NAME="unknown"
    fi

    echo "Detected: $ID (${PRETTY_NAME:-$ID})"

    case "$ID" in
        fedora|rhel|centos|rocky|almalinux|ol)
            echo "Installing system dependencies (dnf)..."
            dnf install -y -q python3 python3-pip python3-devel python3-pyyaml \
                qemu-img libguestfs-tools 2>/dev/null || \
            yum install -y -q python3 python3-pip python3-devel python3-pyyaml \
                qemu-img libguestfs-tools 2>/dev/null || true
            ;;
        ubuntu|debian|linuxmint|pop)
            echo "Installing system dependencies (apt)..."
            apt-get update -qq 2>/dev/null
            apt-get install -y -qq python3 python3-pip python3-venv python3-dev \
                python3-yaml qemu-utils libguestfs-tools 2>/dev/null || true
            ;;
        sles|opensuse*|suse)
            echo "Installing system dependencies (zypper)..."
            zypper install -y python3 python3-pip python3-devel python3-PyYAML \
                qemu-tools libguestfs 2>/dev/null || true
            ;;
        *)
            echo "WARNING: Unknown distro '$ID'. Ensure python3, pip, qemu-img are installed."
            ;;
    esac
}

# Only install system deps if running as root
if [ "$(id -u)" -eq 0 ]; then
    install_system_deps
else
    echo "Not root — skipping system dependency install."
    echo "Ensure python3, python3-venv, qemu-img are installed."
fi

# ---------- Create venv ----------
echo ""
echo "Creating virtual environment at $VENV_DIR..."
if [ -d "$VENV_DIR" ]; then
    echo "  Existing venv found — upgrading..."
fi
python3 -m venv "$VENV_DIR" --system-site-packages --upgrade-deps 2>/dev/null || \
python3 -m venv "$VENV_DIR" --system-site-packages

# ---------- Install hyper2kvm ----------
echo "Installing hyper2kvm $VERSION..."
"$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel -q 2>/dev/null || true

# Install from source (editable) or wheel
if [ -f "$REPO_ROOT/pyproject.toml" ]; then
    "$VENV_DIR/bin/pip" install -e "$REPO_ROOT" -q 2>&1 | tail -3
else
    "$VENV_DIR/bin/pip" install hyper2kvm -q 2>&1 | tail -3
fi

# ---------- Create symlinks ----------
echo ""
echo "Creating symlinks in $SYMLINK_DIR..."
mkdir -p "$SYMLINK_DIR"
for cmd in h2kvmctl hyper2kvm hyper2kvm-encrypt hyper2kvm-luks; do
    if [ -f "$VENV_DIR/bin/$cmd" ]; then
        ln -sf "$VENV_DIR/bin/$cmd" "$SYMLINK_DIR/$cmd"
        echo "  $SYMLINK_DIR/$cmd -> $VENV_DIR/bin/$cmd"
    fi
done

# ---------- Install configs (only as root) ----------
if [ "$(id -u)" -eq 0 ]; then
    echo ""
    echo "Installing system configs..."
    if [ -d "$REPO_ROOT/etc/hyper2kvm" ]; then
        mkdir -p /etc/hyper2kvm/migrations
        [ -f /etc/hyper2kvm/config.yaml ] || \
            install -m 644 "$REPO_ROOT/etc/hyper2kvm/config.yaml.sample" /etc/hyper2kvm/config.yaml
        [ -f /etc/hyper2kvm/daemon.yaml ] || \
            install -m 644 "$REPO_ROOT/etc/hyper2kvm/daemon.yaml.sample" /etc/hyper2kvm/daemon.yaml
        install -m 644 "$REPO_ROOT/etc/hyper2kvm/migrations/"*.yaml /etc/hyper2kvm/migrations/ 2>/dev/null || true
        echo "  /etc/hyper2kvm/config.yaml"
    fi

    if [ -d "$REPO_ROOT/etc/modprobe.d" ]; then
        mkdir -p /etc/modprobe.d
        install -m 644 "$REPO_ROOT/etc/modprobe.d/nbd.conf" /etc/modprobe.d/hyper2kvm-nbd.conf
        echo "  /etc/modprobe.d/hyper2kvm-nbd.conf"
    fi

    if [ -d "$REPO_ROOT/systemd" ]; then
        UNIT_DIR="/etc/systemd/system"
        install -m 644 "$REPO_ROOT/systemd/hyper2kvm.service" "$UNIT_DIR/"
        install -m 644 "$REPO_ROOT/systemd/hyper2kvm@.service" "$UNIT_DIR/"
        systemctl daemon-reload 2>/dev/null || true
        echo "  $UNIT_DIR/hyper2kvm.service"
    fi

    mkdir -p /var/lib/hyper2kvm /var/log/hyper2kvm
fi

# ---------- Verify ----------
echo ""
echo "=== Verification ==="
"$VENV_DIR/bin/h2kvmctl" --version
"$VENV_DIR/bin/python" -c "import hyper2kvm; print(f'Module: {hyper2kvm.__version__}')"
echo "Python:  $("$VENV_DIR/bin/python" --version)"
echo "Venv:    $VENV_DIR"
echo "Binary:  $(readlink -f "$SYMLINK_DIR/h2kvmctl")"

echo ""
echo "=== Installation complete ==="
echo ""
echo "Quick start:"
echo "  sudo h2kvmctl --version"
echo "  sudo h2kvmctl --config migration.yaml"
echo ""
echo "Uninstall:"
echo "  sudo $0 --uninstall"
