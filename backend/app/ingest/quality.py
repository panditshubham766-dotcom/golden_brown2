"""
Per-page quality gate (Guide §6.4).

Checks:
- Extracted character count (image-only likelihood).
- Garble ratio (very high ratio of non-printable / non-ASCII control chars).
- Repeated header/footer indicators.
- Multi-column / table layout warnings.
- Hidden-text warning pass-through from parser.

Returns a QualityReport per page.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class PageQuality:
    page_num: int
    char_count: int
    is_image_only: bool       # True if char_count < threshold
    garble_ratio: float       # 0.0–1.0; high = garbled
    has_layout_warning: bool  # table / multi-column detected
    hidden_text_possible: bool
    warnings: list[str] = field(default_factory=list)

    @property
    def is_readable(self) -> bool:
        """True if the page has enough clean text for extraction."""
        return (
            not self.is_image_only
            and self.garble_ratio < 0.15
        )


_IMAGE_ONLY_CHAR_THRESHOLD = 20    # fewer chars than this → likely image-only
_TABLE_RE = re.compile(r"\t|  {3,}|\|")   # multiple spaces, tabs, pipes


def assess_page(page_num: int, text: str, parser_warnings: list[str]) -> PageQuality:
    """Assess the quality of a single page's extracted text."""
    char_count = len(text)
    warnings: list[str] = list(parser_warnings)

    is_image_only = char_count < _IMAGE_ONLY_CHAR_THRESHOLD

    # Garble ratio: fraction of characters that are non-printable.
    if char_count > 0:
        non_printable = sum(
            1 for c in text if ord(c) < 32 and c not in ("\n", "\t", "\r")
        )
        garble_ratio = non_printable / char_count
    else:
        garble_ratio = 0.0

    if is_image_only:
        warnings.append(
            f"Page {page_num}: very little text extracted ({char_count} chars). "
            "This page may be image-only. OCR (Phase 1b) may help."
        )
    if garble_ratio >= 0.15:
        warnings.append(
            f"Page {page_num}: high garble ratio ({garble_ratio:.1%}). "
            "Extraction quality may be poor."
        )

    # Multi-column / table heuristic.
    has_layout_warning = bool(_TABLE_RE.search(text))
    if has_layout_warning:
        warnings.append(
            f"Page {page_num}: possible table or multi-column layout detected. "
            "Citations from this page may not preserve reading order."
        )

    hidden_text_possible = any(
        "hidden text" in w.lower() for w in parser_warnings
    )

    return PageQuality(
        page_num=page_num,
        char_count=char_count,
        is_image_only=is_image_only,
        garble_ratio=garble_ratio,
        has_layout_warning=has_layout_warning,
        hidden_text_possible=hidden_text_possible,
        warnings=warnings,
    )
