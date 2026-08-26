# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/converters/extractors/raw.py
"""Raw disk image extractor and handler."""
# pylint: disable=duplicate-code
# reason: this module's tar-safety/dedup/qcow2-conversion helpers structurally mirror
# the sibling ami.py/ovf.py/vhd.py extractor modules in several places -- coincidental
# per-format similarity, not shared logic; kept independent so each format's extraction
# path can evolve without coupling.

from __future__ import annotations

import hashlib
import os
import stat
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from hyper2kvm.converters.qemu.converter import Convert
from hyper2kvm.core.constants import SIZE_1_MIB
from hyper2kvm.core.utils import U

if TYPE_CHECKING:
    import logging

_ALLOWED_MANIFEST_EXTS = {".txt", ".json", ".yaml", ".yml"}
_ALLOWED_RAW_EXTS = {".raw", ".img"}


# Shared extraction policy / result (tar-safe core)


@dataclass(frozen=True)
class ExtractPolicy:
    """Options controlling how tar members are extracted and materialized on disk."""

    skip_special: bool = True
    preserve_permissions: bool = True
    preserve_timestamps: bool = False
    overwrite: bool = False
    rename_on_collision: bool = False
    max_total_bytes: int | None = None
    max_manifest_bytes: int = 5 * SIZE_1_MIB  # 5 MiB cap for manifest-like files


@dataclass(frozen=True)
class ExtractResult:
    """Outcome of extracting a single tar member: bytes written, path, and status."""

    extracted_bytes: int
    extracted_path: Path | None
    # stable identity for deterministic naming (normalized tar member name when possible)
    origin_key: str
    # reason for non-extraction when extracted_path is None
    reason: str = ""  # "", "skipped_special", "skipped_manifest_too_large"


def normalize_tar_name(name: str) -> str:
    """Normalize a tar member name to a safe relative posix path, rejecting traversal/absolute paths."""
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


def unique_path(path: Path) -> Path:
    """Return `path` if it doesn't exist, otherwise the first available '(N)'-suffixed variant."""
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


def short_hash(text: str, n: int = 10) -> str:
    """Return the first `n` hex characters of the SHA-256 digest of `text`."""
    return hashlib.sha256(text.encode("utf-8", "strict")).hexdigest()[:n]


def _is_symlink_lstat(p: Path) -> bool:
    try:
        st = os.lstat(p)
    except FileNotFoundError:
        return False
    except OSError as e:
        raise RuntimeError(
            f"Security: filesystem error while checking path '{p}' — cannot verify safety. "
            f"The archive may reference inaccessible or corrupted paths. Detail: {e}"
        ) from e
    return stat.S_ISLNK(st.st_mode)


def ensure_no_symlink_components(base: Path, target_dir: Path) -> None:
    """Raise if `target_dir` escapes `base` or any path component between them is a symlink."""
    base = base.resolve()
    target_dir = target_dir.resolve()

    if base != target_dir and base not in target_dir.parents:
        raise RuntimeError(
            f"Security: extraction path '{target_dir}' is outside the allowed base directory '{base}'. "
            f"The archive may contain a path traversal attempt."
        )

    cur = base
    rel_parts = target_dir.relative_to(base).parts
    for part in rel_parts:
        cur = cur / part
        if _is_symlink_lstat(cur):
            raise RuntimeError(
                f"Security: refusing to follow symlink at '{cur}' during extraction — "
                f"this prevents potential path traversal in the archive."
            )


def _open_for_write_nofollow(path: Path, *, overwrite: bool) -> int:
    flags_base = os.O_WRONLY
    o_nofollow = getattr(os, "O_NOFOLLOW", 0)

    try:
        st = os.lstat(path)
        if stat.S_ISLNK(st.st_mode):
            raise RuntimeError(
                f"Security: refusing to write to symlink target '{path}' — "
                f"this prevents potential path traversal during extraction."
            )
        if not overwrite:
            raise RuntimeError(
                f"File '{path.name}' already exists and overwrite is disabled. "
                f"Use a clean output directory or enable overwrite."
            )
        if not stat.S_ISREG(st.st_mode):
            raise RuntimeError(
                f"Cannot overwrite '{path}' — it is not a regular file (may be a device, socket, or pipe). "
                f"Remove it manually or use a different output directory."
            )
        flags = flags_base | os.O_TRUNC | o_nofollow
        return os.open(path, flags, 0o600)
    except FileNotFoundError:
        flags = flags_base | os.O_CREAT | os.O_EXCL | o_nofollow
        return os.open(path, flags, 0o600)
    except OSError as e:
        raise RuntimeError(
            f"Cannot write to '{path}'. Check that the output directory is writable "
            f"and has sufficient disk space. Detail: {e}"
        ) from e


