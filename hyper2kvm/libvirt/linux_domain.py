# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Libvirt domain XML generation for Linux VMs."""
# hyper2kvm/libvirt/linux_domain.py

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import subprocess
import uuid as _uuid_mod
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Literal

from hyper2kvm.core.xml_utils import xml_escape as _xml

from .libvirt_utils import (
    find_qemu_binary,
    sanitize_name as _sanitize_name,
)
from .windows_domain import (
    _resolve_secure_boot_ovmf,
    _resolve_secure_boot_vars,
    _virsh_define,
)

Firmware = Literal["bios", "uefi"]
Graphics = Literal["none", "vnc", "spice"]
Profile = Literal["default", "minimal-bios-gui"]
ClockOffset = Literal["utc", "localtime"]


@dataclass
class LinuxDomainConfig:  # pylint: disable=too-many-instance-attributes  # covers every knob emit_linux_domain() accepts, grouped by category
    """
    Configuration for Linux domain XML generation.

    Groups all parameters for emit_linux_domain() into logical categories.
    """

    # Required parameters
    name: str
    image_path: Path
    out_dir: Path

    # Profile and firmware
    profile: Profile = "minimal-bios-gui"
    firmware: Firmware = "bios"

    # Compute resources
    memory_mib: int = 4096
    vcpus: int = 2
    machine: str | None = None

    # Disk configuration
    disk_bus: str = "virtio"
    disk_dev: str = "vda"
    disk_type: str = "qcow2"
    disk_cache: str | None = None
    disk_io: str | None = None
    disk_discard: str | None = None
    disk_boot_order: int | None = None

    # High-performance tuning
    hugepages: bool = False
    iothreads: int | None = None
    disable_memballoon: bool = False
    cpu_topology: str | None = None  # "S:C:T" e.g. "1:4:1"
    tsc_timer: bool = False

    # Network
    network: str = "default"
    net_model: str = "virtio"

    # Graphics and display
    graphics: Graphics = "vnc"
    graphics_listen: str = "127.0.0.1"
    video: str = "vga"
    video_heads: int | None = None

    # Peripherals
    usb_tablet: bool = True
    serial_pty: bool = True
    console_pty: bool = True
    cloudinit_iso: str | None = None

    # Clock
    clock: ClockOffset = "utc"

    # UEFI-specific
    ovmf_code: str = "/usr/share/edk2/ovmf/OVMF_CODE.fd"
    nvram_vars: str | None = None
    ovmf_vars_template: str | None = None

    # Network
    mac_address: str | None = None
    nic_count: int = 1

    # Additional disks (data/log volumes beyond the boot disk)
    additional_disks: tuple[str, ...] = ()

    # Secure Boot (UEFI only)
    secure_boot: bool = False

    # Actions
    write_xml: bool = True
    virsh_define: bool = False

    # Cleanup policy
    force_replace: bool = False

    # Storage policy
    copy_to_libvirt_images: bool | None = None
    libvirt_images_dir: str | None = None
    overwrite_disk_copy: bool = False


# Small utilities

_DEFAULT_IMAGES_DIR = Path("/var/lib/libvirt/images")
_DEFAULT_NVRAM_DIR = Path("/var/lib/libvirt/qemu/nvram")


def _default_libvirt_images_dir() -> Path:
    return _DEFAULT_IMAGES_DIR


