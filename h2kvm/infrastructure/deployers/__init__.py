# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
# https://zyvor.dev · info@zyvor.dev

# h2kvm/deployers/__init__.py
"""
Deployment modules for various target platforms.

Supported deployers:
- kubernetes: Deploy to Kubernetes/k3s with KubeVirt
- openstack: Upload to Glance and optionally boot Nova
- libvirt: Deploy to local libvirt (domain XML + virsh)
"""
