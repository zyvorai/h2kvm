# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd-creds integration for credential management.

This module wraps systemd-creds to provide secure credential storage
and encryption for VM migration credentials (vCenter passwords, cloud keys, etc.).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from hyper2kvm.systemd._common import check_systemd_binary_available


class SystemdCreds:
    """
    Wrapper for systemd-creds command-line tool.

    Provides secure credential encryption, decryption, and management
    for storing sensitive migration credentials.
    """

    def __init__(self, systemd_creds: str = "systemd-creds"):
        """
        Initialize systemd-creds wrapper.

        Parameters
        ----------
        systemd_creds : str, default="systemd-creds"
            Path to systemd-creds binary
        """
        self.binary = systemd_creds
        self._check_available()

    def _check_available(self) -> None:
        """Check if systemd-creds is available."""
        check_systemd_binary_available(
            self.binary,
            "systemd-creds",
            solutions=["Install systemd version 250+ (Debian/Ubuntu: apt install systemd)"],
        )

    def encrypt(
        self,
        data: str | bytes,
        name: str | None = None,
        *,
        output: Path | None = None,
    ) -> Path | bytes:
        """
        Encrypt credential data.

        Parameters
        ----------
        data : str | bytes
            Data to encrypt
        name : str | None
            Credential name
        output : Path | None
            Output file path (if None, returns encrypted data)

        Returns
        -------
        Path | bytes
            Path to encrypted file or encrypted data

        Examples
        --------
        >>> creds = SystemdCreds()
        >>> encrypted = creds.encrypt("my-password", "vcenter-password")
        """
        cmd = [self.binary, "encrypt"]

        if name:
            cmd.extend(["--name", name])

        if output:
            cmd.extend(["--output", str(output)])

        # Write data to stdin
        if isinstance(data, str):
            data = data.encode()

        result = subprocess.run(
            cmd,
            input=data,
            capture_output=True,
            check=True,
        )

        if output:
            return output
        return result.stdout

    def decrypt(
        self,
        encrypted_data: Path | bytes,
    ) -> str:
        """
        Decrypt credential data.

        Parameters
        ----------
        encrypted_data : Path | bytes
            Encrypted data or path to encrypted file

        Returns
        -------
        str
            Decrypted credential

        Examples
        --------
        >>> creds = SystemdCreds()
        >>> password = creds.decrypt(Path("/etc/credentials/password.cred"))
        """
        cmd = [self.binary, "decrypt"]

        if isinstance(encrypted_data, Path):
            cmd.append(str(encrypted_data))
            # pylint: disable=duplicate-code
            # reason: mirrors the subprocess.run(...) call shape in
            # hyper2kvm/systemd/cryptenroll.py's enroll_recovery() --
            # coincidental, both just capture their own binary's text output.
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
        else:
            result = subprocess.run(
                cmd,
                input=encrypted_data,
                capture_output=True,
                text=True,
                check=True,
            )

        return result.stdout.strip()

    def setup(
        self,
        *,
        tpm2_device: str | None = None,
    ) -> None:
        """
        Set up credential encryption.

        Parameters
        ----------
        tpm2_device : str | None
            TPM2 device path

        Examples
        --------
        >>> creds = SystemdCreds()
        >>> creds.setup()
        """
        cmd = [self.binary, "setup"]

        if tpm2_device:
            cmd.extend(["--tpm2-device", tpm2_device])

        subprocess.run(cmd, check=True)

    def has_tpm2(self) -> bool:
        """
        Check if TPM2 is available for credential encryption.

        Returns
        -------
        bool
            True if TPM2 available, False otherwise

        Examples
        --------
        >>> creds = SystemdCreds()
        >>> if creds.has_tpm2():
        ...     print("TPM2 available for secure credential storage")
        """
        cmd = [self.binary, "has-tpm2"]

        result = subprocess.run(
            cmd,
            capture_output=True,
            check=False,
        )

        return result.returncode == 0
