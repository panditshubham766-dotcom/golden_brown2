"""
Upload validation: magic bytes, size, encoding.

Nothing from the uploaded file (filename, metadata, content) is logged
or placed in model prompts. Only structured quality/warning data is surfaced.
"""
from __future__ import annotations

PDF_MAGIC = b"%PDF-"


class UploadValidationError(ValueError):
    """Raised when an uploaded file fails validation before parsing."""


def _is_probable_text(text: str) -> bool:
    """Check if decoded string is plausible text rather than binary data."""
    if not text:
        return True
    printable = sum(1 for c in text if c.isprintable() or c in "\n\r\t")
    return (printable / len(text)) > 0.85


def detect_file_type(raw: bytes) -> str:
    """
    Detect file type from content, not filename.

    Returns "pdf" or "txt". Raises UploadValidationError for encrypted PDFs
    or files that are neither valid PDF nor valid UTF-8 text.
    """
    if raw[:5] == PDF_MAGIC:
        # Check for encryption dictionary — quick heuristic scan.
        # A fully encrypted PDF has /Encrypt in its trailer.
        # This catches the most common case; the parser will be the definitive check.
        sample = raw[:4096]
        if b"/Encrypt" in sample:
            raise UploadValidationError(
                "This PDF appears to be encrypted. "
                "LexiGuard cannot process password-protected PDFs. "
                "Please remove the password and try again."
            )
        return "pdf"

    sample = raw[:8192]

    # Binary files containing NUL bytes are rejected immediately
    if b"\x00" in sample:
        raise UploadValidationError(
            "File is not a supported format. "
            "Upload a PDF (starting with %PDF-) or a plain-text (.txt) file."
        )

    # Try UTF-8 decoding on a sample to classify as TXT.
    try:
        decoded = sample.decode("utf-8")
        if _is_probable_text(decoded):
            return "txt"
    except UnicodeDecodeError:
        pass

    # Try latin-1 as a fallback for legacy TXT.
    try:
        decoded = sample.decode("latin-1")
        if _is_probable_text(decoded):
            return "txt"
    except Exception:
        pass

    raise UploadValidationError(
        "File is not a supported format. "
        "Upload a PDF (starting with %PDF-) or a plain-text (.txt) file."
    )


def validate_upload(raw: bytes, max_bytes: int) -> str:
    """
    Run all pre-parse validation checks.

    Returns the detected file type ("pdf" or "txt").
    Raises UploadValidationError on any failure.
    """
    if len(raw) == 0:
        raise UploadValidationError("Uploaded file is empty.")
    if len(raw) > max_bytes:
        raise UploadValidationError(
            f"File size {len(raw):,} bytes exceeds the maximum of {max_bytes:,} bytes."
        )
    return detect_file_type(raw)
