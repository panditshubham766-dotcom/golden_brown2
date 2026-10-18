"""
SQLite connection factory.

Every connection uses:
  - PRAGMA secure_delete=ON  (overwrite free pages)
  - PRAGMA journal_mode=DELETE  (rollback journal; NOT WAL)
  - PRAGMA foreign_keys=ON
  - PRAGMA synchronous=FULL  (safe for document data)

No WAL is used so there is no -wal or -shm file left behind on deletion.
"""
from __future__ import annotations

import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger("lexiguard.store.db")

# Schema version — bump when schema changes require migration.
_SCHEMA_VERSION = 1

_SCHEMA_SQL = """
-- Document metadata (no filenames, no user data).
CREATE TABLE IF NOT EXISTS document (
    document_id     TEXT PRIMARY KEY,
    sha256          TEXT NOT NULL,
    file_type       TEXT NOT NULL CHECK(file_type IN ('pdf', 'txt')),
    page_count      INTEGER NOT NULL,
    has_unread_pages INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'ready',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- Physical pages (1-based; TXT virtual pages use "virtual page (TXT)" warning).
CREATE TABLE IF NOT EXISTS pages (
    page_num        INTEGER NOT NULL,
    norm_text       TEXT NOT NULL,
    text_hash       TEXT NOT NULL,
    is_readable     INTEGER NOT NULL DEFAULT 1,
    lang_supported  INTEGER NOT NULL DEFAULT 1,
    warnings_json   TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (page_num)
);

-- Sentences with deterministic sids.
CREATE TABLE IF NOT EXISTS sentences (
    sid             TEXT PRIMARY KEY,
    page_num        INTEGER NOT NULL,
    section         TEXT NOT NULL DEFAULT '',
    start_offset    INTEGER NOT NULL,
    end_offset      INTEGER NOT NULL,
    sentence_text   TEXT NOT NULL,
    normalised_number TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (page_num) REFERENCES pages(page_num)
);

-- FTS5 virtual table over sentence_text.
-- unicode61 tokenizer with diacritic removal.
-- A normalised_number column so "Rs. 25,000/-", "25000" and "₹25,000" match.
CREATE VIRTUAL TABLE IF NOT EXISTS sentences_fts USING fts5(
    sid UNINDEXED,
    sentence_text,
    normalised_number,
    content=sentences,
    content_rowid=rowid,
    tokenize='unicode61 remove_diacritics 2'
);

-- FTS5 triggers to keep the index in sync.
CREATE TRIGGER IF NOT EXISTS sentences_ai AFTER INSERT ON sentences BEGIN
    INSERT INTO sentences_fts(rowid, sid, sentence_text, normalised_number)
    VALUES (new.rowid, new.sid, new.sentence_text, new.sentence_text);
END;
CREATE TRIGGER IF NOT EXISTS sentences_ad AFTER DELETE ON sentences BEGIN
    INSERT INTO sentences_fts(sentences_fts, rowid, sid, sentence_text, normalised_number)
    VALUES('delete', old.rowid, old.sid, old.sentence_text, old.sentence_text);
END;

-- Run ledger: no question text, no answer text, no evidence text.
CREATE TABLE IF NOT EXISTS run_ledger (
    run_id          TEXT PRIMARY KEY,
    route           TEXT,
    tool_names_json TEXT NOT NULL DEFAULT '[]',
    tool_call_count INTEGER NOT NULL DEFAULT 0,
    sids_json       TEXT NOT NULL DEFAULT '[]',
    validation_codes_json TEXT NOT NULL DEFAULT '[]',
    duration_ms     INTEGER,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
"""


def open_doc_db(db_path: Path) -> sqlite3.Connection:
    """
    Open (or create) the per-document SQLite database.

    Applies all required PRAGMAs and creates the schema if needed.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path), check_same_thread=False)
    con.row_factory = sqlite3.Row

    _apply_pragmas(con)

    # Check FTS5 availability (belt-and-suspenders; main.py also checks at startup).
    try:
        con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(x)")
        con.execute("DROP TABLE IF EXISTS _fts5_probe")
    except sqlite3.OperationalError as exc:
        con.close()
        raise RuntimeError(
            f"SQLite FTS5 not available for document DB at {db_path}: {exc}"
        ) from exc

    con.executescript(_SCHEMA_SQL)
    con.commit()

    return con


def _apply_pragmas(con: sqlite3.Connection) -> None:
    """Apply LexiGuard-required PRAGMAs to an open connection."""
    con.execute("PRAGMA secure_delete=ON")
    con.execute("PRAGMA journal_mode=DELETE")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA synchronous=FULL")
