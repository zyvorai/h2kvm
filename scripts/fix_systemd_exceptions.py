#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Script to replace RuntimeError with SystemdError in systemd wrapper files.
Adds helpful error messages with installation instructions.
"""

import re
from pathlib import Path

# systemd binary to package mapping
PACKAGE_HINTS = {
    "systemd-vmspawn": "systemd-container (Debian/Ubuntu: apt install systemd-container)",
    "systemd-nspawn": "systemd-container (Debian/Ubuntu: apt install systemd-container)",
    "systemd-dissect": "systemd (usually pre-installed)",
    "systemd-creds": "systemd (version 250+)",
    "systemd-cryptenroll": "systemd (version 248+)",
    "systemd-run": "systemd (usually pre-installed)",
    "systemd-analyze": "systemd (usually pre-installed)",
    "systemd-mount": "systemd (usually pre-installed)",
    "systemd-tmpfiles": "systemd (usually pre-installed)",
    "systemd-notify": "systemd (usually pre-installed)",
    "systemd-inhibit": "systemd (usually pre-installed)",
    "systemd-cat": "systemd (usually pre-installed)",
    "systemd-path": "systemd (usually pre-installed)",
    "systemd-delta": "systemd (usually pre-installed)",
    "systemd-cgtop": "systemd (usually pre-installed)",
    "systemd-repart": "systemd (version 245+)",
    "systemd-detect-virt": "systemd (usually pre-installed)",
    "systemd-machine-id-setup": "systemd (usually pre-installed)",
    "systemd-id128": "systemd (usually pre-installed)",
}


def extract_binary_name(file_path: Path) -> str:
    """Extract the systemd binary name from the Python file."""
    content = file_path.read_text()

    # Try to find the binary name from common patterns
    # Pattern 1: self.binary = systemd_vmspawn or default value
    match = re.search(r'systemd_[a-z_]+:\s*str\s*=\s*"([^"]+)"', content)
    if match:
        return match.group(1)

    # Pattern 2: from filename (e.g., vmspawn.py -> systemd-vmspawn)
    stem = file_path.stem
    if stem == "__init__":
        return "systemd"
    return f"systemd-{stem.replace('_', '-')}"


def update_file(file_path: Path):
    """Update a single systemd wrapper file."""
    content = file_path.read_text()
    original_content = content

    # Check if file contains RuntimeError
    if "raise RuntimeError" not in content:
        return False

    # Add SystemdError import if not present
    if "from hyper2kvm.core.exceptions import SystemdError" not in content:
        # Find the imports section and add SystemdError
        if "from __future__ import annotations" in content:
            content = content.replace(
                "from __future__ import annotations\n",
                "from __future__ import annotations\n\nfrom hyper2kvm.core.exceptions import SystemdError\n",
                1,
            )
        else:
            # Add at the top after docstring
            lines = content.split("\n")
            insert_idx = 0
            for i, line in enumerate(lines):
                if '"""' in line and i > 0:  # End of docstring
                    # Find the closing """
                    for j in range(i, len(lines)):
                        if '"""' in lines[j] and j > i:
                            insert_idx = j + 1
                            break
                    if insert_idx == 0:
                        insert_idx = i + 1
                    break

            if insert_idx > 0:
                lines.insert(insert_idx, "")
                lines.insert(insert_idx + 1, "from hyper2kvm.core.exceptions import SystemdError")
                content = "\n".join(lines)

    # Extract binary name for helpful error message
    binary_name = extract_binary_name(file_path)
    package_hint = PACKAGE_HINTS.get(binary_name, "systemd")

    # Replace RuntimeError with SystemdError and improve message
    # Pattern: raise RuntimeError(msg) from e
    old_pattern = r"raise RuntimeError\(msg\) from e"
    new_text = (
        f'raise SystemdError(code=127, msg=msg).with_context(solutions=["Install {package_hint}"]) from e'
    )
    content = re.sub(old_pattern, new_text, content)

    # Pattern: raise RuntimeError(f"...") from e
    # This is more complex - we need to capture the message and rewrite it
    pattern = r'raise RuntimeError\((f?"[^"]+"\s*(?:\.\s*format\([^)]*\))?)\)\s*from\s+e'

    def replace_runtime_error(match):
        msg = match.group(1)
        return f'raise SystemdError(code=127, msg={msg}).with_context(solutions=["Install {package_hint}"]) from e'

    content = re.sub(pattern, replace_runtime_error, content)

    # Write back if changed
    if content != original_content:
        file_path.write_text(content)
        print(f"✓ Updated {file_path.name}")
        return True

    return False


def main():
    """Update all systemd wrapper files."""
    systemd_dir = Path(__file__).parent.parent / "hyper2kvm" / "systemd"

    if not systemd_dir.exists():
        print(f"Error: {systemd_dir} not found")
        return 1

    updated_count = 0
    for py_file in sorted(systemd_dir.glob("*.py")):
        if py_file.name == "__init__.py":
            continue

        if update_file(py_file):
            updated_count += 1

    print(f"\n✓ Updated {updated_count} files with SystemdError and helpful messages")
    return 0


if __name__ == "__main__":
    exit(main())
