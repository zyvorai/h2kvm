#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Advanced Analytics Report Generator

Aggregates results from multiple tool runs to generate:
- Trend analysis over time
- Cross-VM security comparison
- Migration readiness dashboard
- Compliance tracking
- Performance metrics

Usage:
    python3 analytics_report_generator.py [--format html|json|markdown]

Example:
    python3 analytics_report_generator.py --format html
"""

import sys
import json
import glob
from pathlib import Path
from typing import Any
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))


class AnalyticsReportGenerator:
    """Generate comprehensive analytics from tool outputs."""

    def __init__(self):
        self.forensic_reports = []
        self.readiness_reports = []
        self.security_reports = []
        self.comparison_reports = []
        self.benchmark_reports = []

    def collect_reports(self):
        """Collect all available report files from /tmp."""
        print("Collecting report files...")

        # Forensic analysis reports
        for report_file in glob.glob("/tmp/forensic_analysis_report*.json"):
            try:
                with open(report_file) as f:
                    data = json.load(f)
                    data["_file"] = report_file
                    data["_timestamp"] = Path(report_file).stat().st_mtime
                    self.forensic_reports.append(data)
            except Exception:
                pass

        # Migration readiness reports
        for report_file in glob.glob("/tmp/migration_readiness_*.json"):
            try:
                with open(report_file) as f:
                    data = json.load(f)
                    data["_file"] = report_file
                    data["_timestamp"] = Path(report_file).stat().st_mtime
                    self.readiness_reports.append(data)
            except Exception:
                pass

        # Security audit reports
        for report_file in glob.glob("/tmp/security_audit_*.json"):
            try:
                with open(report_file) as f:
                    data = json.load(f)
                    data["_file"] = report_file
                    data["_timestamp"] = Path(report_file).stat().st_mtime
                    self.security_reports.append(data)
            except Exception:
                pass

        # Comparison reports
        for report_file in glob.glob("/tmp/systemd_comparison_report*.json"):
            try:
                with open(report_file) as f:
                    data = json.load(f)
                    data["_file"] = report_file
                    data["_timestamp"] = Path(report_file).stat().st_mtime
                    self.comparison_reports.append(data)
            except Exception:
                pass

        # Benchmark reports
        for report_file in glob.glob("/tmp/systemd_tools_benchmark*.json"):
            try:
                with open(report_file) as f:
                    data = json.load(f)
                    data["_file"] = report_file
                    data["_timestamp"] = Path(report_file).stat().st_mtime
                    self.benchmark_reports.append(data)
            except Exception:
                pass

        print(f"  Found {len(self.forensic_reports)} forensic reports")
        print(f"  Found {len(self.readiness_reports)} readiness reports")
        print(f"  Found {len(self.security_reports)} security reports")
        print(f"  Found {len(self.comparison_reports)} comparison reports")
        print(f"  Found {len(self.benchmark_reports)} benchmark reports")
        print()

    def generate_security_dashboard(self) -> dict[str, Any]:
        """Generate security compliance dashboard."""
        dashboard = {
            "total_vms_audited": len(self.security_reports),
            "vms": [],
            "overall_stats": {
                "avg_score": 0,
                "min_score": 100,
                "max_score": 0,
                "grade_distribution": defaultdict(int),
            },
        }

        if not self.security_reports:
            return dashboard

        scores = []
        for report in self.security_reports:
            vm_data = {
                "vm_name": report.get("vm_name", "unknown"),
                "score": report.get("overall_score", 0),
                "grade": report.get("grade", "F"),
                "risk_level": report.get("risk_level", "unknown"),
                "findings_count": report.get("total_findings", 0),
            }
            dashboard["vms"].append(vm_data)
            scores.append(vm_data["score"])
            dashboard["overall_stats"]["grade_distribution"][vm_data["grade"]] += 1

        # Calculate overall statistics
        if scores:
            dashboard["overall_stats"]["avg_score"] = round(sum(scores) / len(scores), 1)
            dashboard["overall_stats"]["min_score"] = min(scores)
            dashboard["overall_stats"]["max_score"] = max(scores)

        # Sort VMs by score (lowest first - needs attention)
        dashboard["vms"].sort(key=lambda x: x["score"])

        return dashboard

    def generate_migration_dashboard(self) -> dict[str, Any]:
        """Generate migration readiness dashboard."""
        dashboard = {
            "total_vms_assessed": len(self.readiness_reports),
            "ready_count": 0,
            "not_ready_count": 0,
            "risk_distribution": defaultdict(int),
            "vms": [],
        }

        if not self.readiness_reports:
            return dashboard

        for report in self.readiness_reports:
            ready = report.get("ready", False)
            risk_level = report.get("risk_level", "unknown")

            vm_data = {
                "vm_disk": report.get("vm_disk", "unknown"),
                "ready": ready,
                "risk_level": risk_level,
                "blockers": len(report.get("checks", {}).get("systemd_readiness", {}).get("blockers", [])),
                "warnings": len(report.get("checks", {}).get("systemd_readiness", {}).get("warnings", [])),
            }

            dashboard["vms"].append(vm_data)

            if ready:
                dashboard["ready_count"] += 1
            else:
                dashboard["not_ready_count"] += 1

            dashboard["risk_distribution"][risk_level] += 1

        # Sort by risk level (high risk first)
        risk_order = {"high": 0, "medium": 1, "low": 2, "minimal": 3, "unknown": 4}
        dashboard["vms"].sort(key=lambda x: risk_order.get(x["risk_level"], 99))

        return dashboard

    def generate_forensic_summary(self) -> dict[str, Any]:
        """Generate forensic analysis summary."""
        summary = {
            "total_vms_analyzed": len(self.forensic_reports),
            "total_anomalies": 0,
            "total_coredumps": 0,
            "total_failed_services": 0,
            "vms_with_issues": [],
        }

        if not self.forensic_reports:
            return summary

        for report in self.forensic_reports:
            summary_data = report.get("summary", {})

            anomalies = summary_data.get("anomalies_found", 0)
            coredumps = summary_data.get("core_dumps", 0)
            failed_services = summary_data.get("failed_services", 0)

            summary["total_anomalies"] += anomalies
            summary["total_coredumps"] += coredumps
            summary["total_failed_services"] += failed_services

            # Track VMs with issues
            if anomalies > 0 or coredumps > 0 or failed_services > 0:
                summary["vms_with_issues"].append(
                    {
                        "machine_id": summary_data.get("machine_id", "unknown"),
                        "anomalies": anomalies,
                        "coredumps": coredumps,
                        "failed_services": failed_services,
                    }
                )

        return summary

    def generate_performance_metrics(self) -> dict[str, Any]:
        """Generate performance metrics from benchmarks."""
        metrics = {
            "benchmarks_run": len(self.benchmark_reports),
            "total_tests": 0,
            "successful_tests": 0,
            "failed_tests": 0,
            "tool_performance": {},
        }

        if not self.benchmark_reports:
            return metrics

        # Aggregate from all benchmark runs
        for report in self.benchmark_reports:
            metrics["total_tests"] += report.get("total_tests", 0)
            metrics["successful_tests"] += report.get("successful_tests", 0)
            metrics["failed_tests"] += report.get("failed_tests", 0)

            # Aggregate tool statistics
            for tool_name, stats in report.get("tool_statistics", {}).items():
                if tool_name not in metrics["tool_performance"]:
                    metrics["tool_performance"][tool_name] = {
                        "total_runs": 0,
                        "avg_time": 0,
                        "avg_memory": 0,
                        "avg_throughput": 0,
                    }

                perf = metrics["tool_performance"][tool_name]
                perf["total_runs"] += stats.get("count", 0)
                perf["avg_time"] += stats.get("avg_time", 0)
                perf["avg_memory"] += stats.get("avg_memory", 0)
                perf["avg_throughput"] += stats.get("avg_throughput", 0)

        # Average the aggregated metrics
        num_reports = len(self.benchmark_reports)
        for tool_name, perf in metrics["tool_performance"].items():
            perf["avg_time"] = round(perf["avg_time"] / num_reports, 2)
            perf["avg_memory"] = round(perf["avg_memory"] / num_reports, 2)
            perf["avg_throughput"] = round(perf["avg_throughput"] / num_reports, 3)

        return metrics

    def generate_markdown_report(self) -> str:
        """Generate comprehensive markdown report."""
        security_dash = self.generate_security_dashboard()
        migration_dash = self.generate_migration_dashboard()
        forensic_sum = self.generate_forensic_summary()
        perf_metrics = self.generate_performance_metrics()

        report = f"""# hyper2kvm Analytics Report

