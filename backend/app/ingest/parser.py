"""
PDF / TXT parser — runs inside a child process.

This module is the entry point for the sandboxed child process.
It receives raw bytes on stdin (as a JSON envelope) and writes
structured JSON to stdout.

Design:
- Parent calls run_parser_worker(raw, file_type, settings) which
  spawns this module as a subprocess.
- All parsing happens here; crashes in pypdfium2 cannot affect the API process.
- Output is capped at parser_output_cap_bytes.

Security (Guide §6.2 platform matrix):
  Linux  : RLIMIT_CPU + RLIMIT_AS + wall timeout + output cap.
  macOS  : CPU-time limit + wall timeout + output cap + page/size caps;
           RLIMIT_AS unreliable → RSS watchdog thread.
  Windows: NO resource module → wall timeout + output cap + page/size caps only.
           Startup notice is emitted by main.py.
"""
from __future__ import annotations

import json
import os
import platform
import sys
import threading
import time
from pathlib import Path
from typing import Any


# ─── Resource limits (best-effort per platform) ───────────────────────────────

def _apply_resource_limits(
    cpu_seconds: int,
    max_address_bytes: int,
) -> list[str]:
    """Apply OS-level resource limits; return list of limits NOT applied."""
    missing: list[str] = []
    system = platform.system()

    if system == "Linux":
        try:
            import resource  # type: ignore[import]
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
            resource.setrlimit(resource.RLIMIT_AS, (max_address_bytes, max_address_bytes))
        except Exception as exc:
            missing.append(f"RLIMIT_CPU/RLIMIT_AS ({exc})")
    elif system == "Darwin":
        try:
            import resource  # type: ignore[import]
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        except Exception as exc:
            missing.append(f"RLIMIT_CPU ({exc})")
        missing.append("RLIMIT_AS (not reliable on macOS; RSS watchdog used)")
    else:
        missing.append("RLIMIT_CPU (not available on Windows)")
        missing.append("RLIMIT_AS (not available on Windows)")

    return missing


def _rss_watchdog(max_rss_bytes: int, interval: float = 1.0) -> None:
    """Kill this process if RSS exceeds max_rss_bytes (macOS fallback)."""
    pid = os.getpid()
    while True:
        time.sleep(interval)
        try:
            import resource  # type: ignore[import]
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # macOS: bytes; Linux: kilobytes (but this thread only runs on macOS).
            if rss > max_rss_bytes:
                os.kill(pid, 9)
        except Exception:
            pass


# ─── PDF extraction ───────────────────────────────────────────────────────────

def _extract_pdf(raw: bytes, max_pages: int, max_text_bytes: int) -> dict[str, Any]:
    """Extract text from a PDF using pypdfium2."""
    import pypdfium2 as pdfium  # type: ignore[import]

    try:
        doc = pdfium.PdfDocument(raw)
    except Exception as exc:
        return {"error": f"pypdfium2 failed to open document: {exc}"}

    page_count = len(doc)
    warnings: list[str] = []

    if page_count == 0:
        return {"error": "PDF has no pages."}
    if page_count > max_pages:
        return {
            "error": (
                f"PDF has {page_count} pages, which exceeds the maximum of {max_pages}. "
                "Split the document and upload it in parts."
            )
        }

    pages: list[dict[str, Any]] = []
    total_text_bytes = 0

    for page_num in range(page_count):
        page = doc[page_num]
        text_page = page.get_textpage()

        # Extract full page text.
        raw_text = text_page.get_text_range()

        # Check for hidden text (heuristic: bounding boxes with zero height/width).
        hidden_text_warning: str | None = None
        try:
            char_count = text_page.count_chars()
            loose_chars = 0
            for i in range(min(char_count, 500)):  # sample first 500 chars
                rect = text_page.get_charbox(i, loose=True)
                if rect and (rect[2] - rect[0] < 0.5 or rect[3] - rect[1] < 0.5):
                    loose_chars += 1
            if loose_chars > 0.3 * min(char_count, 500):
                hidden_text_warning = (
                    "Possible hidden text detected on this page "
                    "(many characters with near-zero bounding boxes). "
                    "Content may be incomplete."
                )
        except Exception:
            pass

        page_warnings: list[str] = []
        if hidden_text_warning:
            page_warnings.append(hidden_text_warning)

        # Accumulate text-size cap.
        total_text_bytes += len(raw_text.encode("utf-8"))
        if total_text_bytes > max_text_bytes:
            warnings.append(
                f"Text extraction stopped at page {page_num + 1}: "
                f"total extracted text exceeds {max_text_bytes:,} bytes."
            )
            # Truncate this page and stop.
            pages.append({
                "page_num": page_num + 1,
                "text": "",
                "warnings": ["Text truncated: total text-size cap reached."],
            })
            break

        pages.append({
            "page_num": page_num + 1,
            "text": raw_text,
            "warnings": page_warnings,
        })

        text_page.close()
        page.close()

    doc.close()

    return {
        "file_type": "pdf",
        "page_count": page_count,
        "pages": pages,
        "warnings": warnings,
    }


