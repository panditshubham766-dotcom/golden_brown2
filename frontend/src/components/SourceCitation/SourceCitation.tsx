/**
 * SourceCitation — renders an evidence item with source metadata.
 *
 * Rules:
 * - Quote is immutable — never alter, truncate mid-sentence, or reformat for meaning.
 * - Always label as "Quoted source text — not LexiGuard's legal assessment."
 * - OCR-derived content is visibly marked.
 * - Physical page label shown separately from any printed label.
 * - Clicking opens the source viewer (only if onOpenPage is provided).
 * - Never fabricate a highlight, offset, or location that was not returned by the backend.
 */

import styles from './SourceCitation.module.css';
import { Button } from '../Button/Button';
import type { EvidenceItem } from '../../api/contracts';

interface SourceCitationProps {
  evidence: EvidenceItem;
  onOpenPage?: (physicalPage: number, sid: string) => void;
  onClick?: () => void;
}

export function SourceCitation({ evidence, onOpenPage, onClick }: SourceCitationProps) {
  const { page, section, quote, ocr_derived, sid } = evidence;
  const handleOpen = () => {
    if (onClick) {
      onClick();
    } else if (onOpenPage) {
      onOpenPage(page, sid);
    }
  };

  return (
    <div className={styles.citation}>
      <div className={styles.meta}>
        <span className={styles.pageLabel}>
          Page {page}
          {section ? ` · ${section}` : ''}
        </span>
        {ocr_derived && (
          <span className="ocr-badge" title="This text was derived from OCR — check the page image for accuracy">
            OCR-derived — check the page image
          </span>
        )}
        {(onOpenPage || onClick) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleOpen}
            aria-label={`Open source page ${page}`}
            className={styles.openBtn}
          >
            View page ↗
          </Button>
        )}
      </div>
      <div>
        <div className="source-quote-label">Quoted source text — not LexiGuard's legal assessment</div>
        <blockquote className="source-quote" aria-label="Source quotation">
          {quote}
        </blockquote>
      </div>
    </div>
  );
}
