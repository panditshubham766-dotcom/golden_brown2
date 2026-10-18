"""Pages table CRUD."""
from __future__ import annotations

import hashlib
import json
import sqlite3

from backend.app.config import get_settings


def insert_page(
    con: sqlite3.Connection,
    doc_id: str,
    page_num: int,
    norm_text: str,
    is_readable: bool,
    lang_supported: bool,
    warnings: list[str],
) -> None:
    text_hash = hashlib.sha256(norm_text.encode()).hexdigest()
    con.execute(
        """
        INSERT INTO pages (page_num, norm_text, text_hash, is_readable, lang_supported, warnings_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            page_num,
            norm_text,
            text_hash,
            int(is_readable),
            int(lang_supported),
            json.dumps(warnings),
        ),
    )


def get_page_text(document_id: str, page_num: int) -> str | None:
    """Return normalised page text for the source viewer."""
    settings = get_settings()
    db_path = settings.data_dir / document_id / "doc.sqlite3"
    if not db_path.exists():
        return None
    try:
        from backend.app.store.db import open_doc_db
        con = open_doc_db(db_path)
        row = con.execute(
            "SELECT norm_text FROM pages WHERE page_num = ?", (page_num,)
        ).fetchone()
        con.close()
        return row["norm_text"] if row else None
    except Exception:
        return None
