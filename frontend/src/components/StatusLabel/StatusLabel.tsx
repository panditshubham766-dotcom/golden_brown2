import styles from './StatusLabel.module.css';
import type { ClaimClassification, AskStatus, ReviewTopicStatus } from '../../api/contracts';

/**
 * Maps backend classification/status values to human-readable labels and CSS classes.
 * Color is a supplementary cue only — text label always carries the meaning.
 */

interface StatusLabelProps {
  value?: ClaimClassification | AskStatus | ReviewTopicStatus | string;
  status?: ClaimClassification | AskStatus | ReviewTopicStatus | string;
  /** Explicit override label — use when the backend value needs specific UI wording */
  label?: string;
  className?: string;
}

function getClaimStyle(value: string): { cssClass: string; text: string } {
  switch (value.toUpperCase()) {
    case 'DIRECT':
      return { cssClass: styles.direct, text: 'Stated in the agreement' };
    case 'SUPPORTED':
      return { cssClass: styles.restatement, text: 'Restatement' };
    case 'INTERPRETIVE':
    case 'INTERPRETATION':
      return { cssClass: styles.interpretation, text: 'Interpretation' };
    case 'AMBIGUOUS':
    case 'AMBIGUITY':
      return { cssClass: styles.ambiguity, text: 'Ambiguity' };
    case 'CONFLICTING':
    case 'CONFLICT':
      return { cssClass: styles.conflict, text: 'Possible conflict' };
    case 'GENERAL_EXPLANATION':
      return { cssClass: styles.general, text: 'General definition (not from your document)' };
    case 'NOT_LOCATED':
      return { cssClass: styles.notFound, text: 'Not located' };
    case 'INSUFFICIENT_EVIDENCE':
      return { cssClass: styles.limited, text: 'Insufficient evidence' };
    case 'OUT_OF_SCOPE':
      return { cssClass: styles.notFound, text: 'Out of scope' };
    // Review topic statuses
    case 'FOUND':
      return { cssClass: styles.found, text: 'Found' };
    case 'NOT_FOUND':
      return { cssClass: styles.notFound, text: 'Not located' }; // per spec: present as "Not located"
    case 'NOT_ASSESSED':
      return { cssClass: styles.notAssessed, text: 'Not assessed' };
    case 'POSSIBLE_CONFLICT':
      return { cssClass: styles.possibleConflict, text: 'Possible conflict' };
    // Ask overall statuses
    case 'ANSWERED':
      return { cssClass: styles.answered, text: 'Answered' };
    case 'LIMITED':
      return { cssClass: styles.limited, text: 'Limited' };
    case 'LEGAL_LIMIT':
      return { cssClass: styles.legalLimit, text: 'Legal boundary' };
    case 'ERROR_LOCAL_MODEL_UNAVAILABLE':
      return { cssClass: styles.error, text: 'Local model unavailable' };
    case 'ERROR_PROCESSING':
      return { cssClass: styles.error, text: 'Processing error' };
    // Concern type
    case 'CONCERN':
      return { cssClass: styles.concern, text: 'Concern' };
    default:
      // Unknown values should NOT be silently coerced to a success state
      return { cssClass: styles.notAssessed, text: `Unknown: ${value}` };
  }
}

export function StatusLabel({ value, status, label, className }: StatusLabelProps) {
  const effectiveValue = value ?? status ?? '';
  const { cssClass, text } = getClaimStyle(effectiveValue);
  return (
    <span className={`${styles.label} ${cssClass} ${className ?? ''}`}>
      {label ?? text}
    </span>
  );
}
