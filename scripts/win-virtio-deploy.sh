#!/bin/bash
# =============================================================================
# Multi-stage Windows VirtIO deployment
# =============================================================================
# Stage 1: Boot with SATA + VirtIO ISO attached → Windows auto-installs drivers
# Stage 2: Shut down, verify drivers installed via offline registry check
# Stage 3: Update domain XML to use VirtIO disk bus permanently
# Stage 4: Boot with VirtIO to confirm
#
# Usage:
#   sudo ./scripts/win-virtio-deploy.sh <qcow2> <virtio-iso> [vm-name]
#
# Example:
#   sudo ./scripts/win-virtio-deploy.sh output-win10/win10-converted.qcow2 \
#     /home/ssahani/Downloads/virtio-win-0.1.285.iso win10-converted
# =============================================================================

set -euo pipefail


log()  { echo "[Stage] $1"; }
ok()   { echo "✅   ✓ $1"; }
warn() { echo "⚠️   ! $1"; }
err()  { echo "❌   ✗ $1"; }
die()  { err "$1"; exit 1; }

QCOW2="${1:-}"
VIRTIO_ISO="${2:-}"
VM_NAME="${3:-win10-converted}"
TIMEOUT_BOOT="${WIN_BOOT_TIMEOUT:-120}"
TIMEOUT_INSTALL="${WIN_INSTALL_TIMEOUT:-180}"

[ -n "$QCOW2" ] || die "Usage: $0 <qcow2> <virtio-iso> [vm-name]"
[ -f "$QCOW2" ] || die "QCOW2 not found: $QCOW2"
[ -n "$VIRTIO_ISO" ] || die "VirtIO ISO path required"
[ -f "$VIRTIO_ISO" ] || die "VirtIO ISO not found: $VIRTIO_ISO"

QCOW2=$(realpath "$QCOW2")
VIRTIO_ISO=$(realpath "$VIRTIO_ISO")
OUTPUT_DIR=$(dirname "$QCOW2")
XML_BOOTSTRAP="$OUTPUT_DIR/libvirt/${VM_NAME}-bootstrap.xml"
XML_FINAL="$OUTPUT_DIR/libvirt/${VM_NAME}-final.xml"

# Find a free NBD device
modprobe nbd max_part=16 2>/dev/null || true

NBD_DEV=""
for dev in /dev/nbd{0..15}; do
    if [ -b "$dev" ] && [ ! -f "/sys/block/$(basename "$dev")/pid" ]; then
        NBD_DEV="$dev"
        break
    fi
done
[ -n "$NBD_DEV" ] || die "No free NBD device found"

# Windows partition (auto-detected below, default p3)
WIN_PART="${WIN_PART:-p3}"

cleanup_nbd() {
    umount /tmp/win10-mount 2>/dev/null || true
    qemu-nbd --disconnect "$NBD_DEV" 2>/dev/null || true
}
trap cleanup_nbd EXIT

mkdir -p "$OUTPUT_DIR/libvirt"

echo ""
echo "🔹 === Multi-stage Windows VirtIO Deployment ==="
echo "  QCOW2:      $QCOW2"
echo "  VirtIO ISO:  $VIRTIO_ISO"
echo "  VM Name:     $VM_NAME"
echo ""

# ─── Detect OVMF firmware ────────────────────────────────────────────────────

OVMF_CODE=""
for p in /usr/share/edk2/ovmf/OVMF_CODE.fd /usr/share/OVMF/OVMF_CODE.fd /usr/share/edk2/x64/OVMF_CODE.fd; do
    [ -f "$p" ] && OVMF_CODE="$p" && break
done
[ -n "$OVMF_CODE" ] || die "OVMF firmware not found"
OVMF_VARS=$(echo "$OVMF_CODE" | sed 's/CODE/VARS/')
ok "OVMF: $OVMF_CODE"

