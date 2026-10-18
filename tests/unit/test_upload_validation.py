"""
T-ING-* unit tests: upload validation.

Tests:
- PDF magic bytes accepted.
- TXT UTF-8 accepted.
- TXT latin-1 accepted.
- Non-PDF/non-TXT binary rejected.
- Encrypted PDF rejected (has /Encrypt in header).
- Empty file rejected.
- Oversized file rejected.
"""
from __future__ import annotations

import pytest

from backend.app.ingest.upload import validate_upload, UploadValidationError, PDF_MAGIC


MAX = 10 * 1024 * 1024  # 10 MB for tests

# ── Helpers ───────────────────────────────────────────────────────────────────

def make_pdf(encrypted: bool = False) -> bytes:
    header = b"%PDF-1.4\n"
    body = b"<< /Type /Catalog >>"
    if encrypted:
        body += b" /Encrypt << /Filter /Standard >>"
    return header + body


def make_txt_utf8() -> bytes:
    return "This is a rental agreement.\nRent: Rs. 25,000/-\n".encode("utf-8")


def make_txt_latin1() -> bytes:
    return "Tenancy agreement\xe9\n".encode("latin-1")


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_pdf_accepted() -> None:
    result = validate_upload(make_pdf(), MAX)
    assert result == "pdf"


def test_txt_utf8_accepted() -> None:
    result = validate_upload(make_txt_utf8(), MAX)
    assert result == "txt"


def test_txt_latin1_accepted() -> None:
    result = validate_upload(make_txt_latin1(), MAX)
    assert result == "txt"


def test_encrypted_pdf_rejected() -> None:
    with pytest.raises(UploadValidationError, match="encrypted"):
        validate_upload(make_pdf(encrypted=True), MAX)


def test_empty_file_rejected() -> None:
    with pytest.raises(UploadValidationError, match="empty"):
        validate_upload(b"", MAX)


def test_oversized_file_rejected() -> None:
    max_bytes = 100
    with pytest.raises(UploadValidationError, match="exceeds"):
        validate_upload(b"x" * 200, max_bytes)


def test_binary_garbage_rejected() -> None:
    with pytest.raises(UploadValidationError, match="not a supported format"):
        validate_upload(b"\x00\x01\x02\x03\xFF\xFE" * 50, MAX)


def test_pdf_magic_constant() -> None:
    assert PDF_MAGIC == b"%PDF-"
