"""Seven read-only retrieval tools bound to request document context.

Guarantees:
- Bound to document context: NO document_id parameter accepted.
- Strictly capped at 12 chunks per tool output.
- Nonce-delimitable data representation.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from backend.app.retrieval.lexical import MAX_CHUNKS, extract_cross_references, search_lexical
from backend.app.retrieval.silence import check_silence


class DocumentTools:
    """Document-context bound retrieval tools."""

    def __init__(self, con: sqlite3.Connection) -> None:
        """Bind tools to the active document SQLite database connection."""
        self.con = con

    def search_document(
        self,
        query: str = "",
        topic: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search document for query and/or rental topic.
        Output capped at 12 chunks.
        """
        hits = search_lexical(self.con, query=query, topic=topic, expand_xrefs=True, limit=MAX_CHUNKS)
        return [
            {
                "sid": h.sid,
                "page_num": h.page_num,
                "section": h.section,
                "sentence_text": h.sentence_text,
                "source": h.source,
            }
            for h in hits[:MAX_CHUNKS]
        ]

    def get_evidence(self, ev_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve specific evidence chunk by sid (evidence ID).
        Output capped at 12 chunks.
        """
        rows = self.con.execute(
            """
            SELECT sid, page_num, section, sentence_text
            FROM sentences
            WHERE sid = ?
            LIMIT ?
            """,
            (ev_id, MAX_CHUNKS),
        ).fetchall()

        return [
            {
                "sid": row["sid"],
                "page_num": row["page_num"],
                "section": row["section"],
                "sentence_text": row["sentence_text"],
                "source": "direct_sid",
            }
            for row in rows[:MAX_CHUNKS]
        ]

    def get_page(self, page: int) -> List[Dict[str, Any]]:
        """
        Retrieve sentences on physical page.
        Output capped at 12 chunks.
        """
        rows = self.con.execute(
            """
            SELECT sid, page_num, section, sentence_text
            FROM sentences
            WHERE page_num = ?
            ORDER BY start_offset
            LIMIT ?
            """,
            (page, MAX_CHUNKS),
        ).fetchall()

        return [
            {
                "sid": row["sid"],
                "page_num": row["page_num"],
                "section": row["section"],
                "sentence_text": row["sentence_text"],
                "source": f"page_{page}",
            }
            for row in rows[:MAX_CHUNKS]
        ]

    def get_section(self, label: str) -> List[Dict[str, Any]]:
        """
        Retrieve sentences belonging to a clause or section label.
        Output capped at 12 chunks.
        """
        rows = self.con.execute(
            """
            SELECT sid, page_num, section, sentence_text
            FROM sentences
            WHERE section = ? OR section LIKE ? OR section LIKE ?
            ORDER BY page_num, start_offset
            LIMIT ?
            """,
            (label, f"{label}.%", f"%{label}%", MAX_CHUNKS),
        ).fetchall()

        return [
            {
                "sid": row["sid"],
                "page_num": row["page_num"],
                "section": row["section"],
                "sentence_text": row["sentence_text"],
                "source": f"section_{label}",
            }
            for row in rows[:MAX_CHUNKS]
        ]

    def get_document_map(self) -> List[Dict[str, Any]]:
        """
        Retrieve document structure: distinct sections/headings and their page spans.
        Output capped at 12 chunks/items.
        """
        rows = self.con.execute(
            """
            SELECT section, MIN(page_num) AS start_page, MAX(page_num) AS end_page, COUNT(*) AS sentence_count
            FROM sentences
            WHERE section != ''
            GROUP BY section
            ORDER BY MIN(page_num), MIN(start_offset)
            LIMIT ?
            """,
            (MAX_CHUNKS,),
        ).fetchall()

        return [
            {
                "section": row["section"],
                "start_page": row["start_page"],
                "end_page": row["end_page"],
                "sentence_count": row["sentence_count"],
            }
            for row in rows[:MAX_CHUNKS]
        ]

    def find_related_clauses(self, ev_id: str) -> List[Dict[str, Any]]:
        """
        Find clauses/sentences related to ev_id via cross-reference or shared section.
        Output capped at 12 chunks.
        """
        # Fetch target sentence
        target_row = self.con.execute(
            "SELECT sid, section, sentence_text FROM sentences WHERE sid = ?",
            (ev_id,),
        ).fetchone()

        if not target_row:
            return []

        section = target_row["section"]
        text = target_row["sentence_text"]
        xrefs = extract_cross_references(text)

        related: List[Dict[str, Any]] = []
        seen_sids = {ev_id}

        # 1. First add referenced clauses
        for ref in xrefs:
            if len(related) >= MAX_CHUNKS:
                break
            rows = self.con.execute(
                """
                SELECT sid, page_num, section, sentence_text
                FROM sentences
                WHERE (section = ? OR section LIKE ? OR sentence_text LIKE ?) AND sid != ?
                ORDER BY page_num, start_offset
                LIMIT ?
                """,
                (ref, f"{ref}.%", f"%{ref}%", ev_id, MAX_CHUNKS - len(related)),
            ).fetchall()
            for r in rows:
                if r["sid"] not in seen_sids:
                    seen_sids.add(r["sid"])
                    related.append(
                        {
                            "sid": r["sid"],
                            "page_num": r["page_num"],
                            "section": r["section"],
                            "sentence_text": r["sentence_text"],
                            "source": f"xref:{ref}",
                        }
                    )
                    if len(related) >= MAX_CHUNKS:
                        break

        # 2. Add sibling sentences in the same section if room remains
        if section and len(related) < MAX_CHUNKS:
            rows = self.con.execute(
                """
                SELECT sid, page_num, section, sentence_text
                FROM sentences
                WHERE section = ? AND sid != ?
                ORDER BY page_num, start_offset
                LIMIT ?
                """,
                (section, ev_id, MAX_CHUNKS - len(related)),
            ).fetchall()
            for r in rows:
                if r["sid"] not in seen_sids:
                    seen_sids.add(r["sid"])
                    related.append(
                        {
                            "sid": r["sid"],
                            "page_num": r["page_num"],
                            "section": r["section"],
                            "sentence_text": r["sentence_text"],
                            "source": f"same_section:{section}",
                        }
                    )
                    if len(related) >= MAX_CHUNKS:
                        break

        return related[:MAX_CHUNKS]

    def check_document_silence(self, topic: str) -> Dict[str, Any]:
        """
        Run the silence gate for a topic against the document.
        Output capped at 12 chunks.
        """
        result = check_silence(self.con, topic=topic)
        return {
            "status": result.status,
            "topic": result.topic,
            "explanation": result.explanation,
            "coverage_complete": result.coverage_complete,
            "hits": [
                {
                    "sid": h.sid,
                    "page_num": h.page_num,
                    "section": h.section,
                    "sentence_text": h.sentence_text,
                    "source": h.source,
                }
                for h in result.hits[:MAX_CHUNKS]
            ],
        }
