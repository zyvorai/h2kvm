# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/windows/virtio_warning.py

"""
VirtIO driver availability warnings for Windows migration.

Warns users when VirtIO drivers are not provided, explaining the performance
impact and providing instructions to download and inject drivers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging


VIRTIO_WIN_DIR = "/var/lib/h2kvm"
VIRTIO_WIN_ISO = f"{VIRTIO_WIN_DIR}/virtio-win.iso"
# Fedora/RHEL virtio-win RPM installs here
VIRTIO_WIN_RPM_ISO = "/usr/share/virtio-win/virtio-win.iso"
VIRTIO_WIN_URL = (
    "https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso"
)


def warn_no_virtio_drivers(  # pylint: disable=too-many-statements  # long but linear block of user-facing warning text, splitting would hurt readability
    logger: logging.Logger, windows_info: dict[str, Any] | None = None
) -> None:
    """
    Emit detailed warning when VirtIO drivers are not available.

    Args:
        logger: Logger instance
        windows_info: Optional Windows version info for specific recommendations
    """
    windows_version = ""
    if windows_info:
        product = windows_info.get("product_name", "Unknown")
        version = windows_info.get("version_full", "")
        windows_version = f" ({product} {version})" if version else f" ({product})"

    logger.warning("")
    logger.warning("=" * 80)
    logger.warning("⚠️  NO VIRTIO DRIVERS PROVIDED - REDUCED PERFORMANCE EXPECTED")
    logger.warning("=" * 80)
    logger.warning("")
    logger.warning(f"Windows VM{windows_version} will use compatibility mode:")
    logger.warning("")
    logger.warning("  Storage:  SATA/IDE (instead of VirtIO-SCSI)  → Slower disk I/O")
    logger.warning("  Network:  e1000    (instead of VirtIO-Net)   → Lower network throughput")
    logger.warning("  Balloon:  Disabled (no memory ballooning)    → Fixed memory allocation")
    logger.warning("")
    logger.warning("Expected Performance Impact:")
    logger.warning("  • Disk I/O:     ~30-50% slower than VirtIO-SCSI")
    logger.warning("  • Network:      ~20-40% lower throughput than VirtIO-Net")
    logger.warning("  • Memory:       No dynamic memory management")
    logger.warning("")
    logger.warning("Migration will continue with compatibility drivers, but for production use:")
    logger.warning("")
    logger.warning("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.warning("RECOMMENDED ACTIONS:")
    logger.warning("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.warning("")
    logger.warning("Option 1: Download VirtIO Drivers (Recommended)")
    logger.warning("  1. Install virtio-win.iso to the standard location:")
    logger.warning("       sudo ./scripts/quickstart.sh          # auto-downloads")
    logger.warning("       sudo ./scripts/install-deps.sh --virtio-win")
    logger.warning("       # or manually:")
    logger.warning("       curl -fSL %s -o %s", VIRTIO_WIN_URL, VIRTIO_WIN_ISO)
    logger.warning("")
    logger.warning("  2. Re-run migration (auto-detected, no extra flags needed):")
    logger.warning("       h2kvmctl --config your-vm.yaml")
    logger.warning("       # or override with: --virtio-drivers-dir /custom/path")
    logger.warning("")
    logger.warning("Option 2: Install VirtIO Drivers After Migration")
    logger.warning("  1. Boot migrated VM in KVM (with SATA/e1000)")
    logger.warning("  2. Attach virtio-win.iso to VM as CD-ROM")
    logger.warning("  3. Run installer: D:\\virtio-win-guest-tools.exe")
    logger.warning("  4. Shut down VM")
    logger.warning("  5. Change libvirt XML to use VirtIO:")
    logger.warning("       <disk ... bus='virtio'>")
    logger.warning("       <interface ... model='virtio'>")
    logger.warning("  6. Start VM - Windows will activate VirtIO drivers")
    logger.warning("")
    logger.warning("Option 3: Let Windows Update Install Drivers (Slowest)")
    logger.warning("  1. Boot migrated VM with internet access")
    logger.warning("  2. Windows Update may install VirtIO drivers (not guaranteed)")
    logger.warning("  3. This may take several hours and require reboots")
    logger.warning("")
    logger.warning("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.warning("")
    logger.warning("ℹ️  Current Configuration:")
    logger.warning("    Disk Bus:     SATA (compatible with all Windows versions)")
    logger.warning("    Network:      e1000 (Intel PRO/1000 - wide compatibility)")
    logger.warning("    Graphics:     QXL (QEMU/KVM standard)")
    logger.warning("")
    logger.warning("    VM will boot successfully but with reduced performance.")
    logger.warning("    Consider using VirtIO drivers for production deployments.")
    logger.warning("")
    logger.warning("=" * 80)
    logger.warning("")


def get_virtio_download_url(windows_version: str | None = None) -> str:
    """
    Get the recommended VirtIO download URL for a specific Windows version.

    Args:
        windows_version: Windows version string (e.g., "10.0", "6.3")

    Returns:
        URL string for downloading VirtIO drivers
    """
    # Main stable repository
    base_url = "https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/"

    # Version-specific recommendations
    version_mapping = {
        "10.0": "virtio-win.iso",  # Windows 10/11, Server 2016+
        "6.3": "virtio-win.iso",  # Windows 8.1, Server 2012 R2
        "6.2": "virtio-win.iso",  # Windows 8, Server 2012
        "6.1": "virtio-win.iso",  # Windows 7, Server 2008 R2
    }

    filename = version_mapping.get(windows_version, "virtio-win.iso")
    return base_url + filename


def get_performance_expectations() -> dict[str, Any]:
    """
    Return expected performance characteristics with and without VirtIO.

    Returns:
        Dict with performance comparison data
    """
    return {
        "storage": {
            "sata": {
                "throughput": "~300-500 MB/s",
                "iops": "~10k-20k IOPS",
                "latency": "~2-5ms",
                "overhead": "~15-25% CPU overhead",
            },
            "virtio_scsi": {
                "throughput": "~600-1000 MB/s",
                "iops": "~30k-50k IOPS",
                "latency": "~0.5-1ms",
                "overhead": "~5-10% CPU overhead",
            },
            "improvement": "+50-100% throughput, +100-150% IOPS, 50-75% lower latency",
        },
        "network": {
            "e1000": {
                "throughput": "~500-800 Mb/s",
                "packet_rate": "~50k-100k pps",
                "overhead": "~20-30% CPU overhead",
            },
            "virtio_net": {
                "throughput": "~1-10 Gb/s",
                "packet_rate": "~200k-1M pps",
                "overhead": "~5-10% CPU overhead",
            },
            "improvement": "+25-1000% throughput depending on workload, +100-900% packet rate",
        },
        "memory": {
            "fixed": {
                "allocation": "Static allocation",
                "ballooning": "Not available",
                "overcommit": "Not possible",
            },
            "virtio_balloon": {
                "allocation": "Dynamic adjustment",
                "ballooning": "Host can reclaim unused memory",
                "overcommit": "Possible with ballooning",
            },
            "improvement": "20-40% better memory utilization across host",
        },
    }


def should_warn_about_virtio(virtio_drivers_dir: str | None = None, quiet: bool = False) -> bool:
    """
    Determine if VirtIO warning should be displayed.

    Args:
        virtio_drivers_dir: Path to VirtIO drivers (None = not provided)
        quiet: Suppress warnings if True

    Returns:
        True if warning should be shown
    """
    if quiet:
        return False

    return bool(not virtio_drivers_dir)


def get_virtio_installation_instructions(post_migration: bool = False) -> str:
    """
    Return step-by-step VirtIO installation instructions.

    Args:
        post_migration: If True, return post-migration installation steps

    Returns:
        Formatted installation instructions
    """
    if post_migration:
        return """
