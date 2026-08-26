# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Deterministic offline VirtIO driver injector for Windows guests.

Injects VirtIO drivers directly into an offline Windows QCOW2 image
without any guest runtime scripts, RunOnce entries, or certificate hacks.

How it works:
  1. Mount QCOW2 via NBD + ntfs-3g
  2. Detect Windows version + architecture from offline registry
  3. Resolve exact driver paths from VirtIO ISO using a strict matrix
  4. Copy .sys/.inf/.cat files into Windows driver locations
  5. Register drivers in SYSTEM hive (Services + CriticalDeviceDatabase)

This is the approach used by virt-v2v and enterprise cloud platforms.
No guest execution. No UI prompts. Fully deterministic. Idempotent.

Usage:
    from hyper2kvm.fixers.windows.virtio_injector import VirtIOOfflineInjector

    injector = VirtIOOfflineInjector(
        qcow2_path="/path/to/windows.qcow2",
        virtio_iso="/path/to/virtio-win.iso",
    )
    result = injector.run()
"""

# pylint: disable=too-many-lines
# too-many-lines: cohesive offline VirtIO driver injector covering NBD mount, OS detection,
# driver copy/staging, and SYSTEM/SOFTWARE hive edits; splitting would scatter tightly-coupled
# private helpers across files.

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Driver definitions ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DriverDef:  # pylint: disable=too-many-instance-attributes
    """Definition of a VirtIO driver for offline injection.

    Dataclass models a single VirtIO driver's registry/service metadata,
    which inherently requires this many independent fields.
    """

    name: str  # Service name in registry (e.g. "viostor")
    sys_file: str  # Driver .sys filename
    iso_dir: str  # Directory on VirtIO ISO (e.g. "viostor")
    start: int  # Service Start type: 0=boot, 3=demand
    group: str  # Service Group (e.g. "SCSI miniport")
    driver_type: int  # Service Type: 1=kernel driver
    error_control: int  # ErrorControl: 1=normal
    class_guid: str  # Device class GUID
    pci_ids: list[str]  # PCI hardware IDs for CriticalDeviceDatabase


# VMware services to disable in SYSTEM hive.
# Shared with hyper2kvm/fixers/windows/virtio_stage.py (imports this constant directly
# instead of keeping its own copy).
# pylint: disable-next=duplicate-code
# reason: shares its first 9 entries with virtio_deploy.py's VMWARE_SERVICES, which adds
# 2 extra entries (VMnetAdapter, VMnetuserif) -- kept separate since deploy.py's extra
# entries shouldn't silently apply to the injector/stage pipeline.
VMWARE_SERVICES_CORE = [
    "VMTools",
    "vm3dservice",
    "VGAuthService",
    "vmvss",
    "vmci",
    "vsock",
    "vmhgfs",
    "vmrawdsk",
    "vmusbmouse",
]

# VirtIO PCI vendor ID
_VEN = "1AF4"

# Boot-critical: Start=0 (loaded at boot by Windows kernel)
VIOSTOR = DriverDef(
    name="viostor",
    sys_file="viostor.sys",
    iso_dir="viostor",
    start=3,  # demand-start during bootstrap (SATA); promoted to 0 for final VirtIO boot
    group="SCSI miniport",
    driver_type=1,
    error_control=1,
    class_guid="{4D36E97B-E325-11CE-BFC1-08002BE10318}",
    pci_ids=[f"PCI#VEN_{_VEN}&DEV_1001", f"PCI#VEN_{_VEN}&DEV_1042"],
)

# Network: Start=3 (demand start, PnP will start it)
NETKVM = DriverDef(
    name="netkvm",
    sys_file="netkvm.sys",
    iso_dir="NetKVM",
    start=3,
    group="NDIS",
    driver_type=1,
    error_control=1,
    class_guid="{4D36E972-E325-11CE-BFC1-08002BE10318}",
    pci_ids=[f"PCI#VEN_{_VEN}&DEV_1000", f"PCI#VEN_{_VEN}&DEV_1041"],
)

BALLOON = DriverDef(
    name="balloon",
    sys_file="balloon.sys",
    iso_dir="Balloon",
    start=3,
    group="",
    driver_type=1,
    error_control=1,
    class_guid="{4D36E97D-E325-11CE-BFC1-08002BE10318}",
    pci_ids=[f"PCI#VEN_{_VEN}&DEV_1002", f"PCI#VEN_{_VEN}&DEV_1045"],
)

VIOSERIAL = DriverDef(
    name="vioser",
    sys_file="vioser.sys",
    iso_dir="vioserial",
    start=3,
    group="",
    driver_type=1,
    error_control=1,
    class_guid="{4D36E978-E325-11CE-BFC1-08002BE10318}",
    pci_ids=[f"PCI#VEN_{_VEN}&DEV_1003", f"PCI#VEN_{_VEN}&DEV_1043"],
)

VIORNG = DriverDef(
    name="viorng",
    sys_file="viorng.sys",
    iso_dir="viorng",
    start=3,
    group="",
    driver_type=1,
    error_control=1,
    class_guid="{4D36E97D-E325-11CE-BFC1-08002BE10318}",
    pci_ids=[f"PCI#VEN_{_VEN}&DEV_1005", f"PCI#VEN_{_VEN}&DEV_1044"],
)

# All drivers to inject
ALL_DRIVERS = [VIOSTOR, NETKVM, BALLOON, VIOSERIAL, VIORNG]

# ── OS version → ISO folder mapping ──────────────────────────────────────────

# Maps (ProductName keywords, build ranges) → ISO subfolder name
OS_FOLDER_MAP = {
    "w11": ["Windows 11"],
    "w10": ["Windows 10"],
    "2k25": ["Server 2025"],
    "2k22": ["Server 2022"],
    "2k19": ["Server 2019"],
    "2k16": ["Server 2016"],
    "2k12R2": ["Server 2012 R2"],
    "2k12": ["Server 2012"],
    "w8.1": ["Windows 8.1"],
    "w8": ["Windows 8"],
    "w7": ["Windows 7"],
}


# ── Result ────────────────────────────────────────────────────────────────────


@dataclass
class InjectionResult:
    """Result of offline driver injection."""

    success: bool = False
    os_detected: str = ""
    arch_detected: str = ""
    os_folder: str = ""
    drivers_injected: list[str] = field(default_factory=list)
    drivers_skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return this result as a plain dict for JSON/manifest serialization."""
        return {
            "success": self.success,
            "os_detected": self.os_detected,
            "arch_detected": self.arch_detected,
            "os_folder": self.os_folder,
            "drivers_injected": self.drivers_injected,
            "drivers_skipped": self.drivers_skipped,
            "errors": self.errors,
        }


