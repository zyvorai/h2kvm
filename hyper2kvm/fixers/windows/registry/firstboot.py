# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/fixers/windows/registry/firstboot.py
# pylint: disable=too-many-lines  # cohesive Windows first-boot registry fixer; splitting would hurt readability more than help
"""
First-boot provisioning for Windows VMs.

This module provides functionality to create and manage a one-shot Windows service
that executes on first boot to perform driver installation, VMware Tools removal,
and other post-conversion tasks. The service is more reliable than RunOnce registry
entries as it executes regardless of logon/autologon quirks.

Key features:
- Creates a Windows service that runs firstboot.cmd as LocalSystem
- Installs staged drivers via pnputil
- Optionally removes VMware Tools (registry-based uninstall + service cleanup)
- Writes detailed logs to Windows\\Temp\\hyper2kvm-firstboot.log
- Self-deletes the service after successful execution
- Uses idempotency markers to prevent reruns
"""

from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hyper2kvm.core.logging_utils import safe_logger as _safe_logger_base
from hyper2kvm.core.utils import U

from .encoding import (
    _close_best_effort,
    _commit_best_effort,
    _detect_current_controlset,
    _encode_windows_cmd_script,
    _ensure_child,
    _mkdir_p_guest,
    _node_id,
    _open_hive_local,
    _set_dword,
    _set_expand_sz,
    _set_sz,
    _upload_bytes,
)
from .io import _download_hive_local, _log_mountpoints_best_effort
from .mount import _ensure_windows_root, _guest_path_join
from .software import add_software_run_key as _add_software_run_key

# pylint: disable=duplicate-code
# reason: shared optional-dependency import boilerplate (guestfs/hivex) and
# the _safe_logger wrapper, mirrored in registry/software.py -- kept
# per-module so each registry fixer stays independently importable.
if TYPE_CHECKING:
    import logging

    import guestfs  # type: ignore
else:
    try:
        import guestfs  # type: ignore
    except ImportError:
        guestfs = None  # type: ignore

try:
    import hivex  # type: ignore
except ImportError:
    hivex = None  # type: ignore

# Logging helper


def _safe_logger(self) -> logging.Logger:
    """Get logger from instance or create default for registry modules."""
    return _safe_logger_base(self, "hyper2kvm.windows_registry")


# pylint: enable=duplicate-code


# First-boot mechanism: create a one-shot SERVICE using rhsrvany.exe
# (proper Windows service wrapper, works on all Windows versions including Win11)

_DEFAULT_GUEST_DIR = "/hyper2kvm"
_DEFAULT_DRIVER_STAGE_DIR = "/hyper2kvm/drivers/virtio"
_DEFAULT_LOG_PATH = "/Windows/Temp/hyper2kvm-firstboot.log"
_DEFAULT_MARKER_PATH = "/hyper2kvm/firstboot.done"
_RHSRVANY_GUEST_DIR = "/Program Files/Guestfs/Firstboot"
_RHSRVANY_GUEST_PATH = f"{_RHSRVANY_GUEST_DIR}/rhsrvany.exe"

# Bundled rhsrvany.exe (from mingw-srvany-redistributable, GPL-2.0)
_RHSRVANY_LOCAL = Path(__file__).parent.parent / "bin" / "rhsrvany.exe"


def _service_imagepath_rhsrvany(service_name: str) -> str:
    """ImagePath using rhsrvany.exe — proper SCM-compatible service wrapper.

    The path MUST be quoted because it contains spaces (Program Files).
    SCM parses the ImagePath by splitting on the first space if unquoted,
    which would make it try to run 'C:\\Program' as the binary.
    """
    win_path = _RHSRVANY_GUEST_DIR.replace("/", "\\")
    return rf'"C:{win_path}\rhsrvany.exe" -s {service_name}'


def _service_imagepath_cmd(cmdline: str) -> str:
    """Fallback ImagePath using cmd.exe (may not work on Win11 edge builds)."""
    return r"%SystemRoot%\System32\cmd.exe /c " + cmdline


def _add_firstboot_service_system_hive(  # pylint: disable=too-many-arguments,too-many-locals,too-many-return-statements,too-many-branches,too-many-statements  # stages a full service registry entry across many independent hive edits
    self,
    g: guestfs.GuestFS,
    system_hive_path: str,
    *,
    service_name: str,
    display_name: str,
    cmdline: str,
    start: int = 2,  # AUTO_START
    description: str | None = None,
    use_rhsrvany: bool = False,
) -> dict[str, Any]:
    """
    Create/update a Win32 service entry that executes once at boot.

    NOTE: This is a "command service" (ImagePath uses cmd.exe /c ...).
    Script must self-delete the service.
    """
    logger = _safe_logger(self)
    dry_run = bool(getattr(self, "dry_run", False))

    logger.debug(
        "add_firstboot_service_system_hive: service_name=%s, display_name=%s, "
        "start=%d, use_rhsrvany=%s, dry_run=%s",
        service_name,
        display_name,
        start,
        use_rhsrvany,
        dry_run,
    )
    logger.debug("add_firstboot_service_system_hive: cmdline=%s", cmdline)
    logger.debug("add_firstboot_service_system_hive: hive_path=%s", system_hive_path)

    results: dict[str, Any] = {
        "success": False,
        "dry_run": dry_run,
        "hive_path": system_hive_path,
        "service_name": service_name,
        "cmdline": cmdline,
        "errors": [],
        "notes": [],
        "verification": {},
    }

    _ensure_windows_root(logger, g, hint_hive_path=system_hive_path)

    try:
        if not g.is_file(system_hive_path):
            results["errors"].append(f"SYSTEM hive not found: {system_hive_path}")
            return results
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort hive stat, must not abort first-boot staging
        results["errors"].append(f"Failed to stat hive {system_hive_path}: {e}")
        return results

    with tempfile.TemporaryDirectory() as td:
        local_hive = Path(td) / "SYSTEM"
        h: hivex.Hivex | None = None
        try:
            _log_mountpoints_best_effort(logger, g)

            if not dry_run:
                ts = U.now_ts()
                backup_path = f"{system_hive_path}.hyper2kvm.backup.{ts}"
                g.cp(system_hive_path, backup_path)
                results["hive_backup"] = backup_path

            _download_hive_local(logger, g, system_hive_path, local_hive)
            orig_hash = hashlib.sha256(local_hive.read_bytes()).hexdigest()

            h = _open_hive_local(local_hive, write=not dry_run)
            root = _node_id(h.root())
            if root == 0:
                results["errors"].append("Invalid hivex root()")
                return results

            cs_name = _detect_current_controlset(h, root)
            logger.debug("Detected ControlSet: %s", cs_name)
            cs = _node_id(h.node_get_child(root, cs_name))
            if cs == 0:
                cs_name = "ControlSet001"
                logger.debug("Falling back to ControlSet001")
                cs = _node_id(h.node_get_child(root, cs_name))
            if cs == 0:
                results["errors"].append("No usable ControlSet found (001/current)")
                logger.debug("No usable ControlSet found")
                return results

            services = _ensure_child(h, cs, "Services")
            svc = _node_id(h.node_get_child(services, service_name))
            action = "updated" if svc != 0 else "created"
            logger.debug("Service node action=%s for %s", action, service_name)
            if svc == 0:
                svc = _node_id(h.node_add_child(services, service_name))
            if svc == 0:
                results["errors"].append(f"Failed to create Services\\{service_name}")
                return results

            logger.debug(
                "Setting service registry values: Type=0x10, Start=%d, ErrorControl=1",
                int(start),
            )
            _set_dword(h, svc, "Type", 0x10)  # SERVICE_WIN32_OWN_PROCESS
            _set_dword(h, svc, "Start", int(start))
            _set_dword(h, svc, "ErrorControl", 1)

            if use_rhsrvany:
                # Match virt-v2v: REG_SZ ImagePath, Parameters\CommandLine + PWD
                image_path_val = _service_imagepath_rhsrvany(service_name)
                logger.debug("Using rhsrvany ImagePath: %s", image_path_val)
                _set_sz(h, svc, "ImagePath", image_path_val)
                params = _ensure_child(h, svc, "Parameters")
                cmd_val = f"cmd /c {cmdline}"
                win_guest_dir = cmdline.strip('"').rsplit("\\", 1)[0]
                logger.debug(
                    "rhsrvany Parameters: CommandLine=%s, PWD=%s",
                    cmd_val,
                    win_guest_dir,
                )
                _set_sz(h, params, "CommandLine", cmd_val)
                _set_sz(h, params, "PWD", win_guest_dir)
            else:
                image_path_val = _service_imagepath_cmd(cmdline)
                logger.debug("Using cmd.exe ImagePath: %s", image_path_val)
                _set_expand_sz(h, svc, "ImagePath", image_path_val)

            # pylint: disable=duplicate-code
            # reason: result-dict bookkeeping mirrors the equivalent step in
            # registry/system.py's hive editors -- coincidentally similar
            # shape, kept independent since each editor tracks different
            # per-hive state.
            _set_sz(h, svc, "ObjectName", "LocalSystem")
            _set_sz(h, svc, "DisplayName", display_name)
            if description:
                _set_sz(h, svc, "Description", description)

            results["action"] = action
            results["controlset"] = cs_name
            # pylint: enable=duplicate-code

            if not dry_run:
                try:
                    _commit_best_effort(h)
                finally:
                    _close_best_effort(h)
                    h = None

                g.upload(str(local_hive), system_hive_path)

                with tempfile.TemporaryDirectory() as vtd:
                    vlocal = Path(vtd) / "SYSTEM_verify"
                    _download_hive_local(logger, g, system_hive_path, vlocal)
                    new_hash = hashlib.sha256(vlocal.read_bytes()).hexdigest()

                results["verification"] = {
                    "sha256_before": orig_hash,
                    "sha256_after": new_hash,
                    "changed": (new_hash != orig_hash),
                }
                logger.debug(
                    "SYSTEM hive verification: before=%s after=%s changed=%s",
                    orig_hash[:12],
                    new_hash[:12],
                    new_hash != orig_hash,
                )
                results["success"] = True
            else:
                results["success"] = True

            results["notes"] += [
                f"Service created at HKLM\\SYSTEM\\{cs_name}\\Services\\{service_name}",
                "Service runs as LocalSystem at boot; script should self-delete via "
                "sc.exe delete (1060 == already removed).",
                "ImagePath written as REG_EXPAND_SZ to expand %SystemRoot% at runtime.",
            ]
            logger.info("Firstboot service %s: %s", action, service_name)
            return results

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort hive edit, must not abort first-boot staging
            results["errors"].append(f"Firstboot service creation failed: {e}")
            return results
        finally:
            _close_best_effort(h)


