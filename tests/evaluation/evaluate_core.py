"""Evaluation runner aligned with CUAD extractive QA benchmark (Phase 6 / Tier 0).

Runs CUAD-style extractive prompts through the local BoundedRuntime state machine
and SQLite FTS5 lexical retrieval engine. Extracts verbatim span answers, exact
physical page citations, token usage, and execution latency.
Outputs structured results to docs/reports/eval_results.json.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.agent.runtime import BoundedRuntime
from backend.app.ingest.normalize import normalise
from backend.app.ingest.segment import segment_page
from backend.app.store.db import open_doc_db
from backend.app.store.documents import insert_document
from backend.app.store.pages import insert_page
from backend.app.store.sentences import insert_sentences
from backend.app.validation.renderer import RenderedAnswer

logger = logging.getLogger("lexiguard.evaluation")


def estimate_tokens(text: str) -> int:
    """Accurate heuristic token count (~4 characters or ~1.3 words per token)."""
    if not text:
        return 0
    words = len(text.split())
    chars = len(text)
    return max(1, int(max(words * 1.3, chars / 4)))


def calculate_total_tokens(question: str, answer: RenderedAnswer) -> Dict[str, int]:
    """Calculate prompt, completion, and total tokens for a run."""
    prompt_tokens = estimate_tokens(question)

    completion_text = answer.answer or ""
    for claim in answer.claims:
        completion_text += " " + claim.text
        for ev in claim.evidence:
            completion_text += " " + ev.quote
    for interp in answer.interpretations:
        completion_text += " " + interp.get("text", "")
    for concern in answer.concerns:
        completion_text += " " + concern.get("text", "")
    for gen in answer.general_explanations:
        completion_text += " " + gen.get("text", "")

    completion_tokens = estimate_tokens(completion_text)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def create_eval_db(db_path: Path, fixture_path: Optional[Path] = None) -> sqlite3.Connection:
    """Create a populated evaluation SQLite document database from synthetic fixture."""
    if db_path.exists():
        try:
            db_path.unlink()
        except Exception:
            pass

    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = open_doc_db(db_path)

    # Find fixture text
    if not fixture_path or not fixture_path.exists():
        repo_root = Path(__file__).resolve().parents[2]
        fixture_path = repo_root / "fixtures" / "synthetic_rental_simple.txt"

    content = fixture_path.read_text(encoding="utf-8") if fixture_path.exists() else "Test document content."
    norm_text, _ = normalise(content)

    doc_id = "eval_cuad_doc_001"
    insert_document(
        con,
        document_id=doc_id,
        sha256="eval_cuad_sha256",
        file_type="txt",
        page_count=1,
        has_unread_pages=False,
    )
    insert_page(
        con,
        doc_id=doc_id,
        page_num=1,
        norm_text=norm_text,
        is_readable=True,
        lang_supported=True,
        warnings=[],
    )

    sentences = segment_page(doc_id=doc_id, page_num=1, page_text=norm_text)
    insert_sentences(con, sentences)
    con.commit()
    return con


def run_evaluation(
    questions_file: Path,
    output_file: Path,
    db_path: Optional[Path] = None,
    provider: Optional[Any] = None,
) -> Dict[str, Any]:
    """Execute CUAD-style extractive prompts and generate structured JSON report."""
    if not questions_file.exists():
        raise FileNotFoundError(f"Questions file not found: {questions_file}")

    questions_data: List[Dict[str, Any]] = json.loads(questions_file.read_text(encoding="utf-8"))

    # Connect to or create database
    con_cleanup_needed = False
    if db_path and db_path.exists():
        con = open_doc_db(db_path)
    else:
        temp_eval_db = Path("data/eval_temp/doc.sqlite3")
        con = create_eval_db(temp_eval_db)
        con_cleanup_needed = True

    results: List[Dict[str, Any]] = []
    total_start = time.perf_counter()
    status_counts: Dict[str, int] = {}
    coverage_scores: List[float] = []

    try:
        for idx, item in enumerate(questions_data, start=1):
            qid = item.get("question_id") or item.get("id", f"CUAD_{idx:03d}")
            user_query = item.get("user_query") or item.get("question", "")
            category = item.get("category", item.get("topic", "General"))
            expected_snippets = item.get("expected_verbatim_snippets", [])

            # Execute bounded runtime state machine
            runtime = BoundedRuntime(con=con, provider=provider)
            q_start = time.perf_counter()
            rendered: RenderedAnswer = runtime.run(user_query)
            latency_sec = time.perf_counter() - q_start

            # Extract verbatim spans and citations from verified evidence
            verbatim_spans = []
            for claim in rendered.claims:
                for ev in claim.evidence:
                    verbatim_spans.append({
                        "sid": ev.sid,
                        "page": ev.page,
                        "section": ev.section,
                        "quote": ev.quote,
                    })

            # Check coverage against expected verbatim snippets
            matched_snippets = []
            for exp in expected_snippets:
                for span in verbatim_spans:
                    exp_clean = exp.strip().lower()
                    span_clean = span["quote"].strip().lower()
                    if exp_clean in span_clean or span_clean in exp_clean:
                        matched_snippets.append(exp)
                        break

            coverage = (len(matched_snippets) / len(expected_snippets)) if expected_snippets else 1.0
            coverage_scores.append(coverage)

            token_stats = calculate_total_tokens(user_query, rendered)
            status_counts[rendered.status] = status_counts.get(rendered.status, 0) + 1

            results.append({
                "question_id": qid,
                "category": category,
                "user_query": user_query,
                "expected_status": item.get("expected_status"),
                "expected_verbatim_snippets": expected_snippets,
                "verbatim_spans": verbatim_spans,
                "snippet_coverage": round(coverage, 2),
                "rendered_answer": rendered.model_dump(),
                "latency_seconds": round(latency_sec, 4),
                "latency_ms": round(latency_sec * 1000, 2),
                "token_counts": token_stats,
                "total_tokens": token_stats["total_tokens"],
                "tool_calls": runtime.tool_calls,
                "gemma_calls": runtime.gemma_calls,
            })

    finally:
        con.close()

    total_duration = time.perf_counter() - total_start
    total_tokens = sum(r["total_tokens"] for r in results)
    avg_latency_ms = round((total_duration / len(results) * 1000) if results else 0, 2)
    avg_coverage = round((sum(coverage_scores) / len(coverage_scores) * 100) if coverage_scores else 100.0, 1)

    report = {
        "benchmark": "CUAD (Contract Understanding Atticus Dataset) Extractive QA Alignment",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tier": "Tier 0 (Deterministic lexical fast-path & runtime state machine)",
        "total_questions": len(results),
        "summary": {
            "total_duration_seconds": round(total_duration, 4),
            "avg_latency_ms": avg_latency_ms,
            "total_tokens": total_tokens,
            "avg_tokens_per_question": round(total_tokens / len(results), 1) if results else 0,
            "verbatim_snippet_coverage_pct": avg_coverage,
            "status_breakdown": status_counts,
        },
        "results": results,
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Evaluate LexiGuard BoundedRuntime with CUAD extractive QA paradigm.")
    repo_root = Path(__file__).resolve().parents[2]

    default_questions = repo_root / "tests" / "evaluation" / "ground_truth_questions.json"
    default_output = repo_root / "docs" / "reports" / "eval_results.json"

    parser.add_argument("--questions", type=Path, default=default_questions, help="Path to CUAD questions JSON")
    parser.add_argument("--output", type=Path, default=default_output, help="Path to write evaluation results JSON")
    parser.add_argument("--db", type=Path, default=None, help="Path to SQLite doc.sqlite3 database")

    args = parser.parse_args()

    print(f"[CUAD-EVAL] Running CUAD-aligned evaluation on {args.questions}...")
    report = run_evaluation(questions_file=args.questions, output_file=args.output, db_path=args.db)

    print(f"[CUAD-EVAL] Evaluation completed in {report['summary']['total_duration_seconds']}s")
    print(f"[CUAD-EVAL] Total categories evaluated: {report['total_questions']}")
    print(f"[CUAD-EVAL] Avg latency: {report['summary']['avg_latency_ms']} ms")
    print(f"[CUAD-EVAL] Verbatim span coverage: {report['summary']['verbatim_snippet_coverage_pct']}%")
    print(f"[CUAD-EVAL] Total tokens: {report['summary']['total_tokens']}")
    print(f"[CUAD-EVAL] Status breakdown: {report['summary']['status_breakdown']}")
    print(f"[CUAD-EVAL] Report saved to: {args.output}")
    return 0


# ── Pytest Test Integration ───────────────────────────────────────────────────

def test_evaluate_core(tmp_path: Path):
    """Test that CUAD evaluation runs cleanly, outputs valid report with verbatim citations."""
    repo_root = Path(__file__).resolve().parents[2]
    questions_file = repo_root / "tests" / "evaluation" / "ground_truth_questions.json"
    output_file = tmp_path / "eval_results.json"
    eval_db_path = tmp_path / "eval_cuad_test.sqlite3"

    report = run_evaluation(
        questions_file=questions_file,
        output_file=output_file,
        db_path=eval_db_path,
    )

    assert output_file.exists()
    assert report["total_questions"] >= 4
    assert "summary" in report
    assert report["summary"]["total_tokens"] > 0
    assert report["summary"]["avg_latency_ms"] >= 0

    # Verify CUAD questions 1-4 and per-question structure
    for res in report["results"]:
        assert "question_id" in res
        assert "category" in res
        assert "user_query" in res
        assert "rendered_answer" in res
        assert "verbatim_spans" in res
        assert "total_tokens" in res
        assert "latency_ms" in res
        assert res["rendered_answer"]["legal_verdict"] is None  # Permanently null


if __name__ == "__main__":
    sys.exit(main())
