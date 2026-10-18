"""
Unit tests for quality and language gates.

T-ING-LANG-PAGE-01: 10-page English fixture with 1 non-English page
must result in that page being marked UNREAD_LANGUAGE.
"""
from __future__ import annotations

from backend.app.ingest.quality import assess_page
from backend.app.ingest.language import assess_language, apply_majority_language


# ── Quality gate tests ────────────────────────────────────────────────────────

def test_image_only_page_detected() -> None:
    quality = assess_page(1, "", [])
    assert quality.is_image_only
    assert not quality.is_readable


def test_garbled_page_detected() -> None:
    # A page with many non-printable chars.
    garbled = "".join(chr(i) for i in range(1, 20)) * 10
    quality = assess_page(1, garbled, [])
    assert quality.garble_ratio >= 0.15


def test_clean_page_readable() -> None:
    text = "This is a normal rental agreement clause. The tenant shall pay rent."
    quality = assess_page(1, text, [])
    assert quality.is_readable
    assert not quality.is_image_only


def test_table_warning() -> None:
    text = "Clause\t\tAmount\t\tDate\n1.\t\tRs. 25,000\t\t01/01/2025"
    quality = assess_page(1, text, [])
    assert quality.has_layout_warning


def test_hidden_text_flag_passthrough() -> None:
    warnings = ["Possible hidden text detected on this page (many characters with near-zero bounding boxes)."]
    quality = assess_page(1, "Some text here.", warnings)
    assert quality.hidden_text_possible


# ── Language gate tests (T-ING-LANG-PAGE-01) ──────────────────────────────────

_ENGLISH_PAGE = (
    "This agreement is entered into between the landlord and the tenant. "
    "The tenant shall pay a monthly rent of Rs. 25,000. "
    "The landlord shall maintain the property in good repair. "
    "Notice of termination must be given in writing at least two months before the end of the term. "
    "The security deposit shall be refunded within thirty days of vacating the premises."
)

_HINDI_PAGE = (
    "यह एक किराया समझौता है। किरायेदार प्रति माह 25,000 रुपये का किराया देगा। "
    "मकान मालिक संपत्ति की देखभाल करेगा।"
)


def test_english_page_supported() -> None:
    result = assess_language(1, _ENGLISH_PAGE)
    assert result.supported


def test_non_english_page_not_supported() -> None:
    result = assess_language(1, _HINDI_PAGE)
    assert not result.supported
    assert result.warning is not None


def test_t_ing_lang_page_01() -> None:
    """
    T-ING-LANG-PAGE-01: 10-page fixture with 1 non-English page.

    The non-English page must be marked not-supported (UNREAD_LANGUAGE).
    All English pages must be supported.
    """
    results = []
    for i in range(1, 11):
        if i == 5:  # page 5 is the non-English page
            results.append(assess_language(i, _HINDI_PAGE))
        else:
            results.append(assess_language(i, _ENGLISH_PAGE))

    results = apply_majority_language(results)

    english_pages = [r for r in results if r.page_num != 5]
    non_english_page = next(r for r in results if r.page_num == 5)

    assert not non_english_page.supported, (
        "Non-English page must be marked UNREAD_LANGUAGE"
    )
    assert all(r.supported for r in english_pages), (
        "English pages must all be supported"
    )


def test_short_page_inherits_english_majority() -> None:
    """A page with < 40 tokens should inherit supported=True from majority."""
    results = []
    # 9 English pages.
    for i in range(1, 10):
        results.append(assess_language(i, _ENGLISH_PAGE))
    # 1 short page (< 40 tokens).
    results.append(assess_language(10, "Short clause."))

    results = apply_majority_language(results)
    short_page = next(r for r in results if r.page_num == 10)
    assert short_page.supported