def _atomic_tmp(final_path: Path) -> Path:
    # deterministic-ish temp name; avoid leaking tar names into tmp too much
    tag = short_hash(f"{final_path}:{os.getpid()}", n=8)
    return final_path.with_name(final_path.name + f".tmp.{tag}")


def safe_extract_one(  # pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements
    # reason: single-member tar extraction has to cover directory vs regular-file handling,
    # symlink/traversal safety checks, byte-budget enforcement, and atomic-write cleanup in
    # one place; splitting it up would scatter the security invariants across helpers.
    logger: logging.Logger,
    tar: tarfile.TarFile,
    member: tarfile.TarInfo,
    outdir: Path,
    *,
    policy: ExtractPolicy,
    written_total: int = 0,
    bytes_budget: int | None = None,
    is_manifest: bool = False,
) -> ExtractResult:
    """Safely extract a single tar member into `outdir`, enforcing traversal/symlink/size checks."""
    outdir = Path(outdir).resolve()

    # IMPORTANT: don't force normalization for special members we might skip
    raw_name = member.name or ""
    try:
        origin_key = normalize_tar_name(raw_name)
    except RuntimeError:
        origin_key = raw_name  # best-effort identity for logs

    # If we are going to skip specials, do it BEFORE strict normalization enforcement
    if not member.isdir() and not member.isreg():
        if policy.skip_special:
            logger.warning(f"Skipping special tar member: {raw_name} (type={member.type!r})")
            return ExtractResult(0, None, origin_key, "skipped_special")
        raise RuntimeError(f"Refusing to extract unsupported tar member: {raw_name} (type={member.type!r})")

    # Now enforce normalization strictly for paths we will materialize
    origin_key = normalize_tar_name(raw_name)
    target_path = (outdir / origin_key).resolve()

    if outdir != target_path and outdir not in target_path.parents:
        raise RuntimeError(
            f"Security: extraction path for '{raw_name}' would escape the output directory. "
            f"The archive may contain a path traversal attempt."
        )

    if member.isdir():
        target_path.mkdir(parents=True, exist_ok=True)

        if policy.preserve_permissions:
            try:
                mode = int(member.mode or 0o755) & 0o777
                mode |= 0o200
                os.chmod(target_path, mode)
            except OSError:
                pass

        if policy.preserve_timestamps:
            try:
                mt = int(getattr(member, "mtime", 0) or 0)
                if mt > 0:
                    os.utime(target_path, (mt, mt))
            except OSError:
                pass

        return ExtractResult(0, target_path, origin_key, "")

    # Regular file
    target_path.parent.mkdir(parents=True, exist_ok=True)
    ensure_no_symlink_components(outdir, target_path.parent)

    final_path = target_path
    if final_path.exists():
        if _is_symlink_lstat(final_path):
            raise RuntimeError(
                f"Security: refusing to write to symlink target '{final_path.name}' — "
                f"this prevents potential path traversal during extraction."
            )

        if policy.rename_on_collision and not policy.overwrite:
            final_path = unique_path(final_path)
        elif policy.overwrite:
            pass
        else:
            raise RuntimeError(
                f"File '{final_path.name}' already exists and overwrite is disabled. "
                f"Use a clean output directory or enable overwrite."
            )

    if is_manifest and policy.max_manifest_bytes is not None:
        try:
            sz = int(getattr(member, "size", 0) or 0)
        except (ValueError, TypeError):
            sz = 0
        if sz > policy.max_manifest_bytes:
            logger.warning(
                f"Skipping large manifest-like file {raw_name!r} "
                f"(size={sz} > max_manifest_bytes={policy.max_manifest_bytes})"
            )
            return ExtractResult(0, None, origin_key, "skipped_manifest_too_large")

    f = tar.extractfile(member)
    if f is None:
        raise RuntimeError(
            f"Failed to read file '{raw_name}' from the archive. The archive may be corrupted or truncated."
        )

    extracted = 0
    bb = bytes_budget if bytes_budget is not None else policy.max_total_bytes

    # Write to temp + atomic replace to avoid deleting/truncating preexisting files on failure
    tmp_path = _atomic_tmp(final_path)
    fd: int | None = None
    try:
        # tmp_path must not already exist, and must not be a symlink
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)  # type: ignore[attr-defined]
        fd = _open_for_write_nofollow(tmp_path, overwrite=False)

        with f, os.fdopen(fd, "wb") as out_f:
            fd = None
            while True:
                chunk = f.read(SIZE_1_MIB)
                if not chunk:
                    break
                out_f.write(chunk)
                extracted += len(chunk)

                if bb is not None and (written_total + extracted) > bb:
                    try:
                        out_f.flush()
                        os.fsync(out_f.fileno())
                    except OSError:
                        pass
                    raise RuntimeError(
                        f"Extraction exceeded max_total_bytes={bb} while writing {raw_name!r} "
                        f"(written_total={written_total}, this_file={extracted})"
                    )

            try:
                out_f.flush()
                os.fsync(out_f.fileno())
            except OSError:
                pass

        # Preserve mode/mtime on tmp, then atomic replace
        if policy.preserve_permissions:
            try:
                mode = int(member.mode or 0o644) & 0o666
                mode |= 0o200
                os.chmod(tmp_path, mode)
            except OSError:
                pass

        if policy.preserve_timestamps:
            try:
                mt = int(getattr(member, "mtime", 0) or 0)
                if mt > 0:
                    os.utime(tmp_path, (mt, mt))
            except OSError:
                pass

        os.replace(tmp_path, final_path)

        return ExtractResult(extracted, final_path, origin_key, "")

    except Exception:  # pylint: disable=broad-exception-caught
        # reason: must catch any failure mode from the write/replace above (I/O errors,
        # RuntimeError from the budget check, etc.) to clean up the partial tmp file
        # before re-raising, without masking the original exception type.
        try:
            if fd is not None:
                os.close(fd)
        except OSError:
            pass
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise


