# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Multi-stage Windows VirtIO boot deployment.

Automates the full VirtIO driver lifecycle after offline registry fixes:
  Stage 1 — Bootstrap boot: SATA disk + VirtIO ISO + VirtIO NIC/balloon/channel
  Stage 2 — Wait for QEMU guest agent (proves drivers installed)
  Stage 3 — Shutdown + offline driver verification via NBD
  Stage 4 — Final VM with VirtIO disk bus (or SATA fallback)

Designed so the VM lifecycle ops (define/start/shutdown/destroy) can be
swapped for KubeVirt (virtctl) in the future.

Usage:
    from h2kvm.fixers.windows.virtio_stage import VirtioStagedDeployer

    deployer = VirtioStagedDeployer(
        logger=logger,
        qcow2_path=Path("win10.qcow2"),
        virtio_iso=Path("/path/to/virtio-win.iso"),
        vm_name="win10-converted",
        out_dir=Path("output-win10"),
    )
    result = deployer.run()
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from h2kvm.core.utils import U
from h2kvm.fixers.windows.virtio_deploy import VIRTIO_INSTALL_BAT, VIRTIO_RUNONCE_CMD
from h2kvm.fixers.windows.virtio_injector import (
    VMWARE_SERVICES_CORE,
    VirtIOOfflineInjector,
    cleanup_nbd_mount,
    disable_services_in_hive,
    find_free_nbd,
    find_ntfs_partition,
)
from h2kvm.libvirt.domain_emitter import _default_graphics, auto_detect_ovmf
from h2kvm.libvirt.libvirt_utils import find_qemu_binary

logger = logging.getLogger(__name__)

# Driver files to verify after bootstrap boot
_CRITICAL_DRIVERS = ["viostor.sys"]
_OPTIONAL_DRIVERS = ["netkvm.sys", "vioser.sys", "balloon.sys", "viorng.sys"]


