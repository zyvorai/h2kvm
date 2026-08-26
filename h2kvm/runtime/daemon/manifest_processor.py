# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/daemon/manifest_processor.py
"""
Manifest file processor for daemon mode.

Processes YAML/JSON manifest files and triggers migrations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from ...core.logger import Log
from ...core.metrics import errors_total, manifest_vms_total, manifests_processed_total

logger = logging.getLogger(__name__)


class ManifestProcessor:
    """
    Processes migration manifest files.

    Loads YAML/JSON manifests and triggers appropriate migrations.
    """

    def __init__(self, output_dir: Path | None = None):
        """
        Initialize manifest processor.

        Args:
            output_dir: Default output directory for migrations
        """
        self.output_dir = output_dir or Path("/var/lib/h2kvm/output")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def process_manifest(self, manifest_path: Path) -> bool:
        """
        Process a manifest file.

        Args:
            manifest_path: Path to manifest file (.yaml or .json)

        Returns:
            True if processing succeeded, False otherwise
        """
        log = Log.bind(logger, manifest=manifest_path.name)

        try:
            log.info("Processing manifest file")

            # Load manifest
            manifest = self._load_manifest(manifest_path)

            if not manifest:
                log.error("Empty or invalid manifest")
                manifests_processed_total.labels(status="failed").inc()
                return False

            # Validate manifest structure
            if not self._validate_manifest(manifest):
                log.error("Manifest validation failed")
                manifests_processed_total.labels(status="failed").inc()
                return False

            # Process based on type
            if self._is_batch_manifest(manifest):
                success = self._process_batch_manifest(manifest, manifest_path)
            else:
                success = self._process_single_manifest(manifest, manifest_path)

            if success:
                log.info("Manifest processed successfully")
                manifests_processed_total.labels(status="success").inc()
            else:
                log.error("Manifest processing failed")
                manifests_processed_total.labels(status="failed").inc()

            return success

        except Exception as e:
            log.error(f"Unexpected error processing manifest: {e}", exc_info=True)
            manifests_processed_total.labels(status="failed").inc()
            errors_total.labels(error_type=type(e).__name__, component="manifest_processor").inc()
            return False

    def _load_manifest(self, manifest_path: Path) -> dict[str, Any] | None:
        """Load manifest from YAML/JSON file."""
        try:
            with open(manifest_path) as f:
                if manifest_path.suffix.lower() == ".json":
                    import json

                    return json.load(f)
                return yaml.safe_load(f)

        except Exception as e:
            logger.exception(f"Failed to load manifest {manifest_path.name}: {e}")
            return None

    def _validate_manifest(self, manifest: dict[str, Any]) -> bool:
        """Validate manifest structure."""
        # Basic validation - should have either:
        # - Single VM config: hypervisor, vm_name/vm_uuid
        # - Batch config: vms list

        if "vms" in manifest:
            # Batch manifest
            if not isinstance(manifest["vms"], list):
                logger.error("Batch manifest 'vms' must be a list")
                return False
            if len(manifest["vms"]) == 0:
                logger.error("Batch manifest 'vms' list is empty")
                return False
            return True

        # Single VM manifest
        if "hypervisor" not in manifest:
            logger.error("Manifest missing 'hypervisor' field")
            return False

        hypervisor = manifest["hypervisor"]

        if hypervisor == "vmware":
            vmware_config = manifest.get("vmware", {})
            if not vmware_config.get("vm_name") and not vmware_config.get("vm_uuid"):
                logger.error("VMware manifest must have vm_name or vm_uuid")
                return False

        return True

    def _is_batch_manifest(self, manifest: dict[str, Any]) -> bool:
        """Check if manifest is a batch (multi-VM) manifest."""
        return "vms" in manifest and isinstance(manifest["vms"], list)

    def _process_single_manifest(self, manifest: dict[str, Any], manifest_path: Path) -> bool:
        """Process a single VM manifest."""
        log = Log.bind(logger, manifest=manifest_path.name)

        try:
            hypervisor = manifest.get("hypervisor")
            log.info("Processing single VM manifest", extra={"ctx": {"hypervisor": hypervisor}})

            # Here you would integrate with your orchestrator
            # For now, we'll log the action
            vm_name = self._get_vm_name(manifest)

            log.info(
                f"Would migrate VM: {vm_name}", extra={"ctx": {"hypervisor": hypervisor, "vm": vm_name}}
            )

            # Update metrics
            manifest_vms_total.labels(status="success").inc()

            # In real implementation:
            # from ..orchestration import Orchestrator
            # orchestrator = Orchestrator(manifest)
            # result = orchestrator.run()

            return True

        except Exception as e:
            log.error(f"Failed to process single manifest: {e}", exc_info=True)
            manifest_vms_total.labels(status="failed").inc()
            return False

    def _process_batch_manifest(self, manifest: dict[str, Any], manifest_path: Path) -> bool:
        """Process a batch (multi-VM) manifest."""
        log = Log.bind(logger, manifest=manifest_path.name)

        vms = manifest.get("vms", [])
        log.info(f"Processing batch manifest with {len(vms)} VMs")

        success_count = 0
        failed_count = 0

        for vm_config in vms:
            try:
                vm_name = self._get_vm_name(vm_config)
                log.info(f"Processing VM from batch: {vm_name}")

                # Process VM
                # In real implementation, call orchestrator here
                success_count += 1
                manifest_vms_total.labels(status="success").inc()

            except Exception as e:
                log.exception(f"Failed to process VM: {e}")
                failed_count += 1
                manifest_vms_total.labels(status="failed").inc()

        log.info(f"Batch processing complete: {success_count} succeeded, {failed_count} failed")

        return failed_count == 0

    def _get_vm_name(self, config: dict[str, Any]) -> str:
        """Extract VM name from config."""
        # Try different config structures
        if "vm_name" in config:
            return config["vm_name"]

        if "vmware" in config:
            vmware = config["vmware"]
            if "vm_name" in vmware:
                return vmware["vm_name"]
            if "vm_uuid" in vmware:
                return vmware["vm_uuid"]

        return "unknown"


# Convenience function for daemon mode
def create_manifest_processor_callback(output_dir: Path | None = None):
    """
    Create a manifest processor callback for daemon mode.

    Args:
        output_dir: Output directory for migrations

    Returns:
        Callback function that processes manifest files

    Example:
        >>> from .manifest_processor import create_manifest_processor_callback
        >>> from .manifest_watcher import start_manifest_daemon
        >>>
        >>> callback = create_manifest_processor_callback()
        >>> daemon = start_manifest_daemon("/var/lib/h2kvm/manifests", callback)
    """
    processor = ManifestProcessor(output_dir)
    return processor.process_manifest
