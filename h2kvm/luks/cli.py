# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
H2KVM LUKS CLI Tool

Command-line interface for LUKS auto-unlock operations.

Usage:
    h2kvm-luks unlock               # Unlock all LUKS devices
    h2kvm-luks seal <device> <key>  # Seal key to TPM2
    h2kvm-luks list                 # List LUKS devices
    h2kvm-luks status               # Show unlock status
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from .tpm import TPMSealer
from .unlocker import (
    Cryptsetup,
    LUKSDevice,
    LUKSUnlocker,
)


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def cmd_unlock(args):
    """Unlock LUKS devices."""
    config = load_config(args.config)

    unlocker = LUKSUnlocker(
        tpm_handle=config.get("tpm_handle"),
        vault_config=config.get("vault"),
        keyfile_path=config.get("keyfile"),
    )

    results = unlocker.unlock_all()

    # Exit with error if any failed
    if not all(results.values()):
        sys.exit(1)


def cmd_list(args):  # pylint: disable=unused-argument  # dispatch-table callback signature (handlers.get(args.command)(args)) must match its siblings
    """List LUKS devices."""
    devices = LUKSDevice.list()

    if not devices:
        print("No LUKS devices found")
        return

    print(f"Found {len(devices)} LUKS devices:")
    for device in devices:
        uuid = LUKSDevice.get_uuid(device)
        print(f"  {device}")
        if uuid:
            print(f"    UUID: {uuid}")


def cmd_status(args):
    """Show unlock status."""
    devices = LUKSDevice.list()

    if not devices:
        print("No LUKS devices found")
        return

    config = load_config(args.config)
    unlocker = LUKSUnlocker(
        tpm_handle=config.get("tpm_handle"),
        vault_config=config.get("vault"),
        keyfile_path=config.get("keyfile"),
    )

    print("LUKS Device Status:")
    for device in devices:
        mapper = unlocker.mapper_name(device)
        is_open = Cryptsetup.is_open(mapper)
        status = "✓ UNLOCKED" if is_open else "✗ LOCKED"
        print(f"  {device}: {status}")
        if is_open:
            print(f"    Mapper: /dev/mapper/{mapper}")


def cmd_seal(args):
    """Seal key to TPM2."""
    sealer = TPMSealer()

    print(f"Sealing key from {args.keyfile} to TPM2...")

    # Read key
    with open(args.keyfile, "rb") as f:
        key = f.read()

    # Seal to TPM
    handle = sealer.seal_key(
        key,
        pcrs=args.pcr,
        handle=args.handle,
    )

    print(f"✓ Key sealed to TPM2 handle: {handle}")
    print("\nAdd to config:")
    print(f"  tpm_handle: {handle}")


def load_config(config_path: Optional[str] = None) -> dict:
    """Load configuration from file or environment."""
    config = {}

    # Try config file
    if config_path and Path(config_path).exists():
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
    elif Path("/etc/h2kvm/luks.json").exists():
        with open("/etc/h2kvm/luks.json", encoding="utf-8") as f:
            config = json.load(f)

    # Override with environment variables
    if os.getenv("H2KVM_TPM_HANDLE"):
        config["tpm_handle"] = os.getenv("H2KVM_TPM_HANDLE")

    if os.getenv("H2KVM_VAULT_ADDR"):
        config["vault"] = {
            "addr": os.getenv("H2KVM_VAULT_ADDR"),
            "token": os.getenv("H2KVM_VAULT_TOKEN"),
            "path": os.getenv("H2KVM_VAULT_PATH", "secret/h2kvm/luks"),
        }

    if os.getenv("H2KVM_LUKS_KEYFILE"):
        config["keyfile"] = os.getenv("H2KVM_LUKS_KEYFILE")

    return config


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="H2KVM LUKS Auto-Unlock Tool")

    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")

    parser.add_argument("-c", "--config", help="Config file path (default: /etc/h2kvm/luks.json)")

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # unlock command
    subparsers.add_parser("unlock", help="Unlock LUKS devices")

    # list command
    subparsers.add_parser("list", help="List LUKS devices")

    # status command
    subparsers.add_parser("status", help="Show unlock status")

    # seal command
    seal_parser = subparsers.add_parser("seal", help="Seal key to TPM2")
    seal_parser.add_argument("keyfile", help="Keyfile to seal")
    seal_parser.add_argument(
        "--handle", default="0x81000010", help="TPM2 persistent handle (default: 0x81000010)"
    )
    seal_parser.add_argument(
        "--pcr",
        nargs="+",
        type=int,
        default=[0, 1, 2, 3, 7],
        help="PCRs to seal against (default: 0 1 2 3 7)",
    )

    args = parser.parse_args()

    setup_logging(args.verbose)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Dispatch to command handler
    handlers = {
        "unlock": cmd_unlock,
        "list": cmd_list,
        "status": cmd_status,
        "seal": cmd_seal,
    }

    handler = handlers.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
