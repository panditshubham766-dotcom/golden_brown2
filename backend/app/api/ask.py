"""
API: Single-Pass RAG pipeline for document question-answering.

Endpoints:
  POST /api/documents/{document_id}/ask       — single-pass BM25 → Gemma QA
  POST /api/documents/{document_id}/review    — Core 10 topic risk assessment
  POST /api/documents/{document_id}/summarize — structured document overview

All processing is strictly local (127.0.0.1 only). Zero external egress.
No dense retrieval, no FAISS, no verdict generation.
"""
from __future__ import annotations

import logging
import re
import secrets
from typing import Annotated, List, Optional

import requests as _requests
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.config import get_settings
from backend.app.model.ollama_native import OllamaNativeProvider
from backend.app.model.provider import ErrorLocalModelUnavailable
from backend.app.retrieval.lexical import load_rental_topics, search_lexical, SearchHit
from backend.app.security.auth import require_token
from backend.app.store.db import open_doc_db
from backend.app.validation.renderer import EvidenceItem

logger = logging.getLogger("lexiguard.api.ask")
router = APIRouter()

AuthDep = Annotated[str, Depends(require_token)]

# ─── Ollama base URL / model helpers ─────────────────────────────────────────

def _ollama_chat(
    base_url: str,
    model: str,
    messages: list,
    timeout: float = 90.0,
) -> str:
    """
    Fire a single non-streaming chat request to Ollama.
    Returns the assistant message content string.
    Raises RuntimeError on any failure so callers can fall back gracefully.
    """
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0,
            "seed": 42,
            "num_ctx": 8192,
        },
    }
    try:
        resp = _requests.post(
            f"{base_url.rstrip('/')}/api/chat",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "").strip()
    except Exception as exc:
        raise RuntimeError(f"Ollama call failed: {exc}") from exc


def _ollama_available(base_url: str, model: str) -> bool:
    """Quick check: is Ollama reachable and does it have the model?"""
    try:
        provider = OllamaNativeProvider(base_url=base_url, model=model, timeout=5.0)
        _ = provider  # just validate
        return True
    except (ErrorLocalModelUnavailable, Exception):
        return False


# ═══════════════════════════════════════════════════════════════════════════════
#  POST /api/documents/{document_id}/ask  — Single-Pass RAG
# ═══════════════════════════════════════════════════════════════════════════════

class AskRequest(BaseModel):
    question: str = Field(..., max_length=500, description="User question about the document")


class PageCitation(BaseModel):
    page: int
    snippet: str
    section: str = ""


class AskResponse(BaseModel):
    status: str
    answer: str
    citations: List[PageCitation] = Field(default_factory=list)
    fallback: bool = False
    legal_verdict: None = None  # Always null — non-verdict policy


