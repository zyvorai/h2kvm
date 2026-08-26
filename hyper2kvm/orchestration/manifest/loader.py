# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Artifact Manifest v1 loader and validator for hypersdk integration."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from hyper2kvm.config.config_loader import Config
from hyper2kvm.core.exceptions import ManifestError
from hyper2kvm.orchestration.profiles import ProfileLoader


class DiskArtifact:  # pylint: disable=too-many-instance-attributes,too-few-public-methods
    """Represents a single disk artifact from the manifest (data model with only __repr__)."""

    def __init__(self, data: dict[str, Any]):
        self.id = data["id"]
        self.source_format = data["source_format"]
        self.bytes = data["bytes"]
        self.local_path = Path(data["local_path"])
        self.checksum = data.get("checksum")
        self.boot_order_hint = data.get("boot_order_hint", 999)
        self.label = data.get("label", self.id)
        self.disk_type = data.get("disk_type", "unknown")

    def __repr__(self) -> str:
        return f"DiskArtifact(id={self.id!r}, path={self.local_path}, type={self.disk_type})"


class ManifestLoader:  # pylint: disable=too-many-public-methods
    """Loads and validates Artifact Manifest v1 for hypersdk integration.

    Many getter methods are exposed as a stable, discoverable facade over the
    manifest dict for callers (orchestrator, CLI) rather than making them poke
    at self.manifest directly.
    """

    SUPPORTED_VERSIONS = ["1.0"]
    SUPPORTED_SOURCE_FORMATS = ["vmdk", "qcow2", "raw", "vhd", "vhdx", "vdi"]
    SUPPORTED_OUTPUT_FORMATS = ["qcow2", "raw", "vdi"]

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)
        self.manifest: dict[str, Any] = {}
        self.path: Path | None = None
        self.disks: list[DiskArtifact] = []
        self.profile_loader = ProfileLoader(logger)
        self.loaded_profile: dict[str, Any] | None = None

    def load(self, manifest_path: str | Path) -> dict[str, Any]:
        """
        Load and validate Artifact Manifest v1.

        Args:
            manifest_path: Path to manifest JSON file

        Returns:
            Validated manifest dictionary

        Raises:
            ManifestError: If manifest is invalid
            FileNotFoundError: If manifest file doesn't exist
            json.JSONDecodeError: If manifest is not valid JSON
        """
        self.path = Path(manifest_path).expanduser().resolve()

        if not self.path.exists():
            raise FileNotFoundError(
                f"Artifact manifest not found at {self.path}. "
                f"Ensure the manifest file exists and the path is correct."
            )

        self.logger.info("Loading Artifact Manifest: %s", self.path)

        try:
            with open(self.path, encoding="utf-8") as f:
                self.manifest = json.load(f)
        except json.JSONDecodeError as e:
            raise ManifestError(
                msg=(
                    f"Invalid JSON in manifest '{self.path}': {e}\n"
                    "Verify the file contains valid JSON. Common issues:\n"
                    "  - Trailing commas after the last item in arrays/objects\n"
                    "  - Missing quotes around string values\n"
                    "  - Comments (JSON does not support comments; use YAML instead)"
                ),
                cause=e,
            ) from e
        except PermissionError as e:
            raise ManifestError(
                msg=f"Permission denied reading manifest '{self.path}': {e}",
                cause=e,
            ) from e

        self._validate()

        # Load and apply profile if specified
        self._apply_profile()

        self.logger.info("✅ Artifact Manifest v%s loaded successfully", self.get_version())

        return self.manifest

    def _validate(self) -> None:
        """Validate manifest structure and required fields."""
        if not isinstance(self.manifest, dict):
            raise ManifestError(msg="Manifest must be a JSON object")

        # Validate version
        version = self.manifest.get("manifest_version")
        if not version:
            raise ManifestError(
                msg="Missing required field: manifest_version. "
                f"This is an Artifact Manifest v1. Expected versions: {self.SUPPORTED_VERSIONS}"
            )

        if version not in self.SUPPORTED_VERSIONS:
            raise ManifestError(
                msg=f"Unsupported manifest version: {version}. "
                f"This hyper2kvm version supports: {self.SUPPORTED_VERSIONS}"
            )

        # Validate disks (REQUIRED)
        if "disks" not in self.manifest:
            raise ManifestError(
                msg="Missing required field: disks[]. Artifact Manifest v1 requires at least one disk."
            )

        if not isinstance(self.manifest["disks"], list):
            raise ManifestError(msg="Field 'disks' must be an array")

        if len(self.manifest["disks"]) == 0:
            raise ManifestError(msg="Field 'disks' must contain at least one disk")

        # Validate each disk
        self._validate_disks()

        # Optional sections (validate if present)
        if "source" in self.manifest:
            self._validate_source()

        if "vm" in self.manifest:
            self._validate_vm()

    def _validate_disks(self) -> None:  # pylint: disable=too-many-branches
        """Validate disks array.

        Each disk field (id, format, bytes, path, checksum, boot hint, type) has its
        own independent validation branch, so the branch count is inherent here.
        """
        disk_ids = set()

        for idx, disk_data in enumerate(self.manifest["disks"]):
            if not isinstance(disk_data, dict):
                raise ManifestError(msg=f"disks[{idx}] must be an object")

            # Required fields
            for field in ["id", "source_format", "bytes", "local_path"]:
                if field not in disk_data:
                    raise ManifestError(msg=f"disks[{idx}].{field} is required")

            # Validate id uniqueness
            disk_id = disk_data["id"]
            if disk_id in disk_ids:
                raise ManifestError(msg=f"Duplicate disk ID: {disk_id}")
            disk_ids.add(disk_id)

            # Validate id format
            if not re.match(r"^[a-zA-Z0-9_-]+$", disk_id):
                raise ManifestError(
                    msg=f"disks[{idx}].id must match pattern: ^[a-zA-Z0-9_-]+$ (got: {disk_id!r})"
                )

            # Validate source_format
            source_format = disk_data["source_format"]
            if source_format not in self.SUPPORTED_SOURCE_FORMATS:
                raise ManifestError(
                    msg=f"disks[{idx}].source_format unsupported: {source_format}. "
                    f"Supported: {self.SUPPORTED_SOURCE_FORMATS}"
                )

            # Validate bytes
            if not isinstance(disk_data["bytes"], int) or disk_data["bytes"] < 0:
                raise ManifestError(msg=f"disks[{idx}].bytes must be a non-negative integer")

            # Validate local_path exists
            local_path = Path(disk_data["local_path"]).expanduser().resolve()
            if not local_path.exists():
                raise ManifestError(msg=f"disks[{idx}].local_path not found: {local_path}")

            # Validate checksum format (if present)
            if "checksum" in disk_data:
                checksum = disk_data["checksum"]
                if not re.match(r"^sha256:[a-f0-9]{64}$", checksum):
                    raise ManifestError(
                        msg=f"disks[{idx}].checksum must match format: sha256:<hexdigest> (got: {checksum!r})"
                    )

            # Validate boot_order_hint (if present)
            if "boot_order_hint" in disk_data:
                if not isinstance(disk_data["boot_order_hint"], int) or disk_data["boot_order_hint"] < 0:
                    raise ManifestError(msg=f"disks[{idx}].boot_order_hint must be a non-negative integer")

            # Validate disk_type (if present)
            if "disk_type" in disk_data:
                if disk_data["disk_type"] not in ["boot", "data", "unknown"]:
                    raise ManifestError(msg=f"disks[{idx}].disk_type must be one of: boot, data, unknown")

            # Create DiskArtifact
            try:
                disk = DiskArtifact(disk_data)
            except KeyError as e:
                raise ManifestError(
                    msg=f"disks[{idx}] is missing required field {e}. "
                    f"Each disk must have: id, source_format, bytes, local_path."
                ) from e
            except (TypeError, ValueError) as e:
                raise ManifestError(
                    msg=f"disks[{idx}] has an invalid field value: {e}. "
                    f"Check that 'bytes' is an integer and 'local_path' is a valid path."
                ) from e
            self.disks.append(disk)

        self.logger.info("Validated %d disk artifact(s)", len(self.disks))

    def _validate_source(self) -> None:
        """Validate source section (optional but checked if present)."""
        source = self.manifest["source"]

        if not isinstance(source, dict):
            raise ManifestError(msg="Field 'source' must be an object")

        # Validate provider (if present)
        if "provider" in source:
            if not isinstance(source["provider"], str) or not source["provider"]:
                raise ManifestError(msg="source.provider must be a non-empty string")

        # Validate export_timestamp (if present)
        if "export_timestamp" in source:
            ts = source["export_timestamp"]
            if not isinstance(ts, str) or not ts:
                raise ManifestError(msg="source.export_timestamp must be a non-empty string")
            # Basic ISO8601 check
            try:
                datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                self.logger.warning("source.export_timestamp is not valid ISO8601: %s", ts)

        # Validate vm_name (if present)
        if "vm_name" in source and not isinstance(source["vm_name"], str):
            raise ManifestError(msg="source.vm_name must be a string")

        # Validate vm_id (if present)
        if "vm_id" in source and not isinstance(source["vm_id"], str):
            raise ManifestError(msg="source.vm_id must be a string")

    def _validate_vm(self) -> None:
        """Validate VM section (optional)."""
        vm = self.manifest["vm"]

        if not isinstance(vm, dict):
            raise ManifestError(msg="Field 'vm' must be an object")

        # Validate firmware (if present)
        if "firmware" in vm:
            firmware = vm["firmware"]
            if firmware not in ["bios", "uefi", "unknown"]:
                raise ManifestError(
                    msg=f"vm.firmware must be one of: bios, uefi, unknown (got: {firmware!r})"
                )

        # Validate secureboot (if present)
        if "secureboot" in vm and not isinstance(vm["secureboot"], bool):
            raise ManifestError(msg="vm.secureboot must be a boolean")

        # Validate cpu (if present)
        if "cpu" in vm and (not isinstance(vm["cpu"], int) or vm["cpu"] < 1):
            raise ManifestError(msg="vm.cpu must be an integer >= 1")

        # Validate mem_gb (if present)
        if "mem_gb" in vm and (not isinstance(vm["mem_gb"], int) or vm["mem_gb"] < 1):
            raise ManifestError(msg="vm.mem_gb must be an integer >= 1")

    def verify_checksums(self) -> dict[str, bool]:
        """
        Verify checksums for all disks that have them.

        Returns:
            Dictionary mapping disk_id to verification result (True=pass, False=fail)
        """
        results = {}

        for disk in self.disks:
            if not disk.checksum:
                self.logger.info("Disk %s: No checksum provided, skipping verification", disk.id)
                continue

            self.logger.info("Verifying checksum for disk %s...", disk.id)

            # Extract expected hash
            expected_hash = disk.checksum.replace("sha256:", "")

            # Compute actual hash
            sha256 = hashlib.sha256()
            with open(disk.local_path, "rb") as f:
                while chunk := f.read(8192 * 1024):  # 8MB chunks
                    sha256.update(chunk)
            actual_hash = sha256.hexdigest()

            # Compare
            match = actual_hash == expected_hash
            results[disk.id] = match

            if match:
                self.logger.info("✅ Disk %s: Checksum verified", disk.id)
            else:
                self.logger.error(
                    "❌ Disk %s: Checksum mismatch!\n   Expected: %s\n   Actual:   %s",
                    disk.id,
                    expected_hash,
                    actual_hash,
                )
                raise ManifestError(msg=f"Checksum verification failed for disk {disk.id}")

        return results

    def _apply_profile(self) -> None:
        """
        Load and apply migration profile if specified in manifest.

        Profiles are merged with manifest configuration:
        - Profile settings act as defaults
        - Manifest settings override profile settings
        - profile_overrides apply on top of profile

        Priority (lowest to highest):
        1. Profile defaults
        2. Profile overrides (from manifest.profile_overrides)
        3. Direct manifest settings (always win)
        """
        profile_name = self.manifest.get("profile")
        if not profile_name:
            self.logger.debug("No profile specified in manifest")
            return

        try:
            # Load profile
            custom_path = self.manifest.get("profiles_directory")
            custom_path_obj = Path(custom_path) if custom_path else None

            self.logger.info("📋 Loading profile: %s", profile_name)
            profile_config = self.profile_loader.load_profile(
                profile_name, custom_profile_path=custom_path_obj
            )

            # Apply profile_overrides if present
            profile_overrides = self.manifest.get("profile_overrides", {})
            if profile_overrides:
                self.logger.debug("Applying profile overrides: %s", list(profile_overrides.keys()))
                profile_config = self.profile_loader.apply_overrides(profile_config, profile_overrides)

            # Store loaded profile for reference
            self.loaded_profile = profile_config.copy()

            # Merge profile into manifest (manifest settings override profile)
            # Use Config.merge_dicts: base=profile, override=manifest
            merged = Config.merge_dicts(profile_config, self.manifest)

            # Update manifest with merged configuration
            self.manifest = merged

            self.logger.info("✅ Profile '%s' applied successfully", profile_name)

        except Exception as e:
            self.logger.debug("Profile loading exception for '%s'", profile_name, exc_info=True)
            raise ManifestError(
                msg=(
                    f"Failed to load migration profile '{profile_name}': {e}\n"
                    "Verify the profile name is correct. Available profiles can be listed with:\n"
                    "  h2kvmctl --list-profiles\n"
                    "Custom profiles should be placed in the profiles directory or specified via profiles_directory."
                ),
                cause=e,
            ) from e

    # Convenience getters

    def get_version(self) -> str:
        """Get manifest version."""
        return self.manifest.get("manifest_version", "unknown")

    def get_disks(self) -> list[DiskArtifact]:
        """Get validated disk artifacts."""
        return self.disks

    def get_boot_disk(self) -> DiskArtifact:
        """
        Get the primary boot disk.

        Uses boot_order_hint if available, otherwise returns first disk.
        """
        if not self.disks:
            raise ManifestError(msg="No disks available")

        # Sort by boot_order_hint (lower is higher priority)
        sorted_disks = sorted(self.disks, key=lambda d: d.boot_order_hint)
        boot_disk = sorted_disks[0]

        self.logger.info(
            f"Boot disk identified: {boot_disk.id} (boot_order_hint={boot_disk.boot_order_hint})"
        )
        return boot_disk

    def get_firmware(self) -> str:
        """Get firmware hint (bios/uefi/unknown)."""
        vm = self.manifest.get("vm", {})
        return vm.get("firmware", "bios")

    def get_os_hint(self) -> str:
        """Get OS hint (linux/windows/unknown)."""
        vm = self.manifest.get("vm", {})
        return vm.get("os_hint", "unknown")

    def get_secureboot(self) -> bool:
        """Get secure boot setting."""
        vm = self.manifest.get("vm", {})
        return vm.get("secureboot", False)

    def get_source_metadata(self) -> dict[str, Any]:
        """Get source metadata (provider, vm_id, etc.)."""
        return self.manifest.get("source", {})

    def get_vm_metadata(self) -> dict[str, Any]:
        """Get VM metadata (cpu, mem, firmware, etc.)."""
        return self.manifest.get("vm", {})

    def get_nics(self) -> list[dict[str, Any]]:
        """Get network interfaces."""
        return self.manifest.get("nics", [])

    def get_input_notes(self) -> list[str]:
        """Get notes from export process."""
        return self.manifest.get("notes", [])

    def get_input_warnings(self) -> list[dict[str, Any]]:
        """Get warnings from export process."""
        return self.manifest.get("warnings", [])

    def get_metadata(self) -> dict[str, Any]:
        """Get additional metadata."""
        return self.manifest.get("metadata", {})

    def get_output_directory(self) -> Path:
        """
        Get output directory from manifest or derive from manifest location.

        For Artifact Manifest v1, output directory is derived from manifest path:
        /work/{job_id}/manifest.json → /work/{job_id}/output/
        """
        # If manifest has explicit output directory, use it
        if "output" in self.manifest and "directory" in self.manifest["output"]:
            return Path(self.manifest["output"]["directory"]).expanduser().resolve()

        # Otherwise, derive from manifest path
        if self.path:
            manifest_dir = self.path.parent
            return manifest_dir / "output"

        # Fallback
        return Path("./output")

    def get_output_format(self) -> str:
        """Get output format (qcow2/raw/vdi)."""
        if "output" in self.manifest:
            return self.manifest["output"].get("format", "qcow2")
        return "qcow2"

    def is_dry_run(self) -> bool:
        """Check if dry-run mode is enabled."""
        if "options" in self.manifest:
            return self.manifest["options"].get("dry_run", False)
        return False

    def get_verbosity(self) -> int:
        """Get verbosity level (default: 1)."""
        if "options" in self.manifest:
            return self.manifest["options"].get("verbose", 1)
        return 1

    def get_pipeline_config(self) -> dict[str, Any]:
        """Get pipeline configuration (for backward compat with orchestrator)."""
        return self.manifest.get("pipeline", {})

    def is_stage_enabled(self, stage: str) -> bool:
        """Check if a pipeline stage is enabled (for backward compat)."""
        pipeline = self.get_pipeline_config()
        stage_config = pipeline.get(stage, {})
        return stage_config.get("enabled", False)

    def get_stage_config(self, stage: str) -> dict[str, Any]:
        """Get configuration for a pipeline stage."""
        pipeline = self.get_pipeline_config()
        return pipeline.get(stage, {})

    def get_configuration(self) -> dict[str, Any]:
        """Get guest configuration injection settings."""
        return self.manifest.get("configuration", {})

    def get_options(self) -> dict[str, Any]:
        """Get global options."""
        return self.manifest.get("options", {})

    def is_libvirt_integration_enabled(self) -> bool:
        """Check if libvirt integration is enabled."""
        libvirt_config = self.manifest.get("libvirt_integration", {})
        return libvirt_config.get("enabled", False)

    def get_libvirt_integration_config(self) -> dict[str, Any]:
        """Get libvirt integration configuration."""
        return self.manifest.get("libvirt_integration", {})

    def to_dict(self) -> dict[str, Any]:
        """Return the loaded manifest as a dictionary."""
        return self.manifest.copy()