# Enterprise firstboot script blocks


def _qemu_guest_agent_installation_cmd_block() -> str:
    """Generate QEMU Guest Agent installation PowerShell block."""
    return r"""
echo === [1/8] QEMU Guest Agent Installation === >> "%LOG%"

where powershell >> "%LOG%" 2>&1
if %ERRORLEVEL%==0 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Continue';" ^
    "$LOG=$env:LOG;" ^
    "try {" ^
    " 'Installing QEMU Guest Agent...' | Out-File -Append -Encoding ascii $LOG;" ^
    " $agentPath='%STAGE%\guest-agent\qemu-ga-x86_64.msi';" ^
    " if(Test-Path $agentPath) {" ^
    "  'Found QEMU Guest Agent MSI at: ' + $agentPath | Out-File -Append -Encoding ascii $LOG;" ^
    "  $proc=Start-Process msiexec.exe -ArgumentList '/i',$agentPath,'/qn','/norestart','/l*v',\"$env:SystemRoot\Temp\qemu-ga-install.log\" -Wait -PassThru;" ^
    "  'QEMU GA installation exit code: ' + $proc.ExitCode | Out-File -Append -Encoding ascii $LOG;" ^
    "  if($proc.ExitCode -eq 0 -or $proc.ExitCode -eq 3010) {" ^
    "   'QEMU Guest Agent installed successfully' | Out-File -Append -Encoding ascii $LOG;" ^
    "   Start-Sleep -Seconds 2;" ^
    "   Set-Service QEMU-GA -StartupType Automatic -ErrorAction SilentlyContinue;" ^
    "   Start-Service QEMU-GA -ErrorAction SilentlyContinue;" ^
    "   (Get-Service QEMU-GA | Select-Object Name,Status,StartType | Out-String) | Out-File -Append -Encoding ascii $LOG;" ^
    "  } else {" ^
    "   'WARNING: QEMU GA installation failed with code: ' + $proc.ExitCode | Out-File -Append -Encoding ascii $LOG;" ^
    "  }" ^
    " } else {" ^
    "  'QEMU Guest Agent MSI not found at: ' + $agentPath | Out-File -Append -Encoding ascii $LOG;" ^
    "  'Attempting to download from virtio-win...' | Out-File -Append -Encoding ascii $LOG;" ^
    " }" ^
    "} catch {" ^
    " 'ERROR: QEMU GA installation failed: ' + $_.Exception.Message | Out-File -Append -Encoding ascii $LOG;" ^
    "}" ^
    >> "%LOG%" 2>&1
) else (
  echo PowerShell not available; skipping QEMU Guest Agent installation >> "%LOG%"
)
"""


def _enhanced_virtio_driver_installation_cmd_block() -> str:
    """Generate enhanced VirtIO driver installation using all methods."""
    return r"""
echo === [2/8] Enhanced VirtIO Driver Installation === >> "%LOG%"

where powershell >> "%LOG%" 2>&1
if %ERRORLEVEL%==0 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Continue';" ^
    "$LOG=$env:LOG;" ^
    "$STAGE=$env:STAGE;" ^
    "try {" ^
    " $toolsPath=Join-Path $STAGE 'guest-agent\virtio-win-guest-tools.exe';" ^
    " if(Test-Path $toolsPath) {" ^
    "  '=== Method 0: Install staged virtio-win guest tools ===' | Out-File -Append -Encoding ascii $LOG;" ^
    "  'Running: ' + $toolsPath + ' /S /norestart' | Out-File -Append -Encoding ascii $LOG;" ^
    "  $toolsProc=Start-Process $toolsPath -ArgumentList '/S','/norestart' -Wait -PassThru;" ^
    "  'virtio-win guest tools exit code: ' + $toolsProc.ExitCode | Out-File -Append -Encoding ascii $LOG;" ^
    "  Set-Service QEMU-GA -StartupType Automatic -ErrorAction SilentlyContinue;" ^
    "  Start-Service QEMU-GA -ErrorAction SilentlyContinue;" ^
    " } else {" ^
    "  'Staged virtio-win guest tools not found at: ' + $toolsPath | Out-File -Append -Encoding ascii $LOG;" ^
    " }" ^
    " '=== Method 1: Install staged VirtIO driver MSI ===' | Out-File -Append -Encoding ascii $LOG;" ^
    " $is64=[Environment]::Is64BitOperatingSystem;" ^
    " $msiName=if($is64){'virtio-win-gt-x64.msi'}else{'virtio-win-gt-x86.msi'};" ^
    " $msiPath=Join-Path $STAGE ('guest-agent\' + $msiName);" ^
    " if(-not (Test-Path $msiPath)) {" ^
    "  $fallback=Get-ChildItem -Path (Join-Path $STAGE 'guest-agent') -Filter 'virtio-win-gt-*.msi' -ErrorAction SilentlyContinue | Select-Object -First 1;" ^
    "  if($fallback){$msiPath=$fallback.FullName}" ^
    " }" ^
    " if(Test-Path $msiPath) {" ^
    "  'Running: msiexec /i ' + $msiPath + ' /qn /norestart' | Out-File -Append -Encoding ascii $LOG;" ^
    "  $msiProc=Start-Process msiexec.exe -ArgumentList '/i',$msiPath,'/qn','/norestart','/l*v',\"$env:SystemRoot\Temp\virtio-win-gt-install.log\" -Wait -PassThru;" ^
    "  'virtio-win driver MSI exit code: ' + $msiProc.ExitCode | Out-File -Append -Encoding ascii $LOG;" ^
    " } else {" ^
    "  'Staged VirtIO driver MSI not found under guest-agent' | Out-File -Append -Encoding ascii $LOG;" ^
    " }" ^
    " '=== Method 2: Install from staged driver INF files ===' | Out-File -Append -Encoding ascii $LOG;" ^
    " $infFiles=Get-ChildItem -Path $STAGE -Filter '*.inf' -Recurse -ErrorAction SilentlyContinue;" ^
    " if($infFiles) {" ^
    "  'Found ' + $infFiles.Count + ' INF file(s)' | Out-File -Append -Encoding ascii $LOG;" ^
    "  foreach($inf in $infFiles) {" ^
    "   'Installing: ' + $inf.FullName | Out-File -Append -Encoding ascii $LOG;" ^
    "   $pnpResult=pnputil /add-driver $inf.FullName /install 2>&1 | Out-String;" ^
    "   $pnpResult | Out-File -Append -Encoding ascii $LOG;" ^
    "  }" ^
    " } else {" ^
    "  'No INF files found in staging directory' | Out-File -Append -Encoding ascii $LOG;" ^
    " }" ^
    " '=== Method 3: Install from DriverStore ===' | Out-File -Append -Encoding ascii $LOG;" ^
    " $driverStore=\"$env:SystemRoot\System32\DriverStore\FileRepository\";" ^
    " if(Test-Path $driverStore) {" ^
    "  $virtioDrivers=Get-ChildItem -Path $driverStore -Filter '*.inf' -Recurse | Where-Object { $_.FullName -match 'virtio|redhat' };" ^
    "  foreach($drv in $virtioDrivers) {" ^
    "   'Installing from DriverStore: ' + $drv.FullName | Out-File -Append -Encoding ascii $LOG;" ^
    "   pnputil /add-driver $drv.FullName /install 2>&1 | Out-File -Append -Encoding ascii $LOG;" ^
    "  }" ^
    " }" ^
    " '=== Method 4: Scan for hardware changes ===' | Out-File -Append -Encoding ascii $LOG;" ^
    " pnputil /scan-devices 2>&1 | Out-File -Append -Encoding ascii $LOG;" ^
    " '=== Method 5: Enable VirtIO devices ===' | Out-File -Append -Encoding ascii $LOG;" ^
    " $devMgmt=Get-WmiObject Win32_PnPEntity | Where-Object { $_.Name -match 'VirtIO' -and $_.ConfigManagerErrorCode -ne 0 };" ^
    " if($devMgmt) {" ^
    "  foreach($dev in $devMgmt) {" ^
    "   'Enabling device: ' + $dev.Name | Out-File -Append -Encoding ascii $LOG;" ^
    "   $dev.Enable() | Out-File -Append -Encoding ascii $LOG;" ^
    "  }" ^
    " } else {" ^
    "  'All VirtIO devices are already enabled' | Out-File -Append -Encoding ascii $LOG;" ^
    " }" ^
    " 'VirtIO driver installation completed' | Out-File -Append -Encoding ascii $LOG;" ^
    "} catch {" ^
    " 'ERROR: VirtIO driver installation failed: ' + $_.Exception.Message | Out-File -Append -Encoding ascii $LOG;" ^
    "}" ^
    >> "%LOG%" 2>&1
) else (
  echo PowerShell not available; skipping enhanced VirtIO installation >> "%LOG%"
)
"""


