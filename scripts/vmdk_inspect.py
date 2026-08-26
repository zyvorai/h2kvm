#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
vmdk_inspect.py (v1.2)

Enterprise-grade VMDK inspection tool for ESXi → KVM migration.

Exit codes:
  0 = OK (or --no-fail mode)
  2 = HIGH risks present
  3 = FATAL risks present

Options:
  --json       Output results as JSON
  --no-fail    Exit with code 0 even if risks found (inventory mode)
  --auto-fix   Convert and inject virtio drivers for controller mismatches
               Requires --output <file.qcow2> to specify where to save fixed image

Usage examples:
  # Pre-migration validation (fails on risks)
  ./vmdk_inspect.py disk.vmdk

  # Fleet inventory scan (never fails, collects all findings)
  ./vmdk_inspect.py --no-fail --json *.vmdk > inventory.json

  # Auto-fix controller mismatch (converts VMDK, injects virtio drivers)
  ./vmdk_inspect.py --auto-fix --output fixed.qcow2 disk.vmdk

  # Audit existing VMs (non-blocking)
  for vmdk in /vmfs/volumes/*/VMs/*/*.vmdk; do
    ./vmdk_inspect.py --no-fail "$vmdk"
  done
"""

import os
import re
import sys
import json
import glob
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional


# ============================================================
# Risk model
# ============================================================


@dataclass
class Risk:
    level: str  # FATAL | HIGH | MEDIUM | INFO
    message: str


# ============================================================
# Parsed VMDK information
# ============================================================


@dataclass
class VMDKInfo:
    path: Path

    create_type: Optional[str] = None
    parent_cid: Optional[str] = None
    adapter_type: Optional[str] = None
    thin: bool = False

    sectors: Optional[int] = None
    extent_type: Optional[str] = None
    extent_file: Optional[str] = None

    geometry: dict = field(default_factory=dict)

    boot_mode: Optional[str] = None  # BIOS | UEFI | UNKNOWN
    risks: List[Risk] = field(default_factory=list)

    @property
    def size_bytes(self):
        return self.sectors * 512 if self.sectors else None

    @property
    def size_gb(self):
        if self.size_bytes:
            return round(self.size_bytes / (1024**3), 2)
        return None


# ============================================================
# Constants
# ============================================================

FATAL_CONTROLLERS = {"buslogic"}
HIGH_RISK_CONTROLLERS = {"lsilogic", "lsilogicsas"}

EXTENT_RE = re.compile(r'^(?:RW|RDONLY|NOACCESS)\s+(\d+)\s+(\w+)\s+"(.+)"')


# ============================================================
# Descriptor parsing
# ============================================================


def parse_vmdk_descriptor(path: Path) -> VMDKInfo:
    info = VMDKInfo(path=path)

    with path.open(errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if line.startswith("createType"):
                info.create_type = _val(line)

            elif line.startswith("parentCID"):
                info.parent_cid = _val(line)

            elif line.startswith("ddb.adapterType"):
                info.adapter_type = _val(line).lower()

            elif line.startswith("ddb.thinProvisioned"):
                info.thin = _val(line) == "1"

            elif line.startswith("ddb.geometry"):
                key = line.split(".")[-1].split("=")[0]
                info.geometry[key] = _val(line)

            elif line.startswith("RW") or line.startswith("RDONLY"):
                m = EXTENT_RE.match(line)
                if m:
                    info.sectors = int(m.group(1))
                    info.extent_type = m.group(2)
                    info.extent_file = m.group(3)

    # Fallback: infer size from file if descriptor didn't provide it
    if info.sectors is None:
        _infer_size_from_file(info)

    analyze_risks(info)
    detect_boot_mode(info)
    return info


def _infer_size_from_file(info: VMDKInfo):
    """Infer size from extent file or VMDK itself (streamOptimized)."""
    extent_path = None

    # Try separate extent file first
    if info.extent_file:
        extent_path = info.path.parent / info.extent_file
        if not extent_path.exists():
            extent_path = None

    # Try VMDK file itself (monolithic/streamOptimized)
    if extent_path is None:
        try:
            vmdk_size = info.path.stat().st_size
            if vmdk_size > 1024 * 1024:  # > 1MB
                extent_path = info.path
        except Exception:
            pass

    if extent_path:
        try:
            file_size = extent_path.stat().st_size
            if file_size > 0:
                info.sectors = file_size // 512
                source = "extent file" if extent_path != info.path else "VMDK file (streamOptimized)"
                info.risks.append(Risk("INFO", f"Size inferred from {source} ({info.size_gb:.2f} GB)"))
        except Exception:
            pass


def _val(line: str) -> str:
    return line.split("=", 1)[1].strip().strip('"')


# ============================================================
# Risk analysis
# ============================================================


def analyze_risks(info: VMDKInfo):
    # Snapshot
    if info.parent_cid and info.parent_cid.lower() != "ffffffff":
        info.risks.append(Risk("FATAL", "Snapshot chain detected (parentCID != ffffffff)"))

    # Controller
    if info.adapter_type:
        at = info.adapter_type

        if at in FATAL_CONTROLLERS:
            info.risks.append(Risk("FATAL", f"Legacy controller '{at}' – unsupported on KVM"))

        elif at in HIGH_RISK_CONTROLLERS:
            info.risks.append(Risk("HIGH", f"Controller '{at}' – initramfs may lack driver"))

        if at != "virtio" and at not in FATAL_CONTROLLERS:
            info.risks.append(
                Risk("HIGH", f"Controller mismatch: guest expects '{at}', libvirt will use virtio")
            )
    else:
        info.risks.append(Risk("MEDIUM", "Missing ddb.adapterType"))

    # Geometry
    if info.geometry:
        info.risks.append(Risk("INFO", "Legacy CHS geometry present (ignored by modern kernels)"))

    # Extent validation
    if info.extent_type == "VMFS":
        info.risks.append(Risk("INFO", "VMFS-backed extent – convert using descriptor only"))

    if info.extent_file and info.sectors:
        flat = info.path.parent / info.extent_file
        expected = info.sectors * 512

        if not flat.exists():
            info.risks.append(Risk("FATAL", f"Extent file missing: {flat}"))
        else:
            actual = flat.stat().st_size
            if actual < expected:
                info.risks.append(
                    Risk("FATAL", f"Extent size mismatch: expected ≥ {expected}, got {actual}")
                )


# ============================================================
# Boot mode detection (UEFI vs BIOS)
# ============================================================


def detect_boot_mode(info: VMDKInfo):
    """
    Detect UEFI by checking for EFI System Partition using guestfs.
    """
    flat = info.path.parent / info.extent_file if info.extent_file else info.path
    if not flat.exists():
        info.boot_mode = "UNKNOWN"
        return

    try:
        cmd = ["virt-inspector", "--no-applications", "--no-icon", str(flat)]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)

        if 'firmware="uefi"' in out.lower():
            info.boot_mode = "UEFI"
            info.risks.append(Risk("HIGH", "UEFI guest detected – libvirt domain must use OVMF firmware"))
        else:
            info.boot_mode = "BIOS"

    except FileNotFoundError:
        info.boot_mode = "UNKNOWN"
        info.risks.append(Risk("INFO", "guestfs not available – boot mode detection skipped"))
    except subprocess.CalledProcessError:
        info.boot_mode = "UNKNOWN"
        info.risks.append(Risk("INFO", "Unable to inspect guest boot mode"))


# ============================================================
# Auto-fix: Controller mismatch remediation
# ============================================================


def needs_virtio_fix(info: VMDKInfo) -> bool:
    """Check if VMDK needs virtio driver injection due to controller mismatch."""
    if not info.adapter_type:
        return False

    # BusLogic is FATAL (no fix possible - no KVM driver exists)
    if info.adapter_type in FATAL_CONTROLLERS:
        return False

    # LSI Logic and similar need initramfs rebuild
    if info.adapter_type in HIGH_RISK_CONTROLLERS:
        return True

    # Any non-virtio controller needs fixing
    if info.adapter_type != "virtio":
        return True

    return False


def generate_fix_config(vmdk_path: Path, output_path: str, boot_mode: str = "BIOS") -> str:
    """Generate hyper2kvm YAML config to fix controller mismatch."""
    config = f"""# Auto-generated fix config for: {vmdk_path.name}
