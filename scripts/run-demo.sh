#!/bin/bash
# ============================================
# hyper2kvm Demo — Download, Convert, Boot
# ============================================
# Downloads a small cloud image, converts it with hyper2kvm,
# and boots it on libvirt — shows a running VM in under 5 minutes.
#
# Usage:
#   sudo ./scripts/run-demo.sh                 # default: Fedora Cloud
#   sudo ./scripts/run-demo.sh --cirros        # tiny 13MB image (fastest)
#   sudo ./scripts/run-demo.sh --fedora        # Fedora Cloud (~400MB)
#   sudo ./scripts/run-demo.sh --ubuntu        # Ubuntu Cloud (~600MB)
#   sudo ./scripts/run-demo.sh --local ./vm.vmdk  # use local VMDK
#   sudo ./scripts/run-demo.sh --cleanup       # remove demo VMs
# ============================================

set -euo pipefail







info()  { echo -e "[OK] $*"; }
warn()  { echo -e "[!!] $*"; }
error() { echo -e "[ERR] $*"; }
step()  { echo -e ">>> $*"; }

usage() {
    cat <<EOF
Usage: sudo $0 [options]

Download a cloud image, convert with hyper2kvm, and boot on libvirt.

Options:
  --photon       VMware Photon OS (default, ~300MB)
  --cirros       CirrOS tiny image (13MB, fastest)
  --fedora       Fedora Cloud (~400MB)
  --ubuntu       Ubuntu Cloud (~600MB)
  --photon-ami   Photon OS AMI (~310MB, cloud repatriation demo)
  --local FILE   Use a local VMDK/OVA file
  --cleanup      Remove demo VMs and images
  --help, -h     Show this help message

Examples:
  sudo $0                        # Default Photon OS
  sudo $0 --cirros               # Fastest demo
  sudo $0 --photon-ami           # AWS AMI migration demo
  sudo $0 --local ./my-vm.vmdk  # Your own image
  sudo $0 --cleanup              # Clean up
EOF
    exit 0
}

DEMO_DIR="./demo-output"
DEMO_NAME="hyper2kvm-demo"
IMAGE_TYPE="${1:---photon}"
LOCAL_DISK=""

# Parse args
case "$IMAGE_TYPE" in
    --help|-h) usage ;;
    --photon)  IMAGE_TYPE="photon" ;;
    --photon-ami) IMAGE_TYPE="photon-ami" ;;
    --cirros)  IMAGE_TYPE="cirros" ;;
    --fedora)  IMAGE_TYPE="fedora" ;;
    --ubuntu)  IMAGE_TYPE="ubuntu" ;;
    --local)   IMAGE_TYPE="local"; LOCAL_DISK="${2:-}"; [ -z "$LOCAL_DISK" ] && error "Usage: $0 --local /path/to/disk.vmdk" && exit 1 ;;
    --cleanup) IMAGE_TYPE="cleanup" ;;
    *)         IMAGE_TYPE="photon" ;;
esac

if [ "$(id -u)" -ne 0 ] && [ "$IMAGE_TYPE" != "cleanup" ]; then
    error "Run as root: sudo $0 $*"
    exit 1
fi

# ── Pre-flight checks ──
preflight() {
    local ok=true

    # Check RAM
    local ram_mb
    ram_mb=$(free -m | awk '/Mem:/{print $2}')
    if [ "$ram_mb" -lt 3500 ]; then
        warn "Low RAM: ${ram_mb}MB (recommend 4GB+)"
    else
        info "RAM: ${ram_mb}MB"
    fi

    # Check disk space
    local free_gb
    free_gb=$(df -BG . | awk 'NR==2{print $4}' | tr -d 'G')
    if [ "$free_gb" -lt 10 ]; then
        error "Low disk space: ${free_gb}GB free (need 10GB+)"
        ok=false
    else
        info "Disk: ${free_gb}GB free"
    fi

    # Check tools
    for tool in h2kvmctl qemu-img virsh; do
        if ! command -v "$tool" &>/dev/null; then
            error "$tool not found — run: sudo ./scripts/quickstart.sh"
            ok=false
        fi
    done

    # Check KVM
    if [ ! -e /dev/kvm ]; then
        warn "/dev/kvm not available — VMs will use emulation (slow)"
    fi

    # Check nbd module
    if ! lsmod | grep -q "^nbd "; then
        modprobe nbd max_part=16 2>/dev/null || warn "Cannot load nbd module"
    fi

    # Check SELinux
    if command -v getenforce &>/dev/null; then
        local se_mode
        se_mode=$(getenforce 2>/dev/null || echo "Unknown")
        if [ "$se_mode" = "Enforcing" ]; then
            info "SELinux: Enforcing (if qemu-nbd fails, try: sudo setenforce 0)"
        fi
    fi

    $ok || { error "Pre-flight failed — fix issues above"; exit 1; }
}

