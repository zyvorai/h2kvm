# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/converters/extractors/ami.py
# pylint: disable=too-many-lines  # cohesive AMI/tarball extractor: safe-extraction, disk-discovery, and conversion helpers belong together
"""AWS AMI image extractor for EC2 instance imports."""
# pylint: disable=duplicate-code
# reason: this module's tar-safety/dedup/qcow2-conversion helpers structurally mirror
# the sibling ovf.py/raw.py/vhd.py extractor modules in several places -- coincidental
# per-format similarity, not shared logic; kept independent so each format's extraction
# path can evolve without coupling.

from __future__ import annotations

import contextlib
import errno
import hashlib
import json
import os
import shutil
import stat
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hyper2kvm.core.constants import SIZE_1_MIB
from hyper2kvm.core.utils import U

if TYPE_CHECKING:
    import logging


@dataclass
class ExtractManifest:  # pylint: disable=too-many-instance-attributes  # audit/debug manifest data model, one field per tracked extraction facet
    """
    Extraction manifest written to outdir/manifest.json for audit/debug.

    We keep it intentionally simple & JSON-friendly.
    """

    src: str
    outdir: str
    extracted_to: str
    extracted_members: list[dict[str, Any]]
    skipped_members: list[dict[str, Any]]
    nested_extractions: list[dict[str, Any]]
    discovered_disks: list[dict[str, Any]]
    conversions: list[dict[str, Any]]
    notes: list[str]


