"""Deterministic pre-router for user queries (Guide §8.2).

Catches verdict / outcome patterns and routes them strictly to limitation paths.
Never allows a model to downgrade a deterministic legal limitation into an ordinary factual answer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Route(str, Enum):
    FACT_LOOKUP = "FACT_LOOKUP"
    MULTI_CLAUSE_ANALYSIS = "MULTI_CLAUSE_ANALYSIS"
    DOCUMENT_MAP = "DOCUMENT_MAP"
    REVIEW_SCAN = "REVIEW_SCAN"
    DOCUMENT_SILENCE_CHECK = "DOCUMENT_SILENCE_CHECK"
    AMBIGUITY_OR_CONFLICT = "AMBIGUITY_OR_CONFLICT"
    TERM_EXPLANATION = "TERM_EXPLANATION"
    LEGAL_CONCLUSION = "LEGAL_CONCLUSION"
    EXTERNAL_LAW_REQUIRED = "EXTERNAL_LAW_REQUIRED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


@dataclass
class RouteDecision:
    route: Route
    reason: str
    target_topic: Optional[str] = None
    is_limitation: bool = False


# Prohibited verdict / outcome question patterns that require legal conclusion or external law
_LEGAL_VERDICT_PATTERNS = [
    re.compile(r"\b(?:is\s+this|is\s+the|is\s+it)\s*(?:[a-zA-Z\s]{0,25})?\s*(?:legally\s+|completely\s+)?(?:enforceable|valid|binding|legal|lawful|void|fair|unfair)\b", re.IGNORECASE),
    re.compile(r"\b(?:will\s+this|will\s+it)\s+(?:hold\s+up|stand)\s+(?:up\s+)?in\s+court\b", re.IGNORECASE),
    re.compile(r"\bcan\s+I\s+(?:sue|take\s+(?:[a-zA-Z\s]+)?to\s+court|take\s+legal\s+action|go\s+to\s+court)\b", re.IGNORECASE),
    re.compile(r"\b(?:can\s+(?:they|the\s+landlord|owner)\s+(?:throw\s+me\s+out|kick\s+me\s+out|evict\s+me)\s*(?:legally|without\s+court)?)\b", re.IGNORECASE),
    re.compile(r"\b(?:is\s+this\s+allowed\s+by\s+law|is\s+it\s+against\s+the\s+law|is\s+this\s+illegal)\b", re.IGNORECASE),
    re.compile(r"\b(?:is\s+it\s+legal\s+to|can\s+the\s+landlord\s+legally)\b", re.IGNORECASE),
    re.compile(r"\b(?:do\s+I\s+have\s+a\s+(?:strong\s+)?case|will\s+I\s+win(?:\s+in\s+court)?)\b", re.IGNORECASE),
    re.compile(r"\b(?:what\s+does\s+the\s+law\s+say\s+about|according\s+to\s+the\s+law)\b", re.IGNORECASE),
]

# Term explanation patterns: require explicit definition / meaning intent
_TERM_EXPLANATION_PATTERNS = [
    re.compile(r"^\s*what\s+does\s+(.+?)\s+mean\s*\??\s*$", re.IGNORECASE),
    re.compile(r"^\s*what\s+is\s+the\s+meaning\s+of\s+(.+?)\s*\??\s*$", re.IGNORECASE),
    re.compile(r"^\s*define\s+(?:a\s+|an\s+|the\s+)?(.+?)\s*\??\s*$", re.IGNORECASE),
    re.compile(r"^\s*explain\s+(?:the\s+term\s+|the\s+concept\s+of\s+)(.+?)\s*\??\s*$", re.IGNORECASE),
]

# Silence check patterns
_SILENCE_PATTERNS = [
    re.compile(r"\b(?:does\s+(?:this|the)\s+agreement\s+(?:say|mention|have|contain)\s+(?:anything\s+about|any\s+provision\s+for)?)\s*(.+?)\??$", re.IGNORECASE),
    re.compile(r"\b(?:is\s+there\s+(?:any|a)\s+mention\s+of)\s*(.+?)\??$", re.IGNORECASE),
    re.compile(r"\b(?:is\s+(?:there\s+any\s+clause|anything\s+stated)\s+about)\s*(.+?)\??$", re.IGNORECASE),
]

# Structure / map patterns
_MAP_PATTERNS = [
    re.compile(r"\b(?:show\s+(?:me\s+)?(?:the\s+)?(?:table\s+of\s+contents|document\s+map|structure|sections|clauses))\b", re.IGNORECASE),
    re.compile(r"\b(?:list\s+all\s+(?:the\s+)?(?:clauses|sections|headings))\b", re.IGNORECASE),
]


def route_query(question: str) -> RouteDecision:
    """
    Deterministically route a user question to an appropriate execution path.
    Enforces legal limitations, size limits, and term lookup bounds.
    """
    clean_q = question.strip()

    # 1. Size bounds
    if not clean_q:
        return RouteDecision(
            route=Route.OUT_OF_SCOPE,
            reason="Empty question received.",
            is_limitation=True,
        )

    if len(clean_q) > 500:
        return RouteDecision(
            route=Route.OUT_OF_SCOPE,
            reason="Question exceeds maximum allowed length of 500 characters.",
            is_limitation=True,
        )

    # 2. Legal verdict / outcome limitations (MUST-ROUTE to limitation path)
    for pattern in _LEGAL_VERDICT_PATTERNS:
        if pattern.search(clean_q):
            return RouteDecision(
                route=Route.LEGAL_CONCLUSION,
                reason="Question asks for legal verdict, enforceability assessment, or judicial prediction.",
                is_limitation=True,
            )

    # 3. Document Map
    for pattern in _MAP_PATTERNS:
        if pattern.search(clean_q):
            return RouteDecision(
                route=Route.DOCUMENT_MAP,
                reason="Question requests overall document outline or section list.",
                is_limitation=False,
            )

    # 4. Silence check
    for pattern in _SILENCE_PATTERNS:
        m = pattern.search(clean_q)
        if m:
            topic = m.group(1).strip()
            return RouteDecision(
                route=Route.DOCUMENT_SILENCE_CHECK,
                reason="Question explicitly asks about the absence or presence of a clause/topic.",
                target_topic=topic,
                is_limitation=False,
            )

    # 5. Term explanation
    for pattern in _TERM_EXPLANATION_PATTERNS:
        m = pattern.search(clean_q)
        if m:
            term = m.group(1).strip().lower()
            return RouteDecision(
                route=Route.TERM_EXPLANATION,
                reason="Question requests definition of a general term.",
                target_topic=term,
                is_limitation=False,
            )

    # 6. Default to FACT_LOOKUP with optional detected topic
    lower_q = clean_q.lower()
    detected_topic = None
    for t_key in ("parties", "party", "rent", "deposit", "notice", "maintenance", "term", "dispute", "governing law", "law"):
        if re.search(r"\b" + t_key + r"\b", lower_q):
            if t_key in ("dispute", "governing law", "law"):
                detected_topic = "disputes"
            elif t_key in ("parties", "party"):
                detected_topic = "parties"
            else:
                detected_topic = t_key
            break

    return RouteDecision(
        route=Route.FACT_LOOKUP,
        reason="Standard factual inquiry over document clauses.",
        target_topic=detected_topic,
        is_limitation=False,
    )