# Ensure libvirt NAT rules exist (Docker/nftables can override them)
# Detect the network dynamically from the default libvirt bridge
VIRBR_SUBNET=$(virsh net-dumpxml default 2>/dev/null | grep '<ip ' | grep -oP "address='\K[0-9.]+")
if [ -n "$VIRBR_SUBNET" ]; then
    VIRBR_CIDR="${VIRBR_SUBNET%.*}.0/24"
    if ! iptables -t nat -C POSTROUTING -s "$VIRBR_CIDR" -j MASQUERADE 2>/dev/null; then
        log "Adding NAT masquerade for libvirt network ($VIRBR_CIDR)..."
        iptables -t nat -A POSTROUTING -s "$VIRBR_CIDR" -j MASQUERADE 2>/dev/null
        iptables -A FORWARD -s "$VIRBR_CIDR" -j ACCEPT 2>/dev/null
        iptables -A FORWARD -d "$VIRBR_CIDR" -j ACCEPT 2>/dev/null
        ok "NAT rules added for $VIRBR_CIDR"
    fi
fi

# Create per-VM NVRAM copy
NVRAM_FILE="$OUTPUT_DIR/libvirt/${VM_NAME}_VARS.fd"
if [ ! -f "$NVRAM_FILE" ]; then
    cp "$OVMF_VARS" "$NVRAM_FILE"
    ok "NVRAM copy created"
fi

# ─── Remove VMware Tools (offline) ──────────────────────────────────────────

# ─── Pre-stage: Offline registry fix (VMware removal + VirtIO RunOnce) ───────

log "Pre-stage: Offline registry fix via ntfs-3g + hivex..."
log "  Mounting NTFS partition..."

qemu-nbd --connect="$NBD_DEV" "$QCOW2" 2>/dev/null
sleep 2
ntfsfix "${NBD_DEV}${WIN_PART}" 2>/dev/null | tail -1
mkdir -p /tmp/win10-mount
ntfs-3g -o remove_hiberfile,force "${NBD_DEV}${WIN_PART}" /tmp/win10-mount 2>/dev/null

if [ -d "/tmp/win10-mount/Windows" ]; then
    ok "NTFS mounted"

    python3 << 'PYEOF'
import hivex

WIN = '/tmp/win10-mount'
cfg = f'{WIN}/Windows/System32/config'

# 1. SYSTEM hive: disable VMware services
h = hivex.Hivex(f'{cfg}/SYSTEM', write=True)
cs = h.node_get_child(h.root(), 'ControlSet001')
svc = h.node_get_child(cs, 'Services')
d = []
for n in ['VMTools','vm3dservice','VGAuthService','vmvss','vmci','vsock','vmhgfs','vmrawdsk','vmusbmouse']:
    try:
        nd = h.node_get_child(svc, n)
        if nd:
            h.node_set_value(nd, {'key':'Start','t':4,'value':(4).to_bytes(4,'little')})
            d.append(n)
    except: pass
h.commit(f'{cfg}/SYSTEM')
print(f'  SYSTEM: disabled {len(d)} VMware services: {d}')

# 2. SOFTWARE hive: neuter VMware Run key + add VirtIO RunOnce with cert import
h2 = hivex.Hivex(f'{cfg}/SOFTWARE', write=True)
cv = h2.node_get_child(h2.node_get_child(h2.node_get_child(h2.root(),'Microsoft'),'Windows'),'CurrentVersion')

# Neuter VMware User Process
run = h2.node_get_child(cv,'Run')
if run:
    for v in h2.node_values(run):
        k = h2.value_key(v)
        if 'vmware' in k.lower():
            h2.node_set_value(run, {'key':k,'t':1,'value':b'\x00\x00'})
            print(f'  SOFTWARE: neutered Run key: {k}')

# Add RunOnce: import Red Hat cert (no confirmation) + pnputil install all drivers from CD
try: ro = h2.node_get_child(cv,'RunOnce')
except: ro = None
if not ro: ro = h2.node_add_child(cv,'RunOnce')

