"""Unit tests for Phase 3: Lexical retrieval, silence gate, and read-only tools."""
from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path
import pytest

from backend.app.agent.tools import DocumentTools
from backend.app.retrieval.lexical import MAX_CHUNKS, search_lexical
from backend.app.retrieval.silence import (
    STATUS_INSUFFICIENT_EVIDENCE,
    STATUS_LOCATED,
    STATUS_NOT_LOCATED,
    check_silence,
)
from backend.app.store.db import open_doc_db


@pytest.fixture
def test_db(tmp_path: Path) -> sqlite3.Connection:
    """Create a test document SQLite database with schema and triggers."""
    db_file = tmp_path / "test_doc.sqlite3"
    con = open_doc_db(db_file)

    # Insert document record
    con.execute(
        """
        INSERT INTO document (document_id, sha256, file_type, page_count, has_unread_pages, status)
        VALUES ('doc123', 'fake_sha', 'pdf', 3, 0, 'ready')
        """
    )

    # Insert pages (all readable and English supported by default)
    for p in range(1, 4):
        con.execute(
            """
            INSERT INTO pages (page_num, norm_text, text_hash, is_readable, lang_supported)
            VALUES (?, ?, ?, 1, 1)
            """,
            (p, f"Page {p} content", f"hash_{p}"),
        )

    con.commit()
    yield con
    con.close()


def test_12_chunk_cap_lexical_search(test_db: sqlite3.Connection):
    """Assert search_lexical never returns more than 12 chunks even if 25 match."""
    # Insert 25 matching sentences
    for i in range(25):
        test_db.execute(
            """
            INSERT INTO sentences (sid, page_num, section, start_offset, end_offset, sentence_text)
            VALUES (?, 1, 'Rent Section', ?, ?, ?)
            """,
            (f"s_rent_{i}", i * 10, (i + 1) * 10, f"The tenant shall pay monthly rent {i} on the first."),
        )
    test_db.commit()

    hits = search_lexical(test_db, query="rent", limit=20)
    assert len(hits) == 12
    assert len(hits) == MAX_CHUNKS


def test_12_chunk_cap_tools(test_db: sqlite3.Connection):
    """Assert every tool output is capped at 12 chunks."""
    # Insert 20 sentences into section 5 on page 1
    for i in range(20):
        test_db.execute(
            """
            INSERT INTO sentences (sid, page_num, section, start_offset, end_offset, sentence_text)
            VALUES (?, 1, '5. Maintenance', ?, ?, ?)
            """,
            (f"s_maint_{i}", i * 20, (i + 1) * 20, f"Maintenance charge rule number {i} applies."),
        )
    test_db.commit()

    tools = DocumentTools(test_db)

    # 1. search_document
    res_search = tools.search_document("maintenance")
    assert len(res_search) <= 12

    # 2. get_page
    res_page = tools.get_page(1)
    assert len(res_page) <= 12

    # 3. get_section
    res_sec = tools.get_section("5. Maintenance")
    assert len(res_sec) <= 12

    # 4. find_related_clauses
    res_related = tools.find_related_clauses("s_maint_0")
    assert len(res_related) <= 12

    # 5. check_document_silence
    res_silence = tools.check_document_silence("maintenance")
    assert len(res_silence["hits"]) <= 12


def test_silence_gate_not_located(test_db: sqlite3.Connection):
    """
    NOT_LOCATED is returned IF AND ONLY IF:
    - no unread pages exist,
    - language is supported,
    - searches yield zero results.
    """
    # Insert sentences about rent only
    test_db.execute(
        """
        INSERT INTO sentences (sid, page_num, section, start_offset, end_offset, sentence_text)
        VALUES ('s1', 1, '1. Rent', 0, 50, 'Monthly rent shall be twenty thousand.')
        """
    )
    test_db.commit()

    # Query for absent topic (e.g. disputes/arbitration)
    result = check_silence(test_db, topic="disputes")
    assert result.status == STATUS_NOT_LOCATED
    assert result.coverage_complete is True
    assert len(result.hits) == 0
    assert "could not locate a provision about 'disputes'" in result.explanation


