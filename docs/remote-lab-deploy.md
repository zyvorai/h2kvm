# Remote lab deploy

One SSH command installs system deps, h2kvm and GuestKit on a target host. The full guide is [deployment/deploy-remote.md](deployment/deploy-remote.md).

[Back to the README](../README.md) · [Documentation index](README.md)

---

One SSH command installs system deps, h2kvm, GuestKit (from PyPI), and optionally h2kweb:

```bash
./scripts/deploy-remote.sh 175.110.122.71 sus --keep-sources

# GuestKit CLI binary (separate repo)
cd /path/to/guestkit
GUESTKIT_ZYVOR_ACCEPT=1 ./scripts/deploy-remote.sh 175.110.122.71 sus --quick --key
```

End-to-end demo on the target (osboxes Ubuntu VMDK):

```bash
sudo bash ~/.deployments/h2kvm/scripts/demo-libvirt.sh \
  ~/demo/ubuntu2404.vmdk ubuntu-test --memory 4096 --vcpus 2
```

Full guide: **[docs/deployment/deploy-remote.md](deployment/deploy-remote.md)**
