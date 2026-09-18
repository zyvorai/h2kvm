# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
# https://zyvor.dev · info@zyvor.dev
"""Locate or install OVMF so UEFI domain XML and the boot test need no manual paths."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

_log = logging.getLogger(__name__)

# Fedora/RHEL names first, then Debian/Ubuntu 4M split firmware.
OVMF_CODE_CANDIDATES: tuple[str, ...] = (
    "/usr/share/OVMF/OVMF_CODE_4M.fd",
    "/usr/share/OVMF/OVMF_CODE.fd",
    "/usr/share/OVMF/OVMF_CODE_4M.ms.fd",
    "/usr/share/edk2/ovmf/OVMF_CODE.fd",
    "/usr/share/edk2/ovmf/OVMF_CODE.secboot.fd",
    "/usr/share/edk2/ovmf/x64/OVMF_CODE.fd",
    "/usr/share/qemu/OVMF_CODE.fd",
    "/usr/share/ovmf/OVMF.fd",
)

OVMF_VARS_CANDIDATES: tuple[str, ...] = (
    "/usr/share/OVMF/OVMF_VARS_4M.fd",
    "/usr/share/OVMF/OVMF_VARS.fd",
    "/usr/share/OVMF/OVMF_VARS_4M.ms.fd",
    "/usr/share/edk2/ovmf/OVMF_VARS.fd",
    "/usr/share/edk2/ovmf/OVMF_VARS.secboot.fd",
    "/usr/share/edk2/ovmf/x64/OVMF_VARS.fd",
    "/usr/share/qemu/OVMF_VARS.fd",
)


def _first_existing(candidates: tuple[str, ...]) -> Path | None:
    for raw in candidates:
        path = Path(raw)
        if path.is_file():
            return path
    return None


def _install_ovmf() -> bool:
    """Install the distro OVMF package when running as root. Returns True if a package manager ran."""
    if os.geteuid() != 0:
        _log.warning("OVMF is missing and h2kvm is not root, so it cannot install the package")
        return False
    if shutil.which("apt-get"):
        _log.info("Installing ovmf (apt) so UEFI boot can proceed")
        subprocess.run(["apt-get", "update", "-qq"], check=False)
        result = subprocess.run(["apt-get", "install", "-y", "ovmf"], check=False)
        return result.returncode == 0
    if shutil.which("dnf"):
        _log.info("Installing edk2-ovmf (dnf) so UEFI boot can proceed")
        result = subprocess.run(["dnf", "install", "-y", "edk2-ovmf"], check=False)
        return result.returncode == 0
    if shutil.which("yum"):
        result = subprocess.run(["yum", "install", "-y", "edk2-ovmf"], check=False)
        return result.returncode == 0
    if shutil.which("zypper"):
        result = subprocess.run(["zypper", "--non-interactive", "install", "-y", "qemu-ovmf-x86_64"], check=False)
        return result.returncode == 0
    return False


def resolve_ovmf_code(preferred: str | None = None) -> Path | None:
    """Return an OVMF code firmware file, installing the package if none is present."""
    if preferred:
        path = Path(preferred)
        if path.is_file():
            return path
    found = _first_existing(OVMF_CODE_CANDIDATES)
    if found:
        return found
    if _install_ovmf():
        if preferred and Path(preferred).is_file():
            return Path(preferred)
        return _first_existing(OVMF_CODE_CANDIDATES)
    return None


def resolve_ovmf_vars(preferred: str | None = None) -> Path | None:
    """Return an OVMF NVRAM template, installing the package if none is present."""
    if preferred:
        path = Path(preferred)
        if path.is_file():
            return path
    found = _first_existing(OVMF_VARS_CANDIDATES)
    if found:
        return found
    if _install_ovmf():
        if preferred and Path(preferred).is_file():
            return Path(preferred)
        return _first_existing(OVMF_VARS_CANDIDATES)
    return None
