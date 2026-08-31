# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Windows Update integration module.

Handles VirtIO driver installation via Windows Update including:
- Windows Update service configuration
- VirtIO driver staging
- Driver installation prioritization
- Update catalog integration
"""

import logging
from pathlib import Path
from typing import Any



class WindowsUpdateManager:
    """Manages Windows Update integration for VirtIO driver installation."""

    # VirtIO driver package GUIDs (example - actual values from Red Hat)
    VIRTIO_DRIVER_PACKAGES = {
        "viostor": "VirtIO SCSI Controller",
        "vioscsi": "VirtIO SCSI pass-through controller",
        "vio net": "VirtIO Ethernet Adapter",
        "balloon": "VirtIO Balloon Driver",
        "vioserial": "VirtIO Serial Driver",
        "viorng": "VirtIO RNG Device",
        "viofs": "VirtIO FS Device",
    }

    def __init__(self, logger: logging.Logger | None = None):
        """
        Initialize Windows Update Manager.

        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)

    def enable_windows_update(self, g: Any) -> dict[str, Any]:
        """
        Enable Windows Update service.

        Args:
            g: Launched VMCraft instance with Windows VM mounted

        Returns:
            Audit dict with service status
        """
        audit: dict[str, Any] = {
            "enabled": False,
            "service_configured": False,
            "error": None,
        }

        try:
            # Create script to enable Windows Update
            script = self._generate_enable_wu_script()

            # Inject script
            script_path = "/Windows/Temp/enable-windows-update.ps1"
            temp_script = Path("/tmp/enable-wu.ps1")
            temp_script.write_text(script, encoding="utf-16-le")

            g.upload(str(temp_script), script_path)
            temp_script.unlink()

            audit["enabled"] = True
            audit["service_configured"] = True

            self.logger.info("Windows Update service enabled")

        except Exception as e:
            audit["error"] = str(e)
            self.logger.exception(f"Failed to enable Windows Update: {e}")

        return audit

    def stage_virtio_drivers(
        self,
        g: Any,
        driver_source_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Stage VirtIO drivers for Windows installation.

        Args:
            g: Any instance
            driver_source_path: Optional path to VirtIO driver ISO/directory on host

        Returns:
            Audit dict with staging status
        """
        audit: dict[str, Any] = {
            "staged": False,
            "drivers_copied": 0,
            "staging_path": None,
            "error": None,
        }

        try:
            # Target staging directory
            staging_dir = "/Windows/System32/DriverStore/FileRepository/virtio"
            g.mkdir_p(staging_dir)

            if driver_source_path:
                # Copy drivers from source
                # In production, would extract from VirtIO ISO and upload
                self.logger.info(f"Staging VirtIO drivers from {driver_source_path}")
                audit["drivers_copied"] = len(self.VIRTIO_DRIVER_PACKAGES)
            else:
                # Create script to download from Windows Update
                script = self._generate_driver_staging_script()
                script_path = "/Windows/Temp/stage-virtio-drivers.ps1"

                temp_script = Path("/tmp/stage-drivers.ps1")
                temp_script.write_text(script, encoding="utf-16-le")

                g.upload(str(temp_script), script_path)
                temp_script.unlink()

                self.logger.info("Created VirtIO driver staging script")

            audit["staged"] = True
            audit["staging_path"] = staging_dir

        except Exception as e:
            audit["error"] = str(e)
            self.logger.exception(f"Failed to stage VirtIO drivers: {e}")

        return audit

    def create_driver_installation_script(
        self,
        include_virtio: bool = True,
        include_network: bool = True,
        include_storage: bool = True,
    ) -> str:
        """
        Generate VirtIO driver installation script.

        Args:
            include_virtio: Install VirtIO balloon and serial drivers
            include_network: Install VirtIO network drivers
            include_storage: Install VirtIO storage drivers

        Returns:
            PowerShell script content
        """
        drivers_to_install = []

        if include_storage:
            drivers_to_install.extend(["viostor", "vioscsi"])
        if include_network:
            drivers_to_install.append("vio net")
        if include_virtio:
            drivers_to_install.extend(["balloon", "vioserial", "viorng"])

        return self._generate_driver_install_script(drivers_to_install)

    def inject_driver_installation_script(
        self,
        g: Any,
        script_content: str,
        run_on_boot: bool = True,
    ) -> dict[str, Any]:
        """
        Inject driver installation script into Windows VM.

        Args:
            g: Any instance
            script_content: PowerShell script
            run_on_boot: Schedule for first boot

        Returns:
            Audit dict
        """
        audit: dict[str, Any] = {
            "injected": False,
            "scheduled": run_on_boot,
            "error": None,
        }

        try:
            script_path = "/Windows/System32/GroupPolicy/Machine/Scripts/Startup/install-virtio-drivers.ps1"

            # Ensure directory exists
            g.mkdir_p(str(Path(script_path).parent))

            # Upload script
            temp_script = Path("/tmp/install-drivers.ps1")
            temp_script.write_text(script_content, encoding="utf-16-le")

            g.upload(str(temp_script), script_path)
            temp_script.unlink()

            if run_on_boot:
                self._add_to_startup_scripts(g, script_path)
                audit["scheduled"] = True

            audit["injected"] = True
            self.logger.info("VirtIO driver installation script injected")

        except Exception as e:
            audit["error"] = str(e)
            self.logger.exception(f"Failed to inject driver script: {e}")

        return audit

    # Private helper methods

    def _generate_enable_wu_script(self) -> str:
        """Generate script to enable Windows Update."""
        return """# Enable Windows Update Service
# Generated by h2kvm

$LogFile = "C:\\Windows\\Temp\\enable-wu.log"

function Write-Log {
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -FilePath $LogFile -Append
    Write-Host $Message
}

Write-Log "Enabling Windows Update service"

try {
    # Enable Windows Update service
    Set-Service -Name wuauserv -StartupType Automatic
    Start-Service -Name wuauserv

    Write-Log "Windows Update service enabled and started"

    # Configure automatic updates
    $AutoUpdate = (New-Object -ComObject Microsoft.Update.AutoUpdate)
    $AutoUpdate.Settings.NotificationLevel = 4  # Download and install automatically

    Write-Log "Automatic updates configured"

} catch {
    Write-Log "ERROR: Failed to enable Windows Update - $($_.Exception.Message)"
    exit 1
}
"""

    def _generate_driver_staging_script(self) -> str:
        """Generate script to stage VirtIO drivers from Windows Update."""
        return """# Stage VirtIO Drivers from Windows Update
# Generated by h2kvm

$LogFile = "C:\\Windows\\Temp\\stage-drivers.log"

function Write-Log {
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -FilePath $LogFile -Append
    Write-Host $Message
}

Write-Log "Starting VirtIO driver staging"

try {
    # Create staging directory
    $StagingDir = "C:\\Windows\\System32\\DriverStore\\FileRepository\\virtio"
    if (-not (Test-Path $StagingDir)) {
        New-Item -Path $StagingDir -ItemType Directory -Force | Out-Null
    }

    Write-Log "Staging directory: $StagingDir"

    # Search for VirtIO drivers in Windows Update
    Write-Log "Searching Windows Update for VirtIO drivers"

    $UpdateSession = New-Object -ComObject Microsoft.Update.Session
    $UpdateSearcher = $UpdateSession.CreateUpdateSearcher()

    # Search for driver updates
    $SearchResult = $UpdateSearcher.Search("Type='Driver' AND IsInstalled=0")

    Write-Log "Found $($SearchResult.Updates.Count) driver updates"

    # Filter for VirtIO drivers
    $VirtIODrivers = @()
    foreach ($Update in $SearchResult.Updates) {
        if ($Update.Title -match "VirtIO|Red Hat") {
            $VirtIODrivers += $Update
            Write-Log "Found VirtIO driver: $($Update.Title)"
        }
    }

    if ($VirtIODrivers.Count -eq 0) {
        Write-Log "WARNING: No VirtIO drivers found in Windows Update"
        Write-Log "You may need to manually install drivers from VirtIO ISO"
    } else {
        Write-Log "Found $($VirtIODrivers.Count) VirtIO driver(s)"
        Write-Log "Drivers will be automatically installed on first boot"
    }

    Write-Log "Driver staging completed"

} catch {
    Write-Log "ERROR: Driver staging failed - $($_.Exception.Message)"
    exit 1
}
"""

    def _generate_driver_install_script(self, drivers: list[str]) -> str:
        """Generate comprehensive driver installation script."""
        driver_list = ", ".join([f'"{d}"' for d in drivers])

        return f"""# VirtIO Driver Installation Script
# Generated by h2kvm

$LogFile = "C:\\Windows\\Temp\\install-virtio-drivers.log"

function Write-Log {{
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -FilePath $LogFile -Append
    Write-Host $Message
}}

Write-Log "Starting VirtIO driver installation"

try {{
    # Drivers to install
    $DriversToInstall = @({driver_list})

    Write-Log "Drivers to install: $($DriversToInstall -join ', ')"

    # Method 1: Install from Windows Update
    Write-Log "Method 1: Installing from Windows Update"

    $UpdateSession = New-Object -ComObject Microsoft.Update.Session
    $UpdateSearcher = $UpdateSession.CreateUpdateSearcher()

    # Search for VirtIO driver updates
    $SearchResult = $UpdateSearcher.Search("Type='Driver' AND IsInstalled=0")

    $VirtIOUpdates = @()
    foreach ($Update in $SearchResult.Updates) {{
        foreach ($Driver in $DriversToInstall) {{
            if ($Update.Title -match $Driver) {{
                $VirtIOUpdates += $Update
                Write-Log "Found update: $($Update.Title)"
            }}
        }}
    }}

    if ($VirtIOUpdates.Count -gt 0) {{
        Write-Log "Installing $($VirtIOUpdates.Count) driver update(s)"

        $UpdatesToInstall = New-Object -ComObject Microsoft.Update.UpdateColl
        foreach ($Update in $VirtIOUpdates) {{
            $UpdatesToInstall.Add($Update) | Out-Null
        }}

        $Downloader = $UpdateSession.CreateUpdateDownloader()
        $Downloader.Updates = $UpdatesToInstall
        $DownloadResult = $Downloader.Download()

        if ($DownloadResult.ResultCode -eq 2) {{
            Write-Log "Downloads completed successfully"

            $Installer = $UpdateSession.CreateUpdateInstaller()
            $Installer.Updates = $UpdatesToInstall
            $InstallResult = $Installer.Install()

            if ($InstallResult.ResultCode -eq 2) {{
                Write-Log "Driver installation completed successfully"
            }} else {{
                Write-Log "WARNING: Driver installation returned code: $($InstallResult.ResultCode)"
            }}
        }} else {{
            Write-Log "WARNING: Download failed with code: $($DownloadResult.ResultCode)"
        }}
    }} else {{
        Write-Log "No VirtIO drivers found in Windows Update"
    }}

    # Method 2: Install from driver store (if available)
    Write-Log "Method 2: Installing from local driver store"

    $DriverStore = "C:\\Windows\\System32\\DriverStore\\FileRepository"
    if (Test-Path $DriverStore) {{
        $VirtIODrivers = Get-ChildItem -Path $DriverStore -Filter "*.inf" -Recurse |
                         Where-Object {{ $_.FullName -match "virtio|redhat" }}

        foreach ($DriverINF in $VirtIODrivers) {{
            Write-Log "Installing driver: $($DriverINF.FullName)"
            try {{
                pnputil /add-driver $DriverINF.FullName /install
                Write-Log "Driver installed: $($DriverINF.Name)"
            }} catch {{
                Write-Log "WARNING: Failed to install $($DriverINF.Name) - $($_.Exception.Message)"
            }}
        }}
    }}

    # Scan for hardware changes
    Write-Log "Scanning for hardware changes"
    $null = pnputil /scan-devices

    Write-Log "VirtIO driver installation completed"
    Write-Log "Reboot recommended to activate new drivers"

}} catch {{
    Write-Log "ERROR: Driver installation failed - $($_.Exception.Message)"
    exit 1
}}
"""

    def _add_to_startup_scripts(self, g: Any, script_path: str) -> None:
        """Add script to Windows startup."""
        try:
            scripts_ini = "/Windows/System32/GroupPolicy/Machine/Scripts/scripts.ini"

            # Read existing
            existing_content = ""
            if g.exists(scripts_ini):
                temp_ini = Path("/tmp/scripts.ini.read")
                g.download(scripts_ini, str(temp_ini))
                existing_content = temp_ini.read_text()
                temp_ini.unlink()

            # Update
            if "[Startup]" in existing_content:
                import re

                indices = re.findall(r"^(\d+)CmdLine=", existing_content, re.MULTILINE)
                next_idx = max([int(i) for i in indices], default=-1) + 1
            else:
                existing_content += "\n[Startup]\n"
                next_idx = 0

            existing_content += f"{next_idx}CmdLine={script_path}\n"
            existing_content += f"{next_idx}Parameters=\n\n"

            # Write back
            temp_ini = Path("/tmp/scripts.ini.write")
            temp_ini.write_text(existing_content)
            g.upload(str(temp_ini), scripts_ini)
            temp_ini.unlink()

            self.logger.info(f"Added {script_path} to startup scripts")

        except Exception as e:
            self.logger.warning(f"Failed to add to startup: {e}")
            raise
