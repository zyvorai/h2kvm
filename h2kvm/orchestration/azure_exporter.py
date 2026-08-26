# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/orchestrator/azure_exporter.py
"""
Azure VM export handler.
Supports Azure VM disk export with snapshot-based zero-downtime migration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from h2kvm.core.exceptions import Fatal
from h2kvm.core.logger import Log

if TYPE_CHECKING:
    import argparse
    import logging
    from pathlib import Path

# Conditional imports
try:
    from h2kvm.providers.azure import AzureConfig, AzureSourceProvider
    from h2kvm.providers.azure.models import (
        AzureDownloadConfig,
        AzureExportConfig,
        AzureSelectConfig,
        AzureShutdownConfig,
    )

    AZURE_AVAILABLE = True
except ImportError:
    AzureConfig = None  # type: ignore
    AzureSourceProvider = None  # type: ignore
    AZURE_AVAILABLE = False


class AzureExporter:
    """
    Handles Azure VM export operations.

    Responsibilities:
    - Azure VM identification and selection
    - Snapshot-based export (zero-downtime migration)
    - VHD download with resume capability
    - Resource cleanup
    """

    def __init__(self, logger: logging.Logger, args: argparse.Namespace):
        self.logger = logger
        self.args = args

    def is_enabled(self) -> bool:
        """Check if Azure export is enabled."""
        enabled = getattr(self.args, "cmd", None) == "azure"
        Log.trace(self.logger, "☁️ Azure export enabled: %s", enabled)
        return enabled

    def export_vms(self, out_root: Path) -> list[Path]:
        """
        Export Azure VMs to local VHD files.

        Returns:
            List of exported VHD paths
        """
        if not AZURE_AVAILABLE:
            raise Fatal(
                2,
                "Azure export requires the Azure Python SDK, which is not installed.\n"
                "Install with: pip install azure-identity azure-mgmt-compute azure-mgmt-network azure-storage-blob\n"
                "Or install with Azure support: pip install h2kvm[azure]",
            )

        Log.step(self.logger, "Azure export initializing...")

        # Build Azure configuration from args
        cfg = self._build_config(out_root)

        # Execute Azure fetch
        Log.step(self.logger, "Fetching Azure VMs...")
        report, artifacts = AzureSourceProvider.fetch(self.logger, cfg)

        # Log summary
        self.logger.info(f"✅ Azure export completed: {len(report.vms)} VM(s), {len(artifacts)} disk(s)")
        for vm in report.vms:
            self.logger.info(f" - {vm.name} ({vm.resource_group}): {len(vm.exports)} disk(s)")

        # Return list of local VHD paths
        return [art.local_path for art in artifacts]

    def _build_config(self, out_root: Path) -> AzureConfig:
        """Build AzureConfig from args."""
        select = AzureSelectConfig(
            resource_group=getattr(self.args, "azure_resource_group", None),
            vm_names=self._get_vm_names(),
            tags=self._get_tags(),
            power_state=getattr(self.args, "azure_power_state", None),
            list_only=bool(getattr(self.args, "azure_list_only", False)),
            allow_all_rgs=bool(getattr(self.args, "azure_allow_all_rgs", False)),
        )

        shutdown = AzureShutdownConfig(
            mode=getattr(self.args, "azure_shutdown_mode", None) or "none",
            force=bool(getattr(self.args, "azure_shutdown_force", False)),
            wait=bool(getattr(self.args, "azure_shutdown_wait", True)),
        )

        export = AzureExportConfig(
            use_snapshots=bool(getattr(self.args, "azure_use_snapshots", True)),
            stage_disk_from_snapshot=bool(getattr(self.args, "azure_stage_disk", False)),
            disks=getattr(self.args, "azure_disks", None) or "all",
            consistency=getattr(self.args, "azure_consistency", None) or "crash_consistent",
            tag_resources=bool(getattr(self.args, "azure_tag_resources", True)),
            keep_snapshots=bool(getattr(self.args, "azure_keep_snapshots", False)),
            keep_temp_disks=bool(getattr(self.args, "azure_keep_temp_disks", False)),
            run_tag=getattr(self.args, "azure_run_tag", None) or "",
            sas_duration_s=int(getattr(self.args, "azure_sas_duration", 3600)),
        )

        download = AzureDownloadConfig(
            parallel=int(getattr(self.args, "azure_parallel", 4)),
            chunk_mb=int(getattr(self.args, "azure_chunk_mb", 4)),
            resume=bool(getattr(self.args, "azure_resume", True)),
            verify_size=bool(getattr(self.args, "azure_verify_size", True)),
            strict_verify=bool(getattr(self.args, "azure_strict_verify", False)),
            temp_suffix=getattr(self.args, "azure_temp_suffix", None) or ".part",
            connect_timeout_s=int(getattr(self.args, "azure_connect_timeout", 30)),
            read_timeout_s=int(getattr(self.args, "azure_read_timeout", 300)),
            retries=int(getattr(self.args, "azure_retries", 3)),
            backoff_base_s=float(getattr(self.args, "azure_backoff_base", 1.0)),
            backoff_cap_s=float(getattr(self.args, "azure_backoff_cap", 60.0)),
        )

        return AzureConfig(
            subscription=getattr(self.args, "azure_subscription", None),
            tenant=getattr(self.args, "azure_tenant", None),
            output_dir=out_root,
            select=select,
            shutdown=shutdown,
            export=export,
            download=download,
        )

    def _get_vm_names(self) -> list[str]:
        """Extract VM names from args."""
        vm_names = getattr(self.args, "azure_vm_names", None) or []
        if isinstance(vm_names, str):
            vm_names = [s.strip() for s in vm_names.split(",") if s.strip()]
        return list(vm_names)

    def _get_tags(self) -> dict:
        """Extract tags from args."""
        tags = getattr(self.args, "azure_tags", None) or {}
        if isinstance(tags, str):
            # Parse "key1=val1, key2=val2" format
            result = {}
            for pair in tags.split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    result[k.strip()] = v.strip()
            return result
        return dict(tags)
