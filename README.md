# Golden Brown (LexiGuard)

**Private, Evidence-Backed Legal Document Triage Agent**  
*ZeroDay OSS Hacktoberfest 2026 — Problem Statement 2*

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue)](pyproject.toml)
[![Architecture](https://img.shields.io/badge/Privacy-100%25%20Air--Gapped%20Local-success)](docs/reports/network_isolation.log)
[![Evaluation](https://img.shields.io/badge/Benchmark-CUAD%20Aligned-orange)](docs/reports/eval_results.json)

---

## 1. Overview & Problem Statement

**Golden Brown (LexiGuard)** is an offline, privacy-first legal document triage agent designed to help non-lawyers analyze complex residential lease and leave-and-licence agreements without compromising data confidentiality.

Contracts and rental agreements contain sensitive personal data (identities, addresses, financial deposits, bank details). LexiGuard guarantees **zero cloud leakage**: all document parsing, indexing, question answering, and risk triage run entirely on your local machine with strict loopback binding (`127.0.0.1`).

### Core Value Propositions
- **100% Local Execution**: Operates completely disconnected from the internet. No document content, questions, or derived metadata ever leave your computer.
- **Verbatim Evidence Anchoring**: Claims, interpretations, and risks are grounded strictly in verbatim document quotes with physical page and sentence citations.
- **Strict Non-Verdict Policy**: LexiGuard informs and triages; it refuses judicial predictions and enforces a permanently null `legal_verdict` to prevent unauthorized practice of law (UPL).
- **Attention-First Risk Review**: Automatically scans for high-friction contract terms (conflicts, ambiguities, termination notice periods, deposit forfeiture, lock-ins, and jurisdiction flags).
- **Forensic Deletion**: Document databases are stored in dedicated per-document SQLite instances supporting verified unlinking and `PRAGMA secure_delete=ON`.

---

## 2. Architecture & Technology Stack

LexiGuard is engineered under strict **Tier 0 local survival constraints**, maximizing deterministic reliability, low latency, and zero data leakage:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        React + Vite UI (Frontend)                      │
│         - Static client mounted on FastAPI or Vite Dev Server          │
│         - Token-guarded via URL fragment (#k=<launch_code>)            │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP / REST (127.0.0.1:8000)
┌───────────────────────────────────▼────────────────────────────────────┐
│                       FastAPI Application Server                       │
│  - Loopback-only binding (127.0.0.1)                                  │
│  - Single-use Launch Code Exchange (600s TTL session persistence)     │
│  - Security headers (No-Store, CSP, frame-ancestors 'none')           │
└───────────┬───────────────────────┬───────────────────────────┬────────┘
            │                       │                           │
┌───────────▼──────────┐ ┌──────────▼───────────┐ ┌─────────────▼────────┐
│   Isolated Parser    │ │  SQLite FTS5 Storage  │ │   Bounded Runtime    │
│  - Subprocess isol.  │ │  - Per-doc DB store  │ │  - 7-step deterministic│
│  - pypdfium2 (PDF)   │ │  - BM25 lexical rank │ │    state machine     │
│  - Virtual page (.txt│ │  - Rental topic lexs │ │  - Local Ollama      │
│  - Memory/CPU caps   │ │  - Cross-ref expan.  │ │    (Gemma 4 e4b/e2b) │
│  - Graceful fallback │ │  - Zero dense/FAISS  │ │  - Extractive backup │
└──────────────────────┘ └──────────────────────┘ └──────────────────────┘
```

| Component | Technology | Rationale & Operational Role |
| :--- | :--- | :--- |
| **Backend API** | **FastAPI** + **Uvicorn** | High-performance asynchronous API server strictly bound to `127.0.0.1`. |
| **Frontend UI** | **React 18** + **Vite** + **TypeScript** | Responsive single-page application with source viewer, risk review dashboard, and Q&A interface. Mounted directly by FastAPI in production. |
| **PDF Parser** | **pypdfium2** (PDFium) | Sandboxed child-process parser extracting text streams with CPU limits, page limits (50 pages), and text size caps. Fallback handler provides structured errors on unreadable scans. |
| **Text Ingestion** | **Pure Python Normalizer** | Unicode NFKC normalization, paragraph-aware virtual page generation (3,000 chars/page), and regex sentence segmentation. |
| **Lexical Engine** | **SQLite FTS5** + **BM25** | Local full-text search with query term escaping, curated rental topic lexicons (`lexicons/rental_topics.yaml`), and cross-reference expansion. **Zero dense vector databases (no FAISS/torch)** to guarantee low memory and instant startup. |
| **Local LLM** | **Ollama** (`gemma4:e4b-it-q4_K_M`) | Fully offline local language model via native Ollama API. Fast-path constrained to at most one single-turn model call per question. Extractive fallback activates automatically if Ollama is offline. |
| **Agent State Machine**| **BoundedRuntime** | Strictly bounded 7-stage state machine (`RECEIVE -> CLASSIFY -> PLAN -> RETRIEVE -> ANALYZE -> VALIDATE -> RESPOND`). Hard-capped at 8 tool calls and 4 LLM invocations. |

---

## 3. Privacy & Network Isolation Verification

LexiGuard's air-gapped security model has been validated through network socket auditing.

- **Loopback Enforcement**: The FastAPI backend, subprocesses, and Ollama bridge bind exclusively to `127.0.0.1` and `::1`.
- **Egress Prevention**: No external socket calls, analytics pings, or CDN script loads exist in the codebase.
- **Audit Log Verification**: See [`docs/reports/network_isolation.log`](docs/reports/network_isolation.log). A syscall trace confirms 100% loopback socket activity during document upload and QA cycles:
  ```text
  ================================================================================
  LEXIGUARD NETWORK ISOLATION AUDIT LOG (Tier 0 Verification)
  Audit Target: FastAPI Application + Pipeline Ingestion + Local Runtime
  Allowed IPs: 127.0.0.1, ::1, 0.0.0.0 (bind only)
  ================================================================================
  [2026-10-18 16:36:34] SYSCALL=bind TARGET=('::1', 0)
  [2026-10-18 11:06:35] SYSCALL=bind TARGET=('127.0.0.1', 8000)
  [2026-10-18 11:06:36] SYSCALL=connect TARGET=('127.0.0.1', 8000)
  ```
- **Auditing Script**: To re-run the isolation audit on Linux with network namespaces:
  ```bash
  bash scripts/run_privacy_audit.sh
  ```

---

## 4. Evaluation Benchmark: CUAD-Aligned Extractive QA

LexiGuard's extractive accuracy and citation reliability are benchmarked against an extractive QA suite aligned with the **CUAD (Contract Understanding Atticus Dataset)** methodology.

### Benchmark Highlights
- **Report Location**: [`docs/reports/eval_results.json`](docs/reports/eval_results.json)
- **Test Dataset**: Standardized rental contracts and synthetic fixtures covering Core 10 contract topics (Parties, Governing Law, Notice to Terminate, Rent/Deposit, Lock-in, Dispute Resolution).
- **Key Metrics**:
  - **Verbatim Snippet Coverage**: **81.7%**
  - **Average Query Latency**: **7.61 ms** (Deterministic lexical fast-path)
  - **Questions Answered**: **9 / 10** (`ANSWERED` status)
  - **Verdict Refusal Rate**: **100%** (`LEGAL_LIMIT` correctly returned on enforceability query `CUAD_005_LEGAL_VERDICT_REFUSAL`, producing zero hallucinations and zero unauthorized legal judgments).

To execute the evaluation suite:
```bash
python -m tests.evaluation.evaluate_core
```

---

## 5. Setup & Run Instructions

### Prerequisites
- **Python 3.11, 3.12, or 3.13**
- **Node.js ≥ 18** (for compiling frontend assets)
- **Ollama ≥ 0.21.1** (Optional but recommended for full generative QA; extractive fallback works without it)

---

### Step 1: Install & Launch Ollama
1. Download Ollama from [ollama.ai](https://ollama.ai/).
2. Pull the recommended Gemma 4 quantized model:
   ```bash
   ollama pull gemma4:e4b-it-q4_K_M
   ```
   *(Optional lightweight model: `ollama pull gemma4:e2b-it-q4_K_M`)*
3. Ollama will run locally in the background on `http://127.0.0.1:11434`.

---

### Step 2: Set Up Backend Environment
```bash
# Clone the repository
git clone https://github.com/panditshubham766-dotcom/golden_brown2.git
cd golden_brown2

# Create and activate virtual environment
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1

# Install package dependencies
pip install -e ".[dev]"
```

---

### Step 3: Build Frontend (Production Mode)
The frontend build is pre-mounted at `frontend/dist`. If modifying or rebuilding:
```bash
cd frontend
npm install
npm run build
cd ..
```

---

### Step 4: Run the Server
Launch the unified FastAPI server:
```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Upon startup, the server prints a secure launch URL with a pre-authenticated session token:
```text
============================================================
  LexiGuard is running.
  Open this URL in your browser (valid for 600s):
  http://127.0.0.1:8000/#k=<launch_code>
============================================================
```
Open the printed URL in your browser to start triaging agreements.

---

### Step 5: (Alternative) Run Frontend in Development Mode
If actively developing the frontend with hot-module reloading (HMR):
```bash
cd frontend
npm run dev
```
The Vite dev server will run on `http://localhost:5173`. Make sure the FastAPI backend is running on port 8000.

---

## 6. Running the Test Suite

Run the full suite of unit, integration, and retrieval tests:
```bash
# Run all unit and integration tests (40+ tests)
python -m pytest tests/unit tests/integration -v

# Run retrieval-specific tests
python -m pytest tests/retrieval -v
```

---

## 7. Project Structure

```text
golden_brown/
├── backend/app/
│   ├── agent/             # Bounded state machine runtime & query router
│   ├── api/               # FastAPI endpoints (/session, /documents, /ask, /review)
│   ├── ingest/            # Parser subprocess (pypdfium2), normalizer, segmentation
│   ├── model/             # Ollama native API client & prompt definitions
│   ├── retrieval/         # SQLite FTS5 BM25 lexical search & cross-ref expansion
│   ├── security/          # Launch code token store & security headers middleware
│   ├── store/             # Per-document SQLite schemas, FTS tables & deletion
│   └── validation/        # Grounding validator, quote scanner & RenderedAnswer
├── frontend/              # React 18 + Vite + TypeScript application
│   ├── src/               # UI components (Upload, Viewer, Review Dashboard, Ask)
│   └── dist/              # Compiled production static bundle
├── docs/
│   ├── reports/           # LIMITATIONS.md, network_isolation.log, eval_results.json
│   └── SOLUTION_GUIDE_v3.md # Architectural design authority
├── fixtures/              # Synthetic rental agreement test fixtures
├── lexicons/              # Curated rental topics & jurisdiction keyword lists
└── tests/                 # Unit, integration, retrieval, and CUAD evaluation tests
```

---

## 8. Limitations & Boundary Scope

For a comprehensive analysis of Tier 0 design decisions, see [`docs/reports/LIMITATIONS.md`](docs/reports/LIMITATIONS.md):
- **No Dense Embeddings (No FAISS)**: Intentional omission to prevent non-deterministic neural drift and high memory footprints.
- **No Optical Character Recognition (OCR)**: Scanned image-only PDFs are safely flagged as unreadable; false negative assumptions are avoided.
- **No Unconstrained Agent Loops**: Continuous multi-turn agent frameworks (e.g. Hermes) are replaced by bounded state machines to eliminate infinite loops and context overflows.
- **Informational Triage Only**: LexiGuard provides document triage and quote retrieval; it does not replace consultation with a licensed legal practitioner.

---

## 9. License & Attribution

- **Source Code**: Released under the [Apache License 2.0](LICENSE).
- **Component Attribution**: See [NOTICE](NOTICE) for PDFium / `pypdfium2` (BSD-3-Clause) licensing and curated lexicon attributions.