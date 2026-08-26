# AMI & Cloud Image Migration Guide

Migrate Amazon Machine Images (AMI), Azure VHDs, and cloud VM disk images to on-premises KVM infrastructure.

## Supported Cloud Formats

| Cloud | Export Format | h2kvm Input | How to Get |
|-------|-------------|----------------|-----------|
| AWS EC2 | RAW, VMDK, VHD | All formats | `aws ec2 export-image` or AMI tar.gz |
| Azure | VHD (fixed) | Native VHD | `az disk download` or managed disk export |
| GCP | RAW (tar.gz) | RAW extraction | `gcloud compute images export` |
| VMware Cloud | OVA, VMDK | OVA + VMDK | vSphere export or govc |
| Community | RAW (tar.gz) | Direct download | Photon OS, Ubuntu, Fedora cloud images |

## Quick Start: Photon OS AMI

### 1. Download

```bash
wget https://packages.vmware.com/photon/5.0/GA/ami/photon-ami-5.0-dde71ec57.x86_64.tar.gz
tar xzf photon-ami-5.0-dde71ec57.x86_64.tar.gz
```

### 2. Migrate

```bash
sudo h2kvmctl \
  --cmd local \
  --vmdk photon-ami-5.0-dde71ec57.x86_64.raw \
  --out-format qcow2 --compress \
  --fstab-mode stabilize-all \
  --regen-initramfs \
  --emit-domain-xml \
  --libvirt-test \
  --vm-name photon-ami \
  --memory 2048 --vcpus 2
```

### 3. Deploy

```bash
sudo virsh define out/libvirt/photon-ami.xml
sudo virsh start photon-ami
sudo virsh domifaddr photon-ami
```

## YAML Config

```yaml
command: local
vmdk: /path/to/cloud-image.raw
output_dir: ./out
to_output: cloud-vm.qcow2
out_format: qcow2
compress: true
fstab_mode: stabilize-all
regen_initramfs: true
emit_domain_xml: true
libvirt_test: true
vm_name: cloud-vm
memory: 2048
vcpus: 2
headless: true
```

## AWS EC2 Export

### Private AMIs

Export a running AMI from your AWS account:

```bash
# Create export task
aws ec2 export-image \
  --image-id ami-0123456789abcdef0 \
  --disk-image-format RAW \
  --s3-export-location S3Bucket=my-exports,S3Prefix=ami/

# Wait for export
aws ec2 describe-export-image-tasks --export-image-task-ids export-ami-xxx

# Download from S3
aws s3 cp s3://my-exports/ami/export-ami-xxx.raw ./ami-export.raw

# Migrate
sudo h2kvmctl --cmd local --vmdk ./ami-export.raw \
  --out-format qcow2 --compress \
  --fstab-mode stabilize-all --regen-initramfs \
  --emit-domain-xml --vm-name aws-vm
```

### Public AMIs (Community Images)

Many vendors publish downloadable disk images:

| Image | URL | Format |
|-------|-----|--------|
| Photon OS 5.0 AMI | `packages.vmware.com/photon/5.0/GA/ami/` | RAW tar.gz |
| Ubuntu 24.04 | `cloud-images.ubuntu.com/noble/current/` | OVA or qcow2 |
| Fedora Cloud | `download.fedoraproject.org/pub/fedora/linux/releases/` | qcow2 |
| CentOS Stream | `cloud.centos.org/centos/` | qcow2 |

## Azure VHD Export

```bash
# Create SAS URL for managed disk
az disk grant-access --resource-group myRG --name myDisk \
  --duration-in-seconds 3600 --access-level Read

# Download VHD
az storage blob download --account-name myStorage \
  --container-name exports --name disk.vhd --file ./azure-disk.vhd

# Migrate
sudo h2kvmctl --cmd local --vmdk ./azure-disk.vhd \
  --out-format qcow2 --compress \
  --fstab-mode stabilize-all --regen-initramfs \
  --emit-domain-xml --vm-name azure-vm
```

## GCP Image Export

```bash
# Export image to GCS
gcloud compute images export \
  --image my-image \
  --destination-uri gs://my-bucket/my-image.tar.gz \
  --export-format raw

# Download
gsutil cp gs://my-bucket/my-image.tar.gz .
tar xzf my-image.tar.gz

# Migrate
sudo h2kvmctl --cmd local --vmdk ./disk.raw \
  --out-format qcow2 --compress \
  --fstab-mode stabilize-all --regen-initramfs \
  --emit-domain-xml --vm-name gcp-vm
```

## What Gets Fixed Automatically

When migrating cloud images to KVM, h2kvm performs these offline fixes:

### Linux

| Fix | Description |
|-----|-------------|
| **Initramfs rebuild** | Adds virtio_blk, virtio_scsi, virtio_net, nvme drivers via dracut or initramfs-tools |
| **GRUB root= repair** | Updates root device from cloud names (xvda, nvme0n1) to VirtIO topology (vda) |
| **fstab stabilization** | Converts device names to UUID/PARTUUID, adds nofail flags |
| **Network config** | Ensures NetworkManager/systemd-networkd/netplan work with VirtIO NIC |
| **Serial console** | Configures serial console for headless access |

### Windows

| Fix | Description |
|-----|-------------|
| **VirtIO driver injection** | Offline inject viostor, vioscsi, netkvm, balloon from cached virtio-win ISO |
| **Registry editing** | SYSTEM hive: Services, CriticalDeviceDatabase, StartOverride cleanup |
| **VMware tools removal** | Remove VMware service entries from registry |
| **RDP verification** | Check fDenyTSConnections to prevent admin lockout |
| **Firewall staging** | Stage PowerShell script to preserve firewall rules |

## Troubleshooting

### Cloud-init hangs at boot

Cloud images expect a metadata service at 169.254.169.254. On KVM without cloud-init datasource, the VM may wait at boot. Fix:

```bash
# Disable cloud-init before migration (in the guest)
sudo touch /etc/cloud/cloud-init.disabled

# Or set a root password via h2kvm
sudo h2kvmctl --cmd local --vmdk cloud-image.raw \
  --root-password "changeme" \
  --fstab-mode stabilize-all --regen-initramfs
```

### No SSH access after migration

Cloud images typically have no root password and rely on SSH keys from instance metadata. Set credentials before or after migration:

```yaml
# In migration YAML
root_password: "changeme"
ssh_authorized_key: "ssh-rsa AAAA... user@host"
```

### Wrong disk device names in GRUB

If the VM fails to boot with "cannot find root device":

```bash
# Rebuild with explicit GRUB fix
sudo h2kvmctl --cmd local --vmdk image.raw \
  --fstab-mode stabilize-all \
  --regen-initramfs \
  --no-grub false
```

## See Also

- [Client Presentation: AMI to KVM Migration](../../client-presentations/61-ami-to-kvm-migration.pdf) — 8-page deck
- [Client Presentation: Cloud to KVM Repatriation](../../client-presentations/42-cloud-to-kvm-repatriation.pdf) — deep-dive
- [Test Config: Photon OS AMI](../../../test-confs/52-photon-os-ami.yaml) — ready-to-use YAML