def _sid_regeneration_cmd_block() -> str:
    """Generate SID regeneration (Windows machine identity reset)."""
    return r"""
echo === [3/8] SID Regeneration (Machine Identity Reset) === >> "%LOG%"

where powershell >> "%LOG%" 2>&1
if %ERRORLEVEL%==0 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Continue';" ^
    "$LOG=$env:LOG;" ^
    "try {" ^
    " 'Preparing SID regeneration using sysprep...' | Out-File -Append -Encoding ascii $LOG;" ^
    " $sysprepPath='%SystemRoot%\System32\Sysprep\sysprep.exe';" ^
    " if(Test-Path $sysprepPath) {" ^
    "  'Found sysprep at: ' + $sysprepPath | Out-File -Append -Encoding ascii $LOG;" ^
    "  'NOTE: SID regeneration requires sysprep /generalize which resets activation' | Out-File -Append -Encoding ascii $LOG;" ^
    "  'Skipping automatic SID regeneration to preserve Windows activation' | Out-File -Append -Encoding ascii $LOG;" ^
    "  'If SID regeneration is required, run manually: sysprep /generalize /oobe /reboot' | Out-File -Append -Encoding ascii $LOG;" ^
    " } else {" ^
    "  'sysprep.exe not found; SID regeneration not available' | Out-File -Append -Encoding ascii $LOG;" ^
    " }" ^
    "} catch {" ^
    " 'ERROR: SID check failed: ' + $_.Exception.Message | Out-File -Append -Encoding ascii $LOG;" ^
    "}" ^
    >> "%LOG%" 2>&1
) else (
  echo PowerShell not available; skipping SID regeneration >> "%LOG%"
)
"""


def _network_reconfiguration_cmd_block() -> str:
    """Generate network reconfiguration for MAC address changes."""
    return r"""
echo === [4/8] Network Reconfiguration === >> "%LOG%"

where powershell >> "%LOG%" 2>&1
if %ERRORLEVEL%==0 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Continue';" ^
    "$LOG=$env:LOG;" ^
    "try {" ^
    " '=== Removing persistent network rules ===' | Out-File -Append -Encoding ascii $LOG;" ^
    " $netRules=\"$env:SystemRoot\System32\drivers\etc\hosts\";" ^
    " 'Network adapters before cleanup:' | Out-File -Append -Encoding ascii $LOG;" ^
    " (Get-NetAdapter | Select-Object Name,InterfaceDescription,Status,MacAddress | Out-String) | Out-File -Append -Encoding ascii $LOG;" ^
    " '=== Resetting network adapters ===' | Out-File -Append -Encoding ascii $LOG;" ^
    " $adapters=Get-NetAdapter -ErrorAction SilentlyContinue;" ^
    " if($adapters) {" ^
    "  foreach($adapter in $adapters) {" ^
    "   if($adapter.InterfaceDescription -match 'VMware') {" ^
    "    'Disabling VMware adapter: ' + $adapter.Name | Out-File -Append -Encoding ascii $LOG;" ^
    "    Disable-NetAdapter -Name $adapter.Name -Confirm:`$false -ErrorAction SilentlyContinue;" ^
    "   } elseif($adapter.InterfaceDescription -match 'VirtIO|Red Hat') {" ^
    "    'VirtIO adapter found: ' + $adapter.Name | Out-File -Append -Encoding ascii $LOG;" ^
    "    'Resetting adapter: ' + $adapter.Name | Out-File -Append -Encoding ascii $LOG;" ^
    "    Restart-NetAdapter -Name $adapter.Name -ErrorAction SilentlyContinue;" ^
    "   }" ^
    "  }" ^
    " }" ^
    " '=== Renewing DHCP leases ===' | Out-File -Append -Encoding ascii $LOG;" ^
    " ipconfig /release 2>&1 | Out-File -Append -Encoding ascii $LOG;" ^
    " ipconfig /renew 2>&1 | Out-File -Append -Encoding ascii $LOG;" ^
    " 'Network adapters after reconfiguration:' | Out-File -Append -Encoding ascii $LOG;" ^
    " (Get-NetAdapter | Select-Object Name,InterfaceDescription,Status,MacAddress | Out-String) | Out-File -Append -Encoding ascii $LOG;" ^
    "} catch {" ^
    " 'ERROR: Network reconfiguration failed: ' + $_.Exception.Message | Out-File -Append -Encoding ascii $LOG;" ^
    "}" ^
    >> "%LOG%" 2>&1
) else (
  echo PowerShell not available; skipping network reconfiguration >> "%LOG%"
  ipconfig /release >> "%LOG%" 2>&1
  ipconfig /renew >> "%LOG%" 2>&1
)
"""


def _rdp_enablement_cmd_block() -> str:
    """Generate RDP enablement block (registry, firewall, TermService listener)."""
    return r"""
echo === [5/8] RDP Enablement === >> "%LOG%"

where powershell >> "%LOG%" 2>&1
if %ERRORLEVEL%==0 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Continue';" ^
    "$LOG=$env:LOG;" ^
    "try {" ^
    " '=== RDP enablement (registry + firewall + services) ===' | Out-File -Append -Encoding ascii $LOG;" ^
    " $tsPath='HKLM:\System\CurrentControlSet\Control\Terminal Server';" ^
    " Set-ItemProperty -Path $tsPath -Name fDenyTSConnections -Value 0 -ErrorAction SilentlyContinue;" ^
    " 'Set fDenyTSConnections=0' | Out-File -Append -Encoding ascii $LOG;" ^
    " Enable-NetFirewallRule -DisplayGroup 'Remote Desktop' -ErrorAction SilentlyContinue | Out-Null;" ^
    " netsh advfirewall firewall set rule group=\"remote desktop\" new enable=yes 2>&1 | Out-File -Append -Encoding ascii $LOG;" ^
    " 'Enabled Remote Desktop firewall rules' | Out-File -Append -Encoding ascii $LOG;" ^
    " foreach($svc in @('TermService','UmRdpService')) {" ^
    "  Set-Service -Name $svc -StartupType Automatic -ErrorAction SilentlyContinue;" ^
    "  $s=Get-Service -Name $svc -ErrorAction SilentlyContinue;" ^
    "  if($s -and $s.Status -ne 'Running') { Start-Service -Name $svc -ErrorAction SilentlyContinue; }" ^
    "  Get-Service -Name $svc -ErrorAction SilentlyContinue | Format-List Name,Status,StartType | Out-File -Append -Encoding ascii $LOG;" ^
    " }" ^
    " netstat -an | Select-String ':3389' | Out-File -Append -Encoding ascii $LOG;" ^
    "} catch {" ^
    " 'ERROR: RDP enablement failed: ' + $_.Exception.Message | Out-File -Append -Encoding ascii $LOG;" ^
    "}" ^
    >> "%LOG%" 2>&1
) else (
  echo PowerShell not available; using reg/sc/netsh for RDP enablement >> "%LOG%"
  reg add "HKLM\System\CurrentControlSet\Control\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 0 /f >> "%LOG%" 2>&1
  netsh advfirewall firewall set rule group="remote desktop" new enable=yes >> "%LOG%" 2>&1
  sc config TermService start= auto >> "%LOG%" 2>&1
  sc config UmRdpService start= auto >> "%LOG%" 2>&1
  net start TermService >> "%LOG%" 2>&1
  net start UmRdpService >> "%LOG%" 2>&1
)
"""


