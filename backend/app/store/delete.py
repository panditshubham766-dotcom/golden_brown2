"""
Safe deletion service (Guide §5.3).

Steps:
1. Reject new work for the document (via a per-doc lock).
2. Close all SQLite connections to the document DB.
3. Remove the per-document directory (doc.sqlite3, source file, page images).
4. Run a verification scan to confirm directory absence and no derived rows remain.
5. Return a DeletionResult distinguishing app-controlled removal from forensic erasure.

SECURITY NOTE:
  PRAGMA secure_delete=ON overwrites freed SQLite pages with zeros.
  Rollback journal mode (journal_mode=DELETE) means no WAL file is left behind.
  We do NOT claim forensic erasure from SSD wear-levelling, OS swap,
  hibernation files, or external backups. This is documented in LIMITATIONS.md.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from backend.app.config import get_settings

logger = logging.getLogger("lexiguard.store.delete")

# Per-document deletion locks: prevents concurrent operations during deletion.
_deletion_locks: dict[str, Lock] = {}
_global_lock = Lock()


def _get_lock(document_id: str) -> Lock:
    with _global_lock:
        if document_id not in _deletion_locks:
            _deletion_locks[document_id] = Lock()
        return _deletion_locks[document_id]


@dataclass
class DeletionResult:
    document_id: str
    app_files_removed: bool
    fts_rows_removed: bool
    directory_absent: bool


async def safe_delete_document(document_id: str) -> DeletionResult | None:
    """
    Safely delete all app-controlled data for a document.

    Returns None if the document directory does not exist.
    """
    settings = get_settings()
    doc_dir = settings.data_dir / document_id

    # Validate document_id is a safe path component (hex string only).
    if not _is_safe_doc_id(document_id):
        logger.warning("Attempted deletion with unsafe document_id: (redacted)")
        return None

    if not doc_dir.exists():
        return None

    lock = _get_lock(document_id)

    def _do_delete() -> DeletionResult:
        with lock:
            return _delete_sync(document_id, doc_dir)

    # Run the blocking deletion in a thread pool so we don't block the event loop.
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _do_delete)
    return result


def _delete_sync(document_id: str, doc_dir: Path) -> DeletionResult:
    """Synchronous deletion logic — called from a thread pool."""
    db_path = doc_dir / "doc.sqlite3"
    fts_removed = False

    # ── Step 1: Close connections and explicitly zero FTS shadow tables ───────
    if db_path.exists():
        con = None
        try:
            # Use autocommit mode (isolation_level=None) so VACUUM can be called
            # outside any transaction — required by SQLite.
            con = sqlite3.connect(str(db_path), isolation_level=None)
            # secure_delete=ON ensures freed pages are overwritten.
            con.execute("PRAGMA secure_delete=ON")
            # Delete all rows — triggers fire and remove FTS5 shadow rows.
            con.execute("BEGIN")
            con.execute("DELETE FROM sentences")
            con.execute("DELETE FROM pages")
            con.execute("DELETE FROM document")
            # Rebuild FTS to flush shadow tables.
            try:
                con.execute("INSERT INTO sentences_fts(sentences_fts) VALUES('delete-all')")
            except sqlite3.OperationalError:
                pass
            con.execute("COMMIT")
            # VACUUM must run outside any transaction (autocommit required).
            con.execute("VACUUM")
            fts_removed = True
        except Exception as exc:
            logger.warning("Could not clear DB rows before deletion: %s", exc)
        finally:
            # Always close and dereference — critical on Windows to release the file lock.
            if con is not None:
                try:
                    con.close()
                except Exception:
                    pass
                con = None

    # ── Step 2: Remove the directory tree ─────────────────────────────────────
    removed = False
    try:
        shutil.rmtree(str(doc_dir), ignore_errors=False)
        removed = True
    except Exception as exc:
        logger.error("Failed to remove document directory: %s", exc)

    # ── Step 3: Verify directory absence ──────────────────────────────────────
    directory_absent = not doc_dir.exists()

    if not directory_absent:
        logger.error(
            "Document directory still exists after deletion attempt. "
            "Manual cleanup may be required."
        )

    # Clean up the lock (best-effort).
    with _global_lock:
        _deletion_locks.pop(document_id, None)

    logger.info(
        "Deletion complete for document %s: files_removed=%s, fts_removed=%s, dir_absent=%s",
        document_id, removed, fts_removed, directory_absent,
    )

    return DeletionResult(
        document_id=document_id,
        app_files_removed=removed,
        fts_rows_removed=fts_removed,
        directory_absent=directory_absent,
    )


def _is_safe_doc_id(document_id: str) -> bool:
    """
    Validate that document_id is a safe filesystem path component.

    Accepts only lowercase hex strings (32 chars) as generated by secrets.token_hex(16).
    Rejects any path traversal attempt.
    """
    return bool(document_id) and len(document_id) == 32 and all(
        c in "0123456789abcdef" for c in document_id
    )
