# VMDK Inspector

Enterprise-grade VMDK inspection and pre-migration risk analysis.

## Overview

The VMDK Inspector performs comprehensive validation of VMDK files **before** migration to detect:

- **Controller compatibility** issues (BusLogic, LSI Logic, etc.)
- **Snapshot chains** (parentCID verification)
- **Boot firmware mode** (UEFI vs BIOS)
- **Extent file** integrity
- **Size mismatches**
- **Migration risks** with severity levels

This prevents migration failures by catching issues early.

---

## Quick Start

### CLI Usage

```bash
# Inspect single VMDK
./scripts/vmdk_inspect.py /path/to/disk.vmdk

# Inspect multiple VMDKs
./scripts/vmdk_inspect.py /vms/*.vmdk

# JSON output for automation
./scripts/vmdk_inspect.py --json /path/to/disk.vmdk
```

### Library Usage

```python
from h2kvm.validation import VMDKInspector, RiskLevel
from pathlib import Path

# Create inspector
inspector = VMDKInspector()

# Inspect VMDK
result = inspector.inspect(Path("/path/to/disk.vmdk"))

# Check results
if result.has_fatal_risks:
    print("FATAL: Migration will fail!")
    for risk in result.risks:
        if risk.level == RiskLevel.FATAL:
            print(f"  - {risk.message}")
elif result.has_high_risks:
    print("WARNING: High risk of boot failure")

# Boot mode detection
if result.boot_mode == BootMode.UEFI:
    print("UEFI detected - use OVMF firmware in libvirt")

# Generate libvirt config
xml = inspector.generate_libvirt_config(
    result,
    "/var/lib/libvirt/images/disk.qcow2"
)
print(xml)
```

---

## Risk Levels

| Level | Description | Action Required |
|-------|-------------|-----------------|
| **FATAL** | Migration will fail | Must fix before migration |
| **HIGH** | Boot failure likely | Initramfs rebuild needed |
| **MEDIUM** | Minor compatibility issue | Review configuration |
| **INFO** | Informational only | No action required |

---

## Detected Issues

### 1. Snapshot Chains (FATAL)

**Problem**: VMDK has `parentCID != ffffffff`

**Fix**: Consolidate snapshots in VMware before migration

```bash
# In vSphere:
# Right-click VM → Snapshots → Consolidate
```

### 2. Legacy Controllers (FATAL)

**Problem**: BusLogic controller detected

**Fix**: No fix available - BusLogic not supported on KVM. Change controller in VMware first.

### 3. Controller Mismatch (HIGH)

**Problem**: Guest expects `lsilogic` but KVM uses `virtio`

**Fix**: h2kvm automatically rebuilds initramfs with virtio drivers

### 4. UEFI vs BIOS (HIGH)

**Problem**: UEFI guest detected

**Action**: Use OVMF firmware in libvirt domain

```xml
<os>
  <type arch='x86_64' machine='pc-q35'>hvm</type>
  <loader readonly='yes' type='pflash'>/usr/share/OVMF/OVMF_CODE.fd</loader>
  <nvram>/var/lib/libvirt/qemu/nvram/VM_NAME_VARS.fd</nvram>
</os>
```

### 5. Missing Extent Files (FATAL)

**Problem**: Descriptor references extent file that doesn't exist

**Fix**: Verify VMDK files are complete before migration

### 6. Size Mismatch (FATAL)

**Problem**: Extent file smaller than expected

**Fix**: Re-export VMDK from vSphere

---

## Auto-Fix Mode

The VMDK Inspector can automatically remediate controller mismatches by injecting virtio drivers into the guest initramfs.

### Standalone CLI Auto-Fix

```bash
# Detect and fix controller mismatch in one command
./scripts/vmdk_inspect.py --auto-fix --output fixed.qcow2 disk.vmdk

# Output:
🔧 Applying automatic fix for controller mismatch...
   Controller: lsilogic → virtio
   Action: Injecting virtio drivers into initramfs

📋 Generated fix configuration:
   /tmp/vmdk-fix-abc123.yaml

✅ Fix applied successfully!
   Output: fixed.qcow2

   The fixed image has virtio drivers in initramfs.
   Boot this VM on KVM - it will use virtio-blk/virtio-scsi controllers.
```

### YAML Config Auto-Fix

Enable automatic controller remediation in your migration config:

