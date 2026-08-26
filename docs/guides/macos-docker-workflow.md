# macOS Docker Workflow

hyper2kvm requires Linux for guest fixes (VMCraft uses qemu-nbd). On macOS,
use Docker to run the full pipeline.

## Setup

```bash
# Install Docker Desktop for Mac
# https://docs.docker.com/desktop/install/mac-install/

# Install govc (runs natively on macOS)
brew install govc

# Install qemu (qemu-img runs natively)
brew install qemu
```

## Option 1: Use Pre-built Image

```bash
docker run --rm --privileged \
  -v $(pwd)/input:/input \
  -v $(pwd)/output:/output \
  ghcr.io/ssahani/hyper2kvm:latest \
  --cmd local \
  --vmdk /input/vm.vmdk \
  --to-output /output/vm.qcow2 \
  --out-format qcow2 \
  --flatten --compress \
  --fstab-mode stabilize-all \
  --regen-initramfs
```

## Option 2: Build Locally

```bash
# Clone repo
git clone https://github.com/ssahani/hyper2kvm.git
cd hyper2kvm

# Build container
docker build -t hyper2kvm .

# Convert a VMDK
docker run --rm --privileged \
  -v $(pwd):/workspace \
  hyper2kvm \
  --cmd local \
  --vmdk /workspace/photon.vmdk \
  --output-dir /workspace/output \
  --to-output photon.qcow2 \
  --out-format qcow2 \
  --flatten --compress \
  --fstab-mode stabilize-all \
  --regen-initramfs
```

## Option 3: Export from vCenter on Mac, Fix on Linux

```bash
# Step 1: Export on Mac (govc runs natively)
export GOVC_URL='https://vcenter.example.com/sdk'
export GOVC_USERNAME='administrator@vsphere.local'
export GOVC_PASSWORD='password'
export GOVC_INSECURE=1
govc export.ovf -vm MyVM ./exports/

# Step 2: Convert in Docker
docker run --rm --privileged \
  -v $(pwd)/exports:/input \
  -v $(pwd)/output:/output \
  hyper2kvm \
  --cmd local \
  --vmdk /input/MyVM/MyVM-disk-0.vmdk \
  --to-output /output/MyVM.qcow2 \
  --out-format qcow2 \
  --flatten --compress \
  --fstab-mode stabilize-all \
  --regen-initramfs

# Step 3: Transfer to Linux KVM host
scp output/MyVM.qcow2 user@kvm-host:/var/lib/libvirt/images/
```

## Limitations on macOS

| Feature | macOS Native | Docker |
|---------|-------------|--------|
| govc export | Yes | Yes |
| qemu-img convert | Yes | Yes |
| Guest fixes (fstab, initramfs) | No | Yes |
| libvirt/virsh | No | No |
| Boot testing | No | No |

For full functionality (libvirt, boot testing), use a Linux VM or remote host.
