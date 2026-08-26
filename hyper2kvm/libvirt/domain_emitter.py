# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Libvirt domain XML generation for Linux and Windows VMs.

Emits domain XML definitions from converted VM disks and metadata.
"""

# hyper2kvm/libvirt/domain_emitter.py
from __future__ import annotations

import re
import subprocess
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from hyper2kvm.core.guest_identity import GuestDetector, GuestType, emit_guest_identity_log
from hyper2kvm.core.logger import Log
from hyper2kvm.core.utils import U

from .libvirt_utils import (
    default_graphics as _default_graphics,
    default_video as _default_video,
    has_spice as _has_spice,
)

if TYPE_CHECKING:
    import argparse

    from .linux_domain import Firmware, Profile

# Common OVMF firmware paths across distributions.
_OVMF_SEARCH_PATHS = [
    "/usr/share/edk2/ovmf/OVMF_CODE.fd",  # Fedora/RHEL
    "/usr/share/OVMF/OVMF_CODE.fd",  # Debian/Ubuntu
    "/usr/share/edk2/x64/OVMF_CODE.fd",  # Arch/openSUSE
    "/usr/share/qemu/OVMF_CODE.fd",  # Some distros
    "/usr/share/edk2/ovmf/OVMF_CODE.secboot.fd",  # Secure Boot variant
]


def auto_detect_ovmf() -> str:
    """Auto-detect OVMF firmware path, returning first found or Fedora default."""
    for p in _OVMF_SEARCH_PATHS:
        if Path(p).exists():
            return p
    return "/usr/share/edk2/ovmf/OVMF_CODE.fd"


try:
    from .linux_domain import LinuxDomainConfig, emit_linux_domain  # type: ignore

    _LINUX_DOMAIN_OK = True
except ImportError:  # pragma: no cover
    emit_linux_domain = None  # type: ignore
    LinuxDomainConfig = None  # type: ignore
    _LINUX_DOMAIN_OK = False


try:
    from .windows_domain import WinDomainSpec, render_windows_domain_xml  # type: ignore

    _WIN_DOMAIN_OK = True
except ImportError:  # pragma: no cover
    WinDomainSpec = None  # type: ignore
    render_windows_domain_xml = None  # type: ignore
    _WIN_DOMAIN_OK = False


def _write_text(path: Path, s: str) -> None:
    U.ensure_dir(path.parent)
    path.write_text(s, encoding="utf-8")


def _guess_guest_kind(  # pylint: disable=too-many-return-statements  # ordered priority chain of detection methods
    args: argparse.Namespace, img: Path, logger
) -> str:
    """
    Priority:
      1) explicit args.guest_os (linux/windows)
      2) explicit args.windows / args.win / args.is_windows booleans
      3) guestfs-based detection (shared GuestDetector) + hostnamectl-like log
      4) heuristic from name/image stem
      5) default: linux
    """
    # 1) explicit string
    v = str(getattr(args, "guest_os", "") or "").strip().lower()
    if v in ("windows", "win"):
        Log.trace(logger, "🧠 guest_kind (args.guest_os) -> windows")
        return "windows"
    if v in ("linux", "lin"):
        Log.trace(logger, "🧠 guest_kind (args.guest_os) -> linux")
        return "linux"

    # 2) boolean flags
    for b in ("windows", "win", "is_windows"):
        if bool(getattr(args, b, False)):
            Log.trace(logger, "🧠 guest_kind (args.%s) -> windows", b)
            return "windows"

    # 3) guestfs-based (best signal)
    ident = GuestDetector.detect(img, logger)
    if ident is not None:
        emit_guest_identity_log(logger, ident)
        if ident.type in (GuestType.WINDOWS, GuestType.LINUX):
            Log.trace(
                logger,
                "🧠 guest_kind (guestfs) -> %s (%.0f%% via %s)",
                ident.type.value,
                ident.confidence * 100,
                ident.detection_method,
            )
            return ident.type.value

    # 4) heuristic fallback (filenames)
    name = str(getattr(args, "vm_name", None) or getattr(args, "name", None) or img.stem).lower()
    stem = img.stem.lower()

    windows_patterns = [
        r"windows",
        r"win\d+",
        r"win-\d+",
        r"win_\d+",
        r"win\.",
        r"w2k",
        r"winxp",
        r"win7",
        r"win8",
        r"win10",
        r"win11",
        r"ws\d+",
        r"winserver",
        r"win-server",
        # Windows Server years without "win" prefix (e.g. "2025secure", "2019dc")
        r"(?:^|[\W_])(?:2008|2012|2016|2019|2022|2025)(?:r2)?[\W_\-]?(?:legacy|secure|dc|std|ent|eval|core)?",
        # Server + year (e.g. "server2025", "server-2022")
        r"server[\-_]?(?:2008|2012|2016|2019|2022|2025)",
    ]
    linux_patterns = [
        r"linux",
        r"ubuntu",
        r"debian",
        r"centos",
        r"redhat",
        r"rhel",
        r"fedora",
        r"alma",
        r"rocky",
        r"oracle[\-_]?linux",
        r"arch",
        r"suse",
        r"sles",
        r"alpine",
        r"mint",
        r"gentoo",
        r"photon",  # VMware Photon OS (vCenter appliance)
        r"vcenter",  # vCenter is a Photon Linux appliance
        r"vyos",
        r"openwrt",
        r"nixos",
        r"flatcar",
        r"coreos",
    ]

    for pat in windows_patterns:
        if re.search(pat, name) or re.search(pat, stem):
            Log.trace(logger, "🧠 guest_kind (heuristic:%s) -> windows", pat)
            return "windows"

    for pat in linux_patterns:
        if re.search(pat, name) or re.search(pat, stem):
            Log.trace(logger, "🧠 guest_kind (heuristic:%s) -> linux", pat)
            return "linux"

    # 5) default
    Log.trace(logger, "🧠 guest_kind (default) -> linux")
    return "linux"


def emit_from_args(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements,too-many-nested-blocks
    logger,
    args: argparse.Namespace,
    *,
    out_root: Path,
    out_images: list[Path],
) -> Path | None:
    """
    Emit ONE domain with all images attached (boot disk + additional disks).

    Note:
        Handles the full Windows-vs-Linux domain emission decision tree (firmware,
        graphics, driver ISO, virsh define/start) in one place; splitting it up would
        scatter the many argparse-derived knobs across helper signatures.

    Controlled by args (common):
      - emit_domain_xml: bool
      - virsh_define: bool (Linux emitter supports define; Windows emitter here writes XML only)
      - vm_name, memory, vcpus, uefi, headless, libvirt_network, graphics*, ovmf*
      - machine, disk_cache, out_format, net_model, video
      - nic_count: int (number of NICs, auto-detected from OVF)
      - cloudinit_iso/cloudinit_seed_iso (Linux only)

    Windows-specific knobs (optional):
      - win_stage: bootstrap|final (default bootstrap)
      - win_driver_iso / virtio_win_iso / driver_iso
      - win_localtime_clock: bool (default True)
      - win_hyperv: bool (default True)

    Returns the XML path if written, else None.
    """
    if not getattr(args, "emit_domain_xml", False):
        Log.trace(logger, "🧾 emit_domain_xml disabled")
        return None
    if not out_images:
        Log.trace(logger, "🧾 emit_domain_xml: no outputs")
        return None

    img = Path(out_images[0]).expanduser().resolve()

    base_name = str(getattr(args, "vm_name", None) or getattr(args, "name", None) or img.stem)
    name = f"{base_name}-{uuid.uuid4().hex[:6]}"
    logger.debug("Domain name: %s (base=%s, uuid suffix appended)", name, base_name)
    # Update args so downstream code (virsh_define, libvirt_test) uses the unique name.
    if hasattr(args, "vm_name"):
        args.vm_name = name

    domain_dir = out_root / "libvirt"
    U.ensure_dir(domain_dir)

    guest_kind = _guess_guest_kind(args, img, logger)
    uefi = bool(getattr(args, "uefi", False))
    headless = bool(getattr(args, "headless", False))

    # default graphics policy:
    # - headless => none
    # - otherwise => spice if supported, else vnc
    user_graphics = getattr(args, "graphics", None)
    if headless:
        graphics = "none"
    elif user_graphics:
        graphics = str(user_graphics)
    else:
        graphics = _default_graphics()

    logger.info(
        " emit_domain_xml: guest=%s uefi=%s headless=%s name=%s image=%s",
        guest_kind,
        bool(uefi),
        bool(headless),
        name,
        img,
    )

    logger.debug(
        "emit_from_args: graphics=%s (user=%s, headless=%s, has_spice=%s), video_default=%s",
        graphics,
        user_graphics,
        headless,
        _has_spice(),
        _default_video(),
    )

    # WINDOWS
    if guest_kind == "windows":
        if not _WIN_DOMAIN_OK or WinDomainSpec is None or render_windows_domain_xml is None:
            logger.warning(
                "emit_domain_xml requested for Windows but windows_domain module not available.\n"
                "    Install with: pip install hyper2kvm[libvirt]\n"
                "    Or install libvirt Python bindings: dnf install python3-libvirt"
            )
            return None

        Log.step(logger, "➡️ Emit libvirt domain XML (Windows)")

        # Always use SATA for Windows — no VirtIO disk/network support
        # without injected drivers. Windows has inbox AHCI + e1000e.
        stage = "bootstrap"

        driver_iso = (
            getattr(args, "win_driver_iso", None)
            or getattr(args, "virtio_win_iso", None)
            or getattr(args, "driver_iso", None)
            or getattr(args, "virtio_drivers_dir", None)
        )
        # Only attach as CD-ROM if it's actually an ISO file
        if driver_iso and not str(driver_iso).lower().endswith(".iso"):
            driver_iso = None

        # Auto-detect virtio-win ISO from well-known locations
        if not driver_iso:
            for iso_path in (
                "/var/lib/hyper2kvm/virtio-win.iso",
                "/usr/share/virtio-win/virtio-win.iso",
            ):
                if Path(iso_path).is_file():
                    driver_iso = iso_path
                    logger.info("Auto-detected VirtIO driver ISO: %s", iso_path)
                    break

        win_graphics = "none" if headless else str(getattr(args, "graphics", None) or _default_graphics())

        # Determine firmware: use args.uefi if explicitly set, otherwise auto-detect
        win_firmware = "uefi" if uefi else "bios"
        win_machine = str(getattr(args, "machine", "q35")) if win_firmware == "uefi" else "pc"

        logger.debug(
            "Windows domain: stage=%s, firmware=%s, machine=%s, driver_iso=%s, "
            "graphics=%s, video=%s, tpm=%s, secure_boot=%s, hyperv=%s",
            stage,
            win_firmware,
            win_machine,
            driver_iso,
            win_graphics,
            getattr(args, "video", None) or _default_video(),
            getattr(args, "win_tpm", False),
            getattr(args, "win_secure_boot", False),
            getattr(args, "win_hyperv", True),
        )

        spec = WinDomainSpec(  # type: ignore[misc]
            name=name,
            img_path=str(img),
            firmware=win_firmware,
            ovmf_code=str(getattr(args, "ovmf_code", None) or auto_detect_ovmf()),
            nvram_vars=str(
                getattr(args, "nvram_vars", None) or f"/var/lib/libvirt/qemu/nvram/{name}_VARS.fd"
            ),
            memory_mib=int(getattr(args, "memory", 8192)),
            vcpus=int(getattr(args, "vcpus", 4)),
            machine=win_machine,
            net_model=str(getattr(args, "net_model", "e1000e")),
            video=str(getattr(args, "video", None) or _default_video()),
            graphics=win_graphics,
            graphics_listen=str(getattr(args, "graphics_listen", "127.0.0.1")),
            disk_cache=str(getattr(args, "disk_cache", "none")),
            disk_type=str(getattr(args, "out_format", "qcow2")),
            driver_iso=str(driver_iso) if driver_iso else None,
            localtime_clock=bool(getattr(args, "win_localtime_clock", True)),
            hyperv=bool(getattr(args, "win_hyperv", True)),
            tpm=bool(getattr(args, "win_tpm", False)),
            secure_boot=bool(getattr(args, "win_secure_boot", False)),
            additional_disks=tuple(str(p) for p in out_images[1:]) if len(out_images) > 1 else (),
            nic_count=int(getattr(args, "nic_count", 1)),
            disk_boot_order=getattr(args, "boot_disk_index", None),
        )

        xml = render_windows_domain_xml(spec, stage=stage)  # type: ignore[misc]
        xml_path = domain_dir / f"{name}.xml"
        _write_text(xml_path, xml)
        logger.debug("Windows domain XML written: %s (%d bytes)", xml_path, len(xml))

        logger.info("🧩 Domain XML: %s", xml_path)
        if driver_iso:
            logger.info("💿 VirtIO driver ISO attached: %s (stage=%s)", driver_iso, stage)

        # virsh define + start if requested (same as Linux path).
        if getattr(args, "virsh_define", False):
            try:
                result = subprocess.run(
                    ["virsh", "define", str(xml_path)],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                if result.returncode == 0:
                    logger.info("✅ virsh define: %s", result.stdout.strip())
                    # Auto-start the VM after defining it.
                    if name:
                        try:
                            start_result = subprocess.run(
                                ["virsh", "start", name],
                                capture_output=True,
                                text=True,
                                timeout=30,
                                check=False,
                            )
                            if start_result.returncode == 0:
                                logger.info("✅ virsh start: VM '%s' started", name)
                            else:
                                err = start_result.stderr.strip()
                                if "already running" not in err.lower():
                                    logger.warning("virsh start failed: %s", err)
                        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort auto-start
                            logger.warning("virsh start failed: %s", e)
                else:
                    logger.warning("virsh define failed: %s", result.stderr.strip())
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort virsh define, non-fatal
                logger.warning("virsh define failed: %s", e)

        return xml_path

    # LINUX
    if not _LINUX_DOMAIN_OK or emit_linux_domain is None:
        logger.warning(
            "emit_domain_xml requested but libvirt linux_domain module not available.\n"
            "    Install with: pip install hyper2kvm[libvirt]\n"
            "    Or install libvirt Python bindings: dnf install python3-libvirt"
        )
        return None

    cloudinit_iso = getattr(args, "cloudinit_iso", None) or getattr(args, "cloudinit_seed_iso", None)

    # High-perf convenience: apply defaults only when user hasn't explicitly set each knob
    high_perf = bool(getattr(args, "high_perf", False))
    hugepages = bool(getattr(args, "hugepages", False)) or high_perf
    iothreads = getattr(args, "iothreads", None)
    if iothreads is None and high_perf:
        iothreads = 1
    disable_memballoon = bool(getattr(args, "disable_memballoon", False)) or high_perf
    cpu_topology = getattr(args, "cpu_topology", None) or None
    tsc_timer = bool(getattr(args, "tsc_timer", False)) or high_perf
    disk_io = getattr(args, "disk_io", None) or None
    if disk_io is None and high_perf:
        disk_io = "native"
    disk_discard = getattr(args, "disk_discard", None) or None
    if disk_discard is None and high_perf:
        disk_discard = "unmap"

    Log.step(logger, "➡️ Emit libvirt domain XML (Linux)")
    logger.debug(
        "Linux domain: memory=%s, vcpus=%s, high_perf=%s, hugepages=%s, "
        "iothreads=%s, tsc_timer=%s, disk_io=%s, disk_discard=%s",
        getattr(args, "memory", 2048),
        getattr(args, "vcpus", 2),
        high_perf,
        hugepages,
        iothreads,
        tsc_timer,
        disk_io,
        disk_discard,
    )
    firmware: Firmware = "uefi" if uefi else "bios"
    # minimal-bios-gui only supports BIOS; auto-switch to default for UEFI
    profile: Profile = "default" if firmware == "uefi" else "minimal-bios-gui"
    config = LinuxDomainConfig(  # type: ignore[misc]
        name=name,
        image_path=img,
        out_dir=domain_dir,
        profile=profile,
        firmware=firmware,
        memory_mib=int(getattr(args, "memory", 2048)),
        vcpus=int(getattr(args, "vcpus", 2)),
        machine=str(getattr(args, "machine", "q35")),
        disk_bus=str(getattr(args, "disk_bus", "virtio")),
        disk_dev=str(getattr(args, "disk_dev", "vda")),
        disk_type=str(getattr(args, "out_format", "qcow2")),
        disk_cache=str(getattr(args, "disk_cache", "none")),
        disk_io=disk_io,
        disk_discard=disk_discard,
        network=str(getattr(args, "libvirt_network", "default")),
        net_model=str(getattr(args, "net_model", "virtio")),
        mac_address=getattr(args, "mac_address", None) or None,
        graphics=graphics,
        graphics_listen=str(getattr(args, "graphics_listen", "127.0.0.1")),
        video=str(getattr(args, "video", None) or "virtio"),
        usb_tablet=bool(getattr(args, "usb_tablet", True)),
        serial_pty=True,
        console_pty=True,
        cloudinit_iso=str(cloudinit_iso) if cloudinit_iso else None,
        clock=str(getattr(args, "clock", "utc")),
        ovmf_code=str(getattr(args, "ovmf_code", None) or auto_detect_ovmf()),
        nvram_vars=getattr(args, "nvram_vars", None),
        ovmf_vars_template=getattr(args, "ovmf_vars_template", None),
        write_xml=True,
        virsh_define=bool(getattr(args, "virsh_define", False)),
        force_replace=bool(getattr(args, "force_replace", False)),
        hugepages=hugepages,
        iothreads=iothreads,
        disable_memballoon=disable_memballoon,
        cpu_topology=cpu_topology,
        tsc_timer=tsc_timer,
        disk_boot_order=getattr(args, "boot_disk_index", None),
        additional_disks=tuple(str(p) for p in out_images[1:]) if len(out_images) > 1 else (),
        nic_count=int(getattr(args, "nic_count", 1)),
        secure_boot=bool(getattr(args, "win_secure_boot", False)),
    )
    paths = emit_linux_domain(config)

    logger.info("🧩 Domain XML: %s", paths.xml_path)
    if paths.nvram_path:
        logger.info("🧬 NVRAM: %s", paths.nvram_path)
    return paths.xml_path
