#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Push a QCOW2 VM image to OpenStack using h2kvm (convert + fix + Glance upload).

Requires: pip install 'h2kvm[openstack]'
Auth: clouds.yaml (--os-cloud), sourced openrc, or OS_* environment variables.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate QCOW2/VMDK to OpenStack via h2kvm")
    parser.add_argument("image_path", help="Source disk (VMDK, QCOW2, OVA path, etc.) or existing QCOW2")
    parser.add_argument("--config", "-c", help="h2kvm YAML config (cmd: local, flatten, etc.)")
    parser.add_argument("--glance-name", required=True, help="Name for the Glance image")
    parser.add_argument("--os-cloud", help="Cloud entry in clouds.yaml")
    parser.add_argument("--openstack-boot-instance", action="store_true")
    parser.add_argument("--openstack-flavor")
    parser.add_argument("--openstack-network")
    parser.add_argument("--openstack-key-name")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not Path(args.image_path).is_file():
        print(f"Error: {args.image_path} not found", file=sys.stderr)
        sys.exit(1)

    cmd = [
        "h2kvmctl",
        "--output-dir",
        "./openstack-out",
        "--deploy-openstack",
        "--glance-name",
        args.glance_name,
    ]
    if args.config:
        cmd.extend(["--config", args.config])
    else:
        # local mode uses --vmdk for any disk path (vmdk, qcow2, etc.)
        cmd.extend(["local", "--vmdk", args.image_path, "--flatten", "--to-output", "migrated.qcow2"])

    if args.os_cloud:
        cmd.extend(["--os-cloud", args.os_cloud])
    if args.openstack_boot_instance:
        cmd.append("--openstack-boot-instance")
    if args.openstack_flavor:
        cmd.extend(["--openstack-flavor", args.openstack_flavor])
    if args.openstack_network:
        cmd.extend(["--openstack-network", args.openstack_network])
    if args.openstack_key_name:
        cmd.extend(["--openstack-key-name", args.openstack_key_name])
    if args.dry_run:
        cmd.append("--dry-run")

    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
