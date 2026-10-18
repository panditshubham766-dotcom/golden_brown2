"""Bounded runtime state machine for question answering (Guide §8.3).

Flow: RECEIVE -> CLASSIFY -> PLAN -> RETRIEVE -> ANALYZE -> VALIDATE -> RESPOND.
Fast Path: Single Gemma call when lexical retrieval is confident.
Hard limits:
- Max 4 Gemma calls total (including retries)
- Max 8 tool calls total
- Max 2 retrieve loops
- Question <= 500 characters
"""
from __future__ import annotations

import logging
import secrets
import sqlite3
from typing import Any, Dict, List, Optional, Set
from pathlib import Path

from backend.app.agent.router import Route, route_query
from backend.app.agent.schema import ModelAnswer, ModelPoint
from backend.app.agent.tools import DocumentTools
from backend.app.model.provider import LLMProvider
from backend.app.retrieval.silence import STATUS_LOCATED, STATUS_NOT_LOCATED, check_silence
from backend.app.validation.legal_policy import scan_verdict
from backend.app.validation.literal import validate_restatement
from backend.app.validation.provenance import validate_provenance
from backend.app.validation.renderer import RenderedAnswer, render_response

logger = logging.getLogger("lexiguard.agent.runtime")

MAX_GEMMA_CALLS = 4
MAX_TOOL_CALLS = 8
MAX_RETRIEVE_LOOPS = 2


def _load_glossary() -> Dict[str, Dict[str, Any]]:
    """Load curated glossary terms."""
    root = Path(__file__).resolve().parents[3]
    candidate = root / "glossary" / "rental_terms.yaml"
    if not candidate.exists():
        candidate = Path("glossary/rental_terms.yaml")
    if not candidate.exists():
        return {}

    content = candidate.read_text(encoding="utf-8")
    try:
        import yaml
        loaded = yaml.safe_load(content)
        return loaded.get("terms", {}) if isinstance(loaded, dict) else {}
    except Exception:
        pass

    # Simple fallback parser for terms
    terms: Dict[str, Dict[str, Any]] = {}
    current_term = None
    for line in content.splitlines():
        if line.startswith("  ") and line.endswith(":") and not line.strip().startswith("terms:"):
            current_term = line.strip()[:-1]
            terms[current_term] = {}
        elif current_term and "definition:" in line:
            parts = line.split("definition:", 1)
            terms[current_term]["definition"] = parts[1].strip().strip('"')
    return terms


