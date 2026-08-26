#!/bin/bash
# build-deb.sh — Build h2kvm .deb package for Debian/Ubuntu
#
# Usage:
#   ./scripts/build-deb.sh              # build on current system
#   ./scripts/build-deb.sh ubuntu:24.04  # build inside container
#   ./scripts/build-deb.sh debian:12     # build inside container
#
# Output: dist/h2kvm_<version>-1_all.deb

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VERSION=$(grep '^version' "$REPO_ROOT/pyproject.toml" | head -1 | sed 's/.*"\(.*\)"/\1/')
DEB_NAME="h2kvm_${VERSION}-1_all"
CONTAINER_IMAGE="${1:-}"

echo "=== h2kvm .deb builder ==="
echo "Version: $VERSION"
echo "Source:  $REPO_ROOT"

# ---------- Container mode ----------
if [ -n "$CONTAINER_IMAGE" ]; then
    echo "Building inside container: $CONTAINER_IMAGE"
    RUNTIME="podman"
    command -v podman >/dev/null 2>&1 || RUNTIME="docker"

    $RUNTIME run --rm \
        -v "$REPO_ROOT:/src:ro" \
        -v "$REPO_ROOT/dist:/out" \
        "$CONTAINER_IMAGE" bash -c "
            set -e
            apt-get update -qq
            apt-get install -y -qq python3 python3-pip python3-build python3-venv \
                python3-yaml python3-setuptools qemu-utils dpkg-dev >/dev/null 2>&1

            cp -a /src /tmp/build && cd /tmp/build
            rm -rf dist/ build/ *.egg-info

            python3 -m build --wheel 2>&1 | tail -1

            DEB=/tmp/${DEB_NAME}
            mkdir -p \$DEB/usr \$DEB/DEBIAN

            python3 -m pip install --no-index --no-deps --root \$DEB --prefix /usr \
                --ignore-installed --break-system-packages \
                dist/h2kvm-${VERSION}-py3-none-any.whl 2>&1 | tail -1

            # Configs
            mkdir -p \$DEB/etc/h2kvm/migrations
            cp etc/h2kvm/config.yaml.sample \$DEB/etc/h2kvm/config.yaml
            cp etc/h2kvm/daemon.yaml.sample \$DEB/etc/h2kvm/daemon.yaml
            cp etc/h2kvm/README.md \$DEB/etc/h2kvm/
            cp etc/h2kvm/migrations/*.yaml \$DEB/etc/h2kvm/migrations/

            mkdir -p \$DEB/etc/modprobe.d \$DEB/etc/sysctl.d \$DEB/etc/systemd/system.conf.d
            cp etc/modprobe.d/nbd.conf \$DEB/etc/modprobe.d/h2kvm-nbd.conf
            cp etc/sysctl.d/99-h2kvm-nbd.conf \$DEB/etc/sysctl.d/
            cp etc/systemd/system.conf.d/h2kvm-limits.conf \$DEB/etc/systemd/system.conf.d/

            # Systemd + docs
            mkdir -p \$DEB/lib/systemd/system
            cp systemd/h2kvm.service \$DEB/lib/systemd/system/
            cp systemd/h2kvm@.service \$DEB/lib/systemd/system/
            mkdir -p \$DEB/usr/share/doc/h2kvm/examples
            cp test-confs/*.yaml \$DEB/usr/share/doc/h2kvm/examples/
            mkdir -p \$DEB/usr/libexec/h2kvm
            cp scripts/install-deps.sh \$DEB/usr/libexec/h2kvm/
            chmod 755 \$DEB/usr/libexec/h2kvm/install-deps.sh
            mkdir -p \$DEB/var/lib/h2kvm \$DEB/var/log/h2kvm

            # DEBIAN metadata
            cat > \$DEB/DEBIAN/control <<CTRL
Package: h2kvm
Version: ${VERSION}-1
Section: admin
Priority: optional
Architecture: all
Depends: python3, python3-yaml (>= 6.0), qemu-utils
Recommends: libguestfs-tools, libvirt-clients, libvirt-daemon-system, qemu-kvm, ovmf, virtinst
Suggests: podman | docker.io
Maintainer: ZyvorAI Labs Private Limited <ssahani@zyvor.dev>
Homepage: https://github.com/ssahani/h2kvm
Description: Production-grade hypervisor to KVM/QEMU migration toolkit
 Migrate VMs from VMware, Hyper-V, Azure, AWS to KVM/QEMU.
 Automated guest fixes, VirtIO injection, libvirt/KubeVirt deploy.
CTRL

            cat > \$DEB/DEBIAN/conffiles <<CONF
/etc/h2kvm/config.yaml
/etc/h2kvm/daemon.yaml
/etc/modprobe.d/h2kvm-nbd.conf
/etc/sysctl.d/99-h2kvm-nbd.conf
/etc/systemd/system.conf.d/h2kvm-limits.conf
CONF

            printf '#!/bin/bash\nset -e\nmkdir -p /var/lib/h2kvm /var/log/h2kvm\necho \"h2kvm ${VERSION} installed. Run: sudo h2kvmctl --version\"\n' > \$DEB/DEBIAN/postinst
            chmod 755 \$DEB/DEBIAN/postinst

            dpkg-deb --root-owner-group --build \$DEB /out/ 2>&1
            echo \"=== Built: /out/${DEB_NAME}.deb ===\"
        "
    echo ""
    ls -lh "$REPO_ROOT/dist/${DEB_NAME}.deb"
    echo "Done. Install with: sudo apt install -y ./dist/${DEB_NAME}.deb"
    exit 0
fi

# ---------- Native mode (run on Debian/Ubuntu host) ----------
echo "Building natively..."

if ! command -v dpkg-deb >/dev/null 2>&1; then
    echo "ERROR: dpkg-deb not found. Install dpkg or use container mode:"
    echo "  $0 ubuntu:24.04"
    exit 1
fi

cd "$REPO_ROOT"
rm -rf dist/ build/ *.egg-info

# Build wheel
if python3 -m build --help >/dev/null 2>&1; then
    python3 -m build --wheel 2>&1 | tail -1
else
    pip3 install --break-system-packages build 2>/dev/null || pip3 install build
    python3 -m build --wheel 2>&1 | tail -1
fi

# Create deb tree
DEB="/tmp/${DEB_NAME}"
rm -rf "$DEB"
mkdir -p "$DEB/usr" "$DEB/DEBIAN"

python3 -m pip install --no-index --no-deps --root "$DEB" --prefix /usr \
    --ignore-installed --break-system-packages \
    "dist/h2kvm-${VERSION}-py3-none-any.whl" 2>&1 | tail -1

# Install configs
mkdir -p "$DEB/etc/h2kvm/migrations"
install -m 644 etc/h2kvm/config.yaml.sample "$DEB/etc/h2kvm/config.yaml"
install -m 644 etc/h2kvm/daemon.yaml.sample "$DEB/etc/h2kvm/daemon.yaml"
install -m 644 etc/h2kvm/README.md "$DEB/etc/h2kvm/"
install -m 644 etc/h2kvm/migrations/*.yaml "$DEB/etc/h2kvm/migrations/"
mkdir -p "$DEB/etc/modprobe.d" "$DEB/etc/sysctl.d" "$DEB/etc/systemd/system.conf.d"
install -m 644 etc/modprobe.d/nbd.conf "$DEB/etc/modprobe.d/h2kvm-nbd.conf"
install -m 644 etc/sysctl.d/99-h2kvm-nbd.conf "$DEB/etc/sysctl.d/"
install -m 644 etc/systemd/system.conf.d/h2kvm-limits.conf "$DEB/etc/systemd/system.conf.d/"

# Systemd + docs
mkdir -p "$DEB/lib/systemd/system"
install -m 644 systemd/h2kvm.service "$DEB/lib/systemd/system/"
install -m 644 systemd/h2kvm@.service "$DEB/lib/systemd/system/"
mkdir -p "$DEB/usr/share/doc/h2kvm/examples"
install -m 644 test-confs/*.yaml "$DEB/usr/share/doc/h2kvm/examples/"
mkdir -p "$DEB/usr/libexec/h2kvm"
install -m 755 scripts/install-deps.sh "$DEB/usr/libexec/h2kvm/"
mkdir -p "$DEB/var/lib/h2kvm" "$DEB/var/log/h2kvm"

# DEBIAN metadata
cat > "$DEB/DEBIAN/control" <<CTRL
Package: h2kvm
Version: ${VERSION}-1
Section: admin
Priority: optional
Architecture: all
Depends: python3, python3-yaml (>= 6.0), qemu-utils
Recommends: libguestfs-tools, libvirt-clients, libvirt-daemon-system, qemu-kvm, ovmf, virtinst
Suggests: podman | docker.io
Maintainer: ZyvorAI Labs Private Limited <ssahani@zyvor.dev>
Homepage: https://github.com/ssahani/h2kvm
Description: Production-grade hypervisor to KVM/QEMU migration toolkit
 Migrate VMs from VMware, Hyper-V, Azure, AWS to KVM/QEMU.
 Automated guest fixes, VirtIO injection, libvirt/KubeVirt deploy.
CTRL

cat > "$DEB/DEBIAN/conffiles" <<CONF
/etc/h2kvm/config.yaml
/etc/h2kvm/daemon.yaml
/etc/modprobe.d/h2kvm-nbd.conf
/etc/sysctl.d/99-h2kvm-nbd.conf
/etc/systemd/system.conf.d/h2kvm-limits.conf
CONF

printf '#!/bin/bash\nset -e\nmkdir -p /var/lib/h2kvm /var/log/h2kvm\necho "h2kvm %s installed. Run: sudo h2kvmctl --version"\n' "$VERSION" > "$DEB/DEBIAN/postinst"
chmod 755 "$DEB/DEBIAN/postinst"

# Build
mkdir -p "$REPO_ROOT/dist"
dpkg-deb --root-owner-group --build "$DEB" "$REPO_ROOT/dist/" 2>&1
rm -rf "$DEB"

echo ""
ls -lh "$REPO_ROOT/dist/${DEB_NAME}.deb"
echo "Done. Install with: sudo apt install -y ./dist/${DEB_NAME}.deb"
