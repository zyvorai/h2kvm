# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Manifest pipeline reporter - generates structured report.json."""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any


class ManifestReporter:
    """Generates structured reports for manifest-driven pipelines."""

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)
        self.report: dict[str, Any] = {
            "version": "1.0",
            "timestamp": datetime.datetime.now().isoformat(),
            "pipeline": {
                "success": False,
                "duration_seconds": 0.0,
                "stages": {},
            },
            "artifacts": [],
            "warnings": [],
            "errors": [],
        }

    def add_stage_result(self, stage_name: str, result: dict[str, Any]) -> None:
        """Add result for a pipeline stage."""
        self.report["pipeline"]["stages"][stage_name] = result

    def add_artifact(self, artifact_type: str, path: str, **metadata: Any) -> None:
        """Add an artifact to the report."""
        artifact = {
            "type": artifact_type,
            "path": path,
            **metadata,
        }
        self.report["artifacts"].append(artifact)

    def add_warning(self, stage: str, message: str) -> None:
        """Add a warning."""
        self.report["warnings"].append(
            {
                "stage": stage,
                "message": message,
                "timestamp": datetime.datetime.now().isoformat(),
            }
        )

    def add_error(self, stage: str, message: str) -> None:
        """Add an error."""
        self.report["errors"].append(
            {
                "stage": stage,
                "message": message,
                "timestamp": datetime.datetime.now().isoformat(),
            }
        )

    def set_success(self, success: bool) -> None:
        """Set overall pipeline success status."""
        self.report["pipeline"]["success"] = success

    def set_duration(self, duration: float) -> None:
        """Set pipeline duration in seconds."""
        self.report["pipeline"]["duration_seconds"] = round(duration, 2)

    def generate(self) -> dict[str, Any]:
        """Generate final report dictionary."""
        # Add final artifacts from stages
        stages = self.report["pipeline"]["stages"]

        # Add converted disks as artifacts (Artifact Manifest v1: multi-disk support)
        if "convert" in stages and stages["convert"].get("success"):
            convert_result = stages["convert"].get("result", {})
            converted_disks = convert_result.get("converted_disks", [])

            for disk_info in converted_disks:
                self.add_artifact(
                    "converted_disk",
                    disk_info["output_path"],
                    disk_id=disk_info["disk_id"],
                    format=disk_info["output_format"],
                    size_bytes=disk_info["output_size_bytes"],
                    size_human=disk_info["output_size_human"],
                    boot_order_hint=disk_info["boot_order_hint"],
                    compressed=convert_result.get("compressed", False),
                )

        # Add input manifest metadata
        if "load_manifest" in stages:
            load_result = stages["load_manifest"].get("result", {})
            self.report["input_manifest"] = {
                "path": load_result.get("manifest_path"),
                "manifest_version": load_result.get("manifest_version"),
                "source_provider": load_result.get("source_provider"),
                "source_vm_id": load_result.get("source_vm_id"),
                "source_vm_name": load_result.get("source_vm_name"),
            }

        # Add hyper2kvm version info
        self.report["hyper2kvm_version"] = self._get_hyper2kvm_version()

        # Add summary
        load_result = stages.get("load_manifest", {}).get("result", {})
        self.report["summary"] = {
            "total_stages": len(stages),
            "successful_stages": sum(1 for s in stages.values() if s.get("success")),
            "failed_stages": sum(1 for s in stages.values() if not s.get("success")),
            "total_warnings": len(self.report["warnings"]),
            "total_errors": len(self.report["errors"]),
            "total_artifacts": len(self.report["artifacts"]),
            "input_disks": load_result.get("disks_count", 0),
            "output_disks": len(self.report["artifacts"]),
        }

        return self.report

    def _get_hyper2kvm_version(self) -> str:
        """Get hyper2kvm version."""
        try:
            # __version__ may not be defined on hyper2kvm.orchestration; keep this import scoped to
            # the try/except so a missing attribute here doesn't fail module import for callers who
            # never need the version string
            # pylint: disable-next=import-outside-toplevel,cyclic-import
            from hyper2kvm.orchestration import __version__

            return __version__
        except ImportError:
            return "unknown"

    def write_json(self, path: Path | str) -> None:
        """Write report to JSON file."""
        path = Path(path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.report, f, indent=2)
        self.logger.info(f"📊 Report written: {path}")

    def to_json(self) -> str:
        """Return report as JSON string."""
        return json.dumps(self.report, indent=2)
