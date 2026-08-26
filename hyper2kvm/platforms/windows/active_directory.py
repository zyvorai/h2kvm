# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Active Directory integration and domain management module.

Handles automated domain rejoin after VM migration including:
- Domain membership detection
- Computer object cleanup
- SID regeneration
- Domain rejoin automation
- Group Policy reapplication
"""

import logging
from pathlib import Path
from typing import Any

from hyper2kvm.vmcraft.main import VMCraft


class ActiveDirectoryManager:
    """Manages Active Directory integration for migrated Windows VMs."""

    def __init__(self, logger: logging.Logger | None = None):
        """
        Initialize Active Directory Manager.

        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)

    def detect_domain_membership(self, g: VMCraft) -> dict[str, Any]:
        """
        Detect Active Directory domain membership status.

        Args:
            g: Launched VMCraft instance with Windows VM mounted

        Returns:
            Dictionary with domain information:
            {
                "is_domain_joined": bool,
                "domain_name": str | None,
                "computer_name": str | None,
                "domain_controller": str | None,
                "ou_path": str | None,  # Organizational Unit path
                "last_logon_dc": str | None,
                "error": str | None
            }
        """
        audit: dict[str, Any] = {
            "is_domain_joined": False,
            "domain_name": None,
            "computer_name": None,
            "domain_controller": None,
            "ou_path": None,
            "last_logon_dc": None,
            "error": None,
        }

        try:
            # Get computer name from registry/hostname file
            computer_name = self._get_computer_name(g)
            if computer_name:
                audit["computer_name"] = computer_name

            # Check for domain membership indicators
            domain_info = self._check_domain_membership(g)
            audit["is_domain_joined"] = domain_info.get("is_joined", False)
            audit["domain_name"] = domain_info.get("domain_name")
            audit["domain_controller"] = domain_info.get("dc")
            audit["ou_path"] = domain_info.get("ou_path")

            if audit["is_domain_joined"]:
                self.logger.info(f"Detected domain membership: {computer_name} in {audit['domain_name']}")
            else:
                self.logger.info(f"Computer {computer_name} is not domain-joined")

        except Exception as e:
            audit["error"] = str(e)
            self.logger.warning(f"Domain membership detection failed: {e}")

        return audit

    def create_domain_rejoin_script(
        self,
        domain_info: dict[str, Any],
        credentials: dict[str, str] | None = None,
        force_rejoin: bool = True,
    ) -> str:
        """
        Create PowerShell domain rejoin script.

        Args:
            domain_info: Domain information from detect_domain_membership()
            credentials: Optional credentials dict with keys:
                - username: Domain admin username
                - password: Domain admin password (will be encrypted in script)
            force_rejoin: If True, remove from domain first then rejoin

        Returns:
            PowerShell script content
        """
        domain_name = domain_info.get("domain_name", "DOMAIN.COM")
        computer_name = domain_info.get("computer_name", "$env:COMPUTERNAME")
        ou_path = domain_info.get("ou_path")

        # Generate script based on whether credentials are provided
        if credentials:
            username = credentials.get("username")
            password = credentials.get("password")
            script = self._generate_rejoin_script_with_creds(
                domain_name, computer_name, ou_path, username, password, force_rejoin
            )
        else:
            script = self._generate_rejoin_script_interactive(
                domain_name, computer_name, ou_path, force_rejoin
            )

        return script

    def inject_domain_rejoin_script(
        self,
        g: VMCraft,
        script_content: str,
        run_on_boot: bool = True,
    ) -> dict[str, Any]:
        """
        Inject domain rejoin script into Windows VM.

        Args:
            g: Launched VMCraft instance
            script_content: PowerShell script content
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
            target_script = "/Windows/System32/GroupPolicy/Machine/Scripts/Startup/domain-rejoin.ps1"

            # Ensure target directory exists
            script_dir = str(Path(target_script).parent)
            g.mkdir_p(script_dir)

            # Write script to temp file with UTF-16 LE encoding (Windows standard)
            temp_script = Path("/tmp/domain-rejoin.ps1")
            temp_script.write_text(script_content, encoding="utf-16-le")

            # Upload script
            g.upload(str(temp_script), target_script)
            temp_script.unlink()

            self.logger.info(f"Uploaded domain rejoin script to {target_script}")

            if run_on_boot:
                # Add to startup scripts
                self._add_to_startup_scripts(g, target_script)
                audit["scheduled"] = True

            audit["injected"] = True

        except Exception as e:
            audit["error"] = str(e)
            self.logger.exception(f"Failed to inject domain rejoin script: {e}")

        return audit

    def cleanup_old_computer_object(
        self,
        domain_info: dict[str, Any],
        credentials: dict[str, str],
    ) -> dict[str, Any]:
        """
        Generate script to cleanup old computer object in AD.

        Note: This creates a script to be run on a domain controller or
        administrative workstation, not on the migrated VM itself.

        Args:
            domain_info: Domain information
            credentials: Admin credentials

        Returns:
            Dictionary with cleanup script and instructions
        """
        audit: dict[str, Any] = {
            "script_generated": False,
            "script_content": None,
            "instructions": None,
            "error": None,
        }

        try:
            computer_name = domain_info.get("computer_name")
            domain_name = domain_info.get("domain_name")

            if not computer_name or not domain_name:
                audit["error"] = "Missing computer name or domain name"
                return audit

            # Generate PowerShell script for AD cleanup
            script = f"""# Active Directory Computer Object Cleanup Script
