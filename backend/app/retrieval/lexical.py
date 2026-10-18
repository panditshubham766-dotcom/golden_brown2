"""Lexical retrieval using SQLite FTS5 / BM25 and deterministic cross-reference expansion.

Strictly capped at 12 chunks per search result.
No dense retrieval or FAISS.
"""
from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("lexiguard.retrieval.lexical")

MAX_CHUNKS = 12

# Rupee / number normalisation
_RUPEE_RE = re.compile(r"(?:Rs\.?|INR|₹)\s*([\d,]+)(?:/-)?")
_COMMA_NUM_RE = re.compile(r"([\d,]+)")

# Cross-reference patterns
_XREF_PATTERNS = [
    re.compile(
        r"(?:subject to|pursuant to|in accordance with|provided under|under|refer to|read with|as per)\s*(?:clause|section|article|cl\.)?\s*([0-9]+(?:\.[0-9]+)*|[a-zA-Z]|[ivxlcdm]+)",
        re.IGNORECASE,
    ),
    re.compile(r"(?:clause|section|article|cl\.)\s*([0-9]+(?:\.[0-9]+)*|[ivxlcdm]+)", re.IGNORECASE),
    re.compile(r"(?:schedule|annexure|appendix)\s*([0-9a-zA-Z]+)", re.IGNORECASE),
]


@dataclass
class SearchHit:
    sid: str
    page_num: int
    section: str
    sentence_text: str
    bm25_rank: float
    source: str = "fts"


def _normalise_numbers(text: str) -> str:
    """Produce normalised-number text for matching."""
    result = _RUPEE_RE.sub(lambda m: m.group(1).replace(",", ""), text)
    result = _COMMA_NUM_RE.sub(lambda m: m.group(1).replace(",", ""), result)
    return result


def _escape_fts5_term(term: str) -> str:
    """Escape a term safely for FTS5 unicode61 tokenizer."""
    safe = re.sub(r'["\^\*\:\(\)\{\}\[\]\\]', " ", term)
    tokens = [t.strip() for t in safe.split() if t.strip()]
    if not tokens:
        return ""
    # Wrap each token in double quotes for safe exact token matching
    return " ".join(f'"{t}"' for t in tokens)


