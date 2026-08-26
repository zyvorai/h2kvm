# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Windows license information extraction.

Extracts Windows product keys, license type, and activation state from
offline registry hives for preservation during VM migration.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class LicenseType(Enum):
    """Windows license types."""

    RETAIL = "Retail"
    OEM = "OEM"
    MAK = "MAK"  # Multiple Activation Key
    KMS = "KMS"  # Key Management Service
    VOLUME = "Volume"
    UNKNOWN = "Unknown"


@dataclass
class LicenseInfo:  # pylint: disable=too-many-instance-attributes  # models every field of extracted Windows license/activation data
    """Windows license information."""

    product_key: Optional[str] = None
    license_type: LicenseType = LicenseType.UNKNOWN
    product_id: Optional[str] = None
    kms_server: Optional[str] = None
    kms_port: Optional[int] = None
    activation_status: Optional[str] = None
    licensed_product_name: Optional[str] = None
    edition: Optional[str] = None
    is_activated: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "product_key": self.product_key,
            "license_type": self.license_type.value,
            "product_id": self.product_id,
            "kms_server": self.kms_server,
            "kms_port": self.kms_port,
            "activation_status": self.activation_status,
            "licensed_product_name": self.licensed_product_name,
            "edition": self.edition,
            "is_activated": self.is_activated,
        }


