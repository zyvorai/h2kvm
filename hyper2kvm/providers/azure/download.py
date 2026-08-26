# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Azure VHD download with retry and progress tracking."""
# hyper2kvm/azure/download.py

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import requests

from hyper2kvm.core.retry_decorator import api_retry

from .exceptions import AzureDownloadError

if TYPE_CHECKING:
    from pathlib import Path

LOG = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    """Outcome of a resumable download: bytes written, expected total, and resume offset."""

    bytes_written: int
    expected_total: int | None
    resumed_from: int = 0


def _backoff_sleep(attempt: int, base: float, cap: float) -> None:
    t = min(cap, base * (2**attempt))
    t = t * (0.7 + random.random() * 0.6)
    time.sleep(t)


@api_retry(max_retries=3, retryable_exceptions=(ConnectionError, TimeoutError, OSError))
# Resumable HTTP download covers many independent knobs: resume, retry, verification, progress logging.
# pylint: disable-next=too-many-arguments,too-many-locals,too-many-branches,too-many-statements
def download_with_resume(
    *,
    url: str,
    dest: Path,
    resume: bool,
    chunk_bytes: int,
    verify_size: bool,
    strict_verify: bool,
    temp_suffix: str,
    connect_timeout_s: int,
    read_timeout_s: int,
    retries: int,
    backoff_base_s: float,
    backoff_cap_s: float,
    progress: object | None = None,  # pylint: disable=unused-argument  # kept for API compatibility; called with progress=... elsewhere
    task_id: int | None = None,  # pylint: disable=unused-argument  # kept for API compatibility; called with task_id=... elsewhere
) -> DownloadResult:
    """
    Download a file from URL with resume capability and retry logic.

    Args:
        url: Source URL (SAS token included)
        dest: Destination file path
        resume: Enable resume from partial download
        chunk_bytes: Size of chunks to download
        verify_size: Check final size matches Content-Length
        strict_verify: Fail if size mismatch (otherwise warn)
        temp_suffix: Suffix for temporary download file
        connect_timeout_s: Connection timeout
        read_timeout_s: Read timeout
        retries: Number of retry attempts
        backoff_base_s: Base backoff time
        backoff_cap_s: Maximum backoff time
        progress: Unused, kept for API compatibility
        task_id: Unused, kept for API compatibility

    Returns:
        DownloadResult with bytes written and expected total
    """
    temp = dest.parent / f"{dest.name}{temp_suffix}"

    # Check existing progress
    start_byte = 0
    if resume and temp.exists():
        start_byte = temp.stat().st_size
        LOG.info("Resuming download from byte %d", start_byte)

    headers = {}
    if start_byte > 0:
        headers["Range"] = f"bytes={start_byte}-"

    # Use session for connection pooling and reuse across retries
    session = requests.Session()

    try:  # pylint: disable=too-many-nested-blocks  # inherent to parsing headers + streaming + verifying in one retry loop
        last_error = None
        for attempt in range(max(1, retries)):
            try:
                resp = session.get(
                    url,
                    headers=headers,
                    stream=True,
                    timeout=(connect_timeout_s, read_timeout_s),
                    allow_redirects=True,
                )
                resp.raise_for_status()

                # Parse Content-Range or Content-Length
                expected_total: int | None = None
                content_range = resp.headers.get("Content-Range")
                if content_range:
                    # Format: bytes start-end/total
                    parts = content_range.split("/")
                    if len(parts) == 2 and parts[1].isdigit():
                        expected_total = int(parts[1])
                else:
                    content_length = resp.headers.get("Content-Length")
                    if content_length and content_length.isdigit():
                        if start_byte > 0:
                            expected_total = start_byte + int(content_length)
                        else:
                            expected_total = int(content_length)

                if expected_total:
                    LOG.info("Download size: %d bytes", expected_total)

                # Download
                mode = "ab" if start_byte > 0 else "wb"
                bytes_written = start_byte
                last_log_pct = -1

                with open(temp, mode) as f:
                    for chunk in resp.iter_content(chunk_size=chunk_bytes):
                        if chunk:
                            f.write(chunk)
                            bytes_written += len(chunk)
                            if expected_total and expected_total > 0:
                                pct = int(bytes_written * 100 / expected_total)
                                if pct >= last_log_pct + 10:
                                    LOG.info("Download progress: %d%%", pct)
                                    last_log_pct = pct

                # Verify size
                if verify_size and expected_total is not None:
                    if bytes_written != expected_total:
                        msg = f"Size mismatch: expected {expected_total}, got {bytes_written}"
                        if strict_verify:
                            temp.unlink(missing_ok=True)
                            raise AzureDownloadError(msg)
                        LOG.warning(msg)

                # Success - move to final location
                temp.rename(dest)
                return DownloadResult(
                    bytes_written=bytes_written,
                    expected_total=expected_total,
                    resumed_from=start_byte,
                )

            except (requests.RequestException, OSError) as e:
                last_error = str(e)
                LOG.warning("Download attempt %d/%d failed: %s", attempt + 1, retries, e)

                if attempt + 1 < retries:
                    _backoff_sleep(attempt, backoff_base_s, backoff_cap_s)

                    # Update start_byte for resume
                    if resume and temp.exists():
                        start_byte = temp.stat().st_size
                        headers["Range"] = f"bytes={start_byte}-"
                    continue

        # All retries exhausted
        temp.unlink(missing_ok=True)
        raise AzureDownloadError(f"Download failed after {retries} attempts: {last_error}")

    finally:
        session.close()
