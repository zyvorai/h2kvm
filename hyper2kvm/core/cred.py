# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/cred.py
"""Credential management and storage."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True)
class VsphereCreds:
    """Resolved vSphere credentials (host, user, password)."""

    host: str
    user: str
    password: str


def _strip(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    return str(v).strip()


def _get_env(env_key: str) -> str:
    env_key = _strip(env_key)
    if not env_key:
        return ""
    return _strip(os.environ.get(env_key, ""))


def resolve_vsphere_creds(cfg: Mapping[str, Any]) -> VsphereCreds:
    """
    Resolve vSphere creds for BOTH:
      - pyvmomi control plane (vc_* / vcenter)
      - export data plane (vs_*)

    Priority:
      host: vs_host > vcenter > vc_host
      user: vs_user > vc_user
      pass: vs_password > $vs_password_env > vc_password > $vc_password_env
    """
    host = _strip(cfg.get("vs_host") or cfg.get("vcenter") or cfg.get("vc_host"))
    user = _strip(cfg.get("vs_user") or cfg.get("vc_user"))

    pw = _strip(cfg.get("vs_password"))
    if not pw:
        pw = _get_env(cfg.get("vs_password_env", ""))
    if not pw:
        pw = _strip(cfg.get("vc_password"))
    if not pw:
        pw = _get_env(cfg.get("vc_password_env", ""))

    return VsphereCreds(host=host, user=user, password=pw)
