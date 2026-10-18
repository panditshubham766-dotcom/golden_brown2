import { useCallback, useEffect, useState } from 'react';
import styles from './AskView.module.css';
import { Button } from '../../components/Button/Button';
import { RenderedAnswerView } from './RenderedAnswerView';
import type { LexiGuardApi } from '../../api/index';
import type { DocumentCard, RenderedAnswer } from '../../api/contracts';
import { ApiError } from '../../api/errors';

interface AskViewProps {
  api: LexiGuardApi;
  document: DocumentCard;
  currentAnswer: RenderedAnswer | null;
  initialQuestion?: string;
  onAnswerReceived: (answer: RenderedAnswer) => void;
  onOpenSourceView: (page: number, quote?: string, sid?: string) => void;
}

const SUGGESTED_QUESTIONS = [
  "Highlight the parts related to 'Parties'",
  'What is the monthly licence fee and payment obligations?',
  "Highlight the parts related to 'Notice Period to Terminate'",
  'What is the security deposit amount and refund condition?',
  "Highlight the parts related to 'Governing Law'",
  'Is this clause legally valid and enforceable in court?',
];

export function AskView({
  api,
  document,
  currentAnswer,
  initialQuestion,
  onAnswerReceived,
  onOpenSourceView,
}: AskViewProps) {
  const [question, setQuestion] = useState(initialQuestion || '');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initialQuestion) {
      setQuestion(initialQuestion);
    }
  }, [initialQuestion]);

  const charCount = question.length;
  const isOverLimit = charCount > 500;
  const isNearLimit = charCount >= 450 && !isOverLimit;

  const handleSubmit = useCallback(async () => {
    const trimmed = question.trim();
    if (!trimmed || isOverLimit || loading) return;

    setLoading(true);
    setError(null);
    try {
      const res = await api.askDocument(document.document_id, trimmed);
      onAnswerReceived(res);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.userMessage);
      } else {
        setError('Failed to process your question. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  }, [question, isOverLimit, loading, api, document.document_id, onAnswerReceived]);

  const handleChipClick = (q: string) => {
    setQuestion(q);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      void handleSubmit();
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.composerCard}>
        <div className={styles.composerHeader}>
          <h2 className={styles.composerTitle}>Ask about this agreement</h2>
          <p className={styles.composerDesc}>
            Ask questions about the provisions in your agreement. Answers cite exact source clauses and
            pages. LexiGuard does not provide legal advice or predict dispute outcomes.
          </p>
        </div>

        <div className={styles.inputWrapper}>
          <textarea
            className={`${styles.textarea} ${isOverLimit ? styles.overLimit : ''}`}
            placeholder="e.g. What is the notice period for terminating this agreement?"
            value={question}
            onChange={e => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
            aria-label="Question about agreement"
            rows={3}
          />

          <div className={styles.charCountRow}>
            <span>Press Ctrl+Enter to submit</span>
            <span
              className={`${styles.charCount} ${isOverLimit ? styles.error : isNearLimit ? styles.warn : ''}`}
            >
              {charCount} / 500 characters
            </span>
          </div>
        </div>

        <div>
          <span className="text-xs text-muted font-medium">Suggested questions:</span>
          <div className={styles.suggestedChips}>
            {SUGGESTED_QUESTIONS.map((q, idx) => (
              <button
                key={idx}
                type="button"
                className={styles.chipBtn}
                onClick={() => handleChipClick(q)}
                disabled={loading}
              >
                {q}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="error-banner" role="alert">
            <span aria-hidden="true">⚠</span>
            <span>{error}</span>
          </div>
        )}

        <div className={styles.actions}>
          <Button
            variant="primary"
            onClick={handleSubmit}
            disabled={!question.trim() || isOverLimit || loading}
            loading={loading}
          >
            {loading ? 'Analysing document…' : 'Ask question'}
          </Button>
        </div>
      </div>

      {loading && !currentAnswer && (
        <div className={styles.loadingSpinner} aria-label="Processing question" role="status" />
      )}

      {currentAnswer && (
        <RenderedAnswerView
          answer={currentAnswer}
          onOpenSourceView={onOpenSourceView}
        />
      )}
    </div>
  );
}
