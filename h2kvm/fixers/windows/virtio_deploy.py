# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Windows VirtIO driver deployment automation.

Handles the complete VirtIO driver lifecycle for Windows guest migration:
  1. Disable VMware services in SYSTEM registry hive
  2. Neuter VMware startup entries in SOFTWARE registry hive
  3. Stage custom PnP drivers (vendor-supplied) into guest filesystem
  4. Add RunOnce entry for automatic pnputil driver installation from VirtIO CD
  5. Generate bootstrap and final domain XMLs

Uses ntfs-3g + hivex for offline registry editing (no libguestfs dependency).

Usage:
    from h2kvm.fixers.windows.virtio_deploy import WindowsVirtioDeployer

    deployer = WindowsVirtioDeployer(
        qcow2_path="win10.qcow2",
        virtio_iso="/path/to/virtio-win.iso",
        custom_pnp_drivers=["/path/to/vendor-drivers/"],
    )
    result = deployer.prepare_offline()

YAML config support:
    windows: true
    virtio_win_iso: /path/to/virtio-win.iso
    custom_pnp_drivers:
      - /path/to/vendor-gpu-drivers/
      - /path/to/vendor-storage-drivers.iso
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# VMware services to disable in the SYSTEM registry hive.
# pylint: disable=duplicate-code
# reason: shares its first 9 entries with virtio_injector.py's VMWARE_SERVICES_CORE, but
# this deployer's list has 2 extra entries (VMnetAdapter, VMnetuserif) -- kept as its own
# list rather than merged, since changing the shared list would alter injector/stage
# behavior.
VMWARE_SERVICES = [
    "VMTools",
    "vm3dservice",
    "VGAuthService",
    "vmvss",
    "vmci",
    "vsock",
    "vmhgfs",
    "vmrawdsk",
    "vmusbmouse",
    "VMnetAdapter",
    "VMnetuserif",
]
# pylint: enable=duplicate-code

# VirtIO pnputil command for RunOnce — finds CD with NetKVM dir, installs all drivers.
# Uses simple cmd.exe for loop — proven to work in testing.
# certutil cert import added to avoid confirmation dialogs.
# RunOnce points to a batch file we stage in Windows\Temp.
# Batch file avoids all escaping issues with registry RunOnce.
VIRTIO_RUNONCE_CMD = r"C:\Windows\Temp\h2kvm-virtio-install.bat"

# Batch file content staged into the guest filesystem
VIRTIO_INSTALL_BAT = r"""@echo off
setlocal

echo [h2kvm] Starting VirtIO driver installation...

rem Wait for CD-ROM drive to become available
timeout /t 10 /nobreak >nul

rem Detect architecture
if "%PROCESSOR_ARCHITECTURE%"=="AMD64" (
    set ARCH=amd64
) else (
    set ARCH=x86
)

rem Detect OS version folder (w10 covers Win10+Win11, 2k22 for Server 2022, etc.)
for /f "tokens=4-5 delims=. " %%i in ('ver') do set WINVER=%%i.%%j
set OSFOLDER=w10
if "%WINVER%"=="6.1" set OSFOLDER=w7
if "%WINVER%"=="6.2" set OSFOLDER=w8
if "%WINVER%"=="6.3" set OSFOLDER=w8.1

echo [h2kvm] OS=%OSFOLDER% ARCH=%ARCH%

rem Locate VirtIO ISO
for %%d in (D E F G H I J K L M N) do (
    if exist "%%d:\viostor" (
        set ISO=%%d:
        goto :found
    )
)

echo [h2kvm] VirtIO ISO not found
goto :done

:found
echo [h2kvm] Found VirtIO ISO at %ISO%

rem Install only matching OS/arch drivers — silent, no prompts
for %%c in (viostor NetKVM Balloon vioserial viorng qxldod viogpudo vioinput viofs pvpanic smbus qemufwcfg) do (
    if exist "%ISO%\%%c\%OSFOLDER%\%ARCH%" (
        echo [h2kvm] Installing %%c from %OSFOLDER%\%ARCH%
        pnputil /add-driver "%ISO%\%%c\%OSFOLDER%\%ARCH%\*.inf" /install >nul 2>&1
    )
)

rem Install QEMU guest agent
if exist "%ISO%\guest-agent\qemu-ga-x86_64.msi" (
    echo [h2kvm] Installing QEMU guest agent...
    msiexec /i "%ISO%\guest-agent\qemu-ga-x86_64.msi" /quiet /norestart
)

echo [h2kvm] VirtIO driver installation completed

:done
del "%~f0"
"""