def test_silence_gate_insufficient_evidence_unread_pages(test_db: sqlite3.Connection):
    """Zero hits + unread pages in document -> INSUFFICIENT_EVIDENCE (not silent)."""
    # Mark document as having unread pages
    test_db.execute("UPDATE document SET has_unread_pages = 1")
    test_db.commit()

    result = check_silence(test_db, topic="disputes")
    assert result.status == STATUS_INSUFFICIENT_EVIDENCE
    assert result.coverage_complete is False
    assert "unread or uninspected pages" in result.explanation


def test_silence_gate_insufficient_evidence_unreadable_page(test_db: sqlite3.Connection):
    """Zero hits + unreadable page -> INSUFFICIENT_EVIDENCE."""
    test_db.execute("UPDATE pages SET is_readable = 0 WHERE page_num = 2")
    test_db.commit()

    result = check_silence(test_db, topic="disputes")
    assert result.status == STATUS_INSUFFICIENT_EVIDENCE
    assert result.coverage_complete is False
    assert "unreadable page" in result.explanation


def test_silence_gate_insufficient_evidence_unsupported_language(test_db: sqlite3.Connection):
    """Zero hits + unsupported language page -> INSUFFICIENT_EVIDENCE."""
    test_db.execute("UPDATE pages SET lang_supported = 0 WHERE page_num = 3")
    test_db.commit()

    result = check_silence(test_db, topic="disputes")
    assert result.status == STATUS_INSUFFICIENT_EVIDENCE
    assert result.coverage_complete is False
    assert "unsupported language" in result.explanation


def test_silence_gate_located(test_db: sqlite3.Connection):
    """Matches present -> LOCATED."""
    test_db.execute(
        """
        INSERT INTO sentences (sid, page_num, section, start_offset, end_offset, sentence_text)
        VALUES ('s_dep', 1, '2. Deposit', 0, 80, 'The tenant has paid a refundable security deposit of 50000.')
        """
    )
    test_db.commit()

    result = check_silence(test_db, topic="deposit")
    assert result.status == STATUS_LOCATED
    assert len(result.hits) > 0
    assert result.hits[0].sid == "s_dep"


def test_cross_reference_expansion(test_db: sqlite3.Connection):
    """Verify deterministic cross-reference expansion finds referenced clause."""
    # Sentence 1 references clause 4
    test_db.execute(
        """
        INSERT INTO sentences (sid, page_num, section, start_offset, end_offset, sentence_text)
        VALUES ('s_main', 1, '1. Terms', 0, 60, 'Notice period is 30 days subject to clause 4.')
        """
    )
    # Sentence 2 is clause 4
    test_db.execute(
        """
        INSERT INTO sentences (sid, page_num, section, start_offset, end_offset, sentence_text)
        VALUES ('s_ref', 2, '4. Exceptions', 0, 70, 'Clause 4. In case of emergency no notice is required.')
        """
    )
    test_db.commit()

    hits = search_lexical(test_db, query="Notice period", expand_xrefs=True)
    hit_sids = [h.sid for h in hits]
    assert "s_main" in hit_sids
    assert "s_ref" in hit_sids


def test_tool_context_binding_no_document_id():
    """Verify tools are bound to document context and DO NOT accept document_id parameter."""
    tools = DocumentTools(con=sqlite3.connect(":memory:"))
    methods = [
        tools.search_document,
        tools.get_evidence,
        tools.get_page,
        tools.get_section,
        tools.get_document_map,
        tools.find_related_clauses,
        tools.check_document_silence,
    ]

    for method in methods:
        sig = inspect.signature(method)
        assert "document_id" not in sig.parameters, f"{method.__name__} must not accept document_id"