# Install cert first to avoid confirmation dialogs, then pnputil
cmd = r'cmd.exe /c "for %d in (D E F G H) do if exist %d:\cert ( certutil -addstore TrustedPublisher %d:\cert\*.cer >nul 2>&1 & certutil -addstore Root %d:\cert\*.cer >nul 2>&1 & pnputil /add-driver %d:\*.inf /subdirs /install & if exist %d:\guest-agent\qemu-ga-x86_64.msi msiexec /i %d:\guest-agent\qemu-ga-x86_64.msi /quiet )"'
h2.node_set_value(ro, {'key':'hyper2kvm-virtio','t':1,'value':(cmd+'\0').encode('utf-16-le')})
print('  SOFTWARE: added RunOnce (certutil + pnputil from VirtIO CD)')

h2.commit(f'{cfg}/SOFTWARE')
print('  Registry hives updated successfully')
PYEOF

    sync
    umount /tmp/win10-mount
    ok "Registry fixes applied"
else
    warn "Could not mount NTFS (non-fatal)"
fi

qemu-nbd --disconnect "$NBD_DEV" 2>/dev/null

# ─── Stage 1: Generate bootstrap XML (SATA + VirtIO ISO) ─────────────────────

log "Stage 1: Generating bootstrap domain XML (SATA disk + VirtIO ISO)..."

cat > "$XML_BOOTSTRAP" <<XMLEOF
<domain type='kvm'>
  <name>${VM_NAME}-bootstrap</name>
  <memory unit='MiB'>4096</memory>
  <vcpu>2</vcpu>
  <os>
    <type arch='x86_64' machine='q35'>hvm</type>
    <loader readonly='yes' type='pflash'>$OVMF_CODE</loader>
    <nvram>$NVRAM_FILE</nvram>
  </os>
  <features>
    <acpi/>
    <apic/>
    <hyperv mode='custom'>
      <relaxed state='on'/>
      <vapic state='on'/>
      <spinlocks state='on' retries='8191'/>
    </hyperv>
  </features>
  <cpu mode='host-passthrough'/>
  <clock offset='localtime'>
    <timer name='hypervclock' present='yes'/>
  </clock>
  <devices>
    <!-- Boot disk on SATA (safe — no VirtIO storage driver yet) -->
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2' cache='none'/>
      <source file='$QCOW2'/>
      <target dev='sda' bus='sata'/>
      <boot order='1'/>
    </disk>
    <!-- VirtIO driver ISO -->
    <disk type='file' device='cdrom'>
      <driver name='qemu' type='raw'/>
      <source file='$VIRTIO_ISO'/>
      <target dev='sdb' bus='sata'/>
    </disk>
    <!-- VirtIO network (triggers netkvm driver install) -->
    <interface type='network'>
      <source network='default'/>
      <model type='virtio'/>
    </interface>
    <!-- VirtIO balloon (triggers balloon driver) -->
    <memballoon model='virtio'/>
    <!-- VirtIO serial (triggers vioserial driver) -->
    <channel type='unix'>
      <target type='virtio' name='org.qemu.guest_agent.0'/>
    </channel>
    <graphics type='vnc' autoport='yes' listen='127.0.0.1'/>
    <video><model type='qxl'/></video>
    <input type='tablet' bus='usb'/>
  </devices>
</domain>
XMLEOF
ok "Bootstrap XML: $XML_BOOTSTRAP"

# ─── Stage 1: Boot with SATA + VirtIO devices ────────────────────────────────

log "Stage 1: Booting VM with SATA + VirtIO devices for driver installation..."

# Clean up any previous domain
virsh destroy "${VM_NAME}-bootstrap" 2>/dev/null || true
virsh undefine "${VM_NAME}-bootstrap" --nvram 2>/dev/null || true

virsh define "$XML_BOOTSTRAP"
virsh start "${VM_NAME}-bootstrap"
ok "VM started: ${VM_NAME}-bootstrap"

log "  Waiting for Windows to boot and install VirtIO drivers..."
log "  Connect VNC: virt-viewer ${VM_NAME}-bootstrap"
log "  Timeout: ${TIMEOUT_INSTALL}s (set WIN_INSTALL_TIMEOUT to override)"

