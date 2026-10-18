"""Verdict scanner and legal boundary enforcement (Guide §9.3a).

Scans assistant-authored text only. Never alters or scans immutable source quotations.
Blocks:
1. Evaluative predicates (valid, invalid, enforceable, void, illegal, unfair).
2. Outcome predictions (sue, court win/loss, police, safe to sign, no lawyer needed).
Exceptions:
- Source-echo exception: STATED or RESTATEMENT points echoing exact source wording
  (e.g. "valid for 11 months", "legal heirs", "lawful purposes").
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

# Evaluative predicates applied to agreement / clause / parties
_VERDICT_PATTERNS = [
    re.compile(r"\b(?:this|the)\s+(?:[a-zA-Z-]+\s+)*(?:clause|agreement|term|provision|contract|document|notice|condition|rule)\s+is\s+(?:not\s+)?(?:\w+\s+)?(?:valid|invalid|enforceable|unenforceable|binding|void|voidable|illegal|unlawful|unconscionable|fair|unfair)\b", re.IGNORECASE),
    re.compile(r"\b(?:is|are)\s+(?:not\s+)?(?:\w+\s+)?(?:void|voidable|unenforceable|invalid|illegal|unlawful)\b", re.IGNORECASE),
    re.compile(r"\b(?:violates|is\s+against)\s+(?:the\s+)?(?:\w+\s+)*(?:law|laws|act|statute|regulations|rules)\b", re.IGNORECASE),
    re.compile(r"\b(?:cannot\s+legally|not\s+legally\s+allowed|has\s+no\s+legal\s+right\s+to)\b", re.IGNORECASE),
    re.compile(r"\b(?:legally\s+binding\s+in\s+court|holds?\s+up\s+in\s+court|invalid\s+in\s+law)\b", re.IGNORECASE),
]

# Outcome and legal advice patterns
_OUTCOME_ADVICE_PATTERNS = [
    re.compile(r"\byou\s+(?:will|can|cannot|should)\s+(?:sue|take\s+(?:the\s+)?(?:\w+\s+)?to\s+court|win\s+in\s+court|lose\s+in\s+court)\b", re.IGNORECASE),
    re.compile(r"\b(?:court\s+will|judge\s+will)\s+(?:rule|decide|strike\s+down|uphold|order)\b", re.IGNORECASE),
    re.compile(r"\b(?:you\s+should\s+not\s+sign|do\s+not\s+sign|safe\s+to\s+sign)\b", re.IGNORECASE),
    re.compile(r"\b(?:no\s+need\s+for\s+a\s+lawyer|you\s+do\s+not\s+need\s+(?:a\s+)?lawyer)\b", re.IGNORECASE),
    re.compile(r"\b(?:standard\s+market\s+practice|normal\s+industry\s+standard)\b", re.IGNORECASE),
    re.compile(r"\b(?:this|the)\s+(?:[a-zA-Z-]+\s+)*(?:term|penalty|clause|forfeiture|lock-in|provision)\s+is\s+(?:unreasonable|excessive|punitive|draconian)\b", re.IGNORECASE),
    re.compile(r"\b(?:police\s+will|file\s+an\s+FIR)\b", re.IGNORECASE),
]

# Patterns that are safe must-pass contexts even if containing keywords like "valid" or "legal"
_SAFE_COMPOUND_PHRASES = [
    re.compile(r"\bvalid\s+for\s+\d+\s+(?:months?|years?|days?)\b", re.IGNORECASE),
    re.compile(r"\bvalid\s+(?:id|identity|address|proof|document|passport|license|licence)\b", re.IGNORECASE),
    re.compile(r"\blegal\s+(?:heirs?|representatives?|counsel|notice|entity|action)\b", re.IGNORECASE),
    re.compile(r"\blawful\s+(?:purposes?|use|activities)\b", re.IGNORECASE),
    re.compile(r"\blegal\s+right\s+to\s+occupy\b", re.IGNORECASE),  # glossary definition context
]


def _check_source_echo(flagged_snippet: str, cited_texts: List[str]) -> bool:
    """Return True if the flagged phrasing is an exact quotation from cited source."""
    clean_snippet = flagged_snippet.strip().lower()
    for source in cited_texts:
        if clean_snippet in source.lower():
            return True
    return False


def scan_verdict(
    text: str,
    kind: str = "ASSISTANT",
    cited_sources: Optional[List[str]] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Scan assistant-authored text for prohibited legal verdicts or advice.

    Returns:
    - (True, None) if clean and compliant.
    - (False, violation_reason) if a prohibited verdict pattern is detected.
    """
    if not text.strip():
        return True, None

    cited_texts = cited_sources or []
    is_stated_or_restatement = kind.upper() in ("STATED", "RESTATEMENT")

    # Check for safe compound phrases first (e.g. "valid for 11 months", "legal heirs")
    # If the sentence contains a safe compound phrase, mask it before scanning
    sanitized_text = text
    for safe_re in _SAFE_COMPOUND_PHRASES:
        sanitized_text = safe_re.sub("SAFE_COMPOUND", sanitized_text)

    # 1. Scan Verdict Patterns
    for pattern in _VERDICT_PATTERNS:
        match = pattern.search(sanitized_text)
        if match:
            matched_phrase = match.group(0)
            # Source echo exception for STATED / RESTATEMENT
            if is_stated_or_restatement and _check_source_echo(match.group(0), cited_texts):
                continue
            return False, f"Prohibited legal verdict pattern: '{matched_phrase}'"

    # 2. Scan Outcome & Advice Patterns
    for pattern in _OUTCOME_ADVICE_PATTERNS:
        match = pattern.search(sanitized_text)
        if match:
            matched_phrase = match.group(0)
            if is_stated_or_restatement and _check_source_echo(match.group(0), cited_texts):
                continue
            return False, f"Prohibited outcome prediction or legal advice: '{matched_phrase}'"

    return True, None
