# AGENTS.md — Instructions for automated coding agents working on LexiGuard

## Read this first

Before changing any source file:

1. Read `docs/SOLUTION_GUIDE_v3.md` in full — it is the sole design authority.
2. Read `TASKS.md` to understand which phase is active and what is unfinished.
3. Inspect the actual working tree; do not assume files exist.

## Guiding principles

- **Real, not mocked.** Every feature must be implemented and testable. Do not create stub files that claim tests pass.
- **Fail closed.** When uncertain (model unavailable, schema invalid, parse error), return a controlled error status — never guess or invent data.
- **Deterministic code owns truth.** The model proposes; validators and policy decide what may be shown.
- **No legal verdicts.** Never generate or allow text that concludes an agreement is valid/invalid, enforceable, legal, illegal, fair or unfair.
- **Privacy.** No document content leaves the device. No cloud fallback. Loopback only.
- **Honest docs.** No placeholder doc may claim an unperformed test passed.

## Synthetic fixtures only

Never commit a real rental agreement, private document, model weight, user data, secret, API key or personal information. All fixtures must be clearly marked as synthetic in `fixtures/README.md`.

## Before claiming a phase complete

Run the relevant tests, check actual pass/fail counts, update `TASKS.md` and commit only real test results. A feature is not complete because source files exist.

## What NOT to build (Tier 0 cut)

- OCR / Tesseract (Phase 1b — Tier 1 only)
- Dense retrieval / FAISS / torch / sentence-transformers
- Hermes (ADR-0010 — not built unless precondition in §12 of the Guide is met)
- Entailment pass (Tier 2)
- Evaluate lexical-vs-dense comparison (only if dense is enabled)

## Commit discipline

- Commit after each phase with a descriptive message referencing the phase number.
- Never push, force-push or take destructive remote actions unless the user explicitly asks.
- Keep all changes on the current feature branch.