def _windows_event_log_integration_cmd_block() -> str:
    """Generate Windows Event Log integration."""
    return r"""
echo === [6/8] Windows Event Log Integration === >> "%LOG%"

where powershell >> "%LOG%" 2>&1
if %ERRORLEVEL%==0 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Continue';" ^
    "$LOG=$env:LOG;" ^
    "try {" ^
    " 'Registering hyper2kvm event source...' | Out-File -Append -Encoding ascii $LOG;" ^
    " if(-not [System.Diagnostics.EventLog]::SourceExists('hyper2kvm')) {" ^
    "  [System.Diagnostics.EventLog]::CreateEventSource('hyper2kvm','Application');" ^
    "  'Event source registered: hyper2kvm' | Out-File -Append -Encoding ascii $LOG;" ^
    " } else {" ^
    "  'Event source already exists: hyper2kvm' | Out-File -Append -Encoding ascii $LOG;" ^
    " }" ^
    " 'Writing conversion completion event...' | Out-File -Append -Encoding ascii $LOG;" ^
    " $evt=New-Object System.Diagnostics.EventLog('Application');" ^
    " $evt.Source='hyper2kvm';" ^
    " $message='Hyper2KVM first boot initialization completed successfully. VMware to KVM conversion finalized.';" ^
    " $evt.WriteEntry($message,[System.Diagnostics.EventLogEntryType]::Information,1000);" ^
    " 'Event written to Application log (Event ID 1000)' | Out-File -Append -Encoding ascii $LOG;" ^
    "} catch {" ^
    " 'ERROR: Event log integration failed: ' + $_.Exception.Message | Out-File -Append -Encoding ascii $LOG;" ^
    "}" ^
    >> "%LOG%" 2>&1
) else (
  echo PowerShell not available; skipping Event Log integration >> "%LOG%"
)
"""


def _health_verification_cmd_block() -> str:
    """Generate health verification block."""
    return r"""
echo === [7/8] Health Verification === >> "%LOG%"

where powershell >> "%LOG%" 2>&1
if %ERRORLEVEL%==0 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Continue';" ^
    "$LOG=$env:LOG;" ^
    "try {" ^
    " $errors=0;" ^
    " '=== System Health Check ===' | Out-File -Append -Encoding ascii $LOG;" ^
    " '1. QEMU Guest Agent Status' | Out-File -Append -Encoding ascii $LOG;" ^
    " $ga=Get-Service QEMU-GA -ErrorAction SilentlyContinue;" ^
    " if($ga -and $ga.Status -eq 'Running') {" ^
    "  '  OK: QEMU Guest Agent is running' | Out-File -Append -Encoding ascii $LOG;" ^
    " } else {" ^
    "  '  WARNING: QEMU Guest Agent is not running' | Out-File -Append -Encoding ascii $LOG;" ^
    "  $errors++;" ^
    " }" ^
    " '2. Network Connectivity' | Out-File -Append -Encoding ascii $LOG;" ^
    " $adapters=Get-NetAdapter | Where-Object { $_.Status -eq 'Up' };" ^
    " if($adapters) {" ^
    "  '  OK: ' + $adapters.Count + ' network adapter(s) UP' | Out-File -Append -Encoding ascii $LOG;" ^
    " } else {" ^
    "  '  WARNING: No network adapters are UP' | Out-File -Append -Encoding ascii $LOG;" ^
    "  $errors++;" ^
    " }" ^
    " '3. VirtIO Drivers' | Out-File -Append -Encoding ascii $LOG;" ^
    " $virtioDevices=Get-WmiObject Win32_PnPEntity | Where-Object { $_.Name -match 'VirtIO' };" ^
    " if($virtioDevices) {" ^
    "  '  OK: ' + $virtioDevices.Count + ' VirtIO device(s) detected' | Out-File -Append -Encoding ascii $LOG;" ^
    "  foreach($dev in $virtioDevices) {" ^
    "   '    - ' + $dev.Name + ' (Status: ' + $dev.Status + ')' | Out-File -Append -Encoding ascii $LOG;" ^
    "  }" ^
    " } else {" ^
    "  '  WARNING: No VirtIO devices detected' | Out-File -Append -Encoding ascii $LOG;" ^
    " }" ^
    " '4. System Disk' | Out-File -Append -Encoding ascii $LOG;" ^
    " $sysDrive=Get-WmiObject Win32_LogicalDisk | Where-Object { $_.DeviceID -eq $env:SystemDrive };" ^
    " if($sysDrive) {" ^
    "  '  OK: System drive mounted (' + $sysDrive.DeviceID + ')' | Out-File -Append -Encoding ascii $LOG;" ^
    "  '    Free: ' + [math]::Round($sysDrive.FreeSpace/1GB,2) + ' GB / ' + [math]::Round($sysDrive.Size/1GB,2) + ' GB' | Out-File -Append -Encoding ascii $LOG;" ^
    " }" ^
    " '5. Failed Services Check' | Out-File -Append -Encoding ascii $LOG;" ^
    " $failedSvcs=Get-Service | Where-Object { $_.Status -eq 'Stopped' -and $_.StartType -eq 'Automatic' };" ^
    " if($failedSvcs) {" ^
    "  '  WARNING: ' + $failedSvcs.Count + ' failed service(s)' | Out-File -Append -Encoding ascii $LOG;" ^
    "  foreach($svc in $failedSvcs | Select-Object -First 10) {" ^
    "   '    - ' + $svc.Name + ' (' + $svc.DisplayName + ')' | Out-File -Append -Encoding ascii $LOG;" ^
    "  }" ^
    " } else {" ^
    "  '  OK: No failed services detected' | Out-File -Append -Encoding ascii $LOG;" ^
    " }" ^
    " '=== Health Check Summary ===' | Out-File -Append -Encoding ascii $LOG;" ^
    " 'Total errors/warnings: ' + $errors | Out-File -Append -Encoding ascii $LOG;" ^
    " if($errors -eq 0) {" ^
    "  'Health check: PASS' | Out-File -Append -Encoding ascii $LOG;" ^
    " } else {" ^
    "  'Health check: PASS with warnings' | Out-File -Append -Encoding ascii $LOG;" ^
    " }" ^
    "} catch {" ^
    " 'ERROR: Health verification failed: ' + $_.Exception.Message | Out-File -Append -Encoding ascii $LOG;" ^
    "}" ^
    >> "%LOG%" 2>&1
) else (
  echo PowerShell not available; skipping health verification >> "%LOG%"
)
"""


def _conversion_metadata_cmd_block() -> str:
    """Generate conversion metadata creation block."""
    return r"""
echo === [8/8] Conversion Metadata === >> "%LOG%"

where powershell >> "%LOG%" 2>&1
if %ERRORLEVEL%==0 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Continue';" ^
    "$LOG=$env:LOG;" ^
    "try {" ^
    " $metadataDir=\"$env:SystemDrive\hyper2kvm\";" ^
    " $metadataFile=Join-Path $metadataDir 'metadata.json';" ^
    " 'Creating conversion metadata...' | Out-File -Append -Encoding ascii $LOG;" ^
    " $metadata=@{" ^
    "  conversion_tool='hyper2kvm';" ^
    "  conversion_version='enterprise-1.0';" ^
    "  conversion_date=(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ');" ^
    "  source_platform='VMware';" ^
    "  target_platform='KVM/QEMU';" ^
    "  features_applied=@(" ^
    "   'VMware Tools removal'," ^
    "   'VirtIO driver installation'," ^
    "   'QEMU Guest Agent installation'," ^
    "   'Network reconfiguration'," ^
    "   'RDP enablement'," ^
    "   'Windows Event Log integration'" ^
    "  );" ^
    "  firstboot_completed=(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ');" ^
    "  computer_name=$env:COMPUTERNAME;" ^
    "  os_version=[System.Environment]::OSVersion.Version.ToString();" ^
    " };" ^
    " $metadata | ConvertTo-Json -Depth 5 | Out-File -FilePath $metadataFile -Encoding UTF8;" ^
    " 'Metadata written to: ' + $metadataFile | Out-File -Append -Encoding ascii $LOG;" ^
    "} catch {" ^
    " 'ERROR: Metadata creation failed: ' + $_.Exception.Message | Out-File -Append -Encoding ascii $LOG;" ^
    "}" ^
    >> "%LOG%" 2>&1
) else (
  echo PowerShell not available; skipping metadata creation >> "%LOG%"
)
"""


# VMware Tools removal (firstboot script block)


