# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
# https://zyvor.dev · info@zyvor.dev

# h2kvm/daemon/__init__.py
"""Daemon mode components for h2kvm."""

from .control import DEFAULT_CONTROL_SOCKET, DaemonControl, DaemonControlClient
from .daemon_watcher import DaemonWatcher
from .deduplicator import FileDeduplicator
from .manifest_workflow_daemon import ManifestWorkflowDaemon
from .notifier import DaemonNotifier
from .stats import DaemonStatistics
from .workflow_daemon import WorkflowDaemon

__all__ = [
    "DEFAULT_CONTROL_SOCKET",
    "DaemonControl",
    "DaemonControlClient",
    "DaemonNotifier",
    "DaemonStatistics",
    "DaemonWatcher",
    "FileDeduplicator",
    "ManifestWorkflowDaemon",
    "WorkflowDaemon",
]