def _run_sudo(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    # NOTE: keep as simple as possible; user wants deterministic sudo behavior.
    return subprocess.run(["sudo", *args], check=check, text=True, capture_output=True)


def _restorecon_best_effort(path: Path) -> None:
    if shutil.which("restorecon") is None:
        return
    with contextlib.suppress(Exception):
        subprocess.run(["restorecon", "-v", str(path)], check=False, text=True, capture_output=True)


def _validate_positive_int(value: int, *, field: str) -> None:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(
            f"{field} must be a positive integer (e.g., 1024 for memory_mib, 2 for vcpus), got: {value!r}"
        )


def _validate_listen_addr(addr: str) -> None:
    # Keep it lightweight; just avoid empty + obvious junk.
    if not addr or not addr.strip():
        raise ValueError(
            "graphics_listen must be non-empty (e.g., '127.0.0.1' for local-only or '0.0.0.0' for all interfaces)."
        )


# Disk copy policy (avoid perms/SELinux surprises)


def copy_disk_for_libvirt(
    *,
    src: Path,
    name: str,
    dest_dir: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """
    Copy disk into /var/lib/libvirt/images (or override) to avoid perms/SELinux surprises.

    Keeps your prior policy:
      - sudo rm (optional overwrite)
      - sudo cp
      - sudo chown qemu:qemu
      - sudo chmod 0640
      - restorecon best-effort
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
        if overwrite:
            _run_sudo(["rm", "-f", str(dst)], check=True)
        else:
            # Auto-rename with timestamp: name-20260219-164532.qcow2
            dst = dest_dir / f"{safe}-{datetime.now().strftime('%Y%m%d-%H%M%S')}{suffix}"

    _run_sudo(["cp", str(src), str(dst)], check=True)
    _run_sudo(["chown", "qemu:qemu", str(dst)], check=True)
    _run_sudo(["chmod", "0640", str(dst)], check=True)
    _restorecon_best_effort(dst)
    return dst


# Spec


@dataclass(frozen=True)
class LinuxDomainSpec:  # pylint: disable=too-many-instance-attributes  # mirrors LinuxDomainConfig's full knob set for XML rendering
    """
    Linux domain XML spec.

    Two modes:
      - profile="minimal-bios-gui" => emit *exactly* the known-good Photon smoke test XML shape.
      - profile="default" => richer/console-first XML (more knobs).
    """

    name: str
    img_path: str

    profile: Profile = "default"

    # Firmware
    firmware: Firmware = "bios"
    ovmf_code: str = "/usr/share/edk2/ovmf/OVMF_CODE.fd"
    ovmf_vars_template: str | None = None
    nvram_vars: str = "/var/tmp/VM_VARS.fd"

    # Compute
    memory_mib: int = 4096
    vcpus: int = 2

    # Machine
    machine: str = "q35"  # overridden by minimal-bios-gui profile

    # Disk
    disk_bus: str = "virtio"
    disk_dev: str = "vda"
    disk_type: str = "qcow2"
    disk_cache: str | None = None  # None => omit cache attr (matches your working XML)
    disk_io: str | None = None
    disk_discard: str | None = None
    disk_boot_order: int | None = None

    # High-performance tuning
    hugepages: bool = False
    iothreads: int | None = None
    disable_memballoon: bool = False
    cpu_topology: str | None = None  # "S:C:T" e.g. "1:4:1"
    tsc_timer: bool = False

    # Network
    network: str = "default"
    net_model: str = "virtio"
    mac_address: str | None = None
    nic_count: int = 1

    # Additional disks
    additional_disks: tuple[str, ...] = ()

    # Display
    graphics: Graphics = "vnc"
    graphics_listen: str = "127.0.0.1"
    video: str = "vga"
    video_heads: int | None = None
    usb_tablet: bool = True

    # Console (default profile only)
    serial_pty: bool = True
    console_pty: bool = True

    # Optional cloud-init seed ISO (default profile only)
    cloudinit_iso: str | None = None

    # Clock (default profile only)
    clock: ClockOffset = "utc"

    # Secure Boot (UEFI only)
    secure_boot: bool = False


# XML rendering helpers


def _render_nics(spec: LinuxDomainSpec) -> str:
    """Render NIC XML elements (supports multi-NIC from OVF detection)."""
    parts = []
    for i in range(max(1, spec.nic_count)):
        mac_line = ""
        if i == 0 and spec.mac_address:
            mac_line = f"\n      <mac address='{_xml(spec.mac_address)}'/>"
        parts.append(
            f"    <interface type='network'>\n"
            f"      <source network='{_xml(spec.network)}'/>\n"
            f"      <model type='{_xml(spec.net_model)}'/>{mac_line}\n"
            f"    </interface>"
        )
    return "\n".join(parts)


def _render_extra_disks(spec: LinuxDomainSpec) -> str:
    """Render additional disk XML elements for multi-disk VMs."""
    if not spec.additional_disks:
        return ""

    disk_bus = spec.disk_bus
    disk_type = spec.disk_type
    disk_cache = spec.disk_cache or "none"
    disk_dev = spec.disk_dev
    dev_letters = "bcdefghijklmnop"
    parts = []
    for i, path in enumerate(spec.additional_disks):
        if i >= len(dev_letters):
            break
        dev = f"{disk_dev[:-1]}{dev_letters[i]}" if disk_dev else f"vd{dev_letters[i]}"
        cache_attr = f" cache='{_xml(disk_cache)}'" if disk_cache else ""
        parts.append(
            f"\n    <disk type='file' device='disk'>\n"
            f"      <driver name='qemu' type='{_xml(disk_type)}'{cache_attr}/>\n"
            f"      <source file='{_xml(str(path))}'/>\n"
            f"      <target dev='{_xml(dev)}' bus='{_xml(disk_bus)}'/>\n"
            f"    </disk>"
        )
    return "".join(parts)


# XML rendering


def _render_minimal_bios_gui_xml(spec: LinuxDomainSpec) -> str:
    """
    Emit the same shape as your known-good Photon XML:
      - machine='pc'
      - <boot dev='hd'/>
      - disk driver type=qcow2 (no cache)
      - vnc + video + tablet
      - no memballoon / no serial / no extras
    """
    img = Path(spec.img_path)
    if not img.exists():
        raise FileNotFoundError(
            f"Disk image not found at {img}. "
            f"Ensure the conversion completed successfully and the output path is correct."
        )

    _validate_positive_int(spec.memory_mib, field="memory_mib")
    _validate_positive_int(spec.vcpus, field="vcpus")
    _validate_listen_addr(spec.graphics_listen)

    if spec.firmware != "bios":
        raise ValueError(
            "The 'minimal-bios-gui' profile only supports firmware='bios'. "
            "Use profile='default' for UEFI firmware, or set firmware='bios'."
        )

    machine = "pc"
    disk_bus = "virtio"
    disk_dev = "vda"
    disk_type = "qcow2"

    # Your existing small vram tweak (kept), but still minimal.
    vram_attr = ""
    if spec.video == "qxl":
        vram_attr = " vram='65536'"

    return f"""<domain type='kvm'>
  <name>{_xml(spec.name)}</name>
  <uuid>{_uuid_mod.uuid4()}</uuid>
  <memory unit='MiB'>{spec.memory_mib}</memory>
  <vcpu>{spec.vcpus}</vcpu>
  <os>
    <type arch='x86_64' machine='{machine}'>hvm</type>
    <boot dev='hd'/>
  </os>
  <features>
    <acpi/>
    <apic/>
  </features>
  <cpu mode='host-passthrough'/>
  <devices>
    <!-- Disk -->
    <disk type='file' device='disk'>
      <driver name='qemu' type='{disk_type}'/>
      <source file='{_xml(img)}'/>
      <target dev='{disk_dev}' bus='{disk_bus}'/>
    </disk>{_render_extra_disks(spec)}
    <!-- Network -->
{_render_nics(spec)}
    <!-- Graphics -->
    <graphics type='{_xml(spec.graphics)}' autoport='yes' listen='{_xml(spec.graphics_listen)}'/>
    <!-- Video -->
    <video>
      <model type='{_xml(spec.video)}'{vram_attr}/>
    </video>
    <input type='tablet' bus='usb'/>
  </devices>
</domain>
"""


def _default_ovmf_vars_template() -> Path | None:
    candidates = [
        "/usr/share/edk2/ovmf/OVMF_VARS.fd",
        "/usr/share/OVMF/OVMF_VARS.fd",
        "/usr/share/edk2/ovmf/OVMF_VARS.secboot.fd",
        "/usr/share/qemu/OVMF_VARS.fd",
        # Some distros place these under /usr/share/edk2/ovmf/x64/...
        "/usr/share/edk2/ovmf/x64/OVMF_VARS.fd",
        "/usr/share/edk2/ovmf/x64/OVMF_VARS.secboot.fd",
    ]
    for p in candidates:
        pp = Path(p)
        if pp.exists():
            return pp
    return None


# pylint: disable-next=too-many-locals,too-many-branches,too-many-statements  # renders every optional XML section (firmware, disk, graphics, console, cpu, ...) for the "default" domain profile
def _render_default_xml(spec: LinuxDomainSpec) -> str:
    img = Path(spec.img_path)
    if not img.exists():
        raise FileNotFoundError(
            f"Disk image not found at {img}. "
            f"Ensure the conversion completed successfully and the output path is correct."
        )

    _validate_positive_int(spec.memory_mib, field="memory_mib")
    _validate_positive_int(spec.vcpus, field="vcpus")
    if spec.graphics != "none":
        _validate_listen_addr(spec.graphics_listen)

    # OS / firmware block
    os_lines: list[str] = [
        " <os>",
        f" <type arch='x86_64' machine='{_xml(spec.machine)}'>hvm</type>",
    ]

    if spec.firmware == "uefi":
        if not os.path.exists(spec.ovmf_code):
            raise FileNotFoundError(
                f"UEFI firmware (OVMF_CODE) not found at {spec.ovmf_code}. "
                f"Install OVMF: sudo dnf install edk2-ovmf (Fedora/RHEL) "
                f"or sudo apt install ovmf (Debian/Ubuntu)"
            )

        ovmf_code_path = spec.ovmf_code
        if spec.secure_boot:
            ovmf_code_path = _resolve_secure_boot_ovmf(spec.ovmf_code)

        loader_secure = " secure='yes'" if spec.secure_boot else ""
        os_lines.append(
            f" <loader readonly='yes' type='pflash'{loader_secure}>{_xml(ovmf_code_path)}</loader>"
        )

        nvram_line = " <nvram"
        vars_template = spec.ovmf_vars_template
        if spec.secure_boot and vars_template:
            vars_template = _resolve_secure_boot_vars(vars_template)
        if vars_template:
            nvram_line += f" template='{_xml(vars_template)}'"
        nvram_line += f">{_xml(spec.nvram_vars)}</nvram>"
        os_lines.append(nvram_line)

    elif spec.firmware == "bios":
        os_lines.append(" <boot dev='hd'/>")
    else:
        raise ValueError(f"Invalid firmware '{spec.firmware}'. Supported values: 'bios' or 'uefi'.")

    os_lines.append(" </os>")

    tsc_line = "\n    <timer name='tsc' present='yes' mode='native'/>" if spec.tsc_timer else ""
    clock_xml = f"""  <clock offset='{_xml(spec.clock)}'>
    <timer name='rtc' tickpolicy='catchup'/>
    <timer name='pit' tickpolicy='delay'/>
    <timer name='hpet' present='no'/>{tsc_line}
  </clock>"""

    on_actions = """  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>restart</on_crash>"""

    # Optional cloud-init ISO
    cidata_xml = ""
    if spec.cloudinit_iso:
        iso = Path(spec.cloudinit_iso)
        if not iso.exists():
            raise FileNotFoundError(
                f"Cloud-init ISO not found at {iso}. "
                f"Generate it with: genisoimage -output {iso} -volid cidata -joliet -rock user-data meta-data"
            )
        cidata_xml = f"""
    <disk type='file' device='cdrom'>
      <driver name='qemu' type='raw' cache='none'/>
      <source file='{_xml(iso)}'/>
      <target dev='sdc' bus='sata'/>
      <readonly/>
    </disk>"""

    # Disk driver line
    # io='native' requires cache='none' or cache='directsync'; fall back to 'threads'
    effective_io = spec.disk_io
    if effective_io == "native" and spec.disk_cache not in (None, "", "none", "directsync"):
        effective_io = "threads"
    cache_attr = f" cache='{_xml(spec.disk_cache)}'" if spec.disk_cache else ""
    io_attr = f" io='{_xml(effective_io)}'" if effective_io else ""
    discard_attr = f" discard='{_xml(spec.disk_discard)}'" if spec.disk_discard else ""
    iothread_attr = f" iothread='{spec.iothreads}'" if spec.iothreads else ""
    disk_driver = (
        f" <driver name='qemu' type='{_xml(spec.disk_type)}'"
        f"{cache_attr}{io_attr}{discard_attr}{iothread_attr}/>"
    )
    disk_boot = f" <boot order='{spec.disk_boot_order}'/>" if spec.disk_boot_order else ""

    # Graphics / video / input / usb
    graphics_xml = ""
    video_xml = ""
    input_xml = ""
    usb_controller_xml = ""

    if spec.graphics != "none":
        graphics_xml = (
            f" <graphics type='{_xml(spec.graphics)}' autoport='yes' listen='{_xml(spec.graphics_listen)}'/>"
        )
        heads_attr = f" heads='{spec.video_heads}'" if spec.video_heads else ""
        video_xml = f" <video><model type='{_xml(spec.video)}'{heads_attr}/></video>"
        if spec.usb_tablet:
            input_xml = " <input type='tablet' bus='usb'/>"
            usb_controller_xml = " <controller type='usb' index='0' model='qemu-xhci'/>"

    # Console
    serial_xml = " <serial type='pty'><target port='0'/></serial>" if spec.serial_pty else ""
    console_xml = (
        " <console type='pty'><target type='serial' port='0'/></console>" if spec.console_pty else ""
    )

    guest_agent_xml = """    <channel type='unix'>
      <source mode='bind'/>
      <target type='virtio' name='org.qemu.guest_agent.0'/>
    </channel>"""

    rng_xml = """    <rng model='virtio'>
      <backend model='random'>/dev/urandom</backend>
    </rng>"""

    memballoon_xml = (
        " <memballoon model='none'/>" if spec.disable_memballoon else " <memballoon model='virtio'/>"
    )

    # Hugepages
    hugepages_xml = ""
    if spec.hugepages:
        hugepages_xml = """  <memoryBacking>
    <hugepages/>
    <locked/>
  </memoryBacking>
"""

    # IOThreads
    iothreads_xml = ""
    if spec.iothreads:
        iothreads_xml = f"  <iothreads>{spec.iothreads}</iothreads>\n"

    # CPU topology
    if spec.cpu_topology:
        parts = spec.cpu_topology.split(":")
        if len(parts) != 3:
            raise ValueError(
                f"cpu_topology must be 'Sockets:Cores:Threads' format (e.g., '1:2:2' for 4 vCPUs), "
                f"got: {spec.cpu_topology!r}"
            )
        sockets, cores, threads = parts
        cpu_xml = (
            "  <cpu mode='host-passthrough' check='none'>\n"
            f"    <topology sockets='{_xml(sockets)}' cores='{_xml(cores)}' threads='{_xml(threads)}'/>\n"
            "  </cpu>"
        )
    else:
        cpu_xml = "  <cpu mode='host-passthrough' check='none'/>"

    return (
        f"""<domain type='kvm'>
  <name>{_xml(spec.name)}</name>
  <memory unit='MiB'>{spec.memory_mib}</memory>
  <currentMemory unit='MiB'>{spec.memory_mib}</currentMemory>
  <vcpu placement='static'>{spec.vcpus}</vcpu>
"""
        + hugepages_xml
        + iothreads_xml
        + "\n".join(os_lines)
        + "\n"
        + clock_xml
        + "\n"
        + on_actions
        + f"""
  <features>
    <acpi/>
    <apic/>
    <vmport state='off'/>
  </features>
{cpu_xml}
  <devices>
    <emulator>{find_qemu_binary()}</emulator>
{usb_controller_xml}
    <disk type='file' device='disk'>
{disk_driver}
      <source file='{_xml(img)}'/>
      <target dev='{_xml(spec.disk_dev)}' bus='{_xml(spec.disk_bus)}'/>
{disk_boot}
    </disk>{_render_extra_disks(spec)}{cidata_xml}
{_render_nics(spec)}
{serial_xml}
{console_xml}
{graphics_xml}
{input_xml}
{video_xml}
{guest_agent_xml}
{rng_xml}
{memballoon_xml}
  </devices>
</domain>
"""
    )


def render_linux_domain_xml(spec: LinuxDomainSpec) -> str:
    """Render the domain XML for the given spec, dispatching on spec.profile."""
    if spec.profile == "minimal-bios-gui":
        return _render_minimal_bios_gui_xml(spec)
    if spec.profile == "default":
        return _render_default_xml(spec)
    raise ValueError(
        f"Invalid libvirt profile '{spec.profile}'. Supported profiles: 'default', 'minimal-bios-gui'."
    )


# Write/define helpers


@dataclass(frozen=True)
class LinuxDomainPaths:
    """Paths produced by writing (and optionally defining) a Linux domain."""

    out_dir: Path
    xml_path: Path
    nvram_path: Path | None = None
    disk_path: Path | None = None


def write_linux_domain_xml(
    *,
    spec: LinuxDomainSpec,
    out_dir: Path,
    filename: str | None = None,
    overwrite: bool = True,
    disk_path: Path | None = None,
) -> LinuxDomainPaths:
    """Render spec to XML and write it under out_dir, returning the resulting paths."""
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    xml_text = render_linux_domain_xml(spec)
    xml_path = out_dir / (filename or f"{_sanitize_name(spec.name)}.xml")

    if xml_path.exists() and not overwrite:
        # Auto-rename with timestamp: stem-20260219-164532.xml
        stem = xml_path.stem
        suffix = xml_path.suffix
        xml_path = out_dir / f"{stem}-{datetime.now().strftime('%Y%m%d-%H%M%S')}{suffix}"

    xml_path.write_text(xml_text, encoding="utf-8")

    nvram_path: Path | None = Path(spec.nvram_vars) if spec.firmware == "uefi" else None
    return LinuxDomainPaths(out_dir=out_dir, xml_path=xml_path, nvram_path=nvram_path, disk_path=disk_path)


def _domain_exists(name: str) -> bool:
    """Check if a libvirt domain with the given name exists."""
    try:
        result = subprocess.run(
            ["sudo", "virsh", "dominfo", name],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError) as e:
        logger = logging.getLogger(__name__)
        logger.debug("virsh dominfo check failed for '%s': %s", name, e)
        return False


def _domain_state(name: str) -> str | None:
    """Get libvirt domain state (running, shut off, etc.). Returns None if not found."""
    try:
        result = subprocess.run(
            ["sudo", "virsh", "domstate", name],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip().lower()
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def _destroy_and_undefine_domain(name: str) -> None:
    """Destroy (if running) and undefine a libvirt domain, removing its disk copy."""
    # Try destroy first (may fail if already shut off, which is fine)
    subprocess.run(
        ["sudo", "virsh", "destroy", name],
        capture_output=True,
        text=True,
        check=False,
    )
    # Undefine with --remove-all-storage to clean up disk copies in /var/lib/libvirt/images
    result = subprocess.run(
        ["sudo", "virsh", "undefine", name, "--remove-all-storage", "--nvram"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Fallback without --remove-all-storage (older libvirt)
        subprocess.run(
            ["sudo", "virsh", "undefine", name, "--nvram"],
            capture_output=True,
            text=True,
            check=False,
        )
        subprocess.run(
            ["sudo", "virsh", "undefine", name],
            capture_output=True,
            text=True,
            check=False,
        )


def _find_unique_domain_name(base_name: str) -> str:
    """
    Find a unique domain name by appending a timestamp suffix.

    If 'rhel88-converted' exists, produces 'rhel88-converted-20260219-164532'.
    """
    if not _domain_exists(base_name):
        return base_name

    return f"{base_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def define_linux_domain(*, xml_path: Path) -> None:
    """
    Define a libvirt domain from XML and start it.

    Name conflicts are resolved upstream in emit_linux_domain() which
    picks a unique name before disk copy and XML generation.
    """
    # Parse domain name from XML
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        name_elem = root.find("name")
        domain_name = name_elem.text if name_elem is not None else None
    except (ET.ParseError, OSError):
        domain_name = None

    # Define the domain
    _virsh_define(xml_path)

    # Auto-start the domain
    if domain_name:
        try:
            subprocess.run(
                ["sudo", "virsh", "start", domain_name],
                check=True,
                text=True,
                capture_output=True,
            )
            print(f"Domain '{domain_name}' started")
        except subprocess.CalledProcessError as e:
            err = (e.stderr or "").strip()
            if "already running" not in err.lower():
                print(f"Warning: failed to start domain '{domain_name}': {err}")


# High-level "emit" function (your main entry point)


# pylint: disable-next=too-many-locals,too-many-branches,too-many-statements  # orchestrates name-conflict handling, disk copy, UEFI defaults, and XML emission for the whole VM
def emit_linux_domain(config: LinuxDomainConfig) -> LinuxDomainPaths:
    """
    Emit Linux domain XML using a configuration object.

    If a libvirt domain with the same name already exists, automatically
    picks a unique name (appends -2, -3, etc.) so the disk copy, XML,
    and domain definition all use the same unique name.

    Args:
        config: Complete configuration for domain generation

    Returns:
        LinuxDomainPaths with paths to generated files

    Example:
        config = LinuxDomainConfig(
            name="myvm",
            image_path=Path("/path/to/disk.qcow2"),
            out_dir=Path("/tmp/domains"),
            firmware="uefi",
            memory_mib=8192,
            vcpus=4,
        )
        paths = emit_linux_domain(config)
    """
    image_path = config.image_path.expanduser().resolve()
    out_dir = config.out_dir.expanduser().resolve()

    if not image_path.exists():
        raise FileNotFoundError(
            f"Converted disk image not found at {image_path}. "
            f"Ensure the conversion step completed successfully."
        )

    _validate_positive_int(config.memory_mib, field="memory_mib")
    _validate_positive_int(config.vcpus, field="vcpus")

    # Handle existing domain conflicts
    if config.virsh_define and _domain_exists(config.name):
        state = _domain_state(config.name)

        if config.force_replace and state and "shut off" in state:
            # Force-replace only shut-off domains
            print(f"Replaced domain '{config.name}' (force-replace, was {state})")
            _destroy_and_undefine_domain(config.name)
        elif not config.force_replace and state and "shut off" in state:
            # Stale cleanup for shut-off domains
            print(f"Replaced domain '{config.name}' (stale cleanup, was {state})")
            _destroy_and_undefine_domain(config.name)
        else:
            # Running, paused, or any other state: auto-rename to avoid disruption
            new_name = _find_unique_domain_name(config.name)
            print(f"Domain '{config.name}' already exists (state={state or 'unknown'}), using '{new_name}'")
            config = replace(config, name=new_name)

    # pylint: disable=duplicate-code
    # reason: mirrors the equivalent disk-copy-decision block in
    # windows_domain.emit_windows_domain() -- both configs expose the same
    # field names by convention, but each calls its own module-local
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

    # Decide machine defaults
    machine = config.machine
    if machine is None:
        if config.profile == "minimal-bios-gui":
            machine = "pc"
        else:
            machine = "pc" if config.firmware == "bios" else "q35"

    # Decide NVRAM path + default tuning for UEFI
    nvram_path = config.nvram_vars
    disk_cache = config.disk_cache
    disk_io = config.disk_io
    disk_discard = config.disk_discard
    disk_boot_order = config.disk_boot_order
    graphics = config.graphics
    video = config.video
    video_heads = config.video_heads
    ovmf_vars_template = config.ovmf_vars_template

    if config.firmware == "uefi":
        if ovmf_vars_template is None:
            tpl = _default_ovmf_vars_template()
            if tpl is not None:
                ovmf_vars_template = str(tpl)
            else:
                raise FileNotFoundError("No default OVMF_VARS template found.")

        if not nvram_path:
            _DEFAULT_NVRAM_DIR.mkdir(parents=True, exist_ok=True)
            nvram_path = str(_DEFAULT_NVRAM_DIR / f"{_sanitize_name(config.name)}_VARS.fd")

        # Sensible UEFI defaults
        disk_cache = "none" if disk_cache is None else disk_cache
        disk_io = "native" if disk_io is None else disk_io
        disk_discard = "unmap" if disk_discard is None else disk_discard
        disk_boot_order = 1 if disk_boot_order is None else disk_boot_order

        if graphics == "vnc":
            # Local import: domain_emitter imports LinuxDomainConfig/emit_linux_domain from this
            # module at top level, so importing domain_emitter here at top level would create a
            # circular import (verified: it silently disables domain_emitter._LINUX_DOMAIN_OK).
            from .domain_emitter import _default_graphics  # pylint: disable=import-outside-toplevel

            graphics = _default_graphics()
        if video == "vga":
            video = "virtio"
        if video_heads is None:
            video_heads = 1

    spec = LinuxDomainSpec(
        name=config.name,
        img_path=str(effective_disk),
        profile=config.profile,
        firmware=config.firmware,
        ovmf_code=config.ovmf_code,
        ovmf_vars_template=ovmf_vars_template,
        nvram_vars=(nvram_path or "/var/tmp/VM_VARS.fd"),
        memory_mib=config.memory_mib,
        vcpus=config.vcpus,
        machine=machine,
        disk_bus=config.disk_bus,
        disk_dev=config.disk_dev,
        disk_type=config.disk_type,
        disk_cache=disk_cache,
        disk_io=disk_io,
        disk_discard=disk_discard,
        disk_boot_order=disk_boot_order,
        network=config.network,
        net_model=config.net_model,
        mac_address=config.mac_address,
        graphics=graphics,
        graphics_listen=config.graphics_listen,
        video=video,
        video_heads=video_heads,
        usb_tablet=config.usb_tablet,
        serial_pty=config.serial_pty,
        console_pty=config.console_pty,
        cloudinit_iso=config.cloudinit_iso,
        clock=config.clock,
        hugepages=config.hugepages,
        iothreads=config.iothreads,
        disable_memballoon=config.disable_memballoon,
        cpu_topology=config.cpu_topology,
        tsc_timer=config.tsc_timer,
        nic_count=config.nic_count,
        additional_disks=config.additional_disks,
        secure_boot=config.secure_boot,
    )

    if not config.write_xml:
        xml_path = out_dir / f"{_sanitize_name(spec.name)}.xml"
        return LinuxDomainPaths(
            out_dir=out_dir,
            xml_path=xml_path,
            nvram_path=Path(spec.nvram_vars) if config.firmware == "uefi" else None,
            disk_path=effective_disk,
        )

    paths = write_linux_domain_xml(
        spec=spec,
        out_dir=out_dir,
        filename=f"{_sanitize_name(spec.name)}.xml",
        overwrite=False,
        disk_path=effective_disk,
    )

    if config.virsh_define:
        define_linux_domain(xml_path=paths.xml_path)

    return paths
