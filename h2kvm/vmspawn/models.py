# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Data models for vmspawn SDK."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class VMConfig:  # pylint: disable=too-many-instance-attributes
    # reason: models the full set of independent VM launch options (resources,
    # networking, vsock, TPM) as a flat config record.
    """VM configuration."""

    name: str
    image: Path
    memory_mb: int = 2048
    cpus: int = 2
    timeout: int = 120
    vsock: bool = True
    vsock_cid: int | None = None
    network_user: bool = True
    tpm: bool = False

    def __post_init__(self) -> None:
        if self.memory_mb <= 0:
            raise ValueError(
                f"VM memory must be a positive number, got {self.memory_mb} MB. "
                f"Specify memory in megabytes (e.g., 1024 for 1 GB)."
            )
        if self.cpus <= 0:
            raise ValueError(
                f"VM CPU count must be a positive number, got {self.cpus}. Specify at least 1 CPU."
            )

    @property
    def memory(self) -> int:
        """Alias for memory_mb."""
        return self.memory_mb

    @memory.setter
    def memory(self, value: int) -> None:
        self.memory_mb = value


@dataclass
class VMStatus:
    """VM status information."""

    name: str
    running: bool
    pid: int | None = None
    state: str | None = None


@dataclass
class ValidationChecks:
    """Validation check results."""

    systemd: bool = False
    network: bool = False
    boot_complete: bool = False
    kubelet: bool = False
    container_runtime: bool = False
    cni: bool = False

    def __getattr__(self, name: str) -> bool:
        """Allow arbitrary check names."""
        return False


@dataclass
class ValidationResult:
    """Result of a VM validation run."""

    success: bool
    checks: Any = None
    error: str | None = None
    duration: float = 0.0

    def __post_init__(self) -> None:
        if self.checks is None:
            self.checks = ValidationChecks()
        elif isinstance(self.checks, dict):
            vc = ValidationChecks()
            for k, v in self.checks.items():
                setattr(vc, k, v)
            self.checks = vc

    def to_json(self) -> dict:
        """Convert to JSON-serializable dict."""
        checks_dict = {}
        if isinstance(self.checks, ValidationChecks):
            checks_dict = {k: v for k, v in self.checks.__dict__.items() if not k.startswith("_")}
        elif isinstance(self.checks, dict):
            checks_dict = self.checks
        return {
            "success": self.success,
            "checks": checks_dict,
            "error": self.error,
            "duration": self.duration,
        }
