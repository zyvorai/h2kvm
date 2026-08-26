# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/deployers/__init__.py
"""
Deployment modules for various target platforms.

Supported deployers:
- kubernetes: Deploy to Kubernetes/k3s with KubeVirt
- openstack: Upload to Glance and optionally boot Nova
- libvirt: Deploy to local libvirt (domain XML + virsh)
"""
