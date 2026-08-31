#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Validate disk images via qemu-img and GuestKit doctor."""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from h2kvm.core import guestkit_client


def setup_logging(verbose: bool = False) -> logging.Logger:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")
    return logging.getLogger(__name__)


def format_size(bytes_val: int) -> str:
    for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} PiB"


def basic_validation(image_path: Path, logger: logging.Logger) -> bool:
    logger.info("Basic validation: %s", image_path.name)
    try:
        result = subprocess.run(
            ["qemu-img", "info", "--output=json", str(image_path)],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        metadata = json.loads(result.stdout)
        logger.info("Format: %s", metadata.get("format"))
        logger.info("Virtual size: %s", format_size(int(metadata.get("virtual-size", 0))))
        logger.info("Actual size: %s", format_size(int(metadata.get("actual-size", 0))))
        return True
    except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError) as exc:
        logger.error("Validation failed: %s", exc)
        return False


def guestkit_validation(image_path: Path, logger: logging.Logger, *, deep: bool) -> bool:
    logger.info("GuestKit %s validation: %s", "doctor" if deep else "boot inspect", image_path.name)
    try:
        if deep:
            report = guestkit_client.doctor(image_path, explain=True)
        else:
            report = guestkit_client.boot_inspect(image_path)
        score = report.get("bootability", {}).get("score") if deep else None
        if score is not None:
            logger.info("Boot score: %s", score)
        logger.info("Message: %s", report.get("message") or report.get("bootability", {}).get("summary", ""))
        return True
    except ImportError as exc:
        logger.error("%s", exc)
        return False
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("GuestKit validation failed: %s", exc)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate disk images")
    parser.add_argument("image", type=Path)
    parser.add_argument("--deep", action="store_true", help="Run GuestKit doctor (requires guestkit + root)")
    parser.add_argument("--full", action="store_true", help="Alias for --deep")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logger = setup_logging(args.verbose)
    if not args.image.exists():
        logger.error("Image not found: %s", args.image)
        sys.exit(1)

    ok = basic_validation(args.image, logger)
    if ok and (args.deep or args.full):
        ok = guestkit_validation(args.image, logger, deep=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
