# OpenStack deployment (Glance + Nova)

Upload a converted QCOW2 to OpenStack Glance and optionally boot a Nova instance. This uses the same post-conversion hook as KubeVirt (`--deploy-k8s`) and libvirt (`emit_domain_xml` / `virsh_define`).

## Prerequisites

```bash
pip install 'h2kvm[openstack]'
```

Authentication (pick one):

- `export OS_CLOUD=production` (from `~/.config/openstack/clouds.yaml`)
- Source an `openrc` file
- Explicit flags: `--os-auth-url`, `--os-username`, `--os-password`, `--os-project-name`

## CLI / YAML

```yaml
cmd: local
vmdk: /path/to/vm.vmdk
output_dir: ./out
flatten: true
to_output: migrated.qcow2
regen_initramfs: true
fstab_mode: stabilize-all

deploy_openstack: true
glance_name: web-prod
os_cloud: production

# Optional Nova boot
openstack_boot_instance: true
openstack_flavor: m1.medium
openstack_network: <neutron-network-uuid>
openstack_key_name: admin-key
openstack_wait: true
```

```bash
sudo h2kvmctl --config migration-openstack.yaml
```

## Mutual exclusion

Do not combine `deploy_openstack` with `deploy_k8s` or local libvirt define/start on the same run — the disk must not be write-locked during Glance upload. The CLI, web API, and migration wizard enforce this and disable libvirt options when a remote deploy flag is set.

Multi-disk migrations upload **one** Glance image (the first qcow2 output); additional disks are skipped with a log warning.

## Artifact manifest (hypersdk → h2kvm)

```yaml
pipeline:
  openstack:
    enabled: true
    glance_name: my-vm
    os_cloud: production
    boot_instance: true
    flavor: m1.medium
    network: <uuid>
    key_name: admin-key
    wait: true
```

## Web dashboard

In the migration wizard, open **OpenStack** and enable **Upload to Glance**. Set `OS_CLOUD` or use environment credentials on the h2kvm host.

When the host has the `openstack` CLI configured, the job monitor polls Glance/Nova status and instance IPs via `/api/v1/deploy/{vmName}/status` and `/ip`.

## See also

- [examples/yaml/20-openstack/openstack-glance-upload.yaml](../../examples/yaml/20-openstack/openstack-glance-upload.yaml)
- [examples/push_to_openstack.py](../../examples/push_to_openstack.py)
