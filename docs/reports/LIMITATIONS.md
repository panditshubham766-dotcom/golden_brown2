# LexiGuard Limitations & System Scope Report (Tier 0)

> **Execution Tier:** **Tier 0 (Survival Mode)**  
> **Status:** Measured & Verified  
> **Design Authority:** `docs/SOLUTION_GUIDE_v3.md`

This document provides a rigorous, transparent breakdown of the operational boundaries, architectural decisions, and known limitations of the Golden Brown / LexiGuard system running in **Tier 0**.

---

## 1. Tier 0 Execution Mode

Golden Brown is currently running in **strict Tier 0 survival mode**. This mode prioritizes maximum deterministic reliability, low latency, and zero data leakage over non-essential agentic complexity:

- **Bounded State Machine Runtime:** The core execution engine is a strictly bounded, non-looping state machine (`RECEIVE -> CLASSIFY -> PLAN -> RETRIEVE -> ANALYZE -> VALIDATE -> RESPOND`).
- **Lexical-First Retrieval:** All search operations are powered by SQLite FTS5 with BM25 ranking, rental topic lexicons, and deterministic cross-reference resolution. Dense retrieval embeddings and FAISS were intentionally excluded from the core dependency footprint to eliminate memory overhead, heavy C++ extensions, and non-deterministic neural search behaviors.
- **Fast-Path Inference:** When lexical retrieval is confident, the system enforces a fast-path constraint of at most one single-turn Gemma 4 model call with an absolute per-question ceiling of 4 calls (including format retries).

---

## 2. Intentional Omissions (Phases 1b and 8)

To preserve rock-solid system stability, rapid startup, and minimal hardware requirements on consumer devices, the following two components were intentionally omitted:

### A. Phase 1b: Tesseract OCR
- **Rationale:** Tesseract OCR requires heavy native binaries, complex C++ dependencies (`tesseract`, `leptonica`), and multi-gigabyte language trained data. Running OCR on consumer CPUs introduces prohibitive latency (often 10–30 seconds per page) and unpredictable memory spikes.
- **Operational Impact:** Golden Brown processes digital PDFs containing embedded text streams and plain text agreements (`.txt`). Scanned or image-only PDF pages without text streams are detected by the quality gate (`assess_page`) and flagged as unreadable. In accordance with safety policies, unread pages prevent false negative assumptions and safely return `INSUFFICIENT_EVIDENCE` rather than attempting speculative OCR.

### B. Phase 8: Hermes Agentic Framework
- **Rationale:** As documented in `ADR-0010 (Hermes Not Built)`, multi-turn unconstrained agentic loops (such as Hermes or auto-reflection agents) introduce non-deterministic execution paths, risk of infinite tool-calling loops, context window exhaustion, and model hallucinations.
- **Operational Impact:** Replaced completely by the deterministic `BoundedRuntime` state machine. Maximum tool calls are hard-capped at 8, retrieval loops at 2, and Gemma calls at 4. The model never dictates execution flow, never selects which document database to open, and cannot forge sentence IDs.

---

## 3. PDF Table Parsing & Layout Analysis Limitations

- **Text Stream Chunking vs. 2D Layout Analysis:** Golden Brown utilizes `pypdfium2` for secure, sandboxed PDF text extraction. Extraction operates on the underlying content stream rather than performing computer-vision layout decomposition.
- **Complex Table Degradation:** For rental agreements containing complex tabular matrices (such as multi-tier rent escalation schedules, multi-column utility breakdown tables, or shared repair matrices), text extracted sequentially from the stream may interleave adjacent columns or break table rows across sentence boundaries.
- **Impact on Retrieval:** While lexical FTS5 will locate keywords inside tabular chunks, semantic association between column headers and cell values may be degraded. Users are advised to verify tabular numerical figures against the original document viewer.

---

## 4. Parser Sandboxing & Platform Parity

The PDF parser child process enforces strict security boundaries, but enforcement mechanisms vary across host operating systems:

- **Windows:** The POSIX `resource` module is unavailable on Windows. Memory and CPU limits are enforced via process timeouts (default 15s), maximum output byte caps (10MB), and total page count caps (50 pages). OS-level Job Object memory ceilings are not applied.
- **macOS:** `RLIMIT_AS` is not reliably honored by the Darwin kernel; an active RSS watchdog monitoring thread is utilized instead.
- **Linux:** Full platform sandboxing is enforced using `RLIMIT_CPU`, `RLIMIT_AS`, wall-clock watchdog timeouts, and output size caps.

---

## 5. Citation Integrity vs. Semantic Faithfulness

The verification subsystem (`backend/app/validation/`) implements deterministic checks for restatements and stated claims:
- **Literal Number/Date Matching:** Ensures amounts (e.g., "Rs. 25,000", "75000") and dates exist verbatim in the supporting source clause.
- **Role Swap & Party Protection (`T-CITE-ROLE-01`):** Ensures obligations belonging to the tenant cannot be attributed to the landlord, and vice versa.
- **Provenance Enforcement:** Discards any sentence ID (`sid`) that was not explicitly returned by approved tools during the current query execution.

**Crucial Caveat:** These checks verify **citation integrity** (that the cited text directly supports the numbers, entities, and obligations claimed). They **do not prove semantic legal validity** or resolve conflicting case law.

---

## 6. Strict Non-Verdict Policy & Legal Disclaimer

- **Permanently Null Legal Verdict:** `RenderedAnswer.legal_verdict` is permanently set to `None`.
- **Verdict Scanner (`T-LEGAL-FP-01`):** A strict dual-regex scanner monitors all assistant-generated output. Queries seeking legal conclusions ("is this valid", "can I sue", "is this enforceable") are intercepted by the deterministic router and directed to `Route.LEGAL_CONCLUSION`.
- **Advisory Status:** LexiGuard is an informational document triage tool for non-lawyers. It is **not an attorney and does not provide legal advice**. When contractual interpretation or statutory rights are at issue, the system explicitly recommends consulting a qualified legal professional.

---

## 7. Data Deletion & Privacy Boundaries

- **Application-Level Erasure:** Deletion requests (`DELETE /api/documents/{id}`) invoke `PRAGMA secure_delete=ON`, zero out SQLite FTS shadow tables, close all file handles, and remove directory trees via `shutil.rmtree`.
- **Forensic Caveats:** This process does not guarantee forensic erasure against SSD hardware-level wear-leveling algorithms, OS swap/hibernation files, or external automated backup systems (e.g. OneDrive, Time Machine).
- **Network Privacy:** Verified by `scripts/run_privacy_audit.sh`. The application binds exclusively to `127.0.0.1` and executes with zero external network connectivity.