**Generated**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---

## Executive Summary

| Metric | Value |
|--------|-------|
| VMs Audited (Security) | {security_dash["total_vms_audited"]} |
| VMs Assessed (Migration) | {migration_dash["total_vms_assessed"]} |
| VMs Analyzed (Forensics) | {forensic_sum["total_vms_analyzed"]} |
| Benchmark Runs | {perf_metrics["benchmarks_run"]} |

---

## Security Compliance Dashboard

**Overall Statistics:**
- Average Security Score: **{security_dash["overall_stats"]["avg_score"]}/100**
- Score Range: {security_dash["overall_stats"]["min_score"]}-{security_dash["overall_stats"]["max_score"]}
- Grade Distribution: {dict(security_dash["overall_stats"]["grade_distribution"])}

**VMs Needing Attention** (lowest scores first):

| VM Name | Score | Grade | Risk Level | Findings |
|---------|-------|-------|------------|----------|
"""

        for vm in security_dash["vms"][:10]:  # Top 10 needing attention
            report += f"| {vm['vm_name'][:40]} | {vm['score']} | {vm['grade']} | {vm['risk_level']} | {vm['findings_count']} |\n"

        report += f"""
---

## Migration Readiness Dashboard

**Status Overview:**
- ✅ Ready for Migration: **{migration_dash["ready_count"]}**
- ❌ Not Ready: **{migration_dash["not_ready_count"]}**
- Risk Distribution: {dict(migration_dash["risk_distribution"])}

