import { useCallback, useState } from 'react';
import styles from './DeleteModal.module.css';
import { Button } from '../../components/Button/Button';
import type { LexiGuardApi } from '../../api/index';
import type { DeletionResponse } from '../../api/contracts';
import { ApiError } from '../../api/errors';

interface DeleteModalProps {
  api: LexiGuardApi;
  documentId: string;
  onConfirmSuccess: (res: DeletionResponse) => void;
  onClose: () => void;
}

export function DeleteModal({
  api,
  documentId,
  onConfirmSuccess,
  onClose,
}: DeleteModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<DeletionResponse | null>(null);

  const handleDelete = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.deleteDocument(documentId);
      setReport(res);
      // Wait briefly so user sees the verified report before closing
      setTimeout(() => {
        onConfirmSuccess(res);
      }, 1500);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.userMessage);
      } else {
        setError('Failed to delete document. Please try again.');
      }
      setLoading(false);
    }
  }, [api, documentId, onConfirmSuccess]);

  return (
    <div className={styles.overlay} role="dialog" aria-modal="true" aria-labelledby="delete-title">
      <div className={styles.modal}>
        <div className={styles.title} id="delete-title">
          <span>Delete Agreement</span>
        </div>

        {!report ? (
          <>
            <p className={styles.desc}>
              Are you sure you want to delete this agreement from local application storage?
              All parsed text, indexed search entries, and question history for this document
              will be permanently cleared from this application.
            </p>

            <div className={styles.docBadge}>
              Document ID: {documentId}
            </div>

            <div className={styles.notice}>
              <strong>Notice:</strong> This removes application-controlled files and search indexes.
              It does not guarantee forensic erasure from solid-state storage (SSD wear-levelling),
              OS swap, or system backups.
            </div>

            {error && (
              <div className="error-banner" role="alert">
                <span aria-hidden="true">⚠</span>
                <span>{error}</span>
              </div>
            )}

            <div className={styles.actions}>
              <Button variant="ghost" onClick={onClose} disabled={loading}>
                Cancel
              </Button>
              <Button
                variant="danger"
                onClick={handleDelete}
                loading={loading}
                disabled={loading}
              >
                {loading ? 'Deleting…' : 'Yes, delete document'}
              </Button>
            </div>
          </>
        ) : (
          <>
            <div className="info-banner" role="status">
              <span aria-hidden="true">✓</span>
              <span>Document successfully removed from application control.</span>
            </div>

            <div className={styles.successReport}>
              <div className={styles.statusRow}>
                <span>App-controlled files removed:</span>
                <strong>{report.app_files_removed ? 'Yes' : 'No'}</strong>
              </div>
              <div className={styles.statusRow}>
                <span>FTS search rows removed:</span>
                <strong>{report.fts_rows_removed ? 'Yes' : 'No'}</strong>
              </div>
              <div className={styles.statusRow}>
                <span>Directory absent:</span>
                <strong>{report.directory_absent ? 'Yes' : 'No'}</strong>
              </div>
              {report.note && (
                <div style={{ marginTop: 'var(--space-2)', fontStyle: 'italic', color: 'var(--color-text-muted)' }}>
                  {report.note}
                </div>
              )}
            </div>

            <p className="text-xs text-muted" style={{ textAlign: 'center' }}>
              Clearing local workspace…
            </p>
          </>
        )}
      </div>
    </div>
  );
}
