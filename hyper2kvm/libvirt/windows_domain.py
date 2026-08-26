# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/libvirt/windows_domain.py
"""
Windows libvirt domain XML emitter (UEFI-focused).

What this module does well (on purpose):
- Generates a sane Windows UEFI libvirt XML with SATA disk + e1000e network
  (Windows has inbox AHCI and Intel NIC drivers — no VirtIO needed)
- Optionally copies the disk into /var/lib/libvirt/images with safe perms + restorecon
- Optionally runs `virsh define` (via sudo) on the generated XML

"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from hyper2kvm.core.xml_utils import (
    xml_escape_attr as _xml_escape_attr,
    xml_escape_text as _xml_escape_text,
)
from hyper2kvm.libvirt.libvirt_utils import (
    default_graphics as _default_graphics,
    default_video as _default_video,
)

from .libvirt_utils import (
    find_qemu_binary,
    sanitize_name as _sanitize_name,
)

WinStage = Literal["bootstrap", "final"]


# Models


# dataclass models the full libvirt domain XML surface (firmware, compute,
# display, disks, Windows-specific enlightenments) as independent fields
@dataclass(frozen=True, slots=True)
# pylint: disable-next=too-many-instance-attributes
class WinDomainSpec:
    """
    Windows domain XML spec (supports both UEFI and BIOS boot).

    Notes:
      - stage=bootstrap => disk on SATA (boots even without VirtIO storage driver)
      - stage=final => disk on VirtIO (performance, requires VirtIO storage driver installed)
      - firmware=uefi => Q35 + OVMF (GPT disks)
      - firmware=bios => i440fx/pc (MBR disks)
      - graphics/video defaults are Windows-friendly for SPICE-based consoles
    """

    name: str
    img_path: str

    # Boot firmware: "uefi" or "bios" (auto-detected from disk partition table)
    firmware: str = "uefi"

    # Firmware / NVRAM (only used when firmware=uefi)
    ovmf_code: str = "/usr/share/edk2/ovmf/OVMF_CODE.fd"
    ovmf_vars_template: str | None = "/usr/share/edk2/ovmf/OVMF_VARS.fd"
    nvram_vars: str = "/var/lib/libvirt/qemu/nvram/VM_VARS.fd"

    # Compute
    memory_mib: int = 8192
    vcpus: int = 4
    machine: str = "q35"

    # Devices
    net_model: str = "e1000e"

    # Display (auto-detected: qxl+spice if SPICE available, virtio+vnc otherwise)
    video: str = field(default_factory=_default_video)
    graphics: str = field(default_factory=_default_graphics)
    graphics_listen: str = "127.0.0.1"  # safer default; use 0.0.0.0 for remote consoles

    # Disk
    disk_cache: str = "none"
    disk_type: str = "qcow2"  # allow "raw" etc.

    # Optional: attach drivers ISO (virtio-win.iso) as CDROM for bootstrap
    driver_iso: str | None = None

    # Windows niceties
    localtime_clock: bool = True

    # Hyper-V enlightenments (auto-enabled for detected Windows guests)
    hyperv: bool = False

    # TPM 2.0 (required for Windows 11+ builds >= 22000)
    tpm: bool = False

    # Secure Boot (UEFI only; auto-enabled for Windows 11+)
    secure_boot: bool = False

    # Additional disks (data/log volumes beyond the boot disk)
    additional_disks: tuple[str, ...] = ()

    # Number of NICs to emit (auto-detected from OVF)
    nic_count: int = 1

    # Boot order: which disk gets boot order=1 in multi-disk scenarios.
    # None means first disk (default). Set from inspect_root for multi-OS guests.
    disk_boot_order: int | None = None


@dataclass(frozen=True, slots=True)
class WinDomainPaths:
    """Output paths produced by emit_windows_domain() (XML, NVRAM, disk copy)."""

    out_dir: Path
    xml_path: Path
    nvram_path: Path | None = None
    disk_path: Path | None = None


# groups every emit_windows_domain() parameter into one config object; the
# field count mirrors WinDomainSpec's independently-configurable XML surface
@dataclass
# pylint: disable-next=too-many-instance-attributes
class WindowsDomainConfig:
    """
    Configuration for Windows domain XML generation.

    Groups all parameters for emit_windows_domain() into logical categories.
    """

    # Required parameters
    name: str
    image_path: Path
    out_dir: Path
    stage: WinStage

    # Boot firmware (resolved by orchestrator; BIOS is the safe default for legacy MBR)
    firmware: str = "bios"  # "uefi" or "bios"

    # Firmware (only used when firmware=uefi)
    ovmf_code: str = "/usr/share/edk2/ovmf/OVMF_CODE.fd"
    ovmf_vars_template: str | None = "/usr/share/edk2/ovmf/OVMF_VARS.fd"
    nvram_vars: str | None = None

    # Compute resources
    memory_mib: int = 8192
    vcpus: int = 4
    machine: str = "q35"

    # Devices
    net_model: str = "e1000e"
    video: str = field(default_factory=_default_video)
    graphics: str = field(default_factory=_default_graphics)
    graphics_listen: str = "127.0.0.1"
    disk_cache: str = "none"
    disk_type: str = "qcow2"
    driver_iso: str | None = None

    # Windows settings
    localtime_clock: bool = True
    hyperv: bool = False

    # Actions
    write_xml: bool = True
    virsh_define: bool = False

    # Storage policy
    copy_to_libvirt_images: bool | None = None
    libvirt_images_dir: str | None = None
    overwrite_disk_copy: bool = False


# Small utilities


def _default_libvirt_images_dir() -> Path:
    return Path("/var/lib/libvirt/images")


def _restorecon_best_effort(path: Path) -> None:
    """
    Best-effort SELinux labeling fix. Silent on systems without restorecon / SELinux.
    """
    if shutil.which("restorecon") is None:
        return
    try:
        subprocess.run(
            ["restorecon", "-v", str(path)],
            check=False,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError):
        # Intentionally swallow: SELinux tools absent or permission issues shouldn't kill flow
        return


def _require_file(path: str | Path, *, label: str) -> Path:
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"{label} not found at {p}. Ensure the file exists and the path is correct.")
    return p


def _resolve_secure_boot_ovmf(ovmf_code: str) -> str:
    """Find Secure Boot OVMF firmware variant, falling back to the original."""
    p = Path(ovmf_code)
    # Common Secure Boot OVMF code paths (Fedora, RHEL, Debian/Ubuntu)
    candidates = [
        p.parent / p.name.replace("OVMF_CODE", "OVMF_CODE.secboot"),
        Path("/usr/share/edk2/ovmf/OVMF_CODE.secboot.fd"),
        Path("/usr/share/OVMF/OVMF_CODE_4M.secboot.fd"),
        Path("/usr/share/OVMF/OVMF_CODE.secboot.fd"),
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return ovmf_code  # fallback: non-secboot variant still works


def _resolve_secure_boot_vars(vars_template: str) -> str:
    """Find Secure Boot OVMF VARS template variant, falling back to the original."""
    p = Path(vars_template)
    candidates = [
        p.parent / p.name.replace("OVMF_VARS", "OVMF_VARS.secboot"),
        Path("/usr/share/edk2/ovmf/OVMF_VARS.secboot.fd"),
        Path("/usr/share/OVMF/OVMF_VARS_4M.secboot.fd"),
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return vars_template


# XML rendering


# builds the full libvirt domain XML tree (firmware, disks, NICs, Hyper-V
# enlightenments, TPM, etc.) in one linear pass; splitting it up would
# obscure how the XML elements relate to each other
# pylint: disable-next=too-many-locals,too-many-branches,too-many-statements
def render_windows_domain_xml(spec: WinDomainSpec, *, stage: WinStage) -> str:
    """
    Render libvirt domain XML for Windows.

    stage:
      - "bootstrap" => disk on SATA (safe boot)
      - "final" => disk on VirtIO (performance)
    """
    if stage not in ("bootstrap", "final"):
        raise ValueError(
            f"Invalid deployment stage '{stage}'. Must be 'bootstrap' (SATA, safe boot) "
            f"or 'final' (VirtIO, performance)."
        )

    img = _require_file(spec.img_path, label="image")
    ovmf_code = _require_file(spec.ovmf_code, label="OVMF_CODE")

    # Always use SATA for Windows — no VirtIO disk support without injected drivers.
    disk_bus = "sata"
    disk_dev = "sda"
    stage_note = "SATA (Windows inbox AHCI driver)"

    # Optional driver ISO (commonly used during bootstrap)
    cdrom_xml = ""
    if spec.driver_iso:
        iso = _require_file(spec.driver_iso, label="driver ISO")
        cdrom_xml = f"""
    <disk type='file' device='cdrom'>
      <driver name='qemu' type='raw' cache='none'/>
      <source file='{_xml_escape_attr(str(iso))}'/>
      <target dev='sdc' bus='sata'/>
      <readonly/>
    </disk>"""

    # Clock: Windows often expects localtime; hypervclock avoids hv-stimer/hv-time QEMU errors
    if spec.localtime_clock:
        clock_xml = """\
  <clock offset='localtime'>
    <timer name='hypervclock' present='yes'/>
  </clock>"""
    else:
        clock_xml = """\
  <clock offset='utc'>
    <timer name='hypervclock' present='yes'/>
  </clock>"""

    # Hyper-V enlightenments (conservative but useful)
    hyperv_xml = ""
    if spec.hyperv:
        hyperv_xml = """
    <hyperv mode='custom'>
      <relaxed state='on'/>
      <vapic state='on'/>
      <spinlocks state='on' retries='8191'/>
    </hyperv>"""

    # Graphics: include listen so it behaves consistently across hosts
    graphics_xml = (
        f" <graphics type='{_xml_escape_attr(spec.graphics)}' autoport='yes' "
        f"listen='{_xml_escape_attr(spec.graphics_listen)}'/>"
    )
    video_xml = f" <video><model type='{_xml_escape_attr(spec.video)}'/></video>"
    input_xml = " <input type='tablet' bus='usb'/>"

    # NICs: emit one per detected NIC (default 1)
    nic_parts = []
    for _ in range(max(1, spec.nic_count)):
        nic_parts.append(f"""
    <interface type='network'>
      <source network='default'/>
      <model type='{_xml_escape_attr(spec.net_model)}'/>
    </interface>""")
    nic_xml = "".join(nic_parts)

    # Additional disks (data/log volumes)
    extra_disks_xml = ""
    if spec.additional_disks:
        dev_letters = "bcdefghijklmnop"
        for i, extra_path in enumerate(spec.additional_disks):
            if i >= len(dev_letters):
                break
            extra_dev = f"{disk_dev[:-1]}{dev_letters[i]}" if disk_dev else f"sd{dev_letters[i]}"
            extra_disks_xml += f"""
    <disk type='file' device='disk'>
      <driver name='qemu' type='{_xml_escape_attr(spec.disk_type)}' cache='{_xml_escape_attr(spec.disk_cache)}'/>
      <source file='{_xml_escape_attr(extra_path)}'/>
      <target dev='{_xml_escape_attr(extra_dev)}' bus='{_xml_escape_attr(disk_bus)}'/>
    </disk>"""

    # Helpful extras for Windows guests — include in both stages so Windows PnP
    # discovers the devices and installs drivers during bootstrap boot.
    memballoon_xml = " <memballoon model='virtio'/>"
    channel_xml = """
    <channel type='unix'>
      <target type='virtio' name='org.qemu.guest_agent.0'/>
    </channel>"""

    # TPM 2.0 (required for Windows 11+, useful for all modern Windows)
    tpm_xml = ""
    if spec.tpm:
        tpm_xml = """
    <tpm model='tpm-tis'>
      <backend type='emulator' version='2.0'/>
    </tpm>"""

    # Build <os> block based on firmware type
    is_uefi = spec.firmware.lower() == "uefi"
    machine = spec.machine if is_uefi else "pc"

    if is_uefi:
        # Secure Boot requires the .secboot OVMF variant
        ovmf_code_path = _resolve_secure_boot_ovmf(str(ovmf_code)) if spec.secure_boot else str(ovmf_code)

        # NVRAM template is optional in libvirt; include attribute only when present
        if spec.ovmf_vars_template:
            # For Secure Boot, prefer the .secboot VARS template if available
            vars_template = spec.ovmf_vars_template
            if spec.secure_boot:
                vars_template = _resolve_secure_boot_vars(vars_template)
            nvram_line = (
                f"    <nvram template='{_xml_escape_attr(vars_template)}'>"
                f"{_xml_escape_text(spec.nvram_vars)}</nvram>"
            )
        else:
            nvram_line = f"    <nvram>{_xml_escape_text(spec.nvram_vars)}</nvram>"

        loader_secure = " secure='yes'" if spec.secure_boot else ""
        os_xml = f"""  <os firmware='efi'>
    <type arch='x86_64' machine='{_xml_escape_attr(machine)}'>hvm</type>
    <loader readonly='yes' type='pflash'{loader_secure}>{_xml_escape_text(ovmf_code_path)}</loader>
{nvram_line}
  </os>"""
    else:
        os_xml = f"""  <os>
    <type arch='x86_64' machine='{_xml_escape_attr(machine)}'>hvm</type>
    <boot dev='hd'/>
  </os>"""

    fw_label = "UEFI" if is_uefi else "BIOS"
    if spec.secure_boot:
        fw_label += " + Secure Boot"

    # NOTE: We keep cpu mode host-passthrough (good default for Windows perf),
    # and avoid piling on dozens of options until the caller asks for them.
    return f"""<domain type='kvm'>
  <name>{_xml_escape_text(spec.name)}</name>
  <description>{_xml_escape_text(f"Windows {fw_label} domain ({stage}): {stage_note}")}</description>
  <memory unit='MiB'>{spec.memory_mib}</memory>
  <vcpu>{spec.vcpus}</vcpu>
{os_xml}
  <features>
    <acpi/>
    <apic/>{hyperv_xml}
  </features>
  <cpu mode='host-passthrough'/>
{clock_xml}
  <devices>
    <emulator>{find_qemu_binary()}</emulator>
    <disk type='file' device='disk'>
      <driver name='qemu' type='{_xml_escape_attr(spec.disk_type)}' cache='{_xml_escape_attr(spec.disk_cache)}'/>
      <source file='{_xml_escape_attr(str(img))}'/>
      <target dev='{_xml_escape_attr(disk_dev)}' bus='{_xml_escape_attr(disk_bus)}'/>
{"      <boot order='" + str(spec.disk_boot_order or 1) + "'/>" if is_uefi or spec.disk_boot_order else ""}
    </disk>{extra_disks_xml}{cdrom_xml}
{nic_xml}
{graphics_xml}
{input_xml}
{video_xml}
{memballoon_xml}
{channel_xml}{tpm_xml}
  </devices>