**VMs by Risk Level:**

| VM | Ready | Risk Level | Blockers | Warnings |
|----|-------|------------|----------|----------|
"""

        for vm in migration_dash["vms"][:15]:
            ready_icon = "✅" if vm["ready"] else "❌"
            vm_name = Path(vm["vm_disk"]).stem[:35]
            report += (
                f"| {vm_name} | {ready_icon} | {vm['risk_level']} | {vm['blockers']} | {vm['warnings']} |\n"
            )

        report += f"""
---

## Forensic Analysis Summary

**Issues Detected:**
- Total Anomalies: **{forensic_sum["total_anomalies"]}**
- Total Core Dumps: **{forensic_sum["total_coredumps"]}**
- Total Failed Services: **{forensic_sum["total_failed_services"]}**

**VMs with Issues:**

"""

        if forensic_sum["vms_with_issues"]:
            report += "| Machine ID | Anomalies | Core Dumps | Failed Services |\n"
            report += "|------------|-----------|------------|------------------|\n"
            for vm in forensic_sum["vms_with_issues"][:10]:
                machine_id = vm["machine_id"][:20] if vm["machine_id"] else "unknown"
                report += (
                    f"| {machine_id} | {vm['anomalies']} | {vm['coredumps']} | {vm['failed_services']} |\n"
                )
        else:
            report += "✅ No VMs with anomalies, crashes, or failed services detected.\n"

        report += f"""
---

## Performance Metrics

**Benchmark Summary:**
- Total Tests Run: {perf_metrics["total_tests"]}
- Successful: {perf_metrics["successful_tests"]}
- Failed: {perf_metrics["failed_tests"]}

**Tool Performance:**

| Tool | Avg Time | Avg Memory | Throughput |
|------|----------|------------|------------|
"""

        for tool_name, perf in perf_metrics.get("tool_performance", {}).items():
            report += f"| {tool_name[:30]} | {perf['avg_time']:.2f}s | {perf['avg_memory']:.1f} MB | {perf['avg_throughput']:.3f} GB/s |\n"

        report += """
---

## Recommendations

