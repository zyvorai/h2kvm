#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
VM Security Audit Tool

Comprehensive security audit of VM using systemd forensic capabilities.
Checks for misconfigurations, vulnerabilities, and compliance issues.

Usage:
    python3 security_audit.py <disk-image> [--format json|html|text]

Example:
    python3 security_audit.py /path/to/vm.qcow2 --format html
"""

import sys
import json
from pathlib import Path
from datetime import datetime
import argparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from h2kvm.vmcraft.main import VMCraft


class SecurityAuditor:
    """Comprehensive VM security auditor."""

    def __init__(self, disk_path: str):
        self.disk_path = Path(disk_path)
        self.g = VMCraft()
        self.findings = []
        self.report = {
            "timestamp": datetime.now().isoformat(),
            "vm_disk": str(self.disk_path),
            "overall_score": 0,
            "risk_level": "unknown",
            "categories": {},
        }

    def run(self) -> dict:
        """Run comprehensive security audit."""
        try:
            print(f"🔍 Security Audit: {self.disk_path.name}\n")

            self.g.add_drive_opts(str(self.disk_path), readonly=True)
            self.g.launch()

            # Run all security checks
            self._audit_systemd_security()
            self._audit_compliance()
            self._audit_anomalies()
            self._audit_user_security()
            self._audit_network_security()
            self._audit_boot_security()

            # Calculate overall score
            self._calculate_overall_score()

            return self.report

        finally:
            self.g.shutdown()

    def _audit_systemd_security(self):
        """Audit systemd service security hardening."""
        print("=" * 70)
        print(" CATEGORY 1: systemd Service Security")
        print("=" * 70)

        security = self.g.systemd_analyze_security_offline()

        if not security:
            print("ℹ No systemd security data available (offline VM)\n")
            self.report["categories"]["systemd_security"] = {
                "score": "N/A",
                "services_analyzed": 0,
                "findings": [],
            }
            return

        # Analyze exposure levels
        high_exposure = [
            s
            for s in security
            if float(s.get("exposure", "0") if s.get("exposure", "0").replace(".", "").isdigit() else "0")
            >= 9.0
        ]
        medium_exposure = [
            s
            for s in security
            if 5.0
            <= float(s.get("exposure", "0") if s.get("exposure", "0").replace(".", "").isdigit() else "0")
            < 9.0
        ]
        low_exposure = [
            s
            for s in security
            if float(s.get("exposure", "0") if s.get("exposure", "0").replace(".", "").isdigit() else "0")
            < 5.0
        ]

        print(f"Services Analyzed: {len(security)}")
        print(f"  High Exposure (>=9.0):   {len(high_exposure)}")
        print(f"  Medium Exposure (5-9):   {len(medium_exposure)}")
        print(f"  Low Exposure (<5.0):     {len(low_exposure)}")

        if high_exposure:
            print(f"\n🚨 HIGH EXPOSURE SERVICES:")
            for svc in high_exposure[:5]:
                print(f"  • {svc['unit']:40} {svc['exposure']:>6} {svc['predicate']}")
                self.findings.append(
                    {
                        "category": "systemd_security",
                        "severity": "high",
                        "service": svc["unit"],
                        "issue": f"High security exposure: {svc['exposure']}",
                        "recommendation": "Review service hardening options",
                    }
                )

        # Calculate category score
        if security:
            avg_exposure = sum(
                float(s.get("exposure", "0") if s.get("exposure", "0").replace(".", "").isdigit() else "0")
                for s in security
            ) / len(security)
            score = max(0, 100 - int(avg_exposure * 10))
        else:
            score = 0

        self.report["categories"]["systemd_security"] = {
            "score": score,
            "services_analyzed": len(security),
            "high_exposure": len(high_exposure),
            "findings": self.findings[-len(high_exposure) :] if high_exposure else [],
        }

        print(f"\nCategory Score: {score}/100\n")

    def _audit_compliance(self):
        """Audit against security compliance standards."""
        print("=" * 70)
        print(" CATEGORY 2: Security Compliance")
        print("=" * 70)

        compliance = self.g.systemd_security_compliance_check()

        print(f"Compliance Score: {compliance['score']}/100")
        print(f"  Checks Performed: {compliance['total_checks']}")
        print(f"  Passed:           {compliance['passed']}")
        print(f"  Failed:           {compliance['failed']}")

        if compliance["findings"]:
            print(f"\n⚠️  FINDINGS:")
            for finding in compliance["findings"]:
                severity_icon = {"high": "🚨", "medium": "⚠️", "low": "ℹ"}.get(finding["severity"], "•")
                print(
                    f"  {severity_icon} [{finding['severity'].upper()}] {finding['check']}: {finding['status']}"
                )

                self.findings.append(
                    {
                        "category": "compliance",
                        "severity": finding["severity"],
                        "check": finding["check"],
                        "status": finding["status"],
                    }
                )

        if compliance["recommendations"]:
            print(f"\n💡 RECOMMENDATIONS:")
            for rec in compliance["recommendations"][:5]:
                print(f"  • {rec}")

        self.report["categories"]["compliance"] = {
            "score": compliance["score"],
            "passed": compliance["passed"],
            "failed": compliance["failed"],
            "findings": compliance["findings"],
            "recommendations": compliance["recommendations"],
        }

        print()

    def _audit_anomalies(self):
        """Detect security anomalies and suspicious configurations."""
        print("=" * 70)
        print(" CATEGORY 3: Anomaly Detection")
        print("=" * 70)

        anomalies = self.g.systemd_detect_anomalies()

        total_anomalies = sum(len(v) for v in anomalies.values())
        print(f"Anomalies Detected: {total_anomalies}")

        findings_by_type = []

        if anomalies["hidden_units"]:
            print(f"\n🔍 HIDDEN UNITS ({len(anomalies['hidden_units'])}):")
            for unit in anomalies["hidden_units"][:5]:
                print(f"  • {unit['file']} ({unit['size']} bytes)")
                findings_by_type.append({"type": "hidden_unit", "file": unit["file"], "severity": "high"})

        if anomalies["writable_units"]:
            print(f"\n🔓 WORLD-WRITABLE UNITS ({len(anomalies['writable_units'])}):")
            for unit in anomalies["writable_units"][:5]:
                print(f"  • {unit['file']} (mode: {unit['mode']})")
                findings_by_type.append({"type": "writable_unit", "file": unit["file"], "severity": "high"})

        if anomalies["suspicious_timers"]:
            print(f"\n⏰ SUSPICIOUS TIMERS ({len(anomalies['suspicious_timers'])}):")
            for timer in anomalies["suspicious_timers"][:5]:
                print(f"  • {timer['file']}: {timer['reason']}")
                findings_by_type.append(
                    {"type": "suspicious_timer", "file": timer["file"], "severity": "medium"}
                )

        if anomalies["suspicious_sockets"]:
            print(f"\n🔌 SUSPICIOUS SOCKETS ({len(anomalies['suspicious_sockets'])}):")
            for socket in anomalies["suspicious_sockets"][:5]:
                print(f"  • {socket['file']}: {socket['address']} ({socket['reason']})")
                findings_by_type.append(
                    {
                        "type": "suspicious_socket",
                        "file": socket["file"],
                        "address": socket["address"],
                        "severity": "high",
                    }
                )

        # Calculate score (deduct points for anomalies)
        score = max(0, 100 - (total_anomalies * 5))

        self.report["categories"]["anomalies"] = {
            "score": score,
            "total": total_anomalies,
            "by_type": anomalies,
            "findings": findings_by_type,
        }

        for finding in findings_by_type:
            self.findings.append(
                {
                    "category": "anomalies",
                    "severity": finding["severity"],
                    "type": finding["type"],
                    "details": finding,
                }
            )

        print(f"\nCategory Score: {score}/100\n")

    def _audit_user_security(self):
        """Audit user and session security."""
        print("=" * 70)
        print(" CATEGORY 4: User & Session Security")
        print("=" * 70)

        sysusers = self.g.systemd_sysusers_config()
        logind = self.g.systemd_logind_config()

        print(f"System Users: {len(sysusers)} provisioned")

        # Check for users with shells
        users_with_shells = [u for u in sysusers if not u["shell"].endswith("nologin")]

        if users_with_shells:
            print(f"\n⚠️  Users with login shells: {len(users_with_shells)}")
            for user in users_with_shells[:5]:
                print(f"  • {user['name']} ({user['shell']})")

        # Check logind configuration
        print(f"\nlogind Configuration:")
        print(f"  KillUserProcesses: {logind['KillUserProcesses']}")
        print(f"  IdleAction:        {logind['IdleAction']}")

        issues = []
        if logind["KillUserProcesses"] == "no":
            issues.append("KillUserProcesses disabled (processes survive logout)")

        score = 100 - (len(users_with_shells) * 5) - (len(issues) * 10)
        score = max(0, score)

        self.report["categories"]["user_security"] = {
            "score": score,
            "system_users": len(sysusers),
            "users_with_shells": len(users_with_shells),
            "issues": issues,
        }

        print(f"\nCategory Score: {score}/100\n")

    def _audit_network_security(self):
        """Audit network configuration security."""
        print("=" * 70)
        print(" CATEGORY 5: Network Security")
        print("=" * 70)

        netconfig = self.g.systemd_networkd_config()
        dns_config = self.g.systemd_resolved_config()

        print(f"Network Configuration Files: {len(netconfig['networks'])}")

        issues = []

        # Check DNS security
        if dns_config["dnssec"] == "no":
            print(f"⚠️  DNSSEC disabled")
            issues.append("DNSSEC disabled")

        if not dns_config["dns_servers"]:
            print(f"ℹ  No custom DNS servers configured")

        # Check for hardcoded network configs (already checked in migration, but important for security)
        score = 100 - (len(issues) * 20)
        score = max(0, score)

        self.report["categories"]["network_security"] = {
            "score": score,
            "dnssec": dns_config["dnssec"],
            "issues": issues,
        }

        print(f"\nCategory Score: {score}/100\n")

    def _audit_boot_security(self):
        """Audit boot security configuration."""
        print("=" * 70)
        print(" CATEGORY 6: Boot Security")
        print("=" * 70)

        boot_entries = self.g.systemd_boot_entries()
        loader_config = self.g.systemd_boot_loader_config()

        issues = []

        if boot_entries:
            print(f"Boot Entries: {len(boot_entries)}")

            # Check for insecure boot options
            for entry in boot_entries:
                options = entry.get("options", "")
                if "init=/bin/bash" in options or "init=/bin/sh" in options:
                    issues.append(f"Insecure init in {entry['file']}")
                if "selinux=0" in options or "apparmor=0" in options:
                    issues.append(f"Security framework disabled in {entry['file']}")
        else:
            print("ℹ No systemd-boot entries (may use GRUB)")

        if issues:
            print(f"\n⚠️  ISSUES:")
            for issue in issues:
                print(f"  • {issue}")

        score = 100 - (len(issues) * 20)
        score = max(0, score)

        self.report["categories"]["boot_security"] = {
            "score": score,
            "boot_entries": len(boot_entries),
            "issues": issues,
        }

        print(f"\nCategory Score: {score}/100\n")

    def _calculate_overall_score(self):
        """Calculate weighted overall security score."""
        # Weight each category
        weights = {
            "systemd_security": 0.25,
            "compliance": 0.25,
            "anomalies": 0.20,
            "user_security": 0.15,
            "network_security": 0.10,
            "boot_security": 0.05,
        }

        total_score = 0
        total_weight = 0

        for category, weight in weights.items():
            cat_data = self.report["categories"].get(category, {})
            score = cat_data.get("score")

            if score == "N/A" or score is None:
                continue

            total_score += score * weight
            total_weight += weight

        if total_weight > 0:
            self.report["overall_score"] = int(total_score / total_weight)
        else:
            self.report["overall_score"] = 0

        # Determine risk level
        score = self.report["overall_score"]
        if score >= 90:
            self.report["risk_level"] = "minimal"
        elif score >= 75:
            self.report["risk_level"] = "low"
        elif score >= 60:
            self.report["risk_level"] = "medium"
        elif score >= 40:
            self.report["risk_level"] = "high"
        else:
            self.report["risk_level"] = "critical"

        self.report["total_findings"] = len(self.findings)

    def print_summary(self):
        """Print executive summary."""
        print("=" * 70)
        print(" SECURITY AUDIT SUMMARY")
        print("=" * 70)

        score = self.report["overall_score"]
        risk = self.report["risk_level"]

        # Overall grade
        if score >= 90:
            grade, icon = "A", "🟢"
        elif score >= 75:
            grade, icon = "B", "🟡"
        elif score >= 60:
            grade, icon = "C", "🟠"
        elif score >= 40:
            grade, icon = "D", "🔴"
        else:
            grade, icon = "F", "🔴"

        print(f"\nOverall Security Score: {score}/100 (Grade: {grade}) {icon}")
        print(f"Risk Level: {risk.upper()}")
        print(f"Total Findings: {self.report['total_findings']}")

        # Category breakdown
        print(f"\nCategory Scores:")
        for category, data in self.report["categories"].items():
            score = data.get("score", "N/A")
            score_str = f"{score}/100" if isinstance(score, int) else score
            print(f"  {category:20} {score_str:>10}")

        # Top findings
        if self.findings:
            print(f"\nTop Security Findings:")
            high_severity = [f for f in self.findings if f.get("severity") == "high"]
            for finding in high_severity[:5]:
                print(
                    f"  🚨 [{finding['category']}] {finding.get('issue', finding.get('check', 'Security issue'))}"
                )

        # Recommendations
        print(f"\nRecommendations:")
        if score < 60:
            print("  • Immediate action required to improve security posture")
            print("  • Review all high-severity findings")
            print("  • Consider security hardening guide")
        elif score < 75:
            print("  • Address high and medium severity findings")
            print("  • Enable additional security features")
        elif score < 90:
            print("  • Fine-tune security configurations")
            print("  • Address remaining findings")
        else:
            print("  • Maintain current security posture")
            print("  • Regular security audits recommended")

        print()

    def save_report(self, format: str = "json"):
        """Save audit report in specified format."""
        stem = self.disk_path.stem
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if format == "json":
            output_file = f"/tmp/security_audit_{stem}_{timestamp}.json"
            with open(output_file, "w") as f:
                json.dump(self.report, f, indent=2)

        elif format == "html":
            output_file = f"/tmp/security_audit_{stem}_{timestamp}.html"
            self._generate_html_report(output_file)

        else:  # text
            output_file = f"/tmp/security_audit_{stem}_{timestamp}.txt"
            # Text report already printed to console
            with open(output_file, "w") as f:
                f.write(f"Security Audit Report\n")
                f.write(f"Generated: {self.report['timestamp']}\n")
                f.write(f"VM: {self.report['vm_disk']}\n")
                f.write(f"Overall Score: {self.report['overall_score']}/100\n")
                f.write(f"Risk Level: {self.report['risk_level']}\n")

        print(f"📄 Report saved: {output_file}")

    def _generate_html_report(self, output_file: str):
        """Generate HTML audit report."""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Security Audit Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; }}
        h1 {{ color: #333; border-bottom: 3px solid #007bff; padding-bottom: 10px; }}
        .score {{ font-size: 48px; font-weight: bold; text-align: center; margin: 20px 0; }}
        .grade-A {{ color: #28a745; }}
        .grade-B {{ color: #ffc107; }}
        .grade-C {{ color: #fd7e14; }}
        .grade-D, .grade-F {{ color: #dc3545; }}
        .category {{ margin: 20px 0; padding: 15px; background: #f8f9fa; border-left: 4px solid #007bff; }}
        .finding {{ padding: 10px; margin: 5px 0; border-left: 3px solid #ffc107; background: #fff3cd; }}
        .high {{ border-left-color: #dc3545; background: #f8d7da; }}
        .medium {{ border-left-color: #ffc107; background: #fff3cd; }}
        .low {{ border-left-color: #17a2b8; background: #d1ecf1; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔒 Security Audit Report</h1>
        <p><strong>VM:</strong> {self.report["vm_disk"]}</p>
        <p><strong>Generated:</strong> {self.report["timestamp"]}</p>

        <div class="score grade-{self._get_grade()}">
            {self.report["overall_score"]}/100
            <br><small>Grade: {self._get_grade()}</small>
        </div>

        <p style="text-align: center;"><strong>Risk Level:</strong> {self.report["risk_level"].upper()}</p>

        <h2>Category Scores</h2>
        {
            "".join(
                f'<div class="category"><strong>{cat}</strong>: {data.get("score", "N/A")}/100</div>'
                for cat, data in self.report["categories"].items()
            )
        }

        <h2>Findings ({self.report["total_findings"]})</h2>
        {
            "".join(
                f'<div class="finding {f.get("severity", "low")}">[{f.get("severity", "").upper()}] {f.get("issue", f.get("check", ""))}</div>'
                for f in self.findings[:20]
            )
        }

        <p style="margin-top: 30px; text-align: center; color: #666;">
            Generated by h2kvm Security Auditor
        </p>
    </div>
</body>
</html>"""

        with open(output_file, "w") as f:
            f.write(html)

    def _get_grade(self) -> str:
        """Get letter grade from score."""
        score = self.report["overall_score"]
        if score >= 90:
            return "A"
        elif score >= 75:
            return "B"
        elif score >= 60:
            return "C"
        elif score >= 40:
            return "D"
        else:
            return "F"


def main():
    parser = argparse.ArgumentParser(description="VM Security Audit Tool")
    parser.add_argument("disk_image", help="Path to disk image")
    parser.add_argument(
        "--format", choices=["json", "html", "text"], default="text", help="Output format (default: text)"
    )

    args = parser.parse_args()

    if not Path(args.disk_image).exists():
        print(f"Error: Disk image not found: {args.disk_image}")
        sys.exit(1)

    auditor = SecurityAuditor(args.disk_image)
    auditor.run()
    auditor.print_summary()
    auditor.save_report(args.format)


if __name__ == "__main__":
    main()
