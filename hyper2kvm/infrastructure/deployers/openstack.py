# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
OpenStack deployment: upload converted QCOW2 to Glance and optionally boot a Nova instance.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hyper2kvm.core.exceptions import InfrastructureError

try:
    import openstack

    HAS_OPENSTACK = True
except ImportError:
    HAS_OPENSTACK = False


class OpenStackDeployer:
    """Upload a disk image to Glance; optionally create a Nova server."""

    def __init__(self, logger, args) -> None:
        self.logger = logger
        self.args = args

    def _connect(self):
        if not HAS_OPENSTACK:
            raise InfrastructureError(
                msg="openstacksdk is not installed. Install with: pip install 'hyper2kvm[openstack]'"
            )

        cloud = getattr(self.args, "os_cloud", None)
        if cloud:
            self.logger.info("Connecting to OpenStack cloud: %s", cloud)
            return openstack.connect(cloud=cloud)

        auth_url = getattr(self.args, "os_auth_url", None)
        if auth_url:
            self.logger.info("Connecting to OpenStack: %s", auth_url)
            return openstack.connect(
                auth_url=auth_url,
                username=getattr(self.args, "os_username", None),
                password=getattr(self.args, "os_password", None),
                project_name=getattr(self.args, "os_project_name", None),
                user_domain_name=getattr(self.args, "os_user_domain_name", None) or "Default",
                project_domain_name=getattr(self.args, "os_project_domain_name", None) or "Default",
            )

        self.logger.info("Connecting to OpenStack (OS_* env / clouds.yaml default)")
        return openstack.connect()

    def deploy(self, qcow2_path: str) -> dict[str, Any]:
        image_path = Path(qcow2_path)
        if not image_path.is_file():
            raise InfrastructureError(msg=f"Image not found: {image_path}")

        glance_name = getattr(self.args, "glance_name", None) or getattr(self.args, "vm_name", None)
        if not glance_name:
            glance_name = image_path.stem
        glance_name = str(glance_name)

        if getattr(self.args, "openstack_boot_instance", False):
            flavor = getattr(self.args, "openstack_flavor", None)
            network = getattr(self.args, "openstack_network", None)
            key_name = getattr(self.args, "openstack_key_name", None)
            missing = [
                n for n, v in (("flavor", flavor), ("network", network), ("key_name", key_name)) if not v
            ]
            if missing:
                raise InfrastructureError(
                    msg="--openstack-boot-instance requires "
                    + ", ".join(f"--openstack-{m.replace('_', '-')}" for m in missing)
                )

        if getattr(self.args, "dry_run", False):
            self.logger.info(
                "[dry-run] Would upload %s to Glance as '%s'",
                image_path.name,
                glance_name,
            )
            return {"glance_name": glance_name, "dry_run": True}

        conn = self._connect()
        description = getattr(self.args, "openstack_description", None) or ""
        visibility = getattr(self.args, "openstack_visibility", None) or "private"

        self.logger.info("Uploading %s to Glance as '%s'...", image_path.name, glance_name)
        with image_path.open("rb") as handle:
            image = conn.image.create_image(
                name=glance_name,
                disk_format="qcow2",
                container_format="bare",
                visibility=visibility,
                description=description or None,
                data=handle,
            )

        image = conn.image.wait_for_status(image, status="active", wait=3600)
        self.logger.info("Glance image active: %s (%s)", glance_name, image.id)

        result: dict[str, Any] = {
            "glance_name": glance_name,
            "image_id": image.id,
        }

        if not getattr(self.args, "openstack_boot_instance", False):
            return result

        flavor = getattr(self.args, "openstack_flavor", None)
        network = getattr(self.args, "openstack_network", None)
        key_name = getattr(self.args, "openstack_key_name", None)

        server_name = getattr(self.args, "openstack_server_name", None) or f"{glance_name}-instance"
        self.logger.info("Booting Nova instance '%s' from image %s...", server_name, image.id)

        security_groups = None
        sg_name = getattr(self.args, "openstack_security_group", None)
        if sg_name:
            security_groups = [{"name": sg_name}]

        server = conn.compute.create_server(
            name=server_name,
            image_id=image.id,
            flavor_id=flavor,
            networks=[{"uuid": network}],
            key_name=key_name,
            security_groups=security_groups,
            availability_zone=getattr(self.args, "openstack_availability_zone", None) or None,
        )

        if getattr(self.args, "openstack_wait", False):
            server = conn.compute.wait_for_server(server, status="ACTIVE", wait=1200)
            self.logger.info("Instance ACTIVE: %s", server.id)
        else:
            self.logger.info("Instance created: %s (not waiting for ACTIVE)", server.id)

        result.update(
            {
                "server_id": server.id,
                "server_name": server_name,
                "addresses": getattr(server, "addresses", None),
            }
        )
        return result


def deploy_to_openstack(logger, args, qcow2_path: str) -> dict[str, Any]:
    """Upload QCOW2 to Glance; optionally boot a Nova instance."""
    return OpenStackDeployer(logger, args).deploy(qcow2_path)
