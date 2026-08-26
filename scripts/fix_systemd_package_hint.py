#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Fix the undefined package_hint variable in systemd wrapper files.
"""

from pathlib import Path

# Map of file names to their package hints
FILE_TO_HINT = {
    "vmspawn.py": "systemd-container (Debian/Ubuntu: apt install systemd-container)",
    "nspawn.py": "systemd-container (Debian/Ubuntu: apt install systemd-container)",
    "dissect.py": "systemd (usually pre-installed)",
    "creds.py": "systemd version 250+ (Debian/Ubuntu: apt install systemd)",
    "cryptenroll.py": "systemd version 248+ (Debian/Ubuntu: apt install systemd)",
    "run.py": "systemd (usually pre-installed)",
    "analyze.py": "systemd (usually pre-installed)",
    "mount.py": "systemd (usually pre-installed)",
    "tmpfiles.py": "systemd (usually pre-installed)",
    "notify.py": "systemd (usually pre-installed)",
    "inhibit.py": "systemd (usually pre-installed)",
    "cat.py": "systemd (usually pre-installed)",
    "path.py": "systemd (usually pre-installed)",
    "delta.py": "systemd (usually pre-installed)",
    "cgtop.py": "systemd (usually pre-installed)",
    "repart.py": "systemd version 245+ (Debian/Ubuntu: apt install systemd)",
    "detect_virt.py": "systemd (usually pre-installed)",
    "machine_id.py": "systemd (usually pre-installed)",
    "id128.py": "systemd (usually pre-installed)",
}


def main():
    systemd_dir = Path(__file__).parent.parent / "h2kvm" / "systemd"

    updated_count = 0
    for file_name, hint in FILE_TO_HINT.items():
        file_path = systemd_dir / file_name
        if not file_path.exists():
            continue

        content = file_path.read_text()
        original = content

        # Replace the undefined f-string with a proper string
        content = content.replace('solutions=[f"Install {package_hint}"]', f'solutions=["Install {hint}"]')

        if content != original:
            file_path.write_text(content)
            print(f"✓ Fixed {file_name}")
            updated_count += 1

    print(f"\n✓ Fixed {updated_count} files")


if __name__ == "__main__":
    main()
