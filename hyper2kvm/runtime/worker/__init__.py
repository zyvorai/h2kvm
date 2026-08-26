# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/worker/__init__.py
"""
Worker Job Protocol for hyper2kvm.

Implements production-grade job orchestration for disk operations that require
privileged access (NBD, LVM, filesystem surgery).

Architecture:
    - Control Plane (Safe): Job submission, validation, monitoring
    - Data Plane (Privileged): Worker nodes executing disk operations

Components:
    - schemas: Pydantic models for job specs, events, results
    - engine: Worker execution engine
    - scheduler: Job queue and worker matching
    - events: Progress event streaming and storage
    - capabilities: Runtime environment detection
    - state_machine: Job lifecycle management
    - cli: Command-line interface
"""

from .capabilities import CapabilityDetector, ExecutionMode, get_detector
from .engine import WorkerEngine
from .events import EventEmitter, EventStore, ProgressTracker, get_event_store
from .scheduler import JobQueue, JobScheduler, WorkerRegistry, get_scheduler
from .schemas import (
    JobResult,
    JobSpec,
    JobState,
    OperationType,
    ProgressEvent,
    WorkerCapabilities,
)
from .state_machine import JobRegistry, JobStateMachine

__version__ = "1.0.0"

__all__ = [
    # Capabilities
    "CapabilityDetector",
    "EventEmitter",
    # Events
    "EventStore",
    "ExecutionMode",
    "JobQueue",
    "JobRegistry",
    "JobResult",
    # Scheduler
    "JobScheduler",
    # Schemas
    "JobSpec",
    "JobState",
    # State Management
    "JobStateMachine",
    "OperationType",
    "ProgressEvent",
    "ProgressTracker",
    "WorkerCapabilities",
    # Engine
    "WorkerEngine",
    "WorkerRegistry",
    # REST API (requires fastapi installation)
    "api",
    "get_detector",
    "get_event_store",
    "get_scheduler",
]