@dataclass
class VirtioStageResult:  # pylint: disable=too-many-instance-attributes
    """Result of the multi-stage VirtIO boot deployment (many independent per-stage fields)."""

    success: bool = False
    stage_reached: int = 0
    guest_agent_responded: bool = False
    drivers_found: list[str] = field(default_factory=list)
    drivers_missing: list[str] = field(default_factory=list)
    viostor_present: bool = False
    final_disk_bus: str = "sata"
    bootstrap_xml: Path | None = None
    final_xml: Path | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict representation of this result."""
        return {
            "success": self.success,
            "stage_reached": self.stage_reached,
            "guest_agent_responded": self.guest_agent_responded,
            "drivers_found": self.drivers_found,
            "drivers_missing": self.drivers_missing,
            "viostor_present": self.viostor_present,
            "final_disk_bus": self.final_disk_bus,
            "bootstrap_xml": str(self.bootstrap_xml) if self.bootstrap_xml else None,
            "final_xml": str(self.final_xml) if self.final_xml else None,
            "errors": self.errors,
        }


# Many independent lifecycle-config fields (memory/vcpus/timeouts/firmware/mode); the public
# surface is intentionally just run() — everything else is a private per-stage helper.
# pylint: disable-next=too-many-instance-attributes,too-few-public-methods
class VirtioStagedDeployer:
    """Multi-stage VirtIO boot deployer for Windows guests.

    Args:
        logger: Logger instance
        qcow2_path: Path to the Windows QCOW2 image
        virtio_iso: Path to VirtIO driver ISO
        vm_name: VM domain name
        out_dir: Output directory for XMLs and NVRAM
        memory_mib: VM memory in MiB
        vcpus: Number of vCPUs
        guest_agent_timeout: Seconds to wait for guest agent
        start_final: Whether to start the final VM
    """

    # Constructor configures many independent, orthogonal deployment knobs
    # (paths, sizing, timeouts, firmware, mode) for the whole staged-deploy lifecycle.
    # Param is named 'logger' (not renamed) because callers (e.g. orchestrator.py) pass it
    # as a keyword argument; only the shadowing of the module-level `logger` is suppressed.
    # pylint: disable-next=too-many-arguments
    def __init__(
        self,
        logger: logging.Logger,  # pylint: disable=redefined-outer-name
        qcow2_path: Path,
        virtio_iso: Path,
        vm_name: str,
        out_dir: Path,
        *,
        memory_mib: int = 4096,
        vcpus: int = 2,
        guest_agent_timeout: int = 180,
        start_final: bool = True,
        firmware: str = "uefi",
        win11_manual_mode: bool = False,
    ):
        self.logger = logger
        self.qcow2_path = Path(qcow2_path).resolve()
        self.virtio_iso = Path(virtio_iso).resolve()
        self.vm_name = vm_name
        self.out_dir = Path(out_dir).resolve()
        self.memory_mib = memory_mib
        self.vcpus = vcpus
        self.guest_agent_timeout = guest_agent_timeout
        self.start_final = start_final
        self.firmware = firmware
        self.win11_manual_mode = win11_manual_mode

        self._bootstrap_name = f"{vm_name}-bootstrap"
        self._libvirt_dir = self.out_dir / "libvirt"

    # Drives the full 4-stage (or Win11-manual single-stage) lifecycle inline so the stage
    # sequence, logging, and result bookkeeping stay easy to follow top-to-bottom.
    # pylint: disable-next=too-many-statements
    def run(self) -> VirtioStageResult:
        """Execute the 4-stage VirtIO deployment lifecycle.

        Returns:
            VirtioStageResult with details of what happened at each stage.
        """
        result = VirtioStageResult()

        try:
            self._libvirt_dir.mkdir(parents=True, exist_ok=True)

            # Ensure QCOW2 is readable by libvirt (qemu user)
            try:
                os.chmod(self.qcow2_path, 0o644)
            except OSError:
                pass

            # Pre-stage: Offline driver injection + VMware disable + auto-logon
            # All done in a single NBD mount cycle
            self.logger.info("Pre-stage: Offline VirtIO driver injection...")
            self._inject_drivers_offline()

            # Detect OVMF and prepare NVRAM
            ovmf_code, ovmf_vars = self._detect_ovmf()
            nvram_path = self._prepare_nvram(ovmf_vars)

            # Ensure libvirt default network
            self._ensure_network()

            # Win11 manual mode: boot once with SATA + VirtIO ISO, let user
            # install drivers manually from the CD. No force-shutdown cycle.
            if self.win11_manual_mode:
                self.logger.info("Win11 manual mode: booting VM with SATA disk + VirtIO ISO attached.")
                self.logger.info(
                    "The user must install VirtIO drivers manually from the CD drive "
                    "(D: or E:) using Device Manager or the virtio-win installer."
                )

                final_xml = self._render_final_xml(
                    ovmf_code,
                    nvram_path,
                    disk_bus="sata",
                )
                result.final_xml = final_xml
                result.final_disk_bus = "sata"

                self._cleanup_domain(self.vm_name)
                self._define_and_start(self.vm_name, final_xml)
                self._wait_running(self.vm_name, timeout_s=60)

                self.logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                self.logger.info(
                    "  VM '%s' is RUNNING (SATA + VirtIO ISO attached)",
                    self.vm_name,
                )
                self.logger.info(
                    "  Connect with: virt-viewer %s",
                    self.vm_name,
                )
                self.logger.info("  Install VirtIO drivers from CD: Device Manager → Update Driver")
                self.logger.info("  Or run: D:\\virtio-win-gt-x64.msi (from the VirtIO CD)")
                self.logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

                result.stage_reached = 4
                result.success = True
                return result

            # Stage 1: Bootstrap boot
            self.logger.info("Stage 1: Generating bootstrap XML (SATA + VirtIO devices)...")
            bootstrap_xml = self._render_bootstrap_xml(ovmf_code, nvram_path)
            result.bootstrap_xml = bootstrap_xml
            self._define_and_start(self._bootstrap_name, bootstrap_xml)
            result.stage_reached = 1
            self.logger.info(
                "Stage 1: VM started: %s (connect: virt-viewer %s)",
                self._bootstrap_name,
                self._bootstrap_name,
            )

            # Stage 2: Wait for guest agent
            self.logger.info(
                "Stage 2: Waiting for guest agent (timeout=%ds)...",
                self.guest_agent_timeout,
            )
            result.guest_agent_responded = self._wait_guest_agent(
                self._bootstrap_name,
                self.guest_agent_timeout,
            )
            result.stage_reached = 2
            if result.guest_agent_responded:
                self.logger.info("Stage 2: Guest agent responding — VirtIO drivers installed")
            else:
                self.logger.warning(
                    "Stage 2: Guest agent did not respond within %ds — drivers may not be fully installed",
                    self.guest_agent_timeout,
                )

            # Stage 3: Shutdown + verify
            self.logger.info("Stage 3: Shutting down for offline verification...")
            self._graceful_shutdown(self._bootstrap_name)
            result.stage_reached = 3

            found, missing = self._verify_drivers_offline()
            result.drivers_found = found
            result.drivers_missing = missing
            result.viostor_present = "viostor.sys" in found

            # TODO: VirtIO disk bus switch requires proper PnP boot-start binding  # pylint: disable=fixme
            # which offline registry promotion alone doesn't achieve. Keep SATA
            # for now; VirtIO NIC/balloon/serial are all working.
            result.final_disk_bus = "sata"
            if result.viostor_present:
                self.logger.info(
                    "Stage 3: viostor.sys present (found: %s, missing: %s). "
                    "Keeping SATA disk bus (VirtIO disk switch planned for future).",
                    found,
                    missing,
                )
            else:
                self.logger.warning(
                    "Stage 3: viostor.sys NOT found — keeping SATA disk bus (found: %s, missing: %s)",
                    found,
                    missing,
                )

            # Clean up bootstrap domain
            self._cleanup_domain(self._bootstrap_name)

            # Stage 4: Final VM
            self.logger.info(
                "Stage 4: Generating final VM (disk bus: %s)...",
                result.final_disk_bus,
            )
            final_xml = self._render_final_xml(
                ovmf_code,
                nvram_path,
                disk_bus=result.final_disk_bus,
            )
            result.final_xml = final_xml

            self._cleanup_domain(self.vm_name)
            if self.start_final:
                self._define_and_start(self.vm_name, final_xml)
                self._wait_running(self.vm_name, timeout_s=60)
                self.logger.info(
                    "Stage 4: Final VM '%s' is RUNNING with %s disk bus",
                    self.vm_name,
                    result.final_disk_bus,
                )
            else:
                self._virsh(["define", str(final_xml)])
                self.logger.info(
                    "Stage 4: Final VM '%s' defined (not started) with %s disk bus",
                    self.vm_name,
                    result.final_disk_bus,
                )

            result.stage_reached = 4
            result.success = True

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Top-level guard for the whole multi-stage lifecycle; any unexpected failure
            # must be recorded and cleaned up rather than crash the caller.
            result.errors.append(str(e))
            self.logger.exception("VirtIO staged deploy failed at stage %d: %s", result.stage_reached, e)
            # Best-effort cleanup
            self._cleanup_domain(self._bootstrap_name)

        return result

    # ── OVMF / NVRAM ──────────────────────────────────────────────────────

    def _detect_ovmf(self) -> tuple[str, str]:
        """Detect OVMF firmware paths. Returns (code_path, vars_path)."""
        code = auto_detect_ovmf()
        if not Path(code).exists():
            raise FileNotFoundError(
                f"UEFI firmware (OVMF) not found at {code}. "
                f"Install OVMF: sudo dnf install edk2-ovmf (Fedora/RHEL) "
                f"or sudo apt install ovmf (Debian/Ubuntu)"
            )
        vars_path = code.replace("CODE", "VARS")
        if not Path(vars_path).exists():
            raise FileNotFoundError(
                f"UEFI NVRAM template (OVMF_VARS) not found at {vars_path}. "
                f"This file is required for UEFI boot. Reinstall OVMF or check the firmware package."
            )
        self.logger.info("OVMF: %s", code)
        return code, vars_path

    def _prepare_nvram(self, ovmf_vars_template: str) -> Path:
        """Copy OVMF_VARS template to output dir for per-VM NVRAM."""
        nvram = self._libvirt_dir / f"{self.vm_name}_VARS.fd"
        if not nvram.exists():
            shutil.copy2(ovmf_vars_template, nvram)
            self.logger.info("NVRAM copy created: %s", nvram)
        return nvram

    # ── Pre-stage: offline driver injection ──────────────────────────────

    def _inject_drivers_offline(self) -> None:
        """Inject VirtIO drivers offline using the deterministic injector."""
        try:
            injector = VirtIOOfflineInjector(
                qcow2_path=self.qcow2_path,
                virtio_iso=self.virtio_iso,
            )
            result = injector.run()

            if result.success:
                self.logger.info(
                    "Offline injection: OS=%s arch=%s injected=%s skipped=%s",
                    result.os_detected,
                    result.arch_detected,
                    result.drivers_injected,
                    result.drivers_skipped,
                )
            else:
                self.logger.warning("Offline injection failed: %s", result.errors)

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Offline driver injection is a best-effort pre-stage; failure must not abort
            # the rest of the staged boot lifecycle (bootstrap boot can still be attempted).
            self.logger.warning("Offline injection failed (non-fatal): %s", e)

    # ── Pre-stage: offline registry fixes ─────────────────────────────────

    # SYSTEM+SOFTWARE hive edits (services, Run keys, auto-logon, RunOnce) each need their
    # own locals/branches; this mirrors the batch-file approach used by WindowsVirtioDeployer.
    # pylint: disable-next=too-many-locals,too-many-statements,too-many-branches
    def _apply_offline_fixes(self) -> None:
        """Offline registry fix via NBD + ntfs-3g + hivex.

        Uses the same batch-file approach as WindowsVirtioDeployer:
        1. Stage batch file into Windows\\Temp
        2. SYSTEM hive: disable VMware services
        3. SOFTWARE hive: neuter VMware Run keys, set RunOnce → batch file
        """
        nbd_dev: str | None = None
        mount_point: Path | None = None

        # pylint: disable=duplicate-code
        # reason: mirrors the NBD-connect + ntfsfix preamble in
        # virtio_injector.py's promote_viostor_boot_start(). Not factored into a shared
        # "connect and prepare" helper because nbd_dev must stay a local var visible to
        # this method's finally/cleanup_nbd_mount() call even if find_ntfs_partition()
        # raises after the NBD device is already connected -- a helper returning
        # (nbd_dev, part_dev) as a single value would lose that partially-connected
        # nbd_dev on the exception path and leak the NBD device.
        try:
            # hivex is an optional dependency (not installed in all environments); imported
            # lazily so the rest of this module works without it.
            import hivex  # pylint: disable=import-outside-toplevel,import-error

            nbd_dev = find_free_nbd()
            subprocess.run(
                ["qemu-nbd", "--connect", nbd_dev, str(self.qcow2_path)],
                check=True,
                capture_output=True,
            )
            time.sleep(2)

            part_dev = find_ntfs_partition(nbd_dev)
            subprocess.run(["ntfsfix", part_dev], check=False, capture_output=True)
            # pylint: enable=duplicate-code

            mount_point = Path(tempfile.mkdtemp(prefix="h2kvm-pre-"))
            subprocess.run(
                ["ntfs-3g", "-o", "remove_hiberfile,force", part_dev, str(mount_point)],
                check=True,
                capture_output=True,
            )

            # Stage batch file into Windows\Temp
            # pylint: disable=duplicate-code
            # reason: mirrors virtio_deploy.py's WindowsVirtioDeployer._stage_virtio_batch()
            # -- this call site needs a "stop after first hit" break inline (not a return
            # from a helper) plus self.logger, so it isn't reused as a shared helper.
            for win_dir in ["Windows", "WINDOWS"]:
                temp_dir = mount_point / win_dir / "Temp"
                if temp_dir.exists():
                    bat_path = temp_dir / "h2kvm-virtio-install.bat"
                    bat_path.write_text(VIRTIO_INSTALL_BAT, encoding="utf-8")
                    self.logger.info("Staged batch file: %s", bat_path.name)
                    break
            # pylint: enable=duplicate-code

            cfg = mount_point / "Windows" / "System32" / "config"
            if not cfg.exists():
                self.logger.warning("Pre-stage: Windows config dir not found — skipping")
                return

            # 1. SYSTEM hive: disable VMware services
            h = hivex.Hivex(str(cfg / "SYSTEM"), write=True)
            cs = h.node_get_child(h.root(), "ControlSet001")
            svc = h.node_get_child(cs, "Services")
            disabled = disable_services_in_hive(h, svc, VMWARE_SERVICES_CORE)
            h.commit(str(cfg / "SYSTEM"))
            self.logger.info("SYSTEM: disabled %d VMware services", len(disabled))

            # 2. SOFTWARE hive: neuter VMware Run keys + RunOnce → batch file
            h2 = hivex.Hivex(str(cfg / "SOFTWARE"), write=True)
            cv = h2.node_get_child(
                h2.node_get_child(h2.node_get_child(h2.root(), "Microsoft"), "Windows"),
                "CurrentVersion",
            )
            run = h2.node_get_child(cv, "Run")
            if run:
                for v in h2.node_values(run):
                    k = h2.value_key(v)
                    if "vmware" in k.lower():
                        h2.node_set_value(run, {"key": k, "t": 1, "value": b"\x00\x00"})

            # Enable auto-logon so RunOnce fires without manual login
            ms = h2.node_get_child(h2.root(), "Microsoft")
            winnt = h2.node_get_child(ms, "Windows NT")
            cv_nt = h2.node_get_child(winnt, "CurrentVersion")
            winlogon = h2.node_get_child(cv_nt, "Winlogon")
            h2.node_set_value(
                winlogon,
                {
                    "key": "AutoAdminLogon",
                    "t": 1,
                    "value": ("1\0").encode("utf-16-le"),
                },
            )
            self.logger.info("SOFTWARE: AutoAdminLogon enabled")

            try:
                ro = h2.node_get_child(cv, "RunOnce")
            except Exception:  # pylint: disable=broad-exception-caught
                # hivex raises for a missing child node; treat as "needs creation" below.
                ro = None
            if not ro:
                ro = h2.node_add_child(cv, "RunOnce")

            h2.node_set_value(
                ro,
                {
                    "key": "h2kvm-virtio",
                    "t": 1,
                    "value": (VIRTIO_RUNONCE_CMD + "\0").encode("utf-16-le"),
                },
            )
            h2.commit(str(cfg / "SOFTWARE"))
            self.logger.info("SOFTWARE: RunOnce → %s", VIRTIO_RUNONCE_CMD)

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Registry pre-stage fixes are best-effort; failure must not abort the deploy.
            self.logger.warning("Pre-stage: offline fixes failed (non-fatal): %s", e)

        finally:
            cleanup_nbd_mount(mount_point, nbd_dev)

    # ── Network ───────────────────────────────────────────────────────────

    def _ensure_network(self) -> None:
        """Ensure libvirt default network is active; add iptables NAT if needed."""
        # Ensure default network exists and is started
        cp = self._virsh(["net-info", "default"], check=False)
        if cp.returncode != 0:
            self.logger.warning("Libvirt default network not found — VM may lack connectivity")
            return

        stdout = (cp.stdout or "").lower()
        if "active:" in stdout and "no" in stdout.split("active:")[-1].split("\n")[0]:
            self._virsh(["net-start", "default"], check=False)

        # Add iptables NAT rules if Docker/nftables interfered
        try:
            cp = self._virsh(["net-dumpxml", "default"], check=False)
            xml_out = cp.stdout or ""
            # Extract subnet from <ip address='...'
            m = re.search(r"address='([0-9.]+)'", xml_out)
            if m:
                base_ip = m.group(1)
                cidr = f"{base_ip.rsplit('.', 1)[0]}.0/24"
                # Check if NAT rule exists
                nat_check = subprocess.run(
                    ["iptables", "-t", "nat", "-C", "POSTROUTING", "-s", cidr, "-j", "MASQUERADE"],
                    check=False,
                    capture_output=True,
                )
                if nat_check.returncode != 0:
                    self.logger.info("Adding NAT masquerade for libvirt network (%s)...", cidr)
                    subprocess.run(
                        ["iptables", "-t", "nat", "-A", "POSTROUTING", "-s", cidr, "-j", "MASQUERADE"],
                        check=False,
                        capture_output=True,
                    )
                    subprocess.run(
                        ["iptables", "-A", "FORWARD", "-s", cidr, "-j", "ACCEPT"],
                        check=False,
                        capture_output=True,
                    )
                    subprocess.run(
                        ["iptables", "-A", "FORWARD", "-d", cidr, "-j", "ACCEPT"],
                        check=False,
                        capture_output=True,
                    )
        except Exception as e:  # pylint: disable=broad-exception-caught
            # NAT setup is a best-effort connectivity nicety; must not abort the deploy.
            self.logger.debug("NAT rule check/add failed (non-fatal): %s", e)

    # ── XML rendering ─────────────────────────────────────────────────────

    def _render_bootstrap_xml(self, ovmf_code: str, nvram_path: Path) -> Path:
        """Render and write bootstrap domain XML (SATA disk + VirtIO devices)."""
        graphics = _default_graphics()
        video = "vga" if graphics == "vnc" else "qxl"

        if self.firmware == "uefi":
            os_xml = f"""\
  <os>
    <type arch='x86_64' machine='q35'>hvm</type>
    <loader readonly='yes' type='pflash'>{ovmf_code}</loader>
    <nvram>{nvram_path}</nvram>
  </os>"""
        else:
            os_xml = """\
  <os>
    <type arch='x86_64' machine='pc'>hvm</type>
    <boot dev='hd'/>
  </os>"""

        xml = f"""\