```yaml
cmd: local
vmdk: /path/to/vm-with-lsilogic.vmdk
output_dir: ./output
to_output: vm-fixed.qcow2

# Enable automatic controller fix
vmdk_auto_fix_controller: true

# These are enabled automatically when controller mismatch detected:
# regen_initramfs: true  (auto-enabled)
# initramfs_add_drivers: [virtio, virtio_blk, virtio_scsi, virtio_net, virtio_pci]  (auto-added)

verbose: 2
```

When `vmdk_auto_fix_controller: true` is set:
1. VMDK Inspector detects controller mismatch (LSI Logic, IDE, etc.)
2. Pipeline automatically enables initramfs rebuild
3. Virtio drivers are injected into guest initramfs
4. Result: VM boots successfully on KVM with virtio controllers

### Supported Auto-Fix Scenarios

✅ **Can Auto-Fix:**
- LSI Logic → virtio
- LSI Logic SAS → virtio
- IDE → virtio
- SATA → virtio
- Any non-virtio controller where KVM driver exists

❌ **Cannot Auto-Fix:**
- BusLogic → No KVM driver (FATAL - must change in VMware first)
- Snapshot chains → Must consolidate snapshots
- Missing extent files → Must re-export from VMware

### Custom Drivers with Auto-Fix

Specify additional drivers beyond the defaults:

```yaml
cmd: local
vmdk: /path/to/vm.vmdk
to_output: vm-custom.qcow2

# Enable auto-fix
vmdk_auto_fix_controller: true

# Add custom drivers (replaces defaults)
initramfs_add_drivers:
  - virtio
  - virtio_blk
  - virtio_scsi
  - virtio_net
  - virtio_pci
  - e1000e        # Intel NIC
  - nvme          # NVMe storage
  - megaraid_sas  # RAID controller
```

### Batch Auto-Fix

Fix multiple VMs with controller mismatches:

```yaml
cmd: local
parallel_processing: true

# Apply auto-fix to all VMs
vmdk_auto_fix_controller: true

vms:
  - vmdk: /data/vm1-lsilogic.vmdk
    to_output: vm1-fixed.qcow2
  - vmdk: /data/vm2-ide.vmdk
    to_output: vm2-fixed.qcow2
  - vmdk: /data/vm3-virtio.vmdk
    to_output: vm3.qcow2  # No fix needed

output_dir: ./batch-output
```

### See Also

- [Complete Auto-Fix Example Config](../../examples/vmdk-auto-fix-controller.yaml)
- [Initramfs Drivers Examples](../../test-confs/96-linux-initramfs-drivers-examples.yaml)

---

## Inventory Mode (--no-fail)

For fleet-wide VMDK scanning without early exit:

```bash
# Scan all VMDKs, never fail (even with FATAL risks)
./scripts/vmdk_inspect.py --no-fail --json "/vmfs/volumes/*/*.vmdk" > fleet-report.json

# Exit code: 0 ✅ (complete scan regardless of risks)

# Filter problematic VMs
jq '.[] | select(.risks[].level == "FATAL")' fleet-report.json
```

Use cases:
- **Discovery**: Catalog all VMs in ESXi datastore
- **Audit**: Generate migration compatibility reports
- **Planning**: Identify which VMs need manual intervention
- **CI/CD**: Collect findings without pipeline failure

---

## Exit Codes (CLI)

| Code | Meaning |
|------|---------|
| `0` | No issues or only INFO/MEDIUM (or --no-fail mode) |
| `2` | HIGH risk detected |
| `3` | FATAL risk detected |

Use in scripts:

```bash
#!/bin/bash
# Option 1: Fail on risks (default)
if ! ./scripts/vmdk_inspect.py disk.vmdk; then
    echo "Pre-migration validation failed!"
    exit 1
fi

# Option 2: Auto-fix controller mismatches
if ./scripts/vmdk_inspect.py disk.vmdk 2>&1 | grep -q "Controller.*mismatch"; then
    echo "Controller mismatch detected - applying auto-fix"
    ./scripts/vmdk_inspect.py --auto-fix --output fixed.qcow2 disk.vmdk
else
    echo "No fix needed - direct conversion"
    h2kvm --config migration.yaml
fi

# Option 3: Inventory mode (never fail)
./scripts/vmdk_inspect.py --no-fail --json "*.vmdk" > inventory.json
```

---

## JSON Output Format

```json
[
  {
    "file": "/path/to/disk.vmdk",
    "size_gb": 50.0,
    "adapter": "lsilogic",
    "boot_mode": "UEFI",
    "risks": [
      {
        "level": "HIGH",
        "message": "Controller 'lsilogic' – initramfs may require rebuild",
        "component": "controller"
      },
      {
        "level": "HIGH",
        "message": "UEFI firmware detected - libvirt domain MUST use OVMF",
        "component": "boot"
      }
    ]
  }
]
```

