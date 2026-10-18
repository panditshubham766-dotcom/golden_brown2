/**
 * Session bootstrap — reads the one-time launch code from the URL fragment
 * and exchanges it for a bearer token via POST /api/session.
 *
 * Security rules:
 * - Fragment is read once on startup only.
 * - Fragment is immediately removed from the URL (history.replaceState).
 * - The one-time code is NOT logged.
 * - The returned token is NOT logged.
 * - Token is held in memory only; callers store it via setToken().
 */

export type BootstrapResult =
  | { kind: 'ok'; token: string }
  | { kind: 'missing-code' }
  | { kind: 'invalid-code'; userMessage: string }
  | { kind: 'network-error'; userMessage: string };

/**
 * Read the one-time launch code from the URL fragment and immediately remove
 * the fragment from the browser URL (so it cannot be seen in the address bar
 * or history after this point).
 *
 * Returns the code, or null if no #k= fragment is present.
 */
export function extractAndRemoveLaunchCode(): string | null {
  const hash = window.location.hash;
  if (!hash || !hash.startsWith('#k=')) {
    return null;
  }
  const code = hash.slice(3); // remove '#k='

  // Immediately clear the fragment from the URL — do not add a history entry
  history.replaceState(null, '', window.location.pathname + window.location.search);

  return code.trim() || null;
}

/**
 * Exchange the one-time code for a bearer token.
 * Uses the production API endpoint directly (not through the typed client,
 * since we don't have a token yet for the bootstrap call).
 */
export async function exchangeCodeForToken(code: string): Promise<BootstrapResult> {
  try {
    const response = await fetch('/api/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
      cache: 'no-store',
    });

    if (response.status === 401) {
      return {
        kind: 'invalid-code',
        userMessage: 'The launch code has expired or was already used. Please close this tab and reopen the launch URL.',
      };
    }

    if (!response.ok) {
      return {
        kind: 'network-error',
        userMessage: `Session setup failed (${response.status}). Please try reopening the launch URL.`,
      };
    }

    let body: { token?: string };
    try {
      body = await response.json() as { token?: string };
    } catch {
      return { kind: 'network-error', userMessage: 'Unreadable session response.' };
    }

    if (typeof body.token !== 'string' || !body.token) {
      return { kind: 'network-error', userMessage: 'Session response missing token field.' };
    }

    return { kind: 'ok', token: body.token };
  } catch {
    return {
      kind: 'network-error',
      userMessage: 'Could not reach the local server. Is LexiGuard running? Try reopening the launch URL.',
    };
  }
}