# Generated by vmdk_inspect.py v1.2

cmd: local
vmdk: {vmdk_path.absolute()}
output_dir: {Path(output_path).parent.absolute() if output_path else "./output"}
to_output: {Path(output_path).name if output_path else vmdk_path.stem + "-fixed.qcow2"}
out_format: qcow2

# Controller mismatch fix: inject virtio drivers
regen_initramfs: true
initramfs_add_drivers:
  - virtio
  - virtio_blk
  - virtio_scsi
  - virtio_net
  - virtio_pci
"""

    if boot_mode == "UEFI":
        config += """
# UEFI firmware required
# Configure libvirt with:
#   <loader readonly='yes' type='pflash'>/usr/share/OVMF/OVMF_CODE.fd</loader>
"""

    return config


def apply_auto_fix(info: VMDKInfo, output_path: str) -> bool:
    """
    Apply automatic fix for controller mismatch using hyper2kvm.

    Returns True if fix was applied successfully, False otherwise.
    """
    # Check if fix is possible
    if info.adapter_type in FATAL_CONTROLLERS:
        print(f"\n❌ FATAL: Cannot auto-fix '{info.adapter_type}' controller")
        print(f"   Reason: No KVM driver exists for '{info.adapter_type}'")
        print(f"\n💡 Solution: Change controller in VMware before migration:")
        print(f"   1. Shut down VM in VMware")
        print(f"   2. Edit VM Settings → SCSI Controller")
        print(f"   3. Change from BusLogic to LSI Logic or PVSCSI")
        print(f"   4. Boot VM in VMware to verify")
        print(f"   5. Re-run migration")
        return False

    if not needs_virtio_fix(info):
        print(f"\n✅ No controller fix needed for {info.path.name}")
        return True

    print(f"\n🔧 Applying automatic fix for controller mismatch...")
    print(f"   Controller: {info.adapter_type} → virtio")
    print(f"   Action: Injecting virtio drivers into initramfs")

    # Generate fix config
    config_content = generate_fix_config(info.path, output_path, info.boot_mode or "BIOS")

    # Save config to temp file
    import tempfile
    import atexit

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, prefix="vmdk-fix-") as f:
        f.write(config_content)
        config_file = f.name
    atexit.register(lambda: os.unlink(config_file) if os.path.exists(config_file) else None)

    print(f"\n📋 Generated fix configuration:")
    print(f"   Config file: {config_file}")
    print(f"\n{config_content}")

    # Check if hyper2kvm is available
    try:
        result = subprocess.run(["hyper2kvm", "--version"], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"\n❌ hyper2kvm not found in PATH")
            print(f"   Install with: pip install hyper2kvm")
            print(f"\n   Manual fix: hyper2kvm --config {config_file}")
            return False
    except FileNotFoundError:
        print(f"\n❌ hyper2kvm not found in PATH")
        print(f"   Install with: pip install hyper2kvm")
        print(f"\n   Manual fix: hyper2kvm --config {config_file}")
        return False

    # Execute fix
    print(f"\n🚀 Executing fix with hyper2kvm...")
    print(f"   (This may require sudo for guest filesystem operations)\n")

    try:
        result = subprocess.run(["hyper2kvm", "--config", config_file], text=True, capture_output=True)

        if result.returncode == 0:
            print(f"\n✅ Fix applied successfully!")
            print(f"   Output: {output_path}")
            print(f"\n   The fixed image has virtio drivers in initramfs.")
            print(f"   Boot this VM on KVM - it will use virtio-blk/virtio-scsi controllers.")
            return True
        else:
            print(f"\n⚠️  Fix command exited with code {result.returncode}")

            # Common error scenarios
            if result.stderr and "requires root" in result.stderr:
                print(f"\n💡 Try with sudo:")
                print(f"   sudo hyper2kvm --config {config_file}")
            else:
                print(f"   Check logs above for details")
                print(f"\n💡 Manual retry:")
                print(f"   hyper2kvm --config {config_file}")

            print(f"\n📝 Config saved: {config_file}")
            return False

    except Exception as e:
        print(f"\n❌ Fix failed: {e}")
        print(f"\n💡 Manual retry:")
        print(f"   hyper2kvm --config {config_file}")
        print(f"\n📝 Config saved: {config_file}")
        return False


# ============================================================
# libvirt XML generation
# ============================================================


def generate_libvirt_disk_xml(image_path: str, boot_mode: str = "BIOS") -> str:
    """Generate libvirt disk XML configuration."""
    disk_xml = f"""
