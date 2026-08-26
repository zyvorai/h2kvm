#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
VMCraft Migration Analytics Dashboard

Track and analyze migration metrics over time.

This tool provides:
1. Migration metrics aggregation
2. Success rate tracking
3. Performance trend analysis
4. Risk score trending
5. Production readiness tracking
6. Analytics reporting (HTML/JSON)

Usage:
    # Add migration report to analytics database
    python migration_analytics.py add migration_report_12345.json

    # Add multiple reports
    python migration_analytics.py add-batch reports/

    # Generate analytics dashboard
    python migration_analytics.py dashboard --output analytics.html

    # Show statistics
    python migration_analytics.py stats

    # Show trends
    python migration_analytics.py trends --period 30

    # Export metrics
    python migration_analytics.py export --format json --output metrics.json

Author: VMCraft Team
Version: 1.0.0
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from collections import Counter
except ImportError:
    print("ERROR: Python 3.x required")
    sys.exit(1)


class MigrationAnalytics:
    """
    Migration analytics and metrics tracking.

    Stores migration reports in SQLite database and provides analytics.
    """

    def __init__(self, db_path: str = "migration_analytics.db"):
        """
        Initialize analytics database.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_database()

    def _init_database(self) -> None:
        """Initialize database schema."""
        cursor = self.conn.cursor()

        # Migrations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                migration_id TEXT UNIQUE NOT NULL,
                timestamp TEXT NOT NULL,
                source_disk TEXT NOT NULL,
                target_disk TEXT NOT NULL,
                strategy TEXT NOT NULL,
                success INTEGER NOT NULL,
                duration_seconds REAL,
                dry_run INTEGER DEFAULT 0,
                aborted INTEGER DEFAULT 0,
                error TEXT
            )
        """)

        # Risk assessments table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS risk_assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                migration_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                overall_score INTEGER NOT NULL,
                risk_level TEXT NOT NULL,
                blocker_count INTEGER DEFAULT 0,
                recommendation_count INTEGER DEFAULT 0,
                FOREIGN KEY (migration_id) REFERENCES migrations(migration_id)
            )
        """)

        # Validation results table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS validation_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                migration_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                production_score INTEGER NOT NULL,
                readiness_level TEXT NOT NULL,
                issue_count INTEGER DEFAULT 0,
                critical_issue_count INTEGER DEFAULT 0,
                FOREIGN KEY (migration_id) REFERENCES migrations(migration_id)
            )
        """)

        # Phase results table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS phase_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                migration_id TEXT NOT NULL,
                phase_name TEXT NOT NULL,
                success INTEGER NOT NULL,
                duration_seconds REAL,
                error TEXT,
                FOREIGN KEY (migration_id) REFERENCES migrations(migration_id)
            )
        """)

        self.conn.commit()

    def add_migration_report(self, report_path: Path) -> bool:
        """
        Add migration report to analytics database.

        Args:
            report_path: Path to migration report JSON file

        Returns:
            True if added successfully
        """
        try:
            with open(report_path) as f:
                report = json.load(f)

            migration_id = report.get("migration_id")
            if not migration_id:
                print(f"WARNING: No migration_id in report {report_path}")
                return False

            # Check if already exists
            cursor = self.conn.cursor()
            cursor.execute("SELECT id FROM migrations WHERE migration_id = ?", (migration_id,))
            if cursor.fetchone():
                print(f"Migration {migration_id} already in database")
                return False

            # Insert migration record
            cursor.execute(
                """
                INSERT INTO migrations (
                    migration_id, timestamp, source_disk, target_disk,
                    strategy, success, duration_seconds, dry_run, aborted, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    migration_id,
                    report.get("timestamp", datetime.now().isoformat()),
                    report.get("source_disk", "unknown"),
                    report.get("target_disk", "unknown"),
                    report.get("strategy", "unknown"),
                    1 if report.get("success") else 0,
                    report.get("duration_seconds"),
                    1 if report.get("dry_run") else 0,
                    1 if report.get("aborted") else 0,
                    report.get("error"),
                ),
            )

            # Insert risk assessment if available
            if "readiness_assessment" in report:
                assessment = report["readiness_assessment"]
                risk_data = assessment.get("risk_assessment", {})

                cursor.execute(
                    """
                    INSERT INTO risk_assessments (
                        migration_id, timestamp, overall_score, risk_level,
                        blocker_count, recommendation_count
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        migration_id,
                        assessment.get("timestamp", report.get("timestamp")),
                        risk_data.get("overall_score", 0),
                        risk_data.get("risk_level", "UNKNOWN"),
                        len(assessment.get("blockers", [])),
                        len(assessment.get("recommendations", [])),
                    ),
                )

            # Insert validation results if available
            if "validation_report" in report:
                validation = report["validation_report"]
                readiness = validation.get("production_readiness", {})
                issues = validation.get("issues", [])

                critical_issues = sum(1 for issue in issues if issue.get("severity") == "CRITICAL")

                cursor.execute(
                    """
                    INSERT INTO validation_results (
                        migration_id, timestamp, production_score,
                        readiness_level, issue_count, critical_issue_count
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        migration_id,
                        validation.get("timestamp", report.get("timestamp")),
                        readiness.get("score", 0),
                        readiness.get("readiness", "UNKNOWN"),
                        len(issues),
                        critical_issues,
                    ),
                )

            # Insert phase results
            for phase_name, phase_data in report.get("phases", {}).items():
                cursor.execute(
                    """
                    INSERT INTO phase_results (
                        migration_id, phase_name, success,
                        duration_seconds, error
                    ) VALUES (?, ?, ?, ?, ?)
                """,
                    (
                        migration_id,
                        phase_name,
                        1 if phase_data.get("success") else 0,
                        phase_data.get("duration_seconds"),
                        phase_data.get("error"),
                    ),
                )

            self.conn.commit()
            print(f"✓ Added migration report: {migration_id}")
            return True

        except Exception as e:
            print(f"ERROR: Failed to add report {report_path}: {e}")
            return False

    def add_batch_reports(self, reports_dir: Path) -> dict[str, int]:
        """
        Add multiple migration reports from directory.

        Args:
            reports_dir: Directory containing migration report JSON files

        Returns:
            Dict with 'added' and 'failed' counts
        """
        stats = {"added": 0, "failed": 0, "skipped": 0}

        for report_file in reports_dir.glob("*.json"):
            if self.add_migration_report(report_file):
                stats["added"] += 1
            else:
                stats["failed"] += 1

        return stats

    def get_statistics(self) -> dict[str, Any]:
        """
        Get overall migration statistics.

        Returns:
            Statistics dictionary
        """
        cursor = self.conn.cursor()

        # Total migrations
        cursor.execute("SELECT COUNT(*) FROM migrations")
        total_migrations = cursor.fetchone()[0]

        # Successful migrations
        cursor.execute("SELECT COUNT(*) FROM migrations WHERE success = 1")
        successful = cursor.fetchone()[0]

        # Failed migrations
        cursor.execute("SELECT COUNT(*) FROM migrations WHERE success = 0")
        failed = cursor.fetchone()[0]

        # Success rate
        success_rate = (successful / total_migrations * 100) if total_migrations > 0 else 0

        # Average duration
        cursor.execute("""
            SELECT AVG(duration_seconds)
            FROM migrations
            WHERE duration_seconds IS NOT NULL
        """)
        avg_duration = cursor.fetchone()[0] or 0

        # Strategy breakdown
        cursor.execute("""
            SELECT strategy, COUNT(*) as count
            FROM migrations
            GROUP BY strategy
        """)
        strategies = {row["strategy"]: row["count"] for row in cursor.fetchall()}

        # Risk score statistics
        cursor.execute("""
            SELECT AVG(overall_score) as avg_score,
                   MIN(overall_score) as min_score,
                   MAX(overall_score) as max_score
            FROM risk_assessments
        """)
        risk_stats = cursor.fetchone()

        # Production readiness statistics
        cursor.execute("""
            SELECT AVG(production_score) as avg_score,
                   MIN(production_score) as min_score,
                   MAX(production_score) as max_score
            FROM validation_results
        """)
        prod_stats = cursor.fetchone()

        return {
            "total_migrations": total_migrations,
            "successful_migrations": successful,
            "failed_migrations": failed,
            "success_rate": round(success_rate, 2),
            "average_duration_seconds": round(avg_duration, 2),
            "strategies": strategies,
            "risk_scores": {
                "average": round(risk_stats["avg_score"] or 0, 2),
                "min": risk_stats["min_score"] or 0,
                "max": risk_stats["max_score"] or 0,
            }
            if risk_stats
            else None,
            "production_scores": {
                "average": round(prod_stats["avg_score"] or 0, 2),
                "min": prod_stats["min_score"] or 0,
                "max": prod_stats["max_score"] or 0,
            }
            if prod_stats
            else None,
        }

    def get_trends(self, days: int = 30) -> dict[str, Any]:
        """
        Get migration trends for specified period.

        Args:
            days: Number of days to analyze

        Returns:
            Trends dictionary
        """
        cursor = self.conn.cursor()
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        # Migrations per day
        cursor.execute(
            """
            SELECT DATE(timestamp) as day, COUNT(*) as count
            FROM migrations
            WHERE timestamp >= ?
            GROUP BY DATE(timestamp)
            ORDER BY day
        """,
            (cutoff_date,),
        )
        migrations_per_day = [{"date": row["day"], "count": row["count"]} for row in cursor.fetchall()]

        # Success rate trend
        cursor.execute(
            """
            SELECT DATE(timestamp) as day,
                   SUM(success) as successful,
                   COUNT(*) as total
            FROM migrations
            WHERE timestamp >= ?
            GROUP BY DATE(timestamp)
            ORDER BY day
        """,
            (cutoff_date,),
        )
        success_trend = [
            {"date": row["day"], "success_rate": round(row["successful"] / row["total"] * 100, 2)}
            for row in cursor.fetchall()
        ]

        # Average duration trend
        cursor.execute(
            """
            SELECT DATE(timestamp) as day,
                   AVG(duration_seconds) as avg_duration
            FROM migrations
            WHERE timestamp >= ? AND duration_seconds IS NOT NULL
            GROUP BY DATE(timestamp)
            ORDER BY day
        """,
            (cutoff_date,),
        )
        duration_trend = [
            {"date": row["day"], "avg_duration": round(row["avg_duration"], 2)} for row in cursor.fetchall()
        ]

        return {
            "period_days": days,
            "migrations_per_day": migrations_per_day,
            "success_rate_trend": success_trend,
            "duration_trend": duration_trend,
        }

    def get_phase_statistics(self) -> dict[str, Any]:
        """
        Get statistics for migration phases.

        Returns:
            Phase statistics dictionary
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT phase_name,
                   COUNT(*) as total,
                   SUM(success) as successful,
                   AVG(duration_seconds) as avg_duration
            FROM phase_results
            GROUP BY phase_name
        """)

        phases = {}
        for row in cursor.fetchall():
            phase_name = row["phase_name"]
            total = row["total"]
            successful = row["successful"]
            success_rate = (successful / total * 100) if total > 0 else 0

            phases[phase_name] = {
                "total_executions": total,
                "successful": successful,
                "failed": total - successful,
                "success_rate": round(success_rate, 2),
                "avg_duration_seconds": round(row["avg_duration"] or 0, 2),
            }

        return phases

    def generate_html_dashboard(self, output_path: Path) -> None:
        """
        Generate HTML dashboard with analytics.

        Args:
            output_path: Path to output HTML file
        """
        stats = self.get_statistics()
        trends = self.get_trends(days=30)
        phase_stats = self.get_phase_statistics()

        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VMCraft Migration Analytics Dashboard</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #f5f5f5;
            padding: 20px;
            color: #333;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            margin-bottom: 10px;
            font-size: 32px;
        }}
        .subtitle {{
            color: #7f8c8d;
            margin-bottom: 30px;
            font-size: 16px;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}
        .metric-card {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 6px;
            border-left: 4px solid #3498db;
        }}
        .metric-card.success {{
            border-left-color: #27ae60;
        }}
        .metric-card.warning {{
            border-left-color: #f39c12;
        }}
        .metric-card.danger {{
            border-left-color: #e74c3c;
        }}
        .metric-label {{
            color: #7f8c8d;
            font-size: 14px;
            margin-bottom: 8px;
        }}
        .metric-value {{
            font-size: 32px;
            font-weight: bold;
            color: #2c3e50;
        }}
        .metric-unit {{
            font-size: 14px;
            color: #7f8c8d;
            margin-left: 5px;
        }}
        .section {{
            margin-bottom: 40px;
        }}
        .section-title {{
            font-size: 24px;
            color: #2c3e50;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #ecf0f1;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ecf0f1;
        }}
        th {{
            background: #f8f9fa;
            color: #2c3e50;
            font-weight: 600;
        }}
        tr:hover {{
            background: #f8f9fa;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }}
        .badge.success {{
            background: #d4edda;
            color: #155724;
        }}
        .badge.warning {{
            background: #fff3cd;
            color: #856404;
        }}
        .badge.danger {{
            background: #f8d7da;
            color: #721c24;
        }}
        .progress-bar {{
            width: 100%;
            height: 8px;
            background: #ecf0f1;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 8px;
        }}
        .progress-fill {{
            height: 100%;
            background: #3498db;
            transition: width 0.3s ease;
        }}
        .timestamp {{
            color: #95a5a6;
            font-size: 14px;
            margin-top: 20px;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 VMCraft Migration Analytics</h1>
        <p class="subtitle">Migration performance metrics and trends</p>

        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">Total Migrations</div>
                <div class="metric-value">{stats["total_migrations"]}</div>
            </div>
            <div class="metric-card success">
                <div class="metric-label">Success Rate</div>
                <div class="metric-value">
                    {stats["success_rate"]}<span class="metric-unit">%</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {stats["success_rate"]}%; background: #27ae60;"></div>
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Average Duration</div>
                <div class="metric-value">
                    {int(stats["average_duration_seconds"] / 60)}<span class="metric-unit">min</span>
                </div>
            </div>
            <div class="metric-card {"success" if stats.get("production_scores", {}).get("average", 0) >= 90 else "warning"}">
                <div class="metric-label">Avg Production Score</div>
                <div class="metric-value">
                    {stats.get("production_scores", {}).get("average", 0)}<span class="metric-unit">/100</span>
                </div>
            </div>
        </div>

        <div class="section">
            <h2 class="section-title">Migration Strategies</h2>
            <table>
                <thead>
                    <tr>
                        <th>Strategy</th>
                        <th>Count</th>
                        <th>Percentage</th>
                    </tr>
                </thead>
                <tbody>
"""

        # Add strategy rows
        total = stats["total_migrations"]
        for strategy, count in sorted(stats["strategies"].items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total * 100) if total > 0 else 0
            html += f"""
                    <tr>
                        <td><strong>{strategy}</strong></td>
                        <td>{count}</td>
                        <td>
                            {percentage:.1f}%
                            <div class="progress-bar">
                                <div class="progress-fill" style="width: {percentage}%;"></div>
                            </div>
                        </td>
                    </tr>
"""

        html += """
                </tbody>
            </table>
        </div>

        <div class="section">
            <h2 class="section-title">Phase Performance</h2>
            <table>
                <thead>
                    <tr>
                        <th>Phase</th>
                        <th>Executions</th>
                        <th>Success Rate</th>
                        <th>Avg Duration</th>
                    </tr>
                </thead>
                <tbody>
"""

        # Add phase rows
        for phase_name, phase_data in sorted(phase_stats.items()):
            success_rate = phase_data["success_rate"]
            badge_class = "success" if success_rate >= 95 else "warning" if success_rate >= 80 else "danger"

            html += f"""
                    <tr>
                        <td><strong>{phase_name.replace("_", " ").title()}</strong></td>
                        <td>{phase_data["total_executions"]}</td>
                        <td>
                            <span class="badge {badge_class}">{success_rate}%</span>
                        </td>
                        <td>{phase_data["avg_duration_seconds"]:.2f}s</td>
                    </tr>
"""

        html += f"""
                </tbody>
            </table>
        </div>

        <div class="section">
            <h2 class="section-title">Quality Metrics</h2>
            <div class="metrics-grid">
                <div class="metric-card {"success" if stats.get("risk_scores", {}).get("average", 100) < 30 else "warning"}">
                    <div class="metric-label">Avg Risk Score</div>
                    <div class="metric-value">
                        {stats.get("risk_scores", {}).get("average", 0)}<span class="metric-unit">/100</span>
                    </div>
                    <div class="metric-label" style="margin-top: 10px;">Lower is better</div>
                </div>
                <div class="metric-card success">
                    <div class="metric-label">Successful Migrations</div>
                    <div class="metric-value">{stats["successful_migrations"]}</div>
                </div>
                <div class="metric-card {"danger" if stats["failed_migrations"] > 0 else "success"}">
                    <div class="metric-label">Failed Migrations</div>
                    <div class="metric-value">{stats["failed_migrations"]}</div>
                </div>
            </div>
        </div>

        <p class="timestamp">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    </div>
</body>
</html>
"""

        with open(output_path, "w") as f:
            f.write(html)

        print(f"✓ Dashboard generated: {output_path}")

    def export_metrics(self, format: str = "json") -> dict[str, Any]:
        """
        Export all metrics.

        Args:
            format: Export format ("json" or "csv")

        Returns:
            Complete metrics dictionary
        """
        return {
            "statistics": self.get_statistics(),
            "trends_30d": self.get_trends(days=30),
            "phase_statistics": self.get_phase_statistics(),
            "export_timestamp": datetime.now().isoformat(),
        }

    def close(self) -> None:
        """Close database connection."""
        self.conn.close()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="VMCraft Migration Analytics Dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Add migration report
  %(prog)s add migration_report_12345.json

  # Add all reports from directory
  %(prog)s add-batch reports/

  # Generate HTML dashboard
  %(prog)s dashboard --output analytics.html

  # Show statistics
  %(prog)s stats

  # Show 30-day trends
  %(prog)s trends --period 30

  # Export metrics to JSON
  %(prog)s export --format json --output metrics.json
        """,
    )

    parser.add_argument(
        "--db",
        default="migration_analytics.db",
        help="Path to analytics database (default: migration_analytics.db)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Add report command
    add_parser = subparsers.add_parser("add", help="Add migration report to database")
    add_parser.add_argument("report", help="Path to migration report JSON file")

    # Add batch command
    batch_parser = subparsers.add_parser("add-batch", help="Add multiple reports from directory")
    batch_parser.add_argument("directory", help="Directory containing migration reports")

    # Dashboard command
    dashboard_parser = subparsers.add_parser("dashboard", help="Generate HTML dashboard")
    dashboard_parser.add_argument(
        "--output",
        "-o",
        default="migration_analytics.html",
        help="Output HTML file (default: migration_analytics.html)",
    )

    # Stats command
    subparsers.add_parser("stats", help="Show migration statistics")

    # Trends command
    trends_parser = subparsers.add_parser("trends", help="Show migration trends")
    trends_parser.add_argument("--period", "-p", type=int, default=30, help="Period in days (default: 30)")

    # Export command
    export_parser = subparsers.add_parser("export", help="Export metrics")
    export_parser.add_argument(
        "--format", "-f", choices=["json", "csv"], default="json", help="Export format (default: json)"
    )
    export_parser.add_argument("--output", "-o", help="Output file (default: stdout)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Initialize analytics
    analytics = MigrationAnalytics(db_path=args.db)

    try:
        if args.command == "add":
            report_path = Path(args.report)
            if not report_path.exists():
                print(f"ERROR: Report file not found: {report_path}")
                sys.exit(1)
            analytics.add_migration_report(report_path)

        elif args.command == "add-batch":
            reports_dir = Path(args.directory)
            if not reports_dir.is_dir():
                print(f"ERROR: Directory not found: {reports_dir}")
                sys.exit(1)
            stats = analytics.add_batch_reports(reports_dir)
            print(f"\n=== Batch Import Summary ===")
            print(f"Added: {stats['added']}")
            print(f"Failed: {stats['failed']}")

        elif args.command == "dashboard":
            output_path = Path(args.output)
            analytics.generate_html_dashboard(output_path)
            print(f"\nOpen in browser: file://{output_path.absolute()}")

        elif args.command == "stats":
            stats = analytics.get_statistics()
            print("\n=== Migration Statistics ===")
            print(f"Total Migrations: {stats['total_migrations']}")
            print(f"Successful: {stats['successful_migrations']}")
            print(f"Failed: {stats['failed_migrations']}")
            print(f"Success Rate: {stats['success_rate']}%")
            print(f"Average Duration: {stats['average_duration_seconds']:.2f}s")
            print(f"\nStrategies:")
            for strategy, count in sorted(stats["strategies"].items()):
                print(f"  {strategy}: {count}")

        elif args.command == "trends":
            trends = analytics.get_trends(days=args.period)
            print(f"\n=== Trends ({args.period} days) ===")
            print(f"Migrations per day: {len(trends['migrations_per_day'])} data points")
            print(f"Success rate trend: {len(trends['success_rate_trend'])} data points")
            print(f"Duration trend: {len(trends['duration_trend'])} data points")

        elif args.command == "export":
            metrics = analytics.export_metrics(format=args.format)

            if args.output:
                with open(args.output, "w") as f:
                    json.dump(metrics, f, indent=2)
                print(f"✓ Metrics exported to: {args.output}")
            else:
                print(json.dumps(metrics, indent=2))

    finally:
        analytics.close()


if __name__ == "__main__":
    main()
