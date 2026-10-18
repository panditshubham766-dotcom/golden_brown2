/**
 * LexiGuard API wire contracts.
 *
 * IMPORTANT: Do not add fields that are not confirmed in the backend source.
 */

// ── Session ───────────────────────────────────────────────────────────────────

/** POST /api/session — request body */
export interface SessionExchangeRequest {
  /** One-time launch code from URL fragment */
  code: string;
}

/** POST /api/session — response */
export interface SessionTokenResponse {
  /** Bearer token to use for all subsequent /api/* calls */
  token: string;
}

// ── Health ────────────────────────────────────────────────────────────────────

/** GET /api/health — response (token-protected) */
export interface HealthResponse {
  ok: boolean;
  fts5: boolean;
}

// ── Documents ─────────────────────────────────────────────────────────────────

/** GET /api/documents — single card in the list */
export interface DocumentCard {
  document_id: string;
  page_count: number;
  /** "ready" | "processing" | "error" — from backend source */
  status: DocumentStatus;
  quality_summary: string;
  warnings: string[];
  created_at: string;
}

export type DocumentStatus = 'ready' | 'processing' | 'error' | string;

/** POST /api/documents — upload response */
export interface UploadDocumentResponse {
  document_id: string;
  page_count: number;
  /** Quality metadata object */
  quality: Record<string, unknown>;
  warnings: string[];
  /** "ready" | "partial" | "error" — from worker.py */
  status: string;
}

// ── Evidence ──────────────────────────────────────────────────────────────────

/** Evidence item within a claim — from renderer.py */
export interface EvidenceItem {
  /** Sentence ID — uniquely identifies the sentence in SQLite */
  sid: string;
  /** Physical page number (1-based) */
  page: number;
  /** Section heading or empty string */
  section: string;
  /** Immutable quoted source text — never rewrite or alter this */
  quote: string;
  ocr_derived: boolean;
}

// ── Ask / Single-Pass RAG ─────────────────────────────────────────────────────

/** A page-level citation returned by the /ask endpoint */
export interface PageCitation {
  page: number;
  snippet: string;
  section: string;
}

/**
 * Response from POST /api/documents/{id}/ask (Single-Pass RAG pipeline).
 * legal_verdict is always null by design — non-verdict policy.
 */
export interface AskResponse {
  status: 'ANSWERED' | 'NOT_LOCATED' | string;
  answer: string;
  citations: PageCitation[];
  fallback: boolean;
  legal_verdict: null;
}

/**
 * @deprecated Legacy alias — prefer AskResponse for new code.
 */
export type RenderedAnswer = AskResponse;

// ── Review ────────────────────────────────────────────────────────────────────

/**
 * Review topic status.
 * NOT_ASSESSED must never be presented as absence of a clause.
 */
export type ReviewTopicStatus =
  | 'FOUND'
  | 'NOT_FOUND'
  | 'AMBIGUOUS'
  | 'POSSIBLE_CONFLICT'
  | 'NOT_ASSESSED';

export interface ReviewTopic {
  topic_id: string;
  label: string;
  status: ReviewTopicStatus | string;
  evidence: EvidenceItem[];
  /** Reason for attention-first ordering — neutral, no legal conclusions */
  attention_reason?: string;
}

export interface ReviewResponse {
  topics: ReviewTopic[];
  professional_questions: ProfessionalQuestion[];
}

export interface ProfessionalQuestion {
  question_id: string;
  text: string;
  evidence?: EvidenceItem[];
}

// ── Summarize ─────────────────────────────────────────────────────────────────

/** A single structured key point extracted by the /summarize endpoint */
export interface SummaryKeyPoint {
  label: string;
  value: string;
  page_refs: number[];
}

/** POST /api/documents/{id}/summarize — response */
export interface SummaryResponse {
  document_id: string;
  /** Full markdown-formatted summary text from Gemma or extractive fallback */
  summary_markdown: string;
  /** Structured key points with page citations */
  key_points: SummaryKeyPoint[];
  /** Physical page numbers referenced in building the summary */
  referenced_pages: number[];
  /** Model/strategy that produced the summary (e.g. "gemma4:..." or "extractive-bm25") */
  model_used: string;
  /** True when Ollama was unavailable and BM25 extractive fallback was used */
  fallback: boolean;
}

// ── Source page ───────────────────────────────────────────────────────────────

/**
 * GET /api/documents/{id}/pages/{n} returns plain text.
 */
export interface SourcePageResponse {
  physical_page: number;
  printed_label?: string;
  norm_text: string;
  is_readable?: boolean;
  lang_supported?: boolean;
  warnings?: string[];
}

// ── Deletion ──────────────────────────────────────────────────────────────────

/** DELETE /api/documents/{id} — response from delete.py */
export interface DeletionResponse {
  document_id: string;
  app_files_removed: boolean;
  fts_rows_removed: boolean;
  directory_absent: boolean;
  /** Backend-authored limitation note — never claim forensic erasure */
  note: string;
}

// ── HTTP Error envelope ───────────────────────────────────────────────────────

export interface ApiErrorEnvelope {
  detail: string | unknown;
}
