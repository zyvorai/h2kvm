# Building the h2kvm .deb Package

## Prerequisites (Ubuntu/Debian)

```bash
sudo apt install -y python3-all python3-setuptools python3-pip python3-build \
    python3-wheel debhelper dh-python dpkg-dev
```

## Quick Build (with debhelper)

```bash
cd /path/to/h2kvm

# Clean old artifacts
sudo rm -rf dist/ build/ *.egg-info

# Build using dpkg-buildpackage
dpkg-buildpackage -us -uc -b

# The .deb will be in the parent directory
ls -lh ../h2kvm_0.3.0-1_all.deb
```

## Manual Build (without debhelper, works on any Linux)

Use this method when building on a non-Debian system (e.g., Fedora) or in CI:

```bash
cd /path/to/h2kvm

# 1. Clean and build wheel
sudo rm -rf dist/ build/ *.egg-info
python3 -m build --wheel --no-isolation

# 2. Create package tree
DEB=/tmp/h2kvm_0.3.0-1_all
mkdir -p $DEB/usr $DEB/DEBIAN

# 3. Install Python package
python3 -m pip install --no-index --no-deps --root $DEB --prefix /usr \
    --ignore-installed --no-build-isolation dist/h2kvm-0.3.0-py3-none-any.whl

# 4. Install configs
mkdir -p $DEB/etc/h2kvm/migrations
install -m 644 etc/h2kvm/config.yaml.sample $DEB/etc/h2kvm/config.yaml
install -m 644 etc/h2kvm/daemon.yaml.sample $DEB/etc/h2kvm/daemon.yaml
install -m 644 etc/h2kvm/migrations/*.yaml $DEB/etc/h2kvm/migrations/
mkdir -p $DEB/etc/modprobe.d $DEB/etc/sysctl.d $DEB/etc/systemd/system.conf.d
install -m 644 etc/modprobe.d/nbd.conf $DEB/etc/modprobe.d/h2kvm-nbd.conf
install -m 644 etc/sysctl.d/99-h2kvm-nbd.conf $DEB/etc/sysctl.d/
install -m 644 etc/systemd/system.conf.d/h2kvm-limits.conf $DEB/etc/systemd/system.conf.d/

# 5. Install systemd services
mkdir -p $DEB/lib/systemd/system
install -m 644 systemd/h2kvm.service $DEB/lib/systemd/system/
install -m 644 systemd/h2kvm@.service $DEB/lib/systemd/system/

# 6. Install examples and helper scripts
mkdir -p $DEB/usr/share/doc/h2kvm/examples
install -m 644 test-confs/*.yaml $DEB/usr/share/doc/h2kvm/examples/
mkdir -p $DEB/usr/libexec/h2kvm
install -m 755 scripts/install-deps.sh $DEB/usr/libexec/h2kvm/

# 7. Create working dirs
mkdir -p $DEB/var/lib/h2kvm/conversions $DEB/var/log/h2kvm

# 8. Create DEBIAN control
cat > $DEB/DEBIAN/control <<'EOF'
Package: h2kvm
Version: 0.3.0-1
Section: admin
Priority: optional
Architecture: all
Depends: python3, python3-yaml (>= 6.0), qemu-utils
Recommends: libguestfs-tools, python3-pyvmomi, python3-requests, libvirt-clients, libvirt-daemon-system, qemu-kvm, ovmf, virtinst
Suggests: podman | docker.io
Maintainer: ZyvorAI Labs Private Limited <ssahani@zyvor.dev>
Homepage: https://github.com/ssahani/h2kvm
Description: Production-grade hypervisor to KVM/QEMU migration toolkit
 h2kvm migrates virtual machines from VMware vSphere, Hyper-V, Azure,
 AWS, and local disks into reliable, bootable KVM/QEMU systems.
EOF

cat > $DEB/DEBIAN/conffiles <<'EOF'
/etc/h2kvm/config.yaml
/etc/h2kvm/daemon.yaml
/etc/modprobe.d/h2kvm-nbd.conf
/etc/sysctl.d/99-h2kvm-nbd.conf
/etc/systemd/system.conf.d/h2kvm-limits.conf
EOF

cat > $DEB/DEBIAN/postinst <<'EOF'
#!/bin/bash
set -e
mkdir -p /var/lib/h2kvm/conversions /var/log/h2kvm
echo "h2kvm 0.3.0 installed. Run: sudo h2kvmctl --version"
EOF
chmod 755 $DEB/DEBIAN/postinst

# 9. Build the .deb
dpkg-deb --root-owner-group --build $DEB /tmp/
```

## Install (Ubuntu/Debian)

```bash
# Install with dependencies
sudo apt install -y ./h2kvm_0.3.0-1_all.deb

# Or force install (skip dependency resolution)
sudo dpkg -i h2kvm_0.3.0-1_all.deb
sudo apt install -f  # fix missing deps
```

## Verify

```bash
h2kvmctl --version
# Expected: 0.3.0

dpkg -l h2kvm
which h2kvmctl
python3 -c "import h2kvm; print(h2kvm.__version__)"
```

## What the Package Installs

| Path | Description |
|------|-------------|
| `/usr/bin/h2kvmctl` | Primary CLI binary |
| `/usr/lib/python3/dist-packages/h2kvm/` | Python package |
| `/etc/h2kvm/config.yaml` | System configuration |
| `/etc/h2kvm/daemon.yaml` | Daemon mode configuration |
| `/etc/h2kvm/migrations/*.yaml` | Example migration configs |
| `/etc/modprobe.d/h2kvm-nbd.conf` | NBD module config |
| `/lib/systemd/system/h2kvm.service` | Daemon service |
| `/lib/systemd/system/h2kvm@.service` | Template service |
| `/usr/share/doc/h2kvm/examples/` | Example YAML configs |
| `/usr/libexec/h2kvm/install-deps.sh` | Dependency installer |

## Runtime Dependencies (Ubuntu)

```bash
# Required (pulled by .deb)
sudo apt install -y python3-yaml qemu-utils

# Recommended (full functionality)
sudo apt install -y libguestfs-tools qemu-kvm libvirt-clients \
    libvirt-daemon-system ovmf virtinst python3-pyvmomi python3-requests

# Optional
sudo apt install -y podman  # container-isolated LVM
```

## Uninstall

```bash
sudo apt remove h2kvm
# Or purge (remove configs too):
sudo apt purge h2kvm
```
