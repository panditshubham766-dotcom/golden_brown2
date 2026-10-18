import { useCallback, useEffect, useState } from 'react';
import styles from './ReviewView.module.css';
import { Button } from '../../components/Button/Button';
import { StatusLabel } from '../../components/StatusLabel/StatusLabel';
import { SourceCitation } from '../../components/SourceCitation/SourceCitation';
import type { LexiGuardApi } from '../../api/index';
import type { DocumentCard, ReviewResponse, ReviewTopic } from '../../api/contracts';
import { ApiError } from '../../api/errors';

interface ReviewViewProps {
  api: LexiGuardApi;
  document: DocumentCard;
  currentReview: ReviewResponse | null;
  onReviewReceived: (review: ReviewResponse) => void;
  onOpenSourceView: (page: number, quote?: string, sid?: string) => void;
}

// Order topics by attention-first priority
function sortTopicsByAttention(topics: ReviewTopic[]): ReviewTopic[] {
  return [...topics].sort((a, b) => {
    // 1. Conflicts first
    const aConflict = a.status === 'POSSIBLE_CONFLICT';
    const bConflict = b.status === 'POSSIBLE_CONFLICT';
    if (aConflict !== bConflict) return aConflict ? -1 : 1;

    // 2. Ambiguity second
    const aAmb = a.status === 'AMBIGUOUS';
    const bAmb = b.status === 'AMBIGUOUS';
    if (aAmb !== bAmb) return aAmb ? -1 : 1;

    // 3. Has attention reason
    const aAttn = Boolean(a.attention_reason);
    const bAttn = Boolean(b.attention_reason);
    if (aAttn !== bAttn) return aAttn ? -1 : 1;

    // 4. FOUND
    const aFound = a.status === 'FOUND';
    const bFound = b.status === 'FOUND';
    if (aFound !== bFound) return aFound ? -1 : 1;

    // 5. NOT_FOUND before NOT_ASSESSED
    const aNotFound = a.status === 'NOT_FOUND';
    const bNotFound = b.status === 'NOT_FOUND';
    if (aNotFound !== bNotFound) return aNotFound ? -1 : 1;

    return 0;
  });
}

export function ReviewView({
  api,
  document,
  currentReview,
  onReviewReceived,
  onOpenSourceView,
}: ReviewViewProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadReview = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getReview(document.document_id);
      onReviewReceived(data);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.userMessage);
      } else {
        setError('Could not load risk review data.');
      }
    } finally {
      setLoading(false);
    }
  }, [api, document.document_id, onReviewReceived]);

  useEffect(() => {
    if (!currentReview) {
      void loadReview();
    }
  }, [loadReview, currentReview]);

  const sortedTopics = currentReview?.topics
    ? sortTopicsByAttention(currentReview.topics)
    : [];

  return (
    <div className={styles.container}>
      <div className={styles.headerCard}>
        <h1 className={styles.title}>Agreement Risk &amp; Attention Review</h1>
        <p className={styles.subtitle}>
          This dashboard reviews clauses in attention-first order: potential conflicts, ambiguities,
          and obligations requiring caution are listed before standard terms.
          Evidence citations link directly to physical document pages.
        </p>

        {document.warnings && document.warnings.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            {document.warnings.map((w, idx) => (
              <div key={idx} className="warning-banner" role="status">
                <span aria-hidden="true">⚠</span>
                <span>{w}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {error && (
        <div className="error-banner" role="alert">
          <span aria-hidden="true">⚠</span>
          <span>{error}</span>
          <Button variant="ghost" size="sm" onClick={loadReview}>
            Retry
          </Button>
        </div>
      )}

      {loading && !currentReview ? (
        <div className={styles.loadingSpinner} aria-label="Loading review analysis" role="status" />
      ) : (
        <>
          {/* Attention-first Review Topics */}
          <div className={styles.section}>
            <div className={styles.sectionTitle}>
              <span>1. Rental Review Topics (Attention-First Order)</span>
            </div>

            <ul className={styles.topicList} role="list">
              {sortedTopics.map((topic) => {
                const isConflict = topic.status === 'POSSIBLE_CONFLICT';
                const hasAttention = Boolean(topic.attention_reason);

                return (
                  <li
                    key={topic.topic_id}
                    className={`${styles.topicCard} ${isConflict ? styles.conflict : hasAttention ? styles.attention : ''}`}
                  >
                    <div className={styles.topicTop}>
                      <div>
                        <span className={styles.topicLabel}>{topic.label}</span>
                        {topic.attention_reason && (
                          <div className={styles.attentionReason}>
                            ⚡ {topic.attention_reason}
                          </div>
                        )}
                      </div>
                      <StatusLabel status={topic.status} />
                    </div>

                    {topic.evidence && topic.evidence.length > 0 && (
                      <div className={styles.quotesContainer}>
                        {topic.evidence.map((ev, i) => (
                          <div key={i}>
                            {i > 0 && isConflict && (
                              <div className={styles.conflictVsBadge}>
                                ↕ Conflicting with clause on Page {ev.page}:
                              </div>
                            )}
                            <p className={styles.evidenceQuote}>
                              &ldquo;{ev.quote}&rdquo;
                            </p>
                          </div>
                        ))}
                      </div>
                    )}

                    {topic.evidence && topic.evidence.length > 0 && (
                      <div className={styles.citationsRow}>
                        {topic.evidence.map((ev, i) => (
                          <SourceCitation
                            key={i}
                            evidence={ev}
                            onClick={() => onOpenSourceView(ev.page, ev.quote, ev.sid)}
                          />
                        ))}
                      </div>
                    )}

                    {topic.status === 'NOT_FOUND' && (
                      <p className="text-xs text-muted" style={{ fontStyle: 'italic' }}>
                        No provision matching this topic was located in the readable text.
                      </p>
                    )}

                    {topic.status === 'NOT_ASSESSED' && (
                      <p className="text-xs text-muted" style={{ fontStyle: 'italic' }}>
                        This topic was not assessed during triage.
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>

          {/* Professional Questions */}
          {currentReview?.professional_questions && currentReview.professional_questions.length > 0 && (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>
                <span>2. Questions to Bring to a Legal Professional</span>
              </div>
              <p className="text-xs text-secondary">
                Neutral, evidence-backed questions you can bring to an advocate or lawyer to clarify
                ambiguities or conflicts in your agreement before signing.
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                {currentReview.professional_questions.map((pq) => (
                  <div key={pq.question_id} className={styles.pqCard}>
                    <p className={styles.pqQuestion}>{pq.text}</p>
                    {pq.evidence && pq.evidence.length > 0 && (
                      <div className={styles.citationsRow}>
                        {pq.evidence.map((ev, i) => (
                          <SourceCitation
                            key={i}
                            evidence={ev}
                            onClick={() => onOpenSourceView(ev.page, ev.quote, ev.sid)}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      <div style={{ textAlign: 'center', marginTop: 'var(--space-4)' }}>
        <p className="legal-caveat">
          LexiGuard does not evaluate agreement legality or judge validity. The topics and questions
          above reflect factual pattern matches and neutral attention indicators.
        </p>
      </div>
    </div>
  );
}
