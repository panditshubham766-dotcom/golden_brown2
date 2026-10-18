"""
Text normalisation.

Applies: CRLF→LF, Unicode NFC, controlled whitespace.
Records the de-hyphenation mapping for offset tracking.

Offsets into the NORMALISED text are what all sentence IDs and citations use.
They must NOT be confused with raw PDFium character indices.
"""
from __future__ import annotations

import re
import unicodedata


# Regex for end-of-line hyphens used for word-wrapping.
_DEHYPHEN_RE = re.compile(r"-\n(\S)")


def normalise(text: str) -> tuple[str, list[tuple[int, int]]]:
    """
    Normalise page text.

    Returns:
        (normalised_text, dehyphen_map)

    dehyphen_map is a list of (original_start, normalised_start) pairs
    for every de-hyphenated word, so callers can map offsets if needed.
    """
    # 1. CRLF → LF
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 2. Unicode NFC normalisation.
    text = unicodedata.normalize("NFC", text)

    # 3. Track de-hyphenation offsets for round-tripping.
    dehyphen_map: list[tuple[int, int]] = []
    offset_delta = 0
    result_parts: list[str] = []
    last_end = 0

    for m in _DEHYPHEN_RE.finditer(text):
        # Append text up to the match.
        result_parts.append(text[last_end : m.start()])
        # Record mapping: original position of the re-joined word start.
        dehyphen_map.append((m.start() - offset_delta, len("".join(result_parts))))
        # Replace "foo-\nbar" with "foobar" (remove hyphen and newline).
        result_parts.append(m.group(1))
        offset_delta += 2  # we removed "-\n" (2 chars)
        last_end = m.end()

    result_parts.append(text[last_end:])
    text = "".join(result_parts)

    # 4. Collapse runs of spaces (NOT newlines — preserve paragraph breaks).
    text = re.sub(r"[ \t]+", " ", text)

    # 5. Trim leading/trailing whitespace from each line.
    text = "\n".join(line.strip() for line in text.split("\n"))

    # 6. Collapse runs of 3+ blank lines to 2.
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text, dehyphen_map
