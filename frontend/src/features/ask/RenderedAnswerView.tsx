import styles from './RenderedAnswerView.module.css';
import { StatusLabel } from '../../components/StatusLabel/StatusLabel';
import { SourceCitation } from '../../components/SourceCitation/SourceCitation';
import type { RenderedAnswer, EvidenceItem } from '../../api/contracts';

interface RenderedAnswerViewProps {
  answer: RenderedAnswer;
  onOpenSourceView: (page: number, quote?: string, sid?: string) => void;
}

export function RenderedAnswerView({ answer, onOpenSourceView }: RenderedAnswerViewProps) {
  // Collect all SIDs and pages for the process ledger
  const allEvidence: EvidenceItem[] = [];
  answer.claims?.forEach(c => c.evidence?.forEach(e => allEvidence.push(e)));
  answer.conflicts?.forEach(c => c.evidence?.forEach(e => allEvidence.push(e)));
  answer.concerns?.forEach(c => c.evidence?.forEach(e => allEvidence.push(e)));
  answer.interpretations?.forEach(c => c.evidence?.forEach(e => allEvidence.push(e)));
  answer.ambiguities?.forEach(c => c.evidence?.forEach(e => allEvidence.push(e)));

  const uniqueSids = Array.from(new Set(allEvidence.map(e => e.sid)));
  const uniquePages = Array.from(new Set(allEvidence.map(e => e.page))).sort((a, b) => a - b);

  return (
    <div className={styles.answerCard} role="region" aria-label="Answer results">
      <div className={styles.answerHeader}>
        <div className={styles.answerTitle}>
          <span>Answer Analysis</span>
          <StatusLabel status={answer.status} />
        </div>
      </div>

      {answer.answer && (
        <div className={styles.answerSummary}>
          <p>{answer.answer}</p>
        </div>
      )}

      {/* Jurisdiction flags */}
      {answer.jurisdiction_flags && answer.jurisdiction_flags.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
          {answer.jurisdiction_flags.map((flag, idx) => (
            <span key={idx} className="jurisdiction-flag">
              ⚖ {flag}
            </span>
          ))}
        </div>
      )}

      {/* Recommend professional review */}
      {answer.recommend_professional_review && (
        <div className="warning-banner" role="status">
          <span aria-hidden="true">💡</span>
          <div>
            <strong>Legal Professional Review Recommended:</strong> This question involves terms that
            may have significant legal ramifications or conflicts. Consult a qualified advocate.
          </div>
        </div>
      )}

      {/* Extraction warnings */}
      {answer.extraction_warnings && answer.extraction_warnings.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          {answer.extraction_warnings.map((w, idx) => (
            <div key={idx} className="warning-banner" role="status">
              <span aria-hidden="true">⚠</span>
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}

      {/* Missing information */}
      {answer.missing_information && answer.missing_information.length > 0 && (
        <div className="info-banner" role="status">
          <span aria-hidden="true">ℹ</span>
          <div>
            <strong>Missing Information in readable text:</strong>
            <ul style={{ margin: 'var(--space-2) 0 0 var(--space-4)', padding: 0 }}>
              {answer.missing_information.map((item, idx) => (
                <li key={idx}>
                  {item.message || (typeof item === 'string' ? item : JSON.stringify(item))}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Claims */}
      {answer.claims && answer.claims.length > 0 && (
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Direct Statements &amp; Supported Claims</h3>
          <ul className={styles.itemList}>
            {answer.claims.map((claim) => (
              <li key={claim.claim_id} className={styles.itemCard}>
                <div className={styles.itemHeader}>
                  <span className={styles.itemText}>{claim.text}</span>
                  <span className={styles.classificationTag}>{claim.classification}</span>
                </div>
                {claim.evidence && claim.evidence.length > 0 && (
                  <div className={styles.citationsRow}>
                    {claim.evidence.map((ev, i) => (
                      <SourceCitation
                        key={i}
                        evidence={ev}
                        onClick={() => onOpenSourceView(ev.page, ev.quote, ev.sid)}
                      />
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Conflicts */}
      {answer.conflicts && answer.conflicts.length > 0 && (
        <div className={styles.section}>
          <h3 className={styles.sectionTitle} style={{ color: 'var(--color-status-error)' }}>
            Detected Clause Conflicts
          </h3>
          <ul className={styles.itemList}>
            {answer.conflicts.map((conf) => (
              <li key={conf.item_id} className={`${styles.itemCard} ${styles.conflictItem}`}>
                <p className={styles.itemText}>{conf.text}</p>
                {conf.evidence && conf.evidence.length > 0 && (
                  <div className={styles.citationsRow}>
                    {conf.evidence.map((ev, i) => (
                      <SourceCitation
                        key={i}
                        evidence={ev}
                        onClick={() => onOpenSourceView(ev.page, ev.quote, ev.sid)}
                      />
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Concerns */}
      {answer.concerns && answer.concerns.length > 0 && (
        <div className={styles.section}>
          <h3 className={styles.sectionTitle} style={{ color: 'var(--color-status-warn)' }}>
            Areas of Note / Potential Concerns
          </h3>
          <ul className={styles.itemList}>
            {answer.concerns.map((item) => (
              <li key={item.item_id} className={`${styles.itemCard} ${styles.concernItem}`}>
                <p className={styles.itemText}>{item.text}</p>
                {item.evidence && item.evidence.length > 0 && (
                  <div className={styles.citationsRow}>
                    {item.evidence.map((ev, i) => (
                      <SourceCitation
                        key={i}
                        evidence={ev}
                        onClick={() => onOpenSourceView(ev.page, ev.quote, ev.sid)}
                      />
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Ambiguities */}
      {answer.ambiguities && answer.ambiguities.length > 0 && (
        <div className={styles.section}>
          <h3 className={styles.sectionTitle} style={{ color: 'hsl(30, 70%, 52%)' }}>
            Ambiguous Language
          </h3>
          <ul className={styles.itemList}>
            {answer.ambiguities.map((item) => (
              <li key={item.item_id} className={`${styles.itemCard} ${styles.ambiguityItem}`}>
                <p className={styles.itemText}>{item.text}</p>
                {item.evidence && item.evidence.length > 0 && (
                  <div className={styles.citationsRow}>
                    {item.evidence.map((ev, i) => (
                      <SourceCitation
                        key={i}
                        evidence={ev}
                        onClick={() => onOpenSourceView(ev.page, ev.quote, ev.sid)}
                      />
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Interpretations */}
      {answer.interpretations && answer.interpretations.length > 0 && (
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Clause Interpretations</h3>
          <ul className={styles.itemList}>
            {answer.interpretations.map((item) => (
              <li key={item.item_id} className={styles.itemCard}>
                <p className={styles.itemText}>{item.text}</p>
                {item.evidence && item.evidence.length > 0 && (
                  <div className={styles.citationsRow}>
                    {item.evidence.map((ev, i) => (
                      <SourceCitation
                        key={i}
                        evidence={ev}
                        onClick={() => onOpenSourceView(ev.page, ev.quote, ev.sid)}
                      />
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Process Ledger — Process metadata only, no chain-of-thought */}
      <details className={styles.ledgerDetails}>
        <summary className={styles.ledgerSummary}>
          Why this answer? (Process &amp; Source Ledger)
        </summary>
        <div className={styles.ledgerContent}>
          <div>Status outcome: <strong>{answer.status}</strong></div>
          <div>Retrieved pages: {uniquePages.length > 0 ? uniquePages.join(', ') : 'None'}</div>
          <div>Evidence sentence IDs: {uniqueSids.length > 0 ? uniqueSids.join(', ') : 'None'}</div>
          <div>External law required: {answer.external_law_required ? 'Yes' : 'No'}</div>
          <div>Legal verdict provided: No (Always null by policy)</div>
        </div>
      </details>

      <div style={{ textAlign: 'center', marginTop: 'var(--space-2)' }}>
        <p className="legal-caveat">
          LexiGuard presents factual agreement text and triage indicators only. It does not determine
          legality or enforceability.
        </p>
      </div>
    </div>
  );
}