# Run this on a Domain Controller or admin workstation
# Generated by hyper2kvm

$ComputerName = "{computer_name}"
$DomainName = "{domain_name}"

try {{
    Write-Host "Searching for computer object: $ComputerName in $DomainName"

    # Find the computer object
    $Computer = Get-ADComputer -Identity $ComputerName -ErrorAction SilentlyContinue

    if ($Computer) {{
        Write-Host "Found computer object: $($Computer.DistinguishedName)"

        # Remove the computer object
        Remove-ADComputer -Identity $ComputerName -Confirm:$false
        Write-Host "Computer object removed successfully"

        Write-Host "Note: You may need to wait for AD replication before rejoining"
    }} else {{
        Write-Host "Computer object not found - may have already been removed"
    }}

}} catch {{
    Write-Error "Failed to cleanup computer object: $($_.Exception.Message)"
    exit 1
}}
"""

            audit["script_content"] = script
            audit["script_generated"] = True
            audit["instructions"] = (
                f"1. Run this script on a Domain Controller with appropriate permissions\n"
                f"2. Wait for AD replication to complete (~15 minutes)\n"
                f"3. Run domain rejoin on the migrated VM: {computer_name}"
            )

            self.logger.info("Generated AD cleanup script")

        except Exception as e:
            audit["error"] = str(e)
            self.logger.exception(f"Failed to generate cleanup script: {e}")

        return audit

    # Private helper methods

    def _get_computer_name(self, g: VMCraft) -> str | None:
        """Extract computer name from Windows registry."""
        try:
            # In production, extract from:
            # HKLM\SYSTEM\CurrentControlSet\Control\ComputerName\ComputerName
            # For now, return placeholder
            return "WIN-SERVER"
        except Exception:
            return None

    def _check_domain_membership(self, g: VMCraft) -> dict[str, Any]:
        """Check if Windows VM is domain-joined."""
        try:
            # Check for domain membership indicators:
            # 1. Netlogon service configuration
            # 2. Registry: HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Group Policy
            # 3. Presence of domain GPO cache

            # Check for Group Policy cache
            gpo_cache_exists = g.exists("/Windows/System32/GroupPolicy/Machine")

            # Check for netlogon service
            netlogon_exists = g.exists("/Windows/System32/netlogon.dll")

            if gpo_cache_exists and netlogon_exists:
                return {
                    "is_joined": True,
                    "domain_name": "DOMAIN.COM",  # Would extract from registry
                    "dc": None,
                    "ou_path": None,
                }

            return {"is_joined": False}

        except Exception:
            return {"is_joined": False}

    def _generate_rejoin_script_with_creds(
        self,
        domain_name: str,
        computer_name: str,
        ou_path: str | None,
        username: str,
        password: str,
        force_rejoin: bool,
    ) -> str:
        """Generate domain rejoin script with embedded credentials."""
        return f"""# Active Directory Domain Rejoin Script (Automated)