def extract_license_info(guestfs, root: str) -> LicenseInfo:
    """Extract Windows license information from offline registry.

    Args:
        guestfs: GuestFS instance with mounted filesystem
        root: Root path of Windows installation

    Returns:
        LicenseInfo object with extracted license data

    Raises:
        RuntimeError: If registry hives cannot be accessed
    """
    # pylint: disable=import-outside-toplevel  # keeps registry/hivex machinery optional for callers that never touch licensing
    import tempfile
    from pathlib import Path

    from h2kvm.fixers.windows.registry.io import detect_windows_hive, download_and_open_hive

    logger.info("Extracting Windows license information")

    license_info = LicenseInfo()

    try:
        # Locate SOFTWARE hive
        software_path = detect_windows_hive(guestfs, root, "SOFTWARE")
        if not software_path:
            logger.warning("SOFTWARE hive not found")
            return license_info

        # Download and open hive
        from h2kvm.fixers.windows.registry.encoding import (  # pylint: disable=import-outside-toplevel
            _close_best_effort,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            local_hive = Path(tmpdir) / "SOFTWARE"
            hive = download_and_open_hive(logger, guestfs, software_path, local_hive, write=False)

            try:
                # Extract license data from registry
                license_data = _read_license_registry_values(hive)

                # Decode product key
                license_info.product_key = decode_product_key(license_data)

                # Extract product ID
                license_info.product_id = license_data.get("ProductId")

                # Extract edition
                license_info.edition = license_data.get("EditionID")
                license_info.licensed_product_name = license_data.get("ProductName")

                # Detect license type
                license_info.license_type = detect_license_type(license_data)

                # Extract KMS information if applicable
                if license_info.license_type == LicenseType.KMS:
                    license_info.kms_server = license_data.get("KeyManagementServiceName")
                    kms_port_str = license_data.get("KeyManagementServicePort")
                    if kms_port_str:
                        try:
                            license_info.kms_port = int(kms_port_str)
                        except (ValueError, TypeError):
                            license_info.kms_port = 1688  # Default KMS port

                # Determine activation status
                license_info.activation_status = _determine_activation_status(license_data)
                license_info.is_activated = license_info.activation_status == "Licensed"

                logger.info(
                    "Extracted license info: type=%s, edition=%s, activated=%s",
                    license_info.license_type.value,
                    license_info.edition,
                    license_info.is_activated,
                )
            finally:
                _close_best_effort(hive)

    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort license extraction must not abort the migration
        logger.exception("Failed to extract license information: %s", e)
        logger.debug("License extraction error", exc_info=True)

    return license_info


def _read_license_registry_values(hive) -> dict:
    """Read license-related registry values from SOFTWARE hive.

    Args:
        hive: Opened SOFTWARE registry hive

    Returns:
        Dictionary of extracted registry values
    """
    from h2kvm.fixers.windows.registry.encoding import (  # pylint: disable=import-outside-toplevel
        _hivex_read_sz,
        _hivex_read_value_dict,
        _node_id,
    )

    # pylint: disable=duplicate-code
    # reason: mirrors _read_registry_sz_value in
    # h2kvm/fixers/windows/activedirectory/extractor.py -- both are small
    # hivex key-path readers local to unrelated fixer domains (licensing vs.
    # AD); a shared home belongs in registry/encoding.py, out of scope here.
    def _navigate_key(h, key_path: str):
        """Navigate hivex hive to a registry key path (backslash-separated)."""
        node = h.root()
        for component in key_path.split("\\"):
            if not component:
                continue
            child = h.node_get_child(node, component)
            if not _node_id(child):
                return None
            node = child
        return node

    def _read_registry_value(h, key_path: str, value_name: str):
        """Read a registry value by navigating key_path and reading value_name."""
        node = _navigate_key(h, key_path)
        if node is None:
            return None
        # Try reading as string first
        result = _hivex_read_sz(h, node, value_name)
        if result is not None:
            return result
        # Fall back to raw value dict (for binary values like DigitalProductId)
        vd = _hivex_read_value_dict(h, node, value_name)
        if vd is not None:
            raw = vd.get("value")
            if raw is not None:
                return raw
        return None

    keys_to_read = {
        # Windows 8+ encrypted product key
        "DigitalProductId4": r"Microsoft\Windows NT\CurrentVersion",
        # Windows 7 and earlier product key
        "DigitalProductId": r"Microsoft\Windows NT\CurrentVersion",
        # Product ID
        "ProductId": r"Microsoft\Windows NT\CurrentVersion",
        # Edition information
        "EditionID": r"Microsoft\Windows NT\CurrentVersion",
        "ProductName": r"Microsoft\Windows NT\CurrentVersion",
        # KMS information
        "KeyManagementServiceName": r"Microsoft\Windows NT\CurrentVersion\SoftwareProtectionPlatform",
        "KeyManagementServicePort": r"Microsoft\Windows NT\CurrentVersion\SoftwareProtectionPlatform",
        # Activation information (limited offline access)
        "VLActivationInterval": r"Microsoft\Windows NT\CurrentVersion\SoftwareProtectionPlatform",
        "VLRenewalInterval": r"Microsoft\Windows NT\CurrentVersion\SoftwareProtectionPlatform",
        # License channel
        "Channel": r"Microsoft\Windows NT\CurrentVersion",
    }

    license_data = {}

    for value_name, key_path in keys_to_read.items():
        try:
            value = _read_registry_value(hive, key_path, value_name)
            if value is not None:
                license_data[value_name] = value
        except Exception as e:  # pylint: disable=broad-exception-caught  # hivex raises dynamic/untyped errors; one missing value must not abort the read
            logger.debug("Could not read %s\\%s: %s", key_path, value_name, e)
            continue

    return license_data


def decode_product_key(license_data: dict) -> Optional[str]:
    """Decode Windows product key from DigitalProductId.

    Implements Microsoft's product key encoding algorithm for both
    Windows 7 (DigitalProductId) and Windows 8+ (DigitalProductId4).

    Args:
        license_data: Dictionary containing DigitalProductId binary data

    Returns:
        Formatted product key (XXXXX-XXXXX-XXXXX-XXXXX-XXXXX) or None

    Note:
        Windows 8+ uses a different encoding scheme than Windows 7.
        This function handles both variants.
    """
    # Try Windows 8+ format first
    dpid4 = license_data.get("DigitalProductId4")
    if dpid4:
        try:
            return _decode_dpid4(dpid4)
        # pylint: disable-next=broad-exception-caught  # decoder can fail many ways on bad data; fall back to Windows 7 format
        except Exception as e:
            logger.debug("Failed to decode DigitalProductId4: %s", e)

    # Fall back to Windows 7 format
    dpid = license_data.get("DigitalProductId")
    if dpid:
        try:
            return _decode_dpid(dpid)
        except Exception as e:  # pylint: disable=broad-exception-caught  # decoder can fail in many ways on malformed/corrupted registry data
            logger.debug("Failed to decode DigitalProductId: %s", e)

    return None


def _decode_dpid4(dpid_bytes: bytes) -> str:
    """Decode Windows 8+ DigitalProductId4.

    Windows 8+ uses a modified base-24 encoding with a 3-byte header.

    Args:
        dpid_bytes: Binary DigitalProductId4 data

    Returns:
        Formatted 25-character product key
    """
    if len(dpid_bytes) < 0x328:  # Minimum required size
        raise ValueError(
            f"Windows DigitalProductId4 data too short ({len(dpid_bytes)} bytes, need >= {0x328}). "
            f"The registry value may be corrupted."
        )

    # Key data starts at offset 0x328 (808 decimal)
    key_offset = 0x328
    key_length = 15  # 15 bytes encode to 25 characters

    if len(dpid_bytes) < key_offset + key_length:
        raise ValueError(
            f"Windows DigitalProductId4 data truncated at key region "
            f"({len(dpid_bytes)} bytes, need >= {key_offset + key_length}). "
            f"The registry value may be corrupted."
        )

    # Extract key bytes
    key_bytes = bytearray(dpid_bytes[key_offset : key_offset + key_length])

    # Character set for base-24 encoding (Windows 8+ variant)
    chars = "BCDFGHJKMPQRTVWXY2346789"

    # Windows 8+ includes an 'N' check digit
    # Byte at offset 0x8 (8) indicates if 'N' should be injected
    contains_n = (dpid_bytes[key_offset + 8] >> 3) & 1

    decoded_chars = []

    # Decode 25 characters
    for _i in range(25):
        char_index = 0

        # Process bytes in reverse
        for j in range(14, -1, -1):
            char_index = (char_index << 8) | key_bytes[j]
            key_bytes[j] = char_index // 24
            char_index %= 24

        decoded_chars.append(chars[char_index])

    # Reverse to get correct order
    decoded_chars.reverse()

    # Insert 'N' if required (Windows 8+ retail vs OEM indicator)
    # Replace the character at position n_pos (not insert) to maintain 25 chars
    if contains_n:
        n_pos = (dpid_bytes[key_offset + 8] & 0x07) % 24
        decoded_chars[n_pos] = "N"

    product_key = "".join(decoded_chars)

    # Format as XXXXX-XXXXX-XXXXX-XXXXX-XXXXX
    return _format_product_key(product_key)


def _decode_dpid(dpid_bytes: bytes) -> str:
    """Decode Windows 7 and earlier DigitalProductId.

    Windows 7 uses standard base-24 encoding starting at offset 52.

    Args:
        dpid_bytes: Binary DigitalProductId data

    Returns:
        Formatted 25-character product key
    """
    if len(dpid_bytes) < 67:  # Minimum: 52 offset + 15 bytes
        raise ValueError(
            f"Windows DigitalProductId data too short ({len(dpid_bytes)} bytes, need >= 67). "
            f"The registry value may be corrupted."
        )

    # Key data starts at offset 52
    key_offset = 52
    key_length = 15

    if len(dpid_bytes) < key_offset + key_length:
        raise ValueError(
            f"Windows DigitalProductId data truncated at key region "
            f"({len(dpid_bytes)} bytes, need >= {key_offset + key_length}). "
            f"The registry value may be corrupted."
        )

    # Extract key bytes
    key_bytes = bytearray(dpid_bytes[key_offset : key_offset + key_length])

    # Character set for base-24 encoding (Windows 7 variant)
    chars = "BCDFGHJKMPQRTVWXY2346789"

    decoded_chars = []

    # Decode 25 characters
    for _i in range(25):
        char_index = 0

        # Process bytes in reverse
        for j in range(14, -1, -1):
            char_index = (char_index << 8) | key_bytes[j]
            key_bytes[j] = char_index // 24
            char_index %= 24

        decoded_chars.append(chars[char_index])

    # Reverse to get correct order
    decoded_chars.reverse()

    product_key = "".join(decoded_chars)

    # Format as XXXXX-XXXXX-XXXXX-XXXXX-XXXXX
    return _format_product_key(product_key)


def _format_product_key(key: str) -> str:
    """Format product key with dashes.

    Args:
        key: 25-character product key

    Returns:
        Formatted key (XXXXX-XXXXX-XXXXX-XXXXX-XXXXX)
    """
    if len(key) != 25:
        # Pad or truncate to 25 characters
        key = key.ljust(25, "X")[:25]

    return f"{key[0:5]}-{key[5:10]}-{key[10:15]}-{key[15:20]}-{key[20:25]}"


def detect_license_type(license_data: dict) -> LicenseType:  # pylint: disable=too-many-return-statements  # one branch per detectable license-type signal
    """Detect Windows license type from registry data.

    Args:
        license_data: Dictionary of registry values

    Returns:
        Detected LicenseType
    """
    # Check for KMS activation
    if license_data.get("KeyManagementServiceName"):
        return LicenseType.KMS

    # Check channel indicator (Windows 10+)
    channel = license_data.get("Channel", "").lower()
    if "retail" in channel:
        return LicenseType.RETAIL
    if "oem" in channel:
        return LicenseType.OEM
    if "volume" in channel:
        return LicenseType.VOLUME

    # Check for Volume Licensing indicators
    if license_data.get("VLActivationInterval") or license_data.get("VLRenewalInterval"):
        # Could be MAK or KMS
        if license_data.get("KeyManagementServiceName"):
            return LicenseType.KMS
        return LicenseType.MAK

    # Check Product ID format for OEM indicator
    product_id = license_data.get("ProductId", "")
    if product_id:
        # OEM product IDs typically have different patterns
        # Format: XXXXX-OEM-XXXXXXX-XXXXX or similar
        if "OEM" in product_id.upper():
            return LicenseType.OEM

    # Default to unknown
    return LicenseType.UNKNOWN


def _determine_activation_status(license_data: dict) -> str:
    """Determine activation status from registry data.

    Note: Full activation status requires online SPP service access.
    This provides a best-effort offline approximation.

    Args:
        license_data: Dictionary of registry values

    Returns:
        Activation status string
    """
    # KMS licenses are typically activated if server is configured
    if license_data.get("KeyManagementServiceName"):
        return "Licensed (KMS)"

    # Check for volume licensing intervals (indicates activation)
    if license_data.get("VLActivationInterval"):
        return "Licensed (Volume)"

    # Without online SPP access, we can't definitively determine status
    return "Unknown (Offline)"
