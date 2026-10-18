"""API: /api/documents/{document_id}/ask — trigger bounded question answering."""
from __future__ import annotations

import logging
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.agent.runtime import BoundedRuntime
from backend.app.config import get_settings
from backend.app.model.ollama_native import OllamaNativeProvider
from backend.app.model.provider import ErrorLocalModelUnavailable
from backend.app.security.auth import require_token
from backend.app.store.db import open_doc_db
from backend.app.validation.renderer import RenderedAnswer

logger = logging.getLogger("lexiguard.api.ask")
router = APIRouter()

AuthDep = Annotated[str, Depends(require_token)]


class AskRequest(BaseModel):
    question: str = Field(..., max_length=500, description="User question about the document")


@router.post(
    "/documents/{document_id}/ask",
    response_model=RenderedAnswer,
    status_code=status.HTTP_200_OK,
)
async def ask_document(
    document_id: str,
    body: AskRequest,
    _token: AuthDep,
) -> RenderedAnswer:
    """
    Trigger the bounded runtime to answer a question about the document.
    Enforces token authentication, hard limits, and verified local retrieval.
    """
    settings = get_settings()
    db_path = settings.data_dir / document_id / "doc.sqlite3"

    if not db_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )

    con = open_doc_db(db_path)
    try:
        # Attempt to initialize Ollama provider (falls back to extractive if unavailable)
        provider = None
        try:
            provider = OllamaNativeProvider(base_url=settings.ollama_base_url, model=settings.model_tag)
        except ErrorLocalModelUnavailable as exc:
            logger.info("Local Ollama model unavailable (%s); using extractive fallback.", exc)
        except Exception as exc:
            logger.warning("Could not reach Ollama: %s", exc)

        runtime = BoundedRuntime(con=con, provider=provider)
        result = runtime.run(body.question)
        return result
    finally:
        con.close()