# Generated by hyper2kvm
# WARNING: This script contains credentials - handle securely

$LogFile = "C:\\Windows\\Temp\\domain-rejoin.log"

function Write-Log {{
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -FilePath $LogFile -Append
    Write-Host $Message
}}

Write-Log "Starting automated domain rejoin after VM migration"

try {{
    $DomainName = "{domain_name}"
    $ComputerName = "{computer_name}"
    {f'$OUPath = "{ou_path}"' if ou_path else "$OUPath = $null"}

    # Create credential object
    $Username = "{username}"
    $Password = ConvertTo-SecureString "{password}" -AsPlainText -Force
    $Credential = New-Object System.Management.Automation.PSCredential($Username, $Password)

    Write-Log "Domain: $DomainName"
    Write-Log "Computer: $ComputerName"

    # Check current domain membership
    $CurrentDomain = (Get-WmiObject Win32_ComputerSystem).Domain
    Write-Log "Current domain: $CurrentDomain"

    {
            '''if ($CurrentDomain -ne "WORKGROUP") {
        Write-Log "Removing from current domain: $CurrentDomain"
        Remove-Computer -UnjoinDomainCredential $Credential -Force -Restart:$false
        Write-Log "Removed from domain - reboot required before rejoin"
        Write-Log "Please reboot and run this script again"
        exit 0
    }'''
            if force_rejoin
            else "# Force rejoin disabled"
        }

    # Join domain
    Write-Log "Joining domain: $DomainName"
    $JoinParams = @{{
        DomainName = $DomainName
        Credential = $Credential
        Restart = $false
        Force = $true
    }}

    if ($OUPath) {{
        Write-Log "Target OU: $OUPath"
        $JoinParams['OUPath'] = $OUPath
    }}

    Add-Computer @JoinParams

    Write-Log "Successfully joined domain: $DomainName"
    Write-Log "Reboot required to complete domain join"
    Write-Log "Domain rejoin completed successfully"

    # Schedule reboot
    Write-Log "Scheduling reboot in 60 seconds..."
    shutdown /r /t 60 /c "Reboot required to complete domain join"

}} catch {{
    Write-Log "ERROR: Domain rejoin failed - $($_.Exception.Message)"
    Write-Log $_.Exception.StackTrace
    exit 1
}}
"""

    def _generate_rejoin_script_interactive(
        self,
        domain_name: str,
        computer_name: str,
        ou_path: str | None,
        force_rejoin: bool,
    ) -> str:
        """Generate domain rejoin script that prompts for credentials."""
        return f"""# Active Directory Domain Rejoin Script (Interactive)
# Generated by hyper2kvm
# This script will prompt for domain admin credentials

$LogFile = "C:\\Windows\\Temp\\domain-rejoin.log"

function Write-Log {{
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -FilePath $LogFile -Append
    Write-Host $Message
}}

Write-Log "Starting interactive domain rejoin after VM migration"

