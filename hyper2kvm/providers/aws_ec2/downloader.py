# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""S3 download with progress tracking and resume support."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from .exceptions import DownloadFailed
from .utils import retry

logger = logging.getLogger(__name__)


class Downloader:
    """
    Download exported disk images from S3 with progress and resume.

    Features:
    - Progress callbacks with bytes/total
    - Resume partial downloads (Range header)
    - Retry with exponential backoff
    - Size verification after download
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        s3_client,
        *,
        retries: int = 5,
        backoff_base: float = 1.0,
        backoff_cap: float = 30.0,
        verify_size: bool = True,
        temp_suffix: str = ".part",
        log: logging.Logger | None = None,
    ):
        # reason: independent retry/backoff/verification tuning knobs for a downloader
        # that's constructed once and reused.
        self.s3 = s3_client
        self.retries = retries
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self.verify_size = verify_size
        self.temp_suffix = temp_suffix
        self.log = log or logger

    def download(  # pylint: disable=too-many-statements
        self,
        bucket: str,
        key: str,
        dest: str | Path,
        *,
        progress_cb: Callable[[int, int], None] | None = None,
        resume: bool = True,
    ) -> Path:
        # reason: covers empty-object short-circuit, resume detection, the nested
        # download implementation (range-resume vs fresh managed transfer), retry,
        # size verification, and the final atomic rename -- all inherent to one
        # resumable download operation.
        """
        Download an S3 object to local file.

        Args:
            bucket: S3 bucket name
            key: S3 object key
            dest: Local destination path
            progress_cb: Callback(bytes_downloaded, total_bytes)
            resume: Attempt to resume partial downloads

        Returns:
            Path to downloaded file

        Raises:
            DownloadFailed: If download fails after retries
        """
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        part_path = dest.with_suffix(dest.suffix + self.temp_suffix)

        # Get total size
        try:
            head = self.s3.head_object(Bucket=bucket, Key=key)
            total_size = head["ContentLength"]
        except Exception as e:
            raise DownloadFailed(f"Failed to get object info: s3://{bucket}/{key}: {e}") from e

        self.log.info(
            "Downloading s3://%s/%s (%.2f GB) -> %s",
            bucket,
            key,
            total_size / (1024**3),
            dest,
        )

        if total_size == 0:
            # Empty object — write empty file
            part_path.write_bytes(b"")
            part_path.rename(dest)
            if progress_cb:
                progress_cb(0, 0)
            return dest

        # Check for existing partial download
        if resume and part_path.exists():
            existing = part_path.stat().st_size
            if existing >= total_size:
                part_path.rename(dest)
                self.log.info("Download already complete (resumed)")
                if progress_cb:
                    progress_cb(total_size, total_size)
                return dest
            self.log.info("Resuming from byte %d (%.1f%%)", existing, 100 * existing / total_size)

        def _do_download() -> None:
            # Re-check part file size on each retry attempt
            current_size = part_path.stat().st_size if part_path.exists() else 0
            downloaded = current_size

            def _progress_callback(bytes_amount: int) -> None:
                nonlocal downloaded
                downloaded += bytes_amount
                if progress_cb:
                    progress_cb(downloaded, total_size)

            if current_size > 0 and resume:
                # Range-based resume from current file position
                resp = self.s3.get_object(
                    Bucket=bucket,
                    Key=key,
                    Range=f"bytes={current_size}-",
                )
                body = resp["Body"]
                try:
                    with open(str(part_path), "ab") as f:
                        for chunk in body.iter_chunks(chunk_size=8 * 1024 * 1024):
                            f.write(chunk)
                            _progress_callback(len(chunk))
                finally:
                    body.close()
            else:
                # Fresh download with boto3 managed transfer
                from boto3.s3.transfer import TransferConfig  # pylint: disable=import-outside-toplevel
                # reason: boto3 is an optional cloud-SDK dependency; keep it lazily
                # imported here so this module can be imported without boto3 installed
                # unless an actual S3 download is attempted.

                config = TransferConfig(
                    multipart_threshold=8 * 1024 * 1024,
                    max_concurrency=4,
                    multipart_chunksize=8 * 1024 * 1024,
                )
                self.s3.download_file(
                    bucket,
                    key,
                    str(part_path),
                    Callback=_progress_callback,
                    Config=config,
                )

        try:
            retry(
                _do_download,
                retries=self.retries,
                backoff_base=self.backoff_base,
                backoff_cap=self.backoff_cap,
                label=f"download(s3://{bucket}/{key})",
                log=self.log,
            )
        except Exception as e:
            raise DownloadFailed(f"Download failed after {self.retries} retries: {e}") from e

        # Verify size
        if self.verify_size:
            actual = part_path.stat().st_size
            if actual != total_size:
                raise DownloadFailed(
                    f"Size mismatch: expected {total_size}, got {actual} (s3://{bucket}/{key})"
                )

        # Rename part file to final
        part_path.rename(dest)
        self.log.info("Download complete: %s (%.2f GB)", dest, total_size / (1024**3))
        return dest

    def delete_s3_object(self, bucket: str, key: str) -> None:
        """Delete an S3 object (cleanup after download)."""
        try:
            self.s3.delete_object(Bucket=bucket, Key=key)
            self.log.info("Deleted s3://%s/%s", bucket, key)
        except Exception as e:  # pylint: disable=broad-exception-caught
            # reason: best-effort cleanup step -- a failed delete of the source S3
            # object must not abort the overall migration.
            self.log.warning("Failed to delete s3://%s/%s: %s", bucket, key, e)