### Security Improvements
"""

        # Security recommendations based on scores
        low_score_vms = [vm for vm in security_dash["vms"] if vm["score"] < 70]
        if low_score_vms:
            report += f"\n**{len(low_score_vms)} VMs** have security scores below 70:\n"
            for vm in low_score_vms[:5]:
                report += f"- {vm['vm_name']}: Score {vm['score']} (Grade {vm['grade']})\n"
            report += "\n**Action**: Run security audit with `--format html` for detailed findings.\n"
        else:
            report += "\n✅ All VMs meet minimum security requirements.\n"

        report += "\n### Migration Readiness\n"

        # Migration recommendations
        not_ready_vms = [vm for vm in migration_dash["vms"] if not vm["ready"]]
        if not_ready_vms:
            report += f"\n**{len(not_ready_vms)} VMs** are not ready for migration:\n"
            for vm in not_ready_vms[:5]:
                vm_name = Path(vm["vm_disk"]).stem
                report += f"- {vm_name}: {vm['blockers']} blocker(s)\n"
            report += "\n**Action**: Review blockers and fix before attempting migration.\n"
        else:
            high_risk_vms = [vm for vm in migration_dash["vms"] if vm["risk_level"] in ["high", "medium"]]
            if high_risk_vms:
                report += f"\n**{len(high_risk_vms)} VMs** ready but with elevated risk:\n"
                for vm in high_risk_vms[:5]:
                    vm_name = Path(vm["vm_disk"]).stem
                    report += f"- {vm_name}: {vm['risk_level']} risk, {vm['warnings']} warning(s)\n"
                report += "\n**Action**: Review warnings before migration.\n"
            else:
                report += "\n✅ All assessed VMs are ready for migration with minimal risk.\n"

        report += "\n### Forensic Follow-up\n"

        if forensic_sum["vms_with_issues"]:
            report += f"\n**{len(forensic_sum['vms_with_issues'])} VMs** need forensic attention:\n"
            report += "\n**Action**: Investigate anomalies, core dumps, and failed services.\n"
        else:
            report += "\n✅ No VMs require forensic investigation.\n"

        report += """
---

## Next Steps

1. **Security**: Address low-scoring VMs (< 70)
2. **Migration**: Fix blockers on VMs marked as not ready
3. **Forensics**: Investigate VMs with anomalies or crashes
4. **Performance**: Monitor trends across multiple benchmark runs

---