# Custom PnP pnputil command — installs from C:\h2kvm-drivers staging dir
CUSTOM_PNP_RUNONCE_CMD = (
    'cmd.exe /c "if exist C:\\h2kvm-drivers'
    ' pnputil /add-driver C:\\h2kvm-drivers\\*.inf /subdirs /install"'
)


@dataclass
class VirtioDeployResult:
    """Result of the VirtIO deployment preparation."""

    success: bool = False
    vmware_services_disabled: list[str] = field(default_factory=list)
    vmware_run_keys_neutered: list[str] = field(default_factory=list)
    custom_drivers_staged: list[str] = field(default_factory=list)
    runonce_set: bool = False
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return the deployment result as a JSON-serializable dict."""
        return {
            "success": self.success,
            "vmware_services_disabled": self.vmware_services_disabled,
            "vmware_run_keys_neutered": self.vmware_run_keys_neutered,
            "custom_drivers_staged": self.custom_drivers_staged,
            "runonce_set": self.runonce_set,
            "errors": self.errors,
        }


class WindowsVirtioDeployer:  # pylint: disable=too-few-public-methods  # deliberately exposes only prepare_offline(); rest is private orchestration
    """Prepares a Windows QCOW2 image for VirtIO + custom driver installation.

    Performs offline registry edits via ntfs-3g + hivex:
      - Disables VMware services (prevents error dialogs on boot)
      - Removes VMware startup entries
      - Stages custom PnP drivers into C:\\h2kvm-drivers
      - Adds RunOnce entries for automatic driver installation

    Args:
        qcow2_path: Path to the Windows QCOW2 image
        virtio_iso: Path to the VirtIO driver ISO (attached as CD at boot)
        custom_pnp_drivers: List of paths to directories or ISOs with vendor .inf drivers
        nbd_device: NBD device to use (default: auto-detect free device)
        partition: Windows partition number (default: auto-detect NTFS)
    """

    def __init__(
        self,
        qcow2_path: str,
        virtio_iso: str | None = None,
        custom_pnp_drivers: list[str] | None = None,
        nbd_device: str | None = None,
        partition: int | None = None,
    ):
        self.qcow2_path = Path(qcow2_path)
        self.virtio_iso = Path(virtio_iso) if virtio_iso else None
        self.custom_pnp_drivers = [Path(p) for p in (custom_pnp_drivers or [])]
        self.nbd_device = nbd_device
        self.partition = partition
        self._mount_point: Path | None = None
        self._allocated_nbd: str | None = None

    def prepare_offline(self) -> VirtioDeployResult:
        """Apply all offline fixes in a single mount/unmount cycle.

        Returns:
            VirtioDeployResult with details of what was done.
        """
        result = VirtioDeployResult()

        try:
            nbd = self._connect_nbd()
            part_dev = self._find_windows_partition(nbd)

            self._ntfsfix(part_dev)
            mount_point = self._mount_ntfs(part_dev)

            config_dir = self._find_config_dir(mount_point)
            if not config_dir:
                result.errors.append("Windows System32/config directory not found")
                return result

            # Stage VirtIO install batch file
            self._stage_virtio_batch(mount_point)

            # Stage custom PnP drivers into guest filesystem
            result.custom_drivers_staged = self._stage_custom_drivers(mount_point)

            # Edit SYSTEM hive — disable VMware services
            result.vmware_services_disabled = self._fix_system_hive(config_dir)

            # Edit SOFTWARE hive — neuter VMware + add RunOnce
            neutered, runonce = self._fix_software_hive(
                config_dir,
                has_custom_drivers=len(result.custom_drivers_staged) > 0,
            )
            result.vmware_run_keys_neutered = neutered
            result.runonce_set = runonce

            result.success = True
            logger.info(
                "VirtIO deploy prepared: %d services disabled, %d Run keys neutered, "
                "%d custom drivers staged, RunOnce=%s",
                len(result.vmware_services_disabled),
                len(result.vmware_run_keys_neutered),
                len(result.custom_drivers_staged),
                result.runonce_set,
            )

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort fixer step, must not abort the whole migration
            result.errors.append(str(e))
            logger.exception("VirtIO deploy preparation failed: %s", e)

        finally:
            self._cleanup()

        return result

    def _stage_virtio_batch(self, mount_point: Path) -> None:
        """Write VirtIO install batch file into Windows\\Temp."""
        # pylint: disable=duplicate-code
        # reason: mirrors the inline batch-staging loop in
        # virtio_stage.py's _apply_offline_fixes() -- that call site needs a
        # "stop after first hit" break (not return) plus its own logger instance,
        # so it isn't reused here as a shared helper.
        for win_dir in ["Windows", "WINDOWS"]:
            temp_dir = mount_point / win_dir / "Temp"
            if temp_dir.exists():
                bat_path = temp_dir / "h2kvm-virtio-install.bat"
                bat_path.write_text(VIRTIO_INSTALL_BAT, encoding="utf-8")
                logger.info("Staged VirtIO install batch: %s", bat_path.name)
                return
        logger.warning("Windows\\Temp not found — batch file not staged")
        # pylint: enable=duplicate-code

    def _stage_custom_drivers(self, mount_point: Path) -> list[str]:
        """Copy custom PnP driver packages into guest filesystem.

        Drivers are staged at C:\\h2kvm-drivers so pnputil can find them
        via RunOnce on first boot.

        Supports directories (copied directly) and ISOs (mounted + copied).
        """
        if not self.custom_pnp_drivers:
            return []

        staged = []
        stage_dir = mount_point / "h2kvm-drivers"
        stage_dir.mkdir(exist_ok=True)

        for driver_path in self.custom_pnp_drivers:
            if not driver_path.exists():
                logger.warning("Custom driver path not found: %s", driver_path)
                continue

            name = driver_path.stem

            if driver_path.suffix.lower() == ".iso":
                # Mount ISO and copy contents
                iso_mount = Path(tempfile.mkdtemp(prefix="h2kvm-iso-"))
                try:
                    subprocess.run(
                        ["mount", "-o", "loop,ro", str(driver_path), str(iso_mount)],
                        check=True,
                        capture_output=True,
                    )
                    dst = stage_dir / name
                    shutil.copytree(iso_mount, dst, dirs_exist_ok=True)
                    staged.append(name)
                    logger.info(
                        "Staged custom ISO drivers: %s (%d files)", name, sum(1 for _ in dst.rglob("*.inf"))
                    )
                finally:
                    subprocess.run(["umount", str(iso_mount)], check=False, capture_output=True)
                    shutil.rmtree(iso_mount, ignore_errors=True)

            elif driver_path.is_dir():
                # Copy directory
                dst = stage_dir / name
                shutil.copytree(driver_path, dst, dirs_exist_ok=True)
                inf_count = sum(1 for _ in dst.rglob("*.inf"))
                staged.append(name)
                logger.info("Staged custom directory drivers: %s (%d .inf files)", name, inf_count)

            else:
                logger.warning("Unsupported custom driver format: %s", driver_path)

        return staged

    def _connect_nbd(self) -> str:
        """Connect QCOW2 to NBD device."""
        # pylint: disable=duplicate-code
        # reason: mirrors find_free_nbd()/find_ntfs_partition() in virtio_injector.py
        # (also used by virtio_stage.py) -- NOT imported here because virtio_injector.py
        # already has a deliberate lazy import of this module (see its
        # "avoid circular import between fixer submodules" comment); adding a module-level
        # import in the other direction would reintroduce that cycle.
        if self.nbd_device:
            nbd = self.nbd_device
        else:
            for i in range(16):
                dev = f"/dev/nbd{i}"
                size_file = f"/sys/block/nbd{i}/size"
                if Path(size_file).exists():
                    size = int(Path(size_file).read_text(encoding="utf-8").strip())
                    if size == 0:
                        nbd = dev
                        break
            else:
                raise RuntimeError(
                    "No free NBD device available. All /dev/nbd0 through /dev/nbd15 are in use. "
                    "Disconnect unused devices with 'qemu-nbd -d /dev/nbdN' or load the nbd module "
                    "with more devices: modprobe nbd max_part=16 nbds_max=32"
                )

        subprocess.run(
            ["qemu-nbd", "--connect", nbd, str(self.qcow2_path)],
            check=True,
            capture_output=True,
        )
        time.sleep(2)
        self._allocated_nbd = nbd
        logger.info("Connected %s to %s", self.qcow2_path.name, nbd)
        return nbd

    def _find_windows_partition(self, nbd: str) -> str:
        """Find the Windows NTFS partition."""
        if self.partition:
            return f"{nbd}p{self.partition}"

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
                    logger.info("Found NTFS partition: %s", dev)
                    return dev

        raise RuntimeError(
            f"No NTFS partition found on {nbd}. "
            f"The disk may not contain a Windows installation, or the partition table is unreadable. "
            f"Verify the disk image contains a valid Windows NTFS filesystem."
        )
        # pylint: enable=duplicate-code

    def _ntfsfix(self, device: str) -> None:
        """Run ntfsfix to clear dirty journal flags."""
        subprocess.run(["ntfsfix", device], check=False, capture_output=True)

    def _mount_ntfs(self, device: str) -> Path:
        """Mount NTFS partition read-write."""
        mount_point = Path(tempfile.mkdtemp(prefix="h2kvm-win-"))
        subprocess.run(
            ["ntfs-3g", "-o", "remove_hiberfile,force", device, str(mount_point)],
            check=True,
            capture_output=True,
        )
        self._mount_point = mount_point
        logger.info("Mounted %s at %s", device, mount_point)
        return mount_point

    def _find_config_dir(self, mount_point: Path) -> Path | None:
        """Find the Windows System32/config directory."""
        for win_dir in ["Windows", "WINDOWS", "winnt", "WINNT"]:
            for sys_dir in ["System32", "system32"]:
                config = mount_point / win_dir / sys_dir / "config"
                if config.exists():
                    return config
        return None

    def _fix_system_hive(self, config_dir: Path) -> list[str]:
        """Disable VMware services in the SYSTEM registry hive."""
        try:
            import hivex  # pylint: disable=import-outside-toplevel  # keep python-hivex an optional/lazy dependency
        except ImportError:
            logger.warning("python-hivex not installed — skipping SYSTEM hive edit")
            return []

        hive_path = str(config_dir / "SYSTEM")
        h = hivex.Hivex(hive_path, write=True)
        cs = h.node_get_child(h.root(), "ControlSet001")
        svc = h.node_get_child(cs, "Services")

        # pylint: disable=duplicate-code
        # reason: mirrors disable_services_in_hive()/the VMware Start=4 disable loop in
        # virtio_injector.py (also used by virtio_stage.py). NOT switched to call that
        # shared helper because virtio_injector.py already has a deliberate lazy import of
        # this module (see its "avoid circular import between fixer submodules" comment);
        # a module-level import in the other direction would reintroduce that cycle.
        disabled = []
        for name in VMWARE_SERVICES:
            try:
                node = h.node_get_child(svc, name)
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
            except Exception:  # pylint: disable=broad-exception-caught  # service key may legitimately not exist in this hive
                pass

        # Enable AHCI/SATA storage driver as boot-critical (Start=0).
        # Required for SATA bootstrap boot — VMware uses LSI Logic SCSI,
        # so storahci may be Start=3 (manual) which causes BSOD on KVM/SATA.
        # Structurally mirrors the loop above (and injector's/stage's Start=4 disable
        # loop) but sets Start=0 (enable boot-critical) -- different semantics, so it is
        # kept as its own small loop rather than merged with disable_services_in_hive().
        for drv in ("storahci", "msahci"):
            try:
                node = h.node_get_child(svc, drv)
                if node:
                    h.node_set_value(
                        node,
                        {
                            "key": "Start",
                            "t": 4,
                            "value": (0).to_bytes(4, "little"),
                        },
                    )
                    logger.info("SYSTEM: enabled %s as boot-critical (Start=0)", drv)
            except Exception:  # pylint: disable=broad-exception-caught  # driver key may legitimately not exist in this hive
                pass
        # pylint: enable=duplicate-code

        h.commit(hive_path)
        logger.info("SYSTEM: disabled %d VMware services", len(disabled))
        return disabled

    def _fix_software_hive(
        self,
        config_dir: Path,
        *,
        has_custom_drivers: bool = False,
    ) -> tuple[list[str], bool]:
        """Neuter VMware Run keys and add RunOnce entries in SOFTWARE hive."""
        try:
            import hivex  # pylint: disable=import-outside-toplevel  # keep python-hivex an optional/lazy dependency
        except ImportError:
            logger.warning("python-hivex not installed — skipping SOFTWARE hive edit")
            return [], False

        hive_path = str(config_dir / "SOFTWARE")
        h = hivex.Hivex(hive_path, write=True)
        cv = h.node_get_child(
            h.node_get_child(h.node_get_child(h.root(), "Microsoft"), "Windows"),
            "CurrentVersion",
        )

        # Neuter VMware Run keys
        neutered = []
        run = h.node_get_child(cv, "Run")
        if run:
            for v in h.node_values(run):
                key = h.value_key(v)
                if "vmware" in key.lower():
                    h.node_set_value(run, {"key": key, "t": 1, "value": b"\x00\x00"})
                    neutered.append(key)

        # Add RunOnce entries
        try:
            runonce = h.node_get_child(cv, "RunOnce")
        except Exception:  # pylint: disable=broad-exception-caught  # RunOnce subkey may legitimately not exist yet
            runonce = None
        if not runonce:
            runonce = h.node_add_child(cv, "RunOnce")

        # VirtIO pnputil from CD
        h.node_set_value(
            runonce,
            {
                "key": "h2kvm-virtio",
                "t": 1,
                "value": (VIRTIO_RUNONCE_CMD + "\0").encode("utf-16-le"),
            },
        )

        # Custom PnP drivers from staging directory
        if has_custom_drivers:
            h.node_set_value(
                runonce,
                {
                    "key": "h2kvm-custom-pnp",
                    "t": 1,
                    "value": (CUSTOM_PNP_RUNONCE_CMD + "\0").encode("utf-16-le"),
                },
            )
            logger.info("SOFTWARE: added RunOnce for custom PnP drivers")

        h.commit(hive_path)
        logger.info("SOFTWARE: neutered %s, RunOnce set", neutered)
        return neutered, True

    def _cleanup(self) -> None:
        """Unmount and disconnect NBD."""
        if self._mount_point and self._mount_point.exists():
            subprocess.run(["sync"], check=False)
            subprocess.run(["umount", str(self._mount_point)], check=False, capture_output=True)
            shutil.rmtree(self._mount_point, ignore_errors=True)
            self._mount_point = None

        if self._allocated_nbd:
            subprocess.run(
                ["qemu-nbd", "--disconnect", self._allocated_nbd],
                check=False,
                capture_output=True,
            )
            self._allocated_nbd = None
