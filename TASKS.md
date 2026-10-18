# TASKS.md — LexiGuard implementation tracker

## Deadline

Hard deadline: 18 Oct 2026, 19:00 IST (13:30 UTC).

## Active tier: Tier 0 (submittable core)

Tier 0 = Phases 0–4 cut-down + T8 smoke capture + honest README/docs.

---

## Phase 0 — INSPECT, FREEZE, DOCUMENT

**Status: IN PROGRESS**

- [x] Inspect repo (branch, tree, .gitignore, LICENSE, README)
- [x] Replace README with honest status README
- [x] Create NOTICE
- [x] Create AGENTS.md
- [x] Create TASKS.md (this file)
- [ ] Create pyproject.toml
- [ ] Create CONTRIBUTING.md
- [ ] Create CODE_OF_CONDUCT.md
- [ ] Create .gitignore (update)
- [ ] Create docs/REQUIREMENTS.md
- [ ] Create docs/ARCHITECTURE.md
- [ ] Create docs/DATA_FLOW.md
- [ ] Create docs/PRIVACY.md
- [ ] Create docs/LIMITATIONS.md
- [ ] Create docs/MODEL.md
- [ ] Create docs/MODEL_SETUP.md (fill at pin time)
- [ ] Create docs/MODEL_LICENSE.md (fill at pin time)
- [ ] Create docs/EVALUATION.md (targets only, results pending)
- [ ] Create docs/TEST_PLAN.md
- [ ] Create docs/adr/ initial ADRs
- [ ] Create Makefile scaffold
- [ ] CI scaffold (.github/workflows/ci.yml)

---

## Phase 1 — INGESTION

**Status: IN PROGRESS**

### 1.1 FastAPI skeleton

- [x] backend/app/main.py — app factory, static serving, startup checks
- [x] backend/app/config.py — settings (Pydantic)
- [x] backend/app/security/ — tokens, host/origin validation, headers
- [x] backend/app/api/ — route stubs (documents, health)

### 1.2 Upload validation

- [x] backend/app/ingest/upload.py — magic bytes, size, page cap, encoding
- [x] backend/app/ingest/worker.py — orchestrate ingest pipeline
- [x] backend/app/ingest/parser.py — child-process pypdfium2 runner
- [x] backend/app/ingest/normalize.py — CRLF→LF, NFC, whitespace
- [x] backend/app/ingest/segment.py — page→headings→paragraphs→sentences + sid generation
- [x] backend/app/ingest/quality.py — per-page quality gate
- [x] backend/app/ingest/language.py — per-page language gate (no ML)

### 1.3 SQLite/FTS5 store

- [x] backend/app/store/db.py — connection factory, PRAGMA setup
- [x] backend/app/store/documents.py — document table CRUD
- [x] backend/app/store/pages.py — pages table
- [x] backend/app/store/sentences.py — sentences table
- [x] backend/app/store/fts.py — FTS5 index helpers
- [x] backend/app/store/delete.py — safe deletion service

### 1.4 Tests (T-ING-*)

- [ ] tests/unit/test_upload_validation.py
- [ ] tests/unit/test_normalize.py
- [ ] tests/unit/test_segment.py
- [ ] tests/unit/test_quality_language.py
- [ ] tests/integration/test_ingest_pipeline.py
- [ ] tests/integration/test_deletion.py

---

## Phase 2 — OLLAMA ADAPTER (not started)

## Phase 3 — RETRIEVAL (not started)

## Phase 4 — VERTICAL SLICE (not started)

---

## Known gaps / unresolved

- Python launcher path needs to be confirmed on the demo machine.
- Ollama tags/digests must be verified at run time with scripts/verify_model_tags.py.
- Parser sandbox limits: Windows has no `resource` module; startup notice will be emitted.
- All metrics are NOT YET RUN — do not treat any target as achieved.
