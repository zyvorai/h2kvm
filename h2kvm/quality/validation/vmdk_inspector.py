# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
VMDK Inspector - Pre-migration VMDK validation and risk analysis.

Provides enterprise-grade VMDK inspection including:
- Descriptor parsing and validation
- Controller compatibility checking
- Snapshot chain detection
- UEFI vs BIOS boot mode detection
- Extent file validation
- Risk-based analysis
"""

import logging
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from h2kvm.core.structured_log import PhaseTimer, log_event


class RiskLevel(Enum):
    """Risk severity levels."""

    FATAL = "FATAL"  # Migration will fail
    HIGH = "HIGH"  # Likely boot/driver issues
    MEDIUM = "MEDIUM"  # Minor compatibility issues
    INFO = "INFO"  # Informational only


class BootMode(Enum):
    """Boot firmware mode."""

    BIOS = "BIOS"
    UEFI = "UEFI"
    UNKNOWN = "UNKNOWN"


@dataclass
class Risk:
    """Individual risk finding."""

    level: RiskLevel
    message: str
    component: str = "general"  # controller, boot, snapshot, extent, etc.


@dataclass
class VMDKInspectionResult:
    """Complete VMDK inspection result."""

    path: Path
    valid: bool

    # Descriptor metadata
    create_type: Optional[str] = None
    parent_cid: Optional[str] = None
    adapter_type: Optional[str] = None
    thin_provisioned: bool = False

    # Disk geometry
    sectors: Optional[int] = None
    extent_type: Optional[str] = None
    extent_file: Optional[str] = None
    extents: list[dict[str, Any]] = field(default_factory=list)  # All extents for split VMDKs
    geometry: dict[str, str] = field(default_factory=dict)

    # Boot mode detection
    boot_mode: BootMode = BootMode.UNKNOWN

    # Risk analysis
    risks: list[Risk] = field(default_factory=list)

    # Auto-fix tracking
    fixed_vmdk_path: Optional[Path] = None  # Path to fixed VMDK if BusLogic was auto-fixed

    @property
    def size_bytes(self) -> Optional[int]:
        """Calculate disk size in bytes."""
        return self.sectors * 512 if self.sectors else None

    @property
    def size_gb(self) -> Optional[float]:
        """Calculate disk size in GB."""
        if self.size_bytes:
            return round(self.size_bytes / (1024**3), 2)
        return None

    @property
    def has_fatal_risks(self) -> bool:
        """Check if any FATAL risks exist."""
        return any(r.level == RiskLevel.FATAL for r in self.risks)

    @property
    def has_high_risks(self) -> bool:
        """Check if any HIGH risks exist."""
        return any(r.level == RiskLevel.HIGH for r in self.risks)

    @property
    def max_risk_level(self) -> Optional[RiskLevel]:
        """Get highest risk level."""
        if not self.risks:
            return None
        levels = [r.level for r in self.risks]
        for level in [RiskLevel.FATAL, RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.INFO]:
            if level in levels:
                return level
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "path": str(self.path),
            "valid": self.valid,
            "create_type": self.create_type,
            "adapter_type": self.adapter_type,
            "thin_provisioned": self.thin_provisioned,
            "size_gb": self.size_gb,
            "boot_mode": self.boot_mode.value,
            "extent_type": self.extent_type,
            "risks": [
                {"level": r.level.value, "message": r.message, "component": r.component} for r in self.risks
            ],
            "max_risk_level": self.max_risk_level.value if self.max_risk_level else None,
        }


class VMDKInspector:
    """
    VMDK inspection and validation engine.

    Performs comprehensive pre-migration validation of VMDK files including:
    - Descriptor parsing
    - Risk analysis
    - Boot mode detection (UEFI/BIOS)
    - Controller compatibility
    - Snapshot detection
    """

    # Controller compatibility mapping
    FATAL_CONTROLLERS = {"buslogic"}
    HIGH_RISK_CONTROLLERS = {"lsilogic", "lsilogicsas"}
    SAFE_CONTROLLERS = {"virtio", "pvscsi"}

    # Regex patterns
    EXTENT_PATTERN = re.compile(r'^RW\s+(\d+)\s+(\w+)\s+"(.+)"')

    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize inspector."""
        self.logger = logger or logging.getLogger(__name__)

    def inspect(self, vmdk_path: Path) -> VMDKInspectionResult:
        """
        Perform comprehensive VMDK inspection.

        Args:
            vmdk_path: Path to VMDK descriptor file

        Returns:
            VMDKInspectionResult with all findings
        """
        self.logger.info(f"Inspecting disk: {vmdk_path}")

        result = VMDKInspectionResult(path=vmdk_path, valid=False)

        if not vmdk_path.exists():
            result.risks.append(Risk(RiskLevel.FATAL, f"Disk image not found: {vmdk_path}", "extent"))
            return result

        with PhaseTimer("vmdk_inspection_start", "vmdk_inspection_complete", phase="vmdk_inspection"):
            # Parse descriptor
            self.logger.info("  → Parsing VMDK descriptor...")
            self._parse_descriptor(vmdk_path, result)

            # Fallback: infer size from flat file if descriptor didn't provide it
            if result.sectors is None:
                self.logger.info("  → Inferring disk size from extent file...")
                self._infer_size_from_extent(result)

            # Analyze risks
            self.logger.info("  → Analyzing migration risks (controller, snapshots, geometry)...")
            self._analyze_snapshot_risks(result)
            self._analyze_controller_risks(result)
            self._analyze_geometry_risks(result)
            self._analyze_extent_risks(result)

            # Detect boot mode
            self.logger.info("  → Detecting boot mode (BIOS/UEFI) - this may take 1-2 minutes...")
            self._detect_boot_mode(result)

            # Mark as valid if no fatal risks
            result.valid = not result.has_fatal_risks

        log_event(
            "vmdk_inspection_result",
            vmdk=str(vmdk_path),
            valid=result.valid,
            risk_count=len(result.risks),
            adapter_type=result.adapter_type,
            boot_mode=result.boot_mode.value,
            create_type=result.create_type,
        )
        self.logger.info(f"Inspection complete: {len(result.risks)} findings")
        return result

    def _parse_descriptor(self, path: Path, result: VMDKInspectionResult):
        """
        Parse VMDK descriptor file.

        VMDK descriptors are small text sections (typically <2KB) that contain
        metadata like createType, adapterType, extent references, and geometry.

        For split VMDKs, the descriptor is a standalone text file (<10KB).
        For monolithic/streamOptimized VMDKs, the descriptor is embedded in
        the first few KB of the binary file. We only read the first 64KB to
        avoid scanning the entire multi-GB binary data section.
        """
        try:
            file_size = path.stat().st_size

            # Read only the descriptor portion -- never the entire file.
            # VMDK descriptors are always in the first few KB. For monolithic
            # binary VMDKs (streamOptimized, monolithicSparse), reading the
            # full file would scan GB of binary data line-by-line, causing
            # the parse to appear hung for minutes/hours.
            max_read = min(file_size, 64 * 1024)  # 64KB is more than enough

            self.logger.info(
                "     Reading first %d bytes of %s (file size: %.2f GB)",
                max_read,
                path.name,
                file_size / (1024**3),
            )

            with path.open("rb") as f:
                raw = f.read(max_read)

            # Decode as ASCII with error replacement (descriptor is ASCII text,
            # binary portions will have garbage but we only care about key= lines)
            text = raw.decode("ascii", errors="replace")

            lines_parsed = 0
            descriptor_keys_found = 0
            for line in text.splitlines():
                lines_parsed += 1
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                if line.startswith("createType"):
                    result.create_type = self._extract_value(line)
                    descriptor_keys_found += 1

                elif line.startswith("parentCID"):
                    result.parent_cid = self._extract_value(line)
                    descriptor_keys_found += 1

                elif line.startswith("ddb.adapterType"):
                    result.adapter_type = self._extract_value(line).lower()
                    descriptor_keys_found += 1

                elif line.startswith("ddb.thinProvisioned"):
                    result.thin_provisioned = self._extract_value(line) == "1"
                    descriptor_keys_found += 1

                elif line.startswith("ddb.geometry"):
                    key = line.split(".")[-1].split("=")[0]
                    result.geometry[key] = self._extract_value(line)
                    descriptor_keys_found += 1

                elif line.startswith("RW"):
                    m = self.EXTENT_PATTERN.match(line)
                    if m:
                        ext_sectors = int(m.group(1))
                        ext_type = m.group(2)
                        ext_file = m.group(3)
                        result.extents.append(
                            {
                                "sectors": ext_sectors,
                                "type": ext_type,
                                "file": ext_file,
                            }
                        )
                        # Keep first extent as primary (compat)
                        if result.extent_file is None:
                            result.sectors = ext_sectors
                            result.extent_type = ext_type
                            result.extent_file = ext_file
                        descriptor_keys_found += 1

            self.logger.info(
                "     Parsed %d lines, found %d descriptor keys (createType=%s, adapter=%s, extent=%s)",
                lines_parsed,
                descriptor_keys_found,
                result.create_type,
                result.adapter_type,
                result.extent_type,
            )

        except Exception as e:
            self.logger.exception(f"Failed to parse descriptor: {e}")
            result.risks.append(Risk(RiskLevel.FATAL, f"Descriptor parsing failed: {e}", "general"))

    def _extract_value(self, line: str) -> str:
        """Extract value from descriptor key=value line."""
        return line.split("=", 1)[1].strip().strip('"')

    def _infer_size_from_extent(self, result: VMDKInspectionResult):
        """
        Infer disk size from extent file when descriptor parsing fails.

        This is a fallback for:
        - streamOptimized VMDKs (binary header, no RW line)
        - Thin-provisioned ESXi exports
        - Corrupted descriptors
        - Monolithic VMDK files (descriptor + data in one file)
        """
        extent_path = None

        # Try 1: Separate extent file referenced in descriptor
        if result.extent_file:
            extent_path = result.path.parent / result.extent_file
            if not extent_path.exists():
                self.logger.debug(f"Referenced extent file not found: {extent_path}")
                extent_path = None

        # Try 2: The VMDK itself might be monolithic (streamOptimized, etc.)
        if extent_path is None:
            # Check if the VMDK file itself is large enough to be a disk image
            try:
                vmdk_size = result.path.stat().st_size
                if vmdk_size > 1024 * 1024:  # > 1MB, likely contains data
                    extent_path = result.path
                    self.logger.debug("Using VMDK file itself as extent (monolithic format)")
            except Exception as e:
                self.logger.debug(f"Failed to check VMDK file size: {e}")

        if not extent_path:
            self.logger.debug("No extent file available for size inference")
            return

        try:
            extent_size = extent_path.stat().st_size
            if extent_size > 0:
                # Infer sectors from file size
                result.sectors = extent_size // 512
                source = "extent file" if extent_path != result.path else "VMDK file (streamOptimized)"
                self.logger.debug(
                    f"Inferred size from {source}: {result.size_gb:.2f} GB ({extent_size} bytes)"
                )
                result.risks.append(
                    Risk(RiskLevel.INFO, f"Size inferred from {source} ({result.size_gb:.2f} GB)", "extent")
                )
        except Exception as e:
            self.logger.debug(f"Failed to infer size: {e}")

    def _analyze_snapshot_risks(self, result: VMDKInspectionResult):
        """Check for snapshot chains."""
        if result.parent_cid and result.parent_cid.lower() != "ffffffff":
            result.risks.append(
                Risk(
                    RiskLevel.FATAL,
                    "Snapshot chain detected (parentCID != ffffffff) - must consolidate before migration",
                    "snapshot",
                )
            )

    def _analyze_controller_risks(self, result: VMDKInspectionResult):
        """Analyze controller compatibility."""
        if not result.adapter_type:
            result.risks.append(Risk(RiskLevel.MEDIUM, "Missing ddb.adapterType metadata", "controller"))
            return

        adapter = result.adapter_type

        if adapter in self.FATAL_CONTROLLERS:
            result.risks.append(
                Risk(
                    RiskLevel.FATAL,
                    f"Legacy controller '{adapter}' unsupported on KVM - no driver available",
                    "controller",
                )
            )

        elif adapter in self.HIGH_RISK_CONTROLLERS:
            result.risks.append(
                Risk(
                    RiskLevel.HIGH,
                    f"Controller '{adapter}' may require initramfs rebuild with virtio drivers",
                    "controller",
                )
            )

        elif adapter not in self.SAFE_CONTROLLERS:
            result.risks.append(
                Risk(
                    RiskLevel.HIGH,
                    f"Controller mismatch: guest expects '{adapter}', KVM will use virtio",
                    "controller",
                )
            )

    def _analyze_geometry_risks(self, result: VMDKInspectionResult):
        """Check legacy geometry."""
        if result.geometry:
            result.risks.append(
                Risk(RiskLevel.INFO, "Legacy CHS geometry present (ignored by modern kernels)", "geometry")
            )

    def _analyze_extent_risks(self, result: VMDKInspectionResult):
        """Validate extent files."""
        if result.extent_type == "VMFS":
            result.risks.append(
                Risk(RiskLevel.INFO, "VMFS-backed extent - conversion will read via ESXi API", "extent")
            )

        # For split VMDKs (twoGbMaxExtentSparse etc.), validate each extent individually
        if result.extents and len(result.extents) > 1:
            for ext in result.extents:
                ext_file = result.path.parent / ext["file"]
                if not ext_file.exists():
                    result.risks.append(
                        Risk(RiskLevel.FATAL, f"Extent file missing: {ext['file']}", "extent")
                    )
            return

        # Single-extent VMDK: validate size
        if result.extent_file and result.sectors:
            flat = result.path.parent / result.extent_file
            expected_size = result.sectors * 512

            if not flat.exists():
                result.risks.append(Risk(RiskLevel.FATAL, f"Extent file missing: {flat.name}", "extent"))
            else:
                actual_size = flat.stat().st_size
                if actual_size < expected_size:
                    result.risks.append(
                        Risk(
                            RiskLevel.FATAL,
                            f"Extent size mismatch: expected ≥{expected_size}, got {actual_size}",
                            "extent",
                        )
                    )

    def _detect_boot_mode(self, result: VMDKInspectionResult):
        """
        Detect UEFI vs BIOS boot mode using virt-inspector.

        This is critical for proper libvirt domain configuration.
        """
        if not result.extent_file:
            result.boot_mode = BootMode.UNKNOWN
            self.logger.info("     Boot mode detection skipped (no extent file)")
            return

        flat = result.path.parent / result.extent_file
        if not flat.exists():
            result.boot_mode = BootMode.UNKNOWN
            self.logger.info("     Boot mode detection skipped (extent file not found)")
            return

        try:
            self.logger.info("     Running virt-inspector to detect boot firmware...")
            cmd = ["virt-inspector", "--no-applications", "--no-icon", str(flat)]
            output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True, timeout=30)

            # Check for UEFI indicators
            if 'firmware="uefi"' in output.lower() or "/efi/" in output.lower():
                result.boot_mode = BootMode.UEFI
                self.logger.info("     ✓ Detected UEFI boot mode")
                result.risks.append(
                    Risk(
                        RiskLevel.HIGH,
                        "UEFI firmware detected - libvirt domain MUST use OVMF (not SeaBIOS)",
                        "boot",
                    )
                )
            else:
                result.boot_mode = BootMode.BIOS
                self.logger.info("     ✓ Detected BIOS boot mode")

        except FileNotFoundError:
            result.boot_mode = BootMode.UNKNOWN
            result.risks.append(
                Risk(
                    RiskLevel.INFO,
                    "virt-inspector not available - boot mode detection skipped",
                    "boot",
                )
            )

        except subprocess.TimeoutExpired:
            result.boot_mode = BootMode.UNKNOWN
            result.risks.append(Risk(RiskLevel.INFO, "Boot mode detection timed out", "boot"))

        except subprocess.CalledProcessError as e:
            result.boot_mode = BootMode.UNKNOWN
            self.logger.debug(f"virt-inspector failed: {e}")
            result.risks.append(
                Risk(
                    RiskLevel.INFO, "Unable to detect boot mode (disk may be encrypted or corrupted)", "boot"
                )
            )

    def generate_libvirt_config(self, result: VMDKInspectionResult, converted_image_path: str) -> str:
        """
        Generate libvirt XML disk configuration based on inspection results.

        Args:
            result: Inspection result
            converted_image_path: Path to converted qcow2 image

        Returns:
            libvirt XML snippet
        """
        xml = f"""<disk type='file' device='disk'>
  <driver name='qemu' type='qcow2' cache='none' io='native'/>
  <source file='{converted_image_path}'/>
  <target dev='vda' bus='virtio'/>
</disk>

<controller type='scsi' index='0' model='virtio-scsi'/>"""

        if result.boot_mode == BootMode.UEFI:
            xml += """

<!-- UEFI firmware configuration (REQUIRED for UEFI guests) -->
<os>
  <type arch='x86_64' machine='pc-q35'>hvm</type>
  <loader readonly='yes' type='pflash'>/usr/share/OVMF/OVMF_CODE.fd</loader>
  <nvram>/var/lib/libvirt/qemu/nvram/VM_NAME_VARS.fd</nvram>
</os>"""

        return xml
