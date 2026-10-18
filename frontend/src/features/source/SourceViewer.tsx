import { useCallback, useEffect, useState } from 'react';
import styles from './SourceViewer.module.css';
import { Button } from '../../components/Button/Button';
import type { LexiGuardApi } from '../../api/index';
import type { SourcePageResponse } from '../../api/contracts';
import { ApiError } from '../../api/errors';

interface SourceViewerProps {
  api: LexiGuardApi;
  documentId: string;
  totalPages: number;
  initialPhysicalPage: number;
  targetQuote?: string;
  targetSid?: string;
  onClose: () => void;
}

export function SourceViewer({
  api,
  documentId,
  totalPages,
  initialPhysicalPage,
  targetQuote,
  targetSid,
  onClose,
}: SourceViewerProps) {
  const [currentPage, setCurrentPage] = useState<number>(initialPhysicalPage || 1);
  const [pageData, setPageData] = useState<SourcePageResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPage = useCallback(async (page: number) => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getPage(documentId, page);
      setPageData(data);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.userMessage);
      } else {
        setError(`Could not load page ${page}.`);
      }
    } finally {
      setLoading(false);
    }
  }, [api, documentId]);

  useEffect(() => {
    void fetchPage(currentPage);
  }, [currentPage, fetchPage]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      } else if (e.key === 'ArrowLeft' && currentPage > 1) {
        setCurrentPage(p => p - 1);
      } else if (e.key === 'ArrowRight' && currentPage < totalPages) {
        setCurrentPage(p => p + 1);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [currentPage, totalPages, onClose]);

  // Render page text with truthful passage highlighting
  const renderPageText = () => {
    if (!pageData?.norm_text) return null;

    // Only attempt inline highlight if targetQuote is non-empty and present on this page
    if (targetQuote && pageData.norm_text.includes(targetQuote)) {
      const parts = pageData.norm_text.split(targetQuote);
      return (
        <div className={styles.pageText}>
          {parts.map((part, i) => (
            <span key={i}>
              {part}
              {i < parts.length - 1 && (
                <mark className={styles.highlightedPassage} title="Quoted evidence passage">
                  {targetQuote}
                </mark>
              )}
            </span>
          ))}
        </div>
      );
    }

    return <div className={styles.pageText}>{pageData.norm_text}</div>;
  };

  return (
    <div className={styles.overlay} role="dialog" aria-modal="true" aria-labelledby="source-title">
      <div className={styles.modal}>
        <div className={styles.header}>
          <div className={styles.headerTitle} id="source-title">
            <span>Source Evidence Viewer</span>
            <span className={styles.pageBadge}>
              Physical Page {currentPage} of {totalPages}
            </span>
            {pageData?.printed_label && pageData.printed_label !== `Page ${currentPage}` && (
              <span className={styles.pageBadge} title="Printed label from page content">
                Printed: {pageData.printed_label}
              </span>
            )}
            {targetSid && (
              <span className="text-xs text-muted">
                SID: {targetSid}
              </span>
            )}
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close source viewer">
            ✕ Close
          </Button>
        </div>

        {targetQuote && (
          <div className={styles.quoteSection}>
            <div className={styles.quoteTitle}>Exact Evidence Quoted</div>
            <div className={styles.quoteText}>{targetQuote}</div>
          </div>
        )}

        {pageData?.warnings && pageData.warnings.length > 0 && (
          <div style={{ padding: 'var(--space-3) var(--space-6)' }}>
            {pageData.warnings.map((w, idx) => (
              <div key={idx} className="warning-banner" role="status">
                <span aria-hidden="true">⚠</span>
                <span>{w}</span>
              </div>
            ))}
          </div>
        )}

        <div className={styles.contentArea}>
          {error && (
            <div className="error-banner" role="alert">
              <span aria-hidden="true">⚠</span>
              <span>{error}</span>
              <Button variant="ghost" size="sm" onClick={() => fetchPage(currentPage)}>
                Retry
              </Button>
            </div>
          )}

          {loading ? (
            <div style={{ textAlign: 'center', padding: 'var(--space-8)' }}>
              <p className="text-sm text-muted">Loading page content…</p>
            </div>
          ) : (
            renderPageText()
          )}
        </div>

        <div className={styles.footer}>
          <div className={styles.pageControls}>
            <Button
              variant="secondary"
              size="sm"
              disabled={currentPage <= 1 || loading}
              onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
              aria-label="Previous page"
            >
              ← Previous
            </Button>
            <span className={styles.pageIndicator}>
              Page {currentPage} of {totalPages}
            </span>
            <Button
              variant="secondary"
              size="sm"
              disabled={currentPage >= totalPages || loading}
              onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
              aria-label="Next page"
            >
              Next →
            </Button>
          </div>

          <Button variant="ghost" size="sm" onClick={onClose}>
            Done
          </Button>
        </div>
      </div>
    </div>
  );
}
