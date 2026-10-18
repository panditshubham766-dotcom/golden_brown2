"""
Sentence and clause segmentation.

Order (Guide §6.6):
  page → numbered headings/clauses → paragraphs → sentence splitting
  → character-cap fallback.

Each sentence gets a deterministic `sid` and start/end offsets into
the stored normalised text for that page.

NEVER uses an ML model.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field


# ── Sentence-splitting abbreviation protection ────────────────────────────────

# Abbreviations that should NOT trigger a sentence split.
_ABBREVS = frozenset([
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "vs", "etc",
    "e.g", "i.e", "no", "rs", "inr", "pg", "pp", "vol", "fig",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    "inc", "ltd", "llp", "pvt", "co", "cl", "sec", "art",
])

# Candidate end of sentence — period/! or ? followed by space+capital/number/bracket.
_PUNCT_SPLIT_RE = re.compile(r"([.!?])(?=['\"]?\s+[A-Z\d([])")
_PRECEDING_WORD_RE = re.compile(r"(\b[a-zA-Z.]+)\Z")

# Heading / clause patterns.
_HEADING_RE = re.compile(
    r"^(?:"
    r"\d+(?:\.\d+)*[.)]\s+"      # e.g. "1." "1.2." "3.4.5)"
    r"|[A-Z][A-Z\s]{3,}$"        # ALL-CAPS heading line
    r"|(?:CLAUSE|SECTION|ARTICLE|SCHEDULE|ANNEXURE)\s+\d+"
    r")",
    re.MULTILINE | re.IGNORECASE,
)

_MAX_SENTENCE_CHARS = 1_200  # character cap fallback


@dataclass
class Sentence:
    sid: str
    page_num: int
    section: str
    start: int   # offset into page's normalised text
    end: int
    text: str


def _sid_for(doc_id: str, page_num: int, section: str, start: int) -> str:
    """Stable, deterministic sentence ID."""
    key = f"{doc_id}|{page_num}|{section}|{start}"
    return "s_" + hashlib.sha1(key.encode()).hexdigest()[:12]


def _split_sentences(text: str, start_offset: int) -> list[tuple[int, int]]:
    """
    Return list of (start, end) byte offsets for sentence spans within `text`,
    offset by `start_offset` into the page text.
    """
    if not text.strip():
        return []

    spans: list[tuple[int, int]] = []
    last = 0

    for m in _PUNCT_SPLIT_RE.finditer(text):
        punct_idx = m.start(1)
        # Don't split if preceded by digit (e.g. "1." or "3.14")
        if punct_idx > 0 and text[punct_idx - 1].isdigit():
            continue

        # Check if preceding word is an abbreviation
        prefix = text[last:punct_idx]
        word_match = _PRECEDING_WORD_RE.search(prefix)
        if word_match:
            word = word_match.group(1).lower().rstrip(".")
            if word in _ABBREVS or f"{word}." in _ABBREVS:
                continue

        end = m.end()
        segment = text[last:end].strip()
        if segment:
            spans.append((start_offset + last, start_offset + end))
        last = end

    # Remainder.
    remainder = text[last:].strip()
    if remainder:
        spans.append((start_offset + last, start_offset + len(text)))

    # Character-cap fallback: split any span that's too long.
    final: list[tuple[int, int]] = []
    for s, e in spans:
        length = e - s
        if length <= _MAX_SENTENCE_CHARS:
            final.append((s, e))
        else:
            # Split at word boundaries within the cap.
            chunk_start = s
            while chunk_start < e:
                chunk_end = min(chunk_start + _MAX_SENTENCE_CHARS, e)
                # Retreat to last space.
                if chunk_end < e:
                    space = text.rfind(" ", chunk_start - start_offset,
                                       chunk_end - start_offset)
                    if space > 0:
                        chunk_end = start_offset + space + 1
                final.append((chunk_start, chunk_end))
                chunk_start = chunk_end

    return final


def segment_page(
    doc_id: str,
    page_num: int,
    page_text: str,
) -> list[Sentence]:
    """
    Segment a single page's normalised text into sentences with sids.

    Returns Sentence objects with offsets into `page_text`.
    """
    sentences: list[Sentence] = []
    paragraphs = re.split(r"\n{2,}", page_text)
    cursor = 0

    for para in paragraphs:
        para_start = page_text.find(para, cursor)
        if para_start < 0:
            para_start = cursor

        # Detect heading.
        first_line = para.split("\n")[0].strip()
        is_heading = bool(_HEADING_RE.match(first_line))
        section = first_line if is_heading else ""

        spans = _split_sentences(para, para_start)

        for s_start, s_end in spans:
            raw_text = page_text[s_start:s_end].strip()
            if not raw_text:
                continue
            sid = _sid_for(doc_id, page_num, section, s_start)
            sentences.append(
                Sentence(
                    sid=sid,
                    page_num=page_num,
                    section=section,
                    start=s_start,
                    end=s_end,
                    text=raw_text,
                )
            )

        cursor = para_start + len(para)

    return sentences