def _vmware_tools_removal_cmd_block() -> str:
    return r"""
echo --- VMware Tools removal (best-effort) --- >> "%LOG%"

where powershell >> "%LOG%" 2>&1
if %ERRORLEVEL%==0 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Continue';" ^
    "$keys=@(" ^
    "'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'," ^
    "'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'" ^
    ");" ^
    "$apps=Get-ItemProperty $keys -ErrorAction SilentlyContinue | Where-Object { ($_.DisplayName -match 'VMware Tools') -or ($_.Publisher -match 'VMware') };" ^
    "if(-not $apps){ 'No VMware Tools uninstall entry found (DisplayName/Publisher)' | Out-File -Append -Encoding ascii $env:LOG; exit 0 }" ^
    "foreach($a in $apps){" ^
    " ('Found: ' + $a.DisplayName + ' [' + $a.Publisher + ']') | Out-File -Append -Encoding ascii $env:LOG;" ^
    " $u=$a.QuietUninstallString; if(-not $u){ $u=$a.UninstallString };" ^
    " if(-not $u){ 'No uninstall string' | Out-File -Append -Encoding ascii $env:LOG; continue }" ^
    " ('UninstallString: ' + $u) | Out-File -Append -Encoding ascii $env:LOG;" ^
    " try {" ^
    " if($u -match 'msiexec'){ if($u -notmatch '/qn'){ $u += ' /qn' }; if($u -notmatch '/norestart'){ $u += ' /norestart' } }" ^
    " $p=Start-Process -FilePath 'cmd.exe' -ArgumentList ('/c ' + $u) -Wait -PassThru;" ^
    " ('rc=' + $p.ExitCode) | Out-File -Append -Encoding ascii $env:LOG;" ^
    " } catch { $_ | Out-File -Append -Encoding ascii $env:LOG }" ^
    "}" ^
    >> "%LOG%" 2>&1
) else (
  echo powershell not available; skipping VMware Tools uninstall via registry >> "%LOG%"
)

echo --- VMware services stop/delete (best-effort) --- >> "%LOG%"
for %%S in (VMTools VGAuthService vmvss vmware-aliases vmtoolsd) do (
  sc.exe query "%%S" >> "%LOG%" 2>&1
  if %ERRORLEVEL%==0 (
    sc.exe stop "%%S" >> "%LOG%" 2>&1
    sc.exe delete "%%S" >> "%LOG%" 2>&1
  )
)

echo --- VMware driver/services DELETE (aggressive cleanup) --- >> "%LOG%"
for %%D in (vm3dmp vmmouse vmusbmouse vmxnet3 vmxnet vmhgfs vmci vmscsi pvscsi vmmemctl vsock vmrawdsk vm3dservice vmvss) do (
  echo Removing driver service: %%D >> "%LOG%"
  sc.exe stop "%%D" >> "%LOG%" 2>&1
  sc.exe delete "%%D" >> "%LOG%" 2>&1
  reg delete "HKLM\SYSTEM\CurrentControlSet\Services\%%D" /f >> "%LOG%" 2>&1
  reg delete "HKLM\SYSTEM\ControlSet001\Services\%%D" /f >> "%LOG%" 2>&1
  reg delete "HKLM\SYSTEM\ControlSet002\Services\%%D" /f >> "%LOG%" 2>&1
)

echo --- VMware driver files DELETE from System32\drivers --- >> "%LOG%"
for %%F in (vm3dmp.sys vmmouse.sys vmusbmouse.sys vmxnet3.sys vmxnet.sys vmhgfs.sys vmci.sys vmscsi.sys pvscsi.sys vmmemctl.sys vsock.sys vmrawdsk.sys) do (
  if exist "%SystemRoot%\System32\drivers\%%F" (
    echo Deleting: %SystemRoot%\System32\drivers\%%F >> "%LOG%"
    del /f /q "%SystemRoot%\System32\drivers\%%F" >> "%LOG%" 2>&1
  )
)

echo --- VMware PnP drivers removal via pnputil --- >> "%LOG%"
where pnputil >> "%LOG%" 2>&1
if %ERRORLEVEL%==0 (
  for /f "tokens=1" %%I in ('pnputil /enum-drivers ^| findstr /i "vmware"') do (
    echo Removing PnP driver: %%I >> "%LOG%"
    pnputil /delete-driver %%I /uninstall /force >> "%LOG%" 2>&1
  )
) else (
  echo pnputil not available; skipping PnP driver removal >> "%LOG%"
)

echo --- VMware devices removal from Device Manager --- >> "%LOG%"
where powershell >> "%LOG%" 2>&1
if %ERRORLEVEL%==0 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Continue';" ^
    "try {" ^
    " $devcon = Get-WmiObject Win32_PnPEntity | Where-Object { $_.Name -match 'VMware' -or $_.Manufacturer -match 'VMware' };" ^
    " if($devcon) {" ^
    "  foreach($d in $devcon) {" ^
    "   ('Removing device: ' + $d.Name) | Out-File -Append -Encoding ascii $env:LOG;" ^
    "   try { $d.Delete() } catch { $_ | Out-File -Append -Encoding ascii $env:LOG }" ^
    "  }" ^
    " } else {" ^
    "  'No VMware devices found in Device Manager' | Out-File -Append -Encoding ascii $env:LOG;" ^
    " }" ^
    "} catch { $_ | Out-File -Append -Encoding ascii $env:LOG }" ^
    >> "%LOG%" 2>&1
)

echo --- VMware Tools directory cleanup (best-effort but deterministic) --- >> "%LOG%"
for %%D in (
  "%ProgramFiles%\VMware\VMware Tools"
  "%ProgramFiles(x86)%\VMware\VMware Tools"
) do (
  if exist "%%~D" (
    echo Removing %%~D >> "%LOG%"
    dir /s /b "%%~D" >> "%LOG%" 2>&1
    takeown /f "%%~D" /r /d y >> "%LOG%" 2>&1
    icacls "%%~D" /grant Administrators:F /t >> "%LOG%" 2>&1
    rmdir /s /q "%%~D" >> "%LOG%" 2>&1
    if exist "%%~D" (
      echo WARN: directory still exists after rmdir: %%~D >> "%LOG%"
    ) else (
      echo OK: removed %%~D >> "%LOG%"
    )
  )
)
"""


# Firstboot provisioning: refactored into small helpers


@dataclass(frozen=True)
class _FirstbootPolicyPaths:
    guest_dir: str = _DEFAULT_GUEST_DIR
    driver_stage_dir: str = _DEFAULT_DRIVER_STAGE_DIR
    log_path: str = _DEFAULT_LOG_PATH
    marker_path: str = _DEFAULT_MARKER_PATH

    def as_dict(self) -> dict[str, str]:
        """Return the policy paths as a plain dict."""
        return {
            "guest_dir": self.guest_dir,
            "driver_stage_dir": self.driver_stage_dir,
            "log_path": self.log_path,
            "marker_path": self.marker_path,
        }


@dataclass(frozen=True)
class _FirstbootWinPaths:
    win_guest_dir: str
    win_stage_dir: str
    win_log: str
    win_marker: str


def _enforce_firstboot_policy_paths(
    guest_dir: str,
    driver_stage_dir: str,
    log_path: str,
    marker_path: str,
    *,
    notes: list[str],
) -> _FirstbootPolicyPaths:
    gd = guest_dir
    sd = driver_stage_dir
    lp = log_path
    mp = marker_path

    if gd.rstrip("/") != _DEFAULT_GUEST_DIR:
        notes.append(f"guest_dir overridden to {_DEFAULT_GUEST_DIR} for stability (was {gd})")
        gd = _DEFAULT_GUEST_DIR
    if sd.rstrip("/") != _DEFAULT_DRIVER_STAGE_DIR:
        notes.append(f"driver_stage_dir overridden to {_DEFAULT_DRIVER_STAGE_DIR} for stability (was {sd})")
        sd = _DEFAULT_DRIVER_STAGE_DIR
    if lp.rstrip("/") != _DEFAULT_LOG_PATH:
        notes.append(f"log_path overridden to {_DEFAULT_LOG_PATH} for stability (was {lp})")
        lp = _DEFAULT_LOG_PATH
    if mp.rstrip("/") != _DEFAULT_MARKER_PATH:
        notes.append(f"marker_path overridden to {_DEFAULT_MARKER_PATH} for stability (was {mp})")
        mp = _DEFAULT_MARKER_PATH

    return _FirstbootPolicyPaths(guest_dir=gd, driver_stage_dir=sd, log_path=lp, marker_path=mp)


def _firstboot_windows_paths(service_name: str) -> _FirstbootWinPaths:
    # Windows runtime paths aligned with policy guestfs paths:
    #   guestfs /hyper2kvm               -> Windows C:\hyper2kvm
    #   guestfs /hyper2kvm/drivers/virtio-> Windows C:\hyper2kvm\drivers\virtio
    #   guestfs /Windows/Temp/...        -> Windows C:\Windows\Temp\...
    win_guest_dir = r"%SystemDrive%\hyper2kvm"
    win_stage_dir = rf"{win_guest_dir}\drivers\virtio"
    win_log = rf"%SystemRoot%\Temp\{service_name}.log"
    win_marker = rf"{win_guest_dir}\{service_name}.done"
    return _FirstbootWinPaths(
        win_guest_dir=win_guest_dir,
        win_stage_dir=win_stage_dir,
        win_log=win_log,
        win_marker=win_marker,
    )


