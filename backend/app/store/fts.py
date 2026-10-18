"""
FTS5 index helpers.

The FTS5 virtual table (sentences_fts) is populated automatically via
triggers defined in db.py whenever sentences are inserted.

This module provides:
- build_fts_index: no-op (triggers handle it) but performs a consistency check.
- search: BM25-ranked FTS5 search returning up to `limit` chunk rows.

FTS5 settings (from schema):
  tokenize='unicode61 remove_diacritics 2'

A normalised_number column is populated with the sentence text;
in Phase 3 it will be replaced with a normalised-number version
so "Rs. 25,000/-", "25000" and "₹25,000" match each other.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.ingest.segment import Sentence

# Rupee normalisation for the FTS number column.
_RUPEE_RE = re.compile(r"(?:Rs\.?|INR|₹)\s*([\d,]+)(?:/-)?")
_COMMA_NUM_RE = re.compile(r"([\d,]+)")


def _normalise_numbers(text: str) -> str:
    """
    Produce a normalised-number variant of text for FTS matching.

    "Rs. 25,000/-" → "25000"
    "₹25,000" → "25000"
    """
    result = _RUPEE_RE.sub(lambda m: m.group(1).replace(",", ""), text)
    result = _COMMA_NUM_RE.sub(lambda m: m.group(1).replace(",", ""), result)
    return result


@dataclass
class SearchHit:
    sid: str
    page_num: int
    section: str
    sentence_text: str
    bm25_rank: float


def build_fts_index(con: sqlite3.Connection, sentences: "list[Sentence]") -> None:
    """
    Verify that FTS5 rows were inserted by the triggers.

    In Phase 3 this will also index normalised-number variants.
    """
    sentence_count = con.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
    fts_count = con.execute("SELECT COUNT(*) FROM sentences_fts").fetchone()[0]
    if sentence_count != fts_count:
        # Triggers may have failed (edge case in some SQLite builds).
        # Rebuild manually.
        con.execute("INSERT INTO sentences_fts(sentences_fts) VALUES('rebuild')")


def search(
    con: sqlite3.Connection,
    query: str,
    limit: int = 12,
) -> list[SearchHit]:
    """
    Run a BM25-ranked FTS5 search.

    Returns up to `limit` hits ordered by descending relevance.
    FTS5 BM25 scores are negative (closer to 0 = more relevant).
    """
    if not query.strip():
        return []

    # Escape FTS5 special characters to avoid query syntax errors.
    fts_query = _escape_fts5(query)

    try:
        rows = con.execute(
            """
            SELECT s.sid, s.page_num, s.section, s.sentence_text,
                   bm25(sentences_fts) AS rank
            FROM sentences_fts
            JOIN sentences s ON s.rowid = sentences_fts.rowid
            WHERE sentences_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts_query, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        # If the FTS query is invalid, return empty rather than crash.
        return []

    return [
        SearchHit(
            sid=row["sid"],
            page_num=row["page_num"],
            section=row["section"],
            sentence_text=row["sentence_text"],
            bm25_rank=row["rank"],
        )
        for row in rows
    ]


def _escape_fts5(query: str) -> str:
    """
    Escape a user / system query for safe FTS5 use.

    Strips FTS5 operator characters that could cause parse errors.
    """
    # Remove FTS5 special characters.
    safe = re.sub(r'["\^\*\:\(\)\{\}\[\]\\]', " ", query)
    # Collapse whitespace.
    safe = " ".join(safe.split())
    return safe if safe else '""'
