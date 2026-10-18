/**
 * Session state — memory-only.
 *
 * The bearer token lives here (in React context) only.
 * No localStorage, sessionStorage, IndexedDB, or cookie access.
 * On page reload, all state is intentionally lost.
 */

import React, { createContext, useCallback, useContext, useRef, useState } from 'react';

/** Explicit session states. */
export type SessionState =
  | 'bootstrapping'           // reading fragment and exchanging code
  | 'ready'                   // valid in-memory session
  | 'missing-launch-code'     // no #k= fragment present
  | 'session-expired'         // code rejected / already used / expired
  | 'backend-unavailable'     // server not reachable
  | 'session-invalidated';    // later 401 from a protected call

interface SessionContextValue {
  sessionState: SessionState;
  setSessionState: (state: SessionState) => void;
  /** Token is held in a ref so it does not re-render on read, only on change */
  getToken: () => string | null;
  setToken: (token: string) => void;
  clearSession: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [sessionState, setSessionState] = useState<SessionState>('bootstrapping');
  // Store token in ref — not in state — to avoid accidental renders exposing it
  const tokenRef = useRef<string | null>(null);

  const getToken = useCallback(() => tokenRef.current, []);

  const setToken = useCallback((token: string) => {
    tokenRef.current = token;
  }, []);

  const clearSession = useCallback(() => {
    tokenRef.current = null;
    setSessionState('session-invalidated');
  }, []);

  return (
    <SessionContext.Provider value={{ sessionState, setSessionState, getToken, setToken, clearSession }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession must be used within SessionProvider');
  return ctx;
}
