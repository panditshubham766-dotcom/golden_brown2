/**
 * LexiGuard API errors — central parsing and classification.
 *
 * HTTP transport errors and valid answer-level statuses (e.g. LEGAL_LIMIT) are
 * different things. A 200 OK response can contain LEGAL_LIMIT. A 401 means the
 * session has been invalidated, not that the answer is limited.
 */

export type ApiErrorKind =
  | 'session-expired'       // 401 — invalidate session, show relaunch
  | 'not-found'             // 404 — document/resource not found
  | 'too-large'             // 413 — file too large
  | 'unsupported-type'      // 415 or 422 with type error
  | 'validation-error'      // 422 — backend validation failed
  | 'server-error'          // 500 — internal server error
  | 'network-error'         // fetch failed (offline/unreachable)
  | 'timeout'               // AbortController timeout
  | 'malformed-response'    // response could not be parsed
  | 'unknown';

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly statusCode?: number;
  /** Safe user-facing message. Never includes stack traces, paths, or internal detail. */
  readonly userMessage: string;

  constructor(kind: ApiErrorKind, userMessage: string, statusCode?: number) {
    super(userMessage);
    this.name = 'ApiError';
    this.kind = kind;
    this.statusCode = statusCode;
    this.userMessage = userMessage;
  }
}

/**
 * Parse a fetch Response into an ApiError.
 * Never exposes internal server details, stack traces, or paths to the UI.
 */
export async function parseApiError(response: Response): Promise<ApiError> {
  const status = response.status;

  if (status === 401) {
    return new ApiError('session-expired', 'Session expired. Please reopen the launch URL.', 401);
  }
  if (status === 404) {
    return new ApiError('not-found', 'The requested resource was not found.', 404);
  }
  if (status === 413) {
    return new ApiError('too-large', 'The file is too large to upload. Please check the size limit.', 413);
  }
  if (status === 415) {
    return new ApiError('unsupported-type', 'This file type is not supported. Please upload a PDF or TXT file.', 415);
  }
  if (status === 422) {
    // Try to extract the backend's user-facing detail
    let detail = 'The upload was rejected. Please check the file type and size.';
    try {
      const body = await response.json() as { detail?: string | unknown };
      if (typeof body?.detail === 'string') {
        // Only use backend detail if it looks safe (no paths, no stack traces)
        const raw = body.detail;
        if (!raw.includes('/') && !raw.includes('Traceback') && raw.length < 300) {
          detail = raw;
        }
      }
    } catch {
      // ignore — use default
    }
    return new ApiError('validation-error', detail, 422);
  }
  if (status === 429) {
    return new ApiError('server-error', 'Too many requests. Please wait a moment and try again.', 429);
  }
  if (status >= 500) {
    return new ApiError('server-error', 'The server encountered an error. Please try again.', status);
  }

  return new ApiError('unknown', `Unexpected response (${status}). Please try again.`, status);
}