<disk type='file' device='disk'>
  <driver name='qemu' type='qcow2' cache='none' io='native'/>
  <source file='{image_path}'/>
  <target dev='vda' bus='virtio'/>
</disk>

<controller type='scsi' index='0' model='virtio-scsi'/>
""".strip()

    if boot_mode == "UEFI":
        disk_xml += """

<!-- UEFI firmware configuration required -->
<os>
  <type arch='x86_64' machine='pc-q35'>hvm</type>
  <loader readonly='yes' type='pflash'>/usr/share/OVMF/OVMF_CODE.fd</loader>
  <nvram>/var/lib/libvirt/qemu/nvram/GUEST_NAME_VARS.fd</nvram>
</os>
"""

    return disk_xml


# ============================================================
# CLI
# ============================================================


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} [--json] [--no-fail] [--auto-fix] [--output FILE] <vmdk | glob>")
        sys.exit(1)

    json_mode = "--json" in sys.argv
    no_fail = "--no-fail" in sys.argv
    auto_fix = "--auto-fix" in sys.argv

    # Parse --output option
    output_file = None
    if "--output" in sys.argv:
        try:
            idx = sys.argv.index("--output")
            output_file = sys.argv[idx + 1]
        except (IndexError, ValueError):
            print("ERROR: --output requires a filename")
            sys.exit(1)

    args = [
        a
        for a in sys.argv[1:]
        if a not in ("--json", "--no-fail", "--auto-fix", "--output")
        and not (output_file and a == output_file)
    ]

    vmdks = []
    for a in args:
        vmdks.extend(Path(x) for x in glob.glob(a))

    if not vmdks:
        print("ERROR: no VMDK files found")
        sys.exit(1)

    # Validate --auto-fix requirements
    if auto_fix:
        if not output_file:
            print("ERROR: --auto-fix requires --output <file.qcow2>")
            sys.exit(1)
        if len(vmdks) > 1:
            print("ERROR: --auto-fix only supports single VMDK (not glob patterns)")
            sys.exit(1)

    if no_fail and not json_mode:
        print("[INVENTORY MODE: --no-fail enabled, will exit 0 regardless of risks]\n")

    worst = 0
    results = []
    fix_applied = False

    for vmdk in vmdks:
        info = parse_vmdk_descriptor(vmdk)

        levels = {r.level for r in info.risks}
        if "FATAL" in levels:
            worst = max(worst, 3)
        elif "HIGH" in levels:
            worst = max(worst, 2)

        if not json_mode:
            print(f"\n=== {vmdk} ===")
            size_display = f"{info.size_gb} GB" if info.size_gb is not None else "UNKNOWN"
            print(f"Size      : {size_display}")
            print(f"Adapter   : {info.adapter_type or 'UNKNOWN'}")
            print(f"Boot mode : {info.boot_mode}")
            for r in info.risks:
                print(f"[{r.level}] {r.message}")

            # Auto-fix if requested
            if auto_fix and output_file:
                fix_applied = apply_auto_fix(info, output_file)
                if not fix_applied:
                    worst = max(worst, 3)  # Treat fix failure as fatal
            else:
                print("\nSuggested libvirt XML:")
                print(
                    generate_libvirt_disk_xml("/var/lib/libvirt/images/disk.qcow2", info.boot_mode or "BIOS")
                )
        else:
            results.append(
                {
                    "file": str(vmdk),
                    "size_gb": info.size_gb,
                    "adapter": info.adapter_type,
                    "boot_mode": info.boot_mode,
                    "risks": [{"level": r.level, "message": r.message} for r in info.risks],
                }
            )

    if json_mode:
        print(json.dumps(results, indent=2))

    # In --no-fail mode, always exit 0 (useful for inventory/audit scans)
    exit_code = 0 if no_fail else worst
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