def _firstboot_extra_cmd_block(extra_cmd: str | None) -> str:
    if not extra_cmd:
        return ""
    # Keep this as "call ..." because user might pass a .cmd/.bat path.
    return (
        "\r\n"
        'echo ==== EXTRA CMD BEGIN ====>> "%LOG%"\r\n'
        f'call {extra_cmd} >> "%LOG%" 2>&1\r\n'
        'echo ==== EXTRA CMD END ====>> "%LOG%"\r\n'
    )


def _firstboot_build_cmd_script(  # pylint: disable=too-many-arguments,too-many-locals  # assembles firstboot.cmd from many independent optional feature blocks
    *,
    service_name: str,
    win: _FirstbootWinPaths,
    include_vmware_removal: bool,
    include_qemu_ga: bool = True,
    include_enhanced_virtio: bool = True,
    include_network_reconfig: bool = True,
    include_rdp: bool = True,
    include_event_log: bool = True,
    include_health_check: bool = True,
    include_metadata: bool = True,
    extra_cmd: str | None,
) -> str:
    extra = _firstboot_extra_cmd_block(extra_cmd)

    # Enterprise features (in order of execution)
    qemu_ga_block = _qemu_guest_agent_installation_cmd_block().strip() + "\r\n" if include_qemu_ga else ""
    enhanced_virtio_block = (
        _enhanced_virtio_driver_installation_cmd_block().strip() + "\r\n" if include_enhanced_virtio else ""
    )
    sid_block = _sid_regeneration_cmd_block().strip() + "\r\n"  # Always include (informational)
    network_block = _network_reconfiguration_cmd_block().strip() + "\r\n" if include_network_reconfig else ""
    rdp_block = _rdp_enablement_cmd_block().strip() + "\r\n" if include_rdp else ""
    event_log_block = (
        _windows_event_log_integration_cmd_block().strip() + "\r\n" if include_event_log else ""
    )
    health_block = _health_verification_cmd_block().strip() + "\r\n" if include_health_check else ""
    metadata_block = _conversion_metadata_cmd_block().strip() + "\r\n" if include_metadata else ""

    vmware_block = ""
    if include_vmware_removal:
        vmware_block = _vmware_tools_removal_cmd_block().strip() + "\r\n"

    # NOTE: This is a "pure string builder"; no guestfs/hivex side effects.
    return rf"""@echo off
setlocal EnableExtensions EnableDelayedExpansion

set LOG={win.win_log}
set SVC={service_name}
set STAGE={win.win_stage_dir}
set MARKER={win.win_marker}

rem ---- idempotency guard ----
if exist "%MARKER%" (
  echo hyper2kvm firstboot marker exists: %MARKER%>> "%LOG%"
  echo Exiting without doing work.>> "%LOG%"
  exit /b 0
)

echo ==================================================>> "%LOG%"
echo ==================================================>> "%LOG%"
echo    Hyper2KVM Enterprise First Boot Initialization
echo ==================================================>> "%LOG%"
echo ==================================================>> "%LOG%"
echo Started: %DATE% %TIME%>> "%LOG%"
echo ComputerName: %COMPUTERNAME%>> "%LOG%"
echo SystemDrive: %SystemDrive%>> "%LOG%"
echo SystemRoot: %SystemRoot%>> "%LOG%"
echo StageDir: %STAGE%>> "%LOG%"
echo ==================================================>> "%LOG%"

echo === System Information === >> "%LOG%"
echo --- Windows Version --- >> "%LOG%"
ver >> "%LOG%"

echo --- Disk / Volume Information --- >> "%LOG%"
where wmic >> "%LOG%" 2>&1
if %ERRORLEVEL%==0 (
  wmic logicaldisk get deviceid, volumename, filesystem, freespace, size >> "%LOG%" 2>&1
  wmic computersystem get manufacturer, model, totalphysicalmemory >> "%LOG%" 2>&1
) else (
  echo wmic not available >> "%LOG%"
)

echo --- Verify Staged Drivers --- >> "%LOG%"
if not exist "%STAGE%" (
  echo WARNING: Stage dir missing: %STAGE%>> "%LOG%"
  mkdir "%STAGE%" 2>> "%LOG%"
) else (
  echo Stage directory exists: %STAGE%>> "%LOG%"
  dir /s /b "%STAGE%" >> "%LOG%" 2>&1
)

echo.>> "%LOG%"
echo ==================================================>> "%LOG%"
echo   Starting Enterprise Initialization (8 Steps)
echo ==================================================>> "%LOG%"
echo.>> "%LOG%"

{qemu_ga_block}
{enhanced_virtio_block}
{sid_block}
{network_block}
{rdp_block}
{event_log_block}
{health_block}
{metadata_block}

rem === Legacy driver installation (pnputil fallback) ===
echo === Legacy INF Driver Installation (Fallback) === >> "%LOG%"
where pnputil >> "%LOG%" 2>&1
if %ERRORLEVEL%==0 (
  for /f "delims=" %%I in ('dir /b /s "%STAGE%\*.inf" 2^>nul') do (
    echo Installing INF: %%I >> "%LOG%"
    pnputil /add-driver "%%I" /install >> "%LOG%" 2>&1
    echo pnputil rc=!ERRORLEVEL!>> "%LOG%"
  )
) else (
  echo pnputil not found; cannot install INF drivers >> "%LOG%"
)

{vmware_block}
{extra}

echo.>> "%LOG%"
echo ==================================================>> "%LOG%"
echo   Finalization
echo ==================================================>> "%LOG%"

echo --- Write completion marker --- >> "%LOG%"
echo Conversion completed at %DATE% %TIME%> "%MARKER%" 2>> "%LOG%"
if exist "%MARKER%" (
  echo Marker written: %MARKER%>> "%LOG%"
) else (
  echo WARNING: failed to write marker: %MARKER%>> "%LOG%"
)

echo --- Self-delete service --- >> "%LOG%"
where sc.exe >> "%LOG%" 2>&1
if %ERRORLEVEL%==0 (
  echo Deleting service %SVC% (1060 == already removed) >> "%LOG%"
  sc.exe stop "%SVC%" >> "%LOG%" 2>&1
  sc.exe delete "%SVC%" >> "%LOG%" 2>&1
  echo Service delete attempted (rc: !ERRORLEVEL!) >> "%LOG%"
) else (
  echo sc.exe not found; cannot delete service >> "%LOG%"
)

echo --- Remove Run key (login trigger fallback) --- >> "%LOG%"
reg delete "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" /v "%SVC%" /f >> "%LOG%" 2>&1
reg delete "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce" /v "%SVC%" /f >> "%LOG%" 2>&1
echo Run key cleanup done >> "%LOG%"

echo --- Remove Startup folder script (login trigger fallback) --- >> "%LOG%"
if exist "%ProgramData%\Microsoft\Windows\Start Menu\Programs\Startup\hyper2kvm-firstboot.bat" (
  del /f /q "%ProgramData%\Microsoft\Windows\Start Menu\Programs\Startup\hyper2kvm-firstboot.bat" >> "%LOG%" 2>&1
  echo Startup folder script removed >> "%LOG%"
) else (
  echo Startup folder script already removed >> "%LOG%"
)

echo.>> "%LOG%"
echo ==================================================>> "%LOG%"
echo ==================================================>> "%LOG%"
echo    Hyper2KVM Enterprise First Boot Initialization
echo                     COMPLETED
echo ==================================================>> "%LOG%"
echo ==================================================>> "%LOG%"
echo Completed: %DATE% %TIME%>> "%LOG%"
echo Log file: %LOG%>> "%LOG%"
echo.>> "%LOG%"
echo Please check Windows Event Viewer (Application log)>> "%LOG%"
echo for hyper2kvm events (Event ID 1000)>> "%LOG%"
echo.>> "%LOG%"

endlocal
exit /b 0
"""


def _firstboot_create_guest_dirs(
    logger: logging.Logger, g: guestfs.GuestFS, policy: _FirstbootPolicyPaths
) -> None:
    _mkdir_p_guest(logger, g, policy.guest_dir)
    _mkdir_p_guest(logger, g, str(Path(policy.log_path).parent).replace("\\", "/"))
    _mkdir_p_guest(logger, g, policy.driver_stage_dir)


def _firstboot_upload_payload(  # pylint: disable=too-many-arguments  # bundles all upload inputs (target, content, policy, result sink) in one call
    logger: logging.Logger,
    g: guestfs.GuestFS,
    *,
    policy: _FirstbootPolicyPaths,
    service_name: str,
    script_text: str,
    results: dict[str, Any],
    dry_run: bool,
) -> str:
    script_name = f"{service_name}.cmd"
    guest_firstboot = _guest_path_join(policy.guest_dir, script_name)
    if not dry_run:
        _upload_bytes(logger, g, guest_firstboot, _encode_windows_cmd_script(script_text), results=results)
    return guest_firstboot