<domain type='kvm'>
  <name>{self._bootstrap_name}</name>
  <memory unit='MiB'>{self.memory_mib}</memory>
  <vcpu>{self.vcpus}</vcpu>
{os_xml}
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
    <emulator>{find_qemu_binary()}</emulator>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2' cache='none'/>
      <source file='{self.qcow2_path}'/>
      <target dev='sda' bus='sata'/>
      <boot order='1'/>
    </disk>
    <disk type='file' device='cdrom'>
      <driver name='qemu' type='raw'/>
      <source file='{self.virtio_iso}'/>
      <target dev='sdb' bus='sata'/>
    </disk>
    <interface type='network'>
      <source network='default'/>
      <model type='virtio'/>
    </interface>
    <memballoon model='virtio'/>
    <channel type='unix'>
      <target type='virtio' name='org.qemu.guest_agent.0'/>
    </channel>
    <graphics type='{graphics}' autoport='yes' listen='127.0.0.1'/>
    <video><model type='{video}'/></video>
    <input type='tablet' bus='usb'/>
  </devices>
</domain>
"""
        xml_path = self._libvirt_dir / f"{self._bootstrap_name}.xml"
        xml_path.write_text(xml, encoding="utf-8")
        self.logger.info("Bootstrap XML: %s", xml_path)
        return xml_path

    def _render_final_xml(
        self,
        ovmf_code: str,
        nvram_path: Path,
        *,
        disk_bus: str = "virtio",
    ) -> Path:
        """Render and write final domain XML."""
        graphics = _default_graphics()
        video = "vga" if graphics == "vnc" else "qxl"
        disk_dev = "vda" if disk_bus == "virtio" else "sda"

        if self.firmware == "uefi":
            os_xml = f"""\
  <os>
    <type arch='x86_64' machine='q35'>hvm</type>
    <loader readonly='yes' type='pflash'>{ovmf_code}</loader>
    <nvram>{nvram_path}</nvram>
  </os>"""
        else:
            os_xml = """\
  <os>
    <type arch='x86_64' machine='pc'>hvm</type>
    <boot dev='hd'/>
  </os>"""

        xml = f"""\
