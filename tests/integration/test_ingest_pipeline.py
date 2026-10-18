"""Integration tests for ingest pipeline (FTS5 store)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def test_db_schema_created(tmp_path: Path) -> None:
    """SQLite schema is created with all required tables and FTS5."""
    from backend.app.store.db import open_doc_db

    db_path = tmp_path / "test.sqlite3"
    con = open_doc_db(db_path)

    tables = {
        row[0]
        for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "document" in tables
    assert "pages" in tables
    assert "sentences" in tables
    assert "run_ledger" in tables

    # FTS5 virtual table.
    vt = {
        row[0]
        for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%fts%'"
        ).fetchall()
    }
    assert "sentences_fts" in vt or any("sentences_fts" in n for n in vt)
    con.close()


def test_secure_delete_pragma(tmp_path: Path) -> None:
    """PRAGMA secure_delete=ON must be set."""
    from backend.app.store.db import open_doc_db

    con = open_doc_db(tmp_path / "test.sqlite3")
    row = con.execute("PRAGMA secure_delete").fetchone()
    assert row[0] == 1, "PRAGMA secure_delete must be ON (1)"
    con.close()


def test_journal_mode_delete(tmp_path: Path) -> None:
    """journal_mode must be DELETE (not WAL)."""
    from backend.app.store.db import open_doc_db

    con = open_doc_db(tmp_path / "test.sqlite3")
    row = con.execute("PRAGMA journal_mode").fetchone()
    assert row[0].lower() == "delete", (
        f"journal_mode must be DELETE, got {row[0]!r}"
    )
    con.close()


def test_fts5_search(tmp_path: Path) -> None:
    """FTS5 search returns the inserted sentence."""
    from backend.app.store.db import open_doc_db
    from backend.app.ingest.segment import Sentence
    from backend.app.store.sentences import insert_sentences
    from backend.app.store.fts import search

    con = open_doc_db(tmp_path / "test.sqlite3")

    # Insert required page row first (FK: sentences.page_num -> pages.page_num)
    con.execute(
        "INSERT INTO pages (page_num, norm_text, text_hash) VALUES (?, ?, ?)",
        (1, "Test page content.", "abc123hash"),
    )
    con.commit()

    sents = [
        Sentence(
            sid="s_test001",
            page_num=1,
            section="",
            start=0,
            end=50,
            text="The tenant shall pay security deposit of Rs. 25000.",
        )
    ]
    insert_sentences(con, sents)
    con.commit()

    hits = search(con, "security deposit", limit=5)
    assert len(hits) >= 1
    assert hits[0].sid == "s_test001"
    con.close()


def test_no_wal_file_after_close(tmp_path: Path) -> None:
    """After closing the connection, no -wal or -shm files should exist."""
    from backend.app.store.db import open_doc_db

    db_path = tmp_path / "test.sqlite3"
    con = open_doc_db(db_path)
    con.close()

    assert not (tmp_path / "test.sqlite3-wal").exists(), "WAL file must not exist"
    assert not (tmp_path / "test.sqlite3-shm").exists(), "SHM file must not exist"