# Wait for VM to run — Windows will auto-detect VirtIO devices and install drivers
# from the ISO via PnP (Plug and Play)
sleep 10

# Wait for VM to be running and for some time for driver installation
ELAPSED=0
while [ "$ELAPSED" -lt "$TIMEOUT_INSTALL" ]; do
    STATE=$(virsh domstate "${VM_NAME}-bootstrap" 2>/dev/null || echo "unknown")
    if [ "$STATE" != "running" ]; then
        warn "VM state: $STATE (expected running)"
        break
    fi

    # Check if guest agent is responding (means drivers are installed)
    if virsh qemu-agent-command "${VM_NAME}-bootstrap" '{"execute":"guest-ping"}' 2>/dev/null | grep -q "return"; then
        ok "QEMU Guest Agent responding — VirtIO drivers installed!"
        sleep 5  # Give it a moment to finish
        break
    fi

    sleep 10
    ELAPSED=$((ELAPSED + 10))
    if [ $((ELAPSED % 30)) -eq 0 ]; then
        log "  Waiting for driver installation... (${ELAPSED}s/${TIMEOUT_INSTALL}s)"
    fi
done

# ─── Stage 2: Shut down and verify ────────────────────────────────────────────

log "Stage 2: Shutting down VM for verification..."

# Try graceful shutdown first
virsh shutdown "${VM_NAME}-bootstrap" 2>/dev/null || true
SHUTDOWN_WAIT=0
while [ "$SHUTDOWN_WAIT" -lt 60 ]; do
    STATE=$(virsh domstate "${VM_NAME}-bootstrap" 2>/dev/null || echo "shut off")
    [ "$STATE" = "shut off" ] && break
    sleep 5
    SHUTDOWN_WAIT=$((SHUTDOWN_WAIT + 5))
done

# Force if still running
virsh destroy "${VM_NAME}-bootstrap" 2>/dev/null || true
ok "VM shut down"

# Verify VirtIO drivers via offline registry check
log "Stage 2: Verifying VirtIO driver installation (offline registry)..."

python3 -c "
import sys, subprocess, tempfile, os
sys.path.insert(0, '.')

# Mount the QCOW2 and check Windows registry for VirtIO services
try:
    from hyper2kvm.vmcraft import VMCraft
    vm = VMCraft()
    vm.add_drive_opts('$QCOW2', readonly=True)
    vm.launch()

    roots = vm.inspect_os()
    root = roots[0] if isinstance(roots, list) else roots
    if root:
        vm.mount(root, '/')

        drivers_found = []
        drivers_missing = []

        # Check for VirtIO driver files in System32/drivers
        for drv in ['viostor.sys', 'netkvm.sys', 'vioserial.sys', 'balloon.sys', 'viorng.sys']:
            path = f'/Windows/System32/drivers/{drv}'
            try:
                if vm.exists(path):
                    drivers_found.append(drv)
                else:
                    drivers_missing.append(drv)
            except Exception:
                drivers_missing.append(drv)

        print(f'  VirtIO drivers found:   {len(drivers_found)}: {drivers_found}')
        if drivers_missing:
            print(f'  VirtIO drivers missing: {len(drivers_missing)}: {drivers_missing}')

        # Check for VMware tools remnants
        vmtools_found = []
        for f in ['vmtoolsd.exe', 'vmtoolsd.sys', 'VMwareUser.exe']:
            for base in ['/Windows/System32', '/Program Files/VMware/VMware Tools']:
                path = f'{base}/{f}'
                try:
                    if vm.exists(path):
                        vmtools_found.append(path)
                except Exception:
                    pass

        if vmtools_found:
            print(f'  VMware tools remnants:  {vmtools_found}')
        else:
            print(f'  VMware tools:           removed')

        # Result
        if 'viostor.sys' in drivers_found:
            print('  RESULT: VirtIO storage driver (viostor) PRESENT — safe to switch to VirtIO bus')
            sys.exit(0)
        else:
            print('  RESULT: VirtIO storage driver NOT found — keep SATA bus')
            sys.exit(1)

    vm.shutdown()
