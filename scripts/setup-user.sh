#!/bin/bash
# ============================================
# Setup user permissions for h2kvm
# ============================================
# Adds a user to all required groups for running
# h2kvm, libvirt, QEMU, KVM, and container tools
# without needing sudo for every command.
#
# Usage:
#   sudo ./scripts/setup-user.sh                 # current user
#   sudo ./scripts/setup-user.sh username         # specific user
# ============================================

set -euo pipefail






info()  { echo -e "[INFO] $*"; }
warn()  { echo -e "[WARN] $*"; }
error() { echo -e "[ERROR] $*"; }

if [ "$(id -u)" -ne 0 ]; then
    error "Run as root: sudo $0 [username]"
    exit 1
fi

# Target user
TARGET_USER="${1:-${SUDO_USER:-$(logname 2>/dev/null || echo "")}}"
if [ -z "$TARGET_USER" ] || [ "$TARGET_USER" = "root" ]; then
    error "Usage: sudo $0 <username>"
    error "Cannot setup root — specify a regular user"
    exit 1
fi

if ! id "$TARGET_USER" &>/dev/null; then
    error "User '$TARGET_USER' does not exist"
    exit 1
fi

info "Setting up permissions for user: $TARGET_USER"

# ── Add to groups ──
GROUPS_ADDED=()
GROUPS_SKIPPED=()

for group in libvirt libvirt-qemu kvm qemu disk docker podman; do
    if getent group "$group" &>/dev/null; then
        if id -nG "$TARGET_USER" | grep -qw "$group"; then
            GROUPS_SKIPPED+=("$group")
        else
            usermod -aG "$group" "$TARGET_USER"
            GROUPS_ADDED+=("$group")
            info "  Added to group: $group"
        fi
    fi
done

# ── Polkit rule for libvirt (passwordless virsh for group members) ──
POLKIT_DIR="/etc/polkit-1/rules.d"
POLKIT_RULE="$POLKIT_DIR/50-libvirt.rules"
if [ -d "$POLKIT_DIR" ] && [ ! -f "$POLKIT_RULE" ]; then
    cat > "$POLKIT_RULE" << 'EOF'
/* Allow members of libvirt group to manage VMs without password */
polkit.addRule(function(action, subject) {
    if (action.id == "org.libvirt.unix.manage" &&
        subject.isInGroup("libvirt")) {
        return polkit.Result.YES;
    }
});
EOF
    info "  Created polkit rule: $POLKIT_RULE"
fi

# ── Sudoers for h2kvm commands (passwordless) ──
SUDOERS_FILE="/etc/sudoers.d/h2kvm-${TARGET_USER}"
if [ ! -f "$SUDOERS_FILE" ]; then
    cat > "$SUDOERS_FILE" << EOF
# Allow $TARGET_USER to run h2kvm migration tools without password
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/local/sbin/h2kvmctl
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/local/bin/h2kvmctl
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/h2kvmctl
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/qemu-img
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/qemu-nbd
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/virsh
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/virt-install
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/sbin/modprobe
# mount/umount restricted to NBD devices and h2kvm temp dirs only
# (trade-off: allows passwordless mount of any NBD partition to /tmp/h2kvm-*)
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/mount /dev/nbd* /tmp/h2kvm-*
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/umount /tmp/h2kvm-*
EOF
    chmod 0440 "$SUDOERS_FILE"
    visudo -cf "$SUDOERS_FILE" &>/dev/null || {
        error "Invalid sudoers file — removing"
        rm -f "$SUDOERS_FILE"
    }
    info "  Created sudoers: $SUDOERS_FILE"
fi

# ── Set ACLs on common directories ──
for dir in /var/lib/libvirt/images /var/lib/h2kvm /var/log/h2kvm; do
    if [ -d "$dir" ]; then
        setfacl -m "u:${TARGET_USER}:rwx" "$dir" 2>/dev/null || \
            chmod 775 "$dir" 2>/dev/null || true
    fi
done

# ── Enable lingering for systemd user services ──
loginctl enable-linger "$TARGET_USER" 2>/dev/null || true

# ── Summary ──
echo ""
info "=== Setup Complete for $TARGET_USER ==="
echo ""
if [ ${#GROUPS_ADDED[@]} -gt 0 ]; then
    info "Groups added: ${GROUPS_ADDED[*]}"
fi
if [ ${#GROUPS_SKIPPED[@]} -gt 0 ]; then
    info "Groups already member: ${GROUPS_SKIPPED[*]}"
fi
echo ""
echo "  Permissions granted:"
echo "    - libvirt: manage VMs (virsh, virt-install) without password"
echo "    - kvm/qemu: direct KVM/QEMU access"
echo "    - disk: raw disk device access"
echo "    - docker/podman: container tools (if installed)"
echo "    - sudoers: h2kvmctl, qemu-img, virsh without password"
echo ""
echo "  IMPORTANT: Log out and back in for group changes to take effect."
echo "  Or run: newgrp libvirt"
echo ""
echo "  Test:"
echo "    virsh list --all"
echo "    sudo h2kvmctl --version"
echo ""
