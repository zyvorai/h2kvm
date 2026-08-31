#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Offline disk inspection via GuestKit (replaces vmcraft_inspect.py)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from h2kvm.core import guestkit_client


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect an offline disk image with GuestKit")
    parser.add_argument("image", type=Path, help="Path to disk image")
    parser.add_argument("--target", default="kvm", help="Migration target (default: kvm)")
    parser.add_argument("--json", action="store_true", help="Emit doctor JSON only")
    parser.add_argument("--boot", action="store_true", help="Run boot inspect summary")
    args = parser.parse_args()

    if not args.image.exists():
        print(f"Image not found: {args.image}", file=sys.stderr)
        return 1

    try:
        if args.boot:
            result = guestkit_client.boot_inspect(args.image, target=args.target)
        else:
            result = guestkit_client.doctor(args.image, target=args.target, explain=True)
    except ImportError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return 0

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
