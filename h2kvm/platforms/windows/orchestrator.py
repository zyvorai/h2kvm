# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Windows migration orchestrator.

Coordinates Windows-specific migration tasks including:
- License detection and reactivation
- Active Directory integration
- SQL Server migration
- VirtIO driver installation
"""

import argparse
import logging
from pathlib import Path
from typing import Any


from .active_directory import ActiveDirectoryManager
from .license import WindowsLicenseManager
from .sql_server import SQLServerManager
from .windows_update import WindowsUpdateManager


class WindowsMigrationOrchestrator:
    """Orchestrates Windows-specific migration tasks."""

    def __init__(
        self,
        logger: logging.Logger,
        args: argparse.Namespace | None = None,
    ):
        """
        Initialize Windows Migration Orchestrator.

        Args:
            logger: Logger instance
            args: CLI arguments namespace (optional)
        """
        self.logger = logger
        self.args = args or argparse.Namespace()

        # Initialize managers
        self.license_mgr = WindowsLicenseManager(logger)
        self.ad_mgr = ActiveDirectoryManager(logger)
        self.sql_mgr = SQLServerManager(logger)
        self.wu_mgr = WindowsUpdateManager(logger)

    def detect_windows_configuration(self, g: Any) -> dict[str, Any]:
        """
        Detect Windows configuration including license, domain, SQL Server.

        Args:
            g: Launched VMCraft instance with Windows VM mounted

        Returns:
            Dictionary with complete Windows configuration
        """
        config: dict[str, Any] = {
            "detected": False,
            "license": {},
            "domain": {},
            "sql_server": {},
            "error": None,
        }

        try:
            self.logger.info("🔍 Detecting Windows configuration")

            # Detect license
            self.logger.info("  Detecting Windows license...")
            license_info = self.license_mgr.detect_license_type(g)
            config["license"] = license_info

            # Detect domain membership
            self.logger.info("  Detecting domain membership...")
            domain_info = self.ad_mgr.detect_domain_membership(g)
            config["domain"] = domain_info

            # Detect SQL Server
            self.logger.info("  Detecting SQL Server...")
            sql_info = self.sql_mgr.detect_sql_server(g)
            config["sql_server"] = sql_info

            config["detected"] = True

            # Log summary
            self._log_detection_summary(license_info, domain_info, sql_info)

        except Exception as e:
            config["error"] = str(e)
            self.logger.exception(f"❌ Windows configuration detection failed: {e}")

        return config

    def prepare_windows_migration(
        self,
        g: Any,
        config: dict[str, Any],
        output_dir: Path,
    ) -> dict[str, Any]:
        """
        Prepare Windows VM for migration (inject scripts, stage drivers).

        Args:
            g: Any instance
            config: Windows configuration from detect_windows_configuration()
            output_dir: Output directory for scripts and artifacts

        Returns:
            Audit dict with preparation status
        """
        audit: dict[str, Any] = {
            "prepared": False,
            "scripts_created": [],
            "scripts_injected": [],
            "drivers_staged": False,
            "error": None,
        }

        try:
            self.logger.info("🔧 Preparing Windows VM for migration")

            scripts_dir = output_dir / "windows-scripts"
            scripts_dir.mkdir(parents=True, exist_ok=True)

            # 1. License reactivation
            if config["license"].get("detected"):
                self.logger.info("  Preparing license reactivation...")
                self._prepare_license_reactivation(g, config["license"], scripts_dir, audit)

            # 2. Domain rejoin
            if config["domain"].get("is_domain_joined"):
                self.logger.info("  Preparing domain rejoin...")
                self._prepare_domain_rejoin(g, config["domain"], scripts_dir, audit)

            # 3. SQL Server migration
            if config["sql_server"].get("detected"):
                self.logger.info("  Preparing SQL Server migration...")
                self._prepare_sql_server(g, config["sql_server"], scripts_dir, audit)

            # 4. VirtIO drivers
            if getattr(self.args, "windows_virtio_drivers", True):
                self.logger.info("  Staging VirtIO drivers...")
                driver_result = self.wu_mgr.stage_virtio_drivers(g)
                audit["drivers_staged"] = driver_result.get("staged", False)

                # Create driver installation script
                driver_script = self.wu_mgr.create_driver_installation_script()
                inject_result = self.wu_mgr.inject_driver_installation_script(
                    g, driver_script, run_on_boot=True
                )

                if inject_result.get("injected"):
                    audit["scripts_injected"].append("virtio-drivers")

            audit["prepared"] = True
            self.logger.info("✅ Windows VM preparation completed")

        except Exception as e:
            audit["error"] = str(e)
            self.logger.exception(f"❌ Windows VM preparation failed: {e}")

        return audit

    def generate_post_migration_guide(
        self,
        config: dict[str, Any],
        output_path: Path,
    ) -> None:
        """
        Generate post-migration guide for manual steps.

        Args:
            config: Windows configuration
            output_path: Path to save guide
        """
        try:
            guide_content = self._generate_guide_content(config)

            output_path.write_text(guide_content, encoding="utf-8")

            self.logger.info(f"📄 Post-migration guide created: {output_path}")

        except Exception as e:
            self.logger.warning(f"Failed to create post-migration guide: {e}")

    # Private helper methods

    def _prepare_license_reactivation(
        self,
        g: Any,
        license_info: dict[str, Any],
        scripts_dir: Path,
        audit: dict[str, Any],
    ) -> None:
        """Prepare license reactivation scripts."""
        try:
            # Get license configuration from args
            product_key = getattr(self.args, "windows_product_key", None)
            kms_server = getattr(self.args, "windows_kms_server", None)
            kms_port = getattr(self.args, "windows_kms_port", None)

            # Create reactivation script
            script_path = scripts_dir / "reactivate-license.ps1"
            result = self.license_mgr.create_reactivation_script(
                license_info,
                str(script_path),
                product_key=product_key,
                kms_server=kms_server,
                kms_port=kms_port,
            )

            if result.get("created"):
                audit["scripts_created"].append(str(script_path))

                # Inject script into VM
                inject_result = self.license_mgr.inject_reactivation_script(
                    g, str(script_path), run_on_boot=True
                )

                if inject_result.get("injected"):
                    audit["scripts_injected"].append("license-reactivation")

        except Exception as e:
            self.logger.warning(f"License reactivation preparation failed: {e}")

    def _prepare_domain_rejoin(
        self,
        g: Any,
        domain_info: dict[str, Any],
        scripts_dir: Path,
        audit: dict[str, Any],
    ) -> None:
        """Prepare domain rejoin scripts."""
        try:
            # Get credentials from args (if provided)
            credentials = None
            if hasattr(self.args, "ad_username") and hasattr(self.args, "ad_password"):
                credentials = {
                    "username": self.args.ad_username,
                    "password": self.args.ad_password,
                }

            # Create rejoin script
            script_content = self.ad_mgr.create_domain_rejoin_script(domain_info, credentials=credentials)

            # Save script
            script_path = scripts_dir / "domain-rejoin.ps1"
            script_path.write_text(script_content, encoding="utf-8")
            audit["scripts_created"].append(str(script_path))

            # Inject script
            inject_result = self.ad_mgr.inject_domain_rejoin_script(g, script_content, run_on_boot=True)

            if inject_result.get("injected"):
                audit["scripts_injected"].append("domain-rejoin")

            # Generate AD cleanup script (for admin use)
            if credentials:
                cleanup_result = self.ad_mgr.cleanup_old_computer_object(domain_info, credentials)

                if cleanup_result.get("script_generated"):
                    cleanup_path = scripts_dir / "ad-cleanup.ps1"
                    cleanup_path.write_text(cleanup_result["script_content"], encoding="utf-8")
                    audit["scripts_created"].append(str(cleanup_path))

                    # Save instructions
                    instructions_path = scripts_dir / "ad-cleanup-instructions.txt"
                    instructions_path.write_text(cleanup_result["instructions"], encoding="utf-8")

        except Exception as e:
            self.logger.warning(f"Domain rejoin preparation failed: {e}")

    def _prepare_sql_server(
        self,
        g: Any,
        sql_info: dict[str, Any],
        scripts_dir: Path,
        audit: dict[str, Any],
    ) -> None:
        """Prepare SQL Server migration scripts."""
        try:
            # Get target details from args
            target_ip = getattr(self.args, "target_ip", None)
            target_hostname = getattr(self.args, "target_hostname", None)

            # Create migration script
            result = self.sql_mgr.migrate_sql_configuration(g, sql_info, target_ip, target_hostname)

            if result.get("script_generated"):
                audit["scripts_injected"].append("sql-server-migration")

            # Create validation script
            validation_result = self.sql_mgr.validate_databases(g, sql_info)

            if validation_result.get("script_generated"):
                audit["scripts_injected"].append("sql-validation")

        except Exception as e:
            self.logger.warning(f"SQL Server preparation failed: {e}")

    def _log_detection_summary(
        self,
        license_info: dict[str, Any],
        domain_info: dict[str, Any],
        sql_info: dict[str, Any],
    ) -> None:
        """Log Windows configuration detection summary."""
        self.logger.info("")
        self.logger.info("📊 Windows Configuration Summary:")

        # License
        if license_info.get("detected"):
            self.logger.info(
                f"  License: {license_info.get('license_type')} ({license_info.get('product_name')})"
            )
            self.logger.info(f"  Activation: {license_info.get('activation_status')}")
        else:
            self.logger.info("  License: Not detected")

        # Domain
        if domain_info.get("is_domain_joined"):
            self.logger.info(
                f"  Domain: {domain_info.get('computer_name')} in {domain_info.get('domain_name')}"
            )
        else:
            self.logger.info("  Domain: Workgroup (not domain-joined)")

        # SQL Server
        if sql_info.get("detected"):
            instances = sql_info.get("instances", [])
            databases = sql_info.get("databases", [])
            self.logger.info(f"  SQL Server: {len(instances)} instance(s), {len(databases)} database(s)")
            for inst in instances:
                self.logger.info(f"    - {inst['name']}: {inst['version']}")
        else:
            self.logger.info("  SQL Server: Not detected")

        self.logger.info("")

    def _generate_guide_content(self, config: dict[str, Any]) -> str:
        """Generate post-migration guide content."""
        guide = """# Windows VM Post-Migration Guide
