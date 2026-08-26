# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Analysis Operations.

Provides comprehensive analysis and detection methods for VMCraft via composition.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


class AnalyzerOps:  # pylint: disable=too-many-public-methods,protected-access
    """
    Analysis operations via composition.

    This is a thin delegation facade: every method forwards to a manager
    attribute on ``_host`` (the composed VMCraft instance) via
    ``_host._dispatch_manager_attr_call``. `_host` is part of the same
    object graph as this component, so the protected-access is intentional
    tight internal coupling rather than reaching into an unrelated class.
    The large method count mirrors the many independent analyzer managers
    VMCraft composes (network, firewall, filesystem, etc.).
    """

    def __init__(self, host) -> None:
        self._host = host

    # Network Configuration Analysis

    def analyze_network_config(self, os_type: str) -> dict[str, Any]:
        """Analyze network configuration based on OS type."""
        return self._host._dispatch_manager_attr_call("_network_config", "analyze_network_config", os_type)

    def find_static_ips(self, config: dict[str, Any]) -> list[str]:
        """Find statically configured IP addresses."""
        return self._host._dispatch_manager_attr_call("_network_config", "find_static_ips", config)

    def detect_network_bonds(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        """Detect network bonding/teaming configurations."""
        return self._host._dispatch_manager_attr_call("_network_config", "detect_network_bonds", config)

    # Firewall Analysis

    def analyze_firewall(self, os_type: str) -> dict[str, Any]:
        """Analyze firewall configuration based on OS type."""
        return self._host._dispatch_manager_attr_call("_firewall_analyzer", "analyze_firewall", os_type)

    def get_open_ports(self, config: dict[str, Any]) -> list[int]:
        """Extract list of open ports from firewall configuration."""
        return self._host._dispatch_manager_attr_call("_firewall_analyzer", "get_open_ports", config)

    def get_blocked_ports(self, config: dict[str, Any]) -> list[int]:
        """Extract list of blocked ports from firewall configuration."""
        return self._host._dispatch_manager_attr_call("_firewall_analyzer", "get_blocked_ports", config)

    def get_firewall_stats(self, config: dict[str, Any]) -> dict[str, Any]:
        """Get firewall statistics."""
        return self._host._dispatch_manager_attr_call("_firewall_analyzer", "get_firewall_stats", config)

    # Advanced Filesystem Analysis

    def search_files(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # flexible multi-criteria file search API
        self,
        path: str = "/",
        name_pattern: str | None = None,
        content_pattern: str | None = None,
        min_size_mb: float | None = None,
        max_size_mb: float | None = None,
        file_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Multi-criteria file search with flexible filters."""
        return self._host._dispatch_manager_attr_call(
            "_advanced_analyzer",
            "search_files",
            path=path,
            name_pattern=name_pattern,
            content_pattern=content_pattern,
            min_size_mb=min_size_mb,
            max_size_mb=max_size_mb,
            file_type=file_type,
            limit=limit,
        )

    def find_large_files(
        self, path: str = "/", min_size_mb: float = 100, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Find large files above a size threshold."""
        return self._host._dispatch_manager_attr_call(
            "_advanced_analyzer",
            "find_large_files",
            path=path,
            min_size_mb=min_size_mb,
            limit=limit,
        )

    def find_duplicates(
        self, path: str = "/", min_size_mb: float = 1, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Find duplicate files using SHA256 checksums."""
        return self._host._dispatch_manager_attr_call(
            "_advanced_analyzer",
            "find_duplicates",
            path=path,
            min_size_mb=min_size_mb,
            limit=limit,
        )

    def analyze_disk_space(self, path: str = "/", top_n: int = 20) -> dict[str, Any]:
        """Analyze disk space usage by directory."""
        return self._host._dispatch_manager_attr_call(
            "_advanced_analyzer",
            "analyze_disk_space",
            path=path,
            top_n=top_n,
        )

    def find_certificates(self, path: str = "/") -> list[dict[str, Any]]:
        """Find SSL/TLS certificate files."""
        return self._host._dispatch_manager_attr_call("_advanced_analyzer", "find_certificates", path=path)

    # Export and Reporting

    def export_json(self, data: dict[str, Any], output_path: str | Path) -> bool:
        """Export data to JSON format."""
        return self._host._dispatch_manager_attr_call("_export_mgr", "export_json", data, output_path)

    def export_yaml(self, data: dict[str, Any], output_path: str | Path) -> bool:
        """Export data to YAML format."""
        return self._host._dispatch_manager_attr_call("_export_mgr", "export_yaml", data, output_path)

    def export_markdown_report(
        self, data: dict[str, Any], output_path: str | Path, title: str = "VM Analysis Report"
    ) -> bool:
        """Generate Markdown report from analysis data."""
        return self._host._dispatch_manager_attr_call(
            "_export_mgr", "export_markdown_report", data, output_path, title
        )

    def create_vm_profile(
        self,
        os_info: dict[str, Any] | None = None,
        containers: dict[str, Any] | None = None,
        security: dict[str, Any] | None = None,
        packages: dict[str, Any] | None = None,
        performance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create comprehensive VM profile for analysis and comparison."""
        return self._host._dispatch_manager_attr_call(
            "_export_mgr",
            "create_vm_profile",
            os_info=os_info,
            containers=containers,
            security=security,
            packages=packages,
            performance=performance,
        )

    def compare_vms(self, vm1_profile: dict[str, Any], vm2_profile: dict[str, Any]) -> dict[str, Any]:
        """Compare two VM profiles and generate diff report."""
        return self._host._dispatch_manager_attr_call("_export_mgr", "compare_vms", vm1_profile, vm2_profile)

    # Scheduled Task Analysis

    def analyze_scheduled_tasks(self, os_type: str) -> dict[str, Any]:
        """Analyze scheduled tasks based on OS type (cron, systemd timers, Windows Task Scheduler)."""
        return self._host._dispatch_manager_attr_call("_scheduled_tasks", "analyze_scheduled_tasks", os_type)

    def get_task_count(self, config: dict[str, Any]) -> int:
        """Get total count of scheduled tasks."""
        return self._host._dispatch_manager_attr_call("_scheduled_tasks", "get_task_count", config)

    def find_daily_tasks(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        """Find tasks that run daily."""
        return self._host._dispatch_manager_attr_call("_scheduled_tasks", "find_daily_tasks", config)

    def find_tasks_by_user(self, config: dict[str, Any], user: str) -> list[dict[str, Any]]:
        """Find tasks scheduled for a specific user."""
        return self._host._dispatch_manager_attr_call("_scheduled_tasks", "find_tasks_by_user", config, user)

    # SSH Configuration Analysis

    def analyze_ssh_config(self) -> dict[str, Any]:
        """Analyze SSH server and client configuration."""
        return self._host._dispatch_manager_attr_call("_ssh_analyzer", "analyze_ssh_config")

    def get_ssh_port(self, config: dict[str, Any]) -> int:
        """Get SSH server port."""
        return self._host._dispatch_manager_attr_call("_ssh_analyzer", "get_ssh_port", config)

    def is_root_login_allowed(self, config: dict[str, Any]) -> bool:
        """Check if root login is allowed via SSH."""
        return self._host._dispatch_manager_attr_call("_ssh_analyzer", "is_root_login_allowed", config)

    def is_password_auth_enabled(self, config: dict[str, Any]) -> bool:
        """Check if password authentication is enabled for SSH."""
        return self._host._dispatch_manager_attr_call("_ssh_analyzer", "is_password_auth_enabled", config)

    def get_authorized_key_count(self, config: dict[str, Any]) -> int:
        """Get total count of authorized SSH keys."""
        return self._host._dispatch_manager_attr_call("_ssh_analyzer", "get_authorized_key_count", config)

    def get_security_score(self, config: dict[str, Any]) -> dict[str, Any]:
        """Calculate SSH security score."""
        return self._host._dispatch_manager_attr_call("_ssh_analyzer", "get_security_score", config)

    # Log Analysis

    def analyze_logs(self) -> dict[str, Any]:
        """Analyze system logs comprehensively."""
        return self._host._dispatch_manager_attr_call("_log_analyzer", "analyze_logs")

    def get_recent_errors(self, hours: int = 24, limit: int = 20) -> list[dict[str, Any]]:
        """Get errors from the last N hours."""
        return self._host._dispatch_manager_attr_call(
            "_log_analyzer", "get_recent_errors", hours=hours, limit=limit
        )

    def get_critical_events(self) -> list[dict[str, Any]]:
        """Get critical events (kernel panics, OOM, crashes)."""
        return self._host._dispatch_manager_attr_call("_log_analyzer", "get_critical_events")

    # Hardware Detection

    def detect_hardware(self) -> dict[str, Any]:
        """Detect hardware configuration comprehensively."""
        return self._host._dispatch_manager_attr_call("_hardware_detector", "detect_hardware")

    def is_virtual_machine(self, hardware: dict[str, Any]) -> bool:
        """Check if the system is a virtual machine."""
        return self._host._dispatch_manager_attr_call("_hardware_detector", "is_virtual_machine", hardware)

    def get_hypervisor(self, hardware: dict[str, Any]) -> str | None:
        """Get the hypervisor type."""
        return self._host._dispatch_manager_attr_call("_hardware_detector", "get_hypervisor", hardware)

    def get_total_memory_mb(self, hardware: dict[str, Any]) -> float | None:
        """Get total memory in MB."""
        return self._host._dispatch_manager_attr_call("_hardware_detector", "get_total_memory_mb", hardware)

    def get_disk_count(self, hardware: dict[str, Any]) -> int:
        """Get number of disk devices."""
        return self._host._dispatch_manager_attr_call("_hardware_detector", "get_disk_count", hardware)

    def get_network_interface_count(self, hardware: dict[str, Any]) -> int:
        """Get number of network interfaces."""
        return self._host._dispatch_manager_attr_call(
            "_hardware_detector", "get_network_interface_count", hardware
        )

    def get_hardware_summary(self, hardware: dict[str, Any]) -> dict[str, Any]:
        """Get hardware summary."""
        return self._host._dispatch_manager_attr_call("_hardware_detector", "get_hardware_summary", hardware)

    # Database Detection

    def detect_databases(self) -> dict[str, Any]:
        """Detect all database installations."""
        return self._host._dispatch_manager_attr_call("_database_detector", "detect_databases")

    def get_database_summary(self, databases: dict[str, Any]) -> dict[str, Any]:
        """Get database summary."""
        return self._host._dispatch_manager_attr_call(
            "_database_detector", "get_database_summary", databases
        )

    def check_database_security(self, databases: dict[str, Any]) -> list[dict[str, Any]]:
        """Check database security settings."""
        return self._host._dispatch_manager_attr_call(
            "_database_detector", "check_database_security", databases
        )

    # Web Server Analysis

    def detect_webservers(self) -> dict[str, Any]:
        """Detect all web server installations."""
        return self._host._dispatch_manager_attr_call("_webserver_analyzer", "detect_webservers")

    def get_webserver_summary(self, webservers: dict[str, Any]) -> dict[str, Any]:
        """Get web server summary."""
        return self._host._dispatch_manager_attr_call(
            "_webserver_analyzer", "get_webserver_summary", webservers
        )

    def check_webserver_security(self, webservers: dict[str, Any]) -> list[dict[str, Any]]:
        """Check web server security settings."""
        return self._host._dispatch_manager_attr_call(
            "_webserver_analyzer", "check_webserver_security", webservers
        )

    # Certificate Management

    def find_all_certificates(self) -> dict[str, Any]:
        """Find all certificate files."""
        return self._host._dispatch_manager_attr_call("_certificate_manager", "find_certificates")

    def check_certificate_expiration(self, certs: dict[str, Any], warning_days: int = 30) -> dict[str, Any]:
        """Check certificate expiration."""
        return self._host._dispatch_manager_attr_call(
            "_certificate_manager", "check_certificate_expiration", certs, warning_days
        )

    def get_certificate_summary(self, certs: dict[str, Any]) -> dict[str, Any]:
        """Get certificate summary."""
        return self._host._dispatch_manager_attr_call(
            "_certificate_manager", "get_certificate_summary", certs
        )

    def check_certificate_security(self, certs: dict[str, Any]) -> list[dict[str, Any]]:
        """Check certificate security issues."""
        return self._host._dispatch_manager_attr_call(
            "_certificate_manager", "check_certificate_security", certs
        )

    # Container Analysis

    def analyze_containers(self) -> dict[str, Any]:
        """Analyze container installations comprehensively."""
        return self._host._dispatch_manager_attr_call("_container_analyzer", "analyze_containers")

    def get_container_summary(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Get container summary."""
        return self._host._dispatch_manager_attr_call(
            "_container_analyzer", "get_container_summary", analysis
        )

    def list_container_images(self, analysis: dict[str, Any]) -> list[str]:
        """List all container images."""
        return self._host._dispatch_manager_attr_call(
            "_container_analyzer", "list_container_images", analysis
        )

    def check_container_security(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """Check container security issues."""
        return self._host._dispatch_manager_attr_call(
            "_container_analyzer", "check_container_security", analysis
        )

    # Compliance Checking

    def check_compliance(self, os_type: str = "linux") -> dict[str, Any]:
        """Run comprehensive compliance checks."""
        return self._host._dispatch_manager_attr_call("_compliance_checker", "check_compliance", os_type)

    def get_compliance_summary(self, compliance: dict[str, Any]) -> dict[str, Any]:
        """Get compliance summary."""
        return self._host._dispatch_manager_attr_call(
            "_compliance_checker", "get_compliance_summary", compliance
        )

    def get_failed_checks(self, compliance: dict[str, Any]) -> list[dict[str, Any]]:
        """Get all failed compliance checks."""
        return self._host._dispatch_manager_attr_call("_compliance_checker", "get_failed_checks", compliance)

    def get_recommendations(self, compliance: dict[str, Any]) -> list[str]:
        """Get all compliance recommendations."""
        return self._host._dispatch_manager_attr_call(
            "_compliance_checker", "get_recommendations", compliance
        )

    # Backup Analysis

    def analyze_backup_software(self) -> dict[str, Any]:
        """Analyze backup software installations."""
        return self._host._dispatch_manager_attr_call("_backup_analysis", "analyze_backup_software")

    def get_backup_summary(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Get backup summary."""
        return self._host._dispatch_manager_attr_call("_backup_analysis", "get_backup_summary", analysis)

    def check_backup_health(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """Check backup health and configuration."""
        return self._host._dispatch_manager_attr_call("_backup_analysis", "check_backup_health", analysis)

    def list_backup_software(self, analysis: dict[str, Any]) -> list[str]:
        """List names of detected backup software."""
        return self._host._dispatch_manager_attr_call("_backup_analysis", "list_backup_software", analysis)

    # User Activity Analysis

    def analyze_user_activity(self) -> dict[str, Any]:
        """Analyze user activity comprehensively."""
        return self._host._dispatch_manager_attr_call("_user_activity", "analyze_user_activity")

    def get_activity_summary(self, activity: dict[str, Any]) -> dict[str, Any]:
        """Get user activity summary."""
        return self._host._dispatch_manager_attr_call("_user_activity", "get_activity_summary", activity)

    def detect_suspicious_activity(self, activity: dict[str, Any]) -> list[dict[str, Any]]:
        """Detect suspicious user activity."""
        return self._host._dispatch_manager_attr_call(
            "_user_activity", "detect_suspicious_activity", activity
        )

    def get_top_sudo_users(self, activity: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
        """Get users with most sudo usage."""
        return self._host._dispatch_manager_attr_call(
            "_user_activity", "get_top_sudo_users", activity, limit
        )

    # Application Framework Detection

    def detect_frameworks(self) -> dict[str, Any]:
        """Detect application frameworks comprehensively."""
        return self._host._dispatch_manager_attr_call("_app_framework_detector", "detect_frameworks")

    def get_framework_summary(self, frameworks: dict[str, Any]) -> dict[str, Any]:
        """Get framework summary."""
        return self._host._dispatch_manager_attr_call(
            "_app_framework_detector", "get_framework_summary", frameworks
        )

    def list_web_frameworks(self, frameworks: dict[str, Any]) -> list[str]:
        """List detected web frameworks."""
        return self._host._dispatch_manager_attr_call(
            "_app_framework_detector", "list_web_frameworks", frameworks
        )

    # Cloud Integration Detection

    def detect_cloud_integration(self) -> dict[str, Any]:
        """Detect cloud platform integrations comprehensively."""
        return self._host._dispatch_manager_attr_call("_cloud_detector", "detect_cloud_integration")

    def get_cloud_summary(self, cloud: dict[str, Any]) -> dict[str, Any]:
        """Get cloud integration summary."""
        return self._host._dispatch_manager_attr_call("_cloud_detector", "get_cloud_summary", cloud)

    def is_cloud_vm(self, cloud: dict[str, Any]) -> bool:
        """Check if VM is running in cloud."""
        return self._host._dispatch_manager_attr_call("_cloud_detector", "is_cloud_vm", cloud)

    def get_cloud_services(self, cloud: dict[str, Any]) -> list[str]:
        """List detected cloud services."""
        return self._host._dispatch_manager_attr_call("_cloud_detector", "get_cloud_services", cloud)

    # Monitoring Agent Detection

    def detect_monitoring_agents(self) -> dict[str, Any]:
        """Detect monitoring agents comprehensively."""
        return self._host._dispatch_manager_attr_call("_monitoring_detector", "detect_monitoring_agents")

    def get_monitoring_summary(self, agents: dict[str, Any]) -> dict[str, Any]:
        """Get monitoring summary."""
        return self._host._dispatch_manager_attr_call(
            "_monitoring_detector", "get_monitoring_summary", agents
        )

    def list_agent_vendors(self, agents: dict[str, Any]) -> list[str]:
        """List unique agent vendors."""
        return self._host._dispatch_manager_attr_call("_monitoring_detector", "list_agent_vendors", agents)

    def check_monitoring_health(self, agents: dict[str, Any]) -> list[dict[str, Any]]:
        """Check monitoring health and configuration."""
        return self._host._dispatch_manager_attr_call(
            "_monitoring_detector", "check_monitoring_health", agents
        )

    # Vulnerability Scanning

    def scan_vulnerabilities(self, os_type: str = "linux") -> dict[str, Any]:
        """Scan for vulnerabilities comprehensively."""
        return self._host._dispatch_manager_attr_call(
            "_vulnerability_scanner", "scan_vulnerabilities", os_type
        )

    def get_vulnerability_summary(self, scan: dict[str, Any]) -> dict[str, Any]:
        """Get vulnerability summary."""
        return self._host._dispatch_manager_attr_call(
            "_vulnerability_scanner", "get_vulnerability_summary", scan
        )

    def get_critical_vulnerabilities(self, scan: dict[str, Any]) -> list[dict[str, Any]]:
        """Get critical vulnerabilities only."""
        return self._host._dispatch_manager_attr_call(
            "_vulnerability_scanner", "get_critical_vulnerabilities", scan
        )

    def get_remediation_priority(self, scan: dict[str, Any]) -> list[dict[str, Any]]:
        """Get prioritized remediation list."""
        return self._host._dispatch_manager_attr_call(
            "_vulnerability_scanner", "get_remediation_priority", scan
        )

    def detect_ransomware_indicators(self) -> list[dict[str, Any]]:
        """Detect potential ransomware indicators."""
        return self._host._dispatch_manager_attr_call(
            "_vulnerability_scanner", "detect_ransomware_indicators"
        )

    def check_kernel_vulnerabilities(self) -> list[dict[str, Any]]:
        """Check for kernel vulnerabilities."""
        return self._host._dispatch_manager_attr_call(
            "_vulnerability_scanner", "check_kernel_vulnerabilities"
        )

    # License Detection

    def detect_licenses(self, os_type: str = "linux") -> dict[str, Any]:
        """Detect software licenses comprehensively."""
        return self._host._dispatch_manager_attr_call("_license_detector", "detect_licenses", os_type)

    def get_license_summary(self, licenses: dict[str, Any]) -> dict[str, Any]:
        """Get license summary."""
        return self._host._dispatch_manager_attr_call("_license_detector", "get_license_summary", licenses)

    def get_copyleft_packages(self, licenses: dict[str, Any]) -> list[dict[str, Any]]:
        """Get packages with copyleft licenses."""
        return self._host._dispatch_manager_attr_call("_license_detector", "get_copyleft_packages", licenses)

    def generate_sbom(self, licenses: dict[str, Any]) -> dict[str, Any]:
        """Generate Software Bill of Materials (SBOM)."""
        return self._host._dispatch_manager_attr_call("_license_detector", "generate_sbom", licenses)

    def check_license_compatibility(
        self, licenses: dict[str, Any], target_license: str = "proprietary"
    ) -> list[dict[str, Any]]:
        """Check license compatibility issues."""
        return self._host._dispatch_manager_attr_call(
            "_license_detector", "check_license_compatibility", licenses, target_license
        )

    # Performance Analysis

    def analyze_performance(self) -> dict[str, Any]:
        """Analyze performance comprehensively."""
        return self._host._dispatch_manager_attr_call("_performance_analyzer", "analyze_performance")

    def get_performance_summary(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Get performance summary."""
        return self._host._dispatch_manager_attr_call(
            "_performance_analyzer", "get_performance_summary", analysis
        )

    def get_sizing_recommendation(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Get VM sizing recommendation for migration."""
        return self._host._dispatch_manager_attr_call(
            "_performance_analyzer", "get_sizing_recommendation", analysis
        )

    def estimate_resource_cost(
        self, analysis: dict[str, Any], cloud_provider: str = "aws"
    ) -> dict[str, Any]:
        """Estimate cloud resource cost."""
        return self._host._dispatch_manager_attr_call(
            "_performance_analyzer", "estimate_resource_cost", analysis, cloud_provider
        )

    # Migration Planning

    def plan_migration(
        self, source_platform: str, target_platform: str, os_info: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Plan migration from source to target platform."""
        return self._host._dispatch_manager_attr_call(
            "_migration_planner", "plan_migration", source_platform, target_platform, os_info
        )

    def get_migration_summary(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Get migration summary."""
        return self._host._dispatch_manager_attr_call("_migration_planner", "get_migration_summary", plan)

    def get_migration_checklist(self, plan: dict[str, Any]) -> list[dict[str, Any]]:
        """Generate pre-migration checklist."""
        return self._host._dispatch_manager_attr_call("_migration_planner", "get_checklist", plan)

    def generate_rollback_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Generate rollback plan."""
        return self._host._dispatch_manager_attr_call("_migration_planner", "generate_rollback_plan", plan)

    def validate_migration_readiness(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Validate migration readiness."""
        return self._host._dispatch_manager_attr_call(
            "_migration_planner", "validate_migration_readiness", plan
        )

    # Dependency Mapping

    def map_dependencies(self) -> dict[str, Any]:
        """Map dependencies comprehensively."""
        return self._host._dispatch_manager_attr_call("_dependency_mapper", "map_dependencies")

    def get_dependency_summary(self, mapping: dict[str, Any]) -> dict[str, Any]:
        """Get dependency summary."""
        return self._host._dispatch_manager_attr_call(
            "_dependency_mapper", "get_dependency_summary", mapping
        )

    def get_service_graph(self, mapping: dict[str, Any]) -> dict[str, Any]:
        """Generate service dependency graph data."""
        return self._host._dispatch_manager_attr_call("_dependency_mapper", "get_service_graph", mapping)

    def find_critical_services(self, mapping: dict[str, Any]) -> list[dict[str, Any]]:
        """Find critical services (most dependencies)."""
        return self._host._dispatch_manager_attr_call(
            "_dependency_mapper", "find_critical_services", mapping
        )

    def get_port_security_analysis(self, mapping: dict[str, Any]) -> dict[str, Any]:
        """Analyze port security."""
        return self._host._dispatch_manager_attr_call(
            "_dependency_mapper", "get_port_security_analysis", mapping
        )

    # Forensic Analysis

    def analyze_forensics(self, os_type: str = "linux") -> dict[str, Any]:
        """Perform comprehensive forensic analysis."""
        return self._host._dispatch_manager_attr_call("_forensic_analyzer", "analyze_forensics", os_type)

    def get_forensic_summary(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Get forensic analysis summary."""
        return self._host._dispatch_manager_attr_call("_forensic_analyzer", "get_forensic_summary", analysis)

    def generate_forensic_timeline(self, hours: int = 24) -> list[dict[str, Any]]:
        """Generate file activity timeline."""
        return self._host._dispatch_manager_attr_call("_forensic_analyzer", "generate_timeline", hours)

    def detect_rootkit_indicators(self) -> list[dict[str, Any]]:
        """Detect rootkit indicators."""
        return self._host._dispatch_manager_attr_call("_forensic_analyzer", "detect_rootkit_indicators")

    def analyze_browser_history(self) -> dict[str, Any]:
        """Analyze browser history artifacts."""
        return self._host._dispatch_manager_attr_call("_forensic_analyzer", "analyze_browser_history")

    def find_recently_accessed_files(self, days: int = 7) -> list[dict[str, Any]]:
        """Find files accessed in the last N days."""
        return self._host._dispatch_manager_attr_call(
            "_forensic_analyzer", "find_recently_accessed_files", days
        )

    def detect_data_exfiltration_indicators(self) -> list[dict[str, Any]]:
        """Detect potential data exfiltration indicators."""
        return self._host._dispatch_manager_attr_call(
            "_forensic_analyzer", "detect_data_exfiltration_indicators"
        )

    # Data Discovery

    def discover_sensitive_data(self) -> dict[str, Any]:
        """Discover sensitive data comprehensively."""
        return self._host._dispatch_manager_attr_call("_data_discovery", "discover_sensitive_data")

    def get_data_discovery_summary(self, discovery: dict[str, Any]) -> dict[str, Any]:
        """Get data discovery summary."""
        return self._host._dispatch_manager_attr_call("_data_discovery", "get_discovery_summary", discovery)

    def classify_data_sensitivity(self, discovery: dict[str, Any]) -> dict[str, Any]:
        """Classify discovered data by sensitivity level."""
        return self._host._dispatch_manager_attr_call(
            "_data_discovery", "classify_data_sensitivity", discovery
        )

    def get_compliance_report(self, discovery: dict[str, Any]) -> dict[str, Any]:
        """Generate compliance report (GDPR, CCPA)."""
        return self._host._dispatch_manager_attr_call("_data_discovery", "get_compliance_report", discovery)

    # Configuration Tracking

    def track_configurations(self, os_type: str = "linux") -> dict[str, Any]:
        """Track all system configurations."""
        return self._host._dispatch_manager_attr_call("_config_tracker", "track_configurations", os_type)

    def create_config_baseline(self, tracking: dict[str, Any]) -> dict[str, Any]:
        """Create configuration baseline."""
        return self._host._dispatch_manager_attr_call("_config_tracker", "create_baseline", tracking)

    def detect_config_drift(self, baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
        """Detect configuration drift from baseline."""
        return self._host._dispatch_manager_attr_call("_config_tracker", "detect_drift", baseline, current)

    def validate_best_practices(self) -> list[dict[str, Any]]:
        """Validate configurations against best practices."""
        return self._host._dispatch_manager_attr_call("_config_tracker", "validate_best_practices")

    def get_config_summary(self, tracking: dict[str, Any]) -> dict[str, Any]:
        """Get configuration tracking summary."""
        return self._host._dispatch_manager_attr_call("_config_tracker", "get_config_summary", tracking)

    def analyze_config_security(self) -> list[dict[str, Any]]:
        """Analyze configuration security."""
        return self._host._dispatch_manager_attr_call("_config_tracker", "analyze_config_security")

    def compare_configs(self, config1_path: str, config2_path: str) -> dict[str, Any]:
        """Compare two configuration files."""
        return self._host._dispatch_manager_attr_call(
            "_config_tracker", "compare_configs", config1_path, config2_path
        )

    def generate_config_documentation(self, tracking: dict[str, Any]) -> dict[str, Any]:
        """Generate configuration documentation."""
        return self._host._dispatch_manager_attr_call(
            "_config_tracker", "generate_config_documentation", tracking
        )

    def get_config_backup_recommendations(self, tracking: dict[str, Any]) -> list[dict[str, Any]]:
        """Get configuration backup recommendations."""
        return self._host._dispatch_manager_attr_call(
            "_config_tracker", "get_config_backup_recommendations", tracking
        )

    # Network Topology

    def map_network_topology(self) -> dict[str, Any]:
        """Map complete network topology."""
        return self._host._dispatch_manager_attr_call("_network_topology", "map_network_topology")

    def get_topology_summary(self, topology: dict[str, Any]) -> dict[str, Any]:
        """Get network topology summary."""
        return self._host._dispatch_manager_attr_call("_network_topology", "get_topology_summary", topology)

    def analyze_network_redundancy(self, topology: dict[str, Any]) -> dict[str, Any]:
        """Analyze network redundancy."""
        return self._host._dispatch_manager_attr_call(
            "_network_topology", "analyze_network_redundancy", topology
        )

    def detect_network_segmentation(self, topology: dict[str, Any]) -> dict[str, Any]:
        """Detect network segmentation."""
        return self._host._dispatch_manager_attr_call(
            "_network_topology", "detect_network_segmentation", topology
        )

    def generate_topology_graph(self, topology: dict[str, Any]) -> dict[str, Any]:
        """Generate topology graph data for visualization."""
        return self._host._dispatch_manager_attr_call(
            "_network_topology", "generate_topology_graph", topology
        )

    def get_network_policy_summary(self) -> dict[str, Any]:
        """Get network policy summary."""
        return self._host._dispatch_manager_attr_call("_network_topology", "get_network_policy_summary")

    # Storage Analysis

    def analyze_storage_advanced(self) -> dict[str, Any]:
        """Analyze storage comprehensively."""
        return self._host._dispatch_manager_attr_call("_storage_analyzer", "analyze_storage")

    def get_storage_summary(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Get storage summary."""
        return self._host._dispatch_manager_attr_call("_storage_analyzer", "get_storage_summary", analysis)

    def get_capacity_planning(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Get storage capacity planning recommendations."""
        return self._host._dispatch_manager_attr_call("_storage_analyzer", "get_capacity_planning", analysis)

    def analyze_storage_performance(self) -> dict[str, Any]:
        """Analyze storage performance indicators."""
        return self._host._dispatch_manager_attr_call("_storage_analyzer", "analyze_storage_performance")

    def detect_storage_tiering(self) -> dict[str, Any]:
        """Detect storage tiering configuration."""
        return self._host._dispatch_manager_attr_call("_storage_analyzer", "detect_storage_tiering")

    def estimate_deduplication_ratio(self) -> dict[str, Any]:
        """Estimate potential deduplication ratio."""
        return self._host._dispatch_manager_attr_call("_storage_analyzer", "estimate_deduplication_ratio")

    def analyze_raid_health(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """Analyze RAID array health."""
        return self._host._dispatch_manager_attr_call("_storage_analyzer", "analyze_raid_health", analysis)

    def get_storage_optimization_recommendations(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """Get storage optimization recommendations."""
        return self._host._dispatch_manager_attr_call(
            "_storage_analyzer", "get_optimization_recommendations", analysis
        )
