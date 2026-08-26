#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
images/offline-fix-vm/worker.py

Offline-fix VM worker that runs inside KubeVirt VM and executes fixers.
This is the execution plane that receives work from the controller.
"""

import sys
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# Import fixers from Phase 3
sys.path.insert(0, "/opt/offline-fix/fixers")
from fix_fstab import FstabFixer
from fix_initramfs import InitramfsFixer
from fix_grub import GrubFixer
from fix_selinux import SELinuxFixer

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class OfflineFixVMWorker:
    """VM worker that executes offline fixes."""

    def __init__(self, spec_path: str, root_mount: str, output_path: str):
        self.spec_path = Path(spec_path)
        self.root_mount = Path(root_mount)
        self.output_path = Path(output_path)

        self.spec = None
        self.results = {"success": False, "operations": [], "warnings": [], "artifacts": []}

    def run(self) -> int:
        """Execute offline-fix workflow."""
        logger.info("Offline-fix VM worker starting")
        logger.info(f"Root mount: {self.root_mount}")

        try:
            # Step 1: Load job spec
            if not self.load_spec():
                return 1

            # Step 2: Validate root mount
            if not self.validate_root_mount():
                return 1

            # Step 3: Execute fixers
            if not self.execute_fixers():
                return 1

            # Step 4: Write results
            self.write_results()

            logger.info("Offline-fix VM worker completed successfully")
            return 0

        except Exception as e:
            logger.error(f"Worker failed: {e}", exc_info=True)
            self.results["success"] = False
            self.results["error"] = str(e)
            self.write_results()
            return 1

    def load_spec(self) -> bool:
        """Load job specification from config file."""
        logger.info(f"Loading spec from {self.spec_path}")

        if not self.spec_path.exists():
            logger.error(f"Spec file not found: {self.spec_path}")
            return False

        try:
            with open(self.spec_path) as f:
                self.spec = json.load(f)

            logger.info(f"Loaded spec for job: {self.spec.get('job_id', 'unknown')}")
            logger.info(f"Requested fixes: {self.spec.get('fixes', [])}")
            return True

        except Exception as e:
            logger.error(f"Failed to load spec: {e}")
            return False

    def validate_root_mount(self) -> bool:
        """Validate that root filesystem is mounted."""
        logger.info("Validating root mount")

        if not self.root_mount.exists():
            logger.error(f"Root mount does not exist: {self.root_mount}")
            return False

        etc_path = self.root_mount / "etc"
        if not etc_path.is_dir():
            logger.error(f"Root mount does not contain /etc: {self.root_mount}")
            return False

        logger.info("Root mount validated")
        return True

    def execute_fixers(self) -> bool:
        """Execute requested fixers."""
        logger.info("Executing fixers")

        fixes = self.spec.get("fixes", [])
        if not fixes:
            logger.warning("No fixes requested")
            return True

        # Execute each fixer
        for fix_name in fixes:
            logger.info(f"Executing fixer: {fix_name}")

            try:
                result = self.execute_single_fixer(fix_name)
                self.results["operations"].append(result)

                if not result["success"]:
                    logger.error(f"Fixer failed: {fix_name}")
                    # Continue with other fixers even if one fails

            except Exception as e:
                logger.error(f"Fixer {fix_name} raised exception: {e}", exc_info=True)
                self.results["operations"].append({"operation": fix_name, "success": False, "error": str(e)})

        # Overall success if at least one fixer succeeded
        any_success = any(op["success"] for op in self.results["operations"])
        self.results["success"] = any_success

        return True

    def execute_single_fixer(self, fix_name: str) -> Dict[str, Any]:
        """Execute a single fixer and return result."""
        start_time = datetime.now()

        # Safety parameters
        safety = self.spec.get("safety", {})
        dry_run = safety.get("readOnly", False)

        try:
            if fix_name == "fstab":
                fixer = FstabFixer(root_mount=str(self.root_mount), dry_run=dry_run)
                result = fixer.fix()

            elif fix_name == "initramfs":
                add_lvm = self.spec.get("parameters", {}).get("addLVM", True)
                fixer = InitramfsFixer(root_mount=str(self.root_mount), add_lvm=add_lvm, dry_run=dry_run)
                result = fixer.fix()

            elif fix_name == "grub":
                boot_disk = self.spec.get("parameters", {}).get("bootDisk", "/dev/vda")
                fixer = GrubFixer(root_mount=str(self.root_mount), boot_disk=boot_disk, dry_run=dry_run)
                result = fixer.fix()

            elif fix_name == "selinux":
                fixer = SELinuxFixer(root_mount=str(self.root_mount), dry_run=dry_run)
                result = fixer.fix()

            else:
                return {"operation": fix_name, "success": False, "error": f"Unknown fixer: {fix_name}"}

            # Calculate duration
            duration = (datetime.now() - start_time).total_seconds()

            # Format result
            return {
                "operation": fix_name,
                "success": result.get("success", False),
                "message": result.get("message", ""),
                "durationSeconds": duration,
                "details": result.get("stats", {}),
            }

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return {"operation": fix_name, "success": False, "error": str(e), "durationSeconds": duration}

    def write_results(self):
        """Write results to output file."""
        logger.info(f"Writing results to {self.output_path}")

        try:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.output_path, "w") as f:
                json.dump(self.results, f, indent=2)

            logger.info("Results written successfully")

        except Exception as e:
            logger.error(f"Failed to write results: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Offline-fix VM worker")
    parser.add_argument("--spec", required=True, help="Path to job spec JSON")
    parser.add_argument("--root", required=True, help="Guest root mount point")
    parser.add_argument("--output", required=True, help="Path to write results JSON")

    args = parser.parse_args()

    worker = OfflineFixVMWorker(spec_path=args.spec, root_mount=args.root, output_path=args.output)

    sys.exit(worker.run())


if __name__ == "__main__":
    main()