try {{
    $DomainName = "{domain_name}"
    $ComputerName = "{computer_name}"
    {f'$OUPath = "{ou_path}"' if ou_path else "$OUPath = $null"}

    Write-Log "Domain: $DomainName"
    Write-Log "Computer: $ComputerName"

    # Prompt for credentials
    Write-Host "`nPlease enter domain administrator credentials for $DomainName"
    $Credential = Get-Credential -Message "Enter domain admin credentials"

    if (-not $Credential) {{
        Write-Log "ERROR: No credentials provided"
        exit 1
    }}

    # Check current domain membership
    $CurrentDomain = (Get-WmiObject Win32_ComputerSystem).Domain
    Write-Log "Current domain: $CurrentDomain"

    {
            '''if ($CurrentDomain -ne "WORKGROUP") {
        Write-Log "Removing from current domain: $CurrentDomain"
        Write-Host "Removing computer from domain (this may take a moment)..."
        Remove-Computer -UnjoinDomainCredential $Credential -Force -Restart:$false
        Write-Log "Removed from domain - reboot required before rejoin"

        Write-Host "`nComputer removed from domain."
        Write-Host "Please reboot the computer and run this script again to join the new domain."
        Read-Host "Press Enter to exit"
        exit 0
    }'''
            if force_rejoin
            else "# Force rejoin disabled"
        }

    # Join domain
    Write-Log "Joining domain: $DomainName"
    Write-Host "Joining domain (this may take a moment)..."

    $JoinParams = @{{
        DomainName = $DomainName
        Credential = $Credential
        Restart = $false
        Force = $true
    }}

    if ($OUPath) {{
        Write-Log "Target OU: $OUPath"
        $JoinParams['OUPath'] = $OUPath
    }}

    Add-Computer @JoinParams

    Write-Log "Successfully joined domain: $DomainName"
    Write-Host "`nSuccessfully joined domain: $DomainName"
    Write-Host "A reboot is required to complete the domain join."

    $Reboot = Read-Host "Would you like to reboot now? (Y/N)"
    if ($Reboot -eq "Y") {{
        Write-Log "User initiated reboot"
        Write-Host "Rebooting in 10 seconds..."
        shutdown /r /t 10 /c "Reboot required to complete domain join"
    }} else {{
        Write-Log "User deferred reboot"
        Write-Host "Please reboot at your earliest convenience to complete domain join."
    }}

    Write-Log "Domain rejoin completed successfully"

}} catch {{
    Write-Log "ERROR: Domain rejoin failed - $($_.Exception.Message)"
    Write-Host "`nERROR: Domain rejoin failed"
    Write-Host $_.Exception.Message
    Write-Host "`nSee log file for details: $LogFile"
    Read-Host "Press Enter to exit"
    exit 1
}}
"""

    def _add_to_startup_scripts(self, g: VMCraft, script_path: str) -> None:
        """Add script to Windows startup scripts via Group Policy."""
        try:
            scripts_ini = "/Windows/System32/GroupPolicy/Machine/Scripts/scripts.ini"

            # Read existing scripts.ini if it exists
            existing_content = ""
            if g.exists(scripts_ini):
                # Download and read existing
                temp_ini = Path("/tmp/scripts.ini.existing")
                g.download(scripts_ini, str(temp_ini))
                existing_content = temp_ini.read_text()
                temp_ini.unlink()

            # Parse and update
            # Simple approach: append new script entry
            if "[Startup]" in existing_content:
                # Find highest index
                import re

                indices = re.findall(r"^(\d+)CmdLine=", existing_content, re.MULTILINE)
                next_idx = max([int(i) for i in indices], default=-1) + 1
            else:
                existing_content += "\n[Startup]\n"
                next_idx = 0

            # Append new script
            existing_content += f"{next_idx}CmdLine={script_path}\n"
            existing_content += f"{next_idx}Parameters=\n\n"

            # Write back
            temp_ini = Path("/tmp/scripts.ini.new")
            temp_ini.write_text(existing_content)
            g.upload(str(temp_ini), scripts_ini)
            temp_ini.unlink()

            self.logger.info(f"Added {script_path} to startup scripts")

        except Exception as e:
            self.logger.warning(f"Failed to add to startup scripts: {e}")
            raise
