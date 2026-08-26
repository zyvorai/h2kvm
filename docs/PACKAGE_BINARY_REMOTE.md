# Package h2kvm as a Linux client bundle (remote build)

Ship **h2kvm**, **h2kvmctl**, **h2kweb**, and the dashboard UI as a tarball—without running full `deploy-remote.sh` (systemd, daemon install).

**Distribution model:** this product uses a **Python venv bundle** (type C in `VMRogue/docs/CLIENT_BUNDLE_POLICY.md`), not a single static ELF like Rust/Go products. The customer tarball contains `venv/` + wrapper scripts; **no source tree** and no `pip install` on the customer host (unless they rebuild the venv themselves).

## What you get

```
~/h2kvm-dist/
  h2kvm-<version>-linux-amd64/
    bin/h2kvm        wrapper → `venv/bin/python -m h2kvm`
    bin/h2kvmctl
    bin/h2kweb
    venv/                Python 3.10+ env with package installed
    web/dashboard/       static UI
    config.example.yaml  (from examples/h2kvm-tools.yaml.example)
    h2kweb.env.example
    README.txt
  h2kvm-<version>-linux-amd64.tar.gz
  h2kvm-<version>-linux-amd64.tar.gz.sha256
```

With `--fetch`, files copy to **`dist/`** locally.

## Prerequisites (remote build host)

Build deps (**Python 3.10+**, **go**, **npm**) are installed automatically unless **`--skip-deps`**. **h2kweb** is still built on your laptop (remote lacks libpam for Go).

| Requirement | Notes |
|-------------|--------|
| **Linux x86_64** | Client target arch |
| **go + npm** on laptop | h2kweb + dashboard built locally before rsync |
| **SSH** | Key auth |

## Tarball contents

`README.txt`, `install-client-deps.sh` (wraps `scripts/install-deps.sh`), `test-package.sh`, `venv/`, `bin/`, `web/dashboard/`.

## Build and download

```bash
./scripts/package-binary-remote.sh 212.8.252.194 sus --fetch
```

First run: **10–25 minutes** (pip + npm + Go). Later:

```bash
./scripts/package-binary-remote.sh 212.8.252.194 sus --reuse-build --fetch
```

### Options

| Flag | Effect |
|------|--------|
| `--fetch` | Copy tarball to `./dist/` |
| `--reuse-build` | Skip if `.pkg-venv` + `h2kweb` already exist on remote |

### Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `DEPLOY_HOST` / `DEPLOY_USER` | — / `sus` | When omitted |
| `H2KVM_PACKAGE_DIR` | `~/h2kvm-dist` | Remote output |
| `H2KVM_PACKAGE_VERSION` | `pyproject.toml` | Archive version |
| `H2KVM_REMOTE_SKIP_SSH_CHECK=1` | off | Skip SSH preflight |

## Client quick start

```bash
tar xzf h2kvm-*-linux-amd64.tar.gz
cd h2kvm-*-linux-amd64
./bin/h2kweb --addr 0.0.0.0:5070 --static-dir "$(pwd)/web/dashboard"
# http://<host>:5070
./bin/h2kvm --help
```

Install OS packages on the target host first (`./install.sh --deps-only` from a full checkout, or match your distro libvirt/qemu packages).

## vs `deploy-remote.sh`

| Flow | Use when |
|------|----------|
| **`package-binary-remote.sh`** | Hand off binaries; client owns install |
| **`deploy-remote.sh`** | Full server install (systemd, daemon, h2kweb service) |
