#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Example: Boot Issue Debugging with systemd Journal

This script demonstrates how to debug boot issues in migrated VMs using
VMCraft's systemd journal integration.

Workflow:
1. Analyze journal logs from last boot
2. Identify failed services
3. Analyze boot performance
4. Generate diagnostic report
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

from h2kvm.vmcraft.main import VMCraft


def setup_logging():
    """Configure logging."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    return logging.getLogger(__name__)


def debug_boot_issues(vm_image_path: str):
    """
    Debug boot issues using journal logs and systemd-analyze.

    Args:
        vm_image_path: Path to VM disk image
    """
    logger = setup_logging()
    logger.info(f"Analyzing boot issues for: {vm_image_path}")

    with VMCraft(vm_image_path) as g:
        logger.info("VMCraft launched successfully")

        # =====================================================================
        # Step 1: Analyze Journal Logs from Last Boot
        # =====================================================================
        logger.info("Step 1: Analyzing journal logs from last boot...")

        # Get boot logs
        boot_logs = g.journal_get_since_boot(boot_offset=0)

        if boot_logs["ok"]:
            entry_count = boot_logs["count"]
            logger.info(f"Retrieved {entry_count} journal entries from current boot")

            # Get boot ID
            boot_id = g.journal_get_boot_id()
            logger.info(f"Boot ID: {boot_id}")
        else:
            logger.warning(f"Failed to get boot logs: {boot_logs.get('error')}")

        # List all available boots
        boots = g.journal_list_boots()
        if boots["ok"]:
            logger.info(f"Available boots: {boots['count']}")
            for boot_info in boots["boots"][:5]:  # Show last 5 boots
                logger.info(f"  {boot_info['offset']}: {boot_info['boot_id']}")

        # =====================================================================
        # Step 2: Identify Failed Services
        # =====================================================================
        logger.info("Step 2: Identifying failed services...")

        # Get all failed services
        failed_services = g.systemd_list_failed_services()

        if failed_services:
            logger.warning(f"Found {len(failed_services)} failed services:")
            for service in failed_services:
                logger.warning(f"  ✗ {service}")

                # Get service status details
                status = g.systemd_service_status(service)
                if status["ok"]:
                    logger.warning(f"    State: {status.get('active')} ({status.get('sub')})")

                # Get recent logs for this service
                service_logs = g.journal_get_service(service, lines=10)
                if service_logs["ok"] and service_logs["count"] > 0:
                    logger.warning(f"    Recent log entries:")
                    for entry in service_logs["entries"][:3]:
                        message = entry.get("MESSAGE", "")[:100]  # Truncate long messages
                        logger.warning(f"      {message}")
        else:
            logger.info("✓ No failed services detected")

        # =====================================================================
        # Step 3: Get Error and Critical Messages
        # =====================================================================
        logger.info("Step 3: Analyzing error and critical messages...")

        # Get critical errors
        critical_logs = g.journal_get_priority("crit", lines=50)
        if critical_logs["ok"]:
            crit_count = critical_logs["count"]
            if crit_count > 0:
                logger.warning(f"Found {crit_count} critical messages:")
                for entry in critical_logs["entries"][:5]:
                    unit = entry.get("UNIT", "unknown")
                    message = entry.get("MESSAGE", "")[:100]
                    logger.warning(f"  {unit}: {message}")
            else:
                logger.info("✓ No critical messages found")

        # Get error messages
        error_logs = g.journal_get_priority("err", lines=100)
        if error_logs["ok"]:
            err_count = error_logs["count"]
            logger.info(f"Found {err_count} error messages")

        # =====================================================================
        # Step 4: Analyze Boot Performance
        # =====================================================================
        logger.info("Step 4: Analyzing boot performance...")

        # Get boot performance analysis
        perf = g.units_analyze_boot_performance()
        if perf["ok"]:
            logger.info("Boot performance:")
            logger.info(f"  Kernel time: {perf.get('kernel_time', 'N/A')}")
            logger.info(f"  Userspace time: {perf.get('userspace_time', 'N/A')}")
            logger.info(f"  Total boot time: {perf.get('boot_time', 'N/A')}")
        else:
            logger.warning(f"Boot performance analysis failed: {perf.get('error')}")

        # Get critical boot path chain
        chain = g.units_analyze_critical_chain()
        if chain["ok"]:
            logger.info("Critical boot path:")
            # Show first few lines
            output_lines = chain["output"].split("\n")[:10]
            for line in output_lines:
                logger.info(f"  {line}")

        # Get blame analysis (slowest services)
        blame = g.units_analyze_blame()
        if blame["ok"]:
            logger.info(f"Slowest services (top 10):")
            for service_info in blame["services"][:10]:
                time = service_info["time"]
                name = service_info["name"]
                logger.info(f"  {time:>10} - {name}")

        # =====================================================================
        # Step 5: Check Journal Disk Usage
        # =====================================================================
        logger.info("Step 5: Checking journal disk usage...")

        usage = g.journal_get_disk_usage()
        if usage["ok"]:
            logger.info(f"Journal disk usage: {usage.get('size', 'N/A')}")
            logger.info(f"Full output: {usage.get('usage', 'N/A')}")

        # =====================================================================
        # Step 6: Generate Diagnostic Report
        # =====================================================================
        logger.info("Step 6: Generating diagnostic report...")

        # Create report
        report = []
        report.append("=" * 70)
        report.append("BOOT DIAGNOSTIC REPORT")
        report.append("=" * 70)
        report.append(f"VM Image: {vm_image_path}")
        report.append(f"Analysis Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")

        report.append("BOOT PERFORMANCE:")
        if perf["ok"]:
            report.append(f"  Kernel: {perf.get('kernel_time', 'N/A')}")
            report.append(f"  Userspace: {perf.get('userspace_time', 'N/A')}")
            report.append(f"  Total: {perf.get('boot_time', 'N/A')}")
        report.append("")

        report.append(f"FAILED SERVICES: {len(failed_services)}")
        for service in failed_services:
            report.append(f"  - {service}")
        report.append("")

        report.append(
            f"CRITICAL MESSAGES: {critical_logs.get('count', 0) if critical_logs['ok'] else 'N/A'}"
        )
        report.append(f"ERROR MESSAGES: {error_logs.get('count', 0) if error_logs['ok'] else 'N/A'}")
        report.append("")

        report.append("RECOMMENDATIONS:")
        if failed_services:
            report.append("  1. Review failed service logs and fix configuration issues")
        if critical_logs["ok"] and critical_logs["count"] > 0:
            report.append("  2. Address critical errors before production use")
        if blame["ok"] and len(blame["services"]) > 0:
            slowest = blame["services"][0]
            report.append(f"  3. Investigate slow service: {slowest['name']} ({slowest['time']})")
        if not failed_services and (not critical_logs["ok"] or critical_logs["count"] == 0):
            report.append("  ✓ No critical issues detected - VM appears healthy")

        report.append("=" * 70)

        # Print report
        for line in report:
            print(line)

    logger.info("")
    logger.info("Boot analysis completed")


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: python 03_boot_issue_debugging.py <vm_image_path>")
        print("")
        print("Example:")
        print("  python 03_boot_issue_debugging.py /path/to/rhel9-vm.qcow2")
        sys.exit(1)

    vm_image_path = sys.argv[1]

    if not Path(vm_image_path).exists():
        print(f"Error: VM image not found: {vm_image_path}")
        sys.exit(1)

    debug_boot_issues(vm_image_path)


if __name__ == "__main__":
    main()
