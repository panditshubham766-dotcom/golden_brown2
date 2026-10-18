"""RenderedAnswer builder (Guide §10.2 and Appendix A3).

Constructs server-owned response JSON. Quotes, physical pages, and sections
are loaded strictly from local SQLite storage; the model's text is never
trusted for quotes or citations.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from backend.app.agent.schema import ModelPoint


class EvidenceItem(BaseModel):
    sid: str
    page: int
    section: str
    quote: str
    ocr_derived: bool = False


class ClaimItem(BaseModel):
    claim_id: str
    text: str
    classification: str
    evidence: List[EvidenceItem] = Field(default_factory=list)


class RenderedAnswer(BaseModel):
    """Server-generated, verified response schema."""
    status: str
    answer: str
    claims: List[ClaimItem] = Field(default_factory=list)
    interpretations: List[Dict[str, Any]] = Field(default_factory=list)
    concerns: List[Dict[str, Any]] = Field(default_factory=list)
    ambiguities: List[Dict[str, Any]] = Field(default_factory=list)
    conflicts: List[Dict[str, Any]] = Field(default_factory=list)
    general_explanations: List[Dict[str, Any]] = Field(default_factory=list)
    missing_information: List[Dict[str, Any]] = Field(default_factory=list)
    extraction_warnings: List[str] = Field(default_factory=list)
    external_law_required: bool = False
    jurisdiction_flags: List[str] = Field(default_factory=list)
    recommend_professional_review: bool = False
    legal_verdict: Optional[str] = None  # Permanently null


def render_response(
    con: sqlite3.Connection,
    status: str,
    summary_answer: str,
    points: List[ModelPoint],
    external_law_required: bool = False,
    recommend_review: bool = False,
    jurisdiction_flags: Optional[List[str]] = None,
    missing_info: Optional[List[Dict[str, Any]]] = None,
) -> RenderedAnswer:
    """
    Construct the final RenderedAnswer using verified database records.
    """
    claims: List[ClaimItem] = []
    interpretations: List[Dict[str, Any]] = []
    concerns: List[Dict[str, Any]] = []
    ambiguities: List[Dict[str, Any]] = []
    conflicts: List[Dict[str, Any]] = []
    general_explanations: List[Dict[str, Any]] = []

    for idx, pt in enumerate(points, start=1):
        # Fetch verified evidence from local database
        evidence_items: List[EvidenceItem] = []
        for sid in pt.sids:
            row = con.execute(
                "SELECT sid, page_num, section, sentence_text FROM sentences WHERE sid = ?",
                (sid,),
            ).fetchone()
            if row:
                evidence_items.append(
                    EvidenceItem(
                        sid=row["sid"],
                        page=row["page_num"],
                        section=row["section"] or "",
                        quote=row["sentence_text"],
                        ocr_derived=False,
                    )
                )

        kind_upper = pt.kind.upper()
        item_id = f"item_{idx:03d}"

        if kind_upper in ("STATED", "RESTATEMENT"):
            classification = "DIRECT" if kind_upper == "STATED" else "SUPPORTED"
            claims.append(
                ClaimItem(
                    claim_id=item_id,
                    text=pt.text,
                    classification=classification,
                    evidence=evidence_items,
                )
            )
        elif kind_upper == "INTERPRETATION":
            interpretations.append(
                {
                    "item_id": item_id,
                    "text": pt.text,
                    "evidence": [e.model_dump() for e in evidence_items],
                }
            )
        elif kind_upper == "CONCERN":
            concerns.append(
                {
                    "item_id": item_id,
                    "text": pt.text,
                    "evidence": [e.model_dump() for e in evidence_items],
                }
            )
        elif kind_upper == "AMBIGUITY":
            ambiguities.append(
                {
                    "item_id": item_id,
                    "text": pt.text,
                    "evidence": [e.model_dump() for e in evidence_items],
                }
            )
        elif kind_upper == "CONFLICT":
            conflicts.append(
                {
                    "item_id": item_id,
                    "text": pt.text,
                    "evidence": [e.model_dump() for e in evidence_items],
                }
            )
        elif kind_upper == "GENERAL_EXPLANATION":
            general_explanations.append(
                {
                    "item_id": item_id,
                    "text": pt.text,
                }
            )

    return RenderedAnswer(
        status=status,
        answer=summary_answer,
        claims=claims,
        interpretations=interpretations,
        concerns=concerns,
        ambiguities=ambiguities,
        conflicts=conflicts,
        general_explanations=general_explanations,
        missing_information=missing_info or [],
        extraction_warnings=[],
        external_law_required=external_law_required,
        jurisdiction_flags=jurisdiction_flags or [],
        recommend_professional_review=recommend_review,
        legal_verdict=None,  # Always null
    )
