"""Rigorous silence gate implementation (Guide §7.4).

A document may be declared silent (NOT_LOCATED) IF AND ONLY IF:
1. No unread pages exist (adequate coverage),
2. Language is fully supported across all pages,
3. Lexical FTS5, heading searches, topic lexicon synonyms, and cross-reference
   expansions yield zero results.

Otherwise, if zero hits are found under incomplete coverage, return INSUFFICIENT_EVIDENCE.
If hits are found, return LOCATED.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import List, Optional
from backend.app.retrieval.lexical import SearchHit, load_rental_topics, search_lexical

STATUS_LOCATED = "LOCATED"
STATUS_NOT_LOCATED = "NOT_LOCATED"
STATUS_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass
class SilenceGateResult:
    status: str
    topic: str
    hits: List[SearchHit]
    explanation: str
    coverage_complete: bool


def verify_coverage_and_language(con: sqlite3.Connection) -> tuple[bool, str]:
    """
    Check that document coverage is complete and all pages are readable in a supported language.
    """
    doc_row = con.execute("SELECT has_unread_pages FROM document LIMIT 1").fetchone()
    if doc_row and doc_row[0] != 0:
        return False, "Document contains unread or uninspected pages"

    page_counts = con.execute(
        """
        SELECT 
            SUM(CASE WHEN is_readable = 0 THEN 1 ELSE 0 END) AS unreadable,
            SUM(CASE WHEN lang_supported = 0 THEN 1 ELSE 0 END) AS unsupported_lang
        FROM pages
        """
    ).fetchone()

    if page_counts:
        unreadable = page_counts[0] or 0
        unsupported = page_counts[1] or 0
        if unreadable > 0:
            return False, f"Document has {unreadable} unreadable page(s)"
        if unsupported > 0:
            return False, f"Document has {unsupported} page(s) with unsupported language"

    return True, "Coverage complete and language supported"


def _search_headings(con: sqlite3.Connection, topic: str) -> List[SearchHit]:
    """Search for topic in section headings."""
    topics_dict = load_rental_topics()
    terms = [topic.lower()]
    if topic.lower() in topics_dict:
        terms.extend(t.lower() for t in topics_dict[topic.lower()].get("synonyms", []))

    hits: List[SearchHit] = []
    seen_sids = set()

    for term in terms:
        rows = con.execute(
            """
            SELECT sid, page_num, section, sentence_text
            FROM sentences
            WHERE LOWER(section) LIKE ?
            LIMIT 12
            """,
            (f"%{term}%",),
        ).fetchall()

        for row in rows:
            sid = row["sid"]
            if sid not in seen_sids:
                seen_sids.add(sid)
                hits.append(
                    SearchHit(
                        sid=sid,
                        page_num=row["page_num"],
                        section=row["section"],
                        sentence_text=row["sentence_text"],
                        bm25_rank=0.0,
                        source="heading",
                    )
                )
                if len(hits) >= 12:
                    return hits

    return hits


def check_silence(
    con: sqlite3.Connection,
    topic: str,
    query: str = "",
) -> SilenceGateResult:
    """
    Execute the rigorous silence gate.

    Returns:
    - LOCATED if any evidence is found.
    - NOT_LOCATED iff zero results found AND coverage is complete AND language is supported.
    - INSUFFICIENT_EVIDENCE if zero results found BUT coverage is incomplete / language unsupported.
    """
    # 1. Search lexical index with topic + synonyms + cross-references
    lexical_hits = search_lexical(con, query=query, topic=topic, expand_xrefs=True, limit=12)

    # 2. Search headings
    heading_hits = _search_headings(con, topic)

    # Combine hits
    combined_hits: List[SearchHit] = list(lexical_hits)
    seen_sids = {h.sid for h in combined_hits}
    for h in heading_hits:
        if h.sid not in seen_sids and len(combined_hits) < 12:
            seen_sids.add(h.sid)
            combined_hits.append(h)

    # If hits found, topic is located
    if combined_hits:
        return SilenceGateResult(
            status=STATUS_LOCATED,
            topic=topic,
            hits=combined_hits[:12],
            explanation=f"Found {len(combined_hits)} relevant passage(s) regarding '{topic}'.",
            coverage_complete=True,
        )

    # If zero hits, verify coverage & language strictly
    coverage_ok, reason = verify_coverage_and_language(con)

    if coverage_ok:
        return SilenceGateResult(
            status=STATUS_NOT_LOCATED,
            topic=topic,
            hits=[],
            explanation=(
                f"I could not locate a provision about '{topic}' in the readable parts of this document. "
                f"I checked lexical full-text, headings, topic synonyms, and cross-references. "
                f"This does not mean '{topic}' is allowed or prohibited."
            ),
            coverage_complete=True,
        )

    # Coverage or language incomplete -> INSUFFICIENT_EVIDENCE
    return SilenceGateResult(
        status=STATUS_INSUFFICIENT_EVIDENCE,
        topic=topic,
        hits=[],
        explanation=(
            f"Could not locate a provision about '{topic}', but cannot confirm silence: {reason}."
        ),
        coverage_complete=False,
    )