# ── Download image ──
download_image() {
    mkdir -p "$DEMO_DIR"

    case "$IMAGE_TYPE" in
        photon)
            DEMO_NAME="demo-photon"
            local url="https://packages.vmware.com/photon/5.0/Rev2/ova/photon-ova-5.0-dde71ec57.x86_64.ova"
            local disk="$DEMO_DIR/photon.ova"
            # Check for local photon.vmdk first
            if [ -f "./photon.vmdk" ]; then
                disk="./photon.vmdk"
                info "Using local photon.vmdk"
            elif [ ! -f "$disk" ]; then
                step "Downloading Photon OS OVA (~300MB)..."
                curl -fsSL -o "$disk" "$url"
                info "Downloaded: $disk ($(du -h "$disk" | awk '{print $1}'))"
            else
                info "Using cached: $disk"
            fi
            SOURCE_DISK="$disk"
            ;;
        photon-ami)
            DEMO_NAME="demo-photon-ami"
            local url="https://packages.vmware.com/photon/5.0/GA/ami/photon-ami-5.0-dde71ec57.x86_64.tar.gz"
            local tarball="$DEMO_DIR/photon-ami.tar.gz"
            local disk="$DEMO_DIR/photon-ami-5.0-dde71ec57.x86_64.raw"
            if [ ! -f "$disk" ]; then
                if [ ! -f "$tarball" ]; then
                    step "Downloading Photon OS 5.0 AMI (~310MB)..."
                    curl -fsSL -o "$tarball" "$url"
                    info "Downloaded: $tarball ($(du -h "$tarball" | awk '{print $1}'))"
                fi
                step "Extracting AMI raw disk..."
                tar xzf "$tarball" -C "$DEMO_DIR"
                info "Extracted: $disk"
            else
                info "Using cached: $disk"
            fi
            SOURCE_DISK="$disk"
            ;;
        cirros)
            DEMO_NAME="demo-cirros"
            local url="https://download.cirros-cloud.net/0.6.2/cirros-0.6.2-x86_64-disk.img"
            local disk="$DEMO_DIR/cirros.img"
            if [ ! -f "$disk" ]; then
                step "Downloading CirrOS (13MB — fastest demo)..."
                curl -fsSL -o "$disk" "$url"
                info "Downloaded: $disk ($(du -h "$disk" | awk '{print $1}'))"
            else
                info "Using cached: $disk"
            fi
            SOURCE_DISK="$disk"
            ;;
        fedora)
            DEMO_NAME="demo-fedora"
            local url="https://download.fedoraproject.org/pub/fedora/linux/releases/41/Cloud/x86_64/images/Fedora-Cloud-Base-Generic-41-1.4.x86_64.qcow2"
            local disk="$DEMO_DIR/fedora-cloud.qcow2"
            if [ ! -f "$disk" ]; then
                step "Downloading Fedora Cloud (400MB)..."
                curl -fsSL -o "$disk" "$url"
                info "Downloaded: $disk ($(du -h "$disk" | awk '{print $1}'))"
            else
                info "Using cached: $disk"
            fi
            SOURCE_DISK="$disk"
            ;;
        ubuntu)
            DEMO_NAME="demo-ubuntu"
            local url="https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img"
            local disk="$DEMO_DIR/ubuntu-cloud.img"
            if [ ! -f "$disk" ]; then
                step "Downloading Ubuntu Cloud (600MB)..."
                curl -fsSL -o "$disk" "$url"
                info "Downloaded: $disk ($(du -h "$disk" | awk '{print $1}'))"
            else
                info "Using cached: $disk"
            fi
            SOURCE_DISK="$disk"
            ;;
        local)
            if [ ! -f "$LOCAL_DISK" ]; then
                error "File not found: $LOCAL_DISK"
                exit 1
            fi
            DEMO_NAME="demo-local"
            SOURCE_DISK="$LOCAL_DISK"
            info "Using local disk: $SOURCE_DISK"
            ;;
    esac
}

