#!/bin/bash
# Import converted QCOW2 to libvirt
set -euo pipefail

QCOW2_FILE="${1:-output/rhel8.8-fixed.qcow2}"
VM_NAME="${2:-rhel88-imported}"
VM_RAM="${3:-4096}"  # 4GB RAM
VM_VCPUS="${4:-2}"
OS_VARIANT="${OS_VARIANT:-auto}"

echo "════════════════════════════════════════════════"
echo "  Import QCOW2 to Libvirt/KVM"
echo "════════════════════════════════════════════════"
echo ""
echo "QCOW2 File: $QCOW2_FILE"
echo "VM Name:    $VM_NAME"
echo "RAM:        ${VM_RAM} MB"
echo "vCPUs:      $VM_VCPUS"
echo ""

# Check if file exists
if [ ! -f "$QCOW2_FILE" ]; then
    echo "❌ Error: $QCOW2_FILE not found"
    exit 1
fi

# Get image info
echo "📊 Image Information:"
qemu-img info "$QCOW2_FILE" | grep -E "virtual size|disk size|format"
echo ""

# Copy to libvirt images directory
LIBVIRT_DIR="/var/lib/libvirt/images"
DEST_IMAGE="$LIBVIRT_DIR/${VM_NAME}.qcow2"

echo "📁 Copying image to libvirt directory..."
sudo cp "$QCOW2_FILE" "$DEST_IMAGE"
sudo chown qemu:qemu "$DEST_IMAGE" 2>/dev/null || sudo chown libvirt-qemu:kvm "$DEST_IMAGE"
sudo chmod 600 "$DEST_IMAGE"
echo "   ✓ Copied to: $DEST_IMAGE"
echo ""

# Create VM with virt-install
echo "🚀 Creating VM with virt-install..."
if sudo virt-install \
    --name "$VM_NAME" \
    --memory "$VM_RAM" \
    --vcpus "$VM_VCPUS" \
    --disk path="$DEST_IMAGE",format=qcow2,bus=virtio \
    --import \
    --os-variant "$OS_VARIANT" \
    --network network=default,model=virtio \
    --graphics vnc,listen=127.0.0.1 \
    --video virtio \
    --channel unix,target_type=virtio,name=org.qemu.guest_agent.0 \
    --noautoconsole; then
    echo ""
    echo "════════════════════════════════════════════════"
    echo "✅ VM Created Successfully!"
    echo "════════════════════════════════════════════════"
    echo ""
    echo "VM Name: $VM_NAME"
    echo "Status:  $(sudo virsh domstate "$VM_NAME")"
    echo ""
    echo "Useful Commands:"
    echo "  Start:      sudo virsh start $VM_NAME"
    echo "  Console:    sudo virsh console $VM_NAME"
    echo "  VNC:        virt-viewer $VM_NAME"
    echo "  Info:       sudo virsh dominfo $VM_NAME"
    echo "  Edit:       sudo virsh edit $VM_NAME"
    echo "  Delete:     sudo virsh undefine $VM_NAME --remove-all-storage"
    echo ""
else
    echo ""
    echo "❌ VM creation failed!"
    echo ""
    echo "Cleanup:"
    echo "  sudo rm -f $DEST_IMAGE"
    exit 1
fi
