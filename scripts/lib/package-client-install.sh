#!/usr/bin/env bash
# Client-side runtime dependencies for hyper2kvm bundle.
# Uses install-deps.sh from the same directory when present.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
if [ -x "${ROOT}/scripts/install-deps.sh" ]; then
  echo "== hyper2kvm: running scripts/install-deps.sh (qemu, guestfs, libvirt) =="
  sudo env HYPER2KVM_REMOTE_INSTALL=1 bash "${ROOT}/scripts/install-deps.sh" --qemu --guestfs --libvirt --ovmf
else
  echo "== hyper2kvm: minimal libvirt/qemu install =="
  SUDO=""
  [ "$(id -u)" -ne 0 ] && command -v sudo &>/dev/null && SUDO=sudo
  if command -v dnf &>/dev/null; then
    $SUDO dnf install -y qemu-kvm qemu-img libvirt virt-install guestfs-tools edk2-ovmf 2>&1 | tail -8
  elif command -v apt-get &>/dev/null; then
    $SUDO apt-get update -qq
    $SUDO apt-get install -y qemu-kvm qemu-utils libvirt-daemon-system virtinst guestfs-tools ovmf 2>&1 | tail -8
  fi
fi
echo "Done."
