# Installing hyper2kvm in a Virtual Environment

Install hyper2kvm in an isolated Python virtual environment on any Linux distribution. This avoids conflicts with system packages and works on Fedora, RHEL, CentOS, Rocky, Alma, Ubuntu, Debian, and SUSE.

## Quick Install

```bash
# Clone the repo
git clone https://github.com/ssahani/hyper2kvm.git
cd hyper2kvm

# Install to /opt/hyper2kvm (recommended)
sudo ./scripts/install-venv.sh

# Or install to a custom path
sudo ./scripts/install-venv.sh /srv/hyper2kvm

# Or install per-user (no sudo needed)
./scripts/install-venv.sh --user
```

## What It Does

1. **Detects your distro** and installs system dependencies (python3, qemu-img, libguestfs-tools, python3-libguestfs)
2. **Creates a Python venv** at `/opt/hyper2kvm` with `--system-site-packages`
3. **Installs hyper2kvm** in editable mode from the source tree
4. **Creates symlinks** in `/usr/local/sbin/` (h2kvmctl, hyper2kvm)
5. **Installs system configs** (/etc/hyper2kvm/, modprobe, systemd units)

## Verify

```bash
h2kvmctl --version
# 0.3.0

which h2kvmctl
# /usr/local/sbin/h2kvmctl -> /opt/hyper2kvm/bin/h2kvmctl
```

## Distro-Specific Notes

### Fedora / RHEL / Rocky / Alma / CentOS

```bash
# System deps installed automatically:
#   python3 python3-pip python3-devel python3-pyyaml qemu-img libguestfs-tools

sudo ./scripts/install-venv.sh

# Optional extras:
sudo dnf install -y libvirt-client libvirt-daemon-kvm edk2-ovmf virt-install
```

### Ubuntu / Debian

```bash
# System deps installed automatically:
#   python3 python3-pip python3-venv python3-dev python3-yaml qemu-utils libguestfs-tools

sudo ./scripts/install-venv.sh

# Optional extras:
sudo apt install -y libvirt-clients libvirt-daemon-system qemu-kvm ovmf virtinst
```

### SUSE / openSUSE

```bash
# System deps installed automatically:
#   python3 python3-pip python3-devel python3-PyYAML qemu-tools libguestfs

sudo ./scripts/install-venv.sh
```

## Per-User Install (No Root)

```bash
# Install to ~/.local/hyper2kvm
./scripts/install-venv.sh --user

# Symlinks go to ~/.local/bin/
# Make sure ~/.local/bin is in your PATH:
export PATH="$HOME/.local/bin:$PATH"

h2kvmctl --version
```

Note: system dependencies (qemu-img, libguestfs-tools) still need root to install.

## Upgrade

Re-run the installer — it upgrades in place:

```bash
cd hyper2kvm
git pull
sudo ./scripts/install-venv.sh
```

## Uninstall

```bash
sudo ./scripts/install-venv.sh --uninstall
```

This removes:
- The venv directory (`/opt/hyper2kvm`)
- Symlinks in `/usr/local/sbin/` and `~/.local/bin/`

System configs in `/etc/hyper2kvm/` are preserved.

## Testing the Install

```bash
# Quick test with a VMDK
cat > /tmp/test.yaml <<'EOF'
cmd: local
vmdk: /path/to/your.vmdk
output_dir: /tmp/hyper2kvm-test
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

## How It Differs from RPM/DEB

| Feature | RPM/DEB | Venv Install |
|---------|---------|-------------|
| System integration | Full (systemd, logrotate, tmpfiles) | Partial (systemd, configs) |
| Upgrade | `dnf upgrade` / `apt upgrade` | `git pull && ./install-venv.sh` |
| Isolation | System Python | Isolated venv |
| Editable | No | Yes (code changes take effect immediately) |
| Multi-version | No | Yes (different venv paths) |
| Uninstall | `dnf remove` / `apt remove` | `./install-venv.sh --uninstall` |
| Best for | Production servers | Development, testing, multi-version |
