# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/converters/extractors/vhd.py
"""VHD/VHDX (Hyper-V) disk image extractor."""
# pylint: disable=duplicate-code
# reason: this module's tar-safety/dedup/qcow2-conversion helpers structurally mirror
# the sibling ami.py/ovf.py/raw.py extractor modules in several places -- coincidental
# per-format similarity, not shared logic; kept independent so each format's extraction
# path can evolve without coupling.

from __future__ import annotations

import contextlib
import os
import subprocess
import tarfile
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from h2kvm.core.constants import SIZE_1_MIB
from h2kvm.core.utils import U

if TYPE_CHECKING:
    import logging

_ALLOWED_MANIFEST_EXTS = {".txt", ".json", ".yaml", ".yml"}


class VHD:  # pylint: disable=too-few-public-methods  # deliberately exposes only extract_vhd_or_tar(); rest is private helpers
    """VHD/VHDX extraction and (optional) QCOW2 conversion, namespaced as static methods."""

    @staticmethod
    def extract_vhd_or_tar(  # pylint: disable=too-many-arguments,too-many-locals  # top-level entry point covers many independent extraction/conversion knobs
        logger: logging.Logger,
        src: Path,
        outdir: Path,
        *,
        # --- Enhancement (non-breaking): optional convert stage right after extract ---
        convert_to_qcow2: bool = False,
        convert_outdir: Path | None = None,
        convert_compress: bool = False,
        convert_compress_level: int | None = None,
        # --- Enhancement: optional host-side debug logging ---
        log_virt_filesystems: bool = False,
        # --- Safety rails (non-breaking) ---
        max_members: int | None = None,
        max_total_bytes: int | None = None,
        skip_special: bool = True,
        preserve_permissions: bool = True,
        # --- Extraction policy ---
        extract_all: bool = False,
        include_manifests: bool = True,
        overwrite: bool = False,
        rename_on_collision: bool = False,
        # --- Optional timestamp preservation (off by default) ---
        preserve_timestamps: bool = False,
    ) -> list[Path]:
        """
        Accepts either:
          - a plain .vhd / .vhdx
          - a tar/tar.gz/tgz/tar.xz containing .vhd/.vhdx file(s)

        Defaults to a "safe" extraction policy:
          - Extract ONLY .vhd/.vhdx (+ optional small manifest-like files)
          - Skip special tar members (symlinks/hardlinks/devices/FIFOs)
          - Block path traversal / absolute paths / NUL bytes
          - Optional max_members / max_total_bytes safety rails

        Returns:
          - extracted VHD/VHDX paths (if no conversion), OR
          - converted .qcow2 paths (if convert_to_qcow2=True)
        """
        src = Path(src)
        outdir = Path(outdir)
        U.ensure_dir(outdir)

        if not src.exists():
            U.die(logger, f"Source not found: {src}", 1)
        if not src.is_file():
            U.die(logger, f"Source is not a file: {src}", 1)

        # Case A: direct VHD/VHDX
        if VHD._looks_like_vhd(src):
            logger.info(f"VHD: {src}")
            vhds = [src.expanduser().resolve()]
            # Replay dirty VHDX log if present (Hyper-V exports often have uncommitted logs)
            for vhd in vhds:
                if vhd.suffix.lower() == ".vhdx":
                    VHD._replay_vhdx_log(logger, vhd)
            if log_virt_filesystems:
                VHD._log_virt_filesystems(logger, vhds[0])

            if convert_to_qcow2:
                out_conv = Path(convert_outdir) if convert_outdir else (outdir / "qcow2")
                U.ensure_dir(out_conv)
                logger.info(f"QCOW2 outdir: {out_conv}")
                return VHD._convert_disks_to_qcow2(
                    logger,
                    vhds,
                    out_conv,
                    compress=convert_compress,
                    compress_level=convert_compress_level,
                    log_virt_filesystems=log_virt_filesystems,
                )
            return vhds

        # Case B: tarball
        if VHD._looks_like_tar(src):
            return VHD._extract_vhd_tar(
                logger,
                src,
                outdir,
                convert_to_qcow2=convert_to_qcow2,
                convert_outdir=convert_outdir,
                convert_compress=convert_compress,
                convert_compress_level=convert_compress_level,
                log_virt_filesystems=log_virt_filesystems,
                max_members=max_members,
                max_total_bytes=max_total_bytes,
                skip_special=skip_special,
                preserve_permissions=preserve_permissions,
                extract_all=extract_all,
                include_manifests=include_manifests,
                overwrite=overwrite,
                rename_on_collision=rename_on_collision,
                preserve_timestamps=preserve_timestamps,
            )

        # Unknown extension: try tar open anyway; if it fails, error nicely.
        try:
            with tarfile.open(src, mode="r:*"):
                pass
            return VHD._extract_vhd_tar(
                logger,
                src,
                outdir,
                convert_to_qcow2=convert_to_qcow2,
                convert_outdir=convert_outdir,
                convert_compress=convert_compress,
                convert_compress_level=convert_compress_level,
                log_virt_filesystems=log_virt_filesystems,
                max_members=max_members,
                max_total_bytes=max_total_bytes,
                skip_special=skip_special,
                preserve_permissions=preserve_permissions,
                extract_all=extract_all,
                include_manifests=include_manifests,
                overwrite=overwrite,
                rename_on_collision=rename_on_collision,
                preserve_timestamps=preserve_timestamps,
            )
        except Exception:
            U.die(logger, f"Unsupported source type (expected .vhd/.vhdx or tarball): {src}", 1)
            raise  # unreachable

    @staticmethod
    def _extract_vhd_tar(  # pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements  # single-pass safe tar extraction covers many independent policy knobs
        logger: logging.Logger,
        vhd_tar: Path,
        outdir: Path,
        *,
        convert_to_qcow2: bool = False,
        convert_outdir: Path | None = None,
        convert_compress: bool = False,
        convert_compress_level: int | None = None,
        log_virt_filesystems: bool = False,
        max_members: int | None = None,
        max_total_bytes: int | None = None,
        skip_special: bool = True,
        preserve_permissions: bool = True,
        extract_all: bool = False,
        include_manifests: bool = True,
        overwrite: bool = False,
        rename_on_collision: bool = False,
        preserve_timestamps: bool = False,
    ) -> list[Path]:
        U.banner(logger, "Extract VHD tarball")
        logger.info(f"VHD tarball: {vhd_tar}")

        outdir = Path(outdir)
        U.ensure_dir(outdir)

        # UX: summarize policy up front
        policy = "all" if extract_all else ("vhd+manifests" if include_manifests else "vhd-only")
        logger.info(
            "Extract policy: "
            f"policy={policy}, skip_special={skip_special}, "
            f"overwrite={overwrite}, rename_on_collision={rename_on_collision}, "
            f"preserve_permissions={preserve_permissions}, preserve_timestamps={preserve_timestamps}, "
            f"max_members={max_members}, max_total_bytes={max_total_bytes}"
        )
        if extract_all and not skip_special:
            logger.warning(
                "Unsafe extraction configuration: extract_all=True and skip_special=False. "
                "This may extract symlinks/hardlinks/devices/FIFOs from the tarball."
            )
        if not extract_all and include_manifests:
            logger.info(f"Manifest extensions: {', '.join(sorted(_ALLOWED_MANIFEST_EXTS))}")

        # Enforced byte limit during copy (if set)
        bytes_budget = max_total_bytes
        written_total = 0

        extracted_vhds: list[Path] = []
        extracted_other: list[Path] = []

        skipped_by_filter = 0
        skipped_special = 0

        def should_extract(member: tarfile.TarInfo) -> bool:
            """
            Default: only extract .vhd/.vhdx (+ optional manifests).
            If extract_all=True: extract everything (still subject to skip_special and safety checks).
            """
            if extract_all:
                return True

            nm = (member.name or "").strip()
            if not nm:
                return False
            # normalize separators for basename decisions
            nm = nm.replace("\\", "/")
            base = PurePosixPath(nm).name.strip().lower()

            if base.endswith((".vhd", ".vhdx")):
                return True
            if include_manifests:
                ext = Path(base).suffix.lower()
                if ext in _ALLOWED_MANIFEST_EXTS:
                    return True
            return False

        with tarfile.open(vhd_tar, mode="r:*") as tar:
            members = tar.getmembers()

            if max_members is not None and len(members) > max_members:
                U.die(
                    logger, f"Tarball has too many members ({len(members)} > max_members={max_members})", 1
                )

            # Progress total: regular-file bytes for members we intend to extract
            total_bytes = 0
            planned_files = 0
            planned_dirs = 0
            for m in members:
                if not should_extract(m):
                    continue
                if m.isdir():
                    planned_dirs += 1
                    continue
                planned_files += 1
                if m.isreg():
                    with contextlib.suppress(Exception):
                        total_bytes += int(getattr(m, "size", 0) or 0)

            if planned_files == 0 and planned_dirs == 0:
                U.die(
                    logger,
                    "Tarball contains no extractable members under current policy "
                    "(expected .vhd/.vhdx, optionally manifests).",
                    1,
                )

            # Metadata-based check is still useful, but not sufficient; we enforce at write-time too.
            if bytes_budget is not None and total_bytes > bytes_budget:
                U.die(
                    logger,
                    f"Tarball planned payload too large ({total_bytes} bytes > max_total_bytes={bytes_budget})",
                    1,
                )

            logger.info(
                f"Planned extraction: files={planned_files}, dirs={planned_dirs}, "
                f"planned_regular_bytes={total_bytes}"
            )

            extract_count = 0
            for member in members:
                if not should_extract(member):
                    skipped_by_filter += 1
                    continue

                extracted_bytes, extracted_path = VHD._safe_extract_one(
                    logger,
                    tar,
                    member,
                    outdir,
                    skip_special=skip_special,
                    preserve_permissions=preserve_permissions,
                    preserve_timestamps=preserve_timestamps,
                    # byte limit enforcement + overwrite policy:
                    bytes_budget=bytes_budget,
                    written_total=written_total,
                    overwrite=overwrite,
                    rename_on_collision=rename_on_collision,
                )

                written_total += extracted_bytes

                if extracted_path is None and extracted_bytes == 0:
                    skipped_special += 1

                if extracted_path is not None:
                    extract_count += 1
                    if VHD._looks_like_vhd(extracted_path):
                        extracted_vhds.append(extracted_path)
                    else:
                        extracted_other.append(extracted_path)
                    logger.info("Extracted %d/%d: %s", extract_count, planned_files, extracted_path.name)

        # De-dup while preserving order
        def _dedup(paths: list[Path]) -> list[Path]:
            seen: set[str] = set()
            out: list[Path] = []
            for p in paths:
                s = str(p)
                if s not in seen:
                    out.append(p)
                    seen.add(s)
            return out

        uniq_vhds = _dedup(extracted_vhds)
        uniq_other = _dedup(extracted_other)

        if not uniq_vhds:
            U.die(logger, "No .vhd/.vhdx found inside tarball after extraction.", 1)

        # UX: summary
        logger.info(
            "Extraction summary: "
            f"extracted_vhds={len(uniq_vhds)}, extracted_other={len(uniq_other)}, "
            f"skipped_by_filter={skipped_by_filter}, skipped_special={skipped_special}, "
            f"written_total_bytes={written_total}"
        )
        logger.info(f"Output directory: {outdir.resolve()}")

        logger.info("VHD(s) extracted:")
        for d in uniq_vhds:
            logger.info(f" - {d}")

        if uniq_other:
            logger.info("Other extracted files:")
            for p in uniq_other[:50]:
                logger.info(f" - {p}")
            if len(uniq_other) > 50:
                logger.info(f" - ... ({len(uniq_other) - 50} more)")

        # Replay dirty VHDX logs if present
        for d in uniq_vhds:
            if d.suffix.lower() == ".vhdx":
                VHD._replay_vhdx_log(logger, d)

        if log_virt_filesystems:
            for d in uniq_vhds:
                if d.exists():
                    VHD._log_virt_filesystems(logger, d)

        if convert_to_qcow2:
            out_conv = Path(convert_outdir) if convert_outdir else (outdir / "qcow2")
            U.ensure_dir(out_conv)
            logger.info(f"QCOW2 outdir: {out_conv}")
            return VHD._convert_disks_to_qcow2(
                logger,
                uniq_vhds,
                out_conv,
                compress=convert_compress,
                compress_level=convert_compress_level,
                log_virt_filesystems=log_virt_filesystems,
            )

        return uniq_vhds

    @staticmethod
    def _convert_disks_to_qcow2(  # pylint: disable=too-many-arguments,too-many-locals  # per-disk conversion loop covers several independent options
        logger: logging.Logger,
        disks: list[Path],
        outdir: Path,
        *,
        compress: bool = False,
        compress_level: int | None = None,
        log_virt_filesystems: bool = False,
    ) -> list[Path]:
        try:
            # Lazy import: keep vhd.py importable even if the converter module fails,
            # and give a friendly error only when conversion is actually requested.
            # pylint: disable-next=import-outside-toplevel
            from h2kvm.converters.qemu.converter import Convert  # type: ignore
        except Exception as e:
            U.die(logger, f"QCOW2 conversion requested but Convert could not be imported: {e}", 1)
            raise

        U.banner(logger, "Convert extracted VHD(s) to QCOW2")
        U.ensure_dir(outdir)

        outputs: list[Path] = []
        for idx, disk in enumerate(disks, 1):
            if not disk.exists():
                logger.warning(f"Skipping missing disk: {disk}")
                continue

            if log_virt_filesystems:
                VHD._log_virt_filesystems(logger, disk)

            out = (outdir / f"{disk.stem}.qcow2").expanduser().resolve()

            last_bucket = {"b": -1}

            # Default-arg capture is intentional per-iteration state binding, not a shared mutable default.
            def progress_callback(  # pylint: disable=dangerous-default-value
                progress: float, idx=idx, disk=disk, last_bucket=last_bucket
            ) -> None:
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

            if log_virt_filesystems:
                VHD._log_virt_filesystems(logger, out)

            U.post_disk_tool_barrier(logger, out, settle_s=2.0)

        # De-dup preserving order
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
        return U.log_virt_filesystems_introspection(logger, image)

    @staticmethod
    def _replay_vhdx_log(logger: logging.Logger, vhdx: Path) -> None:
        """Replay dirty VHDX journal log if present.

        Hyper-V exports often produce VHDX files with uncommitted write logs.
        qemu-img refuses to open these read-only. Running ``qemu-img check -r all``
        replays the log and marks the image clean.
        """
        try:
            result = subprocess.run(
                ["qemu-img", "check", "-r", "all", str(vhdx)],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            if result.returncode == 0 and "repaired" in result.stdout.lower():
                logger.info(f"Replayed dirty VHDX log: {vhdx.name}")
                logger.info(result.stdout.strip())
            elif result.returncode != 0 and "log that needs to be replayed" in result.stderr:
                logger.warning(f"VHDX log replay failed for {vhdx.name}: {result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            logger.warning(f"VHDX log replay timed out for {vhdx.name}")
        except FileNotFoundError:
            logger.debug("qemu-img not found, skipping VHDX log replay")

    @staticmethod
    def _looks_like_vhd(p: Path) -> bool:
        s = p.name.lower()
        return s.endswith((".vhd", ".vhdx"))

    @staticmethod
    def _looks_like_tar(p: Path) -> bool:
        s = p.name.lower()
        return s.endswith((".tar", ".tar.gz", ".tgz", ".tar.xz", ".txz"))

    @staticmethod
    def _normalize_tar_name(name: str) -> str:
        """
        Normalize tar member names to a predictable POSIX-ish form.

        - Reject NUL bytes
        - Convert backslashes to slashes.
        - Strip leading "./"
        - Reject empty names.
        - Reject any path segment that is ".." after normalization.
        - Drop "." segments to make paths/logs cleaner.
        """
        nm = (name or "").strip()
        if "\x00" in nm:
            raise RuntimeError(
                "Security: archive contains a file name with null bytes, which is not allowed. "
                "The archive may be malformed or malicious."
            )

        nm = nm.replace("\\", "/")
        while nm.startswith("./"):
            nm = nm[2:]
        if not nm:
            raise RuntimeError(
                "Archive contains a file entry with an empty name. "
                "The archive may be corrupted — try re-downloading or re-exporting from the source."
            )

        # Block absolute paths (posix + windows-ish)
        if nm.startswith(("/", "\\")) or (len(nm) >= 2 and nm[1] == ":" and nm[0].isalpha()):
            raise RuntimeError(
                f"Security: archive contains an absolute path '{name}', which is not allowed. "
                f"The archive may contain a path traversal attempt."
            )

        pp = PurePosixPath(nm)
        clean_parts: list[str] = []
        for part in pp.parts:
            if part in ("", "."):
                continue
            if part == "..":
                raise RuntimeError(
                    f"Security: archive contains path traversal segment '..' in '{name}'. "
                    f"This is blocked to prevent directory escape."
                )
            clean_parts.append(part)

        if not clean_parts:
            raise RuntimeError(
                "Archive contains a file entry that resolves to an empty name after normalization. "
                "The archive may be corrupted — try re-downloading or re-exporting from the source."
            )

        return str(PurePosixPath(*clean_parts))

    @staticmethod
    def _unique_path(path: Path) -> Path:
        """
        Create a unique path by appending ' (N)' before suffix.
        Example: disk.vhd -> disk (1).vhd, disk (2).vhd, ...
        """
        if not path.exists():
            return path
        stem = path.stem
        suf = path.suffix
        parent = path.parent
        for i in range(1, 10_000):
            cand = parent / f"{stem} ({i}){suf}"
            if not cand.exists():
                return cand
        raise RuntimeError(
            f"Could not find a unique filename for '{path.name}' after 10000 attempts. "
            f"The output directory may contain too many files with similar names — try a clean output directory."
        )

    @staticmethod
    def _safe_extract_one(  # pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements  # single safe-extraction path covers many independent security/policy checks
        logger: logging.Logger,
        tar: tarfile.TarFile,
        member: tarfile.TarInfo,
        outdir: Path,
        *,
        skip_special: bool = True,
        preserve_permissions: bool = True,
        preserve_timestamps: bool = False,
        bytes_budget: int | None = None,
        written_total: int = 0,
        overwrite: bool = False,
        rename_on_collision: bool = False,
    ) -> tuple[int, Path | None]:
        """
        Safely extract a single tar member into outdir.

        Policy:
          - Normalize path: '\\' -> '/', strip './', reject '..' segments, reject NUL bytes, drop '.' segments.
          - Block absolute paths + traversal.
          - By default, skip symlinks/hardlinks/devices/FIFOs and anything non-file/non-dir.
          - Extract regular files manually via extractfile() (avoid tar.extract() footguns).
          - Create directories explicitly.
          - Enforce byte budget during copy (if set).
          - Handle collisions: default fail; optional overwrite; optional auto-rename.
          - On any error (budget abort, I/O): delete partially written file.
          - Optional timestamp preservation (mtime).

        Returns:
          (extracted_bytes, extracted_path_or_none)
        """
        outdir = Path(outdir).resolve()

        # Normalize and validate member name
        norm = VHD._normalize_tar_name(member.name or "")
        target_path = (outdir / norm).resolve()

        # Block traversal (defense in depth after normalization)
        if outdir != target_path and outdir not in target_path.parents:
            raise RuntimeError(
                f"Security: extraction path for '{member.name}' would escape the output directory. "
                f"The archive may contain a path traversal attempt."
            )

        # Directories
        if member.isdir():
            target_path.mkdir(parents=True, exist_ok=True)
            if preserve_permissions:
                try:
                    mode = int(member.mode or 0o755) & 0o777
                    mode |= 0o200  # ensure user-write
                    os.chmod(target_path, mode)
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort permission restore, must not abort extraction
                    pass
            if preserve_timestamps:
                try:
                    mt = int(getattr(member, "mtime", 0) or 0)
                    if mt > 0:
                        os.utime(target_path, (mt, mt))
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort timestamp restore, must not abort extraction
                    pass
            return 0, target_path

        # Regular files
        if member.isreg():
            target_path.parent.mkdir(parents=True, exist_ok=True)

            final_path = target_path
            if final_path.exists():
                if rename_on_collision and not overwrite:
                    final_path = VHD._unique_path(final_path)
                elif overwrite:
                    pass
                else:
                    raise RuntimeError(
                        f"File '{final_path.name}' already exists and overwrite is disabled. "
                        f"Use a clean output directory or enable overwrite."
                    )

            f = tar.extractfile(member)
            if f is None:
                raise RuntimeError(
                    f"Failed to read file '{member.name}' from the archive. "
                    f"The archive may be corrupted or truncated."
                )

            extracted = 0
            try:
                with f, open(final_path, "wb") as out_f:
                    while True:
                        chunk = f.read(SIZE_1_MIB)
                        if not chunk:
                            break
                        out_f.write(chunk)
                        extracted += len(chunk)

                        if bytes_budget is not None and (written_total + extracted) > bytes_budget:
                            try:
                                out_f.flush()
                                os.fsync(out_f.fileno())
                            except Exception:  # pylint: disable=broad-exception-caught  # best-effort flush before raising the real budget error
                                pass
                            raise RuntimeError(
                                f"Extraction exceeded max_total_bytes={bytes_budget} while writing {member.name} "
                                f"(written_total={written_total}, this_file={extracted})"
                            )
            except Exception:  # pylint: disable=broad-exception-caught  # any copy failure must trigger partial-file cleanup below
                # Ensure partial file doesn't survive errors
                try:
                    if final_path.exists():
                        final_path.unlink()
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort cleanup, must not mask the original error
                    pass
                raise

            if preserve_permissions:
                try:
                    # files: mask to 666, and ensure user-write so cleanup is possible
                    mode = int(member.mode or 0o644) & 0o666
                    mode |= 0o200
                    os.chmod(final_path, mode)
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort permission restore, must not abort extraction
                    pass

            if preserve_timestamps:
                try:
                    mt = int(getattr(member, "mtime", 0) or 0)
                    if mt > 0:
                        os.utime(final_path, (mt, mt))
                except Exception:  # pylint: disable=broad-exception-caught  # best-effort timestamp restore, must not abort extraction
                    pass

            return extracted, final_path

        # Everything else (symlinks, hardlinks, devices, fifos, etc.)
        if skip_special:
            logger.warning(f"Skipping special tar member: {member.name} (type={member.type!r})")
            return 0, None

        raise RuntimeError(
            f"Refusing to extract unsupported tar member: {member.name} (type={member.type!r})"
        )