# ─── TXT extraction (virtual pages) ──────────────────────────────────────────

def _extract_txt(
    raw: bytes,
    virtual_page_chars: int,
    max_pages: int,
    max_text_bytes: int,
) -> dict[str, Any]:
    """Split TXT into virtual pages at paragraph boundaries."""
    # Try UTF-8 first, then latin-1.
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    # Normalise line endings.
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    if len(text.encode("utf-8")) > max_text_bytes:
        return {
            "error": (
                f"Text file exceeds the maximum extracted text size of {max_text_bytes:,} bytes."
            )
        }

    # Split into virtual pages at paragraph boundaries (double newlines).
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    pages: list[dict[str, Any]] = []
    current_chunks: list[str] = []
    current_len = 0
    page_num = 1

    for para in paragraphs:
        if current_len + len(para) > virtual_page_chars and current_chunks:
            pages.append({
                "page_num": page_num,
                "text": "\n\n".join(current_chunks),
                "warnings": ["virtual page (TXT)"],
            })
            page_num += 1
            current_chunks = []
            current_len = 0
            if page_num > max_pages:
                break
        current_chunks.append(para)
        current_len += len(para) + 2  # +2 for "\n\n"

    if current_chunks and page_num <= max_pages:
        pages.append({
            "page_num": page_num,
            "text": "\n\n".join(current_chunks),
            "warnings": ["virtual page (TXT)"],
        })

    return {
        "file_type": "txt",
        "page_count": len(pages),
        "pages": pages,
        "warnings": [],
    }


# ─── Child-process entry point ────────────────────────────────────────────────

def main() -> None:
    """
    Entry point when this module is run as a child process.

    Reads a JSON envelope from stdin, applies resource limits,
    extracts text, and writes structured JSON to stdout.
    """
    try:
        envelope = json.loads(sys.stdin.buffer.read())
    except Exception as exc:
        print(json.dumps({"error": f"Failed to read input: {exc}"}))
        sys.exit(1)

    file_type: str = envelope.get("file_type", "")
    max_pages: int = envelope.get("max_pages", 500)
    max_text_bytes: int = envelope.get("max_text_bytes", 10 * 1024 * 1024)
    virtual_page_chars: int = envelope.get("virtual_page_chars", 3_000)
    cpu_seconds: int = envelope.get("cpu_seconds", 60)
    max_address_bytes: int = envelope.get("max_address_bytes", 512 * 1024 * 1024)

    # Base64-decode the raw bytes.
    import base64
    raw = base64.b64decode(envelope.get("raw_b64", ""))

    missing_limits = _apply_resource_limits(cpu_seconds, max_address_bytes)

    # RSS watchdog on macOS.
    if platform.system() == "Darwin":
        t = threading.Thread(
            target=_rss_watchdog,
            args=(max_address_bytes,),
            daemon=True,
        )
        t.start()

    if file_type == "pdf":
        result = _extract_pdf(raw, max_pages, max_text_bytes)
    elif file_type == "txt":
        result = _extract_txt(raw, virtual_page_chars, max_pages, max_text_bytes)
    else:
        result = {"error": f"Unknown file type: {file_type!r}"}

    result["missing_limits"] = missing_limits

    output = json.dumps(result)
    sys.stdout.write(output)
    sys.stdout.flush()


if __name__ == "__main__":
    main()
