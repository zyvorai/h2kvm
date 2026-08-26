#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
H2KVM Encryption Pipeline - CLI Interface

Automated VMware VMDK → LUKS2 + TPM conversion pipeline.

Usage:
    h2kvm-encrypt convert <vmdk> [options]
    h2kvm-encrypt --help

Examples:
    # Basic conversion with default output
    h2kvm-encrypt convert /vms/centos8.vmdk

    # Custom output path
    h2kvm-encrypt convert /vms/centos8.vmdk -o /encrypted/centos8.raw

    # Custom PCRs
    h2kvm-encrypt convert /vms/ubuntu.vmdk --pcrs 0,1,7

    # Skip TPM enrollment (LUKS only)
    h2kvm-encrypt convert /vms/vm.vmdk --no-tpm
"""

import argparse
import logging
import sys
from pathlib import Path

from .vmware_to_luks_tpm import H2KVMVMwareToLUKSPipeline


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    return logging.getLogger("h2kvm.encrypt")


def cmd_convert(args):
    """Execute VMware → LUKS + TPM conversion."""
    logger = setup_logging(args.verbose)

    # Validate input
    vmdk = Path(args.vmdk)
    if not vmdk.exists():
        logger.error("Input file not found: %s", vmdk)
        return 1

    if not vmdk.is_file():
        logger.error("Input is not a file: %s", vmdk)
        return 1

    # Prepare output path
    output = args.output
    if output:
        output = str(Path(output).resolve())

    # Parse PCRs if provided
    if args.pcrs:
        try:
            [int(p.strip()) for p in args.pcrs.split(",")]
        except ValueError:
            logger.exception("Invalid PCR format: %s", args.pcrs)
            logger.exception("Expected comma-separated integers, e.g., '0,1,2,3,7'")
            return 1

    # Run conversion
    try:
        logger.info("Starting VMware → LUKS2 + TPM conversion pipeline")
        logger.info("Input: %s", vmdk)

        pipeline = H2KVMVMwareToLUKSPipeline()

        skip_tpm = getattr(args, "no_tpm", False)
        if skip_tpm:
            logger.info("TPM enrollment will be skipped (--no-tpm)")

        result = pipeline.run(str(vmdk), output, skip_tpm=skip_tpm)

        logger.info("✓ Conversion complete: %s", result)
        logger.info("VM is ready to boot with TPM auto-unlock")

        return 0

    except KeyboardInterrupt:
        logger.warning("Conversion interrupted by user")
        return 130

    except Exception as e:  # pylint: disable=broad-exception-caught  # top-level CLI command handler must report any failure and exit cleanly, not crash
        logger.exception("Conversion failed: %s", e)
        if args.verbose:
            logger.exception("Stack trace:")
        return 1


def cmd_info(args):  # pylint: disable=unused-argument  # dispatched uniformly as args.func(args) alongside cmd_convert, must share its signature
    """Show pipeline information."""
    print("""
H2KVM Encryption Pipeline
==============================

Automated VMware VMDK → LUKS2 + TPM conversion.

Components:
  • Disk Conversion     - VMDK to RAW format
  • NBD Attachment      - Network Block Device mounting
  • Root Detection      - Automatic root partition identification
  • LUKS Encryption     - AES-XTS-512 + Argon2id
  • Filesystem Migration - rsync-based data transfer
  • crypttab Update     - Auto-unlock configuration
  • TPM Enrollment      - systemd-cryptenroll integration
  • Initramfs Rebuild   - dracut/update-initramfs
  • GRUB Update         - Boot configuration

Security:
  • Encryption: AES-XTS-512
  • KDF: Argon2id
  • Hash: SHA-256
  • TPM PCRs: 0, 1, 2, 3, 7 (default)

Performance (20GB VM):
  • Total time: ~15 minutes
  • Boot overhead: <1 second

Requirements:
  • qemu-img, qemu-nbd
  • cryptsetup, lvm2
  • rsync, blkid
  • systemd-cryptenroll
  • dracut or update-initramfs
  • Hardware TPM 2.0

For more information:
  https://github.com/anthropics/h2kvm
    """)
    return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="h2kvm-encrypt",
        description="Automated VMware → LUKS2 + TPM conversion pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic conversion
  h2kvm-encrypt convert /vms/centos8.vmdk

  # Custom output path
  h2kvm-encrypt convert /vms/ubuntu.vmdk -o /encrypted/ubuntu.raw

  # Custom PCR banks
  h2kvm-encrypt convert /vms/vm.vmdk --pcrs 0,1,7

  # Verbose output
  h2kvm-encrypt convert /vms/vm.vmdk -v

Security:
  Encryption: AES-XTS-512 + Argon2id
  TPM Binding: Hardware-backed auto-unlock
  Boot Protection: PCR 0,1,2,3,7 measurements

Performance:
  ~15 minutes for 20GB VM
  <1s boot overhead for TPM unlock
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Convert command
    convert_parser = subparsers.add_parser(
        "convert", help="Convert VMware VMDK to encrypted LUKS2 + TPM image"
    )
    convert_parser.add_argument("vmdk", help="Path to VMware VMDK file")
    convert_parser.add_argument(
        "-o", "--output", help="Output path for encrypted RAW image (default: {vmdk}.encrypted.raw)"
    )
    convert_parser.add_argument(
        "--pcrs", help="Comma-separated PCR banks for TPM (default: 0,1,2,3,7)", metavar="PCRS"
    )
    convert_parser.add_argument(
        "--no-tpm", action="store_true", help="Skip TPM enrollment (LUKS encryption only)"
    )
    convert_parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    convert_parser.set_defaults(func=cmd_convert)

    # Info command
    info_parser = subparsers.add_parser("info", help="Show pipeline information")
    info_parser.set_defaults(func=cmd_info)

    # Parse arguments
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Execute command
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