def load_rental_topics(path: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """
    Load rental topics and synonyms from lexicons/rental_topics.yaml.
    Supports PyYAML with a pure-Python fallback.
    """
    if path is None:
        # Standard repository location
        root = Path(__file__).resolve().parents[3]
        candidate = root / "lexicons" / "rental_topics.yaml"
        if candidate.exists():
            path = candidate
        else:
            path = Path("lexicons/rental_topics.yaml")

    if not path.exists():
        return {}

    content = path.read_text(encoding="utf-8")
    try:
        import yaml
        loaded = yaml.safe_load(content)
        if isinstance(loaded, dict) and "topics" in loaded:
            return loaded["topics"]
    except Exception:
        pass

    # Pure-Python fallback parser for the YAML structure
    topics: Dict[str, Dict[str, Any]] = {}
    current_topic: Optional[str] = None
    in_synonyms = False

    for line in content.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue

        match_topic = re.match(r"^ {2}([a-zA-Z0-9_-]+):", line)
        if match_topic and not line.strip().startswith("topics:"):
            current_topic = match_topic.group(1)
            topics[current_topic] = {"label": current_topic, "synonyms": []}
            in_synonyms = False
            continue

        if current_topic:
            match_label = re.match(r'^ {4}label:\s*"?([^"]+)"?', line)
            if match_label:
                topics[current_topic]["label"] = match_label.group(1)
                continue

            if re.match(r"^ {4}synonyms:", line):
                in_synonyms = True
                continue

            if in_synonyms:
                match_syn = re.match(r'^ {6}-\s*"?([^"]+)"?', line)
                if match_syn:
                    topics[current_topic]["synonyms"].append(match_syn.group(1))

    return topics


def extract_cross_references(text: str) -> List[str]:
    """Deterministically extract referenced clause / section / schedule labels from text."""
    references: Set[str] = set()
    for pattern in _XREF_PATTERNS:
        for match in pattern.finditer(text):
            ref = match.group(1).strip()
            if ref and len(ref) <= 15:
                references.add(ref)
    return sorted(references)


def _expand_cross_references(
    con: sqlite3.Connection,
    source_hits: List[SearchHit],
    existing_sids: Set[str],
    max_to_add: int,
) -> List[SearchHit]:
    """Retrieve sentences referenced by source hits."""
    if max_to_add <= 0:
        return []

    target_refs: Set[str] = set()
    for hit in source_hits:
        for ref in extract_cross_references(hit.sentence_text):
            target_refs.add(ref)

    if not target_refs:
        return []

    expanded_hits: List[SearchHit] = []
    for ref in target_refs:
        if len(expanded_hits) >= max_to_add:
            break

        # Match section exactly or with prefix, or matching starting clause number
        query = """
            SELECT sid, page_num, section, sentence_text
            FROM sentences
            WHERE section = ?
               OR section LIKE ?
               OR sentence_text LIKE ?
               OR sentence_text LIKE ?
            ORDER BY page_num, start_offset
            LIMIT ?
        """
        params = (
            ref,
            f"{ref}.%",
            f"{ref}. %",
            f"Clause {ref}%",
            max_to_add - len(expanded_hits),
        )

        try:
            rows = con.execute(query, params).fetchall()
        except sqlite3.OperationalError:
            continue

        for row in rows:
            sid = row["sid"]
            if sid not in existing_sids:
                existing_sids.add(sid)
                expanded_hits.append(
                    SearchHit(
                        sid=sid,
                        page_num=row["page_num"],
                        section=row["section"],
                        sentence_text=row["sentence_text"],
                        bm25_rank=0.0,
                        source=f"cross_ref:{ref}",
                    )
                )
                if len(expanded_hits) >= max_to_add:
                    break

    return expanded_hits


def search_lexical(
    con: sqlite3.Connection,
    query: str = "",
    topic: Optional[str] = None,
    expand_xrefs: bool = True,
    limit: int = MAX_CHUNKS,
) -> List[SearchHit]:
    """
    Search SQLite FTS5 index with BM25 ranking and optional cross-reference expansion.

    Guarantees:
    - Never returns more than 12 chunks.
    - Pure lexical / BM25; zero dense retrieval or FAISS.
    """
    effective_limit = min(max(1, limit), MAX_CHUNKS)
    search_terms: List[str] = []

    # 1. Detect topic from query if topic was not explicitly provided
    topics_dict = load_rental_topics()
    active_topic = topic
    if not active_topic and query.strip():
        q_lower = query.lower()
        for t_key in topics_dict:
            if re.search(r"\b" + re.escape(t_key) + r"\b", q_lower):
                active_topic = t_key
                break

    # Add topic synonyms
    if active_topic:
        t_lower = active_topic.strip().lower()
        if t_lower in topics_dict:
            synonyms = topics_dict[t_lower].get("synonyms", [])
            for syn in synonyms:
                escaped = _escape_fts5_term(syn)
                if escaped:
                    search_terms.append(escaped)
        else:
            escaped_topic = _escape_fts5_term(active_topic)
            if escaped_topic:
                search_terms.append(escaped_topic)

    # 2. Add user query terms (filter out common conversational question stopwords and prompt wrappers)
    _STOPWORDS = frozenset([
        "what", "is", "the", "are", "was", "were", "when", "where", "how", "why", "who",
        "does", "do", "did", "can", "could", "will", "would", "shall", "should", "a", "an",
        "of", "to", "in", "on", "for", "at", "by", "with", "from", "about", "tell", "me", "please",
        "highlight", "parts", "part", "contract", "related", "any", "this", "if"
    ])
    if query.strip():
        # Prioritize quoted phrases (e.g. 'Parties', 'Governing Law', 'Notice Period to Terminate')
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", query)
        for qphrase in quoted:
            escaped_qphrase = _escape_fts5_term(qphrase)
            if escaped_qphrase and escaped_qphrase not in search_terms:
                search_terms.insert(0, escaped_qphrase)

        # First add clean content tokens individually
        clean_words = [
            w for w in re.findall(r"[a-zA-Z0-9_-]+", query)
            if w.lower() not in _STOPWORDS and len(w) > 1
        ]
        for w in clean_words:
            search_terms.append(f'"{w}"')

        # Also add the full phrase if short (<= 8 tokens)
        if len(clean_words) <= 8:
            escaped_query = _escape_fts5_term(" ".join(clean_words))
            if escaped_query and escaped_query not in search_terms:
                search_terms.append(escaped_query)

    if not search_terms:
        return []

    # Combine with OR for FTS5
    fts_expression = " OR ".join(f"({term})" for term in search_terms)

    hits: List[SearchHit] = []
    seen_sids: Set[str] = set()

    try:
        rows = con.execute(
            """
            SELECT s.sid, s.page_num, s.section, s.sentence_text,
                   bm25(sentences_fts) AS rank
            FROM sentences_fts
            JOIN sentences s ON s.rowid = sentences_fts.rowid
            WHERE sentences_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts_expression, effective_limit),
        ).fetchall()

        for row in rows:
            sid = row["sid"]
            if sid not in seen_sids:
                seen_sids.add(sid)
                hits.append(
                    SearchHit(
                        sid=sid,
                        page_num=row["page_num"],
                        section=row["section"],
                        sentence_text=row["sentence_text"],
                        bm25_rank=float(row["rank"]),
                        source="fts",
                    )
                )
    except sqlite3.OperationalError as exc:
        logger.warning("FTS5 query failed: %s", exc)

    # 3. Deterministic cross-reference expansion
    if expand_xrefs and hits and len(hits) < effective_limit:
        remaining = effective_limit - len(hits)
        xref_hits = _expand_cross_references(con, hits, seen_sids, remaining)
        hits.extend(xref_hits)

    # Strictly cap to MAX_CHUNKS
    return hits[:effective_limit]
