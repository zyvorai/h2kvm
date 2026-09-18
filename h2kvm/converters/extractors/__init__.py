# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
# https://zyvor.dev · info@zyvor.dev

# h2kvm/converters/extractors/__init__.py
"""
Disk format extractors for various VM image formats.

This package provides extractors for converting VM disk images to raw format:
- ami: Amazon AMI (EC2 image format) extraction
- libvirt_xml: Libvirt domain XML parser and Artifact Manifest generator
- ovf: OVF/OVA package extraction and conversion
- raw: Raw disk image handling
- vhd: VHD/VHDX (Hyper-V) disk extraction
"""

from .ami import AMI
from .libvirt_xml import LibvirtXML
from .ovf import OVF
from .raw import RAW
from .vhd import VHD

__all__ = ["AMI", "OVF", "RAW", "VHD", "LibvirtXML"]
