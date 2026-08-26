# Building the h2kvm RPM

## Prerequisites

```bash
sudo dnf install -y rpm-build python3-devel python3-setuptools python3-pip \
    python3-wheel python3-build python3-sphinx python3-sphinx_rtd_theme make \
    systemd-rpm-macros
```

## Quick Build

```bash
cd /path/to/h2kvm

# 1. Clean old build artifacts
sudo rm -rf dist/ build/ *.egg-info

# 2. Build the Python wheel
python3 -m build --wheel --no-isolation

# 3. Create RPM build tree
mkdir -p ~/rpmbuild/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

# 4. Create source tarball
tar czf ~/rpmbuild/SOURCES/h2kvm-0.3.0.tar.gz \
    --transform 's,^,h2kvm-0.3.0/,' \
    --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='*.egg-info' --exclude='build' \
    --exclude='*.vmdk' --exclude='*.qcow2' --exclude='*.ova' \
    --exclude='*.vhd' --exclude='*.raw' --exclude='*.pdf' \
    --exclude='docs/pdf' --exclude='out-*' \
    --exclude='.claude' --exclude='node_modules' \
    .

# 5. Build the RPM
rpmbuild -bb h2kvm.spec
```

The RPM will be at `~/rpmbuild/RPMS/noarch/h2kvm-0.3.0-1.*.noarch.rpm`.

## Install

```bash
# Fresh install
sudo dnf install -y ~/rpmbuild/RPMS/noarch/h2kvm-0.3.0-1.*.noarch.rpm

# Upgrade from previous version
sudo rpm -Uvh ~/rpmbuild/RPMS/noarch/h2kvm-0.3.0-1.*.noarch.rpm

# Force reinstall (if same version)
sudo rpm -Uvh --force ~/rpmbuild/RPMS/noarch/h2kvm-0.3.0-1.*.noarch.rpm
```

## Verify Installation

```bash
# Check version
h2kvmctl --version
# Expected: 0.3.0

# Check installed files
rpm -ql h2kvm | head -20

# Check Python module
python3 -c "import h2kvm; print(h2kvm.__version__)"

# Check binary location
which h2kvmctl
# Expected: /usr/bin/h2kvmctl
```

## What the RPM Installs

| Path | Description |
|------|-------------|
| `/usr/bin/h2kvmctl` | Primary CLI binary |
| `/usr/lib/python3.*/site-packages/h2kvm/` | Python package |
| `/etc/h2kvm/config.yaml` | System-wide configuration |
| `/etc/h2kvm/daemon.yaml` | Daemon mode configuration |
| `/etc/h2kvm/migrations/*.yaml` | Example migration configs |
| `/etc/modprobe.d/h2kvm-nbd.conf` | NBD module config (max_part=16) |
| `/etc/sysctl.d/99-h2kvm-nbd.conf` | File descriptor limits |
| `/usr/lib/systemd/system/h2kvm.service` | Daemon service unit |
| `/usr/lib/systemd/system/h2kvm@.service` | Template service unit |
| `/usr/share/doc/h2kvm/` | Documentation |
| `/usr/share/man/man1/h2kvm*.1` | Man pages |
| `/var/lib/h2kvm/` | Working data directory |
| `/var/log/h2kvm/` | Log directory |

## Runtime Dependencies

**Required** (pulled by RPM):
- `python3-pyyaml`, `python3-click`, `python3-argcomplete`, `qemu-img`, `systemd`

**Recommended** (install for full functionality):
```bash
sudo dnf install -y libguestfs-tools qemu-kvm libvirt-client \
    libvirt-daemon-kvm edk2-ovmf virt-install python3-pyvmomi python3-requests
```

**Optional**:
- `virtio-win` — Windows VirtIO driver ISO (for Windows VM migration)
- `govc` — VMware vSphere CLI (for vSphere export)
- `podman` — Container isolation for LVM operations

## Test After Install

```bash
# Run a migration
sudo h2kvmctl --config /etc/h2kvm/migrations/photon-example.yaml

# Or create a test config
cat > /tmp/test.yaml <<'EOF'
cmd: local
vmdk: /path/to/your.vmdk
output_dir: /tmp/h2kvm-test
flatten: true
out_format: qcow2
regen_initramfs: true
emit_domain_xml: true
vm_name: test-vm
memory: 2048
vcpus: 2
machine: q35
EOF
sudo h2kvmctl --config /tmp/test.yaml
```

## Updating the Spec for New Releases

1. Update `Version:` in `h2kvm.spec`
2. Reset `Release:` to `1%{?dist}`
3. Update `__version__` in `h2kvm/__init__.py` and `pyproject.toml`
4. Add a `%changelog` entry
5. Rebuild: `python3 -m build --wheel --no-isolation && rpmbuild -bb h2kvm.spec`

## Troubleshooting

**"conflicting requests: nothing provides user(h2kvm)"**
The RPM creates a system user in `%pre`. Use `rpm -Uvh` instead of `dnf install`, or run: `sudo useradd -r -s /sbin/nologin h2kvm` first.

**"Could not install packages: Permission denied"**
A previous version is pip-installed system-wide. The spec uses `--ignore-installed` to handle this. If you still see it, uninstall first: `sudo pip uninstall h2kvm`.

**Stale 0.2.x wheel in dist/**
Clean before building: `sudo rm -rf dist/ build/ *.egg-info`. The `dist/*.whl` glob must match only one wheel.
