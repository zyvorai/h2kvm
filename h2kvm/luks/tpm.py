# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
TPM2 Key Sealing for LUKS

Seals LUKS keys to TPM2 PCRs for automatic unlock.

Security properties:
- Keys only unseal on same machine
- Keys only unseal with same boot state
- Keys bound to PCR measurements (firmware, bootloader, kernel)
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

LOG = logging.getLogger("h2kvm.luks.tpm")


class TPMSealer:
    """
    TPM2 key sealing operations.

    Seals keys to TPM2 with PCR policy, ensuring keys
    can only be unsealed when:
    - Same physical machine (TPM is hardware-bound)
    - Same boot state (PCRs match)
    - Same firmware/kernel (measured boot)
    """

    def __init__(self):
        """Initialize TPM sealer."""
        self._check_tpm_available()

    def _check_tpm_available(self):
        """Verify TPM2 is available."""
        if not os.path.exists("/dev/tpm0") and not os.path.exists("/dev/tpmrm0"):
            raise RuntimeError(
                "TPM2 device not found (/dev/tpm0 or /dev/tpmrm0). "
                "Ensure the system has a TPM2 chip and the tpm_tis or tpm_crb kernel module is loaded. "
                "Try: sudo modprobe tpm_crb"
            )

        # Check tpm2-tools is installed
        try:
            subprocess.run(
                ["tpm2_pcrread"],
                capture_output=True,
                check=True,
            )
        except FileNotFoundError as err:
            raise RuntimeError(
                "tpm2-tools is not installed. Install it with: "
                "sudo dnf install tpm2-tools (Fedora/RHEL) or sudo apt install tpm2-tools (Debian/Ubuntu)"
            ) from err
        except subprocess.CalledProcessError:
            # May fail if no TPM, but command exists
            pass

    def seal_key(
        self,
        key: bytes,
        pcrs: Optional[list[int]] = None,
        handle: str = "0x81000010",
    ) -> str:
        """
        Seal key to TPM2 with PCR policy.

        Args:
            key: Key bytes to seal
            pcrs: List of PCR indices to seal against (default: [0,1,2,3,7])
            handle: Persistent handle to store at

        Returns:
            Handle where key is stored

        Raises:
            RuntimeError: If sealing fails
        """
        if pcrs is None:
            # Default PCRs:
            # 0 = BIOS/UEFI
            # 1 = BIOS/UEFI config
            # 2 = Option ROMs
            # 3 = MBR/GPT
            # 7 = Secure Boot state
            pcrs = [0, 1, 2, 3, 7]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Write key to file
            key_file = tmpdir / "luks.key"
            with open(key_file, "wb") as f:
                f.write(key)

            # Create primary object
            LOG.debug("Creating TPM2 primary object")
            primary_ctx = tmpdir / "primary.ctx"
            subprocess.run(
                [
                    "tpm2_createprimary",
                    "-C",
                    "o",  # Owner hierarchy
                    "-c",
                    str(primary_ctx),
                ],
                check=True,
                capture_output=True,
            )

            # Create PCR policy
            LOG.debug("Creating PCR policy for PCRs: %s", pcrs)
            policy = tmpdir / "policy.dat"
            pcr_list = ",".join(f"sha256:{p}" for p in pcrs)

            subprocess.run(
                [
                    "tpm2_createpolicy",
                    "--policy-pcr",
                    "-l",
                    pcr_list,
                    "-L",
                    str(policy),
                ],
                check=True,
                capture_output=True,
            )

            # Create sealed object
            LOG.debug("Creating sealed TPM2 object")
            key_pub = tmpdir / "key.pub"
            key_priv = tmpdir / "key.priv"

            subprocess.run(
                [
                    "tpm2_create",
                    "-C",
                    str(primary_ctx),
                    "-u",
                    str(key_pub),
                    "-r",
                    str(key_priv),
                    "-i",
                    str(key_file),
                    "-L",
                    str(policy),
                    "-a",
                    "fixedtpm|fixedparent",
                ],
                check=True,
                capture_output=True,
            )

            # Load object
            LOG.debug("Loading sealed object")
            key_ctx = tmpdir / "key.ctx"
            subprocess.run(
                [
                    "tpm2_load",
                    "-C",
                    str(primary_ctx),
                    "-u",
                    str(key_pub),
                    "-r",
                    str(key_priv),
                    "-c",
                    str(key_ctx),
                ],
                check=True,
                capture_output=True,
            )

            # Persist to handle
            LOG.debug("Persisting to handle %s", handle)
            subprocess.run(
                [
                    "tpm2_evictcontrol",
                    "-C",
                    "o",
                    "-c",
                    str(key_ctx),
                    handle,
                ],
                check=True,
                capture_output=True,
            )

        LOG.info("✓ Key sealed to TPM2 handle %s", handle)
        return handle

    def unseal_key(self, handle: str, pcrs: Optional[list[int]] = None) -> Optional[bytes]:
        """
        Unseal key from TPM2.

        Args:
            handle: Persistent handle
            pcrs: PCR list (must match what was used to seal)

        Returns:
            Unsealed key bytes, or None if failed
        """
        if pcrs is None:
            pcrs = [0, 1, 2, 3, 7]

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir = Path(tmpdir)

                # Create PCR policy session
                policy = tmpdir / "policy.dat"
                pcr_list = ",".join(f"sha256:{p}" for p in pcrs)

                subprocess.run(
                    [
                        "tpm2_createpolicy",
                        "--policy-pcr",
                        "-l",
                        pcr_list,
                        "-L",
                        str(policy),
                    ],
                    check=True,
                    capture_output=True,
                )

                # Start auth session
                session = tmpdir / "session.ctx"
                subprocess.run(
                    [
                        "tpm2_startauthsession",
                        "--policy-session",
                        "-S",
                        str(session),
                    ],
                    check=True,
                    capture_output=True,
                )

                # Load policy
                subprocess.run(
                    [
                        "tpm2_policypcr",
                        "-S",
                        str(session),
                        "-l",
                        pcr_list,
                        "-L",
                        str(policy),
                    ],
                    check=True,
                    capture_output=True,
                )

                # Unseal
                result = subprocess.run(
                    [
                        "tpm2_unseal",
                        "-c",
                        handle,
                        "-p",
                        f"session:{session}",
                    ],
                    check=True,
                    capture_output=True,
                )

                return result.stdout

        except subprocess.CalledProcessError as e:
            LOG.exception("TPM2 unseal failed: %s", e)
            return None

    def read_pcrs(self, pcrs: Optional[list[int]] = None) -> dict:
        """
        Read current PCR values.

        Args:
            pcrs: PCR indices to read (default: all)

        Returns:
            Dict mapping PCR index -> hex value
        """
        if pcrs:
            pcr_list = ",".join(f"sha256:{p}" for p in pcrs)
            cmd = ["tpm2_pcrread", "sha256:" + pcr_list]
        else:
            cmd = ["tpm2_pcrread"]

        # pylint: disable=duplicate-code
        # reason: mirrors the equivalent subprocess.run(...) invocation in
        # h2kvm/systemd/analyze.py's verify() -- generic subprocess-call shape,
        # not shared logic worth extracting across unrelated tpm2/systemd tooling.
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        # Parse output
        pcr_values = {}
        for line in result.stdout.splitlines():
            if ":" in line and "0x" in line:
                parts = line.split(":")
                if len(parts) >= 2:
                    try:
                        pcr_num = int(parts[0].strip())
                        pcr_val = parts[1].strip()
                        pcr_values[pcr_num] = pcr_val
                    except ValueError:
                        continue

        return pcr_values

    def clear_handle(self, handle: str):
        """
        Clear a persistent TPM2 handle.

        Args:
            handle: Handle to clear
        """
        try:
            subprocess.run(
                [
                    "tpm2_evictcontrol",
                    "-C",
                    "o",
                    "-c",
                    handle,
                ],
                check=True,
                capture_output=True,
            )
            LOG.info("✓ Cleared TPM2 handle %s", handle)
        except subprocess.CalledProcessError as e:
            LOG.exception("Failed to clear handle %s: %s", handle, e)
