# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/orchestrator/disk_discovery.py
"""
Disk discovery from various sources.
Handles input disk detection for different conversion modes.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from h2kvm.converters.extractors.ami import AMI
from h2kvm.converters.extractors.libvirt_xml import LibvirtXML
from h2kvm.converters.extractors.ovf import OVF
from h2kvm.converters.extractors.raw import RAW
from h2kvm.converters.extractors.vhd import VHD
from h2kvm.converters.fetch import Fetch
from h2kvm.core.exceptions import Fatal
from h2kvm.core.logger import Log
from h2kvm.core.utils import U
from h2kvm.fixers.live.fixer import LiveFixer
from h2kvm.infrastructure.ssh.ssh_client import SSHClient
from h2kvm.infrastructure.ssh.ssh_config import SSHConfig

from .ssh_opts import normalize_ssh_opts as _normalize_ssh_opts_impl

if TYPE_CHECKING:
    import argparse
    import logging


class DiskDiscovery:  # pylint: disable=too-few-public-methods
    # Public surface is intentionally just discover(); per-source logic lives in private handlers.
    """
    Multi-source disk discovery and extraction engine.

    Discovers, validates, and prepares disk images from diverse input sources
    for the migration pipeline. Handles format-specific extraction, SSH-based
    remote fetching, and temporary workspace management.

    Supported Input Sources:
    - local: Local VMDK files (descriptor + extent or monolithic)
    - ova: VMware OVA archives (TAR with OVF descriptor + VMDKs)
    - ovf: OVF packages (directory with .ovf + VMDKs)
    - vhd: Hyper-V VHD/VHDX files or TAR archives
    - raw: Raw disk images (.img, .raw) or TAR archives
    - ami: Amazon AMI bundles (manifest + parts or TAR)
    - fetch-and-fix: Remote VMDK fetch via SSH/SCP/rsync
    - live-fix: Live VM repair over SSH (no disk extraction)
    - libvirt-xml: Generate migration manifest from libvirt domain XML

    Features:
    - Automatic format detection and extraction
    - Optional on-the-fly QCOW2 conversion during extraction
    - Nested TAR extraction for bundled images
    - SSH client configuration for remote operations
    - Temporary directory lifecycle management
    - Filesystem boundary checking and size validation

    Attributes:
        logger: Logger instance for status/error reporting
        args: Parsed command-line arguments specifying input source

    Returns:
        Tuple[List[Path], Optional[Path]]:
            - List of discovered/extracted disk paths
            - Temporary directory to cleanup (None if cleanup not needed)

    Examples:
        >>> discovery = DiskDiscovery(logger, args)
        >>> disks, temp_dir = discovery.discover(Path("/output"))
        >>> # Process disks...
        >>> if temp_dir and temp_dir.exists():
        ...     shutil.rmtree(temp_dir)  # Cleanup

    See Also:
        - OVF: OVA/OVF archive extraction
        - VHD: Hyper-V format handling
        - RAW: Raw image extraction
        - AMI: Amazon AMI bundle parsing
        - Fetch: Remote SSH-based VMDK retrieval
        - LibvirtXML: Domain XML manifest generation
    """

    def __init__(self, logger: logging.Logger, args: argparse.Namespace):
        self.logger = logger
        self.args = args

    @staticmethod
    def _normalize_ssh_opts(v) -> list[str] | None:
        """Normalize SSH options from various input formats."""
        return _normalize_ssh_opts_impl(v)

    def discover(self, out_root: Path) -> tuple[list[Path], Path | None]:
        """
        Discover disks based on args.cmd.

        Args:
            out_root: Output directory root

        Returns:
            Tuple of (disk_list, temp_dir_to_cleanup)
            temp_dir is None if no cleanup needed or if mode exits early (live-fix, vsphere)
        """
        cmd = getattr(self.args, "cmd", None)
        Log.trace(self.logger, "🧭 discover_disks: cmd=%r out_root=%s", cmd, out_root)

        # Dispatch to appropriate handler
        handlers = {
            "local": self._discover_local,
            "fetch-and-fix": self._discover_fetch_and_fix,
            "ova": self._discover_ova,
            "ovf": self._discover_ovf,
            "vhd": self._discover_vhd,
            "raw": self._discover_raw,
            "ami": self._discover_ami,
            "live-fix": self._discover_live_fix,
            "libvirt-xml": self._discover_libvirt_xml,
            "daemon": lambda _o: ([], None),
            "generate-systemd": lambda _o: ([], None),
        }

        handler = handlers.get(cmd)
        if not handler:
            valid_cmds = sorted(handlers.keys())
            U.die(
                self.logger,
                f"Unknown command: '{cmd}'.\n"
                f"Supported input sources: {', '.join(valid_cmds)}\n\n"
                "Examples:\n"
                "  h2kvmctl local --vmdk /path/to/disk.vmdk\n"
                "  h2kvmctl ova --ova /path/to/vm.ova\n"
                "  h2kvmctl vhd --vhd /path/to/disk.vhdx",
                1,
            )

        disks, temp_dir = handler(out_root)
        Log.trace(self.logger, "📦 discovered disks=%d: %s", len(disks), [str(d) for d in disks])
        return disks, temp_dir

    def _discover_local(self, _out_root: Path) -> tuple[list[Path], Path | None]:
        """Handle local disk discovery."""
        disk_path = Path(self.args.vmdk).expanduser().resolve()
        if not disk_path.exists():
            raise Fatal(
                2,
                f"Disk image not found: {disk_path}\n"
                "Verify the path is correct and the file has not been moved or deleted.\n"
                "For split VMDKs, point to the descriptor file (not the -flat.vmdk extent).",
            )
        if not disk_path.is_file():
            raise Fatal(
                2,
                f"Path is not a regular file: {disk_path}\n"
                "Provide a path to a disk image file (.vmdk, .qcow2, .raw, .vhd, etc.).",
            )
        disks = [disk_path]
        Log.trace(self.logger, "📍 local disk: %s", disks[0])
        return disks, None

    def _discover_fetch_and_fix(self, out_root: Path) -> tuple[list[Path], Path | None]:
        """Handle remote fetch-and-fix discovery."""
        sshc = SSHClient(
            self.logger,
            SSHConfig(
                host=self.args.host,
                user=self.args.user,
                port=self.args.port,
                identity=getattr(self.args, "identity", None),
                ssh_opts=self._normalize_ssh_opts(getattr(self.args, "ssh_opt", None)),
                sudo=False,
            ),
        )
        fetch_dir = (
            Path(self.args.fetch_dir).expanduser().resolve()
            if getattr(self.args, "fetch_dir", None)
            else (out_root / "downloaded")
        )
        U.ensure_dir(fetch_dir)
        Log.step(self.logger, f"Fetching remote VMDK descriptor/extent → {fetch_dir}")
        desc = Fetch.fetch_descriptor_and_extent(
            self.logger,
            sshc,
            self.args.remote,
            fetch_dir,
            getattr(self.args, "fetch_all", False),
        )
        disks = [desc]
        Log.ok(self.logger, f"Fetched: {desc.name}")
        return disks, None

    def _discover_ova(self, out_root: Path) -> tuple[list[Path], Path | None]:
        """Handle OVA extraction."""
        temp_dir = out_root / "extracted"
        U.ensure_dir(temp_dir)

        Log.step(self.logger, f"Extract OVA → {temp_dir}")
        disks = OVF.extract_ova(
            self.logger,
            Path(self.args.ova).expanduser().resolve(),
            temp_dir,
            convert_to_qcow2=bool(getattr(self.args, "to_qcow2", False)),
            convert_outdir=(
                Path(self.args.qcow2_dir).expanduser().resolve()
                if getattr(self.args, "qcow2_dir", None)
                else (out_root / "qcow2")
            ),
            convert_compress=bool(getattr(self.args, "compress", False)),
            convert_compress_level=getattr(self.args, "compress_level", None),
            log_virt_filesystems=bool(getattr(self.args, "log_virt_filesystems", False)),
        )
        self.logger.info("📦 Extracted %d disk(s) from OVA", len(disks))
        self._apply_ovf_firmware()
        return disks, temp_dir

    def _discover_ovf(self, out_root: Path) -> tuple[list[Path], Path | None]:
        """Handle OVF extraction."""
        temp_dir = out_root / "extracted"
        Log.step(self.logger, f"Extract OVF → {temp_dir}")
        disks = OVF.extract_ovf(
            self.logger,
            Path(self.args.ovf).expanduser().resolve(),
            temp_dir,
        )
        self.logger.info("📦 Extracted %d disk(s) from OVF", len(disks))
        self._apply_ovf_firmware()
        return disks, temp_dir

    def _apply_ovf_firmware(self) -> None:
        """If OVF declared UEFI firmware, propagate to args so downstream uses it."""
        if OVF.last_firmware == "uefi" and not getattr(self.args, "uefi", False):
            self.logger.info("UEFI firmware detected from OVF metadata — auto-enabling UEFI")
            self.args.uefi = True

    def _discover_vhd(self, out_root: Path) -> tuple[list[Path], Path | None]:
        """Handle VHD/TAR extraction. Supports single file or directory of VHD/VHDX files."""
        vhd_path = Path(self.args.vhd).expanduser().resolve()

        # If path is a directory, discover all VHD/VHDX files inside (multi-disk support)
        if vhd_path.is_dir():
            all_disks: list[Path] = []
            for ext in ("*.vhd", "*.vhdx"):
                all_disks.extend(sorted(vhd_path.glob(ext)))
            if not all_disks:
                raise Fatal(2, f"No .vhd or .vhdx files found in directory: {vhd_path}")

            self.logger.info("📦 Directory mode: found %d VHD/VHDX disk(s) in %s", len(all_disks), vhd_path)

            # Process each disk through the VHD extractor
            temp_dir = out_root / "extracted"
            result_disks: list[Path] = []
            for disk in all_disks:
                self.logger.info("  Processing disk: %s", disk.name)
                extracted = VHD.extract_vhd_or_tar(
                    self.logger,
                    disk,
                    temp_dir,
                    convert_to_qcow2=True,
                    convert_outdir=out_root / "qcow2",
                    convert_compress=bool(self.args.compress),
                    convert_compress_level=self.args.compress_level,
                    log_virt_filesystems=True,
                )
                result_disks.extend(extracted)

            self.logger.info(
                "📦 Extracted %d total disk(s) from %d VHD/VHDX files", len(result_disks), len(all_disks)
            )
            return result_disks, temp_dir

        # Single file: existing behavior
        temp_dir = out_root / "extracted"
        Log.step(self.logger, f"Extract VHD/TAR → {temp_dir}")
        disks = VHD.extract_vhd_or_tar(
            self.logger,
            vhd_path,
            temp_dir,
            convert_to_qcow2=True,
            convert_outdir=out_root / "qcow2",
            convert_compress=bool(self.args.compress),
            convert_compress_level=self.args.compress_level,
            log_virt_filesystems=True,
        )
        self.logger.info("📦 Extracted %d disk(s) from VHD/TAR", len(disks))
        return disks, temp_dir

    def _discover_raw(self, out_root: Path) -> tuple[list[Path], Path | None]:
        """Handle RAW/IMG/TAR extraction."""
        temp_dir = out_root / "extracted"
        Log.step(self.logger, f"Extract RAW/IMG/TAR → {temp_dir}")

        raw_src = (
            getattr(self.args, "raw", None)
            or getattr(self.args, "img", None)
            or getattr(self.args, "raw_src", None)
            or getattr(self.args, "raw_path", None)
        )
        if not raw_src:
            raise Fatal(2, "raw mode requires --raw <path> (or config: raw/img/raw_src/raw_path)")

        disks = RAW.extract_raw_or_tar(
            self.logger,
            Path(raw_src).expanduser().resolve(),
            temp_dir,
            convert_to_qcow2=bool(
                getattr(self.args, "to_qcow2", False) or getattr(self.args, "convert_to_qcow2", False)
            ),
            convert_outdir=(
                Path(getattr(self.args, "qcow2_dir", None)).expanduser().resolve()
                if getattr(self.args, "qcow2_dir", None)
                else (out_root / "qcow2")
            ),
            convert_compress=bool(getattr(self.args, "compress", False)),
            convert_compress_level=getattr(self.args, "compress_level", None),
            log_virt_filesystems=bool(getattr(self.args, "log_virt_filesystems", False)),
            max_members=getattr(self.args, "max_members", None),
            max_total_bytes=getattr(self.args, "max_total_bytes", None),
            max_manifest_bytes=int(
                getattr(self.args, "max_manifest_bytes", 5 * 1024 * 1024) or (5 * 1024 * 1024)
            ),
            skip_special=bool(getattr(self.args, "skip_special", True)),
            preserve_permissions=bool(getattr(self.args, "preserve_permissions", True)),
            extract_all=bool(getattr(self.args, "extract_all", False)),
            include_manifests=bool(getattr(self.args, "include_manifests", True)),
            overwrite=bool(getattr(self.args, "overwrite", False)),
            rename_on_collision=bool(getattr(self.args, "rename_on_collision", False)),
            preserve_timestamps=bool(getattr(self.args, "preserve_timestamps", False)),
        )
        self.logger.info("📦 Extracted %d disk(s) from RAW/IMG/TAR", len(disks))
        return disks, temp_dir

    def _discover_ami(self, out_root: Path) -> tuple[list[Path], Path | None]:
        """Handle AMI/TAR extraction."""
        temp_dir = out_root / "extracted"
        Log.step(self.logger, f"Extract AMI/TAR → {temp_dir}")

        disks = AMI.extract_ami_or_tar(
            self.logger,
            Path(self.args.ami).expanduser().resolve(),
            temp_dir,
            extract_nested_tar=bool(getattr(self.args, "extract_nested_tar", True)),
            convert_to_qcow2=bool(getattr(self.args, "convert_payload_to_qcow2", False)),
            convert_outdir=(
                Path(self.args.payload_qcow2_dir).expanduser().resolve()
                if getattr(self.args, "payload_qcow2_dir", None)
                else (out_root / "qcow2")
            ),
            convert_compress=bool(getattr(self.args, "payload_convert_compress", False)),
            convert_compress_level=getattr(self.args, "payload_convert_compress_level", None),
            log_virt_filesystems=True,
        )
        self.logger.info("📦 Extracted %d disk(s) from AMI/TAR", len(disks))
        return disks, temp_dir

    def _discover_live_fix(self, _out_root: Path) -> tuple[list[Path], Path | None]:
        """Handle live-fix over SSH."""
        sshc = SSHClient(
            self.logger,
            SSHConfig(
                host=self.args.host,
                user=self.args.user,
                port=self.args.port,
                identity=getattr(self.args, "identity", None),
                password=getattr(self.args, "ssh_password", None),
                ssh_opts=self._normalize_ssh_opts(getattr(self.args, "ssh_opt", None)),
                sudo=getattr(self.args, "sudo", False),
            ),
        )
        Log.step(self.logger, "Live-fix over SSH")
        LiveFixer(
            self.logger,
            sshc,
            dry_run=getattr(self.args, "dry_run", False),
            no_backup=getattr(self.args, "no_backup", False),
            print_fstab=getattr(self.args, "print_fstab", False),
            update_grub=not getattr(self.args, "no_grub", False),
            regen_initramfs=getattr(self.args, "regen_initramfs", True),
            remove_vmware_tools=getattr(self.args, "remove_vmware_tools", False),
            luks_passphrase=getattr(self.args, "luks_passphrase", None),
            luks_passphrase_env=getattr(self.args, "luks_passphrase_env", None),
            luks_keyfile=getattr(self.args, "luks_keyfile", None),
        ).run()
        self.logger.info("✅ Live fix done.")
        return [], None

    def _discover_libvirt_xml(self, out_root: Path) -> tuple[list[Path], Path | None]:
        """Handle libvirt domain XML parsing."""
        Log.step(self.logger, "Parse Libvirt Domain XML → Generate Manifest")

        xml_path = getattr(self.args, "libvirt_xml", None) or getattr(self.args, "xml_path", None)
        if not xml_path:
            raise Fatal(2, "libvirt-xml mode requires --libvirt-xml <path> or --xml-path <path>")

        LibvirtXML.parse_domain_xml(
            self.logger,
            Path(xml_path).expanduser().resolve(),
            output_dir=out_root,
            compute_checksums=bool(getattr(self.args, "compute_checksums", True)),
            manifest_filename=getattr(self.args, "manifest_filename", "manifest.json"),
        )

        self.logger.info("=" * 80)
        self.logger.info("✅ Artifact Manifest v1 generated successfully")
        self.logger.info("=" * 80)
        self.logger.info(
            f"📄 Manifest: {out_root / getattr(self.args, 'manifest_filename', 'manifest.json')}"
        )
        self.logger.info("")
        self.logger.info("Next steps:")
        self.logger.info(
            f"  sudo h2kvm --config {out_root / getattr(self.args, 'manifest_filename', 'manifest.json')}"
        )
        self.logger.info("")

        return [], None
