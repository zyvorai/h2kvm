# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/vmcraft/windows_drivers.py
"""
Windows driver injection.

Provides driver injection into Windows DriverStore for:
- VirtIO drivers (network, storage, balloon, etc.)
- Hardware drivers
- Custom drivers

Injection process:
1. Locate DriverStore/FileRepository directory
2. Find INF file in driver package
3. Copy all driver files to DriverStore
4. Optionally update registry for driver installation
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class WindowsDriverInjector:
    """
    Windows driver injector.

    Handles injection of driver packages into Windows DriverStore.
    """

    def __init__(self, logger_instance: logging.Logger, mount_root: Path):
        """
        Initialize driver injector.

        Args:
            logger_instance: Logger instance
            mount_root: Root directory where Windows filesystem is mounted
        """
        self.logger = logger_instance
        self.mount_root = mount_root

    def _find_driver_store(self) -> Path | None:
        """
        Find Windows DriverStore directory (case-insensitive).

        Returns:
            Path to DriverStore/FileRepository or None if not found
        """
        for try_path in [
            "Windows/System32/DriverStore/FileRepository",
            "windows/system32/driverstore/filerepository",
            "Windows/System32/DriverStore",
            "windows/system32/driverstore",
        ]:
            test_path = self.mount_root / try_path
            if test_path.exists():
                # Ensure FileRepository subdirectory exists
                if test_path.name.lower() == "driverstore":
                    file_repo = test_path / "FileRepository"
                    file_repo.mkdir(parents=True, exist_ok=True)
                    return file_repo
                return test_path

        # Fallback: Create DriverStore path
        driver_store = self.mount_root / "Windows/System32/DriverStore/FileRepository"
        driver_store.mkdir(parents=True, exist_ok=True)
        return driver_store

    def _find_inf_file(self, driver_path: Path, inf_file: str | None = None) -> Path | None:
        """
        Find INF file in driver directory.

        Args:
            driver_path: Path to driver directory
            inf_file: Optional specific INF filename

        Returns:
            Path to INF file or None if not found
        """
        if inf_file:
            inf_path = driver_path / inf_file
            if inf_path.exists():
                return inf_path
            return None

        # Auto-detect INF file
        inf_files = list(driver_path.glob("*.inf"))
        if inf_files:
            return inf_files[0]

        return None

    def inject_driver(self, driver_path: str, inf_file: str | None = None) -> dict[str, Any]:
        """
        Inject Windows driver into guest filesystem.

        Args:
            driver_path: Path to driver directory on host
            inf_file: Optional specific INF file to use (default: auto-detect)

        Returns:
            Dict with injection results:
            {
                "ok": bool,
                "driver_path": str,
                "inf_file": str,
                "destination": str,
                "files_copied": int,
                "error": str | None
            }

        Example:
            result = injector.inject_driver("/path/to/virtio-drivers/NetKVM/w10/amd64")
            if result["ok"]:
                print(f"Injected driver to {result['destination']}")
        """
        driver_src = Path(driver_path)
        if not driver_src.exists():
            raise FileNotFoundError(f"Driver path not found: {driver_path}")

        result: dict[str, Any] = {
            "ok": False,
            "driver_path": driver_path,
            "inf_file": inf_file,
            "destination": None,
            "files_copied": 0,
            "error": None,
        }

        try:
            # Find DriverStore path
            driver_store = self._find_driver_store()
            if not driver_store:
                raise RuntimeError(
                    "Windows DriverStore directory not found on the mounted disk. "
                    "Expected at Windows\\System32\\DriverStore. "
                    "The Windows installation may be damaged or a non-standard layout."
                )

            # Find INF file
            inf_path = self._find_inf_file(driver_src, inf_file)
            if not inf_path:
                raise ValueError(
                    f"No .inf driver file found in '{driver_path}'. "
                    f"Ensure the driver package contains a valid Windows INF file."
                )

            result["inf_file"] = inf_path.name

            # Create destination directory (driver package name from INF)
            inf_name = inf_path.stem
            dest_dir = driver_store / inf_name
            dest_dir.mkdir(parents=True, exist_ok=True)

            # Copy all driver files
            copied_files = []
            for src_file in driver_src.iterdir():
                if src_file.is_file():
                    dest_file = dest_dir / src_file.name
                    shutil.copy2(src_file, dest_file)
                    copied_files.append(src_file.name)
                    self.logger.debug(f"Copied driver file: {src_file.name}")

            result["ok"] = True
            result["destination"] = str(dest_dir.relative_to(self.mount_root))
            result["files_copied"] = len(copied_files)
            self.logger.info(f"Injected Windows driver: {inf_name} ({len(copied_files)} files)")

        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort driver injection, must report failure not crash
            result["error"] = str(e)
            self.logger.exception("Failed to inject driver: %s", e)

        return result

    def inject_driver_package(self, driver_package_path: str) -> dict[str, Any]:
        """
        Inject entire driver package with multiple architectures/versions.

        Automatically detects architecture subdirectories and injects appropriate drivers.

        Args:
            driver_package_path: Path to driver package root (e.g., /path/to/virtio-drivers)

        Returns:
            Dict with injection results for all detected drivers

        Example:
            results = injector.inject_driver_package("/path/to/virtio-drivers")
            for driver, result in results.items():
                if result["ok"]:
                    print(f"{driver}: OK")
        """
        package_root = Path(driver_package_path)
        if not package_root.exists():
            raise FileNotFoundError(f"Driver package not found: {driver_package_path}")

        results = {}

        # Common driver architecture patterns
        arch_patterns = [
            "**/amd64",
            "**/x64",
            "**/w10/amd64",
            "**/w11/amd64",
            "**/*64",
        ]

        for pattern in arch_patterns:
            for driver_dir in package_root.glob(pattern):
                if driver_dir.is_dir():
                    # Check if contains INF files
                    inf_files = list(driver_dir.glob("*.inf"))
                    if inf_files:
                        driver_name = f"{driver_dir.parent.name}/{driver_dir.name}"
                        self.logger.info(f"Found driver: {driver_name}")

                        result = self.inject_driver(str(driver_dir))
                        results[driver_name] = result

        return results

    def list_injected_drivers(self) -> list[str]:
        """
        List all drivers in DriverStore.

        Returns:
            List of driver package names

        Example:
            drivers = injector.list_injected_drivers()
            print(f"Found {len(drivers)} drivers")
        """
        driver_store = self._find_driver_store()
        if not driver_store or not driver_store.exists():
            return []

        drivers = []
        for entry in driver_store.iterdir():
            if entry.is_dir():
                drivers.append(entry.name)

        return sorted(drivers)