</domain>
"""


# Storage helpers


def copy_disk_for_libvirt(
    *,
    src: Path,
    name: str,
    dest_dir: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """
    Copy disk into /var/lib/libvirt/images (or override) to avoid perms/SELinux surprises.
    Matches guide: chmod 0644.
    """
    src = Path(src).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(
            f"Disk image not found at {src}. "
            f"Ensure the conversion completed successfully and the output path is correct."
        )

    dest_dir = (dest_dir or _default_libvirt_images_dir()).expanduser().resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    safe = _sanitize_name(name)
    suffix = src.suffix or ".qcow2"
    dst = dest_dir / f"{safe}{suffix}"

    if dst.exists():
        if not overwrite:
            return dst
        try:
            dst.unlink()
        except OSError:
            # If unlink fails, let copy2 raise something meaningful
            pass

    shutil.copy2(src, dst)
    os.chmod(dst, 0o644)
    _restorecon_best_effort(dst)
    return dst


# Output helpers


# pylint: disable-next=too-many-arguments  # all keyword-only output-shaping options
def write_windows_domain_xml(
    *,
    spec: WinDomainSpec,
    out_dir: Path,
    stage: WinStage,
    filename: str | None = None,
    overwrite: bool = True,
    disk_path: Path | None = None,
) -> WinDomainPaths:
    """Render the domain XML for `spec` and write it to `out_dir`, returning the output paths."""
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    xml_text = render_windows_domain_xml(spec, stage=stage)

    xml_name = filename or f"{_sanitize_name(spec.name)}-{stage}.xml"
    xml_path = out_dir / xml_name

    if xml_path.exists() and not overwrite:
        raise FileExistsError(f"domain XML already exists: {xml_path}")

    xml_path.write_text(xml_text, encoding="utf-8")

    return WinDomainPaths(
        out_dir=out_dir,
        xml_path=xml_path,
        nvram_path=Path(spec.nvram_vars) if spec.nvram_vars else None,
        disk_path=disk_path,
    )


def _virsh_define(xml_path: Path) -> subprocess.CompletedProcess[str]:
    """
    Run `virsh define <xml_path>` (via sudo), raising RuntimeError with full
    stdout/stderr context on failure.

    Shared by define_windows_domain() and linux_domain.define_linux_domain()
    (which also auto-starts the domain afterward).
    """
    try:
        cp = subprocess.run(
            ["sudo", "virsh", "define", str(xml_path)],
            check=True,
            text=True,
            capture_output=True,
        )
        if cp.stdout.strip():
            print(cp.stdout.strip())
        return cp
    except subprocess.CalledProcessError as e:
        out = (e.stdout or "").strip()
        err = (e.stderr or "").strip()
        raise RuntimeError(
            "virsh define failed\n"
            f" xml: {xml_path}\n"
            f" rc: {e.returncode}\n"
            f" stdout: {out or '(empty)'}\n"
            f" stderr: {err or '(empty)'}"
        ) from e


def define_windows_domain(*, xml_path: Path) -> None:
    """
    `virsh define <xml>` with good error reporting.
    """
    xml_path = Path(xml_path).expanduser().resolve()
    if not xml_path.exists():
        raise FileNotFoundError(
            f"Libvirt domain XML not found at {xml_path}. "
            f"Generate it first with emit_domain_xml or check the output directory."
        )

    _virsh_define(xml_path)


def emit_windows_domain(config: WindowsDomainConfig) -> WinDomainPaths:
    """
    Emit Windows domain XML using a configuration object.

    Args:
        config: Complete configuration for Windows domain generation

    Returns:
        WinDomainPaths with paths to generated files

    Example:
        config = WindowsDomainConfig(
            name="windows11",
            image_path=Path("/path/to/disk.qcow2"),
            out_dir=Path("/tmp/domains"),
            stage="bootstrap",
            memory_mib=16384,
            vcpus=8,
        )
        paths = emit_windows_domain(config)
    """
    image_path = Path(config.image_path).expanduser().resolve()
    out_dir = Path(config.out_dir).expanduser().resolve()

    if not image_path.exists():
        raise FileNotFoundError(
            f"Converted Windows disk image not found at {image_path}. "
            f"Ensure the conversion step completed successfully."
        )

    # pylint: disable=duplicate-code
    # reason: mirrors the equivalent disk-copy-decision block in
    # linux_domain.emit_linux_domain() -- both configs expose the same field
    # names by convention, but each calls its own module-local
    # _default_libvirt_images_dir()/copy_disk_for_libvirt() (which differ in
    # Linux- vs Windows-specific perms/SELinux handling), so kept independent.
    copy_to_libvirt_images = config.copy_to_libvirt_images
    if copy_to_libvirt_images is None:
        copy_to_libvirt_images = bool(config.virsh_define)

    effective_disk = image_path
    if copy_to_libvirt_images:
        effective_images_dir = (
            Path(config.libvirt_images_dir).expanduser().resolve()
            if config.libvirt_images_dir
            else _default_libvirt_images_dir()
        )
        effective_disk = copy_disk_for_libvirt(
            src=image_path,
            name=config.name,
            dest_dir=effective_images_dir,
            overwrite=config.overwrite_disk_copy,
        )
    # pylint: enable=duplicate-code

    # Decide NVRAM path
    nvram_vars = config.nvram_vars
    if not nvram_vars:
        nvram_dir = Path("/var/lib/libvirt/qemu/nvram")
        nvram_vars = str(nvram_dir / f"{_sanitize_name(config.name)}_VARS.fd")

    spec = WinDomainSpec(
        name=config.name,
        img_path=str(effective_disk),
        firmware=config.firmware,
        ovmf_code=config.ovmf_code,
        ovmf_vars_template=config.ovmf_vars_template,
        nvram_vars=nvram_vars,
        memory_mib=config.memory_mib,
        vcpus=config.vcpus,
        machine=config.machine,
        net_model=config.net_model,
        video=config.video,
        graphics=config.graphics,
        graphics_listen=config.graphics_listen,
        disk_cache=config.disk_cache,
        disk_type=config.disk_type,
        driver_iso=config.driver_iso,
        localtime_clock=config.localtime_clock,
        hyperv=config.hyperv,
    )

    # Caller might only want to know where we'd write things
    if not config.write_xml:
        xml_path = out_dir / f"{_sanitize_name(spec.name)}-{config.stage}.xml"
        return WinDomainPaths(
            out_dir=out_dir,
            xml_path=xml_path,
            nvram_path=Path(spec.nvram_vars),
            disk_path=effective_disk,
        )

    paths = write_windows_domain_xml(
        spec=spec,
        out_dir=out_dir,
        stage=config.stage,
        overwrite=True,
        disk_path=effective_disk,
    )

    if config.virsh_define:
        define_windows_domain(xml_path=paths.xml_path)

    return paths