except Exception as e:
    print(f'  Verification error: {e}')
    print('  Falling back to SATA bus (safe)')
    sys.exit(1)
" 2>&1
VERIFY_RESULT=$?

if [ "$VERIFY_RESULT" -eq 0 ]; then
    ok "VirtIO storage driver verified — proceeding to Stage 3"
    DISK_BUS="virtio"
    DISK_DEV="vda"
else
    warn "VirtIO storage driver not verified — keeping SATA bus"
    DISK_BUS="sata"
    DISK_DEV="sda"
fi

# ─── Stage 3: Generate final domain XML ─────────────────────────────────────

log "Stage 3: Generating final domain XML (disk bus: $DISK_BUS)..."

virsh undefine "${VM_NAME}-bootstrap" --nvram 2>/dev/null || true

cat > "$XML_FINAL" <<XMLEOF
<domain type='kvm'>
  <name>$VM_NAME</name>
  <memory unit='MiB'>4096</memory>
  <vcpu>2</vcpu>
  <os>
    <type arch='x86_64' machine='q35'>hvm</type>
    <loader readonly='yes' type='pflash'>$OVMF_CODE</loader>
    <nvram>$NVRAM_FILE</nvram>
  </os>
  <features>
    <acpi/>
    <apic/>
    <hyperv mode='custom'>
      <relaxed state='on'/>
      <vapic state='on'/>
      <spinlocks state='on' retries='8191'/>
      <vpindex state='on'/>
      <synic state='on'/>
      <stimer state='on'/>
      <reset state='on'/>
    </hyperv>
  </features>
  <cpu mode='host-passthrough'/>
  <clock offset='localtime'>
    <timer name='hypervclock' present='yes'/>
  </clock>
  <devices>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2' cache='none' discard='unmap'/>
      <source file='$QCOW2'/>
      <target dev='$DISK_DEV' bus='$DISK_BUS'/>
      <boot order='1'/>
    </disk>
    <interface type='network'>
      <source network='default'/>
      <model type='virtio'/>
    </interface>
    <memballoon model='virtio'/>
    <channel type='unix'>
      <target type='virtio' name='org.qemu.guest_agent.0'/>
    </channel>
    <graphics type='vnc' autoport='yes' listen='127.0.0.1'/>
    <video><model type='qxl'/></video>
    <input type='tablet' bus='usb'/>
    <rng model='virtio'>
      <backend model='random'>/dev/urandom</backend>
    </rng>
  </devices>
</domain>
XMLEOF
ok "Final XML: $XML_FINAL"

# ─── Stage 4: Boot final VM ──────────────────────────────────────────────────

log "Stage 4: Booting final VM with $DISK_BUS disk bus..."

virsh destroy "$VM_NAME" 2>/dev/null || true
virsh undefine "$VM_NAME" --nvram 2>/dev/null || true

virsh define "$XML_FINAL"
virsh start "$VM_NAME"

sleep 10
STATE=$(virsh domstate "$VM_NAME" 2>/dev/null || echo "unknown")
if [ "$STATE" = "running" ]; then
    ok "VM '$VM_NAME' is RUNNING with $DISK_BUS disk bus"
else
    err "VM '$VM_NAME' state: $STATE"
fi

# ─── Summary ─────────────────────────────────────────────────────────────────

echo ""
echo "✅ === Windows VirtIO Deployment Complete ==="
echo ""
echo "  VM Name:     $VM_NAME"
echo "  Disk Bus:    $DISK_BUS"
echo "  QCOW2:      $QCOW2"
echo "  Final XML:   $XML_FINAL"
echo ""
echo "  Commands:"
echo "    virsh console $VM_NAME"
echo "    virt-viewer $VM_NAME"
echo "    virsh vncdisplay $VM_NAME"
echo "    virsh shutdown $VM_NAME"
echo ""
echo "✅ ==========================================="
