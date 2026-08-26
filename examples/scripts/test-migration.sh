#!/bin/bash
# ============================================
# Test Migrated VM Script
# ============================================
# Description: Test a migrated qcow2 VM with QEMU/libvirt
# Usage: ./test-migration.sh <vm.qcow2>
# ============================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Check arguments
if [ $# -lt 1 ]; then
    echo -e "${RED}Usage: $0 <vm.qcow2> [options]${NC}"
    echo ""
    echo "Options:"
    echo "  --libvirt       Test with libvirt (creates temporary domain)"
    echo "  --qemu          Test with QEMU directly"
    echo "  --uefi          Boot with UEFI firmware"
    echo "  --memory MB     Memory size (default: 2048)"
    echo "  --vnc           Enable VNC console (default: headless)"
    echo ""
    echo "Examples:"
    echo "  $0 vm.qcow2 --qemu"
    echo "  $0 vm.qcow2 --libvirt --uefi --vnc"
    echo "  $0 vm.qcow2 --qemu --memory 4096"
    exit 1
fi

QCOW2_IMAGE="$1"
shift

# Default options
USE_LIBVIRT=false
USE_QEMU=false
USE_UEFI=false
MEMORY=2048
VNC=false

# Parse options
while [[ $# -gt 0 ]]; do
    case $1 in
        --libvirt)
            USE_LIBVIRT=true
            shift
            ;;
        --qemu)
            USE_QEMU=true
            shift
            ;;
        --uefi)
            USE_UEFI=true
            shift
            ;;
        --memory)
            MEMORY="$2"
            shift 2
            ;;
        --vnc)
            VNC=true
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Validate
if [ ! -f "$QCOW2_IMAGE" ]; then
    echo -e "${RED}Error: Image not found: $QCOW2_IMAGE${NC}"
    exit 1
fi

# Default to QEMU if neither specified
if ! $USE_LIBVIRT && ! $USE_QEMU; then
    USE_QEMU=true
