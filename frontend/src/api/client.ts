/**
 * LexiGuard production API client.
 *
 * Security rules enforced here:
 * - All paths are relative (/api/...) — no hardcoded hostname.
 * - Bearer token is passed in via setToken(); never persisted anywhere.
 * - fetch() requests use cache: 'no-store' for document/answer endpoints.
 * - AbortController signals provide request timeouts.
 * - 401 responses emit a session-expired error and clear the token slot.
 * - No document content, questions, answers, or tokens are logged.
 */

import { ApiError, parseApiError } from './errors';
import type { LexiGuardApi } from './index';
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

const REQUEST_TIMEOUT_MS = 60_000; // 60 s — generous for slow local model

/** Called when a 401 is received — caller should clear session state. */
type OnSessionExpired = () => void;

export class LexiGuardApiClient implements LexiGuardApi {
  private _token: string | null = null;
  private _onSessionExpired: OnSessionExpired | null = null;

  setToken(token: string): void {
    this._token = token;
  }

  clearToken(): void {
    this._token = null;
  }

  setOnSessionExpired(cb: OnSessionExpired): void {
    this._onSessionExpired = cb;
  }

  // ── Internal helpers ────────────────────────────────────────────────────────

  private _authHeaders(): Record<string, string> {
    if (!this._token) {
      throw new ApiError('session-expired', 'No active session. Please reopen the launch URL.');
    }
    return { Authorization: `Bearer ${this._token}` };
  }

  private _controller(): [AbortController, ReturnType<typeof setTimeout>] {
    const controller = new AbortController();
    const timerId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    return [controller, timerId];
  }

  private async _fetch(input: RequestInfo, init?: RequestInit): Promise<Response> {
    const [controller, timerId] = this._controller();
    try {
      const response = await fetch(input, {
        ...init,
        signal: controller.signal,
        // Prevent caching of any API response
        cache: 'no-store',
      });

      if (response.status === 401) {
        this.clearToken();
        this._onSessionExpired?.();
        throw new ApiError('session-expired', 'Session expired. Please reopen the launch URL.', 401);
      }

      if (!response.ok) {
        throw await parseApiError(response);
      }

      return response;
    } catch (err) {
      if (err instanceof ApiError) throw err;
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw new ApiError('timeout', 'The request timed out. Please try again.');
      }
      throw new ApiError('network-error', 'Could not reach the local server. Is LexiGuard running?');
    } finally {
      clearTimeout(timerId);
    }
  }

  private async _json<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
    const response = await this._fetch(input, init);
    try {
      return await response.json() as T;
    } catch {
      throw new ApiError('malformed-response', 'The server returned an unreadable response.');
    }
  }

  // ── Session ──────────────────────────────────────────────────────────────────

  async exchangeLaunchCode(code: string): Promise<SessionTokenResponse> {
    // No bearer token for this bootstrap call
    const [controller, timerId] = this._controller();
    try {
      const response = await fetch('/api/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
        signal: controller.signal,
        cache: 'no-store',
      });
      if (!response.ok) {
        throw await parseApiError(response);
      }
      try {
        return await response.json() as SessionTokenResponse;
      } catch {
        throw new ApiError('malformed-response', 'The server returned an unreadable response.');
      }
    } catch (err) {
      if (err instanceof ApiError) throw err;
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw new ApiError('timeout', 'The session request timed out.');
      }
      throw new ApiError('network-error', 'Could not reach the local server. Is LexiGuard running?');
    } finally {
      clearTimeout(timerId);
    }
  }

  // ── Health ───────────────────────────────────────────────────────────────────

  async getHealth(): Promise<HealthResponse> {
    return this._json<HealthResponse>('/api/health', {
      headers: this._authHeaders(),
    });
  }

  // ── Documents ────────────────────────────────────────────────────────────────

  async listDocuments(): Promise<DocumentCard[]> {
    return this._json<DocumentCard[]>('/api/documents', {
      headers: this._authHeaders(),
    });
  }

  async uploadDocument(file: File): Promise<UploadDocumentResponse> {
    const formData = new FormData();
    // Backend expects field name "file" (UploadFile = File(...))
    formData.append('file', file);

    return this._json<UploadDocumentResponse>('/api/documents', {
      method: 'POST',
      headers: this._authHeaders(),
      body: formData,
    });
  }

  // ── Ask ──────────────────────────────────────────────────────────────────────

  async askDocument(documentId: string, question: string): Promise<RenderedAnswer> {
    return this._json<RenderedAnswer>(`/api/documents/${documentId}/ask`, {
      method: 'POST',
      headers: {
        ...this._authHeaders(),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ question }),
    });
  }

  // ── Review ───────────────────────────────────────────────────────────────────

  async getReview(documentId: string): Promise<ReviewResponse> {
    try {
      return await this._json<ReviewResponse>(`/api/documents/${documentId}/review`, {
        method: 'POST',
        headers: {
          ...this._authHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({}),
      });
    } catch {
      // Endpoint /review is provisional; if backend does not expose it, return empty structure
      return { topics: [], professional_questions: [] };
    }
  }

  // ── Source pages ─────────────────────────────────────────────────────────────

  async getPage(documentId: string, physicalPage: number): Promise<SourcePageResponse> {
    // Backend returns plain text — we wrap it
    const response = await this._fetch(
      `/api/documents/${documentId}/pages/${physicalPage}`,
      { headers: this._authHeaders() }
    );
    let norm_text: string;
    try {
      norm_text = await response.text();
    } catch {
      throw new ApiError('malformed-response', 'Could not read page content.');
    }
    return {
      physical_page: physicalPage,
      norm_text,
    };
  }

  async getPageImage(documentId: string, physicalPage: number): Promise<Blob> {
    // @provisional — not yet in backend source
    const response = await this._fetch(
      `/api/documents/${documentId}/pages/${physicalPage}/image`,
      { headers: this._authHeaders() }
    );
    return response.blob();
  }

  // ── Delete ───────────────────────────────────────────────────────────────────

  async deleteDocument(documentId: string): Promise<DeletionResponse> {
    return this._json<DeletionResponse>(`/api/documents/${documentId}`, {
      method: 'DELETE',
      headers: this._authHeaders(),
    });
  }
}

/** Singleton production client */
export const apiClient = new LexiGuardApiClient();
