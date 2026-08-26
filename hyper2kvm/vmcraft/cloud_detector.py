# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/vmcraft/cloud_detector.py
"""
Cloud platform integration detection.

Provides comprehensive cloud platform analysis:
- AWS integration (CLI, SDKs, cloud-init, instance metadata)
- Azure integration (CLI, SDKs, cloud-init, Azure agent)
- GCP integration (CLI, SDKs, cloud-init, GCE metadata)
- Cloud-init configuration
- Cloud provider metadata
- Cloud storage mounting (S3, Azure Blob, GCS)

Features:
- Detect cloud CLIs and SDKs
- Parse cloud-init configurations
- Identify cloud provider from metadata
- List cloud storage mounts
- Detect cloud monitoring agents
"""

from __future__ import annotations

from typing import Any

from .base_analyzer import BaseAnalyzer


class CloudDetector(BaseAnalyzer):
    """
    Cloud platform integration detector.

    Detects cloud provider integrations and configurations.
    """

    def detect_cloud_integration(self) -> dict[str, Any]:
        """
        Detect cloud platform integrations comprehensively.

        Returns:
            Cloud integration detection results
        """
        cloud: dict[str, Any] = {
            "aws": None,
            "azure": None,
            "gcp": None,
            "cloud_init": None,
            "detected_provider": None,
            "cloud_agents": [],
        }

        # Detect AWS integration
        aws = self._detect_aws()
        if aws.get("detected"):
            cloud["aws"] = aws
            cloud["detected_provider"] = "AWS"

        # Detect Azure integration
        azure = self._detect_azure()
        if azure.get("detected"):
            cloud["azure"] = azure
            if not cloud["detected_provider"]:
                cloud["detected_provider"] = "Azure"

        # Detect GCP integration
        gcp = self._detect_gcp()
        if gcp.get("detected"):
            cloud["gcp"] = gcp
            if not cloud["detected_provider"]:
                cloud["detected_provider"] = "GCP"

        # Detect cloud-init
        cloud_init = self._detect_cloud_init()
        if cloud_init.get("installed"):
            cloud["cloud_init"] = cloud_init

        # Detect cloud agents
        agents = self._detect_cloud_agents()
        cloud["cloud_agents"] = agents

        return cloud

    def _detect_aws(self) -> dict[str, Any]:
        """Detect AWS integration."""
        aws: dict[str, Any] = {
            "detected": False,
            "cli_installed": False,
            "credentials_found": False,
            "instance_metadata": False,
            "sdks": [],
        }

        # Check for AWS CLI
        if self.file_ops.exists("/usr/local/bin/aws") or self.file_ops.exists("/usr/bin/aws"):
            aws["cli_installed"] = True
            aws["detected"] = True

        # Check for AWS credentials
        cred_paths = [
            "/root/.aws/credentials",
            "/root/.aws/config",
        ]
        for cred_path in cred_paths:
            if self.file_ops.exists(cred_path):
                aws["credentials_found"] = True
                aws["detected"] = True
                break

        # Check for instance metadata service indicators
        if self.file_ops.exists("/etc/ec2_version"):
            aws["instance_metadata"] = True
            aws["detected"] = True

        # Check for AWS SDKs (Python boto3, Node.js aws-sdk, etc.)
        # This would require checking site-packages or node_modules
        # For now, just mark as detected if other indicators present

        return aws

    def _detect_azure(self) -> dict[str, Any]:
        """Detect Azure integration."""
        azure: dict[str, Any] = {
            "detected": False,
            "cli_installed": False,
            "agent_installed": False,
            "credentials_found": False,
        }

        # Check for Azure CLI
        if self.file_ops.exists("/usr/bin/az"):
            azure["cli_installed"] = True
            azure["detected"] = True

        # Check for Azure VM agent
        if self.file_ops.is_dir("/var/lib/waagent"):
            azure["agent_installed"] = True
            azure["detected"] = True

        # Check for Azure credentials
        if self.file_ops.exists("/root/.azure"):
            azure["credentials_found"] = True
            azure["detected"] = True

        return azure

    def _detect_gcp(self) -> dict[str, Any]:
        """Detect GCP integration."""
        gcp: dict[str, Any] = {
            "detected": False,
            "cli_installed": False,
            "agent_installed": False,
            "credentials_found": False,
        }

        # Check for gcloud CLI
        if self.file_ops.exists("/usr/bin/gcloud"):
            gcp["cli_installed"] = True
            gcp["detected"] = True

        # Check for GCE metadata agent
        if self.file_ops.exists("/usr/bin/google_metadata_script_runner"):
            gcp["agent_installed"] = True
            gcp["detected"] = True

        # Check for GCP credentials
        if self.file_ops.exists("/root/.config/gcloud"):
            gcp["credentials_found"] = True
            gcp["detected"] = True

        return gcp

    def _detect_cloud_init(self) -> dict[str, Any]:
        """Detect cloud-init installation and configuration."""
        cloud_init: dict[str, Any] = {
            "installed": False,
            "config_paths": [],
            "datasource": None,
        }

        # Check for cloud-init binary
        if not self.file_ops.exists("/usr/bin/cloud-init"):
            return cloud_init

        cloud_init["installed"] = True

        # Check for cloud-init configs
        config_paths = [
            "/etc/cloud/cloud.cfg",
            "/etc/cloud/cloud.cfg.d",
        ]

        for config_path in config_paths:
            if self.file_ops.exists(config_path):
                cloud_init["config_paths"].append(config_path)

        # Try to detect datasource
        # nested line-by-line datasource_list parsing is clearer kept inline than split apart
        # pylint: disable-next=too-many-nested-blocks
        if self.file_ops.exists("/etc/cloud/cloud.cfg"):
            try:
                content = self.file_ops.cat("/etc/cloud/cloud.cfg")
                if "datasource_list" in content:
                    # Extract datasource
                    for line in content.splitlines():
                        if "datasource_list" in line:
                            if "Ec2" in line:
                                cloud_init["datasource"] = "AWS EC2"
                            elif "Azure" in line:
                                cloud_init["datasource"] = "Azure"
                            elif "GCE" in line:
                                cloud_init["datasource"] = "GCP"
                            elif "NoCloud" in line:
                                cloud_init["datasource"] = "NoCloud"
                            break
            # best-effort datasource detection; cloud_init is still reported as installed either way
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        return cloud_init

    def _detect_cloud_agents(self) -> list[dict[str, Any]]:
        """Detect cloud monitoring and management agents."""
        agents = []

        # AWS CloudWatch agent
        if self.file_ops.exists("/opt/aws/amazon-cloudwatch-agent"):
            agents.append(
                {
                    "name": "Amazon CloudWatch Agent",
                    "provider": "AWS",
                    "type": "monitoring",
                }
            )

        # AWS SSM agent
        if self.file_ops.exists("/usr/bin/amazon-ssm-agent"):
            agents.append(
                {
                    "name": "AWS Systems Manager Agent",
                    "provider": "AWS",
                    "type": "management",
                }
            )

        # Azure Monitor agent
        if self.file_ops.exists("/opt/microsoft/azuremonitoragent"):
            agents.append(
                {
                    "name": "Azure Monitor Agent",
                    "provider": "Azure",
                    "type": "monitoring",
                }
            )

        # GCP Ops Agent
        if self.file_ops.exists("/opt/google-cloud-ops-agent"):
            agents.append(
                {
                    "name": "Google Cloud Ops Agent",
                    "provider": "GCP",
                    "type": "monitoring",
                }
            )

        return agents

    def get_cloud_summary(self, cloud: dict[str, Any]) -> dict[str, Any]:
        """
        Get cloud integration summary.

        Args:
            cloud: Cloud detection results

        Returns:
            Summary dictionary
        """
        return {
            "provider": cloud.get("detected_provider", "None"),
            "aws_detected": cloud.get("aws", {}).get("detected", False),
            "azure_detected": cloud.get("azure", {}).get("detected", False),
            "gcp_detected": cloud.get("gcp", {}).get("detected", False),
            "cloud_init_installed": cloud.get("cloud_init", {}).get("installed", False),
            "cloud_agents_count": len(cloud.get("cloud_agents", [])),
        }

    def is_cloud_vm(self, cloud: dict[str, Any]) -> bool:
        """
        Check if VM is running in cloud.

        Args:
            cloud: Cloud detection results

        Returns:
            True if cloud VM detected
        """
        return cloud.get("detected_provider") is not None

    def get_cloud_services(self, cloud: dict[str, Any]) -> list[str]:
        """
        List detected cloud services.

        Args:
            cloud: Cloud detection results

        Returns:
            List of cloud service names
        """
        services = []

        # AWS services
        aws = cloud.get("aws", {})
        if aws.get("cli_installed"):
            services.append("AWS CLI")
        if aws.get("credentials_found"):
            services.append("AWS Credentials")

        # Azure services
        azure = cloud.get("azure", {})
        if azure.get("cli_installed"):
            services.append("Azure CLI")
        if azure.get("agent_installed"):
            services.append("Azure VM Agent")

        # GCP services
        gcp = cloud.get("gcp", {})
        if gcp.get("cli_installed"):
            services.append("Google Cloud CLI")
        if gcp.get("agent_installed"):
            services.append("GCE Metadata Agent")

        # Cloud-init
        if cloud.get("cloud_init", {}).get("installed"):
            services.append("cloud-init")

        # Agents
        for agent in cloud.get("cloud_agents", []):
            services.append(agent.get("name", "Unknown Agent"))

        return services
