# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Disk image format conversion for NBD pipeline.

Handles VMDK → QCOW2 conversion with:
- Problematic VMDK type detection (streamOptimized, monolithicSparse)
- Space estimation and validation
- Two-step conversion via RAW intermediate for sparse VMDKs
- LVM/LUKS/mdraid-aware sparse threshold selection
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import TYPE_CHECKING, Any

from hyper2kvm.converters.qemu.converter import Convert, run_qemu_img_convert
from hyper2kvm.core.structured_log import PhaseTimer, log_event

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class DiskConverter:
    """
    Converts VMDK disk images to QCOW2 format.

    Handles the full conversion pipeline including format detection,
    space estimation, sparse-aware conversion, and verification.
    Extracted from NBDDeviceManager for single-responsibility.
    """

    def __init__(self, conversion_dir: Path, log: logging.Logger | None = None):
        self.logger = log or logger
        self._conversion_dir = conversion_dir

    @staticmethod
    def _run_command(
        cmd: list[str],
        *,
        check: bool = False,
        timeout: int = 30,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run a local command and return the result."""
        return subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            check=check,
            timeout=timeout,
        )

    @staticmethod
    def _run_json_command(cmd: list[str], *, timeout: int = 30) -> dict[str, Any]:
        """Run a command and parse JSON output."""
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=timeout)
        return json.loads(result.stdout)

    def needs_conversion(self, image_path: Path) -> bool:
        """
        Check if VMDK needs conversion to qcow2.

        Detects problematic VMDK types: streamOptimized, monolithicSparse, compressed.
        """
        if image_path.suffix.lower() != ".vmdk":
            return False

        try:
            info = Convert.qemu_img_info(self.logger, image_path)
            vmdk_info = info.get("format-specific", {}).get("data", {})
            create_type = vmdk_info.get("create-type", "").lower()
            compressed = vmdk_info.get("compressed", False)

            reasons = []
            if "streamoptimized" in create_type:
                reasons.append("streamOptimized format")
            elif "sparse" in create_type:
                reasons.append(f"sparse format ({create_type})")
            if compressed:
                reasons.append("compressed")

            if reasons:
                self.logger.warning(
                    "Detected problematic VMDK: %s. Will convert to qcow2 for reliability.",
                    ", ".join(reasons),
                )
                return True

            return False
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort format probe; any failure just means "skip conversion"
            self.logger.debug("Could not check VMDK type: %s, proceeding without conversion", e)
            return False

    def convert_to_qcow2(self, image_path: Path) -> Path:
        """
        Convert disk image to qcow2 in the configured conversion directory.

        Handles space estimation, two-step RAW intermediate for sparse disks,
        LVM-aware sparse threshold selection, and size verification.

        Returns:
            Path to converted qcow2 file

        Raises:
            RuntimeError: On conversion failure, timeout, or insufficient space
        """
        # Get disk metadata
        original_virtual_size, actual_disk_size, create_type = self._get_disk_info(image_path)

        # Prepare output path
        self._conversion_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        temp_qcow2 = self._conversion_dir / f"{image_path.stem}.qcow2"

        # Check disk space
        if original_virtual_size:
            self._check_disk_space(original_virtual_size, actual_disk_size, create_type)

        self._log_conversion_start(
            image_path, temp_qcow2, create_type, original_virtual_size, actual_disk_size
        )

        with PhaseTimer("disk_conversion_start", "disk_conversion_complete", phase="disk_conversion"):
            try:
                is_sparse = create_type in ("monolithicSparse", "streamOptimized")
                use_raw_intermediate = self._should_use_raw_intermediate(
                    is_sparse,
                    original_virtual_size,
                    actual_disk_size,
                )

                if use_raw_intermediate:
                    self._convert_via_raw(image_path, temp_qcow2)
                else:
                    self._convert_direct(image_path, temp_qcow2)

                # Verify
                self._verify_conversion(temp_qcow2, original_virtual_size)

                self.logger.info(
                    "✓ Conversion completed: %s",
                    temp_qcow2,
                    extra={
                        "ctx": {
                            "event": "disk_conversion_complete",
                            "source": str(image_path),
                            "destination": str(temp_qcow2),
                        }
                    },
                )
                log_event(
                    "disk_conversion_succeeded",
                    source=str(image_path),
                    destination=str(temp_qcow2),
                    create_type=create_type,
                )
                return temp_qcow2

            except subprocess.TimeoutExpired as e:
                if temp_qcow2.exists():
                    temp_qcow2.unlink()
                raise RuntimeError(
                    "Disk conversion timed out after 1 hour. "
                    "The disk image may be very large or the system is under heavy I/O load. "
                    "Consider using a faster storage backend or increasing system resources."
                ) from e
            except subprocess.CalledProcessError as e:
                if temp_qcow2.exists():
                    temp_qcow2.unlink()
                stderr = getattr(e, "stderr", "") or str(e)
                hint = ""
                sl = str(stderr).lower()
                if "no space" in sl or "enospc" in sl:
                    hint = (
                        "\n\nInsufficient disk space for conversion. Free up space in "
                        f"{self._conversion_dir} or set a different conversion directory: "
                        "--conversion-dir /path/with/space"
                    )
                elif "not found" in sl or "no such file" in sl:
                    hint = (
                        "\n\nqemu-img not found. Install it:\n"
                        "  RHEL/Fedora: dnf install qemu-img\n"
                        "  Ubuntu/Debian: apt install qemu-utils"
                    )
                elif "could not open" in sl or "invalid" in sl:
                    hint = (
                        "\n\nThe disk image may be corrupted or in an unsupported format. "
                        "Try re-exporting the VM from the source hypervisor."
                    )
                raise RuntimeError(
                    f"Disk image to qcow2 conversion failed.\n"
                    f"Ensure qemu-img is installed (dnf install qemu-img / apt install qemu-utils) "
                    f"and the source disk is not corrupted.{hint}\n"
                    f"Detail: {e}"
                ) from e

    # ── Internal helpers ────────────────────────────────────────────

    def _get_disk_info(self, image_path: Path) -> tuple[int, int, str]:
        """Get disk virtual size, actual size, and create-type (VMDK-specific, empty for others)."""
        try:
            info = Convert.qemu_img_info(self.logger, image_path)
            return (
                info.get("virtual-size", 0),
                info.get("actual-size", 0),
                info.get("format-specific", {}).get("data", {}).get("create-type", ""),
            )
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort probe; caller falls back to zeroed sizes
            self.logger.warning("Could not get disk image info: %s", e)
            return 0, 0, ""

    def _run_qemu_convert(
        self,
        cmd: list[str],
        *,
        dst: Path,
        src: Path,
        task_label: str,
    ) -> None:
        """Run qemu-img convert with live progress in logs."""
        run_qemu_img_convert(
            self.logger,
            cmd,
            dst,
            src=src,
            task_label=task_label,
            log_every_s=15.0,
        )

    def _check_disk_space(self, virtual_size: int, actual_size: int, create_type: str) -> None:
        """Raise RuntimeError if insufficient space for conversion."""
        stat = self._run_command(
            ["df", "--output=avail", "-B1", str(self._conversion_dir)],
            check=True,
        )
        avail_bytes = int(stat.stdout.strip().split("\n")[-1])

        is_sparse = create_type in ("monolithicSparse", "streamOptimized")
        if is_sparse and actual_size:
            needed = int(max(actual_size * 2.5, virtual_size * 0.05))
        else:
            needed = int(virtual_size * 0.4)

        if avail_bytes < needed:
            allow = os.getenv("HYPER2KVM_ALLOW_LOW_DISK_SPACE", "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            avail_gb = avail_bytes / (1024**3)
            needed_gb = needed / (1024**3)

            if not allow:
                raise RuntimeError(
                    f"Insufficient disk space for conversion:\n"
                    f"  Available: {avail_gb:.1f} GiB in {self._conversion_dir}\n"
                    f"  Needed:    ~{needed_gb:.1f} GiB (estimated)\n\n"
                    f"Possible solutions:\n"
                    f"  1. Free up disk space in {self._conversion_dir}\n"
                    f"  2. Set different conversion directory: --conversion-dir /path/with/space\n"
                    f"  3. Use external storage for conversions\n\n"
                    f"To override this check (may fail mid-conversion):\n"
                    f"  export HYPER2KVM_ALLOW_LOW_DISK_SPACE=1"
                )

            self.logger.warning(
                "⚠️  DANGER: Low disk space detected (%.1f GiB available, ~%.1f GiB needed)",
                avail_gb,
                needed_gb,
            )
            self.logger.warning("⚠️  HYPER2KVM_ALLOW_LOW_DISK_SPACE=1 detected - proceeding anyway")

    def _log_conversion_start(
        self, image_path: Path, dest: Path, create_type: str, virtual_size: int, actual_size: int
    ) -> None:
        src_format = image_path.suffix.lstrip(".").upper() or "disk"
        self.logger.info(
            "Converting %s to qcow2...",
            image_path.name,
            extra={
                "ctx": {
                    "event": "disk_conversion_start",
                    "source": str(image_path),
                    "destination": str(dest),
                    "source_format": src_format.lower(),
                    "target_format": "qcow2",
                    "create_type": create_type,
                    "virtual_size_gib": round(virtual_size / (1024**3), 2) if virtual_size else None,
                    "actual_size_gib": round(actual_size / (1024**3), 2) if actual_size else None,
                }
            },
        )
        self.logger.info("  Source: %s", image_path)
        self.logger.info("  Destination: %s", dest)
        if virtual_size:
            self.logger.info("  Original virtual size: %.2f GiB", virtual_size / (1024**3))

    def _should_use_raw_intermediate(self, is_sparse: bool, virtual_size: int, actual_size: int) -> bool:
        """Determine whether to use RAW intermediate for conversion."""
        if not is_sparse:
            return False
        if virtual_size and actual_size:
            sparsity_ratio = actual_size / virtual_size
            if sparsity_ratio < 0.10:
                self.logger.info(
                    "  Highly sparse disk (%.1f%% allocated) — using direct conversion",
                    sparsity_ratio * 100,
                )
                return False
        return True

    def _convert_via_raw(self, image_path: Path, temp_qcow2: Path) -> None:
        """Two-step conversion: disk → RAW → QCOW2."""
        temp_raw = temp_qcow2.with_suffix(".raw")
        try:
            self.logger.info("  Using RAW intermediate for sparse disk (faster)")
            self.logger.info("  Step 1/2: %s → RAW", image_path.suffix.upper().lstrip(".") or "disk")
            self._run_qemu_convert(
                ["qemu-img", "convert", "-p", "-O", "raw", str(image_path), str(temp_raw)],
                dst=temp_raw,
                src=image_path,
                task_label=f"{image_path.suffix.upper().lstrip('.') or 'disk'} → RAW",
            )

            has_layered = self.detect_layered_storage(temp_raw)
            sparse_opt = "4k" if has_layered else "64k"
            label = "LVM detected, sparse threshold 4k" if has_layered else "sparse-aware"
            self.logger.info("  Step 2/2: RAW → QCOW2 (%s)", label)

            self._run_qemu_convert(
                [
                    "qemu-img",
                    "convert",
                    "-p",
                    "-S",
                    sparse_opt,
                    "-f",
                    "raw",
                    "-O",
                    "qcow2",
                    str(temp_raw),
                    str(temp_qcow2),
                ],
                dst=temp_qcow2,
                src=temp_raw,
                task_label="RAW → QCOW2",
            )
        finally:
            if temp_raw.exists():
                self.logger.debug("Removing RAW intermediate: %s", temp_raw)
                temp_raw.unlink()

    def _convert_direct(self, image_path: Path, temp_qcow2: Path) -> None:
        """Direct conversion: disk → QCOW2 (auto-detects source format)."""
        self._run_qemu_convert(
            [
                "qemu-img",
                "convert",
                "-p",
                "-S",
                "4k",
                "-O",
                "qcow2",
                str(image_path),
                str(temp_qcow2),
            ],
            dst=temp_qcow2,
            src=image_path,
            task_label=f"{image_path.suffix.upper().lstrip('.') or 'disk'} → QCOW2",
        )

    def _verify_conversion(self, qcow2_path: Path, original_virtual_size: int) -> None:
        """Verify converted image size matches original."""
        if not original_virtual_size:
            return
        try:
            info = Convert.qemu_img_info(self.logger, qcow2_path)
            converted_size = info.get("virtual-size", 0)
            if converted_size != original_virtual_size:
                self.logger.warning(
                    "Virtual size mismatch: original=%.2f GiB, converted=%.2f GiB",
                    original_virtual_size / (1024**3),
                    converted_size / (1024**3),
                )
            else:
                self.logger.info("✓ Virtual size verified: %.2f GiB", converted_size / (1024**3))
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort post-conversion sanity check, must not fail the conversion
            self.logger.debug("Could not verify qcow2 size: %s", e)

    def detect_layered_storage(self, raw_image: Path) -> bool:
        """
        Detect if RAW image contains layered storage (LVM, mdraid, LUKS, btrfs).

        Sparse detection with layered storage causes corruption.
        """
        detected: list[str] = []

        try:
            result = self._run_command(
                ["parted", "-s", str(raw_image), "print"],
                timeout=30,
            )
            output = result.stdout.lower()
            if "lvm" in output or "8e" in output:
                detected.append("LVM")
            if "raid" in output or "fd" in output:
                detected.append("mdraid")
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort detection; missing tooling must not abort conversion
            self.logger.debug("Partition table check failed: %s", e)

        try:
            result = self._run_command(["file", "-s", str(raw_image)], timeout=30)
            output = result.stdout.lower()
            if "luks" in output or "crypto_luks" in output:
                detected.append("LUKS")
            if "btrfs" in output:
                detected.append("btrfs")
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort detection; missing tooling must not abort conversion
            self.logger.debug("Filesystem signature check failed: %s", e)

        if detected:
            self.logger.info("  🔍 Layered storage detected: %s", ", ".join(detected))
            self.logger.info("  ⚠️  Sparse detection will be disabled to prevent corruption")
            return True

        self.logger.debug("  No layered storage detected, sparse-aware conversion is safe")
        return False