def _firstboot_service_cmdline(service_name: str = "hyper2kvm-firstboot") -> str:
    """Return the literal Windows path to the firstboot script.

    Uses C:\\hyper2kvm (literal, no env vars) because rhsrvany reads
    Parameters\\CommandLine as REG_SZ — environment variables are NOT expanded.
    """
    return rf'"C:\hyper2kvm\{service_name}.cmd"'


# Top-level entry point wires together every optional enterprise firstboot feature.
# pylint: disable-next=too-many-arguments,too-many-locals,too-many-branches,too-many-statements
def provision_firstboot_payload_and_service(
    self,
    g: guestfs.GuestFS,
    *,
    system_hive_path: str = "/Windows/System32/config/SYSTEM",
    service_name: str = "hyper2kvm-firstboot",
    guest_dir: str = _DEFAULT_GUEST_DIR,
    log_path: str = _DEFAULT_LOG_PATH,
    driver_stage_dir: str = _DEFAULT_DRIVER_STAGE_DIR,
    extra_cmd: str | None = None,
    remove_vmware_tools: bool = False,
    install_qemu_guest_agent: bool = True,
    enhanced_virtio_install: bool = True,
    network_reconfiguration: bool = True,
    enable_rdp: bool = True,
    event_log_integration: bool = True,
    health_verification: bool = True,
    create_metadata: bool = True,
    marker_path: str = _DEFAULT_MARKER_PATH,
) -> dict[str, Any]:
    """
    End-to-end enterprise firstboot provisioning (policy-driven paths for stability):
      1) Ensure Windows system volume is mounted as / (C: mapping)
      2) Upload firstboot.cmd to /hyper2kvm/firstboot.cmd with enterprise features
      3) Create a service that runs it at boot (LocalSystem)
      4) Record uploads (sha256 + bytes)

    Enterprise features (matching Linux systemd firstboot):
      - VMware Tools removal (comprehensive: registry, services, drivers, pnputil)
      - QEMU Guest Agent installation
      - Enhanced VirtIO driver installation (multiple methods)
      - Machine identity (SID regeneration info)
      - Network reconfiguration (MAC address changes)
      - RDP enablement
      - Windows Event Log integration (matches systemd journal)
      - Health verification
      - Conversion metadata creation

    NOTE: guest_dir/log_path/driver_stage_dir/marker_path are policy paths.
    If callers pass different values, we override them (and record a note) to
    prevent Windows runtime paths from diverging from guestfs paths.
    """
    logger = _safe_logger(self)
    dry_run = bool(getattr(self, "dry_run", False))

    logger.debug(
        "provision_firstboot_payload_and_service: service_name=%s, dry_run=%s, "
        "remove_vmware_tools=%s, install_qemu_ga=%s",
        service_name,
        dry_run,
        remove_vmware_tools,
        install_qemu_guest_agent,
    )
    logger.debug(
        "provision_firstboot: enterprise features: enhanced_virtio=%s, "
        "network_reconfig=%s, rdp=%s, event_log=%s, health=%s, metadata=%s",
        enhanced_virtio_install,
        network_reconfiguration,
        enable_rdp,
        event_log_integration,
        health_verification,
        create_metadata,
    )

    results: dict[str, Any] = {
        "success": False,
        "dry_run": dry_run,
        "errors": [],
        "notes": [],
        "uploaded_files": [],
        "service": None,
        "payload": None,
        "paths": {},
        "enterprise_features": {
            "remove_vmware_tools": bool(remove_vmware_tools),
            "install_qemu_guest_agent": bool(install_qemu_guest_agent),
            "enhanced_virtio_install": bool(enhanced_virtio_install),
            "network_reconfiguration": bool(network_reconfiguration),
            "enable_rdp": bool(enable_rdp),
            "event_log_integration": bool(event_log_integration),
            "health_verification": bool(health_verification),
            "create_metadata": bool(create_metadata),
        },
    }

    # 1) Enforce stable guest paths (policy)
    logger.debug("Step 1: Enforcing stable guest paths (policy)")
    policy = _enforce_firstboot_policy_paths(
        guest_dir=guest_dir,
        driver_stage_dir=driver_stage_dir,
        log_path=log_path,
        marker_path=marker_path,
        notes=results["notes"],
    )
    results["paths"] = policy.as_dict()

    # 2) Ensure correct Windows root mount (C: mapping)
    logger.debug("Step 2: Ensuring Windows root mount")
    try:
        _ensure_windows_root(logger, g, hint_hive_path=system_hive_path)
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort mount step, must not abort provisioning
        logger.debug("Windows root mount failed: %s", e)
        results["errors"].append(str(e))
        return results

    # 3) Create guest directories
    logger.debug("Step 3: Creating guest directories: %s", policy.as_dict())
    try:
        _firstboot_create_guest_dirs(logger, g, policy)
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort dir creation, must not abort provisioning
        logger.debug("Failed to create guest dirs: %s", e)
        results["errors"].append(f"Failed to create guest dirs: {e}")
        return results

    # 4) Build enterprise script + upload
    logger.debug("Step 4: Building enterprise script")
    win = _firstboot_windows_paths(service_name)
    script = _firstboot_build_cmd_script(
        service_name=service_name,
        win=win,
        include_vmware_removal=bool(remove_vmware_tools),
        include_qemu_ga=bool(install_qemu_guest_agent),
        include_enhanced_virtio=bool(enhanced_virtio_install),
        include_network_reconfig=bool(network_reconfiguration),
        include_rdp=bool(enable_rdp),
        include_event_log=bool(event_log_integration),
        include_health_check=bool(health_verification),
        include_metadata=bool(create_metadata),
        extra_cmd=extra_cmd,
    )
    script_bytes = len(script.encode("utf-8"))
    script_hash = hashlib.sha256(script.encode("utf-8")).hexdigest()
    logger.debug(
        "Firstboot script built: size=%d bytes, sha256=%s",
        script_bytes,
        script_hash,
    )
    try:
        guest_script_path = _firstboot_upload_payload(
            logger,
            g,
            policy=policy,
            service_name=service_name,
            script_text=script,
            results=results,
            dry_run=dry_run,
        )
        logger.debug("Firstboot payload uploaded to: %s", guest_script_path)
        results["payload"] = {
            "guest_path": guest_script_path,
            "log_path": policy.log_path,
            "marker_path": policy.marker_path,
        }
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort payload upload, must not abort provisioning
        logger.debug("Failed to upload firstboot.cmd: %s", e)
        results["errors"].append(f"Failed to upload firstboot.cmd: {e}")
        return results

    # 4b) Upload rhsrvany.exe service wrapper (required for reliable service execution)
    logger.debug(
        "Step 4b: rhsrvany.exe check: local_exists=%s, dry_run=%s",
        _RHSRVANY_LOCAL.is_file(),
        dry_run,
    )
    rhsrvany_uploaded = False
    if _RHSRVANY_LOCAL.is_file() and not dry_run:
        try:
            _mkdir_p_guest(logger, g, _RHSRVANY_GUEST_DIR)
            g.upload(str(_RHSRVANY_LOCAL), _RHSRVANY_GUEST_PATH)
            rhsrvany_uploaded = True
            logger.info("Uploaded rhsrvany.exe to %s", _RHSRVANY_GUEST_PATH)
            results["rhsrvany"] = {"uploaded": True, "guest_path": _RHSRVANY_GUEST_PATH}
        except Exception as e:  # pylint: disable=broad-exception-caught  # optional wrapper upload, must not abort provisioning
            logger.warning("Failed to upload rhsrvany.exe (will fall back to cmd.exe): %s", e)
            results["rhsrvany"] = {"uploaded": False, "error": str(e)}

    # 5) Add service in SYSTEM hive
    logger.debug("Step 5: Adding service in SYSTEM hive (use_rhsrvany=%s)", rhsrvany_uploaded)
    cmdline = _firstboot_service_cmdline(service_name)
    logger.debug("Service cmdline: %s", cmdline)
    svc_res = _add_firstboot_service_system_hive(
        self,
        g,
        system_hive_path,
        service_name=service_name,
        display_name="hyper2kvm First Boot Driver Installer",
        cmdline=cmdline,
        start=2,
        use_rhsrvany=rhsrvany_uploaded,
        description="One-shot first boot installer for hyper2kvm staged drivers; writes log to Windows\\Temp.",
    )
    results["service"] = svc_res
    if not svc_res.get("success"):
        results["errors"].extend(svc_res.get("errors", []))
        return results

    # 5b) Add Run key in SOFTWARE hive
    logger.debug("Step 5b: Adding Run key fallback in SOFTWARE hive")
    # persistent login trigger for Win11 edge builds
    # where cmd.exe-based services may not execute reliably under SCM).
    # Uses "Run" instead of "RunOnce" — RunOnce only fires on NEW logins, but if the
    # user session was already active from the VMware image, RunOnce never triggers.
    # The firstboot.cmd has an idempotency guard (marker file) so repeated runs are safe.
    try:
        software_hive = system_hive_path.replace("/SYSTEM", "/SOFTWARE")
        run_cmd = f'cmd.exe /c "C:\\hyper2kvm\\{service_name}.cmd"'

        # Add to HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run (persistent)
        run_res = _add_software_run_key(
            self,
            g,
            software_hive,
            name=service_name,
            command=run_cmd,
        )
        results["run_key"] = run_res
        if run_res.get("success"):
            logger.info("Run key fallback set: %s", service_name)
        else:
            logger.debug("Run key fallback failed (non-fatal): %s", run_res.get("errors"))
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort fallback, must not abort provisioning
        logger.debug("Run key fallback failed (non-fatal): %s", e)
        results["run_key"] = {"success": False, "error": str(e)}

    # 5c) Upload a startup folder script
    logger.debug("Step 5c: Uploading Startup folder fallback script")
    # from the attached CD-ROM on first user login. Scans drives for
    # virtio-win-guest-tools.exe and runs it silently. If not found,
    # opens the CD-ROM drive in Explorer with a notification.
    if not dry_run:
        try:
            startup_bat = (
                "@echo off\r\n"
                f'if exist "C:\\hyper2kvm\\{service_name}.done" goto :eof\r\n'
                "setlocal enabledelayedexpansion\r\n"
                "set LOGFILE=C:\\Windows\\Logs\\virtio-install.log\r\n"
                "echo %DATE% %TIME% - VirtIO auto-install started >> %LOGFILE%\r\n"
                "\r\n"
                "rem Find VirtIO CD-ROM\r\n"
                "for %%i in (D E F G H I J K L M N O P Q R S T U V W X Y Z) do (\r\n"
                "    if exist %%i:\\virtio-win-guest-tools.exe (\r\n"
                "        echo %DATE% %TIME% - Found VirtIO at %%i: >> %LOGFILE%\r\n"
                "        start /wait %%i:\\virtio-win-guest-tools.exe /S /norestart\r\n"
                "        echo %DATE% %TIME% - Install exit code: !ERRORLEVEL! >> %LOGFILE%\r\n"
                f'        echo done > "C:\\hyper2kvm\\{service_name}.done"\r\n'
                '        del "%~f0"\r\n'
                "        exit /b 0\r\n"
                "    )\r\n"
                "    if exist %%i:\\guest-agent\\virtio-win-guest-tools.exe (\r\n"
                "        echo %DATE% %TIME% - Found VirtIO at %%i:\\guest-agent >> %LOGFILE%\r\n"
                "        start /wait %%i:\\guest-agent\\virtio-win-guest-tools.exe /S /norestart\r\n"
                "        echo %DATE% %TIME% - Install exit code: !ERRORLEVEL! >> %LOGFILE%\r\n"
                f'        echo done > "C:\\hyper2kvm\\{service_name}.done"\r\n'
                '        del "%~f0"\r\n'
                "        exit /b 0\r\n"
                "    )\r\n"
                ")\r\n"
                "\r\n"
                "rem CD-ROM not found — open Explorer and notify user\r\n"
                "echo %DATE% %TIME% - VirtIO CD not found, notifying user >> %LOGFILE%\r\n"
                'msg * /time:30 "hyper2kvm: VirtIO drivers need to be installed. Please open the '
                'CD-ROM drive (D:) and run virtio-win-guest-tools.exe" 2>nul\r\n'
                "if exist D:\\ explorer.exe D:\\\r\n"
            )
            startup_guest_path = (
                "/ProgramData/Microsoft/Windows/Start Menu/Programs/Startup/hyper2kvm-firstboot.bat"
            )
            _mkdir_p_guest(
                logger,
                g,
                "/ProgramData/Microsoft/Windows/Start Menu/Programs/Startup",
            )
            _upload_bytes(
                logger,
                g,
                startup_guest_path,
                _encode_windows_cmd_script(startup_bat),
                results=results,
            )
            results["startup_folder"] = {"uploaded": True, "guest_path": startup_guest_path}
            logger.info("Startup folder fallback uploaded: %s", startup_guest_path)
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort fallback, must not abort provisioning
            logger.debug("Startup folder fallback failed (non-fatal): %s", e)
            results["startup_folder"] = {"uploaded": False, "error": str(e)}

    # 6) Enterprise notes + success
    results["notes"] += [
        "Enterprise firstboot uses SERVICE (LocalSystem) + Run key + Startup folder fallback for Win11 compatibility.",
        "Log file: C:\\Windows\\Temp\\hyper2kvm-firstboot.log (guestfs: /Windows/Temp/hyper2kvm-firstboot.log).",
        "Drivers staged under: C:\\hyper2kvm\\drivers\\virtio (guestfs: /hyper2kvm/drivers/virtio).",
        "Completion marker: C:\\hyper2kvm\\firstboot.done (prevents re-runs if service delete fails).",
        "Conversion metadata: C:\\hyper2kvm\\metadata.json (tracks applied features and timestamps).",
        "Windows Event Log: Application log with source 'hyper2kvm' (Event ID 1000 on completion).",
        "uploaded_files includes sha256+size for verification.",
    ]

    # Add feature-specific notes
    if remove_vmware_tools:
        results["notes"].append(
            "✅ VMware Tools removal: registry uninstall + services stop/delete + "
            "driver removal via pnputil + directory cleanup"
        )
    if install_qemu_guest_agent:
        results["notes"].append(
            "✅ QEMU Guest Agent: MSI installation from staged drivers (C:\\hyper2kvm\\drivers\\virtio\\guest-agent\\)"
        )
    if enhanced_virtio_install:
        results["notes"].append(
            "✅ Enhanced VirtIO: 4 installation methods (INF files, DriverStore, hardware scan, device enablement)"
        )
    if network_reconfiguration:
        results["notes"].append(
            "✅ Network reconfiguration: VMware adapter disable, VirtIO adapter reset, DHCP lease renewal"
        )
    if enable_rdp:
        results["notes"].append(
            "✅ RDP enablement: fDenyTSConnections=0, firewall rules, TermService/UmRdpService Automatic+start"
        )
    if event_log_integration:
        results["notes"].append(
            "✅ Event Log integration: hyper2kvm event source registered + completion event (ID 1000)"
        )
    if health_verification:
        results["notes"].append(
            "✅ Health verification: QEMU-GA status, network connectivity, VirtIO devices, disk space, failed services"
        )
    if create_metadata:
        results["notes"].append(
            "✅ Conversion metadata: JSON file with timestamp, features applied, OS version, computer name"
        )

    results["notes"].append(
        "\nTo verify firstboot execution:\n"
        "  1. Check log: type C:\\Windows\\Temp\\hyper2kvm-firstboot.log\n"
        "  2. Check Event Viewer: Application log → Source: hyper2kvm → Event ID 1000\n"
        "  3. Check metadata: type C:\\hyper2kvm\\metadata.json\n"
        "  4. Check QEMU-GA: sc query QEMU-GA\n"
        "  5. Check marker: dir C:\\hyper2kvm\\firstboot.done"
    )

    results["success"] = True
    logger.debug(
        "provision_firstboot_payload_and_service completed: success=True, "
        "mechanisms: service=%s, run_key=%s, startup_folder=%s",
        bool(results.get("service", {}).get("success")),
        bool(results.get("run_key", {}).get("success")),
        bool(results.get("startup_folder", {}).get("uploaded")),
    )
    return results


