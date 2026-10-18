"""Document table CRUD."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from backend.app.config import get_settings


@dataclass
class DocumentRecord:
    document_id: str
    page_count: int
    status: str
    quality_summary: str
    warnings: list[str]
    created_at: str


def insert_document(
    con: sqlite3.Connection,
    document_id: str,
    sha256: str,
    file_type: str,
    page_count: int,
    has_unread_pages: bool,
) -> None:
    con.execute(
        """
        INSERT INTO document (document_id, sha256, file_type, page_count, has_unread_pages, status)
        VALUES (?, ?, ?, ?, ?, 'ready')
        """,
        (document_id, sha256, file_type, page_count, int(has_unread_pages)),
    )


def get_document(con: sqlite3.Connection, document_id: str) -> sqlite3.Row | None:
    row = con.execute(
        "SELECT * FROM document WHERE document_id = ?", (document_id,)
    ).fetchone()
    return row


def list_all_documents() -> list[DocumentRecord]:
    """
    Scan data_dir for per-document directories and return display cards.
    Each directory contains a doc.sqlite3 with the document row.
    """
    settings = get_settings()
    records: list[DocumentRecord] = []

    if not settings.data_dir.exists():
        return records

    for doc_dir in sorted(settings.data_dir.iterdir()):
        if not doc_dir.is_dir():
            continue
        db_path = doc_dir / "doc.sqlite3"
        if not db_path.exists():
            continue
        try:
            from backend.app.store.db import open_doc_db
            con = open_doc_db(db_path)
            row = con.execute("SELECT * FROM document LIMIT 1").fetchone()
            con.close()
            if row:
                records.append(
                    DocumentRecord(
                        document_id=row["document_id"],
                        page_count=row["page_count"],
                        status=row["status"],
                        quality_summary=f"{row['page_count']} pages",
                        warnings=[],
                        created_at=row["created_at"],
                    )
                )
        except Exception:
            pass  # Skip corrupt directories silently

    return records