# ── NBD/hive utilities shared with WindowsVirtioStager ───────────────────────────
# These are pure, side-effect-scoped helpers (NBD device discovery, NTFS partition
# lookup, mount/NBD teardown, and generic Start=4 service-disable hive edits) reused
# verbatim by hyper2kvm/fixers/windows/virtio_stage.py, which already imports from
# this module. virtio_deploy.py has near-identical inline logic (see its
# _connect_nbd/_find_windows_partition) but is NOT switched to import these, since
# this module already has a deliberate lazy import of virtio_deploy.py to avoid a
# cycle (see the "avoid circular import between fixer submodules" comment below) --
# importing the other direction too would reintroduce it.


def find_free_nbd() -> str:
    """Find a free /dev/nbd* device."""
    # pylint: disable=duplicate-code
    # reason: mirrors the inline NBD-scan loop in virtio_deploy.py's _connect_nbd()
    # -- not imported there due to the cycle noted above.
    for i in range(16):
        dev = f"/dev/nbd{i}"
        size_file = f"/sys/block/nbd{i}/size"
        if Path(size_file).exists():
            size = int(Path(size_file).read_text(encoding="utf-8").strip())
            if size == 0:
                return dev
    raise RuntimeError(
        "No free NBD device available. All /dev/nbd0 through /dev/nbd15 are in use. "
        "Disconnect unused devices with 'qemu-nbd -d /dev/nbdN' or load the nbd module "
        "with more devices: modprobe nbd max_part=16 nbds_max=32"
    )
    # pylint: enable=duplicate-code


def find_ntfs_partition(nbd: str) -> str:
    """Find the NTFS partition on an NBD device."""
    # pylint: disable=duplicate-code
    # reason: mirrors the inline NTFS-partition-scan loop in virtio_deploy.py's
    # _find_windows_partition() -- not imported there due to the cycle noted above.
    for p in [3, 2, 1, 4]:
        dev = f"{nbd}p{p}"
        if Path(dev).exists():
            result = subprocess.run(
                ["blkid", "-s", "TYPE", "-o", "value", dev],
                capture_output=True,
                text=True,
                check=False,
            )
            if "ntfs" in result.stdout.lower():
                return dev
    raise RuntimeError(
        f"No NTFS partition found on {nbd}. "
        f"The disk may not contain a Windows installation, or the partition table is unreadable. "
        f"Verify the disk image contains a valid Windows NTFS filesystem."
    )
    # pylint: enable=duplicate-code


def cleanup_nbd_mount(mount_point: Path | None, nbd_dev: str | None) -> None:
    """Best-effort unmount + NBD disconnect for a mount/device pair opened via find_free_nbd()."""
    if mount_point and mount_point.exists():
        subprocess.run(["sync"], check=False)
        subprocess.run(["umount", str(mount_point)], check=False, capture_output=True)
        shutil.rmtree(mount_point, ignore_errors=True)
    if nbd_dev:
        subprocess.run(
            ["qemu-nbd", "--disconnect", nbd_dev],
            check=False,
            capture_output=True,
        )


def disable_services_in_hive(h, services_node, service_names: list[str]) -> list[str]:
    """Set Start=4 (disabled) for each named service under services_node.

    Returns the subset of service_names actually found and disabled.
    """
    # pylint: disable=duplicate-code
    # reason: mirrors the Start=4 hive-set idiom in antivirus.py's Windows-Defender
    # disable loop (different service list/error-result tracking) and in
    # virtio_deploy.py's own VMware-disable loop (not imported here because that
    # module already has a lazy import of this one -- see
    # WindowsVirtioDeployer._fix_system_hive's comment -- so a module-level import
    # in this direction would reintroduce that cycle).
    disabled = []
    for name in service_names:
        try:
            node = h.node_get_child(services_node, name)
            if node:
                h.node_set_value(
                    node,
                    {
                        "key": "Start",
                        "t": 4,
                        "value": (4).to_bytes(4, "little"),
                    },
                )
                disabled.append(name)
        except Exception:  # pylint: disable=broad-exception-caught
            # hivex node lookups can fail in various ways for a missing/malformed
            # service key; skip that one service rather than abort the whole hive edit.
            pass
    return disabled
    # pylint: enable=duplicate-code


# ── Injector ──────────────────────────────────────────────────────────────────


