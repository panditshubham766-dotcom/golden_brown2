# LexiGuard Frontend — API Contract Gap Register & Integration Checkpoint

> **Specification Basis**: LexiGuard Final Requirements v3.2, Solution Guide v3.1, Review Findings v3.0, and Limitations v3.0.  
> **Backend Code Analysis Date**: 2026-10-18  
> **Status**: Provisional shapes established in `src/api/contracts.ts`; pending final live backend reconciliation.

This document records the exact wire-level decisions between the frontend and the FastAPI backend as outlined in Master Implementation Prompt Part II §5.3.

---

## 1. Session Bootstrap (`POST /api/session`)

| Item | Frontend Assumption (Mock / Client) | Backend Status / OpenAPI Requirement | Status |
| :--- | :--- | :--- | :--- |
| **Request Body** | `{"code": "<launch_code>"}` | Derived from `session.py` one-time code exchange. | **Confirmed** |
| **Response Body** | `{"token": "<bearer_token>"}` | Returns JSON token. Token is stored only in memory (`useRef` in React context). | **Confirmed** |
| **Auth Exception** | No `Authorization: Bearer` header on this endpoint only. | Permitted by FastAPI dependency for bootstrap. | **Confirmed** |
| **Error Statuses** | `401 Unauthorized` for expired, re-used, or invalid code. | Backend returns 401. UI clears token and prompts relaunch. | **Confirmed** |
| **Revocation** | Reloading browser intentionally loses token. Subsequent calls return 401. | State cleared; no infinite retry loops. | **Confirmed** |

---

## 2. Health Endpoint (`GET /api/health`)

| Item | Frontend Assumption | Backend Status | Status |
| :--- | :--- | :--- | :--- |
| **Authorization** | Requires `Authorization: Bearer <token>`. | Protected endpoint in `main.py`. | **Confirmed** |
| **Response Body** | `{"ok": true, "fts5": true}` | Booleans only; never leaks system paths, secret keys, or model prompts. | **Confirmed** |

---

## 3. Document Ingestion / Upload (`POST /api/documents`)

| Item | Frontend Assumption | Backend Status | Status |
| :--- | :--- | :--- | :--- |
| **Method / Format** | `multipart/form-data` | FastAPI `UploadFile = File(...)`. | **Confirmed** |
| **Form Field Name** | `"file"` | Checked against `api/documents.py`. | **Confirmed** |
| **Accepted Types** | PDF (`application/pdf`, magic `%PDF-`) and TXT (`text/plain`). | Validated by backend `magic` bytes / parser. | **Confirmed** |
| **Max File Size** | 50 MB (local check); backend authoritative (returns 413). | Return 413 Payload Too Large. | **Confirmed** |
| **Response Body** | `{"document_id": string, "page_count": number, "quality": object, "warnings": string[], "status": string}` | Defined in worker/pipeline models. | **Confirmed** |
| **Progress Reporting** | Truthful status only ("Uploading and analysing…"). No invented percentages. | Ingestion is synchronous or fast background job. | **Confirmed** |

---

## 4. Document Listing (`GET /api/documents`)

| Item | Frontend Assumption | Backend Status | Status |
| :--- | :--- | :--- | :--- |
| **Response Body** | `DocumentCard[]`: `[{"document_id": string, "page_count": number, "status": string, "quality_summary": string, "warnings": string[], "created_at": string}]` | Minimal display metadata only. | **Confirmed** |
| **Persistence** | In-memory query result. No local storage caching. | Read directly from SQLite/runtime store. | **Confirmed** |

---

## 5. Document Overview & Core 10 Map (`GET /api/documents/{id}/overview`)

| Item | Frontend Assumption | Backend Status | Status |
| :--- | :--- | :--- | :--- |
| **Endpoint Path** | `POST /api/documents/{id}/review` or `GET /api/documents/{id}/overview` | In backend source, Core 10 topics are assessed via review pipeline. | **Provisional** |
| **Core 10 Categories** | 1. Parties, 2. Term, 3. Rent, 4. Deposit, 5. Notice, 6. Lock-in, 7. Penalties, 8. Restrictions, 9. Maintenance, 10. Disputes. | Aligned with versioned rental topic lexicon in backend. | **Confirmed** |
| **Evidence Gating** | Each card renders verbatim quote with physical page number. "Not located" displayed when absent; never claims legal absence. | Backend provides `EvidenceItem` or null. | **Confirmed** |

