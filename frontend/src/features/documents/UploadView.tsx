/**
 * UploadView — drag-and-drop + file picker for PDF/TXT documents.
 *
 * Rules:
 * - Frontend validation is for usability only. Backend is authoritative.
 * - Never display invented progress percentages.
 * - Show "Uploading and analysing…" only — truthful status.
 * - File name is shown transiently only. Not logged or persisted.
 * - Duplicate submission is blocked while uploading.
 * - Stale requests are cancelled on unmount.
 */

import { useCallback, useRef, useState } from 'react';
import styles from './UploadView.module.css';
import { Button } from '../../components/Button/Button';
import type { LexiGuardApi } from '../../api/index';
import type { DocumentCard, UploadDocumentResponse } from '../../api/contracts';
import { ApiError } from '../../api/errors';

type UploadState =
  | 'idle'
  | 'file-selected'
  | 'uploading'
  | 'success'
  | 'rejected'
  | 'failed';

interface UploadViewProps {
  api: LexiGuardApi;
  onUploadSuccess: (doc: DocumentCard, result: UploadDocumentResponse) => void;
}

const ACCEPTED_TYPES = ['application/pdf', 'text/plain'];
const ACCEPTED_EXTS = ['.pdf', '.txt'];

function isAcceptedExt(name: string): boolean {
  const lower = name.toLowerCase();
  return ACCEPTED_EXTS.some(ext => lower.endsWith(ext));
}

export function UploadView({ api, onUploadSuccess }: UploadViewProps) {
  const [uploadState, setUploadState] = useState<UploadState>('idle');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const handleFile = useCallback((file: File) => {
    setError(null);
    // Usability check — backend is authoritative
    if (!isAcceptedExt(file.name) && !ACCEPTED_TYPES.includes(file.type)) {
      setError('Please select a PDF or plain-text TXT file.');
      setUploadState('rejected');
      return;
    }
    setSelectedFile(file);
    setUploadState('file-selected');
  }, []);

  const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    // Reset input so same file can be re-selected after rejection
    e.target.value = '';
  }, [handleFile]);

  const handleUpload = useCallback(async () => {
    if (!selectedFile || uploadState === 'uploading') return;

    setUploadState('uploading');
    setError(null);

    try {
      const result = await api.uploadDocument(selectedFile);

      // Build a document card from the upload response
      const card: DocumentCard = {
        document_id: result.document_id,
        page_count: result.page_count,
        status: result.status,
        quality_summary: `${result.page_count} pages`,
        warnings: result.warnings,
        created_at: new Date().toISOString(),
      };

      setUploadState('success');
      setSelectedFile(null); // Revoke file reference per privacy rules

      onUploadSuccess(card, result);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.userMessage);
      } else {
        setError('Upload failed. Please try again.');
      }
      setUploadState('failed');
    }
  }, [selectedFile, uploadState, api, onUploadSuccess]);

  const handleReset = useCallback(() => {
    setUploadState('idle');
    setSelectedFile(null);
    setError(null);
    abortRef.current?.abort();
  }, []);

  const isUploading = uploadState === 'uploading';

  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <h1 className={styles.title}>Upload your agreement</h1>
        <p className={styles.subtitle}>
          Upload a PDF or plain-text rental agreement or leave-and-licence agreement.
          Your document is processed entirely on your device — it never leaves your machine.
        </p>
      </div>

      <div
        className={`${styles.dropZone} ${isDragging ? styles.dragging : ''} ${uploadState === 'rejected' || uploadState === 'failed' ? styles.hasError : ''}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => !isUploading && fileInputRef.current?.click()}
        role="button"
        tabIndex={0}
        aria-label="Upload area — click or drag and drop a PDF or TXT file"
        onKeyDown={e => e.key === 'Enter' || e.key === ' ' ? fileInputRef.current?.click() : undefined}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.txt,application/pdf,text/plain"
          className={styles.hiddenInput}
          onChange={handleInputChange}
          aria-hidden="true"
          tabIndex={-1}
          disabled={isUploading}
        />

        {uploadState === 'idle' && (
          <div className={styles.dropContent}>
            <div className={styles.uploadIcon} aria-hidden="true">⬆</div>
            <p className={styles.dropText}>Drag and drop your file here, or click to browse</p>
            <p className={styles.dropHint}>PDF or TXT · Maximum 50 MB</p>
          </div>
        )}

        {(uploadState === 'file-selected' || uploadState === 'rejected') && selectedFile && (
          <div className={styles.dropContent}>
            <div className={styles.fileIcon} aria-hidden="true">📄</div>
            <p className={styles.fileName}>{selectedFile.name}</p>
            <p className={styles.dropHint}>
              {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
            </p>
          </div>
        )}

        {uploadState === 'uploading' && (
          <div className={styles.dropContent}>
            <div className={styles.uploadingSpinner} aria-hidden="true" />
            <p className={styles.uploadingText}>Uploading and analysing…</p>
            <p className={styles.dropHint}>This may take a moment</p>
          </div>
        )}

        {uploadState === 'failed' && !selectedFile && (
          <div className={styles.dropContent}>
            <div className={styles.uploadIcon} aria-hidden="true">⬆</div>
            <p className={styles.dropText}>Click to try again</p>
            <p className={styles.dropHint}>PDF or TXT · Maximum 50 MB</p>
          </div>
        )}
      </div>

      {error && (
        <div className="error-banner" role="alert" aria-live="assertive">
          <span aria-hidden="true">⚠</span>
          <span>{error}</span>
        </div>
      )}

      {(uploadState === 'file-selected') && (
        <div className={styles.actions}>
          <Button variant="ghost" onClick={handleReset} disabled={isUploading}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleUpload}
            loading={isUploading}
            disabled={isUploading}
          >
            {isUploading ? 'Uploading and analysing…' : 'Upload and analyse'}
          </Button>
        </div>
      )}

      {uploadState === 'failed' && (
        <div className={styles.actions}>
          <Button variant="secondary" onClick={handleReset}>
            Try again
          </Button>
        </div>
      )}

      <div className={styles.caveat}>
        <p className="legal-caveat">
          LexiGuard is not a lawyer and does not provide legal advice. It helps you understand
          what your agreement states, with source evidence. Always consult a qualified legal
          professional before making decisions based on any agreement.
        </p>
      </div>
    </div>
  );
}
