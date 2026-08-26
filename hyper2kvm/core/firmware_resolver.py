# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Resolve guest firmware (BIOS vs UEFI) from offline signals and user overrides."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

FirmwareMode = Literal["bios", "uefi"]
UserFirmwareMode = Literal["auto", "bios", "uefi"]
Confidence = Literal["high", "medium", "low"]


@dataclass(slots=True)
class FirmwareSignals:  # pylint: disable=too-many-instance-attributes
    """Inputs collected from disk analysis, provider metadata, and offline fixer.

    Each field is an independent detection signal; the count is inherent to
    covering all the boot-mode heuristics this resolver considers.
    """

    boot_mode: str | None = None  # bios | uefi | unknown
    partition_scheme: str | None = None  # mbr | gpt | unknown
    has_efi_partition: bool | None = None
    windows_bcd_bios: bool = False
    windows_bcd_uefi: bool = False
    hyperv_generation: int | None = None  # 1 → BIOS hint, 2 → UEFI hint
    ovf_firmware: str | None = None  # bios | uefi
    is_windows: bool = False


@dataclass(slots=True)
class FirmwareResolution:
    """Resolved firmware mode plus the confidence and source of that decision."""

    firmware: FirmwareMode
    user_mode: UserFirmwareMode
    source: str
    confidence: Confidence
    alternate: FirmwareMode | None = None
    signals: dict[str, Any] = field(default_factory=dict)


def reconcile_legacy_firmware_flags(
    *,
    firmware_mode: str | None = None,
    uefi_flag: bool | None = None,
) -> str:
    """
    Promote legacy ``uefi: true`` / ``--uefi`` to ``firmware_mode=uefi``.

    Auto-detected hints must not set ``args.uefi``; only explicit operator config/CLI should.
    """
    mode = (firmware_mode or "auto").strip().lower()
    if mode in ("bios", "uefi"):
        return mode
    # Legacy ``uefi: true`` / ``--uefi`` only — argparse defaults uefi to False, not "explicit bios".
    if uefi_flag is True:
        return "uefi"
    return "auto"


def normalize_user_firmware_mode(
    *,
    firmware_mode: str | None = None,
    uefi_flag: bool | None = None,
) -> UserFirmwareMode:
    """Map legacy ``uefi: true/false`` and ``firmware_mode`` to a single user mode."""
    return reconcile_legacy_firmware_flags(  # type: ignore[return-value]
        firmware_mode=firmware_mode, uefi_flag=uefi_flag
    )


def _score_bios(signals: FirmwareSignals) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if signals.boot_mode == "bios":
        score += 40
        reasons.append("offline_boot_mode=bios")
    if signals.windows_bcd_bios and not signals.windows_bcd_uefi:
        score += 35
        reasons.append("windows_bcd=bios")
    if signals.partition_scheme == "mbr":
        score += 25
        reasons.append("partition_table=mbr")
    if signals.has_efi_partition is False:
        score += 20
        reasons.append("no_efi_partition")
    if signals.hyperv_generation == 1:
        score += 15
        reasons.append("hyperv_gen1")
    if signals.ovf_firmware == "bios":
        score += 15
        reasons.append("ovf_firmware=bios")
    return score, reasons


def _score_uefi(signals: FirmwareSignals) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if signals.boot_mode == "uefi":
        score += 40
        reasons.append("offline_boot_mode=uefi")
    if signals.windows_bcd_uefi and not signals.windows_bcd_bios:
        score += 35
        reasons.append("windows_bcd=uefi")
    if signals.has_efi_partition is True:
        score += 30
        reasons.append("efi_system_partition")
    if signals.partition_scheme == "gpt":
        score += 20
        reasons.append("partition_table=gpt")
    if signals.hyperv_generation == 2:
        score += 15
        reasons.append("hyperv_gen2")
    if signals.ovf_firmware == "uefi":
        score += 15
        reasons.append("ovf_firmware=uefi")
    return score, reasons


