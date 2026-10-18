"""
Unit tests for text normalisation.

Tests:
- CRLF → LF conversion.
- NFC normalisation.
- De-hyphenation.
- Whitespace collapse.
"""
from __future__ import annotations

import unicodedata

from backend.app.ingest.normalize import normalise


def test_crlf_to_lf() -> None:
    text = "line1\r\nline2\r\nline3"
    result, _ = normalise(text)
    assert "\r" not in result
    assert "line1\nline2\nline3" in result


def test_nfc_normalisation() -> None:
    # "é" as NFD (e + combining acute) should become NFC.
    nfd = "e\u0301"  # NFD: e + combining acute
    result, _ = normalise(nfd)
    assert result == unicodedata.normalize("NFC", nfd)


def test_dehyphenation() -> None:
    text = "land-\nlord shall pay"
    result, mapping = normalise(text)
    assert "lord" in result
    # The hyphen and newline should be removed.
    assert "-\n" not in result


def test_multiple_spaces_collapsed() -> None:
    text = "The   tenant   shall"
    result, _ = normalise(text)
    assert "   " not in result
    assert "The tenant shall" in result


def test_blank_lines_collapsed() -> None:
    text = "Para 1.\n\n\n\n\nPara 2."
    result, _ = normalise(text)
    assert "\n\n\n" not in result


def test_empty_string() -> None:
    result, mapping = normalise("")
    assert result == ""
    assert mapping == []
