#Golden Brown

**Private, evidence-backed legal-document triage — ZeroDay OSS Hacktoberfest 2026, Problem Statement 2**

> **Status: early development — Phase 1 in progress.**  
> No application is shipped yet. No tests have run. No privacy, accuracy or benchmark claim is verified.  
> Do not rely on this repository for any legal purpose.

## What this project will do (planned)

Help a non-lawyer understand what an English rental / leave-and-licence agreement says:

- Accept a PDF or TXT file and process it **entirely on your device** — no document ever leaves your machine.
- Extract page-level text with `pypdfium2` in a sandboxed child process.
- Build a lexical (SQLite FTS5/BM25) index over the document.
- Answer questions using a locally running Gemma 4 model via Ollama.
- Cite exact source passages; show the physical page and sentence.
- Distinguish stated fact, restatement, interpretation, concern, ambiguity and conflict.
- Explain rental terms from a curated local glossary.
- Flag topics that may depend on local law.
- Detect missing evidence and refuse to give a legal verdict.
- Support verified deletion of all derived data.

## What is NOT yet built

- No working application — source files are being written in Phase 1.
- No RAG engine, no FAISS, no dense retrieval in the default build.
- No cloud component; privacy claims require a verified isolated-network run (not yet done).
- No Hermes integration (ADR-0010: not built).
- No evaluation results yet.

## Technology choices (locked)

| Concern | Decision |
|---------|----------|
| Frontend | React + Vite + TypeScript (Phase 4+) |
| Backend | Python + FastAPI, bound to `127.0.0.1` only |
| PDF parser | `pypdfium2` in a child process; **not PyMuPDF** |
| Model | `gemma4:e4b-it-q4_K_M` via Ollama ≥ 0.21.1 (native API) |
| Storage | Per-document SQLite + FTS5; `PRAGMA secure_delete=ON` |
| Dense retrieval | Off by default; not in the default install |
| Hermes | Not built (see `docs/adr/0010-hermes-not-built.md`) |
| License | Apache-2.0 |

## Setup (not yet functional — instructions will be finalised in Phase 9)

```
# 1. Install Ollama >= 0.21.1 and pull models
ollama pull gemma4:e4b-it-q4_K_M
ollama pull gemma4:e2b-it-q4_K_M

# 2. Install Python dependencies
pip install -e ".[dev]"

# 3. Run (development)
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

## Licence

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).  
Model licence: see `docs/MODEL_LICENSE.md` (to be populated at pin time).