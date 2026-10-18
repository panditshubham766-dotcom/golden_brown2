"""
Per-page language gate (Guide §6.4).

No ML dependency. Two rules:

1. If the share of letters outside the Latin script exceeds
   `nonlatin_threshold` (default 15%) → UNREAD_LANGUAGE.

2. For pages with at least `min_tokens` tokens: if the share of
   common English function words is below `english_fn_threshold`
   (default 8%) → INCONCLUSIVE → UNREAD_LANGUAGE.

Pages with fewer than `min_tokens` tokens inherit the document
majority (most common classification across other pages) unless
rule (1) fails them.

Romanised Hindi / regional text usually fails rule (2), which is
the safe outcome — it is excluded rather than silently misread.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Common English function words (closed-class; do not add content words).
_ENGLISH_FN_WORDS = frozenset([
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could",
    "of", "in", "on", "at", "by", "for", "with", "to", "from", "and",
    "or", "but", "not", "this", "that", "which", "who", "whom", "whose",
    "it", "its", "he", "she", "they", "we", "you", "i",
    "as", "if", "when", "where", "how", "all", "any", "such", "no",
])

_TOKEN_RE = re.compile(r"\b[a-zA-Z]+\b")


@dataclass
class LanguageResult:
    page_num: int
    supported: bool      # True if English; False = UNREAD_LANGUAGE
    inconclusive: bool   # True if below fn-word threshold
    nonlatin_ratio: float
    fn_word_ratio: float | None
    token_count: int
    warning: str | None


def _nonlatin_ratio(text: str) -> float:
    """Fraction of Unicode letters that are outside the Latin script block."""
    letters = [c for c in text if unicodedata.category(c).startswith("L")]
    if not letters:
        return 0.0
    nonlatin = [
        c for c in letters
        if unicodedata.name(c, "").split()[0] not in ("LATIN", "DIGIT")
        and not ("A" <= c <= "Z" or "a" <= c <= "z")
    ]
    return len(nonlatin) / len(letters)


def assess_language(
    page_num: int,
    text: str,
    nonlatin_threshold: float = 0.15,
    english_fn_threshold: float = 0.08,
    min_tokens: int = 40,
) -> LanguageResult:
    """Assess the language of a single page."""
    nl_ratio = _nonlatin_ratio(text)

    if nl_ratio > nonlatin_threshold:
        return LanguageResult(
            page_num=page_num,
            supported=False,
            inconclusive=False,
            nonlatin_ratio=nl_ratio,
            fn_word_ratio=None,
            token_count=0,
            warning=(
                f"Page {page_num} is not in a supported language and was not analysed. "
                f"({nl_ratio:.0%} non-Latin characters detected.)"
            ),
        )

    tokens = _TOKEN_RE.findall(text.lower())
    token_count = len(tokens)

    if token_count < min_tokens:
        # Too short to apply function-word test; inherit document majority later.
        return LanguageResult(
            page_num=page_num,
            supported=True,  # tentative; will be updated by majority logic
            inconclusive=False,
            nonlatin_ratio=nl_ratio,
            fn_word_ratio=None,
            token_count=token_count,
            warning=None,
        )

    fn_count = sum(1 for t in tokens if t in _ENGLISH_FN_WORDS)
    fn_ratio = fn_count / token_count

    if fn_ratio < english_fn_threshold:
        return LanguageResult(
            page_num=page_num,
            supported=False,
            inconclusive=True,
            nonlatin_ratio=nl_ratio,
            fn_word_ratio=fn_ratio,
            token_count=token_count,
            warning=(
                f"Page {page_num} is not in a supported language and was not analysed. "
                f"(Inconclusive: only {fn_ratio:.0%} English function words found.)"
            ),
        )

    return LanguageResult(
        page_num=page_num,
        supported=True,
        inconclusive=False,
        nonlatin_ratio=nl_ratio,
        fn_word_ratio=fn_ratio,
        token_count=token_count,
        warning=None,
    )


def apply_majority_language(results: list[LanguageResult], min_tokens: int = 40) -> list[LanguageResult]:
    """
    For pages below `min_tokens` that passed rule (1), inherit the majority
    language decision from longer pages.
    """
    # Determine majority from pages that had enough tokens.
    long_pages = [r for r in results if r.token_count >= min_tokens]
    if not long_pages:
        return results

    supported_count = sum(1 for r in long_pages if r.supported)
    majority_supported = supported_count >= len(long_pages) / 2

    updated: list[LanguageResult] = []
    for r in results:
        if r.token_count < min_tokens and r.supported:
            # Update tentative short-page result.
            if not majority_supported:
                r = LanguageResult(
                    page_num=r.page_num,
                    supported=False,
                    inconclusive=True,
                    nonlatin_ratio=r.nonlatin_ratio,
                    fn_word_ratio=None,
                    token_count=r.token_count,
                    warning=(
                        f"Page {r.page_num} is not in a supported language and was not analysed. "
                        "(Short page; inherited from document majority.)"
                    ),
                )
        updated.append(r)

    return updated
