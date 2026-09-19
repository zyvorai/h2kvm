# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: LicenseRef-Zyvor-Production-1.0
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/__init__.py
"""Core utilities and abstractions for h2kvm."""

from .guest_identity import GuestDetector, GuestIdentity, GuestType, emit_guest_identity_log

__all__ = ["GuestDetector", "GuestIdentity", "GuestType", "emit_guest_identity_log"]