# ── Convert and boot ──
convert_and_boot() {
    step "Converting with hyper2kvm..."

    # Detect format
    local fmt
    fmt=$(qemu-img info --output=json "$SOURCE_DISK" | python3 -c "import sys,json; print(json.load(sys.stdin)['format'])" 2>/dev/null || echo "raw")

    # Cloud images don't need guest fixes (already have virtio drivers)
    # Cloud images already have virtio drivers — skip guest fixes
    # VMware/local disks need full fixes (fstab, initramfs, vmware-tools)
    local skip_fixes="false"
    if [ "$IMAGE_TYPE" = "cirros" ]; then
        skip_fixes="true"
    fi

    # Detect if OVA
    local cmd_type="local"
    local input_key="vmdk"
    if [[ "$SOURCE_DISK" == *.ova ]]; then
        cmd_type="ova"
        input_key="ova"
    fi

    # Create YAML config
    local config="$DEMO_DIR/${DEMO_NAME}.yaml"
    if [ "$skip_fixes" = "true" ]; then
        cat > "$config" << YAMLEOF
# Cloud image — skip guest fixes (already has virtio drivers)
cmd: ${cmd_type}
${input_key}: ${SOURCE_DISK}
output_dir: ${DEMO_DIR}
to_output: ${DEMO_NAME}.qcow2
out_format: qcow2
flatten: true
compress: true

# Skip offline fixes for cloud images
fstab_mode: noop
regen_initramfs: false

emit_domain_xml: true
virsh_define: true
vm_name: ${DEMO_NAME}
memory: 1024
vcpus: 2
uefi: false
machine: q35
disk_bus: virtio
disk_cache: writeback
net_model: virtio
libvirt_network: default
serial_console: true
graphics: vnc
guest_os: linux

libvirt_test: true
keep_domain: true
timeout: 120

verbose: 1
YAMLEOF
    else
        cat > "$config" << YAMLEOF
# VMware/local disk — apply full guest fixes
cmd: ${cmd_type}
${input_key}: ${SOURCE_DISK}
output_dir: ${DEMO_DIR}
to_output: ${DEMO_NAME}.qcow2
out_format: qcow2
flatten: true
compress: true

fstab_mode: stabilize-all
regen_initramfs: true
remove_vmware_tools: true

emit_domain_xml: true
virsh_define: true
vm_name: ${DEMO_NAME}
memory: 1024
vcpus: 2
uefi: false
machine: q35
disk_bus: virtio
disk_cache: writeback
net_model: virtio
libvirt_network: default
serial_console: true
graphics: vnc
guest_os: linux

libvirt_test: true
keep_domain: true
timeout: 120

verbose: 1
YAMLEOF
    fi

    info "Config: $config"

    # Remove old domain if exists
    virsh destroy "$DEMO_NAME" 2>/dev/null || true
    virsh undefine "$DEMO_NAME" --nvram 2>/dev/null || true
    virsh undefine "$DEMO_NAME" 2>/dev/null || true

    # Run hyper2kvm
    h2kvmctl --config "$config"

    # Set root password and enable SSH for demo access
    local output_qcow2="$DEMO_DIR/${DEMO_NAME}.qcow2"
    if [ -f "$output_qcow2" ] && command -v virt-customize &>/dev/null; then
        step "Configuring demo access (root password + SSH)..."
        virsh destroy "$DEMO_NAME" 2>/dev/null || true
        sleep 2
        virt-customize -a "$output_qcow2" \
            --root-password password:hyper2kvm \
            --run-command "sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config" \
            --run-command "sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config" \
            2>/dev/null
        virsh start "$DEMO_NAME" 2>/dev/null || true
        info "Root password set to: hyper2kvm"
        # Wait for VM to boot and get IP
        sleep 15
    fi
}

