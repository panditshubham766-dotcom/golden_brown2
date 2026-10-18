import { useCallback, useEffect, useState } from 'react';
import styles from './OverviewView.module.css';
import { Button } from '../../components/Button/Button';
import { StatusLabel } from '../../components/StatusLabel/StatusLabel';
import { SourceCitation } from '../../components/SourceCitation/SourceCitation';
import type { LexiGuardApi } from '../../api/index';
import type { DocumentCard, ReviewResponse, ReviewTopic } from '../../api/contracts';
import { ApiError } from '../../api/errors';

interface OverviewViewProps {
  api: LexiGuardApi;
  document: DocumentCard;
  onNavigateToAsk: (initialQuestion?: string) => void;
  onNavigateToReview: () => void;
  onOpenSourceView: (page: number, quote?: string, sid?: string) => void;
  onRequestDelete: () => void;
}

interface CoreTopicDef {
  id: string;
  label: string;
  prompt: string;
}

const CORE_10_TOPICS: CoreTopicDef[] = [
  { id: 'parties', label: '1. Parties', prompt: "Highlight the parts related to 'Parties'" },
  { id: 'term', label: '2. Term & Commencement', prompt: "Highlight the parts related to 'Term' or duration" },
  { id: 'rent', label: '3. Rent & Licence Fee', prompt: "What is the monthly rent or licence fee and payment obligations?" },
  { id: 'deposit', label: '4. Security Deposit', prompt: "What is the security deposit and refund condition?" },
  { id: 'notice', label: '5. Notice Period', prompt: "Highlight the parts related to 'Notice Period to Terminate'" },
  { id: 'lock_in', label: '6. Lock-in Period', prompt: "Is there a lock-in period mentioned in this agreement?" },
  { id: 'penalties', label: '7. Penalties & Late Fees', prompt: "Highlight the parts related to penalties or late payment charges" },
  { id: 'restrictions', label: '8. Restrictions & Prohibitions', prompt: "Highlight the parts related to restrictions or prohibitions" },
  { id: 'maintenance', label: '9. Maintenance & Repairs', prompt: "What are the maintenance and repair obligations?" },
  { id: 'disputes', label: '10. Dispute Resolution & Jurisdiction', prompt: "Highlight the parts related to 'Governing Law' and dispute resolution" },
];

