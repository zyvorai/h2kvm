# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/converters/extractors/ovf.py
"""OVF (Open Virtualization Format) package extractor."""
# pylint: disable=duplicate-code
# reason: this module's tar-safety/dedup/qcow2-conversion helpers structurally mirror
# the sibling ami.py/raw.py/vhd.py extractor modules in several places -- coincidental
# per-format similarity, not shared logic; kept independent so each format's extraction
# path can evolve without coupling.

from __future__ import annotations

import hashlib
import os
import re
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from h2kvm.core.constants import SIZE_1_MIB
from h2kvm.core.utils import U

if TYPE_CHECKING:
    import logging


class OVF:
    """OVF/OVA package extraction, XML parsing, and hardware-metadata helpers."""

    last_firmware: str = "bios"
    last_hardware: dict[str, Any] = {}  # memory_mib, vcpus, nic_count, secure_boot, os_type

    # Extraction with many optional safety rails and an optional post-extract conversion stage.
    @staticmethod
    def extract_ova(  # pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements
        logger: logging.Logger,
        ova: Path,
        outdir: Path,
        *,
        # --- Enhancement (non-breaking): optional convert stage right after extract ---
        convert_to_qcow2: bool = False,
        convert_outdir: Path | None = None,
        convert_compress: bool = False,
        convert_compress_level: int | None = None,
        # --- Enhancement: optional host-side debug logging ---
        log_virt_filesystems: bool = False,
        # --- Safety rails (optional; defaults keep behavior permissive) ---
        skip_special: bool = True,  # skip symlinks/hardlinks/devices/fifos
        max_members: int | None = None,
        max_total_bytes: int | None = None,
        max_member_bytes: int | None = None,
        max_files: int | None = None,  # regular files only
    ) -> list[Path]:
        """
        Extract an OVA (tar) into outdir, then parse OVF(s) inside and return referenced disk paths.

        Enhancements (non-breaking):
          - Optional conversion to QCOW2 immediately after extraction (convert_to_qcow2=True)
          - Optional "virt-filesystems -a ..." logging for each disk

        Safety improvements:
          - Strong safe extraction (no tar.extract for files; blocks traversal; skips links/devices by default)
          - Optional limits to reduce tar-bomb risk (max_members / max_total_bytes / max_member_bytes / max_files)
          - OVF href safe-join (blocks ../ escapes from OVF metadata)

        Returns:
            List[Path]: Disk file paths (in outdir) referenced by the OVF
                        (or converted qcow2 outputs if enabled).
        """
        U.banner(logger, "Extract OVA")
        ova = Path(ova)
        outdir = Path(outdir)
        U.ensure_dir(outdir)

        if not ova.exists():
            U.die(logger, f"OVA not found: {ova}", 1)
        if not ova.is_file():
            U.die(logger, f"OVA is not a file: {ova}", 1)

        logger.info(f"OVA: {ova}")

        extracted_files = 0
        skipped_special_count = 0
        skipped_other = 0
        blocked = 0
        regular_file_count = 0

        with tarfile.open(ova, mode="r:*") as tar:
            members = tar.getmembers()

            if max_members is not None and len(members) > max_members:
                U.die(
                    logger,
                    f"OVA contains {len(members)} members which exceeds max_members={max_members}",
                    1,
                )

            # Total bytes for progress (regular files only; directories/specials don't count)
            total_bytes = 0
            for m in members:
                try:
                    if m.isreg():
                        total_bytes += int(getattr(m, "size", 0) or 0)
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort size tally for a progress guard; a bad member must not abort extraction
                    pass

            if max_total_bytes is not None and total_bytes > max_total_bytes:
                U.die(
                    logger,
                    f"OVA total regular-file size {total_bytes} exceeds max_total_bytes={max_total_bytes}",
                    1,
                )

            for member in members:
                wrote = 0  # IMPORTANT: avoid UnboundLocalError when exceptions happen

                # File-count DoS guard (regular files only)
                if member.isreg():
                    regular_file_count += 1
                    if max_files is not None and regular_file_count > max_files:
                        U.die(
                            logger,
                            f"OVA exceeds max_files={max_files} (regular files seen: {regular_file_count})",
                            1,
                        )

                try:
                    wrote, status = OVF._safe_extract_one(
                        tar,
                        member,
                        outdir,
                        skip_special=skip_special,
                        max_member_bytes=max_member_bytes,
                    )
                    if status == "extracted":
                        extracted_files += 1
                        logger.info("Extracted %d: %s (%d bytes)", extracted_files, member.name, wrote)
                    elif status == "skipped_special":
                        skipped_special_count += 1
                    elif status == "skipped_other":
                        skipped_other += 1
                except Exception as e:  # pylint: disable=broad-exception-caught  # try each tar member, log failure, continue extracting the rest
                    blocked += 1
                    logger.exception(f"Blocked/failed extracting tar member {member.name!r}: {e}")

        if skipped_special_count:
            logger.warning(
                f"Security: skipped {skipped_special_count} special tar members (links/devices/fifos)"
            )
        if blocked:
            logger.warning(
                f"Security: {blocked} tar members failed safety checks or extraction (see errors above)"
            )

        # Validate checksums from .mf (manifest) files if present
        mf_files = sorted(outdir.glob("*.mf"))
        for mf_file in mf_files:
            OVF._validate_manifest(logger, mf_file, outdir)

        ovfs = sorted(outdir.glob("*.ovf"))
        if not ovfs:
            U.die(logger, "No OVF found inside OVA.", 1)

        # Many OVAs have one OVF; if multiple, parse them all and union disk references.
        disks: list[Path] = []
        for ovf in ovfs:
            disks.extend(
                OVF.extract_ovf(
                    logger,
                    ovf,
                    outdir,
                    log_virt_filesystems=log_virt_filesystems,
                )
            )

        # De-dup while preserving order
        seen: set[Path] = set()
        uniq: list[Path] = []
        for d in disks:
            if d not in seen:
                uniq.append(d)
                seen.add(d)

        # Validate existence and warn (don’t hard-fail; OVFs can reference missing disks in broken exports)
        missing = [d for d in uniq if not d.exists()]
        if missing:
            logger.warning("Some OVF-referenced disks were not found after extraction:")
            for m in missing:
                logger.warning(f" - {m}")
            uniq = [d for d in uniq if d.exists()]
            if not uniq:
                U.die(logger, "OVF referenced disks but none were found on disk after extraction.", 1)

        # Optional conversion
        if convert_to_qcow2:
            out_conv = Path(convert_outdir) if convert_outdir else (outdir / "qcow2")
            U.ensure_dir(out_conv)
            return OVF._convert_disks_to_qcow2(
                logger,
                uniq,
                out_conv,
                compress=convert_compress,
                compress_level=convert_compress_level,
                log_virt_filesystems=log_virt_filesystems,
            )

        return uniq

    # Parses OVF descriptor, handles firmware/hardware detection, and multiple safety rails.
    @staticmethod
    def extract_ovf(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        logger: logging.Logger,
        ovf: Path,
        outdir: Path,
        *,
        log_virt_filesystems: bool = False,
    ) -> list[Path]:
        """
        Parse an OVF file and return disk paths referenced via <File ... ovf:href="..."> used by
        <Disk ovf:fileRef="...">.

        Safety improvement:
          - OVF href safe-join (blocks ../ escapes from OVF metadata)
          - Prefer defusedxml if available (mitigates XML entity expansion DoS)
        """
        U.banner(logger, "Parse OVF")
        ovf = Path(ovf)
        outdir = Path(outdir)

        if not ovf.exists():
            U.die(logger, f"OVF not found: {ovf}", 1)

        logger.info(f"OVF: {ovf}")

        # Prefer defusedxml if installed
        try:
            # pylint: disable-next=import-outside-toplevel  # defusedxml is an optional hardening dependency; fall back to stdlib ET if absent
            from defusedxml.ElementTree import parse as safe_parse  # type: ignore
        except ImportError:
            safe_parse = None

        try:
            tree = safe_parse(ovf) if safe_parse else ET.parse(ovf)
        except ET.ParseError as e:
            U.die(
                logger,
                f"Failed to parse OVF XML '{ovf.name}': {e}\n"
                "    The OVF file contains invalid XML. The OVA may be corrupted or truncated.\n"
                "    Try re-downloading the OVA from the source hypervisor.",
                1,
            )
        # pylint: disable-next=broad-exception-caught  # defusedxml/OSError both funnel to the same die() path
        except Exception as e:
            U.die(
                logger,
                f"Failed to read OVF file '{ovf}': {e}\n    Verify the file exists and is readable.",
                1,
            )

        root = tree.getroot()

        # Try to detect OVF namespace dynamically, fallback to common one.
        ns_uri = None
        if root.tag.startswith("{") and "}" in root.tag:
            ns_uri = root.tag.split("}", 1)[0][1:]
        if not ns_uri:
            ns_uri = "http://schemas.dmtf.org/ovf/envelope/1"

        ns = {"ovf": ns_uri}

        # Build fileRef -> href map from <File ovf:id="..." ovf:href="...">
        file_map: dict[str, str] = {}
        for f in root.findall(".//ovf:File", ns):
            fid = f.get(f"{{{ns_uri}}}id") or f.get("ovf:id") or f.get("id")
            href = f.get(f"{{{ns_uri}}}href") or f.get("ovf:href") or f.get("href")
            if fid and href:
                file_map[fid] = href

        # Detect firmware type (BIOS vs UEFI) from OVF metadata
        firmware = OVF._detect_firmware(logger, root)
        OVF.last_firmware = firmware
        logger.info(f"Firmware (from OVF): {firmware}")

        # Extract hardware resources (memory, CPU, NIC count, secure boot)
        OVF.last_hardware = OVF._parse_hardware(logger, root)
        if OVF.last_hardware:
            hw = OVF.last_hardware
            parts = []
            if hw.get("memory_mib"):
                parts.append(f"memory={hw['memory_mib']}MiB")
            if hw.get("vcpus"):
                parts.append(f"vcpus={hw['vcpus']}")
            if hw.get("nic_count", 1) > 1:
                parts.append(f"nics={hw['nic_count']}")
            if hw.get("secure_boot"):
                parts.append("secure_boot=yes")
            if hw.get("os_type"):
                parts.append(f"os={hw['os_type']}")
            if parts:
                logger.info("Hardware (from OVF): %s", ", ".join(parts))

        disks: list[Path] = []
        for disk in root.findall(".//ovf:Disk", ns):
            file_id = disk.get(f"{{{ns_uri}}}fileRef") or disk.get("ovf:fileRef") or disk.get("fileRef")
            if not file_id:
                continue

            href = file_map.get(file_id)
            if not href:
                logger.warning(
                    f"OVF disk references fileRef={file_id} but no matching <File> entry was found"
                )
                continue

            try:
                disks.append(OVF._safe_out_path(outdir, href))
            except ValueError as e:
                logger.warning(f"Security: skipping unsafe OVF href={href!r} (fileRef={file_id}): {e}")

        if not disks:
            U.die(logger, "No disks found in OVF.", 1)

        logger.info("Disks referenced by OVF:")
        for d in disks:
            logger.info(f" - {d}")

        # Optional: log host-side disk layout for each disk that exists
        if log_virt_filesystems:
            for d in disks:
                if d.exists():
                    OVF._log_virt_filesystems(logger, d)

        return disks

    @staticmethod
    def _convert_disks_to_qcow2(  # pylint: disable=too-many-arguments,too-many-locals
        logger: logging.Logger,
        disks: list[Path],
        outdir: Path,
        *,
        compress: bool = False,
        compress_level: int | None = None,
        log_virt_filesystems: bool = False,
    ) -> list[Path]:
        """
        Convert extracted disks to qcow2 outputs. Keeps order and de-dups.
        Uses the project Convert wrapper if available.
        """
        try:
            # pylint: disable-next=import-outside-toplevel  # keeps the qemu converter (and its deps) optional for callers that only extract
            from h2kvm.converters.qemu.converter import Convert  # type: ignore
        except ImportError as e:
            U.die(logger, f"QCOW2 conversion requested but Convert could not be imported: {e}", 1)
            raise  # unreachable

        U.banner(logger, "Convert extracted disks to QCOW2")
        U.ensure_dir(outdir)

        outputs: list[Path] = []
        for idx, disk in enumerate(disks, 1):
            if not disk.exists():
                logger.warning(f"Skipping missing disk: {disk}")
                continue

            if log_virt_filesystems:
                OVF._log_virt_filesystems(logger, disk)

            # Name outputs deterministically
            stem = disk.name
            if stem.lower().endswith(".vmdk"):
                stem = stem[:-5]
            out = (outdir / f"{stem}.qcow2").expanduser().resolve()

            last_bucket = {"b": -1}

            # pylint: disable-next=dangerous-default-value  # intentional: binds this iteration's fresh dict, not a shared literal default
            def progress_callback(progress: float, idx=idx, disk=disk, last_bucket=last_bucket) -> None:
                b = int(progress * 20)  # 0..20
                if b != last_bucket["b"]:
                    last_bucket["b"] = b
                    if progress < 1.0:
                        logger.info(f"QCOW2 convert [{idx}/{len(disks)}] {disk.name}: {progress:.1%}")
                    else:
                        logger.info(f"QCOW2 convert [{idx}/{len(disks)}] {disk.name}: complete")

            logger.info(
                f"Converting [{idx}/{len(disks)}]: {disk} -> {out} "
                f"(compress={compress}, level={compress_level})"
            )

            Convert.convert_image_with_progress(
                logger,
                disk,
                out,
                out_format="qcow2",
                compress=compress,
                compress_level=compress_level,
                progress_callback=progress_callback,
            )
            Convert.validate(logger, out)
            outputs.append(out)

        # De-dup while preserving order
        seen: set[str] = set()
        uniq: list[Path] = []
        for p in outputs:
            s = str(p)
            if s not in seen:
                uniq.append(p)
                seen.add(s)

        if not uniq:
            U.die(logger, "QCOW2 conversion produced no outputs.", 1)

        logger.info("QCOW2 outputs:")
        for p in uniq:
            logger.info(f" - {p}")
        return uniq

    @staticmethod
    def _log_virt_filesystems(logger: logging.Logger, image: Path) -> dict[str, Any]:
        """Host-side introspection via ``virt-filesystems`` (libguestfs-tools)."""
        return U.log_virt_filesystems_introspection(logger, image, timeout=60)

    # Safe path helpers

    @staticmethod
    def _clean_posix_relpath(name: str) -> PurePosixPath:
        """
        Normalize a tar/OVF path to a safe relative POSIX path:
          - converts backslashes to slashes
          - strips ALL leading '/' (no absolute paths)
          - drops '.' segments
          - rejects '..' segments
          - rejects empty results
        """
        raw = (name or "").replace("\\", "/")

        # Strip all leading slashes explicitly (clear intent)
        raw = raw.lstrip("/")

        p = PurePosixPath(raw)

        clean_parts: list[str] = []
        for part in p.parts:
            if part in ("", "."):
                continue
            if part == "..":
                raise ValueError(
                    f"Security: path traversal segment '..' detected in '{name}'. "
                    f"The OVA/OVF archive may be malformed."
                )
            clean_parts.append(part)

        if not clean_parts:
            raise ValueError(
                f"OVA/OVF archive contains a file entry with an empty or invalid name: {name!r}. "
                f"The archive may be corrupted."
            )

        return PurePosixPath(*clean_parts)

    @staticmethod
    def _assert_no_symlink_parents(outdir_r: Path, target: Path) -> None:
        """
        Hardening: ensure no path component *within outdir* is a symlink.
        This mitigates attacks where an adversary pre-creates symlinks inside outdir.
        """
        try:
            rel = target.relative_to(outdir_r)
        except Exception:
            raise ValueError(
                f"Security: extraction target '{target}' is outside the output directory. "
                f"The archive may contain a path traversal attempt."
            ) from None

        cur = outdir_r
        for part in rel.parts[:-1]:  # parent components only
            cur = cur / part
            # If it exists and is a symlink -> reject
            try:
                if cur.exists() and cur.is_symlink():
                    raise ValueError(
                        f"Security: refusing to follow symlink at '{cur}' — "
                        f"this prevents potential path traversal during extraction."
                    )
            except OSError:
                # If we can't stat, treat as suspicious
                raise ValueError(
                    f"Security: cannot verify path component '{cur}' — "
                    f"treating as suspicious. Check output directory permissions."
                ) from None

    @staticmethod
    def _safe_out_path(outdir: Path, rel: str) -> Path:
        """
        Safe-join outdir with a possibly-untrusted relative path (tar member name or OVF href).
        """
        outdir_r = Path(outdir).resolve()
        pp = OVF._clean_posix_relpath(rel)
        target = (outdir_r / Path(*pp.parts)).resolve()

        if target != outdir_r and outdir_r not in target.parents:
            raise ValueError(
                f"Security: path '{rel}' would escape the output directory during extraction. "
                f"The archive may contain a path traversal attempt."
            )

        # Additional hardening: prevent symlink parent hops
        OVF._assert_no_symlink_parents(outdir_r, target)

        return target

    # Firmware detection from OVF metadata

    @staticmethod
    def _detect_firmware(  # pylint: disable=too-many-locals,too-many-branches,too-many-nested-blocks
        logger: logging.Logger, root: ET.Element
    ) -> str:
        """
        Detect firmware type from OVF XML.

        VMware OVF encodes firmware via:
          - <vmw:Config vmw:key="firmware" vmw:value="efi"/>
          - ExtraConfig item with key "firmware" and value "efi"
          - VirtualSystem containing ResourceSubType with "UEFI"
          - <BootType> element containing "efi"

        Returns "uefi" or "bios".
        """
        xml_str = ET.tostring(root, encoding="unicode")
        xml_lower = xml_str.lower()

        # 1. VMware vmw:Config with firmware=efi (most common)
        #    <vmw:Config ovf:required="false" vmw:key="firmware" vmw:value="efi"/>
        for elem in root.iter():
            tag_local = elem.tag.rsplit("}", 1)[-1] if "}" in elem.tag else elem.tag
            if tag_local.lower() == "config":
                for attr_name, attr_val in elem.attrib.items():
                    attr_local = attr_name.rsplit("}", 1)[-1] if "}" in attr_name else attr_name
                    if attr_local.lower() == "key" and attr_val.lower() == "firmware":
                        for vn, vv in elem.attrib.items():
                            vl = vn.rsplit("}", 1)[-1] if "}" in vn else vn
                            if vl.lower() == "value" and "efi" in vv.lower():
                                logger.info("UEFI detected: vmw:Config firmware=efi")
                                return "uefi"

        # 2. ExtraConfig elements (VMware vSphere export)
        for elem in root.iter():
            tag_local = elem.tag.rsplit("}", 1)[-1] if "}" in elem.tag else elem.tag
            if tag_local.lower() == "extraconfig":
                key = ""
                val = ""
                for an, av in elem.attrib.items():
                    al = an.rsplit("}", 1)[-1] if "}" in an else an
                    if al.lower() == "key":
                        key = av.lower()
                    elif al.lower() == "value":
                        val = av.lower()
                if key == "firmware" and "efi" in val:
                    logger.info("UEFI detected: ExtraConfig firmware=efi")
                    return "uefi"

        # 3. ResourceSubType containing UEFI (DMTF OVF standard)
        for elem in root.iter():
            tag_local = elem.tag.rsplit("}", 1)[-1] if "}" in elem.tag else elem.tag
            if tag_local.lower() == "resourcesubtype":
                text = (elem.text or "").lower()
                if "uefi" in text or "efi" in text:
                    logger.info(f"UEFI detected: ResourceSubType={elem.text}")
                    return "uefi"

        # 4. BootType element
        for elem in root.iter():
            tag_local = elem.tag.rsplit("}", 1)[-1] if "}" in elem.tag else elem.tag
            if tag_local.lower() == "boottype":
                text = (elem.text or "").lower()
                if "efi" in text:
                    logger.info(f"UEFI detected: BootType={elem.text}")
                    return "uefi"

        # 5. Broad scan: any attribute or text containing firmware=efi patterns
        if 'firmware" value="efi' in xml_lower or "firmware' value='efi" in xml_lower:
            logger.info("UEFI detected: firmware=efi pattern in OVF XML")
            return "uefi"

        return "bios"

    # Hardware resource parsing from OVF metadata

    @staticmethod
    def _parse_hardware(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        logger: logging.Logger, root: ET.Element
    ) -> dict[str, Any]:
        """
        Extract hardware resources from OVF XML (DMTF CIM ResourceType).

        Single-pass traversal that parses:
          - CPU count (ResourceType=3)
          - Memory in MiB (ResourceType=4, with AllocationUnits normalization)
          - NIC count (ResourceType=10)
          - Secure Boot (VMware bootOptions.efiSecureBootEnabled)
          - Guest OS type hint (OperatingSystemSection vmw:osType)
          - CPU topology (VMware CoresPerSocket)
        """
        hw: dict[str, Any] = {}
        _local = OVF._tag_local

        vcpus = 0
        memory_mib = 0
        nic_count = 0

        for elem in root.iter():
            tag = _local(elem.tag).lower()

            # ResourceType-based hardware items
            if tag == "item":
                res_type = None
                quantity = None
                alloc_units = None
                for child in elem:
                    ctag = _local(child.tag).lower()
                    text = (child.text or "").strip()
                    if ctag == "resourcetype":
                        try:
                            res_type = int(text)
                        except (ValueError, TypeError):
                            pass
                    elif ctag == "virtualquantity":
                        try:
                            quantity = int(text)
                        except (ValueError, TypeError):
                            pass
                    elif ctag == "allocationunits":
                        alloc_units = text.lower()

                if res_type == 3 and quantity:  # Processor
                    vcpus = max(vcpus, quantity)
                elif res_type == 4 and quantity:  # Memory
                    memory_mib = OVF._normalize_memory(quantity, alloc_units)
                elif res_type == 10:  # Ethernet Adapter
                    nic_count += 1

            # CoresPerSocket element (direct)
            elif tag == "corespersocket":
                try:
                    cores = int((elem.text or "").strip())
                    if cores > 0 and vcpus > 0:
                        sockets = max(1, vcpus // cores)
                        hw["cpu_topology"] = f"{sockets}:{cores}:1"
                except (ValueError, TypeError):
                    pass

            # vmw:Config — handles CoresPerSocket, Secure Boot
            elif tag == "config":
                key_val = ""
                value_val = ""
                for an, av in elem.attrib.items():
                    al = an.rsplit("}", 1)[-1] if "}" in an else an
                    if al.lower() == "key":
                        key_val = av.lower()
                    elif al.lower() == "value":
                        value_val = av
                if key_val == "cpuid.corespersocket" and value_val:
                    try:
                        cores = int(value_val)
                        if cores > 0 and vcpus > 0:
                            sockets = max(1, vcpus // cores)
                            hw["cpu_topology"] = f"{sockets}:{cores}:1"
                    except (ValueError, TypeError):
                        pass
                if "secureboot" in key_val and value_val.lower() in ("true", "1", "yes"):
                    hw["secure_boot"] = True
                    logger.info("Secure Boot detected from OVF metadata")

            # Guest OS type hint
            elif tag == "operatingsystemsection":
                for an, av in elem.attrib.items():
                    al = an.rsplit("}", 1)[-1] if "}" in an else an
                    if al.lower() == "ostype" and av:
                        hw["os_type"] = av
                        break
                for child in elem:
                    if _local(child.tag).lower() == "description":
                        desc = (child.text or "").strip()
                        if desc:
                            hw["os_description"] = desc

        if vcpus:
            hw["vcpus"] = vcpus
        if memory_mib:
            hw["memory_mib"] = memory_mib
        hw["nic_count"] = max(nic_count, 1)

        return hw

    @staticmethod
    def _tag_local(tag: str) -> str:
        """Extract local name from a namespaced XML tag."""
        return tag.rsplit("}", 1)[-1] if "}" in tag else tag

    @staticmethod
    def _normalize_memory(  # pylint: disable=too-many-return-statements  # one branch per OVF AllocationUnits variant
        quantity: int, alloc_units: str | None
    ) -> int:
        """Normalize memory quantity to MiB based on AllocationUnits."""
        if not alloc_units:
            # Default: assume MiB (most common in VMware OVF)
            return quantity

        # DMTF standard: "byte * 2^20" = MiB, "byte * 2^30" = GiB, etc.
        m = re.search(r"byte\s*\*\s*2\^(\d+)", alloc_units)
        if m:
            power = int(m.group(1))
            # Convert to MiB (2^20)
            if power >= 20:
                return quantity * (2 ** (power - 20))
            return max(1, quantity // (2 ** (20 - power)))

        # Fallback: check for unit keywords
        if "gib" in alloc_units or "gigabyte" in alloc_units:
            return quantity * 1024
        if "kib" in alloc_units or "kilobyte" in alloc_units:
            return max(1, quantity // 1024)
        if "byte" in alloc_units and "mega" not in alloc_units:
            return max(1, quantity // (1024 * 1024))

        # Default: MiB
        return quantity

    # Manifest checksum validation

    @staticmethod
    def _validate_manifest(  # pylint: disable=too-many-locals,too-many-branches
        logger: logging.Logger,
        mf_path: Path,
        outdir: Path,
    ) -> None:
        """
        Parse an OVA .mf (manifest) file and validate checksums.

        Manifest format (one entry per line):
            SHA256(disk.vmdk)= abcdef1234...
            SHA1(file.ovf)= 9876...
        """
        logger.info(f"Validating OVA manifest: {mf_path.name}")
        # Pattern: ALGO(filename)= hexdigest
        pattern = re.compile(r"^(SHA256|SHA1|SHA512|MD5)\((.+?)\)\s*=\s*([0-9a-fA-F]+)\s*$")
        algo_map = {
            "SHA256": "sha256",
            "SHA1": "sha1",
            "SHA512": "sha512",
            "MD5": "md5",
        }

        checked = 0
        failed = 0
        mismatched_files: list[str] = []

        for line in mf_path.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue

            m = pattern.match(line)
            if not m:
                continue

            algo_name, filename, expected_hex = m.group(1), m.group(2), m.group(3).lower()

            # Reject path traversal in manifest filenames
            if ".." in filename or filename.startswith(("/", "\\")):
                logger.warning(f"  Security: skipping manifest entry with unsafe filename: {filename!r}")
                continue

            filepath = outdir / filename

            if not filepath.exists():
                logger.warning(f"  Manifest references {filename} but file not found, skipping")
                continue

            hash_name = algo_map.get(algo_name)
            if not hash_name:
                continue

            logger.info(f"  Checking {algo_name}({filename})...")
            h = hashlib.new(hash_name)
            with open(filepath, "rb") as f:
                while True:
                    chunk = f.read(8 * 1024 * 1024)  # 8 MiB chunks
                    if not chunk:
                        break
                    h.update(chunk)

            actual_hex = h.hexdigest().lower()
            checked += 1

            if actual_hex != expected_hex:
                failed += 1
                mismatched_files.append(filename)
                logger.error(
                    f"  CHECKSUM MISMATCH: {filename}\n"
                    f"    expected: {expected_hex}\n"
                    f"    actual:   {actual_hex}"
                )
            else:
                logger.info(f"  {algo_name}({filename}) OK")

        if checked == 0:
            logger.info("  No checksum entries found in manifest")
        elif failed > 0:
            U.die(
                logger,
                f"OVA manifest validation: {failed}/{checked} checksum(s) FAILED "
                f"({', '.join(mismatched_files)}) — files may be corrupt or tampered",
                1,
            )
        else:
            logger.info(f"OVA manifest validation: {checked}/{checked} checksums OK")

    # Safe extraction

    @staticmethod
    def _safe_extract_one(
        tar: tarfile.TarFile,
        member: tarfile.TarInfo,
        outdir: Path,
        *,
        skip_special: bool = True,
        max_member_bytes: int | None = None,
    ) -> tuple[int, str]:
        """
        Extract a single tar member safely.

        Returns:
            (bytes_written, status)
            status in: extracted | skipped_special | skipped_other
        """
        # Identify special members
        is_special = (
            member.issym()
            or member.islnk()
            or member.ischr()
            or member.isblk()
            or member.isfifo()
            or getattr(member, "isdev", lambda: False)()
        )
        if is_special and skip_special:
            return (0, "skipped_special")

        # We only support dirs + regular files (everything else skipped)
        if member.isdir():
            target_dir = OVF._safe_out_path(outdir, member.name)
            target_dir.mkdir(parents=True, exist_ok=True)
            return (0, "extracted")

        if not member.isreg():
            return (0, "skipped_other")

        # Size safety rail
        size = int(getattr(member, "size", 0) or 0)
        if max_member_bytes is not None and size > max_member_bytes:
            raise ValueError(
                f"Member {member.name!r} size {size} exceeds max_member_bytes={max_member_bytes}"
            )

        target = OVF._safe_out_path(outdir, member.name)
        target.parent.mkdir(parents=True, exist_ok=True)

        src = tar.extractfile(member)
        if src is None:
            return (0, "skipped_other")

        wrote = 0
        tmp_path: Path | None = None
        try:
            # Use a unique temp file in the same directory (avoids collisions; best-effort atomic replace)
            with tempfile.NamedTemporaryFile(
                dir=str(target.parent),
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as tf:
                tmp_path = Path(tf.name)
                while True:
                    chunk = src.read(SIZE_1_MIB)
                    if not chunk:
                        break
                    tf.write(chunk)
                    wrote += len(chunk)

            os.replace(str(tmp_path), str(target))

            # Conservative permissions: we are not honoring tar modes (safer),
            # but ensure it's not accidentally executable/world-writable.
            try:
                if os.name == "posix":
                    os.chmod(target, 0o644)
            except OSError:
                pass

        finally:
            try:
                if tmp_path is not None and tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass

        return (wrote, "extracted")
