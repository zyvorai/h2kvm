# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Windows license detection and reactivation module.

Handles automated Windows license reactivation after VM migration including:
- License type detection (KMS, MAK, OEM, Retail)
- Product key extraction (when possible)
- Reactivation script generation
- Post-migration license validation
"""

import logging
import re
from pathlib import Path
from typing import Any



class WindowsLicenseManager:
    """Manages Windows license detection and reactivation for migrated VMs."""

    # Common Windows product key patterns
    PRODUCT_KEY_PATTERN = re.compile(r"[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}")

    # KMS servers common ports
    KMS_DEFAULT_PORT = 1688

    # License types
    LICENSE_TYPE_RETAIL = "Retail"
    LICENSE_TYPE_OEM = "OEM"
    LICENSE_TYPE_VOLUME_MAK = "Volume:MAK"
    LICENSE_TYPE_VOLUME_KMS = "Volume:KMS"
    LICENSE_TYPE_UNKNOWN = "Unknown"

    def __init__(self, logger: logging.Logger | None = None):
        """
        Initialize Windows License Manager.

        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)

    def detect_license_type(self, g: Any) -> dict[str, Any]:
        """
        Detect Windows license type and configuration.

        Args:
            g: Launched VMCraft instance with Windows VM mounted

        Returns:
            Dictionary with license information:
            {
                "detected": bool,
                "license_type": str,  # "Retail", "OEM", "Volume:MAK", "Volume:KMS"
                "product_name": str,
                "product_key_partial": str,  # Last 5 chars
                "kms_server": str | None,
                "kms_port": int | None,
                "activation_status": str,  # "Licensed", "Unlicensed", "Unknown"
                "grace_period_days": int | None,
                "error": str | None
            }
        """
        audit: dict[str, Any] = {
            "detected": False,
            "license_type": self.LICENSE_TYPE_UNKNOWN,
            "product_name": None,
            "product_key_partial": None,
            "kms_server": None,
            "kms_port": None,
            "activation_status": "Unknown",
            "grace_period_days": None,
            "error": None,
        }

        try:
            # Check if Windows registry is accessible
            if not self._is_windows_vm(g):
                audit["error"] = "Not a Windows VM or registry not accessible"
                return audit

            # Detect product name
            product_name = self._get_product_name(g)
            if product_name:
                audit["product_name"] = product_name

            # Detect license type from registry
            license_type = self._detect_license_type_from_registry(g)
            audit["license_type"] = license_type

            # Get partial product key (last 5 characters)
            partial_key = self._get_partial_product_key(g)
            if partial_key:
                audit["product_key_partial"] = partial_key

            # For KMS licenses, detect KMS server
            if license_type == self.LICENSE_TYPE_VOLUME_KMS:
                kms_info = self._get_kms_server_info(g)
                audit["kms_server"] = kms_info.get("server")
                audit["kms_port"] = kms_info.get("port", self.KMS_DEFAULT_PORT)

            # Get activation status
            activation_info = self._get_activation_status(g)
            audit["activation_status"] = activation_info.get("status", "Unknown")
            audit["grace_period_days"] = activation_info.get("grace_days")

            audit["detected"] = True
            self.logger.info(f"Detected Windows license: {license_type} ({product_name})")

        except Exception as e:
            audit["error"] = str(e)
            self.logger.warning(f"License detection failed: {e}")

        return audit

    def create_reactivation_script(
        self,
        license_info: dict[str, Any],
        output_path: str,
        product_key: str | None = None,
        kms_server: str | None = None,
        kms_port: int | None = None,
    ) -> dict[str, Any]:
        """
        Create PowerShell reactivation script.

        Args:
            license_info: License information from detect_license_type()
            output_path: Path where script will be saved
            product_key: Optional product key (for MAK/Retail)
            kms_server: Optional KMS server (for KMS activation)
            kms_port: Optional KMS port (default 1688)

        Returns:
            Audit dict with script creation status
        """
        audit: dict[str, Any] = {
            "created": False,
            "script_path": output_path,
            "license_type": license_info.get("license_type"),
            "error": None,
        }

        try:
            license_type = license_info.get("license_type", self.LICENSE_TYPE_UNKNOWN)

            if license_type == self.LICENSE_TYPE_VOLUME_KMS:
                script = self._generate_kms_reactivation_script(
                    kms_server or license_info.get("kms_server"),
                    kms_port or license_info.get("kms_port", self.KMS_DEFAULT_PORT),
                )
            elif license_type == self.LICENSE_TYPE_VOLUME_MAK:
                script = self._generate_mak_reactivation_script(product_key)
            elif license_type == self.LICENSE_TYPE_OEM:
                script = self._generate_oem_reactivation_script()
            elif license_type == self.LICENSE_TYPE_RETAIL:
                script = self._generate_retail_reactivation_script(product_key)
            else:
                audit["error"] = f"Unknown license type: {license_type}"
                return audit

            # Write script to file
            Path(output_path).write_text(script, encoding="utf-16-le")
            audit["created"] = True
            self.logger.info(f"Created reactivation script: {output_path}")

        except Exception as e:
            audit["error"] = str(e)
            self.logger.exception(f"Failed to create reactivation script: {e}")

        return audit

    def inject_reactivation_script(
        self,
        g: Any,
        script_path: str,
        run_on_boot: bool = True,
    ) -> dict[str, Any]:
        """
        Inject reactivation script into Windows VM.

        Args:
            g: Launched VMCraft instance
            script_path: Path to reactivation script on host
            run_on_boot: If True, configure script to run on first boot

        Returns:
            Audit dict with injection status
        """
        audit: dict[str, Any] = {
            "injected": False,
            "scheduled": run_on_boot,
            "error": None,
        }

        try:
            # Target paths in Windows VM
            target_script = "/Windows/System32/GroupPolicy/Machine/Scripts/Startup/reactivate-license.ps1"
            target_log = "/Windows/System32/GroupPolicy/Machine/Scripts/Startup/reactivate-license.log"

            # Ensure target directory exists
            script_dir = str(Path(target_script).parent)
            g.mkdir_p(script_dir)

            # Upload reactivation script
            g.upload(script_path, target_script)
            self.logger.info(f"Uploaded reactivation script to {target_script}")

            if run_on_boot:
                # Create scheduled task to run on boot
                self._create_startup_task(g, target_script, target_log)
                audit["scheduled"] = True

            audit["injected"] = True

        except Exception as e:
            audit["error"] = str(e)
            self.logger.exception(f"Failed to inject reactivation script: {e}")

        return audit

    # Private helper methods

    def _is_windows_vm(self, g: Any) -> bool:
        """Check if VM is Windows by checking for registry."""
        try:
            # Check for Windows registry hives
            return g.exists("/Windows/System32/config/SOFTWARE")
        except Exception:
            return False

    def _get_product_name(self, g: Any) -> str | None:
        """Extract Windows product name from registry."""
        try:
            # Try to read ProductName from SOFTWARE hive
            # This would require registry parsing - for now return placeholder
            # In production, use hivex or reg commands
            return "Windows Server" if g.exists("/Windows/System32/ServerManager.exe") else "Windows"
        except Exception:
            return None

    def _detect_license_type_from_registry(self, g: Any) -> str:
        """Detect license type from Windows registry."""
        try:
            # Check for KMS indicators
            if g.exists("/Windows/System32/slmgr.vbs"):
                # Check for KMS client setup key presence
                # This is a simplified check - production would parse registry
                if g.exists("/Windows/ServiceProfiles"):
                    return self.LICENSE_TYPE_VOLUME_KMS

            # Check for OEM indicators
            if g.exists("/Windows/System32/oem"):
                return self.LICENSE_TYPE_OEM

            # Default to unknown
            return self.LICENSE_TYPE_UNKNOWN

        except Exception:
            return self.LICENSE_TYPE_UNKNOWN

    def _get_partial_product_key(self, g: Any) -> str | None:
        """Get last 5 characters of product key."""
        try:
            # In production, extract from SOFTWARE registry hive
            # For now, return placeholder
            return "XXXXX"
        except Exception:
            return None

    def _get_kms_server_info(self, g: Any) -> dict[str, Any]:
        """Get KMS server configuration."""
        try:
            # In production, parse from registry:
            # HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\SoftwareProtectionPlatform\KeyManagementServiceName
            # HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\SoftwareProtectionPlatform\KeyManagementServicePort
            return {
                "server": None,
                "port": self.KMS_DEFAULT_PORT,
            }
        except Exception:
            return {}

    def _get_activation_status(self, g: Any) -> dict[str, Any]:
        """Get Windows activation status."""
        try:
            # In production, run: slmgr /dli or check registry
            # For now, return unknown
            return {
                "status": "Unknown",
                "grace_days": None,
            }
        except Exception:
            return {}

    def _generate_kms_reactivation_script(
        self,
        kms_server: str | None,
        kms_port: int = 1688,
    ) -> str:
        """Generate KMS reactivation PowerShell script."""
        return f"""# Windows KMS Reactivation Script
# Generated by h2kvm

$LogFile = "C:\\Windows\\System32\\GroupPolicy\\Machine\\Scripts\\Startup\\reactivate-license.log"

function Write-Log {{
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -FilePath $LogFile -Append
}}

Write-Log "Starting KMS license reactivation after VM migration"

try {{
    # Configure KMS server
    {f'$KmsServer = "{kms_server}"' if kms_server else "# KMS server not configured"}
    $KmsPort = {kms_port}

    if ($KmsServer) {{
        Write-Log "Configuring KMS server: $KmsServer:$KmsPort"
        cscript //B //NoLogo C:\\Windows\\System32\\slmgr.vbs /skms "$($KmsServer):$KmsPort"
        if ($LASTEXITCODE -eq 0) {{
            Write-Log "KMS server configured successfully"
        }} else {{
            Write-Log "ERROR: Failed to configure KMS server (exit code: $LASTEXITCODE)"
        }}
    }}

    # Clear activation cache
    Write-Log "Clearing activation cache"
    cscript //B //NoLogo C:\\Windows\\System32\\slmgr.vbs /ckms

    # Activate Windows
    Write-Log "Activating Windows"
    cscript //B //NoLogo C:\\Windows\\System32\\slmgr.vbs /ato
    if ($LASTEXITCODE -eq 0) {{
        Write-Log "Windows activated successfully"
    }} else {{
        Write-Log "WARNING: Activation returned exit code: $LASTEXITCODE"
    }}

    # Get activation status
    Write-Log "Checking activation status"
    $Status = cscript //NoLogo C:\\Windows\\System32\\slmgr.vbs /dli
    Write-Log "Activation status: $Status"

    Write-Log "KMS reactivation completed"

}} catch {{
    Write-Log "ERROR: Reactivation failed - $($_.Exception.Message)"
    exit 1
}}
"""

    def _generate_mak_reactivation_script(self, product_key: str | None) -> str:
        """Generate MAK reactivation PowerShell script."""
        return f"""# Windows MAK Reactivation Script
# Generated by h2kvm

$LogFile = "C:\\Windows\\System32\\GroupPolicy\\Machine\\Scripts\\Startup\\reactivate-license.log"

function Write-Log {{
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -FilePath $LogFile -Append
}}

Write-Log "Starting MAK license reactivation after VM migration"

try {{
    {f'$ProductKey = "{product_key}"' if product_key else "# Product key not provided - using existing key"}

    if ($ProductKey) {{
        Write-Log "Installing product key"
        cscript //B //NoLogo C:\\Windows\\System32\\slmgr.vbs /ipk $ProductKey
        if ($LASTEXITCODE -eq 0) {{
            Write-Log "Product key installed successfully"
        }} else {{
            Write-Log "ERROR: Failed to install product key (exit code: $LASTEXITCODE)"
        }}
    }}

    # Activate Windows
    Write-Log "Activating Windows with MAK"
    cscript //B //NoLogo C:\\Windows\\System32\\slmgr.vbs /ato
    if ($LASTEXITCODE -eq 0) {{
        Write-Log "Windows activated successfully"
    }} else {{
        Write-Log "WARNING: Activation returned exit code: $LASTEXITCODE"
    }}

    # Get activation status
    Write-Log "Checking activation status"
    $Status = cscript //NoLogo C:\\Windows\\System32\\slmgr.vbs /dli
    Write-Log "Activation status: $Status"

    Write-Log "MAK reactivation completed"

}} catch {{
    Write-Log "ERROR: Reactivation failed - $($_.Exception.Message)"
    exit 1
}}
"""

    def _generate_oem_reactivation_script(self) -> str:
        """Generate OEM reactivation PowerShell script."""
        return """# Windows OEM Reactivation Script
# Generated by h2kvm

$LogFile = "C:\\Windows\\System32\\GroupPolicy\\Machine\\Scripts\\Startup\\reactivate-license.log"

function Write-Log {
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -FilePath $LogFile -Append
}

Write-Log "Starting OEM license reactivation after VM migration"

try {
    # OEM licenses typically auto-activate from BIOS/UEFI
    # Attempt reactivation
    Write-Log "Attempting OEM reactivation"
    cscript //B //NoLogo C:\\Windows\\System32\\slmgr.vbs /ato
    if ($LASTEXITCODE -eq 0) {
        Write-Log "Windows activated successfully"
    } else {
        Write-Log "WARNING: Automatic activation failed (exit code: $LASTEXITCODE)"
        Write-Log "OEM licenses may require manual reactivation or BIOS key injection"
    }

    # Get activation status
    Write-Log "Checking activation status"
    $Status = cscript //NoLogo C:\\Windows\\System32\\slmgr.vbs /dli
    Write-Log "Activation status: $Status"

    Write-Log "OEM reactivation attempt completed"

} catch {
    Write-Log "ERROR: Reactivation failed - $($_.Exception.Message)"
    exit 1
}
"""

    def _generate_retail_reactivation_script(self, product_key: str | None) -> str:
        """Generate Retail reactivation PowerShell script."""
        return f"""# Windows Retail Reactivation Script
# Generated by h2kvm

$LogFile = "C:\\Windows\\System32\\GroupPolicy\\Machine\\Scripts\\Startup\\reactivate-license.log"

function Write-Log {{
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -FilePath $LogFile -Append
}}

Write-Log "Starting Retail license reactivation after VM migration"

try {{
    {f'$ProductKey = "{product_key}"' if product_key else "# Product key not provided - using existing key"}

    if ($ProductKey) {{
        Write-Log "Installing product key"
        cscript //B //NoLogo C:\\Windows\\System32\\slmgr.vbs /ipk $ProductKey
        if ($LASTEXITCODE -eq 0) {{
            Write-Log "Product key installed successfully"
        }} else {{
            Write-Log "ERROR: Failed to install product key (exit code: $LASTEXITCODE)"
        }}
    }}

    # Activate Windows
    Write-Log "Activating Windows"
    cscript //B //NoLogo C:\\Windows\\System32\\slmgr.vbs /ato
    if ($LASTEXITCODE -eq 0) {{
        Write-Log "Windows activated successfully"
    }} else {{
        Write-Log "WARNING: Activation returned exit code: $LASTEXITCODE"
        Write-Log "Retail licenses may require phone activation after hardware changes"
    }}

    # Get activation status
    Write-Log "Checking activation status"
    $Status = cscript //NoLogo C:\\Windows\\System32\\slmgr.vbs /dli
    Write-Log "Activation status: $Status"

    Write-Log "Retail reactivation completed"

}} catch {{
    Write-Log "ERROR: Reactivation failed - $($_.Exception.Message)"
    exit 1
}}
"""

    def _create_startup_task(self, g: Any, script_path: str, log_path: str) -> None:
        """Create Windows startup task to run reactivation script."""
        try:
            # Create GPO startup script configuration
            # In production, this would modify:
            # C:\Windows\System32\GroupPolicy\Machine\Scripts\scripts.ini

            scripts_ini = "/Windows/System32/GroupPolicy/Machine/Scripts/scripts.ini"

            # Create scripts.ini content
            ini_content = f"""[Startup]
0CmdLine={script_path}
0Parameters=

"""

            # Write scripts.ini using VMCraft
            temp_ini = Path("/tmp/scripts.ini")
            temp_ini.write_text(ini_content)
            g.upload(str(temp_ini), scripts_ini)
            temp_ini.unlink()

            self.logger.info("Configured startup script in Group Policy")

        except Exception as e:
            self.logger.warning(f"Failed to create startup task: {e}")
            raise
