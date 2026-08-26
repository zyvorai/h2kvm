# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/ai/workload.py
"""
Rules-based workload classifier for migrated VMs.

Inspects packages and services to determine the VM's primary role.
"""

from __future__ import annotations

from typing import Any

from .models import MigrationFeatures, WorkloadProfile, WorkloadType

# Each rule maps a WorkloadType to indicators (packages/services) and
# recommendations.
_RULES: dict[WorkloadType, dict[str, list[str]]] = {
    WorkloadType.DATABASE: {
        "packages": [
            "mysql",
            "mariadb",
            "postgresql",
            "postgres",
            "oracle",
            "mongodb",
            "redis",
            "memcached",
            "sqlite",
        ],
        "services": [
            "mysqld",
            "mariadb",
            "postgresql",
            "mongod",
            "redis",
            "redis-server",
            "memcached",
            "oracle",
        ],
        "recommendations": [
            "Verify database data directory is on virtio-backed storage",
            "Tune I/O scheduler (mq-deadline or none) for database workloads",
            "Validate database service starts after migration",
        ],
    },
    WorkloadType.WEBSERVER: {
        "packages": [
            "httpd",
            "apache2",
            "nginx",
            "lighttpd",
            "caddy",
            "haproxy",
        ],
        "services": [
            "httpd",
            "apache2",
            "nginx",
            "lighttpd",
            "caddy",
            "haproxy",
        ],
        "recommendations": [
            "Verify web server binds to correct interface after migration",
            "Check TLS certificate paths are accessible",
            "Validate virtual host configurations",
        ],
    },
    WorkloadType.APPSERVER: {
        "packages": [
            "tomcat",
            "jboss",
            "wildfly",
            "weblogic",
            "dotnet",
            "nodejs",
            "npm",
            "gunicorn",
            "uwsgi",
            "php-fpm",
        ],
        "services": [
            "tomcat",
            "wildfly",
            "node",
            "gunicorn",
            "uwsgi",
            "php-fpm",
        ],
        "recommendations": [
            "Verify application binding addresses after migration",
            "Check file descriptor and memory limits",
        ],
    },
    WorkloadType.MAILSERVER: {
        "packages": [
            "postfix",
            "sendmail",
            "exim",
            "dovecot",
            "cyrus",
            "zimbra",
        ],
        "services": [
            "postfix",
            "sendmail",
            "exim",
            "dovecot",
            "cyrus",
        ],
        "recommendations": [
            "Verify MX records point to new IP after migration",
            "Check mail queue for pending deliveries",
            "Validate TLS certificates for mail",
        ],
    },
    WorkloadType.CONTAINER_HOST: {
        "packages": [
            "docker",
            "podman",
            "containerd",
            "cri-o",
            "kubernetes",
            "kubelet",
            "k3s",
        ],
        "services": [
            "docker",
            "containerd",
            "podman",
            "crio",
            "kubelet",
            "k3s",
        ],
        "recommendations": [
            "Verify container runtime storage driver after migration",
            "Check container networking (bridge, overlay) configuration",
            "Validate cgroup version compatibility (v1 vs v2)",
        ],
    },
    WorkloadType.DNS: {
        "packages": [
            "bind",
            "named",
            "unbound",
            "dnsmasq",
            "powerdns",
            "coredns",
        ],
        "services": [
            "named",
            "bind",
            "unbound",
            "dnsmasq",
            "pdns",
        ],
        "recommendations": [
            "Verify DNS zone files are intact",
            "Update upstream forwarder addresses if needed",
        ],
    },
    WorkloadType.MONITORING: {
        "packages": [
            "prometheus",
            "grafana",
            "nagios",
            "zabbix",
            "icinga",
            "collectd",
            "telegraf",
            "datadog",
        ],
        "services": [
            "prometheus",
            "grafana-server",
            "nagios",
            "zabbix-server",
            "icinga2",
            "collectd",
            "telegraf",
        ],
        "recommendations": [
            "Verify monitoring agent connects to the controller",
            "Check scrape targets are reachable from new location",
        ],
    },
}


def _score_rule(
    rule: dict[str, Any], pkg_set: set[str], svc_set: set[str]
) -> tuple[float, list[str]]:
    """Return (score, matched_indicators) for a single workload rule."""
    matches: list[str] = []
    rule_pkgs = rule.get("packages", [])
    rule_svcs = rule.get("services", [])
    for pkg in rule_pkgs:
        if any(pkg in p for p in pkg_set):
            matches.append(f"pkg:{pkg}")
    for svc in rule_svcs:
        if any(svc in s for s in svc_set):
            matches.append(f"svc:{svc}")
    if not matches:
        return 0.0, matches
    total_indicators = len(rule_pkgs) + len(rule_svcs)
    score = len(matches) / total_indicators if total_indicators else 0.0
    return score, matches


# pylint: disable=too-few-public-methods  # a single-purpose classifier by design
class WorkloadClassifier:
    """Classify a VM's workload from its feature set."""

    def classify(self, features: MigrationFeatures) -> WorkloadProfile:
        """Return the best-matching :class:`WorkloadProfile`."""
        best_type = WorkloadType.GENERIC
        best_score = 0.0
        best_matches: list[str] = []
        best_recs: list[str] = []

        pkg_set = {p.lower() for p in features.packages}
        svc_set = {s.lower() for s in features.services}

        for wtype, rule in _RULES.items():
            score, matches = _score_rule(rule, pkg_set, svc_set)
            if matches and score > best_score:
                best_score = score
                best_type = wtype
                best_matches = matches
                best_recs = rule.get("recommendations", [])

        return WorkloadProfile(
            workload_type=best_type,
            confidence=min(best_score * 2.0, 1.0),  # scale up
            matched_indicators=best_matches,
            recommendations=list(best_recs),
        )
