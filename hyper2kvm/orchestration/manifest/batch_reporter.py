# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Batch reporter - generates aggregate batch_report.json for multi-VM conversions."""

from __future__ import annotations

import datetime
import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


class BatchReporter:
    """Generates structured aggregate reports for batch conversions."""

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)
        self.report: dict[str, Any] = {
            "version": "1.0",
            "report_type": "batch_conversion",
            "timestamp": datetime.datetime.now().isoformat(),
            "batch": {
                "batch_id": "",
                "manifest_path": "",
                "success": False,
                "duration_seconds": 0.0,
                "total_vms": 0,
                "processed_vms": 0,
                "successful_vms": 0,
                "failed_vms": 0,
                "success_rate": 0.0,
            },
            "vm_results": [],
            "aggregate_stats": {
                "total_duration": 0.0,
                "average_duration": 0.0,
                "fastest_conversion": None,
                "slowest_conversion": None,
            },
            "warnings": [],
            "errors": [],
        }

    def set_batch_info(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # one field per batch-level counter is inherent to this setter
        self,
        batch_id: str,
        manifest_path: str,
        total_vms: int,
        processed_vms: int,
        successful_vms: int,
        failed_vms: int,
    ) -> None:
        """Set batch-level information."""
        self.report["batch"]["batch_id"] = batch_id
        self.report["batch"]["manifest_path"] = manifest_path
        self.report["batch"]["total_vms"] = total_vms
        self.report["batch"]["processed_vms"] = processed_vms
        self.report["batch"]["successful_vms"] = successful_vms
        self.report["batch"]["failed_vms"] = failed_vms

        # Calculate success rate
        if processed_vms > 0:
            self.report["batch"]["success_rate"] = round(successful_vms / processed_vms, 4)

    def set_success(self, success: bool) -> None:
        """Set overall batch success status."""
        self.report["batch"]["success"] = success

    def set_duration(self, duration: float) -> None:
        """Set batch duration in seconds."""
        self.report["batch"]["duration_seconds"] = round(duration, 2)

    def add_vm_result(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # one field per VM result attribute is inherent to this setter
        self,
        vm_id: str,
        manifest: str,
        success: bool,
        duration: float,
        error: str | None = None,
        vm_report: dict[str, Any] | None = None,
    ) -> None:
        """Add a VM conversion result to the report."""
        result = {
            "vm_id": vm_id,
            "manifest": manifest,
            "success": success,
            "duration_seconds": round(duration, 2),
            "timestamp": datetime.datetime.now().isoformat(),
        }

        if error:
            result["error"] = error

        if vm_report:
            result["pipeline_report"] = vm_report

        self.report["vm_results"].append(result)

    def add_warning(self, vm_id: str | None, message: str) -> None:
        """Add a warning."""
        self.report["warnings"].append(
            {
                "vm_id": vm_id or "batch",
                "message": message,
                "timestamp": datetime.datetime.now().isoformat(),
            }
        )

    def add_error(self, vm_id: str | None, message: str) -> None:
        """Add an error."""
        self.report["errors"].append(
            {
                "vm_id": vm_id or "batch",
                "message": message,
                "timestamp": datetime.datetime.now().isoformat(),
            }
        )

    def compute_aggregate_stats(self) -> None:
        """Compute aggregate statistics from VM results."""
        vm_results = self.report["vm_results"]

        if not vm_results:
            return

        # Compute durations
        durations = [r["duration_seconds"] for r in vm_results if r.get("success")]

        if durations:
            total_duration = sum(durations)
            average_duration = total_duration / len(durations)

            fastest_idx = durations.index(min(durations))
            slowest_idx = durations.index(max(durations))

            successful_results = [r for r in vm_results if r.get("success")]

            self.report["aggregate_stats"]["total_duration"] = round(total_duration, 2)
            self.report["aggregate_stats"]["average_duration"] = round(average_duration, 2)
            self.report["aggregate_stats"]["fastest_conversion"] = {
                "vm_id": successful_results[fastest_idx]["vm_id"],
                "duration": durations[fastest_idx],
            }
            self.report["aggregate_stats"]["slowest_conversion"] = {
                "vm_id": successful_results[slowest_idx]["vm_id"],
                "duration": durations[slowest_idx],
            }

    def generate(self) -> dict[str, Any]:
        """Generate final batch report dictionary."""
        # Compute aggregate stats before returning
        self.compute_aggregate_stats()

        # Set final batch success (all VMs must succeed)
        all_success = all(r.get("success", False) for r in self.report["vm_results"])
        self.set_success(all_success)

        return self.report

    def write_json(self, output_path: Path) -> None:
        """Write report to JSON file."""
        report = self.generate()

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            self.logger.info(f"📊 Batch report written: {output_path}")
        except Exception as e:  # pylint: disable=broad-exception-caught  # report writing is best-effort; must not abort the batch over a write failure
            self.logger.exception("Failed to write batch report: %s", e)
            self.logger.debug("💥 Batch report write exception", exc_info=True)

    def write_summary(self, output_path: Path) -> None:
        """Write human-readable summary to text file."""
        report = self.generate()
        batch = report["batch"]

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("=" * 80 + "\n")
                f.write("Batch Conversion Summary\n")
                f.write("=" * 80 + "\n\n")

                f.write(f"Batch ID: {batch['batch_id']}\n")
                f.write(f"Timestamp: {report['timestamp']}\n")
                f.write(f"Duration: {batch['duration_seconds']:.2f}s\n\n")

                f.write("Results:\n")
                f.write(f"  Total VMs: {batch['total_vms']}\n")
                f.write(f"  Processed: {batch['processed_vms']}\n")
                f.write(f"  Successful: {batch['successful_vms']}\n")
                f.write(f"  Failed: {batch['failed_vms']}\n")
                f.write(f"  Success Rate: {batch['success_rate'] * 100:.1f}%\n\n")

                # Aggregate stats
                stats = report["aggregate_stats"]
                if stats["average_duration"]:
                    f.write("Performance:\n")
                    f.write(f"  Average Duration: {stats['average_duration']:.2f}s\n")
                    # pylint: disable=unsubscriptable-object  # pylint infers "fastest/slowest_conversion" as
                    # always-None from the __init__ literal; compute_aggregate_stats() replaces it with a
                    # dict at runtime, and access here is guarded by the truthy check above.
                    if stats["fastest_conversion"]:
                        f.write(
                            f"  Fastest: {stats['fastest_conversion']['vm_id']} "
                            f"({stats['fastest_conversion']['duration']:.2f}s)\n"
                        )
                    if stats["slowest_conversion"]:
                        f.write(
                            f"  Slowest: {stats['slowest_conversion']['vm_id']} "
                            f"({stats['slowest_conversion']['duration']:.2f}s)\n"
                        )
                    f.write("\n")

                # VM details
                f.write("VM Details:\n")
                f.write("-" * 80 + "\n")
                for result in report["vm_results"]:
                    status = "✅ SUCCESS" if result["success"] else "❌ FAILED"
                    f.write(f"{status} | {result['vm_id']} | {result['duration_seconds']:.2f}s\n")
                    if result.get("error"):
                        f.write(f"  Error: {result['error']}\n")
                f.write("-" * 80 + "\n\n")

                # Warnings and errors
                if report["warnings"]:
                    f.write("Warnings:\n")
                    for warn in report["warnings"]:
                        f.write(f"  [{warn['vm_id']}] {warn['message']}\n")
                    f.write("\n")

                if report["errors"]:
                    f.write("Errors:\n")
                    for err in report["errors"]:
                        f.write(f"  [{err['vm_id']}] {err['message']}\n")
                    f.write("\n")

                f.write("=" * 80 + "\n")

            self.logger.info(f"📄 Batch summary written: {output_path}")

        except Exception as e:  # pylint: disable=broad-exception-caught  # summary writing is best-effort; must not abort the batch over a write failure
            self.logger.exception("Failed to write batch summary: %s", e)
            self.logger.debug("💥 Batch summary write exception", exc_info=True)
