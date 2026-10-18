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
from backend.app.validation.renderer import RenderedAnswer, EvidenceItem
from backend.app.retrieval.lexical import load_rental_topics, search_lexical

logger = logging.getLogger("lexiguard.api.ask")
router = APIRouter()

AuthDep = Annotated[str, Depends(require_token)]


class AskRequest(BaseModel):
    question: str = Field(..., max_length=500, description="User question about the document")


class ReviewTopic(BaseModel):
    topic_id: str
    label: str
    status: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    attention_reason: str | None = None


class ProfessionalQuestion(BaseModel):
    question_id: str
    text: str
    evidence: list[EvidenceItem] = Field(default_factory=list)


class ReviewResponse(BaseModel):
    topics: list[ReviewTopic] = Field(default_factory=list)
    professional_questions: list[ProfessionalQuestion] = Field(default_factory=list)


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


@router.post(
    "/documents/{document_id}/review",
    response_model=ReviewResponse,
    status_code=status.HTTP_200_OK,
)
async def review_document(
    document_id: str,
    _token: AuthDep,
) -> ReviewResponse:
    """
    Assess Core 10 topics for the document and extract evidence.
    Returns status (FOUND / NOT_FOUND / AMBIGUOUS) and neutral professional questions.
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
        topics_dict = load_rental_topics()
        topics_result: list[ReviewTopic] = []

        for topic_key, topic_data in topics_dict.items():
            label = topic_data.get("label", topic_key.replace("_", " ").title())
            hits = search_lexical(con, topic=topic_key, limit=3)

            evidence_items: list[EvidenceItem] = []
            for h in hits:
                evidence_items.append(
                    EvidenceItem(
                        sid=h.sid,
                        page=h.page_num,
                        section=label,
                        quote=h.norm_text,
                        ocr_derived=False,
                    )
                )

            if evidence_items:
                status_val = "FOUND"
                reason = None
            else:
                status_val = "NOT_FOUND"
                reason = "Not located in document"

            topics_result.append(
                ReviewTopic(
                    topic_id=topic_key,
                    label=label,
                    status=status_val,
                    evidence=evidence_items,
                    attention_reason=reason,
                )
            )

        professional_questions = [
            ProfessionalQuestion(
                question_id="pq_parties",
                text="Are the parties and property details accurately documented with full legal names and addresses?",
            ),
            ProfessionalQuestion(
                question_id="pq_deposit",
                text="Does the agreement specify clear conditions and timelines for the security deposit refund?",
            ),
            ProfessionalQuestion(
                question_id="pq_termination",
                text="Is the notice period for early termination mutual and clearly defined?",
            ),
        ]

        return ReviewResponse(
            topics=topics_result,
            professional_questions=professional_questions,
        )
    finally:
        con.close()

