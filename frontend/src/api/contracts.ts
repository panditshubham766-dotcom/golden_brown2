/**
 * LexiGuard API wire contracts — derived from backend source analysis.
 *
 * PROVISIONAL SHAPES are marked with @provisional comments where the backend
 * source does not fully establish every field. These must be confirmed against
 * the backend's OpenAPI schema before live integration.
 *
 * IMPORTANT: Do not add fields here that are not confirmed in the backend source.
 * Speculative fields must stay in this file with @provisional annotations.
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
  /** Quality metadata object (exact shape @provisional — backend returns dict[str, object]) */
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

// ── Ask / RenderedAnswer ──────────────────────────────────────────────────────

/**
 * Overall answer status — from runtime.py and router.py.
 * These are distinct from ReviewTopicStatus — do not conflate.
 */
export type AskStatus =
  | 'ANSWERED'
  | 'LIMITED'
  | 'NOT_LOCATED'
  | 'AMBIGUOUS'
  | 'CONFLICTING'
  | 'INSUFFICIENT_EVIDENCE'
  | 'LEGAL_LIMIT'
  | 'OUT_OF_SCOPE'
  | 'ERROR_LOCAL_MODEL_UNAVAILABLE'
  | 'ERROR_PROCESSING';

/**
 * Rendered claim classification — from renderer.py.
 * Distinct from the internal point kind enum.
 */
export type ClaimClassification =
  | 'DIRECT'
  | 'SUPPORTED'
  | 'INTERPRETIVE'
  | 'AMBIGUOUS'
  | 'CONFLICTING'
  | 'GENERAL_EXPLANATION'
  | 'NOT_LOCATED'
  | 'INSUFFICIENT_EVIDENCE'
  | 'OUT_OF_SCOPE';

/** A single claim with evidence — from ClaimItem in renderer.py */
export interface ClaimItem {
  claim_id: string;
  text: string;
  classification: ClaimClassification | string;
  evidence: EvidenceItem[];
}

/** Generic list item for interpretations, concerns, ambiguities, conflicts, general_explanations */
export interface ListItem {
  item_id: string;
  text: string;
  evidence?: EvidenceItem[];
}

/** Missing information item — @provisional (backend returns List[Dict[str, Any]]) */
export interface MissingInformationItem {
  /** UNREADABLE_CONTENT | REFERENCED_MATERIAL_NOT_PROVIDED | TOPIC_NOT_LOCATED | CONTEXT_REQUIRED */
  code?: string;
  message?: string;
  [key: string]: unknown;
}

/**
 * Server-generated rendered answer — from renderer.py RenderedAnswer.
 * legal_verdict is always null by design.
 */
export interface RenderedAnswer {
  status: AskStatus | string;
  answer: string;
  claims: ClaimItem[];
  interpretations: ListItem[];
  concerns: ListItem[];
  ambiguities: ListItem[];
  conflicts: ListItem[];
  general_explanations: ListItem[];
  missing_information: MissingInformationItem[];
  extraction_warnings: string[];
  external_law_required: boolean;
  jurisdiction_flags: string[];
  recommend_professional_review: boolean;
  /** Always null — never display as a verdict */
  legal_verdict: null;
}

// ── Review ────────────────────────────────────────────────────────────────────

/**
 * Review topic status — distinct from AskStatus.
 * Present NOT_FOUND as "Not located" in the UI.
 * NOT_ASSESSED must never be presented as absence.
 * @provisional — POST /api/documents/{id}/review not yet confirmed in backend source
 */
export type ReviewTopicStatus =
  | 'FOUND'
  | 'NOT_FOUND'
  | 'AMBIGUOUS'
  | 'POSSIBLE_CONFLICT'
  | 'NOT_ASSESSED';

/** @provisional — full review schema not yet in backend source */
export interface ReviewTopic {
  topic_id: string;
  label: string;
  status: ReviewTopicStatus | string;
  evidence: EvidenceItem[];
  /** Reason for attention-first ordering — neutral, no legal conclusions */
  attention_reason?: string;
}

/** @provisional */
export interface ReviewResponse {
  topics: ReviewTopic[];
  professional_questions: ProfessionalQuestion[];
}

/** @provisional */
export interface ProfessionalQuestion {
  question_id: string;
  text: string;
  evidence?: EvidenceItem[];
}

// ── Source page ───────────────────────────────────────────────────────────────

/**
 * GET /api/documents/{id}/pages/{n} returns plain text.
 * This type wraps parsed metadata — confirm printed_label field with backend.
 * @provisional for fields beyond norm_text
 */
export interface SourcePageResponse {
  /** Physical page number (1-based) */
  physical_page: number;
  /**
   * Human-readable printed label (e.g. "Page 3" or "i" for roman numerals).
   * @provisional — backend currently returns only norm_text as plain text.
   */
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

/** FastAPI's default HTTPException detail — @provisional (not fully specified) */
export interface ApiErrorEnvelope {
  detail: string | unknown;
}