class BoundedRuntime:
    """State machine governing bounded question answering over a document."""

    def __init__(
        self,
        con: sqlite3.Connection,
        provider: Optional[LLMProvider] = None,
    ) -> None:
        self.con = con
        self.provider = provider
        self.tools = DocumentTools(con)
        self.gemma_calls = 0
        self.tool_calls = 0
        self.retrieve_loops = 0
        self.approved_sids: Set[str] = set()

    def run(self, question: str) -> RenderedAnswer:
        """Execute bounded state machine."""
        # 1. RECEIVE & CLASSIFY
        decision = route_query(question)

        # 2. PLAN & DISPATCH
        if decision.route == Route.OUT_OF_SCOPE:
            return render_response(
                con=self.con,
                status="OUT_OF_SCOPE",
                summary_answer=decision.reason,
                points=[],
            )

        if decision.route == Route.DOCUMENT_MAP:
            if self.tool_calls < MAX_TOOL_CALLS:
                self.tool_calls += 1
                sections = self.tools.get_document_map()
                summary = "Here is the structure of the document sections:\n" + "\n".join(
                    f"- {s['section']} (Page {s['start_page']})" for s in sections
                )
                return render_response(
                    con=self.con,
                    status="ANSWERED",
                    summary_answer=summary,
                    points=[],
                )

        if decision.route == Route.DOCUMENT_SILENCE_CHECK:
            topic = decision.target_topic or question
            if self.tool_calls < MAX_TOOL_CALLS:
                self.tool_calls += 1
                silence_res = self.tools.check_document_silence(topic)
                points: List[ModelPoint] = []
                for idx, h in enumerate(silence_res["hits"]):
                    points.append(
                        ModelPoint(
                            point_id=f"p_{idx}",
                            kind="STATED",
                            text=h["sentence_text"],
                            sids=[h["sid"]],
                        )
                    )
                return render_response(
                    con=self.con,
                    status=silence_res["status"],
                    summary_answer=silence_res["explanation"],
                    points=points,
                )

        if decision.route == Route.TERM_EXPLANATION:
            term = decision.target_topic or question
            glossary = _load_glossary()
            term_clean = term.lower().strip()
            definition_entry = glossary.get(term_clean)

            # Search document for occurrences
            doc_hits = []
            if self.tool_calls < MAX_TOOL_CALLS:
                self.tool_calls += 1
                doc_hits = self.tools.search_document(query=term)

            points = []
            if definition_entry:
                def_text = f"General definition: {definition_entry.get('definition', '')}"
                points.append(
                    ModelPoint(
                        point_id="p_def",
                        kind="GENERAL_EXPLANATION",
                        text=def_text,
                        sids=[],
                    )
                )

            for idx, h in enumerate(doc_hits[:3]):
                points.append(
                    ModelPoint(
                        point_id=f"p_doc_{idx}",
                        kind="STATED",
                        text=h["sentence_text"],
                        sids=[h["sid"]],
                    )
                )

            def_str = definition_entry.get("definition", "No curated glossary entry found.") if definition_entry else "No curated glossary entry found."
            answer = f"Explanation of '{term}':\n{def_str}"
            return render_response(
                con=self.con,
                status="ANSWERED",
                summary_answer=answer,
                points=points,
            )

        # 3. RETRIEVE
        self.retrieve_loops += 1
        self.tool_calls += 1
        hits = self.tools.search_document(query=question, topic=decision.target_topic)

        # Record approved sids
        for h in hits:
            self.approved_sids.add(h["sid"])

        # Check silence gate if zero hits found
        if not hits:
            silence_res = check_silence(self.con, topic=decision.target_topic or question, query=question)
            return render_response(
                con=self.con,
                status=silence_res.status,
                summary_answer=silence_res.explanation,
                points=[],
            )

        # Handle LEGAL_CONCLUSION limitation route:
        # We retrieve the relevant text, but refuse legal verdicts and recommend professional review.
        if decision.is_limitation and decision.route in (Route.LEGAL_CONCLUSION, Route.EXTERNAL_LAW_REQUIRED):
            points = [
                ModelPoint(
                    point_id=f"p_{i}",
                    kind="STATED",
                    text=h["sentence_text"],
                    sids=[h["sid"]],
                )
                for i, h in enumerate(hits[:5])
            ]
            summary = (
                "LexiGuard provides factual document triage and cannot provide legal verdicts, "
                "enforceability determinations, or judicial predictions. Below are the relevant "
                "clauses located in your agreement. Please consult a qualified legal professional "
                "to evaluate enforceability under applicable jurisdiction law."
            )
            return render_response(
                con=self.con,
                status="LEGAL_LIMIT",
                summary_answer=summary,
                points=points,
                external_law_required=True,
                recommend_review=True,
            )

        # 4. ANALYZE (Fast Path: Exactly 1 Gemma Call)
        if not self.provider or self.gemma_calls >= MAX_GEMMA_CALLS:
            # Fallback to direct stated facts when model provider is omitted (e.g. tests or model limit)
            points = [
                ModelPoint(
                    point_id=f"p_{i}",
                    kind="STATED",
                    text=h["sentence_text"],
                    sids=[h["sid"]],
                )
                for i, h in enumerate(hits[:5])
            ]
            return render_response(
                con=self.con,
                status="ANSWERED",
                summary_answer="Extracted relevant agreement provisions.",
                points=points,
            )

        # Build nonce-delimited evidence block
        nonce = secrets.token_hex(6)
        evidence_lines = [
            f"[{h['sid']}] (Section: {h['section']}, Page: {h['page_num']}) {h['sentence_text']}"
            for h in hits
        ]
        evidence_block = (
            f"<<EVIDENCE-{nonce}>>\n"
            + "\n".join(evidence_lines)
            + f"\n<<END-EVIDENCE-{nonce}>>"
        )

        system_prompt = (
            "You are LexiGuard, a private legal-document triage assistant.\n"
            "Analyze the provided evidence and extract relevant factual points answering the question.\n"
            "Rules:\n"
            "- Extract statements directly grounded in the evidence.\n"
            "- Set kind to 'STATED' or 'RESTATEMENT'.\n"
            "- Set sids to the exact sentence IDs supporting each point.\n"
            "- NEVER invent dates, numbers, or amounts.\n"
            "- DO NOT make legal conclusions or evaluate enforceability.\n"
        )
        user_prompt = f"Question: {question}\n\nEvidence:\n{evidence_block}"

        self.gemma_calls += 1
        model_answer: ModelAnswer = self.provider.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=ModelAnswer,
        )

        # 5. VALIDATE
        # Provenance check: drop forged/unapproved sids
        valid_points, dropped_reasons = validate_provenance(model_answer, self.approved_sids)

        verified_points: List[ModelPoint] = []
        for pt in valid_points:
            # Fetch source texts for cited sids
            source_texts = []
            for sid in pt.sids:
                row = self.con.execute("SELECT sentence_text FROM sentences WHERE sid = ?", (sid,)).fetchone()
                if row:
                    source_texts.append(row["sentence_text"])

            # Literal validation for restatements
            if pt.kind.upper() == "RESTATEMENT":
                ok_lit, reason = validate_restatement(pt, source_texts)
                if not ok_lit:
                    logger.warning("Dropping restatement point %s: %s", pt.point_id, reason)
                    continue

            # Legal Policy Verdict Scanner
            ok_scan, scan_reason = scan_verdict(pt.text, kind=pt.kind, cited_sources=source_texts)
            if not ok_scan:
                logger.warning("Dropping point %s due to verdict scan: %s", pt.point_id, scan_reason)
                continue

            verified_points.append(pt)

        # 6. RESPOND
        if not verified_points:
            # Fall back to extractive STATED points from top hits
            verified_points = [
                ModelPoint(
                    point_id=f"p_{i}",
                    kind="STATED",
                    text=h["sentence_text"],
                    sids=[h["sid"]],
                )
                for i, h in enumerate(hits[:3])
            ]

        summary_answer = " ".join(pt.text for pt in verified_points[:3])
        return render_response(
            con=self.con,
            status="ANSWERED",
            summary_answer=summary_answer,
            points=verified_points,
        )