<domain type='kvm'>
  <name>{self.vm_name}</name>
  <memory unit='MiB'>{self.memory_mib}</memory>
  <vcpu>{self.vcpus}</vcpu>
{os_xml}
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
    <emulator>{find_qemu_binary()}</emulator>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2' cache='none' discard='unmap'/>
      <source file='{self.qcow2_path}'/>
      <target dev='{disk_dev}' bus='{disk_bus}'/>
      <boot order='1'/>
    </disk>
    <disk type='file' device='cdrom'>
      <driver name='qemu' type='raw'/>
      <source file='{self.virtio_iso}'/>
      <target dev='sdb' bus='sata'/>
    </disk>
    <interface type='network'>
      <source network='default'/>
      <model type='virtio'/>
    </interface>
    <memballoon model='virtio'/>
    <channel type='unix'>
      <target type='virtio' name='org.qemu.guest_agent.0'/>
    </channel>
    <graphics type='{graphics}' autoport='yes' listen='127.0.0.1'/>
    <video><model type='{video}'/></video>
    <input type='tablet' bus='usb'/>
    <rng model='virtio'>
      <backend model='random'>/dev/urandom</backend>
    </rng>
  </devices>
</domain>
"""
        xml_path = self._libvirt_dir / f"{self.vm_name}-final.xml"
        xml_path.write_text(xml, encoding="utf-8")
        self.logger.info("Final XML: %s", xml_path)
        return xml_path

    # ── VM lifecycle ops ──────────────────────────────────────────────────

    def _virsh(
        self,
        args: list[str],
        *,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """Run a virsh command."""
        return U.run_cmd(self.logger, ["virsh", *args], check=check, capture=True)

    def _define_and_start(self, name: str, xml_path: Path) -> None:
        """Define and start a libvirt domain."""
        self._cleanup_domain(name)
        self._virsh(["define", str(xml_path)])
        self._virsh(["start", name])

    def _wait_running(self, name: str, timeout_s: int = 60) -> None:
        """Poll virsh domstate until RUNNING or timeout."""
        t0 = time.time()
        while True:
            try:
                st = self._virsh(["domstate", name], check=False).stdout.strip().lower()
            except Exception:  # pylint: disable=broad-exception-caught
                # virsh polling can fail transiently (process error, timeout); treat as unknown.
                st = "unknown"

            if "running" in st:
                elapsed = int(time.time() - t0)
                self.logger.info("Domain %s reached RUNNING after %ds", name, elapsed)
                return

            elapsed = int(time.time() - t0)
            if elapsed > timeout_s:
                raise RuntimeError(f"Timeout waiting for domain {name} to run (state={st})")
            time.sleep(2)

    def _wait_guest_agent(self, name: str, timeout_s: int) -> bool:
        """Poll guest agent ping until responding or timeout.

        Returns True if guest agent responded.
        """
        t0 = time.time()
        # Give Windows a head start
        time.sleep(10)

        while True:
            elapsed = int(time.time() - t0)

            # Check VM is still running
            try:
                st = self._virsh(["domstate", name], check=False).stdout.strip().lower()
            except Exception:  # pylint: disable=broad-exception-caught
                # virsh polling can fail transiently (process error, timeout); treat as unknown.
                st = "unknown"
            if st != "running":
                self.logger.warning("VM state changed to %s during agent wait", st)
                return False

            # Try guest agent ping
            try:
                r = self._virsh(
                    ["qemu-agent-command", name, '{"execute":"guest-ping"}'],
                    check=False,
                )
                if r.returncode == 0 and "return" in (r.stdout or ""):
                    return True
            except Exception:  # pylint: disable=broad-exception-caught
                # A single failed ping attempt just means "not yet"; keep polling.
                pass

            if elapsed > timeout_s:
                return False

            if elapsed % 30 == 0 and elapsed > 0:
                self.logger.info(
                    "Waiting for guest agent: %ds/%ds",
                    elapsed,
                    timeout_s,
                )
            time.sleep(10)

    def _graceful_shutdown(self, name: str, timeout_s: int = 60) -> None:
        """Graceful shutdown with force-destroy fallback."""
        self._virsh(["shutdown", name], check=False)

        t0 = time.time()
        while time.time() - t0 < timeout_s:
            try:
                st = self._virsh(["domstate", name], check=False).stdout.strip().lower()
            except Exception:  # pylint: disable=broad-exception-caught
                # virsh polling can fail transiently; treat as already shut off so this
                # best-effort poll loop exits rather than looping on a broken virsh call.
                st = "shut off"
            if "shut off" in st:
                self.logger.info("Domain %s shut off gracefully", name)
                return
            time.sleep(5)

        # Force destroy
        self.logger.warning("Graceful shutdown timed out — force destroying %s", name)
        self._virsh(["destroy", name], check=False)

    def _cleanup_domain(self, name: str) -> None:
        """Best-effort destroy + undefine."""
        self._virsh(["destroy", name], check=False)
        self._virsh(["undefine", name, "--nvram"], check=False)
        self._virsh(["undefine", name], check=False)

    # ── Offline driver verification ───────────────────────────────────────

    def _verify_drivers_offline(self) -> tuple[list[str], list[str]]:
        """Mount QCOW2 via NBD and check for VirtIO driver files.

        Returns:
            Tuple of (found_drivers, missing_drivers).
        """
        found: list[str] = []
        missing: list[str] = []
        all_drivers = _CRITICAL_DRIVERS + _OPTIONAL_DRIVERS

        nbd_dev: str | None = None
        mount_point: Path | None = None

        try:
            nbd_dev = find_free_nbd()
            subprocess.run(
                ["qemu-nbd", "--connect", nbd_dev, str(self.qcow2_path)],
                check=True,
                capture_output=True,
            )
            time.sleep(2)

            # Find NTFS partition
            part_dev = find_ntfs_partition(nbd_dev)

            # ntfsfix to clear dirty flags
            subprocess.run(["ntfsfix", part_dev], check=False, capture_output=True)

            mount_point = Path(tempfile.mkdtemp(prefix="h2kvm-verify-"))
            subprocess.run(
                ["ntfs-3g", "-o", "ro", part_dev, str(mount_point)],
                check=True,
                capture_output=True,
            )

            # Check for driver files
            for drv in all_drivers:
                drv_path = mount_point / "Windows" / "System32" / "drivers" / drv
                if drv_path.exists():
                    found.append(drv)
                else:
                    missing.append(drv)

            self.logger.info(
                "Driver verification: found=%s missing=%s",
                found,
                missing,
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Offline verification is best-effort; any failure conservatively assumes no
            # drivers were found, so the caller falls back to the SATA disk bus.
            self.logger.warning("Driver verification failed: %s — assuming SATA fallback", e)
            missing = all_drivers

        finally:
            cleanup_nbd_mount(mount_point, nbd_dev)

        return found, missing
