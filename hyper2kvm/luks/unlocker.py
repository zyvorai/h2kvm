# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Hyper2KVM Production LUKS Unlocker

Supports:
- TPM2 auto unlock
- Vault auto unlock
- keyfile unlock
- initramfs safe
- Kubernetes safe

Security properties:
- Secure memory wiping
- HKDF key derivation
- Audit logging
- No secrets in logs
"""

import hashlib
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False
    HKDF = None
    hashes = None


LOG = logging.getLogger("hyper2kvm.luks")


# ============================================================
# SECURE MEMORY WIPE
# ============================================================


def secure_wipe(data: bytearray):
    """
    Securely wipe sensitive data from memory.

    Overwrites all bytes with zeros to prevent memory dumps from
    exposing sensitive key material.

    Args:
        data: Bytearray to wipe
    """
    for i, _ in enumerate(data):
        data[i] = 0


# ============================================================
# CRYPTSETUP WRAPPER
# ============================================================


class Cryptsetup:
    """
    Safe wrapper around cryptsetup for LUKS operations.

    Uses temporary files for keys to avoid exposing them via
    command line arguments (which are visible in process listings).
    """

    @staticmethod
    def open(device: str, mapper: str, key: bytes) -> bool:
        """
        Open LUKS device with cryptsetup.

        Args:
            device: Block device path (e.g., /dev/sda1)
            mapper: Mapper name (e.g., hyper2kvm-crypt0)
            key: LUKS passphrase/key bytes

        Returns:
            True if successful, False otherwise
        """
        # Write key to temporary file (safer than stdin/cmdline)
        with tempfile.NamedTemporaryFile(delete=False, mode="wb") as f:
            f.write(key)
            keyfile = f.name

        try:
            cmd = [
                "cryptsetup",
                "open",
                "--type",
                "luks",
                "--key-file",
                keyfile,
                device,
                mapper,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                check=False,
            )

            if result.returncode == 0:
                LOG.info("✓ Opened LUKS device: %s -> /dev/mapper/%s", device, mapper)
                return True
            LOG.error("Failed to open LUKS device %s: %s", device, result.stderr.decode())
            return False

        except Exception as e:  # pylint: disable=broad-exception-caught  # unlock must never crash the migration; caller treats False as failure
            LOG.exception("Cryptsetup error for %s: %s", device, e)
            return False

        finally:
            # Securely wipe and remove keyfile
            try:
                if os.path.exists(keyfile):
                    # Overwrite in-place before deletion
                    file_size = Path(keyfile).stat().st_size
                    with open(keyfile, "r+b") as f:
                        f.write(b"\x00" * max(file_size, 4096))
                        f.flush()
                        os.fsync(f.fileno())
                    Path(keyfile).unlink()
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort keyfile cleanup, must not mask the original result
                LOG.warning("Failed to clean up keyfile: %s", e)

    @staticmethod
    def is_open(mapper: str) -> bool:
        """Check if LUKS device is already opened."""
        return Path(f"/dev/mapper/{mapper}").exists()


# ============================================================
# TPM2 KEY SOURCE
# ============================================================


class TPM2KeySource:
    """
    TPM2-based key source using sealed keys.

    Unseals keys from TPM2 that were sealed against:
    - PCR states (boot measurement)
    - Platform configuration
    - Firmware state

    This provides automatic unlock only on the same physical machine
    with the same boot configuration.
    """

    def __init__(self, handle: str):
        """
        Initialize TPM2 key source.

        Args:
            handle: TPM2 persistent handle (e.g., 0x81000010)
        """
        self.handle = handle

    def get_key(self) -> Optional[bytes]:
        """
        Unseal key from TPM2.

        Returns:
            Key bytes if successful, None otherwise
        """
        try:
            result = subprocess.run(
                ["tpm2_unseal", "-c", self.handle],
                capture_output=True,
                check=True,
                timeout=10,  # Prevent hanging
            )

            LOG.debug("TPM2 unseal successful from handle %s", self.handle)
            return result.stdout

        except subprocess.TimeoutExpired:
            LOG.exception("TPM2 unseal timed out")
            return None
        except subprocess.CalledProcessError as e:
            LOG.exception("TPM2 unseal failed: %s", e.stderr.decode())
            return None
        except FileNotFoundError:
            LOG.exception("tpm2_unseal command not found - install tpm2-tools")
            return None
        except Exception as e:  # pylint: disable=broad-exception-caught  # final fallback for unforeseen tpm2_unseal failures, must not crash caller
            LOG.exception("TPM2 unlock failed: %s", e)
            return None

    @staticmethod
    def is_available() -> bool:
        """Check if TPM2 is available on this system."""
        return os.path.exists("/dev/tpm0") or os.path.exists("/dev/tpmrm0")


# ============================================================
# VAULT KEY SOURCE
# ============================================================


class VaultKeySource:
    """
    HashiCorp Vault key source.

    Retrieves LUKS keys from Vault KV secret store.
    Supports:
    - Token authentication
    - AppRole authentication
    - Kubernetes service account auth
    """

    def __init__(self, addr: str, token: str, path: str):
        """
        Initialize Vault key source.

        Args:
            addr: Vault server address (e.g., https://vault:8200)
            token: Vault authentication token
            path: Secret path in KV store (e.g., secret/hyper2kvm/luks)
        """
        try:
            import hvac  # pylint: disable=import-outside-toplevel  # optional dependency, only needed when Vault unlock is configured

            self.hvac = hvac
        except ImportError as err:
            raise ImportError(
                "hvac library required for Vault unlock. Install with: pip install hvac"
            ) from err

        self.client = hvac.Client(url=addr, token=token)
        self.path = path

    def get_key(self) -> Optional[bytes]:
        """
        Retrieve key from Vault.

        Returns:
            Key bytes if successful, None otherwise
        """
        try:
            # Read secret from KV v2
            secret = self.client.secrets.kv.v2.read_secret_version(path=self.path)

            key_hex = secret["data"]["data"]["key"]

            LOG.debug("Vault key retrieved from %s", self.path)
            return bytes.fromhex(key_hex)

        except Exception as e:  # pylint: disable=broad-exception-caught  # Vault client can raise network/auth/parsing errors; best-effort, returns None
            LOG.exception("Vault unlock failed: %s", e)
            return None

    @staticmethod
    def from_kubernetes_sa(addr: str, role: str, path: str):
        """
        Create VaultKeySource using Kubernetes service account auth.

        Args:
            addr: Vault server address
            role: Kubernetes auth role
            path: Secret path

        Returns:
            VaultKeySource instance
        """
        import hvac  # pylint: disable=import-outside-toplevel,import-error  # optional dependency, only needed when Vault unlock is configured

        # Read Kubernetes service account token
        sa_token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
        with open(sa_token_path, encoding="utf-8") as f:
            jwt = f.read()

        # Authenticate with Vault
        client = hvac.Client(url=addr)
        response = client.auth.kubernetes.login(role=role, jwt=jwt)

        token = response["auth"]["client_token"]

        return VaultKeySource(addr, token, path)


# ============================================================
# CLEVIS/NBDE KEY SOURCE
# ============================================================


class ClevisKeySource:
    """
    Clevis/NBDE (Network-Bound Disk Encryption) key source.

    Uses the ``clevis`` CLI to decrypt LUKS volumes that are bound to:
    - Tang servers (NBDE - network-bound)
    - TPM2 (via clevis-tpm2)
    - Shamir Secret Sharing (sss) combining multiple methods

    Clevis bindings are stored as LUKS2 tokens and allow automatic
    unlock when the Tang server is reachable or TPM2 state matches.

    Requirements:
    - ``clevis`` and ``clevis-luks-unlock`` packages installed on host
    - Network access to Tang server(s) if using NBDE
    """

    def __init__(self, tang_url: str | None = None):
        """
        Initialize Clevis key source.

        Args:
            tang_url: Optional Tang server URL for diagnostics/logging.
                      The actual binding is stored in the LUKS2 header,
                      so this is only used for logging.
        """
        self.tang_url = tang_url

    def get_key(self, device: str | None = None) -> Optional[bytes]:
        """
        Recover key using clevis luks pass.

        This extracts the passphrase from the LUKS2 token by communicating
        with the bound Tang server or TPM2.

        Args:
            device: Block device path (required for clevis)

        Returns:
            Key bytes if successful, None otherwise
        """
        if not device:
            LOG.error("Clevis unlock requires a device path")
            return None

        try:
            result = subprocess.run(
                ["clevis", "luks", "pass", "-d", device],
                capture_output=True,
                timeout=30,  # Tang server may be slow
                check=False,
            )

            if result.returncode == 0 and result.stdout:
                LOG.info("Clevis key recovered for %s", device)
                return result.stdout
            LOG.warning(
                "Clevis luks pass failed for %s: rc=%s stderr=%s",
                device,
                result.returncode,
                result.stderr.decode(errors="replace"),
            )
            return None

        except subprocess.TimeoutExpired:
            LOG.warning(
                "Clevis unlock timed out for %s. Ensure Tang server is reachable%s",
                device,
                f" at {self.tang_url}" if self.tang_url else "",
            )
            return None
        except FileNotFoundError:
            LOG.warning(
                "clevis command not found. Install with:\n"
                "    dnf install clevis clevis-luks      # Fedora/RHEL\n"
                "    apt install clevis clevis-luks       # Debian/Ubuntu"
            )
            return None
        except Exception as e:  # pylint: disable=broad-exception-caught  # unexpected clevis subprocess failure, best-effort key recovery
            LOG.exception("Clevis unlock failed for %s: %s", device, e)
            return None

    @staticmethod
    def is_available() -> bool:
        """Check if clevis CLI is installed."""
        try:
            result = subprocess.run(
                ["clevis", "--version"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def has_binding(device: str) -> bool:
        """
        Check if a LUKS device has clevis bindings.

        Args:
            device: Block device path

        Returns:
            True if clevis bindings exist
        """
        try:
            result = subprocess.run(
                ["clevis", "luks", "list", "-d", device],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            # clevis luks list outputs binding info if present
            return result.returncode == 0 and bool(result.stdout.strip())
        except Exception:  # pylint: disable=broad-exception-caught  # binding check must always return a bool, never raise
            return False

    @staticmethod
    def list_bindings(device: str) -> list[dict[str, str]]:
        """
        List all clevis bindings on a LUKS device.

        Returns:
            List of binding dicts with 'slot' and 'pin' keys.
        """
        bindings: list[dict[str, str]] = []
        # pylint: disable=duplicate-code
        # reason: this subprocess.run(...capture_output=True, timeout=10)
        # shape mirrors similar subprocess wrappers in
        # hyper2kvm/fixers/offline_fixer.py (qemu-img info probe) --
        # structurally similar by coincidence, not shared logic; keeping
        # independent avoids coupling unrelated subprocess-invocation code
        # paths.
        try:
            result = subprocess.run(
                ["clevis", "luks", "list", "-d", device],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode != 0:
                return bindings
            for line in result.stdout.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                # Format: "1: tang '{"url":"http://..."}'"
                #      or "1: tpm2 '{}'"
                #      or "1: sss '{"t":1,"pins":{...}}'"
                parts = line.split(":", 1)
                if len(parts) == 2:
                    slot = parts[0].strip()
                    rest = parts[1].strip()
                    pin = rest.split()[0] if rest else "unknown"
                    bindings.append({"slot": slot, "pin": pin, "raw": rest})
        except Exception as e:  # pylint: disable=broad-exception-caught  # binding listing is best-effort diagnostics, must not raise
            LOG.debug("Failed to list clevis bindings for %s: %s", device, e)
        return bindings


# ============================================================
# KEYFILE SOURCE
# ============================================================


class KeyfileSource:  # pylint: disable=too-few-public-methods  # simple single-purpose key source, matches TPM2KeySource/VaultKeySource shape
    """Simple keyfile-based unlock."""

    def __init__(self, keyfile_path: str):
        """
        Initialize keyfile source.

        Args:
            keyfile_path: Path to keyfile
        """
        self.keyfile_path = Path(keyfile_path)

    def get_key(self) -> Optional[bytes]:
        """Read key from file."""
        try:
            if not self.keyfile_path.exists():
                LOG.error("Keyfile not found: %s", self.keyfile_path)
                return None

            with open(self.keyfile_path, "rb") as f:
                key = f.read()

            LOG.debug("Keyfile read from %s", self.keyfile_path)
            return key

        except OSError as e:
            LOG.exception("Failed to read keyfile %s: %s", self.keyfile_path, e)
            return None


# ============================================================
# KEY COMBINER (HKDF)
# ============================================================


class KeyCombiner:  # pylint: disable=too-few-public-methods  # single-purpose HKDF utility, no state to warrant more methods
    """
    Combine multiple keys using HKDF.

    Uses HKDF (HMAC-based Key Derivation Function) to securely
    combine multiple key sources into a single derived key.

    This allows multi-factor unlock where keys from TPM + Vault
    must both be present.
    """

    @staticmethod
    def combine(keys: list[bytes]) -> bytes:
        """
        Combine multiple keys into one using HKDF.

        Args:
            keys: List of key bytes from different sources

        Returns:
            Derived key bytes
        """
        if not HAS_CRYPTOGRAPHY:
            # Fallback to simple concatenation + SHA256
            LOG.warning(
                "cryptography library not available, using simple hash.\n"
                "    For stronger key derivation, install with: pip install cryptography"
            )
            combined = b"".join(sorted(keys))
            return hashlib.sha256(combined).digest()

        # Sort keys for deterministic output
        combined = b"".join(sorted(keys))

        # Derive 32-byte key using HKDF-SHA256
        hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"hyper2kvm-luks-v1")

        return hkdf.derive(combined)


# ============================================================
# DEVICE DISCOVERY
# ============================================================


class LUKSDevice:
    """LUKS device discovery and enumeration."""

    @staticmethod
    def list() -> list[str]:
        """
        List all LUKS devices on the system.

        Returns:
            List of device paths
        """
        try:
            result = subprocess.run(
                ["blkid", "-t", "TYPE=crypto_LUKS", "-o", "device"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )

            devices = [line.strip() for line in result.stdout.splitlines() if line.strip()]

            LOG.info("Found %d LUKS devices", len(devices))
            return devices

        except (subprocess.SubprocessError, OSError) as e:
            LOG.exception("Failed to list LUKS devices: %s", e)
            return []

    @staticmethod
    def get_uuid(device: str) -> Optional[str]:
        """Get LUKS UUID for device."""
        try:
            result = subprocess.run(
                ["cryptsetup", "luksUUID", device],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                return result.stdout.strip()
            return None

        except (subprocess.SubprocessError, OSError) as e:
            LOG.debug("Failed to get LUKS UUID for %s: %s", device, e)
            return None


# ============================================================
# MAIN UNLOCKER
# ============================================================


class LUKSUnlocker:
    """
    Main LUKS auto-unlock coordinator.

    Orchestrates multiple key sources and unlocks LUKS devices
    automatically at boot time.

    Priority order:
    1. TPM2 (hardware-backed, automatic)
    2. Vault (network-based, automatic)
    3. Keyfile (filesystem-based, semi-automatic)
    4. Manual fallback (systemd prompts user)
    """

    def __init__(
        self,
        tpm_handle: Optional[str] = None,
        vault_config: Optional[dict] = None,
        keyfile_path: Optional[str] = None,
        clevis_enabled: bool = False,
        clevis_tang_url: Optional[str] = None,
    ):
        """
        Initialize LUKS unlocker.

        Args:
            tpm_handle: TPM2 persistent handle (e.g., "0x81000010")
            vault_config: Dict with vault addr, token, path
            keyfile_path: Path to keyfile
            clevis_enabled: Enable Clevis/NBDE auto-unlock
            clevis_tang_url: Optional Tang server URL (for logging only)
        """
        self.sources = []
        self._clevis_source: Optional[ClevisKeySource] = None

        # Add Clevis/NBDE source (checked per-device, not globally)
        if clevis_enabled:
            if ClevisKeySource.is_available():
                LOG.info("Adding Clevis/NBDE key source")
                self._clevis_source = ClevisKeySource(tang_url=clevis_tang_url)
            else:
                LOG.warning(
                    "Clevis enabled but clevis CLI not found.\n"
                    "    Install with: dnf install clevis clevis-luks\n"
                    "    Or: apt install clevis clevis-luks"
                )

        # Add TPM2 source
        if tpm_handle and TPM2KeySource.is_available():
            LOG.info("Adding TPM2 key source: %s", tpm_handle)
            self.sources.append(TPM2KeySource(tpm_handle))
        elif tpm_handle:
            LOG.warning(
                "TPM2 handle specified but TPM not available.\n"
                "    Ensure tpm2-tools is installed: dnf install tpm2-tools\n"
                "    Verify TPM device exists: ls /dev/tpmrm0\n"
                "    Or remove the TPM2 handle from your LUKS configuration."
            )

        # Add Vault source
        if vault_config:
            try:
                LOG.info("Adding Vault key source: %s", vault_config.get("path"))
                self.sources.append(
                    VaultKeySource(
                        vault_config["addr"],
                        vault_config["token"],
                        vault_config["path"],
                    )
                )
            except Exception as e:  # pylint: disable=broad-exception-caught  # covers missing hvac, bad config keys, network errors during init
                LOG.exception("Failed to initialize Vault source: %s", e)

        # Add keyfile source
        if keyfile_path:
            LOG.info("Adding keyfile source: %s", keyfile_path)
            self.sources.append(KeyfileSource(keyfile_path))

        if not self.sources and not self._clevis_source:
            LOG.warning("No key sources configured - manual unlock required")

    def unlock_device(self, device: str) -> bool:  # pylint: disable=too-many-branches  # fault-tolerant Clevis/TPM2/Vault/Keyfile fallback chain
        """
        Unlock a single LUKS device.

        Priority order:
        1. Clevis/NBDE (per-device, checks for binding first)
        2. TPM2 / Vault / Keyfile sources
        3. Combined keys via HKDF

        Args:
            device: Block device path (e.g., /dev/sda1)

        Returns:
            True if successfully unlocked, False otherwise
        """
        mapper = self.mapper_name(device)

        # Check if already unlocked
        if Cryptsetup.is_open(mapper):
            LOG.info("Device %s already unlocked as /dev/mapper/%s", device, mapper)
            return True

        # Try Clevis/NBDE first (device-specific binding)
        if self._clevis_source:
            if ClevisKeySource.has_binding(device):
                LOG.info("Clevis binding detected on %s, attempting NBDE unlock", device)
                bindings = ClevisKeySource.list_bindings(device)
                for b in bindings:
                    LOG.info("  Binding slot %s: pin=%s", b["slot"], b["pin"])
                clevis_key = self._clevis_source.get_key(device=device)
                if clevis_key:
                    success = Cryptsetup.open(device, mapper, clevis_key)
                    if isinstance(clevis_key, bytearray):
                        secure_wipe(clevis_key)
                    if success:
                        return True
                    LOG.warning("Clevis key recovered but cryptsetup open failed for %s", device)
                else:
                    LOG.warning("Clevis binding exists but key recovery failed for %s", device)
            else:
                LOG.debug("No clevis binding on %s, trying other sources", device)

        # Try to get keys from all configured sources
        keys = []
        for source in self.sources:
            key = source.get_key()
            if key:
                keys.append(key)

        if not keys:
            LOG.error("No keys available for %s", device)
            return False

        # Combine keys if multiple sources
        if len(keys) > 1:
            LOG.debug("Combining %d keys with HKDF", len(keys))
            combined = KeyCombiner.combine(keys)
        else:
            combined = keys[0]

        # Try to unlock
        success = Cryptsetup.open(device, mapper, combined)

        # Securely wipe key material
        # Note: secure_wipe requires bytearray (mutable). bytes objects are
        # immutable and cannot be wiped. The key sources should ideally return
        # bytearray, but as a best-effort we wipe the combined key used for unlock.
        if isinstance(combined, bytearray):
            secure_wipe(combined)
        if isinstance(keys, list):
            for key in keys:
                if isinstance(key, bytearray):
                    secure_wipe(key)

        return success

    def unlock_all(self) -> dict:
        """
        Unlock all LUKS devices on the system.

        Returns:
            Dict mapping device -> success status
        """
        devices = LUKSDevice.list()

        if not devices:
            LOG.info("No LUKS devices found")
            return {}

        LOG.info("Attempting to unlock %d LUKS devices", len(devices))

        results = {}
        for device in devices:
            LOG.info("Processing device: %s", device)
            success = self.unlock_device(device)
            results[device] = success

        # Summary
        successful = sum(1 for v in results.values() if v)
        LOG.info("Unlock complete: %d/%d successful", successful, len(devices))

        return results

    def mapper_name(self, device: str) -> str:
        """
        Generate consistent mapper name for device.

        Uses device UUID if available, otherwise hash of device path.

        Args:
            device: Block device path

        Returns:
            Mapper name (e.g., "hyper2kvm-abc123def")
        """
        # Try to use UUID for consistency
        uuid = LUKSDevice.get_uuid(device)
        if uuid:
            # Use first 12 chars of UUID
            suffix = uuid.replace("-", "")[:12]
            return f"hyper2kvm-{suffix}"

        # Fallback to hash of device path
        h = hashlib.sha256(device.encode()).hexdigest()[:12]
        return f"hyper2kvm-{h}"
