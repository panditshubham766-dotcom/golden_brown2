import { useCallback, useEffect, useState } from 'react';
import styles from './DocumentListView.module.css';
import { Button } from '../../components/Button/Button';
import { StatusLabel } from '../../components/StatusLabel/StatusLabel';
import type { LexiGuardApi } from '../../api/index';
import type { DocumentCard } from '../../api/contracts';
import { ApiError } from '../../api/errors';

interface DocumentListViewProps {
  api: LexiGuardApi;
  documents: DocumentCard[];
  activeDocument: DocumentCard | null;
  onSelectDocument: (doc: DocumentCard) => void;
  onRequestUpload: () => void;
  onRequestDelete: (doc: DocumentCard) => void;
  onRefreshList: () => void;
}

export function DocumentListView({
  api,
  documents,
  activeDocument,
  onSelectDocument,
  onRequestUpload,
  onRequestDelete,
  onRefreshList,
}: DocumentListViewProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDocuments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await api.listDocuments();
      onRefreshList();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.userMessage);
      } else {
        setError('Failed to load documents.');
      }
    } finally {
      setLoading(false);
    }
  }, [api, onRefreshList]);

  useEffect(() => {
    // Only load initially if documents array is empty
    if (documents.length === 0) {
      void loadDocuments();
    }
  }, [loadDocuments, documents.length]);

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Your Agreements</h1>
          <p className={styles.subtitle}>
            Documents are stored locally in application memory and verified database records.
          </p>
        </div>
        <Button variant="primary" onClick={onRequestUpload}>
          + Upload agreement
        </Button>
      </div>

      {error && (
        <div className="error-banner" role="alert">
          <span aria-hidden="true">⚠</span>
          <span>{error}</span>
          <Button variant="ghost" size="sm" onClick={loadDocuments}>
            Retry
          </Button>
        </div>
      )}

      {loading && documents.length === 0 ? (
        <div className={styles.loadingSpinner} aria-label="Loading agreements" role="status" />
      ) : documents.length === 0 ? (
        <div className={styles.emptyState}>
          <div className={styles.emptyIcon} aria-hidden="true">📄</div>
          <p className={styles.emptyText}>No agreements uploaded yet</p>
          <p className={styles.emptySubtext}>
            Upload a PDF or TXT rental or leave-and-licence agreement to inspect terms,
            review risk areas, and ask questions with source citations.
          </p>
          <Button variant="primary" onClick={onRequestUpload}>
            Upload your first agreement
          </Button>
        </div>
      ) : (
        <ul className={styles.docList} role="list" aria-label="Uploaded documents">
          {documents.map((doc) => {
            const isActive = activeDocument?.document_id === doc.document_id;
            return (
              <li
                key={doc.document_id}
                className={`${styles.docCard} ${isActive ? styles.active : ''}`}
              >
                <div className={styles.cardTop}>
                  <div className={styles.docMeta}>
                    <span className={styles.docId} title={doc.document_id}>
                      Document: {doc.document_id.slice(0, 12)}…
                    </span>
                    <div className={styles.docDetails}>
                      <span>{doc.page_count} {doc.page_count === 1 ? 'page' : 'pages'}</span>
                      <span>·</span>
                      <span>{new Date(doc.created_at).toLocaleDateString()}</span>
                    </div>
                  </div>

                  <div className={styles.cardActions}>
                    <StatusLabel status={doc.status} />
                    <Button
                      variant={isActive ? 'secondary' : 'primary'}
                      size="sm"
                      onClick={() => onSelectDocument(doc)}
                    >
                      {isActive ? 'View workspace' : 'Open'}
                    </Button>
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => onRequestDelete(doc)}
                      aria-label={`Delete document ${doc.document_id.slice(0, 8)}`}
                    >
                      Delete
                    </Button>
                  </div>
                </div>

                {doc.warnings && doc.warnings.length > 0 && (
                  <div className={styles.warningList}>
                    {doc.warnings.map((w, i) => (
                      <div key={i} className="warning-banner">
                        <span aria-hidden="true">⚠</span>
                        <span>{w}</span>
                      </div>
                    ))}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
