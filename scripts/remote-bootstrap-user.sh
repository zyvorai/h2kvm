#!/bin/bash
# ============================================================================
# remote-bootstrap-user.sh — Create a sudo-capable deploy user on a fresh host
# ============================================================================
# Connects as root (password via SSHPASS + sshpass, or SSH key) and:
#   - creates the user with a home directory and login shell
#   - adds them to wheel (RHEL/Fedora/Alma) or sudo (Debian/Ubuntu)
#   - optionally installs your SSH public key for passwordless login
#
# Usage:
#   export SSHPASS='...'   # root password (never commit; rotate if leaked)
#   ./scripts/remote-bootstrap-user.sh 212.8.252.194 sus --pubkey ~/.ssh/id_ed25519.pub
#
#   # Key-based root login (no password):
#   ./scripts/remote-bootstrap-user.sh 212.8.252.194 sus
#
# Requires: sshpass when using SSHPASS (dnf install sshpass / brew install sshpass)
# ============================================================================

set -euo pipefail

info()  { echo "  ✅ $*"; }
warn()  { echo "  ⚠️  $*"; }
error() { echo "  ❌ $*"; exit 1; }

PUBKEY=""
while [ $# -gt 0 ]; do
    case "$1" in
        --pubkey)
            PUBKEY="${2:-}"
            [ -n "$PUBKEY" ] || error "--pubkey requires a file path"
            shift 2
            ;;
        -h|--help)
            grep -E '^# |^#=|^#-' "$0" | sed 's/^# //' | head -n 30
            exit 0
            ;;
        *)
            break
            ;;
    esac
done

HOST="${1:-}"
USER_NAME="${2:-}"

[ -n "$HOST" ] && [ -n "$USER_NAME" ] || error "Usage: $0 <host> <username> [--pubkey ~/.ssh/id_ed25519.pub]"

if [ -n "$PUBKEY" ] && [ ! -f "$PUBKEY" ]; then
    error "Public key file not found: $PUBKEY"
fi

if [ -n "${SSHPASS:-}" ] && ! command -v sshpass &>/dev/null; then
    error "sshpass is required when SSHPASS is set. Install: dnf install sshpass  (or brew install sshpass)"
fi

ROOT="root@${HOST}"
SSH_BASE=(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=20)

_ssh() {
    if [ -n "${SSHPASS:-}" ]; then
        SSHPASS="$SSHPASS" sshpass -e "${SSH_BASE[@]}" "$ROOT" "$@"
    else
        "${SSH_BASE[@]}" "$ROOT" "$@"
    fi
}

PUBKEY_CONTENT=""
if [ -n "$PUBKEY" ]; then
    PUBKEY_CONTENT=$(cat "$PUBKEY")
fi

info "Bootstrapping user ${USER_NAME} on ${HOST} (as root)…"

_ssh bash -s -- "$USER_NAME" "$PUBKEY_CONTENT" <<'REMOTEBASH'
set -euo pipefail
USER_NAME="$1"
PUBKEY_CONTENT="$2"

if id "$USER_NAME" &>/dev/null; then
  echo "User $USER_NAME already exists — updating groups / SSH key only"
else
  useradd -m -s /bin/bash "$USER_NAME"
  echo "Created user: $USER_NAME"
fi

if getent group wheel &>/dev/null; then
  usermod -aG wheel "$USER_NAME" 2>/dev/null || true
  echo "Added to group: wheel"
elif getent group sudo &>/dev/null; then
  usermod -aG sudo "$USER_NAME" 2>/dev/null || true
  echo "Added to group: sudo"
else
  echo "Warning: no wheel or sudo group found" >&2
fi

# Optional: allow passwordless sudo for deploy (same idea as quick setup)
SUDOERS_D="/etc/sudoers.d/90-${USER_NAME}-deploy"
if [ ! -f "$SUDOERS_D" ]; then
  echo "${USER_NAME} ALL=(ALL) NOPASSWD:ALL" > "$SUDOERS_D"
  chmod 0440 "$SUDOERS_D"
  if command -v visudo &>/dev/null; then
    visudo -cf "$SUDOERS_D" || { rm -f "$SUDOERS_D"; echo "visudo rejected sudoers file" >&2; exit 1; }
  fi
  echo "Installed $SUDOERS_D (passwordless sudo for ${USER_NAME})"
else
  echo "Keeping existing $SUDOERS_D"
fi

if [ -n "$PUBKEY_CONTENT" ]; then
  uhome=$(getent passwd "$USER_NAME" | cut -d: -f6)
  install -d -m 700 -o "$USER_NAME" -g "$USER_NAME" "$uhome/.ssh"
  authkeys="$uhome/.ssh/authorized_keys"
  touch "$authkeys"
  chown "$USER_NAME:$USER_NAME" "$authkeys"
  chmod 600 "$authkeys"
  if ! grep -qF "$PUBKEY_CONTENT" "$authkeys" 2>/dev/null; then
    echo "$PUBKEY_CONTENT" >> "$authkeys"
    echo "Appended SSH public key to $authkeys"
  else
    echo "SSH public key already present in $authkeys"
  fi
fi

echo "Done."
REMOTEBASH

info "You can now: ssh ${USER_NAME}@${HOST}"
info "Then run: ./scripts/deploy-remote.sh <target-host> ${USER_NAME}"
