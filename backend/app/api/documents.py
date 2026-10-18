"""API: /api/documents — upload, list, overview, ask, delete."""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel

from backend.app.security.auth import require_token
from backend.app.config import get_settings

logger = logging.getLogger("lexiguard.api.documents")
router = APIRouter()

AuthDep = Annotated[str, Depends(require_token)]


# ── Response schemas ──────────────────────────────────────────────────────────

class DocumentCard(BaseModel):
    document_id: str
    page_count: int
    status: str           # "ready" | "processing" | "error"
    quality_summary: str
    warnings: list[str]
    created_at: str


class UploadResponse(BaseModel):
    document_id: str
    page_count: int
    quality: dict[str, object]
    warnings: list[str]
    status: str


class DeleteResponse(BaseModel):
    document_id: str
    app_files_removed: bool
    fts_rows_removed: bool
    directory_absent: bool
    note: str


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/documents",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/documents/",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def upload_document(
    _token: AuthDep,
    file: UploadFile = File(...),
) -> UploadResponse:
    """
    Validate, parse and ingest a PDF or TXT file.

    - Validates magic bytes (not filename extension).
    - Enforces size, page count, text-size caps.
    - Rejects encrypted, empty and malformed files.
    - Runs the pypdfium2 parser in a child process with timeout + output cap.
    - Stores per-document SQLite/FTS5 DB under data/docs/<doc_id>/.
    """
    from backend.app.ingest.worker import ingest_document

    settings = get_settings()

    # Read upload into memory (guarded by max_upload_bytes in the worker).
    raw = await file.read(settings.max_upload_bytes + 1)
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum upload size of {settings.max_upload_bytes} bytes.",
        )
    if len(raw) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty.",
        )

    # Filename is NOT used as a path component. It is only used to hint at TXT
    # when magic bytes are ambiguous — but is never logged or put in prompts.
    filename_hint = (file.filename or "").lower()

    try:
        result = await ingest_document(raw, filename_hint)
    except ValueError as exc:
        logger.error("Document upload failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return UploadResponse(
        document_id=result.document_id,
        page_count=result.page_count,
        quality=result.quality,
        warnings=result.warnings,
        status=result.status,
    )


@router.get("/documents", response_model=list[DocumentCard])
@router.get("/documents/", response_model=list[DocumentCard], include_in_schema=False)
async def list_documents(_token: AuthDep) -> list[DocumentCard]:
    """Return a list of locally stored document cards (display metadata only)."""
    from backend.app.store.documents import list_all_documents

    return [
        DocumentCard(
            document_id=d.document_id,
            page_count=d.page_count,
            status=d.status,
            quality_summary=d.quality_summary,
            warnings=d.warnings,
            created_at=d.created_at,
        )
        for d in list_all_documents()
    ]


@router.delete("/documents/{document_id}", response_model=DeleteResponse)
async def delete_document(
    document_id: str,
    _token: AuthDep,
) -> DeleteResponse:
    """
    Safely delete all data for a document.

    Steps (Guide §5.3):
    1. Reject new work for the document.
    2. Close SQLite connections.
    3. Remove the per-document directory and verify removal.
    4. Return a result distinguishing app-controlled removal from forensic erasure.
    """
    from backend.app.store.delete import safe_delete_document

    result = await safe_delete_document(document_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return DeleteResponse(
        document_id=document_id,
        app_files_removed=result.app_files_removed,
        fts_rows_removed=result.fts_rows_removed,
        directory_absent=result.directory_absent,
        note=(
            "App-controlled files removed. "
            "This does NOT constitute forensic erasure from SSD, OS swap, "
            "or external backups. See docs/LIMITATIONS.md."
        ),
    )


@router.get("/documents/{document_id}/pages/{page_num}")
async def get_page(
    document_id: str,
    page_num: int,
    _token: AuthDep,
) -> Response:
    """Return normalized page text for source viewer (no-store)."""
    from backend.app.store.pages import get_page_text

    text = get_page_text(document_id, page_num)
    if text is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    return Response(
        content=text,
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
