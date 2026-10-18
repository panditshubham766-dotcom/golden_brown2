"""
Ingest worker: orchestrates the full ingestion pipeline for one document.

Steps:
1. Validate upload (magic bytes, size, encoding).
2. Generate doc_id (random 128-bit; never the filename).
3. Run parser in a child process with timeout + output cap.
4. Validate parser output.
5. Normalise text, run quality + language gates per page.
6. Segment into sentences.
7. Write per-document SQLite/FTS5 store.
8. Return IngestResult.

Nothing about the filename, file metadata or user identity is logged.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import secrets
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.app.config import get_settings
from backend.app.ingest.upload import validate_upload, UploadValidationError
from backend.app.ingest.normalize import normalise
from backend.app.ingest.segment import segment_page
from backend.app.ingest.quality import assess_page
from backend.app.ingest.language import assess_language, apply_majority_language

logger = logging.getLogger("lexiguard.ingest")


@dataclass
class IngestResult:
    document_id: str
    page_count: int
    quality: dict[str, Any]
    warnings: list[str]
    status: str   # "ready" | "partial" | "error"


async def ingest_document(raw: bytes, filename_hint: str) -> IngestResult:
    """
    Ingest a PDF or TXT document.

    `filename_hint` is only used to break tie when magic bytes are ambiguous
    (e.g. an empty first few bytes). It is NEVER logged or used as a path.
    """
    settings = get_settings()

    # ── 1. Upload validation ───────────────────────────────────────────────────
    try:
        file_type = validate_upload(raw, settings.max_upload_bytes)
    except UploadValidationError:
        raise

    # ── 2. Generate doc_id ────────────────────────────────────────────────────
    doc_id = secrets.token_hex(16)  # 128-bit random hex

    # Compute SHA-256 of the raw bytes for provenance tracking.
    sha256 = hashlib.sha256(raw).hexdigest()

    # ── 3. Run parser child process ───────────────────────────────────────────
    parser_result = await _run_parser(raw, file_type, settings)

    if "error" in parser_result:
        raise ValueError(parser_result["error"])

    pages_raw: list[dict[str, Any]] = parser_result.get("pages", [])
    page_count: int = parser_result.get("page_count", len(pages_raw))
    global_warnings: list[str] = parser_result.get("warnings", [])
    missing_limits: list[str] = parser_result.get("missing_limits", [])

    if missing_limits:
        for lim in missing_limits:
            logger.info("[SECURITY] Missing parser limit: %s", lim)

    if page_count > settings.max_pages:
        raise ValueError(
            f"Document has {page_count} pages; maximum is {settings.max_pages}."
        )

    # ── 4. Normalise + quality + language per page ────────────────────────────
    all_warnings: list[str] = list(global_warnings)
    page_records: list[dict[str, Any]] = []
    lang_results_all = []

    for page_raw in pages_raw:
        pnum: int = page_raw["page_num"]
        raw_text: str = page_raw.get("text", "")
        parser_page_warnings: list[str] = page_raw.get("warnings", [])

        norm_text, _ = normalise(raw_text)
        quality = assess_page(pnum, norm_text, parser_page_warnings)
        lang_result = assess_language(
            pnum,
            norm_text,
            nonlatin_threshold=settings.lang_nonlatin_threshold,
            english_fn_threshold=settings.lang_english_fn_threshold,
            min_tokens=settings.lang_min_tokens_for_fn_test,
        )
        lang_results_all.append(lang_result)

        all_warnings.extend(quality.warnings)
        if lang_result.warning:
            all_warnings.append(lang_result.warning)

        page_records.append({
            "page_num": pnum,
            "norm_text": norm_text,
            "quality": quality,
            "lang": lang_result,
        })

    # Apply majority language to short pages.
    lang_results_all = apply_majority_language(
        lang_results_all, settings.lang_min_tokens_for_fn_test
    )
    # Re-apply updated lang results to page_records.
    for i, lr in enumerate(lang_results_all):
        page_records[i]["lang"] = lr
        if lr.warning and lr.warning not in all_warnings:
            all_warnings.append(lr.warning)

    # ── 5. Segment into sentences ─────────────────────────────────────────────
    all_sentences = []
    for pr in page_records:
        if not pr["lang"].supported:
            continue  # exclude unread pages from segmentation
        if not pr["quality"].is_readable:
            continue  # exclude image-only / garbled pages
        sents = segment_page(doc_id, pr["page_num"], pr["norm_text"])
        all_sentences.extend(sents)

    # ── 6. Persist to SQLite/FTS5 ─────────────────────────────────────────────
    doc_dir = settings.data_dir / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    from backend.app.store.db import open_doc_db
    from backend.app.store.documents import insert_document
    from backend.app.store.pages import insert_page
    from backend.app.store.sentences import insert_sentences
    from backend.app.store.fts import build_fts_index

    con = open_doc_db(doc_dir / "doc.sqlite3")
    try:
        insert_document(
            con,
            document_id=doc_id,
            sha256=sha256,
            file_type=file_type,
            page_count=page_count,
            has_unread_pages=any(not lr.supported for lr in lang_results_all),
        )

        for pr in page_records:
            insert_page(
                con,
                doc_id=doc_id,
                page_num=pr["page_num"],
                norm_text=pr["norm_text"],
                is_readable=pr["quality"].is_readable,
                lang_supported=pr["lang"].supported,
                warnings=pr["quality"].warnings + (
                    [pr["lang"].warning] if pr["lang"].warning else []
                ),
            )

        insert_sentences(con, all_sentences)
        build_fts_index(con, all_sentences)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    # ── 7. Determine status ────────────────────────────────────────────────────
    unread_count = sum(1 for lr in lang_results_all if not lr.supported)
    image_only_count = sum(1 for pr in page_records if pr["quality"].is_image_only)
    if unread_count == page_count or image_only_count == page_count:
        status = "partial"
    else:
        status = "ready"

    quality_summary: dict[str, Any] = {
        "total_pages": page_count,
        "readable_pages": sum(1 for pr in page_records if pr["quality"].is_readable),
        "unread_language_pages": unread_count,
        "image_only_pages": image_only_count,
        "sentence_count": len(all_sentences),
        "missing_parser_limits": missing_limits,
    }

    logger.info(
        "Ingested document %s: %d pages, %d sentences, status=%s",
        doc_id, page_count, len(all_sentences), status,
    )

    return IngestResult(
        document_id=doc_id,
        page_count=page_count,
        quality=quality_summary,
        warnings=all_warnings,
        status=status,
    )


async def _run_parser(
    raw: bytes,
    file_type: str,
    settings: Any,
) -> dict[str, Any]:
    """Spawn the parser as a child process with timeout + output cap."""
    envelope = {
        "file_type": file_type,
        "raw_b64": base64.b64encode(raw).decode(),
        "max_pages": settings.max_pages,
        "max_text_bytes": settings.max_text_bytes,
        "virtual_page_chars": settings.txt_virtual_page_chars,
        "cpu_seconds": 60,
        "max_address_bytes": 512 * 1024 * 1024,
    }
    input_bytes = json.dumps(envelope).encode()

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "backend.app.ingest.parser",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=input_bytes),
                timeout=settings.parser_timeout_seconds,
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise ValueError(
                f"Document parsing timed out after {settings.parser_timeout_seconds}s. "
                "The file may be too complex or too large."
            )
    except FileNotFoundError:
        raise ValueError("Python interpreter not found; cannot run parser subprocess.")

    # Output cap.
    if len(stdout) > settings.parser_output_cap_bytes:
        raise ValueError("Parser output exceeded the maximum allowed size.")

    if proc.returncode != 0:
        # Log stderr at debug level only (may contain internal info).
        logger.debug("Parser process stderr: %s", stderr.decode(errors="replace")[:512])
        raise ValueError(
            "Document parser exited with an error. "
            "The file may be malformed, encrypted, or unsupported."
        )

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Parser returned invalid JSON: {exc}") from exc
