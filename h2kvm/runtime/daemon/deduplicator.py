# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/daemon/deduplicator.py
"""
File deduplication for daemon mode.
Tracks processed files to avoid duplicate conversions.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging
    from pathlib import Path


class FileDeduplicator:
    """
    Tracks processed files using SQLite database.

    Deduplication methods:
    1. By filename
    2. By MD5 hash (optional, slower but more reliable)
    """

    def __init__(self, logger: logging.Logger, db_path: Path, use_md5: bool = False):
        self.logger = logger
        self.db_path = db_path
        self.use_md5 = use_md5
        self.lock = threading.Lock()

        # Create database
        self._init_db()

        self.logger.info(f"🔍 Deduplication enabled (MD5: {use_md5})")

    def _init_db(self) -> None:
        """Initialize SQLite database."""
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    md5_hash TEXT,
                    processed_at TEXT NOT NULL,
                    output_path TEXT,
                    status TEXT NOT NULL,
                    UNIQUE(filename, file_size)
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_filename
                ON processed_files(filename)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_md5_hash
                ON processed_files(md5_hash)
            """)

            conn.commit()

    def is_duplicate(self, file_path: Path) -> dict | None:
        """
        Check if file was already processed.

        Returns:
            None if not a duplicate, otherwise dict with duplicate info
        """
        with self.lock:
            filename = file_path.name
            file_size = file_path.stat().st_size

            # Check by filename and size
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT * FROM processed_files
                    WHERE filename = ? AND file_size = ?
                    ORDER BY processed_at DESC
                    LIMIT 1
                """,
                    (filename, file_size),
                )

                row = cursor.fetchone()
                if row:
                    self.logger.info(f"🔍 Duplicate detected: {filename} (size match)")
                    return dict(row)

            # Check by MD5 if enabled
            if self.use_md5:
                md5_hash = self._calculate_md5(file_path)
                with sqlite3.connect(str(self.db_path)) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute(
                        """
                        SELECT * FROM processed_files
                        WHERE md5_hash = ?
                        ORDER BY processed_at DESC
                        LIMIT 1
                    """,
                        (md5_hash,),
                    )

                    row = cursor.fetchone()
                    if row:
                        self.logger.info(f"🔍 Duplicate detected: {filename} (MD5 match)")
                        return dict(row)

            return None

    def mark_processed(
        self, file_path: Path, output_path: Path | None = None, status: str = "success"
    ) -> None:
        """Mark file as processed."""
        with self.lock:
            filename = file_path.name
            filepath = str(file_path.absolute())
            file_size = file_path.stat().st_size if file_path.exists() else 0
            md5_hash = self._calculate_md5(file_path) if self.use_md5 and file_path.exists() else None
            processed_at = datetime.now().isoformat()
            output_path_str = str(output_path) if output_path else None

            try:
                with sqlite3.connect(str(self.db_path)) as conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO processed_files
                        (filename, filepath, file_size, md5_hash, processed_at, output_path, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                        (filename, filepath, file_size, md5_hash, processed_at, output_path_str, status),
                    )
                    conn.commit()

                self.logger.debug(f"🔍 Marked as processed: {filename}")
            except Exception as e:
                self.logger.exception(f"Failed to mark file as processed: {e}")

    def _calculate_md5(self, file_path: Path) -> str:
        """Calculate MD5 hash of file."""
        if not file_path.exists():
            return ""

        try:
            md5 = hashlib.md5(usedforsecurity=False)
            with open(file_path, "rb") as f:
                # Read in chunks to handle large files
                for chunk in iter(lambda: f.read(8192), b""):
                    md5.update(chunk)
            return md5.hexdigest()
        except Exception as e:
            self.logger.exception(f"Failed to calculate MD5: {e}")
            return ""

    def get_stats(self) -> dict:
        """Get deduplication statistics."""
        with self.lock, sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful,
                        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
                    FROM processed_files
                """)
            row = cursor.fetchone()

            return {
                "total_tracked": row[0] if row else 0,
                "successful": row[1] if row else 0,
                "failed": row[2] if row else 0,
            }

    def cleanup_old_records(self, days: int = 90) -> int:
        """
        Remove old records from database.

        Args:
            days: Remove records older than this many days

        Returns:
            Number of records removed
        """
        with self.lock:
            cutoff_date = datetime.now().timestamp() - (days * 24 * 3600)
            cutoff_iso = datetime.fromtimestamp(cutoff_date).isoformat()

            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.execute(
                    """
                    DELETE FROM processed_files
                    WHERE processed_at < ?
                """,
                    (cutoff_iso,),
                )
                conn.commit()
                deleted = cursor.rowcount

            if deleted > 0:
                self.logger.info(f"🔍 Cleaned up {deleted} old deduplication records")

            return deleted
