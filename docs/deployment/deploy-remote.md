# Remote bare-metal / VM deployment (`deploy-remote.sh`)

Deploy h2kvm, system dependencies, GuestKit Python bindings, and optionally the h2kweb dashboard to a Linux host over SSH with a single command.

## Quick start

```bash
cd h2kvm
./scripts/deploy-remote.sh 175.110.122.71 sus
```

**Requirements on the target host:**
- SSH access (key or password via `sshpass`)
- Python ≥ 3.10
- Passwordless sudo recommended for non-root users (long pip installs)
- ~20 GB free disk for conversion work + demo images

## What gets installed

| Component | Result |
|-----------|--------|
| System packages | qemu, libvirt, KVM, OVMF, nbdkit, guestfs-tools, hivex, virtio-win ISO |
| **h2kvm** | `pip install .[full]` → `/usr/local/bin/h2kvmctl` |
| **GuestKit Python** | `hypersdk-guestkit>=1.1.0` from [PyPI](https://pypi.org/project/hypersdk-guestkit/) |
| **h2kweb** | Go binary + React dashboard on port **5070** (HTTPS, auto TLS cert) |
| **h2kvm daemon** | systemd unit watching `/var/lib/h2kvm/queue` |
| Runtime dirs | `/run/h2kvm`, `/var/lib/h2kvm` (mode **755** for QEMU read access) |

## Deploy GuestKit CLI alongside h2kvm

h2kvm depends on the **Python** package `hypersdk-guestkit` (**1.1.0+** on PyPI). The standalone **GuestKit CLI** (`guestkit` binary) is deployed separately:

```bash
cd /path/to/guestkit
GUESTKIT_ZYVOR_ACCEPT=1 ./scripts/deploy-remote.sh 175.110.122.71 sus --quick --key
```

Optional: install GuestKit Python alone:

```bash
pip install "hypersdk-guestkit>=1.1.0"
```

For development wheels, build with maturin from a GuestKit checkout (see [GUESTKIT.md](../architecture/GUESTKIT.md)).

## Script options

```bash
./scripts/deploy-remote.sh <host> [user] [password] [options]
```

| Flag | Description |
|------|-------------|
| *(default)* | Full deploy: quickstart + deps + pip + h2kweb + smoke tests |
| `--quick` | Skip `quickstart.sh`; rsync + pip only |
| `--keep-sources` | Retain checkout at `~/.deployments/h2kvm` after install |
| `--skip-dashboard` | Skip h2kweb build/deploy |
| `--skip-smoke` | Skip HTTPS endpoint smoke tests |
| `--dry-run` | Print planned steps only |
| `--verbose` | Full remote logs (no highlight filtering) |
| `--uninstall` | Remove h2kvm pip package and remote checkout |

**Environment variables:** `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_PASS`, `DEPLOY_DIR`

## Supported targets

| OS family | Notes |
|-----------|--------|
| AlmaLinux / RHEL / Rocky / CentOS Stream 9 | CRB/powertools for `augeas-devel`; `guestfs-tools` provides `virt-filesystems` |
| Ubuntu / Debian | `libguestfs-tools`, `libaugeas-dev`, `ufw` for port 5070 |
| macOS (local only) | Use `deploy-local.sh`; remote target must be Linux |

## Post-deploy verification

```bash
ssh sus@HOST 'h2kvmctl --version'
ssh sus@HOST 'python3.12 -c "import guestkit; print(hasattr(guestkit,\"run_migrate_repair\"))"'
ssh sus@HOST 'curl -sk https://localhost:5070/api/v1/health'
ssh sus@HOST 'sudo virsh list --all'
```

## VMDK → libvirt lab workflow

After deploy, run an end-to-end conversion (example: osboxes.org Ubuntu 24.04):

```bash
# On target — download + migrate
mkdir -p ~/demo
curl -fL -o ~/demo/ubuntu.7z \
  'https://sourceforge.net/projects/osboxes/files/v/vm/55-U--u/24.04/64bit.7z/download'
7z x -o~/demo/extract ~/demo/ubuntu.7z
sudo bash ~/.deployments/h2kvm/scripts/demo-libvirt.sh \
  ~/demo/ubuntu2404.vmdk ubuntu-test --memory 4096 --vcpus 2
```

Credentials for osboxes images: `osboxes` / `osboxes.org`

See [GuestKit integration](../architecture/GUESTKIT.md) and [troubleshooting](../guides/troubleshooting.md#permissions-and-ownership).

## h2kweb build model

- **Frontend:** built locally with `npm ci && npm run build` in `web/dashboard/`
- **Backend:** compiled on the remote Linux host (`go build` with PAM/CGO)
- Dashboard static files: `/usr/local/share/h2kweb/dashboard/`
- Default URL: `https://<host>:5070/`

## Uninstall

```bash
./scripts/deploy-remote.sh HOST sus --uninstall
```

Keeps system packages (qemu, libvirt) and `/var/lib/h2kvm/virtio-win.iso`.

## See also

- [scripts/README.md](../../scripts/README.md) — all deploy scripts
- [PACKAGE_BINARY_REMOTE.md](../PACKAGE_BINARY_REMOTE.md) — customer tarball without deploy scripts
- [GuestKit integration](../architecture/GUESTKIT.md)
- [GuestKit deploy-remote](https://github.com/hypersdk/guestkit/blob/main/docs/guides/DEPLOY-REMOTE.md) — CLI-only deploy
