# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""QEMU-based VM testing for validation and smoke tests."""

# h2kvm/testers/qemu_tester.py
from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from ...core.utils import U

if TYPE_CHECKING:
    import logging
    from collections.abc import Sequence

BootMode = Literal["bios", "uefi"]
DisplayMode = Literal["none", "gtk", "sdl", "vnc"]

GuestOS = Literal["linux", "windows"]
WinStage = Literal["bootstrap", "final"]  # bootstrap=sata (safe), final=virtio (fast)


@dataclass(frozen=True)
class QemuDisplay:
    """
    Display behavior:
      - none: headless (-nographic + serial to stdio)
      - gtk/sdl: local GUI (requires a graphical session)
      - vnc: remote display (safe on headless servers)
    """

    mode: DisplayMode = "none"
    vnc_listen: str = "127.0.0.1"
    vnc_display: int = 1  # :1 => TCP 5901


@dataclass(frozen=True)
class QemuNet:
    """
    User-mode networking (no root needed) by default.
    Optionally add SSH port-forward for easy reachability.
    """

    enabled: bool = True
    ssh_forward_host_port: int | None = 2222  # host:2222 -> guest:22 (if guest runs sshd)


@dataclass(frozen=True)
class QemuMachine:
    """
    Machine & accel knobs.
    """

    machine: str = "q35"
    accel: str = "kvm"  # "kvm" or "tcg"
    cpu: str = "host"


@dataclass(frozen=True)
class GuestProfile:
    """
    Guest OS profile.

    Windows needs two-stage boot sometimes:
      - bootstrap: disk SATA (boots even without virtio storage driver)
      - final: disk VirtIO (performance, requires virtio drivers)

    Optional: attach virtio-win ISO during bootstrap.
    """

    os: GuestOS = "linux"
    win_stage: WinStage = "final"
    driver_iso: Path | None = None

    # Windows niceties
    localtime_clock: bool = True
    hyperv: bool = True