---

## Integration with Pipeline

The VMDK Inspector is automatically used during pre-migration validation:

```python
from h2kvm.validation import VMDKInspector
from h2kvm.orchestrator import Orchestrator

# Inspector runs before conversion
inspector = VMDKInspector(logger)
result = inspector.inspect(vmdk_path)

if result.has_fatal_risks:
    raise MigrationError("Pre-migration validation failed")
```

---

## Boot Mode Detection

Uses `virt-inspector` to detect UEFI:

```bash
# Manual boot mode check
virt-inspector --no-applications --no-icon disk.vmdk
```

If virt-inspector is not installed, boot mode detection is skipped (INFO risk added).

### Install virt-inspector

```bash
# Fedora/RHEL
sudo dnf install guestfs-tools

# Ubuntu/Debian
sudo apt install guestfs-tools
```

---

## Examples

### Example 1: Valid VMDK

```bash
$ ./scripts/vmdk_inspect.py test.vmdk

=== /vms/test.vmdk ===
Size      : 20.0 GB
Adapter   : lsilogic
Boot mode : BIOS
[HIGH] Controller 'lsilogic' – initramfs may require rebuild
[INFO] Legacy CHS geometry present (ignored by modern kernels)

Suggested libvirt XML:
<disk type='file' device='disk'>
  <driver name='qemu' type='qcow2' cache='none' io='native'/>
  <source file='/var/lib/libvirt/images/disk.qcow2'/>
  <target dev='vda' bus='virtio'/>
</disk>
```

Exit code: `2` (HIGH risk)

### Example 2: Snapshot Chain (FATAL)

```bash
$ ./scripts/vmdk_inspect.py snapshot.vmdk

=== /vms/snapshot.vmdk ===
Size      : 10.0 GB
Adapter   : lsilogic
Boot mode : BIOS
[FATAL] Snapshot chain detected (parentCID != ffffffff)
```

Exit code: `3` (FATAL risk)

### Example 3: UEFI Guest

```bash
$ ./scripts/vmdk_inspect.py uefi-guest.vmdk

=== /vms/uefi-guest.vmdk ===
Size      : 40.0 GB
Adapter   : lsilogic
Boot mode : UEFI
[HIGH] UEFI firmware detected - libvirt domain MUST use OVMF
[HIGH] Controller mismatch: guest expects 'lsilogic', KVM will use virtio

Suggested libvirt XML:
<disk type='file' device='disk'>
  <driver name='qemu' type='qcow2' cache='none' io='native'/>
  <source file='/var/lib/libvirt/images/disk.qcow2'/>
  <target dev='vda' bus='virtio'/>
</disk>

<!-- UEFI firmware configuration (REQUIRED for UEFI guests) -->
<os>
  <type arch='x86_64' machine='pc-q35'>hvm</type>
  <loader readonly='yes' type='pflash'>/usr/share/OVMF/OVMF_CODE.fd</loader>
  <nvram>/var/lib/libvirt/qemu/nvram/VM_NAME_VARS.fd</nvram>
</os>
```

---

## API Reference

### VMDKInspector

```python
class VMDKInspector:
    def __init__(self, logger: Optional[logging.Logger] = None)

    def inspect(self, vmdk_path: Path) -> VMDKInspectionResult

    def generate_libvirt_config(
        self,
        result: VMDKInspectionResult,
        converted_image_path: str
    ) -> str
```

### VMDKInspectionResult

```python
@dataclass
class VMDKInspectionResult:
    path: Path
    valid: bool

    # Metadata
    create_type: Optional[str]
    parent_cid: Optional[str]
    adapter_type: Optional[str]
    thin_provisioned: bool

    # Size
    sectors: Optional[int]
    extent_type: Optional[str]
    extent_file: Optional[str]

    # Boot mode
    boot_mode: BootMode  # BIOS | UEFI | UNKNOWN

    # Risks
    risks: List[Risk]

    # Properties
    @property
    def size_gb(self) -> Optional[float]

    @property
    def has_fatal_risks(self) -> bool

    @property
    def has_high_risks(self) -> bool

    @property
    def max_risk_level(self) -> Optional[RiskLevel]

    def to_dict(self) -> Dict[str, Any]
```

---

## See Also

- [Migration Guide](../guides/migration/)
- [Troubleshooting](../guides/troubleshooting.md)
- [VMCraft Inspection](vmcraft-inspection.md)
- [Validation Framework](validation-framework.md)
