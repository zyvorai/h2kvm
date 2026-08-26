# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Windows application compatibility detection and reporting.

This module provides tools for detecting applications and configurations that
may have compatibility issues after VM migration, including:

- Hardware-dependent applications (CAD, graphics, engineering software)
- License manager services (FlexLM, RLM, HASP)
- Hardware dongles and dongle drivers
- SQL Server instances and configuration
"""

from .detector import (
    AppCompatFinding,
    RiskLevel,
    detect_dongle_drivers,
    detect_hardware_dependent_apps,
    detect_license_services,
)
from .reporter import (
    CompatibilityReport,
    generate_compatibility_report,
)
from .sqlserver import (
    SQLServerInstance,
    detect_sql_server_instances,
    generate_sql_reconfiguration_script,
)

__all__ = [
    "AppCompatFinding",
    "CompatibilityReport",
    "RiskLevel",
    "SQLServerInstance",
    "detect_dongle_drivers",
    "detect_hardware_dependent_apps",
    "detect_license_services",
    "detect_sql_server_instances",
    "generate_compatibility_report",
    "generate_sql_reconfiguration_script",
]
