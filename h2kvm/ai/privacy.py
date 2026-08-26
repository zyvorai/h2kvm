# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/ai/privacy.py
"""
Data anonymizer for the AI module.

Hashes sensitive strings (hostnames, IPs, paths) with a per-install salt
so they cannot be reversed but remain consistent across runs.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

_DEFAULT_SALT_DIR = "~/.cache/h2kvm/ai"
_SALT_FILENAME = ".salt"


class DataAnonymizer:
    """SHA-256 anonymizer with a per-install salt file."""

    def __init__(self, salt_dir: str | None = None) -> None:
        self._salt_dir = Path(salt_dir or _DEFAULT_SALT_DIR).expanduser()
        self._salt: bytes | None = None

    # -- salt management ---------------------------------------------------

    @property
    def salt(self) -> bytes:
        """Return the per-install salt, loading or creating it on first access."""
        if self._salt is None:
            self._salt = self._load_or_create_salt()
        return self._salt

    def _load_or_create_salt(self) -> bytes:
        salt_file = self._salt_dir / _SALT_FILENAME
        if salt_file.exists():
            return salt_file.read_bytes()
        self._salt_dir.mkdir(parents=True, exist_ok=True)
        new_salt = os.urandom(32)
        salt_file.write_bytes(new_salt)
        # Restrict permissions
        try:
            salt_file.chmod(0o600)
        except OSError:
            pass
        return new_salt

    # -- hashing -----------------------------------------------------------

    def hash_value(self, value: str) -> str:
        """One-way hash a string using SHA-256 + salt. Returns a 16-char hex digest."""
        h = hashlib.sha256(self.salt + value.encode("utf-8", errors="replace"))
        return h.hexdigest()[:16]

    # -- field-level anonymization -----------------------------------------

    def anonymize_hostname(self, hostname: str) -> str:
        """Replace a hostname with a stable, salted hash-based placeholder."""
        if not hostname:
            return ""
        return f"host-{self.hash_value(hostname)}"

    def anonymize_ip(self, ip: str) -> str:
        """Replace an IP address with a stable, salted hash-based placeholder."""
        if not ip:
            return ""
        return f"ip-{self.hash_value(ip)}"

    def anonymize_path(self, path: str) -> str:
        """Replace a filesystem path with a stable, salted hash-based placeholder."""
        if not path:
            return ""
        return f"path-{self.hash_value(path)}"

    def anonymize_text(self, text: str) -> str:
        """Scrub hostnames, IPs, and file paths from free-form text."""
        if not text:
            return text
        # Replace IPv4 addresses
        text = re.sub(
            r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
            lambda m: self.anonymize_ip(m.group()),
            text,
        )
        # Replace absolute paths
        return re.sub(
            r"(/[a-zA-Z0-9_./-]{3,})",
            lambda m: self.anonymize_path(m.group()),
            text,
        )
