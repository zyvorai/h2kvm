# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Disk image conversion for AWS exports."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Callable

from hyper2kvm.converters.qemu.converter import run_qemu_img_convert

logger = logging.getLogger(__name__)


class Converter:
    """
    Convert exported disk images to qcow2 format.

    Supports both qemu-img (simple conversion) and integration
    with hyper2kvm's offline fix pipeline.
    """

    def __init__(self, log: logging.Logger | None = None):
        self.log = log or logger

    def convert_to_qcow2(
        self,
        src: str | Path,
        dest: str | Path,
        *,
        compress: bool = True,
        progress_cb: Callable[[str], None] | None = None,
    ) -> Path:
        """
        Convert a disk image to qcow2 using qemu-img.

        Args:
            src: Source image path (vmdk, vhd, raw)
            dest: Destination qcow2 path
            compress: Enable compression
            progress_cb: Callback with progress line text

        Returns:
            Path to converted qcow2
        """
        src = Path(src)
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)

        cmd = ["qemu-img", "convert", "-p", "-O", "qcow2"]
        if compress:
            cmd.append("-c")
        cmd.extend([str(src), str(dest)])

        self.log.info("Converting %s -> %s (compress=%s)", src.name, dest.name, compress)

        def _progress(frac: float) -> None:
            if progress_cb:
                progress_cb(f"{frac * 100.0:.1f}%")

        run_qemu_img_convert(
            self.log,
            cmd,
            dest,
            src=src,
            task_label="AWS export → qcow2",
            progress_callback=_progress if progress_cb else None,
            log_every_s=15.0,
        )

        self.log.info("Conversion complete: %s (%.2f GB)", dest.name, dest.stat().st_size / (1024**3))
        return dest

    def run_h2kvmctl(  # pylint: disable=too-many-arguments
        # h2kvmctl CLI wrapper exposes several independent pipeline toggles;
        # keyword-only options keep call sites readable despite the count.
        self,
        src: str | Path,
        output_dir: str | Path,
        *,
        vm_name: str = "aws-vm",
        compress: bool = True,
        regen_initramfs: bool = True,
        emit_domain_xml: bool = True,
        extra_args: list[str] | None = None,
    ) -> int:
        """
        Run h2kvmctl for full offline-fix pipeline.

        This is the preferred conversion path — it handles:
        - Format conversion (qcow2)
        - fstab stabilization
        - GRUB root= fix
        - initramfs rebuild with VirtIO drivers
        - Libvirt domain XML generation

        Args:
            src: Source disk image
            output_dir: Output directory
            vm_name: VM name for libvirt
            compress: Compress output
            regen_initramfs: Rebuild initramfs with VirtIO drivers
            emit_domain_xml: Generate libvirt XML
            extra_args: Additional h2kvmctl arguments

        Returns:
            h2kvmctl exit code
        """
        src = Path(src)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # h2kvmctl accepts any image format via --vmdk (legacy name)
        # regardless of actual format (raw, vhd, vmdk)
        cmd = [
            "h2kvmctl",
            "--cmd",
            "local",
            "--vmdk",
            str(src),
            "--output-dir",
            str(output_dir),
            "--to-output",
            f"{vm_name}.qcow2",
            "--out-format",
            "qcow2",
            "--fstab-mode",
            "stabilize-all",
        ]

        if compress:
            cmd.append("--compress")
        if regen_initramfs:
            cmd.append("--regen-initramfs")
        if emit_domain_xml:
            cmd.append("--emit-domain-xml")
            cmd.extend(["--vm-name", vm_name])

        if extra_args:
            cmd.extend(extra_args)

        self.log.info("Running h2kvmctl pipeline: %s", " ".join(cmd))

        result = subprocess.run(cmd, capture_output=False, check=False)
        return result.returncode
