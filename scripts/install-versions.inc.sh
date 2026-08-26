# shellcheck shell=bash
# Shared installer artifact pins — sourced by quickstart.sh and install-deps.sh.
# Bump HYPER2KVM_INSTALL_BUNDLE_ID when default URLs or pins change.

: "${HYPER2KVM_INSTALL_BUNDLE_ID:=2026.05.07-hivex-deploy}"

# govc: prefix directory on GitHub releases (latest by default).
: "${HYPER2KVM_GOVC_DOWNLOAD_PREFIX:=https://github.com/vmware/govmomi/releases/latest/download}"

# virtio-win stable ISO (Fedora virtio-win stable stream).
: "${HYPER2KVM_VIRTIO_WIN_ISO_URL:=https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso}"

hyper2kvm_govc_download_url() {
    local arch="$1"
    printf '%s/govc_Linux_%s.tar.gz\n' "${HYPER2KVM_GOVC_DOWNLOAD_PREFIX}" "$arch"
}

# Fallback when distro python3.xx-hivex RPM/deb is missing: build C bindings from source.
# Bump HYPER2KVM_INSTALL_BUNDLE_ID when this pin changes.
: "${HIVEX_UPSTREAM_VERSION:=1.3.24}"
: "${HIVEX_UPSTREAM_TARBALL_URL:=https://github.com/libguestfs/hivex/archive/refs/tags/v${HIVEX_UPSTREAM_VERSION}.tar.gz}"