@router.post(
    "/documents/{document_id}/ask",
    response_model=AskResponse,
    status_code=status.HTTP_200_OK,
)
async def ask_document(
    document_id: str,
    body: AskRequest,
    _token: AuthDep,
) -> AskResponse:
    """
    Single-Pass RAG pipeline:

    Step 1 — BM25 SEARCH: Query SQLite FTS5 index for the top 5 most relevant
              chunks from the specific document.
    Step 2 — CONTEXTUALIZE: Inject chunks into a strict grounded system prompt.
    Step 3 — SYNTHESIZE: Call local Ollama Gemma with the bounded prompt.
              The model is instructed to answer using ONLY the provided chunks,
              cite page numbers, and reply 'The document does not contain this
              information.' when the answer is absent.

    Falls back to extractive top-chunk presentation when Ollama is unavailable.
    All processing bound to 127.0.0.1. No external egress. No legal verdicts.
    """
    settings = get_settings()
    db_path = settings.data_dir / document_id / "doc.sqlite3"

    if not db_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )

    # ── Summary-intent interception ───────────────────────────────────────────
    # If the question is a summarization request, delegate to the summarize
    # pipeline and return a formatted answer instead of running BM25 keyword search.
    _SUMMARY_INTENTS = {
        "summarize", "summarise", "summary", "overview", "what is this document",
        "what does this document", "give me an overview", "document about",
        "tell me about this", "give me a summary", "briefly describe",
        "what is this about", "describe this document",
    }
    q_lower = body.question.lower().strip()
    is_summary_intent = any(kw in q_lower for kw in _SUMMARY_INTENTS)

    if is_summary_intent:
        # Delegate directly to summarize_document logic
        con = open_doc_db(db_path)
        try:
            total_pages = _page_count(con)
            chunks = (
                _gather_page_chunks(con, max_pages=total_pages)
                if total_pages <= 8
                else _gather_landmark_chunks(con, max_chunks=20)
            )
            all_pages = sorted({c["page"] for c in chunks})

            if not chunks:
                return AskResponse(
                    status="NOT_LOCATED",
                    answer="The document appears to be empty or could not be read.",
                    citations=[],
                    fallback=True,
                )

            # Try Ollama; fall back to extractive
            if _ollama_available(settings.ollama_base_url, settings.model_tag):
                nonce = secrets.token_hex(6)
                evidence_block = (
                    f"<<EVIDENCE-{nonce}>>\n"
                    + "\n".join(f"[Page {c['page']}] ({c['section']}) {c['text']}" for c in chunks)
                    + f"\n<<END-EVIDENCE-{nonce}>>"
                )
                system_prompt = (
                    "You are LexiGuard, a private legal-document triage assistant.\n"
                    "Using ONLY the evidence provided, give a concise document overview covering:\n"
                    "1. Document Type & Parties\n2. Effective Date & Term\n"
                    "3. Core Obligations\n4. Critical Clauses (rent, deposit, notice)\n"
                    "5. Notable Risks\n"
                    "Always cite page numbers. Keep it under 200 words. No legal conclusions."
                )
                try:
                    answer = _ollama_chat(
                        base_url=settings.ollama_base_url,
                        model=settings.model_tag,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": f"Evidence:\n{evidence_block}"},
                        ],
                    )
                    return AskResponse(
                        status="ANSWERED",
                        answer=answer,
                        citations=[PageCitation(page=p, snippet="", section="") for p in all_pages[:5]],
                        fallback=False,
                    )
                except RuntimeError:
                    pass  # Fall through to extractive

            # Extractive summary fallback
            _md, key_points, ref_pages = _build_extractive_summary(chunks)
            if key_points:
                lines = [f"**{kp.label}**: {kp.value}" for kp in key_points[:5]]
                answer = "\n".join(lines)
            else:
                answer = "The document was indexed but no landmark clauses were located via keyword search."
            return AskResponse(
                status="ANSWERED",
                answer=answer,
                citations=[PageCitation(page=p, snippet="", section="") for p in ref_pages[:5]],
                fallback=True,
            )
        finally:
            con.close()

    con = open_doc_db(db_path)
    try:
        # ── Step 1: BM25 Lexical Search ──────────────────────────────────────
        hits: List[SearchHit] = search_lexical(con, query=body.question, limit=5)

        if not hits:
            return AskResponse(
                status="NOT_LOCATED",
                answer="The document does not contain information relevant to this question.",
                citations=[],
                fallback=False,
            )

        # ── Build citations from hits ─────────────────────────────────────────
        citations = [
            PageCitation(
                page=h.page_num,
                snippet=h.sentence_text[:300],
                section=h.section or "",
            )
            for h in hits
        ]

        # ── Step 2: Contextualize — build grounded prompt ────────────────────
        nonce = secrets.token_hex(6)
        chunk_lines = [
            f"[Chunk {i+1} | Page {h.page_num} | Section: {h.section or 'N/A'}]\n{h.sentence_text}"
            for i, h in enumerate(hits)
        ]
        chunks_block = (
            f"<<DOCUMENT-CHUNKS-{nonce}>>\n"
            + "\n\n".join(chunk_lines)
            + f"\n<<END-CHUNKS-{nonce}>>"
        )

        system_prompt = (
            "You are LexiGuard, a private legal-document triage assistant.\n"
            "You will be given a set of document chunks and a user question.\n\n"
            "STRICT RULES:\n"
            "1. Answer the user's question using ONLY the provided document chunks.\n"
            "2. Do NOT use any outside knowledge or general legal principles.\n"
            "3. If the answer is not in the chunks, reply exactly:\n"
            "   'The document does not contain this information.'\n"
            "4. Always cite the page number(s) where you found the information,\n"
            "   e.g. '(Page 2)' or '(Pages 1, 3)'.\n"
            "5. Do NOT make legal conclusions, enforceability assessments, or predictions.\n"
            "6. Keep your answer concise — 3-5 sentences maximum.\n"
        )
        user_prompt = f"{chunks_block}\n\nQuestion: {body.question}"

        # ── Step 3: Synthesize with local Ollama Gemma ───────────────────────
        if not _ollama_available(settings.ollama_base_url, settings.model_tag):
            # Extractive fallback: top chunk text as the answer
            top = hits[0]
            answer = (
                f"{top.sentence_text} (Page {top.page_num})"
                if top.sentence_text
                else "The document does not contain this information."
            )
            return AskResponse(
                status="ANSWERED",
                answer=answer,
                citations=citations,
                fallback=True,
            )

        try:
            answer = _ollama_chat(
                base_url=settings.ollama_base_url,
                model=settings.model_tag,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except RuntimeError as exc:
            logger.warning("Ollama call failed for /ask (%s); extractive fallback.", exc)
            top = hits[0]
            answer = f"{top.sentence_text} (Page {top.page_num})"
            return AskResponse(
                status="ANSWERED",
                answer=answer,
                citations=citations,
                fallback=True,
            )

        return AskResponse(
            status="ANSWERED",
            answer=answer,
            citations=citations,
            fallback=False,
        )
    finally:
        con.close()


# ═══════════════════════════════════════════════════════════════════════════════
#  POST /api/documents/{document_id}/review  — Core 10 Risk Assessment
# ═══════════════════════════════════════════════════════════════════════════════

class ReviewTopic(BaseModel):
    topic_id: str
    label: str
    status: str
    evidence: List[EvidenceItem] = Field(default_factory=list)
    attention_reason: Optional[str] = None


class ProfessionalQuestion(BaseModel):
    question_id: str
    text: str
    evidence: List[EvidenceItem] = Field(default_factory=list)


class ReviewResponse(BaseModel):
    topics: List[ReviewTopic] = Field(default_factory=list)
    professional_questions: List[ProfessionalQuestion] = Field(default_factory=list)


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
    Assess Core 10 rental topics for the document via BM25 retrieval.
    Returns FOUND / NOT_FOUND status and neutral professional questions.
    No legal verdicts. No external calls.
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
        topics_result: List[ReviewTopic] = []

        for topic_key, topic_data in topics_dict.items():
            label = topic_data.get("label", topic_key.replace("_", " ").title())
            hits = search_lexical(con, topic=topic_key, limit=3)

            evidence_items: List[EvidenceItem] = []
            for h in hits:
                evidence_items.append(
                    EvidenceItem(
                        sid=h.sid,
                        page=h.page_num,
                        section=h.section or label,
                        quote=h.sentence_text,
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


# ═══════════════════════════════════════════════════════════════════════════════
#  POST /api/documents/{document_id}/summarize  — Structured Document Overview
# ═══════════════════════════════════════════════════════════════════════════════

# Landmark topics for chunk selection
_LANDMARK_TOPICS = ["parties", "term", "rent", "deposit", "notice", "penalties", "disputes"]
_LABEL_MAP = {
    "parties": "Identified Parties",
    "term": "Effective Date & Term",
    "rent": "Rent / Licence Fee",
    "deposit": "Security Deposit",
    "notice": "Notice Period",
    "penalties": "Penalties & Late Fees",
    "disputes": "Dispute Resolution",
}


class SummaryKeyPoint(BaseModel):
    label: str
    value: str
    page_refs: List[int] = Field(default_factory=list)


class SummaryResponse(BaseModel):
    document_id: str
    summary_markdown: str
    key_points: List[SummaryKeyPoint] = Field(default_factory=list)
    referenced_pages: List[int] = Field(default_factory=list)
    model_used: str
    fallback: bool = False


def _page_count(con) -> int:
    row = con.execute("SELECT MAX(page_num) AS mp FROM sentences").fetchone()
    return int(row["mp"]) if row and row["mp"] else 1


def _gather_page_chunks(con, max_pages: int = 8) -> List[dict]:
    """Aggregate all sentences for small documents."""
    rows = con.execute(
        "SELECT sid, page_num, section, sentence_text FROM sentences "
        "WHERE page_num <= ? ORDER BY page_num, rowid",
        (max_pages,),
    ).fetchall()
    return [
        {"sid": r["sid"], "page": r["page_num"], "section": r["section"] or "", "text": r["sentence_text"]}
        for r in rows
    ]


def _gather_landmark_chunks(con, max_chunks: int = 20) -> List[dict]:
    """Select top BM25 chunks for landmark rental topics (large documents)."""
    seen: set = set()
    chunks: List[dict] = []
    for topic_key in _LANDMARK_TOPICS:
        hits = search_lexical(con, topic=topic_key, limit=4)
        for h in hits:
            if h.sid not in seen:
                seen.add(h.sid)
                chunks.append({
                    "sid": h.sid, "page": h.page_num,
                    "section": h.section or "", "text": h.sentence_text,
                })
            if len(chunks) >= max_chunks:
                return chunks
    return chunks


def _build_extractive_summary(chunks: List[dict]) -> tuple:
    """Produce a plain extractive summary without any LLM call."""
    pages: set = set()
    topic_snippets: dict = {}
    topic_pages: dict = {}

    for c in chunks:
        pages.add(c["page"])
        haystack = (c["section"] + " " + c["text"]).lower()
        for topic in _LANDMARK_TOPICS:
            if topic not in topic_snippets and topic.replace("_", " ") in haystack:
                topic_snippets[topic] = c["text"][:250]
                topic_pages.setdefault(topic, []).append(c["page"])

    key_points: List[SummaryKeyPoint] = []
    for t, snippet in topic_snippets.items():
        key_points.append(SummaryKeyPoint(
            label=_LABEL_MAP.get(t, t.title()),
            value=snippet,
            page_refs=topic_pages.get(t, []),
        ))

    md_lines = ["## Document Overview (Extractive)\n"]
    for kp in key_points:
        md_lines.append(f"**{kp.label}**  \n{kp.value}\n")
    if not key_points:
        md_lines.append("_No landmark clauses located via lexical search._")

    return "\n".join(md_lines), key_points, sorted(pages)


@router.post(
    "/documents/{document_id}/summarize",
    response_model=SummaryResponse,
    status_code=status.HTTP_200_OK,
)
async def summarize_document(
    document_id: str,
    _token: AuthDep,
) -> SummaryResponse:
    """
    Generate a structured document overview (strictly local — 127.0.0.1 only).

    - Small docs (<= 8 pages): aggregates all page text.
    - Large docs: selects top BM25 landmark chunks (preamble, parties, covenants,
      termination, penalties).
    - Constructs a bounded 5-field Gemma prompt extracting: parties, dates, purpose,
      critical clauses, and notable risks.
    - Falls back to extractive BM25 summary when Ollama is unavailable.
    - Zero external egress. No dense embeddings. No FAISS.
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
        total_pages = _page_count(con)
        chunks = (
            _gather_page_chunks(con, max_pages=total_pages)
            if total_pages <= 8
            else _gather_landmark_chunks(con, max_chunks=20)
        )
        all_pages = sorted({c["page"] for c in chunks})

        # Extractive fallback if Ollama not available or no chunks
        if not chunks or not _ollama_available(settings.ollama_base_url, settings.model_tag):
            md, key_points, ref_pages = _build_extractive_summary(chunks)
            return SummaryResponse(
                document_id=document_id,
                summary_markdown=md,
                key_points=key_points,
                referenced_pages=ref_pages,
                model_used="extractive-bm25",
                fallback=True,
            )

        # Bounded 5-field Gemma prompt
        nonce = secrets.token_hex(6)
        evidence_block = (
            f"<<EVIDENCE-{nonce}>>\n"
            + "\n".join(f"[Page {c['page']}] ({c['section']}) {c['text']}" for c in chunks)
            + f"\n<<END-EVIDENCE-{nonce}>>"
        )
        system_prompt = (
            "You are LexiGuard, a private legal-document triage assistant.\n"
            "Using ONLY the evidence provided, extract a structured document overview.\n"
            "Respond with exactly this markdown structure — no extra sections:\n\n"
            "## Document Overview\n"
            "**Document Type & Identified Parties**  \n<value>\n\n"
            "**Effective Date & Term/Duration**  \n<value>\n\n"
            "**Core Purpose / Key Obligations**  \n<value>\n\n"
            "**Critical Clauses** *(rent, deposit, notice, lock-in, penalties)*  \n<value>\n\n"
            "**Notable Risks / Items Requiring Attention**  \n<value>\n\n"
            "Rules:\n"
            "- Extract facts ONLY from the evidence. Do NOT invent values.\n"
            "- Do NOT make legal conclusions or evaluate enforceability.\n"
            "- If a field is not found, write: *Not located in document.*\n"
            "- Always cite page numbers, e.g. (Page 2).\n"
            "- Keep each value to 2-3 sentences maximum.\n"
        )

        try:
            raw_md = _ollama_chat(
                base_url=settings.ollama_base_url,
                model=settings.model_tag,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Evidence:\n{evidence_block}"},
                ],
            )
        except RuntimeError as exc:
            logger.warning("Gemma summarise call failed (%s); extractive fallback.", exc)
            md, key_points, ref_pages = _build_extractive_summary(chunks)
            return SummaryResponse(
                document_id=document_id,
                summary_markdown=md,
                key_points=key_points,
                referenced_pages=ref_pages,
                model_used="extractive-bm25",
                fallback=True,
            )

        # Parse 5-field markdown into structured key_points
        key_points_out: List[SummaryKeyPoint] = []
        for label in [
            "Document Type & Identified Parties",
            "Effective Date & Term/Duration",
            "Core Purpose / Key Obligations",
            "Critical Clauses",
            "Notable Risks / Items Requiring Attention",
        ]:
            marker = f"**{label}"
            idx = raw_md.find(marker)
            if idx == -1:
                continue
            after = raw_md[idx + len(marker):]
            newline = after.find("\n")
            value_start = after[newline + 1:].strip() if newline != -1 else after.strip()
            end_bold = value_start.find("\n**")
            end_hdr = value_start.find("\n##")
            end = min(
                end_bold if end_bold != -1 else len(value_start),
                end_hdr if end_hdr != -1 else len(value_start),
            )
            value = value_start[:end].strip().replace("\n", " ")
            if value:
                page_refs = [int(m) for m in re.findall(r"\bPage (\d+)\b", value, re.IGNORECASE)]
                key_points_out.append(SummaryKeyPoint(label=label, value=value, page_refs=page_refs))

        return SummaryResponse(
            document_id=document_id,
            summary_markdown=raw_md,
            key_points=key_points_out,
            referenced_pages=all_pages,
            model_used=settings.model_tag,
            fallback=False,
        )
    finally:
        con.close()
