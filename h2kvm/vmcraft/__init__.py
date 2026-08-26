# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/__init__.py
"""
VMCraft: Python library for VM disk image manipulation.

Comprehensive VM manipulation using:
- qemu-nbd for disk image access
- Native Linux tools (mount, lvm, cryptsetup, etc.)
- Python file I/O for guest filesystem operations

This module provides a modular, maintainable architecture with 480+ methods
for comprehensive VM manipulation and configuration.
"""

# Export main VMCraft class for backward compatibility
# Export custom exception classes
from ._utils import (
    CacheError,
    DetectionError,
    DeviceError,
    FileSystemError,
    MountError,
    RegistryError,
    VMCraftError,
)
from .advanced_analysis import AdvancedAnalyzer
from .app_framework_detector import AppFrameworkDetector
from .backup_analysis import BackupAnalysis
from .certificate_manager import CertificateManager
from .cloud_detector import CloudDetector
from .cloud_optimizer import CloudOptimizer
from .compliance_checker import ComplianceChecker
from .config_tracker import ConfigTracker
from .container_analyzer import ContainerAnalyzer
from .data_discovery import DataDiscovery
from .database_detector import DatabaseDetector
from .dependency_mapper import DependencyMapper
from .disaster_recovery import DisasterRecovery
from .export import ExportManager
from .firewall_analyzer import FirewallAnalyzer
from .forensic_analyzer import ForensicAnalyzer
from .hardware_detector import HardwareDetector
from .license_detector import LicenseDetector
from .linux_services import LinuxServiceManager
from .log_analyzer import LogAnalyzer
from .lvm_executor import LVMExecutor, LVMJob, LVMJobResult, LVMJobStatus, list_nbd_partitions
from .main import VMCraft
from .migration_planner import MigrationPlanner
from .monitoring_detector import MonitoringDetector
from .network_config import NetworkConfigAnalyzer
from .network_topology import NetworkTopology
from .performance_analyzer import PerformanceAnalyzer
from .scheduled_tasks import ScheduledTaskAnalyzer
from .ssh_analyzer import SSHAnalyzer
from .storage_analyzer import StorageAnalyzer
from .user_activity import UserActivityAnalyzer
from .vulnerability_scanner import VulnerabilityScanner
from .webserver_analyzer import WebServerAnalyzer
from .windows_applications import WindowsApplicationManager
from .windows_services import WindowsServiceManager

# Export specialized modules (for advanced usage)
from .windows_users import WindowsUserManager

__all__ = [
    "AdvancedAnalyzer",
    "AppFrameworkDetector",
    "BackupAnalysis",
    "CacheError",
    "CertificateManager",
    "CloudDetector",
    "CloudOptimizer",
    "ComplianceChecker",
    "ConfigTracker",
    "ContainerAnalyzer",
    "DataDiscovery",
    "DatabaseDetector",
    "DependencyMapper",
    "DetectionError",
    "DeviceError",
    "DisasterRecovery",
    "ExportManager",
    "FileSystemError",
    "FirewallAnalyzer",
    "ForensicAnalyzer",
    "HardwareDetector",
    "LVMExecutor",
    "LVMJob",
    "LVMJobResult",
    "LVMJobStatus",
    "LicenseDetector",
    "LinuxServiceManager",
    "LogAnalyzer",
    "MigrationPlanner",
    "MonitoringDetector",
    "MountError",
    "NetworkConfigAnalyzer",
    "NetworkTopology",
    "PerformanceAnalyzer",
    "RegistryError",
    "SSHAnalyzer",
    "ScheduledTaskAnalyzer",
    "StorageAnalyzer",
    "UserActivityAnalyzer",
    # Main API
    "VMCraft",
    # Exception classes
    "VMCraftError",
    "VulnerabilityScanner",
    "WebServerAnalyzer",
    "WindowsApplicationManager",
    "WindowsServiceManager",
    # Specialized modules
    "WindowsUserManager",
    "list_nbd_partitions",
]