Generated by h2kvm

## Overview
This guide contains manual steps required after migrating your Windows VM to KVM.

## Automated Tasks
The following tasks have been automated and will run on first boot:
"""

        # Add automated tasks based on configuration
        if config.get("license", {}).get("detected"):
            guide += "\n✅ **Windows License Reactivation**\n"
            guide += "   - Script will run on first boot\n"
            guide += f"   - License type: {config['license'].get('license_type')}\n"

        if config.get("domain", {}).get("is_domain_joined"):
            guide += "\n✅ **Active Directory Domain Rejoin**\n"
            guide += "   - Script will prompt for domain admin credentials on first boot\n"
            guide += f"   - Domain: {config['domain'].get('domain_name')}\n"

        if config.get("sql_server", {}).get("detected"):
            guide += "\n✅ **SQL Server Configuration**\n"
            guide += "   - Script will update SQL Server settings on first boot\n"
            instances = config["sql_server"].get("instances", [])
            guide += f"   - Instances: {len(instances)}\n"

        guide += "\n✅ **VirtIO Drivers Installation**\n"
        guide += "   - Drivers will be installed automatically on first boot\n"

        # Add manual steps
        guide += """

## Manual Steps Required

### 1. First Boot
- Boot the VM in KVM/QEMU environment
- Log in with administrator credentials
- Check startup script execution logs:
  - License: `C:\\Windows\\System32\\GroupPolicy\\Machine\\Scripts\\Startup\\reactivate-license.log`
  - Domain: `C:\\Windows\\Temp\\domain-rejoin.log`
  - SQL Server: `C:\\Windows\\Temp\\sql-migration.log`
  - VirtIO Drivers: `C:\\Windows\\Temp\\install-virtio-drivers.log`