*Report generated by hyper2kvm analytics engine*
"""

        return report

    def generate_json_report(self) -> dict[str, Any]:
        """Generate JSON report with all analytics."""
        return {
            "generated_at": datetime.now().isoformat(),
            "security_dashboard": self.generate_security_dashboard(),
            "migration_dashboard": self.generate_migration_dashboard(),
            "forensic_summary": self.generate_forensic_summary(),
            "performance_metrics": self.generate_performance_metrics(),
        }

    def generate_html_report(self) -> str:
        """Generate HTML report with styling."""
        security_dash = self.generate_security_dashboard()
        migration_dash = self.generate_migration_dashboard()
        forensic_sum = self.generate_forensic_summary()
        perf_metrics = self.generate_performance_metrics()

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>hyper2kvm Analytics Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            border-radius: 10px;
            margin-bottom: 30px;
        }}
        .header h1 {{ margin: 0 0 10px 0; }}
        .header p {{ margin: 0; opacity: 0.9; }}
        .dashboard {{
            background: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .dashboard h2 {{
            margin-top: 0;
            color: #333;
            border-bottom: 3px solid #667eea;
            padding-bottom: 10px;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .stat-card {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }}
        .stat-value {{
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
        }}
        .stat-label {{
            color: #666;
            margin-top: 5px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th {{
            background: #667eea;
            color: white;
            padding: 12px;
            text-align: left;
        }}
        td {{
            padding: 10px 12px;
            border-bottom: 1px solid #eee;
        }}
        tr:hover {{
            background: #f8f9fa;
        }}
        .grade-A {{ color: #28a745; font-weight: bold; }}
        .grade-B {{ color: #17a2b8; font-weight: bold; }}
        .grade-C {{ color: #ffc107; font-weight: bold; }}
        .grade-D {{ color: #fd7e14; font-weight: bold; }}
        .grade-F {{ color: #dc3545; font-weight: bold; }}
        .risk-minimal {{ color: #28a745; }}
        .risk-low {{ color: #17a2b8; }}
        .risk-medium {{ color: #ffc107; }}
        .risk-high {{ color: #dc3545; }}
        .ready-yes {{ color: #28a745; }}
        .ready-no {{ color: #dc3545; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 hyper2kvm Analytics Report</h1>
        <p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    </div>

    <div class="dashboard">
        <h2>📊 Executive Summary</h2>
        <div class="stats">
            <div class="stat-card">
                <div class="stat-value">{security_dash["total_vms_audited"]}</div>
                <div class="stat-label">VMs Audited (Security)</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{migration_dash["total_vms_assessed"]}</div>
                <div class="stat-label">VMs Assessed (Migration)</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{forensic_sum["total_vms_analyzed"]}</div>
                <div class="stat-label">VMs Analyzed (Forensics)</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{perf_metrics["benchmarks_run"]}</div>
                <div class="stat-label">Benchmark Runs</div>
            </div>
        </div>
    </div>

    <div class="dashboard">
        <h2>🔒 Security Compliance Dashboard</h2>
        <div class="stats">
            <div class="stat-card">
                <div class="stat-value">{security_dash["overall_stats"]["avg_score"]}</div>
                <div class="stat-label">Average Security Score</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{security_dash["overall_stats"]["min_score"]}-{security_dash["overall_stats"]["max_score"]}</div>
                <div class="stat-label">Score Range</div>
            </div>
        </div>

        <h3>VMs Needing Attention</h3>
        <table>
            <tr>
                <th>VM Name</th>
                <th>Score</th>
                <th>Grade</th>
                <th>Risk Level</th>
                <th>Findings</th>
            </tr>
"""

        for vm in security_dash["vms"][:10]:
            html += f"""
            <tr>
                <td>{vm["vm_name"][:50]}</td>
                <td>{vm["score"]}/100</td>
                <td><span class="grade-{vm["grade"]}">{vm["grade"]}</span></td>
                <td><span class="risk-{vm["risk_level"]}">{vm["risk_level"]}</span></td>
                <td>{vm["findings_count"]}</td>
            </tr>
"""

        html += f"""
        </table>
    </div>

    <div class="dashboard">
        <h2>🚀 Migration Readiness Dashboard</h2>
        <div class="stats">
            <div class="stat-card">
                <div class="stat-value ready-yes">{migration_dash["ready_count"]}</div>
                <div class="stat-label">Ready for Migration</div>
            </div>
            <div class="stat-card">
                <div class="stat-value ready-no">{migration_dash["not_ready_count"]}</div>
                <div class="stat-label">Not Ready</div>
            </div>
        </div>

        <h3>VMs by Risk Level</h3>
        <table>
            <tr>
                <th>VM</th>
                <th>Status</th>
                <th>Risk Level</th>
                <th>Blockers</th>
                <th>Warnings</th>
            </tr>
"""

        for vm in migration_dash["vms"][:15]:
            ready_icon = "✅" if vm["ready"] else "❌"
            vm_name = Path(vm["vm_disk"]).stem[:40]
            html += f"""
            <tr>
                <td>{vm_name}</td>
                <td>{ready_icon}</td>
                <td><span class="risk-{vm["risk_level"]}">{vm["risk_level"]}</span></td>
                <td>{vm["blockers"]}</td>
                <td>{vm["warnings"]}</td>
            </tr>
"""

        html += """
        </table>
    </div>

</body>
</html>
"""

        return html


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate analytics report from tool outputs")
    parser.add_argument(
        "--format",
        choices=["html", "json", "markdown"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    args = parser.parse_args()

    print("=" * 80)
    print(" hyper2kvm Analytics Report Generator")
    print("=" * 80)
    print()

    # Collect and analyze reports
    generator = AnalyticsReportGenerator()
    generator.collect_reports()

    # Check if we have any reports
    total_reports = (
        len(generator.forensic_reports)
        + len(generator.readiness_reports)
        + len(generator.security_reports)
        + len(generator.comparison_reports)
        + len(generator.benchmark_reports)
    )

    if total_reports == 0:
        print("⚠ No report files found in /tmp/")
        print("\nRun some tools first:")
        print("  python3 systemd_forensic_analysis.py vm.vmdk")
        print("  python3 migration_readiness_check.py vm.vmdk")
        print("  python3 security_audit.py vm.vmdk")
        sys.exit(1)

    # Generate report in requested format
    output_file = None

    if args.format == "json":
        report_data = generator.generate_json_report()
        output_file = "/tmp/analytics_report.json"
        with open(output_file, "w") as f:
            json.dump(report_data, f, indent=2)
        print(f"📄 JSON report saved: {output_file}")

    elif args.format == "html":
        report_html = generator.generate_html_report()
        output_file = "/tmp/analytics_report.html"
        with open(output_file, "w") as f:
            f.write(report_html)
        print(f"📄 HTML report saved: {output_file}")

    else:  # markdown
        report_md = generator.generate_markdown_report()
        output_file = "/tmp/analytics_report.md"
        with open(output_file, "w") as f:
            f.write(report_md)
        print(f"📄 Markdown report saved: {output_file}")
        print()
        print("Report Preview:")
        print("=" * 80)
        print(report_md[:1000])  # Show first 1000 chars
        if len(report_md) > 1000:
            print("\n... (truncated, see full report in file)")

    print()


if __name__ == "__main__":
    main()
