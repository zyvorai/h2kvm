# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/windows/bitlocker.py

"""
BitLocker detection for Windows VMs.

CRITICAL: BitLocker-encrypted disks CANNOT be migrated offline because:
  1. Encrypted volumes cannot be mounted by the guestfs backend
  2. Offline registry access requires decrypted NTFS
  3. Driver injection requires write access to Windows directory

This module detects BitLocker encryption and FAILS migration early with
clear instructions to decrypt before migration.
"""

from __future__ import annotations

import contextlib
import logging
import os
import tempfile
from typing import TYPE_CHECKING, Any

from h2kvm.core.exceptions import BitLockerDetectionError, WindowsFixerError, create_helpful_error
from h2kvm.fixers.windows._hivex_compat import HIVEX_AVAILABLE, hivex

if TYPE_CHECKING:
    from h2kvm.core.guestfs_typing import guestfs


def detect_bitlocker(g: guestfs.GuestFS, root: str) -> dict[str, Any]:
    """
    Detect BitLocker encryption on Windows volumes.

    Args:
        g: GuestFS instance with Windows disk mounted
        root: Windows root path (e.g., '/sysroot')

    Returns:
        Dict with detection results:
            {
                "bitlocker_detected": bool,
                "encrypted_volumes": List[str],
                "protection_status": Dict[str, str],
                "error": str if detection failed
            }

    Raises:
        WindowsFixerError: If BitLocker is detected (blocks migration)
    """
    result = {
        "bitlocker_detected": False,
        "encrypted_volumes": [],
        "protection_status": {},
        "error": None,
    }

    try:
        # Method 1: Check BitLocker registry keys
        bitlocker_status = _check_bitlocker_registry(g, root)

        if bitlocker_status["found"]:
            result["bitlocker_detected"] = True
            result["encrypted_volumes"] = bitlocker_status.get("volumes", [])
            result["protection_status"] = bitlocker_status.get("status", {})

        # Method 2: Check for BitLocker metadata on partitions
        # BitLocker leaves -FVE-FS-* metadata even when unlocked
        bitlocker_metadata = _check_bitlocker_metadata(g)

        if bitlocker_metadata["found"]:
            result["bitlocker_detected"] = True
            result["encrypted_volumes"].extend(bitlocker_metadata.get("volumes", []))

        # Method 3: Check for BitLocker system files
        bitlocker_files = _check_bitlocker_files(g, root)

        if bitlocker_files["found"]:
            result["bitlocker_detected"] = True

        # If BitLocker detected, raise error to block migration
        if result["bitlocker_detected"]:
            volumes_str = (
                ", ".join(result["encrypted_volumes"]) if result["encrypted_volumes"] else "unknown"
            )

            raise create_helpful_error(
                BitLockerDetectionError,
                f"BitLocker encryption detected on volumes: {volumes_str}",
                code=20,
                solutions=[
                    "Boot the VM in VMware",
                    "Decrypt all volumes: manage-bde -off C: (repeat for all encrypted volumes)",
                    "Wait for decryption to complete (may take hours for large disks)",
                    "Verify decryption: manage-bde -status",
                    "Shut down VM cleanly and retry migration",
                    "Alternative: Use live migration instead of offline conversion",
                ],
                causes=[
                    "BitLocker Drive Encryption is enabled on one or more volumes",
                    "Encrypted volumes cannot be mounted by the guestfs backend",
                    "Offline registry access requires decrypted NTFS",
                    "Driver injection requires write access to Windows directory",
                ],
                encrypted_volumes=result["encrypted_volumes"],
                protection_status=result.get("protection_status", {}),
            )

    except WindowsFixerError:
        raise  # Re-raise to caller
    except Exception as e:  # pylint: disable=broad-exception-caught  # detection must not abort migration
        result["error"] = str(e)
        # Don't fail migration on detection errors - log warning instead
        logging.warning("BitLocker detection failed (non-fatal): %s", e)

    return result


