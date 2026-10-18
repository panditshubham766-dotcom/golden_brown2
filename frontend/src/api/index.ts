/**
 * LexiGuard API interface.
 * Both the production HTTP client and the mock implementation must implement this.
 * Components interact only with this interface — never with fetch() directly.
 */

import type {
  SessionTokenResponse,
  HealthResponse,
  DocumentCard,
  UploadDocumentResponse,
  RenderedAnswer,
  ReviewResponse,
  SourcePageResponse,
  DeletionResponse,
} from './contracts';

export interface LexiGuardApi {
  /** POST /api/session — bootstrap exception; no bearer token */
  exchangeLaunchCode(code: string): Promise<SessionTokenResponse>;

  /** GET /api/health — requires bearer token */
  getHealth(): Promise<HealthResponse>;

  /** GET /api/documents — requires bearer token */
  listDocuments(): Promise<DocumentCard[]>;

  /**
   * POST /api/documents — multipart upload; requires bearer token.
   * Calls onProgress with a boolean when upload/processing state changes.
   */
  uploadDocument(file: File): Promise<UploadDocumentResponse>;

  /**
   * POST /api/documents/{id}/ask — requires bearer token.
   * question max length: 500 characters (also enforced by backend).
   */
  askDocument(documentId: string, question: string): Promise<RenderedAnswer>;

  /**
   * POST /api/documents/{id}/review — requires bearer token.
   * @provisional — endpoint not yet confirmed in backend source
   */
  getReview(documentId: string): Promise<ReviewResponse>;

  /**
   * GET /api/documents/{id}/pages/{n} — requires bearer token.
   * Returns plain text; we wrap it in SourcePageResponse.
   */
  getPage(documentId: string, physicalPage: number): Promise<SourcePageResponse>;

  /**
   * GET /api/documents/{id}/pages/{n}/image — requires bearer token.
   * @provisional — not yet in backend source; returns Blob if available.
   */
  getPageImage(documentId: string, physicalPage: number): Promise<Blob>;

  /** DELETE /api/documents/{id} — requires bearer token */
  deleteDocument(documentId: string): Promise<DeletionResponse>;
}
