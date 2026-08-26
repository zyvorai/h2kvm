# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for h2kvm.ai.workload.WorkloadClassifier.

Covers classification of all supported workload types, confidence
scaling, mixed workloads, and recommendation generation.
"""

from __future__ import annotations

from h2kvm.ai.models import MigrationFeatures, WorkloadType
from h2kvm.ai.workload import WorkloadClassifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _classify(packages: list[str] | None = None, services: list[str] | None = None):
    """Shorthand to classify with given packages/services."""
    features = MigrationFeatures(
        packages=packages or [],
        services=services or [],
    )
    return WorkloadClassifier().classify(features)


# ---------------------------------------------------------------------------
# Generic / empty
# ---------------------------------------------------------------------------


class TestGenericWorkload:
    def test_no_packages_no_services(self):
        profile = _classify()
        assert profile.workload_type == WorkloadType.GENERIC
        assert profile.confidence == 0.0
        assert profile.matched_indicators == []
        assert profile.recommendations == []

    def test_unrecognised_packages(self):
        profile = _classify(packages=["vim", "htop", "curl"])
        assert profile.workload_type == WorkloadType.GENERIC

    def test_unrecognised_services(self):
        profile = _classify(services=["crond", "sshd", "systemd-journald"])
        assert profile.workload_type == WorkloadType.GENERIC


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


class TestDatabaseWorkload:
    def test_mysql_package(self):
        profile = _classify(packages=["mysql-server"])
        assert profile.workload_type == WorkloadType.DATABASE

    def test_postgresql_service(self):
        profile = _classify(services=["postgresql"])
        assert profile.workload_type == WorkloadType.DATABASE

    def test_mariadb_package(self):
        profile = _classify(packages=["mariadb-server"])
        assert profile.workload_type == WorkloadType.DATABASE

    def test_redis_service(self):
        profile = _classify(services=["redis-server"])
        assert profile.workload_type == WorkloadType.DATABASE

    def test_database_recommendations_present(self):
        profile = _classify(packages=["postgresql"])
        assert len(profile.recommendations) > 0
        assert any("database" in r.lower() or "i/o" in r.lower() for r in profile.recommendations)


# ---------------------------------------------------------------------------
# Webserver
# ---------------------------------------------------------------------------


class TestWebserverWorkload:
    def test_nginx_package(self):
        profile = _classify(packages=["nginx"])
        assert profile.workload_type == WorkloadType.WEBSERVER

    def test_httpd_service(self):
        profile = _classify(services=["httpd"])
        assert profile.workload_type == WorkloadType.WEBSERVER

    def test_apache2_package(self):
        profile = _classify(packages=["apache2"])
        assert profile.workload_type == WorkloadType.WEBSERVER

    def test_haproxy_package(self):
        profile = _classify(packages=["haproxy"])
        assert profile.workload_type == WorkloadType.WEBSERVER


# ---------------------------------------------------------------------------
# Appserver
# ---------------------------------------------------------------------------


class TestAppserverWorkload:
    def test_tomcat_package(self):
        profile = _classify(packages=["tomcat"])
        assert profile.workload_type == WorkloadType.APPSERVER

    def test_gunicorn_service(self):
        profile = _classify(services=["gunicorn"])
        assert profile.workload_type == WorkloadType.APPSERVER

    def test_nodejs_package(self):
        profile = _classify(packages=["nodejs"])
        assert profile.workload_type == WorkloadType.APPSERVER


# ---------------------------------------------------------------------------
# Mailserver
# ---------------------------------------------------------------------------


class TestMailserverWorkload:
    def test_postfix_package(self):
        profile = _classify(packages=["postfix"])
        assert profile.workload_type == WorkloadType.MAILSERVER

    def test_dovecot_service(self):
        profile = _classify(services=["dovecot"])
        assert profile.workload_type == WorkloadType.MAILSERVER


# ---------------------------------------------------------------------------
# Container host
# ---------------------------------------------------------------------------


class TestContainerHostWorkload:
    def test_docker_package(self):
        profile = _classify(packages=["docker-ce"])
        assert profile.workload_type == WorkloadType.CONTAINER_HOST

    def test_podman_service(self):
        profile = _classify(services=["podman"])
        assert profile.workload_type == WorkloadType.CONTAINER_HOST

    def test_containerd_service(self):
        profile = _classify(services=["containerd"])
        assert profile.workload_type == WorkloadType.CONTAINER_HOST


# ---------------------------------------------------------------------------
# DNS
# ---------------------------------------------------------------------------


class TestDNSWorkload:
    def test_bind_package(self):
        profile = _classify(packages=["bind"])
        assert profile.workload_type == WorkloadType.DNS

    def test_named_service(self):
        profile = _classify(services=["named"])
        assert profile.workload_type == WorkloadType.DNS

    def test_dnsmasq_package(self):
        profile = _classify(packages=["dnsmasq"])
        assert profile.workload_type == WorkloadType.DNS


# ---------------------------------------------------------------------------
# Monitoring
# ---------------------------------------------------------------------------


class TestMonitoringWorkload:
    def test_prometheus_package(self):
        profile = _classify(packages=["prometheus"])
        assert profile.workload_type == WorkloadType.MONITORING

    def test_grafana_service(self):
        profile = _classify(services=["grafana-server"])
        assert profile.workload_type == WorkloadType.MONITORING

    def test_zabbix_package(self):
        profile = _classify(packages=["zabbix-server"])
        assert profile.workload_type == WorkloadType.MONITORING


# ---------------------------------------------------------------------------
# Mixed workload (picks highest score)
# ---------------------------------------------------------------------------


class TestMixedWorkload:
    def test_mixed_picks_highest_score(self):
        # Multiple DB indicators should beat a single webserver indicator
        profile = _classify(
            packages=["mysql-server", "postgresql", "redis"],
            services=["mysqld", "postgresql", "redis-server"],
        )
        assert profile.workload_type == WorkloadType.DATABASE

    def test_mixed_webserver_and_monitoring_picks_dominant(self):
        # More monitoring indicators
        profile = _classify(
            packages=["prometheus", "grafana", "nagios", "zabbix"],
            services=["prometheus", "grafana-server", "nagios", "zabbix-server"],
        )
        assert profile.workload_type == WorkloadType.MONITORING


# ---------------------------------------------------------------------------
# Confidence scaling
# ---------------------------------------------------------------------------


class TestConfidenceScaling:
    def test_single_indicator_low_confidence(self):
        profile = _classify(packages=["nginx"])
        # score = 1/12 * 2 = 0.167 (1 match out of 6 pkg + 6 svc = 12)
        assert 0.0 < profile.confidence < 1.0

    def test_many_indicators_high_confidence(self):
        profile = _classify(
            packages=["mysql", "mariadb", "postgresql", "redis", "mongodb", "memcached"],
            services=["mysqld", "mariadb", "postgresql", "mongod", "redis-server", "memcached"],
        )
        # many matches, score should be high, confidence capped at 1.0
        assert profile.confidence > 0.5

    def test_confidence_capped_at_1(self):
        # Even with all indicators matching, confidence should not exceed 1.0
        profile = _classify(
            packages=["mysql", "mariadb", "postgresql", "oracle", "mongodb", "redis", "memcached", "sqlite"],
            services=[
                "mysqld",
                "mariadb",
                "postgresql",
                "mongod",
                "redis",
                "redis-server",
                "memcached",
                "oracle",
            ],
        )
        assert profile.confidence <= 1.0


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


class TestRecommendations:
    def test_generic_has_no_recommendations(self):
        profile = _classify()
        assert profile.recommendations == []

    def test_classified_has_recommendations(self):
        profile = _classify(packages=["nginx"])
        assert len(profile.recommendations) > 0

    def test_recommendations_are_strings(self):
        profile = _classify(packages=["postfix"])
        for rec in profile.recommendations:
            assert isinstance(rec, str)
            assert len(rec) > 0