def resolve_firmware(
    *,
    user_mode: UserFirmwareMode = "auto",
    signals: FirmwareSignals | None = None,
) -> FirmwareResolution:
    """
    Choose BIOS or UEFI for deploy.

    ``user_mode``:
      - ``auto``: score offline/provider signals (default)
      - ``bios`` / ``uefi``: explicit operator override
    """
    sig = signals or FirmwareSignals()
    signal_map = {
        "boot_mode": sig.boot_mode,
        "partition_scheme": sig.partition_scheme,
        "has_efi_partition": sig.has_efi_partition,
        "windows_bcd_bios": sig.windows_bcd_bios,
        "windows_bcd_uefi": sig.windows_bcd_uefi,
        "hyperv_generation": sig.hyperv_generation,
        "ovf_firmware": sig.ovf_firmware,
        "is_windows": sig.is_windows,
    }

    if user_mode in ("bios", "uefi"):
        alternate: FirmwareMode = "uefi" if user_mode == "bios" else "bios"
        return FirmwareResolution(
            firmware=user_mode,
            user_mode=user_mode,
            source="user_override",
            confidence="high",
            alternate=alternate,
            signals=signal_map,
        )

    bios_score, bios_reasons = _score_bios(sig)
    uefi_score, uefi_reasons = _score_uefi(sig)

    # Dual Windows BCD: partition table breaks the tie.
    if sig.windows_bcd_bios and sig.windows_bcd_uefi:
        if sig.partition_scheme == "mbr" or sig.has_efi_partition is False:
            bios_score += 25
            bios_reasons.append("dual_bcd_prefer_mbr")
        elif sig.partition_scheme == "gpt" or sig.has_efi_partition is True:
            uefi_score += 25
            uefi_reasons.append("dual_bcd_prefer_gpt")

    # MBR disks without an EFI System Partition cannot boot via OVMF.
    if sig.partition_scheme == "mbr" and sig.has_efi_partition is False:
        bios_score += 30
        bios_reasons.append("mbr_no_efi_requires_bios")

    if bios_score == 0 and uefi_score == 0:
        # Safe default: BIOS for Windows legacy/Hyper-V Gen1 style disks.
        default: FirmwareMode = "bios"
        return FirmwareResolution(
            firmware=default,
            user_mode="auto",
            source="default_safe",
            confidence="low",
            alternate="uefi" if default == "bios" else "bios",
            signals=signal_map,
        )

    if uefi_score > bios_score:
        confidence: Confidence = "high" if uefi_score >= 40 else "medium" if uefi_score >= 20 else "low"
        return FirmwareResolution(
            firmware="uefi",
            user_mode="auto",
            source="auto:" + ",".join(uefi_reasons[:4]),
            confidence=confidence,
            alternate="bios",
            signals=signal_map,
        )

    confidence = "high" if bios_score >= 40 else "medium" if bios_score >= 20 else "low"
    return FirmwareResolution(
        firmware="bios",
        user_mode="auto",
        source="auto:" + ",".join(bios_reasons[:4]),
        confidence=confidence,
        alternate="uefi",
        signals=signal_map,
    )


# Serial console patterns indicating wrong firmware choice.
UEFI_BOOT_FAILURE_PATTERNS = (
    "no bootable option or device was found",
    "could not load boot",
    "bdsdxe: failed to load",
    "boot0001",
)
BIOS_BOOT_FAILURE_PATTERNS = (
    "no bootable device",
    "boot failed",
    "disk boot failure",
    "reboot and select proper boot device",
    "no operating system",
)


def serial_indicates_boot_failure(text: str, *, current_uefi: bool) -> bool:
    """Return True when captured serial output suggests firmware/boot mismatch."""
    blob = (text or "").lower()
    if not blob.strip():
        return False
    patterns = UEFI_BOOT_FAILURE_PATTERNS if current_uefi else BIOS_BOOT_FAILURE_PATTERNS
    return any(p in blob for p in patterns)
