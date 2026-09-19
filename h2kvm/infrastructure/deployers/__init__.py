# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: LicenseRef-Zyvor-Production-1.0
# https://zyvor.dev · info@zyvor.dev

# h2kvm/deployers/__init__.py
"""
Deployment modules for various target platforms.

Supported deployers:
- kubernetes: Deploy to Kubernetes/k3s with KubeVirt
- openstack: Upload to Glance and optionally boot Nova
- libvirt: Deploy to local libvirt (domain XML + virsh)
"""
