# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
# https://zyvor.dev · info@zyvor.dev

"""Windows Active Directory integration module.

Provides functionality for extracting domain membership information and
automating domain rejoin after VM migration.
"""

from .extractor import DomainInfo, extract_domain_info
from .rejoin import (
    DomainRejoinMethod,
    get_rejoin_command,
    stage_domain_rejoin_script,
)

__all__ = [
    "DomainInfo",
    "DomainRejoinMethod",
    "extract_domain_info",
    "get_rejoin_command",
    "stage_domain_rejoin_script",
]