# RAW extractor (matches the filename!)


class RAW:  # pylint: disable=too-few-public-methods
    # reason: namespace-style class grouping RAW/tarball extraction entry points and their
    # private helpers, matching the `U` utility-class pattern used elsewhere in this codebase.
    """Extractor for RAW/IMG disk images, optionally packaged inside a tarball."""

    @staticmethod
    def extract_raw_or_tar(  # pylint: disable=too-many-arguments,too-many-locals
        # reason: public entry point that fans out to direct-RAW and tarball handling while
        # threading through many independent, optional extraction/conversion knobs.
        logger: logging.Logger,
        src: Path,
        outdir: Path,
        *,
        convert_to_qcow2: bool = False,
        convert_outdir: Path | None = None,
        convert_compress: bool = False,
        convert_compress_level: int | None = None,
        log_virt_filesystems: bool = False,
        max_members: int | None = None,
        max_total_bytes: int | None = None,
        max_manifest_bytes: int = 5 * SIZE_1_MIB,
        skip_special: bool = True,
        preserve_permissions: bool = True,
        extract_all: bool = False,
        include_manifests: bool = True,
        overwrite: bool = False,
        rename_on_collision: bool = False,
        preserve_timestamps: bool = False,
    ) -> list[Path]:
        """Extract (and optionally convert to qcow2) a RAW/IMG disk from `src`, a file or tarball."""
        src = Path(src)
        outdir = Path(outdir)
        U.ensure_dir(outdir)

        if not src.exists():
            U.die(logger, f"Source not found: {src}", 1)
        if not src.is_file():
            U.die(logger, f"Source is not a file: {src}", 1)

        # Direct RAW/IMG
        if src.suffix.lower() in _ALLOWED_RAW_EXTS:
            disk = src.expanduser().resolve()
            logger.info(f"RAW disk: {disk}")
            if log_virt_filesystems:
                RAW._log_virt_filesystems(logger, disk)

            if convert_to_qcow2:
                out_conv = Path(convert_outdir) if convert_outdir else (outdir / "qcow2")
                U.ensure_dir(out_conv)
                return RAW._convert_to_qcow2(
                    logger,
                    [(disk, f"file:{disk.name}")],
                    out_conv,
                    compress=convert_compress,
                    compress_level=convert_compress_level,
                )
            return [disk]

        # Tarball
        if RAW._looks_like_tar(src):
            return RAW._extract_raw_tar(
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
                max_manifest_bytes=max_manifest_bytes,
                skip_special=skip_special,
                preserve_permissions=preserve_permissions,
                extract_all=extract_all,
                include_manifests=include_manifests,
                overwrite=overwrite,
                rename_on_collision=rename_on_collision,
                preserve_timestamps=preserve_timestamps,
            )

        U.die(logger, f"Unsupported RAW source type (expected .raw/.img or tarball): {src}", 1)
        raise AssertionError("unreachable: U.die() always raises")

    @staticmethod
    def _extract_raw_tar(  # pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements
        # reason: tarball extraction has to plan+validate members, track multiple skip/extract
        # counters, and dispatch to qcow2 conversion, all while threading through the same
        # extraction options as extract_raw_or_tar().
        logger: logging.Logger,
        tar_path: Path,
        outdir: Path,
        *,
        convert_to_qcow2: bool,
        convert_outdir: Path | None,
        convert_compress: bool,
        convert_compress_level: int | None,
        log_virt_filesystems: bool,
        max_members: int | None,
        max_total_bytes: int | None,
        max_manifest_bytes: int,
        skip_special: bool,
        preserve_permissions: bool,
        extract_all: bool,
        include_manifests: bool,
        overwrite: bool,
        rename_on_collision: bool,
        preserve_timestamps: bool,
    ) -> list[Path]:
        U.banner(logger, "Extract RAW tarball")
        logger.info(f"RAW tarball: {tar_path}")

        outdir = Path(outdir)
        U.ensure_dir(outdir)

        policy = ExtractPolicy(
            skip_special=skip_special,
            preserve_permissions=preserve_permissions,
            preserve_timestamps=preserve_timestamps,
            overwrite=overwrite,
            rename_on_collision=rename_on_collision,
            max_total_bytes=max_total_bytes,
            max_manifest_bytes=max_manifest_bytes,
        )

        def is_manifest_name(name: str) -> bool:
            nm = (name or "").strip().replace("\\", "/")
            if not nm:
                return False
            base = PurePosixPath(nm).name.lower()
            return Path(base).suffix in _ALLOWED_MANIFEST_EXTS

        def should_extract_name(name: str) -> bool:
            if extract_all:
                return True
            nm = (name or "").strip()
            if not nm:
                return False
            nm = nm.replace("\\", "/")
            base = PurePosixPath(nm).name.lower()
            if any(base.endswith(ext) for ext in _ALLOWED_RAW_EXTS):
                return True
            return bool(include_manifests and Path(base).suffix in _ALLOWED_MANIFEST_EXTS)

        # Pass 1: plan (streaming)
        planned_files = 0
        planned_dirs = 0
        planned_regular_bytes = 0
        total_seen = 0

        with tarfile.open(tar_path, "r:*") as tar:
            for m in tar:
                total_seen += 1
                if max_members is not None and total_seen > max_members:
                    U.die(logger, f"Tarball has too many members (> max_members={max_members})", 1)

                if not should_extract_name(m.name or ""):
                    continue
                if m.isdir():
                    planned_dirs += 1
                    continue
                planned_files += 1
                if m.isreg():
                    planned_regular_bytes += int(getattr(m, "size", 0) or 0)

        if planned_files == 0 and planned_dirs == 0:
            U.die(
                logger,
                "Tarball contains no extractable members (expected .raw/.img, optionally manifests).",
                1,
            )

        if policy.max_total_bytes is not None and planned_regular_bytes > policy.max_total_bytes:
            U.die(
                logger,
                f"Tarball planned payload too large ({planned_regular_bytes} > "
                f"max_total_bytes={policy.max_total_bytes})",
                1,
            )

        extracted_raw: list[Path] = []
        extracted_pairs: list[tuple[Path, str]] = []
        extracted_other: list[Path] = []
        written_total = 0

        skipped_by_filter = 0
        skipped_special = 0
        skipped_manifest_too_large = 0

        with tarfile.open(tar_path, "r:*") as tar:
            members_seen = 0
            extract_count = 0
            for m in tar:
                members_seen += 1
                if max_members is not None and members_seen > max_members:
                    U.die(logger, f"Tarball has too many members (> max_members={max_members})", 1)

                if not should_extract_name(m.name or ""):
                    skipped_by_filter += 1
                    continue

                res = safe_extract_one(
                    logger,
                    tar,
                    m,
                    outdir,
                    policy=policy,
                    written_total=written_total,
                    bytes_budget=policy.max_total_bytes,
                    is_manifest=is_manifest_name(m.name or ""),
                )
                written_total += res.extracted_bytes

                if res.reason == "skipped_special":
                    skipped_special += 1
                elif res.reason == "skipped_manifest_too_large":
                    skipped_manifest_too_large += 1

                if res.extracted_path is not None:
                    extract_count += 1
                    if res.extracted_path.suffix.lower() in _ALLOWED_RAW_EXTS:
                        extracted_raw.append(res.extracted_path)
                        extracted_pairs.append((res.extracted_path, res.origin_key))
                    else:
                        extracted_other.append(res.extracted_path)
                    logger.info("Extracted %d: %s (%d bytes)", extract_count, m.name, res.extracted_bytes)

        # Dedup preserving order
        def _dedup(ps: list[Path]) -> list[Path]:
            seen: set[str] = set()
            out: list[Path] = []
            for p in ps:
                s = str(p)
                if s not in seen:
                    out.append(p)
                    seen.add(s)
            return out

        uniq_raw = _dedup(extracted_raw)
        uniq_other = _dedup(extracted_other)

        if not uniq_raw:
            U.die(logger, "No .raw/.img found inside tarball after extraction.", 1)

        logger.info(
            "Extraction summary: extracted_raw=%d extracted_other=%d skipped_by_filter=%d skipped_special=%d "
            "skipped_manifest_too_large=%d written_total_bytes=%d",
            len(uniq_raw),
            len(uniq_other),
            skipped_by_filter,
            skipped_special,
            skipped_manifest_too_large,
            written_total,
        )

        if log_virt_filesystems:
            for d in uniq_raw:
                if d.exists():
                    RAW._log_virt_filesystems(logger, d)

        if convert_to_qcow2:
            out_conv = Path(convert_outdir) if convert_outdir else (outdir / "qcow2")
            U.ensure_dir(out_conv)
            return RAW._convert_to_qcow2(
                logger,
                extracted_pairs,
                out_conv,
                compress=convert_compress,
                compress_level=convert_compress_level,
            )

        return uniq_raw

    @staticmethod
    def _convert_to_qcow2(
        logger: logging.Logger,
        disks: list[tuple[Path, str]],
        outdir: Path,
        *,
        compress: bool,
        compress_level: int | None,
    ) -> list[Path]:
        U.banner(logger, "Convert extracted RAW image(s) to QCOW2")
        U.ensure_dir(outdir)

        outs: list[Path] = []
        for disk, origin_key in disks:
            h = short_hash(f"origin:{origin_key}", n=10)
            out = (outdir / f"{disk.stem}-{h}.qcow2").expanduser().resolve()
            logger.info("Converting: %s -> %s (compress=%s level=%r)", disk, out, compress, compress_level)
            Convert.convert_image_with_progress(
                logger,
                disk,
                out,
                out_format="qcow2",
                compress=compress,
                compress_level=compress_level,
            )
            Convert.validate(logger, out)
            outs.append(out)
        return outs

    @staticmethod
    def _log_virt_filesystems(logger: logging.Logger, image: Path) -> dict[str, Any]:
        return U.log_virt_filesystems_introspection(logger, image)

    @staticmethod
    def _looks_like_tar(p: Path) -> bool:
        s = p.name.lower()
        return s.endswith((".tar", ".tar.gz", ".tgz", ".tar.xz", ".txz"))
