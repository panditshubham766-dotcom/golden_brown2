/**
 * RenderedAnswerView — thin adapter over the new AskView answer card.
 *
 * @deprecated This component is kept for backward compatibility during migration.
 * New code should use AskView's inline answer card directly.
 * The underlying AskResponse type (aliased as RenderedAnswer) now uses
 * citations[] instead of claims[]/interpretations[].
 */
import styles from './RenderedAnswerView.module.css';
import type { AskResponse } from '../../api/contracts';

/** @deprecated Use AskResponse directly */
export type RenderedAnswer = AskResponse;

interface RenderedAnswerViewProps {
  answer: AskResponse;
  onOpenSourceView: (page: number, quote?: string, sid?: string) => void;
}

export function RenderedAnswerView({ answer, onOpenSourceView }: RenderedAnswerViewProps) {
  const isAnswered = answer.status === 'ANSWERED';

  return (
    <div className={styles.container}>
      {/* Status */}
      <div className={styles.statusRow}>
        <span className={`${styles.statusBadge} ${isAnswered ? styles.answered : styles.notLocated}`}>
          {isAnswered ? '✓ Answered' : '○ Not Located'}
        </span>
        {answer.fallback && (
          <span className={styles.fallbackNote}>⚡ Extractive fallback</span>
        )}
      </div>

      {/* Answer text */}
      <div className={styles.answerText}>{answer.answer}</div>

      {/* Citations */}
      {answer.citations && answer.citations.length > 0 && (
        <div className={styles.citations}>
          <span className={styles.citationsLabel}>Source pages:</span>
          <div className={styles.citationList}>
            {answer.citations.map((c, i) => (
              <button
                key={i}
                type="button"
                className={styles.citationBadge}
                onClick={() => onOpenSourceView(c.page, c.snippet)}
              >
                📄 Page {c.page}
                {c.section ? ` · ${c.section}` : ''}
              </button>
            ))}
          </div>
        </div>
      )}

      <p className={styles.caveat}>
        LexiGuard extracts factual clauses and does not provide legal advice.
      </p>
    </div>
  );
}
