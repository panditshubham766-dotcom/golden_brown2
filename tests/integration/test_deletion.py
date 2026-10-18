"""
Integration tests: deletion service.

Tests:
- Successful deletion removes directory and returns correct flags.
- Deletion of non-existent document returns None.
- Safe document_id validation rejects traversal attempts.
"""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def tmp_doc_dir(tmp_path: Path) -> tuple[Path, str]:
    """Create a minimal per-document directory for testing."""
    from backend.app.store.db import open_doc_db

    doc_id = "a" * 32  # 32 hex chars
    doc_dir = tmp_path / doc_id
    doc_dir.mkdir()

    db_path = doc_dir / "doc.sqlite3"
    con = open_doc_db(db_path)
    con.execute(
        "INSERT INTO document (document_id, sha256, file_type, page_count) VALUES (?,?,?,?)",
        (doc_id, "abc123", "txt", 1),
    )
    con.execute(
        "INSERT INTO pages (page_num, norm_text, text_hash) VALUES (?,?,?)",
        (1, "Test sentence.", "hash1"),
    )
    con.commit()
    con.close()

    return doc_dir, doc_id


@pytest.mark.asyncio
async def test_deletion_removes_directory(
    tmp_path: Path, tmp_doc_dir: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    doc_dir, doc_id = tmp_doc_dir

    # Patch settings to use tmp_path as data_dir.
    from backend.app import config
    settings = config.get_settings()
    monkeypatch.setattr(settings, "data_dir", tmp_path)

    from backend.app.store.delete import safe_delete_document
    result = await safe_delete_document(doc_id)

    assert result is not None
    assert result.app_files_removed
    assert result.directory_absent
    assert not doc_dir.exists()


@pytest.mark.asyncio
async def test_deletion_nonexistent_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.app import config
    settings = config.get_settings()
    monkeypatch.setattr(settings, "data_dir", tmp_path)

    from backend.app.store.delete import safe_delete_document
    result = await safe_delete_document("b" * 32)
    assert result is None


def test_safe_doc_id_validation() -> None:
    from backend.app.store.delete import _is_safe_doc_id

    assert _is_safe_doc_id("a" * 32)
    assert _is_safe_doc_id("0123456789abcdef" * 2)
    assert not _is_safe_doc_id("../etc/passwd")
    assert not _is_safe_doc_id("")
    assert not _is_safe_doc_id("a" * 31)   # too short
    assert not _is_safe_doc_id("a" * 33)   # too long
    assert not _is_safe_doc_id("ABCDEFGH" + "a" * 24)  # uppercase
