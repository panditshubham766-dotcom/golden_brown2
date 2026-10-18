"""Sentences table CRUD."""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.ingest.segment import Sentence


def insert_sentences(con: sqlite3.Connection, sentences: "list[Sentence]") -> None:
    """Bulk-insert sentences. FTS5 triggers fire automatically."""
    con.executemany(
        """
        INSERT INTO sentences (sid, page_num, section, start_offset, end_offset, sentence_text, normalised_number)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (s.sid, s.page_num, s.section, s.start, s.end, s.text, s.text)
            for s in sentences
        ],
    )


def get_sentence_by_sid(con: sqlite3.Connection, sid: str) -> sqlite3.Row | None:
    return con.execute(
        "SELECT * FROM sentences WHERE sid = ?", (sid,)
    ).fetchone()