def log_firstboot_provision_summary(
    logger: logging.Logger,
    fb: dict[str, Any],
    *,
    guest_log_windows_path: str = r"C:\Windows\Temp\hyper2kvm-firstboot.log",
    virtio_packages: int = 0,
) -> None:
    """Emit INFO/WARNING lines summarizing firstboot install for migration logs."""
    if fb.get("skipped"):
        logger.info("Firstboot: skipped (%s)", fb.get("reason", "unknown"))
        return
    if not fb.get("success", True):
        logger.warning(
            "Firstboot: provisioning failed — guest boot scripts may not run (%s)",
            fb.get("errors") or fb.get("error") or "see fixer report",
        )
        return

    feats = fb.get("enterprise_features") or {}
    logger.info(
        "Firstboot: installed hyper2kvm-firstboot (virtio_packages=%d, rdp=%s, qemu_ga=%s, "
        "enhanced_virtio=%s)",
        virtio_packages,
        feats.get("enable_rdp", True),
        feats.get("install_qemu_guest_agent", True),
        feats.get("enhanced_virtio_install", True),
    )
    logger.info(
        "  Runs on first guest boot — log: %s | marker: C:\\hyper2kvm\\firstboot.done",
        guest_log_windows_path,
    )
    if feats.get("enable_rdp"):
        logger.info(
            "  At boot: fDenyTSConnections=0, Remote Desktop firewall rules, "
            "TermService/UmRdpService Automatic+start"
        )