---

## 6. Question Answering (`POST /api/documents/{id}/ask`)

| Item | Frontend Assumption | Backend Status | Status |
| :--- | :--- | :--- | :--- |
| **Request Body** | `{"question": string}` (Max 500 characters, validated client & server). | Enforced in `ask.py`. | **Confirmed** |
| **Response Model** | `RenderedAnswer` from `renderer.py`: `status`, `answer`, `claims`, `interpretations`, `concerns`, `ambiguities`, `conflicts`, `general_explanations`, `missing_information`, `extraction_warnings`, `external_law_required`, `jurisdiction_flags`, `recommend_professional_review`, `legal_verdict: null`. | Matches backend `renderer.py` Pydantic models. | **Confirmed** |
| **Legal Verdict** | Always `null`. No judicial prediction or legal validity judgement. | Backend strictly outputs null. Frontend displays legal disclaimer. | **Confirmed** |
| **Evidence Quoting** | Immutable quote string, physical page (1-based), section heading, `ocr_derived: boolean`. | Preserved verbatim; no frontend rewriting. | **Confirmed** |
| **Ledger Metadata** | Process metadata only (classification route, pages searched, sentence IDs). | No chain-of-thought, no private prompts exposed. | **Confirmed** |

---

## 7. Risk Review Dashboard (`POST /api/documents/{id}/review`)

| Item | Frontend Assumption | Backend Status | Status |
| :--- | :--- | :--- | :--- |
| **Ordering** | Attention-first priority: 1. Conflicts, 2. Ambiguity, 3. Payment/penalty/lock-in, 4. Jurisdiction, 5. Standard found, 6. Not located, 7. Not assessed. | Frontend implements deterministic attention sort. | **Confirmed** |
| **Conflict Display** | Both conflicting clauses rendered side-by-side with respective page citations. | Supported via multiple `evidence` entries. | **Confirmed** |
| **Professional Questions**| Neutral questions derived from backend `professional_questions` array. | Displayed with supporting citations. | **Confirmed** |
| **Status Vocabulary** | `FOUND`, `NOT_FOUND` ("Not located in document"), `AMBIGUOUS`, `POSSIBLE_CONFLICT`, `NOT_ASSESSED`. | Distinct from `AskStatus`. `NOT_ASSESSED` is never conflated with `NOT_FOUND`. | **Confirmed** |

---

## 8. Source Page & Evidence Retrieval (`GET /api/documents/{id}/pages/{n}`)

| Item | Frontend Assumption | Backend Status | Status |
| :--- | :--- | :--- | :--- |
| **Page Text** | Plain text string (`text/plain`). | Backend returns `norm_text` as raw text. | **Confirmed** |
| **Printed Label** | Displayed separately from physical page number when present. | Provisional wrapper handles physical vs printed distinction. | **Provisional** |
| **Highlighting** | Exact text matching on returned evidence quote only. Never fabricates imaginary bounding boxes or token offsets. | Safe string search highlight. | **Confirmed** |
| **Page Image** | `GET /api/documents/{id}/pages/{n}/image` | Returns Blob/PNG if OCR/PDF renderer produced page image. | **Provisional** |

---

## 9. Document Deletion & Verification (`DELETE /api/documents/{id}`)

| Item | Frontend Assumption | Backend Status | Status |
| :--- | :--- | :--- | :--- |
| **Response Body** | `{"document_id": string, "app_files_removed": boolean, "fts_rows_removed": boolean, "directory_absent": boolean, "note": string}` | Matches `delete.py` response dict. | **Confirmed** |
| **State Clearing** | Wipes active document, cached pages, question, answer, review, and search data from memory. | Full memory wipe in `AppStateProvider.clearDocumentState()`. | **Confirmed** |
| **Forensic Caveat** | Clearly displays backend note: App-controlled removal does NOT constitute forensic erasure from SSD/swap/backups. | Displayed on deletion modal and confirmation report. | **Confirmed** |

---

## 10. Security & Privacy Constraints

1. **No External Network Calls**: Zero CDNs, Google Fonts, remote icons, or analytics. Built assets are self-contained.
2. **No Persistent Storage**: Zero usage of `localStorage`, `sessionStorage`, `indexedDB`, or `document.cookie`.
3. **No Caching of Private Data**: API calls enforce `cache: 'no-store'`.
4. **Content Security Policy**: Compatible with `default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'`.