### 2. Verify License Activation
```powershell
# Check activation status
slmgr /dli

# If not activated, manually activate
slmgr /ato
```

### 3. Verify Domain Membership (if applicable)
```powershell
# Check domain membership
$env:USERDOMAIN

# Verify Group Policy refresh
gpupdate /force
```

### 4. Verify SQL Server (if applicable)
```powershell
# Check SQL Server services
Get-Service MSSQL* | Select Name, Status, StartType

# Connect to SQL Server
sqlcmd -S localhost -E -Q "SELECT @@VERSION"
```

### 5. Update Application Connection Strings
- Update any hardcoded IP addresses or hostnames in applications
- Update linked servers in SQL Server
- Reconfigure scheduled tasks that reference network paths

### 6. Network Configuration
- Verify network connectivity
- Update DNS settings if required
- Configure firewall rules

### 7. Final Validation
- Reboot the VM
- Verify all services start correctly
- Test application functionality

## Support Scripts
Additional scripts have been created in the output directory:
- `ad-cleanup.ps1` - Run on domain controller to cleanup old computer object
- `sql-validation.ps1` - Validate SQL Server databases

## Troubleshooting

### License Activation Fails
- Verify network connectivity to KMS server (if KMS-based)
- Check firewall allows outbound connection on port 1688
- For MAK/Retail, may require phone activation if too many hardware changes

### Domain Rejoin Fails
- Ensure old computer object is removed from AD
- Verify DNS resolution for domain controllers
- Check domain controller is reachable
- Wait 15-30 minutes for AD replication

### SQL Server Connection Issues
- Verify SQL Server services are running
- Check TCP/IP protocol is enabled
- Verify firewall allows SQL Server port (default 1433)
- Test local connectivity first: `sqlcmd -S localhost -E`

## Additional Resources
- h2kvm documentation: https://github.com/ssahani/h2kvm
- Windows activation troubleshooting: https://docs.microsoft.com/en-us/windows-server/get-started/activation-troubleshooting
- SQL Server migration guide: https://docs.microsoft.com/en-us/sql/database-engine/install-windows/migrate-sql-server

---
Generated: {timestamp}
"""
        import datetime

        return guide.replace("{timestamp}", datetime.datetime.now().isoformat())
