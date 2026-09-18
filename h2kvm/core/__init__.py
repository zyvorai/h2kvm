# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/__init__.py
"""Core utilities and abstractions for h2kvm."""

from .guest_identity import GuestDetector, GuestIdentity, GuestType, emit_guest_identity_log

__all__ = ["GuestDetector", "GuestIdentity", "GuestType", "emit_guest_identity_log"]