fi

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}VM Boot Test${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo -e "Image:       ${YELLOW}$QCOW2_IMAGE${NC}"
echo -e "Memory:      ${YELLOW}${MEMORY}MB${NC}"
echo -e "UEFI:        ${YELLOW}$USE_UEFI${NC}"
echo -e "VNC:         ${YELLOW}$VNC${NC}"
echo ""

# Get image info
echo -e "${BLUE}Image Information:${NC}"
qemu-img info "$QCOW2_IMAGE"
echo ""

# Test with QEMU
if $USE_QEMU; then
    echo -e "${BLUE}Testing with QEMU...${NC}"

    QEMU_BIN=$(command -v qemu-system-x86_64 2>/dev/null || command -v qemu-kvm 2>/dev/null || echo /usr/libexec/qemu-kvm)
    QEMU_CMD=("$QEMU_BIN")
    QEMU_CMD+=(-m "$MEMORY")
    QEMU_CMD+=(-smp 2)
    QEMU_CMD+=(-drive "file=$QCOW2_IMAGE,if=virtio,format=qcow2")
    QEMU_CMD+=(-netdev user,id=net0)
    QEMU_CMD+=(-device virtio-net-pci,netdev=net0)

    if $USE_UEFI; then
        # Check for OVMF firmware in common paths
        OVMF_CODE=""
        for ovmf_path in \
            /usr/share/OVMF/OVMF_CODE.fd \
            /usr/share/edk2/ovmf/OVMF_CODE.fd \
            /usr/share/edk2/x64/OVMF_CODE.fd \
            /usr/share/qemu/OVMF_CODE.fd \
            /usr/share/OVMF/OVMF_CODE.secboot.fd; do
            if [ -f "$ovmf_path" ]; then
                OVMF_CODE="$ovmf_path"
                break
            fi
        done
        if [ -n "$OVMF_CODE" ]; then
            QEMU_CMD+=(-bios "$OVMF_CODE")
        else
            echo -e "${YELLOW}Warning: OVMF firmware not found, using BIOS${NC}"
        fi
    fi

    if $VNC; then
        QEMU_CMD+=(-vnc :0)
        echo -e "${GREEN}VNC console available at: localhost:5900${NC}"
    else
        QEMU_CMD+=(-nographic)
    fi

    # Add serial console for logging
    QEMU_CMD+=(-serial stdio)

    echo ""
    echo -e "${YELLOW}QEMU Command:${NC}"
    printf '%q ' "${QEMU_CMD[@]}"
    echo ""
    echo ""
    echo -e "${YELLOW}Starting VM... Press Ctrl+A then X to exit QEMU${NC}"
    echo ""

    "${QEMU_CMD[@]}"
fi

# Test with libvirt
if $USE_LIBVIRT; then
    echo -e "${BLUE}Testing with libvirt...${NC}"

    VM_NAME="hyper2kvm-test-$(date +%s)"
    DOMAIN_XML=$(mktemp /tmp/${VM_NAME}.XXXXXX.xml)
    trap "rm -f '$DOMAIN_XML'" EXIT

    # Generate libvirt XML
    cat > "$DOMAIN_XML" <<EOF
<domain type='kvm'>
  <name>$VM_NAME</name>
  <memory unit='MiB'>$MEMORY</memory>
  <vcpu>2</vcpu>
  <os>
EOF

    # Auto-detect OVMF for libvirt XML
    LIBVIRT_OVMF=""
    if $USE_UEFI; then
        for ovmf_path in \
            /usr/share/OVMF/OVMF_CODE.fd \
            /usr/share/edk2/ovmf/OVMF_CODE.fd \
            /usr/share/edk2/x64/OVMF_CODE.fd \
            /usr/share/qemu/OVMF_CODE.fd \
            /usr/share/OVMF/OVMF_CODE.secboot.fd; do
            if [ -f "$ovmf_path" ]; then
                LIBVIRT_OVMF="$ovmf_path"
                break
            fi
        done
    fi

    if $USE_UEFI; then
        cat >> "$DOMAIN_XML" <<EOF
    <type arch='x86_64' machine='q35'>hvm</type>
    <loader readonly='yes' type='pflash'>${LIBVIRT_OVMF:-/usr/share/OVMF/OVMF_CODE.fd}</loader>
EOF
    else
        cat >> "$DOMAIN_XML" <<EOF
    <type arch='x86_64' machine='pc'>hvm</type>
EOF
    fi

    cat >> "$DOMAIN_XML" <<EOF
    <boot dev='hd'/>
  </os>
  <features>
    <acpi/>
    <apic/>
  </features>
  <cpu mode='host-passthrough'/>
  <clock offset='utc'/>
  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>destroy</on_crash>
  <devices>
    <emulator>$(command -v qemu-system-x86_64 2>/dev/null || command -v qemu-kvm 2>/dev/null || echo /usr/libexec/qemu-kvm)</emulator>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='$(realpath "$QCOW2_IMAGE")'/>
      <target dev='vda' bus='virtio'/>
    </disk>
    <interface type='network'>
      <source network='default'/>
      <model type='virtio'/>
    </interface>
EOF

    if $VNC; then
        cat >> "$DOMAIN_XML" <<EOF
    <graphics type='vnc' port='-1' autoport='yes' listen='127.0.0.1'/>
    <console type='pty'>
      <target type='serial' port='0'/>
    </console>
EOF
    else
        cat >> "$DOMAIN_XML" <<EOF
    <console type='pty'>
      <target type='serial' port='0'/>
    </console>
EOF
    fi

    cat >> "$DOMAIN_XML" <<EOF
  </devices>
</domain>
EOF

    echo -e "${YELLOW}Libvirt Domain XML:${NC}"
    cat "$DOMAIN_XML"
    echo ""

    # Define and start
    echo -e "${GREEN}Defining domain...${NC}"
    sudo virsh define "$DOMAIN_XML"

    echo -e "${GREEN}Starting VM...${NC}"
    sudo virsh start "$VM_NAME"

    if $VNC; then
        VNC_PORT=$(sudo virsh vncdisplay "$VM_NAME")
        echo ""
        echo -e "${GREEN}VM started successfully!${NC}"
        echo -e "VNC Console: ${YELLOW}$VNC_PORT${NC}"
        echo ""
        echo "Connect with: virt-viewer $VM_NAME"
        echo ""
    else
        echo ""
        echo -e "${GREEN}VM started successfully!${NC}"
        echo ""
        echo "View console: sudo virsh console $VM_NAME"
        echo ""
    fi

    echo -e "${YELLOW}VM will run in background. To manage:${NC}"
    echo "  View status:  sudo virsh list --all"
    echo "  Stop VM:      sudo virsh destroy $VM_NAME"
    echo "  Remove VM:    sudo virsh undefine $VM_NAME"
    echo "  View console: sudo virsh console $VM_NAME"
    echo ""

    # Wait for user
    read -p "Press Enter to stop and cleanup the test VM..." -r
    echo ""

    echo -e "${YELLOW}Stopping VM...${NC}"
    sudo virsh destroy "$VM_NAME" 2>/dev/null || true

    echo -e "${YELLOW}Removing domain...${NC}"
    sudo virsh undefine "$VM_NAME" 2>/dev/null || true

    echo -e "${GREEN}Cleanup complete${NC}"
fi

echo ""
echo -e "${GREEN}Test complete!${NC}"
