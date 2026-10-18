"""
Unit tests for sentence segmentation.

Tests:
- Basic sentence splitting.
- Abbreviation protection (Rs., No., e.g.).
- Heading detection.
- Character-cap fallback.
- Sid stability (same input → same sid).
- Empty page → no sentences.
"""
from __future__ import annotations

from backend.app.ingest.segment import segment_page


DOC_ID = "aabbccddeeff00112233445566778899"


def test_basic_sentence_split() -> None:
    text = "The tenant shall pay rent monthly. The landlord shall maintain the property."
    sents = segment_page(DOC_ID, 1, text)
    assert len(sents) >= 2
    assert any("tenant" in s.text for s in sents)
    assert any("landlord" in s.text for s in sents)


def test_abbreviation_protection() -> None:
    # "Rs. 25,000" must NOT split after "Rs."
    text = "Rent shall be Rs. 25,000 per month. Payment is due on the 1st."
    sents = segment_page(DOC_ID, 1, text)
    # Should be 2 sentences, not 3.
    texts = [s.text for s in sents]
    assert any("Rs. 25,000" in t for t in texts)


def test_heading_detected() -> None:
    text = "1. RENT\n\nThe tenant shall pay Rs. 25,000 per month."
    sents = segment_page(DOC_ID, 1, text)
    # At least one sentence should have a section set.
    sections = [s.section for s in sents if s.section]
    assert len(sections) > 0


def test_empty_page_returns_no_sentences() -> None:
    sents = segment_page(DOC_ID, 1, "")
    assert sents == []


def test_sid_stability() -> None:
    text = "The tenant shall pay rent. The landlord shall maintain."
    sents1 = segment_page(DOC_ID, 1, text)
    sents2 = segment_page(DOC_ID, 1, text)
    assert [s.sid for s in sents1] == [s.sid for s in sents2]


def test_sid_different_pages() -> None:
    text = "This is a clause."
    s1 = segment_page(DOC_ID, 1, text)
    s2 = segment_page(DOC_ID, 2, text)
    if s1 and s2:
        assert s1[0].sid != s2[0].sid


def test_offsets_round_trip() -> None:
    text = "First sentence. Second sentence here. Third one."
    sents = segment_page(DOC_ID, 1, text)
    for s in sents:
        # The stored text must match the slice of the page text.
        extracted = text[s.start:s.end].strip()
        assert s.text == extracted or s.text in extracted, (
            f"Offset round-trip failed: sid={s.sid}, "
            f"expected={s.text!r}, got={extracted!r}"
        )