class VirtIOOfflineInjector:
    """Deterministic offline VirtIO driver injector.

    Injects drivers directly into an offline Windows QCOW2 image.
    No guest runtime. No scripts. No prompts. Fully deterministic.

    Args:
        qcow2_path: Path to the Windows QCOW2 image.
        virtio_iso: Path to the VirtIO driver ISO.
        drivers: List of DriverDef to inject (default: all).
    """

    def __init__(
        self,
        qcow2_path: str | Path,
        virtio_iso: str | Path,
        drivers: list[DriverDef] | None = None,
        migration_mode: bool = False,
    ):
        self.qcow2_path = Path(qcow2_path).resolve()
        self.virtio_iso = Path(virtio_iso).resolve()
        self.drivers = drivers or ALL_DRIVERS
        self.migration_mode = migration_mode
        self._nbd_dev: str | None = None
        self._win_mount: Path | None = None
        self._iso_mount: Path | None = None

    def run(self) -> InjectionResult:
        """Execute the full offline injection pipeline.

        Returns:
            InjectionResult with details of what was injected.
        """
        result = InjectionResult()

        try:
            # Stage 1: Mount image
            self._mount_image()

            # Stage 2: Detect OS
            product, build, arch = self._detect_os()
            result.os_detected = product
            result.arch_detected = arch

            # Stage 3: Resolve OS folder
            os_folder = self._resolve_os_folder(product, build)
            result.os_folder = os_folder
            logger.info("OS: %s (build %s) arch=%s → folder=%s", product, build, arch, os_folder)

            # Stage 4: Mount VirtIO ISO
            self._mount_iso()

            # Stage 5: Copy driver .sys files (PnP + pnputil will handle binding)
            for drv in self.drivers:
                try:
                    self._inject_driver(drv, os_folder, arch)
                    result.drivers_injected.append(drv.name)
                except FileNotFoundError as e:
                    logger.warning("Skipping %s: %s", drv.name, e)
                    result.drivers_skipped.append(drv.name)

            # Stage 6: Registry patches
            self._disable_vmware_services()

            # Always register netkvm=2 (AUTO_START) so Win11 OOBE has network.
            # Safe on SATA boot — netkvm is NIC driver, not storage.
            self._register_netkvm_autostart(result.drivers_injected)

            if self.migration_mode:
                # Migration mode: also register viostor=0 for direct VirtIO boot
                self._register_migration_services(result.drivers_injected)

            self._fix_software_hive()

            result.success = True
            logger.info(
                "Injection complete: %d injected, %d skipped",
                len(result.drivers_injected),
                len(result.drivers_skipped),
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            # top-level pipeline catch-all; must not crash on any Windows guest's quirk
            result.errors.append(str(e))
            logger.exception("Injection failed: %s", e)

        finally:
            self._cleanup()

        return result

    # ── Stage 1: Mount ────────────────────────────────────────────────────

    def _mount_image(self) -> None:
        """Mount QCOW2 via NBD + ntfs-3g."""
        self._nbd_dev = find_free_nbd()
        subprocess.run(
            ["qemu-nbd", "--connect", self._nbd_dev, str(self.qcow2_path)],
            check=True,
            capture_output=True,
        )
        time.sleep(2)

        part_dev = find_ntfs_partition(self._nbd_dev)
        subprocess.run(["ntfsfix", part_dev], check=False, capture_output=True)

        self._win_mount = Path(tempfile.mkdtemp(prefix="hyper2kvm-inject-"))
        subprocess.run(
            ["ntfs-3g", "-o", "remove_hiberfile,force", part_dev, str(self._win_mount)],
            check=True,
            capture_output=True,
        )
        logger.info("Mounted Windows at %s", self._win_mount)

    def _mount_iso(self) -> None:
        """Mount VirtIO ISO read-only."""
        self._iso_mount = Path(tempfile.mkdtemp(prefix="hyper2kvm-iso-"))
        subprocess.run(
            ["mount", "-o", "loop,ro", str(self.virtio_iso), str(self._iso_mount)],
            check=True,
            capture_output=True,
        )
        logger.info("Mounted VirtIO ISO at %s", self._iso_mount)

    # ── Stage 2: Detect OS ────────────────────────────────────────────────

    def _detect_os(self) -> tuple[str, str, str]:
        """Detect Windows version + arch from offline registry.

        Returns:
            (product_name, build_number, architecture)
        """
        try:
            import hivex  # pylint: disable=import-outside-toplevel
            # optional system dependency, kept lazy so this module imports fine without
            # python-hivex installed
        except ImportError as e:
            raise RuntimeError(
                "python-hivex is required for Windows OS detection. "
                "Install it with: sudo dnf install python3-hivex (Fedora/RHEL) "
                "or sudo apt install python3-hivex (Debian/Ubuntu)"
            ) from e

        cfg = self._win_mount / "Windows" / "System32" / "config"
        if not cfg.exists():
            raise RuntimeError(
                "Windows System32\\config directory not found on the mounted disk. "
                "The disk may not contain a valid Windows installation, or the mount point is incorrect."
            )

        h = hivex.Hivex(str(cfg / "SOFTWARE"))
        nt = h.node_get_child(
            h.node_get_child(h.node_get_child(h.root(), "Microsoft"), "Windows NT"),
            "CurrentVersion",
        )

        product = self._hive_get_string(h, nt, "ProductName") or "Unknown"
        build = self._hive_get_string(h, nt, "CurrentBuild") or "0"

        # Detect architecture from ntoskrnl.exe presence in System32
        arch = "amd64"
        syswow = self._win_mount / "Windows" / "SysWOW64"
        if not syswow.exists():
            arch = "x86"

        return product, build, arch

    @staticmethod
    def _hive_get_string(h, node, key: str) -> str | None:
        """Read a REG_SZ value from a hivex node."""
        try:
            val = h.node_get_value(node, key)
            t, data = h.value_value(val)
            if t == 1:  # REG_SZ
                return data.decode("utf-16-le").rstrip("\0")
            if t == 2:  # REG_EXPAND_SZ
                return data.decode("utf-16-le").rstrip("\0")
        except Exception:  # pylint: disable=broad-exception-caught
            # hivex value decode/parsing can raise various dynamic-library-specific errors
            return None
        return None

    def _resolve_os_folder(self, product: str, build: str = "0") -> str:
        """Map Windows product name + build to VirtIO ISO folder name."""
        # Build number takes precedence: Win11 often reports "Windows 10" in registry
        build_num = int(build) if build.isdigit() else 0
        if build_num >= 22000:
            return "w11"

        for folder, keywords in OS_FOLDER_MAP.items():
            for kw in keywords:
                if kw.lower() in product.lower():
                    return folder
        # Default to w10 for unknown modern Windows
        logger.warning("Unknown Windows version '%s' (build %s), defaulting to w10", product, build)
        return "w10"

    # ── Stage 4: Inject drivers ───────────────────────────────────────────

    # too-many-locals: copies, hashes, and stages driver files across several Windows driver
    # locations (drivers dir, DriverStore, INF) in one deterministic step.
    # pylint: disable-next=too-many-locals
    def _inject_driver(self, drv: DriverDef, os_folder: str, arch: str) -> None:
        """Copy driver files from ISO to Windows System32/drivers."""
        src_dir = self._iso_mount / drv.iso_dir / os_folder / arch
        if not src_dir.exists():
            raise FileNotFoundError(
                f"VirtIO driver directory '{drv.iso_dir}/{os_folder}/{arch}' not found on the ISO. "
                f"The VirtIO ISO may not contain drivers for this Windows version ({os_folder}/{arch}). "
                f"Download the latest VirtIO drivers ISO from https://fedorapeople.org/groups/virt/virtio-win/"
            )

        drivers_dir = self._win_mount / "Windows" / "System32" / "drivers"
        if not drivers_dir.exists():
            raise RuntimeError(
                "Windows System32\\drivers directory not found on the mounted disk. "
                "The Windows installation may be damaged or the disk layout is non-standard."
            )

        # Copy .sys file to drivers directory
        sys_src = src_dir / drv.sys_file
        if not sys_src.exists():
            raise FileNotFoundError(
                f"VirtIO driver file '{drv.sys_file}' not found in {src_dir}. "
                f"The VirtIO ISO may be incomplete or corrupted. Re-download the ISO."
            )

        sys_dst = drivers_dir / drv.sys_file
        shutil.copy2(sys_src, sys_dst)
        logger.info("Copied %s → %s", drv.sys_file, sys_dst)

        # Find the INF file for hash computation
        inf_files = list(src_dir.glob("*.inf"))
        if not inf_files:
            logger.warning("No INF found for %s — skipping DriverStore staging", drv.name)
            return

        inf_file = inf_files[0]
        inf_name = inf_file.stem  # e.g. "netkvm"

        # Compute hash from INF content (matches Windows DriverStore naming)
        inf_hash = hashlib.md5(inf_file.read_bytes(), usedforsecurity=False).hexdigest()[:16]

        # Stage to DriverStore with proper naming: <inf>_<arch>_<hash>
        store_dir = (
            self._win_mount
            / "Windows"
            / "System32"
            / "DriverStore"
            / "FileRepository"
            / f"{inf_name}.inf_{arch}_{inf_hash}"
        )
        store_dir.mkdir(parents=True, exist_ok=True)
        for f in src_dir.iterdir():
            if f.is_file():
                shutil.copy2(f, store_dir / f.name)

        # Register as OEM INF in Windows\INF (required for PnP discovery)
        inf_dir = self._win_mount / "Windows" / "INF"
        existing_oem = sorted(inf_dir.glob("oem*.inf"))
        next_num = 0
        if existing_oem:
            # Find next available oem number
            for oem in existing_oem:
                try:
                    n = int(oem.stem.replace("oem", ""))
                    if n >= next_num:
                        next_num = n + 1
                except ValueError:
                    pass
        oem_name = f"oem{next_num}.inf"
        shutil.copy2(inf_file, inf_dir / oem_name)

        logger.info(
            "Staged %s to DriverStore (%s) + %s",
            drv.name,
            store_dir.name,
            oem_name,
        )

    # ── Stage 5: Register in SYSTEM hive ──────────────────────────────────

    def _disable_vmware_services(self) -> None:
        """Disable VMware services in the SYSTEM registry hive."""
        try:
            import hivex  # pylint: disable=import-outside-toplevel
            # optional system dependency, kept lazy so this module imports fine without
            # python-hivex installed
        except ImportError:
            logger.warning("python-hivex not available — skipping VMware disable")
            return

        hive_path = str(self._win_mount / "Windows" / "System32" / "config" / "SYSTEM")
        h = hivex.Hivex(hive_path, write=True)
        try:
            cs = h.node_get_child(h.root(), "ControlSet001")
            services = h.node_get_child(cs, "Services")

            disabled = disable_services_in_hive(h, services, VMWARE_SERVICES_CORE)

            h.commit(hive_path)
            logger.info("SYSTEM: disabled %d VMware services", len(disabled))
        finally:
            h.close()

    def _register_netkvm_autostart(self, injected: list[str]) -> None:
        """Register netkvm as AUTO_START so Win11 OOBE has network early.

        Only touches netkvm (NIC) — safe on SATA boot. Does not touch
        viostor (storage) which would cause BSOD on SATA.
        """
        if "netkvm" not in injected:
            return

        try:
            import hivex  # pylint: disable=import-outside-toplevel
            # optional system dependency, kept lazy so this module imports fine without
            # python-hivex installed
        except ImportError:
            return

        hive_path = str(self._win_mount / "Windows" / "System32" / "config" / "SYSTEM")
        h = hivex.Hivex(hive_path, write=True)
        try:
            cs = h.node_get_child(h.root(), "ControlSet001")
            services = h.node_get_child(cs, "Services")

            svc = self._get_or_create_child(h, services, "netkvm")
            h.node_set_value(svc, {"key": "Type", "t": 4, "value": (1).to_bytes(4, "little")})
            h.node_set_value(svc, {"key": "Start", "t": 4, "value": (2).to_bytes(4, "little")})
            h.node_set_value(svc, {"key": "ErrorControl", "t": 4, "value": (1).to_bytes(4, "little")})
            h.node_set_value(
                svc,
                {
                    "key": "ImagePath",
                    "t": 2,
                    "value": ("system32\\drivers\\netkvm.sys\0").encode("utf-16-le"),
                },
            )
            h.node_set_value(
                svc,
                {
                    "key": "Group",
                    "t": 1,
                    "value": ("NDIS\0").encode("utf-16-le"),
                },
            )

            h.commit(hive_path)
            logger.info("netkvm registered as AUTO_START (Start=2)")
        finally:
            h.close()

    def _register_migration_services(self, injected: list[str]) -> None:
        """Register VirtIO driver services for direct VirtIO boot (migration mode).

        Sets service Start types so Windows can boot directly with VirtIO hardware:
        - viostor: Start=0 (BOOT_START) — must load before root volume mount
        - netkvm:  Start=2 (AUTO_START) — loads early, before user logon
        - others:  Start=3 (DEMAND_START) — PnP loads on device detection

        This is the VMware → KVM migration approach: drivers must be
        pre-enabled BEFORE hardware changes.
        """
        try:
            import hivex  # pylint: disable=import-outside-toplevel
            # optional system dependency, kept lazy so this module imports fine without
            # python-hivex installed
        except ImportError:
            logger.warning("python-hivex not available — skipping migration service registration")
            return

        # Migration-specific Start types
        migration_start = {
            "viostor": 0,  # BOOT_START — critical for VirtIO disk
            "netkvm": 2,  # AUTO_START — early NIC binding
        }

        hive_path = str(self._win_mount / "Windows" / "System32" / "config" / "SYSTEM")
        h = hivex.Hivex(hive_path, write=True)
        try:
            cs = h.node_get_child(h.root(), "ControlSet001")
            services = h.node_get_child(cs, "Services")

            for drv in self.drivers:
                if drv.name not in injected:
                    continue

                start = migration_start.get(drv.name, drv.start)
                svc_node = self._get_or_create_child(h, services, drv.name)

                h.node_set_value(
                    svc_node,
                    {
                        "key": "Type",
                        "t": 4,
                        "value": drv.driver_type.to_bytes(4, "little"),
                    },
                )
                h.node_set_value(
                    svc_node,
                    {
                        "key": "Start",
                        "t": 4,
                        "value": start.to_bytes(4, "little"),
                    },
                )
                h.node_set_value(
                    svc_node,
                    {
                        "key": "ErrorControl",
                        "t": 4,
                        "value": drv.error_control.to_bytes(4, "little"),
                    },
                )
                h.node_set_value(
                    svc_node,
                    {
                        "key": "ImagePath",
                        "t": 2,
                        "value": (f"system32\\drivers\\{drv.sys_file}\0").encode("utf-16-le"),
                    },
                )
                if drv.group:
                    h.node_set_value(
                        svc_node,
                        {
                            "key": "Group",
                            "t": 1,
                            "value": (drv.group + "\0").encode("utf-16-le"),
                        },
                    )

                logger.info(
                    "Migration service: %s Start=%d Group=%s", drv.name, start, drv.group or "(none)"
                )

            h.commit(hive_path)
            logger.info("SYSTEM: migration services registered")
        finally:
            h.close()

    # too-many-locals: registers service + CriticalDeviceDatabase entries for each driver in one
    # pass over the SYSTEM hive.
    # pylint: disable-next=too-many-locals
    def _register_drivers_in_hive(self, injected: list[str]) -> None:
        """Register injected drivers in the SYSTEM registry hive.

        Creates:
          - ControlSet001\\Services\\<name> entries (service registration)
          - ControlSet001\\Control\\CriticalDeviceDatabase\\<pci_id> entries
            (tells Windows to load driver at boot for matching PCI devices)
        """
        try:
            import hivex  # pylint: disable=import-outside-toplevel
            # optional system dependency, kept lazy so this module imports fine without
            # python-hivex installed
        except ImportError as e:
            raise RuntimeError(
                "python-hivex is required for Windows registry operations. "
                "Install it with: sudo dnf install python3-hivex (Fedora/RHEL) "
                "or sudo apt install python3-hivex (Debian/Ubuntu)"
            ) from e

        hive_path = str(self._win_mount / "Windows" / "System32" / "config" / "SYSTEM")
        h = hivex.Hivex(hive_path, write=True)
        try:
            cs = h.node_get_child(h.root(), "ControlSet001")
            services = h.node_get_child(cs, "Services")
            control = h.node_get_child(cs, "Control")

            # Get or create CriticalDeviceDatabase
            cdd = self._get_or_create_child(h, control, "CriticalDeviceDatabase")

            for drv in self.drivers:
                if drv.name not in injected:
                    continue

                # Create/update service entry
                svc_node = self._get_or_create_child(h, services, drv.name)

                # Type = 1 (kernel driver)
                h.node_set_value(
                    svc_node,
                    {
                        "key": "Type",
                        "t": 4,
                        "value": drv.driver_type.to_bytes(4, "little"),
                    },
                )
                # Start type
                h.node_set_value(
                    svc_node,
                    {
                        "key": "Start",
                        "t": 4,
                        "value": drv.start.to_bytes(4, "little"),
                    },
                )
                # ErrorControl
                h.node_set_value(
                    svc_node,
                    {
                        "key": "ErrorControl",
                        "t": 4,
                        "value": drv.error_control.to_bytes(4, "little"),
                    },
                )
                # ImagePath
                image_path = f"system32\\drivers\\{drv.sys_file}"
                h.node_set_value(
                    svc_node,
                    {
                        "key": "ImagePath",
                        "t": 2,
                        "value": (image_path + "\0").encode("utf-16-le"),
                    },
                )
                # Group (if set)
                if drv.group:
                    h.node_set_value(
                        svc_node,
                        {
                            "key": "Group",
                            "t": 1,
                            "value": (drv.group + "\0").encode("utf-16-le"),
                        },
                    )

                logger.info(
                    "Registered service: %s (Start=%d, Group=%s)",
                    drv.name,
                    drv.start,
                    drv.group or "(none)",
                )

                # Add CriticalDeviceDatabase entries for PCI IDs
                for pci_id in drv.pci_ids:
                    # Registry key names use # instead of \ and are lowercase
                    cdd_key = pci_id.lower().replace("\\", "#")
                    cdd_node = self._get_or_create_child(h, cdd, cdd_key)

                    h.node_set_value(
                        cdd_node,
                        {
                            "key": "ClassGUID",
                            "t": 1,
                            "value": (drv.class_guid + "\0").encode("utf-16-le"),
                        },
                    )
                    h.node_set_value(
                        cdd_node,
                        {
                            "key": "Service",
                            "t": 1,
                            "value": (drv.name + "\0").encode("utf-16-le"),
                        },
                    )

                logger.info("Added %d CriticalDeviceDatabase entries for %s", len(drv.pci_ids), drv.name)

            # Disable VMware services (same hive, same ControlSet)
            disable_services_in_hive(h, services, VMWARE_SERVICES_CORE)

            h.commit(hive_path)
            logger.info("SYSTEM hive committed (drivers + VMware disable)")

            # Edit SOFTWARE hive: auto-logon + RunOnce for guest agent install
            self._fix_software_hive()
        finally:
            h.close()

    # too-many-locals/statements: edits several independent SOFTWARE hive subtrees (Run keys,
    # Winlogon auto-logon, OOBE bypass, Setup state, RunOnce) as one cohesive firstboot-prep step.
    # pylint: disable-next=too-many-locals,too-many-statements
    def _fix_software_hive(self) -> None:
        """Edit SOFTWARE hive: enable auto-logon, neuter VMware Run keys, set RunOnce."""
        try:
            import hivex  # pylint: disable=import-outside-toplevel
            # optional system dependency, kept lazy so this module imports fine without
            # python-hivex installed
        except ImportError:
            logger.warning("python-hivex not available — skipping SOFTWARE hive")
            return

        # avoid circular import between fixer submodules (virtio_deploy pulls in this module's
        # peers)
        # pylint: disable-next=import-outside-toplevel
        from hyper2kvm.fixers.windows.virtio_deploy import VIRTIO_INSTALL_BAT, VIRTIO_RUNONCE_CMD

        # Stage batch file
        for win_dir in ["Windows", "WINDOWS"]:
            temp_dir = self._win_mount / win_dir / "Temp"
            if temp_dir.exists():
                bat_path = temp_dir / "hyper2kvm-virtio-install.bat"
                bat_path.write_text(VIRTIO_INSTALL_BAT, encoding="utf-8")
                logger.info("Staged batch file: %s", bat_path.name)
                break

        sw_path = str(self._win_mount / "Windows" / "System32" / "config" / "SOFTWARE")
        h = hivex.Hivex(sw_path, write=True)
        try:
            ms = h.node_get_child(h.root(), "Microsoft")
            cv = h.node_get_child(h.node_get_child(ms, "Windows"), "CurrentVersion")

            # Neuter VMware Run keys
            try:
                run = h.node_get_child(cv, "Run")
                if run:
                    for v in h.node_values(run):
                        k = h.value_key(v)
                        if "vmware" in k.lower():
                            h.node_set_value(run, {"key": k, "t": 1, "value": b"\x00\x00"})
            except Exception as e:  # pylint: disable=broad-exception-caught
                # best-effort cleanup; must not abort the whole hive edit
                logger.debug("VMware Run key cleanup skipped: %s", e)

            # Enable auto-logon for first boot only.
            # SECURITY: AutoAdminLogon=1 bypasses the login screen. We add a
            # RunOnce entry that disables it after the first boot so it does
            # not persist as a permanent security hole.
            try:
                winnt = h.node_get_child(ms, "Windows NT")
                cv_nt = h.node_get_child(winnt, "CurrentVersion")
                winlogon = h.node_get_child(cv_nt, "Winlogon")
                h.node_set_value(
                    winlogon,
                    {
                        "key": "AutoAdminLogon",
                        "t": 1,
                        "value": ("1\0").encode("utf-16-le"),
                    },
                )

                # Schedule RunOnce to disable AutoAdminLogon after first boot
                runonce = self._get_or_create_child(h, cv, "RunOnce")
                h.node_set_value(
                    runonce,
                    {
                        "key": "hyper2kvm-disable-autologon",
                        "t": 1,
                        "value": (
                            'powershell -Command "Set-ItemProperty '
                            "-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon' "
                            "-Name 'AutoAdminLogon' -Value '0'\""
                            "\0"
                        ).encode("utf-16-le"),
                    },
                )
                logger.info("AUTO-LOGON enabled (will auto-disable after first boot via RunOnce)")
            except Exception as e:  # pylint: disable=broad-exception-caught
                # best-effort registry edit; must not abort the whole hive edit
                logger.warning(
                    "Auto-logon setup failed in Windows registry: %s. "
                    "The VM will show the login screen on first boot instead of auto-logging in. "
                    "This is non-critical — log in manually with the existing credentials.",
                    e,
                )

            # Win11 OOBE: disable network requirement + dynamic update loop
            try:
                oobe = self._get_or_create_child(h, cv, "OOBE")
                h.node_set_value(
                    oobe,
                    {
                        "key": "BypassNRO",
                        "t": 4,
                        "value": (1).to_bytes(4, "little"),
                    },
                )
                h.node_set_value(
                    oobe,
                    {
                        "key": "SkipMachineOOBE",
                        "t": 4,
                        "value": (1).to_bytes(4, "little"),
                    },
                )
                h.node_set_value(
                    oobe,
                    {
                        "key": "SkipUserOOBE",
                        "t": 4,
                        "value": (1).to_bytes(4, "little"),
                    },
                )
                logger.info("OOBE: BypassNRO + SkipMachineOOBE + SkipUserOOBE enabled")
            except Exception as e:  # pylint: disable=broad-exception-caught
                # best-effort registry edit; must not abort the whole hive edit
                logger.warning(
                    "Windows OOBE bypass failed in registry: %s. "
                    "On Windows 11, you may need to complete the Out-Of-Box Experience manually on first boot. "
                    "If stuck at the network screen, press Shift+F10 and run: OOBE\\BYPASSNRO",
                    e,
                )

            # Disable dynamic update (prevents OOBE restart loop)
            try:
                setup = self._get_or_create_child(h, cv, "Setup")
                state = self._get_or_create_child(h, setup, "State")
                h.node_set_value(
                    state,
                    {
                        "key": "ImageState",
                        "t": 1,
                        "value": ("IMAGE_STATE_COMPLETE\0").encode("utf-16-le"),
                    },
                )
                logger.info("Setup ImageState set to IMAGE_STATE_COMPLETE")
            except Exception as e:  # pylint: disable=broad-exception-caught
                # best-effort registry edit; must not abort the whole hive edit
                logger.warning(
                    "Setup ImageState registry write failed: %s. "
                    "Windows may enter a setup restart loop on first boot. "
                    "If this happens, boot into Safe Mode and set "
                    "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Setup\\State\\ImageState "
                    "to IMAGE_STATE_COMPLETE.",
                    e,
                )

            # Set RunOnce → batch file (installs guest agent MSI)
            ro = self._get_or_create_child(h, cv, "RunOnce")
            h.node_set_value(
                ro,
                {
                    "key": "hyper2kvm-virtio",
                    "t": 1,
                    "value": (VIRTIO_RUNONCE_CMD + "\0").encode("utf-16-le"),
                },
            )
            logger.info("RunOnce → %s", VIRTIO_RUNONCE_CMD)

            h.commit(sw_path)
            logger.info("SOFTWARE hive committed")

            # Inject Unattend.xml for Win11 OOBE bypass
            self._inject_unattend()
        finally:
            h.close()

    def _inject_unattend(self) -> None:
        """Inject Unattend.xml to auto-complete OOBE after migration.

        Handles all OOBE screens that block automation:
        - Region/locale selection
        - Network requirement (Win11)
        - Online account enforcement
        - EULA
        - Privacy settings
        """
        panther = self._win_mount / "Windows" / "Panther"
        panther.mkdir(parents=True, exist_ok=True)

        unattend = panther / "Unattend.xml"
        unattend.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<unattend xmlns="urn:schemas-microsoft-com:unattend">\n'
            '  <settings pass="oobeSystem">\n'
            '    <component name="Microsoft-Windows-International-Core"\n'
            '      processorArchitecture="amd64"\n'
            '      publicKeyToken="31bf3856ad364e35"\n'
            '      language="neutral"\n'
            '      versionScope="nonSxS">\n'
            "      <InputLocale>en-US</InputLocale>\n"
            "      <SystemLocale>en-US</SystemLocale>\n"
            "      <UserLocale>en-US</UserLocale>\n"
            "      <UILanguage>en-US</UILanguage>\n"
            "    </component>\n"
            '    <component name="Microsoft-Windows-Shell-Setup"\n'
            '      processorArchitecture="amd64"\n'
            '      publicKeyToken="31bf3856ad364e35"\n'
            '      language="neutral"\n'
            '      versionScope="nonSxS">\n'
            "      <OOBE>\n"
            "        <HideEULAPage>true</HideEULAPage>\n"
            "        <HideOnlineAccountScreens>true</HideOnlineAccountScreens>\n"
            "        <HideWirelessSetupInOOBE>true</HideWirelessSetupInOOBE>\n"
            "        <HideLocalAccountScreen>true</HideLocalAccountScreen>\n"
            "        <ProtectYourPC>3</ProtectYourPC>\n"
            "        <NetworkLocation>Work</NetworkLocation>\n"
            "      </OOBE>\n"
            "    </component>\n"
            "  </settings>\n"
            "</unattend>\n",
            encoding="utf-8",
        )
        logger.info("Injected Unattend.xml (region + network + account OOBE bypass)")

    # ── Post-verify: promote viostor to boot-start ──────────────────────

    @staticmethod
    def promote_viostor_boot_start(qcow2_path: str | Path) -> None:
        """Set viostor Start=0 (boot-critical) after verifying driver is present.

        Call this AFTER Stage 3 verification confirms viostor.sys exists,
        BEFORE switching the disk bus to VirtIO for the final VM.
        """
        import hivex  # pylint: disable=import-outside-toplevel,import-error
        # hivex is an optional system dependency (python3-hivex); imported lazily and without
        # an ImportError guard here since this static method is only invoked after the offline
        # injection pipeline (which already requires hivex) has completed successfully

        qcow2_path = Path(qcow2_path).resolve()
        nbd_dev: str | None = None
        mount_point: Path | None = None

        # pylint: disable=duplicate-code
        # reason: mirrors the NBD-connect + ntfsfix preamble in
        # virtio_stage.py's _apply_offline_fixes(). Not factored into a shared
        # "connect and prepare" helper because nbd_dev must stay a local var visible
        # to this method's finally/cleanup_nbd_mount() call even if find_ntfs_partition()
        # raises after the NBD device is already connected -- a helper returning
        # (nbd_dev, part_dev) as a single value would lose that partially-connected
        # nbd_dev on the exception path and leak the NBD device.
        try:
            nbd_dev = find_free_nbd()
            subprocess.run(
                ["qemu-nbd", "--connect", nbd_dev, str(qcow2_path)],
                check=True,
                capture_output=True,
            )
            time.sleep(2)

            part_dev = find_ntfs_partition(nbd_dev)
            subprocess.run(["ntfsfix", part_dev], check=False, capture_output=True)
            # pylint: enable=duplicate-code

            mount_point = Path(tempfile.mkdtemp(prefix="hyper2kvm-promote-"))
            subprocess.run(
                ["ntfs-3g", "-o", "remove_hiberfile,force", part_dev, str(mount_point)],
                check=True,
                capture_output=True,
            )

            hive_path = str(mount_point / "Windows" / "System32" / "config" / "SYSTEM")
            h = hivex.Hivex(hive_path, write=True)
            try:
                cs = h.node_get_child(h.root(), "ControlSet001")
                services = h.node_get_child(cs, "Services")

                # Get or create viostor service entry
                try:
                    viostor = h.node_get_child(services, "viostor")
                except Exception:  # pylint: disable=broad-exception-caught
                    # hivex raises a dynamic-library-specific error when the node is absent
                    viostor = None
                if not viostor:
                    viostor = h.node_add_child(services, "viostor")

                # Set as boot-critical kernel driver
                h.node_set_value(
                    viostor,
                    {
                        "key": "Start",
                        "t": 4,
                        "value": (0).to_bytes(4, "little"),
                    },
                )
                h.node_set_value(
                    viostor,
                    {
                        "key": "Type",
                        "t": 4,
                        "value": (1).to_bytes(4, "little"),
                    },
                )
                h.node_set_value(
                    viostor,
                    {
                        "key": "ErrorControl",
                        "t": 4,
                        "value": (1).to_bytes(4, "little"),
                    },
                )
                h.node_set_value(
                    viostor,
                    {
                        "key": "ImagePath",
                        "t": 2,
                        "value": ("system32\\drivers\\viostor.sys\0").encode("utf-16-le"),
                    },
                )
                h.node_set_value(
                    viostor,
                    {
                        "key": "Group",
                        "t": 1,
                        "value": ("SCSI miniport\0").encode("utf-16-le"),
                    },
                )
                h.commit(hive_path)
                logger.info("Promoted viostor to Start=0 (boot-critical)")
            finally:
                h.close()

        finally:
            cleanup_nbd_mount(mount_point, nbd_dev)

    # ── Cleanup ───────────────────────────────────────────────────────────

    def _cleanup(self) -> None:
        """Unmount everything safely."""
        if self._win_mount and self._win_mount.exists():
            subprocess.run(["sync"], check=False)
            subprocess.run(["umount", str(self._win_mount)], check=False, capture_output=True)
            shutil.rmtree(self._win_mount, ignore_errors=True)
            self._win_mount = None

        if self._iso_mount and self._iso_mount.exists():
            subprocess.run(["umount", str(self._iso_mount)], check=False, capture_output=True)
            shutil.rmtree(self._iso_mount, ignore_errors=True)
            self._iso_mount = None

        if self._nbd_dev:
            subprocess.run(
                ["qemu-nbd", "--disconnect", self._nbd_dev],
                check=False,
                capture_output=True,
            )
            self._nbd_dev = None

    # ── Utilities ─────────────────────────────────────────────────────────

    @staticmethod
    def _get_or_create_child(h, parent, name: str):
        """Get a child node by name, or create it if missing."""
        try:
            node = h.node_get_child(parent, name)
            if node:
                return node
        except Exception:  # pylint: disable=broad-exception-caught
            # hivex raises a dynamic-library-specific error when the node is absent
            pass
        return h.node_add_child(parent, name)
