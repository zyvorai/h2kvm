# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd-cryptenroll integration for LUKS encryption management.

This module wraps systemd-cryptenroll to manage LUKS encryption,
enroll TPM2/FIDO2 tokens, and handle encrypted volumes during migration.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from h2kvm.systemd._common import check_systemd_binary_available

if TYPE_CHECKING:
    from pathlib import Path


class SystemdCryptenroll:
    """
    Wrapper for systemd-cryptenroll command-line tool.

    Provides LUKS encryption management, TPM2/FIDO2 enrollment,
    and recovery key management for encrypted VM disks.
    """

    def __init__(self, systemd_cryptenroll: str = "systemd-cryptenroll"):
        """
        Initialize systemd-cryptenroll wrapper.

        Parameters
        ----------
        systemd_cryptenroll : str, default="systemd-cryptenroll"
            Path to systemd-cryptenroll binary
        """
        self.binary = systemd_cryptenroll
        self._check_available()

    def _check_available(self) -> None:
        """Check if systemd-cryptenroll is available."""
        check_systemd_binary_available(
            self.binary,
            "systemd-cryptenroll",
            solutions=["Install systemd version 248+ (Debian/Ubuntu: apt install systemd)"],
        )

    def enroll_tpm2(
        self,
        device: Path,
        *,
        tpm2_device: str = "auto",
        tpm2_pcrs: str | None = None,
    ) -> None:
        """
        Enroll TPM2 for LUKS device auto-unlock.

        Parameters
        ----------
        device : Path
            LUKS device path
        tpm2_device : str, default="auto"
            TPM2 device path
        tpm2_pcrs : str | None
            PCR banks to bind to (e.g., "7+14")

        Examples
        --------
        >>> enroll = SystemdCryptenroll()
        >>> enroll.enroll_tpm2(Path("/dev/sda1"), tpm2_pcrs="7+14")
        """
        cmd = [
            self.binary,
            "--tpm2-device",
            tpm2_device,
        ]

        if tpm2_pcrs:
            cmd.extend(["--tpm2-pcrs", tpm2_pcrs])

        cmd.append(str(device))

        subprocess.run(cmd, check=True)

    def enroll_recovery(
        self,
        device: Path,
    ) -> str:
        """
        Enroll recovery key for LUKS device.

        Parameters
        ----------
        device : Path
            LUKS device path

        Returns
        -------
        str
            Recovery key

        Examples
        --------
        >>> enroll = SystemdCryptenroll()
        >>> recovery_key = enroll.enroll_recovery(Path("/dev/sda1"))
        >>> print(f"Recovery key: {recovery_key}")
        """
        cmd = [self.binary, "--recovery-key", str(device)]

        # pylint: disable=duplicate-code
        # reason: mirrors the subprocess.run(...) call shape in
        # h2kvm/systemd/mount.py's mount() and
        # h2kvm/systemd/creds.py's decrypt() -- coincidental, each
        # just captures its own binary's text output.
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )

        # Parse recovery key from output
        for line in result.stdout.splitlines():
            if "recovery key" in line.lower():
                # Extract key from output
                parts = line.split(":")
                if len(parts) > 1:
                    return parts[1].strip()

        return result.stdout.strip()

    def enroll_password(
        self,
        device: Path,
        password: str,
    ) -> None:
        """
        Enroll password for LUKS device.

        Parameters
        ----------
        device : Path
            LUKS device path
        password : str
            Password to enroll

        Examples
        --------
        >>> enroll = SystemdCryptenroll()
        >>> enroll.enroll_password(Path("/dev/sda1"), "my-password")
        """
        cmd = [self.binary, "--password", str(device)]

        subprocess.run(
            cmd,
            input=f"{password}\n{password}\n",
            text=True,
            check=True,
        )

    def wipe_slot(
        self,
        device: Path,
        slot: int | str,
    ) -> None:
        """
        Wipe enrollment slot from LUKS device.

        Parameters
        ----------
        device : Path
            LUKS device path
        slot : int | str
            Slot number or type (e.g., "tpm2", "recovery", "password")

        Examples
        --------
        >>> enroll = SystemdCryptenroll()
        >>> enroll.wipe_slot(Path("/dev/sda1"), "tpm2")
        """
        cmd = [self.binary, "--wipe-slot", str(slot), str(device)]

        subprocess.run(cmd, check=True)
