/**
 * App-level state — document workspace, current document, pending answer, etc.
 *
 * All state is in-memory. No persistent storage.
 * On document delete, all state tied to that document must be cleared.
 */

import React, { createContext, useCallback, useContext, useState } from 'react';
import type { DocumentCard, RenderedAnswer, SourcePageResponse, ReviewResponse } from '../api/contracts';

export type WorkspaceView = 'overview' | 'ask' | 'review' | 'source';

interface SourceViewState {
  documentId: string;
  physicalPage: number;
  /** Highlight SID — only set if backend provides reliable location data */
  highlightSid?: string;
  /** The evidence quote to display (immutable, from backend) */
  quote?: string;
}

interface AppStateContextValue {
  /** Currently active document */
  activeDocument: DocumentCard | null;
  setActiveDocument: (doc: DocumentCard | null) => void;

  /** All locally known documents (from GET /api/documents) */
  documents: DocumentCard[];
  setDocuments: (docs: DocumentCard[]) => void;
  removeDocument: (documentId: string) => void;

  /** Current workspace view */
  workspaceView: WorkspaceView;
  setWorkspaceView: (view: WorkspaceView) => void;

  /** Last rendered answer for the active document */
  currentAnswer: RenderedAnswer | null;
  setCurrentAnswer: (answer: RenderedAnswer | null) => void;

  /** Current question text (for the ask interface) */
  currentQuestion: string;
  setCurrentQuestion: (q: string) => void;

  /** Current review data */
  currentReview: ReviewResponse | null;
  setCurrentReview: (review: ReviewResponse | null) => void;

  /** Source viewer state */
  sourceView: SourceViewState | null;
  openSourceView: (state: SourceViewState) => void;
  closeSourceView: () => void;

  /** Loaded source pages cache (in-memory only) */
  pageCache: Map<string, SourcePageResponse>;
  setPageInCache: (key: string, page: SourcePageResponse) => void;

  /** Clear all state tied to a specific document */
  clearDocumentState: (documentId: string) => void;

  /** Clear everything (session invalidated / logout) */
  clearAllState: () => void;
}

const AppStateContext = createContext<AppStateContextValue | null>(null);

export function AppStateProvider({ children }: { children: React.ReactNode }) {
  const [activeDocument, setActiveDocumentRaw] = useState<DocumentCard | null>(null);
  const [documents, setDocuments] = useState<DocumentCard[]>([]);
  const [workspaceView, setWorkspaceView] = useState<WorkspaceView>('overview');
  const [currentAnswer, setCurrentAnswer] = useState<RenderedAnswer | null>(null);
  const [currentQuestion, setCurrentQuestion] = useState('');
  const [currentReview, setCurrentReview] = useState<ReviewResponse | null>(null);
  const [sourceView, setSourceView] = useState<SourceViewState | null>(null);
  const [pageCache] = useState<Map<string, SourcePageResponse>>(() => new Map());

  const setActiveDocument = useCallback((doc: DocumentCard | null) => {
    setActiveDocumentRaw(doc);
    // Switching documents clears answer/question/review for the previous
    setCurrentAnswer(null);
    setCurrentQuestion('');
    setCurrentReview(null);
    setSourceView(null);
  }, []);

  const removeDocument = useCallback((documentId: string) => {
    setDocuments(prev => prev.filter(d => d.document_id !== documentId));
  }, []);

  const setPageInCache = useCallback((key: string, page: SourcePageResponse) => {
    pageCache.set(key, page);
  }, [pageCache]);

  const openSourceView = useCallback((state: SourceViewState) => {
    setSourceView(state);
    setWorkspaceView('source');
  }, []);

  const closeSourceView = useCallback(() => {
    setSourceView(null);
    setWorkspaceView('overview');
  }, []);

  const clearDocumentState = useCallback((documentId: string) => {
    setActiveDocumentRaw(prev => prev?.document_id === documentId ? null : prev);
    setDocuments(prev => prev.filter(d => d.document_id !== documentId));
    setCurrentAnswer(null);
    setCurrentQuestion('');
    setCurrentReview(null);
    setSourceView(null);
    // Remove cached pages for this document
    for (const key of Array.from(pageCache.keys())) {
      if (key.startsWith(`${documentId}:`)) {
        pageCache.delete(key);
      }
    }
  }, [pageCache]);

  const clearAllState = useCallback(() => {
    setActiveDocumentRaw(null);
    setDocuments([]);
    setCurrentAnswer(null);
    setCurrentQuestion('');
    setCurrentReview(null);
    setSourceView(null);
    pageCache.clear();
  }, [pageCache]);

  return (
    <AppStateContext.Provider value={{
      activeDocument,
      setActiveDocument,
      documents,
      setDocuments,
      removeDocument,
      workspaceView,
      setWorkspaceView,
      currentAnswer,
      setCurrentAnswer,
      currentQuestion,
      setCurrentQuestion,
      currentReview,
      setCurrentReview,
      sourceView,
      openSourceView,
      closeSourceView,
      pageCache,
      setPageInCache,
      clearDocumentState,
      clearAllState,
    }}>
      {children}
    </AppStateContext.Provider>
  );
}

export function useAppState(): AppStateContextValue {
  const ctx = useContext(AppStateContext);
  if (!ctx) throw new Error('useAppState must be used within AppStateProvider');
  return ctx;
}
