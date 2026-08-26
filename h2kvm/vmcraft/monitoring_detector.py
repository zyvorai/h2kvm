# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/monitoring_detector.py
"""
Monitoring and observability agent detection.

Provides comprehensive monitoring agent analysis:
- Metrics: Prometheus, collectd, Telegraf, Datadog, New Relic
- Logging: Fluentd, Logstash, Filebeat, Splunk forwarder
- APM: Elastic APM, Datadog APM, New Relic APM, AppDynamics
- Infrastructure: Nagios, Zabbix, SNMP, Icinga
- Tracing: Jaeger, Zipkin, OpenTelemetry

Features:
- Detect monitoring agents
- Parse agent configurations
- Identify monitoring endpoints
- List exported metrics/logs
- Check agent status
"""

from __future__ import annotations

from typing import Any

from .base_analyzer import BaseAnalyzer


class MonitoringDetector(BaseAnalyzer):
    """
    Monitoring and observability agent detector.

    Detects monitoring, logging, and APM agents.
    """

    def detect_monitoring_agents(self) -> dict[str, Any]:
        """
        Detect monitoring agents comprehensively.

        Returns:
            Monitoring agent detection results
        """
        agents: dict[str, Any] = {
            "metrics_agents": [],
            "logging_agents": [],
            "apm_agents": [],
            "infrastructure_agents": [],
            "total_agents": 0,
        }

        # Detect metrics agents
        metrics = self._detect_metrics_agents()
        agents["metrics_agents"] = metrics
        agents["total_agents"] += len(metrics)

        # Detect logging agents
        logging_agents = self._detect_logging_agents()
        agents["logging_agents"] = logging_agents
        agents["total_agents"] += len(logging_agents)

        # Detect APM agents
        apm = self._detect_apm_agents()
        agents["apm_agents"] = apm
        agents["total_agents"] += len(apm)

        # Detect infrastructure monitoring
        infra = self._detect_infrastructure_agents()
        agents["infrastructure_agents"] = infra
        agents["total_agents"] += len(infra)

        return agents

    def _detect_metrics_agents(self) -> list[dict[str, Any]]:
        """Detect metrics collection agents."""
        agents = []

        # Prometheus Node Exporter
        if self.file_ops.exists("/usr/local/bin/node_exporter") or self.file_ops.exists(
            "/usr/bin/node_exporter"
        ):
            agents.append(
                {
                    "name": "Prometheus Node Exporter",
                    "type": "metrics",
                    "vendor": "Prometheus",
                    "port": 9100,
                }
            )

        # Prometheus itself
        if self.file_ops.exists("/usr/local/bin/prometheus"):
            config = None
            if self.file_ops.exists("/etc/prometheus/prometheus.yml"):
                config = "/etc/prometheus/prometheus.yml"
            agents.append(
                {
                    "name": "Prometheus Server",
                    "type": "metrics",
                    "vendor": "Prometheus",
                    "port": 9090,
                    "config": config,
                }
            )

        # Telegraf
        if self.file_ops.exists("/usr/bin/telegraf"):
            config = None
            if self.file_ops.exists("/etc/telegraf/telegraf.conf"):
                config = "/etc/telegraf/telegraf.conf"
            agents.append(
                {
                    "name": "Telegraf",
                    "type": "metrics",
                    "vendor": "InfluxData",
                    "config": config,
                }
            )

        # collectd
        if self.file_ops.exists("/usr/sbin/collectd"):
            config = None
            if self.file_ops.exists("/etc/collectd/collectd.conf"):
                config = "/etc/collectd/collectd.conf"
            agents.append(
                {
                    "name": "collectd",
                    "type": "metrics",
                    "vendor": "collectd",
                    "config": config,
                }
            )

        # Datadog agent
        if self.file_ops.exists("/opt/datadog-agent"):
            config = None
            if self.file_ops.exists("/etc/datadog-agent/datadog.yaml"):
                config = "/etc/datadog-agent/datadog.yaml"
            agents.append(
                {
                    "name": "Datadog Agent",
                    "type": "metrics",
                    "vendor": "Datadog",
                    "config": config,
                }
            )

        # New Relic Infrastructure agent
        if self.file_ops.exists("/usr/bin/newrelic-infra"):
            config = None
            if self.file_ops.exists("/etc/newrelic-infra.yml"):
                config = "/etc/newrelic-infra.yml"
            agents.append(
                {
                    "name": "New Relic Infrastructure",
                    "type": "metrics",
                    "vendor": "New Relic",
                    "config": config,
                }
            )

        return agents

    def _detect_logging_agents(self) -> list[dict[str, Any]]:
        """Detect logging agents."""
        agents = []

        # Fluentd / td-agent
        if self.file_ops.exists("/usr/sbin/td-agent") or self.file_ops.exists("/usr/sbin/fluentd"):
            config = None
            if self.file_ops.exists("/etc/td-agent/td-agent.conf"):
                config = "/etc/td-agent/td-agent.conf"
            elif self.file_ops.exists("/etc/fluent/fluentd.conf"):
                config = "/etc/fluent/fluentd.conf"
            agents.append(
                {
                    "name": "Fluentd",
                    "type": "logging",
                    "vendor": "Fluentd",
                    "config": config,
                }
            )

        # Logstash
        if self.file_ops.exists("/usr/share/logstash"):
            config = None
            if self.file_ops.is_dir("/etc/logstash/conf.d"):
                config = "/etc/logstash/conf.d"
            agents.append(
                {
                    "name": "Logstash",
                    "type": "logging",
                    "vendor": "Elastic",
                    "config": config,
                }
            )

        # Filebeat
        if self.file_ops.exists("/usr/share/filebeat"):
            config = None
            if self.file_ops.exists("/etc/filebeat/filebeat.yml"):
                config = "/etc/filebeat/filebeat.yml"
            agents.append(
                {
                    "name": "Filebeat",
                    "type": "logging",
                    "vendor": "Elastic",
                    "config": config,
                }
            )

        # Splunk Universal Forwarder
        if self.file_ops.is_dir("/opt/splunkforwarder"):
            agents.append(
                {
                    "name": "Splunk Universal Forwarder",
                    "type": "logging",
                    "vendor": "Splunk",
                    "config": "/opt/splunkforwarder/etc",
                }
            )

        # Rsyslog (system default, but check for remote forwarding)
        if self.file_ops.exists("/etc/rsyslog.conf"):
            try:
                content = self.file_ops.cat("/etc/rsyslog.conf")
                if "@@" in content or "@" in content:  # Remote syslog
                    agents.append(
                        {
                            "name": "rsyslog (remote forwarding)",
                            "type": "logging",
                            "vendor": "rsyslog",
                            "config": "/etc/rsyslog.conf",
                        }
                    )
            except Exception:  # pylint: disable=broad-exception-caught  # best-effort agent detection; a read failure must not abort the scan
                pass

        return agents

    def _detect_apm_agents(self) -> list[dict[str, Any]]:
        """Detect APM agents."""
        agents = []

        # Elastic APM
        if self.file_ops.is_dir("/usr/share/apm-server"):
            config = None
            if self.file_ops.exists("/etc/apm-server/apm-server.yml"):
                config = "/etc/apm-server/apm-server.yml"
            agents.append(
                {
                    "name": "Elastic APM Server",
                    "type": "apm",
                    "vendor": "Elastic",
                    "config": config,
                }
            )

        # New Relic APM (check for language agents in common locations)
        newrelic_indicators = [
            "/etc/newrelic.ini",  # Python
            "/etc/newrelic/newrelic.yml",  # Java
        ]
        for indicator in newrelic_indicators:
            if self.file_ops.exists(indicator):
                agents.append(
                    {
                        "name": "New Relic APM",
                        "type": "apm",
                        "vendor": "New Relic",
                        "config": indicator,
                    }
                )
                break

        # AppDynamics
        if self.file_ops.is_dir("/opt/appdynamics"):
            agents.append(
                {
                    "name": "AppDynamics Agent",
                    "type": "apm",
                    "vendor": "AppDynamics",
                    "config": "/opt/appdynamics",
                }
            )

        # Jaeger agent
        if self.file_ops.exists("/usr/local/bin/jaeger-agent"):
            agents.append(
                {
                    "name": "Jaeger Agent",
                    "type": "tracing",
                    "vendor": "Jaeger",
                    "port": 6831,
                }
            )

        # OpenTelemetry Collector
        if self.file_ops.exists("/usr/local/bin/otelcol"):
            config = None
            if self.file_ops.exists("/etc/otelcol/config.yaml"):
                config = "/etc/otelcol/config.yaml"
            agents.append(
                {
                    "name": "OpenTelemetry Collector",
                    "type": "observability",
                    "vendor": "OpenTelemetry",
                    "config": config,
                }
            )

        return agents

    def _detect_infrastructure_agents(self) -> list[dict[str, Any]]:
        """Detect infrastructure monitoring agents."""
        agents = []

        # Nagios NRPE
        if self.file_ops.exists("/usr/sbin/nrpe"):
            config = None
            if self.file_ops.exists("/etc/nagios/nrpe.cfg"):
                config = "/etc/nagios/nrpe.cfg"
            agents.append(
                {
                    "name": "Nagios NRPE",
                    "type": "infrastructure",
                    "vendor": "Nagios",
                    "port": 5666,
                    "config": config,
                }
            )

        # Zabbix agent
        if self.file_ops.exists("/usr/sbin/zabbix_agentd"):
            config = None
            if self.file_ops.exists("/etc/zabbix/zabbix_agentd.conf"):
                config = "/etc/zabbix/zabbix_agentd.conf"
            agents.append(
                {
                    "name": "Zabbix Agent",
                    "type": "infrastructure",
                    "vendor": "Zabbix",
                    "port": 10050,
                    "config": config,
                }
            )

        # SNMP daemon
        if self.file_ops.exists("/usr/sbin/snmpd"):
            config = None
            if self.file_ops.exists("/etc/snmp/snmpd.conf"):
                config = "/etc/snmp/snmpd.conf"
            agents.append(
                {
                    "name": "SNMP Daemon",
                    "type": "infrastructure",
                    "vendor": "Net-SNMP",
                    "port": 161,
                    "config": config,
                }
            )

        # Icinga2
        if self.file_ops.exists("/usr/sbin/icinga2"):
            config = None
            if self.file_ops.is_dir("/etc/icinga2"):
                config = "/etc/icinga2"
            agents.append(
                {
                    "name": "Icinga2 Agent",
                    "type": "infrastructure",
                    "vendor": "Icinga",
                    "port": 5665,
                    "config": config,
                }
            )

        # Sensu client
        if self.file_ops.exists("/opt/sensu"):
            config = None
            if self.file_ops.exists("/etc/sensu/config.json"):
                config = "/etc/sensu/config.json"
            agents.append(
                {
                    "name": "Sensu Client",
                    "type": "infrastructure",
                    "vendor": "Sensu",
                    "config": config,
                }
            )

        return agents

    def get_monitoring_summary(self, agents: dict[str, Any]) -> dict[str, Any]:
        """
        Get monitoring summary.

        Args:
            agents: Monitoring agent detection results

        Returns:
            Summary dictionary
        """
        return {
            "total_agents": agents.get("total_agents", 0),
            "metrics_agents": len(agents.get("metrics_agents", [])),
            "logging_agents": len(agents.get("logging_agents", [])),
            "apm_agents": len(agents.get("apm_agents", [])),
            "infrastructure_agents": len(agents.get("infrastructure_agents", [])),
            "has_observability": agents.get("total_agents", 0) > 0,
        }

    def list_agent_vendors(self, agents: dict[str, Any]) -> list[str]:
        """
        List unique agent vendors.

        Args:
            agents: Monitoring agent detection results

        Returns:
            List of vendor names
        """
        vendors = set()

        for agent_type in ["metrics_agents", "logging_agents", "apm_agents", "infrastructure_agents"]:
            for agent in agents.get(agent_type, []):
                vendor = agent.get("vendor")
                if vendor:
                    vendors.add(vendor)

        return sorted(vendors)

    def get_exposed_ports(self, agents: dict[str, Any]) -> list[int]:
        """
        Get list of ports exposed by monitoring agents.

        Args:
            agents: Monitoring agent detection results

        Returns:
            List of port numbers
        """
        ports = []

        for agent_type in ["metrics_agents", "logging_agents", "apm_agents", "infrastructure_agents"]:
            for agent in agents.get(agent_type, []):
                port = agent.get("port")
                if port:
                    ports.append(port)

        return sorted(set(ports))

    def check_monitoring_health(self, agents: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Check monitoring health and configuration.

        Args:
            agents: Monitoring agent detection results

        Returns:
            List of health issues
        """
        issues = []

        # Check if any monitoring is in place
        if agents.get("total_agents", 0) == 0:
            issues.append(
                {
                    "severity": "medium",
                    "issue": "No monitoring agents detected",
                    "recommendation": "Install monitoring solution (Prometheus + Grafana recommended)",
                }
            )

        # Check for logging
        if len(agents.get("logging_agents", [])) == 0:
            issues.append(
                {
                    "severity": "low",
                    "issue": "No centralized logging agents detected",
                    "recommendation": "Consider Fluentd, Filebeat, or Logstash for log aggregation",
                }
            )

        # Check for APM
        if len(agents.get("apm_agents", [])) == 0:
            issues.append(
                {
                    "severity": "info",
                    "issue": "No APM agents detected",
                    "recommendation": "Consider APM for application performance monitoring",
                }
            )

        return issues
