# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for h2kvm.ai.privacy module.

DataAnonymizer: salt creation, hashing, and field-level anonymization.
"""

from __future__ import annotations

import os
import stat

from h2kvm.ai.privacy import DataAnonymizer


# ---------------------------------------------------------------------------
# Salt creation and persistence
# ---------------------------------------------------------------------------


def test_salt_created_on_first_access(tmp_path):
    anon = DataAnonymizer(salt_dir=str(tmp_path))
    salt = anon.salt
    assert isinstance(salt, bytes)
    assert len(salt) == 32


def test_salt_persisted_to_file(tmp_path):
    anon = DataAnonymizer(salt_dir=str(tmp_path))
    _ = anon.salt
    salt_file = tmp_path / ".salt"
    assert salt_file.exists()
    assert salt_file.read_bytes() == anon.salt


def test_salt_reloaded_from_existing_file(tmp_path):
    anon1 = DataAnonymizer(salt_dir=str(tmp_path))
    salt1 = anon1.salt

    anon2 = DataAnonymizer(salt_dir=str(tmp_path))
    salt2 = anon2.salt

    assert salt1 == salt2


def test_salt_file_permissions(tmp_path):
    anon = DataAnonymizer(salt_dir=str(tmp_path))
    _ = anon.salt
    salt_file = tmp_path / ".salt"
    mode = stat.S_IMODE(os.stat(salt_file).st_mode)
    assert mode == 0o600


# ---------------------------------------------------------------------------
# hash_value
# ---------------------------------------------------------------------------


def test_hash_value_returns_16_char_hex(tmp_path):
    anon = DataAnonymizer(salt_dir=str(tmp_path))
    h = anon.hash_value("test-string")
    assert len(h) == 16
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_value_consistent(tmp_path):
    anon = DataAnonymizer(salt_dir=str(tmp_path))
    assert anon.hash_value("hello") == anon.hash_value("hello")


def test_hash_value_different_inputs(tmp_path):
    anon = DataAnonymizer(salt_dir=str(tmp_path))
    assert anon.hash_value("alpha") != anon.hash_value("beta")


# ---------------------------------------------------------------------------
# anonymize_hostname
# ---------------------------------------------------------------------------


def test_anonymize_hostname_non_empty(tmp_path):
    anon = DataAnonymizer(salt_dir=str(tmp_path))
    result = anon.anonymize_hostname("web-server-01")
    assert result.startswith("host-")
    assert len(result) == len("host-") + 16


def test_anonymize_hostname_empty(tmp_path):
    anon = DataAnonymizer(salt_dir=str(tmp_path))
    assert anon.anonymize_hostname("") == ""


# ---------------------------------------------------------------------------
# anonymize_ip
# ---------------------------------------------------------------------------


def test_anonymize_ip_non_empty(tmp_path):
    anon = DataAnonymizer(salt_dir=str(tmp_path))
    result = anon.anonymize_ip("192.168.1.100")
    assert result.startswith("ip-")
    assert len(result) == len("ip-") + 16


def test_anonymize_ip_empty(tmp_path):
    anon = DataAnonymizer(salt_dir=str(tmp_path))
    assert anon.anonymize_ip("") == ""


# ---------------------------------------------------------------------------
# anonymize_path
# ---------------------------------------------------------------------------


def test_anonymize_path_non_empty(tmp_path):
    anon = DataAnonymizer(salt_dir=str(tmp_path))
    result = anon.anonymize_path("/var/log/syslog")
    assert result.startswith("path-")
    assert len(result) == len("path-") + 16


def test_anonymize_path_empty(tmp_path):
    anon = DataAnonymizer(salt_dir=str(tmp_path))
    assert anon.anonymize_path("") == ""


# ---------------------------------------------------------------------------
# anonymize_text
# ---------------------------------------------------------------------------


def test_anonymize_text_replaces_ip(tmp_path):
    anon = DataAnonymizer(salt_dir=str(tmp_path))
    text = "Connection to 10.0.0.1 failed"
    result = anon.anonymize_text(text)
    assert "10.0.0.1" not in result
    assert "ip-" in result


def test_anonymize_text_replaces_path(tmp_path):
    anon = DataAnonymizer(salt_dir=str(tmp_path))
    text = "File /etc/fstab not found"
    result = anon.anonymize_text(text)
    assert "/etc/fstab" not in result
    assert "path-" in result


def test_anonymize_text_empty(tmp_path):
    anon = DataAnonymizer(salt_dir=str(tmp_path))
    assert anon.anonymize_text("") == ""


def test_anonymize_text_no_sensitive_data(tmp_path):
    anon = DataAnonymizer(salt_dir=str(tmp_path))
    text = "Migration completed successfully"
    result = anon.anonymize_text(text)
    assert result == text