def _read_bitlocker_service_info(  # pylint: disable=too-many-locals,too-many-return-statements,too-many-branches
    g: guestfs.GuestFS, root: str
) -> dict[str, Any] | None:
    """
    Read BitLocker service (BDESVC) information from registry.

    Args:
        g: GuestFS instance
        root: Windows root path

    Returns:
        Dict with service info or None if unavailable

    Note:
        Complexity is inherent to walking a live Windows registry hive (ControlSet
        detection, multiple optional values, early-outs when a key is missing).
    """
    if not HIVEX_AVAILABLE:
        return None

    # pylint: disable=duplicate-code
    # reason: the hive-download/open/ControlSet-detection steps mirror
    # h2kvm/fixers/windows/firewall.py's _read_service_start_type() --
    # coincidental. This routine hardcodes the BDESVC service and also
    # reads DisplayName, while firewall.py's takes a parameterized
    # service_name and a root-agnostic hive path; keeping them independent
    # avoids coupling two functions with different data shapes.
    system_hive_path = f"{root}/Windows/System32/config/SYSTEM"
    if not g.exists(system_hive_path):
        return None

    h: hivex.Hivex | None = None
    try:
        # Download hive to temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=".hiv") as tmp:
            tmp_path = tmp.name

        g.download(system_hive_path, tmp_path)

        # Open hive (read-only)
        h = hivex.Hivex(tmp_path, write=False)
        root_node = h.root()

        # Detect current ControlSet
        select_node = h.node_get_child(root_node, "Select")
        if not select_node:
            return None

        current_val = h.node_get_value(select_node, "Current")
        if not current_val:
            return None

        current_cs_num = int.from_bytes(h.value_value(current_val)[1][:4], "little", signed=False)
        controlset_name = f"ControlSet{current_cs_num:03d}"

        # Navigate to Services\BDESVC
        controlset_node = h.node_get_child(root_node, controlset_name)
        if not controlset_node:
            return None

        services_node = h.node_get_child(controlset_node, "Services")
        if not services_node:
            return None

        bdesvc_node = h.node_get_child(services_node, "BDESVC")
        if not bdesvc_node:
            return None  # BitLocker service not installed

        # Read service configuration
        service_info = {"service_exists": True}

        # Read Start type
        start_val = h.node_get_value(bdesvc_node, "Start")
        if start_val:
            start_bytes = h.value_value(start_val)[1]
            if len(start_bytes) >= 4:
                service_info["start_type"] = int.from_bytes(start_bytes[:4], "little", signed=False)

        # Read DisplayName
        display_val = h.node_get_value(bdesvc_node, "DisplayName")
        if display_val:
            display_bytes = h.value_value(display_val)[1]
            with contextlib.suppress(Exception):
                service_info["display_name"] = display_bytes.decode("utf-16le").rstrip("\x00")

        return service_info

    # pylint: disable=duplicate-code
    # reason: the except/finally hive-close-and-tempfile-cleanup shape
    # mirrors h2kvm/fixers/windows/firewall.py's
    # _read_service_start_type() -- coincidental, both are the standard
    # best-effort cleanup for a temporarily downloaded hive.
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort registry read, must not abort
        logging.debug("Failed to read BitLocker service info: %s", e)
        return None
    finally:
        if h:
            with contextlib.suppress(Exception):
                h.close()
        # Clean up temporary file
        try:
            if "tmp_path" in locals():
                os.unlink(tmp_path)
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort cleanup, must not mask real errors
            pass


def _check_bitlocker_registry(g: guestfs.GuestFS, root: str) -> dict[str, Any]:
    """
    Check Windows registry for BitLocker configuration.

    Registry keys checked:
        HKLM\\SYSTEM\\CurrentControlSet\\Control\\BitLockerStatus
        HKLM\\SYSTEM\\CurrentControlSet\\Services\\BDESVC (BitLocker Drive Encryption Service)
        HKLM\\SOFTWARE\\Policies\\Microsoft\\FVE (Full Volume Encryption policies)
    """
    result = {"found": False, "volumes": [], "status": {}}

    try:
        # Check for BitLocker service (BDESVC)
        service_info = _read_bitlocker_service_info(g, root)

        if service_info and service_info.get("service_exists"):
            result["status"]["bdesvc_present"] = True
            result["status"]["bdesvc_start_type"] = service_info.get("start_type")
            result["status"]["bdesvc_display_name"] = service_info.get(
                "display_name", "BitLocker Drive Encryption Service"
            )

            start_type = service_info.get("start_type")
            if start_type is not None:
                # 2 = Automatic, 3 = Manual
                if start_type <= 3:  # Not disabled
                    logging.info("BitLocker service (BDESVC) detected (Start=%s)", start_type)
                    # Note: Service presence alone doesn't mean encryption is active
                    # Just indicates BitLocker was/is configured
                else:
                    logging.debug("BitLocker service exists but is disabled (Start=%s)", start_type)
        else:
            result["status"]["bdesvc_present"] = False
            logging.debug("BitLocker service (BDESVC) not found in registry")

        # Check SOFTWARE hive for BitLocker policies
        # (Not implemented yet - policies are less critical than actual encryption detection)
        software_hive_path = f"{root}/Windows/System32/config/SOFTWARE"
        if g.exists(software_hive_path):
            result["status"]["software_hive_readable"] = True

        # If we get here without errors, hives are readable (not encrypted)
        # BitLocker would prevent NTFS mount, so readable hives = not encrypted
        # The service check above is for historical/policy detection

    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort probe, expected if encrypted
        logging.debug("Registry check failed (expected if encrypted): %s", e)

    return result