POST-MIGRATION VIRTIO INSTALLATION STEPS:

1. Download VirtIO drivers:
   https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso

2. Attach ISO to running VM:
   virsh attach-disk win10-vm /path/to/virtio-win.iso hdc --type cdrom --mode readonly

3. In Windows guest:
   a. Open File Explorer → CD drive (D: or E:)
   b. Run: virtio-win-guest-tools.exe
   c. Follow installer (installs all VirtIO drivers)
   d. Reboot when prompted

4. Update libvirt XML to use VirtIO devices:
   virsh edit win10-vm

   Change:
     <disk type='file' device='disk'>
       <target dev='sda' bus='sata'/>          → <target dev='vda' bus='virtio'/>
     </disk>

     <interface type='network'>
       <model type='e1000'/>                    → <model type='virtio'/>
     </interface>

5. Shut down VM:
   virsh shutdown win10-vm

6. Start VM with VirtIO devices:
   virsh start win10-vm

7. Verify drivers loaded:
   In Device Manager, check for:
     • Red Hat VirtIO SCSI Controller
     • Red Hat VirtIO Ethernet Adapter
"""
    return """
PRE-MIGRATION VIRTIO PREPARATION:

1. Download VirtIO drivers:
   wget https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso

2. Re-run migration with drivers:
   h2kvm local \\
     --vmdk /path/to/source.vmdk \\
     --virtio-drivers /path/to/virtio-win.iso \\
     --to-output output.qcow2 \\
     --disk-bus virtio \\
     --net-model virtio

3. h2kvm will automatically:
   • Inject VirtIO storage drivers (viostor.sys)
   • Inject VirtIO network drivers (netkvm.sys)
   • Configure boot-critical registry entries
   • Stage driver packages for Plug-and-Play installation

4. First boot will:
   • Detect VirtIO devices
   • Install drivers from staged packages
   • Activate VirtIO storage and network

Result: Full VirtIO performance from first boot!
"""