class QemuTest:
    """
    QEMU smoke test runner.

    Enhancements:
      - richer logging (choices + resolved paths + final cmd)
      - more defensive accel fallback and cleanup
      - Windows support via GuestProfile:
          * bootstrap (SATA disk) + optional virtio-win ISO
          * final (VirtIO disk)
      - Windows-friendly defaults:
          * localtime clock (optional)
          * Hyper-V enlightenments (optional)
          * video defaults for early Windows boot (vga) when GUI enabled
      - ensures temp OVMF VARS + tmp ISO copies are cleaned when possible
      - optional timeout so it can “smoke” and then stop
    """

    _OVMF_CODE_CANDIDATES: Sequence[str] = (
        "/usr/share/OVMF/OVMF_CODE.fd",
        "/usr/share/edk2/ovmf/OVMF_CODE.fd",
        "/usr/share/qemu/OVMF_CODE.fd",
        "/usr/share/edk2/x64/OVMF_CODE.fd",
        "/usr/share/edk2/ovmf/OVMF_CODE.secboot.fd",
        "/usr/share/edk2/x64/OVMF_CODE.secboot.fd",
    )
    _OVMF_VARS_CANDIDATES: Sequence[str] = (
        "/usr/share/OVMF/OVMF_VARS.fd",
        "/usr/share/edk2/ovmf/OVMF_VARS.fd",
        "/usr/share/qemu/OVMF_VARS.fd",
        "/usr/share/edk2/x64/OVMF_VARS.fd",
        "/usr/share/edk2/ovmf/OVMF_VARS.secboot.fd",
        "/usr/share/edk2/x64/OVMF_VARS.secboot.fd",
    )

    @staticmethod
    def run(
        logger: logging.Logger,
        disk: Path,
        *,
        memory_mib: int,
        vcpus: int,
        uefi: bool,
        # New knobs (safe defaults):
        display: QemuDisplay | None = None,
        net: QemuNet | None = None,
        machine: QemuMachine | None = None,
        timeout_s: int | None = 20,
        extra_args: Sequence[str] | None = None,
        # ✅ Windows support (default remains Linux)
        guest_os: GuestOS = "linux",
        windows_stage: WinStage = "final",
        windows_driver_iso: Path | None = None,  # virtio-win.iso (bootstrap)
        windows_hyperv: bool = True,
        windows_localtime_clock: bool = True,
    ) -> None:
        from h2kvm.libvirt.libvirt_utils import find_qemu_binary

        qemu_bin = find_qemu_binary()
        if not Path(qemu_bin).is_file():
            U.die(logger, "💥 QEMU binary not found (tried qemu-system-x86_64, qemu-kvm).", 1)

        disk = Path(disk)
        if not disk.exists():
            U.die(logger, f"💥 Disk not found: {disk}", 1)

        display = display or QemuDisplay(mode="none")
        net = net or QemuNet(enabled=True, ssh_forward_host_port=2222)
        machine = machine or QemuMachine(machine="q35", accel="kvm", cpu="host")
        extra_args = list(extra_args or [])

        prof = GuestProfile(
            os=guest_os,
            win_stage=windows_stage,
            driver_iso=Path(windows_driver_iso) if windows_driver_iso else None,
            localtime_clock=windows_localtime_clock,
            hyperv=windows_hyperv,
        )

        # accel fallback: if /dev/kvm missing, auto-switch to tcg (slow but works)
        if machine.accel == "kvm" and not os.path.exists("/dev/kvm"):
            logger.warning("⚠️ /dev/kvm missing; falling back to TCG (no KVM acceleration).")
            machine = QemuMachine(machine=machine.machine, accel="tcg", cpu="max")

        img_fmt = QemuTest._detect_img_format(logger, disk)

        # Track temp files so we can clean them.
        tmp_ovmf_vars: str | None = None

        # Disk bus selection:
        # - Linux: virtio
        # - Windows bootstrap: SATA (safe)
        # - Windows final: virtio
        disk_if = QemuTest._disk_if_for_profile(prof)

        # Video defaults:
        # If GUI is enabled for Windows bootstrap, VGA tends to be the least-surprising.
        # We only add a video device explicitly when display != none, otherwise headless.
        video_args = QemuTest._video_args_for_profile(prof, display)

        cmd: list[str] = [
            str(qemu_bin),
            "-machine",
            f"{machine.machine}, accel={machine.accel}",
            "-m",
            str(int(memory_mib)),
            "-smp",
            str(int(vcpus)),
            "-cpu",
            machine.cpu,
            # Disk
            "-drive",
            f"file={disk}, if={disk_if}, format={img_fmt}, cache=none, discard=unmap",
            # Nice-to-have: show early boot logs on serial (and don't hang on graphics)
            "-serial",
            "mon:stdio",
        ]

        # Display handling
        cmd += QemuTest._display_args(display)

        # Optional video args (primarily for Windows GUI sanity)
        cmd += video_args

        # Networking (user-mode by default)
        if net.enabled:
            cmd += QemuTest._net_args(net)

        # Windows niceties: clock + Hyper-V enlightenments
        if prof.os == "windows":
            if prof.localtime_clock:
                cmd += ["-rtc", "base=localtime, clock=host"]
            else:
                cmd += ["-rtc", "base=utc, clock=host"]

            if prof.hyperv:
                # Keep conservative: avoid forcing vendor_id unless you need it.
                # This helps performance and reduces odd guest timing issues.
                cmd += ["-cpu", "host, hv_relaxed, hv_vapic, hv_spinlocks=0x1fff"]

        # UEFI handling (correct way: pflash CODE + writable VARS)
        if uefi:
            ovmf_code, ovmf_vars = QemuTest._resolve_ovmf(logger)
            tmp_ovmf_vars = QemuTest._copy_ovmf_vars(logger, ovmf_vars)
            cmd += [
                "-drive",
                f"if=pflash, format=raw, readonly=on, file={ovmf_code}",
                "-drive",
                f"if=pflash, format=raw, file={tmp_ovmf_vars}",
            ]

        # Optional: attach virtio driver ISO for Windows bootstrap
        if prof.os == "windows" and prof.driver_iso is not None:
            cmd += QemuTest._cdrom_iso_args(logger, prof.driver_iso)

        # Extra args last so caller can override
        cmd += list(extra_args)

        # Logging
        U.banner(logger, "🧪 QEMU smoke test")
        logger.info("🧾 QEMU: %s", qemu_bin)
        logger.info("💽 Disk: %s (format=%s, if=%s)", disk, img_fmt, disk_if)
        logger.info(
            "🧠 CPU: %s | vCPUs=%s | RAM=%s MiB | accel=%s", machine.cpu, vcpus, memory_mib, machine.accel
        )
        logger.info("🖥️ Display: %s | Net: %s", display.mode, "on" if net.enabled else "off")
        logger.info("🧬 Firmware: %s", "UEFI" if uefi else "BIOS")

        if prof.os == "windows":
            logger.info("🪟 Guest: windows | stage=%s", prof.win_stage)
            if prof.driver_iso:
                logger.info("📀 virtio driver ISO: %s", prof.driver_iso)
            logger.info("🕰️ Clock: %s", "localtime" if prof.localtime_clock else "utc")
            logger.info("🧩 Hyper-V: %s", "on" if prof.hyperv else "off")
        else:
            logger.info("🐧 Guest: linux")

        if display.mode == "vnc":
            port = 5900 + int(display.vnc_display)
            logger.info("🔗 VNC: %s:%s (display :%s)", display.vnc_listen, port, display.vnc_display)

        logger.debug("🧾 QEMU command:\n %s", " ".join(shlex.quote(x) for x in cmd))

        # Execute
        try:
            if timeout_s is None:
                logger.info("🚀 Launching QEMU (no timeout; exit manually)…")
                U.run_cmd(logger, cmd, check=False, capture=False)
                return

            logger.info("🚀 Launching QEMU (smoke run for ~%ss)…", int(timeout_s))
            p = subprocess.Popen(cmd)
            try:
                p.wait(timeout=float(timeout_s))
            except subprocess.TimeoutExpired:
                logger.info("⏱️ Smoke timeout reached; terminating QEMU…")
                p.terminate()
                try:
                    p.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    logger.warning("⚠️ QEMU didn't exit on SIGTERM; killing…")
                    p.kill()
                    p.wait(timeout=5.0)

            rc = p.returncode
            logger.info("🏁 QEMU exited with rc=%s (not enforced).", rc)
        finally:
            # Cleanup temp OVMF vars copy.
            if tmp_ovmf_vars:
                try:
                    U.safe_unlink(Path(tmp_ovmf_vars))
                    logger.debug("🧽 Removed temp OVMF VARS: %s", tmp_ovmf_vars)
                except Exception as e:
                    logger.debug("Could not remove temp OVMF VARS %s: %s", tmp_ovmf_vars, e)

    # Helpers

    @staticmethod
    def _detect_img_format(logger: logging.Logger, disk: Path) -> str:
        suf = disk.suffix.lower().lstrip(".")
        if suf in ("qcow2", "raw", "vmdk", "vdi"):
            logger.debug("🧾 Image format from suffix: %s", suf)
            return suf

        if U.which("qemu-img"):
            try:
                out = U.run_cmd(
                    logger, ["qemu-img", "info", "--output=json", str(disk)], check=True, capture=True
                ).stdout
                key = '"format"'
                i = out.find(key)
                if i != -1:
                    seg = out[i : i + 140]
                    c = seg.find(":")
                    q1 = seg.find('"', c + 1)
                    q2 = seg.find('"', q1 + 1)
                    if c != -1 and q1 != -1 and q2 != -1:
                        fmt = seg[q1 + 1 : q2].strip().lower()
                        if fmt:
                            logger.debug("🧾 Image format from qemu-img: %s", fmt)
                            return fmt
            except Exception as e:
                logger.debug("qemu-img info failed: %s", e)

        logger.warning("⚠️ Could not confidently detect image format; defaulting to qcow2.")
        return "qcow2"

    @staticmethod
    def _display_args(d: QemuDisplay) -> list[str]:
        if d.mode == "none":
            # headless, safe over SSH
            return ["-nographic"]
        if d.mode == "gtk":
            return ["-display", "gtk"]
        if d.mode == "sdl":
            return ["-display", "sdl"]
        if d.mode == "vnc":
            return ["-display", "none", "-vnc", f"{d.vnc_listen}:{int(d.vnc_display)}"]
        raise ValueError(f"Unknown display mode: {d.mode}")

    @staticmethod
    def _net_args(n: QemuNet) -> list[str]:
        # user-mode networking; virtio-net for speed/compat
        if n.ssh_forward_host_port is not None:
            hp = int(n.ssh_forward_host_port)
            return [
                "-netdev",
                f"user, id=n0, hostfwd=tcp::{hp}-:22",
                "-device",
                "virtio-net-pci, netdev=n0",
            ]
        return [
            "-netdev",
            "user, id=n0",
            "-device",
            "virtio-net-pci, netdev=n0",
        ]

    @staticmethod
    def _resolve_ovmf(logger: logging.Logger) -> tuple[str, str]:
        code = next((p for p in QemuTest._OVMF_CODE_CANDIDATES if os.path.exists(p)), None)
        vars_ = next((p for p in QemuTest._OVMF_VARS_CANDIDATES if os.path.exists(p)), None)

        logger.debug("🔎 OVMF probe: CODE=%s", code or "<missing>")
        logger.debug("🔎 OVMF probe: VARS=%s", vars_ or "<missing>")

        if not code or not vars_:
            U.die(logger, "💥 UEFI requested but OVMF not found (CODE/VARS missing).", 1)
        return code, vars_

    @staticmethod
    def _copy_ovmf_vars(logger: logging.Logger, ovmf_vars: str) -> str:
        # Put it under /tmp; caller doesn't need the path later.
        fd, dst = tempfile.mkstemp(prefix="h2kvm-ovmf-vars-", suffix=".fd")
        os.close(fd)
        logger.debug("🧬 Copying OVMF VARS: %s -> %s", ovmf_vars, dst)
        U.run_cmd(logger, ["cp", "-f", ovmf_vars, dst], check=True, capture=False)
        return dst

    # Windows additions

    @staticmethod
    def _disk_if_for_profile(prof: GuestProfile) -> str:
        if prof.os != "windows":
            return "virtio"
        # Bootstrap uses SATA (IDE works too, SATA is fine on q35)
        return "sata" if prof.win_stage == "bootstrap" else "virtio"

    @staticmethod
    def _video_args_for_profile(prof: GuestProfile, display: QemuDisplay) -> list[str]:
        # Only bother when GUI/VNC is enabled.
        if display.mode == "none":
            return []

        # Linux: keep QEMU defaults (less surprise).
        if prof.os != "windows":
            return []

        # Windows bootstrap: VGA is the “works basically everywhere” pick.
        # Windows final: virtio-vga is nice if drivers exist, but VGA still works.
        if prof.win_stage == "bootstrap":
            return ["-vga", "std"]

        # Prefer virtio-vga if available; otherwise std is fine.
        # (If host QEMU doesn't support virtio-vga, it will error; user can override via extra_args.)
        return ["-vga", "virtio"]

    @staticmethod
    def _cdrom_iso_args(logger: logging.Logger, iso: Path) -> list[str]:
        iso = Path(iso)
        if not iso.exists():
            U.die(logger, f"💥 Driver ISO not found: {iso}", 1)

        # Attach as SATA CDROM (broadly compatible).
        # NOTE: we don't force boot order; Windows can mount it after boot.
        return [
            "-drive",
            f"file={iso}, media=cdrom, if=sata, readonly=on",
        ]