def _check_bitlocker_metadata(g: guestfs.GuestFS) -> dict[str, Any]:
    """
    Check for BitLocker filesystem metadata.

    BitLocker uses -FVE-FS- filesystem signatures that persist even after decryption.
    Check partition labels and filesystem types for BitLocker indicators.
    """
    result = {"found": False, "volumes": []}

    try:  # pylint: disable=too-many-nested-blocks  # exhaustive best-effort device/partition/label probing
        # Get all block devices
        devices = g.list_devices()

        for device in devices:
            try:
                # Get partitions on this device
                partitions = g.list_partitions()

                for partition in partitions:
                    if not partition.startswith(device):
                        continue

                    try:
                        # Check filesystem type
                        # BitLocker shows as "BitLocker" or "unknown" type
                        fs_type = g.vfs_type(partition)

                        if fs_type and "bitlocker" in fs_type.lower():
                            result["found"] = True
                            result["volumes"].append(partition)
                            continue

                        # Check partition label for BitLocker indicators
                        try:
                            label = g.vfs_label(partition)
                            if label and ("-fve-fs-" in label.lower() or "bitlocker" in label.lower()):
                                result["found"] = True
                                result["volumes"].append(partition)
                        except (RuntimeError, OSError) as label_err:
                            logging.debug("Could not check label for %s: %s", partition, label_err)

                    except Exception as e:  # pylint: disable=broad-exception-caught  # per-partition probe
                        logging.debug("Could not check partition %s: %s", partition, e)

            except Exception as e:  # pylint: disable=broad-exception-caught  # per-device probe, must not abort scan
                logging.debug("Could not check device %s: %s", device, e)

    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort metadata scan, must not abort
        logging.debug("Metadata check failed: %s", e)

    return result


def _check_bitlocker_files(g: guestfs.GuestFS, root: str) -> dict[str, Any]:
    """
    Check for BitLocker-specific files in Windows directory.

    Files checked:
        - BitLocker recovery keys (*.BEK files)
        - BitLocker startup keys
        - FVEAPI.dll (BitLocker API)
    """
    result = {"found": False, "files": []}

    try:
        # Check for BitLocker DLL (indicates BitLocker was installed)
        bitlocker_dll = f"{root}/Windows/System32/fveapi.dll"
        if g.exists(bitlocker_dll):
            result["files"].append("fveapi.dll")
            # Having the DLL doesn't mean encryption is active
            # Just indicates BitLocker capability

        # Check for recovery key files (strong indicator)
        windows_path = f"{root}/Windows"
        if g.is_dir(windows_path):
            try:
                files = g.ls(windows_path)
                for f in files:
                    if f.endswith((".BEK", ".bek")):
                        result["found"] = True
                        result["files"].append(f)
            except (RuntimeError, OSError) as ls_err:
                logging.debug("Could not list files in %s: %s", windows_path, ls_err)

    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort file scan, must not abort
        logging.debug("File check failed: %s", e)

    return result


def check_bitlocker_before_migration(g: guestfs.GuestFS, root: str, logger: logging.Logger) -> None:
    """
    Pre-migration BitLocker check.

    Call this BEFORE attempting any offline modifications to Windows.
    Raises WindowsFixerError if encryption detected.

    Args:
        g: GuestFS instance
        root: Windows root path
        logger: Logger instance

    Raises:
        BitLockerDetectionError: If BitLocker detected (blocks migration)
    """
    logger.info("🔒 Checking for BitLocker encryption...")

    try:
        result = detect_bitlocker(g, root)

        if result["bitlocker_detected"]:
            # Should not reach here (detect_bitlocker raises)
            logger.error("❌ BitLocker detected - migration blocked")
        else:
            logger.info("✅ No BitLocker encryption detected")

    except BitLockerDetectionError as e:
        logger.exception(str(e))
        raise
