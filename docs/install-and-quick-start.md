# Install and quick start

Install h2kvm, run the first conversion, and find the surfaces (CLI, web, operator, Helm). Moved from the README, wording unchanged.

[Back to the README](../README.md) · [Documentation index](README.md)

---

## Install

**v1.4.0** — on PyPI. GuestKit, the offline repair engine, is the `guestkit` extra.

```bash
pip install "h2kvm[guestkit]==1.4.0"
```

From source (extras / development):

```bash
git clone https://github.com/zyvorai/h2kvm.git
cd h2kvm
pip install -e ".[full]"
```

Host needs Linux with `qemu-img`, `qemu-nbd`, and `losetup`. Repair and NBD mounts often need root or `H2KVM_USE_SUDO=1`.

Shell Completion is optional. Install argcomplete, then see [docs/getting-started/01-Installation.md](getting-started/01-Installation.md#shell-completion-optional).

| Artifact | Where |
|----------|--------|
| **h2kvm 1.4.0** | [PyPI](https://pypi.org/project/h2kvm/1.4.0/) |
| **hypersdk-guestkit ≥ 1.1.0** | [PyPI](https://pypi.org/project/hypersdk-guestkit/) |
| **Operator image** | `ghcr.io/zyvorai/h2kvm/operator:v1.4.0` |

## Quick start

```bash
# Local VMDK → qcow2 (GuestKit repair is the default backend)
h2kvmctl --cmd local --vmdk ubuntu.vmdk --to-output ubuntu.qcow2 --backend guestkit

# vSphere → repair → KubeVirt (there are no subcommands; --cmd picks the mode)
h2kvmctl --cmd vsphere --vcenter vc.example.com --vc-user admin \
  --vc-password-env VC_PASSWORD --vs-vm web-prod-01 \
  --output-dir ./out --to-output web-prod-01.qcow2 --flatten \
  --deploy-k8s --k8s-namespace vms

# Web dashboard
h2kweb
# → https://localhost:5070

# Kubernetes operator
kubectl apply -f operator/deploy/
```

| Surface | What you get |
|---------|----------------|
| **CLI** | `h2kvmctl` / `h2k` |
| **Web** | h2kweb dashboard — `web/` |
| **Operator** | K8s / OpenShift — `operator/`, `olm/` |
| **Helm** | Production charts — `helm/` |
| **Fix engine** | GuestKit `run_migrate_repair` + h2kvm injectors |

| You want… | Go here |
|-----------|---------|
| Full docs | [docs/README.md](README.md) |
| Remote SSH deploy | [docs/deployment/deploy-remote.md](deployment/deploy-remote.md) |
| GuestKit wiring | [docs/architecture/GUESTKIT.md](architecture/GUESTKIT.md) |
| Examples | [examples/](../examples/) |
| CE vs Enterprise | [docs/ce-vs-enterprise.md](ce-vs-enterprise.md) |