export function OverviewView({
  api,
  document,
  onNavigateToAsk,
  onNavigateToReview,
  onOpenSourceView,
  onRequestDelete,
}: OverviewViewProps) {
  const [review, setReview] = useState<ReviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchOverview = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getReview(document.document_id);
      setReview(data);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.userMessage);
      } else {
        setError('Could not load document analysis overview.');
      }
    } finally {
      setLoading(false);
    }
  }, [api, document.document_id]);

  useEffect(() => {
    void fetchOverview();
  }, [fetchOverview]);

  // Topic map lookup
  const topicMap = new Map<string, ReviewTopic>();
  if (review?.topics) {
    for (const t of review.topics) {
      topicMap.set(t.topic_id, t);
    }
  }

  return (
    <div className={styles.container}>
      <div className={styles.headerCard}>
        <div className={styles.headerTop}>
          <div className={styles.docTitleArea}>
            <div className={styles.docTitle}>
              <span>Document Overview</span>
              <StatusLabel status={document.status} />
            </div>
            <span className={styles.docSub}>ID: {document.document_id}</span>
          </div>

          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            <Button variant="primary" onClick={() => onNavigateToAsk()}>
              Ask questions
            </Button>
            <Button variant="secondary" onClick={onNavigateToReview}>
              Review risks
            </Button>
            <Button variant="danger" size="md" onClick={onRequestDelete}>
              Delete document
            </Button>
          </div>
        </div>

        <div className={styles.headerMeta}>
          <div className={styles.metaBadge}>
            <span aria-hidden="true">📄</span>
            <span>{document.page_count} {document.page_count === 1 ? 'page' : 'pages'}</span>
          </div>
          <div className={styles.metaBadge}>
            <span aria-hidden="true">⏱</span>
            <span>Uploaded: {new Date(document.created_at).toLocaleString()}</span>
          </div>
          <div className={styles.metaBadge}>
            <span aria-hidden="true">🔒</span>
            <span>Local processing only</span>
          </div>
        </div>

        {document.warnings && document.warnings.length > 0 && (
          <div className={styles.bannerList}>
            {document.warnings.map((w, idx) => (
              <div key={idx} className="warning-banner" role="status">
                <span aria-hidden="true">⚠</span>
                <span>{w}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className={styles.sectionHeader}>
        <div>
          <h2 className={styles.sectionTitle}>Core 10 Document Map</h2>
          <p className={styles.sectionDesc}>
            Evidence-gated mapping of key rental topics. Note: A topic marked &quot;Not located&quot;
            means the wording was not found in the readable text — not that it does not exist under law.
          </p>
        </div>
      </div>

      {error && (
        <div className="error-banner" role="alert">
          <span aria-hidden="true">⚠</span>
          <span>{error}</span>
          <Button variant="ghost" size="sm" onClick={fetchOverview}>
            Retry
          </Button>
        </div>
      )}

      {loading && !review ? (
        <div style={{ textAlign: 'center', padding: 'var(--space-8)' }}>
          <div className={styles.topicQuote} style={{ border: 'none', background: 'transparent' }}>
            Analysing document provisions against Core 10 rental topics…
          </div>
        </div>
      ) : (
        <div className={styles.coreGrid}>
          {CORE_10_TOPICS.map((topicDef) => {
            const topic = topicMap.get(topicDef.id);
            const status = topic ? topic.status : 'NOT_ASSESSED';
            const evidence = topic?.evidence?.[0];

            return (
              <div key={topicDef.id} className={styles.topicCard}>
                <div className={styles.topicTop}>
                  <span className={styles.topicLabel}>{topicDef.label}</span>
                  <StatusLabel status={status} />
                </div>

                {status === 'FOUND' && evidence ? (
                  <>
                    <p className={styles.topicQuote}>&ldquo;{evidence.quote}&rdquo;</p>
                    <div className={styles.topicActions}>
                      <SourceCitation
                        evidence={evidence}
                        onClick={() => onOpenSourceView(evidence.page, evidence.quote, evidence.sid)}
                      />
                    </div>
                  </>
                ) : status === 'AMBIGUOUS' && evidence ? (
                  <>
                    <p className={styles.topicQuote}>&ldquo;{evidence.quote}&rdquo;</p>
                    {topic?.attention_reason && (
                      <p className="text-xs text-secondary">{topic.attention_reason}</p>
                    )}
                    <div className={styles.topicActions}>
                      <SourceCitation
                        evidence={evidence}
                        onClick={() => onOpenSourceView(evidence.page, evidence.quote, evidence.sid)}
                      />
                    </div>
                  </>
                ) : status === 'POSSIBLE_CONFLICT' && evidence ? (
                  <>
                    <p className={styles.topicQuote}>&ldquo;{evidence.quote}&rdquo;</p>
                    {topic?.attention_reason && (
                      <p className="text-xs text-secondary">{topic.attention_reason}</p>
                    )}
                    <div className={styles.topicActions}>
                      <SourceCitation
                        evidence={evidence}
                        onClick={() => onOpenSourceView(evidence.page, evidence.quote, evidence.sid)}
                      />
                    </div>
                  </>
                ) : status === 'NOT_FOUND' ? (
                  <>
                    <p className={styles.notLocatedText}>
                      Not located in initial scan.
                    </p>
                    <div className={styles.topicActions}>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onNavigateToAsk(topicDef.prompt)}
                      >
                        Ask Gemma →
                      </Button>
                    </div>
                  </>
                ) : (
                  <>
                    <p className={styles.notLocatedText}>
                      Awaiting query.
                    </p>
                    <div className={styles.topicActions}>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onNavigateToAsk(topicDef.prompt)}
                      >
                        Ask Gemma →
                      </Button>
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className={styles.legalNotice}>
        <p className="legal-caveat">
          LexiGuard is an automated document triage tool and does not provide legal advice, enforceability assessments,
          or judicial predictions. Always verify important terms with a qualified legal professional.
        </p>
      </div>
    </div>
  );
}