# ── Show results ──
show_results() {
    echo ""
    echo "============================================"
    echo " Demo Complete"
    echo "============================================"
    echo ""

    local host_ip
    host_ip=$(hostname -I 2>/dev/null | awk '{print $1}')

    # VM status
    if virsh list | grep -q "$DEMO_NAME"; then
        info "VM '$DEMO_NAME' is RUNNING"

        # Wait for VM to get an IP (retry up to 30s)
        local vm_ip=""
        local retries=6
        while [ $retries -gt 0 ] && [ -z "$vm_ip" ]; do
            vm_ip=$(virsh domifaddr "$DEMO_NAME" 2>/dev/null | awk '/ipv4/{print $4}' | cut -d/ -f1 | head -1)
            [ -z "$vm_ip" ] && sleep 5
            retries=$((retries - 1))
        done
        if [ -n "$vm_ip" ]; then
            info "VM IP: $vm_ip"
        else
            warn "VM IP not yet available (run: virsh domifaddr $DEMO_NAME)"
        fi

        # Get VNC display
        local vnc
        vnc=$(virsh vncdisplay "$DEMO_NAME" 2>/dev/null | grep "^:" | head -1 || echo "")
        if [ -n "$vnc" ]; then
            local port_offset="${vnc#:}"
            info "VNC: ${host_ip}:$((5900 + port_offset))"
        fi
    else
        warn "VM '$DEMO_NAME' is not running"
    fi

    # Output files
    echo ""
    info "Output files:"
    ls -lh "$DEMO_DIR/${DEMO_NAME}.qcow2" 2>/dev/null || true
    ls -lh "$DEMO_DIR/libvirt/"*.xml 2>/dev/null || true

    echo ""
    echo "  Access the VM:"
    echo "    virsh console ${DEMO_NAME}          # serial console (Ctrl+] to exit)"
    if [ -n "${vm_ip:-}" ]; then
        echo "    ssh root@${vm_ip}                   # SSH (if enabled)"
    fi
    echo "    virsh vncdisplay ${DEMO_NAME}       # VNC port"
    echo ""
    echo "  Manage:"
    echo "    virsh list                          # see running VMs"
    echo "    virsh domifaddr ${DEMO_NAME}        # VM IP address"
    echo "    virsh shutdown ${DEMO_NAME}         # graceful shutdown"
    echo "    virsh start ${DEMO_NAME}            # start again"
    echo ""

    if [ "$IMAGE_TYPE" = "cirros" ]; then
        echo "  Login: cirros / gocubsgo"
        echo ""
    else
        echo "  Login: root / hyper2kvm"
        echo ""
    fi

    # Cockpit hint
    if systemctl is-active cockpit.socket &>/dev/null; then
        echo "  Cockpit: https://${host_ip}:9090 → Virtual Machines"
        echo ""
    fi

    echo "  Cleanup:"
    echo "    sudo ./scripts/run-demo.sh --cleanup"
    echo ""

    # Auto SSH login
    if [ -n "${vm_ip:-}" ] && command -v sshpass &>/dev/null; then
        echo ""
        read -p "  Connect via SSH now? [Y/n] " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            SSHPASS='hyper2kvm' sshpass -e ssh -o StrictHostKeyChecking=no root@"$vm_ip"
        fi
    elif [ -n "${vm_ip:-}" ]; then
        echo "  Install sshpass for auto-login: dnf install sshpass (or apt install sshpass)"
        echo ""
    fi
}

# ── Cleanup ──
cleanup() {
    step "Cleaning up demo VMs..."
    for vm in demo-cirros demo-fedora demo-ubuntu demo-local demo-photon; do
        virsh destroy "$vm" 2>/dev/null || true
        virsh undefine "$vm" --nvram 2>/dev/null || true
        virsh undefine "$vm" 2>/dev/null || true
    done
    rm -rf "$DEMO_DIR"
    info "Demo cleanup complete"
}

# ── Main ──
if [ "$IMAGE_TYPE" = "cleanup" ]; then
    cleanup
    exit 0
fi

echo ""
echo "============================================"
echo " hyper2kvm Demo ($IMAGE_TYPE)"
echo "============================================"
echo ""

preflight
download_image
convert_and_boot
show_results