class AMI:  # pylint: disable=too-few-public-methods  # namespace-style extractor: one public entry point plus many private static helpers
    """
    Generic AMI/cloud-image tarball extractor.

    The term "AMI tarball" is loosely used in the wild: it's often just a tar/tar.gz
    containing a disk image payload (raw/img/qcow2/vmdk/vhd/...), plus metadata.

    This extractor:
      - safely extracts tar/tar.gz/tgz/tar.xz (and OVA, which is tar)
      - discovers disk payloads by extension
      - optionally extracts one level of nested tarballs
      - optionally converts discovered disks to qcow2

    Security posture:
      - blocks path traversal + absolute paths (hard fail)
      - blocks symlinks/hardlinks and special files by default (skip_special)
      - mitigates filesystem symlink-escape:
          * traversal check uses .resolve()
          * parent symlink checks use lstat + resolved containment guard
          * file writes prefer O_NOFOLLOW where available
      - optional "tar bomb" limits:
          * max_members
          * max_total_bytes (declared)
          * max_single_file_bytes (declared + hard enforced while copying)
      - extraction uses tar.extractfile() + manual writes for regular files
      - manifest is written atomically (tmp + replace)
    """

    # Exit codes (structured, stable)
    EX_OK = 0
    EX_NOT_FOUND = 2
    EX_UNSUPPORTED = 3
    EX_UNSAFE_ARCHIVE = 4
    EX_CONVERT_FAILED = 5

    DISK_EXTS = (
        ".raw",
        ".img",
        ".qcow2",
        ".vmdk",
        ".vhd",
        ".vhdx",
        ".vdi",
    )

    # metadata we don't treat as disks (but may exist in bundles)
    META_EXTS = (
        ".json",
        ".mf",
        ".manifest",
        ".ovf",
        ".xml",
        ".txt",
        ".sha256",
        ".sha512",
        ".sig",
        ".asc",
    )

    # things we never want to treat as disks via "large file heuristic"
    ARCHIVE_LIKE_EXTS = (
        ".tar",
        ".ova",
        ".gz",
        ".tgz",
        ".xz",
        ".txz",
        ".zip",
        ".7z",
        ".rar",
        ".zst",
        ".bz2",
        ".tbz2",
    )

    @staticmethod
    def extract_ami_or_tar(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals  # many independent extraction/conversion/security options
        logger: logging.Logger,
        src: Path,
        outdir: Path,
        *,
        convert_to_qcow2: bool = False,
        convert_outdir: Path | None = None,
        convert_compress: bool = False,
        convert_compress_level: int | None = None,
        log_virt_filesystems: bool = False,
        # Enhancement: handle tar-within-tar (one level)
        extract_nested_tar: bool = True,
        # Security/limits
        skip_special: bool = True,
        max_members: int | None = None,
        max_total_bytes: int | None = None,
        max_single_file_bytes: int | None = None,
        # Disk detection
        probe_with_qemu_img: bool = True,
        probe_with_file: bool = True,
        # Output layout
        extract_subdir: str | None = "extracted",
        # Manifest
        write_manifest: bool = True,
    ) -> list[Path]:
        """
        Accepts:
          - tar/tar.gz/tgz/tar.xz/ova containing disk payload(s)

        Returns:
          - extracted disk paths (if no conversion), OR
          - converted qcow2 paths (if convert_to_qcow2=True)
        """
        src = Path(src)
        outdir = Path(outdir)
        U.ensure_dir(outdir)

        if not src.exists():
            U.die(logger, f"Source not found: {src}", AMI.EX_NOT_FOUND)
        if not src.is_file():
            U.die(logger, f"Source is not a file: {src}", AMI.EX_NOT_FOUND)

        # Try tar open; allow "unknown extension" as long as tar can open it.
        try:
            with tarfile.open(src, mode="r:*"):
                pass
        except (tarfile.TarError, OSError, EOFError):
            U.die(logger, f"Unsupported source type (expected tarball): {src}", AMI.EX_UNSUPPORTED)

        return AMI._extract_and_find_disks(
            logger,
            src,
            outdir,
            convert_to_qcow2=convert_to_qcow2,
            convert_outdir=convert_outdir,
            convert_compress=convert_compress,
            convert_compress_level=convert_compress_level,
            log_virt_filesystems=log_virt_filesystems,
            extract_nested_tar=extract_nested_tar,
            skip_special=skip_special,
            max_members=max_members,
            max_total_bytes=max_total_bytes,
            max_single_file_bytes=max_single_file_bytes,
            probe_with_qemu_img=probe_with_qemu_img,
            probe_with_file=probe_with_file,
            extract_subdir=extract_subdir,
            write_manifest=write_manifest,
        )

    # extraction + discovery

    @staticmethod
    def _extract_and_find_disks(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals  # orchestrates extraction, nested-tar handling, disk discovery, and optional conversion
        logger: logging.Logger,
        tar_path: Path,
        outdir: Path,
        *,
        convert_to_qcow2: bool,
        convert_outdir: Path | None,
        convert_compress: bool,
        convert_compress_level: int | None,
        log_virt_filesystems: bool,
        extract_nested_tar: bool,
        skip_special: bool,
        max_members: int | None,
        max_total_bytes: int | None,
        max_single_file_bytes: int | None,
        probe_with_qemu_img: bool,
        probe_with_file: bool,
        extract_subdir: str | None,
        write_manifest: bool,
    ) -> list[Path]:
        U.banner(logger, "Extract AMI/cloud-image tarball")
        logger.info(f"Tarball: {tar_path}")

        extracted_to = outdir / (extract_subdir or "")
        extracted_to = extracted_to if extract_subdir else outdir
        U.ensure_dir(extracted_to)

        manifest = ExtractManifest(
            src=str(tar_path),
            outdir=str(outdir),
            extracted_to=str(extracted_to),
            extracted_members=[],
            skipped_members=[],
            nested_extractions=[],
            discovered_disks=[],
            conversions=[],
            notes=[],
        )
        manifest.notes.append(
            f"Policy: skip_special={skip_special}, max_members={max_members}, "
            f"max_total_bytes={max_total_bytes}, max_single_file_bytes={max_single_file_bytes}, "
            f"extract_nested_tar={extract_nested_tar}"
        )

        try:
            AMI._extract_tar(
                logger,
                tar_path,
                extracted_to,
                manifest,
                skip_special=skip_special,
                max_members=max_members,
                max_total_bytes=max_total_bytes,
                max_single_file_bytes=max_single_file_bytes,
            )
        except RuntimeError as e:
            AMI._maybe_write_manifest(logger, outdir, manifest, write_manifest)
            U.die(logger, f"Unsafe tar archive: {e}", AMI.EX_UNSAFE_ARCHIVE)

        if extract_nested_tar:
            AMI._extract_one_level_nested_tars(
                logger,
                extracted_to,
                manifest,
                skip_special=skip_special,
                max_members=max_members,
                max_total_bytes=max_total_bytes,
                max_single_file_bytes=max_single_file_bytes,
            )

        disks, disk_meta = AMI._find_disk_payloads(
            logger,
            extracted_to,
            probe_with_qemu_img=probe_with_qemu_img,
            probe_with_file=probe_with_file,
        )
        manifest.discovered_disks.extend(disk_meta)

        if not disks:
            hint = AMI._debug_top_level(extracted_to)
            manifest.notes.append(f"No disk payload found. Top-level entries: {hint}")
            AMI._maybe_write_manifest(logger, outdir, manifest, write_manifest)
            U.die(
                logger, f"No disk payload found inside tarball. Top-level entries: {hint}", AMI.EX_NOT_FOUND
            )

        logger.info("Disk payload(s) found (best-first):")
        for d in disks:
            logger.info(f" - {d}")

        if log_virt_filesystems:
            for d in disks:
                if d.exists():
                    AMI._log_virt_filesystems(logger, d)

        if convert_to_qcow2:
            out_conv = Path(convert_outdir) if convert_outdir else (outdir / "qcow2")
            U.ensure_dir(out_conv)
            try:
                outs = AMI._convert_disks_to_qcow2(
                    logger,
                    disks,
                    out_conv,
                    manifest=manifest,
                    compress=convert_compress,
                    compress_level=convert_compress_level,
                    log_virt_filesystems=log_virt_filesystems,
                )
            except SystemExit:
                AMI._maybe_write_manifest(logger, outdir, manifest, write_manifest)
                raise
            except Exception as e:  # pylint: disable=broad-exception-caught  # conversion delegates to an external tool with many possible failure modes
                manifest.notes.append(f"QCOW2 conversion failed: {e}")
                AMI._maybe_write_manifest(logger, outdir, manifest, write_manifest)
                U.die(logger, f"QCOW2 conversion failed: {e}", AMI.EX_CONVERT_FAILED)

            AMI._maybe_write_manifest(logger, outdir, manifest, write_manifest)
            return outs

        AMI._maybe_write_manifest(logger, outdir, manifest, write_manifest)
        return disks

    @staticmethod
    def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding=encoding)
        tmp.replace(path)

    @staticmethod
    def _maybe_write_manifest(
        logger: logging.Logger, outdir: Path, manifest: ExtractManifest, write_manifest: bool
    ) -> None:
        if not write_manifest:
            return
        try:
            p = Path(outdir) / "manifest.json"
            AMI._atomic_write_text(
                p, json.dumps(manifest.__dict__, indent=2, sort_keys=True), encoding="utf-8"
            )
            logger.info(f"Manifest: {p}")
        except (OSError, TypeError, ValueError) as e:
            logger.warning(f"Failed writing manifest.json: {e}")

    @staticmethod
    def _extract_tar(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals  # safe extraction with several independent security/limit options
        logger: logging.Logger,
        tar_path: Path,
        outdir: Path,
        manifest: ExtractManifest,
        *,
        skip_special: bool,
        max_members: int | None,
        max_total_bytes: int | None,
        max_single_file_bytes: int | None,
    ) -> None:
        """
        Safe tar extraction:
          - blocks traversal + absolute paths (hard fail)
          - optionally skips non-regular files/dirs (symlink/hardlink/dev/fifo/etc.)
          - optional safety limits
          - enforces max_single_file_bytes while copying (not just TarInfo.size)
          - uses tar.extractfile() + manual writes (regular files)
        """
        outdir = Path(outdir).resolve()

        with tarfile.open(tar_path, mode="r:*") as tar:
            members = tar.getmembers()

            if max_members is not None and len(members) > max_members:
                raise RuntimeError(f"Too many tar members: {len(members)} > max_members={max_members}")

            # total bytes: count only regular files; directories often have size=0 anyway
            total_bytes = 0
            for m in members:
                if m.isreg():
                    with contextlib.suppress(Exception):
                        total_bytes += int(getattr(m, "size", 0) or 0)

            if max_total_bytes is not None and total_bytes > max_total_bytes:
                raise RuntimeError(
                    f"Tar total bytes too large: {total_bytes} > max_total_bytes={max_total_bytes}"
                )

            manifest.notes.append(f"Tar stats: members={len(members)}, declared_total_bytes={total_bytes}")

            extracted_count = 0
            for member in members:
                ok, info = AMI._safe_extract_one(
                    tar,
                    member,
                    outdir,
                    skip_special=skip_special,
                    max_single_file_bytes=max_single_file_bytes,
                )
                if ok:
                    manifest.extracted_members.append(info)
                    extracted_count += 1
                    logger.info("Extracted %d/%d: %s", extracted_count, len(members), member.name)
                else:
                    manifest.skipped_members.append(info)

    @staticmethod
    def _extract_one_level_nested_tars(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # forwards the same extraction/limit options as _extract_tar
        logger: logging.Logger,
        extracted_to: Path,
        manifest: ExtractManifest,
        *,
        skip_special: bool,
        max_members: int | None,
        max_total_bytes: int | None,
        max_single_file_bytes: int | None,
    ) -> None:
        """
        One-level nested tar extraction:
          - considers tarballs present immediately after top-level extraction
          - ignores any tarballs living under *.extracted/* to avoid “growth loops”
          - extracts each nested tar into <parent>/<stem>.extracted/
        """
        candidates: list[Path] = []
        for p in extracted_to.rglob("*"):
            if not p.is_file():
                continue
            if not AMI._looks_like_tar(p):
                continue
            if any(part.endswith(".extracted") for part in p.parts):
                continue
            candidates.append(p)

        candidates = sorted(candidates)
        if not candidates:
            return

        U.banner(logger, "Extract nested tarball(s)")

        for t in candidates:
            try:
                with tarfile.open(t, mode="r:*"):
                    pass
            except (tarfile.TarError, OSError, EOFError) as e:
                logger.debug(f"Skipping non-tarball candidate {t.name}: {e}")
                continue

            nested_out = t.parent / f"{t.stem}.extracted"
            U.ensure_dir(nested_out)
            logger.info(f"Nested tarball: {t} -> {nested_out}")

            nested_manifest = ExtractManifest(
                src=str(t),
                outdir=str(nested_out),
                extracted_to=str(nested_out),
                extracted_members=[],
                skipped_members=[],
                nested_extractions=[],
                discovered_disks=[],
                conversions=[],
                notes=[],
            )

            try:
                AMI._extract_tar(
                    logger,
                    t,
                    nested_out,
                    nested_manifest,
                    skip_special=skip_special,
                    max_members=max_members,
                    max_total_bytes=max_total_bytes,
                    max_single_file_bytes=max_single_file_bytes,
                )
                manifest.nested_extractions.append(
                    {
                        "tar": str(t),
                        "outdir": str(nested_out),
                        "extracted_members": len(nested_manifest.extracted_members),
                        "skipped_members": len(nested_manifest.skipped_members),
                    }
                )
            except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort nested-tar extraction; one bad nested tar must not abort the others
                logger.warning(f"Failed extracting nested tar {t}: {e}")
                manifest.nested_extractions.append(
                    {"tar": str(t), "outdir": str(nested_out), "error": str(e)}
                )

    # disk discovery

    @staticmethod
    def _find_disk_payloads(  # pylint: disable=too-many-locals,too-many-statements  # multi-stage discovery: extension hits, probing, scoring, and large-file fallback heuristic
        logger: logging.Logger,
        extracted_to: Path,
        *,
        probe_with_qemu_img: bool,
        probe_with_file: bool,
    ) -> tuple[list[Path], list[dict[str, Any]]]:
        """
        Disk discovery strategy:
          1) Extension hits (DISK_EXTS), skipping obvious metadata.
          2) Probe candidates using qemu-img info (best) / file (fallback).
          3) If no extension hits, do a large-file heuristic BUT still prefer probe-success.
        """
        exts = {e.lower() for e in AMI.DISK_EXTS}

        hits: list[Path] = []
        candidates: list[Path] = []

        for p in extracted_to.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() in AMI.META_EXTS:
                continue
            rp = p.resolve()
            candidates.append(rp)
            if p.suffix.lower() in exts:
                hits.append(rp)

        probe_meta: dict[str, dict[str, Any]] = {}
        qemu_ok = probe_with_qemu_img and shutil.which("qemu-img") is not None
        file_ok = probe_with_file and shutil.which("file") is not None

        def maybe_probe(path: Path) -> dict[str, Any]:
            if str(path) in probe_meta:
                return probe_meta[str(path)]
            meta: dict[str, Any] = {"path": str(path)}
            try:
                meta["size_bytes"] = path.stat().st_size
            except OSError:
                meta["size_bytes"] = None

            if qemu_ok:
                try:
                    cp = U.run_cmd(
                        logger, ["qemu-img", "info", "--output=json", str(path)], capture=True, check=False
                    )
                    out = (cp.stdout or "").strip()
                    if out:
                        j = json.loads(out)
                        meta["qemu_img_ok"] = True
                        meta["qemu_img"] = {
                            "format": j.get("format"),
                            "virtual_size": j.get("virtual-size"),
                            "actual_size": j.get("actual-size"),
                            "backing_filename": j.get("backing-filename"),
                        }
                    else:
                        meta["qemu_img_ok"] = False
                except (OSError, ValueError) as e:
                    meta["qemu_img_ok"] = False
                    meta["qemu_img_error"] = str(e)
            else:
                meta["qemu_img_ok"] = False

            if file_ok:
                try:
                    cp = U.run_cmd(logger, ["file", "-b", str(path)], capture=True, check=False)
                    meta["file_desc"] = (cp.stdout or "").strip()
                except OSError as e:
                    meta["file_error"] = str(e)

            probe_meta[str(path)] = meta
            return meta

        def _name_bonus(p: str) -> int:
            n = (Path(p).name or "").lower()
            # VMware often ships descriptor *.vmdk + real payload *-flat.vmdk
            if n.endswith("-flat.vmdk"):
                return 3
            return 0

        def score(meta: dict[str, Any]) -> tuple[int, int, int, int, int]:
            """
            Higher is better.

            1) qemu-img success (1/0)
            2) name bonus (prefer -flat.vmdk)
            3) virtual size
            4) actual file size
            5) small penalty if file says text-ish and qemu-img didn't validate
            """
            q = 1 if meta.get("qemu_img_ok") else 0
            nb = _name_bonus(meta.get("path", ""))

            vs = 0
            try:
                vs = int((meta.get("qemu_img") or {}).get("virtual_size") or 0)
            except (TypeError, ValueError):
                vs = 0

            sz = 0
            try:
                sz = int(meta.get("size_bytes") or 0)
            except (TypeError, ValueError):
                sz = 0

            penalty = 0
            desc = (meta.get("file_desc") or "").lower()
            if not q and desc:
                if "ascii text" in desc or "unicode text" in desc or "json" in desc or "xml" in desc:
                    penalty = 1

            return (q, nb, vs, sz, -penalty)

        if hits:
            uniq_hits = AMI._dedup_paths(hits)
            metas = [maybe_probe(p) for p in uniq_hits]
            metas.sort(key=score, reverse=True)
            chosen = [Path(m["path"]) for m in metas]
            return chosen, metas

        # No extension hits:
        filtered: list[Path] = []
        for p in candidates:
            suf = p.suffix.lower()
            if suf in AMI.ARCHIVE_LIKE_EXTS:
                continue
            filtered.append(p)

        large: list[Path] = []
        for p in filtered:
            try:
                if p.stat().st_size >= 64 * SIZE_1_MIB:
                    large.append(p)
            except OSError:
                continue

        if not large:
            return [], []

        logger.info("No known disk extensions found; using probe + large-file heuristic.")
        uniq_large = AMI._dedup_paths(large)

        metas = [maybe_probe(p) for p in uniq_large]
        metas.sort(key=score, reverse=True)

        chosen = [Path(m["path"]) for m in metas]
        return chosen, metas

    @staticmethod
    def _dedup_paths(paths: list[Path]) -> list[Path]:
        seen: set[str] = set()
        out: list[Path] = []
        for p in paths:
            s = str(p)
            if s not in seen:
                seen.add(s)
                out.append(p)
        return out

    @staticmethod
    def _debug_top_level(outdir: Path) -> str:
        top = sorted(outdir.iterdir(), key=lambda p: p.name)
        names = [p.name + ("/" if p.is_dir() else "") for p in top[:30]]
        return ", ".join(names) or "(none)"

    # conversion + logging

    @staticmethod
    def _make_progress_callback(logger: logging.Logger, idx: int, disk: Path, total: int):
        """Build a qemu-img progress callback bound to one disk conversion.

        Each call gets its own ``last_bucket`` state (rather than a mutable
        default argument on a closure defined inside the conversion loop),
        so progress is logged at most once per 5% bucket without relying on
        loop-variable closures.
        """
        last_bucket = {"b": -1}

        def progress_callback(progress: float) -> None:
            b = int(progress * 20)
            if b != last_bucket["b"]:
                last_bucket["b"] = b
                if progress < 1.0:
                    logger.info(f"QCOW2 convert [{idx}/{total}] {disk.name}: {progress:.1%}")
                else:
                    logger.info(f"QCOW2 convert [{idx}/{total}] {disk.name}: complete")

        return progress_callback

    @staticmethod
    def _convert_disks_to_qcow2(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals  # conversion covers several independent output/compression/logging options
        logger: logging.Logger,
        disks: list[Path],
        outdir: Path,
        *,
        manifest: ExtractManifest,
        compress: bool = False,
        compress_level: int | None = None,
        log_virt_filesystems: bool = False,
    ) -> list[Path]:
        try:
            # Deliberately lazy: keeps extraction-only use of this module from requiring the qemu
            # converter subsystem, and turns any import failure into a graceful EX_CONVERT_FAILED
            # error instead of crashing the whole module at import time.
            from hyper2kvm.converters.qemu.converter import (  # pylint: disable=import-outside-toplevel
                Convert,  # type: ignore
            )
        except Exception as e:
            U.die(
                logger,
                f"QCOW2 conversion requested but Convert could not be imported: {e}",
                AMI.EX_CONVERT_FAILED,
            )
            raise

        U.banner(logger, "Convert extracted disk(s) to QCOW2")
        U.ensure_dir(outdir)

        outputs: list[Path] = []
        for idx, disk in enumerate(disks, 1):
            if not disk.exists():
                logger.warning(f"Skipping missing disk: {disk}")
                manifest.conversions.append({"src": str(disk), "skipped": True, "reason": "missing"})
                continue

            if log_virt_filesystems:
                AMI._log_virt_filesystems(logger, disk)

            out = AMI._unique_qcow2_name(outdir, disk, idx=idx)

            progress_callback = AMI._make_progress_callback(logger, idx, disk, len(disks))

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

            manifest.conversions.append(
                {"src": str(disk), "dst": str(out), "compress": compress, "compress_level": compress_level}
            )

            if log_virt_filesystems:
                AMI._log_virt_filesystems(logger, out)

        uniq = AMI._dedup_paths(outputs)
        if not uniq:
            U.die(logger, "QCOW2 conversion produced no outputs.", AMI.EX_CONVERT_FAILED)

        logger.info("QCOW2 outputs:")
        for p in uniq:
            logger.info(f" - {p}")
        return uniq

    @staticmethod
    def _unique_qcow2_name(outdir: Path, disk: Path, *, idx: int) -> Path:
        """
        Stable-ish naming that avoids collisions:
          disk01-<stem>.qcow2 + short hash of full path if needed.
        """
        outdir = Path(outdir).expanduser().resolve()
        stem = (disk.name if not disk.suffix else disk.stem) or f"disk{idx:02d}"
        base = f"disk{idx:02d}-{stem}"
        out = outdir / f"{base}.qcow2"
        if not out.exists():
            return out

        h = hashlib.sha256(str(disk).encode("utf-8")).hexdigest()[:10]
        return outdir / f"{base}-{h}.qcow2"

    @staticmethod
    def _log_virt_filesystems(logger: logging.Logger, image: Path) -> dict[str, Any]:
        return U.log_virt_filesystems_introspection(logger, image)

    # tar helpers + safe extraction

    @staticmethod
    def _looks_like_tar(p: Path) -> bool:
        s = p.name.lower()
        return s.endswith((".tar", ".ova", ".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar.bz2", ".tbz2"))

    @staticmethod
    def _normalize_tar_name(name: str) -> str:
        n = (name or "").strip()
        n = n.replace("\\", "/")
        while n.startswith("./"):
            n = n[2:]
        return n

    @staticmethod
    def _is_symlink(path: Path) -> bool:
        try:
            st = os.lstat(path)
            return stat.S_ISLNK(st.st_mode)
        except FileNotFoundError:
            return False
        except OSError:
            # if we can't lstat, treat as unsafe in callers that care
            return True

    @staticmethod
    def _has_symlink_in_parents(base_dir: Path, target_dir: Path) -> bool:
        """
        Return True if:
          - target_dir resolves outside base_dir (containment guard), OR
          - any existing directory on the path base_dir -> target_dir is a symlink (lstat-based).

        This mitigates filesystem symlink-escape even when the tar member itself is a regular file.
        """
        base_r = Path(base_dir).resolve()
        target_r = Path(target_dir).resolve()

        # containment guard: if resolution escapes, it's unsafe
        if base_r != target_r and base_r not in target_r.parents:
            return True

        try:
            rel = target_r.relative_to(base_r)
        except ValueError:
            return True

        cur = base_r
        for part in rel.parts:
            cur = cur / part
            # Only check existing components. Missing ones will be created by us (safe).
            try:
                if cur.exists() and AMI._is_symlink(cur):
                    return True
            except OSError:
                return True
        return False

    @staticmethod
    def _open_no_follow_for_write(path: Path) -> Any:
        """
        Best-effort no-follow open for writing.

        - Uses O_NOFOLLOW where available to refuse symlink targets.
        - If filesystem doesn't support O_NOFOLLOW, falls back to regular open,
          but callers MUST have performed lstat-based checks already.
        """
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        nofollow = getattr(os, "O_NOFOLLOW", 0)

        if nofollow:
            try:
                fd = os.open(str(path), flags | nofollow, 0o644)
                return os.fdopen(fd, "wb")
            except OSError as e:
                # ELOOP => symlink encountered
                if e.errno == errno.ELOOP:
                    raise
                # Unsupported on some filesystems/platforms
                if e.errno in (
                    errno.EINVAL,
                    getattr(errno, "ENOTSUP", 95),
                    getattr(errno, "EOPNOTSUPP", 95),
                ):
                    pass
                else:
                    raise

        return open(path, "wb")

    @staticmethod
    def _copy_limited(src_f: Any, dst_f: Any, *, limit_bytes: int | None) -> int:
        """
        Copy bytes from src to dst, enforcing a hard byte limit if provided.

        Returns bytes written.
        """
        buf = SIZE_1_MIB
        written = 0
        while True:
            chunk = src_f.read(buf)
            if not chunk:
                break
            written += len(chunk)
            if limit_bytes is not None and written > limit_bytes:
                raise RuntimeError(
                    f"Tar member exceeded max_single_file_bytes while extracting: {written} > {limit_bytes}"
                )
            dst_f.write(chunk)
        return written

    @staticmethod
    def _safe_extract_one(  # pylint: disable=too-many-branches,too-many-statements  # many independent security checks (traversal, symlinks, size limits, special files)
        tar: tarfile.TarFile,
        member: tarfile.TarInfo,
        outdir: Path,
        *,
        skip_special: bool,
        max_single_file_bytes: int | None,
    ) -> tuple[bool, dict[str, Any]]:
        """
        Returns (extracted_ok, info_dict).

        Policy:
          - Absolute paths and traversal attempts are ALWAYS unsafe (hard fail).
          - If skip_special=True, symlinks/hardlinks/dev/fifo/etc are skipped.
          - If skip_special=False, non-regular/non-dir members hard fail.
          - Oversized members (declared or actual) are ALWAYS unsafe (hard fail).
        """
        outdir = Path(outdir).resolve()

        raw_name = member.name
        name = AMI._normalize_tar_name(raw_name)

        info: dict[str, Any] = {
            "name": raw_name,
            "normalized_name": name,
            "type": AMI._tar_member_type(member),
            "size": int(getattr(member, "size", 0) or 0),
        }

        if not name:
            msg = f"Blocked empty tar member name (raw={raw_name!r})"
            info["reason"] = msg
            raise RuntimeError(msg)

        if Path(name).is_absolute():
            msg = f"Blocked absolute tar path: {raw_name}"
            info["reason"] = msg
            raise RuntimeError(msg)

        # traversal protection (hard fail)
        target_path = (outdir / name).resolve()
        if outdir != target_path and outdir not in target_path.parents:
            msg = f"Blocked unsafe tar path traversal: {raw_name}"
            info["reason"] = msg
            raise RuntimeError(msg)

        # declared single-file limit (hard fail)
        if member.isreg() and max_single_file_bytes is not None:
            sz = int(getattr(member, "size", 0) or 0)
            if sz > max_single_file_bytes:
                msg = f"Tar member too large: {raw_name} size={sz} > max_single_file_bytes={max_single_file_bytes}"
                info["reason"] = msg
                raise RuntimeError(msg)

        # directories: create, but refuse if the directory path itself resolves outside base or hits symlink parents
        if member.isdir():
            if AMI._has_symlink_in_parents(outdir, target_path):
                msg = f"Blocked directory extraction into symlinked/escaped path: {raw_name}"
                info["reason"] = msg
                raise RuntimeError(msg)

            target_path.mkdir(parents=True, exist_ok=True)
            try:
                if member.mode:
                    os.chmod(target_path, member.mode)
            except OSError:
                pass
            return True, info

        # non-regular files
        if not member.isreg():
            msg = f"Blocked non-regular tar member: {raw_name} ({AMI._tar_member_type(member)})"
            info["reason"] = msg
            if skip_special:
                return False, info
            raise RuntimeError(msg)

        # regular files: mitigate filesystem symlink-escape
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # refuse if parents resolve outside base or any existing parent component is a symlink
        if AMI._has_symlink_in_parents(outdir, target_path.parent):
            msg = f"Blocked file extraction into symlinked/escaped parent path: {raw_name}"
            info["reason"] = msg
            raise RuntimeError(msg)

        # refuse if target exists and is a symlink (lstat)
        if target_path.exists() and AMI._is_symlink(target_path):
            msg = f"Blocked file overwrite of symlink target: {raw_name}"
            info["reason"] = msg
            raise RuntimeError(msg)

        f = tar.extractfile(member)
        if f is None:
            msg = f"Failed reading tar member: {raw_name}"
            info["reason"] = msg
            raise RuntimeError(msg)

        with f:
            try:
                with AMI._open_no_follow_for_write(target_path) as out_f:
                    written = AMI._copy_limited(f, out_f, limit_bytes=max_single_file_bytes)
                    info["written_bytes"] = written
            except RuntimeError:
                # remove partial file
                try:
                    if target_path.exists():
                        target_path.unlink()
                except OSError:
                    pass
                raise

        try:
            # Mask permissions to prevent world-writable files from archives
            safe_mode = (member.mode or 0o644) & 0o755
            os.chmod(target_path, safe_mode)
        except OSError:
            pass

        return True, info

    @staticmethod
    def _tar_member_type(m: tarfile.TarInfo) -> str:  # pylint: disable=too-many-return-statements  # simple member-type classification, one return per tar member kind
        if m.isdir():
            return "dir"
        if m.isreg():
            return "file"
        if m.issym():
            return "symlink"
        if m.islnk():
            return "hardlink"
        if m.ischr():
            return "chardev"
        if m.isblk():
            return "blockdev"
        if m.isfifo():
            return "fifo"
        return "other"
