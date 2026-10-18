import { useCallback, useEffect, useState } from 'react';
import styles from './App.module.css';
import { SessionProvider, useSession } from './auth/session-state';
import { AppStateProvider, useAppState } from './app/app-state';
import { extractAndRemoveLaunchCode } from './auth/session-bootstrap';
import { apiClient } from './api/client';
import type { DeletionResponse, DocumentCard, RenderedAnswer, ReviewResponse } from './api/contracts';
import { AppShell } from './components/AppShell/AppShell';
import { Button } from './components/Button/Button';
import { UploadView } from './features/documents/UploadView';
import { DocumentListView } from './features/documents/DocumentListView';
import { OverviewView } from './features/documents/OverviewView';
import { AskView } from './features/ask/AskView';
import { ReviewView } from './features/review/ReviewView';
import { SourceViewer } from './features/source/SourceViewer';
import { DeleteModal } from './features/delete/DeleteModal';

type ActiveView = 'upload' | 'documents' | 'overview' | 'ask' | 'review';

function LexiGuardMain() {
  const { sessionState, setSessionState, setToken, clearSession } = useSession();
  const {
    activeDocument,
    setActiveDocument,
    documents,
    setDocuments,
    removeDocument,
    currentAnswer,
    setCurrentAnswer,
    currentQuestion,
    setCurrentQuestion,
    currentReview,
    setCurrentReview,
    clearDocumentState,
  } = useAppState();

  const [activeView, setActiveView] = useState<ActiveView>('documents');
  const [deleteTarget, setDeleteTarget] = useState<DocumentCard | null>(null);
  const [manualCode, setManualCode] = useState('');
  const [authError, setAuthError] = useState<string | null>(null);

  // Source viewer modal state
  const [sourceViewerProps, setSourceViewerProps] = useState<{
    page: number;
    quote?: string;
    sid?: string;
  } | null>(null);

  const authenticateWithCode = useCallback((code: string) => {
    setAuthError(null);
    setSessionState('bootstrapping');
    apiClient.exchangeLaunchCode(code.trim())
      .then(res => {
        setToken(res.token);
        apiClient.setToken(res.token);
        apiClient.setOnSessionExpired(() => {
          clearSession();
        });
        setSessionState('ready');
      })
      .catch((err) => {
        setAuthError(err instanceof Error ? err.message : 'Invalid or expired launch code.');
        setSessionState('session-expired');
      });
  }, [setSessionState, setToken, clearSession]);

  // Session bootstrap: check #k= fragment on initial mount
  useEffect(() => {
    const code = extractAndRemoveLaunchCode();
    if (code) {
      authenticateWithCode(code);
    } else {
      setSessionState('missing-launch-code');
    }
  }, [authenticateWithCode, setSessionState]);

  // Fetch documents once session is ready
  const refreshDocuments = useCallback(async () => {
    try {
      const list = await apiClient.listDocuments();
      setDocuments(list);
    } catch {
      // Handled in DocumentListView
    }
  }, [setDocuments]);

  useEffect(() => {
    if (sessionState === 'ready') {
      void refreshDocuments();
    }
  }, [sessionState, refreshDocuments]);

  // Handlers
  const handleUploadSuccess = (card: DocumentCard) => {
    setDocuments([...documents, card]);
    setActiveDocument(card);
    setActiveView('overview');
  };

  const handleSelectDocument = (doc: DocumentCard) => {
    setActiveDocument(doc);
    setActiveView('overview');
  };

  const handleDeleteSuccess = (res: DeletionResponse) => {
    clearDocumentState(res.document_id);
    removeDocument(res.document_id);
    setDeleteTarget(null);
    setActiveView('documents');
    void refreshDocuments();
  };

  const handleOpenSourceView = (page: number, quote?: string, sid?: string) => {
    setSourceViewerProps({ page, quote, sid });
  };

  // Render header navigation controls
  const headerRight = (
    <div className={styles.headerNav}>
      {activeDocument ? (
        <>
          <div className={styles.docIndicator}>
            <span>Doc: {activeDocument.document_id.slice(0, 8)}…</span>
          </div>

          <button
            type="button"
            className={`${styles.navLink} ${activeView === 'overview' ? styles.active : ''}`}
            onClick={() => setActiveView('overview')}
          >
            Overview
          </button>
          <button
            type="button"
            className={`${styles.navLink} ${activeView === 'ask' ? styles.active : ''}`}
            onClick={() => setActiveView('ask')}
          >
            Ask
          </button>
          <button
            type="button"
            className={`${styles.navLink} ${activeView === 'review' ? styles.active : ''}`}
            onClick={() => setActiveView('review')}
          >
            Review
          </button>
          <button
            type="button"
            className={`${styles.navLink} ${activeView === 'documents' ? styles.active : ''}`}
            onClick={() => setActiveView('documents')}
          >
            All Agreements
          </button>
        </>
      ) : (
        <>
          <button
            type="button"
            className={`${styles.navLink} ${activeView === 'documents' ? styles.active : ''}`}
            onClick={() => setActiveView('documents')}
          >
            Agreements
          </button>
          <button
            type="button"
            className={`${styles.navLink} ${activeView === 'upload' ? styles.active : ''}`}
            onClick={() => setActiveView('upload')}
          >
            + Upload
          </button>
        </>
      )}
    </div>
  );

  return (
    <AppShell headerRight={headerRight}>
      {/* Session missing code screen */}
      {sessionState === 'missing-launch-code' && (
        <div className={styles.sessionBanner} role="alert">
          <h2>Connect to LexiGuard Backend</h2>
          <p>
            LexiGuard runs with a secure local FastAPI backend and Gemma. To begin, open the launch URL printed by your backend terminal:
          </p>
          <div className={styles.codeBox}>
            http://127.0.0.1:8000/#k=&lt;launch-code&gt;
          </div>
          <p className="text-xs text-muted">
            Or paste the one-time launch code generated by the backend terminal below:
          </p>
          <div style={{ display: 'flex', gap: 'var(--space-2)', maxWidth: '28rem', margin: 'var(--space-2) auto' }}>
            <input
              type="text"
              placeholder="Paste launch code here"
              value={manualCode}
              onChange={e => setManualCode(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && manualCode.trim() && authenticateWithCode(manualCode)}
              style={{
                flex: 1,
                padding: 'var(--space-2) var(--space-3)',
                background: 'var(--color-bg-base)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-md)',
                color: 'var(--color-text-primary)',
                fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-sm)',
              }}
            />
            <Button
              variant="primary"
              onClick={() => manualCode.trim() && authenticateWithCode(manualCode)}
              disabled={!manualCode.trim()}
            >
              Connect
            </Button>
          </div>
          {authError && (
            <div className="error-banner" style={{ marginTop: 'var(--space-2)' }}>
              <span>{authError}</span>
            </div>
          )}
        </div>
      )}

      {/* Session bootstrapping indicator */}
      {sessionState === 'bootstrapping' && (
        <div className={styles.sessionBanner} role="status">
          <h2>Connecting to local backend…</h2>
          <p>Exchanging launch code for secure in-memory session token…</p>
        </div>
      )}

      {/* Session expired / invalidated screen */}
      {(sessionState === 'session-expired' || sessionState === 'session-invalidated') && (
        <div className={styles.sessionBanner} role="alert">
          <h2>Session Expired or Disconnected</h2>
          <p>
            The session has ended, or the launch code was already used or expired.
            All document state has been cleared from memory.
          </p>
          {authError && (
            <div className="error-banner" style={{ margin: 'var(--space-2) auto', maxWidth: '28rem' }}>
              <span>{authError}</span>
            </div>
          )}
          <p className="text-xs text-muted">
            Please copy the new launch code from your backend terminal:
          </p>
          <div style={{ display: 'flex', gap: 'var(--space-2)', maxWidth: '28rem', margin: 'var(--space-2) auto' }}>
            <input
              type="text"
              placeholder="Paste new launch code"
              value={manualCode}
              onChange={e => setManualCode(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && manualCode.trim() && authenticateWithCode(manualCode)}
              style={{
                flex: 1,
                padding: 'var(--space-2) var(--space-3)',
                background: 'var(--color-bg-base)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-md)',
                color: 'var(--color-text-primary)',
                fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-sm)',
              }}
            />
            <Button
              variant="primary"
              onClick={() => manualCode.trim() && authenticateWithCode(manualCode)}
              disabled={!manualCode.trim()}
            >
              Reconnect
            </Button>
          </div>
        </div>
      )}

      {/* Active Workspaces (Only rendered when session is authenticated) */}
      {sessionState === 'ready' && (
        <>
          {activeView === 'upload' && (
            <UploadView
              api={apiClient}
              onUploadSuccess={handleUploadSuccess}
            />
          )}

          {activeView === 'documents' && (
            <DocumentListView
              api={apiClient}
              documents={documents}
              activeDocument={activeDocument}
              onSelectDocument={handleSelectDocument}
              onRequestUpload={() => setActiveView('upload')}
              onRequestDelete={(doc) => setDeleteTarget(doc)}
              onRefreshList={refreshDocuments}
            />
          )}

          {activeView === 'overview' && activeDocument && (
            <OverviewView
              api={apiClient}
              document={activeDocument}
              onNavigateToAsk={(q) => {
                if (q) setCurrentQuestion(q);
                setActiveView('ask');
              }}
              onNavigateToReview={() => setActiveView('review')}
              onOpenSourceView={handleOpenSourceView}
              onRequestDelete={() => setDeleteTarget(activeDocument)}
            />
          )}

          {activeView === 'ask' && activeDocument && (
            <AskView
              api={apiClient}
              document={activeDocument}
              currentAnswer={currentAnswer}
              initialQuestion={currentQuestion}
              onAnswerReceived={(ans: RenderedAnswer) => setCurrentAnswer(ans)}
              onOpenSourceView={handleOpenSourceView}
            />
          )}

          {activeView === 'review' && activeDocument && (
            <ReviewView
              api={apiClient}
              document={activeDocument}
              currentReview={currentReview}
              onReviewReceived={(rev: ReviewResponse) => setCurrentReview(rev)}
              onOpenSourceView={handleOpenSourceView}
            />
          )}
        </>
      )}

      {/* Source Viewer Modal */}
      {sourceViewerProps && activeDocument && (
        <SourceViewer
          api={apiClient}
          documentId={activeDocument.document_id}
          totalPages={activeDocument.page_count}
          initialPhysicalPage={sourceViewerProps.page}
          targetQuote={sourceViewerProps.quote}
          targetSid={sourceViewerProps.sid}
          onClose={() => setSourceViewerProps(null)}
        />
      )}

      {/* Delete Confirmation Modal */}
      {deleteTarget && (
        <DeleteModal
          api={apiClient}
          documentId={deleteTarget.document_id}
          onConfirmSuccess={handleDeleteSuccess}
          onClose={() => setDeleteTarget(null)}
        />
      )}
    </AppShell>
  );
}

export default function App() {
  return (
    <SessionProvider>
      <AppStateProvider>
        <LexiGuardMain />
      </AppStateProvider>
    </SessionProvider>
  );
}
